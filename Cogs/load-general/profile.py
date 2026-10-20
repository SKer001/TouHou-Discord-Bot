import discord
from discord import app_commands
from discord.ext import commands
from Database.db_manager import get_or_create_user, update_visibility
from .general_embeds import build_profile_embed, get_avatar_dominant_color


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="profile", description="查看個人或指定成員的幻想鄉個人資料卡")
    @app_commands.describe(
        user="【可選】選擇要查看的伺服器成員 (留空則查看自己)",
        visibility="【可選】設定您的資料卡公開狀態 (True: 公開 / False: 私人)"
    )
    async def profile_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.User | discord.Member = None,
        visibility: bool = None
    ):
        # 1. 優先處理隱私變更 (始終只修改指令觸發者自身)
        if visibility is not None:
            await update_visibility(interaction.user.id, visibility)
            user = interaction.user

        # 2. 決定查詢目標（未指定時預設為指令觸發者自身）
        target_user = user or interaction.user
        is_self = (target_user.id == interaction.user.id)

        # 3. 從 SQLite 撈取/自動建立玩家資料
        target_data = await get_or_create_user(target_user.id)

        # 4. 隱私權限檢查
        target_is_public = bool(target_data.get("is_public", 1))

        if not is_self and not target_is_public:
            embed = discord.Embed(
                title="🔒 無法存取個人資料",
                description=f"**{target_user.display_name}** 已將其資料卡設為私人，無法公開檢視。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 5. 從 Utils 呼叫繪製工具
        dominant_color = await get_avatar_dominant_color(target_user)
        embed = build_profile_embed(target_user, target_data, dominant_color)

        is_ephemeral = (visibility is not None) or (is_self and not target_is_public)
        await interaction.response.send_message(embed=embed, ephemeral=is_ephemeral)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
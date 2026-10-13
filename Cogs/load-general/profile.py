import io
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image
from Database.db_manager import get_or_create_user, update_visibility


# ---------------------------------------------------------
# 🎨 輔助函式：從 Discord 頭像 URL 提取主色調 (Dominant Color)
# ---------------------------------------------------------
async def get_avatar_dominant_color(user: discord.User | discord.Member) -> discord.Color:
    """下載使用者頭像並擷取出現頻率最高的代表色彩，回傳 discord.Color 物件"""
    try:
        # 讀取頭像 Byte 資料 (限制尺寸為 64x64 以大幅提升運算速度)
        avatar_bytes = await user.display_avatar.with_size(64).read()

        # 使用 Pillow 開啟圖片並轉為 RGB 模式
        image = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")

        # 使用 quantize(colors=1) 提取圖片出現次數最多的代表色 (主色)
        quantized = image.quantize(colors=1, method=2)
        palette = quantized.getpalette()[:3]  # 取得 R, G, B 三原色

        return discord.Color.from_rgb(palette[0], palette[1], palette[2])

    except Exception:
        # 若抓取失敗 (如網路問題或圖片格式異常)，回傳預設的東方紅/主題色作為備用
        return discord.Color.red()


# ---------------------------------------------------------
# 🛠️ 核心 Embed 渲染輔助函式
# ---------------------------------------------------------
def build_profile_embed(
    user: discord.User | discord.Member,
    user_data: dict,
    dominant_color: discord.Color
) -> discord.Embed:
    """根據玩家資料與頭像主色繪製 Embed 個人資料卡"""
    money = user_data.get("money", 1000)
    level = user_data.get("level", 1)
    exp = user_data.get("exp", 0)
    inventory = user_data.get("inventory", {})
    is_public = bool(user_data.get("is_public", 1))

    # 計算背包總道具數量
    total_items = sum(inventory.values()) if isinstance(inventory, dict) else 0

    # 決定邊條色彩：若設為私人則顯示暗灰；若公開則顯示頭像代表色
    embed_color = dominant_color if is_public else discord.Color.dark_gray()

    embed = discord.Embed(
        title=f"🌸 {user.display_name} 的幻想鄉通行證",
        color=embed_color,
        timestamp=discord.utils.utcnow()
    )

    # 設定使用者頭像
    embed.set_thumbnail(url=user.display_avatar.url)

    # 基礎數據欄位
    embed.add_field(name="💰 賽錢 (Money)", value=f"`{money:,}` 兩", inline=True)
    embed.add_field(name="⭐ 等級 (Level)", value=f"Lv. `{level}`", inline=True)
    embed.add_field(name="✨ 經驗值 (EXP)", value=f"`{exp}` EXP", inline=True)

    embed.add_field(name="🎒 背包物品數", value=f"`{total_items}` 件道具", inline=True)
    embed.add_field(name="🔒 卡片狀態", value="`🌐 公開`" if is_public else "`🔒 私人`", inline=True)

    embed.set_footer(text="TouHouBot Profile System • 幻想鄉居民登記")
    return embed


# ---------------------------------------------------------
# 🤖 Profile Cog 核心類別
# ---------------------------------------------------------
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
            # 若使用者調整了 visibility，強制將目標鎖定回自己
            user = interaction.user

        # 2. 決定查詢目標（未指定時預設為指令觸發者自身）
        target_user = user or interaction.user
        is_self = (target_user.id == interaction.user.id)

        # 3. 從 SQLite 撈取/自動建立玩家資料
        target_data = await get_or_create_user(target_user.id)

        # 4. 隱私權限檢查
        target_is_public = bool(target_data.get("is_public", 1))

        # 若查看他人，且對方設定為私人 ➔ 阻擋檢視
        if not is_self and not target_is_public:
            embed = discord.Embed(
                title="🔒 無法存取個人資料",
                description=f"**{target_user.display_name}** 已將其資料卡設為私人，無法公開檢視。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 5. 🎨 動態擷取目標使用者的頭像代表色
        dominant_color = await get_avatar_dominant_color(target_user)

        # 6. 渲染 Embed 頁面
        embed = build_profile_embed(target_user, target_data, dominant_color)

        # 7. 決定訊息顯示方式：
        #    若剛調整過 visibility、或是查看自己且設為私人，使用私密訊息 (ephemeral=True)
        is_ephemeral = (visibility is not None) or (is_self and not target_is_public)

        await interaction.response.send_message(embed=embed, ephemeral=is_ephemeral)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
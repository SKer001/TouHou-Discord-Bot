import os
import discord
from discord import app_commands
from discord.ext import commands
from Database.db_manager import reset_daily as reset_main_daily, add_money, add_exp

# 👑 最高管理者 Discord ID 鎖定
ADMIN_ID = 403895664666214400

# ---------------------------------------------------------
# 🎛️ ReloadCogSelect：下拉選單選單邏輯
# ---------------------------------------------------------
class ReloadCogSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # 動態掃描目前機器人已載入的所有 Extensions (Cogs)
        options = []
        for ext in list(bot.extensions.keys()):
            options.append(
                discord.SelectOption(
                    label=ext,
                    description=f"重新載入 {ext} 模組",
                    emoji="🔄",
                    value=ext
                )
            )

        # 超過 25 個時截斷 (Discord Select 限制最多 25 項)
        options = options[:25] if options else [
            discord.SelectOption(label="無可用的 Cog 模組", value="none")
        ]

        super().__init__(
            placeholder="請選擇要重新載入 (Reload) 的 Cog 模組...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # 權限驗證
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限操作此選單！", ephemeral=True)
            return

        selected_cog = self.values[0]
        if selected_cog == "none":
            await interaction.response.send_message("❌ 目前沒有可重新載入的模組！", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # 重新載入模組
            await self.bot.reload_extension(selected_cog)
            await self.bot.tree.sync()

            embed = discord.Embed(
                title="✅ 模組重新載入成功",
                description=f"已成功重新載入模組：`{selected_cog}`\n並且完成了指令同步 (`tree.sync`)！",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ 模組重新載入失敗",
                description=f"載入 `{selected_cog}` 時發生錯誤：\n```py\n{e}\n```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
class ReloadCogView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=60)  # 60 秒後選單過期
        self.add_item(ReloadCogSelect(bot))

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    # ---------------------------------------------------------
    # 🔄 1. 動態重新載入模組 (/reload)
    # ---------------------------------------------------------
    @app_commands.command(name="reload", description="【開發者專用】動態重新載入 Cog 模組")
    @app_commands.default_permissions(administrator=True)
    async def reload_cmd(self, interaction: discord.Interaction):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限使用此開發者指令！", ephemeral=True)
            return

        embed = discord.Embed(
            title="🛠️ TouHouBot 模組重載控制台",
            description="請從下方的下拉選單中選擇您想要重新載入 (Reload) 的 Cog 模組：",
            color=discord.Color.blue()
        )
        embed.set_footer(text="TouHouBot Admin System • 選單將於 60 秒後自動失效")

        view = ReloadCogView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ---------------------------------------------------------
    # 🛠️ 2. 重置每日簽到 (/reset_daily)
    # ---------------------------------------------------------
    @app_commands.command(name="reset_daily", description="【開發者專用】重置指定成員或自己的每日簽到狀態")
    @app_commands.describe(target="【可選】指定要重置的成員 (留空則重置自己)")
    @app_commands.default_permissions(administrator=True)
    async def reset_daily_cmd(
        self,
        interaction: discord.Interaction,
        target: discord.User | discord.Member = None
    ):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限使用此開發者指令！", ephemeral=True)
            return

        target_user = target or interaction.user

        # 1. 重置主資料庫 (database.db)
        await reset_main_daily(target_user.id)

        # 2. 同步重置 daily.py 獨立資料庫 (daily.db)
        try:
            import aiosqlite
            daily_db_path = os.path.join(
                os.path.dirname(__file__), "..", "load-general", "daily.db"
            )
            if os.path.exists(daily_db_path):
                async with aiosqlite.connect(daily_db_path) as db:
                    await db.execute(
                        "UPDATE users_daily SET last_daily = NULL WHERE user_id = ?",
                        (target_user.id,)
                    )
                    await db.commit()
        except Exception as e:
            print(f"⚠️ [Admin] 同步重置 daily.db 時出錯: {e}")

        await interaction.response.send_message(
            f"🛠️ [Dev] 已成功重置 **{target_user.display_name}** 的 `/daily` 簽到狀態！",
            ephemeral=True
        )

    # ---------------------------------------------------------
    # 💰 3. 調整玩家賽錢 (/add_money)
    # ---------------------------------------------------------
    @app_commands.command(name="add_money", description="【開發者專用】給予或扣除指定成員的賽錢")
    @app_commands.describe(
        target="要調整賽錢的成員",
        amount="要調整的數額 (輸入負數則為扣除)"
    )
    @app_commands.default_permissions(administrator=True)
    async def add_money_cmd(
        self,
        interaction: discord.Interaction,
        target: discord.User | discord.Member,
        amount: int
    ):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限使用此開發者指令！", ephemeral=True)
            return

        current_money = await add_money(target.id, amount)
        action_text = "給予" if amount >= 0 else "扣除"
        await interaction.response.send_message(
            f"🛠️ [Dev] 已成功向 **{target.display_name}** {action_text} 賽錢 `{abs(amount):,}` 兩！\n目前總金額：`{current_money:,}` 兩",
            ephemeral=True
        )

    # ---------------------------------------------------------
    # ✨ 4. 調整玩家經驗值與火力 (/add_exp)
    # ---------------------------------------------------------
    @app_commands.command(name="add_exp", description="【開發者專用】給予或扣除指定成員經驗值 (自動驗算對應 P點)")
    @app_commands.describe(
        target="要調整經驗值的成員",
        amount="要調整的經驗值數量 (輸入負數則為扣除)"
    )
    @app_commands.default_permissions(administrator=True)
    async def add_exp_cmd(
        self,
        interaction: discord.Interaction,
        target: discord.User | discord.Member,
        amount: int
    ):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限使用此開發者指令！", ephemeral=True)
            return

        exp_result = await add_exp(target.id, amount)
        old_p = exp_result["old_p"]
        new_p = exp_result["new_p"]
        current_exp = exp_result["current_exp"]

        status_text = "給予" if amount >= 0 else "扣除"
        msg = (
            f"🛠️ [Dev] 已成功向 **{target.display_name}** {status_text} `{abs(amount):,}` EXP！\n"
            f"🔴 火力變化：`{old_p:.1f} P` ➔ **`{new_p:.1f} P`**\n"
            f"✨ 剩餘經驗：`{current_exp:,}` EXP"
        )

        if exp_result.get("leveled_up"):
            msg += "\n💥 **(POWER UP! 火力提升)**"
        elif exp_result.get("is_degraded"):
            msg += "\n📉 **(火力降階)**"

        await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
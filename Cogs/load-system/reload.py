import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------
# 1. 下拉式選單 Component
# ---------------------------------------------------------
class ExtensionSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, loaded_extensions: list[str]):
        self.bot = bot

        # 將已載入的 extension 列表轉為 SelectOption
        options = []
        for ext in loaded_extensions:
            # 取出漂亮的顯示名稱，例如 "Cogs.load-system.reload" -> "load-system.reload"
            short_name = ext.replace("Cogs.", "").replace("Logger.", "").replace("load-", "")
            options.append(
                discord.SelectOption(
                    label=short_name,
                    value=ext,
                    description=f"重新載入 {ext}",
                    emoji="🔄"
                )
            )

        # 最多顯示 25 個選項 (Discord API 限制)
        options = options[:25]

        super().__init__(
            placeholder="請選擇要 Reload 的 Cog 模組...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_ext = self.values[0]
        await interaction.response.defer(ephemeral=True)

        try:
            # 重新載入選中的 Cog
            await self.bot.reload_extension(selected_ext)
            
            embed = discord.Embed(
                title="✅ 模組重新載入成功！",
                description=f"已成功 Reload 模組：`{selected_ext}`",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ 模組 Reload 失敗！",
                description=f"Reload `{selected_ext}` 時發生錯誤：\n```python\n{e}\n```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------
# 2. 包含選單的 View
# ---------------------------------------------------------
class ExtensionSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, loaded_extensions: list[str]):
        super().__init__(timeout=60)  # 60 秒後選單自動失效
        self.add_item(ExtensionSelect(bot, loaded_extensions))


# ---------------------------------------------------------
# 3. Reload Cog 核心類別
# ---------------------------------------------------------
class Reload(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reload", description="【管理員專用】選擇並重新載入指定的 Cog 模組")
    @app_commands.default_permissions(administrator=True)  # 限制只有管理員能看到/使用此指令
    async def reload_select(self, interaction: discord.Interaction):
        # 取得所有目前已載入的 Extensions
        loaded_extensions = list(self.bot.extensions.keys())

        if not loaded_extensions:
            await interaction.response.send_message("❌ 目前沒有任何已載入的模組！", ephemeral=True)
            return

        view = ExtensionSelectView(self.bot, loaded_extensions)
        embed = discord.Embed(
            title="🔄 模組熱插拔 (Reload Extensions)",
            description="請從下方選單選擇您要重新載入的模組：\n選單將於 **60 秒** 後自動過期。",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Reload(bot))
import os
import discord
from discord import app_commands
from discord.ext import commands

ADMIN_ID = 403895664666214400


# ---------------------------------------------------------
# 🎛️ Reload 下拉選單 UI
# ---------------------------------------------------------
class ReloadCogSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
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

        options = options[:25] if options else [
            discord.SelectOption(label="無可用的 Cog 模組", value="none")
        ]

        super().__init__(
            placeholder="請選擇要重新載入 (Reload) 的 Cog 模組...",
            min_values=1, max_values=1, options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限操作此選單！", ephemeral=True)
            return

        selected_cog = self.values[0]
        if selected_cog == "none":
            await interaction.response.send_message("❌ 目前沒有可重新載入的模組！", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
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
        super().__init__(timeout=60)
        self.add_item(ReloadCogSelect(bot))


# ---------------------------------------------------------
# 🤖 SysAdmin Cog
# ---------------------------------------------------------
class SysAdmin(commands.GroupCog, group_name="admin-sys", group_description="【開發者專用】系統與模組維護指令"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # 1. 🔄 /reload 重載模組
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
        embed.set_footer(text="TouHouBot SysAdmin • 選單將於 60 秒後自動失效")

        view = ReloadCogView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # 2. ⚡ /sync 手動同步指令
    @app_commands.command(name="sync", description="【開發者專用】強制與 Discord API 同步斜線指令 (Slash Commands)")
    @app_commands.default_permissions(administrator=True)
    async def sync_cmd(self, interaction: discord.Interaction):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限使用此開發者指令！", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"✅ 成功同步 `{len(synced)}` 個全域斜線指令到 Discord！", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 同步指令時發生錯誤：\n```py\n{e}\n```", ephemeral=True)

    # 3. 🛑 /shutdown 安全關閉機器人
    @app_commands.command(name="shutdown", description="【開發者專用】安全儲存並關閉機器人")
    @app_commands.default_permissions(administrator=True)
    async def shutdown_cmd(self, interaction: discord.Interaction):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限使用此開發者指令！", ephemeral=True)
            return

        await interaction.response.send_message("⚙️ 機器人正在安全關閉中... 下次見！", ephemeral=True)
        await self.bot.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(SysAdmin(bot))
import os
import discord
from discord import ui
from discord import app_commands
from discord.ext import commands

from Utils.config import is_admin
from Utils.components import send_notice, notice_container



# ---------------------------------------------------------
# 🎛️ Reload 控制台 (Components V2)
# ---------------------------------------------------------
class ReloadCogView(ui.LayoutView):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=60)
        self.bot = bot
        self.build()

    def build(self, result: ui.Container | None = None):
        """控制台本體；result 為上一次重載的結果，顯示在控制台上方"""
        self.clear_items()
        if result:
            self.add_item(result)

        options = [
            discord.SelectOption(label=ext, description=f"重新載入 {ext} 模組", emoji="🔄", value=ext)
            for ext in list(self.bot.extensions.keys())
        ][:25] or [discord.SelectOption(label="無可用的 Cog 模組", value="none")]

        select = ui.Select(placeholder="請選擇要重新載入 (Reload) 的 Cog 模組...", min_values=1, max_values=1, options=options)
        select.callback = self.select_callback

        container = ui.Container(accent_color=discord.Color.blue())
        container.add_item(ui.TextDisplay(
            "## 🛠️ TouHouBot 模組重載控制台\n"
            "請從下方的下拉選單中選擇您想要重新載入 (Reload) 的 Cog 模組："
        ))
        container.add_item(ui.ActionRow(select))
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay("-# TouHouBot SysAdmin • 選單將於 60 秒後自動失效"))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 您沒有權限操作此選單！")
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        selected_cog = interaction.data["values"][0]
        if selected_cog == "none":
            await send_notice(interaction, "❌ 目前沒有可重新載入的模組！")
            return

        await interaction.response.defer()

        try:
            await self.bot.reload_extension(selected_cog)
            await self.bot.tree.sync()
            result = notice_container(
                f"### ✅ 模組重新載入成功\n已成功重新載入模組：`{selected_cog}`\n並且完成了指令同步 (`tree.sync`)！"
            )
        except Exception as e:
            result = notice_container(
                f"### ❌ 模組重新載入失敗\n載入 `{selected_cog}` 時發生錯誤：\n```py\n{e}\n```"
            )

        self.build(result)
        await interaction.edit_original_response(view=self)


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
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 您沒有權限使用此開發者指令！")
            return

        view = ReloadCogView(self.bot)
        await interaction.response.send_message(view=view, ephemeral=True)

    # 2. ⚡ /sync 手動同步指令
    @app_commands.command(name="sync", description="【開發者專用】強制與 Discord API 同步斜線指令 (Slash Commands)")
    @app_commands.default_permissions(administrator=True)
    async def sync_cmd(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 您沒有權限使用此開發者指令！")
            return

        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await send_notice(interaction, f"✅ 成功同步 `{len(synced)}` 個全域斜線指令到 Discord！")
        except Exception as e:
            await send_notice(interaction, f"❌ 同步指令時發生錯誤：\n```py\n{e}\n```")

    # 3. 🛑 /shutdown 安全關閉機器人
    @app_commands.command(name="shutdown", description="【開發者專用】安全儲存並關閉機器人")
    @app_commands.default_permissions(administrator=True)
    async def shutdown_cmd(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 您沒有權限使用此開發者指令！")
            return

        await send_notice(interaction, "⚙️ 機器人正在安全關閉中... 下次見！")
        await self.bot.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(SysAdmin(bot))

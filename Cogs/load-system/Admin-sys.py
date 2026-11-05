import discord
from discord import ui
from discord import app_commands
from discord.ext import commands

from Utils.config import is_admin
from Utils.components import send_notice, notice_container
from Utils import reloader

RELOAD_ALL = "__all__"
SELF_EXT = __name__   # 這個檔案本身 (Cogs.load-system.Admin-sys)：全部重載時跳過，正在執行中


def reload_report(selected: str, r: dict, synced: int | None, sync_error: str | None = None) -> ui.Container:
    lines = [f"🧩 畫面 / 資料層：重載 `{len(r['support'])}` 個模組"]
    if selected == RELOAD_ALL:
        lines.append(f"🔄 重載 `{len(r['reloaded'])}` 個指令模組")
        if r["loaded"]:
            lines.append("🆕 新載入：" + "、".join(f"`{e}`" for e in r["loaded"]))
        if r["unloaded"]:
            lines.append("📤 已卸載 (檔案不在了)：" + "、".join(f"`{e}`" for e in r["unloaded"]))
        lines.append(f"-# `{SELF_EXT}` (這個控制台) 不會跟著全部重載，要的話從選單單獨選它")
    elif r["reloaded"]:
        lines.append(f"🔄 已重新載入 `{selected}`")
    failed = list(r["failed"]) + ([f"tree.sync: {sync_error}"] if sync_error else [])
    if synced is not None:
        lines.append(f"⚡ 同步了 `{synced}` 個斜線指令（新指令可能要等一下或重開 Discord 才看得到）")
    if failed:
        lines.append("```py\n" + "\n".join(failed)[:1500] + "\n```")
    title = "### ⚠️ 重載完成，但有錯誤" if failed else "### ✅ 模組重新載入成功"
    return notice_container(title + "\n" + "\n".join(lines))


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

        options = [discord.SelectOption(
            label="全部重載", value=RELOAD_ALL, emoji="🔁",
            description="資料層、畫面、所有指令一起重載，並載入新增的模組")]
        options += [
            discord.SelectOption(label=ext, description=f"重新載入 {ext}（含它的畫面）", emoji="🔄", value=ext)
            for ext in sorted(self.bot.extensions.keys())
        ]
        select = ui.Select(placeholder="請選擇要重新載入 (Reload) 的模組...", min_values=1, max_values=1, options=options[:25])
        select.callback = self.select_callback

        container = ui.Container(accent_color=discord.Color.blue())
        container.add_item(ui.TextDisplay(
            "## 🛠️ TouHouBot 模組重載控制台\n"
            "只改了某個功能的指令或畫面 ➔ 選那個模組；改了 Database / Utils、新增或搬移檔案 ➔ 選「🔁 全部重載」。"
        ))
        container.add_item(ui.ActionRow(select))
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay("-# TouHouBot SysAdmin • 選單將於 60 秒後自動失效 · 主控台也可以輸入 `reload`"))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 您沒有權限操作此選單！")
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        selected = interaction.data["values"][0]
        await interaction.response.defer()
        if selected == RELOAD_ALL:
            r = await reloader.reload_all(self.bot, skip={SELF_EXT})
        else:
            r = await reloader.reload_one(self.bot, selected)
        synced, sync_error = None, None
        try:
            synced = len(await self.bot.tree.sync())
        except Exception as e:
            sync_error = str(e)
        self.build(reload_report(selected, r, synced, sync_error))
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

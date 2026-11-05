"""
🛠️ /admin-event：開始 / 結束活動 (結束時會清空所有玩家的活動道具)
"""
import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Database.events import load_events
from Utils.config import is_admin
from Utils.components import send_notice, notice_container


class EndEventConfirm(ui.LayoutView):
    def __init__(self, admin_id: int, event: dict):
        super().__init__(timeout=60)
        self.admin_id, self.event = admin_id, event
        container = notice_container(
            f"⚠️ 確定要結束 **{event['emoji']} {event['name']}** 嗎？\n"
            "所有玩家神社倉庫裡的活動素材與活動料理都會被清除，活動客人也會離開。")
        ok = ui.Button(label="🗑️ 確定結束", style=discord.ButtonStyle.danger)
        ok.callback = self.on_ok
        cancel = ui.Button(label="✖️ 取消", style=discord.ButtonStyle.secondary)
        cancel.callback = self.on_cancel
        container.add_item(ui.ActionRow(ok, cancel))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.admin_id

    async def on_ok(self, interaction: discord.Interaction):
        n = await econ.admin_end_event(self.event["id"])
        self.clear_items()
        self.add_item(notice_container(f"✅ 已結束 **{self.event['name']}**，清除了 `{n}` 位玩家的活動道具。"))
        await interaction.response.edit_message(view=self)

    async def on_cancel(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(notice_container("✖️ 已取消。"))
        await interaction.response.edit_message(view=self)


class EventAdmin(commands.GroupCog, group_name="admin-event", group_description="【開發者專用】活動管理"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _deny(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return True
        return False

    async def event_autocomplete(self, interaction, current: str):
        return [app_commands.Choice(name=f"{e['emoji']} {e['name']} ({k})"[:100], value=k)
                for k, e in load_events().items() if current.lower() in f"{k} {e['name']}".lower()][:25]

    @app_commands.command(name="start", description="【開發者專用】開始活動 (days 留空 = 不設結束時間，測試用)")
    @app_commands.describe(event="活動", days="活動天數 (留空 = 不會自動結束)")
    @app_commands.autocomplete(event=event_autocomplete)
    async def start(self, interaction: discord.Interaction, event: str, days: app_commands.Range[int, 1, 60] | None = None):
        if await self._deny(interaction):
            return
        ev = load_events().get(event)
        if ev is None or not await econ.admin_start_event(event, days):
            await send_notice(interaction, "❌ 找不到這個活動。")
            return
        await send_notice(interaction, f"✅ 已開始 **{ev['emoji']} {ev['name']}**" + (f"，{days} 天後自動結束。" if days else "（沒有結束時間）。"))

    @app_commands.command(name="end", description="【開發者專用】結束活動並清空所有玩家的活動道具")
    @app_commands.describe(event="活動")
    @app_commands.autocomplete(event=event_autocomplete)
    async def end(self, interaction: discord.Interaction, event: str):
        if await self._deny(interaction):
            return
        ev = load_events().get(event)
        if ev is None:
            await send_notice(interaction, "❌ 找不到這個活動。")
            return
        await interaction.response.send_message(view=EndEventConfirm(interaction.user.id, ev), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventAdmin(bot))

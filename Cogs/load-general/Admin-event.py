"""
🛠️ /admin-event：開始 / 結束活動 (結束時會清空所有玩家的活動道具)

/admin-event start [開始時間] [持續天數] (2026-11-22 使用者定案)
  ➔ 只有自己看得到的畫面：多選選單勾要開的活動 ➔ 列出會發生什麼 ➔ 「✅ 確認開始」才執行
  - 開始時間用台灣時間 (2026-11-25 20:00 / 11-25 20:00)，留空 = 現在，過去的時間擋掉
  - 持續天數 0～365，0 或留空 = 一直持續
  - 沒勾到、進行中的活動在新活動的開始時間結束；排好還沒開始的取消；勾到但本來就在進行中的只改結束時間
/admin-event end 活動：進行中 ➔ 確認後結束並清活動道具；排好還沒開始 ➔ 取消排程
"""
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Database.events import load_events
from Utils.config import is_admin
from Utils.components import send_notice, notice_container
from Utils.gacha_pools import GACHA_POOLS
from .Components.shrine_components import ts

TW = timezone(timedelta(hours=8))   # 開始時間一律用台灣時間輸入
START_FORMATS = ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d", "%Y/%m/%d")
START_FORMATS_NO_YEAR = ("%m-%d %H:%M", "%m/%d %H:%M", "%m-%d", "%m/%d")
MAX_DAYS = 365
PHASE_TEXT = {"running": "🟢 進行中", "scheduled": "⏳ 排好了還沒開始", "off": "⚫ 沒在進行"}


def parse_start(text: str | None, now: datetime) -> datetime | None:
    """開始時間 (台灣時間) ➔ datetime (UTC)；留空 ➔ None (= 現在)；看不懂或是過去的時間 ➔ ValueError (訊息給使用者看)"""
    text = (text or "").strip()
    if not text:
        return None
    local = None
    for fmt in START_FORMATS:
        try:
            local = datetime.strptime(text, fmt)
            break
        except ValueError:
            pass
    if local is None:
        for fmt in START_FORMATS_NO_YEAR:
            try:
                local = datetime.strptime(f"{now.astimezone(TW).year}-{text}", f"%Y-{fmt}")   # 沒寫年份 = 今年
                break
            except ValueError:
                pass
    if local is None:
        raise ValueError(f"看不懂開始時間「{text}」，請用台灣時間 `2026-11-25 20:00` 或 `11-25 20:00`")
    start = local.replace(tzinfo=TW).astimezone(timezone.utc)
    if start < now - timedelta(minutes=1):
        raise ValueError(f"開始時間 {ts(start, 'f')} 已經過了；要現在開始就留空")
    return start


def _when(t: datetime | None, now: datetime) -> str:
    return "現在" if t is None or t <= now else ts(t, "f")


def plan_lines(plan: list[dict], now: datetime) -> list[str]:
    """確認畫面 / 結果畫面：每個活動會怎樣 + 會關掉的活動卡池"""
    lines, closing = [], []
    for p in plan:
        ev, a = p["event"], p["action"]
        name = f"{ev.get('emoji', '🎪')} **{ev.get('name', ev['id'])}**"
        end = f"{ts(p['ends_at'], 'f')} 結束" if p.get("ends_at") else "一直持續 (沒有結束時間)"
        if a == "start":
            lines.append(f"🟢 開始：{name} — {_when(p['started_at'], now)}開始，{end}")
        elif a == "extend":
            keep = "活動任務進度、玩家手上的活動道具都保留" + ("；到結束時間會清掉活動素材與活動料理" if p.get("ends_at") else "")
            lines.append(f"🔁 已經在進行中：{name} — 不重開，結束時間改成：{end}\n-# 　{keep}")
        elif a == "end_now":
            cleared = f" (清了 `{p['cleared']}` 位玩家)" if "cleared" in p else ""
            lines.append(f"⚫ 結束：{name} — **馬上結束**，清掉所有玩家的活動素材與活動料理{cleared}")
        elif a == "end_at":
            lines.append(f"⚫ 結束：{name} — {ts(p['ends_at'], 'f')} 結束 (到時候清掉所有玩家的活動素材與活動料理)")
        elif a == "cancel":
            lines.append(f"✖️ 取消排程：{name} (還沒開始，沒有活動道具要清)")
        src = ((ev.get("gacha") or {}).get("pool") or {}).get("from")
        if src in GACHA_POOLS:   # 這個活動開放的一般卡池 (紅霧異變 ➔ 紅魔鄉卡池)
            if a in ("end_now", "end_at", "cancel"):
                closing.append(f"⚠️ {ev.get('name', ev['id'])}結束後，{GACHA_POOLS[src]['name']}也會跟著關 (平常抽不到)")
            elif p.get("ends_at"):   # 開始 / 延長但有結束時間 ➔ 到時候一樣會關
                closing.append(f"⚠️ {ev.get('name', ev['id'])} {ts(p['ends_at'], 'f')} 結束後，"
                               f"{GACHA_POOLS[src]['name']}也會跟著關 (平常抽不到)")
    return lines + closing


class EventStartView(ui.LayoutView):
    """/admin-event start 的畫面：勾活動 ➔ 預覽 ➔ 確認"""
    def __init__(self, admin_id: int, start: datetime | None, days: int | None, events: dict, phases: dict):
        super().__init__(timeout=300)
        self.admin_id, self.start, self.days = admin_id, start, days
        self.events, self.phases = events, phases
        self.selected: list[str] = []
        self.plan: list[dict] = []
        self.done = False
        self.build()

    def header(self, now: datetime) -> str:
        dur = f"{self.days} 天" if self.days else "一直持續 (沒有結束時間)"
        return (f"## 🎪 開始活動\n"
                f"🕒 開始：{_when(self.start, now)} · ⏳ 持續：{dur}\n"
                f"-# 勾要開的活動 (可以多選)；沒勾到、進行中的活動會在開始時間結束。下面會先列出會發生什麼，按「✅ 確認開始」才執行")

    def build(self):
        now = datetime.now(timezone.utc)
        self.clear_items()
        container = ui.Container(accent_color=discord.Color.red())
        container.add_item(ui.TextDisplay(self.header(now)))
        options = [discord.SelectOption(label=f"{ev.get('emoji', '🎪')} {ev.get('name', eid)}"[:100], value=eid,
                                        description=PHASE_TEXT[self.phases.get(eid, "off")], default=eid in self.selected)
                   for eid, ev in list(self.events.items())[:25]]
        select = ui.Select(placeholder="🎪 勾要開始的活動…", min_values=1, max_values=len(options), options=options)
        select.callback = self.on_select
        container.add_item(ui.ActionRow(select))
        if self.plan:
            container.add_item(ui.Separator())
            container.add_item(ui.TextDisplay("### 📋 會發生的事\n" + "\n".join(plan_lines(self.plan, now))))
        ok = ui.Button(label="✅ 確認開始", style=discord.ButtonStyle.danger, disabled=not self.selected)
        ok.callback = self.on_ok
        cancel = ui.Button(label="✖️ 取消", style=discord.ButtonStyle.secondary)
        cancel.callback = self.on_cancel
        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(ok, cancel))
        self.add_item(container)
        self.select = select

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id or not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return False
        return True

    async def on_select(self, interaction: discord.Interaction):
        self.selected = [v for v in self.select.values if v in self.events]
        self.plan = await econ.preview_event_schedule(self.selected, self.start, self.days)
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_ok(self, interaction: discord.Interaction):
        if self.done or not self.selected:   # 連點：第二下直接忽略
            await interaction.response.defer()
            return
        self.done = True
        plan = await econ.admin_schedule_events(self.selected, self.start, self.days)
        self.clear_items()
        if plan is None:
            self.add_item(notice_container("❌ 找不到活動，沒有任何變動 (活動檔可能被移走了)。"))
        else:
            now = datetime.now(timezone.utc)
            self.add_item(notice_container("✅ 已套用：\n" + "\n".join(plan_lines(plan, now))))
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_cancel(self, interaction: discord.Interaction):
        self.done = True
        self.clear_items()
        self.add_item(notice_container("✖️ 已取消，活動沒有任何變動。"))
        await interaction.response.edit_message(view=self)
        self.stop()


class EndEventConfirm(ui.LayoutView):
    def __init__(self, admin_id: int, event: dict, phase: str = "running"):
        super().__init__(timeout=60)
        self.admin_id, self.event, self.phase = admin_id, event, phase
        self.done = False
        if phase == "scheduled":
            text = (f"⚠️ 確定要取消 **{event['emoji']} {event['name']}** 的排程嗎？\n"
                    "它還沒開始，沒有活動道具要清。")
        else:
            text = (f"⚠️ 確定要結束 **{event['emoji']} {event['name']}** 嗎？\n"
                    "所有玩家神社倉庫裡的活動素材與活動料理都會被清除，活動客人也會離開。")
        src = ((event.get("gacha") or {}).get("pool") or {}).get("from")
        if src in GACHA_POOLS:
            text += f"\n{GACHA_POOLS[src]['name']}也會跟著關 (平常抽不到)。"
        container = notice_container(text)
        ok = ui.Button(label="🗑️ 確定取消排程" if phase == "scheduled" else "🗑️ 確定結束", style=discord.ButtonStyle.danger)
        ok.callback = self.on_ok
        cancel = ui.Button(label="✖️ 取消", style=discord.ButtonStyle.secondary)
        cancel.callback = self.on_cancel
        container.add_item(ui.ActionRow(ok, cancel))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.admin_id

    async def on_ok(self, interaction: discord.Interaction):
        if self.done:
            await interaction.response.defer()
            return
        self.done = True
        n = await econ.admin_end_event(self.event["id"])
        self.clear_items()
        if self.phase == "scheduled":
            self.add_item(notice_container(f"✅ 已取消 **{self.event['name']}** 的排程。"))
        else:
            self.add_item(notice_container(f"✅ 已結束 **{self.event['name']}**，清除了 `{n}` 位玩家的活動道具。"))
        await interaction.response.edit_message(view=self)

    async def on_cancel(self, interaction: discord.Interaction):
        self.done = True
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

    @app_commands.command(name="start", description="【開發者專用】開始活動：勾一個或多個活動，可以排開始時間 (沒勾到的進行中活動會在開始時間結束)")
    @app_commands.describe(start="開始時間，台灣時間 (例 2026-11-25 20:00 或 11-25 20:00；留空 = 現在)",
                           days="持續天數 (0 或留空 = 一直持續，不會自動結束)")
    async def start(self, interaction: discord.Interaction, start: str | None = None,
                    days: app_commands.Range[int, 0, MAX_DAYS] | None = None):
        if await self._deny(interaction):
            return
        now = datetime.now(timezone.utc)
        try:
            start_at = parse_start(start, now)
        except ValueError as e:
            await send_notice(interaction, f"❌ {e}")
            return
        if days is not None and not 0 <= days <= MAX_DAYS:   # 繞過 Discord 的範圍限制也再擋一次
            await send_notice(interaction, f"❌ 持續天數要在 0～{MAX_DAYS} 天之間。")
            return
        events = load_events()
        if not events:
            await send_notice(interaction, "❌ Events/ 裡沒有任何活動檔。")
            return
        phases = {eid: await econ.get_event_phase(eid, now) for eid in events}
        view = EventStartView(interaction.user.id, start_at, days or None, events, phases)
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="end", description="【開發者專用】結束活動並清空所有玩家的活動道具 (還沒開始的 = 取消排程)")
    @app_commands.describe(event="活動")
    @app_commands.autocomplete(event=event_autocomplete)
    async def end(self, interaction: discord.Interaction, event: str):
        if await self._deny(interaction):
            return
        ev = load_events().get(event)
        if ev is None:
            await send_notice(interaction, "❌ 找不到這個活動。")
            return
        phase = await econ.get_event_phase(event)
        if phase == "off":
            await send_notice(interaction, f"↩️ **{ev['emoji']} {ev['name']}** 本來就沒在進行，也沒有排程。")
            return
        await interaction.response.send_message(view=EndEventConfirm(interaction.user.id, ev, phase), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventAdmin(bot))

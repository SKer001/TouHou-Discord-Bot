"""
🔔 主動通知 (DM)：/notify 設定面板 + 背景每 10 分鐘檢查一次、私訊玩家

- 要發哪些通知由 Database/Notify_DB_Manager.collect_notices 判斷 (純函式 + 時間差)，這裡只負責私訊
- 背景 loop 只在機器人真的登入後才啟動 (on_ready / cog_load 時 bot.is_ready())；
  tools/botcli.py 與測試載入這個 Cog 時不會啟動，也就不會真的發私訊
- 私訊失敗 (對方關閉私訊) 就略過並記錄，loop 不會因此掛掉
"""
import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

from Database import Notify_DB_Manager as ndm
from Database.notify_data import NOTIFY_TYPES
from Utils.components import send_notice
from .Components.notify_components import build_notice_dm, build_notify_settings


async def run_notify_once(bot: commands.Bot, now: datetime | None = None, sender=None) -> dict:
    """
    檢查一次並私訊 (背景 loop 與主控台 notify 共用)
    sender(user_id, notices) ➔ bool：預設用機器人私訊，測試可以換掉
    回傳 {"notices": 找到幾則, "users": 幾位玩家, "sent": 成功幾位, "failed": 失敗幾位}
    """
    now = now or datetime.now(timezone.utc)
    sender = sender or (lambda uid, ns: send_notice_dm(bot, uid, ns))
    notices = await ndm.collect_notices(now)
    by_user: dict[int, list[dict]] = {}
    for n in notices:
        if await ndm.claim(n["user_id"], n["kind"], n["key"], now):   # 先佔位，同一件事只發一次
            by_user.setdefault(n["user_id"], []).append(n)
    sent = failed = 0
    failed_users = []
    for uid, items in by_user.items():
        try:
            ok = await sender(uid, items)
        except Exception as e:   # 任何錯誤都不能讓 loop 掛掉
            print(f"⚠️ [Notify] 私訊 {uid} 時發生錯誤：{e}")
            ok = False
        if ok:
            sent += 1
        else:
            failed += 1
            failed_users.append((uid, items))
            await ndm.mark_failed(uid, [(n["kind"], n["key"]) for n in items])
    await ndm.prune_sent(now)
    if failed_users:
        await report_failures(bot, failed_users)
    return {"notices": len(notices), "users": len(by_user), "sent": sent, "failed": failed}


async def report_failures(bot, failed_users: list[tuple[int, list[dict]]]):
    """私訊失敗的玩家送到 log 頻道 (使用者 2026-11-11 指定)；沒有 Logger (botcli / 測試) 就略過"""
    logger = bot.get_cog("Logger") if bot is not None else None
    if logger is None:
        return
    lines = [f"<@{uid}>：" + "、".join(sorted({n['kind'] for n in items})) for uid, items in failed_users[:20]]
    if len(failed_users) > 20:
        lines.append(f"…還有 {len(failed_users) - 20} 位")
    try:
        await logger.send_alert_log("🔕 通知私訊失敗", "這些玩家收不到私訊 (可能關閉了私訊)，這幾則不會重送：\n" + "\n".join(lines),
                                    discord.Color.orange())
    except Exception as e:
        print(f"⚠️ [Notify] 送 log 頻道失敗：{e}")


async def send_notice_dm(bot: commands.Bot, user_id: int, notices: list[dict]) -> bool:
    """私訊一位玩家；找不到人或對方關閉私訊時回傳 False"""
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        view = ui.LayoutView()
        view.add_item(build_notice_dm(notices))
        await user.send(view=view)
        return True
    except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
        print(f"⚠️ [Notify] 無法私訊 {user_id}：{e}")
        return False


class NotifySettingsView(ui.LayoutView):
    """/notify 面板：每種通知一個開關；不能私訊的種類顯示「不支援私訊」且不能按"""

    def __init__(self, user_id: int, settings: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.settings = settings
        self.build()

    def build(self, result: str | None = None):
        self.clear_items()
        buttons = {}
        for kind, info in NOTIFY_TYPES.items():
            if not info["dm"]:
                buttons[kind] = ui.Button(label="不支援私訊", style=discord.ButtonStyle.secondary, disabled=True,
                                          custom_id=f"notify:{kind}")
                continue
            on = self.settings.get(kind, False)
            button = ui.Button(label="🔔 開啟中" if on else "🔕 已關閉",
                               style=discord.ButtonStyle.success if on else discord.ButtonStyle.secondary,
                               custom_id=f"notify:{kind}")
            button.callback = self._toggle(kind)
            buttons[kind] = button
        self.add_item(build_notify_settings(self.settings, buttons, result))

        all_on = ui.Button(label="全部開啟", emoji="🔔", style=discord.ButtonStyle.primary)
        all_on.callback = self.on_all_on
        all_off = ui.Button(label="全部關閉", emoji="🔕", style=discord.ButtonStyle.secondary)
        all_off.callback = self.on_all_off
        self.add_item(ui.ActionRow(all_on, all_off))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "🚫 這不是你的通知設定")
            return False
        return True

    def _toggle(self, kind: str):
        async def callback(interaction: discord.Interaction):
            new = not self.settings.get(kind, False)
            await ndm.set_enabled(self.user_id, kind, new)
            self.settings = await ndm.get_settings(self.user_id)
            info = NOTIFY_TYPES[kind]
            self.build(f"-# {'🔔 已開啟' if new else '🔕 已關閉'}「{info['emoji']} {info['name']}」")
            await interaction.response.edit_message(view=self)
        return callback

    async def on_all_on(self, interaction: discord.Interaction):
        await ndm.set_all(self.user_id, True)
        self.settings = await ndm.get_settings(self.user_id)
        self.build("-# 🔔 已全部開啟")
        await interaction.response.edit_message(view=self)

    async def on_all_off(self, interaction: discord.Interaction):
        await ndm.set_all(self.user_id, False)
        self.settings = await ndm.get_settings(self.user_id)
        self.build("-# 🔕 已全部關閉")
        await interaction.response.edit_message(view=self)


class NotifyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = asyncio.Lock()   # 背景 loop 與主控台不要同時跑

    async def cog_load(self):
        await ndm.init_notify_db()
        if self.bot.is_ready() and self.bot.user is not None:   # /admin-sys reload 時機器人早就登入了
            self._start_loop()

    async def cog_unload(self):
        self.notify_loop.cancel()

    def _start_loop(self):
        if not self.notify_loop.is_running():
            self.notify_loop.start()

    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.user is not None:
            self._start_loop()

    async def run_once(self, now: datetime | None = None, sender=None) -> dict:
        async with self.lock:
            return await run_notify_once(self.bot, now, sender)

    @tasks.loop(minutes=ndm.CHECK_INTERVAL_MINUTES)
    async def notify_loop(self):
        try:
            r = await self.run_once()
            if r["users"]:
                print(f"🔔 [Notify] 發出 {r['users']} 位玩家的通知（成功 {r['sent']}、失敗 {r['failed']}）")
        except Exception as e:   # 一輪失敗就等下一輪，不讓 loop 停掉
            print(f"❌ [Notify] 背景檢查失敗：{e}")

    @notify_loop.before_loop
    async def before_notify_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="notify", description="🔔 通知設定：選擇哪些事情要私訊你 (賽錢箱滿了、體力回滿、卡賣出…)")
    async def notify(self, interaction: discord.Interaction):
        settings = await ndm.get_settings(interaction.user.id)
        await interaction.response.send_message(view=NotifySettingsView(interaction.user.id, settings), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(NotifyCog(bot))

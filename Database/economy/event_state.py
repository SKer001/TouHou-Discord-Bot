"""
🎪 活動狀態 (進行中 / 排程 / 結束) 與當下規則 get_rules；經濟系統每個部分都會用到

從 Database/Economy_DB_Manager.py 拆出來的；外面一律照舊從 Database.Economy_DB_Manager 匯入 (入口)，不要直接匯入這裡。
"""
import json
from datetime import datetime, timedelta, timezone

from Database.User_DB_Manager import connect, _load_inventory
from Database.events import load_events, game_rules, event_item_ids
from Database.economy.common import _dt, _get_meta, _set_meta

# =========================================================
# 🎪 活動狀態 (economy_meta 的 event:<id> = {"status", "started_at", "ends_at"})
#   沒有紀錄 + auto_start ➔ 視為進行中 (沒有結束時間)；過了 ends_at ➔ 自動結束並清空活動道具
#   status: active (started_at 是之後的時間 = ⏳ 排好還沒開始) / ended / cancelled (排程被取消)；/admin-event start 見 plan_event_schedule
# =========================================================
async def _event_state(db, event_id: str):
    raw = await _get_meta(db, f"event:{event_id}")
    return json.loads(raw) if raw else None


async def _clear_event_items(db, item_ids: set[str]) -> int:
    """從所有玩家的神社倉庫移除活動道具，回傳受影響的玩家數"""
    changed = 0
    async with db.execute("SELECT user_id, inventory FROM users") as cursor:
        rows = await cursor.fetchall()
    for row in rows:
        inv = _load_inventory(row["inventory"])
        if any(i in inv for i in item_ids):
            for i in item_ids:
                inv.pop(i, None)
            await db.execute("UPDATE users SET inventory = ? WHERE user_id = ?", (json.dumps(inv, ensure_ascii=False), row["user_id"]))
            changed += 1
    return changed


async def _end_event(db, event: dict, now: datetime) -> int:
    changed = await _clear_event_items(db, event_item_ids(event))
    st = await _event_state(db, event["id"]) or {}
    await _set_meta(db, f"event:{event['id']}", json.dumps({**st, "status": "ended", "ended_at": now.isoformat()}))
    return changed


def event_phase(event: dict, state: dict | None, now: datetime) -> str:
    """
    活動現在的階段 (只看資料，不會改東西)：
    "running" 進行中 / "scheduled" 排好了還沒到開始時間 / "off" 沒在進行 (沒開過、已結束、取消、過了結束時間)
    沒有紀錄 + auto_start = 進行中 (started_at 是 None，任務那一輪 = 「活動 id:auto」)
    """
    if state is None:
        return "running" if event.get("auto_start") else "off"
    if state.get("status") != "active":
        return "off"
    if state.get("ends_at") and now >= _dt(state["ends_at"]):
        return "off"
    if state.get("started_at") and now < _dt(state["started_at"]):
        return "scheduled"
    return "running"


async def _active_events(db, now: datetime) -> list[dict]:
    """進行中的活動 (要在交易裡呼叫：過期的活動會在這裡結束並清空道具；排好還沒到開始時間的不算)"""
    active = []
    for ev in load_events().values():
        st = await _event_state(db, ev["id"])
        if st is not None and st.get("status") == "active" and st.get("ends_at") and now >= _dt(st["ends_at"]):
            await _end_event(db, ev, now)
            continue
        if event_phase(ev, st, now) == "running":
            active.append(ev)
    return active


async def get_events_overview(now: datetime | None = None) -> list[dict]:
    """/event info 用：每個活動 + 狀態 [{"event", "status" (active / ended / upcoming), "started_at", "ends_at"}]
    upcoming = 沒開過、排好了還沒開始 (started_at 是之後的時間)、或排程被取消"""
    now = now or datetime.now(timezone.utc)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            active_ids = {ev["id"] for ev in await _active_events(db, now)}
            out = []
            for ev in load_events().values():
                st = await _event_state(db, ev["id"]) or {}
                status = "active" if ev["id"] in active_ids else ("ended" if st.get("status") == "ended" else "upcoming")
                out.append({"event": ev, "status": status, "started_at": st.get("started_at"), "ends_at": st.get("ends_at"),
                            "scheduled": st.get("status") == "active" and status == "upcoming"})   # ⏳ 排好了還沒開始
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return out


def plan_event_schedule(events: dict, states: dict, selected: list[str], start: datetime, days: int | None,
                        now: datetime) -> list[dict]:
    """
    /admin-event start 會做的事 (2026-11-22 使用者定案)，只算不寫：
    - 勾到的活動：沒在進行 / 排好還沒開始 ➔ "start" (start 開始、days 天後結束，days 0 / None = 一直持續)
      本來就在進行中 ➔ "extend" (不重開，只把結束時間改成 start + days；任務進度、活動道具都保留)
    - 沒勾到、進行中 ➔ 在 start 結束："end_now" (start 是現在，馬上結束並清活動道具) / "end_at" (到 start 那一刻才結束；
      本來就更早結束的照舊)
    - 沒勾到、排好還沒開始 ➔ "cancel" (取消排程)
    回傳 [{"event", "action", "started_at", "ends_at"}] (時間是 datetime 或 None)
    """
    ends = start + timedelta(days=days) if days else None
    plan = []
    for eid, ev in events.items():
        st = states.get(eid) or {}
        phase = event_phase(ev, states.get(eid), now)
        current_start = _dt(st["started_at"]) if st.get("started_at") else None
        current_end = _dt(st["ends_at"]) if st.get("ends_at") else None
        if eid in selected:
            if phase == "running":
                plan.append({"event": ev, "action": "extend", "started_at": current_start, "ends_at": ends})
            else:
                plan.append({"event": ev, "action": "start", "started_at": start, "ends_at": ends})
        elif phase == "running":
            if start <= now:
                plan.append({"event": ev, "action": "end_now", "started_at": current_start, "ends_at": now})
            else:
                end_at = min(current_end, start) if current_end else start
                plan.append({"event": ev, "action": "end_at", "started_at": current_start, "ends_at": end_at})
        elif phase == "scheduled":
            plan.append({"event": ev, "action": "cancel", "started_at": current_start, "ends_at": None})
    return plan


async def preview_event_schedule(event_ids: list[str], start: datetime | None = None, days: int | None = None,
                                 now: datetime | None = None) -> list[dict]:
    """確認畫面用：plan_event_schedule 的結果 (唯讀)"""
    now = now or datetime.now(timezone.utc)
    events = load_events()
    async with connect() as db:
        states = {eid: await _event_state(db, eid) for eid in events}
    return plan_event_schedule(events, states, event_ids, start or now, days, now)


async def admin_schedule_events(event_ids: list[str], start: datetime | None = None, days: int | None = None,
                                now: datetime | None = None) -> list[dict] | None:
    """
    【管理員】/admin-event start：照 plan_event_schedule 開始 / 延長 / 結束 / 取消，同一個交易
    回傳實際的計畫 (end_now 多一個 "cleared" = 清了幾位玩家的活動道具)；有找不到的活動 ➔ None (什麼都不改)
    """
    now = now or datetime.now(timezone.utc)
    start = start or now
    events = load_events()
    if not event_ids or any(eid not in events for eid in event_ids):
        return None
    iso = lambda t: t.isoformat() if t else None
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _active_events(db, now)   # 先把已經過了結束時間的活動結束掉
            states = {eid: await _event_state(db, eid) for eid in events}
            plan = plan_event_schedule(events, states, event_ids, start, days, now)
            for p in plan:
                eid, st = p["event"]["id"], states.get(p["event"]["id"]) or {}
                if p["action"] == "start":
                    value = {"status": "active", "started_at": iso(start), "ends_at": iso(p["ends_at"])}
                elif p["action"] in ("extend", "end_at"):   # started_at 照舊 (auto_start 沒紀錄的維持 None ➔ 任務那一輪不變)
                    value = {**st, "status": "active", "started_at": st.get("started_at"), "ends_at": iso(p["ends_at"])}
                elif p["action"] == "cancel":
                    value = {**st, "status": "cancelled", "cancelled_at": now.isoformat()}
                else:   # end_now
                    p["cleared"] = await _end_event(db, p["event"], now)
                    continue
                await _set_meta(db, f"event:{eid}", json.dumps(value))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return plan


async def get_event_phase(event_id: str, now: datetime | None = None) -> str | None:
    """活動現在的階段 (event_phase)；找不到活動 ➔ None"""
    now = now or datetime.now(timezone.utc)
    ev = load_events().get(event_id)
    if ev is None:
        return None
    async with connect() as db:
        return event_phase(ev, await _event_state(db, event_id), now)


async def admin_start_event(event_id: str, days: int | None = None, now: datetime | None = None) -> bool:
    """【管理員】開始活動；days=None 不設結束時間 (測試用；/admin-event start 改用 admin_schedule_events)"""
    now = now or datetime.now(timezone.utc)
    if event_id not in load_events():
        return False
    ends = (now + timedelta(days=days)).isoformat() if days else None
    async with connect() as db:
        await _set_meta(db, f"event:{event_id}", json.dumps({"status": "active", "started_at": now.isoformat(), "ends_at": ends}))
        await db.commit()
    return True


async def admin_end_event(event_id: str, now: datetime | None = None) -> int | None:
    """【管理員】結束活動並清空所有玩家的活動道具；回傳受影響的玩家數 (找不到活動回傳 None)
    排好了還沒開始的活動 ➔ 只取消排程 (沒有活動道具要清，回傳 0)"""
    now = now or datetime.now(timezone.utc)
    ev = load_events().get(event_id)
    if ev is None:
        return None
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            st = await _event_state(db, event_id)
            if event_phase(ev, st, now) == "scheduled":
                await _set_meta(db, f"event:{event_id}", json.dumps({**st, "status": "cancelled", "cancelled_at": now.isoformat()}))
                changed = 0
            else:
                changed = await _end_event(db, ev, now)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return changed


async def get_rules(now: datetime | None = None) -> dict:
    """這一刻的遊戲規則 (含進行中的活動)，給畫面顯示用"""
    now = now or datetime.now(timezone.utc)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            rules = game_rules(await _active_events(db, now))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    _remember_fee_mods(rules)
    return rules


# 活動的手續費倍率 (modifiers.market_fee / transfer_fee)：畫面顯示用的同步快取，每次 get_rules 更新；
# 真正扣款 (buy_listing / transfer_money) 會在交易裡重新算，不靠這個快取
_FEE_MODS = {"market_fee": 1.0, "transfer_fee": 1.0}


def _remember_fee_mods(rules: dict):
    for k in _FEE_MODS:
        _FEE_MODS[k] = rules["modifiers"].get(k, 1.0)

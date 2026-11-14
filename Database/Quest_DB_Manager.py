"""
📜 活動任務 (Database/Users.db)：任務進度、領取、永久活動稱號、快結束提醒用的「還沒領」清單

- 任務定義在活動檔 Events/<id>.json 的 "quests" / "quest_titles" (格式見 Events/README.md)
- 計數：各動作的交易裡呼叫 User_DB_Manager.add_quest_stats (只在活動進行中記)，存在 event_quest_stats
- 一輪 (run) = 「活動 id:這次開始時間」(User_DB_Manager.event_run_id)：同一個活動重開 ➔ 新的一輪，進度、領取都重新算
- 領取紀錄 event_quest_claims (主鍵 user_id + run + quest_id，不會重複領)；活動結束後沒領的就沒了
- 活動稱號：這個活動「所有輪加總」領過的不同任務數 >= min_quests ➔ 寫進 earned_titles (永久，活動結束也保留)
- 這裡不 import discord，畫面在 Cogs/load-general/Components/quest_components.py
"""
from datetime import datetime, timedelta, timezone

from Database import User_DB_Manager as udm
from Database import Economy_DB_Manager as econ
from Database import title_data
from Database.events import quest_need, quest_progress

REMIND_WINDOW = timedelta(hours=24)   # 活動結束前 24 小時內提醒「還有完成但沒領的任務」


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def event_titles(event: dict) -> list[dict]:
    """活動的任務稱號 [{"id" (title_data 的 id), "name", "rarity", "desc", "min"}] (門檻低的在前)"""
    out = []
    for t in event.get("quest_titles", []):
        tid = title_data.event_title_id(event["id"], t["id"])
        out.append({"id": tid, "name": t["name"], "rarity": t["rarity"], "desc": t.get("desc", ""), "min": int(t["min_quests"])})
    return sorted(out, key=lambda t: t["min"])


def remind_due(ends_at: str | None, now: datetime) -> bool:
    """活動快結束了嗎 (結束前 REMIND_WINDOW 內；沒有結束時間 = 不提醒)"""
    if not ends_at:
        return False
    end = _dt(ends_at)
    return end - REMIND_WINDOW <= now < end


def build_quests(event: dict, stats: dict, claimed: set[str]) -> list[dict]:
    """(純計算) 任務 + 進度：[{...任務欄位, "index", "cur", "need", "done", "claimed"}]"""
    out = []
    for i, q in enumerate(event.get("quests", []), 1):
        need = quest_need(q)
        cur = quest_progress(q, stats)
        out.append({**q, "index": i, "cur": cur, "need": need, "done": cur >= need, "claimed": q["id"] in claimed})
    return out


async def _run_stats(db, user_id: int, run: str) -> dict:
    async with db.execute("SELECT stat, value FROM event_quest_stats WHERE user_id = ? AND run = ?", (user_id, run)) as cursor:
        return {r["stat"]: r["value"] for r in await cursor.fetchall()}


async def _claimed(db, user_id: int, run: str) -> set[str]:
    async with db.execute("SELECT quest_id FROM event_quest_claims WHERE user_id = ? AND run = ?", (user_id, run)) as cursor:
        return {r["quest_id"] for r in await cursor.fetchall()}


async def _claimed_all_runs(db, user_id: int, event: dict) -> int:
    """這個活動所有輪加總，領過幾種「目前還存在」的任務 (同一個任務在不同輪領兩次只算一種)"""
    async with db.execute("SELECT DISTINCT quest_id FROM event_quest_claims WHERE user_id = ? AND event_id = ?",
                          (user_id, event["id"])) as cursor:
        ids = {r["quest_id"] for r in await cursor.fetchall()}
    return len(ids & {q["id"] for q in event.get("quests", [])})


async def _earned(db, user_id: int) -> set[str]:
    async with db.execute("SELECT title_id FROM earned_titles WHERE user_id = ?", (user_id,)) as cursor:
        return {r["title_id"] for r in await cursor.fetchall()}


async def _grant_titles(db, user_id: int, event: dict, count: int, now: datetime) -> list[str]:
    """
    (交易裡) 累計領取數 count 達到門檻的活動稱號 ➔ 寫進 earned_titles，回傳這次新拿到的稱號 id
    不看 title_data.TITLES 有沒有這個 id (改了活動檔還沒全部重載時也先記下來；顯示端會再用 TITLES 過濾)
    """
    new_titles = []
    for t in event_titles(event):
        if count >= t["min"]:
            cursor = await db.execute("INSERT OR IGNORE INTO earned_titles (user_id, title_id, earned_at) VALUES (?, ?, ?)",
                                      (user_id, t["id"], now.isoformat()))
            if cursor.rowcount == 1:
                new_titles.append(t["id"])
    return new_titles


async def _active_runs(db, now: datetime) -> dict:
    """(交易裡) 先讓過期的活動結束 (econ._active_events)，再取進行中、有任務的活動的這一輪"""
    await econ._active_events(db, now)
    return await udm._event_runs(db, now)


async def get_quest_board(user_id: int, now: datetime | None = None) -> list[dict]:
    """
    /event quest 用：進行中、有任務的每個活動 ➔
    [{"event", "run", "ends_at", "quests" (build_quests), "done", "claimed", "total",
      "claimed_all_runs" (稱號用的累計), "titles": [{..., "earned"}]}]
    """
    now = now or datetime.now(timezone.utc)
    async with udm.connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            runs = await _active_runs(db, now)
            board = []
            for eid, info in runs.items():
                ev = info["event"]
                quests = build_quests(ev, await _run_stats(db, user_id, info["run"]), await _claimed(db, user_id, info["run"]))
                claimed_all = await _claimed_all_runs(db, user_id, ev)
                # 補發：之後才加的稱號 / 門檻改低了，已經達標的人打開畫面時補進 earned_titles (通知 loop 會私訊)
                await _grant_titles(db, user_id, ev, claimed_all, now)
                earned = await _earned(db, user_id)
                board.append({
                    "event": ev, "run": info["run"], "ends_at": info["ends_at"], "quests": quests,
                    "done": sum(1 for q in quests if q["done"]), "claimed": sum(1 for q in quests if q["claimed"]),
                    "total": len(quests), "claimed_all_runs": claimed_all,
                    "titles": [{**t, "earned": t["id"] in earned} for t in event_titles(ev)],
                })
            await db.commit()   # _active_events 可能剛結束了過期的活動
        except BaseException:
            await db.rollback()
            raise
    return board


async def claim_quest(user_id: int, event_id: str, quest_id: str, now: datetime | None = None) -> dict:
    """
    領取任務獎勵 (單一交易)：活動進行中 + 任務完成 + 這一輪沒領過 ➔ 寫領取紀錄 + 加賽錢 + 加經驗值 + 檢查活動稱號
    經驗值不用 add_exp (另開連線)，改成在同一個交易裡用 calc_exp_change 算好直接 UPDATE users ➔ 領取紀錄寫不進去 (領過了) 就什麼都不給
    失敗 reason：not_active (活動不在進行中) / not_found / not_done / claimed
    成功 {"ok", "money", "exp", "exp_result", "balance", "new_titles": [稱號 id], "quest"}
    """
    now = now or datetime.now(timezone.utc)
    async with udm.connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            runs = await _active_runs(db, now)
            info = runs.get(event_id)
            result = None
            if info is None:
                result = {"ok": False, "reason": "not_active"}
            else:
                ev, run = info["event"], info["run"]
                quest = next((q for q in ev.get("quests", []) if q["id"] == quest_id), None)
                if quest is None:
                    result = {"ok": False, "reason": "not_found"}
                elif quest_progress(quest, await _run_stats(db, user_id, run)) < quest_need(quest):
                    result = {"ok": False, "reason": "not_done"}
            if result is None:
                cursor = await db.execute(
                    "INSERT OR IGNORE INTO event_quest_claims (user_id, run, quest_id, event_id, claimed_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, run, quest_id, event_id, now.isoformat()),
                )
                if cursor.rowcount != 1:
                    result = {"ok": False, "reason": "claimed"}
            if result is not None:
                await db.commit()   # 只有 _active_events 可能結束過期活動的寫入
                return result

            reward = quest.get("reward", {})
            money, exp = int(reward.get("money", 0)), int(reward.get("exp", 0))
            await udm._ensure_user(db, user_id)
            async with db.execute("SELECT money, level, exp FROM users WHERE user_id = ?", (user_id,)) as cursor:
                user = await cursor.fetchone()
            exp_result = udm.calc_exp_change(user["level"], user["exp"], exp)
            await db.execute("UPDATE users SET money = money + ?, level = ?, exp = ? WHERE user_id = ?",
                             (money, exp_result["new_level"], exp_result["current_exp"], user_id))
            # 🏷️ 活動稱號：所有輪加總領過的不同任務數達到門檻 ➔ 永久獲得
            count = await _claimed_all_runs(db, user_id, ev)
            new_titles = await _grant_titles(db, user_id, ev, count, now)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "money": money, "exp": exp, "exp_result": exp_result, "balance": user["money"] + money,
            "new_titles": new_titles, "quest": quest, "claimed_all_runs": count}


async def pending_reminders(now: datetime | None = None) -> list[dict]:
    """
    快結束提醒 (通知 loop 用)：結束前 24 小時內的活動，每位有「完成但沒領」任務的玩家一筆
    [{"user_id", "event", "run", "ends_at", "count"}]
    """
    now = now or datetime.now(timezone.utc)
    out = []
    async with udm.connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            runs = await _active_runs(db, now)
            for eid, info in runs.items():
                if not remind_due(info["ends_at"], now):
                    continue
                async with db.execute("SELECT DISTINCT user_id FROM event_quest_stats WHERE run = ?", (info["run"],)) as cursor:
                    uids = [r["user_id"] for r in await cursor.fetchall()]
                for uid in uids:
                    quests = build_quests(info["event"], await _run_stats(db, uid, info["run"]), await _claimed(db, uid, info["run"]))
                    n = sum(1 for q in quests if q["done"] and not q["claimed"])
                    if n:
                        out.append({"user_id": uid, "event": info["event"], "run": info["run"], "ends_at": info["ends_at"], "count": n})
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return out

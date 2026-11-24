"""
👤 玩家資料、💰 貨幣與經驗、📅 每日簽到、🎒 背包道具、🏆 排行榜與隱私、tw_day、📊 玩家統計、🎪 活動任務計數、⚡ 體力

從 Database/User_DB_Manager.py 拆出來的；外面一律照舊從 Database.User_DB_Manager 匯入 (入口)，不要直接匯入這裡。
"""
import json
from datetime import datetime, timedelta, timezone

from Database.users.schema import connect, _ensure_user

# ---------------------------------------------------------
# 👤 2. 取得或自動建立玩家資料 (Auto-Registration)
# ---------------------------------------------------------
async def get_or_create_user(user_id: int) -> dict:
    """
    取得玩家資料；若玩家不存在則自動創建初始資料 (預設給予 1000 賽錢)
    傳回字典格式的玩家資料，其中 inventory 已轉成 Python 字典
    """
    async with connect() as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()

        if row is None:
            await _ensure_user(db, user_id)
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()

    user_data = dict(row)
    user_data["inventory"] = json.loads(user_data["inventory"])
    return user_data


# ---------------------------------------------------------
# 💰 3. 貨幣與經驗值操作 (Money & Exp)
# ---------------------------------------------------------
async def add_money(user_id: int, amount: int) -> int:
    """增加或扣除玩家賽錢 (amount 可為正數或負數)，傳回更新後的金額"""
    async with connect() as db:
        await _ensure_user(db, user_id)
        await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (amount, user_id))
        async with db.execute("SELECT money FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        await db.commit()
    return row["money"] if row else 0


def get_required_exp_for_level(level: int) -> int:
    """計算從當前階級 (level) 升到下一階級 (level + 1) 所需的經驗值"""
    return 50 + (level * 15)


def get_total_exp_for_level(level: int) -> int:
    """計算到達指定 level 所需的累積總經驗值"""
    # 等差數列求和: sum_{i=0}^{level-1} (50 + 15*i)
    if level <= 0:
        return 0
    return level * 50 + 15 * level * (level - 1) // 2


async def add_exp(user_id: int, exp_amount: int) -> dict:
    """
    給予或扣除玩家經驗值，並自動計算對應 P點 (0.0 P ~ 100.0 P)
    - 支援正負數調整
    - 自動重算累積總經驗值，徹底防止負數 EXP
    - 最低 0.0 P (0 EXP)，最高 100.0 P (FULL POWER)
    """
    user_data = await get_or_create_user(user_id)
    result = calc_exp_change(user_data.get("level", 0), user_data.get("exp", 0), exp_amount)

    # 寫回資料庫
    async with connect() as db:
        await db.execute(
            "UPDATE users SET level = ?, exp = ? WHERE user_id = ?",
            (result["new_level"], result["current_exp"], user_id)
        )
        await db.commit()
    return result


def calc_exp_change(current_level: int, current_exp: int, exp_amount: int) -> dict:
    """
    (純計算) 目前 level / exp + 變動量 ➔ 新的 level / exp 與升降級資訊
    add_exp 用；要跟其他東西在同一個交易裡給經驗時 (活動任務領取) 也用這個，自己 UPDATE users
    回傳 {"leveled_up", "is_degraded", "old_p", "new_p", "current_exp", "is_max", "new_level"}
    """
    current_level = current_level or 0  # 內部 level: 0 ~ 1000
    current_exp = current_exp or 0
    old_p = current_level / 10.0

    # 1. 換算出當前的「歷史累積總經驗值」並加上變動量
    total_exp = get_total_exp_for_level(current_level) + current_exp + exp_amount

    # 2. 嚴格防呆：總經驗值不得低於 0
    if total_exp <= 0:
        new_level = 0
        new_exp = 0
    else:
        # 3. 從 Level 0 開始重新推算階級與剩餘 EXP
        new_level = 0
        while new_level < 1000:
            req_exp = get_required_exp_for_level(new_level)
            if total_exp >= req_exp:
                total_exp -= req_exp
                new_level += 1
            else:
                break

        # 滿等 (1000 level = 100.0 P) 封頂保護
        if new_level >= 1000:
            new_level = 1000
            new_exp = 0
        else:
            new_exp = total_exp

    new_p = new_level / 10.0
    leveled_up = (new_p > old_p)
    is_degraded = (new_p < old_p)

    return {
        "leveled_up": leveled_up,
        "is_degraded": is_degraded,
        "old_p": old_p,
        "new_p": new_p,
        "current_exp": new_exp,
        "is_max": (new_level >= 1000),
        "new_level": new_level,
    }


# ---------------------------------------------------------
# 📅 4. 每日簽到 (Daily)：簽到日期與當日運勢都存在 users 資料表
# ---------------------------------------------------------
async def get_daily_status(user_id: int, today: str) -> dict:
    """
    唯讀查詢「今天」的簽到狀態 (查看別人的資料卡時也安全，不會替對方建立資料)。
    today 格式 YYYY-MM-DD，由呼叫端依時區決定。
    回傳 {"signed_today": bool, "fortune_level": int | None}
    """
    async with connect() as db:
        async with db.execute(
            "SELECT last_daily, fortune_level FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if row and row["last_daily"] == today:
        level = row["fortune_level"] if row["fortune_level"] is not None else 3
        return {"signed_today": True, "fortune_level": level}
    return {"signed_today": False, "fortune_level": None}


async def claim_daily(user_id: int, today: str, fortune_level: int, now: datetime | None = None) -> bool:
    """
    原子性地「搶」今天的簽到名額：只有 last_daily 不是今天時才會寫入成功。
    連點按鈕或兩個視窗同時簽到，也只會有一個人拿到 True，不會重複領獎。
    連續簽到：上次簽到是昨天 ➔ daily_streak + 1，否則從 1 重新算；best_streak 記最長紀錄 (同一個 UPDATE)
    🎪 活動任務：簽到成功時，進行中的活動各記 daily +1 (同一個交易)
    """
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    async with connect() as db:
        await _ensure_user(db, user_id)
        cursor = await db.execute(
            """
            UPDATE users
            SET last_daily = ?, fortune_level = ?, daily_count = COALESCE(daily_count, 0) + 1,
                daily_streak = CASE WHEN last_daily = ? THEN COALESCE(daily_streak, 0) + 1 ELSE 1 END,
                best_streak = MAX(COALESCE(best_streak, 0),
                                  CASE WHEN last_daily = ? THEN COALESCE(daily_streak, 0) + 1 ELSE 1 END)
            WHERE user_id = ? AND (last_daily IS NULL OR last_daily != ?)
            """,
            (today, fortune_level, yesterday, yesterday, user_id, today),
        )
        claimed = cursor.rowcount == 1
        if claimed:
            await add_quest_stats(db, user_id, now, {"daily": 1})
            if fortune_level in (0, 5):   # 🍀 運氣稱號：抽到大吉 (5) / 凶 (0) 的次數 (0.35.005 起)
                await add_player_stat(db, user_id, f"fortune_{fortune_level}")
        await db.commit()
    return claimed


async def reset_daily(user_id: int) -> bool:
    """
    【開發者 / 管理專用】重置指定玩家的簽到紀錄
    將 last_daily 設為 NULL，使其能立即再次觸發每日簽到。
    """
    async with connect() as db:
        await db.execute("UPDATE users SET last_daily = NULL WHERE user_id = ?", (user_id,))
        await db.commit()
    return True


async def update_daily_time(user_id: int, date_str: str):
    """更新玩家上次每日簽到的日期 (格式: YYYY-MM-DD)"""
    async with connect() as db:
        await _ensure_user(db, user_id)
        await db.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (date_str, user_id))
        await db.commit()


# ---------------------------------------------------------
# 🎒 5. 背包道具操作 (Inventory)
# ---------------------------------------------------------
def _load_inventory(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


async def add_item(user_id: int, item_id: str, amount: int = 1) -> dict:
    """給予 (或扣除) 玩家指定道具與數量，傳回更新後的背包字典；同一個交易，不會因同時寫入而遺失"""
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_user(db, user_id)
            async with db.execute("SELECT inventory FROM users WHERE user_id = ?", (user_id,)) as cursor:
                inventory = _load_inventory((await cursor.fetchone())["inventory"])
            inventory[item_id] = inventory.get(item_id, 0) + amount
            if inventory[item_id] <= 0:
                del inventory[item_id]  # 數量小於等於 0 則移除道具
            await db.execute(
                "UPDATE users SET inventory = ? WHERE user_id = ?",
                (json.dumps(inventory, ensure_ascii=False), user_id),
            )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return inventory


async def adjust_item(user_id: int, item_id: str, delta: int) -> dict:
    """
    調整玩家某個道具的數量 (正數給予、負數扣除)，同一個交易
    - 扣完會小於 0 ➔ 不寫入，回傳 ok=False
    - 剛好變成 0 ➔ 從背包移除這個道具
    回傳 {"ok", "before", "after"}
    """
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_user(db, user_id)
            async with db.execute("SELECT inventory FROM users WHERE user_id = ?", (user_id,)) as cursor:
                inventory = _load_inventory((await cursor.fetchone())["inventory"])
            before = inventory.get(item_id, 0)
            after = before + delta
            if after < 0:
                await db.rollback()
                return {"ok": False, "before": before, "after": before}
            if after == 0:
                inventory.pop(item_id, None)
            else:
                inventory[item_id] = after
            await db.execute(
                "UPDATE users SET inventory = ? WHERE user_id = ?",
                (json.dumps(inventory, ensure_ascii=False), user_id),
            )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "before": before, "after": after}


async def clear_all_inventories() -> int:
    """清空所有玩家的背包，回傳受影響的玩家數"""
    async with connect() as db:
        cursor = await db.execute("UPDATE users SET inventory = '{}' WHERE inventory IS NOT NULL AND inventory != '{}'")
        await db.commit()
        return cursor.rowcount


async def update_user_inventory(user_id: int, inventory: dict):
    """統一更新玩家背包資料"""
    async with connect() as db:
        await db.execute(
            "UPDATE users SET inventory = ? WHERE user_id = ?",
            (json.dumps(inventory, ensure_ascii=False), user_id)
        )
        await db.commit()


# ---------------------------------------------------------
# 🏆 6. 排行榜與隱私 (Leaderboard & Visibility)
# ---------------------------------------------------------
async def get_leaderboard_stats(user_ids: list[int]) -> list[dict]:
    """
    排行榜用：指定玩家的各項統計 (只會回傳資料庫裡有的玩家)
    [{"user_id", "money", "level", "is_public", "total_draws", "total_fusions", "card_count", "char_count", "kind_count"}, ...]
    卡牌三項都算卡冊 + 收藏冊 + 出征中 (上架中的卡在市場託管，不算)；kind_count = 🃏 收集卡種 (角色 × 階級)
    """
    if not user_ids:
        return []
    placeholders = ", ".join("?" for _ in user_ids)
    async with connect() as db:
        async with db.execute(
            f"""
            SELECT u.user_id, u.money, u.level, u.is_public,
                   COALESCE(s.total_draws, 0)   AS total_draws,
                   COALESCE(s.total_fusions, 0) AS total_fusions,
                   COUNT(c.instance_id)            AS card_count,
                   COUNT(DISTINCT c.character_key) AS char_count,
                   COUNT(DISTINCT c.character_key || ':' || c.rarity) AS kind_count
            FROM users u
            LEFT JOIN gacha_stats s ON s.user_id = u.user_id
            LEFT JOIN gacha_cards c ON c.user_id = u.user_id
            WHERE u.user_id IN ({placeholders})
            GROUP BY u.user_id
            """,
            tuple(user_ids),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def update_visibility(user_id: int, is_public: bool):
    """更新玩家資料卡片的公開/私人狀態 (is_public: True 代表公開)"""
    async with connect() as db:
        await _ensure_user(db, user_id)
        await db.execute(
            "UPDATE users SET is_public = ? WHERE user_id = ?",
            (1 if is_public else 0, user_id)
        )
        await db.commit()


TW = timezone(timedelta(hours=8))


def tw_day(now: datetime | None = None) -> str:
    """台灣時間 (UTC+8) 的日期 YYYY-MM-DD；每日結算、轉帳額度都用這個"""
    return (now or datetime.now(timezone.utc)).astimezone(TW).strftime("%Y-%m-%d")


# 📊 player_stats 的項目 (2026-11-14 起才開始記，之前的補不回來)
PLAYER_STATS = {
    "serve": "招待客人次數",
    "serve_favorite": "成功招待次數 (額外端上客人最愛的料理)",
    "explore": "採集趟數",
    "youkai": "治退妖怪隻數",
    "cook": "料理次數 (鍋數)",
    "clean": "清掃次數",
    "collect_money": "從賽錢箱累計回收的賽錢",
    "shop": "雜貨店購買次數",
    # 另外還有每種客人一個的 serve_guest:<客人> (招待次數) / serve_fav:<客人> (成功招待次數)，0.35.001 起 (客人稱號用)
    # 以及每個採集地點一個的 explore:<地點> (趟數)，0.35.003 起 (足跡稱號用)
    # 🍀 運氣稱號 (0.35.005 起)：explore_good / explore_bad (採集好 / 壞事件)、fortune_5 / fortune_0 (簽到大吉 / 凶)、
    #    gacha_pity (觸發保底張數，所有卡池合計)、tenpull_2ur:<卡池> (距離上次 UR 90 抽內就出 UR 的次數；
#    2026-11-22 前是「一次十連出 2 張以上 UR」，名字沒改、舊次數照算)
    # 🍳 美食家稱號 (0.35.007 起)：cook:<料理> (每道料理的鍋數)、eat_stamina (吃了幾個體力道具，含飯糰)
    # 🌀 裏世界 (0.35.083 起)：ura_runs (出發次數)、ura_evacuated (成功撤離次數)、ura_kill:<敵人> (打倒 / 勸走隻數；0.35.103 起打倒當下就記，📖 怪物圖鑑用)
}


async def add_player_stat(db, user_id: int, stat: str, amount: int = 1):
    """(在呼叫端的交易裡) 玩家統計 + amount；amount <= 0 不記"""
    if amount <= 0:
        return
    await db.execute(
        "INSERT INTO player_stats (user_id, stat, value) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, stat) DO UPDATE SET value = value + excluded.value",
        (user_id, stat, int(amount)),
    )


async def get_player_stats(user_id: int) -> dict:
    """{項目: 數字} (沒記過的項目是 0)"""
    async with connect() as db:
        async with db.execute("SELECT stat, value FROM player_stats WHERE user_id = ?", (user_id,)) as cursor:
            rows = {r["stat"]: r["value"] for r in await cursor.fetchall()}
    return {k: rows.get(k, 0) for k in PLAYER_STATS} | rows


# ---------------------------------------------------------
# 🎪 活動任務的計數 (領取、畫面在 Database/Quest_DB_Manager.py)
#    只在活動「進行中」時記；一輪 (run) = 「活動 id:這次開始時間」(auto_start 沒有紀錄 = 「活動 id:auto」)，
#    同一個活動之後重開 (admin_start_event) 開始時間不同 ➔ 新的一輪，進度從 0 開始
# ---------------------------------------------------------
EVENT_POOL_PREFIX = "event_"   # 活動限定卡池的 pool key = event_<活動 id> (Database/events.game_rules)


def event_run_id(event_id: str, started_at: str | None) -> str:
    return f"{event_id}:{started_at or 'auto'}"


async def _event_runs(db, now: datetime | None = None) -> dict:
    """
    (在呼叫端的連線裡，唯讀) 進行中、而且有任務的活動 ➔ {活動 id: {"run", "event", "started_at", "ends_at"}}
    判斷跟 Economy_DB_Manager._active_events 一樣 (沒有紀錄 + auto_start = 進行中；過了 ends_at = 已結束)，
    但這裡不會去結束活動 (那個留給 _active_events)
    """
    from Database.events import load_events   # events 只讀 Events/*.json + shrine_data，不會循環匯入
    now = now or datetime.now(timezone.utc)
    runs = {}
    for eid, ev in load_events().items():
        if not ev.get("quests"):
            continue
        async with db.execute("SELECT value FROM economy_meta WHERE key = ?", (f"event:{eid}",)) as cursor:
            row = await cursor.fetchone()
        st = json.loads(row["value"]) if row and row["value"] else None
        if st is None:
            if not ev.get("auto_start"):
                continue
            st = {}
        elif st.get("status") != "active" or (st.get("ends_at") and now >= datetime.fromisoformat(st["ends_at"])):
            continue
        elif st.get("started_at") and now < datetime.fromisoformat(st["started_at"]):   # ⏳ 排好了還沒到開始時間
            continue
        runs[eid] = {"run": event_run_id(eid, st.get("started_at")), "event": ev,
                     "started_at": st.get("started_at"), "ends_at": st.get("ends_at")}
    return runs


async def add_quest_stats(db, user_id: int, now: datetime | None = None, stats: dict | None = None,
                          per_event: dict | None = None):
    """
    (在呼叫端的交易裡) 活動任務計數：進行中的每個有任務的活動，這一輪的 stats {項目: 數量} 各 + 數量
    per_event = {活動 id: {項目: 數量}}：只加給那個活動 (活動卡池抽數、那個活動的活動料理份數)
    數量 <= 0 不記；沒有進行中的活動什麼都不做
    """
    for eid, info in (await _event_runs(db, now)).items():
        items = {**(stats or {}), **(per_event or {}).get(eid, {})}
        for stat, n in items.items():
            if n and n > 0:
                await db.execute(
                    "INSERT INTO event_quest_stats (user_id, run, stat, value) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(user_id, run, stat) DO UPDATE SET value = value + excluded.value",
                    (user_id, info["run"], stat, int(n)),
                )


# ---------------------------------------------------------
# ⚡ 9. 體力 (Stamina)
#   不用背景排程：每次「讀取 / 使用 / 回復」時才依經過時間結算
#   自然回復：每 6 分鐘 +1，自然回復只回到 240 為止 (道具等可以超過 240，超過時不再自然回復)
#   users.stamina_updated_at = 上次結算的時間點 (UTC ISO)；未滿時只推進「已結算的整數個 6 分鐘」，零頭保留
# ---------------------------------------------------------
STAMINA_MAX = 240
STAMINA_INTERVAL_SECONDS = 6 * 60


def calc_stamina(stored: int | None, updated_at: str | None, now: datetime | None = None) -> dict:
    """
    純計算 (不寫資料庫)：
    {"stamina", "max", "updated_at" (新的結算時間 ISO), "next_in" (幾秒後 +1，已滿為 0), "full_in" (幾秒後回滿，已滿為 0)}
    """
    now = now or datetime.now(timezone.utc)
    stamina = STAMINA_MAX if stored is None else stored
    last = datetime.fromisoformat(updated_at) if updated_at else now

    if stamina < STAMINA_MAX:
        ticks = max(0, int((now - last).total_seconds() // STAMINA_INTERVAL_SECONDS))
        stamina = min(STAMINA_MAX, stamina + ticks)
        last = last + timedelta(seconds=ticks * STAMINA_INTERVAL_SECONDS)
    if stamina >= STAMINA_MAX:
        last = now   # 已滿：時鐘停在現在，等到被使用後才開始重新計時
        return {"stamina": stamina, "max": STAMINA_MAX, "updated_at": last.isoformat(), "next_in": 0, "full_in": 0}

    next_in = STAMINA_INTERVAL_SECONDS - int((now - last).total_seconds())
    full_in = next_in + (STAMINA_MAX - stamina - 1) * STAMINA_INTERVAL_SECONDS
    return {"stamina": stamina, "max": STAMINA_MAX, "updated_at": last.isoformat(), "next_in": next_in, "full_in": full_in}


async def _change_stamina(user_id: int, delta: int, require_enough: bool) -> dict:
    """結算後加減體力 (同一個交易)；require_enough 且不夠扣時不寫入，回傳 ok=False"""
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_user(db, user_id)
            async with db.execute(
                "SELECT stamina, stamina_updated_at FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
            now = datetime.now(timezone.utc)
            info = calc_stamina(row["stamina"], row["stamina_updated_at"], now)

            if require_enough and info["stamina"] < -delta:
                await db.rollback()
                return {**info, "ok": False}

            new_value = max(0, info["stamina"] + delta)
            # 從滿 (或超過) 掉到未滿時，從現在開始計時；其餘沿用已結算的時間點
            updated_at = now.isoformat() if info["stamina"] >= STAMINA_MAX else info["updated_at"]
            await db.execute(
                "UPDATE users SET stamina = ?, stamina_updated_at = ? WHERE user_id = ?",
                (new_value, updated_at, user_id),
            )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {**calc_stamina(new_value, updated_at, now), "ok": True}


async def get_stamina(user_id: int) -> dict:
    """查詢目前體力 (唯讀，不替對方建資料)"""
    async with connect() as db:
        async with db.execute(
            "SELECT stamina, stamina_updated_at FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return calc_stamina(None, None)
    return calc_stamina(row["stamina"], row["stamina_updated_at"])


async def spend_stamina(user_id: int, amount: int) -> dict:
    """消耗體力；不夠時不扣並回傳 ok=False"""
    return await _change_stamina(user_id, -abs(amount), require_enough=True)


async def add_stamina(user_id: int, amount: int) -> dict:
    """回復 / 扣除體力 (道具、管理員用)；可以超過 240，扣到 0 為止"""
    return await _change_stamina(user_id, amount, require_enough=False)


# 🍽️ 一天最多吃幾個體力道具 (含簽到送的 🍙；台灣時間 00:00 重置)：防「採集 ➔ 做體力料理 ➔ 吃 ➔ 再採集」無限循環 (使用者 2026-11-16)
STAMINA_ITEM_DAILY_LIMIT = 3


def stamina_items_left(day: str | None, used: int | None, now: datetime | None = None) -> int:
    """(純計算) 今天還能吃幾個體力道具；users.stamina_item_day 不是今天 = 今天還沒吃過"""
    if day != tw_day(now):
        return STAMINA_ITEM_DAILY_LIMIT
    return max(0, STAMINA_ITEM_DAILY_LIMIT - (used or 0))


async def get_stamina_item_left(user_id: int, now: datetime | None = None) -> int:
    """今天還能吃幾個體力道具 (唯讀)"""
    async with connect() as db:
        async with db.execute("SELECT stamina_item_day, stamina_item_used FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
    return stamina_items_left(row["stamina_item_day"], row["stamina_item_used"], now) if row else STAMINA_ITEM_DAILY_LIMIT


async def use_stamina_item(user_id: int, item_id: str, restore: int, qty: int = 1, now: datetime | None = None) -> dict:
    """
    使用 qty 個體力道具：背包 -qty、體力 +restore×qty (可超過 240)、今天吃的數量 +qty，同一個交易
    回傳 {"ok": bool, "left": 剩餘數量, "daily_left": 今天還能吃幾個, "used": qty, "before", 以及 calc_stamina 的欄位 (使用後)}
    失敗 (什麼都不改)：reason = not_owned (背包不夠 qty 個) / daily_limit (今天的額度不夠) / bad_qty
    """
    now = now or datetime.now(timezone.utc)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_user(db, user_id)
            async with db.execute(
                "SELECT inventory, stamina, stamina_updated_at, stamina_item_day, stamina_item_used FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
            inventory = _load_inventory(row["inventory"])
            info = calc_stamina(row["stamina"], row["stamina_updated_at"], now)
            daily_left = stamina_items_left(row["stamina_item_day"], row["stamina_item_used"], now)
            fail = None
            if qty < 1:
                fail = "bad_qty"
            elif inventory.get(item_id, 0) < qty:
                fail = "not_owned"
            elif daily_left < qty:
                fail = "daily_limit"
            if fail:
                await db.rollback()
                return {**info, "ok": False, "reason": fail, "left": inventory.get(item_id, 0), "daily_left": daily_left}

            inventory[item_id] -= qty
            left = inventory[item_id]
            if left <= 0:
                del inventory[item_id]
            new_value = info["stamina"] + restore * qty
            updated_at = now.isoformat() if info["stamina"] >= STAMINA_MAX else info["updated_at"]
            used_today = STAMINA_ITEM_DAILY_LIMIT - daily_left + qty
            await db.execute(
                "UPDATE users SET inventory = ?, stamina = ?, stamina_updated_at = ?, stamina_item_day = ?, stamina_item_used = ? "
                "WHERE user_id = ?",
                (json.dumps(inventory, ensure_ascii=False), new_value, updated_at, tw_day(now), used_today, user_id),
            )
            await add_player_stat(db, user_id, "eat_stamina", qty)   # 🍳 美食家稱號：吃了幾個體力道具 (含飯糰；0.35.007 起)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {**calc_stamina(new_value, updated_at, now), "ok": True, "left": left, "before": info["stamina"],
            "used": qty, "daily_left": daily_left - qty}

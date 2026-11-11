"""
💹 經濟系統 (Database/Users.db)：神社經營、浮動市值、分解、市場、轉帳

資料表結構定義在 User_DB_Manager.SCHEMA_STATEMENTS (同一個 Users.db，init_db 一起建立)。
跟體力一樣「不用背景排程」：神社在每次查看 / 操作時才依經過時間結算，市值在第一次有人用到時補結算前幾天。

所有數值都是使用者 2026-11-05 指定的 (見 TODO.md / CHANGELOG.md 0.23.000)，要改數值改這裡的常數就好。
"""
import json
import math
import random
from datetime import date, datetime, timedelta, timezone

from Database.User_DB_Manager import connect, _ensure_user, _insert_cards, _load_inventory, tw_day, calc_stamina, STAMINA_MAX
from Database import shrine_data
from Database.events import load_events, game_rules, all_guests, event_item_ids

HOUR = timedelta(hours=1)

# =========================================================
# ⛩️ 1. 神社經營
# =========================================================
SHRINE_INCOME_PER_HOUR = 5000          # 效率 100% 時每小時進賽錢箱的錢
SHRINE_BOX_MAX = 200_000               # 賽錢箱上限，滿了就不再累積 (要用指令回收)

DIRT_INTERVAL = timedelta(hours=4)     # 每 4 小時髒一階
DIRT_MAX = 4                           # 乾淨 0 ➔ 最髒 4 (5 個階段)
DIRT_PENALTY = 0.10                    # 每階 −10% (最多 −40%)

YOUKAI_MAX = 5
YOUKAI_SPAWN = [0.80, 0.70, 0.55, 0.35, 0.10]   # 每小時生成機率：目前 0 隻時 80%、1 隻時 70%…
YOUKAI_PENALTY = 0.08                  # 每隻 −8% (最多 −40%)
YOUKAI_REWARD = (800, 1500)            # 打退一隻的賽錢 (隨機，含頭尾；v0.27.004 從固定 1000 改)；打退後留下晦氣 ➔ 清潔度掉一階

GUEST_EVERY_HOURS = 2                  # 每 2 小時判定一次參拜客
GUEST_MAX = 5
GUEST_SPAWN = [0.90, 0.80, 0.70, 0.60, 0.50]    # 目前 0 位時 90%、1 位時 80%…
MOOD_STEP = 10                         # 心情 10% 一個區間
MOOD_INTERVAL = timedelta(hours=4)     # 每 4 小時掉一個區間，掉到 0 就離開
SERVING_REWARD = 2000                  # 每「份」餐點：2000 × 心情² (不保底；v0.27.000 從 1000 調成 2000)
ORDER_SIZE = (1, 3)                    # 每位客人點 1~3 道 (不同種類)，點的每道都要給 1 份
FAVORITE_BONUS = 1.5                   # 額外招待 (可選 1 份) 正中客人最愛 ➔ 整筆 ×1.5
SERVE_TYPES_ORDER = ("food", "drink", "dessert")

SHRINE_MAX_CATCHUP = timedelta(days=14)   # 太久沒來時只模擬最後 14 天 (那時賽錢箱早就滿了)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def shrine_dirt(state: dict, t: datetime) -> int:
    """t 時的清潔度階段 (0 乾淨 ~ 4)：距離上次清掃每 4 小時 +1，再加上妖怪留下的晦氣"""
    base = int((t - _dt(state["clean_at"])) / DIRT_INTERVAL)
    return min(DIRT_MAX, max(0, base) + state["dirt_extra"])


def shrine_efficiency(dirt: int, youkai: int) -> float:
    return max(0.0, 1 - DIRT_PENALTY * dirt - YOUKAI_PENALTY * youkai)


def guest_mood(guest: dict, t: datetime) -> int:
    """參拜客心情 (%)：來的時候 100，每 4 小時 −10"""
    steps = int((t - _dt(guest["arrived_at"])) / MOOD_INTERVAL)
    return max(0, 100 - MOOD_STEP * steps)


def serving_reward(mood: int, portions: int = 1) -> int:
    """招待報酬 (不含加成)：每份 2000 × 心情²"""
    return int(SERVING_REWARD * (mood / 100) ** 2 * portions)


def calc_serve_reward(mood: int, order: list[str], extra: str | None, rules: dict, favorite: str | None) -> dict:
    """
    招待報酬 = 份數 × 2000 × 心情² × 1.2^(活動料理份數) × 1.5 (額外那份正中最愛)
    兩種加成都乘在過完心情之後的金額上 (使用者 2026-11-05 指定)
    """
    served = list(order) + ([extra] if extra else [])
    base = SERVING_REWARD * (mood / 100) ** 2 * len(served)
    event_count = sum(1 for d in served if d in rules["event_dishes"])
    favorite_hit = bool(extra) and extra == favorite
    mult = rules["event_dish_bonus"] ** event_count * (FAVORITE_BONUS if favorite_hit else 1)
    return {"base": int(base), "event_count": event_count, "favorite_hit": favorite_hit,
            "multiplier": mult, "total": int(round(base * mult))}


def make_order(rules: dict, rng=random) -> list[str]:
    """點餐：1~3 個不同種類，每類一道；活動期間每道有 order_event_chance 機率是活動料理"""
    n = ORDER_SIZE[0] + int(rng.random() * (ORDER_SIZE[1] - ORDER_SIZE[0] + 1))
    types = list(SERVE_TYPES_ORDER)
    picked = []
    for _ in range(min(n, len(types))):
        t = rng.choice(types)
        types.remove(t)
        normal = [d for d, k in rules["dish_types"].items() if k == t and d not in rules["event_dishes"]]
        special = [d for d, k in rules["dish_types"].items() if k == t and d in rules["event_dishes"]]
        if special and rng.random() < rules["order_event_chance"]:
            picked.append(rng.choice(special))
        else:
            picked.append(rng.choice(normal))
    order = sorted(picked, key=lambda d: SERVE_TYPES_ORDER.index(rules["dish_types"][d]))
    return order


def new_guest(rules: dict, t: datetime, rng=random) -> dict:
    return {"id": f"{int(t.timestamp()):x}{int(rng.random() * 4096):03x}", "kind": rng.choice(sorted(rules["guests"])),
            "arrived_at": t.isoformat(), "order": make_order(rules, rng)}


_GUEST_NAME_TO_KEY = {g["name"]: k for k, g in shrine_data.GUESTS.items()}


def sanitize_guests(state: dict, rules: dict, rng=random):
    """
    舊資料或活動結束後的修正 (原地修改)：舊版用中文名稱當 kind ➔ 換成 key；
    已結束活動的客人離開；點了不存在的料理 (活動結束) ➔ 重新點餐；補上 id
    """
    fixed = []
    for i, g in enumerate(state["guests"]):
        g = dict(g)
        g["kind"] = _GUEST_NAME_TO_KEY.get(g["kind"], g["kind"])
        if g["kind"] not in rules["guests"]:
            continue
        if not g.get("order") or any(d not in rules["dish_types"] for d in g["order"]):
            g["order"] = make_order(rules, rng)
        g.setdefault("id", f"g{i}{int(_dt(g['arrived_at']).timestamp()):x}")
        fixed.append(g)
    state["guests"] = fixed


def advance_shrine(state: dict, now: datetime, rng=random, rules: dict | None = None) -> dict:
    """
    純計算：把神社從 updated_at 推進到 now (不寫資料庫)
    - 賽錢箱依當下效率連續累積 (效率在整點事件、變髒的時間點改變)
    - 每個整點 (以建立時間為準)：妖怪依目前數量機率生成；每 2 小時：參拜客依目前人數機率來訪
    - 參拜客心情掉到 0 就離開；來的時候就決定好點什麼 (rules = events.game_rules，含活動)
    """
    rules = rules or game_rules([])
    st = dict(state)
    st["guests"] = list(state["guests"])
    anchor = _dt(st["created_at"])
    t = _dt(st["updated_at"])
    if now - t > SHRINE_MAX_CATCHUP:
        t = now - SHRINE_MAX_CATCHUP
        st["tick"] = max(st["tick"], int((t - anchor) / HOUR))

    while t < now:
        next_event = anchor + (st["tick"] + 1) * HOUR
        dirt = shrine_dirt(st, t)
        seg_end = min(now, next_event)
        if dirt < DIRT_MAX:
            clean_at = _dt(st["clean_at"])
            next_dirt = clean_at + (int((t - clean_at) / DIRT_INTERVAL) + 1) * DIRT_INTERVAL
            seg_end = min(seg_end, next_dirt)
        seg_end = max(t, seg_end)   # 保險：事件時間點已經過了就只處理事件、不算收入
        income = (seg_end - t) / HOUR * SHRINE_INCOME_PER_HOUR * shrine_efficiency(dirt, st["youkai"])
        st["box"] = min(SHRINE_BOX_MAX, st["box"] + income)
        t = seg_end

        if t >= next_event:
            st["tick"] += 1
            st["guests"] = [g for g in st["guests"] if guest_mood(g, t) > 0]
            if st["youkai"] < YOUKAI_MAX and rng.random() < YOUKAI_SPAWN[st["youkai"]]:
                st["youkai"] += 1
            if st["tick"] % GUEST_EVERY_HOURS == 0 and len(st["guests"]) < GUEST_MAX \
                    and rng.random() < GUEST_SPAWN[len(st["guests"])]:
                st["guests"].append(new_guest(rules, t, rng))

    st["guests"] = [g for g in st["guests"] if guest_mood(g, now) > 0]
    st["updated_at"] = now.isoformat()
    return st


def shrine_summary(state: dict, now: datetime, rules: dict | None = None) -> dict:
    """畫面要顯示的資料 (已結算後的 state)；客人的台詞模板與提示也放進來 (料理名稱由畫面填)"""
    rules = rules or game_rules([])
    guest_info = {**all_guests(), **rules["guests"]}
    dirt = shrine_dirt(state, now)
    eff = shrine_efficiency(dirt, state["youkai"])
    next_dirt_at = None
    if dirt < DIRT_MAX:
        clean_at = _dt(state["clean_at"])
        next_dirt_at = clean_at + (int((now - clean_at) / DIRT_INTERVAL) + 1) * DIRT_INTERVAL
    guests = []
    for g in state["guests"]:
        arrived = _dt(g["arrived_at"])
        mood = guest_mood(g, now)
        steps = int((now - arrived) / MOOD_INTERVAL)
        info = guest_info.get(g["kind"], {"name": g["kind"], "emoji": "👤", "lines": {}, "hint": ""})
        guests.append({
            "id": g.get("id"), "kind": g["kind"], "name": info["name"], "emoji": info["emoji"],
            "event": info.get("event"), "order": list(g.get("order", [])), "hint": info.get("hint", ""),
            "line": info.get("lines", {}).get(shrine_data.mood_tier(mood), "{order}"),
            "mood": mood, "arrived_at": arrived,
            "next_drop_at": arrived + (steps + 1) * MOOD_INTERVAL,
            "leave_at": arrived + (100 // MOOD_STEP) * MOOD_INTERVAL,
            "reward_per_portion": serving_reward(mood),
        })
    income = SHRINE_INCOME_PER_HOUR * eff
    box = int(state["box"])
    full_in = None
    if box < SHRINE_BOX_MAX and income > 0:
        full_in = now + timedelta(hours=(SHRINE_BOX_MAX - state["box"]) / income)
    return {
        "box": box, "box_max": SHRINE_BOX_MAX, "income_per_hour": int(income), "box_full_at": full_in,
        "dirt": dirt, "dirt_max": DIRT_MAX, "dirt_penalty": DIRT_PENALTY * dirt, "next_dirt_at": next_dirt_at,
        "youkai": state["youkai"], "youkai_max": YOUKAI_MAX, "youkai_penalty": YOUKAI_PENALTY * state["youkai"],
        "efficiency": eff, "guests": guests, "guest_max": GUEST_MAX,
        "next_event_at": _dt(state["created_at"]) + (state["tick"] + 1) * HOUR,
    }


def _new_shrine(now: datetime) -> dict:
    t = now.isoformat()
    return {"created_at": t, "updated_at": t, "tick": 0, "box": 0.0, "clean_at": t, "dirt_extra": 0, "youkai": 0, "guests": []}


async def _shrine_tx(user_id: int, action=None, now: datetime | None = None, rng=random) -> dict:
    """
    神社共用交易：讀取 (沒有就建立) ➔ 結算到現在 ➔ action(state, db, rules) 修改 ➔ 寫回
    rules = 這一刻的遊戲規則 (含進行中的活動)。回傳 {"summary": shrine_summary, **action 的回傳}
    """
    now = now or datetime.now(timezone.utc)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_user(db, user_id)
            async with db.execute("SELECT * FROM shrines WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
            if row is None:
                state = _new_shrine(now)
            else:
                state = dict(row)
                state["guests"] = json.loads(state["guests"] or "[]")
            rules = game_rules(await _active_events(db, now))
            sanitize_guests(state, rules, rng)
            state = advance_shrine(state, now, rng, rules)
            extra = (await action(state, db, rules)) if action else {}
            await db.execute(
                """
                INSERT INTO shrines (user_id, created_at, updated_at, tick, box, clean_at, dirt_extra, youkai, guests)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    updated_at = excluded.updated_at, tick = excluded.tick, box = excluded.box,
                    clean_at = excluded.clean_at, dirt_extra = excluded.dirt_extra,
                    youkai = excluded.youkai, guests = excluded.guests
                """,
                (user_id, state["created_at"], state["updated_at"], state["tick"], state["box"],
                 state["clean_at"], state["dirt_extra"], state["youkai"], json.dumps(state["guests"], ensure_ascii=False)),
            )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"summary": shrine_summary(state, now, rules), **extra}


async def get_shrine(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """查看神社 (會結算並存檔)"""
    return await _shrine_tx(user_id, now=now, rng=rng)


async def shrine_collect(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """回收賽錢箱：整數部分轉進賽錢，零頭留在箱子裡"""
    async def action(state, db, rules):
        amount = int(state["box"])
        state["box"] -= amount
        await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (amount, user_id))
        async with db.execute("SELECT money FROM users WHERE user_id = ?", (user_id,)) as cursor:
            money = (await cursor.fetchone())["money"]
        return {"collected": amount, "money": money}
    return await _shrine_tx(user_id, action, now, rng)


async def shrine_clean(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """清掃：清潔度回到乾淨 (晦氣一起清掉)，沒有獎勵、沒有冷卻"""
    now = now or datetime.now(timezone.utc)

    async def action(state, db, rules):
        before = shrine_dirt(state, now)
        state["clean_at"] = now.isoformat()
        state["dirt_extra"] = 0
        return {"before": before}
    return await _shrine_tx(user_id, action, now, rng)


async def shrine_defeat(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """治退一隻妖怪：+800～1500 賽錢 (隨機)，留下晦氣 (清潔度 +1 階，不會超過最髒)"""
    now = now or datetime.now(timezone.utc)

    async def action(state, db, rules):
        if state["youkai"] <= 0:
            return {"ok": False}
        state["youkai"] -= 1
        if shrine_dirt(state, now) < DIRT_MAX:
            state["dirt_extra"] += 1
        low, high = YOUKAI_REWARD
        reward = min(high, low + int(rng.random() * (high - low + 1)))
        await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (reward, user_id))
        return {"ok": True, "reward": reward}
    return await _shrine_tx(user_id, action, now, rng)


async def admin_set_shrine(user_id: int, box: int | None = None, dirt: int | None = None, youkai: int | None = None,
                           guests: int | None = None, guest_mood: int = 100, now: datetime | None = None, rng=random) -> dict:
    """
    【管理員】調整神社 (先結算到現在再改)：
    box 賽錢箱、dirt 清潔度階段 (從現在開始重新計時)、youkai 妖怪數、guests 參拜客數 (心情都設成 guest_mood)
    """
    now = now or datetime.now(timezone.utc)

    async def action(state, db, rules):
        if box is not None:
            state["box"] = float(max(0, min(SHRINE_BOX_MAX, box)))
        if dirt is not None:
            state["clean_at"] = now.isoformat()
            state["dirt_extra"] = max(0, min(DIRT_MAX, dirt))
        if youkai is not None:
            state["youkai"] = max(0, min(YOUKAI_MAX, youkai))
        if guests is not None:
            mood = max(MOOD_STEP, min(100, guest_mood))
            arrived = now - ((100 - mood) // MOOD_STEP) * MOOD_INTERVAL
            state["guests"] = [new_guest(rules, arrived, rng) for _ in range(max(0, min(GUEST_MAX, guests)))]
            for i, g in enumerate(state["guests"]):
                g["id"] = f"{g['id']}{i}"
        return {}
    return await _shrine_tx(user_id, action, now, rng)


async def admin_reset_shrine(user_id: int) -> bool:
    """【管理員】刪除神社資料 (下次打開時重新建立，賽錢箱歸零)"""
    async with connect() as db:
        cursor = await db.execute("DELETE FROM shrines WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0


# =========================================================
# 🎪 活動狀態 (economy_meta 的 event:<id> = {"status", "started_at", "ends_at"})
#   沒有紀錄 + auto_start ➔ 視為進行中 (測試階段，沒有結束時間)；過了 ends_at ➔ 自動結束並清空活動道具
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


async def _active_events(db, now: datetime) -> list[dict]:
    """進行中的活動 (要在交易裡呼叫：過期的活動會在這裡結束並清空道具)"""
    active = []
    for ev in load_events().values():
        st = await _event_state(db, ev["id"])
        if st is None:
            if ev.get("auto_start"):
                active.append(ev)
            continue
        if st.get("status") != "active":
            continue
        if st.get("ends_at") and now >= _dt(st["ends_at"]):
            await _end_event(db, ev, now)
            continue
        active.append(ev)
    return active


async def get_events_overview(now: datetime | None = None) -> list[dict]:
    """/event 用：每個活動 + 狀態 [{"event", "status" (active / ended / upcoming), "started_at", "ends_at"}]"""
    now = now or datetime.now(timezone.utc)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            active_ids = {ev["id"] for ev in await _active_events(db, now)}
            out = []
            for ev in load_events().values():
                st = await _event_state(db, ev["id"]) or {}
                status = "active" if ev["id"] in active_ids else ("ended" if st.get("status") == "ended" else "upcoming")
                out.append({"event": ev, "status": status, "started_at": st.get("started_at"), "ends_at": st.get("ends_at")})
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return out


async def admin_start_event(event_id: str, days: int | None = None, now: datetime | None = None) -> bool:
    """【管理員】開始活動；days=None 不設結束時間 (測試用)"""
    now = now or datetime.now(timezone.utc)
    if event_id not in load_events():
        return False
    ends = (now + timedelta(days=days)).isoformat() if days else None
    async with connect() as db:
        await _set_meta(db, f"event:{event_id}", json.dumps({"status": "active", "started_at": now.isoformat(), "ends_at": ends}))
        await db.commit()
    return True


async def admin_end_event(event_id: str, now: datetime | None = None) -> int | None:
    """【管理員】結束活動並清空所有玩家的活動道具；回傳受影響的玩家數 (找不到活動回傳 None)"""
    now = now or datetime.now(timezone.utc)
    ev = load_events().get(event_id)
    if ev is None:
        return None
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
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
    return rules


# =========================================================
# 🗺️ 採集 / 🍳 料理 / 🏪 雜貨店 / 🍵 招待
# =========================================================
async def _read_user(db, user_id: int) -> dict:
    await _ensure_user(db, user_id)
    async with db.execute("SELECT money, inventory, stamina, stamina_updated_at FROM users WHERE user_id = ?", (user_id,)) as cursor:
        row = dict(await cursor.fetchone())
    row["inventory"] = _load_inventory(row["inventory"])
    return row


async def _write_inventory(db, user_id: int, inv: dict):
    inv = {k: v for k, v in inv.items() if v > 0}
    await db.execute("UPDATE users SET inventory = ? WHERE user_id = ?", (json.dumps(inv, ensure_ascii=False), user_id))


def roll_explore(location: dict, rng=random) -> dict:
    """一趟採集 (純計算)：3~5 個素材，SPECIAL_CHANCE 機率發生事件 (好壞各半)"""
    lo, hi = shrine_data.EXPLORE_DROPS
    n = lo + int(rng.random() * (hi - lo + 1))
    drops = {}
    for _ in range(n):
        m = rng.choice(location["drops"])
        drops[m] = drops.get(m, 0) + 1
    event = None
    if rng.random() < shrine_data.SPECIAL_CHANCE:
        good = rng.random() < 0.5
        ev = location["good" if good else "bad"]
        fx = ev["effect"]
        for m, k in fx.get("add", {}).items():
            drops[m] = drops.get(m, 0) + k
        if fx.get("empty"):
            drops = {}
        if fx.get("half"):
            drops = {m: k // 2 for m, k in drops.items() if k // 2 > 0}
        for _ in range(fx.get("lose", 0)):
            if drops:
                m = rng.choice(sorted(drops))
                drops[m] -= 1
                if drops[m] <= 0:
                    del drops[m]
        event = {"good": good, "text": ev["text"]}
    return {"drops": drops, "event": event}


async def explore(user_id: int, location_id: str, times: int = 1, now: datetime | None = None, rng=random) -> dict:
    """
    採集 times 趟 (體力不夠時做到體力用完為止，至少要夠 1 趟)
    失敗 reason：not_found (地點不存在 / 活動地點已關閉)、no_stamina
    """
    now = now or datetime.now(timezone.utc)
    cost = shrine_data.EXPLORE_STAMINA
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            rules = game_rules(await _active_events(db, now))
            location = rules["locations"].get(location_id)
            if location is None:
                await db.rollback()
                return {"ok": False, "reason": "not_found"}
            user = await _read_user(db, user_id)
            info = calc_stamina(user["stamina"], user["stamina_updated_at"], now)
            runs = min(max(1, times), info["stamina"] // cost)
            if runs <= 0:
                await db.rollback()
                return {"ok": False, "reason": "no_stamina", "stamina": info["stamina"], "cost": cost}
            results, total = [], {}
            for _ in range(runs):
                r = roll_explore(location, rng)
                results.append(r)
                for m, k in r["drops"].items():
                    total[m] = total.get(m, 0) + k
            inv = user["inventory"]
            for m, k in total.items():
                inv[m] = inv.get(m, 0) + k
            await _write_inventory(db, user_id, inv)
            updated_at = now.isoformat() if info["stamina"] >= STAMINA_MAX else info["updated_at"]
            new_stamina = info["stamina"] - runs * cost
            await db.execute("UPDATE users SET stamina = ?, stamina_updated_at = ? WHERE user_id = ?", (new_stamina, updated_at, user_id))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "location": location, "runs": results, "total": total,
            "stamina": calc_stamina(new_stamina, updated_at, now), "requested": times}


async def cook(user_id: int, dish_id: str, times: int = 1, now: datetime | None = None) -> dict:
    """料理 times 鍋 (每鍋 COOK_YIELD 份)；素材不夠 ➔ reason=not_enough + missing {素材: 還差幾個}"""
    now = now or datetime.now(timezone.utc)
    times = max(1, times)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            rules = game_rules(await _active_events(db, now))
            recipe = rules["recipes"].get(dish_id)
            if recipe is None:
                await db.rollback()
                return {"ok": False, "reason": "not_found"}
            user = await _read_user(db, user_id)
            inv = user["inventory"]
            missing = {m: k * times - inv.get(m, 0) for m, k in recipe.items() if inv.get(m, 0) < k * times}
            if missing:
                await db.rollback()
                return {"ok": False, "reason": "not_enough", "missing": missing}
            for m, k in recipe.items():
                inv[m] -= k * times
            made = shrine_data.COOK_YIELD * times
            inv[dish_id] = inv.get(dish_id, 0) + made
            await _write_inventory(db, user_id, inv)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "made": made, "have": inv[dish_id]}


async def shop_buy(user_id: int, material_id: str, qty: int) -> dict:
    """雜貨店買素材；reason：not_found / bad_qty / not_enough"""
    price = shrine_data.SHOP_PRICES.get(material_id)
    if price is None:
        return {"ok": False, "reason": "not_found"}
    if qty < 1:
        return {"ok": False, "reason": "bad_qty"}
    cost = price * qty
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            user = await _read_user(db, user_id)
            if user["money"] < cost:
                await db.rollback()
                return {"ok": False, "reason": "not_enough", "money": user["money"], "cost": cost}
            inv = user["inventory"]
            inv[material_id] = inv.get(material_id, 0) + qty
            await _write_inventory(db, user_id, inv)
            await db.execute("UPDATE users SET money = money - ? WHERE user_id = ?", (cost, user_id))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "cost": cost, "money": user["money"] - cost, "have": inv[material_id]}


async def serve_guest(user_id: int, guest_id: str, extra: str | None = None, now: datetime | None = None, rng=random) -> dict:
    """
    招待一位客人：點的料理每道扣 1 份 (一定要齊)，額外招待可以再端 1 份任意料理；客人拿到後離開
    失敗 reason：not_found (客人已經離開) / missing (料理不夠，missing = {料理: 還差幾份}) / bad_extra
    """
    now = now or datetime.now(timezone.utc)

    async def action(state, db, rules):
        guest = next((g for g in state["guests"] if g.get("id") == guest_id), None)
        if guest is None:
            return {"ok": False, "reason": "not_found"}
        if extra and extra not in rules["dish_types"]:
            return {"ok": False, "reason": "bad_extra"}
        mood = guest_mood(guest, now)
        need = {}
        for d in guest["order"] + ([extra] if extra else []):
            need[d] = need.get(d, 0) + 1
        user = await _read_user(db, user_id)
        inv = user["inventory"]
        missing = {d: k - inv.get(d, 0) for d, k in need.items() if inv.get(d, 0) < k}
        if missing:
            return {"ok": False, "reason": "missing", "missing": missing}
        favorite = rules["guests"].get(guest["kind"], {}).get("favorite")
        reward = calc_serve_reward(mood, guest["order"], extra, rules, favorite)
        for d, k in need.items():
            inv[d] -= k
        await _write_inventory(db, user_id, inv)
        await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (reward["total"], user_id))
        state["guests"] = [g for g in state["guests"] if g.get("id") != guest_id]
        return {"ok": True, "reward": reward, "mood": mood, "guest": guest, "extra": extra,
                "money": user["money"] + reward["total"]}
    return await _shrine_tx(user_id, action, now, rng)


async def get_inventory(user_id: int) -> dict:
    async with connect() as db:
        async with db.execute("SELECT inventory FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
    return _load_inventory(row["inventory"]) if row else {}


# =========================================================
# 💹 2. 浮動市值 (每天台灣時間 00:00 結算)
# =========================================================
OFFICIAL_PRICES = {"N": 50, "R": 100, "SR": 500, "SSR": 1000, "UR": 10000, "LR": 50000}   # 官方回收價 = 市值的保底
PRICE_DAILY_LIMIT = 0.10       # 每天漲跌最多 ±10%
PRICE_IDLE_RISE = 0.02         # 當天沒人賣 ➔ +2% (也是一天最多漲多少)
NEUTRAL_RATIO = 0.5            # 賣出 = 當天新抽到張數的 50% 時持平
SATURATE_RATIO = 3             # 賣出是持平的 3 倍 ➔ −10% (中間照比例)
MAX_SETTLE_DAYS = 60           # 很久沒人用時最多補結算 60 天


def completeness_multiplier(completeness: float) -> float:
    """
    完整度倍率 (曲線)：0.5 = ×1
    - 0.5 ➔ 1：越接近 1 加成越多，到 1 時 ×1.2
    - 0.5 ➔ 0：越接近 0 減少得越少，到 0 時 ×0.2
    """
    c = max(0.0, min(1.0, completeness))
    if c >= 0.5:
        return 1 + 0.2 * ((c - 0.5) / 0.5) ** 2
    return 0.2 + 0.8 * (c / 0.5) ** 2


def card_value(price: float, completeness: float) -> int:
    """單張卡的價值 = 市值 × 完整度倍率 (分解拿到的錢)"""
    return max(1, int(round(price * completeness_multiplier(completeness))))


def price_change(sold: int, expected: float) -> float:
    """
    一天的漲跌幅：expected = 當天全服抽卡數 × 這張卡的抽中機率 (至少算 1 張)，持平點 = expected × 50%
    - 賣得比持平點少：從 +2% (沒人賣) 平滑降到 0% (剛好持平)
    - 賣得比持平點多：往下跌，賣出是持平點 3 倍時跌到 −10% (上限)
    整條曲線連續、賣越多一定越便宜 (v0.24.000 改：原本只賣 1 張會比沒人賣漲更多)
    """
    neutral = NEUTRAL_RATIO * max(1.0, expected)
    x = max(0, sold) / neutral
    if x <= 1:
        return PRICE_IDLE_RISE * (1 - x)
    return -PRICE_DAILY_LIMIT * min(1.0, (x - 1) / (SATURATE_RATIO - 1))


async def _get_meta(db, key: str):
    async with db.execute("SELECT value FROM economy_meta WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
    return row["value"] if row else None


async def _set_meta(db, key: str, value: str):
    await db.execute("INSERT INTO economy_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


async def _prices(db) -> dict:
    async with db.execute("SELECT character_key, rarity, price FROM market_prices") as cursor:
        return {(r["character_key"], r["rarity"]): r["price"] for r in await cursor.fetchall()}


def _price_of(prices: dict, key: str, rarity: str) -> float:
    return prices.get((key, rarity), OFFICIAL_PRICES.get(rarity, 1))


async def settle_prices(probabilities: dict, now: datetime | None = None) -> int:
    """
    補結算到昨天為止的每一天 (第一次呼叫只記錄起點，不回溯)
    probabilities = {(角色, 階級): (卡池, 單抽抽中機率)}，由抽卡模組依卡池內容算好傳進來
    回傳這次結算了幾天
    """
    now = now or datetime.now(timezone.utc)
    today = date.fromisoformat(tw_day(now))
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            last = await _get_meta(db, "last_settled_day")
            if last is None:
                await _set_meta(db, "last_settled_day", (today - timedelta(days=1)).isoformat())
                await db.commit()
                return 0
            day = date.fromisoformat(last) + timedelta(days=1)
            day = max(day, today - timedelta(days=MAX_SETTLE_DAYS))
            prices = await _prices(db)
            settled = 0
            while day < today:
                d = day.isoformat()
                async with db.execute("SELECT pool, draws FROM daily_draws WHERE day = ?", (d,)) as cursor:
                    draws = {r["pool"]: r["draws"] for r in await cursor.fetchall()}
                async with db.execute("SELECT character_key, rarity, sold FROM daily_sales WHERE day = ?", (d,)) as cursor:
                    sales = {(r["character_key"], r["rarity"]): r["sold"] for r in await cursor.fetchall()}
                for key in set(probabilities) | set(sales):
                    pool, p = probabilities.get(key, (None, 0.0))
                    expected = draws.get(pool, 0) * p
                    change = price_change(sales.get(key, 0), expected)
                    official = OFFICIAL_PRICES.get(key[1], 1)
                    new_price = max(official, _price_of(prices, *key) * (1 + change))
                    prices[key] = new_price
                    await db.execute(
                        "INSERT INTO price_history (day, character_key, rarity, price, change) VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(day, character_key, rarity) DO UPDATE SET price = excluded.price, change = excluded.change",
                        (d, key[0], key[1], new_price, change),
                    )
                settled += 1
                day += timedelta(days=1)
            await db.executemany(
                "INSERT INTO market_prices (character_key, rarity, price) VALUES (?, ?, ?) "
                "ON CONFLICT(character_key, rarity) DO UPDATE SET price = excluded.price",
                [(k[0], k[1], v) for k, v in prices.items()],
            )
            await _set_meta(db, "last_settled_day", (today - timedelta(days=1)).isoformat())
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return settled


async def admin_set_price(character_key: str, rarity: str, price: float | None):
    """【管理員】直接設定市值；price=None 回到官方價 (之後每日結算照常進行，結算時仍不會低於官方價)"""
    async with connect() as db:
        if price is None:
            await db.execute("DELETE FROM market_prices WHERE character_key = ? AND rarity = ?", (character_key, rarity))
        else:
            await db.execute(
                "INSERT INTO market_prices (character_key, rarity, price) VALUES (?, ?, ?) "
                "ON CONFLICT(character_key, rarity) DO UPDATE SET price = excluded.price",
                (character_key, rarity, price),
            )
        await db.commit()


async def get_card_values(user_ids: list[int]) -> dict:
    """排行榜用：每位玩家持有的卡 (含上架中的) 照目前市值 × 完整度倍率算出的總價值 {user_id: 價值}"""
    if not user_ids:
        return {}
    marks = ", ".join("?" for _ in user_ids)
    totals = {uid: 0 for uid in user_ids}
    async with connect() as db:
        prices = await _prices(db)
        for sql in (f"SELECT user_id AS uid, character_key, rarity, completeness FROM gacha_cards WHERE user_id IN ({marks})",
                    f"SELECT seller_id AS uid, character_key, rarity, completeness FROM market_listings WHERE seller_id IN ({marks})"):
            async with db.execute(sql, tuple(user_ids)) as cursor:
                for r in await cursor.fetchall():
                    totals[r["uid"]] += card_value(_price_of(prices, r["character_key"], r["rarity"]), r["completeness"])
    return totals


async def get_market_prices() -> dict:
    """{(角色, 階級): 市值}；沒有紀錄的卡 = 官方價 (用 price_of 查)"""
    async with connect() as db:
        return await _prices(db)


def price_of(prices: dict, key: str, rarity: str) -> float:
    return _price_of(prices, key, rarity)


async def get_price_history(character_key: str, rarity: str, days: int = 7) -> list[dict]:
    """最近幾天的結算紀錄 (舊 ➔ 新) [{"day", "price", "change"}]"""
    async with connect() as db:
        async with db.execute(
            "SELECT day, price, change FROM price_history WHERE character_key = ? AND rarity = ? ORDER BY day DESC LIMIT ?",
            (character_key, rarity, days),
        ) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]
    return rows[::-1]


async def get_today_activity(character_key: str, rarity: str, now: datetime | None = None) -> int:
    """今天 (台灣時間) 這張卡已賣出幾張"""
    async with connect() as db:
        async with db.execute(
            "SELECT sold FROM daily_sales WHERE day = ? AND character_key = ? AND rarity = ?",
            (tw_day(now), character_key, rarity),
        ) as cursor:
            row = await cursor.fetchone()
    return row["sold"] if row else 0


async def _log_sale(db, key: str, rarity: str, day: str, count: int = 1):
    await db.execute(
        "INSERT INTO daily_sales (day, character_key, rarity, sold) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(day, character_key, rarity) DO UPDATE SET sold = sold + excluded.sold",
        (day, key, rarity, count),
    )


async def _log_trade(db, kind, price, day, now, seller=None, buyer=None, card=None, fee=0):
    await db.execute(
        "INSERT INTO market_trades (kind, seller_id, buyer_id, instance_id, character_key, rarity, price, fee, day, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (kind, seller, buyer, card and card["instance_id"], card and card["character_key"], card and card["rarity"],
         price, fee, day, now.isoformat()),
    )


# =========================================================
# ♻️ 3. 分解卡牌 (依市值 × 完整度回收；不需要開通交易)
# =========================================================
async def decompose_cards(user_id: int, instance_ids: list[str], now: datetime | None = None) -> dict:
    """
    分解指定的卡 (同一個交易)：每張拿到 card_value(市值, 完整度)，計入當天賣出量
    卡已不在卡冊 ➔ ValueError，整筆不寫入
    回傳 {"total", "money", "cards": [卡 + "value"]}
    """
    now = now or datetime.now(timezone.utc)
    if not instance_ids or len(set(instance_ids)) != len(instance_ids):
        raise ValueError("沒有選擇卡牌或重複選擇")
    day = tw_day(now)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            placeholders = ", ".join("?" for _ in instance_ids)
            async with db.execute(
                f"SELECT * FROM gacha_cards WHERE user_id = ? AND instance_id IN ({placeholders})", (user_id, *instance_ids)
            ) as cursor:
                cards = [dict(r) for r in await cursor.fetchall()]
            if len(cards) != len(instance_ids):
                raise ValueError("部分卡牌已不在你的卡冊中")
            prices = await _prices(db)
            total = 0
            for card in cards:
                card["value"] = card_value(_price_of(prices, card["character_key"], card["rarity"]), card["completeness"])
                total += card["value"]
                await _log_sale(db, card["character_key"], card["rarity"], day)
                await _log_trade(db, "decompose", card["value"], day, now, seller=user_id, card=card)
            await db.execute(f"DELETE FROM gacha_cards WHERE user_id = ? AND instance_id IN ({placeholders})", (user_id, *instance_ids))
            await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (total, user_id))
            async with db.execute("SELECT money FROM users WHERE user_id = ?", (user_id,)) as cursor:
                money = (await cursor.fetchone())["money"]
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"total": total, "money": money, "cards": cards}


# =========================================================
# 🏪 4. 市場 (玩家上架；需要開通交易)
# =========================================================
TRADE_UNLOCK_DAILY = 7          # 累積簽到 7 天才開放市場與轉帳 (分解不用)
MARKET_BUYER_FEE = 0.05         # 買家付 上架價 × 1.05，多的 5% 被系統回收
LISTING_DURATION = timedelta(days=7)


def buyer_total(price: int) -> int:
    return math.ceil(price * (1 + MARKET_BUYER_FEE))


async def _daily_count(db, user_id: int) -> int:
    async with db.execute("SELECT daily_count FROM users WHERE user_id = ?", (user_id,)) as cursor:
        row = await cursor.fetchone()
    return (row["daily_count"] or 0) if row else 0


async def get_trade_status(user_id: int) -> dict:
    """{"daily_count", "unlocked", "need"}"""
    async with connect() as db:
        count = await _daily_count(db, user_id)
    return {"daily_count": count, "unlocked": count >= TRADE_UNLOCK_DAILY, "need": TRADE_UNLOCK_DAILY}


def _listing_card(listing: dict) -> dict:
    return {k: listing[k] for k in ("instance_id", "character_key", "name", "emoji", "rarity", "title", "completeness", "obtained_at")}


async def expire_listings(now: datetime | None = None) -> int:
    """上架超過 7 天 ➔ 下架，卡退回賣家卡冊；回傳下架張數"""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - LISTING_DURATION).isoformat()
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute("SELECT * FROM market_listings WHERE listed_at <= ?", (cutoff,)) as cursor:
                rows = [dict(r) for r in await cursor.fetchall()]
            for listing in rows:
                await _insert_cards(db, listing["seller_id"], [_listing_card(listing)])
                await db.execute("DELETE FROM market_listings WHERE listing_id = ?", (listing["listing_id"],))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return len(rows)


async def list_card(user_id: int, instance_id: str, price: int, now: datetime | None = None) -> dict:
    """上架：卡從卡冊移到市場託管 {"ok", "reason", "listing"}"""
    now = now or datetime.now(timezone.utc)
    if price < 1:
        return {"ok": False, "reason": "bad_price"}
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            if await _daily_count(db, user_id) < TRADE_UNLOCK_DAILY:
                await db.rollback()
                return {"ok": False, "reason": "locked"}
            async with db.execute("SELECT * FROM gacha_cards WHERE user_id = ? AND instance_id = ?", (user_id, instance_id)) as cursor:
                row = await cursor.fetchone()
            if row is None:
                await db.rollback()
                return {"ok": False, "reason": "not_found"}
            card = dict(row)
            await db.execute("DELETE FROM gacha_cards WHERE instance_id = ?", (instance_id,))
            cursor = await db.execute(
                "INSERT INTO market_listings (seller_id, instance_id, character_key, name, emoji, rarity, title, completeness, obtained_at, price, listed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, card["instance_id"], card["character_key"], card["name"], card["emoji"], card["rarity"],
                 card["title"], card["completeness"], card["obtained_at"], price, now.isoformat()),
            )
            listing = {**card, "listing_id": cursor.lastrowid, "seller_id": user_id, "price": price, "listed_at": now.isoformat()}
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "listing": listing}


async def get_listings(character_keys: list[str] | None = None, seller_id: int | None = None) -> list[dict]:
    """上架中的卡 (依價格低到高)；可依角色或賣家篩選"""
    sql, args = "SELECT * FROM market_listings WHERE 1=1", []
    if character_keys is not None:
        if not character_keys:
            return []
        sql += f" AND character_key IN ({', '.join('?' for _ in character_keys)})"
        args += character_keys
    if seller_id is not None:
        sql += " AND seller_id = ?"
        args.append(seller_id)
    sql += " ORDER BY price, listing_id"
    async with connect() as db:
        async with db.execute(sql, args) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def cancel_listing(user_id: int, listing_id: int) -> dict:
    """賣家自己下架：卡退回卡冊"""
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute("SELECT * FROM market_listings WHERE listing_id = ? AND seller_id = ?", (listing_id, user_id)) as cursor:
                row = await cursor.fetchone()
            if row is None:
                await db.rollback()
                return {"ok": False, "reason": "not_found"}
            listing = dict(row)
            await _insert_cards(db, user_id, [_listing_card(listing)])
            await db.execute("DELETE FROM market_listings WHERE listing_id = ?", (listing_id,))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "listing": listing}


async def buy_listing(buyer_id: int, listing_id: int, now: datetime | None = None) -> dict:
    """
    購買 (同一個交易)：買家付 上架價 × 1.05、賣家拿上架價、卡移到買家卡冊、計入當天賣出量
    失敗 reason：locked / not_found (已賣出或下架) / own / expired / not_enough
    """
    now = now or datetime.now(timezone.utc)
    day = tw_day(now)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async def fail(reason, **extra):
                await db.rollback()
                return {"ok": False, "reason": reason, **extra}

            await _ensure_user(db, buyer_id)
            if await _daily_count(db, buyer_id) < TRADE_UNLOCK_DAILY:
                return await fail("locked")
            async with db.execute("SELECT * FROM market_listings WHERE listing_id = ?", (listing_id,)) as cursor:
                row = await cursor.fetchone()
            if row is None:
                return await fail("not_found")
            listing = dict(row)
            if listing["seller_id"] == buyer_id:
                return await fail("own")
            if _dt(listing["listed_at"]) + LISTING_DURATION <= now:
                return await fail("expired")
            total = buyer_total(listing["price"])
            async with db.execute("SELECT money FROM users WHERE user_id = ?", (buyer_id,)) as cursor:
                money = (await cursor.fetchone())["money"]
            if money < total:
                return await fail("not_enough", money=money, total=total)

            await db.execute("UPDATE users SET money = money - ? WHERE user_id = ?", (total, buyer_id))
            await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (listing["price"], listing["seller_id"]))
            card = _listing_card(listing)
            await _insert_cards(db, buyer_id, [card])
            await db.execute("DELETE FROM market_listings WHERE listing_id = ?", (listing_id,))
            await _log_sale(db, card["character_key"], card["rarity"], day)
            await _log_trade(db, "market", listing["price"], day, now, seller=listing["seller_id"], buyer=buyer_id,
                             card=card, fee=total - listing["price"])
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "listing": listing, "total": total, "money": money - total}


# =========================================================
# 💸 5. 轉帳 (需要開通交易)
# =========================================================
TRANSFER_FEE = 0.05                 # 手續費 5%，從轉帳金額裡扣 (轉 1000 ➔ 對方收到 950)
TRANSFER_DAILY_LIMIT = 500_000      # 每人每天 (台灣時間) 最多轉出 500K


def transfer_fee(amount: int) -> int:
    return math.ceil(amount * TRANSFER_FEE)


async def get_transfer_today(user_id: int, now: datetime | None = None) -> int:
    async with connect() as db:
        return await _sent_today(db, user_id, tw_day(now))


async def _sent_today(db, user_id: int, day: str) -> int:
    async with db.execute(
        "SELECT COALESCE(SUM(price), 0) AS s FROM market_trades WHERE kind = 'transfer' AND seller_id = ? AND day = ?",
        (user_id, day),
    ) as cursor:
        return (await cursor.fetchone())["s"]


async def transfer_money(sender_id: int, receiver_id: int, amount: int, now: datetime | None = None) -> dict:
    """
    轉帳 (同一個交易)：sender −amount、receiver +(amount − 手續費)
    失敗 reason：self / bad_amount / locked / target_locked / not_enough / limit
    """
    now = now or datetime.now(timezone.utc)
    day = tw_day(now)
    if sender_id == receiver_id:
        return {"ok": False, "reason": "self"}
    if amount < 1:
        return {"ok": False, "reason": "bad_amount"}
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async def fail(reason, **extra):
                await db.rollback()
                return {"ok": False, "reason": reason, **extra}

            await _ensure_user(db, sender_id)
            if await _daily_count(db, sender_id) < TRADE_UNLOCK_DAILY:
                return await fail("locked")
            if await _daily_count(db, receiver_id) < TRADE_UNLOCK_DAILY:
                return await fail("target_locked")
            sent = await _sent_today(db, sender_id, day)
            if sent + amount > TRANSFER_DAILY_LIMIT:
                return await fail("limit", sent=sent, left=TRANSFER_DAILY_LIMIT - sent)
            async with db.execute("SELECT money FROM users WHERE user_id = ?", (sender_id,)) as cursor:
                money = (await cursor.fetchone())["money"]
            if money < amount:
                return await fail("not_enough", money=money)
            fee = transfer_fee(amount)
            await db.execute("UPDATE users SET money = money - ? WHERE user_id = ?", (amount, sender_id))
            await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (amount - fee, receiver_id))
            await _log_trade(db, "transfer", amount, day, now, seller=sender_id, buyer=receiver_id, fee=fee)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "fee": fee, "received": amount - fee, "money": money - amount,
            "sent_today": sent + amount, "left_today": TRANSFER_DAILY_LIMIT - sent - amount}

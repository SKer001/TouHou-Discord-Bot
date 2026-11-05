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

from Database.User_DB_Manager import connect, _ensure_user, _insert_cards, tw_day

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
YOUKAI_REWARD = 1000                   # 打退一隻的賽錢；打退後留下晦氣 ➔ 清潔度掉一階

GUEST_EVERY_HOURS = 2                  # 每 2 小時判定一次參拜客
GUEST_MAX = 5
GUEST_SPAWN = [0.90, 0.80, 0.70, 0.60, 0.50]    # 目前 0 位時 90%、1 位時 80%…
MOOD_STEP = 10                         # 心情 10% 一個區間
MOOD_INTERVAL = timedelta(hours=4)     # 每 4 小時掉一個區間，掉到 0 就離開
SERVING_REWARD = 1000                  # 每「份」餐點：1000 × 心情² (不保底)
GUEST_KINDS = ["河童", "鴉天狗", "白狼天狗", "狐妖", "化貓", "唐傘妖怪", "付喪神", "夜雀", "妖精", "小鬼"]

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
    """招待報酬：每份 1000 × 心情²"""
    return int(SERVING_REWARD * (mood / 100) ** 2 * portions)


def advance_shrine(state: dict, now: datetime, rng=random) -> dict:
    """
    純計算：把神社從 updated_at 推進到 now (不寫資料庫)
    - 賽錢箱依當下效率連續累積 (效率在整點事件、變髒的時間點改變)
    - 每個整點 (以建立時間為準)：妖怪依目前數量機率生成；每 2 小時：參拜客依目前人數機率來訪
    - 參拜客心情掉到 0 就離開
    """
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
                st["guests"].append({"kind": rng.choice(GUEST_KINDS), "arrived_at": t.isoformat()})

    st["guests"] = [g for g in st["guests"] if guest_mood(g, now) > 0]
    st["updated_at"] = now.isoformat()
    return st


def shrine_summary(state: dict, now: datetime) -> dict:
    """畫面要顯示的資料 (已結算後的 state)"""
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
        guests.append({
            "kind": g["kind"], "mood": mood, "arrived_at": arrived,
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
    神社共用交易：讀取 (沒有就建立) ➔ 結算到現在 ➔ action(state, db) 修改 ➔ 寫回
    回傳 {"summary": shrine_summary, **action 的回傳}
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
            state = advance_shrine(state, now, rng)
            extra = (await action(state, db)) if action else {}
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
    return {"summary": shrine_summary(state, now), **extra}


async def get_shrine(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """查看神社 (會結算並存檔)"""
    return await _shrine_tx(user_id, now=now, rng=rng)


async def shrine_collect(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """回收賽錢箱：整數部分轉進賽錢，零頭留在箱子裡"""
    async def action(state, db):
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

    async def action(state, db):
        before = shrine_dirt(state, now)
        state["clean_at"] = now.isoformat()
        state["dirt_extra"] = 0
        return {"before": before}
    return await _shrine_tx(user_id, action, now, rng)


async def shrine_defeat(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """治退一隻妖怪：+1000 賽錢，留下晦氣 (清潔度 +1 階，不會超過最髒)"""
    now = now or datetime.now(timezone.utc)

    async def action(state, db):
        if state["youkai"] <= 0:
            return {"ok": False}
        state["youkai"] -= 1
        if shrine_dirt(state, now) < DIRT_MAX:
            state["dirt_extra"] += 1
        await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (YOUKAI_REWARD, user_id))
        return {"ok": True, "reward": YOUKAI_REWARD}
    return await _shrine_tx(user_id, action, now, rng)


async def admin_set_shrine(user_id: int, box: int | None = None, dirt: int | None = None, youkai: int | None = None,
                           guests: int | None = None, guest_mood: int = 100, now: datetime | None = None, rng=random) -> dict:
    """
    【管理員】調整神社 (先結算到現在再改)：
    box 賽錢箱、dirt 清潔度階段 (從現在開始重新計時)、youkai 妖怪數、guests 參拜客數 (心情都設成 guest_mood)
    """
    now = now or datetime.now(timezone.utc)

    async def action(state, db):
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
            state["guests"] = [{"kind": GUEST_KINDS[i % len(GUEST_KINDS)], "arrived_at": arrived.isoformat()}
                               for i in range(max(0, min(GUEST_MAX, guests)))]
        return {}
    return await _shrine_tx(user_id, action, now, rng)


async def admin_reset_shrine(user_id: int) -> bool:
    """【管理員】刪除神社資料 (下次打開時重新建立，賽錢箱歸零)"""
    async with connect() as db:
        cursor = await db.execute("DELETE FROM shrines WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0


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

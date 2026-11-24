"""
💹 浮動市值：每日結算、查價、交易紀錄

從 Database/Economy_DB_Manager.py 拆出來的；外面一律照舊從 Database.Economy_DB_Manager 匯入 (入口)，不要直接匯入這裡。
"""
from datetime import date, datetime, timedelta, timezone

from Database.User_DB_Manager import connect, tw_day
from Database.economy.common import _get_meta, _set_meta

# =========================================================
# 💹 2. 浮動市值 (每天台灣時間 00:00 結算)
# =========================================================
OFFICIAL_PRICES = {"N": 50, "R": 100, "SR": 500, "SSR": 1000, "UR": 10000, "LR": 50000}   # 官方回收價 = 市值的保底
PRICE_DAILY_LIMIT = 0.10       # 每天最多跌 10% (漲最多是 PRICE_IDLE_RISE)
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


def card_value(price: float, completeness: float, mult: float = 1.0) -> int:
    """單張卡的價值 = 市值 × 完整度倍率 (分解拿到的錢)；mult = 活動的分解倍率 (modifiers.decompose)"""
    return max(1, int(round(price * completeness_multiplier(completeness) * mult)))


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
                    expected = draws.get(pool, 0) * p + draws.get(f"card:{key[0]}:{key[1]}", 0)   # 一般卡池 + 活動卡池
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

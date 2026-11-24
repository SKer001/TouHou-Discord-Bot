"""
♻️ 分解卡牌、🏪 市場、💸 轉帳

從 Database/Economy_DB_Manager.py 拆出來的；外面一律照舊從 Database.Economy_DB_Manager 匯入 (入口)，不要直接匯入這裡。
"""
import math
from datetime import datetime, timedelta, timezone

from Database.User_DB_Manager import connect, _ensure_user, _insert_cards, tw_day
from Utils import card_cache   # 卡冊有變動時讓 autocomplete 的快取失效
from Utils.character_data import apply_current_names   # 卡名 / 稱號一律用目前的角色檔
from Database.events import game_rules
from Database.economy.common import _dt, modifier
from Database.economy.event_state import _FEE_MODS, _active_events, _remember_fee_mods
from Database.economy.market_value import _log_sale, _log_trade, _price_of, _prices, card_value

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
                f"SELECT * FROM gacha_cards WHERE user_id = ? AND locked = 0 AND expedition = 0 AND instance_id IN ({placeholders})", (user_id, *instance_ids)
            ) as cursor:
                cards = [dict(r) for r in await cursor.fetchall()]   # 收藏冊裡的卡不能分解
            if len(cards) != len(instance_ids):
                raise ValueError("部分卡牌已不在你的卡冊中")
            prices = await _prices(db)
            mult = modifier(game_rules(await _active_events(db, now)), "decompose")
            total = 0
            for card in cards:
                card["value"] = card_value(_price_of(prices, card["character_key"], card["rarity"]), card["completeness"], mult)
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
    card_cache.invalidate(user_id)
    return {"total": total, "money": money, "cards": cards}


# =========================================================
# 🏪 4. 市場 (玩家上架；需要開通交易)
# =========================================================
TRADE_UNLOCK_DAILY = 7          # 累積簽到 7 天才開放市場與轉帳 (分解不用)
MARKET_BUYER_FEE = 0.05         # 買家付 上架價 × 1.05，多的 5% 被系統回收
LISTING_DURATION = timedelta(days=7)


def market_fee_rate(mult: float | None = None) -> float:
    """買家手續費率 (活動可以用 modifiers.market_fee 調整)"""
    return MARKET_BUYER_FEE * (_FEE_MODS["market_fee"] if mult is None else mult)


def buyer_total(price: int, mult: float | None = None) -> int:
    return math.ceil(price * (1 + market_fee_rate(mult)))


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
    card_cache.invalidate(*{listing["seller_id"] for listing in rows})   # 退回的賣家
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
            async with db.execute("SELECT * FROM gacha_cards WHERE user_id = ? AND instance_id = ? AND locked = 0 AND expedition = 0",
                                  (user_id, instance_id)) as cursor:
                row = await cursor.fetchone()
            if row is None:   # 收藏冊裡的卡不能上架
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
    card_cache.invalidate(user_id)
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
            return apply_current_names([dict(r) for r in await cursor.fetchall()])


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
    card_cache.invalidate(user_id)
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
            rules = game_rules(await _active_events(db, now))
            _remember_fee_mods(rules)
            total = buyer_total(listing["price"], rules["modifiers"]["market_fee"])
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
    card_cache.invalidate(buyer_id, listing["seller_id"])   # 買家多一張；賣家一併失效
    return {"ok": True, "listing": listing, "total": total, "money": money - total}


# =========================================================
# 💸 5. 轉帳 (需要開通交易)
# =========================================================
TRANSFER_FEE = 0.05                 # 手續費 5%，從轉帳金額裡扣 (轉 1000 ➔ 對方收到 950)
TRANSFER_DAILY_LIMIT = 500_000      # 每人每天 (台灣時間) 最多轉出 500K


def transfer_fee_rate(mult: float | None = None) -> float:
    """轉帳手續費率 (活動可以用 modifiers.transfer_fee 調整)"""
    return TRANSFER_FEE * (_FEE_MODS["transfer_fee"] if mult is None else mult)


def transfer_fee(amount: int, mult: float | None = None) -> int:
    return math.ceil(amount * transfer_fee_rate(mult))


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
            rules = game_rules(await _active_events(db, now))
            _remember_fee_mods(rules)
            fee = transfer_fee(amount, rules["modifiers"]["transfer_fee"])
            await db.execute("UPDATE users SET money = money - ? WHERE user_id = ?", (amount, sender_id))
            await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (amount - fee, receiver_id))
            await _log_trade(db, "transfer", amount, day, now, seller=sender_id, buyer=receiver_id, fee=fee)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "fee": fee, "received": amount - fee, "money": money - amount,
            "sent_today": sent + amount, "left_today": TRANSFER_DAILY_LIMIT - sent - amount}

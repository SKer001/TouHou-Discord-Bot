"""
🏷️ 稱號、🖼️ 角色名片

從 Database/User_DB_Manager.py 拆出來的；外面一律照舊從 Database.User_DB_Manager 匯入 (入口)，不要直接匯入這裡。
"""
from datetime import datetime, timezone

from Utils.gacha_pools import collection_stats, oshi_stats   # 稱號：卡池收集、推角
from Database.users.schema import connect, _ensure_user
from Database.users.core import get_or_create_user, get_player_stats

# ---------------------------------------------------------
# 🏷️ 稱號 (清單與條件在 Database/title_data.py)
# ---------------------------------------------------------
# 卡冊裡「現在」有幾種角色的 UR / LR (稱號用；上架中的卡不在 gacha_cards，不算)
TITLE_CARD_KINDS_SQL = (
    "SELECT COUNT(DISTINCT CASE WHEN rarity = 'UR' THEN character_key END) AS ur_kinds, "
    "COUNT(DISTINCT CASE WHEN rarity = 'LR' THEN character_key END) AS lr_kinds, "
    # 完美卡：完整度四捨五入到 4 位 = 1.0000 (跟 gacha.is_perfect 一樣)，角色 + 階級一樣只算一種
    "COUNT(DISTINCT CASE WHEN completeness >= 0.99995 THEN character_key || ':' || rarity END) AS perfect_kinds FROM gacha_cards"
)
# 每種卡 (角色 × 階級) 的持有狀況：卡池收集看有沒有 (卡冊 + 收藏冊都算)；
# 推角看 album_best = 收藏冊 (locked = 1) 裡最完整的那張 (2026-11-14 使用者：推角只算收藏冊)；Notify_DB_Manager 也用這段，兩邊一致
TITLE_OWNED_CARDS_SQL = (
    "SELECT user_id, character_key, rarity, MAX(CASE WHEN locked = 1 THEN completeness END) AS album_best FROM gacha_cards"
)


async def save_earned_titles(pairs: list[tuple[int, str]]):
    """[(user_id, 稱號 id), ...] 寫進 earned_titles (已經有的不動)；踏破這類 keep 稱號第一次達成時用"""
    if not pairs:
        return
    now = datetime.now(timezone.utc).isoformat()
    async with connect() as db:
        await db.executemany("INSERT OR IGNORE INTO earned_titles (user_id, title_id, earned_at) VALUES (?, ?, ?)",
                             [(u, t, now) for u, t in pairs])
        await db.commit()


async def get_earned_titles(user_id: int) -> list[str]:
    """永久獲得的稱號 id (earned_titles 表；活動任務稱號)"""
    async with connect() as db:
        async with db.execute("SELECT title_id FROM earned_titles WHERE user_id = ? ORDER BY earned_at, rowid",
                              (user_id,)) as cursor:
            return [r["title_id"] for r in await cursor.fetchall()]


async def get_title_stats(user_id: int) -> dict:
    """解鎖稱號用的玩家統計 (title_data 的 stat 鍵)"""
    async with connect() as db:
        async with db.execute("SELECT total_draws, total_fusions, total_synths FROM gacha_stats WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        async with db.execute("SELECT daily_count, best_streak, best_money, level FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        async with db.execute(TITLE_CARD_KINDS_SQL + " WHERE user_id = ?", (user_id,)) as cursor:
            kinds = await cursor.fetchone()
        async with db.execute("SELECT COUNT(*) AS n FROM market_trades WHERE kind = 'market' AND seller_id = ?", (user_id,)) as cursor:
            sold = (await cursor.fetchone())["n"]   # 💹 市場賣出 (被別人買走的張數)
        async with db.execute("SELECT COALESCE(SUM(price), 0) AS s FROM market_trades WHERE kind = 'transfer' AND seller_id = ?",
                              (user_id,)) as cursor:
            sent = (await cursor.fetchone())["s"]   # 💸 累計轉出金額
        async with db.execute(TITLE_OWNED_CARDS_SQL + " WHERE user_id = ? GROUP BY character_key, rarity", (user_id,)) as cursor:
            rows = await cursor.fetchall()
    owned = {(r["character_key"], r["rarity"]) for r in rows}
    counts = {}   # 推角：每位角色在「收藏冊」裡有幾個階級有完美卡 (完整度 1.0000，同 TITLE_CARD_KINDS_SQL)
    for r in rows:
        if (r["album_best"] or 0) >= 0.99995:
            counts[r["character_key"]] = counts.get(r["character_key"], 0) + 1
    keys = ("total_draws", "total_fusions", "total_synths")
    stats = {k: (row[k] if row else 0) for k in keys}
    stats["daily_count"] = (user["daily_count"] or 0) if user else 0
    stats["best_streak"] = (user["best_streak"] or 0) if user else 0
    stats["best_money"] = (user["best_money"] or 0) if user else 0
    stats["power_level"] = (user["level"] or 0) if user else 0   # 火力：level 0～1000 = 0.0～100.0 P
    stats["market_sold"] = sold
    stats["transfer_sent"] = sent
    stats.update({f"ps:{k}": v for k, v in (await get_player_stats(user_id)).items()})   # 📊 神社動作計數
    from Database import title_data
    stats.update(title_data.derived_stats(stats))   # 🗺️ 踏破、🍳 美食家 (從 player_stats 算)
    stats["ur_kinds"] = kinds["ur_kinds"] or 0
    stats["lr_kinds"] = kinds["lr_kinds"] or 0
    stats["perfect_kinds"] = kinds["perfect_kinds"] or 0
    stats.update(collection_stats(owned))
    stats.update(oshi_stats(counts))
    return stats


async def get_title_state(user_id: int) -> dict:
    """{"equipped": 戴著的稱號 id (已不符條件或不存在 ➔ None), "unlocked": [已解鎖 id, ...], "stats": 玩家統計}"""
    from Database import title_data
    user = await get_or_create_user(user_id)
    stats = await get_title_stats(user_id)
    unlocked = title_data.unlocked_titles(stats)
    earned = await get_earned_titles(user_id)
    keep = [t for t in title_data.keep_titles(unlocked) if t not in earned]
    if keep:   # 🗺️ 踏破這類「第一次達成就永久保留」的稱號 ➔ 寫進 earned_titles
        await save_earned_titles([(user_id, t) for t in keep])
    # 已解鎖 = 條件達成 ∪ 管理員給的 ∪ 永久獲得的 (活動任務稱號、踏破，earned_titles)
    extra = []
    for t in _split_titles(user.get("granted_titles")) + earned:
        if t in title_data.TITLES and t not in unlocked and t not in extra:
            extra.append(t)
    if extra:   # 一起列 (照等級重新排)
        unlocked = sorted(unlocked + extra, key=lambda t: -title_data.RARITY_ORDER[title_data.TITLES[t]["rarity"]])
    await sync_oshi_namecards(user_id, unlocked)   # 🖼️ 第一次有推角稱號 ➔ 永久拿到那位角色的名片
    equipped = user.get("equipped_title")
    return {"equipped": equipped if equipped in unlocked else None, "unlocked": unlocked,
            "stats": stats}   # stats：說明裡有 {n} 的稱號要用 (title_data.title_desc)


def _split_titles(value: str | None) -> list[str]:
    return [t for t in (value or "").split(",") if t]


async def get_granted_titles(user_id: int) -> list[str]:
    """管理員給的稱號 id (不管條件)"""
    return _split_titles((await get_or_create_user(user_id)).get("granted_titles"))


async def set_granted_title(user_id: int, title_id: str, granted: bool) -> list[str]:
    """管理員給 (granted=True) / 收回稱號，回傳之後的清單 (收回的話自己達成條件的還是會有)"""
    titles = await get_granted_titles(user_id)
    if granted and title_id not in titles:
        titles.append(title_id)
    elif not granted:
        titles = [t for t in titles if t != title_id]
    async with connect() as db:
        await db.execute("UPDATE users SET granted_titles = ? WHERE user_id = ?", (",".join(titles) or None, user_id))
        await db.commit()
    return titles


async def set_equipped_title(user_id: int, title_id: str | None) -> bool:
    """戴上稱號 (None = 卸下)；沒解鎖或不存在回傳 False (使用者可能繞過選單，這裡再驗一次)"""
    if title_id is not None and title_id not in (await get_title_state(user_id))["unlocked"]:
        return False
    async with connect() as db:
        await _ensure_user(db, user_id)
        await db.execute("UPDATE users SET equipped_title = ? WHERE user_id = ?", (title_id, user_id))
        await db.commit()
    return True


# ---------------------------------------------------------
# 🖼️ 角色名片 (2026-11-14 使用者)：第一次獲得某位角色的推角稱號 (oshi_<角色id>) 時永久拿到；
#    之後稱號失去 (卡拿出收藏冊、賣掉) 名片還是留著。戴一張顯示在 /profile 今日運勢下面 (0.35.038 起)，圖片網址在 images/Namecards.json
# ---------------------------------------------------------
OSHI_PREFIX = "oshi_"


def _oshi_characters(title_ids) -> list[str]:
    """已解鎖稱號裡的推角稱號 ➔ 角色 id"""
    return [t[len(OSHI_PREFIX):] for t in title_ids if t.startswith(OSHI_PREFIX) and len(t) > len(OSHI_PREFIX)]


async def _sync_oshi_namecards(db, user_id: int, title_ids, now: str) -> list[str]:
    """(在呼叫端的連線裡) 補上推角稱號對應的名片，回傳這次新拿到的角色 id"""
    added = []
    for cid in _oshi_characters(title_ids):
        cursor = await db.execute(
            "INSERT OR IGNORE INTO namecards (user_id, character_key, obtained_at, source) VALUES (?, ?, ?, 'oshi')",
            (user_id, cid, now),
        )
        if cursor.rowcount == 1:
            added.append(cid)
    return added


async def sync_oshi_namecards(user_id: int, unlocked_title_ids) -> list[str]:
    """有推角稱號就給那位角色的名片 (已經有的不動)；回傳新拿到的角色 id"""
    if not _oshi_characters(unlocked_title_ids):
        return []
    async with connect() as db:
        await _ensure_user(db, user_id)
        added = await _sync_oshi_namecards(db, user_id, unlocked_title_ids, datetime.now(timezone.utc).isoformat())
        await db.commit()
    return added


async def get_namecards(user_id: int) -> list[str]:
    """擁有的名片 (角色 id，依取得時間)"""
    async with connect() as db:
        async with db.execute("SELECT character_key FROM namecards WHERE user_id = ? ORDER BY obtained_at, rowid",
                              (user_id,)) as cursor:
            return [r["character_key"] for r in await cursor.fetchall()]


async def grant_namecard(user_id: int, character_key: str, source: str = "admin") -> bool:
    """給名片 (source = 'oshi' / 'admin')；已經有了回傳 False"""
    async with connect() as db:
        await _ensure_user(db, user_id)
        cursor = await db.execute(
            "INSERT OR IGNORE INTO namecards (user_id, character_key, obtained_at, source) VALUES (?, ?, ?, ?)",
            (user_id, character_key, datetime.now(timezone.utc).isoformat(), source),
        )
        await db.commit()
    return cursor.rowcount == 1


async def revoke_namecard(user_id: int, character_key: str) -> bool:
    """收回名片 (正戴著就一起卸下)；本來就沒有回傳 False
    注意：還有那位角色的推角稱號的話，下次看資料卡又會自動補回來"""
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("DELETE FROM namecards WHERE user_id = ? AND character_key = ?", (user_id, character_key))
        await db.execute("UPDATE users SET equipped_namecard = NULL WHERE user_id = ? AND equipped_namecard = ?",
                         (user_id, character_key))
        await db.commit()
    return cursor.rowcount == 1


async def set_equipped_namecard(user_id: int, character_key: str | None) -> bool:
    """戴上名片 (None = 不放名片)；沒擁有回傳 False (使用者可能繞過選單，這裡再驗一次)"""
    async with connect() as db:
        await _ensure_user(db, user_id)
        if character_key is None:
            await db.execute("UPDATE users SET equipped_namecard = NULL WHERE user_id = ?", (user_id,))
        else:   # 一句 UPDATE 同時檢查有沒有擁有 (原子，不會跟收回名片撞在一起)
            cursor = await db.execute(
                "UPDATE users SET equipped_namecard = ? WHERE user_id = ? AND EXISTS "
                "(SELECT 1 FROM namecards WHERE user_id = ? AND character_key = ?)",
                (character_key, user_id, user_id, character_key),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                return False
        await db.commit()
    return True


async def get_namecard_state(user_id: int) -> dict:
    """{"equipped": 戴著的名片角色 id (沒擁有 ➔ None), "owned": [角色 id, ...] (依取得時間)}"""
    owned = await get_namecards(user_id)
    equipped = (await get_or_create_user(user_id)).get("equipped_namecard")
    return {"equipped": equipped if equipped in owned else None, "owned": owned}

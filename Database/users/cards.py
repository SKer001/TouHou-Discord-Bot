"""
🎴 抽卡：卡牌與統計、🛠️ 管理員卡冊操作

從 Database/User_DB_Manager.py 拆出來的；外面一律照舊從 Database.User_DB_Manager 匯入 (入口)，不要直接匯入這裡。
"""
from datetime import datetime

from Utils import card_cache   # 卡冊有變動時讓 autocomplete 的快取失效
from Utils.character_data import apply_current_names   # 卡名 / 稱號一律用目前的角色檔 (資料庫存的是副本)
from Database.users.schema import connect, _ensure_user
from Database.users.core import add_quest_stats, add_player_stat, EVENT_POOL_PREFIX, tw_day
from Database.users.titles import get_title_state

# ---------------------------------------------------------
# 🎴 7. 抽卡 (Gacha)：卡牌與統計
# ---------------------------------------------------------
async def get_user_cards(user_id: int, include_locked: bool = False) -> list[dict]:
    """
    取得玩家持有的卡牌 (依取得順序)
    - 預設不含收藏冊裡的卡 (locked = 1)：卡冊、合成、融合、分解、上架、autocomplete 都用這個，看不到也選不到
    - include_locked=True：全部 (管理員畫面、圖鑑的「已擁有」)；每張卡多一個 "locked"、"expedition"
    - 🌀 裏世界出征中的卡 (expedition = 1) 預設也不列 (不能合成、融合、分解、上架)
    """
    where = "" if include_locked else " AND locked = 0 AND expedition = 0"
    async with connect() as db:
        async with db.execute(
            f"""
            SELECT instance_id, character_key, name, emoji, rarity, title, completeness, obtained_at, locked, expedition
            FROM gacha_cards WHERE user_id = ?{where} ORDER BY rowid
            """,
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return apply_current_names([dict(row) for row in rows])


async def get_album_cards(user_id: int) -> list[dict]:
    """收藏冊裡的卡 (locked = 1，依取得順序)"""
    async with connect() as db:
        async with db.execute(
            """
            SELECT instance_id, character_key, name, emoji, rarity, title, completeness, obtained_at, locked
            FROM gacha_cards WHERE user_id = ? AND locked = 1 ORDER BY rowid
            """,
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return apply_current_names([dict(row) for row in rows])


async def set_cards_locked(user_id: int, instance_ids: list[str], locked: bool) -> int:
    """放進 (locked=True) / 取出收藏冊，回傳實際改動的張數 (不屬於玩家或已經是那個狀態的不算)"""
    if not instance_ids:
        return 0
    placeholders = ", ".join("?" for _ in instance_ids)
    async with connect() as db:
        cursor = await db.execute(
            f"UPDATE gacha_cards SET locked = ? WHERE user_id = ? AND locked = ? AND expedition = 0 AND instance_id IN ({placeholders})",
            (int(locked), user_id, int(not locked), *instance_ids),
        )
        await db.commit()
    card_cache.invalidate(user_id)
    changed = cursor.rowcount
    if locked and changed:
        # 🖼️ 放進收藏冊可能剛好湊齊推角稱號 ➔ 馬上補發名片 (get_title_state 會 sync_oshi_namecards)；
        # 不然要等下次算稱號 / 通知 loop，中間把卡拿出來就拿不到 (2026-11-23)
        await get_title_state(user_id)
    return changed


async def get_gacha_stats(user_id: int) -> dict:
    """取得玩家抽卡統計 {"total_draws": int, "total_fusions": int}"""
    async with connect() as db:
        async with db.execute(
            "SELECT total_draws, total_fusions FROM gacha_stats WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return {"total_draws": 0, "total_fusions": 0}
    return {"total_draws": row["total_draws"], "total_fusions": row["total_fusions"]}


async def _insert_cards(db, user_id: int, cards: list[dict]):
    """在既有連線 (交易) 中寫入卡牌"""
    await db.executemany(
        """
        INSERT INTO gacha_cards
            (instance_id, user_id, character_key, name, emoji, rarity, title, completeness, obtained_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                c["instance_id"], user_id, c["character_key"], c["name"], c.get("emoji"),
                c["rarity"], c.get("title"), c["completeness"], c.get("obtained_at"),
            )
            for c in cards
        ],
    )


async def _add_draws(db, user_id: int, draw_count: int):
    """在既有連線 (交易) 中累加總抽卡次數"""
    await db.execute(
        """
        INSERT INTO gacha_stats (user_id, total_draws) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET total_draws = total_draws + excluded.total_draws
        """,
        (user_id, draw_count),
    )


async def add_gacha_cards(user_id: int, cards: list[dict], draw_count: int | None = None):
    """
    直接寫入卡牌並累加抽卡次數 (同一個交易)；管理員發放用 draw_count=0。
    一般祈願請用 draw_gacha (扣款、卡牌、統計、保底全部同一個交易)。
    draw_count 預設等於卡牌張數。
    """
    draw_count = len(cards) if draw_count is None else draw_count
    async with connect() as db:
        await _ensure_user(db, user_id)
        await _insert_cards(db, user_id, cards)
        await _add_draws(db, user_id, draw_count)
        await db.commit()
    card_cache.invalidate(user_id)


class InsufficientFunds(Exception):
    """賽錢不足；money 為玩家目前的賽錢"""
    def __init__(self, money: int):
        super().__init__(money)
        self.money = money


async def draw_gacha(user_id: int, pool: str, draw_count: int, cost: int, roll_cards, expected: dict | None = None,
                     now: datetime | None = None, quest_events: list[str] | None = None) -> dict:
    """
    祈願：扣款 ➔ 依保底計數擲卡 ➔ 寫入卡牌 ➔ 累加統計與該卡池的保底，全部同一個交易
    - roll_cards(since_ur) 回傳 (cards, new_since_ur, got_ur)；since_ur = 該卡池距離上次 UR 的抽數
    - expected {(角色, 階級): 預期張數}：活動卡池用，記進 daily_draws 的 `card:<角色>:<階級>` (浮動市值的預期抽到量)
    - 賽錢不足丟出 InsufficientFunds (什麼都不會寫入)
    - 🎪 活動卡池的抽數記進「開這個卡池的活動」這一輪的任務計數 gacha_event_pool (別的活動不算)：
      quest_events = 那些活動 id (rules["gacha_event_pools"][卡池]["events"])；沒給 ➔ event_<活動 id> 就是那個活動
    - 一般卡池 (含活動開放的 th06) 另外記 gacha_pool:<卡池> 給所有進行中的活動 (任務 type gacha_pool)
    回傳 {"cards", "money", "pool_draws", "since_ur"}
    """
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_user(db, user_id)
            async with db.execute("SELECT money FROM users WHERE user_id = ?", (user_id,)) as cursor:
                money = (await cursor.fetchone())["money"]
            if money < cost:
                raise InsufficientFunds(money)

            async with db.execute(
                "SELECT total_draws, since_ur FROM gacha_pity WHERE user_id = ? AND pool = ?", (user_id, pool)
            ) as cursor:
                row = await cursor.fetchone()
            pool_draws, since_ur = (row["total_draws"], row["since_ur"]) if row else (0, 0)

            cards, since_ur, got_ur = roll_cards(since_ur)
            pool_draws += draw_count

            await db.execute("UPDATE users SET money = money - ? WHERE user_id = ?", (cost, user_id))
            await _insert_cards(db, user_id, cards)
            await _add_draws(db, user_id, draw_count)
            await db.execute(   # 全服每日抽卡數 (浮動市值的基準)
                """
                INSERT INTO daily_draws (day, pool, draws) VALUES (?, ?, ?)
                ON CONFLICT(day, pool) DO UPDATE SET draws = draws + excluded.draws
                """,
                (tw_day(), pool, draw_count),
            )
            if expected:   # 小數也照存 (SQLite 存不成整數時會存成實數)
                await db.executemany(
                    """
                    INSERT INTO daily_draws (day, pool, draws) VALUES (?, ?, ?)
                    ON CONFLICT(day, pool) DO UPDATE SET draws = draws + excluded.draws
                    """,
                    [(tw_day(), f"card:{k}:{r}", n) for (k, r), n in expected.items() if n > 0],
                )
            last_ur_at = max(c["obtained_at"] for c in cards) if got_ur else None
            await db.execute(
                """
                INSERT INTO gacha_pity (user_id, pool, total_draws, since_ur, last_ur_at) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, pool) DO UPDATE SET
                    total_draws = excluded.total_draws,
                    since_ur    = excluded.since_ur,
                    last_ur_at  = COALESCE(excluded.last_ur_at, last_ur_at)
                """,
                (user_id, pool, pool_draws, since_ur, last_ur_at),
            )
            # 🍀 運氣稱號 (0.35.005 起)：觸發保底的張數 (所有卡池合計)、90 抽內就出 UR 的次數 (每個卡池分開；
            #    roll_cards 在那張卡標 "lucky"。2026-11-22 前是「一次十連出 2 張以上 UR」，統計名稱沿用 tenpull_2ur)
            await add_player_stat(db, user_id, "gacha_pity", sum(1 for c in cards if c.get("pity")))
            lucky = sum(1 for c in cards if c.get("lucky"))
            if lucky:
                await add_player_stat(db, user_id, f"tenpull_2ur:{pool}", lucky)
            if quest_events is None:
                quest_events = [pool[len(EVENT_POOL_PREFIX):]] if pool.startswith(EVENT_POOL_PREFIX) else []
            per_event = {eid: {"gacha_event_pool": draw_count} for eid in quest_events}   # 🎪 開這個卡池的活動
            if pool.startswith(EVENT_POOL_PREFIX):
                await add_quest_stats(db, user_id, now, per_event=per_event)
            else:   # 一般卡池 ➔ 進行中的活動都記 gacha_pool:<卡池> (任務 type gacha_pool)
                await add_quest_stats(db, user_id, now, stats={f"gacha_pool:{pool}": draw_count}, per_event=per_event)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    card_cache.invalidate(user_id)
    return {"cards": cards, "money": money - cost, "pool_draws": pool_draws, "since_ur": since_ur}


async def get_gacha_pity(user_id: int) -> dict:
    """{"卡池": {"total_draws", "since_ur", "last_ur_at"}, ...}；沒抽過的卡池不會出現"""
    async with connect() as db:
        async with db.execute(
            "SELECT pool, total_draws, since_ur, last_ur_at FROM gacha_pity WHERE user_id = ?", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    return {r["pool"]: {"total_draws": r["total_draws"], "since_ur": r["since_ur"], "last_ur_at": r["last_ur_at"]} for r in rows}


async def transform_cards(user_id: int, instance_ids: list[str], build_new_card, count_fusion: bool = False,
                          count_synthesis: bool = False) -> tuple[list[dict], dict]:
    """
    合成 / 融合共用：消耗指定卡牌並產生一張新卡 (同一個交易)。
    - 以 BEGIN IMMEDIATE 鎖定資料庫，讀取 → 驗證 → 刪除 → 寫入之間不會被其他操作插隊
    - build_new_card(consumed_cards) 負責驗證並回傳新卡；條件不符時丟出 ValueError
    - 任何一張卡已不屬於玩家 (被用掉 / 不存在) 也會丟出 ValueError，整筆不寫入
    - count_fusion=True 時累加 gacha_stats.total_fusions；count_synthesis=True 時累加 total_synths (合成)
    回傳 (被消耗的卡牌, 新卡)
    """
    if len(set(instance_ids)) != len(instance_ids):
        raise ValueError("不能選擇同一張卡牌兩次")

    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            placeholders = ", ".join("?" for _ in instance_ids)
            async with db.execute(
                f"""
                SELECT instance_id, character_key, name, emoji, rarity, title, completeness, obtained_at
                FROM gacha_cards WHERE user_id = ? AND locked = 0 AND expedition = 0 AND instance_id IN ({placeholders})
                """,
                (user_id, *instance_ids),
            ) as cursor:
                rows = {row["instance_id"]: apply_current_names(dict(row)) for row in await cursor.fetchall()}
            if len(rows) != len(instance_ids):   # 收藏冊裡的卡也算不在 (不能拿去合成 / 融合)
                raise ValueError("部分卡牌已不在你的卡冊中")
            consumed = [rows[i] for i in instance_ids]   # 保持呼叫端給的順序

            new_card = build_new_card(consumed)

            await db.execute(
                f"DELETE FROM gacha_cards WHERE user_id = ? AND expedition = 0 AND instance_id IN ({placeholders})",
                (user_id, *instance_ids),
            )
            await _insert_cards(db, user_id, [new_card])
            if count_fusion:
                await db.execute(
                    """
                    INSERT INTO gacha_stats (user_id, total_fusions) VALUES (?, 1)
                    ON CONFLICT(user_id) DO UPDATE SET total_fusions = total_fusions + 1
                    """,
                    (user_id,),
                )
            if count_synthesis:
                await db.execute(
                    """
                    INSERT INTO gacha_stats (user_id, total_synths) VALUES (?, 1)
                    ON CONFLICT(user_id) DO UPDATE SET total_synths = total_synths + 1
                    """,
                    (user_id,),
                )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    card_cache.invalidate(user_id)
    return consumed, new_card


async def auto_synthesize_cards(user_id: int, character_key: str, run_synthesis) -> dict:
    """
    ⚡ 自動合成全部 (2026-11-23)：一位角色的卡全部自動合成，同一個交易
    - BEGIN IMMEDIATE ➔ 重新讀這位角色、卡冊裡 (不含收藏冊 locked、出征中 expedition) 的卡
    - run_synthesis(cards) 回傳 {"consumed": [被用掉的原本卡牌 ID], "created": [最後留下的新卡], "count": 合成次數, ...}；
      中間合出來又被拿去合的卡不會寫進資料庫；條件不符 (例如跟確認畫面不一樣) 丟出 ValueError ➔ 整筆不寫
    - 刪掉用掉的卡、寫入新卡、gacha_stats.total_synths + count (合成稱號一次算一次)
    回傳 run_synthesis 的結果
    """
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                """
                SELECT instance_id, character_key, name, emoji, rarity, title, completeness, obtained_at
                FROM gacha_cards WHERE user_id = ? AND character_key = ? AND locked = 0 AND expedition = 0 ORDER BY rowid
                """,
                (user_id, character_key),
            ) as cursor:
                cards = [apply_current_names(dict(row)) for row in await cursor.fetchall()]
            result = run_synthesis(cards)
            owned = {c["instance_id"] for c in cards}
            consumed = list(dict.fromkeys(result["consumed"]))
            if any(i not in owned for i in consumed):
                raise ValueError("部分卡牌已不在你的卡冊中")
            if consumed:
                placeholders = ", ".join("?" for _ in consumed)
                cursor = await db.execute(
                    f"DELETE FROM gacha_cards WHERE user_id = ? AND locked = 0 AND expedition = 0 AND instance_id IN ({placeholders})",
                    (user_id, *consumed),
                )
                if cursor.rowcount != len(consumed):
                    raise ValueError("部分卡牌已不在你的卡冊中")
            await _insert_cards(db, user_id, result["created"])
            if result["count"]:
                await db.execute(
                    """
                    INSERT INTO gacha_stats (user_id, total_synths) VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET total_synths = total_synths + excluded.total_synths
                    """,
                    (user_id, result["count"]),
                )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    card_cache.invalidate(user_id)
    return result


# ---------------------------------------------------------
# 🛠️ 8. 管理員卡冊操作 (Admin-gacha)
# ---------------------------------------------------------
async def delete_gacha_cards(user_id: int, instance_ids: list[str]) -> int:
    """刪除玩家指定的卡牌，回傳實際刪除的張數 (不屬於該玩家的 ID、🌀 出征中的卡會被忽略)"""
    if not instance_ids:
        return 0
    placeholders = ", ".join("?" for _ in instance_ids)
    async with connect() as db:
        cursor = await db.execute(
            f"DELETE FROM gacha_cards WHERE user_id = ? AND expedition = 0 AND instance_id IN ({placeholders})",
            (user_id, *instance_ids),
        )
        await db.commit()
    card_cache.invalidate(user_id)
    return cursor.rowcount


def _clear_scope(user_id: int | None, column: str = "user_id") -> tuple[str, tuple]:
    """清空卡冊用的 WHERE 條件：user_id None = 全部玩家"""
    return (f" AND {column} = ?", (user_id,)) if user_id is not None else ("", ())


async def count_gacha_clear(user_id: int | None = None) -> dict:
    """
    清空卡冊前的確認畫面用 (user_id None = 全部玩家)：
    {"players": 會被清到的玩家數, "cards": 卡冊 + 收藏冊張數, "listings": 上架中張數,
     "skipped": 🌀 出征中 (不會刪) 張數, "pity": 保底進度不是 0 的卡池數}
    """
    card_where, card_args = _clear_scope(user_id)
    list_where, list_args = _clear_scope(user_id, "seller_id")
    async with connect() as db:
        async def one(sql, args):
            async with db.execute(sql, args) as cursor:
                return (await cursor.fetchone())[0] or 0
        return {
            "players": await one(
                f"SELECT COUNT(*) FROM (SELECT user_id FROM gacha_cards WHERE expedition = 0{card_where} "
                f"UNION SELECT seller_id FROM market_listings WHERE 1 = 1{list_where})", card_args + list_args),
            "cards": await one(f"SELECT COUNT(*) FROM gacha_cards WHERE expedition = 0{card_where}", card_args),
            "listings": await one(f"SELECT COUNT(*) FROM market_listings WHERE 1 = 1{list_where}", list_args),
            "skipped": await one(f"SELECT COUNT(*) FROM gacha_cards WHERE expedition = 1{card_where}", card_args),
            "pity": await one(f"SELECT COUNT(*) FROM gacha_pity WHERE since_ur > 0{card_where}", card_args),
        }


async def _clear_cards(user_id: int | None) -> dict:
    """
    清空卡冊 (user_id None = 全部玩家)，同一個交易：
    - 刪掉卡冊 + 收藏冊的卡、市場上架中的卡 (連同通知用的上架快照，免得被當成到期退回)
    - 所有卡池的保底進度 (since_ur) 歸零；累計抽數、融合 / 合成次數、稱號統計都保留，不退賽錢
    - 🌀 裏世界出征中的卡不刪 (那一局結束後才清得掉)
    回傳 {"cards", "listings", "skipped"}
    """
    card_where, card_args = _clear_scope(user_id)
    list_where, list_args = _clear_scope(user_id, "seller_id")
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(f"SELECT listing_id FROM market_listings WHERE 1 = 1{list_where}", list_args) as cursor:
                listing_ids = [r["listing_id"] for r in await cursor.fetchall()]
            cursor = await db.execute(f"DELETE FROM gacha_cards WHERE expedition = 0{card_where}", card_args)
            cards = cursor.rowcount
            await db.execute(f"DELETE FROM market_listings WHERE 1 = 1{list_where}", list_args)
            async with db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notify_listings'") as cursor:
                has_snapshot = await cursor.fetchone() is not None
            if has_snapshot and listing_ids:
                await db.executemany("DELETE FROM notify_listings WHERE listing_id = ?", [(i,) for i in listing_ids])
            await db.execute(f"UPDATE gacha_pity SET since_ur = 0 WHERE 1 = 1{card_where}", card_args)
            async with db.execute(f"SELECT COUNT(*) FROM gacha_cards WHERE expedition = 1{card_where}", card_args) as cursor:
                skipped = (await cursor.fetchone())[0]
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    if user_id is None:
        card_cache.invalidate_all()
    else:
        card_cache.invalidate(user_id)
    return {"cards": cards, "listings": len(listing_ids), "skipped": skipped}


async def clear_gacha_cards(user_id: int) -> dict:
    """清空一位玩家的卡冊 (規則見 _clear_cards)，回傳 {"cards", "listings", "skipped"}"""
    return await _clear_cards(user_id)


async def clear_all_gacha_cards() -> dict:
    """清空全部玩家的卡冊 (規則見 _clear_cards；/admin-gacha clear_all，兩段確認後才呼叫)"""
    return await _clear_cards(None)


async def update_cards_completeness(user_id: int, instance_ids: list[str], completeness: float) -> int:
    """把玩家指定的卡牌完整度設為同一個值，回傳實際修改的張數 (不屬於該玩家的 ID 會被忽略)"""
    if not instance_ids:
        return 0
    placeholders = ", ".join("?" for _ in instance_ids)
    async with connect() as db:
        cursor = await db.execute(
            f"UPDATE gacha_cards SET completeness = ? WHERE user_id = ? AND expedition = 0 AND instance_id IN ({placeholders})",
            (completeness, user_id, *instance_ids),
        )
        await db.commit()
    card_cache.invalidate(user_id)
    return cursor.rowcount

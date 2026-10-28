"""
👤 玩家資料庫管理 (Database/Users.db)

所有「跟玩家有關」的資料都在同一個資料庫裡：
  - users        ：賽錢 / 等級 / 經驗 / 背包 / 隱私 / 每日簽到日期與運勢
  - gacha_stats  ：每位玩家的抽卡統計
  - gacha_cards  ：每位玩家持有的卡牌 (每張卡一列)

道具範本 (item_templates) 在另一個資料庫：請見 Item_DB_Manager.py
"""
import os
import json
from contextlib import asynccontextmanager

import aiosqlite

# 資料庫檔案與本檔案放在同一個資料夾 (Database/)
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "Users.db")
# 舊版資料庫位置 (專案根目錄)，只用來在啟動時提醒「還沒遷移」
LEGACY_DB_PATH = os.path.join(os.path.dirname(DB_DIR), "database.db")


# ---------------------------------------------------------
# 🧱 資料表結構 (整個資料庫的結構都定義在這裡)
# ---------------------------------------------------------
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id       INTEGER PRIMARY KEY,
        money         INTEGER DEFAULT 1000,
        level         INTEGER DEFAULT 0,
        exp           INTEGER DEFAULT 0,
        last_daily    TEXT    DEFAULT NULL,
        fortune_level INTEGER DEFAULT NULL,
        inventory     TEXT    DEFAULT '{}',
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_public     INTEGER DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gacha_stats (
        user_id       INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
        total_draws   INTEGER NOT NULL DEFAULT 0,
        total_fusions INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gacha_cards (
        instance_id   TEXT PRIMARY KEY,
        user_id       INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        character_key TEXT NOT NULL,
        name          TEXT NOT NULL,
        emoji         TEXT,
        rarity        TEXT NOT NULL,
        title         TEXT,
        completeness  REAL NOT NULL,
        obtained_at   TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_gacha_cards_user ON gacha_cards(user_id)",
]

# 舊版 users 資料表可能缺少的欄位：(欄位名, 欄位定義)；init_db 會自動補上
USERS_EXTRA_COLUMNS = [
    ("is_public", "INTEGER DEFAULT 1"),
    ("fortune_level", "INTEGER DEFAULT NULL"),
]


@asynccontextmanager
async def connect():
    """
    統一的連線入口：
    - 開啟外鍵約束 (卡牌一定屬於存在的玩家)
    - 查詢結果可用欄位名稱存取 (row["money"])
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


async def _ensure_user(db, user_id: int):
    """確保玩家資料列存在 (用資料表預設值建立：1000 賽錢、0 等級、空背包)"""
    await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))


# ---------------------------------------------------------
# 🛠️ 1. 資料庫初始化 (開機時呼叫)
# ---------------------------------------------------------
async def init_db():
    """建立 Users.db 的所有資料表；舊版資料表缺少的欄位會自動補上"""
    existed = os.path.exists(DB_PATH)
    if not existed and os.path.exists(LEGACY_DB_PATH):
        print("⚠️ [Database] 偵測到舊版 database.db，但還沒有 Database/Users.db！")
        print("⚠️ [Database] 請先執行 `python migrate_legacy.py` 遷移舊資料，否則玩家資料會從零開始。")

    async with connect() as db:
        for statement in SCHEMA_STATEMENTS:
            await db.execute(statement)

        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = [row["name"] for row in await cursor.fetchall()]
        for column, definition in USERS_EXTRA_COLUMNS:
            if column not in columns:
                await db.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
                print(f"🔧 [Database] 已自動為 users 資料表補上 `{column}` 欄位！")

        await db.commit()
    print("✅ [Database] Users.db 連線成功並已完成表單初始化！")


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
    current_level = user_data.get("level", 0)  # 內部 level: 0 ~ 1000
    current_exp = user_data.get("exp", 0)

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

    # 4. 寫回資料庫
    async with connect() as db:
        await db.execute(
            "UPDATE users SET level = ?, exp = ? WHERE user_id = ?",
            (new_level, new_exp, user_id)
        )
        await db.commit()

    return {
        "leveled_up": leveled_up,
        "is_degraded": is_degraded,
        "old_p": old_p,
        "new_p": new_p,
        "current_exp": new_exp,
        "is_max": (new_level >= 1000)
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


async def claim_daily(user_id: int, today: str, fortune_level: int) -> bool:
    """
    原子性地「搶」今天的簽到名額：只有 last_daily 不是今天時才會寫入成功。
    連點按鈕或兩個視窗同時簽到，也只會有一個人拿到 True，不會重複領獎。
    """
    async with connect() as db:
        await _ensure_user(db, user_id)
        cursor = await db.execute(
            """
            UPDATE users
            SET last_daily = ?, fortune_level = ?
            WHERE user_id = ? AND (last_daily IS NULL OR last_daily != ?)
            """,
            (today, fortune_level, user_id, today),
        )
        claimed = cursor.rowcount == 1
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
async def add_item(user_id: int, item_id: str, amount: int = 1) -> dict:
    """給予玩家指定道具與數量，傳回更新後的背包字典"""
    user_data = await get_or_create_user(user_id)
    inventory = user_data["inventory"]

    # 更新背包數量
    inventory[item_id] = inventory.get(item_id, 0) + amount
    if inventory[item_id] <= 0:
        del inventory[item_id]  # 數量小於等於 0 則移除道具

    await update_user_inventory(user_id, inventory)
    return inventory


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
async def get_top_money(limit: int = 10) -> list[tuple[int, int]]:
    """取得賽錢排行榜前 N 名，傳回 [(user_id, money), ...]"""
    async with connect() as db:
        async with db.execute(
            "SELECT user_id, money FROM users ORDER BY money DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [(row["user_id"], row["money"]) for row in rows]


async def update_visibility(user_id: int, is_public: bool):
    """更新玩家資料卡片的公開/私人狀態 (is_public: True 代表公開)"""
    async with connect() as db:
        await _ensure_user(db, user_id)
        await db.execute(
            "UPDATE users SET is_public = ? WHERE user_id = ?",
            (1 if is_public else 0, user_id)
        )
        await db.commit()


# ---------------------------------------------------------
# 🎴 7. 抽卡 (Gacha)：卡牌與統計
# ---------------------------------------------------------
async def get_user_cards(user_id: int) -> list[dict]:
    """取得玩家持有的所有卡牌 (依取得順序)"""
    async with connect() as db:
        async with db.execute(
            """
            SELECT instance_id, character_key, name, emoji, rarity, title, completeness, obtained_at
            FROM gacha_cards WHERE user_id = ? ORDER BY rowid
            """,
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


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


async def add_gacha_cards(user_id: int, cards: list[dict], draw_count: int | None = None):
    """
    一次寫入「這次抽到的所有卡牌」並累加抽卡次數。
    全部在同一個交易裡：要嘛卡牌與統計都寫入，要嘛都不寫入。
    draw_count 預設等於卡牌張數。
    """
    draw_count = len(cards) if draw_count is None else draw_count
    async with connect() as db:
        await _ensure_user(db, user_id)
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
        await db.execute(
            """
            INSERT INTO gacha_stats (user_id, total_draws) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET total_draws = total_draws + excluded.total_draws
            """,
            (user_id, draw_count),
        )
        await db.commit()


async def transform_cards(user_id: int, instance_ids: list[str], build_new_card, count_fusion: bool = False) -> tuple[list[dict], dict]:
    """
    合成 / 融合共用：消耗指定卡牌並產生一張新卡 (同一個交易)。
    - 以 BEGIN IMMEDIATE 鎖定資料庫，讀取 → 驗證 → 刪除 → 寫入之間不會被其他操作插隊
    - build_new_card(consumed_cards) 負責驗證並回傳新卡；條件不符時丟出 ValueError
    - 任何一張卡已不屬於玩家 (被用掉 / 不存在) 也會丟出 ValueError，整筆不寫入
    - count_fusion=True 時累加 gacha_stats.total_fusions
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
                FROM gacha_cards WHERE user_id = ? AND instance_id IN ({placeholders})
                """,
                (user_id, *instance_ids),
            ) as cursor:
                rows = {row["instance_id"]: dict(row) for row in await cursor.fetchall()}
            if len(rows) != len(instance_ids):
                raise ValueError("部分卡牌已不在你的卡冊中")
            consumed = [rows[i] for i in instance_ids]   # 保持呼叫端給的順序

            new_card = build_new_card(consumed)

            await db.execute(
                f"DELETE FROM gacha_cards WHERE user_id = ? AND instance_id IN ({placeholders})",
                (user_id, *instance_ids),
            )
            await db.execute(
                """
                INSERT INTO gacha_cards
                    (instance_id, user_id, character_key, name, emoji, rarity, title, completeness, obtained_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_card["instance_id"], user_id, new_card["character_key"], new_card["name"], new_card.get("emoji"),
                    new_card["rarity"], new_card.get("title"), new_card["completeness"], new_card.get("obtained_at"),
                ),
            )
            if count_fusion:
                await db.execute(
                    """
                    INSERT INTO gacha_stats (user_id, total_fusions) VALUES (?, 1)
                    ON CONFLICT(user_id) DO UPDATE SET total_fusions = total_fusions + 1
                    """,
                    (user_id,),
                )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return consumed, new_card


# ---------------------------------------------------------
# 🛠️ 8. 管理員卡冊操作 (Admin-gacha)
# ---------------------------------------------------------
async def delete_gacha_cards(user_id: int, instance_ids: list[str]) -> int:
    """刪除玩家指定的卡牌，回傳實際刪除的張數 (不屬於該玩家的 ID 會被忽略)"""
    if not instance_ids:
        return 0
    placeholders = ", ".join("?" for _ in instance_ids)
    async with connect() as db:
        cursor = await db.execute(
            f"DELETE FROM gacha_cards WHERE user_id = ? AND instance_id IN ({placeholders})",
            (user_id, *instance_ids),
        )
        await db.commit()
        return cursor.rowcount


async def clear_gacha_cards(user_id: int) -> int:
    """清空玩家的整本卡冊 (抽卡統計保留)，回傳刪除的張數"""
    async with connect() as db:
        cursor = await db.execute("DELETE FROM gacha_cards WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount


async def update_cards_completeness(user_id: int, instance_ids: list[str], completeness: float) -> int:
    """把玩家指定的卡牌完整度設為同一個值，回傳實際修改的張數 (不屬於該玩家的 ID 會被忽略)"""
    if not instance_ids:
        return 0
    placeholders = ", ".join("?" for _ in instance_ids)
    async with connect() as db:
        cursor = await db.execute(
            f"UPDATE gacha_cards SET completeness = ? WHERE user_id = ? AND instance_id IN ({placeholders})",
            (completeness, user_id, *instance_ids),
        )
        await db.commit()
        return cursor.rowcount

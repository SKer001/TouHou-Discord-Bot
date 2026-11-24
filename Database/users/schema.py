"""
🧱 資料表結構與初始化：DB_PATH、SCHEMA_STATEMENTS、connect、_ensure_user、init_db

從 Database/User_DB_Manager.py 拆出來的；外面一律照舊從 Database.User_DB_Manager 匯入 (入口)，不要直接匯入這裡。
"""
import os
from contextlib import asynccontextmanager

import aiosqlite

# 資料庫檔案放在 Database/ (這個檔在 Database/users/ 底下，所以往上一層)
DB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "Users.db")
# 舊版資料庫位置 (專案根目錄)，只用來在啟動時提醒「還沒遷移」
LEGACY_DB_PATH = os.path.join(os.path.dirname(DB_DIR), "database.db")

# 💰 新玩家的起步賽錢 (2026-11-23 使用者定：1,000 ➔ 50,000 = 10 抽，一進來就能抽；已經有資料的玩家不補)
STARTING_MONEY = 50_000


# ---------------------------------------------------------
# 🧱 資料表結構 (整個資料庫的結構都定義在這裡)
# ---------------------------------------------------------
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id       INTEGER PRIMARY KEY,
        money         INTEGER DEFAULT 50000,
        level         INTEGER DEFAULT 0,
        exp           INTEGER DEFAULT 0,
        last_daily    TEXT    DEFAULT NULL,
        fortune_level INTEGER DEFAULT NULL,
        inventory     TEXT    DEFAULT '{}',
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_public     INTEGER DEFAULT 1,
        stamina       INTEGER DEFAULT 240,
        stamina_updated_at TEXT DEFAULT NULL,
        daily_count   INTEGER DEFAULT 0,
        equipped_title TEXT   DEFAULT NULL,
        daily_streak  INTEGER DEFAULT 0,
        best_streak   INTEGER DEFAULT 0,
        granted_titles TEXT   DEFAULT NULL,
        best_money    INTEGER DEFAULT 0,
        equipped_namecard TEXT DEFAULT NULL
    )
    """,
    # 🖼️ 角色名片：source = 'oshi' (推角稱號解鎖) / 'admin' (管理員給)；稱號失去後名片還在
    """
    CREATE TABLE IF NOT EXISTS namecards (
        user_id       INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        character_key TEXT NOT NULL,
        obtained_at   TEXT NOT NULL,
        source        TEXT NOT NULL DEFAULT 'oshi',
        PRIMARY KEY (user_id, character_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gacha_stats (
        user_id       INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
        total_draws   INTEGER NOT NULL DEFAULT 0,
        total_fusions INTEGER NOT NULL DEFAULT 0,
        total_synths  INTEGER NOT NULL DEFAULT 0
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
        obtained_at   TEXT,
        locked        INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_gacha_cards_user ON gacha_cards(user_id)",
    # 📊 玩家統計 (通用計數器，一筆 = 玩家 + 項目 + 數字；2026-11-14 起記神社動作，稱號用)
    #    項目見 PLAYER_STATS；以後要多記什麼直接多一個項目名稱，不用改資料表
    """
    CREATE TABLE IF NOT EXISTS player_stats (
        user_id INTEGER NOT NULL,
        stat    TEXT NOT NULL,
        value   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, stat)
    )
    """,
    # 🎪 活動任務 (Database/Quest_DB_Manager.py)：活動進行中才記的計數，一輪 (run) = 活動 id + 這次開始時間
    #    stat 例：explore:<地點>、cook:<料理>、serve_guest:<客人>、serve_event_dish、serve_favorite、gacha_event_pool、daily、
    #    🌀 裏世界 ura_kill:<敵人>、ura_fest_boss、ura_fest_treasure、ura_evacuate (0.35.090，Ura_DB_Manager)
    """
    CREATE TABLE IF NOT EXISTS event_quest_stats (
        user_id INTEGER NOT NULL,
        run     TEXT NOT NULL,
        stat    TEXT NOT NULL,
        value   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, run, stat)
    )
    """,
    # 誰在哪一輪領了哪個任務 (主鍵防重複領取)
    """
    CREATE TABLE IF NOT EXISTS event_quest_claims (
        user_id    INTEGER NOT NULL,
        run        TEXT NOT NULL,
        quest_id   TEXT NOT NULL,
        event_id   TEXT NOT NULL,
        claimed_at TEXT NOT NULL,
        PRIMARY KEY (user_id, run, quest_id)
    )
    """,
    # 🏷️ 永久獲得的稱號 (活動任務稱號；活動結束也保留)
    """
    CREATE TABLE IF NOT EXISTS earned_titles (
        user_id   INTEGER NOT NULL,
        title_id  TEXT NOT NULL,
        earned_at TEXT NOT NULL,
        PRIMARY KEY (user_id, title_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gacha_pity (
        user_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        pool        TEXT    NOT NULL,
        total_draws INTEGER NOT NULL DEFAULT 0,
        since_ur    INTEGER NOT NULL DEFAULT 0,
        last_ur_at  TEXT    DEFAULT NULL,
        PRIMARY KEY (user_id, pool)
    )
    """,
    # ---- 💹 經濟系統 (Economy_DB_Manager.py) ----
    # 每天 (台灣時間) 各卡池的全服抽卡數：浮動市值的基準
    """
    CREATE TABLE IF NOT EXISTS daily_draws (
        day   TEXT NOT NULL,
        pool  TEXT NOT NULL,
        draws INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, pool)
    )
    """,
    # 每天各卡 (角色 × 階級) 的賣出張數 (市場成交 + 分解)
    """
    CREATE TABLE IF NOT EXISTS daily_sales (
        day           TEXT NOT NULL,
        character_key TEXT NOT NULL,
        rarity        TEXT NOT NULL,
        sold          INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, character_key, rarity)
    )
    """,
    # 目前市值 (完整度 0.5 的價格) 與每日結算後的歷史
    """
    CREATE TABLE IF NOT EXISTS market_prices (
        character_key TEXT NOT NULL,
        rarity        TEXT NOT NULL,
        price         REAL NOT NULL,
        PRIMARY KEY (character_key, rarity)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS price_history (
        day           TEXT NOT NULL,
        character_key TEXT NOT NULL,
        rarity        TEXT NOT NULL,
        price         REAL NOT NULL,
        change        REAL NOT NULL,
        PRIMARY KEY (day, character_key, rarity)
    )
    """,
    "CREATE TABLE IF NOT EXISTS economy_meta (key TEXT PRIMARY KEY, value TEXT)",
    # 市場上架中的卡 (上架時卡牌從 gacha_cards 移到這裡託管，賣出或下架再移回)
    """
    CREATE TABLE IF NOT EXISTS market_listings (
        listing_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        instance_id   TEXT NOT NULL UNIQUE,
        character_key TEXT NOT NULL,
        name          TEXT NOT NULL,
        emoji         TEXT,
        rarity        TEXT NOT NULL,
        title         TEXT,
        completeness  REAL NOT NULL,
        obtained_at   TEXT,
        price         INTEGER NOT NULL,
        listed_at     TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_listings_char ON market_listings(character_key, rarity)",
    # 成交 / 分解 / 轉帳紀錄
    """
    CREATE TABLE IF NOT EXISTS market_trades (
        trade_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        kind          TEXT NOT NULL,
        seller_id     INTEGER,
        buyer_id      INTEGER,
        instance_id   TEXT,
        character_key TEXT,
        rarity        TEXT,
        price         INTEGER NOT NULL,
        fee           INTEGER NOT NULL DEFAULT 0,
        day           TEXT NOT NULL,
        created_at    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_trades_day ON market_trades(kind, seller_id, day)",
    # 神社：狀態 + 參拜客 (JSON)
    """
    CREATE TABLE IF NOT EXISTS ura_runs (
        user_id     INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
        rev         INTEGER NOT NULL DEFAULT 0,
        state       TEXT NOT NULL,
        channel_id  INTEGER,
        message_id  INTEGER,
        started_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """,
    # 🌀 裏世界倉庫 (kind = item 道具 / treasure 寶物)；額外背包一個一列 (用 3 次就壞)；排行榜紀錄 (0.35.083)
    """
    CREATE TABLE IF NOT EXISTS ura_storage (
        user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        kind    TEXT NOT NULL,
        key     TEXT NOT NULL,
        qty     INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, kind, key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ura_bags (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id   INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        bag_id    TEXT NOT NULL,
        uses_left INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ura_records (
        user_id          INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
        best_money       INTEGER NOT NULL DEFAULT 0,
        best_money_at    TEXT,
        best_money_party TEXT,
        deepest          INTEGER NOT NULL DEFAULT 0,
        deepest_at       TEXT,
        deepest_party    TEXT,
        loadout          TEXT
    )
    """,
    # 📖 裏世界怪物圖鑑的領獎紀錄 (0.35.103)：reward_id = zone:<主題> / all / fest:<活動>；主鍵防重複領
    """
    CREATE TABLE IF NOT EXISTS ura_bestiary_claims (
        user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        reward_id  TEXT NOT NULL,
        claimed_at TEXT NOT NULL,
        PRIMARY KEY (user_id, reward_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shrines (
        user_id     INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        tick        INTEGER NOT NULL DEFAULT 0,
        box         REAL NOT NULL DEFAULT 0,
        clean_at    TEXT NOT NULL,
        dirt_extra  INTEGER NOT NULL DEFAULT 0,
        youkai      INTEGER NOT NULL DEFAULT 0,
        guests      TEXT NOT NULL DEFAULT '[]'
    )
    """,
]

# 舊版 users 資料表可能缺少的欄位：(欄位名, 欄位定義)；init_db 會自動補上
USERS_EXTRA_COLUMNS = [
    ("is_public", "INTEGER DEFAULT 1"),
    ("fortune_level", "INTEGER DEFAULT NULL"),
    ("stamina", "INTEGER DEFAULT 240"),
    ("stamina_updated_at", "TEXT DEFAULT NULL"),
    ("daily_count", "INTEGER DEFAULT 0"),   # 累積簽到天數 (滿 7 天開放市場與轉帳)
    ("equipped_title", "TEXT DEFAULT NULL"),   # 戴著的稱號 id (Database/title_data.py)；NULL = 沒戴
    ("daily_streak", "INTEGER DEFAULT 0"),     # 目前連續簽到天數 (0.31.005 起才開始記；昨天有簽 +1，否則重新從 1 算)
    ("best_streak", "INTEGER DEFAULT 0"),      # 最長連續簽到天數 (斷掉也不會變少；連續簽到稱號用)
    ("granted_titles", "TEXT DEFAULT NULL"),   # 管理員直接給的稱號 id (逗號分隔)；不用符合條件，/admin-user title 管理
    ("best_money", "INTEGER DEFAULT 0"),       # 曾經持有過的最高賽錢 (財富稱號；觸發器自動更新，剛補欄位時用當下餘額當起點)
    ("equipped_namecard", "TEXT DEFAULT NULL"),   # 戴著的角色名片 (角色 id，namecards 表)；NULL = 不放名片
    ("stamina_item_day", "TEXT DEFAULT NULL"),    # 最後一次吃體力道具的日期 (台灣時間 YYYY-MM-DD)；每日上限用
    ("stamina_item_used", "INTEGER DEFAULT 0"),   # stamina_item_day 那天吃了幾個 (上限 STAMINA_ITEM_DAILY_LIMIT)
    ("job_day", "TEXT DEFAULT NULL"),             # 🏮 人里打工：最後一次打工的日期 (台灣時間 YYYY-MM-DD)
    ("job_used", "INTEGER DEFAULT 0"),            # job_day 那天打了幾次 (上限 Economy_DB_Manager.JOB_DAILY_LIMIT)
]
# 💰 best_money 由觸發器維護：任何地方改到 money (簽到、分解、市場、轉帳、神社…) 都會自動跟上，不用每個函式自己記
#    (init_db 補完欄位之後才建，舊資料庫建觸發器時欄位已經在了)
MONEY_TRIGGERS = [
    """
    CREATE TRIGGER IF NOT EXISTS trg_best_money_update AFTER UPDATE OF money ON users
    WHEN NEW.money > COALESCE(NEW.best_money, 0)
    BEGIN UPDATE users SET best_money = NEW.money WHERE user_id = NEW.user_id; END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_best_money_insert AFTER INSERT ON users
    WHEN NEW.money > COALESCE(NEW.best_money, 0)
    BEGIN UPDATE users SET best_money = NEW.money WHERE user_id = NEW.user_id; END
    """,
]
# 舊版 gacha_stats 缺少的欄位 (init_db 自動補上)
GACHA_STATS_EXTRA_COLUMNS = [
    ("total_synths", "INTEGER NOT NULL DEFAULT 0"),   # 累計合成次數 (2026-11-13 起才開始記，之前的補不回來；合成稱號用)
]
# 舊版 gacha_cards 缺少的欄位 (init_db 自動補上)
GACHA_CARDS_EXTRA_COLUMNS = [
    ("locked", "INTEGER NOT NULL DEFAULT 0"),   # 1 = 放在收藏冊 (/card album)：卡冊、合成、融合、分解、上架都看不到也用不到
    ("expedition", "INTEGER NOT NULL DEFAULT 0"),   # 1 = 🌀 裏世界出征中 (0.35.083；跟收藏冊的 locked 分開)：卡冊、合成、融合、分解、上架、收藏冊、管理員刪卡 / 改完整度都擋
]
# 欄位剛補上時，現有玩家要填的值 (使用者 2026-11-05：現有玩家直接開通交易)
USERS_BACKFILL = {"daily_count": "7", "best_money": "money"}   # best_money：從現在的餘額開始記 (之前的最高值查不到)


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
    """確保玩家資料列存在 (新玩家：STARTING_MONEY 賽錢、0 等級、空背包)
    賽錢直接寫進去，不靠資料表預設值：舊的 Users.db 欄位預設還是 1000 (SQLite 不能改欄位預設)"""
    await db.execute("INSERT OR IGNORE INTO users (user_id, money) VALUES (?, ?)", (user_id, STARTING_MONEY))


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
                if column in USERS_BACKFILL:
                    await db.execute(f"UPDATE users SET {column} = {USERS_BACKFILL[column]}")
                print(f"🔧 [Database] 已自動為 users 資料表補上 `{column}` 欄位！")
        async with db.execute("PRAGMA table_info(gacha_stats)") as cursor:
            columns = [row["name"] for row in await cursor.fetchall()]
        for column, definition in GACHA_STATS_EXTRA_COLUMNS:
            if column not in columns:
                await db.execute(f"ALTER TABLE gacha_stats ADD COLUMN {column} {definition}")
                print(f"🔧 [Database] 已自動為 gacha_stats 資料表補上 `{column}` 欄位！")
        for statement in MONEY_TRIGGERS:
            await db.execute(statement)
        async with db.execute("PRAGMA table_info(gacha_cards)") as cursor:
            columns = [row["name"] for row in await cursor.fetchall()]
        for column, definition in GACHA_CARDS_EXTRA_COLUMNS:
            if column not in columns:
                await db.execute(f"ALTER TABLE gacha_cards ADD COLUMN {column} {definition}")
                print(f"🔧 [Database] 已自動為 gacha_cards 資料表補上 `{column}` 欄位！")

        await db.commit()
    print("✅ [Database] Users.db 連線成功並已完成表單初始化！")

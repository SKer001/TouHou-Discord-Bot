import os
import json
import aiosqlite

# 指定資料庫檔案路徑（放在專案根目錄下的 database.db）
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database.db")


# ---------------------------------------------------------
# 🛠️ 1. 資料庫初始化 (開機時呼叫)
# ---------------------------------------------------------
async def init_db():
    """初始化 SQLite 資料庫與建立/更新 users 資料表"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. 建立基礎 users 資料表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                money INTEGER DEFAULT 1000,
                level INTEGER DEFAULT 1,
                exp INTEGER DEFAULT 0,
                last_daily TEXT DEFAULT NULL,
                inventory TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. 自動檢查並補上舊資料表缺少的 is_public 欄位
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = [column[1] for column in await cursor.fetchall()]
            if "is_public" not in columns:
                await db.execute("ALTER TABLE users ADD COLUMN is_public INTEGER DEFAULT 1")
                print("🔧 [Database] 已自動為舊資料表補上 `is_public` 欄位！")

        await db.commit()
    print("✅ [Database] SQLite 資料庫連線成功並已完成表單初始化！")


# ---------------------------------------------------------
# 👤 2. 取得或自動建立玩家資料 (Auto-Registration)
# ---------------------------------------------------------
async def get_or_create_user(user_id: int) -> dict:
    """
    取得玩家資料；若玩家不存在則自動創建初始資料
    傳回字典格式的玩家資料
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row  # 讓查詢結果可以用欄位名稱存取
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()

            if row:
                user_data = dict(row)
                # 將 JSON 字串轉回 Python 字典
                user_data["inventory"] = json.loads(user_data["inventory"])
                return user_data

            # 若不存在，插入新玩家 (預設給予 1000 賽錢)
            await db.execute(
                "INSERT INTO users (user_id, money, level, exp, inventory) VALUES (?, 1000, 1, 0, '{}')",
                (user_id,)
            )
            await db.commit()

            # 重新取得剛建立的玩家資料
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as new_cursor:
                new_row = await new_cursor.fetchone()
                user_data = dict(new_row)
                user_data["inventory"] = json.loads(user_data["inventory"])
                return user_data


# ---------------------------------------------------------
# 💰 3. 貨幣與經驗值操作 (Money & Exp)
# ---------------------------------------------------------
async def add_money(user_id: int, amount: int) -> int:
    """增加或扣除玩家賽錢 (amount 可為正數或負數)，傳回更新後的金額"""
    # 確保玩家資料已存在
    await get_or_create_user(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET money = money + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

        async with db.execute("SELECT money FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def update_daily_time(user_id: int, date_str: str):
    """更新玩家上次每日簽到的日期 (格式: YYYY-MM-DD)"""
    await get_or_create_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_daily = ? WHERE user_id = ?",
            (date_str, user_id)
        )
        await db.commit()


# ---------------------------------------------------------
# 🎒 4. 背包道具操作 (Inventory)
# ---------------------------------------------------------
async def add_item(user_id: int, item_id: str, amount: int = 1) -> dict:
    """給予玩家指定道具與數量，傳回更新後的背包字典"""
    user_data = await get_or_create_user(user_id)
    inventory = user_data["inventory"]

    # 更新背包數量
    inventory[item_id] = inventory.get(item_id, 0) + amount
    if inventory[item_id] <= 0:
        del inventory[item_id]  # 數量小於等於 0 則移除道具

    inventory_json = json.dumps(inventory, ensure_ascii=False)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET inventory = ? WHERE user_id = ?",
            (inventory_json, user_id)
        )
        await db.commit()

    return inventory


# ---------------------------------------------------------
# 🏆 5. 排行榜查詢 (Leaderboard)
# ---------------------------------------------------------
async def get_top_money(limit: int = 10) -> list[tuple[int, int]]:
    """取得賽錢排行榜前 N 名，傳回 [(user_id, money), ...]"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, money FROM users ORDER BY money DESC LIMIT ?",
            (limit,)
        ) as cursor:
            return await cursor.fetchall()


async def update_visibility(user_id: int, is_public: bool):
    """更新玩家資料卡片的公開/私人狀態 (is_public: True 代表公開)"""
    await get_or_create_user(user_id)
    value = 1 if is_public else 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_public = ? WHERE user_id = ?",
            (value, user_id)
        )
        await db.commit()
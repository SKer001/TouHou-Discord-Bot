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
                level INTEGER DEFAULT 0,
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
                "INSERT INTO users (user_id, money, level, exp, inventory) VALUES (?, 1000, 0, 0, '{}')",
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


async def reset_daily(user_id: int) -> bool:
    """
    【開發者 / 管理專用】重置指定玩家的 last_daily 簽到紀錄
    將 last_daily 設為 NULL，使其能立即再次觸發每日簽到。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_daily = NULL WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
    return True


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
        
        
# Database/db_manager.py

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

    # 4. 寫回 SQLite 資料庫
    async with aiosqlite.connect(DB_PATH) as db:
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
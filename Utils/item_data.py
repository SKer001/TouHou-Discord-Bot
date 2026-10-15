# Utils/item_data.py
import os
import aiosqlite

# 設定資料庫路徑：與這個腳本同目錄下的 item.db
DB_PATH = os.path.join(os.path.dirname(__file__), "item.db")

CATEGORY_NAMES = {
    "all": "🌸 全部道具",
    "consumable": "🍵 消耗品",
    "collectible": "🎴 收藏品",
    "special": "🛠️ 裝備與特殊"
}

# 預設道具清單 (僅在資料庫完全空白時會自動寫入)
DEFAULT_ITEMS = [
    ("apple", "幻想鄉蘋果", "🍎", "consumable", "普通的蘋果，吃起來脆脆的。"),
    ("bomb", "靈擊符", "💣", "consumable", "緊急迴避用的符卡。"),
    ("frog_coin", "守矢硬幣", "🪙", "collectible", "守矢神社發行的紀念幣。"),
    ("hakurei_tea", "博麗神社的茶", "🍵", "consumable", "悠閒的下午茶，喝了能稍微回復精神。"),
    ("kappa_water", "河童礦泉水", "💧", "consumable", "妖怪之山產出的純淨水。"),
    ("mini_hakkero", "迷你八卦爐", "🔥", "special", "魔理沙的魔法道具，火力十足。"),
    ("sake", "鬼殺酒", "🍶", "consumable", "伊吹萃香最愛的酒。"),
    ("senbei", "仙貝", "🍘", "consumable", "普通的仙貝，配茶剛剛好。"),
    ("spell_card_1", "夢想封印", "🎴", "collectible", "靈夢的招牌符卡。"),
    ("spell_card_2", "大魔理沙", "🎴", "collectible", "魔理沙的招牌符卡。"),
    ("tengu_camera", "天狗的相機", "📷", "special", "文文用來取材的相機。"),
    ("yinyang_orb", "陰陽玉", "☯️", "collectible", "博麗神社的秘寶。")
]

async def init_item_db():
    """初始化 item.db 資料表，若為空則寫入預設資料"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS item_templates (
                item_id TEXT PRIMARY KEY,
                name TEXT,
                emoji TEXT,
                category TEXT,
                description TEXT
            )
        """)
        # 檢查是否為空
        async with db.execute("SELECT COUNT(*) FROM item_templates") as cursor:
            count = await cursor.fetchone()
            if count[0] == 0:
                await db.executemany(
                    "INSERT INTO item_templates (item_id, name, emoji, category, description) VALUES (?, ?, ?, ?, ?)",
                    DEFAULT_ITEMS
                )
        await db.commit()

async def get_all_items() -> dict:
    """
    從資料庫讀取所有道具範本，轉換為字典回傳
    回傳格式: {"item_id": {"name": "...", "emoji": "...", "category": "...", "desc": "..."}}
    """
    await init_item_db()
    items = {}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT item_id, name, emoji, category, description FROM item_templates") as cursor:
            async for row in cursor:
                items[row[0]] = {
                    "name": row[1],
                    "emoji": row[2],
                    "category": row[3],
                    "desc": row[4]
                }
    return items

# --- 以下新增至 Utils/item_data.py 最下方 ---

async def get_item(item_id: str) -> dict | None:
    """查詢單一道具"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name, emoji, category, description FROM item_templates WHERE item_id = ?", (item_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"item_id": item_id, "name": row[0], "emoji": row[1], "category": row[2], "desc": row[3]}
    return None

async def add_item_db(item_id: str, name: str, emoji: str, category: str, desc: str) -> bool:
    """新增單一道具 (若 ID 已存在則回傳 False)"""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO item_templates (item_id, name, emoji, category, description) VALUES (?, ?, ?, ?, ?)",
                (item_id, name, emoji, category, desc)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False  # ID 已存在

async def update_item_db(item_id: str, name: str, emoji: str, category: str, desc: str):
    """更新道具資料"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE item_templates SET name = ?, emoji = ?, category = ?, description = ? WHERE item_id = ?",
            (name, emoji, category, desc, item_id)
        )
        await db.commit()

async def delete_item_db(item_id: str):
    """刪除單一道具"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM item_templates WHERE item_id = ?", (item_id,))
        await db.commit()

async def batch_import_db(items_dict: dict, overwrite: bool) -> tuple[int, int]:
    """批量匯入 JSON 道具 (回傳: 成功數, 跳過數)"""
    success, skipped = 0, 0
    async with aiosqlite.connect(DB_PATH) as db:
        for item_id, data in items_dict.items():
            name = data.get("name", "未命名")
            emoji = data.get("emoji", "❓")
            category = data.get("category", "special")
            desc = data.get("desc", "無描述")

            if overwrite:
                await db.execute(
                    "INSERT OR REPLACE INTO item_templates (item_id, name, emoji, category, description) VALUES (?, ?, ?, ?, ?)",
                    (item_id, name, emoji, category, desc)
                )
                success += 1
            else:
                try:
                    await db.execute(
                        "INSERT INTO item_templates (item_id, name, emoji, category, description) VALUES (?, ?, ?, ?, ?)",
                        (item_id, name, emoji, category, desc)
                    )
                    success += 1
                except aiosqlite.IntegrityError:
                    skipped += 1
        await db.commit()
    return success, skipped
"""
🎒 道具範本資料庫管理 (Database/Item.db)

只負責「道具長什麼樣子」(名稱 / 圖示 / 分類 / 說明 / 效果)。
玩家背包裡有哪些道具、各幾件，存在 Users.db：請見 User_DB_Manager.py

effect 是 JSON 字串，目前支援：
  {"stamina": 120}   使用後回復 120 體力 (可超過自然回復上限 240)
"""
import os
import json
import aiosqlite

# 設定資料庫路徑：與這個腳本同目錄下的 Item.db
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Item.db")

CATEGORY_NAMES = {
    "all": "🌸 全部道具",
    "consumable": "🍵 消耗品",
    "collectible": "🎴 收藏品",
    "special": "🛠️ 裝備與特殊"
}

# 每日簽到固定贈送的道具 (道具 ID, 數量)
DAILY_REWARD_ITEM = ("reimu_onigiri", 1)

# 預設道具清單 (僅在資料庫完全空白時會自動寫入)：(item_id, 名稱, emoji, 分類, 說明, 效果)
DEFAULT_ITEMS = [
    ("yuyuko_dango", "幽夢三色團子", "🍡", "consumable",
     "白玉樓秘製的花見團子，口感軟糯 Q 彈並帶有淡淡櫻花香。吃下一串能讓消耗的靈力與體力瞬間恢復，但要小心別被某位亡靈大小姐搶走了。",
     {"stamina": 120}),
    ("sakuya_scone_tea", "咲夜特製司康與紅茶", "🫖", "consumable",
     "完美女僕精心烘焙的司康餅，搭配溫熱濃郁的伯爵紅茶。優雅地享用完後，全身的疲勞彷彿被時間停止般一掃而空。",
     {"stamina": 120}),
    ("marisa_mushroom_soup", "螢光蘑菇濃湯", "🍄", "consumable",
     "採集自魔法森林深處的未知蘑菇熬煮而成。雖然湯汁呈現可疑的七彩螢光且偶爾會冒泡，但喝下去意外地能讓人精神百倍！",
     {"stamina": 67}),
    ("reimu_onigiri", "陰陽梅干飯糰", "🍙", "consumable",
     "用海苔包著酸梅的簡單飯糰，海苔上還貼心地剪出了陰陽玉的圖案。雖然樸素，卻能快速補充退治妖怪所需的體力。",
     {"stamina": 60}),
]


def _parse_effect(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


async def init_item_db():
    """初始化 Item.db 資料表 (缺少 effect 欄位會自動補上)，若為空則寫入預設資料"""
    if not os.path.exists(DB_PATH):
        print("⚠️ [ItemDB] 找不到 Database/Item.db，將建立新的並只寫入預設道具！")
        print("⚠️ [ItemDB] 若你是在搬移資料夾，請確認原本的 item.db 已放到 Database/ 並改名為 Item.db。")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS item_templates (
                item_id TEXT PRIMARY KEY,
                name TEXT,
                emoji TEXT,
                category TEXT,
                description TEXT,
                effect TEXT DEFAULT '{}'
            )
        """)
        async with db.execute("PRAGMA table_info(item_templates)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
        if "effect" not in columns:
            await db.execute("ALTER TABLE item_templates ADD COLUMN effect TEXT DEFAULT '{}'")
            print("🔧 [ItemDB] 已自動為 item_templates 補上 `effect` 欄位！")

        # 檢查是否為空
        async with db.execute("SELECT COUNT(*) FROM item_templates") as cursor:
            count = await cursor.fetchone()
            if count[0] == 0:
                await db.executemany(
                    "INSERT INTO item_templates (item_id, name, emoji, category, description, effect) VALUES (?, ?, ?, ?, ?, ?)",
                    [(i, n, e, c, d, json.dumps(fx, ensure_ascii=False)) for i, n, e, c, d, fx in DEFAULT_ITEMS]
                )
        await db.commit()

async def get_all_items() -> dict:
    """
    從資料庫讀取所有道具範本，轉換為字典回傳
    回傳格式: {"item_id": {"name": "...", "emoji": "...", "category": "...", "desc": "...", "effect": {...}}}
    """
    await init_item_db()
    items = {}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT item_id, name, emoji, category, description, effect FROM item_templates") as cursor:
            async for row in cursor:
                items[row[0]] = {
                    "name": row[1],
                    "emoji": row[2],
                    "category": row[3],
                    "desc": row[4],
                    "effect": _parse_effect(row[5]),
                }
    return items

async def get_item(item_id: str) -> dict | None:
    """查詢單一道具"""
    await init_item_db()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name, emoji, category, description, effect FROM item_templates WHERE item_id = ?", (item_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"item_id": item_id, "name": row[0], "emoji": row[1], "category": row[2], "desc": row[3],
                        "effect": _parse_effect(row[4])}
    return None

async def add_item_db(item_id: str, name: str, emoji: str, category: str, desc: str, effect: dict | None = None) -> bool:
    """新增單一道具 (若 ID 已存在則回傳 False)"""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO item_templates (item_id, name, emoji, category, description, effect) VALUES (?, ?, ?, ?, ?, ?)",
                (item_id, name, emoji, category, desc, json.dumps(effect or {}, ensure_ascii=False))
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False  # ID 已存在

async def update_item_db(item_id: str, name: str, emoji: str, category: str, desc: str):
    """更新道具資料 (效果不變)"""
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

async def replace_all_items(items: list[tuple]):
    """清空所有道具範本並換成 items (格式同 DEFAULT_ITEMS)；同一個交易"""
    await init_item_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await db.execute("DELETE FROM item_templates")
            await db.executemany(
                "INSERT INTO item_templates (item_id, name, emoji, category, description, effect) VALUES (?, ?, ?, ?, ?, ?)",
                [(i, n, e, c, d, json.dumps(fx, ensure_ascii=False)) for i, n, e, c, d, fx in items]
            )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise

async def batch_import_db(items_dict: dict, overwrite: bool) -> tuple[int, int]:
    """
    批量匯入 JSON 道具 (回傳: 成功數, 跳過數)
    範例 JSON 格式 (effect 可省略)：
    {
        "reimu_onigiri": {
            "name": "陰陽梅干飯糰",
            "emoji": "🍙",
            "category": "consumable",
            "desc": "用海苔包著酸梅的簡單飯糰……",
            "effect": {"stamina": 60}
        }
    }
    """
    success, skipped = 0, 0
    await init_item_db()
    async with aiosqlite.connect(DB_PATH) as db:
        for item_id, data in items_dict.items():
            row = (
                item_id,
                data.get("name", "未命名"),
                data.get("emoji", "❓"),
                data.get("category", "special"),
                data.get("desc", "無描述"),
                json.dumps(data.get("effect") or {}, ensure_ascii=False),
            )
            if overwrite:
                await db.execute(
                    "INSERT OR REPLACE INTO item_templates (item_id, name, emoji, category, description, effect) VALUES (?, ?, ?, ?, ?, ?)",
                    row
                )
                success += 1
            else:
                try:
                    await db.execute(
                        "INSERT INTO item_templates (item_id, name, emoji, category, description, effect) VALUES (?, ?, ?, ?, ?, ?)",
                        row
                    )
                    success += 1
                except aiosqlite.IntegrityError:
                    skipped += 1
        await db.commit()
    return success, skipped

"""
🎒 道具範本資料庫管理 (Database/Item.db)

只負責「道具長什麼樣子」(名稱 / 圖示 / 分類 / 說明 / 效果)。
玩家背包裡有哪些道具、各幾件，存在 Users.db：請見 User_DB_Manager.py

effect 是 JSON 字串，目前支援：
  {"stamina": 120}   使用後回復 120 體力 (可超過自然回復上限 240)
  {"serve": "food"}  招待參拜客用的料理，種類 food 食物 / drink 茶水 / dessert 點心 (SERVE_TYPES)
  {"material": true} 料理用的素材 (category = material)
  {"event": "<活動 ID>"} 活動限定道具，活動結束時會從所有玩家的倉庫清除

素材、新料理、活動道具由 Database/shrine_data.py 與 Events/*.json 定義，開機時缺少的會自動補進來 (managed_items)
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
    "special": "🛠️ 裝備與特殊",
    "cuisine": "🍱 招待料理",
    "material": "🧺 素材",
}

# 招待料理的種類 (effect.serve)：每位參拜客至少要 1 份，最多 3 種共 5 份
SERVE_TYPES = {"food": "🍚 食物", "drink": "🍵 茶水", "dessert": "🍮 點心"}

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
    # ---- 🍱 招待料理 (v0.26.000，招待參拜客用；取得方式之後跟素材副本一起做) ----
    ("mystia_lamprey", "夜雀烤八目鰻", "🍢", "cuisine",
     "米斯蒂婭屋台的招牌，炭火烤得焦香油亮的八目鰻。據說吃了夜盲症就會好，妖怪客人一聞到香味就會不自覺地湊過來。",
     {"serve": "food"}),
    ("ran_inari", "八雲特製豆皮壽司", "🍣", "cuisine",
     "油豆腐炸得金黃再浸滿甜鹹醬汁，裡面塞著醋飯。九尾狐式神的拿手料理，只要端出來，狐狸系的客人心情一定會變好。",
     {"serve": "food"}),
    ("nitori_cucumber", "河童冰鎮小黃瓜", "🥒", "cuisine",
     "在玄武之澤的冷泉裡冰得清脆的小黃瓜，沾上一點味噌。河童們最愛的零嘴，簡單卻讓人一根接一根停不下來。",
     {"serve": "food"}),
    ("reimu_bancha", "博麗神社粗茶", "🍵", "cuisine",
     "博麗神社招待客人的標準茶水，茶葉已經回沖了好幾次，顏色淡得有點可疑。不過巫女說，心意才是最重要的。",
     {"serve": "drink"}),
    ("eirin_herbal_tea", "永遠亭藥草茶", "🌿", "cuisine",
     "月之頭腦親手調配的藥草茶，入口微苦、後韻回甘，據說能調理妖怪紊亂的靈力。只是喝完偶爾會看到兔子在眼前晃來晃去。",
     {"serve": "drink"}),
    ("suika_amazake", "伊吹甘酒", "🍶", "cuisine",
     "從鬼之瓢裡倒出來的米麴甘酒，甜而不醉（大概）。鬼族豪爽的招待方式，連天狗都會賞臉多喝兩杯。",
     {"serve": "drink"}),
    ("eientei_tsukimi_dango", "月見糰子", "🌕", "cuisine",
     "永遠亭的月兔們用杵臼一下一下搗出來的糰子，堆成小山供在月下。軟糯滑口，咬下去彷彿嚐到了月亮的味道。",
     {"serve": "dessert"}),
    ("cirno_kakigori", "琪露諾特製刨冰", "🍧", "cuisine",
     "最強的冰精用冰符現場削出來的刨冰，淋上滿滿的草莓糖漿。「這是永遠不會融化的冰！」——至少本人是這麼宣稱的。",
     {"serve": "dessert"}),
    ("alice_cookie", "人偶師的手工餅乾", "🍪", "cuisine",
     "七色的人偶師一邊操縱上海人偶、一邊精準烘焙的奶油餅乾，每一片的形狀和烤色都完美一致。配上茶水剛剛好。",
     {"serve": "dessert"}),
]


def managed_items() -> list[tuple]:
    """遊戲資料裡定義的道具 (素材、新料理、活動道具)，格式同 DEFAULT_ITEMS"""
    from Database import shrine_data
    from Database.events import load_events
    items = [(i, n, e, "material", d, {"material": True}) for i, n, e, d in shrine_data.MATERIAL_ITEMS]
    items += [(i, n, e, "cuisine", d, {"serve": t}) for i, n, e, t, d in shrine_data.DISH_ITEMS]
    for ev in load_events().values():
        for it in ev.get("items", []):
            effect = dict(it.get("effect") or {})
            if it.get("category") == "material":
                effect["material"] = True
            effect["event"] = ev["id"]
            items.append((it["id"], it["name"], it["emoji"], it["category"], it["desc"], effect))
    return items


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
        # 遊戲資料定義的素材 / 料理 / 活動道具：缺少的補上 (已存在的不覆蓋，管理員改過的名稱會保留)
        await db.executemany(
            "INSERT OR IGNORE INTO item_templates (item_id, name, emoji, category, description, effect) VALUES (?, ?, ?, ?, ?, ?)",
            [(i, n, e, c, d, json.dumps(fx, ensure_ascii=False)) for i, n, e, c, d, fx in managed_items()]
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

"""
💹 經濟系統共用：神社經營的數值常數 (原本 Economy_DB_Manager.py 開頭那段)、時間 / 倍率 / economy_meta 小工具

從 Database/Economy_DB_Manager.py 拆出來的；外面一律照舊從 Database.Economy_DB_Manager 匯入 (入口)，不要直接匯入這裡。
"""
from datetime import datetime, timedelta


HOUR = timedelta(hours=1)

# ---------------------------------------------------------
# ⛩️ 神社經營的數值
# ---------------------------------------------------------
SHRINE_INCOME_PER_HOUR = 5000          # 效率 100% 時每小時進賽錢箱的錢
SHRINE_BOX_MAX = 200_000               # 賽錢箱上限，滿了就不再累積 (要用指令回收)

DIRT_INTERVAL = timedelta(hours=4)     # 每 4 小時髒一階
DIRT_MAX = 4                           # 乾淨 0 ➔ 最髒 4 (5 個階段)
DIRT_PENALTY = 0.10                    # 每階 −10% (最多 −40%)

YOUKAI_MAX = 5
YOUKAI_SPAWN = [0.80, 0.70, 0.55, 0.35, 0.10]   # 每小時生成機率：目前 0 隻時 80%、1 隻時 70%…
YOUKAI_PENALTY = 0.08                  # 每隻 −8% (最多 −40%)
YOUKAI_REWARD = (800, 1500)            # 打退一隻的賽錢 (隨機，含頭尾；v0.27.004 從固定 1000 改)；打退後留下晦氣 ➔ 清潔度掉一階

GUEST_EVERY_HOURS = 2                  # 每 2 小時判定一次參拜客
GUEST_MAX = 5
GUEST_SPAWN = [0.90, 0.80, 0.70, 0.60, 0.50]    # 目前 0 位時 90%、1 位時 80%…
MOOD_STEP = 10                         # 心情 10% 一個區間
MOOD_INTERVAL = timedelta(hours=4)     # 每 4 小時掉一個區間，掉到 0 就離開
SERVING_REWARD = 2000                  # 每「份」餐點：2000 × 心情² (不保底；v0.27.000 從 1000 調成 2000)
ORDER_SIZE = (1, 3)                    # 每位客人點 1~3 道 (不同種類)，點的每道都要給 1 份
FAVORITE_BONUS = 1.5                   # 額外招待 (可選 1 份) 正中客人最愛 ➔ 整筆 ×1.5
SERVE_TYPES_ORDER = ("food", "drink", "dessert")

SHRINE_MAX_CATCHUP = timedelta(days=14)   # 太久沒來時只模擬最後 14 天 (那時賽錢箱早就滿了)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def modifier(rules: dict, key: str) -> float:
    """活動的數值倍率預留位 (events.MODIFIER_KEYS)；沒有活動設定 = 1"""
    return (rules or {}).get("modifiers", {}).get(key, 1.0)


async def _get_meta(db, key: str):
    async with db.execute("SELECT value FROM economy_meta WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
    return row["value"] if row else None


async def _set_meta(db, key: str, value: str):
    await db.execute("INSERT INTO economy_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

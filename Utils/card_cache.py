"""
🗂️ 卡冊快取 (只給 autocomplete 用)

autocomplete 打一個字就會呼叫一次，每次都讀整本卡冊會慢 ➔ 每位玩家的卡冊快取 CARD_CACHE_TTL 秒。
規則：
- 只有 autocomplete 可以用 cached_user_cards()；真正執行指令 (合成、融合、分解、上架…) 一律直接讀資料庫，
  不能拿快取的結果做寫入判斷
- 資料層會改到 gacha_cards 的函式，在 commit 成功後呼叫 invalidate(user_id) (買賣 / 退回要讓雙方都失效)
- 這個模組不能 import Cogs (避免循環匯入)；Database 也只在函式裡才匯入 (User_DB_Manager 會匯入這裡)
- 重載 (importlib.reload) 後快取清空，沒關係
"""
import time

CARD_CACHE_TTL = 30          # 秒；卡冊有變動時資料層會主動讓快取失效，TTL 只是保險

_cache: dict[int, tuple[str, float, list[dict]]] = {}   # user_id ➔ (資料庫路徑, 到期時間, 卡牌)
_generation: dict[int, int] = {}                        # user_id ➔ 失效次數 (讀取途中卡冊變了就不寫入快取)
_epoch = 0                                              # invalidate_all 的次數


def _now() -> float:
    return time.monotonic()


def invalidate(*user_ids: int | None):
    """讓指定玩家的快取失效 (None 會被忽略)"""
    for uid in user_ids:
        if uid is None:
            continue
        _cache.pop(uid, None)
        _generation[uid] = _generation.get(uid, 0) + 1


def invalidate_all():
    """全部清空 (例如測試或大量變動時)"""
    global _epoch
    _epoch += 1
    _cache.clear()


def _version(user_id: int) -> tuple[int, int]:
    return _epoch, _generation.get(user_id, 0)


async def cached_user_cards(user_id: int) -> list[dict]:
    """
    autocomplete 專用：取得玩家卡冊 (TTL 內直接回傳快取)。
    回傳複本，呼叫端改了也不會弄髒快取。
    """
    from Database import User_DB_Manager as udm   # 函式內匯入：User_DB_Manager 也會匯入這個模組
    db_path = udm.DB_PATH
    hit = _cache.get(user_id)
    if hit and hit[0] == db_path and hit[1] > _now():
        return [dict(c) for c in hit[2]]

    version = _version(user_id)
    cards = await udm.get_user_cards(user_id)
    if _version(user_id) == version:   # 讀取途中卡冊沒有變動才寫入快取
        _cache[user_id] = (db_path, _now() + CARD_CACHE_TTL, [dict(c) for c in cards])
    return cards

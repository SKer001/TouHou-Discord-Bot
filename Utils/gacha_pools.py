"""
🎰 卡池定義與卡池成員 (抽卡 Cog 與稱號 (卡池收集) 共用，所以放在 Utils 不放在 Cog 裡)
"""
import time

from Utils.character_data import load_categories

# 🎰 卡池依代數劃分：每個卡池包含哪些 Characters/ 分類資料夾
#    新增卡池 ➔ 在這裡加一筆，並把角色檔放進對應資料夾即可
#    (卡池收集稱號是一個卡池兩個，新卡池要在 Database/title_data.py 補稱號)
GACHA_POOLS = {
    "classic": {"name": "📜 舊作卡池", "desc": "主要主角 + TH01 ~ TH05", "folders": ["Main", "TH01", "TH02", "TH03", "TH04", "TH05"]},
    "th06":    {"name": "🔴 紅魔鄉卡池", "desc": "TH06 東方紅魔鄉", "folders": ["TH06"]},
}


def load_gacha_pool() -> dict:
    """
    從 Characters/ 讀取 gacha.enabled 的角色：
    {"角色id": {"name", "emoji", "uuid", "rarities", "titles", "pool"}, ...}
    """
    folder_to_pool = {folder: key for key, pool in GACHA_POOLS.items() for folder in pool["folders"]}
    result = {}
    for folder, category in load_categories().items():
        pool_key = folder_to_pool.get(folder)
        for char in category["characters"]:
            gacha = char["gacha"]
            if pool_key is None or not gacha.get("enabled"):
                continue
            result[char["id"]] = {
                "name": char["name"],
                "emoji": char["emoji"],
                "uuid": gacha["uuid"],
                "rarities": gacha["rarities"],
                "titles": gacha["titles"],
                "pool": pool_key,
                "profile_title": char.get("profile", {}).get("title", ""),   # 角色稱號 (推角稱號的說明用)
            }
    return result


_MEMBERS_TTL = 60   # 秒 (稱號每次看資料卡、每 10 分鐘的通知都會用到，不要每次都讀角色檔)
_members, _members_at = None, 0.0


def pool_members() -> dict:
    """{卡池: {角色id: [階級, ...]}} (60 秒快取)"""
    global _members, _members_at
    if _members is None or time.monotonic() - _members_at > _MEMBERS_TTL:
        members = {key: {} for key in GACHA_POOLS}
        for cid, info in load_gacha_pool().items():
            members[info["pool"]][cid] = list(info["rarities"])
        _members, _members_at = members, time.monotonic()
    return _members


def collection_stats(owned: set) -> dict:
    """
    卡池收集稱號用的統計 (owned = 卡冊現在有的 {(角色id, 階級)})：
    pool_chars:<卡池> / pool_cards:<卡池> = 1 (角色到齊 / 全卡收集) 或 0；all_cards = 所有卡池都全卡收集
    """
    chars = {c for c, _ in owned}
    stats = {}
    for key, members in pool_members().items():
        stats[f"pool_chars:{key}"] = int(bool(members) and all(c in chars for c in members))
        stats[f"pool_cards:{key}"] = int(bool(members) and all((c, r) in owned for c, rs in members.items() for r in rs))
    stats["all_cards"] = int(all(stats[f"pool_cards:{key}"] for key in GACHA_POOLS))
    return stats


def oshi_stats(counts: dict) -> dict:
    """推角稱號用的統計 (counts = 卡冊現在每位角色幾張 {角色id: 張數}，階級不限)：oshi:<卡池>:<角色id> = 張數"""
    return {f"oshi:{pool}:{cid}": counts.get(cid, 0) for pool, members in pool_members().items() for cid in members}

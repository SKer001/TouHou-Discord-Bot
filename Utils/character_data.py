"""
📚 角色資料載入器 (Characters/)

資料夾結構：Characters/<分類資料夾>/<角色id>.json
  - Main/   ：主要主角
  - THxx/   ：各代作品登場的角色 (TH01、TH02 ...)

每個角色檔的格式請見任一角色檔 (例如 Characters/Main/reimu.json)。
格式不符的檔案會印出警告並略過，不會讓整個圖鑑掛掉。
"""
import os
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARACTERS_DIR = os.path.join(PROJECT_ROOT, "Characters")

# 分類資料夾的顯示名稱與說明；沒列在這裡的資料夾直接用資料夾名稱
CATEGORY_INFO = {
    "Main": ("⭐ 主要主角", "東方 Project 歷代的核心主角"),
    "TH01": ("📜 東方靈異傳 (TH01)", "Highly Responsive to Prayers"),
    "TH02": ("📜 東方封魔錄 (TH02)", "Story of Eastern Wonderland"),
    "TH03": ("📜 東方夢時空 (TH03)", "Phantasmagoria of Dim.Dream"),
    "TH04": ("📜 東方幻想鄉 (TH04)", "Lotus Land Story"),
    "TH05": ("📜 東方怪綺談 (TH05)", "Mystic Square"),
    "TH06": ("🔴 東方紅魔鄉 (TH06)", "the Embodiment of Scarlet Devil"),
}

REQUIRED_KEYS = ("id", "name", "emoji", "category", "profile", "gacha", "base_stats", "special_powers")


def _category_sort_key(folder: str):
    """Main 永遠排第一，其餘依資料夾名稱 (TH01, TH02, ...)"""
    return (folder != "Main", folder)


def _validate(data: dict, path: str) -> str | None:
    """回傳錯誤訊息；沒問題回傳 None"""
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        return f"缺少欄位 {missing}"
    if os.path.splitext(os.path.basename(path))[0] != data["id"]:
        return f"檔名與 id `{data['id']}` 不一致"
    levels = data["special_powers"].get("levels", {})
    rarities = data["gacha"].get("rarities", [])
    if list(levels) != rarities:
        return f"special_powers.levels {list(levels)} 與 gacha.rarities {rarities} 不一致"
    return None


def load_categories() -> dict:
    """
    讀取 Characters/ 底下所有角色，依分類資料夾分組：
    {"Main": {"category_name": ..., "description": ..., "characters": [角色, ...]}, ...}
    分類內的角色依 id 排序；空分類不列出。
    """
    categories = {}
    if not os.path.isdir(CHARACTERS_DIR):
        print(f"❌ [Character Error] 找不到角色資料夾：{CHARACTERS_DIR}")
        return categories

    for folder in sorted(os.listdir(CHARACTERS_DIR), key=_category_sort_key):
        folder_path = os.path.join(CHARACTERS_DIR, folder)
        if not os.path.isdir(folder_path):
            continue

        characters = []
        for filename in sorted(os.listdir(folder_path)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(folder_path, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                print(f"⚠️ [Character] 讀取 {folder}/{filename} 失敗，已略過：{e}")
                continue
            error = _validate(data, path)
            if error:
                print(f"⚠️ [Character] {folder}/{filename} 格式錯誤，已略過：{error}")
                continue
            characters.append(data)

        if characters:
            name, desc = CATEGORY_INFO.get(folder, (f"📁 {folder}", ""))
            categories[folder] = {"category_name": name, "description": desc, "characters": characters}

    return categories


def load_characters() -> dict:
    """{"角色id": 角色資料, ...}，不分分類"""
    return {c["id"]: c for cat in load_categories().values() for c in cat["characters"]}


# ---------------------------------------------------------
# 🎴 卡牌顯示用的名稱 / 稱號 (2026-11-13)
# 資料庫的卡牌 (gacha_cards、market_listings) 存有寫入當下的 name / emoji / title 副本，
# 角色改名或改稱號後舊卡不會跟著變 ➔ 讀卡時一律用目前的角色檔覆蓋；角色檔不存在 (已刪除) 才保留副本
# ---------------------------------------------------------
import time

_CARD_INFO_TTL = 60          # 秒；角色檔改了最多 60 秒後生效 (/admin-sys reload 會直接重載本模組)
_card_info: dict | None = None
_card_info_at = 0.0


def _card_info_map() -> dict:
    global _card_info, _card_info_at
    if _card_info is None or time.monotonic() - _card_info_at > _CARD_INFO_TTL:
        _card_info = {cid: (c["name"], c["emoji"], c["gacha"].get("titles", {})) for cid, c in load_characters().items()}
        _card_info_at = time.monotonic()
    return _card_info


def clear_card_info_cache():
    """角色檔改完想立刻生效 (測試也會用)"""
    global _card_info
    _card_info = None


def apply_current_names(cards):
    """把卡牌 (dict 或 dict 的清單) 的 name / emoji / title 換成目前角色檔的內容，原地修改並回傳同一個物件"""
    info = _card_info_map()
    for card in ([cards] if isinstance(cards, dict) else cards):
        cur = info.get(card.get("character_key"))
        if cur is None:
            continue
        name, emoji, titles = cur
        card["name"], card["emoji"] = name, emoji
        if card.get("rarity") in titles:
            card["title"] = titles[card["rarity"]]
    return cards

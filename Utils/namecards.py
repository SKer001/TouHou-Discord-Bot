"""
🖼️ 角色名片的圖片網址：讀 images/Namecards.json ({角色id: 網址?v=雜湊})，由 tools/card_art/build_namecards.py 產生
- 沒有檔案、檔案壞掉、沒有那位角色 ➔ None (資料卡就不放圖)
- 每次都重讀 (檔案很小)，換圖後不用 reload
"""
import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMECARDS_FILE = os.path.join(PROJECT_ROOT, "images", "Namecards.json")


def load_namecard_urls() -> dict:
    try:
        with open(NAMECARDS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def namecard_url(character_key: str | None) -> str | None:
    """那位角色名片的顯示用圖片網址；沒有就回傳 None"""
    if not character_key:
        return None
    url = load_namecard_urls().get(character_key)
    return url if isinstance(url, str) and url else None

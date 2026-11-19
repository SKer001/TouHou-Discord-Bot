"""
🖼️ images/Thumbnails.json 的共用讀取 (0.35.034 起；/help 先用，其他 Cog 之後可以改成用這裡)
格式：{"角色id_階級": URL, "角色id": URL, ..., "fill": 預設圖 URL}
查圖順序：角色id_階級 ➔ 角色id ➔ "fill"；連 fill 都沒有就回傳 None (畫面只顯示文字)
"""
import json
import os

THUMBNAILS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images", "Thumbnails.json")


def load_thumbnails() -> dict:
    """讀取失敗時回傳空字典 (不讓畫面壞掉)"""
    try:
        with open(THUMBNAILS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ [Thumbnails] 讀取 {THUMBNAILS_FILE} 失敗：{e}")
        return {}


def thumbnail_url(key: str | None, thumbnails: dict | None, rarity: str | None = None) -> str | None:
    if not thumbnails:
        return None
    return (thumbnails.get(f"{key}_{rarity}") if key and rarity else None) or (thumbnails.get(key) if key else None) \
        or thumbnails.get("fill")

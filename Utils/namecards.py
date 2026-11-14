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


# ---------------------------------------------------------
# 📥 名片原圖 (2026-11-14 使用者決定)：repo 是公開的，原圖不放 repo，
#    而是由 tools/card_art/upload_namecard.py 上傳到只有機器人看得到的私人頻道 (.env 的 NAMECARD_CHANNEL_ID)，
#    訊息 id 記在 images/NamecardOriginals.json：{角色id: {"message_id": int, "jpg": 檔名, "full": 檔名或 null}}
#    - jpg：原尺寸高畫質 JPG (玩家按「📥 下載名片原圖」拿到的)
#    - full：PNG (或太大時改無損 WebP)，管理員用 /admin-user namecard 的「📥 原檔」私訊自己
# ---------------------------------------------------------
ORIGINALS_FILE = os.path.join(PROJECT_ROOT, "images", "NamecardOriginals.json")


def namecard_channel_id() -> int | None:
    from Utils import config   # noqa: F401  匯入時會 load_dotenv()，確保讀得到 .env
    raw = (os.getenv("NAMECARD_CHANNEL_ID") or "").strip()
    return int(raw) if raw.isdigit() else None


def load_originals() -> dict:
    try:
        with open(ORIGINALS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def namecard_original(character_key: str | None) -> dict | None:
    """那位角色名片原圖的紀錄 {"message_id", "jpg", "full"}；沒上傳過就回傳 None"""
    if not character_key:
        return None
    entry = load_originals().get(character_key)
    if not isinstance(entry, dict) or not entry.get("message_id") or not entry.get("jpg"):
        return None
    return entry


async def fetch_original_file(client, character_key: str, kind: str = "jpg"):
    """
    從私人頻道抓原圖，回傳 discord.File (可以直接私訊出去)；抓不到回傳 None
    kind = "jpg" (高畫質 JPG) / "full" (PNG 或無損 WebP；沒有就退回 jpg)
    """
    entry = namecard_original(character_key)
    channel_id = namecard_channel_id()
    if entry is None or channel_id is None:
        return None
    filename = (entry.get("full") or entry["jpg"]) if kind == "full" else entry["jpg"]
    try:
        channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
        message = await channel.fetch_message(int(entry["message_id"]))
    except Exception as e:   # 頻道 / 訊息被刪、權限不夠
        print(f"⚠️ [Namecard] 抓不到 {character_key} 的名片原圖：{e!r}")
        return None
    attachment = next((a for a in message.attachments if a.filename == filename), None)
    if attachment is None:
        print(f"⚠️ [Namecard] 訊息裡沒有 {filename}")
        return None
    return await attachment.to_file()

"""
⚙️ 共用設定 (從 .env 讀取)

.env 需要：
  ADMIN_IDS=403895664666214400            # 管理員的 Discord 使用者 ID，多位用逗號分隔
  SHOW_UNRELEASED=1                       # (選填) 開發用：看得到還沒公開的卡池 (Utils/gacha_pools.py 裡 "released": False 的)；正式機器人不要設
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _parse_ids(raw: str | None) -> frozenset[int]:
    ids = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return frozenset(ids)


ADMIN_IDS = _parse_ids(os.getenv("ADMIN_IDS"))
if not ADMIN_IDS:
    print("⚠️ [Config] .env 沒有設定 ADMIN_IDS，所有管理員指令都將無法使用")


def _parse_flag(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


# 🙈 未公開卡池開關：沒開 (預設) 時，Utils/gacha_pools.py 裡 "released": False 的卡池整個當作不存在
#    (圖鑑、卡池、稱號、名片選單、裏世界都看不到它的角色)；開發時在 .env 寫 SHOW_UNRELEASED=1
#    測試 (tests/) 與 tools/botcli.py 自己會預設打開
SHOW_UNRELEASED = _parse_flag(os.getenv("SHOW_UNRELEASED"))


def is_admin(user) -> bool:
    """user 可以是 discord.User / Member 或使用者 ID"""
    return getattr(user, "id", user) in ADMIN_IDS

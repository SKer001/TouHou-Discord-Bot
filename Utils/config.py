"""
⚙️ 共用設定 (從 .env 讀取)

.env 需要：
  ADMIN_IDS=403895664666214400            # 管理員的 Discord 使用者 ID，多位用逗號分隔
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


def is_admin(user) -> bool:
    """user 可以是 discord.User / Member 或使用者 ID"""
    return getattr(user, "id", user) in ADMIN_IDS

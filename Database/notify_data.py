"""
🔔 主動通知的種類登記表 (純資料，不碰資料庫)

NOTIFY_TYPES = {種類 key: {name, emoji, desc, dm}}
- dm = 這種通知能不能私訊。目前全部 True。
  之後會有 dm=False 的種類 (例如特定關卡)：那種永遠不發 DM，/notify 面板顯示「不支援私訊」、不能切換。
- 新增種類：在這裡加一筆，再到 Cogs/load-general/notify.py 的判斷函式與
  Cogs/load-general/Components/notify_components.py 的 NOTICE_TEXT 各補一段。
- desc 裡的數字 (賽錢箱上限、妖怪上限、上架天數、活動任務提醒) 從常數組字 (2026-11-23：原本寫死)；/notify 面板和教學書都讀這裡
"""
from Database.Economy_DB_Manager import SHRINE_BOX_MAX, YOUKAI_MAX, LISTING_DURATION
from Database.Quest_DB_Manager import REMIND_WINDOW

NOTIFY_TYPES = {
    "shrine_box_full": {"name": "賽錢箱滿了", "emoji": "💰", "dm": True,
                        "desc": f"神社的賽錢箱存滿 {SHRINE_BOX_MAX:,}，不回收就不會再累積"},
    "guest_leaving":   {"name": "參拜客快離開", "emoji": "🚶", "dm": True,
                        "desc": "有參拜客再過不久就要離開了 (每位客人只通知一次)"},
    "youkai_max":      {"name": f"妖怪滿 {YOUKAI_MAX} 隻", "emoji": "👹", "dm": True,
                        "desc": "神社的妖怪滿了，效率被壓得很低"},
    "stamina_full":    {"name": "體力回滿", "emoji": "⚡", "dm": True,
                        "desc": "花掉的體力自然回復到上限 (沒花過就不通知)"},
    "market_sold":     {"name": "上架的卡賣出了", "emoji": "💹", "dm": True,
                        "desc": "你在市場上架的卡被其他玩家買走"},
    "market_expired":  {"name": "上架到期退回", "emoji": "📦", "dm": True,
                        "desc": f"上架 {LISTING_DURATION.days} 天沒賣出，卡退回你的卡冊"},
    "event_start":     {"name": "活動開始", "emoji": "🎪", "dm": True,
                        "desc": "新的活動開始了 (只通知有神社的玩家)"},
    "event_end":       {"name": "活動結束", "emoji": "🏁", "dm": True,
                        "desc": "活動結束了，活動道具已清除 (只通知有神社的玩家)"},
    "title_unlocked":  {"name": "獲得新稱號", "emoji": "🏷️", "dm": True,
                        "desc": "解鎖了新的稱號，可以到 /profile 戴上"},
    "event_quest_reminder": {"name": "活動任務快結束", "emoji": "⏰", "dm": True,
                             "desc": f"活動結束前 {int(REMIND_WINDOW.total_seconds() // 3600)} 小時內，還有完成但沒領的任務 (每次活動提醒一次)"},
}


def can_dm(kind: str) -> bool:
    """這種通知能不能私訊 (不認識的種類一律不發)"""
    return bool(NOTIFY_TYPES.get(kind, {}).get("dm"))

"""
🔔 主動通知的種類登記表 (純資料，不碰資料庫)

NOTIFY_TYPES = {種類 key: {name, emoji, desc, dm}}
- dm = 這種通知能不能私訊。目前全部 True。
  之後會有 dm=False 的種類 (例如特定關卡)：那種永遠不發 DM，/notify 面板顯示「不支援私訊」、不能切換。
- 新增種類：在這裡加一筆，再到 Cogs/load-general/notify.py 的判斷函式與
  Cogs/load-general/Components/notify_components.py 的 NOTICE_TEXT 各補一段。
"""

NOTIFY_TYPES = {
    "shrine_box_full": {"name": "賽錢箱滿了", "emoji": "💰", "dm": True,
                        "desc": "神社的賽錢箱存滿 200,000，不回收就不會再累積"},
    "guest_leaving":   {"name": "參拜客快離開", "emoji": "🚶", "dm": True,
                        "desc": "有參拜客再過不久就要離開了 (每位客人只通知一次)"},
    "youkai_max":      {"name": "妖怪滿 5 隻", "emoji": "👹", "dm": True,
                        "desc": "神社的妖怪滿了，效率被壓得很低"},
    "stamina_full":    {"name": "體力回滿", "emoji": "⚡", "dm": True,
                        "desc": "花掉的體力自然回復到上限 (沒花過就不通知)"},
    "market_sold":     {"name": "上架的卡賣出了", "emoji": "💹", "dm": True,
                        "desc": "你在市場上架的卡被其他玩家買走"},
    "market_expired":  {"name": "上架到期退回", "emoji": "📦", "dm": True,
                        "desc": "上架 7 天沒賣出，卡退回你的卡冊"},
    "event_start":     {"name": "活動開始", "emoji": "🎪", "dm": True,
                        "desc": "新的活動開始了 (只通知有神社的玩家)"},
    "event_end":       {"name": "活動結束", "emoji": "🏁", "dm": True,
                        "desc": "活動結束了，活動道具已清除 (只通知有神社的玩家)"},
    "title_unlocked":  {"name": "獲得新稱號", "emoji": "🏷️", "dm": True,
                        "desc": "解鎖了新的稱號，可以到 /profile 戴上"},
}


def can_dm(kind: str) -> bool:
    """這種通知能不能私訊 (不認識的種類一律不發)"""
    return bool(NOTIFY_TYPES.get(kind, {}).get("dm"))

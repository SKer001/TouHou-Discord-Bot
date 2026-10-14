# Utils/item_data.py

CATEGORY_NAMES = {
    "all": "🌸 全部道具",
    "consumable": "🍵 消耗品",
    "collectible": "🎴 收藏品",
    "special": "🛠️ 裝備與特殊"
}

# 道具主表：依據 英文ID 作為 Key
ITEM_DATABASE = {
    "apple": {"name": "幻想鄉蘋果", "emoji": "🍎", "category": "consumable", "desc": "普通的蘋果，吃起來脆脆的。"},
    "bomb": {"name": "靈擊符", "emoji": "💣", "category": "consumable", "desc": "緊急迴避用的符卡。"},
    "frog_coin": {"name": "守矢硬幣", "emoji": "🪙", "category": "collectible", "desc": "守矢神社發行的紀念幣。"},
    "hakurei_tea": {"name": "博麗神社的茶", "emoji": "🍵", "category": "consumable", "desc": "悠閒的下午茶，喝了能稍微回復精神。"},
    "kappa_water": {"name": "河童礦泉水", "emoji": "💧", "category": "consumable", "desc": "妖怪之山產出的純淨水。"},
    "mini_hakkero": {"name": "迷你八卦爐", "emoji": "🔥", "category": "special", "desc": "魔理沙的魔法道具，火力十足。"},
    "sake": {"name": "鬼殺酒", "emoji": "🍶", "category": "consumable", "desc": "伊吹萃香最愛的酒。"},
    "senbei": {"name": "仙貝", "emoji": "🍘", "category": "consumable", "desc": "普通的仙貝，配茶剛剛好。"},
    "spell_card_1": {"name": "夢想封印", "emoji": "🎴", "category": "collectible", "desc": "靈夢的招牌符卡。"},
    "spell_card_2": {"name": "大魔理沙", "emoji": "🎴", "category": "collectible", "desc": "魔理沙的招牌符卡。"},
    "tengu_camera": {"name": "天狗的相機", "emoji": "📷", "category": "special", "desc": "文文用來取材的相機。"},
    "yinyang_orb": {"name": "陰陽玉", "emoji": "☯️", "category": "collectible", "desc": "博麗神社的秘寶。"}
}

def get_item_info(item_id: str) -> dict:
    """根據道具 ID 取得道具詳細資訊，找不到則回傳預設值"""
    return ITEM_DATABASE.get(item_id, {
        "name": "未知道具", 
        "emoji": "❓", 
        "category": "special", 
        "desc": "未知的物品。"
    })
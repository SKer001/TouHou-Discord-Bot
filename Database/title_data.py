"""
🏷️ 玩家稱號 (純資料，不碰資料庫)：在 /profile 選一個戴上，顯示在名字下面

- 每個稱號：name 名稱、rarity 等級 (跟卡牌一樣 N～LR)、desc 說明 (顯示成灰色小斜體)、
  stat + min = 解鎖條件 (玩家統計 >= min 就解鎖，不另外存「已解鎖」名單)
- 等級決定 /profile 色條的顏色 (沿用圖鑑的階級色)；沒戴稱號 = Discord 品牌色
- 新增稱號：在 TITLES 加一筆即可；stat 要是 title_stats() (User_DB_Manager.get_title_stats) 有的鍵
- 稱號清單、名稱、門檻都是使用者決定的 (2026-11-13 開始，一組一組加)
"""

# 等級顏色 (0xRRGGBB)，跟 Cogs/load-character 圖鑑的 RARITY_COLORS 同一組
RARITY_COLORS = {
    "N": 0x979C9F,     # 淺灰
    "R": 0x2ECC71,     # 綠
    "SR": 0x3498DB,    # 藍
    "SSR": 0x9B59B6,   # 紫
    "UR": 0xF1C40F,    # 金
    "LR": 0xE74C3C,    # 紅
}
NO_TITLE_COLOR = 0x5865F2   # 沒戴稱號：Discord 品牌藍紫 (公開、私人資料卡一樣)

TITLES = {
    # 🎰 祈願 (累計抽數；2026-11-13 使用者選定)
    "draw_10": {"name": "初次祈願者", "rarity": "N", "stat": "total_draws", "min": 10,
                "desc": "第一次把賽錢投進博麗神社的賽錢箱。靈夢露出了難得的笑容。"},
    "draw_100": {"name": "虔誠的參拜者", "rarity": "R", "stat": "total_draws", "min": 100,
                 "desc": "每天都來祈願，神社的石階已經走得很熟了。"},
    "draw_500": {"name": "博麗神社的常客", "rarity": "SR", "stat": "total_draws", "min": 500,
                 "desc": "祈願次數多到賽錢箱都認得你的硬幣聲。"},
    "draw_1000": {"name": "神社的大施主", "rarity": "SSR", "stat": "total_draws", "min": 1000,
                  "desc": "捐了上千次賽錢，神社的修繕費有一半是你出的。"},
    "draw_2000": {"name": "賽錢箱的守護神", "rarity": "UR", "stat": "total_draws", "min": 2000,
                  "desc": "你的賽錢讓靈夢第一次吃飽了飯。在她心中，你的地位已經接近神明。"},
    "draw_5000": {"name": "幻想鄉第一信仰", "rarity": "LR", "stat": "total_draws", "min": 5000,
                  "desc": "信仰多到快要能自己開一間神社了，連守矢神社都在打聽你是誰。"},
}

RARITY_ORDER = {"N": 0, "R": 1, "SR": 2, "SSR": 3, "UR": 4, "LR": 5}


def unlocked_titles(stats: dict) -> list[str]:
    """依玩家統計列出已解鎖的稱號 id (等級高的在前，同等級照 TITLES 順序)"""
    ids = [tid for tid, t in TITLES.items() if stats.get(t["stat"], 0) >= t["min"]]
    return sorted(ids, key=lambda tid: -RARITY_ORDER[TITLES[tid]["rarity"]])


def title_label(tid: str) -> str:
    """「[UR] 賽錢箱的守護神」"""
    t = TITLES[tid]
    return f"[{t['rarity']}] {t['name']}"


def title_color(tid: str | None) -> int:
    return RARITY_COLORS[TITLES[tid]["rarity"]] if tid in TITLES else NO_TITLE_COLOR


def condition_text(tid: str) -> str:
    """解鎖條件的文字 (選單說明、之後的稱號一覽用)"""
    t = TITLES[tid]
    return {"total_draws": f"累計祈願 {t['min']:,} 抽"}.get(t["stat"], f"{t['stat']} ≥ {t['min']:,}")

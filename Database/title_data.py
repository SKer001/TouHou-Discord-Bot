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
    # 🔮 融合 (累計融合次數；2026-11-13 使用者選定 B 組，UR 門檻 500)
    "fusion_1": {"name": "見習鍊金術師", "rarity": "N", "stat": "total_fusions", "min": 1,
                 "desc": "從帕秋莉的圖書館偷偷借了一本入門書，開始研究融合。"},
    "fusion_10": {"name": "圖書館的常客", "rarity": "R", "stat": "total_fusions", "min": 10,
                  "desc": "每天都來大圖書館翻書，小惡魔已經記得你常坐的位子。"},
    "fusion_50": {"name": "七曜的弟子", "rarity": "SR", "stat": "total_fusions", "min": 50,
                  "desc": "連帕秋莉都抬起頭，承認你的融合功力了。"},
    "fusion_100": {"name": "魔法使的同好", "rarity": "SSR", "stat": "total_fusions", "min": 100,
                   "desc": "愛麗絲和魔理沙都跑來找你討論融合的心得。"},
    "fusion_500": {"name": "大圖書館的常駐研究員", "rarity": "UR", "stat": "total_fusions", "min": 500,
                   "desc": "帕秋莉幫你在大圖書館保留了一張專用的書桌。"},
    "fusion_1000": {"name": "七曜的魔女", "rarity": "LR", "stat": "total_fusions", "min": 1000,
                    "desc": "你的融合造詣已經不輸給帕秋莉本人，可以自稱魔女了。"},
    # ⚗️ 合成 (累計合成次數，0.31.002 起才開始記；2026-11-13 使用者選定 A 組)
    "synth_1": {"name": "初次合成", "rarity": "N", "stat": "total_synths", "min": 1,
                "desc": "把兩張卡疊在一起，發現它們變得更完整了。"},
    "synth_10": {"name": "修卡匠", "rarity": "R", "stat": "total_synths", "min": 10,
                 "desc": "卡角磨損、圖案褪色，交給你處理就對了。"},
    "synth_50": {"name": "精益求精", "rarity": "SR", "stat": "total_synths", "min": 50,
                 "desc": "一張卡要合成到滿意為止，絕不將就。"},
    "synth_100": {"name": "完美主義者", "rarity": "SSR", "stat": "total_synths", "min": 100,
                  "desc": "看到不完整的卡就渾身不對勁。"},
    "synth_500": {"name": "匠心獨具", "rarity": "UR", "stat": "total_synths", "min": 500,
                  "desc": "經你手合成的卡，連卡框的花紋都閃閃發亮。"},
    "synth_1000": {"name": "千錘百鍊", "rarity": "LR", "stat": "total_synths", "min": 1000,
                   "desc": "合成了上千次，你親手造就了無數張完美的卡。"},
    # 📅 簽到 (累積簽到天數，不用連續；2026-11-13 使用者選定 A 組)
    "daily_7": {"name": "三日坊主不再", "rarity": "N", "stat": "daily_count", "min": 7,
                "desc": "破天荒地參拜滿一個禮拜，靈夢有點驚訝。"},
    "daily_30": {"name": "每日參拜", "rarity": "R", "stat": "daily_count", "min": 30,
                 "desc": "一個月沒有缺席，參拜已經成了每天的習慣。"},
    "daily_60": {"name": "風雨無阻", "rarity": "SR", "stat": "daily_count", "min": 60,
                 "desc": "颳風下雨都照樣上山參拜，信仰非常堅定。"},
    "daily_100": {"name": "百日參拜", "rarity": "SSR", "stat": "daily_count", "min": 100,
                  "desc": "完成了百日參拜，聽說這樣願望一定會實現。"},
    "daily_200": {"name": "神社的一份子", "rarity": "UR", "stat": "daily_count", "min": 200,
                  "desc": "你來神社的日子，比靈夢打掃的日子還多。"},
    "daily_365": {"name": "四季的參拜者", "rarity": "LR", "stat": "daily_count", "min": 365,
                  "desc": "看過了神社的春櫻、夏祭、秋楓和冬雪，整整一年都沒有離開。"},
    # 🔥 連續簽到 (最長連續紀錄 best_streak，0.31.005 起才開始記；2026-11-13 使用者選三個都做)
    "streak_30": {"name": "一日不缺", "rarity": "SSR", "stat": "best_streak", "min": 30,
                  "desc": "整整一個月每天都來，靈夢開始擔心你是不是住在神社了。"},
    "streak_100": {"name": "百日不斷", "rarity": "UR", "stat": "best_streak", "min": 100,
                   "desc": "連續一百天沒有缺席，這份毅力連神明都動容。"},
    "streak_365": {"name": "永遠的參拜者", "rarity": "LR", "stat": "best_streak", "min": 365,
                   "desc": "一年三百六十五天從未間斷，你就是博麗神社的一部分。"},
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
    return {"total_draws": f"累計祈願 {t['min']:,} 抽",
            "total_fusions": f"累計融合 {t['min']:,} 次",
            "total_synths": f"累計合成 {t['min']:,} 次",
            "daily_count": f"累積簽到 {t['min']:,} 天",
            "best_streak": f"連續簽到 {t['min']:,} 天"}.get(t["stat"], f"{t['stat']} ≥ {t['min']:,}")

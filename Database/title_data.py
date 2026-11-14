"""
🏷️ 玩家稱號 (純資料，不碰資料庫)：在 /profile 選一個戴上，顯示在名字下面

- 每個稱號：name 名稱、rarity 等級 (跟卡牌一樣 N～LR)、desc 說明 (顯示成灰色小斜體)、
  stat + min = 解鎖條件 (玩家統計 >= min 就解鎖，不另外存「已解鎖」名單)；
  requires = 前一個稱號也要有才解鎖 (換統計的地方要寫，例如 LR 收藏要先有 10 種 UR)
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
    # 🌟 UR / LR 收藏 (卡冊裡「現在」有幾種角色的 UR / LR，賣掉就會失去；2026-11-13 使用者選 B)
    "ur_1": {"name": "金色的奇蹟", "rarity": "SR", "stat": "ur_kinds", "min": 1,
             "desc": "第一次把 UR 卡握在手裡，手還在發抖。"},
    "ur_5": {"name": "傳說收藏家", "rarity": "SSR", "stat": "ur_kinds", "min": 5,
             "desc": "五位角色的 UR 卡排在卡冊裡，金光刺眼。"},
    "ur_10": {"name": "黃金卡冊", "rarity": "UR", "stat": "ur_kinds", "min": 10,
              "desc": "卡冊裡的金色多到靈夢想跟你借錢。"},
    "lr_1": {"name": "觸及傳說之人", "rarity": "UR", "stat": "lr_kinds", "min": 1, "requires": "ur_10",
             "desc": "拿到了只存在於傳說中的卡，連紫都從隙間探頭看了一眼。"},
    "lr_3": {"name": "幻想的頂點", "rarity": "LR", "stat": "lr_kinds", "min": 3, "requires": "lr_1",
             "desc": "三張傳說都在你手上，幻想鄉已經沒有你沒見過的奇蹟。"},
    # 💎 完美卡 (卡冊「現在」有幾種完整度 1.0000 的卡，角色 + 階級一樣只算一種；2026-11-13 使用者選算種類)
    "perfect_1": {"name": "一絲不苟", "rarity": "R", "stat": "perfect_kinds", "min": 1,
                  "desc": "第一張完整度 1.0000 的卡，邊角連一點折痕都沒有。"},
    "perfect_10": {"name": "收藏家的堅持", "rarity": "SR", "stat": "perfect_kinds", "min": 10,
                   "desc": "卡冊裡的完美卡越排越多，你開始用手套翻頁了。"},
    "perfect_30": {"name": "無瑕的卡冊", "rarity": "SSR", "stat": "perfect_kinds", "min": 30,
                   "desc": "三十種完美的卡，連河童都想借去研究保存方法。"},
    "perfect_50": {"name": "完美的瀟灑", "rarity": "UR", "stat": "perfect_kinds", "min": 50,
                   "desc": "完美到這種程度，咲夜都要對你點頭致意。"},
    # 💰 財富 (曾經持有過的最高賽錢 best_money，花掉也不會失去；2026-11-13 使用者選 A)
    "money_100k": {"name": "小有積蓄", "rarity": "N", "stat": "best_money", "min": 100_000,
                   "desc": "錢包終於有點重量了，可以奢侈地多抽幾次。"},
    "money_1m": {"name": "人里的有錢人", "rarity": "R", "stat": "best_money", "min": 1_000_000,
                 "desc": "走在人間之里，商家都會多看你一眼。"},
    "money_10m": {"name": "香霖堂的大主顧", "rarity": "SR", "stat": "best_money", "min": 10_000_000,
                  "desc": "霖之助看到你來，會默默把好貨擺上櫃台。"},
    "money_50m": {"name": "守財奴", "rarity": "SSR", "stat": "best_money", "min": 50_000_000,
                  "desc": "錢多到捨不得花，晚上數著賽錢才睡得著。"},
    "money_100m": {"name": "幻想鄉的財神", "rarity": "UR", "stat": "best_money", "min": 100_000_000,
                   "desc": "靈夢看你的眼神，已經跟看賽錢箱一模一樣了。"},
    "money_1b": {"name": "比賽錢箱還有錢", "rarity": "LR", "stat": "best_money", "min": 1_000_000_000,
                 "desc": "博麗神社的賽錢箱加起來都比不上你的零頭。"},
    # 🔴 火力 (現在的 P 點；統計是內部 level 0～1000 = 0.0～100.0 P，所以 min = P × 10；2026-11-13 使用者選 A 並指定門檻)
    "power_1": {"name": "初次 Power Up", "rarity": "N", "stat": "power_level", "min": 10,
                "desc": "撿到第一個 P 點，射出的彈幕好像變粗了一點。"},
    "power_10": {"name": "火力漸增", "rarity": "R", "stat": "power_level", "min": 100,
                 "desc": "子彈越來越多，終於有點自機的樣子了。"},
    "power_30": {"name": "彈幕職人", "rarity": "SR", "stat": "power_level", "min": 300,
                 "desc": "火力穩定成長，雜魚妖精已經不是對手。"},
    "power_50": {"name": "符卡使", "rarity": "SSR", "stat": "power_level", "min": 500,
                 "desc": "宣言符卡的聲音，連山上的天狗都聽得見。"},
    "power_70": {"name": "異變解決者", "rarity": "UR", "stat": "power_level", "min": 700,
                 "desc": "這份火力，足以獨自解決一場異變。"},
    "power_99": {"name": "全力全開", "rarity": "LR", "stat": "power_level", "min": 990,
                 "desc": "把火力開到極限，連魔理沙都要說一聲「火力就是正義」。"},
    "power_100": {"name": "∞ INFINITE POWER ∞", "rarity": "LR", "stat": "power_level", "min": 1000,
                  "desc": "FULL POWER 的盡頭不是終點，而是無限。彈幕已經多到看不見天空了。"},
    # 💹 市場賣出 (累計在市場被別人買走幾張，market_trades kind = 'market'，不會失去；分解不算；2026-11-13 使用者選 A)
    "sold_1": {"name": "第一筆生意", "rarity": "N", "stat": "market_sold", "min": 1,
               "desc": "第一張卡被買走了，原來自己的收藏也有人想要。"},
    "sold_10": {"name": "跳蚤市場的攤主", "rarity": "R", "stat": "market_sold", "min": 10,
                "desc": "在人里擺了個小攤子，客人開始會回頭光顧。"},
    "sold_50": {"name": "河童的生意夥伴", "rarity": "SR", "stat": "market_sold", "min": 50,
                "desc": "河童們說要跟你合夥，條件是讓她們抽成。"},
    "sold_100": {"name": "霧雨道具店的競爭對手", "rarity": "SSR", "stat": "market_sold", "min": 100,
                 "desc": "魔理沙開始擔心，客人是不是都跑去你那裡了。"},
    "sold_300": {"name": "幻想鄉的大商人", "rarity": "UR", "stat": "market_sold", "min": 300,
                 "desc": "從人里到妖怪之山，大家都知道找你買卡就對了。"},
    "sold_500": {"name": "卡牌市場的支配者", "rarity": "LR", "stat": "market_sold", "min": 500,
                 "desc": "市場的價格由你決定，連紫都想跟你談生意。"},
    # ⛩️ 神社 (玩家統計 player_stats，2026-11-14 起才開始記；使用者：每種一個 SSR，說明裡帶目前的累計數字 {n})
    #    desc 有 {n} ➔ 顯示時用 title_desc() 換成數字；short=True 的用縮寫 (1.5M)
    "shrine_serve": {"name": "幻想鄉的胃袋支配者", "rarity": "SSR", "stat": "ps:serve_favorite", "min": 100,
                     "desc": "已經成功招待了 {n} 位客人，整個幻想鄉的胃都被你抓住了……"},
    "shrine_explore": {"name": "採集達人", "rarity": "SSR", "stat": "ps:explore", "min": 300,
                       "desc": "已經採集了 {n} 次，連妖怪之山哪棵樹下長蘑菇都一清二楚。"},
    "shrine_youkai": {"name": "妖怪退治專家", "rarity": "SSR", "stat": "ps:youkai", "min": 300,
                      "desc": "已經治退了 {n} 隻妖怪，靈夢開始擔心自己的飯碗了。"},
    "shrine_cook": {"name": "神社的大廚", "rarity": "SSR", "stat": "ps:cook", "min": 300,
                    "desc": "已經做了 {n} 道料理，夜雀食堂都想來挖角你。"},
    "shrine_clean": {"name": "一塵不染", "rarity": "SSR", "stat": "ps:clean", "min": 100,
                     "desc": "已經打掃神社 {n} 次，石階亮到可以當鏡子照。"},
    "shrine_collect": {"name": "賽錢箱的好朋友", "rarity": "SSR", "stat": "ps:collect_money", "min": 10_000_000, "short": True,
                       "desc": "已經從賽錢箱回收了 {n} 賽錢，靈夢看你的眼神越來越複雜。"},
    "shrine_shop": {"name": "雜貨店的常客", "rarity": "SSR", "stat": "ps:shop", "min": 100,
                    "desc": "已經在雜貨店買了 {n} 次東西，老闆都會幫你留好貨。"},
    # 📚 卡池收集 (卡冊「現在」的卡；一個卡池兩個：角色到齊、全卡收集；2026-11-13 使用者選定)
    #    統計是 0 / 1 (Utils.gacha_pools.collection_stats)；開新卡池 ➔ 這裡補兩個，all_cards 會自動把新卡池算進去 (使用者選 1：LR 要所有卡池)
    "pool_classic_chars": {"name": "舊作巡禮者", "rarity": "SR", "stat": "pool_chars:classic", "min": 1,
                           "desc": "從魅魔到夢子，舊作的角色都進了你的卡冊。"},
    "pool_classic_cards": {"name": "舊作的守護者", "rarity": "UR", "stat": "pool_cards:classic", "min": 1,
                           "desc": "連早已被遺忘的舊作卡，你也一張不漏地收好了。"},
    "pool_th06_chars": {"name": "紅魔館的訪客", "rarity": "SR", "stat": "pool_chars:th06", "min": 1,
                        "desc": "紅魔館的住人都到齊了，連門番都讓你進門了。"},
    "pool_th06_cards": {"name": "紅魔館的座上賓", "rarity": "UR", "stat": "pool_cards:th06", "min": 1,
                        "desc": "每一張卡都在你手上，蕾米莉亞邀你一起喝紅茶。"},
    "pool_all": {"name": "幻想鄉緣起", "rarity": "LR", "stat": "all_cards", "min": 1,
                 "desc": "幻想鄉的每一位、每一張都在你的卡冊裡，你就是活著的緣起。"},
}

RARITY_ORDER = {"N": 0, "R": 1, "SR": 2, "SSR": 3, "UR": 4, "LR": 5}

# 🗂️ 稱號分組 (/profile 先選分組再選稱號：Discord 選單最多 25 個選項，稱號全放一個選單會放不下)
#    stats = 這組用哪些統計；結尾是「:」的是前綴 (卡池收集每個卡池一個統計)
#    新增一組稱號 ➔ 這裡也要加一筆 (測試會檢查每個稱號都有分組)；分組最多 25 組、每組最多 24 個稱號
TITLE_GROUPS = {
    "draw":    {"name": "🎰 祈願", "stats": ("total_draws",)},
    "fusion":  {"name": "🔮 融合", "stats": ("total_fusions",)},
    "synth":   {"name": "⚗️ 合成", "stats": ("total_synths",)},
    "daily":   {"name": "📅 簽到", "stats": ("daily_count",)},
    "streak":  {"name": "🔥 連續簽到", "stats": ("best_streak",)},
    "rare":    {"name": "🌟 UR / LR 收藏", "stats": ("ur_kinds", "lr_kinds")},
    "perfect": {"name": "💎 完美卡", "stats": ("perfect_kinds",)},
    "money":   {"name": "💰 財富", "stats": ("best_money",)},
    "power":   {"name": "🔴 火力", "stats": ("power_level",)},
    "market":  {"name": "💹 市場賣出", "stats": ("market_sold",)},
    "shrine":  {"name": "⛩️ 神社", "stats": ("ps:",)},
    "pool":    {"name": "📚 卡池收集", "stats": ("pool_chars:", "pool_cards:", "all_cards")},
    # 💕 推角：每個卡池一組 (一組最多 24 個)，在下面 _add_oshi_titles() 自動加
}

# 💕 推角 (2026-11-13 使用者選 A：每位角色一個，名稱「我是XXX的狗!!!」)
#    收藏冊 (/card album，gacha_cards.locked = 1)「現在」有那位角色每個階級各一張完美卡 (完整度 1.0000) 就解鎖，
#    拿出收藏冊 / 賣掉就失去 (2026-11-13 使用者改：原本是同角色 10 張；2026-11-14 改成只算收藏冊)
#    🖼️ 第一次拿到推角稱號時同時永久獲得那位角色的名片 (User_DB_Manager.sync_oshi_namecards)，稱號失去名片還在
#    稱號從角色檔自動產生 (Utils.gacha_pools.load_gacha_pool)，新角色會自動多一個；角色檔改了要 /admin-sys reload


def _add_oshi_titles():
    from Utils.gacha_pools import GACHA_POOLS, load_gacha_pool
    for pool, info in GACHA_POOLS.items():
        TITLE_GROUPS[f"oshi_{pool}"] = {"name": f"💕 推角・{info['name'].split(' ', 1)[-1].removesuffix('卡池')}",
                                        "stats": (f"oshi:{pool}:",)}
    for cid, c in load_gacha_pool().items():
        TITLES[f"oshi_{cid}"] = {
            "name": f"我是{c['name']}的狗!!!", "rarity": "SR", "stat": f"oshi:{c['pool']}:{cid}",
            "min": len(c["rarities"]), "character": c["name"], "rarities": list(c["rarities"]),
            "desc": f"最喜歡「{c['profile_title']}」{c['name']}了，每個階級都收了一張完美的卡放進收藏冊，汪！",
        }


_add_oshi_titles()


def title_group(tid: str) -> str | None:
    """稱號屬於哪一組 (TITLE_GROUPS 的鍵)；找不到回傳 None"""
    stat = TITLES[tid]["stat"]
    for key, group in TITLE_GROUPS.items():
        if any(stat == s or (s.endswith(":") and stat.startswith(s)) for s in group["stats"]):
            return key
    return None


def group_titles(unlocked: list[str]) -> dict[str, list[str]]:
    """已解鎖的稱號依分組排好：{分組: [稱號 id (等級高的在前)]}，只列有稱號的組，照 TITLE_GROUPS 順序"""
    result = {key: [] for key in TITLE_GROUPS}
    for tid in unlocked:
        result.setdefault(title_group(tid) or "other", []).append(tid)
    return {k: v for k, v in result.items() if v}


def unlocked_titles(stats: dict) -> list[str]:
    """依玩家統計列出已解鎖的稱號 id (等級高的在前，同等級照 TITLES 順序)"""
    def ok(tid: str) -> bool:
        t = TITLES[tid]
        return stats.get(t["stat"], 0) >= t["min"] and (not t.get("requires") or ok(t["requires"]))
    ids = [tid for tid in TITLES if ok(tid)]
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
    text = _stat_text(t)
    if t.get("requires"):   # 前一個稱號也要有 (2026-11-13 使用者：獲得稱號前必須先擁有前一個)
        text += f"，且已獲得「{TITLES[t['requires']]['name']}」"
    return text


from Utils.numbers import short_number   # noqa: E402  數字縮寫 (1.5M)


def _number(t: dict, value) -> str:
    return short_number(value) if t.get("short") else f"{int(value):,}"


def title_desc(tid: str, stats: dict | None = None) -> str:
    """稱號說明；有 {n} 的換成目前的累計數字 (沒有統計就顯示 0)"""
    t = TITLES[tid]
    desc = t["desc"]
    if "{n}" in desc:
        desc = desc.replace("{n}", _number(t, (stats or {}).get(t["stat"], 0)))
    return desc


SHRINE_STAT_TEXT = {"ps:serve_favorite": "成功招待 {} 位客人 (額外端上最愛的料理)", "ps:explore": "採集 {} 次",
                    "ps:youkai": "治退 {} 隻妖怪", "ps:cook": "料理 {} 次", "ps:clean": "打掃神社 {} 次",
                    "ps:collect_money": "從賽錢箱累計回收 {} 賽錢", "ps:shop": "在雜貨店買 {} 次東西"}


def _stat_text(t: dict) -> str:
    stat = t["stat"]
    if stat in SHRINE_STAT_TEXT:
        return SHRINE_STAT_TEXT[stat].format(_number(t, t["min"]))
    if stat.startswith("oshi:"):
        rars = " / ".join(t.get("rarities", []))
        return f"收藏冊裡有{t.get('character', stat.rsplit(':', 1)[-1])}每個階級 ({rars}) 各一張完美卡 (完整度 1.0000)"
    if stat.startswith(("pool_chars:", "pool_cards:")):
        from Utils.gacha_pools import GACHA_POOLS
        kind, pool = stat.split(":", 1)
        name = GACHA_POOLS.get(pool, {}).get("name", pool).split(" ", 1)[-1]   # 去掉 emoji
        return f"{name}的角色全部到齊" if kind == "pool_chars" else f"{name}的卡全部收集 (每個階級)"
    return {"total_draws": f"累計祈願 {t['min']:,} 抽",
            "total_fusions": f"累計融合 {t['min']:,} 次",
            "total_synths": f"累計合成 {t['min']:,} 次",
            "daily_count": f"累積簽到 {t['min']:,} 天",
            "best_streak": f"連續簽到 {t['min']:,} 天",
            "ur_kinds": f"卡冊有 {t['min']:,} 種角色的 UR 卡",
            "lr_kinds": f"卡冊有 {t['min']:,} 種角色的 LR 卡",
            "perfect_kinds": f"卡冊有 {t['min']:,} 種完美卡 (完整度 1.0000)",
            "all_cards": "所有卡池的卡全部收集 (每個階級)",
            "best_money": f"曾經持有 {short_number(t['min'])} 賽錢",
            "power_level": f"火力達到 {t['min'] / 10:.1f} P",
            "market_sold": f"在市場賣出 {t['min']:,} 張卡"}.get(t["stat"], f"{t['stat']} ≥ {t['min']:,}")

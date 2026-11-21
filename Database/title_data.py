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
    # 💸 轉帳 (累計轉出金額，market_trades kind = 'transfer' 的 price，不扣手續費、不會失去；2026-11-14 使用者選 A)
    "transfer_100k": {"name": "樂於分享", "rarity": "R", "stat": "transfer_sent", "min": 100_000,
                      "desc": "第一次把賽錢分給別人，心裡暖暖的。"},
    "transfer_1m": {"name": "慷慨解囊", "rarity": "SR", "stat": "transfer_sent", "min": 1_000_000,
                    "desc": "有人缺錢時，大家第一個想到的就是你。"},
    "transfer_10m": {"name": "幻想鄉的散財童子", "rarity": "SSR", "stat": "transfer_sent", "min": 10_000_000,
                     "desc": "錢對你來說只是用來讓大家開心的東西。"},
    "transfer_50m": {"name": "比神明還大方", "rarity": "UR", "stat": "transfer_sent", "min": 50_000_000,
                     "desc": "靈夢看到你送出去的金額，羨慕得說不出話。"},
    # ⛩️ 神社 (玩家統計 player_stats，2026-11-14 起才開始記；使用者：每種一個 SSR，說明裡帶目前的累計數字 {n})
    #    desc 有 {n} ➔ 顯示時用 title_desc() 換成數字；short=True 的用縮寫 (1.5M)
    "shrine_serve": {"name": "幻想鄉的胃袋支配者", "rarity": "SSR", "stat": "ps:serve_favorite", "min": 100,
                     "desc": "已經成功招待了 {n} 位客人，整個幻想鄉的胃都被你抓住了……"},
    "shrine_explore": {"name": "採集達人", "rarity": "SSR", "stat": "ps:explore", "min": 500,   # 0.35.010 使用者從 300 改成 500
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
    # ⛩️ 神社分級 (0.35.010，使用者 2026-11-16 定案)：上面 7 個 SSR 保留，每項再加 N / R / SR / UR，門檻使用者給的
    "shrine_serve_n": {"name": "察言觀色", "rarity": "N", "stat": "ps:serve_favorite", "min": 1,
                       "desc": "第一次正中客人的最愛，原來妖怪也會笑。"},
    "shrine_serve_r": {"name": "貼心的巫女", "rarity": "R", "stat": "ps:serve_favorite", "min": 10,
                       "desc": "成功招待了 {n} 位客人，客人開始說「下次還要來」。"},
    "shrine_serve_sr": {"name": "神社的招牌服務", "rarity": "SR", "stat": "ps:serve_favorite", "min": 50,
                        "desc": "成功招待了 {n} 位客人，天狗新聞把神社寫進了美食專欄。"},
    "shrine_serve_ur": {"name": "妖怪們的心頭好", "rarity": "UR", "stat": "ps:serve_favorite", "min": 500,
                        "desc": "成功招待了 {n} 位客人，妖怪之山的妖怪都排隊來參拜。"},
    "shrine_explore_n": {"name": "初出茅廬的採集者", "rarity": "N", "stat": "ps:explore", "min": 10,
                         "desc": "採集了 {n} 次，竹籃還是新的。"},
    "shrine_explore_r": {"name": "背著竹籃的巫女", "rarity": "R", "stat": "ps:explore", "min": 50,
                         "desc": "採集了 {n} 次，竹籃開始有點破了。"},
    "shrine_explore_sr": {"name": "勤勞的採集者", "rarity": "SR", "stat": "ps:explore", "min": 100,
                          "desc": "採集了 {n} 次，連妖精都記住了你的採集路線。"},
    "shrine_explore_ur": {"name": "行走的食材庫", "rarity": "UR", "stat": "ps:explore", "min": 1000,
                          "desc": "採集了 {n} 次，神社倉庫已經堆到放不下了。"},
    "shrine_youkai_n": {"name": "見習退治人", "rarity": "N", "stat": "ps:youkai", "min": 5,
                        "desc": "治退了 {n} 隻妖怪，御幣揮起來還有點生疏。"},
    "shrine_youkai_r": {"name": "神社的守門人", "rarity": "R", "stat": "ps:youkai", "min": 20,
                        "desc": "治退了 {n} 隻妖怪，小妖怪看到神社都繞路走。"},
    "shrine_youkai_sr": {"name": "妖怪剋星", "rarity": "SR", "stat": "ps:youkai", "min": 100,
                         "desc": "治退了 {n} 隻妖怪，人里開始流傳你的事蹟。"},
    "shrine_youkai_ur": {"name": "讓妖怪聞風喪膽的人", "rarity": "UR", "stat": "ps:youkai", "min": 500,
                         "desc": "治退了 {n} 隻妖怪，妖怪之間流傳「千萬別去那間神社」。"},
    "shrine_cook_n": {"name": "廚房新手", "rarity": "N", "stat": "ps:cook", "min": 5,
                      "desc": "做了 {n} 鍋料理，至少沒把廚房燒掉。"},
    "shrine_cook_r": {"name": "家常料理人", "rarity": "R", "stat": "ps:cook", "min": 20,
                      "desc": "做了 {n} 鍋料理，味道已經可以端上桌了。"},
    "shrine_cook_sr": {"name": "神社的料理擔當", "rarity": "SR", "stat": "ps:cook", "min": 100,
                       "desc": "做了 {n} 鍋料理，客人開始指名要吃你做的菜。"},
    "shrine_cook_ur": {"name": "幻想鄉的料理之神", "rarity": "UR", "stat": "ps:cook", "min": 500,
                       "desc": "做了 {n} 鍋料理，連女僕長都來偷學你的刀工。"},
    "shrine_clean_n": {"name": "拿起掃把的人", "rarity": "N", "stat": "ps:clean", "min": 1,
                       "desc": "第一次打掃神社，落葉少了一點點。"},
    "shrine_clean_r": {"name": "勤快的掃除者", "rarity": "R", "stat": "ps:clean", "min": 10,
                       "desc": "打掃了 {n} 次，參道終於看得見石板了。"},
    "shrine_clean_sr": {"name": "參道的守護者", "rarity": "SR", "stat": "ps:clean", "min": 50,
                        "desc": "打掃了 {n} 次，一片落葉都不放過。"},
    "shrine_clean_ur": {"name": "潔癖巫女", "rarity": "UR", "stat": "ps:clean", "min": 500,
                        "desc": "打掃了 {n} 次，神社乾淨到妖怪都不好意思弄髒。"},
    "shrine_collect_n": {"name": "第一份香油錢", "rarity": "N", "stat": "ps:collect_money", "min": 10_000, "short": True,
                         "desc": "從賽錢箱回收了 {n} 賽錢，雖然不多，但是一份心意。"},
    "shrine_collect_r": {"name": "香火漸旺", "rarity": "R", "stat": "ps:collect_money", "min": 100_000, "short": True,
                         "desc": "回收了 {n} 賽錢，神社的香火開始旺起來了。"},
    "shrine_collect_sr": {"name": "會響的賽錢箱", "rarity": "SR", "stat": "ps:collect_money", "min": 1_000_000, "short": True,
                          "desc": "回收了 {n} 賽錢，搖一搖賽錢箱終於會叮噹響了。"},
    "shrine_collect_ur": {"name": "香火鼎盛", "rarity": "UR", "stat": "ps:collect_money", "min": 100_000_000, "short": True,
                          "desc": "回收了 {n} 賽錢，博麗神社終於成為幻想鄉第一（靈夢感動到哭了）。"},
    "shrine_shop_n": {"name": "第一次的採買", "rarity": "N", "stat": "ps:shop", "min": 1,
                      "desc": "第一次在雜貨店買東西，老闆記住了你的臉。"},
    "shrine_shop_r": {"name": "會殺價的巫女", "rarity": "R", "stat": "ps:shop", "min": 10,
                      "desc": "在雜貨店買了 {n} 次東西，老闆開始給你打折了。"},
    "shrine_shop_sr": {"name": "人里的大客戶", "rarity": "SR", "stat": "ps:shop", "min": 50,
                       "desc": "在雜貨店買了 {n} 次東西，老闆說年底要送你禮盒。"},
    "shrine_shop_ur": {"name": "雜貨店的股東", "rarity": "UR", "stat": "ps:shop", "min": 500,
                       "desc": "在雜貨店買了 {n} 次東西，雜貨店有一半的營收來自你。"},
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
    "transfer": {"name": "💸 轉帳", "stats": ("transfer_sent",)},
    "shrine":  {"name": "⛩️ 神社", "stats": ("ps:",)},
    "guest":   {"name": "🙏 客人", "stats": ()},   # 一般客人的稱號 (下面 _add_guest_titles() 產生，稱號本身帶 group)；活動客人每個活動一組
    "trek":    {"name": "🗺️ 足跡", "stats": ()},   # 一般採集地點的稱號 + 幻想鄉踏破 (_add_trek_titles())；活動地點每個活動一組
    "luck":    {"name": "🍀 運氣", "stats": ()},
    "gourmet": {"name": "🍳 美食家", "stats": ()},   # 料理圖鑑、吃體力料理、分類全收 (_add_gourmet_titles())；活動食譜每個活動一組   # 採集事件、運勢、保底、舊作歐氣 (_add_luck_titles())；其他卡池的歐氣每個卡池一組
    "ura":     {"name": "🌀 裏世界", "stats": ()},   # 📖 怪物圖鑑的全收稱號 (_add_ura_titles())；活動怪的也放這組 (不另開子分組)
    "pool":    {"name": "📚 卡池收集", "stats": ("pool_chars:", "pool_cards:", "all_cards")},
    "event":   {"name": "🎪 活動", "stats": ("evq:",)},   # 活動任務稱號 (下面 _add_event_titles() 從 Events/*.json 自動加)
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


# 🎪 活動任務稱號 (2026-11-14 使用者)：活動檔的 quest_titles，「領取」的任務數 >= min_quests 就「永久」獲得
#    (Quest_DB_Manager.claim_quest 寫進 earned_titles 表，活動結束也保留；get_title_state 會把 earned_titles 列進已解鎖)
#    stat = evq:<活動 id> 只用來分組與條件文字，玩家統計裡沒有這個鍵 (earned=True ➔ unlocked_titles 不用條件判斷)
#    稱號 id = event_<活動 id>_<稱號 id>；改了活動檔要 /admin-sys reload (全部重載)
EVENT_TITLE_PREFIX = "event_"


def event_title_id(event_id: str, title_id: str) -> str:
    return f"{EVENT_TITLE_PREFIX}{event_id}_{title_id}"


def _add_event_titles():
    from Database.events import load_events
    for eid, ev in load_events().items():
        for t in ev.get("quest_titles", []):
            TITLES[event_title_id(eid, t["id"])] = {
                "name": t["name"], "rarity": t["rarity"], "desc": t.get("desc", ""),
                "stat": f"evq:{eid}", "min": int(t["min_quests"]), "earned": True,
                "event": eid, "event_name": ev.get("name", eid),
            }


_add_event_titles()


# 🏭 自動產生稱號的共用工具 (0.35.012 統整：客人 / 足跡 / 運氣 / 美食家四組共用)
#    新增一組「一般 + 每個活動 (或卡池) 一組」的自動稱號：
#      ① TITLE_GROUPS 加基本組 (stats 留空，稱號自己帶 group)
#      ② 固定清單用 _add_title_rows()；每個對象 (客人 / 地點 / 卡池) 分幾階用 _add_tier_titles()
#      ③ 活動 / 卡池的分組用 _sub_group() 收集，最後 _insert_groups_after(基本組, groups) 排在基本組後面
def _insert_groups_after(key: str, groups: dict):
    """把新的分組插在 TITLE_GROUPS 的 key 後面 (選單照這個順序)"""
    items = list(TITLE_GROUPS.items())
    at = next(i for i, (k, _) in enumerate(items) if k == key) + 1
    TITLE_GROUPS.clear()
    TITLE_GROUPS.update(items[:at] + list(groups.items()) + items[at:])


def _sub_group(base: str, key: str, label: str, groups: dict) -> str:
    """基本組底下的子分組 (例如「🙏 客人・紅霧異變」)：id = <基本組>_<key>，名稱 = 基本組名稱・label；回傳分組 id"""
    gid = f"{base}_{key}"
    groups[gid] = {"name": f"{TITLE_GROUPS[base]['name']}・{label}", "stats": ()}
    return gid


def _add_title_rows(rows, group: str):
    """固定清單 [(id, 名稱, 等級, stat, 門檻, 說明), ...] ➔ TITLES (都放 group 這組)"""
    for tid, name, rarity, stat, n, desc in rows:
        TITLES[tid] = {"name": name, "rarity": rarity, "group": group, "stat": stat, "min": n, "desc": desc}


def _add_tier_titles(tid_of, tiers, common: dict, text: dict | None, fallback: dict):
    """
    一個對象 (客人 / 地點 / 卡池) 分幾階的稱號
    tiers = [(階, 等級, stat, 門檻), ...]；tid_of(階) ➔ 稱號 id
    text = {階: (名稱, 說明)} 自訂的 (名稱或說明是 None 就用 fallback[階] 的)；common = 每階都有的欄位 (group…)
    """
    for tier, rarity, stat, n in tiers:
        name, desc = (text or {}).get(tier) or (None, None)
        fb_name, fb_desc = fallback[tier]
        TITLES[tid_of(tier)] = {**common, "name": name or fb_name, "rarity": rarity, "stat": stat, "min": n,
                                "desc": desc or fb_desc}


def _sr_ur_text(pair: tuple | None) -> dict | None:
    """(SR 名稱, SR 說明, UR 名稱, UR 說明) ➔ {"sr": (名稱, 說明), "ur": (名稱, 說明)}"""
    return {"sr": pair[:2], "ur": pair[2:]} if pair else None


def _json_text(titles: dict | None) -> dict:
    """活動檔的 {"sr": {"name", "desc"}, ...} ➔ {階: (名稱, 說明)}"""
    return {k: (v.get("name"), v.get("desc")) for k, v in (titles or {}).items()}


# 🙏 客人稱號 (0.35.001，使用者 2026-11-16 定案)：每種客人兩個
#    SR = 招待那種客人 50 次 (ps:serve_guest:<客人>)、UR = 成功招待 (額外端上牠最愛的料理) 50 次 (ps:serve_fav:<客人>)
#    活動客人也算、門檻一樣；次數存在 player_stats，跨活動一直累積 (輪替活動再來時接著算)
#    一般客人一組「🙏 客人」，活動客人每個活動一組「🙏 客人・<活動名>」(活動檔 guests.<客人>.titles，沒寫就用預設名稱)
GUEST_TITLE_MIN = 50
GUEST_TITLE_TEXT = {   # 客人 ➔ (SR 名稱, SR 說明, UR 名稱, UR 說明)；說明的 {n} 換成目前的次數
    "kappa": ("河童的盟友", "招待了 {n} 次河童，工房的扳手借你隨便用。",
              "小黃瓜外交官", "端了 {n} 次冰鎮小黃瓜給河童，玄武之澤都叫你「盟友中的盟友」。"),
    "crow_tengu": ("天狗新聞的頭版常客", "招待了 {n} 次鴉天狗，你的照片已經上了好幾次頭版。",
                   "天狗的酒友", "用甘酒灌醉了鴉天狗 {n} 次，報導終於開始說神社的好話了。"),
    "wolf_tengu": ("巡邏隊的休息站", "招待了 {n} 次白狼天狗，值班時間一到牠們就往神社跑。",
                   "烤地瓜供應商", "端了 {n} 次烤地瓜給白狼天狗，尾巴一看到你就停不下來。"),
    "fox": ("被狐狸纏上的人", "招待了 {n} 次狐妖，神社後面好像多了一個狐狸窩。",
            "豆皮壽司的信徒", "端了 {n} 次豆皮壽司給狐妖，九尾的式神都來打聽你的食譜。"),
    "bakeneko": ("貓咪的飯碗", "招待了 {n} 次化貓，神社的緣廊變成了貓咪午睡區。",
                 "八目鰻大師", "端了 {n} 次烤八目鰻給化貓，連夜雀都開始對你有戒心。"),
    "kasa_obake": ("被嚇到的好人", "招待了 {n} 次唐傘妖怪，每次都配合地假裝被嚇到。",
                   "刨冰救星", "大熱天端了 {n} 次刨冰給唐傘妖怪，它說你是唯一不會丟下它的人。"),
    "tsukumogami": ("道具的知音", "招待了 {n} 次付喪神，神社的舊燈籠好像也在偷看你。",
                    "粗茶之友", "端了 {n} 次回沖好幾次的粗茶給付喪神，它說這才是老派的味道。"),
    "night_sparrow": ("夜雀的聽眾", "招待了 {n} 次夜雀，每次都乖乖聽完一整首歌。",
                      "夜雀的專屬調茶師", "端了 {n} 次花蜜茶給夜雀，牠的歌越唱越好聽。"),
    "fairy": ("妖精的遊樂場", "招待了 {n} 次妖精，神社變成了惡作劇的大本營。",
              "汽水大人", "端了 {n} 次彈珠汽水給妖精，妖精們現在都這樣叫你。"),
    "oni": ("鬼的酒席主人", "招待了 {n} 次小鬼，神社的酒窖越來越空。",
            "鬼也認可的甜點師", "端了 {n} 次栗子羊羹給小鬼。鬼不說謊，它說你是幻想鄉第一。"),
}


def guest_title_id(kind: str, tier: str) -> str:
    return f"guest_{kind}_{tier}"


def _guest_titles(kind: str, guest: dict, group: str, text: dict | None, event: str | None = None):
    """一種客人的 SR / UR；text = {階: (名稱, 說明)}，沒寫的用預設名稱"""
    name = guest.get("name", kind)
    _add_tier_titles(
        lambda tier: guest_title_id(kind, tier),
        [("sr", "SR", f"ps:serve_guest:{kind}", GUEST_TITLE_MIN), ("ur", "UR", f"ps:serve_fav:{kind}", GUEST_TITLE_MIN)],
        {"group": group, "guest": kind, "guest_name": name, "guest_event": event}, text,
        {"sr": (f"{name}的常客", f"招待了 {{n}} 次{name}，牠已經把神社當成自己家了。"),
         "ur": (f"{name}的知己", f"端了 {{n}} 次{name}最愛的料理，牠說你是最懂牠的人。")})


def _add_guest_titles():
    from Database import shrine_data
    from Database.events import load_events
    for kind, g in shrine_data.GUESTS.items():
        _guest_titles(kind, g, "guest", _sr_ur_text(GUEST_TITLE_TEXT.get(kind)))
    groups = {}
    for eid, ev in load_events().items():
        if not ev.get("guests"):
            continue
        group = _sub_group("guest", eid, ev.get("name", eid), groups)
        for kind, g in ev["guests"].items():
            _guest_titles(kind, g, group, _json_text(g.get("titles")), eid)
    _insert_groups_after("guest", groups)   # 活動客人的分組排在「🙏 客人」後面


_add_guest_titles()


# 🗺️ 足跡稱號 (0.35.003，使用者 2026-11-16 定案)：每個採集地點兩個
#    SR = 在那個地點採集 200 趟、UR = 1000 趟 (ps:explore:<地點>，一般採集和快速採集都算)
#    活動地點也算、門檻一樣，每個活動一組「🗺️ 足跡・<活動名>」(活動檔 location.titles，沒寫就用預設名稱)；次數跨活動累積
#    踏破：「幻想鄉踏破」SR = 一般地點每個都採過 1 趟 (活動地點不算)；每個活動另有「<活動名> • 踏破」SSR = 那個活動的地點都採過 1 趟
#    踏破有 keep=True：第一次達成就寫進 earned_titles 永久保留 (之後新增地點，已經拿到的人不會失去)
TREK_SR_MIN, TREK_UR_MIN = 200, 1000
TREK_TITLE_TEXT = {   # 地點 ➔ (SR 名稱, SR 說明, UR 名稱, UR 說明)；說明的 {n} 換成目前的趟數
    "village": ("人里的熟面孔", "在人間之里採集了 {n} 次，攤販都會主動跟你打招呼。",
                "人里的活地圖", "在人間之里採集了 {n} 次，哪家店幾點打烊你都背得出來。"),
    "misty_lake": ("霧中的漁夫", "在霧之湖採集了 {n} 次，八目鰻看到你都會游遠一點。",
                   "冰精的老朋友", "在霧之湖採集了 {n} 次，琪露諾已經把你當成手下了（她自稱的）。"),
    "youkai_mountain": ("山道的常客", "在妖怪之山採集了 {n} 次，巡邏的白狼天狗懶得趕你了。",
                        "天狗也認可的登山家", "在妖怪之山採集了 {n} 次，天狗新聞專門幫你開了登山專欄。"),
    "bamboo_forest": ("不再迷路的人", "在迷途竹林採集了 {n} 次，終於記得回去的路了。",
                      "竹林的嚮導", "在迷途竹林採集了 {n} 次，連月兔都跑來問你永遠亭怎麼走。"),
    "sunflower_field": ("花田的訪客", "在太陽花田採集了 {n} 次，花田的主人開始記得你的名字了。",
                        "活著走出花田的人", "在太陽花田採集了 {n} 次還毫髮無傷，這本身就是奇蹟。"),
    "magic_forest": ("蘑菇獵人", "在魔法森林採集了 {n} 次，已經分得出哪些蘑菇會讓人看到幻覺。",
                     "瘴氣免疫者", "在魔法森林採集了 {n} 次，森林的瘴氣對你已經完全沒用了。"),
    "kourindou": ("香霖堂的熟客", "在香霖堂翻找了 {n} 次，店主開始幫你留「非賣品」。",
                  "外界道具鑑定士", "在香霖堂翻找了 {n} 次，你比店主還清楚那些外界道具怎麼用。"),
    "hakugyokurou": ("冥界的訪客", "在白玉樓採集了 {n} 次，庭師已經不會對你拔刀了（大部分時候）。",
                     "白玉樓的編外庭師", "在白玉樓採集了 {n} 次，掃落葉的速度快追上半人半靈了。"),
    "old_hell_onsen": ("溫泉街的常客", "在舊地獄溫泉採集了 {n} 次，鬼族會幫你留一池熱水。",
                       "泡不暈的人", "在舊地獄溫泉採集了 {n} 次，連鬼都泡不過你。"),
}
TREK_BASE_ID = "trek_all"
TREK_EVENT_LOCATIONS: dict[str, list[str]] = {}   # 活動 id ➔ 那個活動的採集地點 (踏破統計用)


def trek_title_id(loc_id: str, tier: str) -> str:
    return f"trek_{loc_id}_{tier}"


def _trek_titles(loc_id: str, loc: dict, group: str, text: dict | None):
    """一個採集地點的 SR / UR；text = {階: (名稱, 說明)}，沒寫的用預設名稱"""
    name, stat = loc.get("name", loc_id), f"ps:explore:{loc_id}"
    _add_tier_titles(
        lambda tier: trek_title_id(loc_id, tier),
        [("sr", "SR", stat, TREK_SR_MIN), ("ur", "UR", stat, TREK_UR_MIN)],
        {"group": group, "location": loc_id, "location_name": name}, text,
        {"sr": (f"{name}的熟客", f"在{name}採集了 {{n}} 次，那裡的路你閉著眼睛都會走。"),
         "ur": (f"{name}的活地圖", f"在{name}採集了 {{n}} 次，哪裡有什麼你比誰都清楚。")})


def _add_trek_titles():
    from Database import shrine_data
    from Database.events import load_events
    for loc_id, loc in shrine_data.LOCATIONS.items():
        _trek_titles(loc_id, loc, "trek", _sr_ur_text(TREK_TITLE_TEXT.get(loc_id)))
    TITLES[TREK_BASE_ID] = {"name": "幻想鄉踏破", "rarity": "SR", "group": "trek", "stat": "trek_base",
                            "min": len(shrine_data.LOCATIONS), "keep": True,
                            "desc": "幻想鄉的每一個地方都留下了你的腳印。"}
    groups = {}
    TREK_EVENT_LOCATIONS.clear()
    for eid, ev in load_events().items():
        locs = [loc for loc in ([ev["location"]] if ev.get("location") else []) + list(ev.get("locations", []))]
        if not locs:
            continue
        ev_name = ev.get("name", eid)
        group = _sub_group("trek", eid, ev_name, groups)
        for loc in locs:
            _trek_titles(loc["id"], loc, group, _json_text(loc.get("titles")))
        TREK_EVENT_LOCATIONS[eid] = [loc["id"] for loc in locs]
        # 說明寫在活動檔的 trek_title.desc (照那個活動地點的特色寫)；沒寫才用通用句
        desc = (ev.get("trek_title") or {}).get("desc") or f"{ev_name}期間開放的地方，你全都去過了。"
        TITLES[f"trek_{eid}_all"] = {"name": f"{ev_name} • 踏破", "rarity": "SSR", "group": group, "stat": f"trek_ev:{eid}",
                                     "min": len(locs), "keep": True, "event_name": ev_name, "desc": desc}
    _insert_groups_after("trek", groups)


_add_trek_titles()


# 🍀 運氣稱號 (0.35.005，使用者 2026-11-16 定案；次數都從這版才開始記)
#    採集好 / 壞事件 20 次 SR、100 次 UR；簽到大吉 / 凶 10 次 SR、30 次 SSR；觸發保底 (所有卡池合計) 10 / 50 / 100 次 SSR / UR / LR
#    歐氣 = 一次十連出 2 張以上 UR (含 LR)：1 / 5 / 10 次 SSR / UR / LR，每個卡池分開
#      舊作 (classic) 是普池，放「🍀 運氣」；紅魔鄉 (TH06) 以後的卡池與活動限定卡池各自一組「🍀 運氣・<卡池>」
LUCK_TITLES = [   # (id, 名稱, 等級, stat, 門檻, 說明)
    ("luck_good_sr", "福星高照", "SR", "ps:explore_good", 20, "採集時遇到了 {n} 次好事，連妖精都想跟著你走。"),
    ("luck_good_ur", "被幸運女神看上的人", "UR", "ps:explore_good", 100, "採集時遇到了 {n} 次好事，河童懷疑你身上裝了什麼外界道具。"),
    ("luck_bad_sr", "倒楣巫女", "SR", "ps:explore_bad", 20, "採集時倒楣了 {n} 次，被凍住、被趕下山、被兔子送出竹林……"),
    ("luck_bad_ur", "厄神的好朋友", "UR", "ps:explore_bad", 100, "採集時倒楣了 {n} 次，雛說你是她見過最能扛厄運的人。"),
    ("luck_daikichi_sr", "大吉體質", "SR", "ps:fortune_5", 10, "簽到抽到 {n} 次大吉，博麗大神好像特別偏心你。"),
    ("luck_daikichi_ssr", "神明的寵兒", "SSR", "ps:fortune_5", 30, "抽到 {n} 次大吉，連守矢神社都想挖角你去當巫女。"),
    ("luck_kyo_sr", "凶運纏身", "SR", "ps:fortune_0", 10, "簽到抽到 {n} 次凶，今天也請低調行事。"),
    ("luck_kyo_ssr", "與厄運共舞", "SSR", "ps:fortune_0", 30, "抽到 {n} 次凶，雛已經把你列為 VIP 了。"),
    ("luck_pity_ssr", "保底常客", "SSR", "ps:gacha_pity", 10, "觸發了 {n} 次保底，賽錢箱記得你的每一分錢。"),
    ("luck_pity_ur", "與保底同行之人", "UR", "ps:gacha_pity", 50, "觸發了 {n} 次保底，你的 UR 有一半是保底送的。"),
    ("luck_pity_lr", "被機率遺忘的人", "LR", "ps:gacha_pity", 100, "觸發了 {n} 次保底，博麗大神偷偷替你掉了一滴眼淚。"),
]
LUCK_POOL_TIERS = (("ssr", "SSR", 1), ("ur", "UR", 5), ("lr", "LR", 10))
LUCK_POOL_TEXT = {   # 卡池 ➔ {階: (名稱, 說明)}；沒寫的說明用通用句
    "classic": {"ssr": ("舊作的幸運兒", None), "ur": ("舊作的寵兒", None),
                "lr": ("魔界神也嫉妒的手氣", "在舊作卡池一次十連出 2 張以上 UR {n} 次，神綺說她創造魔界時都沒這麼好運。")},
    "th06": {"ssr": ("紅魔館的幸運兒", None), "ur": ("紅霧裡的閃光", None),
             "lr": ("命運的操縱者", "在紅魔鄉卡池一次十連出 2 張以上 UR {n} 次，蕾米莉亞懷疑你偷學了她的能力。")},
}
LUCK_BASE_POOL = "classic"   # 普池：歐氣稱號放在「🍀 運氣」組


def luck_pool_title_id(pool: str, tier: str) -> str:
    return f"luck_{pool}_{tier}"


def _add_luck_titles():
    from Utils.gacha_pools import GACHA_POOLS
    from Database.events import load_events
    _add_title_rows(LUCK_TITLES, "luck")
    pools = [(key, info["name"].split(" ", 1)[-1].removesuffix("卡池"), None) for key, info in GACHA_POOLS.items()]
    for eid, ev in load_events().items():   # 🎪 活動限定卡池 (event_<活動 id>)；名稱可以寫在 gacha.pool.luck_titles
        pool = (ev.get("gacha") or {}).get("pool") or {}
        if pool.get("characters"):
            pools.append((f"event_{eid}", ev.get("name", eid), pool.get("luck_titles")))
    groups = {}
    for key, label, custom in pools:
        group = "luck" if key == LUCK_BASE_POOL else _sub_group("luck", key, label, groups)
        stat, generic = f"ps:tenpull_2ur:{key}", f"在{label}卡池一次十連出 2 張以上 UR，已經 {{n}} 次了。"
        _add_tier_titles(
            lambda tier: luck_pool_title_id(key, tier),
            [(tier, rarity, stat, n) for tier, rarity, n in LUCK_POOL_TIERS],
            {"group": group, "pool_name": label}, {**LUCK_POOL_TEXT.get(key, {}), **_json_text(custom)},
            {"ssr": (f"{label}的幸運兒", generic), "ur": (f"{label}的寵兒", generic), "lr": (f"{label}的歐皇", generic)})
    _insert_groups_after("luck", groups)


_add_luck_titles()


# 🍳 美食家稱號 (0.35.007，使用者 2026-11-16 定案；次數從這版才開始記)
#    料理圖鑑：做過幾種不同的料理 (招待料理 + 體力料理，活動料理不算) 10 / 20 / 30 種 = SR / SSR / UR (固定種數)
#    吃體力料理 (含簽到的飯糰，ps:eat_stamina) 100 / 500 / 1000 個 = SR / UR / LR
#    分類全收：食物 / 茶水 / 點心 / 體力料理那一類全部做過 = SR (keep 永久保留，之後新增料理也不會失去)
#    活動食譜：每個活動「<活動名> • 食譜全收」SSR = 那個活動的活動料理全部做過 (keep；說明寫在活動檔 recipe_title.desc)
GOURMET_TITLES = [   # (id, 名稱, 等級, stat, 門檻, 說明)
    ("gourmet_dex_sr", "料理見習生", "SR", "dex", 10, "做過 {n} 種不同的料理，夜雀的屋台開始注意你了。"),
    ("gourmet_dex_ssr", "幻想鄉食譜收藏家", "SSR", "dex", 20, "做過 {n} 種料理，連女僕長都想借你的食譜筆記。"),
    ("gourmet_dex_ur", "幻想鄉的美食家", "UR", "dex", 30, "做過 {n} 種料理，亡靈大小姐說要跟你結拜。"),
    ("gourmet_eat_sr", "大胃王巫女", "SR", "ps:eat_stamina", 100, "吃了 {n} 個體力料理，賽錢箱的錢好像都變成你的肉了。"),
    ("gourmet_eat_ur", "白玉樓的飯友", "UR", "ps:eat_stamina", 500, "吃了 {n} 個體力料理，亡靈大小姐對你的食量刮目相看。"),
    ("gourmet_eat_lr", "比幽幽子還能吃", "LR", "ps:eat_stamina", 1000, "吃了 {n} 個體力料理，白玉樓的廚房正式把你列為天敵。"),
]
GOURMET_CATEGORY_TEXT = {   # 分類 ➔ (標籤, 名稱, 說明)
    "food": ("食物", "主食大師", "食物類的料理全部做過了，人里的食堂都跑來請教你。"),
    "drink": ("茶水", "茶道名人", "茶水類的料理全部做過了，天狗的茶園都想請你當顧問。"),
    "dessert": ("點心", "甜點職人", "點心類的料理全部做過了，琪露諾每天都跑來神社討甜點。"),
    "stamina": ("體力", "元氣料理人", "體力料理全部做過了，吃完一輪大概可以連採三天三夜。"),
}
GOURMET_EVENT_DISHES: dict[str, list[str]] = {}   # 活動 id ➔ 那個活動的活動料理 (食譜全收統計用)


def base_dish_categories() -> dict[str, str]:
    """料理圖鑑算的料理 ➔ 分類 (food / drink / dessert / stamina)：一般招待料理 + 體力料理"""
    from Database import shrine_data
    return {**{d: shrine_data.DISH_TYPES.get(d, "food") for d in shrine_data.RECIPES},
            **{d: "stamina" for d in shrine_data.STAMINA_RECIPES}}


def _add_gourmet_titles():
    from Database.events import load_events
    _add_title_rows(GOURMET_TITLES, "gourmet")
    cats = base_dish_categories()
    for cat, (label, name, desc) in GOURMET_CATEGORY_TEXT.items():
        TITLES[f"gourmet_cat_{cat}"] = {"name": name, "rarity": "SR", "group": "gourmet", "stat": f"dex_cat:{cat}",
                                        "min": sum(1 for c in cats.values() if c == cat), "keep": True,
                                        "category_label": label, "desc": desc}
    groups = {}
    GOURMET_EVENT_DISHES.clear()
    for eid, ev in load_events().items():
        dishes = list(ev.get("recipes", {})) + [d for d in ev.get("stamina_recipes", {}) if d not in ev.get("recipes", {})]
        if not dishes:
            continue
        ev_name = ev.get("name", eid)
        GOURMET_EVENT_DISHES[eid] = dishes
        desc = (ev.get("recipe_title") or {}).get("desc") or f"{ev_name}的活動料理你全部做過了。"
        TITLES[f"gourmet_{eid}_all"] = {"name": f"{ev_name} • 食譜全收", "rarity": "SSR",
                                        "group": _sub_group("gourmet", eid, ev_name, groups),
                                        "stat": f"dex_ev:{eid}", "min": len(dishes), "keep": True,
                                        "event_name": ev_name, "desc": desc}
    _insert_groups_after("gourmet", groups)


_add_gourmet_titles()


# 🌀 裏世界・📖 怪物圖鑑 (0.35.103，使用者 2026-11-21 定)：每區全收 SR、一般主題全收 UR、每個活動的活動怪全收 SSR
#    全部 keep (第一次達成就永久保留；之後某區加怪，門檻跟著變，已經拿到的不會失去)；門檻從圖鑑的分區自動算；活動的稱號也放「🌀 裏世界」這組
URA_DEX_TITLE_TEXT = {   # 主題 ➔ (名稱, 說明)；新主題沒寫的用「<主題>的征服者」
    "bamboo": ("竹林的除妖人", "迷途竹林裡的妖怪你全都交過手了，連不死之人都記得你的臉。"),
    "makai": ("魔界的觀光客", "魔界的居民你全都見過一輪，連上級惡魔都不敢再拿契約給你簽。"),
    "mountain": ("闖山的人類", "山上的天狗和河童都被你打過一輪，文文。新聞的頭條又是你。"),
    "netherworld": ("冥界的送魂人", "冥界的幽靈和亡者你全都超渡過一次，連死蝶都認得你了。"),
    "higan": ("三途河的渡河人", "彼岸的亡魂、獄卒和死神你全都打過一輪，閻魔的判決書上多了你的名字。"),
}
URA_DEX_ALL_ID = "ura_dex_all"


def _add_ura_titles():
    from Database.ura import bestiary
    base = 0
    for sec in bestiary.sections():
        n = len(sec["enemies"])
        if sec["kind"] == "zone":
            base += n
            name, desc = URA_DEX_TITLE_TEXT.get(sec["id"], (f"{sec['name']}的征服者", f"{sec['name']}的怪物你全都打倒過了。"))
            TITLES[f"ura_dex_{sec['id']}"] = {"name": name, "rarity": "SR", "group": "ura", "stat": f"ura_dex:{sec['id']}",
                                              "min": n, "keep": True, "zone_name": sec["name"], "desc": desc}
        else:
            from Database.events import load_events
            ev = load_events().get(sec["id"], {})
            desc = (ev.get("bestiary_title") or {}).get("desc") or f"{sec['name']}期間出現的怪物你全都打倒過了。"
            TITLES[f"ura_dex_{sec['id']}"] = {"name": f"{sec['name']} • 怪物全收", "rarity": "SSR",
                                              "group": "ura",   # 不另開子分組 (分組超過 25 個選單就要翻頁)
                                              "stat": f"ura_dex_ev:{sec['id']}", "min": n, "keep": True,
                                              "event_name": sec["name"], "desc": desc}
    TITLES[URA_DEX_ALL_ID] = {"name": "裏世界的博物學者", "rarity": "UR", "group": "ura", "stat": "ura_dex", "min": base,
                              "keep": True, "desc": "五個區域的怪物全部登錄進圖鑑，稗田家的人都想跟你借筆記。"}


_add_ura_titles()


def ura_stats(stats: dict) -> dict:
    """(純計算) 📖 怪物圖鑑用的統計：ura_dex = 一般主題登錄幾隻、ura_dex:<主題>、ura_dex_ev:<活動> (stats 要有 ps:ura_kill:<敵人>)"""
    from Database.ura import bestiary
    prog = bestiary.progress(bestiary.kills_from_stats({k: v for k, v in stats.items() if k.startswith("ps:ura_kill:")}))
    out = {"ura_dex": prog["base"][0]}
    for key, (done, _) in prog["sections"].items():
        kind, sid = key.split(":", 1)
        out[f"ura_dex:{sid}" if kind == "zone" else f"ura_dex_ev:{sid}"] = done
    return out


def gourmet_stats(stats: dict) -> dict:
    """(純計算) 美食家用的統計：dex = 做過幾種料理、dex_cat:<分類>、dex_ev:<活動> (stats 要有 ps:cook:<料理>)"""
    def done(d):
        return stats.get(f"ps:cook:{d}", 0) >= 1
    cats = base_dish_categories()
    out = {"dex": sum(1 for d in cats if done(d))}
    for cat in GOURMET_CATEGORY_TEXT:
        out[f"dex_cat:{cat}"] = sum(1 for d, c in cats.items() if c == cat and done(d))
    for eid, dishes in GOURMET_EVENT_DISHES.items():
        out[f"dex_ev:{eid}"] = sum(1 for d in dishes if done(d))
    return out


def derived_stats(stats: dict) -> dict:
    """從 player_stats 算出來的稱號統計 (踏破 + 美食家 + 📖 怪物圖鑑)；udm.get_title_stats 與通知 loop 都用這個"""
    return {**trek_stats(stats), **gourmet_stats(stats), **ura_stats(stats)}


def trek_stats(stats: dict) -> dict:
    """(純計算) 踏破用的統計：trek_base = 採集過的一般地點數、trek_ev:<活動> = 採集過的那個活動地點數 (stats 要有 ps:explore:<地點>)"""
    from Database import shrine_data
    out = {"trek_base": sum(1 for loc in shrine_data.LOCATIONS if stats.get(f"ps:explore:{loc}", 0) >= 1)}
    for eid, locs in TREK_EVENT_LOCATIONS.items():
        out[f"trek_ev:{eid}"] = sum(1 for loc in locs if stats.get(f"ps:explore:{loc}", 0) >= 1)
    return out


def keep_titles(unlocked: list[str]) -> list[str]:
    """已解鎖裡「第一次達成就永久保留」的稱號 (keep=True，例如踏破)；呼叫端寫進 earned_titles"""
    return [t for t in unlocked if TITLES.get(t, {}).get("keep")]


def title_group(tid: str) -> str | None:
    """稱號屬於哪一組 (TITLE_GROUPS 的鍵)；稱號有寫 group 就用它，不然看 stat 對到哪一組；找不到回傳 None"""
    t = TITLES[tid]
    if t.get("group") in TITLE_GROUPS:
        return t["group"]
    stat = t["stat"]
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
        if t.get("earned"):   # 🎪 永久獲得類 (earned_titles 表)，不看統計
            return False
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


LUCK_STAT_TEXT = {"ps:explore_good": "採集時遇到 {} 次好事件", "ps:explore_bad": "採集時遇到 {} 次壞事件",
                  "ps:fortune_5": "簽到抽到 {} 次大吉", "ps:fortune_0": "簽到抽到 {} 次凶",
                  "ps:gacha_pity": "祈願觸發 {} 次保底 (所有卡池合計)"}


def _stat_text(t: dict) -> str:
    stat = t["stat"]
    if stat in SHRINE_STAT_TEXT:
        return SHRINE_STAT_TEXT[stat].format(_number(t, t["min"]))
    if stat == "dex":   # 🍳 美食家稱號
        return f"做過 {t['min']:,} 種不同的料理 (招待料理 + 體力料理，活動料理不算)"
    if stat == "ps:eat_stamina":
        return f"累計吃 {t['min']:,} 個體力道具 (含簽到的飯糰)"
    if stat.startswith("dex_cat:"):
        return f"{t.get('category_label', stat[8:])}類的料理全部做過 ({t['min']} 道)"
    if stat.startswith("dex_ev:"):
        return f"{t.get('event_name', stat[7:])}的活動料理全部做過 ({t['min']} 道)"
    if stat == "ura_dex":   # 🌀 裏世界・📖 怪物圖鑑
        return f"一般主題的 {t['min']} 隻怪物全部登錄進圖鑑 (打倒或勸走過；活動怪不算)"
    if stat.startswith("ura_dex:"):
        return f"{t.get('zone_name', stat[8:])}的 {t['min']} 隻怪物全部打倒或勸走過"
    if stat.startswith("ura_dex_ev:"):
        return f"{t.get('event_name', stat[11:])}的 {t['min']} 隻活動怪全部打倒或勸走過"
    if stat in LUCK_STAT_TEXT:   # 🍀 運氣稱號
        return LUCK_STAT_TEXT[stat].format(f"{t['min']:,}")
    if stat.startswith("ps:tenpull_2ur:"):
        return f"在{t.get('pool_name', stat.rsplit(':', 1)[-1])}卡池一次十連出 2 張以上 UR {t['min']:,} 次"
    if stat.startswith("ps:explore:"):   # 🗺️ 足跡稱號
        return f"在{t.get('location_name', stat.rsplit(':', 1)[-1])}採集 {t['min']:,} 趟"
    if stat == "trek_base":
        return f"{t['min']} 個一般採集地點都至少採集過 1 趟 (活動地點不算)"
    if stat.startswith("trek_ev:"):
        return f"{t.get('event_name', stat[8:])}的採集地點都至少採集過 1 趟"
    if stat.startswith("ps:serve_guest:"):   # 🙏 客人稱號
        return f"招待{t.get('guest_name', stat.rsplit(':', 1)[-1])} {t['min']:,} 次"
    if stat.startswith("ps:serve_fav:"):
        return f"成功招待{t.get('guest_name', stat.rsplit(':', 1)[-1])} {t['min']:,} 次 (額外端上牠最愛的料理)"
    if stat.startswith("evq:"):   # 🎪 活動任務稱號
        return f"{t.get('event_name', stat[4:])}完成 {t['min']:,} 項活動任務"
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
            "transfer_sent": f"累計轉出 {short_number(t['min'])} 賽錢",
            "power_level": f"火力達到 {t['min'] / 10:.1f} P",
            "market_sold": f"在市場賣出 {t['min']:,} 張卡"}.get(t["stat"], f"{t['stat']} ≥ {t['min']:,}")

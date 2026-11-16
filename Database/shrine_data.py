"""
🍱 神社經營的遊戲資料 (純資料，不碰資料庫)：素材、料理配方、採集地點、雜貨店、參拜客
活動的資料在 Events/<id>.json (由 Database/events.py 讀取)，活動期間會跟這裡的資料合併。

道具的名稱 / 圖示 / 說明存在 Item.db；這裡的 MATERIAL_ITEMS / DISH_ITEMS 是寫進 Item.db 用的定義
(Item_DB_Manager.init_item_db 開機時會把缺少的素材與料理補進去)。
"""

# ---------------------------------------------------------
# 🧺 素材 (category = material)
# ---------------------------------------------------------
MATERIAL_ITEMS = [
    # 人間之里 (雜貨店也有賣)
    ("mat_rice", "稻米", "🌾", "人間之里農家種的新米。煮成飯、搗成糰子、釀成甘酒都行，是幻想鄉最萬用的食材，也是巫女最常缺的東西。"),
    ("mat_flour", "麵粉", "🥡", "雜貨店秤斤賣的麵粉。袋子上印著「開封後請盡快使用」，但大家都當作沒看到。"),
    ("mat_sugar", "砂糖", "🍬", "珍貴的白砂糖，聽說是從外面世界流進來的。點心好不好吃，全看它放得夠不夠。"),
    ("mat_seasoning", "味噌醬油", "🫙", "一罐裝的味噌和醬油組合，人里主婦的必備良品。什麼料理沾一點都會變好吃——巫女是這麼深信的。"),
    ("mat_buckwheat", "蕎麥粉", "🟤", "石臼磨出來的蕎麥粉，香氣很足。據說人里的蕎麥麵店老闆每天凌晨三點就起來磨粉。"),
    # 霧之湖
    ("mat_lamprey", "八目鰻", "🐟", "霧之湖抓到的八目鰻，滑溜溜的不好抓。夜雀聽到牠的名字會很興奮，請不要在她面前提起。"),
    ("mat_ice", "冰晶", "❄️", "霧之湖邊撿到的冰塊，冷到不太會融化。十之八九是某隻冰精隨手丟的。"),
    ("mat_spring_water", "湧泉水", "💧", "湖畔湧出的清澈泉水，冰涼又甘甜。泡茶、做汽水都用得到，就是要自己扛回神社。"),
    # 妖怪之山
    ("mat_tea_leaf", "茶葉", "🍃", "妖怪之山斜坡上採的野生茶葉。天狗說這是他們的茶園，但沒有人看過他們澆水。"),
    ("mat_cucumber", "小黃瓜", "🥒", "河童田裡長出來的小黃瓜，又直又脆。數量少了一根的話，通常可以在河邊找到嫌犯。"),
    ("mat_sweet_potato", "地瓜", "🍠", "秋神姊妹照顧過的地瓜，甜度高得不可思議。據說妹妹穰子身上也是這個香味。"),
    # 迷途竹林
    ("mat_herb", "藥草", "🌱", "竹林裡採的藥草，永遠亭的藥師拿來入藥。分不清楚哪些有毒的話，最好先問一下兔子。"),
    ("mat_chestnut", "栗子", "🌰", "竹林邊緣掉了一地的栗子，殼刺刺的。撿的時候要小心，也要小心不要迷路。"),
    # 太陽花田
    ("mat_nectar", "花蜜", "🌼", "太陽花田的花蜜，金黃濃稠、香得發膩。採的時候記得跟花田的主人打聲招呼，不然後果自負。"),
    ("mat_sunflower_seed", "葵花籽", "🌻", "向日葵成熟後留下的種子，嗑起來很涮嘴。只撿掉在地上的就好，千萬別去摘還長在花上的。"),
    # 魔法森林 (0.35.000)
    ("mat_glow_mushroom", "螢光蘑菇", "🍄", "魔法森林深處會自己發光的蘑菇，晚上不用點燈也找得到。某位黑白魔法使說能吃，但她說這話的時候眼睛也在發光。"),
    ("mat_wild_berry", "森林野莓", "🫐", "灌木叢裡結的紫色小莓果，酸酸甜甜。人偶師說這附近的莓果都被她的人偶數過了，少一顆就會被發現。"),
    ("mat_wild_vegetable", "山菜", "🥬", "森林邊緣冒出來的蕨菜和筍芽，炸成天婦羅最香。長得跟有毒的那種很像，採之前最好先找人試吃——不是你自己。"),
    # 香霖堂
    ("mat_butter", "外界奶油", "🧈", "香霖堂架上包著錫箔紙的奶油，標籤寫著看不懂的外界文字。店主說這是「非賣品」，但只要拿東西來換，什麼都可以談。"),
    ("mat_milk", "牛奶", "🥛", "玻璃瓶裝的外界牛奶，瓶蓋上印著某間牧場的乳牛。沒人知道它是怎麼流進幻想鄉的，也沒人敢看保存期限。"),
    ("mat_coffee_bean", "咖啡豆", "🫘", "烘得黑亮的外界豆子，聞起來很香、咬起來很苦。巫女試吃了一顆，結果整晚睡不著，半夜爬起來掃神社。"),
    # 冥界・白玉樓
    ("mat_sakura", "櫻花", "💮", "白玉樓庭院裡飄落的櫻花瓣，一年四季都開著。庭師每天都在掃，但花瓣掉得比她掃得快。"),
    ("mat_shiratama", "白玉粉", "🥣", "糯米磨成的細粉，搓成糰子 Q 彈滑嫩。白玉樓廚房每天的消耗量驚人，原因只有一個，那位大小姐自己也承認。"),
    ("mat_matcha", "抹茶粉", "🟩", "石臼慢慢磨出來的翠綠抹茶。庭師說要「用練劍的心情」去磨，所以白玉樓的抹茶特別細，也特別貴。"),
    # 舊地獄溫泉
    ("mat_onsen_egg", "溫泉蛋", "🥚", "泡在地獄溫泉裡自然煮熟的蛋，蛋白嫩、蛋黃半流。旁邊的牌子寫著「一人限拿三顆——地靈殿」。"),
    ("mat_oni_sake", "鬼之酒", "🏺", "鬼族自己釀的烈酒，一杯下肚，人類大概會昏三天。據說有個鬼拿著大盃喝了一整晚，盃裡的酒一滴都沒灑出來。"),
    ("mat_hell_pepper", "地獄辣椒", "🌶️", "長在灼熱地獄邊上的紅辣椒，辣到會冒煙。地獄鴉說這是她最愛的零食，大家都決定不要問她的舌頭是什麼做的。"),
]

# ---------------------------------------------------------
# 🍱 新增的招待料理 (原本 9 道在 Item_DB_Manager.DEFAULT_ITEMS)
# ---------------------------------------------------------
DISH_ITEMS = [
    ("village_soba", "人間之里蕎麥麵", "🍜", "food",
     "人里老店的手打蕎麥麵，湯頭是祖傳的。老闆堅持「吸麵要出聲才是禮貌」，所以店裡總是很吵。"),
    ("minoriko_yakiimo", "秋穰子的烤地瓜", "🍠", "food",
     "豐收之神親手烤的地瓜，剝開時金黃冒煙、甜到發光。吃完身上會染上一股地瓜香，三天散不掉。"),
    ("kappa_ramune", "河童特製彈珠汽水", "🥤", "drink",
     "河童工房出品的彈珠汽水，瓶子是自己吹的，彈珠是自己磨的。氣泡強到會從鼻子噴出來，請小口喝。"),
    ("flower_honey_tea", "太陽花田花蜜茶", "🍯", "drink",
     "用太陽花田的花蜜泡的甜茶，喝一口整個人都暖起來。據說花田的主人看到有人喝得開心，會露出不太恐怖的笑容。"),
    ("chestnut_yokan", "栗子羊羹", "🟫", "dessert",
     "一整條栗子羊羹，切開能看到滿滿的栗子顆粒。人里的和菓子師傅說，切得太薄是對羊羹的不敬。"),
    ("yuuka_seed_cookie", "向日葵籽酥", "🌻", "dessert",
     "撒滿葵花籽的酥餅，香脆又不會太甜。花田主人說這是「讓種子派上用場」的料理，至於沒用上的種子去哪了，最好別問。"),
    # ---- 0.35.000：魔法森林、香霖堂、白玉樓、舊地獄溫泉的料理 ----
    ("forest_mushroom_rice", "魔法森林蘑菇炊飯", "🍚", "food",
     "把螢光蘑菇跟米一起炊，煮好的飯會發出淡淡的光。好吃是好吃，就是吃完那天晚上嘴巴也會微微發光。"),
    ("sansai_tempura", "山菜天婦羅", "🍤", "food",
     "現採的山菜裹上薄麵衣，咬下去「喀滋」一聲。巫女說這是「不用花錢的高級料理」，畢竟山菜是自己去採的。"),
    ("onsen_egg_don", "溫泉蛋蓋飯", "🍳", "food",
     "白飯上放一顆地獄溫泉蛋，戳破蛋黃的那一刻最幸福。地底妖怪搞不懂，為什麼地上的人要特地跑下來吃一碗飯。"),
    ("hell_udon", "地獄辣味烏龍麵", "🔥", "food",
     "湯是紅的，麵是紅的，吃完臉也是紅的。招牌寫著「吃完免費」，到現在還沒有人不用付錢就走出去。"),
    ("kourin_cafe_au_lait", "香霖堂咖啡歐蕾", "☕", "drink",
     "店主說這是「外界的文明」。他自己喝了一口就加了三匙糖，文明大概也就到這裡為止。"),
    ("hakugyokurou_matcha", "白玉樓抹茶", "🍵", "drink",
     "庭師一絲不苟點出來的濃茶，泡沫細得像雲。喝之前要轉三次碗，轉錯方向的話，旁邊的半人半靈會默默把手放到刀柄上。"),
    ("sakura_tea", "櫻花茶", "🌺", "drink",
     "用鹽漬櫻花沖的茶，花瓣在杯子裡慢慢綻開。喝起來有點鹹，但很適合一邊賞花一邊發呆。"),
    ("oni_cold_sake", "鬼之冰鎮酒", "🥃", "drink",
     "鬼之酒加冰塊，鬼說這樣「比較順口」。人類喝了一樣會昏三天，只是昏得比較涼快。"),
    ("berry_milk", "野莓牛奶", "🍹", "drink",
     "搗碎的野莓混進外界牛奶，粉紫色的很可愛。人偶師說她的人偶也愛喝——人偶到底能不能喝，請不要追問。"),
    ("berry_tart", "野莓塔", "🥧", "dessert",
     "酥皮上鋪滿野莓，烤得香甜冒汁。人偶師偶爾會訂一整盒，說是要開茶會，但從來沒人見過她的客人。"),
    ("sakura_mochi", "櫻餅", "🌸", "dessert",
     "櫻花葉包著的粉紅色和菓子，一口咬下滿嘴春天。白玉樓的大小姐說，一次吃十個是「基本禮儀」。"),
    ("matcha_ice_cream", "抹茶冰淇淋", "🍨", "dessert",
     "抹茶加牛奶，再請冰精幫忙凍起來。苦甜剛好，唯一的問題是冰精每次都要拿走「一半」當報酬。"),
    ("shiratama_dango", "白玉糰子", "⚪", "dessert",
     "淋上糖蜜的白玉糰子，Q 彈得可以在碗裡跳。送到白玉樓時通常只剩空碗，到現在還查不出是在哪一段路上被吃掉的。"),
]

# ---------------------------------------------------------
# ⚡ 新的體力料理 (category = consumable, effect = {"stamina": N})：(id, 名稱, emoji, 回復量, 說明)
# 原本的 🍡 團子、🫖 司康、🍄 蘑菇湯在 Item_DB_Manager.DEFAULT_ITEMS
# ---------------------------------------------------------
STAMINA_DISH_ITEMS = [
    ("onsen_zosui", "溫泉蛋雜炊", "🍲", 60,
     "剩飯加山菜熬成粥，最後打一顆溫泉蛋進去。巫女說這是「月底的豪華大餐」，因為月底的賽錢箱通常是空的。"),
    ("hell_nabe", "地獄鍋", "🫕", 150,
     "把舊地獄採來的東西全部丟進一個鍋子裡，湯面會自己咕嘟咕嘟冒火。吃完全身發燙、力氣用不完，鬼說這才叫「暖身」。"),
]

# ---------------------------------------------------------
# 📜 料理配方：料理 ID ➔ {素材 ID: 數量}；一次做出 COOK_YIELD 份
# ---------------------------------------------------------
COOK_YIELD = 2
RECIPES = {
    # 🍚 食物
    "mystia_lamprey":   {"mat_lamprey": 1, "mat_seasoning": 1},
    "ran_inari":        {"mat_rice": 2, "mat_seasoning": 1},
    "nitori_cucumber":  {"mat_cucumber": 1, "mat_seasoning": 1},
    "village_soba":     {"mat_buckwheat": 2, "mat_seasoning": 1},
    "minoriko_yakiimo": {"mat_sweet_potato": 2},
    # 🍵 茶水
    "reimu_bancha":     {"mat_tea_leaf": 1},
    "eirin_herbal_tea": {"mat_herb": 1, "mat_tea_leaf": 1},
    "suika_amazake":    {"mat_rice": 2},
    "kappa_ramune":     {"mat_spring_water": 1, "mat_sugar": 1},
    "flower_honey_tea": {"mat_nectar": 1, "mat_tea_leaf": 1},
    # 🍮 點心
    "eientei_tsukimi_dango": {"mat_rice": 1, "mat_sugar": 1},
    "cirno_kakigori":   {"mat_ice": 1, "mat_sugar": 1},
    "alice_cookie":     {"mat_flour": 1, "mat_sugar": 1},
    "chestnut_yokan":   {"mat_chestnut": 2, "mat_sugar": 1},
    "yuuka_seed_cookie": {"mat_sunflower_seed": 1, "mat_flour": 1},
    # ---- 0.35.000 ----
    "forest_mushroom_rice": {"mat_glow_mushroom": 1, "mat_rice": 1, "mat_seasoning": 1},
    "sansai_tempura":   {"mat_wild_vegetable": 2, "mat_flour": 1},
    "onsen_egg_don":    {"mat_onsen_egg": 1, "mat_rice": 1, "mat_seasoning": 1},
    "hell_udon":        {"mat_hell_pepper": 1, "mat_flour": 1, "mat_seasoning": 1},
    "kourin_cafe_au_lait": {"mat_coffee_bean": 1, "mat_milk": 1},
    "hakugyokurou_matcha": {"mat_matcha": 1, "mat_spring_water": 1},
    "sakura_tea":       {"mat_sakura": 1, "mat_spring_water": 1},
    "oni_cold_sake":    {"mat_oni_sake": 1, "mat_ice": 1},
    "berry_milk":       {"mat_wild_berry": 1, "mat_milk": 1},
    "berry_tart":       {"mat_wild_berry": 1, "mat_flour": 1, "mat_butter": 1},
    "sakura_mochi":     {"mat_sakura": 1, "mat_shiratama": 1, "mat_sugar": 1},
    "matcha_ice_cream": {"mat_matcha": 1, "mat_milk": 1, "mat_ice": 1},
    "shiratama_dango":  {"mat_shiratama": 2, "mat_sugar": 1},
}
# 料理的種類 (food / drink / dessert)；活動料理由活動檔補上
DISH_TYPES = {
    "mystia_lamprey": "food", "ran_inari": "food", "nitori_cucumber": "food", "village_soba": "food", "minoriko_yakiimo": "food",
    "reimu_bancha": "drink", "eirin_herbal_tea": "drink", "suika_amazake": "drink", "kappa_ramune": "drink", "flower_honey_tea": "drink",
    "eientei_tsukimi_dango": "dessert", "cirno_kakigori": "dessert", "alice_cookie": "dessert", "chestnut_yokan": "dessert",
    "yuuka_seed_cookie": "dessert",
    "forest_mushroom_rice": "food", "sansai_tempura": "food", "onsen_egg_don": "food", "hell_udon": "food",
    "kourin_cafe_au_lait": "drink", "hakugyokurou_matcha": "drink", "sakura_tea": "drink", "oni_cold_sake": "drink",
    "berry_milk": "drink",
    "berry_tart": "dessert", "sakura_mochi": "dessert", "matcha_ice_cream": "dessert", "shiratama_dango": "dessert",
}

# ⚡ 體力料理：一鍋只做 STAMINA_COOK_YIELD 份，不能拿來招待 (使用者 2026-11-16 指定)
# 防體力無限循環：一天最多吃 User_DB_Manager.STAMINA_ITEM_DAILY_LIMIT 個體力道具 (含簽到的 🍙)
STAMINA_COOK_YIELD = 1
STAMINA_RECIPES = {
    "marisa_mushroom_soup": {"mat_glow_mushroom": 2, "mat_milk": 1, "mat_butter": 1},                     # 回 67
    "yuyuko_dango":     {"mat_shiratama": 2, "mat_sakura": 1, "mat_matcha": 1, "mat_sugar": 1},          # 回 120
    "sakuya_scone_tea": {"mat_flour": 2, "mat_butter": 1, "mat_milk": 1, "mat_tea_leaf": 1},             # 回 120
    "onsen_zosui":      {"mat_onsen_egg": 1, "mat_rice": 1, "mat_wild_vegetable": 1},                    # 回 60
    "hell_nabe":        {"mat_hell_pepper": 1, "mat_onsen_egg": 1, "mat_glow_mushroom": 1,
                         "mat_wild_vegetable": 1, "mat_oni_sake": 1},                                     # 回 150
}


def cook_yield(dish_id: str, rules: dict | None = None) -> int:
    """一鍋做幾份：體力料理 STAMINA_COOK_YIELD，其他 COOK_YIELD"""
    stamina = (rules or {}).get("stamina_dishes", STAMINA_RECIPES)
    return STAMINA_COOK_YIELD if dish_id in stamina else COOK_YIELD

# ---------------------------------------------------------
# 🗺️ 採集地點：每趟從 drops 平均抽 3~5 個；SPECIAL_CHANCE 機率發生事件 (好壞各半)
# 事件 effect：{"add": {素材: 數量}} 多給、{"lose": N} 少拿 N 個、{"half": True} 只剩一半、{"empty": True} 空手而回
# ---------------------------------------------------------
EXPLORE_STAMINA = 20
EXPLORE_DROPS = (3, 5)
SPECIAL_CHANCE = 0.05
LOCATIONS = {
    "village": {
        "name": "人間之里", "emoji": "🏘️", "desc": "人類的村落，雜貨店和市集什麼基本食材都有。",
        "drops": ["mat_rice", "mat_flour", "mat_sugar", "mat_seasoning", "mat_buckwheat"],
        "good": {"text": "雜貨店老闆看你是巫女，多塞了一把米給你！", "effect": {"add": {"mat_rice": 3}}},
        "bad": {"text": "一隻惡作劇的妖精從你的竹籃裡摸走了東西……", "effect": {"lose": 2}},
    },
    "misty_lake": {
        "name": "霧之湖", "emoji": "🏞️", "desc": "霧氣繚繞的湖，偶爾會有冰精出沒。",
        "drops": ["mat_lamprey", "mat_ice", "mat_spring_water"],
        "good": {"text": "琪露諾說要送你「一點點」冰晶——她數學不好，送了 5 個。", "effect": {"add": {"mat_ice": 5}}},
        "bad": {"text": "琪露諾把你連同竹籃一起凍住了，好不容易才敲開……", "effect": {"half": True}},
    },
    "youkai_mountain": {
        "name": "妖怪之山", "emoji": "🏔️", "desc": "天狗與河童的地盤，山坡上有茶園和田地。",
        "drops": ["mat_tea_leaf", "mat_cucumber", "mat_sweet_potato"],
        "good": {"text": "河童說「盟友價」，硬塞了一袋小黃瓜給你。", "effect": {"add": {"mat_cucumber": 3}}},
        "bad": {"text": "巡邏的白狼天狗把你趕下山了，只來得及撿一點東西……", "effect": {"lose": 2}},
    },
    "bamboo_forest": {
        "name": "迷途竹林", "emoji": "🎋", "desc": "一進去就容易迷路的竹林，深處是永遠亭。",
        "drops": ["mat_herb", "mat_rice", "mat_chestnut"],
        "good": {"text": "撿到月兔掉的一袋糯米，看起來是要拿去搗糰子的。", "effect": {"add": {"mat_rice": 3}}},
        "bad": {"text": "在竹林裡迷路了一整天，最後空手被兔子送了出來……", "effect": {"empty": True}},
    },
    "sunflower_field": {
        "name": "太陽花田", "emoji": "🌻", "desc": "一望無際的向日葵花田，主人是位很強的妖怪。",
        "drops": ["mat_nectar", "mat_sunflower_seed"],
        "good": {"text": "花田的主人今天心情很好，親手分了花蜜給你。", "effect": {"add": {"mat_nectar": 3}}},
        "bad": {"text": "不小心踩到一朵向日葵……被笑咪咪地「請」了出去。", "effect": {"half": True}},
    },
    # ---- 0.35.000 ----
    "magic_forest": {
        "name": "魔法森林", "emoji": "🌲", "desc": "瘴氣瀰漫的森林，魔法使和人偶師住在這裡，到處都是奇怪的蘑菇。",
        "drops": ["mat_glow_mushroom", "mat_wild_berry", "mat_wild_vegetable"],
        "good": {"text": "魔理沙把採太多的蘑菇硬塞給你，說「借你的，死了再還」。", "effect": {"add": {"mat_glow_mushroom": 3}}},
        "bad": {"text": "吸到太多瘴氣，頭昏眼花地掉了一些東西……", "effect": {"lose": 2}},
    },
    "kourindou": {
        "name": "香霖堂", "emoji": "🏚️", "desc": "魔法森林入口的古道具店，堆滿了從外界流進來的東西。",
        "drops": ["mat_butter", "mat_milk", "mat_coffee_bean"],
        "good": {"text": "店主今天心情不錯，用一本看不懂的外界雜誌換了你三瓶牛奶。", "effect": {"add": {"mat_milk": 3}}},
        "bad": {"text": "店主滔滔不絕地介紹外界道具的用途，回過神來天都黑了，只來得及拿一半……", "effect": {"half": True}},
    },
    "hakugyokurou": {
        "name": "冥界・白玉樓", "emoji": "🏯", "desc": "亡靈居住的冥界大宅，庭院的櫻花永遠盛開。",
        "drops": ["mat_sakura", "mat_shiratama", "mat_matcha"],
        "good": {"text": "亡靈大小姐說「這些就送你吧～」，然後吃掉了剩下的所有點心。", "effect": {"add": {"mat_sakura": 3}}},
        "bad": {"text": "庭師把你當成可疑人物，二話不說就拔刀……逃跑時掉了東西。", "effect": {"lose": 2}},
    },
    "old_hell_onsen": {
        "name": "舊地獄溫泉", "emoji": "♨️", "desc": "地底深處的舊地獄，有鬼族經營的溫泉街。",
        "drops": ["mat_onsen_egg", "mat_oni_sake", "mat_hell_pepper"],
        "good": {"text": "地底的鬼請你喝了一杯，順手塞了三壺酒給你。", "effect": {"add": {"mat_oni_sake": 3}}},
        "bad": {"text": "泡溫泉泡到暈過去，醒來時竹籃不見了……", "effect": {"empty": True}},
    },
}

# ---------------------------------------------------------
# 🏪 人間之里雜貨店：只賣人里的基本素材 (價格比自己採貴，但做成料理一定還是賺)
# ---------------------------------------------------------
SHOP_PRICES = {"mat_rice": 600, "mat_flour": 700, "mat_sugar": 700, "mat_seasoning": 800, "mat_buckwheat": 900}

# ---------------------------------------------------------
# 🙏 參拜客：每種妖怪有最愛的料理 (額外招待端中 ×1.5)、提示、依心情變化的點餐台詞
# 台詞的 {order} 會換成點的料理名稱；心情 ≥ 70 用 high、40~60 用 mid、≤ 30 用 low
# ---------------------------------------------------------
GUESTS = {
    "kappa": {
        "name": "河童", "emoji": "🥒", "favorite": "nitori_cucumber",
        "hint": "它的視線一直飄向綠色的、細細長長的東西……",
        "lines": {
            "high": "嘿嘿，盟友！今天想來點{order}～有的話我就幫你修賽錢箱喔！",
            "mid": "嗯……就{order}吧。快一點，我工房還有東西在燒。",
            "low": "……{order}。等太久了，我的扳手都生鏽了。",
        },
    },
    "crow_tengu": {
        "name": "鴉天狗", "emoji": "📸", "favorite": "suika_amazake",
        "hint": "它一直聞著空氣，好像在找甜甜的酒香……",
        "lines": {
            "high": "今天的特稿就決定是「博麗神社的{order}」了！趕快端上來讓我拍照～",
            "mid": "嗯，{order}。順便問一下，巫女最近有沒有什麼八卦？",
            "low": "{order}。再等下去，我就寫一篇「神社服務差勁」的報導。",
        },
    },
    "wolf_tengu": {
        "name": "白狼天狗", "emoji": "🐺", "favorite": "minoriko_yakiimo",
        "hint": "它的尾巴在某種香甜的烤物味道飄過時晃了一下……",
        "lines": {
            "high": "巡邏辛苦了……啊不是，我是說，請給我{order}！",
            "mid": "{order}，麻煩了。我只有一點休息時間。",
            "low": "……{order}。值班時間快到了，請快一點。",
        },
    },
    "fox": {
        "name": "狐妖", "emoji": "🦊", "favorite": "ran_inari",
        "hint": "它舔了舔嘴，好像很想念甜鹹的油豆腐……",
        "lines": {
            "high": "呵呵～聽說這裡有好吃的，人家想要{order}呢♪",
            "mid": "那就……{order}吧。不好吃的話，可別怪我惡作劇喔。",
            "low": "{order}。再讓我等，我就把你的神社變成狐狸窩。",
        },
    },
    "bakeneko": {
        "name": "化貓", "emoji": "🐱", "favorite": "mystia_lamprey",
        "hint": "它的鼻子一直往烤魚的方向嗅……",
        "lines": {
            "high": "喵～今天想吃{order}喵！有的話人家就乖乖的喵～",
            "mid": "{order}喵。不要太燙喔，貓舌頭喵。",
            "low": "……{order}。（尾巴不耐煩地拍著地板）",
        },
    },
    "kasa_obake": {
        "name": "唐傘妖怪", "emoji": "☂️", "favorite": "cirno_kakigori",
        "hint": "它說今天好熱，好想吃點冰涼的東西……",
        "lines": {
            "high": "嚇到了嗎？嚇到了吧！作為獎勵，請給我{order}～",
            "mid": "嗯……{order}好了。今天都沒有人被我嚇到……",
            "low": "{order}……反正大家都不理我……",
        },
    },
    "tsukumogami": {
        "name": "付喪神", "emoji": "🏮", "favorite": "reimu_bancha",
        "hint": "它說年紀大了，還是喝慣老派的東西……",
        "lines": {
            "high": "被用了一百年才終於有了身體，今天想慶祝一下，請給我{order}！",
            "mid": "{order}吧。好好用的話，我們這種道具也會很長壽的。",
            "low": "{order}……再被冷落，我就要變回普通的燈籠了。",
        },
    },
    "night_sparrow": {
        "name": "夜雀", "emoji": "🐦", "favorite": "flower_honey_tea",
        "hint": "它清了清喉嚨，說唱太多歌喉嚨好乾，想喝點甜的……",
        "lines": {
            "high": "♪～今天想點{order}～唱首歌給你聽當作謝禮吧～♪",
            "mid": "{order}。……不要給我八目鰻以外的烤鳥喔。",
            "low": "{order}！再不來我就讓你今晚看不見路！",
        },
    },
    "fairy": {
        "name": "妖精", "emoji": "🧚", "favorite": "kappa_ramune",
        "hint": "它盯著冒泡泡的東西，眼睛閃閃發亮……",
        "lines": {
            "high": "哇～神社耶！我要{order}！我要我要我要～！",
            "mid": "那個……{order}！快點快點！",
            "low": "{order}啦！好慢喔！我要去惡作劇了喔！",
        },
    },
    "oni": {
        "name": "小鬼", "emoji": "👹", "favorite": "chestnut_yokan",
        "hint": "它說配酒的話，還是厚實一點的甜點最好……",
        "lines": {
            "high": "哈哈哈！今天心情好，{order}儘管端上來！",
            "mid": "{order}。鬼不說謊，好吃的話我會再來的。",
            "low": "……{order}。鬼最討厭被晾在一邊了。",
        },
    },
}

MOOD_TIERS = (("high", 70), ("mid", 40), ("low", 0))


def mood_tier(mood: int) -> str:
    return next(tier for tier, limit in MOOD_TIERS if mood >= limit)

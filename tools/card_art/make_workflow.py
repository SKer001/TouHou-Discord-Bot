"""產生 ComfyUI 生圖工作流程 (API 格式)：python tools/card_art/make_workflow.py <角色id> <階級> <種子> <輸出.json>
模型 Animagine XL 4.0 Opt，896×1064 (接近畫窗比例)，一次 2 張，輸出到 ComfyUI/output/touhou_card/<角色id>_<階級>_*.png
選好的圖存成 images/Original/Art/<角色id>_<階級>.png，再跑 build_cards.py

階級越高畫面越強：SR = 日常、輕鬆；SSR = 施展法術、動態；UR = 招牌大招、發光特效 (仍維持明亮、淡陰影)
"""
import json
import sys

QUALITY = "masterpiece, high score, great score, absurdres"
LIGHTING = "bright colors, light shadows, clean lineart, vibrant"
COMPOSITION = "full body, centered"
NEGATIVE = (
    "lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, worst quality, "
    "low quality, low score, bad score, average score, signature, watermark, username, blurry, "
    "dark, heavy shadows, chiaroscuro, night, monochrome, gloomy, "
    "cropped, close-up, portrait, upper body, cut off feet, frame, border, multiple girls, "
    "nsfw, nude, nipples, topless, bottomless, exposed breasts"   # 使用者：些微裙底可以，但絕對不能露點
)

# 角色外觀 (Danbooru 標籤)
BASE = {
    "reimu": "1girl, hakurei reimu, touhou, red bow, hair tubes, frilled bow, detached sleeves, red and white miko outfit, red skirt, yellow ascot",
    "marisa": "1girl, kirisame marisa, touhou, witch hat, blonde hair, long hair, side braid, hair bow, black dress, white apron",
    "mima": "1girl, mima (touhou), touhou, green hair, long hair, green eyes, wizard hat, blue hat, sun symbol, blue robe, blue cape, ghost tail, no legs, holding staff, crescent staff",
    "genji": (
        "genjii (touhou), touhou, minogame, tortoise, old tortoise, land tortoise, green shell, olive brown skin, "
        "four legs, clawed feet, long white beard, bushy white eyebrows, half-closed eyes, sleepy eyes, "
        "long fluffy white tail, flowing white hair-like tail, wise, flying tortoise"
    ),
    # 里香：PC-98 角色，二創造型不統一，先用通用的工程師造型 (待使用者確認)
    "rika": (
        "1girl, rika (touhou), touhou, brown hair, short hair, brown eyes, goggles on head, "
        "white shirt, green overalls, work gloves, engineer, mechanic"
    ),
    # 千百合：夢美教授的助手，水手服、水手帽 (PC-98 角色)
    "chiyuri": (
        "1girl, kitashirakawa chiyuri, touhou, touhou (pc-98), blonde hair, short hair, blue eyes, "
        "sailor hat, white sailor shirt, blue sailor collar, blue neckerchief, white sailor dress"
    ),
    # 夢美：照官方 PC-98 立繪 (Touhou Wiki)；暗紅髮紅眼、暗紅披風 / 背心 / 長裙、白襯衫、紅領結
    "yumemi": (
        "1girl, okazaki yumemi, touhou, touhou (pc-98), dark red hair, medium hair, wavy hair, red eyes, "
        "red cape, red vest, red long skirt, white frilled hem, white shirt, puffy sleeves, red bowtie, "
        "red shoes, white socks"
    ),
    # 艾莉：照萌娘百科 / Touhou Wiki (PC-98)；金色雙螺旋捲髮、黃瞳、白色寬檐帽纏紅緞帶、深紅連衣裙白圍領、
    # 外側開刃的紅柄大鐮刀扛在肩後；神主說形象照「死神」設計
    "elly": (
        "1girl, elly (touhou), touhou, touhou (pc-98), blonde hair, drill hair, twin drills, ringlets, yellow eyes, "
        "white wide-brimmed hat, red ribbon on hat, crimson dress, long dress, white frilled collar, "
        "holding scythe, giant scythe, red scythe handle, scythe over shoulder"
    ),
    # 幻月：照萌娘百科 / Touhou Wiki (PC-98)；過肩金色直髮、金瞳、頭頂紅蝴蝶結、淡粉紅長裙 + 棕紅小背心、
    # 紅領結、背後天使般的白色羽翼 (不開心變暗、生氣帶紺色霧氣)；萌點：姊姊、翅膀、大蝴蝶結、雙子、鬼畜、天然呆
    "gengetsu": (
        "1girl, gengetsu (touhou), touhou, touhou (pc-98), blonde hair, medium hair, straight hair, yellow eyes, "
        "red hair bow, big bow, pale pink long dress, brownish red vest, red bowtie, "
        "white angel wings, feathered wings, large wings"
    ),
    # 夢月：照萌娘百科 / Touhou Wiki (PC-98)；齊頸中短金直髮、金瞳、淡粉紅女僕髮卡、粉藍相間女僕裝、大紅蝴蝶結；
    # 沒有翅膀；萌點：妹妹、女僕裝、撲克臉、高冷、傲嬌 (對姊姊)；攻擊前身上閃乳白色光芒
    "mugetsu": (
        "1girl, mugetsu (touhou), touhou, touhou (pc-98), blonde hair, short hair, bob cut, yellow eyes, "
        "pink maid headdress, maid, pink and blue maid dress, blue dress, white apron, large red bowtie"
    ),
    # 愛麗絲 (舊作，怪綺談)：照萌娘百科「愛麗絲(東方Project舊作)」/ Touhou Wiki；齊頸金色短髮、金瞳、
    # 藍緞帶髮卡、粉紅連衣裙 + 藍色圍裙、泡泡袖、白襪；萌點：蘿莉、魔法少女、魔導書、總受
    "alice": (
        "1girl, alice (touhou pc-98), touhou, touhou (pc-98), blonde hair, short hair, yellow eyes, "
        "hair ribbon, blue ribbon, hairclip, pink dress, blue apron, puffy short sleeves, white socks, petite"
    ),
    # 露易絲：照萌娘百科「露易茲(東方Project)」/ Touhou Wiki；金髮中分、兩頰細髮、後腦短辮、金瞳常眯眼、
    # 白色寬簷遮陽帽 + 紫緞帶蝴蝶結、淡紫連衣長裙、紫領巾、身材很高；萌點：遮陽帽、真·路人
    "luize": (
        "1girl, luize (touhou), touhou, touhou (pc-98), blonde hair, parted bangs, sidelocks, short ponytail, yellow eyes, "
        "squinting, white sun hat, wide-brimmed hat, purple ribbon on hat, hat bow, lavender long dress, purple neckerchief, tall"
    ),
    # 神綺：照萌娘百科 / Touhou Wiki (PC-98)；披肩銀髮、偏左紅髮帶紮的側單馬尾 (呆毛) + 兩顆球形飾品、銀白瞳、
    # 哥德風鮮紅連衣裙大 V 領 + 披肩、高領白襯衫、皮靴、背後六片巨大翅膀 (白 ➔ 紫)；萌點：女神、媽媽、呆毛
    "shinki": (
        "1girl, shinki (touhou), touhou, touhou (pc-98), silver hair, long hair, side ponytail, one side up, "
        "red hair tie, hair bobbles, white eyes, silver eyes, red dress, gothic dress, v-neck, red capelet, "
        "white high collar shirt, boots, six wings, multiple wings, large wings, mature female, goddess"
    ),
    # 雪與舞 (雙人卡)：照萌娘百科「雪 / 舞(東方Project)」/ Touhou Wiki；兩人特徵分開寫，避免互相染色
    # 雪：金髮金瞳、寬簷黑帽 + 白緞帶 + 紅球、黑白相間裙、背後大蝴蝶結、泡泡袖；元氣、火魔法、像魔理沙
    # 舞：藍髮藍瞳、白色大蝴蝶結、白色連衣裙、背後小白翼 (有時變成巨大惡魔翼)；沉默、腹黑、冰魔法
    "yuki_mai": (
        "2girls, yuki (touhou), mai (touhou), touhou, touhou (pc-98), "
        "girl on the left: blonde hair, yellow eyes, black wide-brimmed hat with white ribbon, black and white dress, puffy sleeves, "
        "girl on the right: blue hair, blue eyes, white hair bow, white dress, small white wings"
    ),    # 夢子：照萌娘百科 / Touhou Wiki (PC-98)；金色長捲髮、金瞳、白色女僕頭飾 + 髮夾 + 蝴蝶結、紅白女僕裝；
    # 萌點：女僕、飛刀 (其實是劍)、忠犬、反差萌；神綺的最高傑作，咲夜的原型
    "yumeko": (
        "1girl, yumeko (touhou), touhou, touhou (pc-98), blonde hair, long hair, wavy hair, yellow eyes, "
        "maid headdress, hair bow, hairclip, maid, red dress, white apron, red and white maid outfit, puffy sleeves"
    ),
}

# 各階級的場景；依角色個性與故事寫
SCENES = {
    # 靈夢 SR「博麗神社的巫女」：隨性的神社日常
    ("reimu", "SR"): (
        "holding gohei, floating ofuda, yin yang orb, floating in the air, relaxed smile, carefree, "
        "hakurei shrine, torii, stone stairs, cherry blossoms, petals, spring, blue sky, soft lighting, daylight, looking at viewer"
    ),
    # 靈夢 SSR「樂園的奇妙巫女」：飛在空中施展符卡，符紙與陰陽玉環繞
    ("reimu", "SSR"): (
        "flying, floating in the air, dynamic pose, holding gohei, throwing ofuda, many ofuda flying around, "
        "two yin yang orbs orbiting, glowing talismans, spell card, determined smile, wind, sleeves fluttering, "
        "hakurei shrine below, cherry blossoms swirling, petals, golden hour, sunlight, magic particles, looking at viewer"
    ),
    # 靈夢 UR「博麗大結界之守護者」：夢想封印，巨大結界與七彩光球
    ("reimu", "UR"): (
        "fantasy seal, flying high in the sky, arms spread, holding gohei, serious expression, glowing eyes, "
        "huge glowing barrier, giant magic circle behind her, rainbow light orbs, colorful energy spheres, "
        "yin yang orbs, divine aura, radiant light, light rays, bloom, ofuda circle, "
        "above the clouds, gensokyo landscape far below, epic, powerful, majestic, dynamic angle"
    ),
    # 魔理沙 SR「普通的魔法使」：騎掃帚穿過魔法森林
    ("marisa", "SR"): (
        "sitting on broom, riding broom, broom riding, flying on broom, side-saddle, broom under her, "
        "holding mini-hakkero, star (symbol), magic, sparkles, grin, energetic, wind, motion lines, "
        "forest of magic, giant mushrooms, sunlight through trees, soft lighting, daylight, looking at viewer"
    ),
    # 魔理沙 SSR「東洋的西洋魔術師」：騎掃帚高速飛行，星星彈幕與魔法陣
    ("marisa", "SSR"): (
        "sitting on broom, riding broom, flying fast on broom, speed lines, holding glowing mini-hakkero, "
        "star danmaku, many stars, magic circle, sparkles, confident grin, hat ribbon flowing, hair flowing in wind, "
        "above the forest of magic, blue sky, clouds, sunlight, dynamic angle, looking at viewer"
    ),
    # 魔理沙 UR「極光之魔彈專家」：極限火花，七彩光束從八卦爐射出
    ("marisa", "UR"): (
        "master spark, sitting on broom, riding broom, holding mini-hakkero forward with both hands, "
        "huge rainbow laser beam, massive beam of light, aurora, prismatic light, star danmaku, shooting stars, "
        "glowing magic circle, energy, intense grin, hair and hat flowing violently, "
        "flying high above the clouds, sky, light rays, bloom, epic, powerful, dynamic angle"
    ),
    # 魅魔 SR「久遠的博麗神社惡靈」：在荒廢的舊博麗神社上空悠哉飄著
    ("mima", "SR"): (
        "floating in the air, relaxed pose, mischievous smile, sitting cross-legged in the air, "
        "old hakurei shrine, overgrown, moss, tall grass, old torii, afternoon, warm sunlight, "
        "fireflies, soft lighting, daylight, looking at viewer"
    ),
    # 魅魔 SSR「祟高而冷酷的惡靈」：舉杖施法，冷笑，魔法陣與星形彈幕
    ("mima", "SSR"): (
        "floating, raising staff, casting spell, cold smile, half-closed eyes, magic circle, star danmaku, "
        "blue magic, glowing crescent, cape fluttering, wind, spectral wisps, "
        "above an old shrine, blue sky, clouds, dynamic angle, looking at viewer"
    ),
    # 魅魔 UR「憑依博麗之陰影」：靈體光焰與巨大魔法陣，氣場全開
    ("mima", "UR"): (
        "floating high in the sky, staff raised overhead, glowing eyes, confident evil smile, "
        "huge spectral flames, ghostly blue aura, giant magic circle behind her, crescent moon, sun symbol glowing, "
        "massive star danmaku, light rays, bloom, cape billowing, hair flowing, "
        "above the clouds, epic, powerful, majestic, dynamic angle"
    ),
    # 玄爺 N「飛天神龜」：老龜悠哉地飛過湖面
    ("genji", "N"): (
        "no humans, animal focus, flying over a lake, calm expression, eyes half closed, "
        "lake, reeds, water reflection, blue sky, clouds, soft lighting, daylight, peaceful"
    ),
    # 玄爺 R「靈夢的御用坐騎」：載著靈夢在空中飛行
    ("genji", "R"): (
        "hakurei reimu riding on the turtle's back, 1girl, brown hair, black hair, brown eyes, hair tubes, red bow, red and white miko outfit, detached sleeves, "
        "sitting on turtle, flying through the sky, wind, ofuda, hakurei shrine far below, "
        "cherry blossoms, petals, blue sky, clouds, daylight, cheerful"
    ),
    # 玄爺 SR「萬年修行的靈龜」：仙山雲海的神龜，靈氣環繞
    ("genji", "SR"): (
        "no humans, animal focus, ancient divine turtle, glowing golden aura, ancient runes glowing on shell, "
        "floating above a sea of clouds, chinese mountains, waterfall, mystical, sacred, "
        "light rays, bloom, sparkles, epic, majestic, dynamic angle"
    ),
    # 里香 N「戰車技師」：在草地上修理自製的花樣戰車
    ("rika", "N"): (
        "holding wrench, kneeling next to a small tank, repairing tank, oil stain on cheek, cheerful smile, "
        "toolbox, gears, bolts, flower decorations on the tank, "
        "grassy field, wildflowers, blue sky, clouds, soft lighting, daylight, looking at viewer"
    ),
    # 里香 R「邪惡工程師」：坐在花樣戰車頂上指揮，砲口射出彈幕
    ("rika", "R"): (
        "sitting on top of a tank, riding tank, flower tank, tank covered in flowers, tank cannon firing, "
        "danmaku, small glowing bullets, pointing forward, mischievous grin, smug, wind, petals flying, "
        "meadow, blue sky, sunlight, dynamic angle, looking at viewer"
    ),
    # 里香 SR「花樣戰車大師」：邪眼 Evil Eye Σ，巨大機械眼與雷射、花形彈幕
    ("rika", "SR"): (
        "evil eye sigma, giant mechanical eye floating behind her, huge robotic eyeball, metal plating, "
        "glowing red lens, laser beams, flower-shaped danmaku, many glowing bullets, "
        "standing on a flower tank, arms spread, confident laugh, goggles glowing, "
        "light rays, bloom, sparks, sky, clouds, epic, powerful, dynamic angle"
    ),
    # 千百合 N「教授助手」：在研究室抱著一疊書和文件跑來跑去
    ("chiyuri", "N"): (
        "carrying a stack of books, papers flying, running, cheerful smile, open mouth, "
        "laboratory, bookshelves, chalkboard with equations, flasks, large window, sunlight, "
        "soft lighting, daylight, looking at viewer"
    ),
    # 千百合 R「水手服科學家」：在船的甲板上做實驗
    ("chiyuri", "R"): (
        "holding glowing flask, test tube, science experiment, colorful bubbling liquid, sparkles, smug smile, wink, "
        "standing on a ship deck, railing, rope, ocean, seagulls, wind, blue sky, clouds, sunlight, "
        "dynamic angle, looking at viewer"
    ),
    # 千百合 SR「時空船之助手」：駕駛可能性空間移動船穿越時空
    ("chiyuri", "SR"): (
        "piloting a futuristic flying ship, holding ship's wheel, probability space hypervessel, "
        "glowing control panels, holographic screens, flying through a space-time portal, glowing rings, "
        "warp tunnel, stars, nebula, light streaks, determined smile, hat ribbon flowing, "
        "light rays, bloom, epic, dynamic angle"
    ),
    # 夢美 R「比較物理學教授」：在研究室黑板前自信地講課
    ("yumemi", "R"): (
        "holding pointer stick, pointing at chalkboard, chalkboard full of physics equations, lecturing, "
        "confident smile, smug, hand on hip, university lecture hall, desks, books, large window, "
        "soft lighting, daylight, looking at viewer"
    ),
    # 夢美 SR「夢幻的魔術教授」：在飛船艙內用科學儀器施展人造魔法
    ("yumemi", "SR"): (
        "casting artificial magic, glowing scientific instruments, floating mathematical symbols, "
        "glowing equations in the air, magic circle made of formulas, holographic screens, "
        "inside a futuristic ship laboratory, sci-fi machinery, cape fluttering, excited grin, "
        "sparkles, dynamic angle, looking at viewer"
    ),
    # 夢美 SSR「時空空間之主宰」：可能性空間移動船上發射十字架光束兵器
    ("yumemi", "SSR"): (
        "standing on top of a giant futuristic flying ship, arms spread, maniacal laugh, glowing red eyes, "
        "giant glowing cross-shaped laser beam behind her, cross beam weapon, massive energy cross, "
        "space-time rift, cracked sky, swirling dimensional portal, stars, light rays, bloom, "
        "cape billowing, hair flowing, epic, powerful, majestic, dynamic angle"
    ),
    # 艾莉 N「館門守衛」：悠閒(浪費光陰)的門番，在夢幻館門前扛著鐮刀打呵欠
    ("elly", "N"): (
        "standing at the mansion gate, leaning on scythe, yawning, bored, sleepy, relaxed, "
        "western mansion gate, iron gate, sunflower field, flowers, blue sky, clouds, "
        "soft lighting, daylight, from side, looking away, looking into the distance"
    ),
    # 艾莉 R「大鐮的守衛」：揮鐮擋下闖入者，掀起的地磚當彈幕
    ("elly", "R"): (
        "swinging scythe, battle stance, blocking the way, slash effect, arc of light, "
        "floor tiles flying, broken floor tiles floating, stone tiles as projectiles, determined expression, "
        "in front of a western mansion, sunflowers, wind, dynamic angle, looking at viewer"
    ),
    # 艾莉 SR「夢幻館的最後防線」：死鐮「迴旋斬擊」，鐮刀像迴旋鏢高速迴旋飛出
    ("elly", "SR"): (
        "throwing scythe, spinning scythe, scythe flying like a boomerang, circular slash trails, "
        "spinning energy rings, many floor tiles flying, high-speed danmaku, fierce grin, glowing eyes, "
        "hat ribbon flowing, dress fluttering, giant mansion behind her, sunflowers swirling, "
        "light rays, bloom, epic, powerful, dynamic angle"
    ),
    # 幻月 R「夢幻館的主人」：天然呆 ── 歪頭、手指抵下巴、困惑冒問號
    ("gengetsu", "R"): (
        "head tilt, finger to chin, puzzled, confused, airhead, question mark, blank stare, open mouth, "
        "wings folded, sitting on a garden swing, dream world garden, floating islands, pastel sky, "
        "pink clouds, flowers, soft lighting, daylight, from side"
    ),
    # 幻月 SR「金翼的夢幻魔王」：姊姊的得意氣場 ── 抱胸挑眉、翅膀張開、金色光羽
    ("gengetsu", "SR"): (
        "arms crossed, smug, raised eyebrow, proud, confident, looking down at viewer, "
        "wings spread, golden light feathers, glowing feathers falling, flying in the dream sky, "
        "beautiful danmaku, golden bullets, dreamlike clouds, sunset, light rays, bloom, dynamic angle"
    ),
    # 幻月 SSR「漆黑夢幻之支配者」：鬼畜 ── 從高處俯視狂笑，翅膀帶紺色霧氣，發狂發散彈幕 + 魔砲
    ("gengetsu", "SSR"): (
        "sadistic smile, crazy laugh, evil grin, shaded face, glowing eyes, looking down from above, "
        "wings spread wide, wings with dark blue aura, dark blue mist around wings, "
        "massive danmaku, radial bullet pattern, spiraling bullets everywhere, huge magic beam, "
        "dream world sky, swirling clouds, light rays, bloom, epic, powerful, menacing, majestic"
    ),
    # 夢月 N「夢幻館的女僕」：撲克臉端出冰淇淋甜點 (主題曲 Icemilk Magic)
    ("mugetsu", "N"): (
        "expressionless, poker face, half-closed eyes, holding a silver tray, ice cream sundae, parfait, desserts, "
        "serving, elegant pose, western mansion interior, dining room, tea set, window, "
        "soft lighting, daylight, from side"
    ),
    # 夢月 R「夢幻的仙境女僕」：傲嬌 ── 抱胸撇頭、臉紅，夢境中飄浮的茶具與甜點
    ("mugetsu", "R"): (
        "tsundere, arms crossed, looking away, turning head, pout, blush, annoyed, "
        "floating teacups, floating teapot, floating cakes and sweets, dream world, pastel sky, "
        "fluffy clouds, floating islands, sparkles, daylight"
    ),
    # 夢月 SR「惡夢之女補佐」：惡夢侵蝕 ── 面無表情放出鬼畜彈幕，乳白色光芒包身，冷冽俯視
    ("mugetsu", "SR"): (
        "expressionless, cold eyes, glowing eyes, looking down at viewer, one hand raised, "
        "milky white aura, white glowing light around body, massive danmaku, dense bullet curtain, "
        "white and blue bullets, spiraling patterns, nightmare, dream world distorting, cracked sky, "
        "light rays, bloom, epic, powerful, menacing"
    ),
    # 愛麗絲 SR「魔界的人形使」：抱著小人偶、倔強不服氣地瞪著闖入者
    ("alice", "SR"): (
        "hugging a small doll, holding doll tightly, pouting, glaring, determined, stubborn, frown, "
        "demon world town, makai, strange buildings, purple sky, floating lanterns, "
        "soft lighting, from side"
    ),
    # 愛麗絲 SSR「死之少女」：捧著究極魔導書 Grimoire of Alice 邊讀邊出招，「這次一定贏」的得意
    ("alice", "SSR"): (
        "holding open book, reading grimoire, glowing book, glowing pages flying around, magic runes, "
        "smug, confident grin, one finger raised, casting spell, magic circle under feet, "
        "sparkles, blue magic, wind, hair ribbon fluttering, dynamic angle"
    ),
    # 愛麗絲 UR「魔法之國的死靈法師」：人形 Little Legion，人偶軍團列陣、站在中央指揮
    ("alice", "UR"): (
        "commanding an army of dolls, many dolls, doll army, dolls holding lances and shields, marching dolls, "
        "puppeteer, glowing strings from fingers, arms raised, commanding pose, serious expression, glowing eyes, "
        "giant magic circle behind her, floating grimoire, necromancer, ghostly blue flames, "
        "light rays, bloom, epic, powerful, majestic"
    ),
    # 露易絲 N「魔界旅行者」：提著行李箱、壓著帽子、眨眼期待出發
    ("luize", "N"): (
        "holding suitcase, carrying luggage, hand on hat, one eye closed, wink, excited, eager smile, "
        "walking, about to leave, demon world city gate, makai, strange towers, purple sky, "
        "soft lighting, from side"
    ),
    # 露易絲 R「觀光的魔界人」：坐在行李箱上看地圖、悠哉曬太陽的路人感
    ("luize", "R"): (
        "sitting on suitcase, holding map, camera around neck, tourist, relaxed, closed eyes, content smile, "
        "basking in sunlight, sightseeing, scenic overlook, flower field, distant town, blue sky, "
        "soft lighting, daylight"
    ),
    # 露易絲 SR「邊境流浪魔導士」：魔界「旅人的彈幕」，邊境張手放出旋轉縮合的方形結界彈幕，第一次認真
    ("luize", "SR"): (
        "serious expression, eyes open, determined, arms spread, casting magic, "
        "rotating square barriers, converging squares, geometric danmaku, purple and white bullets, "
        "hat ribbon fluttering, dress fluttering in wind, standing at the border between worlds, "
        "dimensional rift, half purple demon world sky and half blue sky, light rays, bloom, epic, dynamic angle"
    ),
    # 神綺 SSR「魔界之神」：坐在魔界王座上溫柔的媽媽微笑托腮，翅膀收起，呆毛翹起 (天然呆)
    ("shinki", "SSR"): (
        "sitting on throne, chin rest, head on hand, gentle smile, motherly, kind eyes, relaxed, "
        "white wings folded, ahoge, grand throne room, demon world castle, makai, stained glass, "
        "red carpet, chandelier, warm lighting"
    ),
    # 神綺 UR「創造萬物之母」：白色六翼張開，雙手捧出生命光球，剛被創造的魔界生物與小人偶飛舞
    ("shinki", "UR"): (
        "six white wings spread, holding glowing orb of light in both hands, creating life, "
        "small glowing creatures, tiny winged demons, little dolls flying around her, sparkles, "
        "serene smile, eyes half closed, divine, holy light, floating above the demon world, "
        "makai landscape below, light rays, bloom, epic, majestic"
    ),
    # 神綺 LR「魔界宇宙之創世主」：魔界神「創世之光」；使用者指定構圖：斜角 (左下腳、右上頭)、微俯視、人物縮小，
    # 背景是大量清楚分明的彈幕 (不要糊成一團的光)，炫彩華麗
    ("shinki", "LR"): (
        "dutch angle, tilted frame, diagonal composition, from above, very wide shot, tiny figure, "
        "distant view, small character in the middle of a huge space, lots of empty space filled with danmaku, "
        "six purple wings fully spread, floating in space, pointing forward, defiant pout, glowing eyes, hair flowing, "
        "touhou danmaku, bullet hell pattern, hundreds of small glowing energy orbs, glowing star shapes, "
        "glowing rice-grain shaped magic shots, concentric rings of glowing orbs, spiral patterns of light dots, "
        "symmetrical radial danmaku, layered danmaku curtains, each orb clearly separated, sharp crisp glowing dots, "
        "rainbow colors, iridescent, prismatic, gold purple cyan magenta pink, "
        "galaxy, nebula, starry sky, cosmic background, ornate, dazzling, gorgeous, epic, godlike"
    ),
    # 雪與舞 N「魔界魔法使二人組」：冰封世界並肩，雪元氣揮手、舞在旁邊安靜面無表情
    ("yuki_mai", "N"): (
        "side by side, blonde girl waving energetically, big grin, blue-haired girl standing quietly, expressionless, "
        "frozen world, ice landscape, snow, icicles, demon world, makai, pale blue sky, soft lighting, daylight"
    ),
    # 雪與舞 R「極寒與狂舞之魔女」：雪放火焰、舞放冰晶，舞偷瞄雪帶腹黑壞笑
    ("yuki_mai", "R"): (
        "blonde girl casting fire magic, flames in hand, determined, "
        "blue-haired girl casting ice magic, ice crystals, side glance at the blonde girl, sly smile, scheming, "
        "frozen world, ice and fire, sparks and snowflakes, dynamic angle"
    ),
    # 雪與舞 SR「黑白交織之魔界禁忌」：雙魔「雪與舞的合奏」，背靠背，火紅與冰藍各半，舞的翅膀變成巨大惡魔翼
    ("yuki_mai", "SR"): (
        "back to back, blonde girl surrounded by red flames, blue-haired girl surrounded by blue ice, "
        "blue-haired girl with huge white demon wings, split composition, half red half blue, "
        "fire and ice danmaku intertwining, symmetrical forbidden magic circle, black and white magic circle, "
        "light rays, bloom, epic, powerful, dynamic angle"
    ),
    # 夢子 R「魔界的女長官」：萬魔殿裡端莊行禮，背後隱約一排劍；被誇獎時臉紅開心的忠犬反差萌
    ("yumeko", "R"): (
        "curtsey, bowing politely, hands on skirt, blushing, happy, embarrassed smile, proud, "
        "row of swords standing behind her, grand palace hall, pandemonium, demon world castle, "
        "red carpet, chandelier, warm lighting, from side"
    ),
    # 夢子 SR「飛刀之魔界女僕」：指間夾多把劍、旋身擲出，大量劍在空中排成陣列，冷靜幹練
    ("yumeko", "SR"): (
        "holding multiple swords between fingers, throwing swords, spinning, mid-throw, "
        "many swords flying in formation, sword array, calm expression, cool, composed, sharp eyes, "
        "skirt fluttering, hair flowing, palace corridor, motion blur on swords, sparkles, dynamic angle"
    ),
    # 夢子 SSR「神綺的終極刃舞」：劍技「魔界之刃」，擋在神綺王座前，數百把劍環狀放射排列
    ("yumeko", "SSR"): (
        "standing guard in front of a grand empty throne, protective stance, one arm outstretched, determined, fierce eyes, "
        "hundreds of swords floating around her, swords arranged in giant rings, radial sword formation, "
        "glowing blades, blade dance, red and gold light, petals of light, demon world throne room, "
        "light rays, bloom, epic, powerful, majestic, dynamic angle"
    ),
}

EXTRA_NEGATIVE = {
    "marisa": "standing, holding broom, carrying broom, broom on shoulder, walking",   # 不加的話常畫成拿著掃帚
    "mima": "legs, feet, shoes, socks, standing",                                       # 幽靈尾巴，沒有腳
    # 玄爺：照官方形象 (陸龜、白鬍子、白毛尾巴)；常被畫成海龜或多長翅膀
    "genji": "sea turtle, flippers, wings, sharp teeth, fangs, open mouth, snake neck, monster",
    ("genji", "N"): "1girl, human, humanization, anthropomorphic, girl",                   # 只畫烏龜
    ("genji", "R"): "humanization, anthropomorphic, turtle girl, multiple girls, white hair, grey hair, silver hair, animal ears, tail on girl",   # 白鬍子的標籤會染到靈夢
    ("genji", "SR"): "1girl, human, humanization, anthropomorphic, girl",
    "rika": "military uniform, soldier, gun, rifle, mecha, robot girl",   # 戰車標籤容易畫成軍裝或機器人
    "chiyuri": "school uniform, serafuku skirt, pleated skirt, navy",      # 水手服容易畫成學生制服
    "yumemi": "blonde hair, black dress, purple, glasses, lab coat",          # 不要替換服裝 (金髮黑衣) 或一般科學家造型
    "elly": "hood, cloak, skeleton, black robe, onozuka komachi, red hair",   # 鐮刀容易畫成死神斗篷或小町
    "gengetsu": "black wings, bat wings, demon horns, maid, maid headdress, mugetsu (touhou), multiple girls",   # 惡魔但長天使翅膀；不要畫成妹妹夢月 (女僕)
    "mugetsu": "wings, angel wings, gengetsu (touhou), multiple girls, long hair, smile",   # 夢月沒有翅膀；撲克臉
    "alice": "alice margatroid, capelet, blue dress, red hairband, hairband, mature female, long hair",   # 不要畫成新作愛麗絲 (藍裙披肩)
    "luize": "blue hair, red eyes, witch hat, short dress, child",   # 不要畫成 4 面道中的藍髮版
    "shinki": "black wings, bat wings, demon horns, two wings, child, short hair",   # 六翼女神 (不是蝙蝠翼惡魔)
    ("shinki", "LR"): ("blurry effects, smeared light, light blob, lens flare, washed out, close-up, cowboy shot, upper body, "
                       "large figure, bullet (ammunition), cartridge, gun, shell casing, missile, rocket, sword, weapon"),   # bullet 標籤會畫成子彈
    "yumeko": "izayoi sakuya, silver hair, short hair, knife, kitchen knife, blue dress",   # 不要畫成咲夜 (銀髮藍裙飛刀)
    "yuki_mai": "solo, 1girl, 3girls, kirisame marisa, witch hat with star, blue hat, white hat, black dress on blue-haired girl, blonde girl with wings",   # 兩人特徵不要互換
}


DUO = {("genji", "R"), ("yuki_mai", "N"), ("yuki_mai", "R"), ("yuki_mai", "SR")}


DUO_GIRLS = {"yuki_mai"}   # 兩個女孩同框的角色


def build(char_id: str, rarity: str, seed: int, batch: int = 2) -> dict:
    solo = "" if (char_id, rarity) in DUO else "solo"   # 有其他角色同框的不加 solo
    positive = ", ".join(filter(None, [BASE[char_id], SCENES[(char_id, rarity)], solo, COMPOSITION, LIGHTING, QUALITY]))
    # 額外的負面提示：可依角色或「角色 + 階級」設定
    base_negative = NEGATIVE.replace(", multiple girls", "") if char_id in DUO_GIRLS else NEGATIVE   # 雙人卡不能排除 multiple girls
    negative = ", ".join(filter(None, [base_negative, EXTRA_NEGATIVE.get(char_id), EXTRA_NEGATIVE.get((char_id, rarity))]))
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "animagine-xl-4.0-opt.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": positive}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 896, "height": 1064, "batch_size": batch}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
            "seed": seed, "steps": 28, "cfg": 5.0, "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0,
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": f"touhou_card/{char_id}_{rarity}"}},
    }


if __name__ == "__main__":
    char_id, rarity, seed, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(build(char_id, rarity, seed), f, ensure_ascii=False, indent=2)
    print("wrote", out)

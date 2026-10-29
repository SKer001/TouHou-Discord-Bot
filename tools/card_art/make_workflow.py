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
    "cropped, close-up, portrait, upper body, cut off feet, frame, border, multiple girls"
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
}


DUO = {("genji", "R")}


def build(char_id: str, rarity: str, seed: int, batch: int = 2) -> dict:
    solo = "" if (char_id, rarity) in DUO else "solo"   # 有其他角色同框的不加 solo
    positive = ", ".join(filter(None, [BASE[char_id], SCENES[(char_id, rarity)], solo, COMPOSITION, LIGHTING, QUALITY]))
    # 額外的負面提示：可依角色或「角色 + 階級」設定
    negative = ", ".join(filter(None, [NEGATIVE, EXTRA_NEGATIVE.get(char_id), EXTRA_NEGATIVE.get((char_id, rarity))]))
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

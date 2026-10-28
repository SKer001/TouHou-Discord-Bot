"""產生 ComfyUI 生圖工作流程 (API 格式)：python tools/card_art/make_workflow.py <角色id> <階級> <種子> <輸出.json>
模型 Animagine XL 4.0 Opt，896×1064 (接近畫窗比例)，一次 2 張，輸出到 ComfyUI/output/touhou_card/<角色id>_<階級>_*.png
選好的圖存成 images/Original/Art/<角色id>_<階級>.png，再跑 build_cards.py

階級越高畫面越強：SR = 日常、輕鬆；SSR = 施展法術、動態；UR = 招牌大招、發光特效 (仍維持明亮、淡陰影)
"""
import json
import sys

QUALITY = "masterpiece, high score, great score, absurdres"
LIGHTING = "bright colors, light shadows, clean lineart, vibrant"
COMPOSITION = "solo, full body, centered"
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
}

EXTRA_NEGATIVE = {
    "marisa": "standing, holding broom, carrying broom, broom on shoulder, walking",   # 不加的話常畫成拿著掃帚
}


def build(char_id: str, rarity: str, seed: int, batch: int = 2) -> dict:
    positive = ", ".join([BASE[char_id], SCENES[(char_id, rarity)], COMPOSITION, LIGHTING, QUALITY])
    negative = ", ".join(filter(None, [NEGATIVE, EXTRA_NEGATIVE.get(char_id)]))
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

"""
🙏 參拜客頭像的 ComfyUI 工作流程 (Q 版、上半身、簡單背景)
用法：python tools/card_art/guest_workflow.py <客人種類> <種子> <out.json>
選好的圖存成 images/Guests/<種類>.png，再跑 python tools/card_art/build_guests.py 縮圖並寫進 Thumbnails.json (guest_<種類>)
"""
import json
import sys

QUALITY = "masterpiece, high score, great score, absurdres"
STYLE = "chibi, cute, upper body, simple background, white background, smile, looking at viewer, bright colors, clean lineart"
NEGATIVE = (
    "lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, worst quality, "
    "low quality, low score, bad score, average score, signature, watermark, username, blurry, "
    "multiple girls, multiple boys, dark, horror, gore, "
    "nsfw, nude, nipples, topless, bottomless, exposed breasts"
)

# 客人外觀 (Danbooru 標籤)：一般的幻想鄉小妖怪，不是特定角色
GUESTS = {
    "kappa": "1girl, kappa, green hair, short hair, blue dress, green backpack, holding cucumber, water droplets",
    "crow_tengu": "1girl, tengu, black hair, short hair, red tokin hat, black wings, white shirt, holding camera",
    "wolf_tengu": "1girl, wolf ears, wolf tail, white hair, short hair, red tokin hat, white shirt, holding sword, holding shield",
    "fox": "1girl, fox ears, fox tail, blonde hair, long hair, kimono, mischievous smile, fox shadow puppet",
    "bakeneko": "1girl, cat ears, two tails, cat tail, brown hair, short hair, red dress, green hat, paw pose",
    "kasa_obake": "1girl, karakasa obake, purple umbrella, umbrella with tongue and eye, heterochromia, blue hair, short hair, blue vest",
    "tsukumogami": "1girl, tsukumogami, paper lantern, chouchin obake, lantern with eye, orange hair, short hair, kimono",
    "night_sparrow": "1girl, bird wings, pink hair, short hair, bird ears, winged hat, brown dress, singing, music notes",
    "fairy": "1girl, fairy, fairy wings, transparent wings, small, blonde hair, short hair, blue dress, sparkle",
    "oni": "1girl, oni, oni horns, long horns, orange hair, long hair, gourd, sake bottle, chains, grin",
    "fairy_maid": "1girl, fairy maid (touhou), maid, maid headdress, fairy wings, green hair, short hair, black dress, white apron, holding broom",
    "familiar_bat": "no humans, bat (animal), cute, chibi, red eyes, small bat, black fur, red bow, tea cup, red mist",
}


def build(kind: str, seed: int, batch: int = 4) -> dict:
    positive = ", ".join([GUESTS[kind], STYLE, QUALITY] if kind == "familiar_bat" else [GUESTS[kind], "solo", STYLE, QUALITY])
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "animagine-xl-4.0-opt.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": positive}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": NEGATIVE}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": batch}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
            "seed": seed, "steps": 26, "cfg": 5.0, "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0,
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": f"touhou_card/guest_{kind}"}},
    }


if __name__ == "__main__":
    kind, seed, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(build(kind, seed), f, ensure_ascii=False, indent=2)

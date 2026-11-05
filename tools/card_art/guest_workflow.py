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

# 客人外觀 (Danbooru 標籤)：一般的幻想鄉種族，照原作種族設定 (Touhou Wiki 種族圖鑑，2026-11-05 查)，
# 但避開同種族知名角色的招牌造型 (AVOID 放進負面提示)，免得畫成某個特定角色
GUESTS = {
    # 原作：藍色登山風服裝，背包和帽子代替龜殼與頭盤；最愛小黃瓜
    "kappa": "1girl, kappa, brown hair, short hair, blue hiking outfit, blue cap, large backpack, tools in backpack, holding cucumber",
    # 原作：擬人化烏鴉、寫報紙發報紙；頭襟、羽扇 (葉團扇)、一本齒木屐
    "crow_tengu": "1girl, crow tengu, black wings, feathered wings, tokin hat, hauchiwa, holding fan, newspaper, black hair, long hair, ponytail",
    # 原作：山的防衛部隊、巡邏
    "wolf_tengu": "1girl, white wolf tengu, wolf ears, wolf tail, white hair, long hair, tokin hat, holding sword, round shield, plain shield, guard",
    # 原作：化成妖怪的狐狸總稱
    "fox": "1girl, kitsune, fox ears, fox tail, three tails, brown hair, long hair, simple kimono, foxfire, hitodama, mischievous smile",
    # 原作：深山的貓妖；貓又兩條尾巴
    "bakeneko": "1girl, nekomata, cat ears, two tails, cat tail, black hair, short hair, yukata, paw pose",
    # 原作：被丟掉的傘化成的付喪神，傘頂一隻眼、長舌頭、傘柄當獨腳
    "kasa_obake": "1girl, karakasa obake, red umbrella, oil-paper umbrella, umbrella with single eye, umbrella tongue, hugging umbrella, black hair, short hair",
    # 原作：外觀照原本的物品；這裡是舊紙燈籠
    "tsukumogami": "1girl, tsukumogami, chouchin obake, holding paper lantern, paper lantern with single eye, lantern tongue, white hair, short hair, old kimono",
    # 民間傳說：半夜跟著人唱歌的夜雀
    "night_sparrow": "1girl, sparrow girl, bird wings, brown wings, brown hair, short hair, singing, music notes, night, stars",
    # 原作：小孩外型，翅膀像蜻蜓或蝴蝶、浮在身後
    "fairy": "1girl, fairy, fairy wings, transparent wings, dragonfly wings, small, blonde hair, short hair, blue dress, sparkle",
    # 原作：愛喝酒、宴會、比賽；角
    "oni": "1girl, oni, oni horns, two horns, black hair, short hair, sake cup, holding gourd, grin, festival",
    # 原作 (紅魔鄉 sprite)：紅色洋裝、白圍裙、翅膀，比一般妖精成熟
    "fairy_maid": "1girl, fairy maid (touhou), maid, maid headdress, fairy wings, transparent wings, red dress, white apron, puffy sleeves, holding tray",
    # 原作：沒有真正的蝙蝠角色，蝙蝠是吸血鬼變身的形態
    "familiar_bat": "no humans, bat (animal), cute, chibi, red eyes, small bat, black fur, red bow, tea cup, red mist",
}
# 要避開的知名角色特徵 (放進負面提示)
AVOID = {
    "kappa": "kawashiro nitori, twintails, blue hair, key",
    "crow_tengu": "shameimaru aya, camera, red eyes, short hair",
    "wolf_tengu": "inubashiri momiji, maple leaf, leaf print",
    "fox": "yakumo ran, nine tails, tabard, pillow hat",
    "bakeneko": "chen, green headwear, mob cap, earrings, red dress",
    "kasa_obake": "tatara kogasa, purple umbrella, heterochromia, blue hair",
    "tsukumogami": "tsukumo benben, tsukumo yatsuhashi, horikawa raiko, musical instrument",
    "night_sparrow": "mystia lorelei, pink hair, winged hat",
    "fairy": "daiyousei, side ponytail, cirno, ice wings",
    "oni": "ibuki suika, chains, orange hair, long hair, hoshiguma yuugi",
    "fairy_maid": "black dress, green hair",
    "familiar_bat": "",
}


def build(kind: str, seed: int, batch: int = 4) -> dict:
    positive = ", ".join([GUESTS[kind], STYLE, QUALITY] if kind == "familiar_bat" else [GUESTS[kind], "solo", STYLE, QUALITY])
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "animagine-xl-4.0-opt.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": positive}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": ", ".join(filter(None, [NEGATIVE, AVOID.get(kind)]))}},
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

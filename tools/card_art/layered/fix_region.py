"""局部重畫人物的一小塊 (手、臉…)，一次出 4 版：雪與舞 R 的手 (2026-11-16) 起
用 07 重繪圖的座標指定範圍，在 1024 的畫布上 SetLatentNoiseMask 重畫 (只改橢圓遮罩內)，選好的那版貼回 08 高清圖 (羽化)，再跑 hd_card char

  python fix_region.py try   <角色> <階級> <層> <cx> <cy> <rx> <ry> [種子]   層 = char / char_a / char_b；cx cy rx ry = 07 圖上的橢圓
  python fix_region.py apply <角色> <階級> <層> <第幾版 1~4>                  貼回 08 (原檔留 08x_char_hd_orig.png)，07 也一起換
提示詞：人物外觀 (LAYERS 的 base) + FIX_PROMPT；環境變數 FIX_PROMPT / FIX_DENOISE / FIX_CROP 可以換
"""
import glob
import json
import os
import shutil
import sys
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hd_card  # noqa: E402
from make_workflow import NEGATIVE, QUALITY  # noqa: E402

COMFY = os.path.expanduser(r"~\Documents\comfy\ComfyUI")
URL = "http://127.0.0.1:8188"
CROP = int(os.environ.get("FIX_CROP", "384"))     # 07 圖上裁的正方形邊長 (放大到 1024 重畫)；臉這種小地方用 192
FIX_PROMPT = os.environ.get("FIX_PROMPT", "outstretched arm, open hand, five fingers, detailed fingers, beautiful hands, "
                                          "simple background, grey background")
FIX_NEG = "bad hands, extra fingers, fused fingers, missing fingers, deformed hand, fire, flames, glowing, light, effects, orb, aura"
DENOISE = float(os.environ.get("FIX_DENOISE", "0.6"))
SUFFIX = {"char": "", "char_a": "a", "char_b": "b"}


def spec_of(char_id, rarity, layer):
    spec = hd_card.LAYERS[(char_id, rarity)]
    return spec["duo"][hd_card.DUO_LAYERS[layer]] if layer in hd_card.DUO_LAYERS else spec


def info_path(d, k):
    return os.path.join(d, f"fix_{k or 'char'}.json")


def try_fix(char_id, rarity, layer, cx, cy, rx, ry, seed=2024):
    d = hd_card.stage_dir(char_id, rarity)
    k = SUFFIX[layer]
    src = Image.open(os.path.join(d, f"07{k}_char_hires.png")).convert("RGB")
    box = (cx - CROP // 2, cy - CROP // 2, cx + CROP // 2, cy + CROP // 2)
    crop = src.crop(box).resize((1024, 1024), Image.LANCZOS)
    s = 1024 / CROP
    mask = Image.new("L", (1024, 1024), 0)
    ImageDraw.Draw(mask).ellipse(((CROP // 2 - rx) * s, (CROP // 2 - ry) * s, (CROP // 2 + rx) * s, (CROP // 2 + ry) * s), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(12))
    tag = f"{char_id}_{rarity}_{layer}_fix"
    crop.save(os.path.join(COMFY, "input", tag + ".png"))
    mask.convert("RGB").save(os.path.join(COMFY, "input", tag + "_mask.png"))
    sp = spec_of(char_id, rarity, layer)
    positive = ", ".join([sp.get("base") or hd_card.BASE[char_id], FIX_PROMPT, QUALITY])
    negative = ", ".join([NEGATIVE, FIX_NEG])
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "animagine-xl-4.0-opt.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": positive}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},
        "4": {"class_type": "LoadImage", "inputs": {"image": tag + ".png"}},
        "5": {"class_type": "LoadImage", "inputs": {"image": tag + "_mask.png"}},
        "6": {"class_type": "ImageToMask", "inputs": {"image": ["5", 0], "channel": "red"}},
        "7": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
        "8": {"class_type": "RepeatLatentBatch", "inputs": {"samples": ["7", 0], "amount": 4}},
        "9": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["8", 0], "mask": ["6", 0]}},
        "10": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["9", 0],
                                                    "seed": seed, "steps": 28, "cfg": 5.0, "sampler_name": "euler_ancestral",
                                                    "scheduler": "normal", "denoise": DENOISE}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["1", 2]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": f"touhou_card/fix/{tag}_s{seed}"}},
    }
    req = urllib.request.Request(URL + "/prompt", data=json.dumps({"prompt": wf}).encode(), headers={"Content-Type": "application/json"})
    json.load(urllib.request.urlopen(req))
    while True:   # 等佇列清空
        time.sleep(5)
        q = json.load(urllib.request.urlopen(URL + "/queue"))
        if not q["queue_running"] and not q["queue_pending"]:
            break
    outs = sorted(glob.glob(os.path.join(COMFY, "output", "touhou_card", "fix", f"{tag}_s{seed}_*.png")))[-4:]
    with open(info_path(d, k), "w", encoding="utf-8") as f:
        json.dump({"box": box, "rx": rx, "ry": ry, "crop": CROP, "outs": outs}, f, ensure_ascii=False)
    # 對照表：原圖 + 4 版
    sheet = Image.new("RGB", (512 * 5, 512), "white")
    sheet.paste(crop.resize((512, 512)), (0, 0))
    for i, p in enumerate(outs):
        sheet.paste(Image.open(p).convert("RGB").resize((512, 512)), (512 * (i + 1), 0))
    out = os.path.join(COMFY, "output", "touhou_card", "sheets", f"fix_{tag}.png")
    sheet.save(out)
    print("SHEET", out)


def apply_fix(char_id, rarity, layer, n):
    d = hd_card.stage_dir(char_id, rarity)
    k = SUFFIX[layer]
    with open(info_path(d, k), encoding="utf-8") as f:
        info = json.load(f)
    box, rx, ry, crop = info["box"], info["rx"], info["ry"], info.get("crop", 384)
    fixed = Image.open(info["outs"][n - 1]).convert("RGB")
    for name, scale in ((f"07{k}_char_hires.png", 1.0), (f"08{k}_char_hd.png", None)):
        path = os.path.join(d, name)
        im = Image.open(path).convert("RGB")
        if scale is None:
            scale = im.width / Image.open(os.path.join(d, f"07{k}_char_hires.png")).width
            backup = os.path.join(d, f"08{k}_char_hd_orig.png")
            if not os.path.exists(backup):
                shutil.copy(path, backup)
        size = round(crop * scale)
        patch = fixed.resize((size, size), Image.LANCZOS)
        m = Image.new("L", (size, size), 0)
        c, s = size / 2, size / crop
        ImageDraw.Draw(m).ellipse((c - rx * s * 1.05, c - ry * s * 1.05, c + rx * s * 1.05, c + ry * s * 1.05), fill=255)
        m = m.filter(ImageFilter.GaussianBlur(10 * s))
        im.paste(patch, (round(box[0] * scale), round(box[1] * scale)), m)
        im.save(path)
        print("✅", name)


if __name__ == "__main__":
    cmd, cid, rar, layer = sys.argv[1:5]
    if cmd == "try":
        try_fix(cid, rar, layer, *map(int, sys.argv[5:9]), *(int(x) for x in sys.argv[9:10]))
    elif cmd == "apply":
        apply_fix(cid, rar, layer, int(sys.argv[5]))
    else:
        raise SystemExit(__doc__)

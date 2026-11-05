"""
🙏 參拜客頭像：images/Original/Guests/<種類>.png (選好的原圖) ➔ images/Thumbnails/guest_<種類>.png (320×320)
並寫進 images/Thumbnails.json 的 "guest_<種類>" (網址帶 ?v= 版本號，避免 Discord 快取舊圖)
用法：python tools/card_art/build_guests.py [種類…]   (不加參數 = 全部)
"""
import glob
import hashlib
import json
import os
import sys

from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(PROJECT_ROOT, "images", "Original", "Guests")
OUT_DIR = os.path.join(PROJECT_ROOT, "images", "Thumbnails")
THUMBNAILS_JSON = os.path.join(PROJECT_ROOT, "images", "Thumbnails.json")
RAW_BASE = "https://raw.githubusercontent.com/SKer001/TouHou-Discord-Bot/refs/heads/main/images/Thumbnails/"
SIZE = 320


def main(kinds: list[str]):
    srcs = {os.path.splitext(os.path.basename(p))[0]: p for p in glob.glob(os.path.join(SRC_DIR, "*.png"))}
    kinds = kinds or sorted(srcs)
    with open(THUMBNAILS_JSON, encoding="utf-8") as f:
        thumbs = json.load(f)
    for kind in kinds:
        if kind not in srcs:
            print(f"⚠️ 找不到 {kind} 的原圖")
            continue
        img = Image.open(srcs[kind]).convert("RGB")
        side = min(img.size)
        left, top = (img.width - side) // 2, (img.height - side) // 2
        img = img.crop((left, top, left + side, top + side)).resize((SIZE, SIZE), Image.LANCZOS)
        out = os.path.join(OUT_DIR, f"guest_{kind}.png")
        img.save(out, optimize=True)
        with open(out, "rb") as f:
            ver = hashlib.sha1(f.read()).hexdigest()[:8]
        thumbs[f"guest_{kind}"] = RAW_BASE + f"guest_{kind}.png?v={ver}"
        print(f"✅ guest_{kind}.png")
    with open(THUMBNAILS_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(thumbs, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    main(sys.argv[1:])

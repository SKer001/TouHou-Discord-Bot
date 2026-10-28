"""空白卡框 empty.png：綠幕卡框 (中間 0,255,0) 去背成透明畫窗，底部陰陽玉兩側加上 TouHou / Project
python tools/card_art/make_empty.py
讀 images/Original/Thumbnails/empty_greenscreen.jpg ➔ 寫 images/Original/Thumbnails/empty.png"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
THUMB_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "images", "Original", "Thumbnails")
SRC = os.path.join(THUMB_DIR, "empty_greenscreen.jpg")
OUT = os.path.join(THUMB_DIR, "empty.png")
NAME_FONT = os.path.join(HERE, "fonts", "HarukazeSolid.ttf")
SIZE = (1748, 2432)                       # 跟 fill.png 一樣 (綠幕原圖只有 736×1024，先放大)
BOTTOM_LEFT = (230, 2118, 730, 2222)
BOTTOM_RIGHT = (1012, 2118, 1512, 2222)
TRACKING = 0.12                           # 字距 (字級的比例)
BOLD = 1                                  # 加粗 (px)
KEY_LO, KEY_HI = 30, 140                  # 綠色程度 (g - max(r, b))：低於 LO 不透明、高於 HI 全透明


def chroma_key(img):
    a = np.asarray(img).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    key = g - np.maximum(r, b)
    alpha = 1 - np.clip((key - KEY_LO) / (KEY_HI - KEY_LO), 0, 1)
    # 去綠邊：半透明邊緣的綠色壓到不超過紅藍
    a[..., 1] = np.where(key > 0, np.maximum(r, b), g)
    return Image.fromarray(np.dstack([a, alpha * 255]).astype(np.uint8), "RGBA")


def draw_spaced(img, text, box, max_size, stroke_ratio, fill, stroke_fill, size=None, ref=None):
    """加大字距、放進 box 的最大字級、置中；給 size + ref 時沿用字級，並用 ref 文字定垂直位置 (兩段字水平對齊)
    回傳實際字級"""
    d = ImageDraw.Draw(img)
    w, h = box[2] - box[0], box[3] - box[1]
    for s in ([size] if size else range(max_size, 19, -2)):
        font = ImageFont.truetype(NAME_FONT, s)
        stroke, gap = int(s * stroke_ratio), s * TRACKING
        widths = [d.textlength(ch, font=font) for ch in text]
        total = sum(widths) + gap * (len(text) - 1) + stroke * 2
        l, t, r, b = d.textbbox((0, 0), ref or text, font=font, stroke_width=stroke)
        if size or (total <= w and b - t <= h):
            break
    x = (box[0] + box[2]) / 2 - total / 2 + stroke
    y = (box[1] + box[3]) / 2 - (t + b) / 2
    for ch, cw in zip(text, widths):
        d.text((x, y), ch, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        d.text((x, y), ch, font=font, fill=fill, stroke_width=BOLD, stroke_fill=fill)   # 同色描邊加粗
        x += cw + gap
    return s


def main():
    img = Image.open(SRC).convert("RGB").resize(SIZE, Image.LANCZOS)   # 先放大再去背，邊緣比較平滑
    img = chroma_key(img)
    # Project 用 TouHou 的字級與基線，兩邊水平對齊
    size = draw_spaced(img, "TouHou", BOTTOM_LEFT, 300, 0.05, (245, 214, 140), (70, 12, 12))
    draw_spaced(img, "Project", BOTTOM_RIGHT, 300, 0.05, (245, 214, 140), (70, 12, 12), size=size, ref="TouHou")
    img.save(OUT, optimize=True)
    print("saved", OUT)


if __name__ == "__main__":
    main()

"""等級圖：從綠幕原圖 (中間 0,255,0) 去背切出 N / R / SR / SSR / UR / LR 六張透明 PNG
python tools/card_art/make_rarity.py
讀 tools/card_art/rarity_greenscreen.jpg ➔ 寫 tools/card_art/rarity/<階級>.png"""
import os
import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "rarity_greenscreen.jpg")
OUT_DIR = os.path.join(HERE, "rarity")
KEY_LO, KEY_HI = 25, 110      # 綠色程度 (g - max(r, b))：低於 LO 不透明、高於 HI 全透明
MIN_PIXELS = 5000             # 小於這個的區塊是雜點
PAD = 8


def main():
    a = np.asarray(Image.open(SRC).convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    key = g - np.maximum(r, b)
    alpha = 1 - np.clip((key - KEY_LO) / (KEY_HI - KEY_LO), 0, 1)
    a[..., 1] = np.where(key > 0, np.maximum(r, b), g)       # 去綠邊
    rgba = np.dstack([a, alpha * 255]).astype(np.uint8)

    # 每個字 (含噴濺) 連成一塊：外擴後標記連通區域，依位置排成 上 / 中 / 下 × 左 / 右
    fg = alpha > 0.5
    lab, n = ndimage.label(ndimage.binary_dilation(fg, iterations=25))
    boxes = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        if ndimage.sum(fg, lab, i) < MIN_PIXELS:
            continue
        boxes.append((i, sl))
    assert len(boxes) == 6, f"找到 {len(boxes)} 個區塊，預期 6 個"
    rows = sorted(boxes, key=lambda bx: (bx[1][0].start + bx[1][0].stop) / 2)
    ordered = []
    for k in range(3):
        ordered += sorted(rows[k * 2:k * 2 + 2], key=lambda bx: bx[1][1].start)

    os.makedirs(OUT_DIR, exist_ok=True)
    for name, (i, sl) in zip(["N", "R", "SR", "SSR", "UR", "LR"], ordered):
        part = rgba.copy()
        part[..., 3] = np.where(lab == i, part[..., 3], 0)        # 只留自己的字，鄰近的字擦掉
        img = Image.fromarray(part, "RGBA")
        l, t, rr, bb = img.getbbox()
        img = img.crop((max(0, l - PAD), max(0, t - PAD), min(img.width, rr + PAD), min(img.height, bb + PAD)))
        img.save(os.path.join(OUT_DIR, f"{name}.png"), optimize=True)
        print(name, img.size)


if __name__ == "__main__":
    main()

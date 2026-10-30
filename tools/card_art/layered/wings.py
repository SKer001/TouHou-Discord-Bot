"""翅膀層 (分層卡用)：翅膀單獨生成、去背，再用程式排在人物背後
人物和翅膀畫在同一張圖時，翅膀常被畫面切掉、顏色選取會跟同色系的頭髮衣服混在一起、去背也會把半透明的水晶切掉，
所以改成：人物不畫翅膀 + 單顆水晶 (W1 生成 → W2 放大 → W3 去背) → W4 程式排列 → W5 打光，疊在人物下面。

clean_crystal(rgba)            去背後只留最大的一塊 (地板倒影、碎屑丟掉)，裁到範圍、轉成「尖端朝上」
arrange(size, anchor, items, crystals)
    items: [{"crystal": "D", "angle": 度 (從正上方順時針，右側翅膀), "length": 長度 (px), "r0": 根部離錨點的距離 (px),
             "width": 粗細倍率 (預設 1), "mirror": True (左邊對稱也放一片)}]
    先畫的在下面；回傳 RGBA (size 大小)
"""
import math

import numpy as np
from PIL import Image
from scipy import ndimage


def clean_crystal(rgba: Image.Image) -> Image.Image:
    a = np.asarray(rgba.split()[3]) > 40
    lab, n = ndimage.label(a)
    if n == 0:
        return rgba
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    keep = lab == sizes.argmax()
    keep = ndimage.binary_dilation(keep, iterations=3)                 # 留一點邊緣的半透明
    out = rgba.copy()
    alpha = np.asarray(out.split()[3]).copy()
    alpha[~keep] = 0
    out.putalpha(Image.fromarray(alpha))
    return out.crop(out.getbbox())


def arrange(size, anchor, items, crystals) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ax, ay = anchor
    for it in items:
        sides = (1, -1) if it.get("mirror", True) else (1,)
        for side in sides:
            src = crystals[it["crystal"]]
            if side == -1:
                src = src.transpose(Image.FLIP_LEFT_RIGHT)
            L = it["length"]
            w = max(2, round(src.width * L / src.height * it.get("width", 1.0)))
            img = src.resize((w, round(L)), Image.LANCZOS)
            ang = it["angle"] * side                                     # 左邊鏡射
            rot = img.rotate(-ang, resample=Image.BICUBIC, expand=True)  # PIL 是逆時針，翅膀角度是順時針
            rad = math.radians(ang)
            dist = it.get("r0", 0) + L / 2
            cx, cy = ax + math.sin(rad) * dist, ay - math.cos(rad) * dist
            _paste_clip(layer, rot, cx, cy)
    return layer


def _paste_clip(layer, img, cx, cy):
    """超出畫布的部分裁掉再貼 (alpha_composite 不接受負座標)"""
    x, y = round(cx - img.width / 2), round(cy - img.height / 2)
    l, t = max(0, -x), max(0, -y)
    img = img.crop((l, t, img.width, img.height))
    layer.alpha_composite(img, (x + l, y + t))

"""從人物圖抓出翅膀上的水晶 (飽和的彩色小塊、不在身體範圍內)，依色相分組存成發光遮罩 (relight emissive 的 mask 檔)
python crystal_mask.py <階段資料夾> <身體多邊形 JSON>
輸出 10m_crystal_<組>.png 與 10m_crystal_preview.png"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

GROUPS = {   # 色相 (度) 範圍 ➔ 發光顏色
    "warm": ((15, 65), (255, 190, 90)),      # 橙、黃
    "green": ((65, 165), (150, 255, 160)),   # 淺綠
    "blue": ((165, 255), (120, 200, 255)),   # 天藍、藍
    "purple": ((255, 340), (230, 140, 255)), # 紫、粉
}


def build(d, body):
    im = Image.open(os.path.join(d, "10_char.png")).convert("RGBA")
    a = np.asarray(im.getchannel("A")) > 128
    hsv = np.asarray(im.convert("RGB").convert("HSV")).astype(np.float32)
    hue, sat, val = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    sel = a & (sat > 0.4) & (val > 0.3) & (hue > 15) & (hue < 340)
    bm = Image.new("L", im.size, 0); ImageDraw.Draw(bm).polygon([tuple(p) for p in body], fill=255)
    bm = np.asarray(bm) > 0
    lab, n = ndimage.label(ndimage.binary_closing(sel, iterations=2))
    keep = np.zeros(n + 1, bool)
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        comp = lab[sl] == i
        area = comp.sum()
        inside = (bm[sl] & comp).sum() / area
        yellow = 25 < np.median(hue[sl][comp]) < 65            # 只有黃色系 (頭髮、領巾) 要用身體範圍排除，其他顏色的彩色塊都是水晶
        keep[i] = area > 150 and not (yellow and inside > 0.3)
    crystal = ndimage.binary_fill_holes(keep[lab]) & a
    prev = Image.new("RGB", im.size, (30, 30, 30)); prev.paste(im.convert("RGB"), mask=im.getchannel("A"))
    pa = np.asarray(prev).copy()
    for g, ((lo, hi), col) in GROUPS.items():
        m = crystal & (((hue >= lo) & (hue < hi)) | ~sel)   # 水晶內部低飽和的亮面也算進最近的組：先粗分，再用擴張補
        m = crystal & ndimage.binary_dilation(crystal & (hue >= lo) & (hue < hi) & sel, iterations=6)
        Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(d, f"10m_crystal_{g}.png"))
        pa[m] = (pa[m] * 0.4 + np.array(col) * 0.6).astype(np.uint8)
        print(g, int(m.sum()))
    ImageDraw.Draw(p := Image.fromarray(pa)).polygon([tuple(q) for q in body], outline=(255, 0, 0), width=3)
    p.save(os.path.join(d, "10m_crystal_preview.png"))


if __name__ == "__main__":
    build(sys.argv[1], json.loads(sys.argv[2]))

"""人物打光 (分層卡用)：讓去背人物的光影符合背景
背景是大量發光彈幕 ➔ 人物是背光的：整體壓暗 + 邊緣輪廓光 (顏色取自身後的彈幕) + 身後光暈，
再讓翅膀紋路、眼睛自己發光。全部用程式算，不會改到人物的線條與細節。

relight(char, bg, opts) ➔ RGBA (同 char 大小)；char = 10_char.png，bg = 背景在同一塊畫窗範圍的裁切
opts (都可省略)：
  dark        背光壓暗程度 (0~1，人物亮度乘上 1 - dark)
  rim         輪廓光強度；rim_width 輪廓光寬度 (px)
  halo        身後光暈強度 (畫在人物外側，半透明)
  glow_red    翅膀上細紅紋路的發光強度 (只抓細線，衣服大片紅色不會發光)
  wing_dark   翅膀本體 (紫色 / 黑色部分) 再壓暗的程度
  eyes        眼睛中心座標 [(x, y), ...] (10_char.png 的座標)；eye 強度、eye_color、eye_size
  emissive    依顏色指定的發光部位清單 [{hue: (lo, hi), sat: (lo, hi), val: (lo,), color, strength, exclude: [多邊形]}]
"""
import colorsys

import numpy as np
from scipy import ndimage
from PIL import Image, ImageChops, ImageDraw, ImageFilter


def _blur(a: np.ndarray, r: float) -> np.ndarray:
    return np.asarray(Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) / 255


def _blur_rgb(a: np.ndarray, r: float) -> np.ndarray:
    return np.asarray(Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8), "RGB").filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) / 255


def _morph(mask: np.ndarray, size: int, op) -> np.ndarray:
    return np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(op(size)), dtype=np.float32) / 255


def relight(char: Image.Image, bg: Image.Image, opts: dict) -> Image.Image:
    w, h = char.size
    rgba = np.asarray(char.convert("RGBA"), dtype=np.float32) / 255
    rgb, a = rgba[..., :3], rgba[..., 3]
    # 環境光：身後背景大幅模糊 + 提亮飽和，當成每個位置照到人物的光色
    env = _blur_rgb(np.asarray(bg.convert("RGB").resize((w, h)), dtype=np.float32) / 255, w / 25)
    env = np.clip(env / max(env.max(), 1e-3) * 1.15, 0, 1)

    # 1. 背光：整體壓暗，暗部帶一點環境色
    dark = opts.get("dark", 0.25)
    out = rgb * (1 - dark) * np.array([0.93, 0.92, 1.05])           # 冷色調壓暗 (不混灰，線條保持清楚)

    # 2. 輪廓光：人物邊緣往內一圈，顏色 = 身後彈幕的顏色
    rw = opts.get("rim_width", max(2, w // 220))
    inner = np.clip(a - _morph(a, rw * 2 + 1, ImageFilter.MinFilter), 0, 1)
    rim = _blur(inner, rw * 0.8) * a * opts.get("rim", 0.9)
    out = 1 - (1 - out) * (1 - env * rim[..., None])                 # 濾色

    # 3. 翅膀紋路發光：紅色區塊裡「四周被翅膀的紫 / 黑色包圍」的才是紋路 (披肩、衣服四周是白邊或頭髮，不會被選到)
    hsv = np.asarray(Image.fromarray((rgb * 255).astype(np.uint8)).convert("HSV"), dtype=np.float32) / 255
    hue_, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    is_red = ((hue_ < 0.04) | (hue_ > 0.95)) & (sat > 0.5) & (val > 0.35) & (a > 0.5)
    wingish = (((hue_ > 0.62) & (hue_ < 0.9) & (sat > 0.35) & (val < 0.85)) | (val < 0.3)) & (a > 0.5) & ~is_red
    labels, n = ndimage.label(is_red, structure=np.ones((3, 3)))
    ring = ndimage.binary_dilation(is_red, iterations=3) & ~is_red
    owner = ndimage.maximum_filter(labels, size=7)[ring]                # 每個邊緣點屬於哪個紅色區塊
    total = np.bincount(owner, minlength=n + 1)
    hits = np.bincount(owner, weights=wingish[ring].astype(np.float64), minlength=n + 1)
    is_pattern = np.zeros(n + 1, bool)
    is_pattern[1:] = (hits[1:] / np.maximum(total[1:], 1)) > opts.get("pattern_ring", 0.6)
    pattern = _blur(is_pattern[labels].astype(np.float32), 0.8)
    # 翅膀本體 = 紫 / 黑色 + 紋路；使用者：黑色部分要暗、紅色紋路要螢亮
    wing = _blur(np.clip(wingish.astype(np.float32) + pattern, 0, 1), 1.0) * a
    out = out * (1 - wing[..., None] * opts.get("wing_dark", 0.45))  # 翅膀壓暗
    g = opts.get("glow_red", 1.0)
    core = np.array([1.0, 0.45, 0.55])                               # 紋路本身：亮粉紅、中心偏白
    out = out * (1 - pattern[..., None] * g) + core * pattern[..., None] * g
    hot = _blur(pattern, 0.6) ** 2                                   # 紋路中心更亮 (螢光感)
    out = out + hot[..., None] * np.array([0.0, 0.35, 0.3]) * g
    bloom = (_blur(pattern, w / 260) * 1.2 + _blur(pattern, w / 90) * 0.5)[..., None] * np.array([1.0, 0.2, 0.35]) * g
    out = 1 - (1 - out) * (1 - np.clip(bloom, 0, 1) * wing[..., None])   # 紋路的光只暈在翅膀上，不會染到衣服

    # 3b. 依顏色指定的發光部位 (例如琪露諾的冰晶翅膀)：hue / sat / val 範圍內、扣掉 exclude 多邊形 (頭髮等同色系部位)
    for em in opts.get("emissive", []):
        if "mask" in em:   # 手描的遮罩最準 (顏色選取會跟同色系的頭髮、衣服混在一起)
            sel = (np.asarray(em["mask"]) > 0.5) & (a > 0.5)
        else:
            sel = (a > 0.5) & (sat >= em["sat"][0]) & (sat <= em["sat"][1]) & (val >= em["val"][0])
            lo, hi = em["hue"]
            sel &= (hue_ >= lo) & (hue_ <= hi)
        if em.get("fill"):   # 補起區域內沒選到的灰色小塊 (冰晶內部的陰影)
            sel = ndimage.binary_closing(sel, structure=np.ones((5, 5)), iterations=2)
            sel = ndimage.binary_fill_holes(ndimage.binary_dilation(sel, iterations=4)) & (a > 0.5)   # 往外擴一點，邊緣灰條也包進來
        sel = sel.astype(np.float32)
        if em.get("exclude"):
            ex = Image.new("L", (w, h), 0)
            for poly in em["exclude"]:
                ImageDraw.Draw(ex).polygon([tuple(p) for p in poly], fill=255)
            sel *= 1 - np.asarray(ex, dtype=np.float32) / 255
        m = _blur(sel, 0.8)
        col = np.array(em.get("color", (120, 215, 255)), dtype=np.float32) / 255
        s_ = em.get("strength", 1.0)
        # 本體：保留顏色、往發光色偏 (body 越大越亮，用濾色提亮才不會變成灰白一片)
        tinted = np.clip(out * np.array([0.8, 1.0, 1.12]), 0, 1)
        lit = 1 - (1 - tinted) * (1 - col * em.get("body", 0.12) * s_)
        if em.get("prism"):
            # 稜鏡彩虹：色相隨位置與晶面明暗變化 (不同晶面散射不同顏色)，低飽和濾色疊上去
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            hue_map = (xx / w * 1.3 + yy / h * 0.9 + _blur(val, 2) * 1.8) % 1.0
            hsv_p = np.stack([hue_map, np.full_like(hue_map, em.get("prism_sat", 0.45)), np.ones_like(hue_map)], axis=-1)
            rainbow = np.asarray(Image.fromarray((hsv_p * 255).astype(np.uint8), "HSV").convert("RGB"), dtype=np.float32) / 255
            p = em["prism"]
            lit = lit * (1 - p) + lit * rainbow * p                       # 乘上去才看得出顏色 (濾色在近白色上幾乎沒效果)
        out = out * (1 - m[..., None]) + lit * m[..., None]
        # 邊緣：背光透過冰晶的亮邊
        ke = max(3, w // 300) | 1
        edge = _blur(np.clip(m - _morph(m, ke, ImageFilter.MinFilter), 0, 1), 1.0)
        out = 1 - (1 - out) * (1 - np.clip(edge * s_, 0, 1)[..., None] * col)
        bloom_e = (_blur(edge, w / 250) * 1.0 + _blur(m, w / 70) * 0.35)[..., None] * col * s_
        out = 1 - (1 - out) * (1 - np.clip(bloom_e, 0, 1) * m[..., None] * 0.4)
        bloom = bloom + bloom_e                                           # 光也溢到人物外 (第 5 步)

    # 4. 眼睛發光：小光點 + 柔光
    eye_layer = Image.new("RGB", (w, h), 0)
    d = ImageDraw.Draw(eye_layer)
    ec = opts.get("eye_color", (190, 160, 255))
    es = opts.get("eye_size", max(2, w // 600))
    for x, y in opts.get("eyes", []):
        d.ellipse((x - es, y - es, x + es, y + es), fill=ec)
    eye = ImageChops.add(eye_layer.filter(ImageFilter.GaussianBlur(es * 3)), eye_layer.filter(ImageFilter.GaussianBlur(es * 0.5)).point(lambda v: int(v * 0.8)))
    out = np.clip(out + np.asarray(eye, dtype=np.float32) / 255 * opts.get("eye", 0.9), 0, 1)

    # 5. 身後光暈：人物外側一圈半透明的環境色光 (翅膀從彈幕裡浮出來)
    k = max(5, w // 90) | 1
    halo_a = np.clip(_blur(_morph(a, k, ImageFilter.MaxFilter), w / 60) - a, 0, 1) * opts.get("halo", 0.55)
    glow_from_pattern = np.clip(bloom.max(axis=2) * (1 - a), 0, 1)   # 紋路的光也溢到人物外
    alpha = np.clip(a + halo_a + glow_from_pattern, 0, 1)
    extra = alpha - a                                                  # 光暈只加在人物外側
    halo_rgb = np.clip(env * halo_a[..., None] + bloom * glow_from_pattern[..., None], 0, None)
    halo_rgb = np.clip(halo_rgb / np.maximum(halo_a + glow_from_pattern, 1e-3)[..., None], 0, 1)
    premul = out * a[..., None] + halo_rgb * extra[..., None]          # 預乘 alpha 再還原
    final_rgb = np.where(alpha[..., None] > 1e-3, premul / np.maximum(alpha, 1e-3)[..., None], 0)
    res = np.dstack([np.clip(final_rgb, 0, 1), alpha])
    return Image.fromarray((res * 255).astype(np.uint8), "RGBA")

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

"""掃帚尾流 (分層卡用，魔理沙 UR 起)：從掃帚尾端往後拉出幾條彩虹光帶 + 沿路散落的星星，疊在人物下面
跟翅膀層一樣不跟人物畫在同一張圖，全部用程式畫，參數可以隨時調。

draw_trail(size, anchor, opts) ➔ RGBA (size 大小)
opts:
  angle     尾流往哪個方向拉 (度，從正上方順時針；例如掃帚往右上飛，尾流就往左下 = 225)
  length    長度 (px)
  spread    光帶散開的角度 (度)
  ribbons   光帶條數
  width     最粗處的寬度 (px，越往後越細)
  wave      光帶擺動幅度 (px)
  stars     星星數量
  hue0      彩虹起始色相 (0~1)；sat 光帶飽和度；core 中心白金色的強度
  seed
"""
import colorsys
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter


def _star(d, x, y, r, rot, color):
    pts = []
    for k in range(10):
        rr = r if k % 2 == 0 else r * 0.45
        a = rot + math.pi * k / 5
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    d.polygon(pts, fill=color)


def draw_trail(size, anchor, opts) -> Image.Image:
    w, h = size
    rnd = random.Random(opts.get("seed", 7))
    ax, ay = anchor
    L = opts.get("length", 600)
    base = math.radians(opts.get("angle", 225))
    spread = math.radians(opts.get("spread", 26))
    n = opts.get("ribbons", 5)
    width = opts.get("width", 40)
    wave = opts.get("wave", 30)
    hue0 = opts.get("hue0", 0.12)

    color = Image.new("RGB", size, 0)            # 加法混色的發光層
    alpha = Image.new("L", size, 0)
    cd, ad = ImageDraw.Draw(color), ImageDraw.Draw(alpha)
    steps = 90
    for i in range(n):
        off = (i / max(1, n - 1) - 0.5) * spread if n > 1 else 0
        ph = rnd.random() * math.tau
        ribbon_w = width * rnd.uniform(0.55, 1.0)
        prev = None
        for s in range(steps + 1):
            t = s / steps
            ang = base + off * (0.4 + 0.6 * t)                         # 越往後散得越開
            # 沿方向前進 + 垂直方向的擺動
            px = ax + math.sin(ang) * L * t
            py = ay - math.cos(ang) * L * t
            sway = math.sin(ph + t * math.tau * 1.3) * wave * t
            px += math.cos(ang) * sway
            py += math.sin(ang) * sway
            if prev:
                fade = (1 - t) ** 1.3
                ww = max(1, ribbon_w * (1 - t * 0.85))
                hue = (hue0 + i / n * 0.8 + t * 0.35) % 1
                r, g, b = colorsys.hsv_to_rgb(hue, opts.get("sat", 0.8), 1)
                col = (int(r * 255 * fade), int(g * 255 * fade), int(b * 255 * fade))
                cd.line((prev, (px, py)), fill=col, width=int(ww))
                ad.line((prev, (px, py)), fill=int(255 * fade), width=int(ww))
            prev = (px, py)
    glow = color.filter(ImageFilter.GaussianBlur(width * 0.6)).point(lambda v: int(v * 0.55))   # 外光暈淡一點，不然疊起來會白成一片
    soft = color.filter(ImageFilter.GaussianBlur(width * 0.12)).point(lambda v: int(v * 0.85))
    # 中心白金色核心：最粗的一條細線
    core = Image.new("RGB", size, 0)
    kd = ImageDraw.Draw(core)
    prev = None
    for s in range(steps + 1):
        t = s / steps
        px, py = ax + math.sin(base) * L * t * 0.8, ay - math.cos(base) * L * t * 0.8
        if prev:
            f = (1 - t) ** 2 * opts.get("core", 1.0) * 0.6
            kd.line((prev, (px, py)), fill=(int(255 * f), int(235 * f), int(170 * f)), width=max(1, int(width * 0.18 * (1 - t))))
        prev = (px, py)
    core = core.filter(ImageFilter.GaussianBlur(width * 0.12))

    # 星星：沿著尾流散落，越後面越稀、越小
    stars = Image.new("RGB", size, 0)
    sd = ImageDraw.Draw(stars)
    for _ in range(opts.get("stars", 70)):
        t = rnd.random() ** 1.6
        ang = base + rnd.uniform(-1, 1) * spread * (0.4 + 0.6 * t) * 0.7
        px = ax + math.sin(ang) * L * t + rnd.uniform(-1, 1) * width
        py = ay - math.cos(ang) * L * t + rnd.uniform(-1, 1) * width
        r_ = width * rnd.uniform(0.25, 0.6) * (1 - t * 0.6)
        r, g, b = colorsys.hsv_to_rgb(rnd.random(), 0.6, 1)
        f = (1 - t * 0.5) * 0.85
        _star(sd, px, py, r_, rnd.random() * math.tau, (int(r * 255 * f), int(g * 255 * f), int(b * 255 * f)))
    stars = ImageChops.add(stars.filter(ImageFilter.GaussianBlur(width * 0.15)), stars)

    rgb = ImageChops.add(ImageChops.add(glow, soft), ImageChops.add(core, stars))
    # alpha = 亮度 (加法光：越亮越不透明)，讓它可以像一般圖層一樣疊在背景上
    lum = np.asarray(rgb, dtype=np.float32).max(axis=2)
    a = np.clip(lum / 255 * 1.4, 0, 1)
    arr = np.asarray(rgb, dtype=np.float32) / np.maximum(a[..., None], 1e-3)
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    out.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    return out

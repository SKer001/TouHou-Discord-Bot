"""程式畫的彈幕層 (分層合成用)：環狀光球、螺旋米粒彈、星形彈、散落小玉 (freeze 風格再加六角冰晶；stars 風格全部換成星彈，魔理沙用)
draw_danmaku(size, seed, style) 回傳 (glow 光暈 RGB, core 清楚彈體 RGBA)；
座標以 1344 寬的畫窗為基準，依 size 等比放大，所以可以直接畫在 4 倍高清的畫布上。"""
import colorsys
import math
import random

from PIL import Image, ImageDraw, ImageFilter

BASE_W = 1344


def draw_danmaku(size, seed=1, style="rainbow", scale=None, density=1.0):
    """scale：彈幕大小的倍率 (預設 = 寬 / 1344)；畫滿整張卡時傳畫窗的倍率，彈幕大小才會跟畫窗版一樣
    density：彈幕留下的比例 (0~1)；隨機略過，排列的圖樣不變"""
    W, H = size
    s = scale or W / BASE_W                            # 放大倍率 (所有尺寸、距離都乘上)
    rnd = random.Random(seed)
    keep = random.Random(seed + 99)                    # 決定哪些彈要略過 (另外一組亂數，不影響排列)
    frozen = 0.8 if style == "freeze" else 0.0         # freeze：8 成彈幕凍成白色冰晶

    def hue(h, sat=0.85, v=1.0):
        if rnd.random() < frozen:
            return rnd.choice([(235, 248, 255), (200, 235, 255), (170, 220, 255), (255, 255, 255)])
        r, g, b = colorsys.hsv_to_rgb(h % 1, sat, v)
        return int(r * 255), int(g * 255), int(b * 255)

    glow = Image.new("RGB", (W, H), 0)
    core = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd, cd = ImageDraw.Draw(glow), ImageDraw.Draw(core)

    def orb(x, y, r, color):
        if keep.random() > density:
            return
        gd.ellipse((x - r * 2.2, y - r * 2.2, x + r * 2.2, y + r * 2.2), fill=color)
        cd.ellipse((x - r, y - r, x + r, y + r), fill=color + (255,), outline=(255, 255, 255, 255), width=max(1, int(r * 0.25)))
        cd.ellipse((x - r * 0.45, y - r * 0.45, x + r * 0.45, y + r * 0.45), fill=(255, 255, 255, 255))

    def rice(x, y, ang, L, color):
        if keep.random() > density:
            return
        pts = []
        for t in range(24):
            a = 2 * math.pi * t / 24
            px, py = math.cos(a) * L, math.sin(a) * L * 0.38
            pts.append((x + px * math.cos(ang) - py * math.sin(ang), y + px * math.sin(ang) + py * math.cos(ang)))
        gd.polygon([(x + (px - x) * 1.8, y + (py - y) * 1.8) for px, py in pts], fill=color)
        cd.polygon(pts, fill=color + (255,), outline=(255, 255, 255, 255), width=max(1, int(s)))
        cd.polygon([(x + (px - x) * 0.45, y + (py - y) * 0.45) for px, py in pts], fill=(255, 255, 255, 255))

    def star(x, y, r, rot, color):
        if keep.random() > density:
            return
        pts = []
        for k in range(10):
            rr = r if k % 2 == 0 else r * 0.45
            a = rot + math.pi * k / 5
            pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
        gd.polygon([(x + (px - x) * 1.7, y + (py - y) * 1.7) for px, py in pts], fill=color)
        cd.polygon(pts, fill=color + (255,), outline=(255, 255, 255, 255), width=max(1, int(s)))

    def crystal(x, y, r, rot, color):
        if keep.random() > density:
            return
        for k in range(6):
            a = rot + math.pi * k / 3
            ex, ey = x + r * math.cos(a), y + r * math.sin(a)
            gd.line((x, y, ex, ey), fill=color, width=max(2, int(r * 0.5)))
            cd.line((x, y, ex, ey), fill=color + (255,), width=max(2, int(r * 0.18)))
            for side in (-1, 1):
                mx, my = x + r * 0.55 * math.cos(a), y + r * 0.55 * math.sin(a)
                b = a + side * 0.7
                cd.line((mx, my, mx + r * 0.35 * math.cos(b), my + r * 0.35 * math.sin(b)), fill=color + (255,), width=max(1, int(r * 0.12)))
        cd.ellipse((x - r * 0.2, y - r * 0.2, x + r * 0.2, y + r * 0.2), fill=(255, 255, 255, 255))

    def inside(x, y):
        return -40 * s < x < W + 40 * s and -40 * s < y < H + 40 * s

    # 幾個發射中心的同心環光球
    for cx, cy in [(W * 0.62, H * 0.36), (W * 0.25, H * 0.2), (W * 0.82, H * 0.78), (W * 0.2, H * 0.72)]:
        base_h = rnd.random()
        for ring in range(4 + rnd.randint(0, 2)):
            n = 18 + ring * 6
            rad = (90 + ring * 95 + rnd.randint(-10, 10)) * s
            r = (9 + ring * 1.5) * s
            off = rnd.random() * math.pi
            for k in range(n):
                a = off + 2 * math.pi * k / n
                x, y = cx + rad * math.cos(a), cy + rad * math.sin(a)
                if inside(x, y):
                    if style == "stars":   # 魔理沙：環狀彈也是星彈
                        star(x, y, r * 1.7, a, hue(base_h + k / n))
                    else:
                        orb(x, y, r, hue(base_h + k / n))
    # 螺旋米粒彈
    for arm in range(7):
        cx, cy = W * 0.6, H * 0.4
        for t in range(60):
            rad = (40 + t * 22) * s
            a = arm * 2 * math.pi / 7 + t * 0.09
            x, y = cx + rad * math.cos(a), cy + rad * math.sin(a)
            if inside(x, y):
                if style == "stars":
                    star(x, y, 15 * s, a, hue(arm / 7 + t / 90, 0.7))
                else:
                    rice(x, y, a + 0.35, 17 * s, hue(arm / 7 + t / 90, 0.7))
    if style == "freeze":
        for _ in range(140):
            crystal(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(10, 26) * s, rnd.random() * 6, (215, 240, 255))
    # 星形彈與散落小玉
    for _ in range(260 if style == "stars" else 110):
        star(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(9, 17) * s, rnd.random() * 6, hue(rnd.random(), 0.6))
    for _ in range(260):
        orb(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(3, 6) * s, hue(rnd.random(), 0.5))

    return glow.filter(ImageFilter.GaussianBlur(9 * s)), core

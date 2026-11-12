"""程式畫的彈幕層 (分層合成用)：環狀光球、螺旋米粒彈、星形彈、散落小玉 (freeze 風格再加六角冰晶；stars 風格全部換成星彈，魔理沙用；seal 風格是七彩大光球 + 紅白符札 + 小陰陽玉，靈夢用；starbow 是紅色大玉環 + 七彩水晶米粒彈 + 七彩菱形水晶彈雨，芙蘭「星弓破碎」用；scarlet 全部紅色系大玉 + 米粒彈，蕾米莉亞用；elements 是七曜色 (日月火水木金土) 大玉環 + 七色螺旋 + 七個元素魔法陣，帕秋莉用)
draw_danmaku(size, seed, style) 回傳 (glow 光暈 RGB, core 清楚彈體 RGBA)；
座標以 1344 寬的畫窗為基準，依 size 等比放大，所以可以直接畫在 4 倍高清的畫布上。"""
import colorsys
import math
import random

from PIL import Image, ImageDraw, ImageFilter

BASE_W = 1344
# 同心環發射中心 (寬高比例)：每種數量都上下、左右錯開，螺旋彈中心在 (0.6, 0.4)
ORIGIN_SETS = {
    1: [(0.4, 0.62)],
    2: [(0.24, 0.24), (0.76, 0.74)],
    3: [(0.22, 0.2), (0.8, 0.5), (0.25, 0.8)],
    4: [(0.62, 0.36), (0.25, 0.2), (0.82, 0.78), (0.2, 0.72)],
}


def draw_danmaku(size, seed=1, style="rainbow", scale=None, density=1.0, origins=4):
    """scale：彈幕大小的倍率 (預設 = 寬 / 1344)；畫滿整張卡時傳畫窗的倍率，彈幕大小才會跟畫窗版一樣
    density：彈幕留下的比例 (0~1)；隨機略過，排列的圖樣不變
    origins：同心環的發射中心數 (最多 4；加上螺旋彈的中心 = 總共 origins + 1 個原點)"""
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

    def ofuda(x, y, ang, L, color):
        """符札彈：紅白長方形，沿行進方向"""
        if keep.random() > density:
            return
        hw, hh = L * 0.28, L * 0.5
        ca, sa = math.cos(ang), math.sin(ang)
        def rect(k):
            return [(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in ((-hh * k, -hw * k), (hh * k, -hw * k), (hh * k, hw * k), (-hh * k, hw * k))]
        gd.polygon(rect(1.7), fill=color)
        cd.polygon(rect(1.0), fill=(255, 250, 245, 255), outline=color + (255,), width=max(1, int(L * 0.12)))
        cd.polygon(rect(0.35), fill=color + (255,))

    def yinyang(x, y, r, rot):
        """小陰陽玉"""
        if keep.random() > density:
            return
        gd.ellipse((x - r * 1.8, y - r * 1.8, x + r * 1.8, y + r * 1.8), fill=(200, 60, 70))
        deg = math.degrees(rot)
        cd.ellipse((x - r, y - r, x + r, y + r), fill=(250, 250, 250, 255), outline=(255, 255, 255, 255))
        cd.pieslice((x - r, y - r, x + r, y + r), deg, deg + 180, fill=(200, 30, 40, 255))
        for side, colr in ((1, (250, 250, 250, 255)), (-1, (200, 30, 40, 255))):
            cx2, cy2 = x + side * r / 2 * math.cos(rot), y + side * r / 2 * math.sin(rot)
            cd.ellipse((cx2 - r / 2, cy2 - r / 2, cx2 + r / 2, cy2 + r / 2), fill=colr)
            dot = (200, 30, 40, 255) if side == 1 else (250, 250, 250, 255)
            cd.ellipse((cx2 - r / 7, cy2 - r / 7, cx2 + r / 7, cy2 + r / 7), fill=dot)

    STARBOW = [(255, 60, 70), (255, 150, 40), (255, 230, 60), (90, 230, 110), (70, 210, 255), (90, 110, 255), (200, 90, 255)]   # 芙蘭翅膀的七色水晶

    SCARLET = [(235, 20, 40), (255, 60, 80), (200, 0, 30), (255, 120, 150), (180, 20, 90)]   # 蕾米莉亞：深紅、緋紅、粉紅、暗紫紅

    # 帕秋莉七曜：日、月、火、水、木、金、土
    ELEMENTS = [(255, 190, 60), (210, 225, 255), (255, 70, 50), (60, 150, 255), (80, 220, 110), (255, 235, 140), (200, 140, 70)]

    def magic_circle(x, y, R, color):
        """元素魔法陣：雙圓 + 七芒星 + 頂點小玉 (帕秋莉；是主題，不受 density 略過)"""
        w =max(2, int(R * 0.035))
        for k, rr in ((1.0, R), (0.82, R * 0.82)):
            gd.ellipse((x - rr * 1.05, y - rr * 1.05, x + rr * 1.05, y + rr * 1.05), outline=color, width=w * 4)
            cd.ellipse((x - rr, y - rr, x + rr, y + rr), outline=color + (235,), width=w)
        pts = [(x + R * 0.82 * math.cos(-math.pi / 2 + 2 * math.pi * k / 7), y + R * 0.82 * math.sin(-math.pi / 2 + 2 * math.pi * k / 7)) for k in range(7)]
        for k in range(7):   # 七芒星 {7/3}
            a, b = pts[k], pts[(k + 3) % 7]
            gd.line((*a, *b), fill=color, width=w * 3)
            cd.line((*a, *b), fill=color + (220,), width=w)
        for px, py in pts:
            r = R * 0.07
            cd.ellipse((px - r, py - r, px + r, py + r), fill=color + (255,), outline=(255, 255, 255, 255), width=max(1, int(r * 0.3)))
        r = R * 0.16
        gd.ellipse((x - r * 2, y - r * 2, x + r * 2, y + r * 2), fill=color)
        cd.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 255))

    def shard(x, y, L, ang, color):
        """菱形水晶彈：細長菱形，沿行進方向"""
        if keep.random() > density:
            return
        ca, sa = math.cos(ang), math.sin(ang)
        def dia(k):
            return [(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in ((L * k, 0), (0, L * 0.32 * k), (-L * k, 0), (0, -L * 0.32 * k))]
        gd.polygon(dia(1.8), fill=color)
        cd.polygon(dia(1.0), fill=color + (255,), outline=(255, 255, 255, 255), width=max(1, int(s)))
        cd.polygon(dia(0.4), fill=(255, 255, 255, 255))

    def inside(x, y):
        return -40 * s < x < W + 40 * s and -40 * s < y < H + 40 * s

    # 幾個發射中心的同心環光球：依數量挑上下平均分布的位置 (不要只取前幾個，否則全擠在上半部)
    for cx, cy in [(W * fx, H * fy) for fx, fy in ORIGIN_SETS[min(max(1, origins), 4)]]:
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
                    elif style == "seal":  # 靈夢：夢想封印的七彩大光球
                        orb(x, y, r * 1.6, hue(base_h + k / n, 0.7))
                    elif style == "scarlet":   # 蕾米莉亞：深紅大玉環 (每四顆夾一顆粉紅)
                        orb(x, y, r * 1.5, SCARLET[3] if k % 4 == 0 else SCARLET[ring % 3])
                    elif style == "starbow":   # 芙蘭：紅色大玉環 (每隔幾顆夾一顆七彩)
                        orb(x, y, r * 1.2, STARBOW[k % 7] if k % 3 == 0 else (230, 25, 45))
                    elif style == "elements":   # 帕秋莉：一圈一種元素色的大玉
                        orb(x, y, r * 1.4, ELEMENTS[(ring + int(base_h * 7)) % 7])
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
                elif style == "seal":   # 靈夢：紅白符札
                    ofuda(x, y, a + 0.35, 22 * s, (215, 35, 45))
                elif style == "scarlet":   # 蕾米莉亞：紅色米粒彈
                    rice(x, y, a + 0.35, 19 * s, SCARLET[arm % 5])
                elif style == "starbow":   # 芙蘭：一條手臂一種水晶色
                    rice(x, y, a + 0.35, 17 * s, STARBOW[arm])
                elif style == "elements":   # 帕秋莉：七條手臂 = 七曜
                    rice(x, y, a + 0.35, 18 * s, ELEMENTS[arm])
                else:
                    rice(x, y, a + 0.35, 17 * s, hue(arm / 7 + t / 90, 0.7))
    if style == "seal":
        for _ in range(60):
            yinyang(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(9, 16) * s, rnd.random() * math.tau)
    if style == "starbow":   # 星弓破碎：七彩菱形水晶彈從上往下斜落
        for _ in range(170):
            shard(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(18, 30) * s, math.pi / 2 + rnd.uniform(-0.35, 0.35), rnd.choice(STARBOW))
    if style == "elements":   # 七曜魔法陣：每種元素一個，散在畫面上下 (避開正中間的人物)
        spots = [(0.18, 0.12), (0.82, 0.16), (0.12, 0.42), (0.88, 0.48), (0.2, 0.78), (0.8, 0.84), (0.5, 0.06)]
        for (fx, fy), color in zip(spots, ELEMENTS):
            magic_circle(W * fx + rnd.uniform(-30, 30) * s, H * fy + rnd.uniform(-30, 30) * s, rnd.uniform(95, 140) * s, color)
    if style == "freeze":
        for _ in range(140):
            crystal(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(10, 26) * s, rnd.random() * 6, (215, 240, 255))
    # 星形彈與散落小玉
    red = style == "scarlet"   # 蕾米莉亞：散落的彈也都是紅色系
    palette = SCARLET if red else ELEMENTS if style == "elements" else None   # 帕秋莉：散落的彈用七曜色
    for _ in range(260 if style == "stars" else 110):
        star(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(9, 17) * s, rnd.random() * 6, rnd.choice(palette) if palette else hue(rnd.random(), 0.6))
    for _ in range(260):
        orb(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(3, 6) * s, rnd.choice(palette) if palette else hue(rnd.random(), 0.5))

    return glow.filter(ImageFilter.GaussianBlur(9 * s)), core

"""神綺 LR 合成：AI 宇宙背景 + 程式畫的大量彈幕 + 去背人物 (縮小、斜角)
python compose_lr.py <背景> <人物去背 png> <輸出> [種子] [人物高度比例] [傾斜角度]"""
import colorsys
import math
import random
import sys
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

W, H = 1344, 1596                      # 跟卡面畫窗同比例
bg_path, char_path, out_path = sys.argv[1:4]
seed = int(sys.argv[4]) if len(sys.argv) > 4 else 1
char_scale = float(sys.argv[5]) if len(sys.argv) > 5 else 0.62
tilt = float(sys.argv[6]) if len(sys.argv) > 6 else -12     # 負 = 順時針：頭往右上、腳往左下
rnd = random.Random(seed)


def hue(h, s=0.85, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


# 1. 背景：AI 宇宙圖填滿、稍微壓暗讓彈幕更跳
bg = Image.open(bg_path).convert("RGB")
scale = max(W / bg.width, H / bg.height)
bg = bg.resize((int(bg.width * scale) + 1, int(bg.height * scale) + 1), Image.LANCZOS)
bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
bg = ImageEnhance.Brightness(bg).enhance(0.62)

# 2. 彈幕層 (加法混色)：環狀光球、螺旋米粒彈、星形彈、散落小玉
glow = Image.new("RGB", (W, H), 0)     # 外圈光暈
core = Image.new("RGBA", (W, H), (0, 0, 0, 0))   # 清楚的彈體
gd, cd = ImageDraw.Draw(glow), ImageDraw.Draw(core)


def orb(x, y, r, color):
    gd.ellipse((x - r * 2.2, y - r * 2.2, x + r * 2.2, y + r * 2.2), fill=color)
    cd.ellipse((x - r, y - r, x + r, y + r), fill=color + (255,), outline=(255, 255, 255, 255), width=max(1, int(r * 0.25)))
    cd.ellipse((x - r * 0.45, y - r * 0.45, x + r * 0.45, y + r * 0.45), fill=(255, 255, 255, 255))


def rice(x, y, ang, L, color):
    """米粒彈：沿行進方向的細長橢圓"""
    pts = []
    for t in range(16):
        a = 2 * math.pi * t / 16
        px, py = math.cos(a) * L, math.sin(a) * L * 0.38
        pts.append((x + px * math.cos(ang) - py * math.sin(ang), y + px * math.sin(ang) + py * math.cos(ang)))
    gd.polygon([(x + (px - x) * 1.8, y + (py - y) * 1.8) for px, py in pts], fill=color)
    cd.polygon(pts, fill=color + (255,), outline=(255, 255, 255, 255))
    inner = [(x + (px - x) * 0.45, y + (py - y) * 0.45) for px, py in pts]
    cd.polygon(inner, fill=(255, 255, 255, 255))


def star(x, y, r, rot, color):
    pts = []
    for k in range(10):
        rr = r if k % 2 == 0 else r * 0.45
        a = rot + math.pi * k / 5
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    gd.polygon([(x + (px - x) * 1.7, y + (py - y) * 1.7) for px, py in pts], fill=color)
    cd.polygon(pts, fill=color + (255,), outline=(255, 255, 255, 255))


# 2-1. 幾個發射中心的同心環光球
centers = [(W * 0.62, H * 0.36), (W * 0.25, H * 0.2), (W * 0.82, H * 0.78), (W * 0.2, H * 0.72)]
for ci, (cx, cy) in enumerate(centers):
    base_h = rnd.random()
    for ring in range(4 + rnd.randint(0, 2)):
        n = 18 + ring * 6
        rad = 90 + ring * 95 + rnd.randint(-10, 10)
        r = 9 + ring * 1.5
        off = rnd.random() * math.pi
        for k in range(n):
            a = off + 2 * math.pi * k / n
            x, y = cx + rad * math.cos(a), cy + rad * math.sin(a)
            if -40 < x < W + 40 and -40 < y < H + 40:
                orb(x, y, r, hue(base_h + k / n))

# 2-2. 螺旋米粒彈 (從中心往外甩)
for arm in range(7):
    cx, cy = W * 0.6, H * 0.4
    h0 = arm / 7
    for t in range(60):
        rad = 40 + t * 22
        a = arm * 2 * math.pi / 7 + t * 0.09
        x, y = cx + rad * math.cos(a), cy + rad * math.sin(a)
        if -40 < x < W + 40 and -40 < y < H + 40:
            rice(x, y, a + 0.35, 17, hue(h0 + t / 90, 0.7))

# 2-3. 星形彈與散落小玉
for _ in range(110):
    star(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(9, 17), rnd.random() * 6, hue(rnd.random(), 0.6))
for _ in range(260):
    orb(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(3, 6), hue(rnd.random(), 0.5))

glow = glow.filter(ImageFilter.GaussianBlur(9))
canvas = ImageChops.add(bg, ImageEnhance.Brightness(glow).enhance(0.9))
canvas = canvas.convert("RGBA")
canvas.alpha_composite(core)

# 3. 人物：縮小、斜角、放在畫面中央偏下 (傾斜後頭在右上、腳在左下)
ch = Image.open(char_path).convert("RGBA")
ch = ch.crop(ch.getbbox())
target_h = int(H * char_scale)
ch = ch.resize((int(ch.width * target_h / ch.height), target_h), Image.LANCZOS)
ch = ch.rotate(tilt, resample=Image.BICUBIC, expand=True)
# 人物後面加一圈柔光，讓翅膀從彈幕裡跳出來
halo = ch.split()[3].filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(18))
halo_layer = Image.new("RGBA", ch.size, (255, 230, 255, 0))
halo_layer.putalpha(halo.point(lambda v: int(v * 0.55)))
x = (W - ch.width) // 2
y = int(H * 0.53 - ch.height / 2)
canvas.alpha_composite(halo_layer, (x, y))
canvas.alpha_composite(ch, (x, y))
canvas.convert("RGB").save(out_path)
print("saved", out_path)

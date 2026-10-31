"""環繞人物的物件圈 (分層卡用，靈夢 UR 的陰陽玉起)：單顆素材排成一圈斜橢圓，分成「人物後面」和「人物前面」兩層
跟翅膀、尾流一樣不跟人物畫在同一張圖；後半圈稍小稍暗 (遠)，前半圈蓋在人物前面 (近)，做出立體環繞的感覺。

ring(size, anchor, orb, opts) ➔ (後層 RGBA, 前層 RGBA)
opts:
  count   顆數
  rx, ry  橢圓半徑 (px)；ry 小 = 從側面看的扁圈
  tilt    整圈傾斜角度 (度，順時針)
  size    最近那顆的直徑 (px)；depth 遠近大小差 (0~1)
  phase   起始角度 (度)，轉動整圈讓陰陽玉避開臉
  spin    每顆自轉角度的差 (度)，看起來不會一模一樣
  link    陰陽玉之間的結界光環亮度 (0 = 不畫)；link_color
"""
import math

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter


def ring(size, anchor, orb: Image.Image, opts):
    back = Image.new("RGBA", size, (0, 0, 0, 0))
    front = Image.new("RGBA", size, (0, 0, 0, 0))
    ax, ay = anchor
    n = opts.get("count", 8)
    rx, ry = opts.get("rx", 400), opts.get("ry", 120)
    tilt = math.radians(opts.get("tilt", 0))
    base = opts.get("size", 120)
    depth = opts.get("depth", 0.35)
    phase = math.radians(opts.get("phase", 0))

    def pos(a):
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        return (ax + ex * math.cos(tilt) - ey * math.sin(tilt), ay + ex * math.sin(tilt) + ey * math.cos(tilt))

    # 結界光環：整圈橢圓，後半畫在後層、前半畫在前層
    if opts.get("link", 0.6) > 0:
        col = opts.get("link_color", (255, 120, 140))
        for layer, front_half in ((back, False), (front, True)):
            ring_img = Image.new("RGB", size, 0)
            d = ImageDraw.Draw(ring_img)
            pts = [pos(2 * math.pi * k / 240) for k in range(241)]
            for k in range(240):
                is_front = math.sin(2 * math.pi * (k + 0.5) / 240) > 0
                if is_front == front_half:
                    d.line((pts[k], pts[k + 1]), fill=col, width=max(2, int(base * 0.06)))
            ring_img = ImageChops.add(ring_img.filter(ImageFilter.GaussianBlur(base * 0.15)),
                                      ImageEnhance.Brightness(ring_img).enhance(0.7))
            ring_img = ImageEnhance.Brightness(ring_img).enhance(opts.get("link", 0.6))
            glow = ring_img.convert("RGBA")
            glow.putalpha(ring_img.convert("L"))
            layer.alpha_composite(glow)

    # 陰陽玉：由遠到近畫 (遠的先畫)
    items = []
    for i in range(n):
        a = phase + 2 * math.pi * i / n
        z = math.sin(a)                                                 # 1 = 最近 (前)、-1 = 最遠 (後)
        items.append((z, a, i))
    for z, a, i in sorted(items):
        d = base * (1 - depth * (1 - z) / 2)
        img = orb.resize((max(2, round(d)), max(2, round(d * orb.height / orb.width))), Image.LANCZOS)
        img = img.rotate(opts.get("spin", 37) * i, resample=Image.BICUBIC)
        if z < 0:                                                       # 後面的稍微暗一點
            rgb = ImageEnhance.Brightness(img.convert("RGB")).enhance(0.8 + 0.2 * (1 + z))
            rgb.putalpha(img.split()[3])
            img = rgb
        x, y = pos(a)
        target = front if z > 0 else back
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.paste(img, (round(x - img.width / 2), round(y - img.height / 2)), img)
        target.alpha_composite(canvas)
    return back, front

"""動態卡面 (GIF)：python tools/card_art/animate.py <角色> <階級> [效果] <輸出.gif> [--size 寬]
(省略效果時用 RARITY_EFFECTS；整批產生由 build_cards.py 呼叫 save_animation)
效果 (可用 + 組合，例如 laser+sparkle)：
  laser    雷射：從發射點掃出多道彩色光束 (只在畫窗內，卡框蓋在上面)
  sparkle  閃爍：畫窗內隨機的四角星光一明一滅
  shine    閃光：一道斜向白光掃過整張卡 (含卡框，卡牌閃卡的感覺)
  holo     雷射：以閃光為基礎，掃過的光帶變成雷射全息彩虹 (隨角度變色 + 金屬細紋 + 亮片)，像塗層蓋在整張卡表面
           (外框全強度、畫窗 HOLO_WINDOW 倍，人物仍看得清楚)
發射點預設是畫窗內最亮的地方 (例如手上的光球)，可用 --origin x,y (畫窗比例 0~1) 指定。

做法：完整卡面只算一次，每一格只在上面疊效果層 (加法混色)，所以很快。
"""
import colorsys
import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from card import EMPTY, render_card  # noqa: E402

FRAMES = 32            # 32 格 × 90ms ≈ 2.9 秒一輪 (使用者 2026-10-30：慢一點、頭尾銜接)
HOLO_STRENGTH = 0.85   # 雷射塗層整體強度 (0~1；使用者 2026-10-30：減少一點點)
HOLO_WINDOW = 0.75     # 畫窗 (人物) 上的雷射強度 = 外框的幾倍
DURATION = 90          # 每格毫秒


def hue(h, s=0.6, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def find_origin(card: Image.Image, window: np.ndarray) -> tuple[float, float]:
    """畫窗中最亮的區域 (模糊後取最大值)，當成雷射的發射點"""
    lum = np.asarray(card.convert("L").filter(ImageFilter.GaussianBlur(card.width / 40)), dtype=np.float32)
    lum = lum * (window > 0.5)
    y, x = np.unravel_index(np.argmax(lum), lum.shape)
    return float(x), float(y)


def laser_layer(size, origin, t, seed=1):
    """多道從 origin 射出的雷射，角度隨 t 掃動、粗細脈動"""
    w, h = size
    rnd = random.Random(seed)
    glow = Image.new("RGB", size, 0)
    core = Image.new("RGB", size, 0)
    gd, cd = ImageDraw.Draw(glow), ImageDraw.Draw(core)
    ox, oy = origin
    length = math.hypot(w, h)
    n = 7
    for k in range(n):
        base = 2 * math.pi * k / n + rnd.random() * 0.3
        ang = base + 0.35 * math.sin(2 * math.pi * t + k)               # 左右掃動
        width = (0.009 + 0.006 * math.sin(2 * math.pi * (t * 2) + k * 1.7)) * w
        color = hue(k / n + t * 0.3, 0.55)
        ex, ey = ox + length * math.cos(ang), oy + length * math.sin(ang)
        sx, sy = ox + w * 0.06 * math.cos(ang), oy + w * 0.06 * math.sin(ang)   # 從光球外緣開始，人物臉部不被蓋白
        gd.line((sx, sy, ex, ey), fill=color, width=int(width * 3))
        cd.line((sx, sy, ex, ey), fill=color, width=max(1, int(width)))
        cd.line((sx, sy, ex, ey), fill=(255, 255, 255), width=max(1, int(width * 0.35)))
    # 發射點的光球
    r = w * (0.025 + 0.008 * math.sin(2 * math.pi * t * 3))
    gd.ellipse((ox - r * 1.6, oy - r * 1.6, ox + r * 1.6, oy + r * 1.6), fill=(200, 170, 220))
    cd.ellipse((ox - r * 0.5, oy - r * 0.5, ox + r * 0.5, oy + r * 0.5), fill=(255, 255, 255))
    glow = glow.filter(ImageFilter.GaussianBlur(w / 70))
    return ImageChops.add(glow.point(lambda v: int(v * 0.45)), core.filter(ImageFilter.GaussianBlur(w / 500)).point(lambda v: int(v * 0.85)))


def sparkle_layer(size, window, t, seed=2, count=26):
    """四角星光：每顆有自己的相位，一明一滅"""
    w, h = size
    rnd = random.Random(seed)
    ys, xs = np.where(window > 0.5)
    layer = Image.new("RGB", size, 0)
    d = ImageDraw.Draw(layer)
    for i in range(count):
        j = rnd.randrange(len(xs))
        x, y = float(xs[j]), float(ys[j])
        phase = rnd.random()
        a = max(0.0, math.sin(2 * math.pi * (t + phase)))        # 0~1，一半時間是暗的
        if a <= 0.02:
            continue
        r = w * rnd.uniform(0.018, 0.04) * a
        color = tuple(int(c * a) for c in hue(rnd.random(), 0.25))
        thin = max(1, r * 0.12)
        d.polygon([(x, y - r), (x + thin, y), (x, y + r), (x - thin, y)], fill=color)
        d.polygon([(x - r, y), (x, y + thin), (x + r, y), (x, y - thin)], fill=color)
        d.ellipse((x - thin * 1.6, y - thin * 1.6, x + thin * 1.6, y + thin * 1.6), fill=(255, 255, 255))
    return ImageChops.add(layer.filter(ImageFilter.GaussianBlur(w / 300)), layer)


def shine_layer(size, t):
    """斜向白光帶掃過整張卡；t 在 0~0.6 掃過、之後休息"""
    w, h = size
    layer = Image.new("RGB", size, 0)
    p = t / 0.6
    if p > 1:
        return layer
    d = ImageDraw.Draw(layer)
    band = w * 0.22
    cx = -band + (w + h * 0.6 + band * 2) * p              # 光帶中心沿 x 移動 (斜 30 度)
    for k, alpha in ((1.0, 70), (0.45, 140), (0.15, 230)):
        half = band * k / 2
        d.polygon([(cx - half, 0), (cx + half, 0), (cx + half - h * 0.6, h), (cx - half - h * 0.6, h)],
                  fill=(alpha, alpha, alpha))
    return layer.filter(ImageFilter.GaussianBlur(w / 50))


def holo_layer(size, frame_mask, t, strength=1.0, seed=3):
    """雷射全息框：斜向光帶掃過 (同 shine 的時間軸)，光帶內是隨位置與時間變化的彩虹 × 金屬紋理，只套在外框"""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    x, y = xx / w, yy / h
    # 掃光位置：t 0~0.7 從左上掃到右下，之後回到淡淡的底光 (起點、終點都在卡外，循環時不會跳)
    p = t / 0.7
    diag = x * 0.75 + y * 0.45                                   # 斜向座標 0~1.2
    center = -0.55 + 2.3 * min(p, 1.0)
    band = np.exp(-((diag - center) ** 2) / (2 * 0.16 ** 2)) if p <= 1 else np.zeros_like(diag)
    base = 0.3 + 0.1 * math.sin(2 * math.pi * t)                # 不掃光時框上也有淡淡彩虹 (像傾斜卡片)
    intensity = np.clip(base + band, 0, 1)
    # 彩虹：色相隨位置與「角度」(t) 變化
    hue_map = (diag * 2.2 + y * 0.6 - t) % 1.0                  # 一輪剛好轉一圈色相，頭尾銜接
    hsv = np.stack([hue_map, np.full_like(hue_map, 0.65), np.ones_like(hue_map)], axis=-1)
    rgb = np.asarray(Image.fromarray((hsv * 255).astype(np.uint8), "HSV").convert("RGB"), dtype=np.float32) / 255
    # 金屬紋理：細斜紋 + 固定亮片
    lines = 0.75 + 0.25 * np.sin((x * 0.6 - y) * h * 0.9)
    rnd = np.random.default_rng(seed)
    flakes = (rnd.random((h, w)) > 0.985).astype(np.float32)
    flakes = np.asarray(Image.fromarray((flakes * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)), dtype=np.float32) / 255
    texture = np.clip(lines + flakes * (band + 0.3) * 2.0, 0, 2.0)
    amount = (intensity * texture * strength * frame_mask)[..., None]
    return rgb, np.clip(amount, 0, 1)


# 各階級的動態效果 (使用者 2026-10-29 指定)：SSR 白色閃光、UR 雷射塗層、LR 雷射塗層 + 閃爍
RARITY_EFFECTS = {"SSR": ["shine"], "UR": ["holo"], "LR": ["holo", "sparkle"]}


def save_animation(card: Image.Image, effects: list[str], out: str, size_w: int = 460, origin_frac=None) -> int:
    """把完整卡面 (1748×2432) 做成循環 GIF，回傳檔案大小 (bytes)"""
    size = (size_w, int(size_w * card.height / card.width))
    card = card.resize(size, Image.LANCZOS)
    # 畫窗遮罩 = 卡框透明的地方
    frame_alpha = np.asarray(Image.open(EMPTY).split()[3].resize(size, Image.LANCZOS), dtype=np.float32) / 255
    window = 1 - frame_alpha
    window_img = Image.fromarray((window * 255).astype(np.uint8))
    if origin_frac:
        ys, xs = np.where(window > 0.5)
        origin = (xs.min() + (xs.max() - xs.min()) * origin_frac[0], ys.min() + (ys.max() - ys.min()) * origin_frac[1])
    else:
        origin = find_origin(card, window)

    frames = []
    for f in range(FRAMES):
        t = f / FRAMES
        inside = Image.new("RGB", size, 0)
        if "laser" in effects:
            inside = ImageChops.add(inside, laser_layer(size, origin, t))
        if "sparkle" in effects:
            inside = ImageChops.add(inside, sparkle_layer(size, window, t))
        frame = card.copy()
        frame = Image.composite(ImageChops.add(frame, inside), frame, window_img)
        if "holo" in effects:
            coat = frame_alpha + window * HOLO_WINDOW                # 塗層蓋滿整張卡，畫窗稍淡
            rgb, amount = holo_layer(size, coat, t, strength=HOLO_STRENGTH)
            a = np.asarray(frame, dtype=np.float32) / 255
            screen = 1 - (1 - a) * (1 - rgb)                       # 濾色：彩虹浮在表面
            mixed = a * (1 - amount) + screen * amount
            frame = Image.fromarray((np.clip(mixed, 0, 1) * 255).astype(np.uint8))
        if "shine" in effects:
            frame = ImageChops.add(frame, shine_layer(size, t))
        frames.append(frame)
    # 所有格共用一組調色盤，避免每格顏色各自量化造成閃爍
    sheet = Image.new("RGB", (size[0], size[1] * 4))
    for i, f in enumerate(frames[::max(1, len(frames) // 4)][:4]):
        sheet.paste(f, (0, size[1] * i))
    palette = sheet.quantize(colors=255, method=Image.MEDIANCUT)
    frames = [f.quantize(palette=palette, dither=Image.FLOYDSTEINBERG) for f in frames]
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=DURATION, loop=0, optimize=True, disposal=1)
    return os.path.getsize(out)


def main():
    args = sys.argv[1:]
    size_w = 460
    origin_arg = None
    if "--size" in args:
        i = args.index("--size")
        size_w = int(args[i + 1])
        del args[i:i + 2]
    if "--origin" in args:
        i = args.index("--origin")
        origin_arg = tuple(float(v) for v in args[i + 1].split(","))
        del args[i:i + 2]
    from build_cards import ART_DIR, EN_NAMES, load_characters   # 放這裡避免和 build_cards 互相 import
    char_id, rarity, out = args[0], args[1], args[-1]
    effects = args[2].split("+") if len(args) > 3 else RARITY_EFFECTS[rarity]

    char = load_characters()[char_id]
    card = render_card(os.path.join(ART_DIR, f"{char_id}_{rarity}.png"), rarity,
                       char["gacha"]["titles"][rarity], EN_NAMES[char_id])
    size = save_animation(card, effects, out, size_w, origin_arg)
    print("saved", out, f"{size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

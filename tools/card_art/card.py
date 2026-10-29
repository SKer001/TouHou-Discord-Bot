"""卡面合成：角色原圖墊在下面 ➔ 蓋上 empty.png (畫窗透明) ➔ 寫稱號、名字，貼等級圖

單張：python tools/card_art/card.py <角色原圖> <階級> <中文稱號> <英文名字> <輸出前綴>
      輸出 <前綴>_full.png (1748×2432) 與 <前綴>_thumb.png (460×640)
整批：用 build_cards.py
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
EMPTY = os.path.join(PROJECT_ROOT, "images", "Original", "Thumbnails", "empty.png")
RARITY_DIR = os.path.join(HERE, "rarity")
TITLE_FONT = os.path.join(HERE, "fonts", "kouzan-mouhitsu-gyosho.ttf")   # 衡山毛筆 行書 (public domain)
NAME_FONT = os.path.join(HERE, "fonts", "HarukazeSolid.ttf")             # demo 版限個人使用，不放上 git
THUMB_SIZE = (460, 640)

# 衡山毛筆缺的字 (畫成方框或空白) ➔ 日文異體字；render_card 會再檢查一次，有缺字直接報錯
GLYPH_FALLBACK = {"吞": "呑", "絕": "絶", "鐮": "鎌", "黑": "黒", "綠": "緑"}

WINDOW = (200, 425, 1560, 2050)       # 角色圖鋪的範圍 (比透明畫窗稍大，邊緣藏在卡框下)
TITLE_BOX = (130, 92, 990, 204)       # 左上稱號
BADGE_BOX = (1120, 30, 1710, 250)     # 右上等級圖的基準範圍 (中心點)
BADGE_SCALE = 1.25                    # 等級圖在基準範圍上再放大 (使用者：1.2~1.3 倍，可超出範圍)
NAME_BOX = (200, 226, 1550, 384)      # 名牌名字 (可稍微超出名牌)
TITLE_TRACKING = 0.08                 # 稱號字距 (字級的比例)
NAME_TRACKING = 0.06
TITLE_BOLD = 0.01                     # 稱號加粗 (字級的比例，太粗筆畫會糊)


def fit_spaced(path, text, box, max_size, stroke_ratio, tracking):
    """加大字距後能放進 box 的最大字級"""
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    w, h = box[2] - box[0], box[3] - box[1]
    for size in range(max_size, 19, -2):
        font = ImageFont.truetype(path, size)
        stroke, gap = int(size * stroke_ratio), size * tracking
        widths = [d.textlength(ch, font=font) for ch in text]
        total = sum(widths) + gap * (len(text) - 1) + stroke * 2
        l, t, r, b = d.textbbox((0, 0), text, font=font, stroke_width=stroke)
        if total <= w and b - t <= h:
            break
    return font, stroke, gap, widths, total, (t, b)


def draw_spaced(img, text, box, path, max_size, stroke_ratio, tracking, fill, stroke_fill, bold_ratio=0.0):
    """bold_ratio：用同色描邊把字加粗 (字型沒有粗體)；stroke_ratio：外圈描邊"""
    font, stroke, gap, widths, total, (t, b) = fit_spaced(path, text, box, max_size, stroke_ratio + bold_ratio, tracking)
    bold = int(font.size * bold_ratio)
    d = ImageDraw.Draw(img)
    x = (box[0] + box[2]) / 2 - total / 2 + stroke
    y = (box[1] + box[3]) / 2 - (t + b) / 2
    for ch, cw in zip(text, widths):
        d.text((x, y), ch, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill or fill)
        if bold:
            d.text((x, y), ch, font=font, fill=fill, stroke_width=bold, stroke_fill=fill)
        x += cw + gap


def paste_badge(img, rarity):
    badge = Image.open(os.path.join(RARITY_DIR, f"{rarity}.png")).convert("RGBA")
    w, h = BADGE_BOX[2] - BADGE_BOX[0], BADGE_BOX[3] - BADGE_BOX[1]
    scale = min(w / badge.width, h / badge.height) * BADGE_SCALE
    badge = badge.resize((int(badge.width * scale), int(badge.height * scale)), Image.LANCZOS)
    x = BADGE_BOX[0] + (w - badge.width) // 2
    y = max(0, BADGE_BOX[1] + (h - badge.height) // 2)                  # 放大後不要超出卡片上緣
    x = min(x, img.width - badge.width)                                  # 也不要超出右緣
    img.alpha_composite(badge, (x, y))


def missing_glyphs(text: str, path: str = TITLE_FONT) -> list[str]:
    """字型畫不出來的字：沒有筆畫 (空白) 或只畫出缺字方框 (跟字型裡不存在的字長得一樣)"""
    font = ImageFont.truetype(path, 80)

    def ink(ch):
        im = Image.new("L", (120, 120), 0)
        ImageDraw.Draw(im).text((10, 10), ch, font=font, fill=255)
        return im.getbbox(), im.tobytes()

    tofu = ink("󰀀")   # 私用區的字，字型一定沒有 ➔ 缺字方框的樣子
    return [ch for ch in dict.fromkeys(text) if not ch.isspace() and (ink(ch)[0] is None or ink(ch) == tofu)]


def render_stages(art_path: str, rarity: str, title: str, name: str) -> dict:
    """依步驟產生卡面，回傳每一步的圖 (都是 1748×2432 RGB)：
    1_art 人物 (鋪進畫窗位置) ➔ 2_frame 人物 + 卡框 ➔ 3_text + 稱號與名字 ➔ 4_card + 等級圖 (完成)"""
    title = "".join(GLYPH_FALLBACK.get(ch, ch) for ch in title)
    missing = missing_glyphs(title)
    if missing:
        raise ValueError(f"稱號「{title}」有字型缺字：{''.join(missing)}，請在 GLYPH_FALLBACK 加上異體字")

    stages = {}
    frame = Image.open(EMPTY).convert("RGBA")
    card = Image.new("RGBA", frame.size, (0, 0, 0, 255))
    l, t, r, b = WINDOW
    art = ImageOps.fit(Image.open(art_path).convert("RGBA"), (r - l, b - t), method=Image.LANCZOS, centering=(0.5, 0.45))
    card.alpha_composite(art, (l, t))
    stages["1_art"] = card.convert("RGB")
    card.alpha_composite(frame)
    stages["2_frame"] = card.convert("RGB")

    draw_spaced(card, title, TITLE_BOX, TITLE_FONT, 104, 0.06, TITLE_TRACKING, (25, 15, 12), (250, 244, 230), bold_ratio=TITLE_BOLD)
    draw_spaced(card, name, NAME_BOX, NAME_FONT, 360, 0, NAME_TRACKING, (30, 20, 20), None)
    stages["3_text"] = card.convert("RGB")
    paste_badge(card, rarity)
    stages["4_card"] = card.convert("RGB")
    return stages


def render_card(art_path: str, rarity: str, title: str, name: str) -> Image.Image:
    """回傳 1748×2432 的完整卡面 (RGB)"""
    return render_stages(art_path, rarity, title, name)["4_card"]


def make_thumb(card: Image.Image) -> Image.Image:
    return card.resize(THUMB_SIZE, Image.LANCZOS)


def main():
    art_path, rarity, title, name, out_prefix = sys.argv[1:6]
    card = render_card(art_path, rarity, title, name)
    card.save(f"{out_prefix}_full.png", optimize=True)
    make_thumb(card).save(f"{out_prefix}_thumb.png", optimize=True)
    print("saved", out_prefix)


if __name__ == "__main__":
    main()

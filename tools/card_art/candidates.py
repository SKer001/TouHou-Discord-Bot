"""候選對照表 (給使用者挑圖)：python tools/card_art/candidates.py <角色id> [階級 ...] [--out 資料夾]
取 ComfyUI 輸出資料夾裡 <角色id>_<階級>_*.png 最新的 4 張，套上卡框並排 (上方標 1~4)，
輸出 <out>/sheet_<角色id>_<階級>.png；ComfyUI 輸出資料夾可用環境變數 COMFY_OUTPUT 指定
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_cards import EN_NAMES, load_characters  # noqa: E402
from card import make_thumb, render_card  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

COMFY_OUTPUT = os.environ.get("COMFY_OUTPUT", os.path.expanduser("~/Documents/comfy/ComfyUI/output/touhou_card"))
GAP = 13


def main():
    args = sys.argv[1:]
    out_dir = "."
    if "--out" in args:
        i = args.index("--out")
        out_dir = args[i + 1]
        del args[i:i + 2]
    char_id = args[0]
    char = load_characters()[char_id]
    rarities = args[1:] or char["gacha"]["rarities"]
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except OSError:
        font = ImageFont.load_default()

    for rarity in rarities:
        files = sorted(glob.glob(os.path.join(COMFY_OUTPUT, f"{char_id}_{rarity}_0*_.png")))[-4:]
        if not files:
            print(f"⚠️ 找不到 {char_id}_{rarity} 的圖")
            continue
        w, h = 460, 640
        sheet = Image.new("RGB", (len(files) * (w + GAP) - GAP, h + 60), "white")
        d = ImageDraw.Draw(sheet)
        for i, src in enumerate(files):
            card = render_card(src, rarity, char["gacha"]["titles"][rarity], EN_NAMES[char_id])
            sheet.paste(make_thumb(card), (i * (w + GAP), 60))
            d.text((i * (w + GAP) + w // 2 - 10, 8), str(i + 1), fill="black", font=font)
        out = os.path.join(out_dir, f"sheet_{char_id}_{rarity}.png")
        sheet.save(out)
        print(out, [os.path.basename(f) for f in files])


if __name__ == "__main__":
    main()

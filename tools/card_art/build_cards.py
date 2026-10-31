"""整批產生卡面縮圖並更新 images/Thumbnails.json
python tools/card_art/build_cards.py [角色id ...] [--full 資料夾]

- 原圖：images/Original/Art/<角色id>_<階級>.png (沒有加框的角色圖；沒有的階級略過)
- 縮圖：images/Thumbnails/<角色id>_<階級>.png (460×640；SSR / UR / LR 只留 GIF)
- 動態卡：SSR / UR / LR 另外產生 images/Thumbnails/<角色id>_<階級>.gif (效果見 animate.RARITY_EFFECTS)，
  Thumbnails.json 指向 GIF；--no-gif 只做靜態圖 (快)
- Thumbnails.json：寫入 "<角色id>_<階級>": GitHub raw 連結 + ?v=版本號 (檔案雜湊，卡面改了 Discord 才不會用快取的舊圖；要 push 之後 Discord 才抓得到)
- --full：另外把 1748×2432 的完整卡面存到指定資料夾 (不放進 repo)
- --stages [資料夾]：每一步都存圖 (預設 card_stages/，已加入 .gitignore，太大不放進 repo)
    _base/frame.png、_base/rarity/<階級>.png             基礎元素 (卡框、等級圖)
    <角色>_<階級>/0_pic.png                              角色原圖
    <角色>_<階級>/1_art.png → 2_frame.png → 3_text.png → 4_card.png
                                                         人物 → 人物 + 框 → + 名字與稱號 → + 等級 (完成)
"""
import glob
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from card import EMPTY, PROJECT_ROOT, RARITY_DIR, make_thumb, render_layered_stages, render_stages  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "layered"))
from animate import RARITY_EFFECTS, save_animation  # noqa: E402

ART_DIR = os.path.join(PROJECT_ROOT, "images", "Original", "Art")
THUMB_DIR = os.path.join(PROJECT_ROOT, "images", "Thumbnails")
THUMBNAILS_FILE = os.path.join(PROJECT_ROOT, "images", "Thumbnails.json")
RAW_BASE = "https://raw.githubusercontent.com/SKer001/TouHou-Discord-Bot/refs/heads/main/images/Thumbnails/"

# 名牌上的英文名字 (Harukaze 只有英文字)
EN_NAMES = {
    "reimu": "Hakurei Reimu",
    "marisa": "Kirisame Marisa",
    "mima": "Mima",
    "genji": "Genjii",
    "rika": "Rika",
    "chiyuri": "Kitashirakawa Chiyuri",
    "yumemi": "Okazaki Yumemi",
    "elly": "Elly",
    "gengetsu": "Gengetsu",
    "mugetsu": "Mugetsu",
    "alice": "Alice",
    "luize": "Luize",
    "shinki": "Shinki",
    "yuki_mai": "Yuki & Mai",
    "yumeko": "Yumeko",
    "cirno": "Cirno",
}


def thumb_url(path: str) -> str:
    """GitHub raw 連結 + 版本號 (檔案內容雜湊)：Discord 會依網址快取圖片，卡面改了檔名不變的話會一直顯示舊圖，
    網址帶 ?v= 版本號就會重新抓 (GitHub 忽略這段參數)"""
    with open(path, "rb") as f:
        ver = hashlib.sha1(f.read()).hexdigest()[:8]
    return RAW_BASE + f"{os.path.basename(path)}?v={ver}"


def load_characters() -> dict:
    chars = {}
    for path in glob.glob(os.path.join(PROJECT_ROOT, "Characters", "*", "*.json")):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        chars[data["id"]] = data
    return chars


def main():
    args = sys.argv[1:]
    full_dir = None
    if "--full" in args:
        i = args.index("--full")
        full_dir = args[i + 1]
        del args[i:i + 2]
        os.makedirs(full_dir, exist_ok=True)
    make_gif = "--no-gif" not in args
    if not make_gif:
        args.remove("--no-gif")
    stages_dir = None
    if "--stages" in args:
        i = args.index("--stages")
        has_path = i + 1 < len(args) and not args[i + 1].startswith("-") and args[i + 1] not in load_characters()
        stages_dir = args[i + 1] if has_path else os.path.join(PROJECT_ROOT, "card_stages")
        del args[i:i + (2 if has_path else 1)]
        os.makedirs(os.path.join(stages_dir, "_base", "rarity"), exist_ok=True)
        shutil.copy(EMPTY, os.path.join(stages_dir, "_base", "frame.png"))
        for f in glob.glob(os.path.join(RARITY_DIR, "*.png")):
            shutil.copy(f, os.path.join(stages_dir, "_base", "rarity"))

    chars = load_characters()
    targets = args or sorted(chars)
    with open(THUMBNAILS_FILE, "r", encoding="utf-8") as f:
        thumbnails = json.load(f)

    made = 0
    for char_id in targets:
        char = chars.get(char_id)
        if not char:
            print(f"⚠️ 找不到角色：{char_id}")
            continue
        for rarity in char["gacha"].get("rarities", []):
            art = os.path.join(ART_DIR, f"{char_id}_{rarity}.png")
            if not os.path.exists(art):
                continue
            if char_id not in EN_NAMES:
                print(f"⚠️ {char_id} 沒有英文名字 (EN_NAMES)，略過")
                break
            from hd_card import layered_paths   # 放這裡避免和 hd_card 互相 import
            layered = layered_paths(char_id, rarity)
            if layered:   # 高清分層卡：images/Original/<分類>/<角色>/<階級>/ 的 05_bg + 10_char
                stages = render_layered_stages(*layered, rarity, char["gacha"]["titles"][rarity], EN_NAMES[char_id])
                stages = {"1_art": stages["art"], "2_frame": stages["bg_frame"], "3_text": stages["text"], "4_card": stages["card"]}
            else:
                stages = render_stages(art, rarity, char["gacha"]["titles"][rarity], EN_NAMES[char_id])
            card = stages["4_card"]
            key = f"{char_id}_{rarity}"
            if stages_dir:
                d = os.path.join(stages_dir, key)
                os.makedirs(d, exist_ok=True)
                shutil.copy(art, os.path.join(d, "0_pic.png"))
                for name, im in stages.items():
                    im.save(os.path.join(d, f"{name}.png"))
            if full_dir:
                card.save(os.path.join(full_dir, f"{key}.png"), optimize=True)
            png_path = os.path.join(THUMB_DIR, f"{key}.png")
            gif_path = os.path.join(THUMB_DIR, f"{key}.gif")
            if rarity in RARITY_EFFECTS and make_gif:
                kb = save_animation(card, RARITY_EFFECTS[rarity], gif_path) / 1024
                print(f"✅ {key}  (GIF {kb:.0f} KB)")
            elif rarity in RARITY_EFFECTS and os.path.exists(gif_path):
                print(f"✅ {key}  (沿用 GIF)")                  # --no-gif 時沿用既有的 GIF
            else:
                make_thumb(card).save(png_path, optimize=True)
                thumbnails[key] = thumb_url(png_path)
                print(f"✅ {key}")
            if rarity in RARITY_EFFECTS and os.path.exists(gif_path):
                thumbnails[key] = thumb_url(gif_path)
                if os.path.exists(png_path):
                    os.remove(png_path)                         # 動態卡只需要 GIF，靜態縮圖機器人用不到
            made += 1

    # fill 放最後，其餘依鍵排序
    ordered = {k: thumbnails[k] for k in sorted(thumbnails) if k != "fill"}
    if "fill" in thumbnails:
        ordered["fill"] = thumbnails["fill"]
    with open(THUMBNAILS_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=4)
        f.write("\n")
    print(f"共 {made} 張，已更新 {THUMBNAILS_FILE}")


if __name__ == "__main__":
    main()

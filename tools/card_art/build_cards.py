"""整批產生卡面縮圖並更新 images/Thumbnails.json
python tools/card_art/build_cards.py [角色id ...] [--full 資料夾]

- 原圖：images/Original/Art/<角色id>_<階級>.png (沒有加框的角色圖；沒有的階級略過)
- 縮圖：images/Thumbnails/<角色id>_<階級>.png (460×640)
- Thumbnails.json：寫入 "<角色id>_<階級>": GitHub raw 連結 (要 push 之後 Discord 才抓得到)
- --full：另外把 1748×2432 的完整卡面存到指定資料夾 (不放進 repo)
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from card import PROJECT_ROOT, make_thumb, render_card  # noqa: E402

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
}


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
            card = render_card(art, rarity, char["gacha"]["titles"][rarity], EN_NAMES[char_id])
            key = f"{char_id}_{rarity}"
            make_thumb(card).save(os.path.join(THUMB_DIR, f"{key}.png"), optimize=True)
            if full_dir:
                card.save(os.path.join(full_dir, f"{key}.png"), optimize=True)
            thumbnails[key] = RAW_BASE + f"{key}.png"
            made += 1
            print(f"✅ {key}")

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

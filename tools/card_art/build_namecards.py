"""🖼️ 角色名片：把高解析原圖縮成 Discord 顯示用的 JPG，並更新 images/Namecards.json
python tools/card_art/build_namecards.py <原圖路徑> <角色id>

- 名片 = 19:9 左右的橫幅 (影畫風)，原圖另外存 (不放進 repo，存放位置還沒決定)
- 顯示用：images/Namecards/<角色id>.jpg (寬 1920，保持比例，JPG quality 88)
- Namecards.json：{"<角色id>": GitHub raw 連結 + ?v=版本號 (檔案雜湊，圖改了 Discord 才不會用快取的舊圖)}
  要 push 之後 Discord 才抓得到 (跟 build_cards.py 的 Thumbnails.json 一樣)
- 程式端讀網址：Utils/namecards.py 的 namecard_url()
"""
import hashlib
import json
import os
import sys

from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAMECARD_DIR = os.path.join(PROJECT_ROOT, "images", "Namecards")
NAMECARDS_FILE = os.path.join(PROJECT_ROOT, "images", "Namecards.json")
RAW_BASE = "https://raw.githubusercontent.com/SKer001/TouHou-Discord-Bot/refs/heads/main/images/Namecards/"

TARGET_WIDTH = 1920
JPEG_QUALITY = 88
TARGET_RATIO = 19 / 9
RATIO_TOLERANCE = 0.08   # 比例差超過 8% 就提醒 (還是會照原比例輸出)


def namecard_url(path: str) -> str:
    """GitHub raw 連結 + ?v=檔案雜湊 (同 build_cards.thumb_url)"""
    with open(path, "rb") as f:
        ver = hashlib.sha1(f.read()).hexdigest()[:8]
    return RAW_BASE + f"{os.path.basename(path)}?v={ver}"


def build_namecard(src: str, cid: str) -> str:
    """原圖 ➔ images/Namecards/<cid>.jpg (寬 1920、保持比例)，回傳輸出路徑"""
    img = Image.open(src)
    img.load()
    if img.mode != "RGB":   # JPG 沒有透明：透明的地方鋪黑底
        rgba = img.convert("RGBA")
        img = Image.new("RGB", rgba.size, (0, 0, 0))
        img.paste(rgba, mask=rgba.getchannel("A"))
    w, h = img.size
    ratio = w / h
    if abs(ratio - TARGET_RATIO) / TARGET_RATIO > RATIO_TOLERANCE:
        print(f"⚠️ 原圖比例 {w}×{h} ({ratio:.2f}:1) 跟 19:9 ({TARGET_RATIO:.2f}:1) 差比較多，照原比例輸出")
    if w != TARGET_WIDTH:
        img = img.resize((TARGET_WIDTH, max(1, round(h * TARGET_WIDTH / w))), Image.LANCZOS)
    os.makedirs(NAMECARD_DIR, exist_ok=True)
    out = os.path.join(NAMECARD_DIR, f"{cid}.jpg")
    img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return out


def update_json(cid: str, path: str) -> str:
    data = {}
    if os.path.exists(NAMECARDS_FILE):
        with open(NAMECARDS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    data[cid] = namecard_url(path)
    with open(NAMECARDS_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(sorted(data.items())), f, ensure_ascii=False, indent=4)
        f.write("\n")
    return data[cid]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    src, cid = argv
    if not os.path.isfile(src):
        print(f"❌ 找不到原圖：{src}")
        return 1
    sys.path.insert(0, PROJECT_ROOT)
    from Utils.gacha_pools import load_gacha_pool
    if cid not in load_gacha_pool():
        print(f"⚠️ 卡池裡沒有角色「{cid}」(還是會輸出，確認一下 id 有沒有打錯)")
    out = build_namecard(src, cid)
    w, h = Image.open(out).size
    url = update_json(cid, out)
    print(f"✅ {out} ({w}×{h}, {os.path.getsize(out) / 1024:.0f} KB)\n   Namecards.json：{cid} = {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

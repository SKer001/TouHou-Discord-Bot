"""把 PhotoCraft 修好的圖層套回步驟資料夾：pc_apply.py <分類> <角色> <階級>
人物層 (雙人卡是兩層，依圖層編號由下往上疊) 裁成畫窗大小 ➔ 10c_char_photocraft.png (疊層優先用)；
--hd (雙人卡)：使用者只是移動 / 縮放人物時，用 PhotoCraft 的圖層量出每個人新的位置與大小，改從高清的 09a / 09b_placed_hd 重新縮放
      (直接放大畫窗大小的人物層會糊，2026-11-16 雪與舞 R 的手)；有在人物層上畫圖時不要加 --hd，不然畫的東西會不見
      量到的位置存成步驟資料夾的 pc_layout.json (高清座標 ➔ 整張卡座標的縮放與位移)
--relayout (雙人卡)：不讀 .pcraft，照 pc_layout.json 重新放 (例如 fix_region.py 修完手、重新去背之後)背景層有改才覆蓋 05_bg.png (原檔備份成 05_bg_orig.png)"""
import glob, os, shutil, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hd_card

cat, cid, rar = sys.argv[1:4]
HD_MODE = "--hd" in sys.argv[4:]
RELAYOUT = "--relayout" in sys.argv[4:]
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "images", "Original", cat, cid, rar)
ed = os.path.join(os.environ["USERPROFILE"], "Documents", "photocraft_out", f"{cid}_{rar}", "edited")
l, t, r, b = hd_card.window_box()

# 先把 .pcraft 每一層輸出成全尺寸 PNG (trim false 才會保留在原本的位置)
import json, subprocess
LAYOUT = os.path.join(d, "pc_layout.json")
cli = next(p for p in (r"C:\Program Files\ArtCraft\PhotoCraft\photocraft-cli.exe",   # 桌機
                       os.path.expandvars(r"%LOCALAPPDATA%\Programs\ArtCraft\PhotoCraft\photocraft-cli.exe"))   # 筆電
           if os.path.exists(p))
os.makedirs(ed, exist_ok=True)
if not RELAYOUT:
  subprocess.run([cli, "run", os.path.join(os.path.dirname(ed), f"{cid}_{rar}.pcraft"), "--cmd", "file.export.layersToFiles",
                "--params", json.dumps({"dir": ed, "format": "png", "prefix": "ed", "trim": False})], check=True, capture_output=True)

import re
layers = sorted(glob.glob(os.path.join(ed, "*_人物*.png")), key=lambda p: int(re.search(r"(\d+)_人物", os.path.basename(p)).group(1)))


def hd_person(edited_path, k):
    """量出 PhotoCraft 圖層裡這個人的新外框 (跟 10{k}_char 比)，從高清 09{k}_placed_hd 重新縮放到那個外框；碰到整張卡邊緣的邊不拿來量"""
    def bbox(im):
        return im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    ed_im = Image.open(edited_path).convert("RGBA")
    W, H = ed_im.size
    o = bbox(Image.open(os.path.join(d, f"10{k}_char.png")).convert("RGBA"))
    o = (o[0] + l, o[1] + t, o[2] + l, o[3] + t)                     # 原本在整張卡上的外框
    e = bbox(ed_im)
    cut = (e[0] <= 0, e[1] <= 0, e[2] >= W, e[3] >= H)                # 左上右下有沒有被整張卡切到
    ow, oh = o[2] - o[0], o[3] - o[1]
    s = (e[3] - e[1]) / oh if not (cut[1] or cut[3]) else (e[2] - e[0]) / ow
    nw, nh = round(ow * s), round(oh * s)
    x = e[0] if not cut[0] else e[2] - nw
    y = e[1] if not cut[1] else e[3] - nh
    # 有沒有水平翻轉 (使用者 2026-11-16 雪與舞 SR 各自翻轉過)：把新舊外框縮成 64×64 的剪影，比原樣 / 鏡像哪個比較像
    orig_a = Image.open(os.path.join(d, f"10{k}_char.png")).getchannel("A")
    ob = bbox(Image.open(os.path.join(d, f"10{k}_char.png")).convert("RGBA"))
    oa = np.asarray(orig_a.crop(ob).resize((64, 64))) > 128
    full = Image.new("L", (nw, nh), 0)                                 # 使用者圖層的剪影放回完整外框 (被切掉的部分空白)
    full.paste(ed_im.getchannel("A").crop(e), (e[0] - x, e[1] - y))
    ea = np.asarray(full.resize((64, 64))) > 128
    flip = bool((ea & oa[:, ::-1]).sum() > (ea & oa).sum())
    src = Image.open(os.path.join(d, f"09{k}_placed_hd.png")).convert("RGBA")
    hb = bbox(src)
    f = nw / (hb[2] - hb[0])                                          # 高清 ➔ 整張卡的縮放
    layout[k] = [f, x - hb[0] * f, y - hb[1] * f, flip]
    print(f"  {k}：放大 {s:.3f} 倍，外框 ({x}, {y}, {x + nw}, {y + nh})" + ("，水平翻轉" if flip else ""))
    return place_hd(k, (W, H))


def place_hd(k, size):
    """照 layout[k] 把 09{k}_placed_hd 放到整張卡大小的畫布"""
    f, ox, oy = layout[k][:3]
    flip = layout[k][3] if len(layout[k]) > 3 else False
    src = Image.open(os.path.join(d, f"09{k}_placed_hd.png")).convert("RGBA")
    hb = src.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    src = src.crop(hb)
    if flip:   # 以自己的外框翻轉 (外框位置不變)
        src = src.transpose(Image.FLIP_LEFT_RIGHT)
    src = src.resize((round(src.width * f), round(src.height * f)), Image.LANCZOS)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(src, (round(ox + hb[0] * f), round(oy + hb[1] * f)))
    return out


duo = hd_card.LAYERS[(cid, rar)].get("duo")
layout = {}
if RELAYOUT:
    with open(LAYOUT, encoding="utf-8") as f_:
        layout = json.load(f_)
    front = duo.get("front", "a")
    size = Image.open(os.path.join(d, "05_bg.png")).size
    imgs = [place_hd(k, size) for k in [k for k in "ab" if k != front] + [front]]
    layers = []
elif HD_MODE and duo:
    who = {v: k for k, v in zip("ab", duo.get("names", ("A", "B")))}
    imgs = [hd_person(p, who[re.search(r"_人物_(.+?)\.png", os.path.basename(p)).group(1)]) for p in layers]
    with open(LAYOUT, "w", encoding="utf-8") as f_:
        json.dump(layout, f_)
else:
    imgs = [Image.open(p).convert("RGBA") for p in layers]
ch = imgs[0]
for im in imgs[1:]:
    ch.alpha_composite(im)
ch.crop((l, t, r, b)).save(os.path.join(d, "10c_char_photocraft.png"))
print("✅ 10c_char_photocraft.png")

if RELAYOUT:
    raise SystemExit(0)
new_bg = Image.open(glob.glob(os.path.join(ed, "*1_背景*.png"))[0]).convert("RGB")
old_bg = Image.open(os.path.join(d, "05_bg.png")).convert("RGB")
diff = np.abs(np.asarray(new_bg, np.int16) - np.asarray(old_bg, np.int16)).max()
if diff > 3:
    if not os.path.exists(os.path.join(d, "05_bg_orig.png")):
        shutil.copy(os.path.join(d, "05_bg.png"), os.path.join(d, "05_bg_orig.png"))
    new_bg.save(os.path.join(d, "05_bg.png"))
    print("✅ 05_bg.png (背景有修改，原檔留 05_bg_orig.png)")
else:
    print("背景沒有改")

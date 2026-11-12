"""把一張卡拆成全尺寸圖層 PNG，再用 PhotoCraft 疊成 .pcraft：pc_layers.py <分類> <角色> <階級>
圖層 (下到上)：1 背景 (05_bg)、2 人物 (10_char 放回畫窗位置)、3 卡框與文字 (15_card 去掉畫窗內跟 11_art 一樣的像素，參考用)"""
import os, subprocess, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hd_card

cat, cid, rar = sys.argv[1:4]
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "images", "Original", cat, cid, rar)
out = os.path.join(os.environ["USERPROFILE"], "Documents", "photocraft_out", f"{cid}_{rar}")
os.makedirs(out, exist_ok=True)
l, t, r, b = hd_card.window_box()

bg = Image.open(os.path.join(d, "05_bg.png")).convert("RGBA")
W, H = bg.size
bg.save(os.path.join(out, "1_背景.png"))

ch = Image.open(hd_card.char_layer(d)).convert("RGBA")
canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
canvas.paste(ch, (l, t))
canvas.save(os.path.join(out, "2_人物.png"))

card = np.asarray(Image.open(os.path.join(d, "15_card.png")).convert("RGB")).astype(np.int16)
art = np.asarray(Image.open(os.path.join(d, "11_art.png")).convert("RGB")).astype(np.int16)
alpha = np.where(np.abs(card - art).max(-1) < 6, 0, 255).astype(np.uint8)   # 11_art 是整張卡大小的背景 + 人物
Image.fromarray(np.dstack([card.astype(np.uint8), alpha]), "RGBA").save(os.path.join(out, "3_卡框與文字.png"))

cli = next(p for p in (r"C:\Program Files\ArtCraft\PhotoCraft\photocraft-cli.exe",   # 桌機
                       os.path.expandvars(r"%LOCALAPPDATA%\Programs\ArtCraft\PhotoCraft\photocraft-cli.exe"))   # 筆電
           if os.path.exists(p))
paths = [os.path.join(out, n) for n in ("1_背景.png", "2_人物.png", "3_卡框與文字.png")]
import json
doc = os.path.join(out, f"{cid}_{rar}.pcraft")
r_ = subprocess.run([cli, "run", "--new", "{}", "--cmd", "file.scripts.loadFilesIntoStack",
                     "--params", json.dumps({"paths": paths}), "--out", doc], capture_output=True, text=True, encoding="utf-8")
print(r_.stdout[-1500:], r_.stderr[-1500:])
print(doc, os.path.exists(doc))

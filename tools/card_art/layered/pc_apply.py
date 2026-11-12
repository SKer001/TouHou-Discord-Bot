"""把 PhotoCraft 修好的圖層套回步驟資料夾：pc_apply.py <分類> <角色> <階級>
人物層裁成畫窗大小 ➔ 10c_char_photocraft.png (疊層優先用)；背景層有改才覆蓋 05_bg.png (原檔備份成 05_bg_orig.png)"""
import glob, os, shutil, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hd_card

cat, cid, rar = sys.argv[1:4]
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "images", "Original", cat, cid, rar)
ed = os.path.join(os.environ["USERPROFILE"], "Documents", "photocraft_out", f"{cid}_{rar}", "edited")
l, t, r, b = hd_card.window_box()

# 先把 .pcraft 每一層輸出成全尺寸 PNG (trim false 才會保留在原本的位置)
import json, subprocess
cli = next(p for p in (r"C:\Program Files\ArtCraft\PhotoCraft\photocraft-cli.exe",   # 桌機
                       os.path.expandvars(r"%LOCALAPPDATA%\Programs\ArtCraft\PhotoCraft\photocraft-cli.exe"))   # 筆電
           if os.path.exists(p))
os.makedirs(ed, exist_ok=True)
subprocess.run([cli, "run", os.path.join(os.path.dirname(ed), f"{cid}_{rar}.pcraft"), "--cmd", "file.export.layersToFiles",
                "--params", json.dumps({"dir": ed, "format": "png", "prefix": "ed", "trim": False})], check=True, capture_output=True)

ch = Image.open(glob.glob(os.path.join(ed, "*2_人物*.png"))[0]).convert("RGBA")
ch.crop((l, t, r, b)).save(os.path.join(d, "10c_char_photocraft.png"))
print("✅ 10c_char_photocraft.png")

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

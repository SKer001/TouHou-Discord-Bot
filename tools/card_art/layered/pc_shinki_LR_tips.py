"""用 PhotoCraft 把神綺 LR 翅膀外緣的淡紫色羽尖壓暗 (2026-10-30)
python pc_shinki_LR_tips.py preview   選取範圍反相後存預覽，確認選到哪裡
python pc_shinki_LR_tips.py apply     壓暗並匯出 Documents/photocraft_out/shinki_LR_10b_fixed.png
                                      ➔ 複製成 images/Original/TH05/shinki/LR/10c_char_photocraft.png
心得：select.colorRange 的 points (滴管) 沒生效、會退回前景色黑色，要直接給 color / colors；
      淡色低飽和度用色相偏移看不出選取範圍，用 invert 預覽；用 transparency 交集保護外側光暈"""
import base64
import os
import sys

from photocraft import PC

OUT = os.path.expanduser(r"~\Documents\photocraft_out")   # 預覽圖也存到 PhotoCraft 的輸出資料夾
SRC = "TH05/shinki/LR/10b_char_lit.png"
mode = sys.argv[1] if len(sys.argv) > 1 else "preview"   # preview：只看選取範圍；apply：調整並匯出

TIPS = [[330, 110], [1180, 548], [60, 640], [40, 980], [250, 300], [1100, 560], [120, 900], [900, 1250]]
TIP_COLORS = ["#a292b4", "#b07fae", "#ad9dbe", "#c8a0d0", "#9a88c0", "#b8a8d8"]   # 羽尖的淡紫色 (從圖上取樣)
HAIR = [[600, 620], [520, 700], [700, 700], [650, 760]]
HEAD = [[540, 540], [740, 540], [810, 640], [800, 780], [720, 840], [560, 850], [410, 820], [390, 700], [450, 590]]
DRESS = [[420, 700], [660, 690], [720, 820], [760, 1100], [740, 1290], [560, 1320], [160, 1170], [160, 990], [320, 880]]


def run(pc, cid, **params):
    _, t = pc.call("command_run", id=cid, params=params)
    print(cid, (t or "")[:160])


def save_preview(pc, name):
    res, _ = pc.call("render_preview", max_side=1024)
    for c in res["content"]:
        if c.get("type") == "image":
            open(f"{OUT}\\{name}", "wb").write(base64.b64decode(c["data"]))
            print("preview ->", name)


pc = PC()
print(pc.call("doc_open", path=SRC)[1][:200])
run(pc, "image.duplicate")
run(pc, "select.colorRange", select="sampledColors", color="#a292b4", colors=TIP_COLORS, fuzziness=40)
run(pc, "select.lasso", points=HEAD, mode="subtract")
run(pc, "select.lasso", points=DRESS, mode="subtract")
run(pc, "select.loadSelection", channel="transparency", operation="intersect")   # 只改不透明的人物，外側光暈不動
run(pc, "select.modify.feather", radius=3)
if mode == "preview":
    # 選取範圍反相，看抓到哪裡
    run(pc, "image.adjustments.invert")
    save_preview(pc, "sel_preview.png")
else:
    # 曲線壓暗 + 稍微往深紫靠
    run(pc, "image.adjustments.curves", points=[[0, 0], [90, 45], [180, 95], [255, 150]])
    run(pc, "image.adjustments.hueSaturation", hue=0, saturation=15, lightness=-10)
    run(pc, "select.deselect")
    save_preview(pc, "fixed_preview.png")
    print(pc.call("doc_export", path="shinki_LR_10b_fixed.png")[1][:300])
pc.close()

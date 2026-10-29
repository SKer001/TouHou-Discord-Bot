"""人物去背 (comfy venv)：python -I cutout.py <輸入...> <輸出資料夾>"""
import os, sys
from PIL import Image
from rembg import new_session, remove
out = sys.argv[-1]
session = new_session("birefnet-general")
for p in sys.argv[1:-1]:
    im = Image.open(p).convert("RGB")
    rgba = remove(im, session=session)
    name = os.path.splitext(os.path.basename(p))[0] + "_cut.png"
    rgba.save(os.path.join(out, name))
    print("saved", name, rgba.getbbox())

"""人物補邊 (翅膀 / 裙擺被切)：神綺 / 幻月用過的做法
06_char_base 縮到 680×820 貼白底 ➔ OpenCV inpaint 往外抹顏色當引導 (越遠越淡到白) ➔ SetLatentNoiseMask 只重畫外圍 (denoise 0.9)，一次出 2 張
python tools/card_art/layered/outpaint_char.py <角色id> <階級> <左> <上> <右> <下 (各補幾 px)> <種子>
結果：ComfyUI output/touhou_card/hd/<角色>_<階級>_op2_s<種子>_*.png；挑好後用 hd_card.py wf-up 放大，再 collect / char / compose
注意：內建 wf-outpaint 會畫出深灰背景、多長翼尖，所以改用這支
"""
import sys, json, os, urllib.request
import numpy as np, cv2
from PIL import Image, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hd_card as h
cid, rar = sys.argv[1], sys.argv[2]
l, t, r, b, seed = map(int, sys.argv[3:8])
D = h.stage_dir(cid, rar)
IN = os.path.expanduser(r"~\Documents\comfy\ComfyUI\input")
src = Image.open(os.path.join(D, "06_char_base.png")).convert("RGB").resize((680, 820), Image.LANCZOS)
W, H = 680 + l + r, 820 + t + b
canvas = np.full((H, W, 3), 255, np.uint8); canvas[t:t+820, l:l+680] = np.array(src)
pad = np.ones((H, W), np.uint8) * 255; pad[t:t+820, l:l+680] = 0
guide = cv2.inpaint(canvas, pad, 25, cv2.INPAINT_TELEA)
# 越遠越淡 (淡到白)
dist = cv2.distanceTransform(pad, cv2.DIST_L2, 5)
k = np.clip(1 - dist / 160.0, 0, 1)[..., None]
guide = (guide * k + 255 * (1 - k)).astype(np.uint8)
guide[pad == 0] = canvas[pad == 0]
# 遮罩：補邊區 + 往內 24px，羽化
m = cv2.dilate(pad, np.ones((49, 49), np.uint8))
m = cv2.GaussianBlur(m, (0, 0), 12)
img = Image.fromarray(guide).convert("RGBA"); img.putalpha(Image.fromarray(255 - m))
name = f"{cid}_{rar}_op2.png"; img.save(os.path.join(IN, name))
Image.fromarray(guide).save(os.path.join(D, "op2_guide.png"))
pos, neg = h.char_prompts(cid, h.LAYERS[(cid, rar)])
wf = {
 "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "animagine-xl-4.0-opt.safetensors"}},
 "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": pos}},
 "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": neg + ", extra wings, multiple wings, four wings, extra legs, extra feet, gray background, dark background, gradient background"}},
 "4": {"class_type": "LoadImage", "inputs": {"image": name}},
 "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
 "6": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["5", 0], "mask": ["4", 1]}},
 "8": {"class_type": "RepeatLatentBatch", "inputs": {"samples": ["6", 0], "amount": 2}},
 "9": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["8", 0],
        "seed": seed, "steps": 28, "cfg": 5.0, "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 0.9}},
 "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
 "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": f"touhou_card/hd/{cid}_{rar}_op2_s{seed}"}},
}
req = urllib.request.Request("http://127.0.0.1:8188/prompt", json.dumps({"prompt": wf}).encode(), {"Content-Type": "application/json"})
print(urllib.request.urlopen(req).read().decode(), W, H)

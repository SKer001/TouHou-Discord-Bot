"""分層卡面候選對照表：一位角色一位角色排 ComfyUI (背景 2 張 + 人物 4 張)，做完就做對照表並印 SHEET <角色> (給 Monitor 通知)
python tools/card_art/layered/candidate_sheets.py alice:SR,SSR shinki:UR ...
種子：環境變數 BG_SEEDS / CH_SEEDS (逗號分隔)；已經生過的種子會略過，只重生人物就只換 CH_SEEDS
輸出：對照表 sheet_<角色>_<階級>.png (上排 B1 B2 背景、下面 C1～C4 人物) 與工作流程 JSON 放在 SHEET_DIR
(預設 ComfyUI output/touhou_card/sheets)
"""
import glob, json, os, subprocess, sys, time, urllib.request
from PIL import Image, ImageDraw, ImageFont
LAY = os.path.dirname(os.path.abspath(__file__))
HERE = os.environ.get("SHEET_DIR", os.path.expanduser(r"~\Documents\comfy\ComfyUI\output\touhou_card\sheets"))
os.makedirs(HERE, exist_ok=True)
OUT = os.path.expanduser(r"~\Documents\comfy\ComfyUI\output\touhou_card\hd")
URL = "http://127.0.0.1:8188"
BG = tuple(int(x) for x in os.environ.get("BG_SEEDS", "1101,2202").split(","))   # 重生背景時換一組種子
CH = tuple(int(x) for x in os.environ.get("CH_SEEDS", "3303,4404,5505,6606").split(","))   # 重生人物時換一組種子
FONT = ImageFont.truetype("arial.ttf", 40); CELL = (480, 640)

def post(wf):
    req = urllib.request.Request(URL + "/prompt", data=json.dumps({"prompt": wf}).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))["prompt_id"]

def wait_empty():
    while True:
        time.sleep(10)
        try:
            q = json.load(urllib.request.urlopen(URL + "/queue"))
            if not q["queue_running"] and not q["queue_pending"]:
                return
        except Exception as e:
            print("WAIT_ERR", e, flush=True)

def latest(p):
    f = sorted(glob.glob(os.path.join(OUT, p))); return f[-1] if f else None

def tile(path, label):
    c = Image.new("RGB", CELL, (60, 60, 60))
    if path:
        im = Image.open(path).convert("RGB"); im.thumbnail(CELL, Image.LANCZOS); c.paste(im, ((CELL[0]-im.width)//2, (CELL[1]-im.height)//2))
    d = ImageDraw.Draw(c); d.rectangle((0, 0, 200, 52), fill=(0, 0, 0)); d.text((10, 4), label, fill=(255, 255, 0), font=FONT); return c

if __name__ == "__main__":
  for arg in sys.argv[1:]:
    cid, rars = arg.split(":"); rars = rars.split(",")
    for r in rars:
        for layer, seeds in (("bg", BG), ("char", CH)):
            for s in seeds:
                if latest(f"{cid}_{r}_{layer}_s{s}_3hd_*.png"):
                    continue
                path = os.path.join(HERE, f"wf_{cid}_{r}_{layer}_{s}.json")
                subprocess.run([sys.executable, "hd_card.py", "wf", cid, r, layer, str(s), path], cwd=LAY, check=True, stdout=subprocess.DEVNULL)
                post(json.load(open(path, encoding="utf-8")))
    wait_empty()
    for r in rars:
        t = [tile(latest(f"{cid}_{r}_bg_s{s}_2hires_*.png"), f"B{i+1}") for i, s in enumerate(BG)]
        t += [tile(latest(f"{cid}_{r}_char_s{s}_2hires_*.png"), f"C{i+1}") for i, s in enumerate(CH)]
        sh = Image.new("RGB", (CELL[0]*2+10, CELL[1]*3+20), (255, 255, 255))
        for i, im in enumerate(t): sh.paste(im, ((i % 2)*(CELL[0]+10), (i//2)*(CELL[1]+10)))
        sh.save(os.path.join(HERE, f"sheet_{cid}_{r}.png"))
    print("SHEET", cid, ",".join(rars), flush=True)
print("ALLDONE", flush=True)

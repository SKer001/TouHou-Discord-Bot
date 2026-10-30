"""高清分層卡面流程 (使用者 2026-10-30 指定，UR / LR 用)：每一步的產出與修改後的圖都保留，方便之後微調
步驟檔放在 images/Original/<分類>/<角色>/<階級>/ (分類 = Characters/ 的資料夾，例如 TH05)：

  背景  01_bg_base.png     SDXL 生成 (跟卡面同比例 864×1200)
        02_bg_hires.png    放大 2 倍再重繪補細節 (1728×2400)
        03_bg_hd.png       4x-UltraSharp 放大成卡面 4×4 = 16 倍像素 (6992×9728)
        04_bg_fx_hd.png    壓暗 + 程式畫的彈幕 (高清畫，邊緣乾淨)
        05_bg.png          壓縮成卡面大小 (1748×2432) ★
  人物  06_char_base.png   SDXL 生成完整全身、白底 (跟畫窗同比例 936×1128)
        07_char_hires.png  放大 1.5 倍重繪 (1400×1688)
        08_char_hd.png     放大成畫窗 16 倍像素 (5316×6384)
        09_char_cut_hd.png 去背 (BiRefNet)
        10_char.png        裁掉空白、傾斜 (tilt)、縮到剛好完整放進畫窗 (× char_scale)，放到畫窗大小的畫布 (offset 微調，超出切掉) ★
        10b_char_lit.png   打光 (relight.py：背光、輪廓光、翅膀紋路與眼睛發光；LAYERS 有 light 才做) ★ 有這張就用這張
        10c_char_photocraft.png  PhotoCraft 手修 (例如 pc_shinki_LR_tips.py) ★ 有這張就優先用；10b 重做後要記得重修
  疊層  11_art.png         背景 + 人物 (沒有框的完整原圖，也複製到 Original/Art/<角色>_<階級>.png；
                           10_char.png 另外複製成 Art/<角色>_<階級>_char.png)
        12_bg_frame.png    背景 + 卡框
        13_frame_char.png  + 人物 (蓋在卡框上)
        14_text.png        + 稱號與名字
        15_card.png        + 等級圖 (完成)
        16_card.gif        + 動態特效 (animate.RARITY_EFFECTS)
  ★ 是重建卡面需要的檔案 (build_cards.py 會優先用它們)；*_hd.png 太大不進 git，只留在本機

用法：
  python hd_card.py wf <角色> <階級> bg|char <種子> <輸出.json>   產生 ComfyUI 工作流程 (生成 → 重繪 → 放大一次做完)
  python hd_card.py wf-up <角色> <階級> <ComfyUI/input 裡的圖> <種子> <輸出.json>  拿現成人物圖走重繪 → 高清
  python hd_card.py wf-outpaint <角色> <階級> <ComfyUI/input 裡的圖> <種子> <輸出.json>  往外擴圖 (神綺翅膀試過會長出多餘的翅膀，不建議)
  python hd_card.py collect <角色> <階級> bg|char <種子>            把 ComfyUI 的輸出複製成 01~03 / 06~08
  python hd_card.py bg <角色> <階級>                                 04、05
  python hd_card.py char <角色> <階級>                               09、10 (去背用 comfy venv 的 python)
  python hd_card.py light <角色> <階級>                              10b (打光，LAYERS 的 light)
  python hd_card.py compose <角色> <階級>                            11~16
"""
import glob
import json
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageChops, ImageEnhance

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from card import PROJECT_ROOT, render_layered_stages, window_box  # noqa: E402
from danmaku import BASE_W, draw_danmaku  # noqa: E402
from relight import relight  # noqa: E402
from make_workflow import BASE, NEGATIVE, QUALITY, EXTRA_NEGATIVE  # noqa: E402

Image.MAX_IMAGE_PIXELS = None                      # 高清背景 6992×9728 超過 PIL 預設上限
COMFY_OUT = os.environ.get("COMFY_OUTPUT", os.path.expanduser(r"~\Documents\comfy\ComfyUI\output"))
COMFY_PY = os.environ.get("COMFY_PYTHON", os.path.expanduser(r"~\Documents\comfy\venv\Scripts\python.exe"))
HD = 4                                             # 長寬各 4 倍 = 16 倍像素
SIZES = {   # 生成尺寸、重繪倍率
    "bg": {"base": (864, 1200), "hires": (1728, 2400)},
    "char": {"base": (936, 1128), "hires": (1400, 1688)},
}
CHAR_COMPOSITION = ("solo, full body, entire body visible, head to toe, wings fully visible, wingtips inside frame, "
                    "very wide shot, zoomed out, small figure in the center, lots of empty white space around the wings, "   # 不加的話翅膀、靴子會被切掉
                    "simple background, white background, plain background")
CHAR_NEGATIVE = ("background scenery, danmaku, effects, cropped, cut off wings, wings out of frame, cut off feet, "
                 "black border, letterbox, frame, close-up, large figure")

# 每張分層卡的提示詞：bg = 背景 (不要人物)、char = 人物動作表情、style = 彈幕風格 (danmaku.py)、dim = 背景亮度
LAYERS = {
    # 神綺 LR「魔界宇宙之創世主」：宇宙背景 + 彩虹彈幕；人物斜角 (左下腳、右上頭)、微仰視、六翼完整
    ("shinki", "LR"): {
        "bg": ("no humans, scenery, galaxy, nebula, starry sky, cosmic, deep space, swirling purple and gold nebula, "
               "distant demon world planet, aurora, cosmic dust, countless tiny stars, rainbow colors, iridescent, prismatic, "
               "ornate, dazzling, gorgeous, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, wings, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "char": ("dutch angle, diagonal composition, slightly from below, floating, six purple wings fully spread, "
                 "pointing at viewer, defiant pout, glowing eyes, hair flowing, long dress fluttering"),
        "style": "rainbow",
        "dim": 0.62,       # 背景壓暗讓彈幕更跳
        "glow": 0.6,       # 彈幕光暈強度 (太高會變成一片霧)
        "tilt": -12,       # 人物傾斜角度 (負 = 順時針：頭往右上、腳往左下)
        "char_scale": 1.0, # 人物大小 = 剛好完整放進畫窗的幾倍
        "offset": (-0.03, -0.05),
        # 打光 (relight.py)：背景是大量彈幕 ➔ 背光 + 輪廓光，翅膀紋路與眼睛發光；眼睛座標是 10_char.png 上的位置
        "light": {"eyes": [(619, 635), (653, 640)]},   # 人物位置微調 (畫窗寬高的比例；使用者：往左上一點，靠近中心，左側翅膀切掉一點沒關係)
    },
}


def category_of(char_id: str) -> str:
    for path in glob.glob(os.path.join(PROJECT_ROOT, "Characters", "*", f"{char_id}.json")):
        return os.path.basename(os.path.dirname(path))
    raise SystemExit(f"找不到角色：{char_id}")


def stage_dir(char_id: str, rarity: str) -> str:
    d = os.path.join(PROJECT_ROOT, "images", "Original", category_of(char_id), char_id, rarity)
    os.makedirs(d, exist_ok=True)
    return d


def workflow(char_id: str, rarity: str, layer: str, seed: int) -> dict:
    spec = LAYERS[(char_id, rarity)]
    if layer == "bg":
        positive = ", ".join([spec["bg"], QUALITY])
        negative = spec["bg_negative"]
        denoise, hd = 0.4, (1748 * HD, 2432 * HD)
    else:
        positive = ", ".join([BASE[char_id], spec["char"], CHAR_COMPOSITION, QUALITY])
        negative = ", ".join(filter(None, [NEGATIVE, EXTRA_NEGATIVE.get(char_id), CHAR_NEGATIVE]))
        l, t, r, b = window_box()
        denoise, hd = 0.35, ((r - l) * HD, (b - t) * HD)
    (bw, bh), (hw, hh) = SIZES[layer]["base"], SIZES[layer]["hires"]
    prefix = f"touhou_card/hd/{char_id}_{rarity}_{layer}_s{seed}"
    sampler = {"steps": 28, "cfg": 5.0, "sampler_name": "euler_ancestral", "scheduler": "normal"}
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "animagine-xl-4.0-opt.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": positive}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": bw, "height": bh, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                                                   "latent_image": ["4", 0], "seed": seed, "denoise": 1.0, **sampler}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": prefix + "_1base"}},
        # 重繪：先用放大模型放大再縮到 hires 尺寸，低 denoise 重畫一次補細節
        "8": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "4x-UltraSharp.pth"}},
        "9": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["8", 0], "image": ["6", 0]}},
        "10": {"class_type": "ImageScale", "inputs": {"image": ["9", 0], "upscale_method": "lanczos", "width": hw, "height": hh, "crop": "disabled"}},
        "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["1", 2]}},
        "12": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                                                    "latent_image": ["11", 0], "seed": seed + 1, "denoise": denoise, **sampler}},
        "13": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["12", 0], "vae": ["1", 2], "tile_size": 1024,
                                                          "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
        "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": prefix + "_2hires"}},
        # 高清：放大模型 4 倍再縮到 16 倍像素的目標尺寸
        "15": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["8", 0], "image": ["13", 0]}},
        "16": {"class_type": "ImageScale", "inputs": {"image": ["15", 0], "upscale_method": "lanczos", "width": hd[0], "height": hd[1], "crop": "disabled"}},
        "17": {"class_type": "SaveImage", "inputs": {"images": ["16", 0], "filename_prefix": prefix + "_3hd"}},
    }


def outpaint_workflow(char_id: str, rarity: str, src: str, seed: int, pads=(240, 200, 200, 100), shrink=(680, 820)) -> dict:
    """往外擴圖 (補完被切掉的翅膀、腳)：原圖縮小到 shrink，四周加 pads (左, 上, 右, 下) 讓 AI 補畫，一次 2 張
    src 要先複製到 ComfyUI/input/"""
    spec = LAYERS[(char_id, rarity)]
    positive = ", ".join([BASE[char_id], spec["char"], CHAR_COMPOSITION, QUALITY])
    negative = ", ".join(filter(None, [NEGATIVE, EXTRA_NEGATIVE.get(char_id), CHAR_NEGATIVE]))
    l, t, r, b = pads
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "animagine-xl-4.0-opt.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": positive}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},
        "4": {"class_type": "LoadImage", "inputs": {"image": src}},
        "5": {"class_type": "ImageScale", "inputs": {"image": ["4", 0], "upscale_method": "lanczos", "width": shrink[0], "height": shrink[1], "crop": "disabled"}},
        "6": {"class_type": "ImagePadForOutpaint", "inputs": {"image": ["5", 0], "left": l, "top": t, "right": r, "bottom": b, "feathering": 40}},
        "7": {"class_type": "VAEEncodeForInpaint", "inputs": {"pixels": ["6", 0], "vae": ["1", 2], "mask": ["6", 1], "grow_mask_by": 16}},
        "8": {"class_type": "RepeatLatentBatch", "inputs": {"samples": ["7", 0], "amount": 2}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["8", 0],
                                                   "seed": seed, "steps": 28, "cfg": 5.0, "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": f"touhou_card/hd/{char_id}_{rarity}_outpaint_s{seed}"}},
    }


def upscale_workflow(char_id: str, rarity: str, src: str, seed: int) -> dict:
    """拿現成的人物圖 (例如之前生成、翅膀完整的) 走重繪 → 高清；src 要先複製到 ComfyUI/input/
    輸出跟 workflow() 同名，collect 可以直接收"""
    spec = LAYERS[(char_id, rarity)]
    positive = ", ".join([BASE[char_id], spec["char"], CHAR_COMPOSITION, QUALITY])
    negative = ", ".join(filter(None, [NEGATIVE, EXTRA_NEGATIVE.get(char_id), CHAR_NEGATIVE]))
    w, h = Image.open(os.path.join(COMFY_OUT, "..", "input", src)).size
    hw, hh = int(w * 1.5) // 8 * 8, int(h * 1.5) // 8 * 8
    prefix = f"touhou_card/hd/{char_id}_{rarity}_char_s{seed}"
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "animagine-xl-4.0-opt.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": positive}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},
        "6": {"class_type": "LoadImage", "inputs": {"image": src}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": prefix + "_1base"}},
        "8": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "4x-UltraSharp.pth"}},
        "9": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["8", 0], "image": ["6", 0]}},
        "10": {"class_type": "ImageScale", "inputs": {"image": ["9", 0], "upscale_method": "lanczos", "width": hw, "height": hh, "crop": "disabled"}},
        "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["1", 2]}},
        "12": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["11", 0],
                                                    "seed": seed, "steps": 28, "cfg": 5.0, "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 0.35}},
        "13": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["12", 0], "vae": ["1", 2], "tile_size": 1024,
                                                          "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
        "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": prefix + "_2hires"}},
        "15": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["8", 0], "image": ["13", 0]}},
        "17": {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": prefix + "_3hd"}},
    }


def collect(char_id, rarity, layer, seed):
    d = stage_dir(char_id, rarity)
    names = {"bg": ["01_bg_base", "02_bg_hires", "03_bg_hd"], "char": ["06_char_base", "07_char_hires", "08_char_hd"]}[layer]
    for step, name in zip(["1base", "2hires", "3hd"], names):
        files = sorted(glob.glob(os.path.join(COMFY_OUT, "touhou_card", "hd", f"{char_id}_{rarity}_{layer}_s{seed}_{step}_*.png")))
        if not files:
            raise SystemExit(f"找不到 ComfyUI 輸出：{layer} s{seed} {step}")
        shutil.copy(files[-1], os.path.join(d, name + ".png"))
        print("✅", name)


def make_bg(char_id, rarity):
    d = stage_dir(char_id, rarity)
    spec = LAYERS[(char_id, rarity)]
    bg = Image.open(os.path.join(d, "03_bg_hd.png")).convert("RGB")
    bg = ImageEnhance.Brightness(bg).enhance(spec.get("dim", 0.62))
    # 彈幕畫滿整張卡 (沒有框的完整原圖也有彈幕)，大小以畫窗為基準
    l, t, r, b = window_box()
    glow, core = draw_danmaku(bg.size, seed=1, style=spec.get("style", "rainbow"), scale=(r - l) * HD / BASE_W)
    bg = ImageChops.add(bg, ImageEnhance.Brightness(glow).enhance(spec.get("glow", 0.6))).convert("RGBA")
    bg.alpha_composite(core)
    bg = bg.convert("RGB")
    bg.save(os.path.join(d, "04_bg_fx_hd.png"))
    print("✅ 04_bg_fx_hd")
    bg.resize((bg.width // HD, bg.height // HD), Image.LANCZOS).save(os.path.join(d, "05_bg.png"))
    print("✅ 05_bg")


def make_char(char_id, rarity):
    d = stage_dir(char_id, rarity)
    src = os.path.join(d, "08_char_hd.png")
    subprocess.run([COMFY_PY, "-I", os.path.join(HERE, "cutout.py"), src, d], check=True)
    os.replace(os.path.join(d, "08_char_hd_cut.png"), os.path.join(d, "09_char_cut_hd.png"))
    print("✅ 09_char_cut_hd")
    spec = LAYERS[(char_id, rarity)]
    ch = Image.open(os.path.join(d, "09_char_cut_hd.png")).convert("RGBA")
    ch = ch.crop(ch.split()[3].point(lambda v: 255 if v > 8 else 0).getbbox())   # 去掉四周空白
    if spec.get("tilt"):
        ch = ch.rotate(spec["tilt"], resample=Image.BICUBIC, expand=True)
        ch = ch.crop(ch.getbbox())
    l, t, r, b = window_box()
    scale = min((r - l) / ch.width, (b - t) / ch.height) * spec.get("char_scale", 1.0)   # 完整放進畫窗
    ch = ch.resize((round(ch.width * scale), round(ch.height * scale)), Image.LANCZOS)
    # 放到畫窗大小的透明畫布：預設置中，offset (畫窗寬高的比例) 微調位置，超出畫窗的部分切掉
    dx, dy = spec.get("offset", (0, 0))
    canvas = Image.new("RGBA", (r - l, b - t), (0, 0, 0, 0))
    canvas.alpha_composite(ch, (round((canvas.width - ch.width) / 2 + dx * canvas.width),
                                round((canvas.height - ch.height) / 2 + dy * canvas.height)))   # 超出部分 PIL 會自動裁掉
    canvas.save(os.path.join(d, "10_char.png"))
    print("✅ 10_char")
    if spec.get("light") is not None:
        make_light(char_id, rarity)


def make_light(char_id, rarity):
    d = stage_dir(char_id, rarity)
    opts = LAYERS[(char_id, rarity)].get("light")
    if opts is None:
        raise SystemExit("LAYERS 沒有 light 設定")
    l, t, r, b = window_box()
    win = Image.open(os.path.join(d, "05_bg.png")).convert("RGB").crop((l, t, r, b))
    relight(Image.open(os.path.join(d, "10_char.png")), win, opts).save(os.path.join(d, "10b_char_lit.png"))
    print("✅ 10b_char_lit")


def char_layer(d):
    """疊層用的人物：PhotoCraft 手修版 (10c) > 打光版 (10b) > 10"""
    for name in ("10c_char_photocraft.png", "10b_char_lit.png", "10_char.png"):
        if os.path.exists(os.path.join(d, name)):
            return os.path.join(d, name)


def layered_paths(char_id, rarity):
    """build_cards 用：有 05_bg.png 與 10_char.png 就回傳 (背景, 人物)，否則 None"""
    try:
        d = os.path.join(PROJECT_ROOT, "images", "Original", category_of(char_id), char_id, rarity)
    except SystemExit:
        return None
    bg, ch = os.path.join(d, "05_bg.png"), char_layer(d)
    return (bg, ch) if os.path.exists(bg) and os.path.exists(ch) else None


def compose(char_id, rarity):
    from animate import RARITY_EFFECTS, save_animation
    from build_cards import ART_DIR, EN_NAMES, load_characters
    d = stage_dir(char_id, rarity)
    char = load_characters()[char_id]
    stages = render_layered_stages(os.path.join(d, "05_bg.png"), char_layer(d), rarity,
                                   char["gacha"]["titles"][rarity], EN_NAMES[char_id])
    names = {"art": "11_art", "bg_frame": "12_bg_frame", "frame_char": "13_frame_char", "text": "14_text", "card": "15_card"}
    for key, name in names.items():
        stages[key].save(os.path.join(d, name + ".png"))
        print("✅", name)
    shutil.copy(os.path.join(d, "11_art.png"), os.path.join(ART_DIR, f"{char_id}_{rarity}.png"))
    shutil.copy(char_layer(d), os.path.join(ART_DIR, f"{char_id}_{rarity}_char.png"))   # 沒有背景的人物 (使用者：UR / LR 都要留)
    print(f"✅ Art/{char_id}_{rarity}.png、{char_id}_{rarity}_char.png")
    if rarity in RARITY_EFFECTS:
        kb = save_animation(stages["card"], RARITY_EFFECTS[rarity], os.path.join(d, "16_card.gif")) / 1024
        print(f"✅ 16_card.gif ({kb:.0f} KB)")


def main():
    cmd, char_id, rarity, *rest = sys.argv[1:]
    if cmd == "wf-outpaint":
        src, seed, out = rest[0], int(rest[1]), rest[2]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(outpaint_workflow(char_id, rarity, src, seed), f, ensure_ascii=False, indent=2)
        print("wrote", out)
    elif cmd == "wf-up":
        src, seed, out = rest[0], int(rest[1]), rest[2]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(upscale_workflow(char_id, rarity, src, seed), f, ensure_ascii=False, indent=2)
        print("wrote", out)
    elif cmd == "wf":
        layer, seed, out = rest[0], int(rest[1]), rest[2]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(workflow(char_id, rarity, layer, seed), f, ensure_ascii=False, indent=2)
        print("wrote", out)
    elif cmd == "collect":
        collect(char_id, rarity, rest[0], int(rest[1]))
    elif cmd == "bg":
        make_bg(char_id, rarity)
    elif cmd == "char":
        make_char(char_id, rarity)
    elif cmd == "light":
        make_light(char_id, rarity)
    elif cmd == "compose":
        compose(char_id, rarity)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()

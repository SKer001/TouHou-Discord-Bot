"""高清分層卡面流程：**N～LR 全部階級都走這套** (使用者 2026-11-11 指定，原本只有 UR / LR)，每一步的產出與修改後的圖都保留，方便之後微調
順序：背景 ➔ 彈幕 (只有 UR / LR) ➔ 翅膀 (有翅膀的角色先做) ➔ 人物 ➔ 卡框 ➔ 文字 / 等級 ➔ 特效 (SSR 閃光、UR 雷射、LR 雷射 + 星光)
彈幕越多背景壓越暗 (auto_dim)，不然畫面很亂；N～SSR 沒有彈幕、背景不壓暗
步驟檔放在 images/Original/<分類>/<角色>/<階級>/ (分類 = Characters/ 的資料夾，例如 TH05)：

  背景  01_bg_base.png     SDXL 生成 (跟卡面同比例 864×1200)
        02_bg_hires.png    放大 2 倍再重繪補細節 (1728×2400)
        03_bg_hd.png       4x-UltraSharp 放大成卡面 4×4 = 16 倍像素 (6992×9728)
        04_bg_fx_hd.png    UR / LR：壓暗 + 程式畫的彈幕 (高清畫，邊緣乾淨)；N～SSR：直接沿用 03 (不壓暗、沒有彈幕)
        05_bg.png          壓縮成卡面大小 (1748×2432) ★
  人物  06_char_base.png   SDXL 生成完整全身、白底 (跟畫窗同比例 936×1128)
        07_char_hires.png  放大 1.5 倍重繪 (1400×1688)
        08_char_hd.png     放大成畫窗 16 倍像素 (5316×6384)
        09_char_cut_hd.png 去背 (BiRefNet)
        10_char.png        裁掉空白、傾斜 (tilt)、縮到剛好完整放進畫窗 (× char_scale)，放到畫窗大小的畫布 (offset 微調，超出切掉) ★
        10b_char_lit.png   打光 (relight.py：背光、輪廓光、翅膀紋路與眼睛發光；LAYERS 有 light 才做) ★ 有這張就用這張
  翅膀  W1_crystal_X.png     單獨生成的水晶 (不要人物、白底) → W2_crystal_X_hd.png 放大 → W3_crystal_X_cut.png 去背 (只留最大一塊)
        W4_wings.png       依 LAYERS 的 wings 排在人物背後 (左右對稱) → W5_wings_lit.png 打光 → 10d_char_wings.png 疊在人物下面 ★
  尾流  T1_trail.png        trail.py 畫的掃帚尾流 (光帶 + 星星，LAYERS 的 trail，錨點 = 掃帚尾端的 06 座標) → 10e_char_trail.png 疊在人物下面 ★
  環繞  O1_orb.png          單獨生成的物件 (例如陰陽玉) → O3_orb_cut.png 去背 → O4_orbs_back / front.png (orbs.py 排成斜橢圓，後半在人物後、前半在人物前)
                           → 10f_char_orbs.png ★
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
  python hd_card.py orbs <角色> <階級>                               O3、O4、10f (環繞物件圈，LAYERS 的 orbs；O1 要先放好)
  python hd_card.py trail <角色> <階級>                              T1、10e (掃帚尾流，LAYERS 的 trail)
  python hd_card.py wings <角色> <階級>                              W3~W5、10d (翅膀層，LAYERS 的 wings；W2 要先放好)
  python hd_card.py compose <角色> <階級>                            11~16
"""
import glob
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from card import PROJECT_ROOT, render_layered_stages, window_box  # noqa: E402
from danmaku import BASE_W, draw_danmaku  # noqa: E402
from relight import relight  # noqa: E402
from wings import arrange, clean_crystal  # noqa: E402
from trail import draw_trail  # noqa: E402
from orbs import ring  # noqa: E402
from make_workflow import BASE, NEGATIVE, QUALITY, EXTRA_NEGATIVE  # noqa: E402

Image.MAX_IMAGE_PIXELS = None                      # 高清背景 6992×9728 超過 PIL 預設上限
COMFY_OUT = os.environ.get("COMFY_OUTPUT", os.path.expanduser(r"~\Documents\comfy\ComfyUI\output"))
COMFY_PY = os.environ.get("COMFY_PYTHON", os.path.expanduser(r"~\Documents\comfy\venv\Scripts\python.exe"))
HD = 4                                             # 長寬各 4 倍 = 16 倍像素
SIZES = {   # 生成尺寸、重繪倍率
    "bg": {"base": (864, 1200), "hires": (1728, 2400)},
    "char": {"base": (936, 1128), "hires": (1400, 1688)},
}
# 共用構圖不提翅膀 (會讓沒有翅膀的角色長出翅膀)；有翅膀的角色寫在 LAYERS 的 "char"，或改用翅膀分層
CHAR_COMPOSITION = ("solo, full body, entire body visible, head to toe, "
                    "very wide shot, zoomed out, small figure in the center, lots of empty white space around, "   # 不加的話腳會被切掉
                    "simple background, white background, plain background")
CHAR_NEGATIVE = ("background scenery, danmaku, effects, cropped, cut off feet, "
                 "black border, letterbox, frame, close-up, large figure")

# 每張分層卡的提示詞：bg = 背景 (不要人物)、char = 人物動作表情、base = 取代 make_workflow.BASE 的外觀 (例如拿掉翅膀標籤)、style = 彈幕風格 (danmaku.py)、dim = 背景亮度
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
        "offset": (-0.03, -0.05),   # 人物位置微調 (畫窗寬高的比例；使用者：往左上一點，靠近中心，左側翅膀切掉一點沒關係)
        # 打光 (relight.py)：背景是大量彈幕 ➔ 背光 + 輪廓光，翅膀紋路與眼睛發光；眼睛座標是 10_char.png 上的位置
        "light": {"eyes": [(619, 635), (653, 640)]},
    },
    # 靈夢 UR「博麗大結界之守護者」夢想天生：幻想鄉夜空 + 發光的博麗大結界 + 封印風格彈幕 (七彩大光球、符札、小陰陽玉)；
    # 使用者：正面、由上往下看著鏡頭 (仰拍)、淡淡微笑、強者感；陰陽玉做成獨立圖層繞一圈 (orbs)
    ("reimu", "UR"): {
        "bg": ("no humans, scenery, night sky high above gensokyo, huge translucent glowing barrier dome in the sky, "
               "hexagonal barrier pattern, shimmering light curtain, starry sky, moon, sea of clouds, distant mountains and torii far below, "
               "deep blue and violet, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "char": ("floating in the air, facing viewer, looking down at viewer, from below, half-closed eyes, faint smile, calm, "
                 "confident, overwhelming presence, holding gohei raised, detached sleeves fluttering, hair ribbon fluttering, "
                 "skirt fluttering"),
        "char_negative": "magic effects, orbs, yin yang orb, light, sparkles, ofuda, wings, multiple girls",
        "style": "seal",
        "density": 0.75,
        "glow": 0.55,
        "char_scale": 0.75,
        "light": {"dark": 0.35},   # 背光；眼睛座標選好人物再補
        # 陰陽玉環 (orbs.py)：anchor = 腰部 (06 基本圖座標)；rx / size 是畫窗寬度比例、ry 是畫窗高度比例
        "orbs": {"anchor": (525, 610), "crop_square": True, "count": 6, "rx": 0.42, "ry": 0.07, "tilt": -8, "size": 0.085,
                 "depth": 0.35, "phase": 30, "spin": 37, "link": 0.55, "link_color": (255, 120, 140)},
    },
    # 魔理沙 UR「極光之魔彈專家」戀符「Master Spark」：雲海上的夜空 + 極光 + 星彈；騎掃帚，掃帚尾流做成獨立圖層 (trail)
    ("marisa", "UR"): {
        "bg": ("no humans, scenery, night sky above the sea of clouds, brilliant aurora, milky way, galaxy, "
               "countless stars, shooting stars, deep blue and purple, glowing horizon, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, broom, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "char": ("riding a single broom, sitting sideways on the broom handle, broom bristles behind her, flying fast to the right, "
                 "whole broom visible, one hand holding the broom, other hand holding mini-hakkero forward, "
                 "intense grin, confident, hair and hat ribbon fluttering, dress fluttering"),
        "extra_negative": "standing, walking, broom on shoulder",   # 魔理沙共用的「不要拿著掃帚」會跟騎掃帚打架
        "char_negative": ("wings, angel wings, feathered wings, magic effects, light trail, motion lines, sparkles, stars, laser, "
                          "multiple brooms, two brooms, bristles on both ends, extra hat, floating hat"),
        "style": "stars",
        "density": 0.75,   # UR：大量彈幕，比 LR 少一點
        "glow": 0.55,
        "char_scale": 0.75,   # 使用者：人物放大一點
        "tilt": -12,               # 原圖掃帚往右上斜 (像往左下俯衝)；使用者：比 -20 再逆時針轉一點，掃帚尾端翹向右上留空間給尾流
        "offset": (-0.14, 0.06),     # 往左挪，右邊留給尾流
        "light": {"dark": 0.35, "eyes": [(452, 803), (482, 807)], "eye_color": (255, 215, 120)},   # 背光 + 金色眼睛 (10_char.png 座標)
        # 掃帚尾流 (trail.py)：anchor = 掃帚尾端 (06 基本圖座標)；angle 是疊層後的方向 (從正上方順時針)
        # length 是畫窗高度的比例、width / wave 是畫窗寬度的比例
        "trail": {"anchor": (885, 572), "angle": 87, "length": 0.75, "width": 0.07, "wave": 0.035,
                  "spread": 34, "ribbons": 6, "stars": 50, "hue0": 0.12, "core": 1.2},
    },
    # 琪露諾 UR「絕對零度之最強⑨」凍符「Perfect Freeze」：冰封湖面 + 極光 + 少量凍結彈幕；人物放大、冰晶翅膀展開、得意大笑
    ("cirno", "UR"): {
        # 深藍色夜晚 + 極光：白色冰彈幕和背光的人物才看得清楚 (亮白雪地會讓彈幕糊成一片)
        "bg": ("no humans, scenery, frozen lake at night, vast ice field, giant ice crystals, frost patterns, "
               "brilliant aurora borealis, starry sky, deep blue and teal, cold glowing light, diamond dust, sparkling, "
               "crisp, beautiful, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, wings, text, watermark, lowres, worst quality, low quality, blurry, frame, border, white sky, overexposed",
        "char": ("dynamic pose, arms spread wide, casting ice magic, six ice crystal wings fully spread, "
                 "laughing, open mouth, smug, confident grin, v-shaped eyebrows, hair fluttering, dress fluttering, "
                 "frost particles around hands, slightly from below"),
        "style": "freeze",
        "density": 0.75,   # 使用者：UR 也要大量彈幕，比 LR 少一點
        "dim": 0.55,       # 夜景本來就暗，比 auto_dim 亮一點 (2026-11-11 使用者兩次要求再暗：0.8 ➔ 0.7 ➔ 0.55)
        "glow": 0.3,
        "char_scale": 0.6, # 人物 (不含翅膀) 的大小；加上翅膀後整體比例偏小 (跟 LR 一樣，彈幕當主角)
        # 人物不畫翅膀 (06h：使用者選的 1 號用手描身體輪廓把翅膀塗白)；背光 + 冰藍色眼睛，座標是 10_char.png 上的位置
        "light": {
            "dark": 0.4,   # 背景很亮，背光要壓暗多一點才看得出來
            "eyes": [(706, 500), (754, 524)], "eye_color": (150, 220, 255),
        },
        # 翅膀層 (wings.py)：單顆水晶 W1 生成 → W2 放大 → W3 去背 → W4 排在背後 → W5 打光，疊在人物下面
        "wings": {
            "crystals": {"D": "W1_crystal_D.png", "H": "W1_crystal_H.png"},   # 使用者選 D (細長雙尖) + H (寬短赫基蒙)
            "anchor": (545, 405),   # 背後 (兩肩之間) 的位置，06 基本圖座標
            # angle：從正上方順時針 (右側，左側自動鏡射)；length / r0：畫窗高度的比例；先寫的在下面
            "items": [
                {"crystal": "H", "angle": 112, "length": 0.2, "r0": 0.03, "width": 0.65},   # width：粗細 (水晶原圖偏胖)
                {"crystal": "D", "angle": 72, "length": 0.32, "r0": 0.03, "width": 0.6},
                {"crystal": "D", "angle": 38, "length": 0.38, "r0": 0.03, "width": 0.6},
            ],
            # 使用者：亮到接近白色但還是藍色系、淡淡的彩虹稜鏡 (像水晶散射彩虹光)
            "light": {"dark": 0.0, "rim": 0.5, "halo": 0.5,
                      "emissive": [{"mask": "alpha", "color": (170, 222, 255), "strength": 1.0, "body": 0.75, "prism": 0.45}]},
        },
    },
    # 大妖精 N / R / SR (2026-11-11 改走高清分層)：明亮白天的霧之湖；人物不畫翅膀 (base 拿掉 BASE 的翅膀標籤 + char_negative)，
    # 翅膀另外做 (W1 單片妖精翅膀：半透明、淡綠、帶彩虹光，三個階級共用同一組素材)；N～SR 沒有彈幕、不打光，人物比 UR 大
    ("daiyousei", "N"): {
        # N「霧之湖的大妖精」：清晨湖邊淺灘，赤腳踩水、提著裙擺回頭看遠方的霧，溫和恬靜
        "bg": ("no humans, scenery, misty lake, lakeside, shallow water, morning mist, reeds, lily pads, ripples, "
               "soft sunlight, daytime, bright, blue sky, distant forest, pastel colors, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, wings, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, daiyousei, touhou, green hair, short hair, side ponytail, yellow hair ribbon, hair bow, green eyes, "
                 "blue dress, white shirt, puffy short sleeves, yellow neckerchief"),
        "char": ("standing on both feet, both legs visible, barefoot, lightly holding skirt hem, looking back over shoulder, from side, looking into the distance, "
                 "gentle smile, calm, soft expression, hair fluttering"),
        "char_negative": "(wings:1.4), (fairy wings:1.3), insect wings, transparent wings, butterfly wings, angel wings, staff, wand, weapon, ribbon streamer, cape, scarf, "
                         "water, splash",
        "inline_wings": True,   # 2026-11-11 使用者：翅膀層版本怪怪的 ➔ 改成人物直接帶翅膀
        "char_scale": 0.95,
        "wings": {   # 錨點是 06 基本圖上的背部 (兩肩之間) 估計值，人物定案後再精準調
            "crystals": {"A": "W1_crystal_A.png"},
            "anchor": (480, 300),   # 06 人物圖的背部 (2026-11-11 人物定案後量的)
            # W5 翅膀素材本身就是一大一小兩片，一邊一個、左右鏡射
            "items": [{"crystal": "A", "angle": 35, "length": 0.3, "r0": 0.0, "width": 1.0}],
            "light": {"dark": 0.0, "rim": 0.2, "halo": 0.2,
                      "emissive": [{"mask": "alpha", "color": (200, 255, 210), "strength": 0.4, "body": 0.9, "prism": 0.35}]},
        },
    },
    ("daiyousei", "R"): {
        # R「湖畔的守護精靈」：站在湖岸張開雙手擋在前面 (像在護著琪露諾)，略帶擔心又堅定 (N～SR 沒有彈幕，原本的綠色小彈拿掉)
        # 2026-11-11：跳躍 / 半空的姿勢模型一定會畫翅膀，塗掉又讓臉和手變形 ➔ 使用者選改成站在地上重生
        "bg": ("no humans, scenery, lake shore, misty lake, mist over water, water splash, wind, forest edge, "
               "daytime, bright sunlight, blue sky, clouds, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, wings, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, daiyousei, touhou, green hair, short hair, side ponytail, yellow hair ribbon, hair bow, green eyes, "
                 "blue dress, white shirt, puffy short sleeves, yellow neckerchief"),
        "char": ("standing, feet on ground, firm stance, legs apart, arms outstretched to the sides, protective pose, shielding, "
                 "worried expression, determined, looking to the side, hair flowing in wind, skirt fluttering, from side"),
        "char_negative": "(wings:1.4), (fairy wings:1.3), insect wings, transparent wings, butterfly wings, angel wings, staff, wand, weapon, ribbon streamer, cape, scarf, "
                         "danmaku, bullets, (wings on back:1.5), (white wings:1.4), flying, floating, midair, jumping",   # 半空姿勢會讓模型自動畫出翅膀
        "inline_wings": True,   # 2026-11-11 使用者：翅膀層版本怪怪的 ➔ 改成人物直接帶翅膀
        "char_scale": 0.95,
        "wings": {
            "crystals": {"A": "W1_crystal_A.png"},
            "anchor": (438, 625),   # 06 人物圖的背部 (2026-11-11 人物定案後量的)
            # W5 翅膀素材本身就是一大一小兩片，一邊一個、左右鏡射
            "items": [{"crystal": "A", "angle": 40, "length": 0.3, "r0": 0.0, "width": 1.0}],
            "light": {"dark": 0.0, "rim": 0.2, "halo": 0.2,
                      "emissive": [{"mask": "alpha", "color": (200, 255, 210), "strength": 0.4, "body": 0.9, "prism": 0.35}]},
        },
    },
    ("daiyousei", "SR"): {
        # SR「翠綠的大自然精靈」：湖畔森林、花草盛開；浮在空中雙手合十、閉眼祈禱，安詳 (捧綠光會畫成一團雲，改掉)
        "bg": ("no humans, scenery, forest clearing by a misty lake, blooming flowers, flower field, vines, swirling leaves, "
               "flower petals, light rays through trees, sunbeam, daytime, bright, lush green, magical, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, wings, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, daiyousei, touhou, green hair, short hair, side ponytail, yellow hair ribbon, hair bow, green eyes, "
                 "blue dress, white shirt, puffy short sleeves, yellow neckerchief"),
        "char": ("floating, both legs visible, hands clasped together in front of chest, own hands together, closed eyes, "
                 "serene, praying, gentle, hair flowing, dress fluttering, slightly from below"),
        "char_negative": "(wings:1.4), (fairy wings:1.3), insect wings, transparent wings, butterfly wings, angel wings, staff, wand, weapon, ribbon streamer, cape, scarf, "
                         "leaves, petals, flowers",
        "inline_wings": True,   # 2026-11-11 使用者：翅膀層版本怪怪的 ➔ 改成人物直接帶翅膀
        "char_scale": 0.9,
        "wings": {
            "crystals": {"A": "W1_crystal_A.png"},
            "anchor": (495, 455),   # 06 人物圖的背部 (2026-11-11 人物定案後量的)
            # W5 翅膀素材本身就是一大一小兩片，一邊一個、左右鏡射
            "items": [{"crystal": "A", "angle": 38, "length": 0.32, "r0": 0.0, "width": 1.0}],
            "light": {"dark": 0.0, "rim": 0.25, "halo": 0.3,
                      "emissive": [{"mask": "alpha", "color": (190, 255, 200), "strength": 0.6, "body": 0.95, "prism": 0.45}]},
        },
    },
    # 芙蘭朵露 SSR / UR / LR (TH06，2026-11-11)：金色側馬尾、紅眼、白色暴民帽 + 紅緞帶、紅背心裙 + 白襯衫、黃色領巾；
    # 角色名一出現模型就會畫翅膀，負面權重加重只會讓圖壞掉 ➔ 人物直接帶翅膀 (SSR 選的 C2 是「不帶翅膀」提示詞但照樣長出翅膀，所以不開 inline 才能跟生成時一致)
    # 使用者選：SSR B1 (s1101) C2 (s2202)、UR B2 (s2202) C3 (s3303)、LR B1 (s1101) + 人物照 C4 的俯瞰視角重生、翅膀要像原作、彈幕少一點
    ("flandre", "SSR"): {
        # SSR「惡魔的妹」：紅魔館地下室的玩具房，燭光溫暖明亮；抱著布偶歪頭笑，天真又有一點危險 (布偶線頭鬆脫)
        "bg": ("no humans, scenery, basement room of a gothic western mansion, toy room, red carpet, scattered toys, stuffed animals, "
               "teddy bears, dolls on shelves, building blocks, candles, candlelight, chandelier, red velvet curtains, red and dark wood, "
               "warm light, bright, cozy, gothic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, wings, text, watermark, lowres, worst quality, low quality, blurry, frame, border, dark, horror, blood",
        "base": ("1girl, flandre scarlet, touhou, blonde hair, one side up, side ponytail, red eyes, mob cap, white headwear, hat ribbon, red ribbon, "
                 "red vest, red skirt, frilled skirt, white shirt, puffy short sleeves, yellow ascot, wrist cuffs, white socks, red shoes"),
        "char": ("standing, hugging stuffed animal, holding teddy bear, head tilt, innocent smile, open mouth, fang, playful, "
                 "one leg raised behind, looking at viewer, hair ribbon fluttering, skirt fluttering"),
        "char_negative": "(wings:1.5), (crystal wings:1.5), (crystals:1.3), demon wings, bat wings, weapon, staff, wand, blue hair, remilia scarlet",
        "inline_wings_tags": ("crystal wings, wings, black branch-like wings, colorful crystals hanging from wings, "
                         "rainbow crystals, multicolored crystals"),   # 只有 inline 候選用 (inline_wings 預設不開)
        "char_scale": 0.9,
    },
    ("flandre", "UR"): {
        # UR「毀滅一切的狂氣之妹」禁忌「萊瓦汀」：血紅滿月下燃燒的紅魔館 + 星弓彈幕；狂笑、萊瓦汀燃燒
        "bg": ("no humans, scenery, huge blood red full moon, crimson night sky, red mist, gothic western mansion silhouette, clock tower, "
               "burning, flames, embers, floating sparks, red clouds, dark red and black, dramatic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, wings, bat, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "base": ("1girl, flandre scarlet, touhou, blonde hair, one side up, side ponytail, red eyes, mob cap, white headwear, hat ribbon, red ribbon, "
                 "red vest, red skirt, frilled skirt, white shirt, puffy short sleeves, yellow ascot, wrist cuffs, white socks, red shoes"),
        "char": ("holding laevatein (touhou), holding black curved staff, flaming staff, fire, dynamic pose, swinging weapon, "
                 "crazy smile, wide-eyed, crazy eyes, constricted pupils, glowing eyes, fang, insane, slightly from below, "
                 "hair fluttering, skirt fluttering"),
        "char_negative": "(wings:1.5), (crystal wings:1.5), (crystals:1.3), demon wings, bat wings, blue hair, remilia scarlet, spear of the gungnir",
        "inline_wings": True,
        "inline_wings_tags": ("crystal wings, wings, black branch-like wings, colorful crystals hanging from wings, "
                         "rainbow crystals, multicolored crystals"),
        "style": "starbow",
        "density": 0.75,
        "glow": 0.55,
        "char_scale": 0.8,
        "light": {"dark": 0.35, "eyes": [(463, 882), (494, 872)], "eye_color": (255, 60, 60), "eye": 1.3, "eye_size": 3},   # 背光 + 紅眼發光 (10_char.png 座標，使用者要眼睛發亮)
    },
    ("flandre", "LR"): {
        # LR：被破壞的大廳、破掉的天花板外是巨大紅月 + 星弓彈幕；俯瞰視角，握碎萬物之「目」的手勢
        # 四重存在 (模型畫不出分身) 使用者說不一定要，稱號可以改
        "bg": ("no humans, scenery, destroyed grand hall, ruined gothic mansion interior, shattered stained glass windows, broken pillars, "
               "collapsed ceiling, huge red moon through broken ceiling, floating debris, floating rubble, glass shards in the air, "
               "crimson light, rainbow light, prismatic, dramatic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, wings, bat, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "base": ("1girl, flandre scarlet, touhou, blonde hair, one side up, side ponytail, red eyes, mob cap, white headwear, hat ribbon, red ribbon, "
                 "red vest, red skirt, frilled skirt, white shirt, puffy short sleeves, yellow ascot, wrist cuffs, white socks, red shoes"),
        "char": ("from above, high angle, full body, floating in midair, looking up at viewer, reaching toward viewer, open hand, "
                 "other hand holding laevatein (touhou), black curved staff, laughing, crazy smile, glowing eyes, fang, "
                 "hair flowing, skirt fluttering"),
        "char_negative": "(wings:1.5), (crystal wings:1.5), (crystals:1.3), demon wings, bat wings, blue hair, remilia scarlet, fire, "
                         "tree, bare tree, many branches, tangled branches, thorns, cropped",
        "inline_wings": True,
        # 原作翅膀 (萌娘百科)：一對扭曲的細黑枝條，每根吊一排水晶；顏色由內到外 天藍、藍、紫、粉、橙、黃、淺綠、天藍，沒有紅色 (不是彩虹七色)
        "inline_wings_tags": ("crystal wings, wings, (one pair of thin black wings:1.2), (single thin twisted branch on each side:1.2), symmetrical wings, "
                              "(crystals hanging in a row:1.2), light blue, blue, purple, pink, orange, yellow, light green crystals, "
                              "small diamond-shaped crystal pendants, (no red crystals:1.1)"),
        "style": "starbow",
        "density": 0.7,   # 使用者：彈幕太多
        "glow": 0.6,
        "char_scale": 0.8,
        "light": {"dark": 0.35, "eyes": [(644, 981), (697, 953)], "eye_color": (255, 60, 60), "eye": 1.3, "eye_size": 3,   # 紅眼發光 (同 UR)
                  # 翅膀水晶各自發光 (使用者要)：crystal_mask.py 依色相抓出水晶存成遮罩，每組用自己的顏色發光
                  "emissive": [{"mask": f"10m_crystal_{g}.png", "color": c, "strength": 0.8, "body": 0.5}
                               for g, c in (("warm", (255, 190, 90)), ("green", (150, 255, 160)), ("blue", (120, 200, 255)), ("purple", (230, 140, 255)))]},
    },
    # 蕾米莉亞 SSR / UR / LR (TH06，2026-11-11 候選)：萌娘百科外貌 = 淡藍短髮 (有時偏紫)、血紅眼、虎牙、淡粉色苞帽 + 左邊紅色大蝴蝶結、背後大蝴蝶結、
    # 比身高還大的蝙蝠翅膀 ➔ 人物直接帶翅膀 (inline_wings_tags = 蝙蝠翅膀)
    ("remilia", "SSR"): {
        # SSR「鮮紅的惡魔」：紅魔館夜晚的玫瑰庭園、紅色滿月；收起的洋傘、高傲的笑
        "bg": ("no humans, scenery, night, rose garden of a gothic western mansion, red roses, rose bushes, stone fountain, garden lanterns, "
               "red brick mansion in background, clock tower, huge red full moon, starry sky, thin red mist, moonlight, elegant, "
               "highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, wings, bat, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "base": ("1girl, remilia scarlet, touhou, light blue hair, short hair, red eyes, slit pupils, fang, mob cap, pink headwear, hat ribbon, red ribbon, "
                 "pink dress, white dress, red trim, puffy short sleeves, wrist cuffs, red bow on back, white socks, red shoes"),
        "char": ("standing, holding closed parasol, pink parasol, hand on hip, smug, confident smile, fang, looking at viewer, "
                 "dress fluttering, elegant pose"),
        "char_negative": "flandre scarlet, blonde hair, crystal wings, crystals, weapon, spear",
        "inline_wings": True,
        "inline_wings_tags": ("bat wings, black bat wings, large wings, wings spread, demon wings"),
        "char_scale": 0.9,
    },
    ("remilia", "UR"): {
        # UR「紅魔館的夜之帝王」：紅魔館的王座大廳 (紅地毯、吊燈、彩繪玻璃透進紅月光)；翹腳坐在王座上拿紅酒杯、翅膀張開 + 紅色彈幕
        "bg": ("no humans, scenery, grand throne room of a gothic western mansion, ornate red velvet throne, red carpet, chandeliers, candles, "
               "tall stained glass windows, moonlight streaming in, dim lighting, dark interior, marble pillars, deep purple and black with gold accents, majestic, dramatic, "   # 背景偏暗紫黑，紅色彈幕才跳得出來
               "highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, wings, bat, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "base": ("1girl, remilia scarlet, touhou, light blue hair, short hair, red eyes, slit pupils, fang, mob cap, pink headwear, hat ribbon, red ribbon, "
                 "pink dress, white dress, red trim, puffy short sleeves, wrist cuffs, red bow on back, white socks, red shoes"),
        "char": ("sitting, crossed legs, holding wine glass, red wine, arrogant smile, fang, half-closed eyes, looking at viewer, "
                 "glowing eyes, chin rest, regal, full body"),
        "char_negative": "flandre scarlet, blonde hair, crystal wings, crystals, spear, chair, throne",
        "inline_wings": True,
        "inline_wings_tags": ("bat wings, black bat wings, large wings, wings spread, demon wings"),
        "style": "scarlet",
        "density": 0.75,
        "glow": 0.55,
        "char_scale": 0.8,
        "light": {"dark": 0.35, "eyes": [(602, 598), (668, 601)], "eye_color": (255, 60, 60), "eye": 1.3, "eye_size": 3},   # 背光 + 紅眼發光 (C3 s5505)
    },
    ("remilia", "LR"): {
        # LR「操縱命運之神槍惡魔」神槍「Spear the Gungnir」：紅霧籠罩的紅魔館上空、巨大紅月；舉起發光的紅色神槍要擲出
        "bg": ("no humans, scenery, night sky above a gothic western mansion, huge blood red full moon, dark purple night sky, thin red mist, "
               "dark clouds, clock tower far below, stars, dramatic, epic, deep purple and black, highly detailed, intricate details"),   # 天空偏暗紫黑 (紅色彈幕要跳)
        "bg_negative": "1girl, person, human, character, face, wings, bat, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "base": ("1girl, remilia scarlet, touhou, light blue hair, short hair, red eyes, slit pupils, fang, mob cap, pink headwear, hat ribbon, red ribbon, "
                 "pink dress, white dress, red trim, puffy short sleeves, wrist cuffs, red bow on back, white socks, red shoes"),
        "char": ("floating in midair, holding spear the gungnir, glowing red spear, huge red energy spear, about to throw, arm raised, "
                 "dynamic pose, fierce smile, fang, glowing eyes, dress fluttering, full body, from below"),
        "char_negative": "flandre scarlet, blonde hair, crystal wings, crystals, cropped",
        "inline_wings": True,
        "inline_wings_tags": ("bat wings, black bat wings, large wings, wings spread, demon wings"),
        "style": "scarlet",
        "density": 0.7,
        "glow": 0.6,
        "char_scale": 0.8,
        "light": {"dark": 0.35, "eyes": [(757, 736), (793, 729)], "eye_color": (255, 60, 60), "eye": 1.3, "eye_size": 3,   # 紅眼發光
                  # 神槍發光試過 (偏粉紅)，使用者選回原版，只留紅眼
                  },
    },
    # 帕秋莉 SR / SSR / UR (TH06，2026-11-12 桌機)：萌娘百科外貌 = 紫色長直髮、末端與兩邊鬢角用緞帶綁、紫瞳半睜眼；
    # 荷葉邊圓形睡帽 + 新月飾品；像睡衣的紫 / 淡紫直條紋長袍 + 淡紫長外衣；紅、藍兩色蝴蝶結；永遠拿著魔導書
    # 萌點：宅女、毒舌、慵懶、畏光、體力差 ➔ SR 慵懶看書、SSR 被打擾的不耐煩 + 施法、UR 認真起來的七曜大魔法
    ("patchouli", "SR"): {
        # SR「七曜的魔導士」：紅魔館地下大圖書館，坐在半空中的書堆上翻魔導書，半睜眼慵懶
        "bg": ("no humans, scenery, huge underground library, endless tall bookshelves, wooden ladders, floating books, stacks of books, "
               "reading desk, oil lamps, warm lamplight, candles, dust particles in light beams, arched ceiling, cozy, bright, "
               "highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, dark, horror",
        "base": ("1girl, patchouli knowledge, touhou, purple hair, very long hair, straight hair, hair ribbon, blunt bangs, purple eyes, "
                 "mob cap, crescent hat ornament, striped dress, vertical-striped dress, pink and purple dress, long sleeves, wide sleeves, "
                 "capelet, red bow, blue bow"),
        # 2026-11-12 使用者：坐姿很難跟背景搭 ➔ 改成浮在半空中邊飄邊看書
        "char": ("floating in midair, slightly reclining in the air, holding open book, reading, half-closed eyes, sleepy, bored expression, "
                 "relaxed, looking down at book, slight tilt of head, both legs visible, dress hanging down, from side"),
        "char_negative": "sitting, chair, stack of books, books on floor, furniture, weapon, staff, wand, wings, fire, magic circle",
        "char_scale": 0.9,
    },
    ("patchouli", "SSR"): {
        # SSR「不動的大圖書館」：被打擾 (偷書賊又來了) 的不耐煩，一手抱魔導書、一手往前施法，書頁翻飛、地上魔法陣發光
        "bg": ("no humans, scenery, great library, towering bookshelves, glowing magic circle on the floor, floating books, flying pages, "
               "swirling paper, purple magic particles, lamplight, bright, mystical, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, horror",
        "base": ("1girl, patchouli knowledge, touhou, purple hair, very long hair, straight hair, hair ribbon, blunt bangs, purple eyes, "
                 "mob cap, crescent hat ornament, striped dress, vertical-striped dress, pink and purple dress, long sleeves, wide sleeves, "
                 "capelet, red bow, blue bow"),
        "char": ("floating, holding book against chest, other arm outstretched, casting spell, open palm, annoyed, frown, half-closed eyes, "
                 "glaring at viewer, sleeves fluttering, hair flowing, dress fluttering, slightly from below"),
        "char_negative": "weapon, staff, wand, wings, broom, witch hat",
        "char_scale": 0.9,
    },
    ("patchouli", "UR"): {
        # UR「元素極致之大魔導士」日符「Royal Flare」/ 火水木金土符「賢者之石」：昏暗的大圖書館深處 + 七曜元素彈幕與魔法陣；
        # 浮在空中、魔導書自己翻開發光，周圍五顆元素水晶 (賢者之石)，認真起來的冷靜表情
        "bg": ("no humans, scenery, depths of a vast dark library, endless bookshelves fading into darkness, floating books, "
               "faint arcane glyphs, dim lighting, dark purple and black, deep shadows, mysterious, majestic, "   # 背景偏暗紫黑，七色彈幕才跳得出來
               "highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, bright, daylight",
        "base": ("1girl, patchouli knowledge, touhou, purple hair, very long hair, straight hair, hair ribbon, blunt bangs, purple eyes, "
                 "mob cap, crescent hat ornament, striped dress, vertical-striped dress, pink and purple dress, long sleeves, wide sleeves, "
                 "capelet, red bow, blue bow"),
        "char": ("floating in midair, open book floating in front of her, glowing book, one hand raised, casting spell, "
                 "five floating crystals around her, red crystal, blue crystal, green crystal, yellow crystal, orange crystal, "
                 "serious expression, calm, glowing eyes, hair flowing, sleeves fluttering, dress fluttering, full body, slightly from below"),
        "char_negative": "weapon, staff, wand, wings, broom, witch hat, cropped",
        "style": "elements",
        "density": 0.75,
        "glow": 0.55,
        "char_scale": 0.8,
        # 使用者選：SR B2 (s2202) C3 (s5505)、SSR B2 (s2202) C1 (s3303)、UR B1 (s1101) C1 (s3303)
        "light": {"dark": 0.35, "eyes": [(668, 588), (710, 571)], "eye_color": (200, 120, 255), "eye": 1.3, "eye_size": 3,   # 背光 + 紫眼發光 (10_char.png 座標)
                  # 環繞的水晶 (賢者之石) 各自發光 (使用者要)：自動抓飽和大色塊、排除身體範圍，使用者在預覽上圈補暗面後，依每顆的色相分組存成 10m_crystal_<組>.png
                  "emissive": [{"mask": f"10m_crystal_{g}.png", "color": c, "strength": 1.0, "body": 0.25, "keep_color": True}
                               for g, c in (("red", (255, 90, 90)), ("orange", (255, 170, 70)), ("yellow", (255, 230, 110)),
                                            ("green", (130, 255, 140)), ("blue", (110, 200, 255)), ("purple", (210, 140, 255)))]},
    },
    # 十六夜咲夜 SR / SSR / UR (TH06，2026-11-12 候選)：萌娘百科外貌 = 銀色短髮、兩側小麻花辮綁綠色絲帶、女僕髮卡、藍白女僕裝 (白圍裙、腰帶)、腰間懷錶、飛刀
    ("sakuya", "SR"): {
        # SR「紅魔館的女僕長」：白天的紅魔館走廊 (紅地毯、長窗)；端著紅茶托盤，微笑
        "bg": ("no humans, scenery, corridor of a gothic western mansion, red carpet, long hallway, tall arched windows, sunlight, "
               "red walls, paintings on walls, chandeliers, vases with flowers, elegant, bright, warm light, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, dark",
        "base": ("1girl, izayoi sakuya, touhou, silver hair, short hair, twin braids, side braids, green bow, hair bow, maid headdress, blue eyes, "
                 "maid, blue dress, blue skirt, white apron, waist apron, puffy short sleeves, wrist cuffs, white shirt, pocket watch, white socks, black shoes"),
        "char": ("standing, holding tray, tea set, teapot, teacup, gentle smile, closed mouth, looking at viewer, elegant, full body"),
        "char_negative": "remilia scarlet, wings, bat wings, long hair, blonde hair" + ", knife, weapon",
        "char_scale": 0.9,
    },
    ("sakuya", "SSR"): {
        # SSR「完美而瀟灑的從者」：紅魔館鐘樓內部 (巨大齒輪、時鐘背面透光)；指間夾著飛刀，帥氣地擺出投擲姿勢
        "bg": ("no humans, scenery, inside a clock tower, giant gears, cogwheels, huge clock face seen from behind, backlit clock glass, "
               "moonlight, wooden beams, gothic, steampunk, dust particles, blue and gold, dramatic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "base": ("1girl, izayoi sakuya, touhou, silver hair, short hair, twin braids, side braids, green bow, hair bow, maid headdress, blue eyes, "
                 "maid, blue dress, blue skirt, white apron, waist apron, puffy short sleeves, wrist cuffs, white shirt, pocket watch, white socks, black shoes"),
        "char": ("holding knife, knives between fingers, throwing knives, multiple knives, dynamic pose, about to throw, cool, "
                 "confident smile, looking at viewer, skirt fluttering, full body"),
        "char_negative": "remilia scarlet, wings, bat wings, long hair, blonde hair",
        "char_scale": 0.9,
    },
    ("sakuya", "UR"): {
        # UR「操縱時間的幻影女僕」：使用者給參考圖 (2026-11-12)：不一定強調時間能力，要有「強者感」——
        # 夜空巨大滿月在背後、人物強烈背光近乎剪影、紅眼發光、兩手指間夾著飛刀、壓低身體前傾、從容的冷笑、四周飄著紅色碎光
        "bg": ("no humans, scenery, night sky, huge full moon, bright moonlight, dark clouds, starry sky, floating red petals, red particles, "
               "rooftop of a gothic western mansion silhouette at bottom, deep navy blue and black, dramatic, cinematic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, clock, gears, daytime",
        "base": ("1girl, izayoi sakuya, touhou, silver hair, short hair, twin braids, side braids, green bow, hair bow, maid headdress, blue eyes, "
                 "maid, blue dress, blue skirt, white apron, waist apron, puffy short sleeves, wrist cuffs, white shirt, pocket watch, white socks, black shoes"),
        "char": ("holding knives, knives between fingers, knife in each hand, crouching, low stance, leaning forward, ready to strike, dutch angle, "
                 "smirk, confident, menacing, glowing eyes, red eyes, glowing red eyes, light trail from eyes, looking at viewer, "
                 "backlighting, rim light, dark shading, intimidating, hair fluttering, skirt fluttering, full body"),
        "char_negative": "remilia scarlet, wings, bat wings, long hair, blonde hair" + ", clock, pocket watch, giant clock, chain, gears, smile, happy",
        "style": "knives",
        "density": 0.7,
        "glow": 0.55,
        "char_scale": 0.8,
        # 使用者選 (桌機重生)：UR B1 (s3101) C3 (s7505)
        "light": {"dark": 0.5, "eyes": [(760, 385), (840, 385)], "eye_color": (255, 50, 50), "eye": 1.5, "eye_size": 3},   # 背光更強 (參考圖的剪影感)；紅眼發光 (10_char.png 座標)
    },
    # 紅美鈴 R / SR / SSR (TH06，2026-11-12 桌機)：萌娘百科外貌 = 紅色及腰長髮、兩鬢各一條麻花辮 + 蝴蝶結、藍灰眼、身材高；
    # 深綠中式上衣 + 裙褂 (不是旗袍，上下分開、高開叉、內穿白長褲)、綠帽 + 刻「龍」字的金色五角星；萌點 = 門番、睡神、武術家，也是紅魔館的園丁
    # 三個階級都沒有彈幕；SSR 有閃光特效 (build_cards 自動)
    ("meiling", "R"): {
        # R「華人小娘」：午後的紅魔館大門前，靠著門柱站著打瞌睡 (睡神)
        "bg": ("no humans, scenery, front gate of a red gothic western mansion, red brick wall, ornate iron gate, gate pillars, stone path, "
               "flower beds, afternoon, warm sunlight, blue sky, clouds, peaceful, bright, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, hong meiling, touhou, red hair, very long hair, side braids, twin braids, hair ribbon, blue eyes, tall, "
                 "green hat, star hat ornament, chinese clothes, green dress, side slit, white pants, puffy short sleeves"),
        "char": ("standing, leaning back, arms crossed, sleeping while standing, closed eyes, dozing off, drooling, peaceful sleepy face, "
                 "head tilted, relaxed, from side"),
        "char_negative": "weapon, sword, wings, fighting stance, qi, aura",
        "char_scale": 0.49,          # 使用者：人物小一點、更符合場景 (0.95 ➔ 0.7 ➔ 再 ×0.7)
        "offset": (0.0, 0.225),      # 腳的位置不變 (踩在石板路上；縮小時 dy 跟著算)
    },
    ("meiling", "SR"): {
        # SR「紅魔館的彩虹門衛」：照顧紅魔館的花圃，提著澆水壺、水霧中出現小彩虹，開朗的笑
        "bg": ("no humans, scenery, flower garden of a red gothic western mansion, colorful flower beds, roses, tulips, sunflowers, "
               "garden path, stone fountain, water spray, small rainbow in the mist, butterflies, sunny day, blue sky, bright, vivid, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, hong meiling, touhou, red hair, very long hair, side braids, twin braids, hair ribbon, blue eyes, tall, "
                 "green hat, star hat ornament, chinese clothes, green dress, side slit, white pants, puffy short sleeves"),
        "char": ("standing, holding watering can, watering flowers, water spray, cheerful smile, open mouth, happy, "
                 "looking to the side, hair ribbon fluttering, gentle breeze"),
        "char_negative": "weapon, sword, wings, fighting stance, flowers, plants",
        "char_scale": 0.56,          # 使用者：人物小一點、更符合場景 (0.95 ➔ 0.7 ➔ 再 ×0.8)
        "offset": (0.05, 0.19),      # 往右 1/10 畫窗寬；腳的位置不變
    },
    ("meiling", "SSR"): {
        # SSR「太極拳之終極衛士」華符「彩光蓮華掌」：大門前擺出太極 / 拳法架式，雙掌凝聚七彩的氣，認真的武術家表情
        "bg": ("no humans, scenery, courtyard in front of a red gothic western mansion gate, stone tiles, red brick, cherry blossom petals flying, "
               "wind, morning sunlight, light rays, blue sky, dramatic, dynamic, bright, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, hong meiling, touhou, red hair, very long hair, side braids, twin braids, hair ribbon, blue eyes, tall, "
                 "green hat, star hat ornament, chinese clothes, green dress, side slit, white pants, puffy short sleeves"),
        "char": ("fighting stance, martial arts, kung fu, tai chi pose, palm strike, one palm thrust forward, wide stance, "
                 "rainbow aura around hands, glowing qi, colorful energy, serious expression, determined, focused eyes, "
                 "hair flowing, dress fluttering, dynamic pose"),
        "char_negative": "weapon, sword, wings, sleeping, closed eyes",
        "char_scale": 0.9,
    },
    # 露米婭 R / SR / SSR (TH06，2026-11-12 桌機)：萌娘百科外貌 = 金色短髮 (鮑伯)、紅眼、左側紅色髮帶 (其實是封印符)；
    # 白襯衫 + 黑背心 + 黑長裙、紅色領巾 / 領帶；招牌動作 = 張開雙臂擺十字架姿勢 (「是這樣嗎～」)；沒有翅膀
    # 三個階級都沒有彈幕；SSR 有閃光特效 (build_cards 自動)
    ("rumia", "R"): {
        # 使用者選 (2026-11-12)：B1 (s1101) C1 (s3303)
        # R「宵暗的妖怪」：黃昏的森林小路，張開雙臂飄在半空，天真的笑
        "bg": ("no humans, scenery, forest path at dusk, tall trees, orange and purple sunset sky, fading light, fireflies, "
               "long shadows, quiet, slightly eerie, beautiful, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "base": ("1girl, rumia, touhou, blonde hair, short hair, bob cut, red eyes, red hair ribbon, hair ribbon, "
                 "white shirt, black vest, black skirt, long skirt, red neckerchief, red ascot"),
        "char": ("outstretched arms, spread arms, t-pose, floating, levitating, open mouth, innocent smile, happy, "
                 "looking at viewer, head tilt, full body"),
        "char_negative": "wings, weapon, cross, crucifix",
        "char_scale": 0.8,
    },
    ("rumia", "SR"): {
        # 使用者選 (2026-11-12)：B1 (s1101) C1 (s3303)
        # SR「暗夜的吞噬者」：沒有月亮的夜晚森林，身邊被一團黑暗包圍，紅眼在黑暗中閃爍、露出小虎牙的危險笑容
        "bg": ("no humans, scenery, dark forest at night, moonless night, deep blue darkness, faint starlight through branches, "
               "black mist, drifting shadows, mysterious, eerie, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, daytime, moon",
        "base": ("1girl, rumia, touhou, blonde hair, short hair, bob cut, red eyes, red hair ribbon, hair ribbon, "
                 "white shirt, black vest, black skirt, long skirt, red neckerchief, red ascot"),
        "char": ("outstretched arms, floating, surrounded by darkness, black aura, dark mist around body, glowing red eyes, "
                 "fang, smile, mischievous, hungry, looking at viewer, slightly from below, full body"),
        "char_negative": "wings, weapon, cross, crucifix, blood, gore",
        "char_scale": 0.8,
    },
    ("rumia", "SSR"): {
        # 使用者選 (2026-11-12)：B1 (s1101) C2 (s4404)，四周氣焰被切 ➔ 補邊 O2 (outpaint s8801 第 2 張) ➔ wf-up s9901
        # SSR「封印解放之宵暗」：紅月之夜，髮帶 (封印) 鬆開、黑暗向四周爆發，嚴肅的紅眼、頭髮與裙擺被黑暗氣流吹起
        "bg": ("no humans, scenery, night sky, huge red moon, crimson moonlight, dark clouds swirling, black void tendrils spreading, "
               "silhouette of forest below, dramatic, ominous, cinematic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, daytime",
        "base": ("1girl, rumia, touhou, blonde hair, short hair, bob cut, red eyes, red hair ribbon, hair ribbon, "
                 "white shirt, black vest, black skirt, long skirt, red neckerchief, red ascot"),
        "char": ("floating, arms spread wide, untied ribbon, ribbon flying away, dark aura exploding, black energy, darkness swirling around, "
                 "glowing red eyes, serious expression, cold stare, looking at viewer, hair flowing, skirt fluttering, dynamic, full body"),
        "char_negative": "wings, weapon, cross, crucifix, blood, gore, smile",
        "char_scale": 0.85,
    },
    # 小惡魔 N / R / SR (TH06，2026-11-12 桌機)：萌娘百科外貌 = 紅色長髮、紅眼、頭上一對蝙蝠小翼、背上一對蝙蝠翅膀；
    # 白長袖襯衫 + 黑背心 + 黑長裙、紅色領帶；帕秋莉的助手，住在大圖書館；人物直接帶翅膀 (同大妖精)
    # 三個階級都沒有彈幕
    ("koakuma", "N"): {
        # 使用者選 (2026-11-12)：B1 (s1101) C1 (s3303)
        # N「大圖書館的使魔」：紅魔館大圖書館，抱著一疊書搬運中
        "bg": ("no humans, scenery, huge library, tall wooden bookshelves, countless books, ladders, warm lamp light, "
               "dust particles in light rays, cozy, gothic interior, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "base": ("1girl, koakuma, touhou, red hair, long hair, red eyes, head wings, bat wings, demon wings, "
                 "white shirt, long sleeves, black vest, black skirt, long skirt, red necktie"),
        "char": ("standing, carrying books, holding stack of books, smile, cheerful, looking at viewer, full body"),
        "char_negative": "patchouli knowledge, purple hair, hat, remilia scarlet",
        "char_scale": 0.8,
    },
    ("koakuma", "R"): {
        # 使用者選 (2026-11-12)：B1 (s1101) C1 (s3303)
        # R「司書的助手小惡魔」：飄在高高的書架前，捧著打開的書，豎起食指抵著嘴唇「噓～圖書館要安靜」
        "bg": ("no humans, scenery, inside a grand library, very tall bookshelves reaching the ceiling, spiral staircase, "
               "floating candles, soft warm light, gothic arches, quiet, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "base": ("1girl, koakuma, touhou, red hair, long hair, red eyes, head wings, bat wings, demon wings, "
                 "white shirt, long sleeves, black vest, black skirt, long skirt, red necktie"),
        "char": ("flying, floating, holding open book, finger to lips, shushing, wink, playful smile, looking at viewer, "
                 "wings spread, full body"),
        "char_negative": "patchouli knowledge, purple hair, hat, remilia scarlet",
        "char_scale": 0.8,
    },
    ("koakuma", "SR"): {
        # 使用者選 (2026-11-12)：B1 (s1101) C3 (s5505)
        # SR「黑魔法秘典守護者」：深夜的禁書區，抱著發光的黑魔法書，身邊浮著紫色魔法陣，小惡魔式的壞笑
        "bg": ("no humans, scenery, forbidden section of a dark library at night, old bookshelves, chained books, candlelight, "
               "purple magical glow, floating runes, mysterious, gothic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, daytime",
        "base": ("1girl, koakuma, touhou, red hair, long hair, red eyes, head wings, bat wings, demon wings, "
                 "white shirt, long sleeves, black vest, black skirt, long skirt, red necktie"),
        "char": ("holding glowing book, grimoire, hugging book, purple magic aura, magic circle, glowing runes, "
                 "smirk, mischievous, devilish smile, looking at viewer, wings spread, hair flowing, full body"),
        "char_negative": "patchouli knowledge, purple hair, hat, remilia scarlet",
        "char_scale": 0.8,
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


INLINE_WINGS = "fairy wings, transparent wings, iridescent insect wings, wings spread"


def char_prompts(char_id: str, spec: dict) -> tuple[str, str]:
    """人物的正 / 負面提示；inline_wings = 翅膀直接跟人物一起畫 (不另外做翅膀層，負面提示拿掉翅膀相關的字)"""
    char, neg = spec["char"], spec.get("char_negative")
    if spec.get("inline_wings"):   # 翅膀提示預設是妖精翅膀，inline_wings_tags 可以換 (例如芙蘭的水晶翅膀)
        wings = spec.get("inline_wings_tags", INLINE_WINGS)
        char = ", ".join([char, wings])
        neg = ", ".join(t for t in (neg or "").split(", ") if "wing" not in t and "crystal" not in t) or None
    positive = ", ".join([spec.get("base") or BASE[char_id], char, CHAR_COMPOSITION, QUALITY])
    negative = ", ".join(filter(None, [NEGATIVE, spec.get("extra_negative", EXTRA_NEGATIVE.get(char_id)), CHAR_NEGATIVE, neg]))
    return positive, negative


def workflow(char_id: str, rarity: str, layer: str, seed: int) -> dict:
    spec = LAYERS[(char_id, rarity)]
    if layer == "bg":
        positive = ", ".join([spec["bg"], QUALITY])
        negative = spec["bg_negative"]
        denoise, hd = 0.4, (1748 * HD, 2432 * HD)
    else:
        positive, negative = char_prompts(char_id, spec)
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
    positive, negative = char_prompts(char_id, spec)
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
    positive, negative = char_prompts(char_id, spec)
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


DANMAKU_RARITIES = {"UR", "LR"}   # 只有 UR / LR 有彈幕 (使用者 2026-11-11)


def auto_dim(density: float) -> float:
    """彈幕越多背景越暗 (使用者 2026-11-11：大量彈幕時背景亮度要壓低，不然畫面很亂；第二次「背景再暗點」)：density 1.0 ➔ 0.45、0.75 ➔ 0.5"""
    return round(0.65 - 0.2 * density, 3)


DANMAKU_ORIGINS = 2   # 同心環的發射中心數 (+ 螺旋彈中心 = 3 個原點；使用者 2026-11-11：原點剩 2～3 個就好，原本 4 + 1)


def make_bg(char_id, rarity):
    d = stage_dir(char_id, rarity)
    spec = LAYERS[(char_id, rarity)]
    bg = Image.open(os.path.join(d, "03_bg_hd.png")).convert("RGB")
    if rarity not in DANMAKU_RARITIES or not spec.get("style"):
        # N～SSR：沒有彈幕，背景原樣 (可用 dim 微調)
        if spec.get("dim"):
            bg = ImageEnhance.Brightness(bg).enhance(spec["dim"])
        bg.save(os.path.join(d, "04_bg_fx_hd.png"))
        print("✅ 04_bg_fx_hd (沒有彈幕)")
        bg.resize((bg.width // HD, bg.height // HD), Image.LANCZOS).save(os.path.join(d, "05_bg.png"))
        print("✅ 05_bg")
        return
    bg = ImageEnhance.Brightness(bg).enhance(spec.get("dim", auto_dim(spec.get("density", 1.0))))
    # 彈幕畫滿整張卡 (沒有框的完整原圖也有彈幕)，大小以畫窗為基準
    l, t, r, b = window_box()
    glow, core = draw_danmaku(bg.size, seed=1, style=spec.get("style", "rainbow"), scale=(r - l) * HD / BASE_W,
                              density=spec.get("density", 1.0), origins=spec.get("origins", DANMAKU_ORIGINS))
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
    if spec.get("wing_mask"):   # 去背模型會把半透明的水晶翅膀當背景切掉：翅膀遮罩範圍內一律保留
        wm = Image.open(os.path.join(d, spec["wing_mask"])).convert("L").resize(ch.size, Image.BILINEAR)
        wm = wm.filter(ImageFilter.GaussianBlur(2))
        alpha = ImageChops.lighter(ch.split()[3], wm)
        orig = Image.open(src).convert("RGB")                       # 去背結果被切掉的地方是黑色，顏色要從原圖拿
        ch = Image.composite(orig, ch.convert("RGB"), wm).convert("RGBA")
        ch.putalpha(alpha)
    box = ch.split()[3].point(lambda v: 255 if v > 8 else 0).getbbox()            # 去掉四周空白

    def place(img, resample):
        """跟人物一樣：裁空白 → 傾斜 → 縮到放進畫窗 (× char_scale) → 放到畫窗大小的畫布 (offset，超出切掉)"""
        img = img.crop(box)
        if spec.get("tilt"):
            img = img.rotate(spec["tilt"], resample=Image.BICUBIC, expand=True)
            img = img.crop(rot_box)
        img = img.resize(size, resample)
        canvas = Image.new(img.mode, (r - l, b - t), 0)
        canvas.paste(img, (round((canvas.width - img.width) / 2 + dx * canvas.width),
                           round((canvas.height - img.height) / 2 + dy * canvas.height)))   # 超出部分 PIL 會自動裁掉
        return canvas

    rot = ch.crop(box).rotate(spec["tilt"], expand=True) if spec.get("tilt") else ch.crop(box)
    rot_box = rot.getbbox()
    rot = rot.crop(rot_box)
    l, t, r, b = window_box()
    scale = min((r - l) / rot.width, (b - t) / rot.height) * spec.get("char_scale", 1.0)   # 完整放進畫窗
    size = (round(rot.width * scale), round(rot.height * scale))
    dx, dy = spec.get("offset", (0, 0))
    place(ch, Image.LANCZOS).save(os.path.join(d, "10_char.png"))
    print("✅ 10_char")
    # 手描的翅膀遮罩 (06 基本圖座標) 跟著放大、裁切、縮放，打光用 (relight 的 emissive "mask")
    if spec.get("wing_mask"):
        m = Image.open(os.path.join(d, spec["wing_mask"])).convert("L").resize(ch.size, Image.BILINEAR)
        place(m, Image.BILINEAR).save(os.path.join(d, "10w_char_wingmask.png"))
        print("✅ 10w_char_wingmask")
    # 翅膀 / 尾流層的錨點 (06 基本圖座標) 也跟著人物換算到 10_char.png 上
    anchors = {}
    base_w, base_h = Image.open(os.path.join(d, "06_char_base.png")).size
    for layer in ("wings", "trail", "orbs"):
        if not spec.get(layer):
            continue
        ax, ay = spec[layer]["anchor"]
        dot = Image.new("L", ch.size, 0)
        sx, sy = ch.width / base_w, ch.height / base_h
        ImageDraw.Draw(dot).ellipse((ax * sx - 12 * sx, ay * sy - 12 * sy, ax * sx + 12 * sx, ay * sy + 12 * sy), fill=255)
        ys, xs = np.nonzero(np.asarray(place(dot, Image.BILINEAR)) > 127)
        anchors[layer] = [float(xs.mean()), float(ys.mean())]
    if anchors:
        anchors["anchor"] = anchors.get("wings")                       # 舊格式 (翅膀) 相容
        with open(os.path.join(d, "10_anchor.json"), "w", encoding="utf-8") as f:
            json.dump(anchors, f)
        print("✅ 10_anchor.json")
    if spec.get("light") is not None:
        make_light(char_id, rarity)
    if spec.get("wings") and all(os.path.exists(os.path.join(d, f"W3_crystal_{k}_cut.png")) for k in spec["wings"]["crystals"]):
        make_wings(char_id, rarity)
    if spec.get("trail"):
        make_trail(char_id, rarity)
    if spec.get("orbs") and os.path.exists(os.path.join(d, "O1_orb.png")):
        make_orbs(char_id, rarity)


def make_orbs(char_id, rarity):
    """環繞的物件圈 (orbs.py，靈夢的陰陽玉)：O1 單顆 → O3 去背 → O4 後 / 前兩層 → 10f = 後層 + 人物 + 前層"""
    d = stage_dir(char_id, rarity)
    os_ = dict(LAYERS[(char_id, rarity)]["orbs"])
    cut = os.path.join(d, "O3_orb_cut.png")
    if not os.path.exists(cut):
        subprocess.run([COMFY_PY, "-I", os.path.join(HERE, "cutout.py"), os.path.join(d, "O1_orb.png"), d], check=True)
        clean_crystal(Image.open(os.path.join(d, "O1_orb_cut.png")).convert("RGBA")).save(cut)
        os.remove(os.path.join(d, "O1_orb_cut.png"))
        print("✅ O3_orb_cut")
    l, t, r, b = window_box()
    W, H = r - l, b - t
    with open(os.path.join(d, "10_anchor.json"), encoding="utf-8") as f:
        anchor = json.load(f)["orbs"]
    for k in ("rx", "size"):
        os_[k] = os_[k] * W                                             # 比例 ➔ px
    os_["ry"] = os_["ry"] * H
    orb = Image.open(cut).convert("RGBA")
    if os_.get("crop_square"):   # 圓球下面連著倒影：只留上方正方形 (球本身)
        orb = orb.crop((0, 0, orb.width, min(orb.height, orb.width)))
    back, front = ring((W, H), anchor, orb, os_)
    back.save(os.path.join(d, "O4_orbs_back.png"))
    front.save(os.path.join(d, "O4_orbs_front.png"))
    print("✅ O4_orbs_back / front")
    for name in ("10e_char_trail.png", "10d_char_wings.png", "10b_char_lit.png", "10_char.png"):
        body = os.path.join(d, name)
        if os.path.exists(body):
            break
    back.alpha_composite(Image.open(body).convert("RGBA"))
    back.alpha_composite(front)
    back.save(os.path.join(d, "10f_char_orbs.png"))
    print("✅ 10f_char_orbs")


def make_trail(char_id, rarity):
    """掃帚尾流層 (trail.py)：T1 尾流 → 10e 疊在人物 (含翅膀) 下面"""
    d = stage_dir(char_id, rarity)
    ts = dict(LAYERS[(char_id, rarity)]["trail"])
    l, t, r, b = window_box()
    W, H = r - l, b - t
    with open(os.path.join(d, "10_anchor.json"), encoding="utf-8") as f:
        anchor = json.load(f)["trail"]
    ts["length"] = ts.get("length", 0.5) * H                          # 比例 ➔ px
    ts["width"] = ts.get("width", 0.03) * W
    ts["wave"] = ts.get("wave", 0.02) * W
    layer = draw_trail((W, H), anchor, ts)
    layer.save(os.path.join(d, "T1_trail.png"))
    print("✅ T1_trail")
    for name in ("10d_char_wings.png", "10b_char_lit.png", "10_char.png"):
        body = os.path.join(d, name)
        if os.path.exists(body):
            break
    layer.alpha_composite(Image.open(body).convert("RGBA"))           # 人物蓋在尾流上
    layer.save(os.path.join(d, "10e_char_trail.png"))
    print("✅ 10e_char_trail")


def make_wings(char_id, rarity):
    """翅膀層：W2 (放大) → W3 去背 → W4 排列 → W5 打光 → 10d 疊在人物下面"""
    d = stage_dir(char_id, rarity)
    ws = LAYERS[(char_id, rarity)]["wings"]
    crystals = {}
    for key in ws["crystals"]:
        cut = os.path.join(d, f"W3_crystal_{key}_cut.png")
        if not os.path.exists(cut):
            hd = os.path.join(d, f"W2_crystal_{key}_hd.png")
            subprocess.run([COMFY_PY, "-I", os.path.join(HERE, "cutout.py"), hd, d], check=True)
            clean_crystal(Image.open(os.path.join(d, f"W2_crystal_{key}_hd_cut.png")).convert("RGBA")).save(cut)
            os.remove(os.path.join(d, f"W2_crystal_{key}_hd_cut.png"))
            print(f"✅ W3_crystal_{key}_cut")
        crystals[key] = Image.open(cut).convert("RGBA")
    l, t, r, b = window_box()
    H = b - t
    with open(os.path.join(d, "10_anchor.json"), encoding="utf-8") as f:
        anchor = json.load(f)["anchor"]
    items = [dict(it, length=it["length"] * H, r0=it.get("r0", 0) * H) for it in ws["items"]]
    layer = arrange((r - l, b - t), anchor, items, crystals)
    layer.save(os.path.join(d, "W4_wings.png"))
    print("✅ W4_wings")
    win = Image.open(os.path.join(d, "05_bg.png")).convert("RGB").crop((l, t, r, b))
    opts = dict(ws.get("light", {}))
    alpha = np.asarray(layer.split()[3], dtype=np.float32) / 255
    opts["emissive"] = [dict(em, mask=alpha) if em.get("mask") == "alpha" else em for em in opts.get("emissive", [])]
    lit = relight(layer, win, opts)
    lit.save(os.path.join(d, "W5_wings_lit.png"))
    print("✅ W5_wings_lit")
    body = os.path.join(d, "10b_char_lit.png")
    body = body if os.path.exists(body) else os.path.join(d, "10_char.png")
    lit.alpha_composite(Image.open(body).convert("RGBA"))              # 人物蓋在翅膀上
    lit.save(os.path.join(d, "10d_char_wings.png"))
    print("✅ 10d_char_wings")


def make_light(char_id, rarity):
    d = stage_dir(char_id, rarity)
    opts = LAYERS[(char_id, rarity)].get("light")
    if opts is None:
        raise SystemExit("LAYERS 沒有 light 設定")
    l, t, r, b = window_box()
    win = Image.open(os.path.join(d, "05_bg.png")).convert("RGB").crop((l, t, r, b))
    opts = dict(opts)
    opts["emissive"] = [dict(em, mask=np.asarray(Image.open(os.path.join(d, em["mask"])).convert("L"), dtype=np.float32) / 255)
                        if isinstance(em.get("mask"), str) else em for em in opts.get("emissive", [])]   # 遮罩檔名 ➔ 陣列
    relight(Image.open(os.path.join(d, "10_char.png")), win, opts).save(os.path.join(d, "10b_char_lit.png"))
    print("✅ 10b_char_lit")


def char_layer(d):
    """疊層用的人物：PhotoCraft 手修版 (10c) > 加上環繞物件 (10f) > 加上尾流 (10e) > 加上翅膀層 (10d) > 打光版 (10b) > 10"""
    for name in ("10c_char_photocraft.png", "10f_char_orbs.png", "10e_char_trail.png", "10d_char_wings.png", "10b_char_lit.png", "10_char.png"):
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
    elif cmd == "wings":
        make_wings(char_id, rarity)
    elif cmd == "trail":
        make_trail(char_id, rarity)
    elif cmd == "orbs":
        make_orbs(char_id, rarity)
    elif cmd == "compose":
        compose(char_id, rarity)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()

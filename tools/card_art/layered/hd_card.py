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
    # 博麗靈夢 SR / SSR (主角，舊版單張生成卡改走高清分層，2026-11-12 草稿)
    # 萌娘百科外貌：黑髮 (「黑長直」「齊劉海」「長鬢角」，部分作品是短髮)、瞳色不固定 (黑瞳或紅瞳)；
    # 頭上大蝴蝶結、兩鬢用髮帶綁起 (束鬢、半馬尾)；露肩露腋的無袖巫女服 + 分離袖子、胸前領巾、紅裙 (緋袴)、纏胸布、
    # 白色短襪 + 瑪麗珍鞋；道具：御幣、符札、封魔針、陰陽玉 (博麗神社最大的秘寶)
    # make_workflow.BASE 沒寫髮色 ➔ base 補上 black hair、brown eyes、sidelocks、hair tubes、white socks、mary janes
    # 跟 UR (夜空 + 博麗大結界、正面仰拍、陰陽玉獨立圖層) 拉開：SR 白天神社日常、SSR 黃昏天空中施放符札的動態
    ("reimu", "SR"): {
        # SR「博麗神社的巫女」：春天的博麗神社 (鳥居、石階、櫻花)；微微浮在參道上，扛著御幣，輕鬆隨性地笑
        "bg": ("no humans, scenery, hakurei shrine grounds, huge cherry blossom tree in the foreground center, thick tree trunk, "
               "grass and fallen petals at the base of the tree, shrine building and red torii behind the tree, stone lanterns, "
               "falling petals, spring, blue sky, daylight, soft lighting, peaceful, bright, highly detailed, intricate details"),   # 使用者：倚在神社櫻花樹下 ➔ 樹畫在背景，人物坐在樹根
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, hakurei reimu, touhou, black hair, long hair, blunt bangs, sidelocks, hair tubes, brown eyes, "
                 "red bow, large bow, frilled bow, red and white miko outfit, sleeveless, bare shoulders, detached sleeves, wide sleeves, "
                 "yellow ascot, red skirt, white socks, mary janes"),
        "char": ("sitting on the ground under a cherry blossom tree, leaning back against the tree trunk, tree trunk behind her, "
                 "cherry blossom branches above, falling petals, knees up, holding gohei over shoulder, relaxed smile, half-closed eyes, "
                 "carefree, looking at viewer, full body"),   # 使用者 (2026-11-12)：喜歡 C4 的坐姿，改成倚在神社的櫻花樹下 (樹畫在人物層，去背一起留下)
        "char_negative": "kirisame marisa, witch hat, blonde hair, wings, multiple girls, magic circle, glowing effects, "
                         "nsfw, nipples, cleavage",
        "char_scale": 0.62,
        "offset": (0.0, 0.17),   # 人物縮小、往下放到樹根
        
    },
    ("reimu", "SSR"): {
        # SSR「樂園的奇妙巫女」：黃昏的幻想鄉天空，博麗神社在遠遠的下方、櫻花被風捲起；
        # 斜身飛行、指間夾著符札甩出，兩顆陰陽玉在身旁，堅定的笑 (UR 是正面俯視的強者感，這張是側身的速度感)
        "bg": ("no humans, scenery, sky above gensokyo, golden hour, sunset, orange and pink clouds, sunlight, light rays, "
               "hakurei shrine and torii far below on a mountain, cherry blossom petals swirling in the wind, "
               "wide view, dramatic, warm colors, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night",
        "base": ("1girl, hakurei reimu, touhou, black hair, long hair, blunt bangs, sidelocks, hair tubes, brown eyes, "
                 "red bow, large bow, frilled bow, red and white miko outfit, sleeveless, bare shoulders, detached sleeves, wide sleeves, "
                 "yellow ascot, red skirt, white socks, mary janes"),
        "char": ("flying, dynamic pose, leaning forward, holding gohei, throwing ofuda, ofuda between fingers, "
                 "two yin yang orbs beside her, determined smile, looking at viewer, wind, sleeves fluttering, "
                 "hair ribbon fluttering, skirt fluttering, both legs visible, full body"),
        "char_negative": "kirisame marisa, witch hat, blonde hair, wings, multiple girls, magic circle, barrier, rainbow, "
                         "nsfw, nipples, cleavage, panties",
        "char_scale": 0.9,
    },
    # ── 霧雨魔理沙 SR / SSR (2026-11-12 從舊的單張生成改走高清分層) ──
    # 萌娘百科外貌：金色長髮 (及肩到及腰、微捲)，一側編成麻花辮垂在胸前，辮子綁蝴蝶結；瞳色金 (少數作品紅瞳)；
    # 寬大的黑色三角巫師帽 (尖頂寬簷)，帽上有大蝴蝶結 (多為白色)；黑色魔女裝 + 白圍裙 (紅魔鄉是全身圍裙，之後是半身圍裙)、泡泡袖；
    # 白短襪 + 樂福鞋 / 瑪麗珍鞋；隨身帶掃帚與迷你八卦爐 (八角形、刻八卦圖)。沒有翅膀、沒有尾巴
    # BASE 沒有跟萌娘百科衝突，只補上金眼、帽子白蝴蝶結、泡泡袖、半身圍裙、鞋襪 (不寫眼睛顏色的話有機會畫成紅眼)
    # UR 是夜空 + 騎掃帚 + Master Spark ➔ SR / SSR 都放在白天，SR 站著不騎、SSR 完全不畫掃帚，跟 UR 拉開
    ("marisa", "SR"): {
        # SR「普通的魔法使」：原本的構想是白天騎掃帚穿過魔法森林 ➔ 改成白天魔法森林裡自己家 (霧雨魔法店) 門口，
        # 一手直握掃帚 (刷毛著地)、一手捧著剛採的發光蘑菇，咧嘴笑加眨眼，日常又有朝氣
        "bg": ("no humans, scenery, forest of magic, giant mushrooms, glowing mushrooms, small cluttered western cottage, wooden sign, "
               "piles of books and jars by the door, sunlight through trees, light rays, dappled light, moss, ferns, daytime, bright, "
               "lush green, whimsical, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, broom, witch hat, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, kirisame marisa, touhou, blonde hair, long hair, wavy hair, single side braid, hair bow, yellow eyes, "
                 "witch hat, black headwear, white bow on hat, black dress, white shirt, puffy short sleeves, white apron, waist apron, "
                 "white socks, black shoes"),
        "char": ("standing, one hand holding a broom upright beside her, broom bristles on the ground, single broom, "
                 "other hand holding up a glowing mushroom, grin, one eye closed, wink, energetic, cheerful, looking at viewer, "
                 "hair fluttering, full body"),
        # 共用的 EXTRA_NEGATIVE 會擋「standing, holding broom」，這張剛好要站著拿掃帚 ➔ 換掉，改成擋騎掃帚
        "extra_negative": "riding broom, sitting on broom, flying, broom on shoulder",
        "char_negative": ("red eyes, wings, multiple brooms, two brooms, bristles on both ends, extra hat, floating hat, "
                          "magic effects, sparkles, stars, laser, mushrooms on ground, alice margatroid, hakurei reimu"),
        "char_scale": 0.9,
    },
    ("marisa", "SSR"): {
        # SSR「東洋的西洋魔術師」：原本的構想是白天在魔法森林上空高速飛、星星彈幕與魔法陣 ➔ 保留白天藍天 + 森林上空 (跟 UR 的夜空分開)，
        # 不騎掃帚 (UR 已經騎了)：跳到半空、一手按住帽子、一手把迷你八卦爐往前伸，爐口噴出星星，自信大笑
        "bg": ("no humans, scenery, above the forest of magic, sea of treetops below, giant mushrooms poking out of the canopy, "
               "bright blue sky, big white clouds, sunlight, lens flare, wind, flying leaves, daytime, vivid colors, "
               "highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, broom, witch hat, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, kirisame marisa, touhou, blonde hair, long hair, wavy hair, single side braid, hair bow, yellow eyes, "
                 "witch hat, black headwear, white bow on hat, black dress, white shirt, puffy short sleeves, white apron, waist apron, "
                 "white socks, black shoes"),
        "char": ("midair, jumping, dynamic pose, one hand holding hat brim, other arm stretched forward holding glowing mini-hakkero, "
                 "octagonal hakkero, star (symbol), stars bursting from the hakkero, confident grin, open mouth, looking at viewer, "
                 "hair flowing in wind, hat ribbon flowing, skirt fluttering, slightly from below, full body"),
        # 這張不要掃帚 ➔ 換掉共用的 EXTRA_NEGATIVE (它只擋拿掃帚，沒擋騎掃帚)
        "extra_negative": "broom, holding broom, riding broom, sitting on broom, broom on shoulder",
        "char_negative": ("red eyes, wings, extra hat, floating hat, laser, beam, huge magic circle, background scenery, "
                          "alice margatroid, hakurei reimu, panties, upskirt"),
        "char_scale": 0.9,
    },
    # 琪露諾 SR / SSR (TH06，2026-11-12 草稿，舊單張卡改走高清分層)：外觀照 make_workflow.BASE 與 UR
    # (萌娘百科這次打不開，沒核對)：藍色短髮、藍眼、藍色大蝴蝶結、白襯衫 + 泡泡短袖、紅色領結、藍色背心裙、
    # 背後六片冰晶翅膀、小孩身材；萌點：笨蛋⑨、自稱最強、愛凍青蛙、霧之湖
    # 翅膀：UR 用翅膀層；SR / SSR 先讓人物直接帶冰晶翅膀 (inline_wings，寫法照大妖精)，base 拿掉 BASE 的翅膀標籤，免得跟 inline_wings_tags 重複
    ("cirno", "SR"): {
        # SR「冰之妖精」：清晨霧之湖邊 (蘆葦、睡蓮葉)；蹲著得意舉起剛凍住的青蛙 (青蛙包在冰塊裡)，調皮又天真
        "bg": ("no humans, scenery, misty lake, lakeside, morning fog, reeds, lily pads, calm water, ripples, thin ice on water edge, "
               "frost on grass, soft sunlight, daytime, bright, pale blue sky, distant forest, pastel colors, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, wings, frog, animal, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, cirno, touhou, blue hair, short hair, blue eyes, blue hair bow, large bow, white shirt, puffy short sleeves, "
                 "red neck ribbon, blue dress, pinafore dress, child, petite"),
        "char": ("squatting, both feet on ground, holding up a frozen frog, frog in ice block, ice cube, arm raised, proud grin, "
                 "mischievous, innocent, open mouth, looking at viewer, frost particles around hand, hair fluttering, from side"),
        "char_negative": "(fairy wings:1.3), insect wings, transparent wings, butterfly wings, angel wings, weapon, staff, wand, "
                         "water, splash, reeds, lily pad, multiple frogs, danmaku",
        "inline_wings": True,
        "inline_wings_tags": "ice wings, six ice crystal wings, ice crystal wings, clear blue ice, wings spread",
        "char_scale": 0.9,
    },
    ("cirno", "SSR"): {
        # SSR「湖上的冰精女王」：結冰的湖面中間一座冰山，晴空、冰柱和雪花飛舞 (冰山在背景裡，人物站在下方中央的冰山頂上)；
        # 一手插腰一手比 V、張嘴大笑，自信又得意；冰塊冰柱只當背景與手邊的冰晶，不做成彈幕 (SSR 沒有彈幕)
        "bg": ("no humans, scenery, frozen lake, ice field, large iceberg in the foreground center, jagged ice peak, icicles, "
               "ice shards in the air, flying ice chunks, snowflakes, sparkles, clear blue sky, white clouds, wind, "
               "daytime, bright, crisp, cold, dynamic angle, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, wings, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, cirno, touhou, blue hair, short hair, blue eyes, blue hair bow, large bow, white shirt, puffy short sleeves, "
                 "red neck ribbon, blue dress, pinafore dress, child, petite"),
        "char": ("standing, feet apart, both legs visible, hand on hip, v sign, laughing, open mouth, confident, smug, v-shaped eyebrows, "
                 "small ice shards swirling around her, frost particles, hair fluttering, dress fluttering, wind, slightly from below"),
        "char_negative": "(fairy wings:1.3), insect wings, transparent wings, butterfly wings, angel wings, weapon, staff, wand, "
                         "iceberg, ground, rock, danmaku, bullets",
        "inline_wings": True,
        "inline_wings_tags": "ice wings, six ice crystal wings, ice crystal wings, clear blue ice, wings spread",
        "char_scale": 0.9,
    },
    ("mima", "SR"): {
        # SR「久遠的博麗神社惡靈」(沿用舊 SCENES)：荒廢的舊博麗神社 (青苔、雜草、舊鳥居、午後陽光、螢火蟲)；人物在空中盤腿悠哉飄著、調皮地笑
        "bg": ("no humans, scenery, old abandoned shinto shrine, overgrown, moss, tall grass, weathered old torii, small stone shrine, stone lanterns, "
               "afternoon, warm sunlight, light rays through trees, fireflies, peaceful, nostalgic, soft lighting, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, ghost, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, mima (touhou), touhou, green hair, very long hair, green eyes, wizard hat, white headwear, "
                 "blue dress, blue skirt, blue cape, red ribbon, neck ribbon, ghost tail, no legs, holding staff, crescent staff"),
        "char": ("floating in the air, ghost tail, no legs, relaxed pose, sitting cross-legged in the air, chin resting on hand, "
                 "mischievous smile, looking at viewer, cape fluttering, hair flowing, full body"),
        "char_negative": "(legs:1.3), (feet:1.3), shoes, socks, thighhighs, standing, kneeling, wings, marisa, kirisame marisa, blonde hair",
        "char_scale": 0.9,
    },
    ("mima", "SSR"): {
        # SSR「祟高而冷酷的惡靈」(沿用舊 SCENES)：舊神社上空，藍天白雲；舉起月牙杖施法、冷笑、半閉眼，披風被風吹起，四周飄著靈體光絲
        # N~SSR 沒有彈幕：舊 SCENES 寫的 star danmaku / magic circle 拿掉，只留杖頭的藍色魔法光 (SSR 的閃光 build_cards 會自動加)
        "bg": ("no humans, scenery, sky above an old shinto shrine, shrine roof and torii far below, blue sky, dramatic clouds, wind, "
               "spectral wisps, faint blue mist, light rays, dynamic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, ghost, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night",
        "base": ("1girl, mima (touhou), touhou, green hair, very long hair, green eyes, wizard hat, white headwear, "
                 "blue dress, blue skirt, blue cape, red ribbon, neck ribbon, ghost tail, no legs, holding staff, crescent staff"),
        "char": ("floating, ghost tail, no legs, raising staff, crescent staff, casting spell, glowing staff tip, blue magic, "
                 "cold smile, half-closed eyes, looking down at viewer, cape fluttering, hair flowing, wind, dynamic pose, dynamic angle, full body"),
        "char_negative": "(legs:1.3), (feet:1.3), shoes, socks, thighhighs, standing, wings, marisa, kirisame marisa, blonde hair, danmaku, magic circle",
        "char_scale": 0.9,
    },
    ("mima", "UR"): {
        # UR「憑依博麗之陰影」(沿用舊 SCENES)：雲層之上的夜空、背後巨大的月牙 / 滿月 (月光下會變強)；
        # 杖高舉過頭、眼睛發光、自信的邪笑，全身藍色靈體光焰，披風與長髮大幅翻飛。背景壓暗紫藍色，彈幕才跳得出來
        "bg": ("no humans, scenery, night sky above the clouds, sea of clouds, huge crescent moon, bright moonlight, starry sky, "
               "faint blue spectral flames, ghostly mist, deep navy blue and purple, dark, dramatic, cinematic, majestic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, ghost, text, watermark, lowres, worst quality, low quality, blurry, frame, border, daytime, blue sky, sun",
        "base": ("1girl, mima (touhou), touhou, green hair, very long hair, green eyes, wizard hat, white headwear, "
                 "blue dress, blue skirt, blue cape, red ribbon, neck ribbon, ghost tail, no legs, holding staff, crescent staff"),
        "char": ("floating high, ghost tail, no legs, staff raised overhead, crescent staff, glowing staff, "
                 "glowing eyes, green eyes, confident, evil smile, menacing, looking at viewer, "
                 "ghostly blue aura, spectral flames, cape billowing, hair flowing, backlighting, rim light, dynamic angle, from below, full body"),
        "char_negative": "(legs:1.3), (feet:1.3), shoes, socks, thighhighs, standing, marisa, kirisame marisa, blonde hair, magic circle, danmaku, happy",
        # 封魔錄第三形態的六隻紫色翅膀 (萌娘百科萌點有翅膀)：要的話參照 remilia 的寫法打開，但會增加畫壞的機率
        # "inline_wings": True,
        # "inline_wings_tags": "six wings, multiple wings, purple wings, wings spread",
        "style": "twilight",   # 新風格提案 (danmaku.py 要另外做)；還沒做之前先用 "stars"
        "density": 0.72,
        "glow": 0.55,
        "char_scale": 0.8,
        "light": {"dark": 0.35, "glow_red": 0,   # glow_red 0：紅色領結會被當成翅膀紋路發光
                  "eyes": [(515, 528), (478, 566)], "eye_color": (90, 255, 150), "eye": 1.3, "eye_size": 3,   # 綠瞳發光 (B2C2 的 10_char 量的)
                  # 使用者 (2026-11-12)：杖頭月牙、旁邊的紫色魔焰、眼睛都要發亮
                  "emissive": [
                      {"hue": (0.70, 0.86), "sat": (0.35, 1.0), "val": (0.25,), "color": (190, 120, 255), "strength": 0.8, "body": 0.45, "keep_color": True},   # 紫色魔焰
                      {"hue": (0.86, 1.0), "sat": (0.35, 1.0), "val": (0.45,), "color": (255, 130, 180), "strength": 1.0, "body": 0.6, "keep_color": True,    # 杖頭粉紅月牙
                       "exclude": [[(450, 530), (610, 530), (610, 670), (450, 670)], [(930, 610), (1210, 610), (1210, 810), (930, 810)]]},   # 扣掉領結、右邊紅緞帶
                  ]},
    },
    ("genji", "N"): {
        # N「飛天神龜」(沿用舊 SCENES)：老龜悠哉地飛過湖面 (蘆葦、倒影、藍天白雲)；眼睛半閉、表情平靜
        # 非人角色：人物層只畫烏龜 (no humans, animal focus)，湖面 / 水花全部放背景，不然去背會一起被切掉或留下奇怪的水塊
        # hd_card 只吃 EXTRA_NEGATIVE["genji"]，舊的 ("genji", "N") 負面提示 (不要人) 要寫進 char_negative
        "bg": ("no humans, scenery, calm lake, lake surface, reeds, water reflection, lily pads, distant green hills, "
               "blue sky, white clouds, daylight, soft lighting, peaceful, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, animal, turtle, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("no humans, animal focus, genjii (touhou), touhou, minogame, tortoise, old tortoise, land tortoise, green shell, olive brown skin, "
                 "four legs, clawed feet, long white beard, bushy white eyebrows, half-closed eyes, sleepy eyes, "
                 "long fluffy white tail, flowing white hair-like tail, wise, flying tortoise"),
        "char": ("flying, floating in the air, legs relaxed, calm expression, eyes half closed, peaceful, beard flowing in the wind, "
                 "side view, from side, full body"),
        "char_negative": ("1girl, human, humanization, anthropomorphic, girl, rider, person riding, "
                          "water, lake, splash, reeds, wings, feathers, sea turtle, flippers"),
        "char_scale": 0.7,   # 烏龜是橫長的，畫窗直長；日常卡人物偏小，先抓 0.7，等去背圖出來再依實際寬度調
    },
    ("genji", "R"): {
        # R「靈夢的御用坐騎」(沿用舊 SCENES)：載著 (舊作 PC-98 造型的) 靈夢在空中飛行，下方遠處是博麗神社、櫻花飛舞
        # 雙人卡 (DUO)：靈夢 + 烏龜都放人物層，神社 / 櫻花 / 天空放背景；手上的符札會留著，飄的花瓣放背景
        # 注意：共用的 CHAR_COMPOSITION 有 "solo"，可能只畫出其中一個 (或烏龜被縮成小配件)，挑圖時要檢查兩個都在
        # 2026-11-12 使用者：第一輪背景 (B2 仰拍鳥居) 跟「在天上飛」的人物不搭 ➔ 改成高空俯瞰，神社只在遠遠的下方
        "bg": ("no humans, scenery, aerial view, high altitude, open sky, white clouds around, wind, "
               "looking down at gensokyo far below, tiny hakurei shrine and red torii far below, forest, mountains, lake, "
               "pink cherry blossom trees far below, few falling petals, blue sky, daylight, cheerful, bright, highly detailed"),
        "bg_negative": ("1girl, person, human, character, face, animal, turtle, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark, "
                        "from below, low angle, close-up building, large building, shrine in foreground, torii in foreground"),
        "base": ("1girl, hakurei reimu, touhou, touhou (pc-98), brown hair, black hair, brown eyes, hair tubes, red bow, "
                 "red and white miko outfit, detached sleeves, red skirt, "
                 "riding on a giant old tortoise, genjii (touhou), minogame, tortoise, green shell, olive brown skin, "
                 "long white beard, bushy white eyebrows, long fluffy white tail"),
        "char": ("sitting on the tortoise's shell, riding, flying through the sky, holding ofuda, cheerful smile, looking at viewer, "
                 "hair flowing, sleeves fluttering, wind, tortoise with half-closed eyes, calm, from side, full body"),
        "char_negative": ("humanization, anthropomorphic, turtle girl, multiple girls, white hair, grey hair, silver hair, "
                          "animal ears, tail on girl, beard on girl, broom, wings, sea turtle, flippers, cherry blossoms, petals"),
        "char_scale": 0.8,   # 靈夢 + 烏龜比單隻大，先 0.8；腳要留在龜殼上，太大會被畫窗切掉
    },
    ("genji", "SR"): {
        # SR「萬年修行的靈龜」(沿用舊 SCENES)：仙山雲海上的神龜，龜殼上古老的符文發著金光、靈氣環繞
        # 去背會把身邊的金色氣焰一起去掉 ➔ 光芒、光柱、金色光點都放背景，人物層只留龜殼上的發光符文 (是身體的一部分，去背會保留)
        # N～SSR 沒有彈幕 / 魔法陣，舊 SCENES 也沒有，維持
        # 2026-11-12 使用者：第一輪背景 (懸崖、瀑布的空中視角) 跟站著的烏龜不搭 ➔ 平視、前景有一塊可以站的山頂岩地
        "bg": ("no humans, scenery, eye level, flat rocky mountain summit in the foreground, mossy stone ground, ancient twisted pine tree, "
               "sea of clouds below, distant chinese karst peaks, golden light rays, divine light, glowing golden particles, mist, "
               "mystical, sacred, majestic, daylight, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, animal, turtle, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark, magic circle",
        "base": ("no humans, animal focus, genjii (touhou), touhou, minogame, tortoise, ancient divine tortoise, old tortoise, land tortoise, green shell, olive brown skin, "
                 "four legs, clawed feet, long white beard, bushy white eyebrows, half-closed eyes, "
                 "long fluffy white tail, flowing white hair-like tail, wise, flying tortoise"),
        # 2026-11-12 第一輪 C1～C4 都畫出整圈金光 / 雲 / 好幾隻烏龜 (去背會切掉) ➔ 拿掉發光、飄動、仰角，改成單隻烏龜安穩站著的側面全身
        # 2026-11-13 使用者：背景 B2 是浮空岩塊 ➔ 人物改漂浮版 (飛在空中、四腳放鬆垂著、鬍鬚尾巴往後飄)，仍然不要光暈 / 雲
        "char": ("solo, single tortoise, floating in the air, flying, levitating, legs relaxed and dangling, from side, three-quarter view, "
                 "beard and white tail trailing behind in the wind, ancient patterns carved on shell, "
                 "dignified, wise expression, half-closed eyes, simple background, white background, full body"),
        "char_negative": ("1girl, human, humanization, anthropomorphic, girl, rider, multiple tortoises, "
                          "aura, glow, glowing, golden light, energy, smoke, clouds, swirl, runes, symbols, light particles, "
                          "wings, feathers, sea turtle, flippers, dragon, waterfall, magic circle, danmaku"),
        "char_scale": 0.75,
    },
    ("rika", "N"): {
        # N「戰車技師」(沿用舊 SCENES)：在草地上修理自製的小戰車 (野花、藍天白雲、白天柔光)；拿扳手跪在戰車旁、臉頰沾油污、開朗笑
        # 外觀照萌娘百科 (封魔錄 1 面)：棕色長髮綁兩條麻花辮、棕瞳、白襯衫 + 紫色領結；舊 base 的護目鏡 / 吊帶工作褲不是原作，拿掉
        # 戰車要跟人物一起留在去背圖裡，所以戰車寫在 char (人物層)，草地、天空寫在 bg
        # 2026-11-12 使用者：草地背景跟人物 (吊著的齒輪機械、生鏽工作台) 不搭 ➔ 改成修車工坊室內，吊車、齒輪掛在天花板下
        "bg": ("no humans, scenery, indoors, workshop, garage, machine shop, steampunk, workbenches, tools hanging on walls, "
               "hanging chains, overhead crane, large gears, pipes, scattered spare parts, warm sunlight through windows, dust particles, "
               "eye level, cozy, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, tank, vehicle, military, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, rika (touhou), touhou, touhou (pc-98), brown hair, long hair, twin braids, brown eyes, "
                 "white shirt, collared shirt, purple bowtie, bowtie"),
        "char": ("kneeling next to a small cute tank, repairing tank, holding wrench, oil stain on cheek, cheerful smile, looking at viewer, "
                 "small handmade tank, flower decorations on the tank, toolbox, gears, bolts, full body"),
        "char_negative": "military uniform, soldier, gun, rifle, mecha, robot girl, goggles, overalls, short hair, helmet",
        "char_scale": 0.55,   # 日常場景人物小一點融入背景 (紅美鈴 R 0.49 / SR 0.56 的經驗)；戰車也要放得下
    },
    ("rika", "R"): {
        # R「邪惡工程師」(沿用舊 SCENES)：坐在長滿花的戰車「Flower～戰車」頂上指揮、得意的壞笑、風吹花瓣、草原藍天
        # N~SSR 沒有彈幕：舊 SCENES 的 tank cannon firing / danmaku / glowing bullets 拿掉，只留砲口一點硝煙
        # 萌娘百科：Flower～戰車有加強裝甲 + 藤蔓偽裝，所以戰車寫 vines / flowers；戰車在 char 層 (去背才留得住)
        "bg": ("no humans, scenery, meadow, flower field, rolling hills, blue sky, white clouds, sunlight, wind, flower petals flying, "
               "highly detailed"),
        "bg_negative": "1girl, person, human, character, face, tank, vehicle, military, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, rika (touhou), touhou, touhou (pc-98), brown hair, long hair, twin braids, brown eyes, "
                 "white shirt, collared shirt, purple bowtie, bowtie"),
        "char": ("sitting on top of a tank, riding tank, flower tank, tank covered in flowers and vines, armored tank, cannon, smoke from cannon, "
                 "pointing forward, mischievous grin, smug, looking at viewer, hair blowing in wind, petals, dynamic angle, full body"),
        "char_negative": ("military uniform, soldier, gun, rifle, mecha, robot girl, goggles, overalls, short hair, helmet, "
                          "danmaku, bullets, explosion, fire, magic circle"),
        "char_scale": 0.8,    # 戰車比人大；使用者 (2026-11-12)：0.65 置中時戰車像飛在天上 ➔ 放大、往下貼地
        "offset": (0.0, 0.17),
    },
    ("rika", "SR"): {
        # SR「花樣戰車大師」(沿用舊 SCENES)：邪眼「Evil Eye Σ」— 飛行戰車；站在邪眼上張開雙手得意大笑，天空雲海、光線
        # 萌娘百科的邪眼Σ造型：一顆大眼睛、紅色眼珠帶血絲、兩隻紫色蝙蝠翅膀、天使光環、兩根粗觸手、下面青色的東西 (可能是葉子)、眼皮下有紅色 Σ 標誌
        # N~SSR 沒有彈幕：舊 SCENES 的 laser beams / flower-shaped danmaku 拿掉；SR 也不放施法光效，只留邪眼本身
        # 邪眼要跟人物一起留在去背圖，寫在 char；背景只有天空
        "bg": ("no humans, scenery, sky, above the clouds, sea of clouds, blue sky, dramatic clouds, sunlight, light rays, wind, "
               "highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, eye, eyeball, monster, tank, vehicle, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night",
        "base": ("1girl, rika (touhou), touhou, touhou (pc-98), brown hair, long hair, twin braids, brown eyes, "
                 "white shirt, collared shirt, purple bowtie, bowtie"),
        "char": ("standing on top of a giant floating eyeball, evil eye sigma, huge eyeball, red iris, bloodshot eye, "
                 "purple bat wings on the eyeball, halo above the eyeball, two thick tentacles, green leaves under the eyeball, red sigma symbol, "
                 "arms spread, confident laugh, open mouth, looking at viewer, hair blowing in wind, dynamic angle, full body"),
        "char_negative": ("military uniform, soldier, gun, rifle, mecha, robot girl, goggles, overalls, short hair, helmet, "
                          "wings on girl, halo on girl, laser, danmaku, bullets, magic circle, gore, blood"),
        "char_scale": 0.75,   # 邪眼很大，人物在上面會變小；邪眼被切到時用 outpaint 補邊
    },
    ("chiyuri", "N"): {
        # N「教授助手」(沿用舊 SCENES)：研究室裡抱著一疊書和文件跑來跑去，紙張飛起來，開朗地笑
        # 背景 = 研究室 (書架、寫滿算式的黑板、燒瓶、大窗戶、陽光)；書與紙張留在人物層 (抱在手上，去背會一起留下)
        # 外觀照萌娘百科：金髮金瞳、偏左側的雙馬尾捲髮、藍白水手服 (胸前黃色結)、露臍、短褲、白色海軍帽 (船錨徽章、後面兩條緞帶)
        "bg": ("no humans, scenery, indoors, laboratory, study room, tall bookshelves, many books, chalkboard with equations, "
               "flasks, test tubes, beakers on desk, scattered papers, large window, sunlight, light rays, daylight, "
               "warm soft lighting, cozy, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, kitashirakawa chiyuri, touhou, touhou (pc-98), blonde hair, twintails, side twintails, curly hair, yellow eyes, red lips, "
                 "white sailor hat, anchor emblem, hat ribbon, sailor collar, blue sailor collar, white sailor shirt, yellow bow, "
                 "midriff, navel, blue shorts, short shorts"),
        "char": ("carrying a stack of books, holding papers, papers flying, running, cheerful smile, open mouth, "
                 "looking at viewer, twintails swaying, dynamic pose, full body"),
        "char_negative": "blue eyes, short hair, long straight hair, skirt, pleated skirt, dress, school uniform, marisa, kirisame marisa, witch hat, danmaku, magic circle",
        "char_scale": 0.85,   # 使用者 (2026-11-12)：0.6 人太小
    },
    ("chiyuri", "R"): {
        # R「水手服科學家」(沿用舊 SCENES)：在船的甲板上做實驗，拿著發光燒瓶、得意地笑 + 眨眼
        # 背景 = 甲板 (欄杆、繩索、海、海鷗、藍天白雲)；燒瓶 / 試管在人物手上 (去背會留下)
        "bg": ("no humans, scenery, ship deck, wooden deck, railing, ropes, mast, ocean, sea, horizon, seagulls, "
               "blue sky, white clouds, sunlight, wind, bright, summer, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark, storm",
        "base": ("1girl, kitashirakawa chiyuri, touhou, touhou (pc-98), blonde hair, twintails, side twintails, curly hair, yellow eyes, red lips, "
                 "white sailor hat, anchor emblem, hat ribbon, sailor collar, blue sailor collar, white sailor shirt, yellow bow, "
                 "midriff, navel, blue shorts, short shorts"),
        "char": ("holding glowing flask, holding test tube, science experiment, colorful bubbling liquid, sparkles, "
                 "smug smile, wink, one eye closed, looking at viewer, hat ribbons fluttering, wind, standing, dynamic angle, full body"),
        "char_negative": "blue eyes, short hair, long straight hair, skirt, pleated skirt, dress, school uniform, marisa, kirisame marisa, witch hat, danmaku, magic circle",
        "char_scale": 0.55,
    },
    ("chiyuri", "SR"): {
        # SR「時空船之助手」(沿用舊 SCENES)：駕駛可能性空間移動船穿越時空 (光環、曲速隧道、星雲)
        # 去背只留人物：船舵 / 控制台放人物層很可能被切掉或切一半 ➔ 船艙 (發光控制台、全息螢幕、窗外的時空隧道) 全放背景，
        # 人物只做「站在船艙裡、一手往前指 / 下指令」的姿勢，SR 不放彈幕
        "bg": ("no humans, scenery, inside a futuristic spaceship bridge, cockpit, glowing control panels, holographic screens, "
               "large front window, flying through a space-time portal, glowing rings, warp tunnel, stars, nebula, light streaks, "
               "blue and gold light, sci-fi, epic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, daytime, blue sky",
        "base": ("1girl, kitashirakawa chiyuri, touhou, touhou (pc-98), blonde hair, twintails, side twintails, curly hair, yellow eyes, red lips, "
                 "white sailor hat, anchor emblem, hat ribbon, sailor collar, blue sailor collar, white sailor shirt, yellow bow, "
                 "midriff, navel, blue shorts, short shorts"),
        "char": ("standing, pointing forward, giving orders, other hand on hip, determined smile, confident, looking at viewer, "
                 "hat ribbons flowing, twintails flowing, wind, dynamic angle, full body"),
        "char_negative": "blue eyes, short hair, long straight hair, skirt, pleated skirt, dress, school uniform, marisa, kirisame marisa, witch hat, ship's wheel, steering wheel, chair, sitting, danmaku, magic circle",
        "char_scale": 0.6,
        "offset": (0.0, 0.14),   # 使用者 (2026-11-12)：人往下一點 (腳踩到船艙地板)
    },
    ("yumemi", "R"): {
        # R「比較物理學教授」(沿用舊 SCENES)：大學階梯教室，黑板寫滿物理公式、桌椅、書本、大窗戶白天光線；
        # 人物拿教鞭指向旁邊 (黑板在背景)、一手插腰、自信得意地笑。平常服裝：不披戰鬥用披風 (萌娘百科：披風是戰鬥時才披)
        # 日常場景人物縮小融入背景 (參考紅美鈴 R 0.49)
        "bg": ("no humans, scenery, university lecture hall, large chalkboard covered with physics equations, chalk diagrams, "
               "rows of wooden desks, stacks of books, large window, daylight, sunlight, soft lighting, academic, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "base": ("1girl, okazaki yumemi, touhou, touhou (pc-98), dark red hair, long hair, braid, single braid, hair behind back, red eyes, "
                 "white shirt, puffy sleeves, red vest, breast pocket, red long skirt, white frilled hem, red bowtie, red shoes, white socks"),
        "char": ("standing, holding pointer stick, pointing to the side, lecturing, hand on hip, confident smile, smug, "
                 "looking at viewer, full body"),
        "char_negative": "cape, cloak, blonde hair, yellow eyes, black vest, black dress, glasses, lab coat, chalkboard, desk, chair, sitting",
        "char_scale": 0.5,
    },
    ("yumemi", "SR"): {
        # SR「夢幻的魔術教授」(沿用舊 SCENES)：可能性空間移動船的艙內實驗室，科幻機械、全像螢幕、空中浮著發光的數學公式；
        # 人物披上戰鬥披風，手上的科學儀器發光、用科學施展「人造魔法」，興奮地咧嘴笑。
        # N~SSR 沒有彈幕：舊 SCENES 的 magic circle made of formulas 拿掉；浮空公式 / 全像螢幕放背景 (去背會去掉人物身邊的光)
        "bg": ("no humans, scenery, inside a futuristic spaceship laboratory, sci-fi machinery, glowing scientific instruments, "
               "holographic screens, glowing equations floating in the air, mathematical symbols, control panels, red and white interior, "
               "cool blue lighting, sparkles, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, magic circle",
        "base": ("1girl, okazaki yumemi, touhou, touhou (pc-98), dark red hair, long hair, braid, single braid, red eyes, "
                 "white shirt, puffy sleeves, red vest, red long skirt, white frilled hem, red bowtie, red shoes, white socks, "
                 "red cape, white collar, white trim, cape lining"),
        "char": ("standing, holding a glowing scientific device, glowing flask, one hand raised, excited grin, open mouth, "
                 "cape fluttering, dynamic pose, dynamic angle, looking at viewer, full body"),
        "char_negative": "blonde hair, yellow eyes, black vest, black dress, glasses, lab coat, magic circle, danmaku, sitting",
        "char_scale": 0.56,
    },
    ("yumemi", "SSR"): {
        # SSR「時空空間之主宰」(沿用舊 SCENES)：可能性空間移動船上方，時空裂縫、碎裂的天空、漩渦狀次元門、星星；
        # 身後巨大的發光十字架光束 (符卡「十字架光束兵器」) 放背景；人物張開雙臂、狂笑、紅眼發光，披風與長髮翻飛。
        # 船畫在背景下方 (人物腳下)，人物圖不畫船 (去背只留人物，船身不會被保留)
        # N~SSR 沒有彈幕；十字光束是背景裡的一道大光，不是彈幕 (SSR 的閃光 build_cards 會自動加)
        "bg": ("no humans, scenery, top deck of a giant futuristic flying ship at the bottom, space-time rift, cracked sky, "
               "swirling dimensional portal, stars, giant glowing cross-shaped laser beam in the center, massive energy cross, "
               "light rays, bloom, epic, majestic, dramatic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, daytime, blue sky, danmaku",
        "base": ("1girl, okazaki yumemi, touhou, touhou (pc-98), dark red hair, long hair, braid, single braid, red eyes, "
                 "white shirt, puffy sleeves, red vest, red long skirt, white frilled hem, red bowtie, red shoes, white socks, "
                 "red cape, white collar, white trim, cape lining"),
        "char": ("standing, arms spread, arms outstretched, maniacal laugh, open mouth, glowing eyes, red eyes, "
                 "cape billowing, hair flowing, wind, powerful, dynamic pose, dynamic angle, from below, looking at viewer, full body"),
        "char_negative": "blonde hair, yellow eyes, black vest, black dress, glasses, lab coat, magic circle, danmaku, ship, vehicle, cross, sitting",
        "char_scale": 0.85,
    },
    # 夢子 R / SR / SSR (TH05 舊卡重生，2026-11-12 桌機)：外觀沿用 make_workflow.BASE (舊作 PC-98：金色波浪長髮、黃眼、女僕頭飾、紅色女僕裝 + 白圍裙)；
    # 神綺的女僕長，武器是劍 (不是飛刀)；不要畫成咲夜 (EXTRA_NEGATIVE 已排除銀髮藍裙)
    ("yumeko", "R"): {
        # 使用者選 (2026-11-12)：B2 (s2202) C1 (s3303)
        # R「魔界的女長官」：魔界宮殿大廳，提裙行禮、被誇獎時害羞又得意的笑
        "bg": ("no humans, scenery, grand palace hall in the demon world, pandemonium, red carpet, chandeliers, tall gothic windows, "
               "purple sky outside, marble pillars, warm lighting, elegant, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "char": ("curtsey, bowing politely, holding skirt, blushing, embarrassed smile, proud, happy, looking at viewer, standing, full body"),
        "char_negative": "sword, weapon, knife, wings",
        "char_scale": 0.75,
    },
    ("yumeko", "SR"): {
        # 使用者選 (2026-11-12)：B1 (s1101) C4 (s6606)
        # SR「飛刀之魔界女僕」：宮殿長廊，指間夾著多把劍、旋身擲出，冷靜幹練
        "bg": ("no humans, scenery, long palace corridor in the demon world, red and gold, arched ceiling, rows of windows, "
               "purple sky, flying swords in the distance, light streaks, dramatic perspective, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "char": ("holding multiple swords between fingers, sword in each hand, spinning, about to throw, mid-turn, "
                 "calm expression, cool, composed, sharp eyes, skirt fluttering, hair flowing, dynamic pose, full body"),
        "char_negative": "knife, kitchen knife, wings, gun",
        "char_scale": 0.85,
    },
    ("yumeko", "SSR"): {
        # 使用者選 (2026-11-12)：B1 (s1101) C3 (s5505)，左上劍焰被切 ➔ 補邊 O3 (outpaint s8802 第 1 張) ➔ wf-up s9901；使用者用 PhotoCraft 放大人物 (10c_char_photocraft.png)
        # SSR「神綺的終極刃舞」：魔界王座廳，擋在空王座前，背後數百把劍排成巨大環狀 (劍陣畫在背景)
        "bg": ("no humans, scenery, demon world throne room, grand empty throne, hundreds of swords floating in giant rings, "
               "radial sword formation, glowing blades, red and gold light, light particles, light rays, majestic, epic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "char": ("standing guard, protective stance, one arm outstretched, holding sword, sword pointed forward, "
                 "determined, fierce eyes, glowing blade, hair flowing, skirt fluttering, wind, powerful, full body"),
        "char_negative": "knife, kitchen knife, wings, throne, multiple swords",
        "char_scale": 0.9,
        "wing_mask": "10m_flame.png",   # 去背會把劍的藍色火焰切掉 ➔ 06 基本圖抓青藍色做遮罩，範圍內保留
    },
    # 露易絲 N / R / SR (TH05 舊卡重生，2026-11-12 桌機)：外觀沿用 make_workflow.BASE (金髮短馬尾、瞇瞇眼、白色寬簷遮陽帽 + 紫緞帶、淡紫長裙、紫領巾)；
    # 魔界的旅行者；不要畫成藍髮版
    ("luize", "N"): {
        # 使用者選 (2026-11-12)：B2 (s2202) C1 (s3303)
        # N「魔界旅行者」：魔界城門前提著行李箱，壓著帽子眨眼，興奮地準備出發
        "bg": ("no humans, scenery, demon world city gate, makai, strange spiral towers, purple sky, floating rocks, "
               "stone road leading out of the city, morning light, soft lighting, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "char": ("holding suitcase, carrying luggage, hand on hat, one eye closed, wink, excited, eager smile, walking, from side, full body"),
        "char_negative": "wings, weapon",
        "char_scale": 0.75,
    },
    ("luize", "R"): {
        # 使用者選 (2026-11-12)：B1 (s1101) C1 (s3303)
        # R「觀光的魔界人」：景觀台上坐在行李箱上看地圖，悠哉曬太陽
        "bg": ("no humans, scenery, scenic overlook, flower field, distant small town, rolling hills, blue sky, white clouds, "
               "sunny day, peaceful, bright, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "char": ("sitting on suitcase, holding map, camera around neck, tourist, relaxed, closed eyes, content smile, basking in sunlight, full body"),
        "char_negative": "wings, weapon",
        "char_scale": 0.75,
    },
    ("luize", "SR"): {
        # 使用者選 (2026-11-12)：B1 (s1101) C1 (s3303)
        # SR「邊境流浪魔導士」：魔界與人間的交界，張手放出旋轉的方形結界彈幕，第一次認真
        "bg": ("no humans, scenery, border between two worlds, dimensional rift, half purple demon world sky and half blue sky, "
               "rotating square barriers, converging glowing squares, geometric patterns, purple and white light, light rays, epic, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, text, watermark, lowres, worst quality, low quality, blurry, frame, border",
        "char": ("serious expression, eyes open, determined, arms spread, casting magic, glowing hands, "
                 "hat ribbon fluttering, dress fluttering in wind, dynamic angle, full body"),
        "char_negative": "wings, weapon, suitcase",
        "char_scale": 0.85,
    },
    # 艾莉 N / R / SR (TH04 舊卡重生)：外觀沿用 make_workflow.BASE["elly"] (金色雙鑽頭捲髮、黃瞳、白色寬簷帽纏紅緞帶、深紅長裙白圍領、紅柄大鐮刀)；
    # 夢幻館 (幽香的住所) 的門番；鐮刀一定要留在人物層 (拿在手上，去背才不會被切掉)；EXTRA_NEGATIVE["elly"] 已擋死神斗篷 / 小町
    # N～SR 沒有彈幕：舊 SCENES 的地磚彈幕、迴旋光環拿掉，飛起的地磚 / 花瓣放背景
    ("elly", "N"): {
        # N「館門守衛」：悠閒 (浪費光陰) 的門番，白天在夢幻館的鐵門前靠著鐮刀打呵欠
        # 背景 = 洋館大門 (鐵柵門、石柱、門後的洋館)、門前的向日葵花田、藍天白雲；平視、日常柔光
        "bg": ("no humans, scenery, eye level, ornate western mansion gate, wrought iron gate, stone gate pillars, stone path, "
               "western mansion in the distance behind the gate, sunflower field, sunflowers, blue sky, white clouds, "
               "daylight, soft lighting, peaceful, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, scythe, weapon, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "char": ("standing, leaning on scythe, both hands resting on scythe handle, yawning, open mouth, one eye closed, sleepy, bored, relaxed, "
                 "looking away, from side, three-quarter view, full body"),
        "char_negative": "cleavage, revealing clothes, short dress, skirt lift, sunflowers, flowers, gate, sitting, multiple scythes",
        "char_scale": 0.65,   # 日常卡人物小一點融入背景；鐮刀很長，要整支放得下
        "offset": (0.0, 0.14),   # 使用者 (2026-11-14)：往下一點，腳要踩到地板 (石板路)
    },
    ("elly", "R"): {
        # R「大鐮的守衛」：闖入者來了 ➔ 在館前石板廣場擺出迎擊架式，鐮刀橫在身前擋住去路、表情認真
        # 背景 = 夢幻館正面 (階梯、大門)、石板廣場、被掀起飛在空中的碎地磚 (原作把地磚當彈幕，這裡只當背景的碎石)、風吹向日葵花瓣
        "bg": ("no humans, scenery, eye level, front of a grand western mansion, stone stairs, large mansion doors, stone tiled plaza, "
               "cracked floor tiles, broken stone tiles floating in the air, debris, sunflower petals flying in the wind, "
               "sunflowers on both sides, blue sky, wind, dramatic, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, scythe, weapon, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "char": ("battle stance, holding scythe with both hands, scythe held horizontally in front of her, blocking the way, legs apart, "
                 "determined expression, serious, looking at viewer, hat ribbon fluttering, hair and dress fluttering in the wind, "
                 "dynamic pose, full body"),
        "char_negative": ("cleavage, revealing clothes, short dress, skirt lift, floor tiles, debris, rocks, slash effect, motion lines, "
                          "danmaku, magic circle, multiple scythes"),
        "char_scale": 0.75,
    },
    ("elly", "SR"): {
        # SR「夢幻館的最後防線」：死鐮「迴旋斬擊」的起手 ── 鐮刀高舉過頭準備甩出去，自信的壞笑、眼睛發亮；微仰視更有氣勢
        # 背景 = 夕陽下的夢幻館 (高聳的洋館剪影、大門敞開)、滿天捲起的向日葵花瓣、光線；SR 沒有彈幕，鐮刀不畫旋轉光環 (去背會切掉)
        "bg": ("no humans, scenery, eye level, slightly from below, towering grand western mansion, open mansion gate, stone courtyard, "
               "sunset, orange and crimson sky, dramatic clouds, sunflower petals swirling in the wind, sunflower field, "
               "light rays, bloom, epic, majestic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, scythe, weapon, text, watermark, lowres, worst quality, low quality, blurry, frame, border, magic circle",
        "char": ("from below, raising scythe overhead with both hands, about to throw the scythe, fierce grin, confident, glowing eyes, "
                 "looking at viewer, hat ribbon flowing, hair flowing, dress fluttering in the wind, dynamic angle, full body"),
        "char_negative": ("cleavage, revealing clothes, short dress, skirt lift, upskirt, panties, spinning effect, energy rings, slash effect, "
                          "motion lines, petals, danmaku, magic circle, multiple scythes"),
        "char_scale": 0.8,
    },
    # 幻月 R / SR / SSR (TH04 舊卡重生)：外觀沿用 make_workflow.BASE["gengetsu"] (萌娘百科：過肩金色直髮、金瞳、紅色大蝴蝶結、
    # 淡粉紅長裙 + 棕紅小背心、紅領結、背後白色天使羽翼)；翅膀照大妖精 / 芙蘭 / 小惡魔的做法 ➔ 人物直接帶翅膀一起生、一起去背
    # (BASE 已經寫了翅膀，不用 inline_wings，char_negative 也不要擋翅膀)；EXTRA_NEGATIVE["gengetsu"] 已擋黑翼 / 蝙蝠翼 / 女僕 (夢月)
    # R～SSR 沒有彈幕 (舊 SCENES 的金色子彈、發散彈幕、魔砲拿掉)；SSR 的閃光特效由程式加；翅膀很大，人物縮小一點免得翅膀被切
    ("gengetsu", "R"): {
        # R「夢幻館的主人」：天然呆 ── 在夢幻館的庭園裡歪頭、手指抵下巴，一臉困惑；翅膀半收、裙擺被風輕輕吹起 (稍有動作)
        # 背景 = 夢幻世界的庭園 (花圃、白色涼亭、遠方的洋館夢幻館)、浮空小島、粉彩天空與粉紅雲；白天柔光
        "bg": ("no humans, scenery, eye level, dreamlike garden, flower garden, white gazebo, western mansion in the distance, "
               "floating islands in the sky, pastel sky, pink clouds, fluffy clouds, flower petals, "
               "daylight, soft lighting, whimsical, fantasy, highly detailed"),
        "bg_negative": "1girl, person, human, character, face, wings, feathers, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "char": ("standing, head tilt, index finger to chin, puzzled, confused, airhead, blank stare, slightly open mouth, "
                 "wings half folded, wings slightly spread, skirt swaying, hair swaying, three-quarter view, from side, full body"),
        "char_negative": ("cleavage, revealing clothes, short dress, skirt lift, upskirt, panties, question mark, "
                          "danmaku, magic circle, sitting, swing, flowers, multiple girls"),
        "char_scale": 0.8,
    },
    ("gengetsu", "SR"): {
        # SR「金翼的夢幻魔王」：姊姊的得意氣場 ── 浮在夢幻世界的雲海上抱胸挑眉、從上往下看，翅膀大大張開 (比 R 更有氣勢)
        # 背景 = 雲海之上的夢幻世界、金色夕陽、遠方浮在雲上的洋館、光線、飄落的金白羽毛 (羽毛只放背景，去背會被切掉)
        "bg": ("no humans, scenery, above the clouds, sea of clouds, dream world, western mansion floating on clouds in the distance, "
               "golden sunset, golden sky, glowing white feathers drifting in the air, light rays, bloom, "
               "majestic, fantasy, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, wings, text, watermark, lowres, worst quality, low quality, blurry, frame, border, night, dark",
        "char": ("floating, arms crossed, smug, raised eyebrow, proud, confident smile, looking down at viewer, slightly from below, "
                 "wings spread wide, large white wings fully spread, hair flowing, dress fluttering in the wind, full body"),
        "char_negative": ("cleavage, revealing clothes, short dress, skirt lift, upskirt, panties, "
                          "danmaku, bullets, magic circle, multiple girls"),   # 不擋 feathers (會跟羽翼打架)
        "char_scale": 0.8,
    },
    ("gengetsu", "SSR"): {
        # SSR「漆黑夢幻之支配者」：鬼畜的本性 ── 施展「發狂發散彈幕」的起手：單手往前張開放出力量、狂笑、眼睛發光、
        # 翅膀全開、頭髮衣服被魔力吹得狂舞，微仰視 (最有動態；彈幕只有 UR/LR，這裡不畫彈幕，閃光由程式加)
        # 背景 = 崩壞扭曲的夢幻世界：紺色 / 紫色霧氣漩渦的天空、碎裂浮空的島嶼、遠方被紺霧籠罩的洋館、光線 (原作翅膀生氣時帶紺色霧氣)
        "bg": ("no humans, scenery, distorted dream world, swirling indigo and violet mist, dark blue fog vortex in the sky, "
               "cracked dreamlike sky, shattered floating islands, floating rubble, western mansion silhouette shrouded in blue mist, "
               "twilight, purple and deep blue, light rays, bloom, epic, ominous, majestic, highly detailed, intricate details"),
        "bg_negative": "1girl, person, human, character, face, wings, text, watermark, lowres, worst quality, low quality, blurry, frame, border, danmaku, bullets",
        "char": ("floating, dynamic pose, one arm outstretched forward, open palm, releasing power, casting magic, "
                 "sadistic smile, evil grin, crazy laugh, glowing eyes, from below, "
                 "wings spread wide, large white wings fully spread, hair flowing wildly, dress fluttering violently, dynamic angle, full body"),
        "char_negative": ("cleavage, revealing clothes, short dress, skirt lift, upskirt, panties, "
                          "danmaku, bullets, magic circle, beam, energy ball, aura, mist, multiple girls"),
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

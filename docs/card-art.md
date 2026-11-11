# 🎨 卡面製作 (ComfyUI、分層合成、PhotoCraft)

> 從 `CLAUDE.md` 拆出來的細節文件 (2026-11-11)。要做這方面的工作時才讀；改了內容記得一起更新。

## ⭐ 現行規則 (2026-11-11 使用者指定，取代下面舊的「UR / LR 才分層」說法)
- **N～LR 全部階級都走高清分層流程** `tools/card_art/layered/hd_card.py`，步驟一樣、也都放大 16 倍再壓縮：
  1. **背景**（01 生成 → 02 重繪 → 03 高清）
  2. **彈幕**（04，**只有 UR / LR**）：彈幕越多背景越暗，`auto_dim(density)` = 0.65 − 0.2 × density（LR 1.0 ➔ 0.45、UR 0.75 ➔ 0.5）；同心環發射中心預設 2 個 (`DANMAKU_ORIGINS`，左上＋右下) + 中間螺旋 = 3 個原點，位置用 `danmaku.ORIGIN_SETS` 上下錯開 (不要只取前幾個，會全擠在上半部)；N～SSR 不壓暗、沒有彈幕
  3. **翅膀**（有翅膀的角色先做翅膀層 W1~W5，再做人物）／其他附屬物件（尾流、環繞物件）
  4. **人物**（06~10，單獨生成、白底、去背；UR / LR 加背光打光 10b）
  5. **卡框** → 文字 → 等級（11~15）
  6. **特效**（16 GIF）：SSR = shine 閃光、UR = holo 雷射、LR = holo + sparkle；N～SR 靜態
- 舊的單張生成卡（`make_workflow.py` 的 `SCENES`）**全部重生**：照現有的 `SCENES` 構想拆成 `LAYERS` 的背景（bg）與人物動作（char），一位一位做，每張先給候選讓使用者挑，定案才推。進度清單在 `TODO.md` 第 1 節。
- **翅膀：先試人物直接帶翅膀**（2026-11-11 大妖精）：翅膀層 (W1~W5 程式排列) 做出來使用者覺得怪；改成 `LAYERS` 加 `"inline_wings": True`，人物提示自動加上翅膀、負面提示拿掉翅膀相關字，去背後翅膀有保留下來 (會變得比較不透明)。翅膀層留給水晶翅膀、六翼這種模型畫不好的。
  - 大妖精的角色名本身就會讓模型畫出金框翅膀；「飛行 / 半空」姿勢更一定會畫。要「沒有翅膀」的人物時，拿掉角色名只描述外觀又會讓衣服跑掉 (水手服)，所以有翅膀的角色乾脆直接帶翅膀。
  - 硬把人物圖上的翅膀塗掉，翅膀蓋到臉 / 手時會連帶弄壞 (大妖精 R 第一次右眼、右手變形)；塗白也會被去背模型當成物體留下，要塗成附近的背景色。
- 階級越高畫面越強的原則不變（N/R 日常、SR 輕鬆、SSR 施法有動態、UR/LR 招牌大招 + 大量彈幕）。

- **卡面（`tools/card_art/`）**：
  - 流程：`make_workflow.py <角色> <階級> <種子> <out.json>` 產生 ComfyUI 工作流程（Animagine XL 4.0 Opt、896×1064、一次 2 張）→ 使用者挑圖 → 存成 `images/Original/Art/<角色>_<階級>.png` → `python tools/card_art/build_cards.py [角色…]` 產生 `images/Thumbnails/<角色>_<階級>.png` 並寫入 Thumbnails.json → **push 之後** Discord 才抓得到圖。
  - 合成順序：角色原圖墊底 → 蓋上 `empty.png`（畫窗透明，邊角不會有瑕疵）→ 左上中文稱號（衡山毛筆行書，`吞→呑`、`絕→絶`）、右上等級圖（`tools/card_art/rarity/`，2026-10-29 換成使用者給的新綠幕版 `rarity_greenscreen.jpg`，用 `make_rarity.py` 去背切成 6 張；`card.py` 的 `BADGE_SCALE = 1.25` 放大 1.25 倍）、名牌英文名（Harukaze Solid，可稍微超出名牌）。`empty.png` 由 `make_empty.py` 從綠幕卡框產生（含底部 TouHou / Project 小字）；綠幕原圖只有 736×1024，所以先用 ComfyUI 的 4x-UltraSharp 放大 4 倍再縮成 1748×2432，存成 `empty_greenscreen_hd.png`（2026-10-29，卡框明顯變清楚）。改了卡框或等級圖要重跑 `make_empty.py` / `make_rarity.py` 和 `build_cards.py`（不加參數＝全部角色）。
  - **分階段輸出**（使用者指定）：`build_cards.py --stages` 會在 `card_stages/`（已加入 .gitignore，太大不進 repo）存每一步的圖：`_base/frame.png`、`_base/rarity/*.png`（基礎元素）；`<角色>_<階級>/0_pic.png`（原圖）→ `1_art`（人物）→ `2_frame`（人物＋框）→ `3_text`（＋名字與稱號）→ `4_card`（＋等級，完成）。程式在 `card.render_stages()`。
  - **動態卡 GIF**（使用者 2026-10-29 指定）：`build_cards.py` 對 SSR / UR / LR 另外產生 `images/Thumbnails/<角色>_<階級>.gif`，Thumbnails.json 指向 GIF（程式不用改，Discord 縮圖直接播）。效果在 `animate.py` 的 `RARITY_EFFECTS`：SSR `shine`（白色閃光掃過）、UR `holo`（實體雷射卡那種全息彩虹塗層：以閃光為基礎，彩虹隨角度流動 + 金屬細紋 + 亮片，蓋在整張卡上，畫窗是外框的 `HOLO_WINDOW`=0.75 倍）、LR `holo+sparkle`（再加畫窗內四角星光閃爍）。使用者要的「雷射」是雷射閃卡的全息反光，**不是光束**。2026-10-30 調整：雷射強度 0.85、32 格 × 90ms（約 2.9 秒一輪，比較慢）、所有動態都頭尾銜接、全部格子共用調色盤（不閃爍）；每張約 2～6MB；`--no-gif` 只做靜態圖。單張試作：`python tools/card_art/animate.py <角色> <階級> [效果] <out.gif>`。
  - **分層合成**（神綺 LR）：模型畫不出清楚的大量彈幕（會變成子彈彈殼或糊成一團），所以改成「AI 宇宙背景＋程式畫的彈幕＋AI 單獨生成再去背的人物」：`tools/card_art/layered/cutout.py`（BiRefNet 去背，用 comfy venv 的 python -I 執行）、`danmaku.py`（光球環、螺旋米粒彈、星彈；風格 `rainbow` = 神綺 LR 彩虹、`freeze` = 琪露諾 UR 冰晶，8 成彈幕凍白 + 六角雪花；`density` 調數量）。新角色的大招可以再加風格。現在一律走下面的高清分層流程 `hd_card.py`（舊的 `compose_lr.py` 已於 2026-10-30 刪除）。
  - **高清分層流程**（使用者 2026-10-30 指定，神綺 LR 試作完成）：`tools/card_art/layered/hd_card.py`（檔頭有完整步驟與指令）。
    - 每一步的產出與修改後的圖都要保留（方便之後微調），放在 `images/Original/<分類>/<角色>/<階級>/`（分類 = `Characters/` 資料夾，例如 TH05）：背景 01 生成 → 02 重繪 → 03 放大 16 倍 → 04 壓暗加彈幕 → 05 壓縮；人物 06 生成 → 07 重繪 → 08 放大 16 倍 → 09 去背 → 10 壓縮 → 10b 打光；疊層 11 沒有框的完整原圖 → 12 背景 + 卡框 → 13 + 人物 → 14 + 文字 → 15 + 等級 → 16 GIF。`*_hd.png`（每張數十 MB）和重做前的 `_old_*/` 只留在本機。
    - 疊層順序（使用者指定）：背景 > HD 外框 > 去背人物（蓋在卡框上）> 文字與等級 > 特效。背景是整張卡大小（沒有框的原圖也完整），彈幕畫滿整張卡。人物放在畫窗大小的畫布上，`LAYERS` 的 `tilt`（傾斜）、`char_scale`、`offset`（位置微調，超出畫窗切掉）可以調。
    - 去背人物另外存成 `images/Original/Art/<角色>_<階級>_char.png`（使用者：UR / LR 都要留）。
    - **打光**（使用者 2026-10-30 指定，`layered/relight.py`，`LAYERS` 的 `light`）：背景是大量發光彈幕，人物要背光。整體冷色調壓暗 + 邊緣輪廓光（顏色取自身後彈幕）+ 身後光暈；翅膀黑 / 紫色部分再壓暗、紅色紋路螢光發亮（只選四周被翅膀紫黑色包圍的紅色區塊，披肩、衣服不會被誤選；用方形形態學會出現方塊光斑、還會吃到頭髮，不要用）；眼睛發光（座標手動找，是 `10_char.png` 上的位置）。產出 `10b_char_lit.png`，有這張時疊層就用它。全部用程式算，不會改到人物線條。
    - **翅膀分層（使用者 2026-10-30 指定，琪露諾 UR 起，有翅膀的角色優先用）**：人物和翅膀畫在同一張圖時，翅膀常被切掉、顏色選取會染到同色系的手 / 裙子 / 蝴蝶結、手描遮罩經過重繪放大去背後會對不準、去背模型會把半透明水晶切掉。改成：人物不畫翅膀（可以拿選好的人物用手描身體輪廓把翅膀塗白，例如琪露諾 06h）+ 翅膀單獨生成（W1 單顆水晶，no humans、白底）→ W2 放大 4 倍 → W3 去背只留最大一塊 → W4 `wings.py` 依 `LAYERS["wings"]["items"]`（角度、長度、粗細、離背距離，左右自動鏡射）排在背後錨點（06 座標，`make_char` 換算成 `10_anchor.json`）→ W5 整層打光（`emissive` 的 `mask: "alpha"`、`body` 亮度、`prism` 彩虹稜鏡）→ `10d_char_wings.png`（人物蓋在翅膀上）。調翅膀只要改參數重跑 `hd_card.py wings` + `compose`，不用重新生成。`relight.py` 的 `emissive` 也支援顏色選取 / 遮罩、`fill`（補洞）、`prism`（彩虹）。
    - **掃帚尾流（使用者 2026-10-31 指定，魔理沙 UR 起）**：沒有翅膀但有掃帚的角色，尾流也做成獨立圖層：`layered/trail.py` 從掃帚尾端拉出幾條擺動的彩虹光帶 + 金白核心 + 沿路星星，`LAYERS["trail"]`（anchor = 掃帚尾端的 06 座標、angle 疊層後方向、length / width / wave 比例、spread、ribbons、stars、sat、core）→ `T1_trail.png` → `10e_char_trail.png`（人物蓋在尾流上）。調整只要改參數重跑 `hd_card.py trail` + `compose`。人物改了大小 / 傾斜後眼睛座標要重找。
    - **環繞物件圈（2026-10-31，靈夢 UR 的陰陽玉起）**：`layered/orbs.py` 把單顆素材（O1 生成 → O3 去背）排成斜橢圓，分成人物後面 / 前面兩層（後半圈稍小稍暗），中間可連一圈結界光環；`LAYERS["orbs"]`（anchor 06 座標、count、rx / ry / size 比例、tilt、depth、phase、spin、link、`crop_square` 去掉球下面連著的倒影）→ `O4_orbs_back / front.png` → `10f_char_orbs.png`。彈幕風格多了 `seal`（七彩大光球 + 紅白符札 + 小陰陽玉，靈夢）。
    - **共用構圖提示不要寫翅膀**：曾經把「翅膀完整入鏡」寫在 `CHAR_COMPOSITION`，魔理沙 4 張全長出翅膀；有翅膀的寫在各卡 `LAYERS["char"]`。各卡可用 `char_negative` 加負面提示、`extra_negative` 取代 `make_workflow.EXTRA_NEGATIVE`（魔理沙共用的「不要拿掃帚」會跟騎掃帚打架）。彈幕風格多了 `stars`（全部星彈，魔理沙）。
    - **翅膀很大的角色（神綺六翼）模型一定會把翅膀畫出畫面**：直長 / 正方形 / 橫長畫布、加強提示都沒用；直接往外擴圖會長出多餘的翅膀。可行做法：挑一張好的 → 縮小到 60% 放在白色大畫布 → 被切的翅膀用 OpenCV inpaint 往外抹一小段當顏色引導（越遠越淡）→ 只重畫外圍（SetLatentNoiseMask，denoise 0.9，下方腳的部分不重畫，不然會多一隻靴子）→ 接縫一圈再用 denoise 0.4 輕度重繪 → `hd_card.py wf-up` 走重繪 / 高清。神綺 LR 的 06a~06d 就是這幾步。
  - **UR 與 LR 一律用分層合成**（使用者 2026-10-29 指定，從 TH06 開始）：背景 / 彈幕（程式畫）/ 人物（單獨生成、正方形畫布、去背）分開做再合成，見下面「分層合成」。
  - **UR 和 LR 的做法與步驟完全一樣**（使用者 2026-10-30 指定）：都走上面的高清分層流程（背景 01~05、人物 06~10、打光 10b、PhotoCraft 手修 10c、疊層 11~16），**只差最後的動態特效**（`animate.RARITY_EFFECTS`：UR = holo、LR = holo + sparkle）。畫面風格也一樣：背景有大量彈幕（UR 的 `density` 可以少一點，例如 0.75，LR 是 1.0）、人物背光（`light`）、人物在畫面中的比例偏小（`char_scale` 約 0.8，彈幕當主角）。舊的 UR 之後要一張張改成這套流程：已完成琪露諾、魔理沙、靈夢（2026-10-31）；還沒改的是魅魔、愛麗絲、神綺（單張生成）。
  - 階級越高畫面越強：SR 日常輕鬆、SSR 施展法術有動態、UR 招牌大招（光效、結界、極限火花）；都維持明亮、淡陰影、全身。prompt 在 `make_workflow.py` 的 `SCENES`，英文名在 `build_cards.py` 的 `EN_NAMES`（新角色兩邊都要加）。
  - 字型：衡山毛筆是 public domain 放在 repo；**`HarukazeSolid.ttf` 是 demo 版限個人使用，已加入 `.gitignore`，換電腦要手動複製到 `tools/card_art/fonts/`**（跟 .env 一樣）。
  - **進度（2026-10-29）**：已完成 靈夢、魔理沙（Main）、魅魔（TH01）、玄爺、里香（TH02）、千百合、夢美（TH03）、艾莉、幻月、夢月（TH04）、愛麗絲（舊作外觀）、露易絲、神綺（LR 為分層合成）、雪與舞、夢子（TH05，舊作全部完成）。TH06：琪露諾（UR 2026-10-30 改用高清分層 + 翅膀分層重做）。**下一位：大妖精 daiyousei（TH06）**，依 `Characters/TH06/` 順序：大妖精 daiyousei → 芙蘭朵露 flandre（SSR/UR/LR）→ 小惡魔 koakuma → 紅美鈴 meiling → 帕秋莉 patchouli → 蕾米莉亞 remilia（SSR/UR/LR）→ 露米婭 rumia → 十六夜咲夜 sakuya。新作角色查萌娘百科一般條目即可。其餘尚未做的角色顯示 fill。
  - **每位角色的做法（使用者指定：一位一位處理）**：
    0. **先上網找參考圖**（使用者 2026-10-29 指定，從夢美開始）：**優先查萌娘百科**（使用者指定，東方資料最詳細，例如 `https://zh.moegirl.org.cn/艾丽(东方Project)`，有外貌、萌點、性格、設定 neta），舊作角色要查「(東方Project舊作)」條目（例如 `愛麗絲(東方Project舊作)`，跟新作同名角色是不同頁）；立繪圖檔可從 Touhou Wiki（en.touhouwiki.net 的 `/wiki/<作品>/Characters` 頁，例如 `Mystic_Square/Characters` 有 TH05 全員頭像、`Embodiment_of_Scarlet_Devil/Characters` 有 TH06 立繪）取得；THBWiki 有 Cloudflare 驗證、Danbooru 內建瀏覽器打不開。確認髮型髮色、服裝、配件、招牌道具，把參考圖與重點特徵給使用者看，再依此寫 prompt。
    1. 在 `make_workflow.py` 加 `BASE`（外觀 Danbooru 標籤）、每個階級的 `SCENES`（依稱號、個性、故事；階級越高越強），需要時加 `EXTRA_NEGATIVE`（可用角色或 `(角色, 階級)` 當鍵）；在 `build_cards.py` 加 `EN_NAMES`。先用一兩句話跟使用者說明各階級的構想。
    2. 每個階級用兩個種子各生 2 張（共 4 張）：`make_workflow.py <角色> <階級> <種子> <out.json>` → ComfyUI MCP `run_workflow(wait=False)` → `job(action="wait")`。
    3. `python tools/card_art/candidates.py <角色> --out <暫存資料夾>` 做對照表（取最新 4 張，標 1～4），用 SendUserFile 傳給使用者，順便指出明顯的問題（多出的腳、翅膀、髮色錯誤等）。
    4. 使用者回覆例如「343」＝各階級依序選第 3、4、3 張 → 把 ComfyUI 輸出的那張複製成 `images/Original/Art/<角色>_<階級>.png` → `build_cards.py <角色>` → 跑測試 → commit + push（不用先問）。
  - **使用者偏好與踩過的坑**：明亮、淡陰影、全身、貼近角色個性；字不能太粗（會糊）；**構圖不一定要正面**（側身、回頭、看遠方都可以，不要每張都 `looking at viewer`）。**仰角可以用、些微裙底可以接受，但絕對不能露點**（2026-10-29 使用者修正；NEGATIVE 排除 nsfw / nude / nipples 等）。**要有角色個性，不要只有微笑**：從萌娘百科的「萌點」「性格」挑幾個元素放進表情、動作、道具（例如幻月：天然呆歪頭、姊姊的得意、鬼畜狂笑），三個等級分配不同的面向。魔理沙要加 `standing, holding broom` 負面提示不然會拿著掃帚；魅魔是幽靈尾巴但模型常畫出腳；玄爺照使用者給的官方形象（陸龜、白鬍子白眉、白毛尾巴，不是海龜、不要翅膀）；里香（PC-98 角色、二創造型不統一）用自訂的工程師造型：棕短髮、護目鏡、白襯衫、綠吊帶褲、手套，使用者已接受；兩個角色同框時（玄爺 R 載著靈夢）外觀標籤會互相染色（靈夢變白髮），要在負面提示排除。雙人卡（雪與舞）兩人特徵也會互相染色（雪的黑衣變白、翅膀長錯人、甚至合成一人）；`make_workflow.py` 用 `DUO` / `DUO_GIRLS`（不排除 multiple girls）處理，品質不穩時可改用分層合成（兩人各自生成去背再合成）。使用者不滿意時會給參考圖或說明，照著改 prompt 重生。小瑕疵（例如魔理沙 UR 掃帚柄沒對齊、幻月 SSR 少一隻腳）可以用 PIL 剪貼 + ComfyUI 局部重繪 (VAEEncodeForInpaint，遮罩只蓋問題區域、一次出 4 版讓使用者挑) 修，修好的檔名 `fix_<角色>_<階級>_*.png`。
  - **PhotoCraft 修圖（2026-10-30 筆電已安裝，使用者指定用官方版）**：storytold/photocraft（免費開源、Rust 寫的 Photoshop 類修圖軟體，Apache-2.0），內建 MCP 伺服器 `photocraft-cli mcp`，有圖層、遮罩、調整（曲線、色階…）等幾百個指令（`command_list` 查、`command_run` / `command_batch` 執行；batch 失敗不會回滾，先 `image.duplicate` 在副本上改）。
    - 安裝：GitHub Releases 下載 `photocraft-<版本>-windows-x64.msi`（對 `SHA256SUMS.txt` 驗證）→ 預設裝在 `%LOCALAPPDATA%\Programs\ArtCraft\PhotoCraft\`，CLI 是同資料夾的 `photocraft-cli.exe`（不在 PATH）。
    - 登記：這台沒有 `claude` 指令，改用專案根目錄的 `.mcp.json`（含本機路徑，已加入 `.gitignore`，**每台電腦自己建**）：command = CLI 的完整路徑，args = `mcp --automation-read-root <專案>\images\Original --automation-write-root %USERPROFILE%\Documents\photocraft_out`。只能讀步驟圖資料夾、只能寫到獨立的輸出資料夾，修好的圖由 Claude 複製回步驟資料夾再重跑後續步驟。加好後要開新對話（第一次會詢問是否允許專案的 MCP 伺服器）。
    - **對話開始後才加的 MCP 不會載入成工具**：用 `tools/card_art/layered/photocraft.py` 的 `PC` 類別直接跟 `photocraft-cli mcp` 走 stdio JSON-RPC，效果一樣（讀 `.mcp.json` 的設定與權限）。範例：`pc_shinki_LR_tips.py`（神綺 LR 羽尖壓暗，產出步驟 `10c_char_photocraft.png`，疊層優先用 10c）。好用的指令：`select.colorRange`（**滴管 points 沒生效、會退回前景黑色，要直接給 color / colors 色碼**）、`select.lasso` (mode subtract)、`select.loadSelection` (channel transparency, operation intersect，保護外側半透明光暈)、`select.modify.feather`、`image.adjustments.curves` / `hueSaturation`；預覽選取範圍用 `image.adjustments.invert` + `render_preview`（低飽和顏色用色相偏移看不出來）。`doc_export` 會保留 alpha。
    - 分工：局部手修（接縫、調亮調暗、調色、光暈）用 PhotoCraft；AI 補畫（翅膀、腳）還是用 ComfyUI；整批、要重複的（去背、放大、疊層、打光、動畫）用程式。
  - **ComfyUI 環境（筆電與桌機都已安裝）**：
    - **桌機（2026-10-28 安裝，RTX 3060 Ti 8GB）**：新版 comfy-cli（1.23）會在 `ComfyUI\.venv` 自建虛擬環境並把 PyTorch（cu130）裝在那裡，`~/Documents/comfy/venv` 只有 comfy-cli。啟動要用 `& '~\Documents\comfy\ComfyUI\.venv\Scripts\python.exe' '~\Documents\comfy\ComfyUI\main.py' --listen 127.0.0.1 --port 8188`。
    - 桌機的 comfy MCP 尚未設定（改 `~/.claude.json` 被自動權限擋下）；改用 REST API 也能生圖：把 `make_workflow.py` 的輸出包成 `{"prompt": 工作流程}` POST 到 `http://127.0.0.1:8188/prompt`，用 `GET /queue` 等佇列清空。
    - 桌機的 Ollama（gemma4:26b）與 Wallpaper Engine 會佔顯示記憶體，SDXL 只能動態搬權重，一個工作要 3～4 分鐘；大量生圖前請使用者先 `ollama stop gemma4:26b`（不要自己關使用者的程式）。
    - 以下是筆電的安裝方式：
    - 獨立虛擬環境 `~/Documents/comfy/venv`（Python 3.11、PyTorch CUDA 版），裡面 `pip install comfy-cli`，`comfy --workspace ~/Documents/comfy/ComfyUI install` 安裝 ComfyUI（筆電是 v0.43.0，含 ComfyUI-Manager）。
    - 模型：`models/checkpoints/animagine-xl-4.0-opt.safetensors`（約 6.9GB，Hugging Face cagliostrolab/animagine-xl-4.0）；放大模型 `models/upscale_models/4x-UltraSharp.pth`（約 67MB，Hugging Face Kim2091/UltraSharp，只有重新放大卡框時需要）。
    - 啟動：`& '<venv>\Scripts\python.exe' '<ComfyUI>\main.py' --listen 127.0.0.1 --port 8188`（用終端機分頁跑，約 1～3 分鐘）。
    - Claude 的 MCP：全域 Python `pip install comfy-mcp`，在 `~/.claude.json` 的 `mcpServers` 加 `comfyui`：command = 全域的 `comfy-mcp.exe`，env `COMFY_BIN` = venv 裡的 `comfy.exe`（`claude mcp add` 指令在這台不能用，直接改 json，改之前先備份）。
    - ComfyUI 輸出在 `~/Documents/comfy/ComfyUI/output/touhou_card/`（`candidates.py` 預設讀這裡，路徑不同時設環境變數 `COMFY_OUTPUT`）。
    - 筆電 RTX 4060 Laptop 8GB：896×1064 一次 2 張約 40 秒；8 個工作一次排進佇列沒問題。

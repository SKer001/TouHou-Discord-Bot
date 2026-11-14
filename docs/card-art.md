# 🎨 卡面製作 (ComfyUI、分層合成、PhotoCraft)

> 從 `CLAUDE.md` 拆出來的細節文件 (2026-11-11)。要做這方面的工作時才讀；改了內容記得一起更新。

## 🧭 使用者的工作習慣 (兩台電腦的 Claude 都照這個做，2026-11-12 整理)
- **外觀先查萌娘百科**：不確定的角色外觀、翅膀、符卡一律先查，不要憑印象 (芙蘭的水晶顏色就曾寫錯)。curl / `action=raw` / api.php 會 403，要用內建瀏覽器打開 `https://zh.moegirl.org.cn/<簡體頁名>`，等幾秒再用 javascript_tool 讀 `document.body.innerText` 搜關鍵字。
- **候選**：每個階級 2 張背景 (B1 B2，種子 1101 2202) + 4 張人物 (C1~C4，種子 3303 4404 5505 6606)，做成對照表 (上排 B、下面 C) 用 SendUserFile 傳。附各張的優缺點和推薦。使用者回覆格式「SR:B1C2 UR:B2C3」。
- **生圖絕對不能露點**；髮色、服裝、是否畫成別的角色都要檢查。
- **人物被切到** (翅膀、腳) ➔ `outpaint_workflow(pads=...)` 往那邊擴圖 (一次 2 張給使用者挑) ➔ `wf-up` 重繪高清。**使用者想自己修** ➔ 把 `10_char.png` 傳給他，傳回來存成 `10c_char_photocraft.png`。
- **UR / LR**：彈幕密度使用者偏好少一點 (UR 0.7～0.75、LR 0.7)；背景偏暗、跟彈幕顏色拉開 (紅彈幕配暗紫黑背景)；人物背光 + **眼睛發光** (`light.eyes` 用 10_char 座標量，`eye` 1.3、`eye_size` 3)。局部發光 (水晶、武器) 先做給使用者看，他不喜歡就拿掉 (蕾米莉亞神槍發光偏粉紅，選回原版)。
- **合成完傳整張卡 (15_card 縮圖) 給使用者看；他問特效再傳 16_card.gif**。
- **定案才推**：使用者說「定案推送」才 `build_cards.py <角色>` ➔ 更新 `Utils/version.py` (+1)、`CHANGELOG.md`、`TODO.md` 第 1 節、本文件 ➔ `python tests/run_all.py` ➔ `git pull --rebase` ➔ commit + push。試作圖不推。
- **筆電 (16GB RAM) 生圖時不要同時去背 / 合成**：ComfyUI 生圖約佔 4GB、去背 (BiRefNet CPU) 再吃好幾 GB，2026-11-12 兩次同時跑都讓 ComfyUI 直接崩潰 (Fatal Python error: Aborted)。先讓佇列跑完或暫停，再合成；桌機 16GB VRAM / 記憶體較多沒遇到。
- **改了 `light` (眼睛、emissive) 要先跑 `hd_card.py light <角色> <階級>`**，再 `compose`；只跑 compose 會沿用舊的 10b_char_lit。紅色小物 (領結) 會被翅膀紋路偵測當成紋路發光 ➔ 沒有翅膀的角色設 `glow_red: 0`。
- **背景道具要跟人物互動時 (倚著樹、坐在椅子上)**：人物層白底去背會把樹、地面一起切掉 ➔ 把樹畫在背景，人物照常去背、用 `char_scale` / `offset` 放到樹根；或像咲夜 / 蕾米莉亞的椅子一樣讓道具留在人物層 (去背模型通常會保留緊貼人物的家具)。
- **兩台分工**：一台負責一位角色的整套流程；每個階段 (候選完成、使用者選圖、合成完、推送) 都用 SendMessage 跟另一台互報一則短訊。

## 🖼️ 角色名片 (0.33.000，2026-11-14 使用者決定)
- 推角稱號 (收藏冊集齊某位角色每個階級的完美卡) 第一次解鎖時，玩家永久拿到那位角色的名片，戴上後顯示在 `/profile` 資料卡最上面 (`ui.MediaGallery`)。
- 規格：**19:9 左右的橫幅、影畫風** (像動畫的一幕)；高解析**原圖另外存，不放進 repo** (repo 是公開的；使用者 2026-11-14 決定 repo 維持公開，原圖放只有機器人看得到的私人 Discord 頻道)。
- **原圖上傳 (定案後跑一次就好)**：`python tools/card_art/upload_namecard.py <原圖路徑> <角色id>` ➔ 先做顯示用壓縮版 (同 build_namecards.py)，再用 REST 把 `<角色id>_full.jpg` (原尺寸 quality 95) + `<角色id>.png` (超過 9.5MB 改無損 WebP，再大就只傳 JPG) 傳到 `.env` 的 `NAMECARD_CHANNEL_ID`，訊息 id 記進 `images/NamecardOriginals.json` (要 commit)。機器人執行中也能跑 (只用 REST)。玩家在 `/profile` 按「📥 下載名片原圖」= 私訊戴著那張的高畫質 JPG；管理員 `/admin-user namecard action:📥 原檔` = 私訊 PNG 給自己 (`Utils/namecards.fetch_original_file`)。
- 顯示用的壓縮版：`python tools/card_art/build_namecards.py <原圖路徑> <角色id>` ➔ 縮成寬 1920 的 JPG (quality 88，保持比例；比例跟 19:9 差超過 8% 會提醒) 存到 `images/Namecards/<角色id>.jpg`，並把 raw.githubusercontent.com 網址 + `?v=<檔案雜湊>` 寫進 `images/Namecards.json` (跟 Thumbnails.json 一樣，push 後 Discord 才抓得到；repo 改成不公開的話 raw 連結會失效，要換放圖的方式)。
- 程式端：`Utils/namecards.namecard_url(角色id)`，沒檔案 / 沒那位角色就回 None，資料卡就不放圖 (名片照樣能戴，選單會寫「名片圖還在製作中」)。
- 已完成：靈夢「夏日午睡」(0.33.001)、魔理沙「深夜的魔法研究」(0.33.004)、魅魔「月夜屋頂的惡靈」(0.33.009)、玄爺「池邊的日光浴」(0.33.010)、里香「黃昏的花田」(0.34.002)、千百合「窗邊的星河」(0.34.003)、夢美「黎明前的證明」(0.34.004)。
- **定案流程 (2026-11-14 使用者決定)**：使用者挑好 ➔ 直接 `python tools/card_art/upload_namecard.py <原圖> <角色id>` (做顯示用 JPG + 原圖傳私人頻道，**不用再問**) ➔ 在 `Database/namecard_data.py` 加那張名片的 `name` / `desc` (**每張名片都要有說明**，使用者要求) ➔ commit + push `images/Namecards/`、`Namecards.json`、`NamecardOriginals.json`、`namecard_data.py`。
- **幻想鄉睡顏圖鑑 (2026-11-14 使用者決定)**：24 位名片**全部畫睡著的樣子**。每張從角色個性長出三個不同點：睡在哪、怎麼睡、一個看得出睡前在幹嘛的小細節；時間 / 光線要分散。使用者已審過的設定表：

  | 角色 | 睡在哪 / 怎麼睡 | 小故事 | 時間・光線 |
  |---|---|---|---|
  | 靈夢 | 神社榻榻米側躺抱枕 | 吃到一半的西瓜 | 夏日午後 (✅ 0.33.001) |
  | 魔理沙 | 被魔法書淹沒、臉埋在書裡 | 實驗鍋還在冒煙 | 深夜燭光 (✅ 0.33.004 打哈欠硬撐版，使用者決定保留不重做) |
  | 魅魔 | 飄在神社屋頂抱著新月杖、帽子滑下來蓋住臉 | 本來在看星星 | 月夜 (✅ 0.33.009：仰躺屋頂、旁邊放發光新月杖) |
  | 玄爺 | 池邊石頭上縮進龜殼曬太陽 | 背上停一隻小鳥 | 午後暖陽 (✅ 0.33.010：照使用者參考圖，池邊草地打盹、殼頂麻雀) |
  | 里香 | ~~窩在戰車駕駛座~~ ➔ 側趴在花田裡縮成一團 | (不放戰車，使用者決定) | 黃昏 (✅ 0.34.002) |
  | 千百合 | ~~趴在控制台~~ ➔ 大窗戶前內八坐著睡 (長裙蓋腿，不要控制台) | 窗外銀河 | 宇宙星光 (✅ 0.34.003) |
  | 夢美 | 熬夜後仰躺椅子、臉上蓋論文 | 黑板寫滿算式、咖啡涼了 | 清晨窗光 (✅ 0.34.004：黑板前仰躺，遠景) |
  | 艾莉 | 躺在花田草地上 | 大鐮刀插在旁邊遮陽 | 午後花田 |
  | 幻月 | 夢世界雲朵上大字形睡、翅膀攤開 | 流口水 | 正午藍天 |
  | 夢月 | 洋館沙發上睡著 | 手裡還拿著雞毛撢子 | 黃昏粉紫天空 |
  | 愛麗絲 | 魔界大床的布偶堆裡 | 抱著魔導書 | 夜燈暖光 |
  | 露易絲 | 坐在行李箱上靠著樹睡 | 地圖滑落、相機和紀念品 | 清晨薄霧 |
  | 神綺 | 王座上托腮睡著 | 一疊公文、身上蓋著夢子給的毯子 | 魔界紅紫光 |
  | 雪與舞 | 背靠背睡 | 一邊冒熱氣、一邊結霜 | 雪夜 (兩人，可能要分開生再合成) |
  | 夢子 | 神綺寢室門外的椅子上守夜睡著 | 膝上縫到一半的神綺衣服 | 燭光 |
  | 琪露諾 | 熱到融化趴在大冰塊上 | 青蛙在旁邊看 | 盛夏正午 |
  | 大妖精 | 霧之湖邊樹根窩、大葉子當被子 | 琪露諾留下的半融冰雕 | 夜晚螢火蟲 |
  | 芙蘭 | 地下室抱著破布偶 | 玩壞的玩具 | 紅色燭光 |
  | 小惡魔 | 書架間抱著一疊書坐著睡 | 頭上的翅膀垂下來 | 圖書館微光 |
  | 美鈴 | 站在門口睡著 | 帽子插著咲夜的飛刀 (搞笑、不見血) | 清晨 |
  | 帕秋莉 | 大圖書館拿書當枕頭 | 小惡魔幫她蓋毯子 | 檯燈光 (兩人) |
  | 蕾米莉亞 | 白天厚窗簾後抱抱枕、翅膀縮成一團 | 窗簾縫一道陽光 | 白天逆光 |
  | 露米婭 | 月夜樹枝上張開雙臂睡、包著黑暗球 | 「是這樣嗎～」的姿勢 | 月夜 |
  | 咲夜 | 坐著趴桌、手拿懷錶 | 時間停止中偷睡、紅茶熱氣停在空中 | 午後茶時間 |

- **名片畫風 (2026-11-14 使用者決定)**：畫「角色平常看不到的另一面」的反差日常，主題固定是睡顏 (見上表)，**不是**戰鬥影畫風；可愛 / 慵懶，**不要性感或擦邊** (衣服完整蓋住，負面提示詞擋 nsfw, cleavage, underwear, panties, suggestive, upskirt, thighs, bare legs, midriff…)。
- **名片生圖 (桌機)**：Animagine XL 4.0 整張一次生 1536×728 ➔ 4x-UltraSharp 放大再縮 2304×1092、denoise 0.4 重繪 ➔ 4x-UltraSharp 放大到 3840×1820。正面加 painterly, soft shading, warm colors, dappled sunlight。RTX 5060 Ti 一張約 1 分鐘，一次出 4 張候選給使用者挑。原圖存 `images/Original/Namecards/<角色>/` (gitignore)。小道具 (蝴蝶結掉在旁邊、團扇、賽錢箱) 一次生常常畫不出來。**補道具**：直接局部重繪 (高 denoise) 只會畫出很小的東西 ➔ 先在原圖上手畫草稿 (形狀 + 顏色 + 光暈)，遮罩內 img2img denoise 0.5～0.65 給使用者挑 (2026-11-14 魅魔新月杖，腳本範例 `SetLatentNoiseMask` + 裁切區 1920×1000 縮到 1536×800 重繪再 4x-UltraSharp 放回)。
- **道具不用硬塞 (2026-11-14 里香，使用者)**：「不一定要戰車元素，名片本來就是跟角色平常的 vibe 不同」— 設定表的道具只是參考，模型畫不好 (里香的戰車畫成箱子) 就拿掉，以睡顏反差感為主。
- **角色畫不像 (2026-11-14 玄爺)**：模型不認得的角色 (玄爺這種 PC-98 冷門角色) 純文字生出來會走樣 ➔ 請使用者給參考圖，去背後 (必要時手改表情、加道具草稿) 貼進候選場景當草稿，整張 img2img denoise 0.45～0.6。denoise 越低越像參考圖；0.55 以上會開始亂改 (鬍子被畫成另一隻小動物)。參考圖只放本機 (gitignore)。細節想再提升：分塊重繪 (Ultimate SD Upscale 節點) 或換模型，都要先問使用者。

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
- **芙蘭朵露 (2026-11-11)**：角色名一出現模型就畫翅膀，負面權重加重只會讓圖壞掉 ➔ 也是人物直接帶翅膀 (`inline_wings_tags` 自訂翅膀提示)。翅膀造型、水晶顏色要照原作 (查萌娘百科：由內到外天藍、藍、紫、粉、橙、黃、淺綠、天藍，沒有紅色)；翅膀末端長出羽毛時用手畫遮罩 inpaint 重畫，再 `wf-up` 走重繪 → 高清。
- **蕾米莉亞 (2026-11-11)**：人物直接帶蝙蝠翅膀；彈幕風格 `scarlet` (全部紅色系)，UR / LR 背景要偏暗紫黑，紅彈幕才跳得出來。翅膀被切到用 `outpaint_workflow(pads=...)` 往那一邊擴圖，再 `wf-up` 走重繪 → 高清。使用者想自己手修時：把 `10_char.png` 傳給使用者 (透明 PNG)，修完傳回來 (會是 WebP、尺寸與透明度保留) 存成 `10c_char_photocraft.png`，疊層優先用它。
- **帕秋莉 (2026-11-12，桌機)**：UR 彈幕風格 `elements` (七曜色大玉環 + 七色螺旋 + 七個元素魔法陣)。環繞的水晶 (賢者之石) 各自發光：先自動抓飽和大色塊、排除身體多邊形、每顆用凸包填滿，給使用者看預覽；使用者在預覽上用紅筆圈要補的地方 (同尺寸)，跟原預覽相減就能抓出圈的範圍。依每顆的平均色相分組存成 `10m_crystal_<組>.png`，`light.emissive` 加 `keep_color: True` (從原圖顏色提亮，不然被背光壓暗後會變灰白)。坐姿人物很難跟背景搭，使用者偏好浮空 / 站姿。
- **紅美鈴 (2026-11-12，桌機)**：N～SR 這類日常場景，使用者偏好人物小一點、融入背景 (R 0.49、SR 0.56)。縮小但腳要留在原位：`make_char` 是置中 + offset，腳底 y = H/2 + h/2 + dy·H，所以 dy_new = dy_old + (h_old − h_new) / 2H (h 用 09 去背圖的裁切高度 × 放進畫窗的倍率 × char_scale 算)。「往右 1/10」= offset dx + 0.1。
- **使用者想自己動圖層 (2026-11-12)**：`python tools/card_art/layered/pc_layers.py <分類> <角色> <階級>` ➔ `Documents/photocraft_out/<角色>_<階級>/<角色>_<階級>.pcraft` (背景 / 人物 / 卡框與文字三層，卡框只是對照，合成時會重畫)，用 `photocraft.exe` 打開給使用者改；改完 `pc_apply.py <分類> <角色> <階級>` 再 `hd_card.py compose`。桌機 PhotoCraft 裝在 `C:\Program Files\ArtCraft\PhotoCraft\`。
- **去背切掉發光特效 (2026-11-12 夢子 SSR 劍焰)**：從 06 基本圖抓那個顏色做遮罩 (例如青藍：飽和度高、B/G > R)，存成步驟資料夾的 PNG、LAYERS 寫 `wing_mask`，遮罩範圍內保留原圖；地面陰影常是同色系，要排除。
- **露米婭 / 小惡魔 (2026-11-12，桌機)**：去背 (BiRefNet) 只留人物，人物身邊的氣焰、黑暗會一起被去掉 ➔ 氛圍要靠背景表現。氣焰被畫面切到時補邊照樣可用 (四邊都補：縮到 680×820、pads (128, 154, 128, 154))。小惡魔沒有官方立繪，頭翼 + 背翼直接寫在 base 提示即可，不用 inline_wings。
- **咲夜 UR (2026-11-12，桌機接手)**：一個角色可以兩台分著做 (筆電 SR / SSR、桌機 UR)。同樣的種子換 GPU 生出來的圖會略有不同，要跟使用者說。`build_cards.py <角色>` 只會建出本機有原圖的階級，所以各推各的階級，Thumbnails.json 不會互相覆蓋。異色眼 (一紅一藍) 是咲夜常見的問題，挑圖時要檢查。
- **背景只露出中間**：背景是整張卡大小 (1748×2432)，畫窗只露出 1329×1596，看起來像放大；使用者確認維持這樣。
- **局部發光**：眼睛 `light.eyes` (10_char 座標) + `eye` 強度 / `eye_size`；彩色小物件 (芙蘭的水晶) 用 `crystal_mask.py <階段資料夾> <身體多邊形>` 依色相抓出、存成 `10m_crystal_<組>.png`，在 `light.emissive` 每組用自己的顏色發光 (黃色系要用身體多邊形排除頭髮、領巾)。
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
    - **桌機（2026-10-28 安裝；2026-11-12 顯示卡換成 RTX 5060 Ti 16GB）**：新版 comfy-cli（1.23）會在 `ComfyUI\.venv` 自建虛擬環境並把 PyTorch（cu130）裝在那裡，`~/Documents/comfy/venv` 只有 comfy-cli。啟動要用 `& '~\Documents\comfy\ComfyUI\.venv\Scripts\python.exe' '~\Documents\comfy\ComfyUI\main.py' --listen 127.0.0.1 --port 8188`。
    - 桌機的 comfy MCP 尚未設定（改 `~/.claude.json` 被自動權限擋下）；改用 REST API 也能生圖：把 `make_workflow.py` 的輸出包成 `{"prompt": 工作流程}` POST 到 `http://127.0.0.1:8188/prompt`，用 `GET /queue` 等佇列清空。
    - 桌機的 Ollama（gemma4:26b）與 Wallpaper Engine 會佔顯示記憶體，SDXL 只能動態搬權重，一個工作要 3～4 分鐘；大量生圖前請使用者先 `ollama stop gemma4:26b`（不要自己關使用者的程式）。
    - 以下是筆電的安裝方式：
    - 獨立虛擬環境 `~/Documents/comfy/venv`（Python 3.11、PyTorch CUDA 版），裡面 `pip install comfy-cli`，`comfy --workspace ~/Documents/comfy/ComfyUI install` 安裝 ComfyUI（筆電是 v0.43.0，含 ComfyUI-Manager）。
    - 模型：`models/checkpoints/animagine-xl-4.0-opt.safetensors`（約 6.9GB，Hugging Face cagliostrolab/animagine-xl-4.0）；放大模型 `models/upscale_models/4x-UltraSharp.pth`（約 67MB，Hugging Face Kim2091/UltraSharp，只有重新放大卡框時需要）。
    - 啟動：`& '<venv>\Scripts\python.exe' '<ComfyUI>\main.py' --listen 127.0.0.1 --port 8188`（用終端機分頁跑，約 1～3 分鐘）。
    - Claude 的 MCP：全域 Python `pip install comfy-mcp`，在 `~/.claude.json` 的 `mcpServers` 加 `comfyui`：command = 全域的 `comfy-mcp.exe`，env `COMFY_BIN` = venv 裡的 `comfy.exe`（`claude mcp add` 指令在這台不能用，直接改 json，改之前先備份）。
    - ComfyUI 輸出在 `~/Documents/comfy/ComfyUI/output/touhou_card/`（`candidates.py` 預設讀這裡，路徑不同時設環境變數 `COMFY_OUTPUT`）。
    - 筆電 RTX 4060 Laptop 8GB：896×1064 一次 2 張約 40 秒；8 個工作一次排進佇列沒問題。hd_card 第一段 28 步約 1.25 it/s。
    - 桌機 RTX 5060 Ti 16GB (2026-11-12)：hd_card 第一段 2.49 it/s、重繪段 1.06 it/s，一個工作含載入約 100 秒 (約筆電 2 倍)。桌機跑 hd_card 要設環境變數 `COMFY_PYTHON` = `ComfyUI\.venv\Scripts\python.exe`、`COMFY_OUTPUT` = `ComfyUI\output`；去背 (rembg 2.0.86 + onnxruntime 1.31.1) 裝在 `ComfyUI\.venv`，全域 Python 3.14 另外裝了 scipy (relight.py 要用)。
    - **兩台分工** (2026-11-12 使用者要求)：一台做一位角色的整套流程 (候選 → 挑圖 → 合成 → 定案推送)，兩邊各自把對照表傳給使用者挑；兩台都會在 `hd_card.py` 的 `LAYERS` 最後加角色、在 `danmaku.py` 加風格，push 前先 `git pull --rebase`，版本號接著最新的編。

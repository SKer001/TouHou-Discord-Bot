# TouHou-Discord-Bot — 專案交接文件（給 Claude Code）

> 這份文件整理了先前對話中對本專案的所有理解與決策。放在專案根目錄命名為 `CLAUDE.md`，Claude Code 啟動時會自動載入。
> 專案在**筆電與桌機兩台電腦**上各有一份 clone，靠 GitHub 同步；對話紀錄與 Claude 記憶不會跨電腦，**重要的背景與決策都要寫進這份文件**。
> 使用者慣用**繁體中文**溝通；回覆請簡潔、用繁體中文，不要貼一堆網址。
> **程式架構與寫法規則（Cog 怎麼分、畫面 / 資料層怎麼寫、新增功能檢查清單）在 `ARCHITECTURE.md`，新增功能前先讀。**

## 1. 專案概觀
- 繁體中文的「東方 Project」主題 Discord 機器人，使用 `discord.py`（**需要 >= 2.6**，因為用了 Components V2；目前用 2.7.1）、`aiosqlite`、`python-dotenv`、`Pillow`。Python 3.11。
- 功能：抽卡（gacha）、卡冊、卡牌合成 / 融合、道具背包、角色圖鑑、個人資料卡 + 每日簽到 + 運勢、管理員指令、日誌。
- Repo 是**公開**的（GitHub：SKer001/TouHou-Discord-Bot），分支 `main`。圖片以 `raw.githubusercontent.com` 連結提供，剛 push 的圖片可能要等一下 GitHub 才抓得到（曾出現「載入圖片失敗」，實為 GitHub 延遲）。

## 2. 專案結構（目前狀態）
```
Main.py                      入口；setup_hook 先 init_db() 再 init_item_db()，並自動載入 Cogs/load-*/ 下所有 .py
README.md                    給人看的專案說明 (功能、指令、安裝、新增角色)
ARCHITECTURE.md              程式架構與寫法規則 (分層、Cog / View / 資料層慣例、新增功能檢查清單)
requirements.txt             套件清單：pip install -r requirements.txt
tests/                       測試 (python tests/run_all.py)，見第 7 節
tools/botcli.py              指令列測試工具：假裝打指令、點按鈕、選選單；--live 會把畫面真的送到測試頻道，見第 7 節
tools/discord_peek.py        用機器人 Token 讀測試頻道最新訊息，把實機 V2 畫面印成文字，見第 7 節
tools/discord_rest.py        上面兩個工具共用的 Discord REST 小工具 (只用 REST，不連 Gateway)
tools/card_art/              卡面產生工具 (ComfyUI 生圖 → 蓋卡框 → 寫字 → 縮圖)，見第 4 節「卡面」
Characters/                  角色資料，一角色一檔：Main/ (主要主角)、TH01/ ~ TH06/ (各代)；圖鑑與卡池都讀這裡
Database/
  User_DB_Manager.py         玩家資料庫（Users.db）所有存取
  Item_DB_Manager.py         道具資料庫（Item.db）所有存取
  Users.db / Item.db         SQLite 檔（開發階段 Users.db 也刻意推上 git，見第 8 節）
  item.new.json              道具批次匯入用資料
Cogs/
  load-character/  character.py, Components/character_components.py   # 圖鑑
  load-gacha/      gacha.py, Admin-gacha.py, Components/gacha_components.py   # 抽卡 / 卡冊 / 合成 / 融合 / 卡冊管理
  load-general/    profile.py, inventory.py, leaderboard.py, Admin-item.py, Admin-user.py, Components/general_components.py
  load-system/     Admin-sys.py
Utils/components.py          共用的 Components V2 通知工具（send_notice 等）
Utils/character_data.py      Characters/ 載入器：load_categories() / load_characters()，壞檔印警告並略過
Utils/config.py              .env 設定：ADMIN_IDS 與 is_admin(user)
Logger/Logger.py             日誌與錯誤回報（需要 .env 的 LOG_CHANNEL_ID）
images/                      專案根目錄；Thumbnails.json = {"角色id_階級": URL, "角色id": URL, ..., "fill": 預設圖URL}
  Thumbnails/                Discord 用的縮圖 (460×640)：<角色id>_<階級>.png、fill.png
  Original/Art/              沒有加框的角色原圖 <角色id>_<階級>.png (ComfyUI 生成、使用者挑選)
  Original/Thumbnails/       fill.png 原圖、empty_greenscreen.jpg (使用者給的綠幕卡框，736×1024)、empty_greenscreen_hd.png (AI 放大版)、empty.png (去背後的空白卡框)
```
- Main.py 會把 `Cogs/<資料夾>/<檔名>.py` 以 `Cogs.<資料夾>.<檔名>` 載入；Cog 內可用相對匯入如 `from .Components.x import ...`（命名空間套件）。
- **載入器會載入 `Cogs/load-*/` 第一層的每一個 .py**：舊檔殘留會讓載入失敗；不是 Cog 的共用程式放 `Components/` 子資料夾或專案根的 `Utils/`。
- 畫面產生器的資料夾與檔名一律叫 `Components` / `*_components.py`（舊名 `Embeds` / `*_embeds.py` 已全部改掉）。
- `.env` 需要 `DISCORD_TOKEN`、`LOG_CHANNEL_ID`、`ADMIN_IDS`（管理員 ID，逗號分隔；沒設定時所有管理員指令都不能用）。`.env` 不進 git，換電腦要手動複製。`.gitignore` 有 `/.env`、`/Logger/Logs/`、`__pycache__/`、`/.vscode` 等。
- 專案換行符為 **LF**（Windows 上 `core.autocrlf=true`，工作目錄可能是 CRLF，git 內部仍是 LF）。
- Windows 主控台是 cp950，印 emoji 會 `UnicodeEncodeError`：執行 Python 時設 `PYTHONIOENCODING=utf-8`（例如 PowerShell：`$env:PYTHONIOENCODING = 'utf-8'; python Main.py`）。

## 3. 資料庫設計
### Users.db（`User_DB_Manager.py`）
- `connect()`：`aiosqlite`、`row_factory=aiosqlite.Row`、`PRAGMA foreign_keys=ON`。
- 資料表：
  - `users(user_id PK, money DEFAULT 1000, level, exp, last_daily TEXT, fortune_level INTEGER DEFAULT NULL, inventory TEXT DEFAULT '{}', created_at, is_public DEFAULT 1, stamina DEFAULT 240, stamina_updated_at TEXT)`
  - `gacha_pity(user_id, pool, total_draws, since_ur, last_ur_at)`，主鍵 `(user_id, pool)`
  - `gacha_stats(user_id PK → users ON DELETE CASCADE, total_draws, total_fusions)`
  - `gacha_cards(instance_id TEXT PK, user_id → users ON DELETE CASCADE, character_key, name, emoji, rarity, title, completeness REAL, obtained_at)`，索引 `idx_gacha_cards_user`
- 缺欄位用 `USERS_EXTRA_COLUMNS` 自動補。
- 主要函式：`get_or_create_user`、`add_money`、`add_exp`（升級回傳 `leveled_up/old_p/new_p/is_max`）、`get_required_exp_for_level`、`get_total_exp_for_level`、`reset_daily`、`update_daily_time`、`add_item`、`update_user_inventory`、`get_leaderboard_stats(user_ids)`、`update_visibility`。
- 簽到：`get_daily_status(user_id, today)`（唯讀，不替對方建資料）、`claim_daily(user_id, today, fortune_level)`（原子 `UPDATE … WHERE last_daily IS NULL OR last_daily != today`，連點/雙視窗只有一次成功）。
- 抽卡：`get_user_cards(user_id)`（依 rowid 排序）、`get_gacha_stats(user_id)`。
  - **祈願一律用 `draw_gacha(user_id, pool, draw_count, cost, roll_cards)`**：`BEGIN IMMEDIATE` → 查賽錢（不足丟 `InsufficientFunds`，什麼都不寫）→ 讀該卡池保底 → `roll_cards(since_ur)` 擲卡 → 扣款、寫卡、累加 `total_draws`、更新保底，全部同一個交易。
  - `add_gacha_cards(user_id, cards, draw_count=None)`：直接寫卡（管理員發放用 `draw_count=0`）。寫卡共用內部的 `_insert_cards` / `_add_draws`。
  - 保底表 `gacha_pity(user_id, pool, total_draws, since_ur, last_ur_at)`；`get_gacha_pity(user_id)`。
- 體力：`users.stamina`（預設 240）、`users.stamina_updated_at`（UTC ISO）。**不用背景排程**，每次讀取 / 使用 / 回復時才結算：
  - `calc_stamina(stored, updated_at, now)` 純計算：每 6 分鐘 +1，自然回復只到 240（`STAMINA_MAX`），零頭保留；超過 240（道具）時不再自然回復；已滿時時鐘停在現在。回傳 `stamina / max / updated_at / next_in / full_in`。
  - `get_stamina`（唯讀）、`spend_stamina(user_id, n)`（不夠不扣，回傳 `ok=False`）、`add_stamina(user_id, n)`（可超過 240，扣到 0 為止），寫入都用 `BEGIN IMMEDIATE`。
  - 目前沒有任何功能**消耗**體力；回復靠道具：`use_stamina_item(user_id, item_id, restore)` 在同一個交易裡背包 -1、體力 +restore（可超過 240），背包沒有時 `ok=False` 什麼都不改，回傳含 `before` / `left`。
- 背包：`adjust_item(user_id, item_id, delta)`（管理員給予 / 扣除用：扣完小於 0 不寫入回 `ok=False`、剛好 0 移除，回傳 `before/after`）；`add_item(user_id, item_id, amount)` 是原子操作（`BEGIN IMMEDIATE`，同時寫入不會遺失；數量 ≤ 0 時移除鍵）；`clear_all_inventories()` 清空所有玩家背包。
- 合成 / 融合：`transform_cards(user_id, instance_ids, build_new_card, count_fusion=False)`
  - `BEGIN IMMEDIATE` 鎖定 → 讀取素材 → `build_new_card(consumed)` 驗證並產生新卡（條件不符丟 `ValueError`）→ 刪素材 → 寫新卡 → 融合時 `total_fusions + 1`，全部同一個交易。
  - 素材已不屬於玩家、重複 ID、驗證失敗都會回滾並丟 `ValueError`；連點或兩個確認畫面同時按只會成功一次。
- 玩家 `inventory` 欄位是 JSON 字串（`{"道具id": 數量}`），讀取時需處理 str/dict 兩種型別。

### Item.db（`Item_DB_Manager.py`）
- `get_all_items`、`get_item`、`add_item_db`、`update_item_db`、`delete_item_db`、`batch_import_db`、`replace_all_items(items)`、`CATEGORY_NAMES`、`DEFAULT_ITEMS`、`DAILY_REWARD_ITEM`；`init_item_db()` 在 Item.db 缺少時會警告，**資料表空白時會寫入 `DEFAULT_ITEMS`**（所以預設清單要跟實際想要的道具一致）。
- `item_templates(item_id PK, name, emoji, category, description, effect TEXT DEFAULT '{}')`；`effect` 是 JSON（目前支援 `{"stamina": N}`），讀出來是 dict；舊資料表缺 `effect` 會自動補。`update_item_db`（Modal 編輯）不會改動 effect。
- 道具分類：`consumable`（消耗品）、`collectible`（收藏品）、`special`（裝備與特殊）。
- **目前道具（2026-10-28 使用者指定，舊的 demo 道具與所有玩家背包已清空）**：全部是 `consumable` 體力道具。
  | ID | 名稱 | 體力 |
  |---|---|---|
  | `yuyuko_dango` | 🍡 幽夢三色團子 | 120 |
  | `sakuya_scone_tea` | 🫖 咲夜特製司康與紅茶 | 120 |
  | `marisa_mushroom_soup` | 🍄 螢光蘑菇濃湯 | 67 |
  | `reimu_onigiri` | 🍙 陰陽梅干飯糰 | 60（每日簽到贈送 1 個，`DAILY_REWARD_ITEM`） |
  - 目前只有簽到能拿到 🍙；其他三個只能用管理員指令發放。`Database/item.new.json` 是這四個道具的批次匯入範本。
- 動到真實資料前的備份放在 `Database/backups/`（已加入 `.gitignore`，只留在本機）。

- 管理員卡冊操作：`delete_gacha_cards(user_id, ids)`、`clear_gacha_cards(user_id)`、`update_cards_completeness(user_id, ids, value)`，都只動該玩家自己的卡並回傳實際影響張數。

### 角色資料（`Characters/<分類>/<id>.json`）
- 格式：`id`、`name`、`emoji`、`category`（`main_character` 或 `th01`…）、`profile{title, species, ability, description}`、`gacha{enabled, uuid, rarities, titles}`、`base_stats{hp, atk, def}`（目前都是 0）、`special_powers{id: "<id>_SP", name, levels{階級: {id: "<id>_SP_I|II|III", name, type, spent, cooldown, desc}}}`。
- SP 等級名稱 = `Easy・初陣` / `Lunatic・瘋狂` / `Phantasm・幻象` + `・` + SP 名稱；`spent` 是 B 點消耗（B 點系統尚未實作）。`type`、`spent`、`cooldown`、`desc` 目前只用於圖鑑顯示。
- 驗證：檔名必須等於 `id`、`special_powers.levels` 的鍵必須等於 `gacha.rarities`。分類顯示名稱在 `Utils/character_data.py` 的 `CATEGORY_INFO`。
- 舊作角色、大妖精、小惡魔的介紹與 SP 名稱是 Claude 依風格自訂的，使用者尚未確認。

### 卡牌 ID
- 格式 `c_<角色uuid前4碼>_<隨機hex>`。`instance_id` 是**全域主鍵**，隨機段為 **12 碼**；舊的 8 碼 ID 仍有效。合成的新卡沿用素材 ID 的前綴，融合的新卡用卡池中的 uuid。

## 4. Components V2 的做法與限制
- **所有介面與通知一律用 Components V2**，不要再用 `discord.Embed` 或純文字 `content` 回覆。
- 使用 `ui.LayoutView`、`ui.Container(accent_color=…)`、`ui.Section(TextDisplay, accessory=Thumbnail|Button)`、`ui.Separator`、`ui.ActionRow`。
- **單則訊息最多 40 個元件**；V2 訊息不能帶 `content`/`embeds`，且一旦是 V2 之後只能以 V2 編輯。
- 互動回呼寫成 `button.callback = self.xxx` 並在 `build()` 內重組畫面（`clear_items()` 後重新 `add_item`）；多種狀態（例如編輯 / 刪除確認 / 已刪除）放在同一個 View 用 `build(mode=...)` 切換。
- 縮圖規則：依序查 `images/Thumbnails.json` 的 `角色id_階級` → `角色id` → `"fill"`，連 URL 都沒有就只顯示文字。卡牌畫面用該卡的階級（融合預覽用升階後的階級）；圖鑑用檢視者擁有的最高階級，沒有收藏時用最低階級。
- **卡面（`tools/card_art/`）**：
  - 流程：`make_workflow.py <角色> <階級> <種子> <out.json>` 產生 ComfyUI 工作流程（Animagine XL 4.0 Opt、896×1064、一次 2 張）→ 使用者挑圖 → 存成 `images/Original/Art/<角色>_<階級>.png` → `python tools/card_art/build_cards.py [角色…]` 產生 `images/Thumbnails/<角色>_<階級>.png` 並寫入 Thumbnails.json → **push 之後** Discord 才抓得到圖。
  - 合成順序：角色原圖墊底 → 蓋上 `empty.png`（畫窗透明，邊角不會有瑕疵）→ 左上中文稱號（衡山毛筆行書，`吞→呑`、`絕→絶`）、右上等級圖（`tools/card_art/rarity/`，2026-10-29 換成使用者給的新綠幕版 `rarity_greenscreen.jpg`，用 `make_rarity.py` 去背切成 6 張；`card.py` 的 `BADGE_SCALE = 1.25` 放大 1.25 倍）、名牌英文名（Harukaze Solid，可稍微超出名牌）。`empty.png` 由 `make_empty.py` 從綠幕卡框產生（含底部 TouHou / Project 小字）；綠幕原圖只有 736×1024，所以先用 ComfyUI 的 4x-UltraSharp 放大 4 倍再縮成 1748×2432，存成 `empty_greenscreen_hd.png`（2026-10-29，卡框明顯變清楚）。改了卡框或等級圖要重跑 `make_empty.py` / `make_rarity.py` 和 `build_cards.py`（不加參數＝全部角色）。
  - **分階段輸出**（使用者指定）：`build_cards.py --stages` 會在 `card_stages/`（已加入 .gitignore，太大不進 repo）存每一步的圖：`_base/frame.png`、`_base/rarity/*.png`（基礎元素）；`<角色>_<階級>/0_pic.png`（原圖）→ `1_art`（人物）→ `2_frame`（人物＋框）→ `3_text`（＋名字與稱號）→ `4_card`（＋等級，完成）。程式在 `card.render_stages()`。
  - **動態卡 GIF**（使用者 2026-10-29 指定）：`build_cards.py` 對 SSR / UR / LR 另外產生 `images/Thumbnails/<角色>_<階級>.gif`，Thumbnails.json 指向 GIF（程式不用改，Discord 縮圖直接播）。效果在 `animate.py` 的 `RARITY_EFFECTS`：SSR `shine`（白色閃光掃過）、UR `holo`（實體雷射卡那種全息彩虹塗層：以閃光為基礎，彩虹隨角度流動 + 金屬細紋 + 亮片，蓋在整張卡上，畫窗是外框的 `HOLO_WINDOW`=0.75 倍）、LR `holo+sparkle`（再加畫窗內四角星光閃爍）。使用者要的「雷射」是雷射閃卡的全息反光，**不是光束**。2026-10-30 調整：雷射強度 0.85、32 格 × 90ms（約 2.9 秒一輪，比較慢）、所有動態都頭尾銜接、全部格子共用調色盤（不閃爍）；每張約 2～6MB；`--no-gif` 只做靜態圖。單張試作：`python tools/card_art/animate.py <角色> <階級> [效果] <out.gif>`。
  - **分層合成**（神綺 LR）：模型畫不出清楚的大量彈幕（會變成子彈彈殼或糊成一團），所以改成「AI 宇宙背景＋程式畫的彈幕＋AI 單獨生成再去背的人物」：`tools/card_art/layered/cutout.py`（BiRefNet 去背，用 comfy venv 的 python -I 執行）、`compose_lr.py <背景> <人物去背> <輸出> [種子] [人物比例] [傾斜] [風格]`（光球環、螺旋米粒彈、星彈；人物縮小、斜角、背後柔光；風格 `rainbow` = 神綺 LR 彩虹、`freeze` = 琪露諾 UR 冰晶，8 成彈幕凍白 + 六角雪花，背景壓暗、光暈減弱避免過曝）。新角色的大招可以再加風格。人物要用正方形畫布、提示「翅膀完整入鏡」，不然翅膀會被切。之後的 LR / 大招卡可以沿用。
  - **高清分層流程**（使用者 2026-10-30 指定，神綺 LR 試作完成）：`tools/card_art/layered/hd_card.py`（檔頭有完整步驟與指令）。
    - 每一步的產出與修改後的圖都要保留（方便之後微調），放在 `images/Original/<分類>/<角色>/<階級>/`（分類 = `Characters/` 資料夾，例如 TH05）：背景 01 生成 → 02 重繪 → 03 放大 16 倍 → 04 壓暗加彈幕 → 05 壓縮；人物 06 生成 → 07 重繪 → 08 放大 16 倍 → 09 去背 → 10 壓縮；疊層 11 沒有框的完整原圖 → 12 背景 + 卡框 → 13 + 人物 → 14 + 文字 → 15 + 等級 → 16 GIF。`*_hd.png`（每張數十 MB）和重做前的 `_old_*/` 只留在本機。
    - 疊層順序（使用者指定）：背景 > HD 外框 > 去背人物（蓋在卡框上）> 文字與等級 > 特效。背景是整張卡大小（沒有框的原圖也完整），彈幕畫滿整張卡。人物放在畫窗大小的畫布上，`LAYERS` 的 `tilt`（傾斜）、`char_scale`、`offset`（位置微調，超出畫窗切掉）可以調。
    - 去背人物另外存成 `images/Original/Art/<角色>_<階級>_char.png`（使用者：UR / LR 都要留）。
    - **翅膀很大的角色（神綺六翼）模型一定會把翅膀畫出畫面**：直長 / 正方形 / 橫長畫布、加強提示都沒用；直接往外擴圖會長出多餘的翅膀。可行做法：挑一張好的 → 縮小到 60% 放在白色大畫布 → 被切的翅膀用 OpenCV inpaint 往外抹一小段當顏色引導（越遠越淡）→ 只重畫外圍（SetLatentNoiseMask，denoise 0.9，下方腳的部分不重畫，不然會多一隻靴子）→ 接縫一圈再用 denoise 0.4 輕度重繪 → `hd_card.py wf-up` 走重繪 / 高清。神綺 LR 的 06a~06d 就是這幾步。
  - **UR 與 LR 一律用分層合成**（使用者 2026-10-29 指定，從 TH06 開始）：背景 / 彈幕（程式畫）/ 人物（單獨生成、正方形畫布、去背）分開做再合成，見下面「分層合成」。
  - 階級越高畫面越強：SR 日常輕鬆、SSR 施展法術有動態、UR 招牌大招（光效、結界、極限火花）；都維持明亮、淡陰影、全身。prompt 在 `make_workflow.py` 的 `SCENES`，英文名在 `build_cards.py` 的 `EN_NAMES`（新角色兩邊都要加）。
  - 字型：衡山毛筆是 public domain 放在 repo；**`HarukazeSolid.ttf` 是 demo 版限個人使用，已加入 `.gitignore`，換電腦要手動複製到 `tools/card_art/fonts/`**（跟 .env 一樣）。
  - **進度（2026-10-29）**：已完成 靈夢、魔理沙（Main）、魅魔（TH01）、玄爺、里香（TH02）、千百合、夢美（TH03）、艾莉、幻月、夢月（TH04）、愛麗絲（舊作外觀）、露易絲、神綺（LR 為分層合成）、雪與舞、夢子（TH05，舊作全部完成）。TH06：琪露諾（UR 為分層合成 freeze 風格）。**下一位：大妖精 daiyousei（TH06）**，依 `Characters/TH06/` 順序：大妖精 daiyousei → 芙蘭朵露 flandre（SSR/UR/LR）→ 小惡魔 koakuma → 紅美鈴 meiling → 帕秋莉 patchouli → 蕾米莉亞 remilia（SSR/UR/LR）→ 露米婭 rumia → 十六夜咲夜 sakuya。新作角色查萌娘百科一般條目即可。其餘尚未做的角色顯示 fill。
  - **每位角色的做法（使用者指定：一位一位處理）**：
    0. **先上網找參考圖**（使用者 2026-10-29 指定，從夢美開始）：**優先查萌娘百科**（使用者指定，東方資料最詳細，例如 `https://zh.moegirl.org.cn/艾丽(东方Project)`，有外貌、萌點、性格、設定 neta），舊作角色要查「(東方Project舊作)」條目（例如 `愛麗絲(東方Project舊作)`，跟新作同名角色是不同頁）；立繪圖檔可從 Touhou Wiki（en.touhouwiki.net 的 `/wiki/<作品>/Characters` 頁，例如 `Mystic_Square/Characters` 有 TH05 全員頭像、`Embodiment_of_Scarlet_Devil/Characters` 有 TH06 立繪）取得；THBWiki 有 Cloudflare 驗證、Danbooru 內建瀏覽器打不開。確認髮型髮色、服裝、配件、招牌道具，把參考圖與重點特徵給使用者看，再依此寫 prompt。
    1. 在 `make_workflow.py` 加 `BASE`（外觀 Danbooru 標籤）、每個階級的 `SCENES`（依稱號、個性、故事；階級越高越強），需要時加 `EXTRA_NEGATIVE`（可用角色或 `(角色, 階級)` 當鍵）；在 `build_cards.py` 加 `EN_NAMES`。先用一兩句話跟使用者說明各階級的構想。
    2. 每個階級用兩個種子各生 2 張（共 4 張）：`make_workflow.py <角色> <階級> <種子> <out.json>` → ComfyUI MCP `run_workflow(wait=False)` → `job(action="wait")`。
    3. `python tools/card_art/candidates.py <角色> --out <暫存資料夾>` 做對照表（取最新 4 張，標 1～4），用 SendUserFile 傳給使用者，順便指出明顯的問題（多出的腳、翅膀、髮色錯誤等）。
    4. 使用者回覆例如「343」＝各階級依序選第 3、4、3 張 → 把 ComfyUI 輸出的那張複製成 `images/Original/Art/<角色>_<階級>.png` → `build_cards.py <角色>` → 跑測試 → commit + push（不用先問）。
  - **使用者偏好與踩過的坑**：明亮、淡陰影、全身、貼近角色個性；字不能太粗（會糊）；**構圖不一定要正面**（側身、回頭、看遠方都可以，不要每張都 `looking at viewer`）。**仰角可以用、些微裙底可以接受，但絕對不能露點**（2026-10-29 使用者修正；NEGATIVE 排除 nsfw / nude / nipples 等）。**要有角色個性，不要只有微笑**：從萌娘百科的「萌點」「性格」挑幾個元素放進表情、動作、道具（例如幻月：天然呆歪頭、姊姊的得意、鬼畜狂笑），三個等級分配不同的面向。魔理沙要加 `standing, holding broom` 負面提示不然會拿著掃帚；魅魔是幽靈尾巴但模型常畫出腳；玄爺照使用者給的官方形象（陸龜、白鬍子白眉、白毛尾巴，不是海龜、不要翅膀）；里香（PC-98 角色、二創造型不統一）用自訂的工程師造型：棕短髮、護目鏡、白襯衫、綠吊帶褲、手套，使用者已接受；兩個角色同框時（玄爺 R 載著靈夢）外觀標籤會互相染色（靈夢變白髮），要在負面提示排除。雙人卡（雪與舞）兩人特徵也會互相染色（雪的黑衣變白、翅膀長錯人、甚至合成一人）；`make_workflow.py` 用 `DUO` / `DUO_GIRLS`（不排除 multiple girls）處理，品質不穩時可改用分層合成（兩人各自生成去背再合成）。使用者不滿意時會給參考圖或說明，照著改 prompt 重生。小瑕疵（例如魔理沙 UR 掃帚柄沒對齊、幻月 SSR 少一隻腳）可以用 PIL 剪貼 + ComfyUI 局部重繪 (VAEEncodeForInpaint，遮罩只蓋問題區域、一次出 4 版讓使用者挑) 修，修好的檔名 `fix_<角色>_<階級>_*.png`。
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
- **通知工具 `Utils/components.py`**：
  - `send_notice(interaction, text, color=None, footer=None, ephemeral=True)`：自動判斷用 `response` 或 `followup` 送出，預設 ephemeral。
  - `notice_container()` / `notice_view()`：需要自行加按鈕或嵌進其他畫面時使用。
  - 色條依開頭 emoji 自動上色：❌/🚫/🗑️ 紅、⚠️ 橘、✅/🎁/✨/🟢 綠、↩️/✖️/⚙️ 灰，其他 blurple。
- V2 畫面清單：`/card gacha`、`/card inventory`、`/card synthesis`、`/card fusion`、道具背包 `/inventory`（分類 + 分頁 + 跳頁 Modal）、`/character` 圖鑑（分類→角色→檔案頁）、`/profile`（含今日簽到狀態、運勢、簽到按鈕）、`/daily`、`/admin-item edit_item` 編輯控制台、`/admin-sys reload` 重載控制台、`/admin-gacha` 各畫面、Logger 重大事件通知，以及所有錯誤 / 成功提示。
- **autocomplete 最多 25 個選項**：選項可能變多的地方一律「先選代數 (pool) → 再選角色」，選卡改用分頁選單畫面（每頁 20 張），不要直接用 autocomplete 列出卡牌。
- 原本的 `/fortune` 已併入 `/profile`，已不存在。

## 5. 各 Cog 重點
- **gacha.py**（指令群組 `/card`）：
  - **卡池分代數**：`GACHA_POOLS` = `classic`（📜 舊作卡池：Main + TH01～TH05，15 位）、`th06`（🔴 紅魔鄉卡池，9 位），每個卡池列出包含的 `Characters/` 資料夾。`GACHA_POOL = load_gacha_pool()` 在載入模組時從 `Characters/` 讀取 `gacha.enabled` 的角色（每筆含 `pool`），改角色檔後要 `/admin-sys reload` 抽卡模組。`card_pool_key(card)` 取卡牌所屬卡池，角色不在卡池時為 `"other"`。
  - 每個角色有三個階級 `rarities`（例如 `["SR","SSR","UR"]`）與各階級稱號 `titles`。
  - 祈願 `/card gacha pool pull_type`：每抽 `DRAW_COST = 2000` 賽錢；稀有度權重 `RARITY_WEIGHTS = [75, 22, 3]`；完整度 `generate_completeness`（高斯平方，0.001–1.0）；擲卡在 `roll_pool_cards()`，寫入走 `draw_gacha`（單一交易）。結果畫面顯示卡池名稱與保底進度，可繼續單抽/十連（沿用同卡池）/查看卡庫；非本人點按鈕會被 `interaction_check` 擋下。
  - **保底**：每個卡池各自計數，連續 `PITY_THRESHOLD = 100` 抽沒有 UR 以上（`PITY_RESET_RARITIES = {UR, LR}`）時，第 100 抽強制換成卡池中有 UR 的角色的 UR；觸發的卡帶 `"pity": True`（只用於顯示「🎯 保底」）。十連會逐抽計算。
  - **`/card history`**：各卡池累計抽數、保底 `since_ur / 100` 與進度條、上次 UR 時間，加上總祈願與融合次數。
  - **卡冊 `/card inventory`**（`InventoryView`）：疊卡列表（同角色同階級一疊，每頁 `STACKS_PER_PAGE = 7`）→ 單一疊（依完整度高到低，每頁 `STACK_CARDS_PER_PAGE = 8`）→ 單卡詳情；卡池篩選（含「其他」）、階級篩選、排序按鈕循環切換 `INVENTORY_SORTS`（階級 / 完整度 / 最新 / 數量）。
  - **合成 `/card synthesis pool character`**：兩張不同的、同角色、同階級、完整度都未滿 1.0000 的卡 → 一張新卡。
    - `pool` / `character` autocomplete 只列出有可合成組合（`find_synthesis_groups`）的代數與角色；送出後開 `SynthesisPickerView`：步驟 1 選第一張 → 步驟 2 只列可配對的卡（皆可分頁）→ `make_synthesis_view()` 重新讀資料庫後交給 `CardActionConfirmView`。
    - 公式 `calc_synthesis` / `roll_synthesis`：新完整度 = 較高那張 + 增幅；相對差距 `d = |a-b| / 較高那張`。
    - 增幅上限依**較低那張**的位數（`SYNTHESIS_CAPS`）：0.x → 0.2、0.0x → 0.05、0.00x → 0.01、0.000x → 0.005；增幅 = 上限 × (1 − d)，至少 0.0001，新完整度不超過 1.0000。
    - 加倍：機率 = 階級機率 × (1 − d)²（`SYNTHESIS_DOUBLE_CHANCE`：N 99%、R 50%、SR 30%、SSR 15%、UR 10%、LR 5%；完整度一模一樣時 d = 0 即原始機率）；加倍時增幅 ×2，可超過上限。
    - 確認畫面同時顯示一般結果、加倍結果與加倍機率，按「確認合成」才擲骰並消耗卡牌。
  - **融合 `/card fusion pool character rarity`**：三張同角色、同階級、完整度 1.0000 的卡 → 該角色的下一個階級（稱號換成新階級的）；已是最高階不能融合。
    - 三個 autocomplete 都只列出符合條件的（`find_fusion_groups`：持有 3 張以上 1.0000 且還能升階）；系統自動取最早獲得的三張（滿完整度的卡除了 ID 都一樣）。角色 `gacha.enabled` 為 false 時不在 `GACHA_POOL`，也就不能融合。
    - 新卡完整度與祈願相同（`generate_completeness`），`total_fusions + 1`。
  - 合成 / 融合共用 `CardActionConfirmView`（確認 / 取消，結果頁可查看卡庫）；`FUSION_COUNT = 3`、`AUTOCOMPLETE_LIMIT = 25`。
- **profile.py**：簽到運勢 0–5 對應賽錢區間 `MONEY_RANGES`，經驗 100–200；時區用台灣 UTC+8，每日 00:00 重置；`/profile` 可傳 `visibility` 設定公開/私人，私人資料卡他人看不到。簽到成功會多送 `DAILY_REWARD_ITEM`（顯示在獎勵那行）。本人的資料卡底部有「⚡ 恢復體力」按鈕 ➔ `StaminaItemView`：列出背包裡有 `effect.stamina` 的道具 ➔ 選擇後顯示說明與「使用後體力」➔ 「🍽️ 使用 1 個」（連點保護）➔ 可繼續使用或「🔙 返回資料卡」。
- **inventory.py / general_components.py**：背包每頁 10 件，排序為分類順序再依道具 ID；`get_avatar_dominant_color` 用 Pillow 取頭像主色（變數名 `accent_color`）。
- **leaderboard.py**：`/leaderboard category`（賽錢、P點、收集角色、卡牌總數、祈願次數、融合次數），只比較「本伺服器成員（排除 bot）∩ 資料庫有資料的玩家」；私人資料卡的玩家計入名次但顯示「🔒 私人玩家」（本人除外）；前 10 名，自己不在前 10 時另外列出。畫面在 `general_components.build_leaderboard_container`。需要 members intent（`Main.py` 用 `Intents.all()`）。
- **Admin-user.py / Admin-item.py / Admin-sys.py / Admin-gacha.py**：管理員由 `.env` 的 `ADMIN_IDS` 決定（目前 2 位：`403895664666214400`、`414789026189672449`），一律用 `Utils.config.is_admin(interaction.user)` 判斷，其他人回「無權限」。
  - `/admin-user`：`reset_daily`、`add_money`、`add_exp`、`clear_inventory`、`add_stamina`（可為負數）
  - `/admin-item`：`add_item`、`add_items_batch`、`edit_item`（V2 控制台：換分類、Modal 編輯、刪除確認）、`manage [target]`、`give_items`
    - `manage`（取代舊的 `give_item` 與 `/admin-user take_item`）：`ItemManageView` 分類選單（全部 / 各分類 / 🎒 只看對方持有的）+ 每頁 10 個的堆疊列表（顯示對方持有數）→ 選道具 → `ItemAmountModal` 輸入數量：正數給予、負數扣除、0 或非整數擋下；寫入用 `adjust_item`（扣完小於 0 拒絕、剛好 0 移除），完成後重新讀取並在畫面上方顯示結果。
  - `/admin-sys`：`reload`（V2 控制台，重載結果顯示在上方、選單保留可連續重載；注意不會重載 `Components/` 子模組）、`sync`、`shutdown`
  - `/admin-gacha`（`Cogs/load-gacha/Admin-gacha.py`）：`view target`（用 `InventoryView` 檢視對方卡冊）、`give target pool character rarity [amount 1~20] [completeness]`（不算抽卡次數）、`remove target pool character`、`set_completeness target pool character value`、`clear target`（確認畫面）。
    - `remove` / `set_completeness` 共用 `CardPickerView`：每頁 20 張、可多選 → 確認 → 執行後重新讀取並回到列表。
    - 每個指令開頭用 `_deny()` 檢查管理員（不要用 Cog 層級的 `interaction_check`，失敗會被 Logger 當成指令錯誤通報）。
    - 用 `gacha_mod()`（`importlib.import_module`）在呼叫時取得抽卡模組，`/admin-sys reload` 抽卡模組後會拿到新的卡池。
- **character.py**：`/character` 每次執行都用 `load_categories()` 重新讀 `Characters/`（改角色檔不必重開）；角色頁顯示稱號、種族、能力、基礎數值、卡牌階級與稱號、SP 三個等級，色條依最高階級上色。
- **Logger.py**：記錄指令/元件互動到 `Logger/Logs/`，重大事件（開機、斷線、重連、指令錯誤）用 `send_alert_log()` 以 V2 送到 `LOG_CHANNEL_ID`，時間用 Discord 時間戳記 `<t:…:F>`。

## 6. 重構歷程（時間順序）
1. 抽卡結果與卡冊改 V2、縮圖用 `images/Thumbnails.json`（沒有就用 `fill`）。起初誤解成「把 embed 合併」，後來澄清是要 10 張相連的畫面，最終採用 Components V2。
2. 背包 `/inventory` 改 V2 並優化（分類排序、分頁、道具說明）。
3. `images/` 移到專案根目錄，修正所有 `Thumbnails.json` 路徑。
4. `/character` 圖鑑改 V2（`characters.json` 格式為 main_character/characters 結構）。
5. 合併 `/profile`、`/daily`、`/fortune`（保留重複簽到提示）。
6. 資料庫與檔案結構重整（提交 7b1bdf6）：`database.db`、`daily.db`、gacha `users/*.json` 全部併入 `Database/Users.db`；道具資料移到 `Database/Item.db`；gacha `character.json` → `Gacha_Pool.json`。一次性遷移腳本 `migrate_legacy.py` 已執行完畢並刪除，舊檔也已移除。
7. 新增卡牌合成 / 融合（提交 cbf85f1）。
8. 所有通知改用 Components V2、`Embeds` 改名 `Components`、新增 `Utils/components.py`（同一個提交 cbf85f1）。
9. 新增 `Characters/` 一角色一檔（24 位卡池角色），`/character` 圖鑑與抽卡卡池都改讀這裡；卡池分代數（舊作 / 紅魔鄉）。
10. 合成公式改為依位數動態決定上限、加倍改為依階級的機率；SP 改為 I/II/III 等級結構並加入 `spent`（B 點）。
11. 卡冊改成疊卡列表 + 卡池 / 階級篩選 + 排序；新增 `/admin-gacha`；合成、融合、管理員選卡都改成「代數 → 角色 → 分頁選卡」避開 25 個選項上限。新增 `README.md`。
12. 刪除已不再讀取的舊資料 `Cogs/load-gacha/Gacha_Pool.json`、`Cogs/load-character/characters.json`（舊圖鑑的 en_name / debut / location / theme_song / color / spell_cards 只存在 git 歷史中，需要時可從提交 d8fb060 以前取回）。`images/Original/` 是縮圖的高解析度原圖，保留。根目錄 `JSON.json` 是使用者的格式範本，不要動。
13. 管理員 ID 移到 `.env`（`Utils/config.py`）、新增 `requirements.txt`；祈願改為單一交易並加入每卡池 100 抽 UR 保底與 `/card history`；卡冊加上收集進度與合成 / 融合捷徑（只有卡冊主人看得到）；圖鑑顯示自己的收藏；新增體力系統與 `/leaderboard`；測試放進 `tests/`。
14. 新增 `tools/botcli.py`：不連 Discord 就能假裝打指令、點按鈕與選單、送出 Modal 來測試機器人（沙盒資料庫 `.botcli/`）。
15. 新增實機工具：`botcli --live` 把畫面真的送到測試頻道讓 Discord 驗證、`tools/discord_peek.py` 讀頻道看實機結果（測試頻道沿用 log 頻道）。
16. 道具改版：Item.db 加上 `effect` 欄位；刪除全部 83 個舊 demo 道具與所有玩家背包（備份在 `Database/backups/`），換成 4 個體力道具；簽到送 🍙；資料卡新增「⚡ 恢復體力」；`add_item` 改為原子操作；新增第二位管理員。
17. `/admin-item give_item` 與 `/admin-user take_item` 合併成 `/admin-item manage`（分類 + 分頁 + 堆疊列表 → Modal 輸入數量，正數給予、負數扣除，不能扣到小於 0）。
18. 卡面：ComfyUI 生成角色圖、套上綠幕去背的空白卡框、寫稱號 / 名字 / 等級圖（`tools/card_art/`）；縮圖改成依「角色＋階級」顯示。之後一位一位補角色卡面（進度見第 4 節「卡面」）。

## 7. 驗證方式
- 本機已安裝 discord.py 2.7.1 與 aiosqlite，可以直接跑機器人與測試。
- 測試做法：把 `udm.DB_PATH` / `idm.DB_PATH` 指到暫存資料夾（道具資料庫用副本），用真實 discord.py 物件 + 假的 Interaction（response / followup / namespace）呼叫指令的 `callback` 與 autocomplete，並斷言回覆都是 `LayoutView`（沒有 content / embed）。**測試絕不碰真實的 Users.db / Item.db**（前後比對 sha256）。
- **測試在 repo 的 `tests/`**：`python tests/run_all.py` 會逐一以子行程執行 `tests/test_*.py`、彙整結果，並在前後比對 `Database/*.db` 的 sha256（機器人同時在跑時可能誤報，跑測試前先關掉機器人）。
  - 🖥️ **給桌機端的 Claude**：pull 之後先跑一次 `python tests/run_all.py` 確認環境正常；改完功能要跑、也要在對應的 `tests/test_*.py` 補測試。新增測試檔沿用現有檔案的寫法（開頭把 `udm.DB_PATH` 指到 `tempfile.mkdtemp()`、最後印出 `passed N, failed M`），`run_all.py` 會自動找到它。
- **用 `tools/botcli.py` 實際操作機器人（改完功能後優先用它檢查畫面與流程）**：
  - 載入全部 Cog（不登入 Discord、不載入 Logger），用假的 Interaction 執行斜線指令，把 V2 畫面印成文字（按鈕編號 `b1`、選單編號 `s1`、元件數 / 40）。
  - 資料庫一律用沙盒 `.botcli/`（第一次從 `Database/` **唯讀**複製，已加進 `.gitignore`），資料會保留到下次；`--reset` 重新複製、`--fresh` 從空白開始、`--sandbox 路徑` 指定資料夾。
  - 畫面只存在於同一次執行中：指令和之後的點擊要寫在同一次執行的步驟裡，例如：
    `python tools/botcli.py "/card gacha pool:th06 pull_type:10" "click 繼續十連" "/card inventory" "select 卡池 th06"`
  - 步驟：`/指令 參數:值`（成員參數用 `me`、`@名稱` 或 ID；`@名稱` 會產生固定的假玩家）、`? /指令 參數 [已填:值] [current:文字]`（看 autocomplete）、`click b2|按鈕文字`、`select s1|選單文字 值…`、`modal 標籤:值`、`as me|@名稱`、`msg 編號`、`show`、`users`、`sql SELECT…`、`commands`、`help`。
  - 會自動抓的問題：回覆帶 content / embed、同一互動回應兩次、指令或元件沒有回應、元件超過 40 個、autocomplete 超過 25 個或選項超過 100 字、Discord 會擋下的參數（choices、Range）、程式例外（印出 traceback）。有任何錯誤時結束碼為 1。
  - 在 Git Bash 執行時 `/card` 可能被改寫成路徑，CLI 會自動還原；也可以省略開頭的 `/`（`card gacha …`）。
  - `tree.sync` 會被略過；頭像不會下載（主色退回預設紅色）。
  - 步驟還有 `wait 秒數`、`say 文字`（示範用）。
- **實機（真的 Discord）**：測試頻道 = `.env` 的 `TEST_CHANNEL_ID`，沒設定時用 `LOG_CHANNEL_ID`（目前就是 log 頻道 `#touhou-logs`）。兩個工具都只用機器人自己的 Token 走 REST，機器人正在跑也能用，完全在 Discord 規範內。**不要**用瀏覽器自動操作使用者的 Discord 帳號（self-bot 違反服務條款）。
  - `python tools/botcli.py --live 步驟…`：流程照樣在沙盒模擬，但每一步新增 / 更新的畫面都由機器人真的送到測試頻道（同一則會用編輯更新），讓 **Discord 驗證真實的 V2 內容**；Discord 拒絕時會印出錯誤欄位（例如 `components：Must be 40 or fewer`）並算成錯誤。鏡像訊息的按鈕全部停用、頂端加一行「🧪 botcli 鏡像」說明（元件已滿 40 時不加）。
  - `python tools/discord_peek.py [-n 5] [--bot-only] [--raw]`：讀測試頻道最新訊息（由舊到新），印出作者、時間、是否 V2、是哪位使用者的互動，以及畫面文字與元件數。使用者在 Discord 實機操作後，用它查看真正的結果。ephemeral 訊息 API 讀不到。
- 最近一次：11 個測試檔全數通過（合成融合 54、Admin-gacha 54、卡冊 44、圖鑑 47、V2 通知 32、保底 21、體力 21、道具 41、botcli 17、卡池 14、排行榜 10，共 355 項）。V2 畫面細節仍以 Discord 實機為準。
- 已知待改進：TH06 其餘 8 位角色的卡面、autocomplete 每次都讀整本卡冊、卡牌存了名稱 / 稱號副本、分解卡牌（等浮動市值設計）、交易（等賽錢來源設計）、收集完成獎勵（等經濟系統）。

## 8. 使用者的決定與工作習慣
- **開發階段 `Database/Users.db` 刻意跟著推上 git**（雖然 repo 公開、內含玩家資料）。不要再建議移出追蹤或加入 `.gitignore`。
  - Claude Code 的自動權限檢查可能會擋下「提交 / 推送 Users.db」，此時請使用者自己執行 git 指令，不要繞過。
- 直接推到 `main`（個人專案，不開 PR）。
- 兩台電腦切換：離開前 `commit` + `push`，開始前 `pull`；**機器人同一時間只在一台上執行**（同一個 Token，且 Users.db 是二進位無法合併）。
- **完成並測試通過後直接 commit + push 到 `main`，不用先問**（2026-10-28 使用者指示）。只有重大事件才先問，例如要開分支、改寫 git 歷史、刪除大量資料等。`Database/Users.db`、`Item.db` 有變動時也一起推。

## 9. 給 Claude Code 的工作守則
- 動資料前先備份；遷移類工作**不得刪除或改動舊檔**。
- 修改後保持 LF 換行；沿用既有的程式風格與繁體中文註解/文案（emoji 標題風格）。
- 新增畫面或通知一律用 V2（優先用 `Utils/components.py`），注意 40 個元件上限，縮圖走 `Thumbnails.json`（角色_階級 → 角色 → `fill` 後備）。
- 資料庫寫入涉及多表時用單一交易；日常領獎類操作用原子 `UPDATE … WHERE` 防重複；會消耗東西的操作先給確認畫面。
- 使用者可能繞過 autocomplete 直接輸入值，指令內一定要再驗證一次。
- 新 Cog 檔放進 `Cogs/load-*/`，不要留下舊的同名/過期檔案。
- 不要在回覆中貼大量 URL；完成後簡述結果與下一步即可。

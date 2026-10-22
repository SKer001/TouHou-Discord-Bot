# TouHou-Discord-Bot — 專案交接文件（給 Claude Code）

> 這份文件整理了先前對話中對本專案的所有理解與決策。放在專案根目錄命名為 `CLAUDE.md`，Claude Code 啟動時會自動載入。
> 專案在**筆電與桌機兩台電腦**上各有一份 clone，靠 GitHub 同步；對話紀錄與 Claude 記憶不會跨電腦，**重要的背景與決策都要寫進這份文件**。
> 使用者慣用**繁體中文**溝通；回覆請簡潔、用繁體中文，不要貼一堆網址。

## 1. 專案概觀
- 繁體中文的「東方 Project」主題 Discord 機器人，使用 `discord.py`（**需要 >= 2.6**，因為用了 Components V2；目前用 2.7.1）、`aiosqlite`、`python-dotenv`、`Pillow`。Python 3.11。
- 功能：抽卡（gacha）、卡冊、卡牌合成 / 融合、道具背包、角色圖鑑、個人資料卡 + 每日簽到 + 運勢、管理員指令、日誌。
- Repo 是**公開**的（GitHub：SKer001/TouHou-Discord-Bot），分支 `main`。圖片以 `raw.githubusercontent.com` 連結提供，剛 push 的圖片可能要等一下 GitHub 才抓得到（曾出現「載入圖片失敗」，實為 GitHub 延遲）。

## 2. 專案結構（目前狀態）
```
Main.py                      入口；setup_hook 先 init_db() 再 init_item_db()，並自動載入 Cogs/load-*/ 下所有 .py
Database/
  User_DB_Manager.py         玩家資料庫（Users.db）所有存取
  Item_DB_Manager.py         道具資料庫（Item.db）所有存取
  Users.db / Item.db         SQLite 檔（開發階段 Users.db 也刻意推上 git，見第 8 節）
  item.new.json              道具批次匯入用資料
Cogs/
  load-character/  character.py, Components/character_components.py, characters.json   # 圖鑑資料
  load-gacha/      gacha.py, Components/gacha_components.py, Gacha_Pool.json            # 抽卡 / 卡冊 / 合成 / 融合；卡池與圖鑑資料分開
  load-general/    profile.py, inventory.py, Admin-item.py, Admin-user.py, Components/general_components.py
  load-system/     Admin-sys.py
Utils/components.py          共用的 Components V2 通知工具（send_notice 等）
Logger/Logger.py             日誌與錯誤回報（需要 .env 的 LOG_CHANNEL_ID）
images/                      專案根目錄；Thumbnails.json = {"角色id": "圖片URL", ..., "fill": "預設圖URL"}
```
- Main.py 會把 `Cogs/<資料夾>/<檔名>.py` 以 `Cogs.<資料夾>.<檔名>` 載入；Cog 內可用相對匯入如 `from .Components.x import ...`（命名空間套件）。
- **載入器會載入 `Cogs/load-*/` 第一層的每一個 .py**：舊檔殘留會讓載入失敗；不是 Cog 的共用程式放 `Components/` 子資料夾或專案根的 `Utils/`。
- 畫面產生器的資料夾與檔名一律叫 `Components` / `*_components.py`（舊名 `Embeds` / `*_embeds.py` 已全部改掉）。
- `.env` 需要 `DISCORD_TOKEN`、`LOG_CHANNEL_ID`（皆不進 git，換電腦要手動複製）。`.gitignore` 有 `/.env`、`/Logger/Logs/`、`__pycache__/`、`/.vscode` 等。
- 專案換行符為 **LF**（Windows 上 `core.autocrlf=true`，工作目錄可能是 CRLF，git 內部仍是 LF）。
- Windows 主控台是 cp950，印 emoji 會 `UnicodeEncodeError`：執行 Python 時設 `PYTHONIOENCODING=utf-8`（例如 PowerShell：`$env:PYTHONIOENCODING = 'utf-8'; python Main.py`）。

## 3. 資料庫設計
### Users.db（`User_DB_Manager.py`）
- `connect()`：`aiosqlite`、`row_factory=aiosqlite.Row`、`PRAGMA foreign_keys=ON`。
- 資料表：
  - `users(user_id PK, money DEFAULT 1000, level, exp, last_daily TEXT, fortune_level INTEGER DEFAULT NULL, inventory TEXT DEFAULT '{}', created_at, is_public DEFAULT 1)`
  - `gacha_stats(user_id PK → users ON DELETE CASCADE, total_draws, total_fusions)`
  - `gacha_cards(instance_id TEXT PK, user_id → users ON DELETE CASCADE, character_key, name, emoji, rarity, title, completeness REAL, obtained_at)`，索引 `idx_gacha_cards_user`
- 缺欄位用 `USERS_EXTRA_COLUMNS` 自動補。
- 主要函式：`get_or_create_user`、`add_money`、`add_exp`（升級回傳 `leveled_up/old_p/new_p/is_max`）、`get_required_exp_for_level`、`get_total_exp_for_level`、`reset_daily`、`update_daily_time`、`add_item`、`update_user_inventory`、`get_top_money`、`update_visibility`。
- 簽到：`get_daily_status(user_id, today)`（唯讀，不替對方建資料）、`claim_daily(user_id, today, fortune_level)`（原子 `UPDATE … WHERE last_daily IS NULL OR last_daily != today`，連點/雙視窗只有一次成功）。
- 抽卡：`get_user_cards(user_id)`（依 rowid 排序）、`get_gacha_stats(user_id)`、`add_gacha_cards(user_id, cards, draw_count=None)`（卡牌 + 統計**同一個交易**）。
- 合成 / 融合：`transform_cards(user_id, instance_ids, build_new_card, count_fusion=False)`
  - `BEGIN IMMEDIATE` 鎖定 → 讀取素材 → `build_new_card(consumed)` 驗證並產生新卡（條件不符丟 `ValueError`）→ 刪素材 → 寫新卡 → 融合時 `total_fusions + 1`，全部同一個交易。
  - 素材已不屬於玩家、重複 ID、驗證失敗都會回滾並丟 `ValueError`；連點或兩個確認畫面同時按只會成功一次。
- 玩家 `inventory` 欄位是 JSON 字串（`{"道具id": 數量}`），讀取時需處理 str/dict 兩種型別。

### Item.db（`Item_DB_Manager.py`）
- `get_all_items`、`get_item`、`add_item_db`、`update_item_db`、`delete_item_db`、`batch_import_db`、`CATEGORY_NAMES`、`DEFAULT_ITEMS`；`init_item_db()` 在 Item.db 缺少時會警告。
- 道具分類：`consumable`（消耗品）、`collectible`（收藏品）、`special`（裝備與特殊）。

### 卡牌 ID
- 格式 `c_<角色uuid前4碼>_<隨機hex>`。`instance_id` 是**全域主鍵**，隨機段為 **12 碼**；舊的 8 碼 ID 仍有效。合成的新卡沿用素材 ID 的前綴，融合的新卡用卡池中的 uuid。

## 4. Components V2 的做法與限制
- **所有介面與通知一律用 Components V2**，不要再用 `discord.Embed` 或純文字 `content` 回覆。
- 使用 `ui.LayoutView`、`ui.Container(accent_color=…)`、`ui.Section(TextDisplay, accessory=Thumbnail|Button)`、`ui.Separator`、`ui.ActionRow`。
- **單則訊息最多 40 個元件**；V2 訊息不能帶 `content`/`embeds`，且一旦是 V2 之後只能以 V2 編輯。
- 互動回呼寫成 `button.callback = self.xxx` 並在 `build()` 內重組畫面（`clear_items()` 後重新 `add_item`）；多種狀態（例如編輯 / 刪除確認 / 已刪除）放在同一個 View 用 `build(mode=...)` 切換。
- 縮圖規則：用角色 `id` 查 `images/Thumbnails.json`，查不到用 `"fill"`，連 URL 都沒有就只顯示文字。
- **通知工具 `Utils/components.py`**：
  - `send_notice(interaction, text, color=None, footer=None, ephemeral=True)`：自動判斷用 `response` 或 `followup` 送出，預設 ephemeral。
  - `notice_container()` / `notice_view()`：需要自行加按鈕或嵌進其他畫面時使用。
  - 色條依開頭 emoji 自動上色：❌/🚫/🗑️ 紅、⚠️ 橘、✅/🎁/✨/🟢 綠、↩️/✖️/⚙️ 灰，其他 blurple。
- V2 畫面清單：`/card gacha`、`/card inventory`、`/card synthesis`、`/card fusion`、道具背包 `/inventory`（分類 + 分頁 + 跳頁 Modal）、`/character` 圖鑑（分類→角色→檔案頁）、`/profile`（含今日簽到狀態、運勢、簽到按鈕）、`/daily`、`/admin-item edit_item` 編輯控制台、`/admin-sys reload` 重載控制台、Logger 重大事件通知，以及所有錯誤 / 成功提示。
- 原本的 `/fortune` 已併入 `/profile`，已不存在。

## 5. 各 Cog 重點
- **gacha.py**（指令群組 `/card`）：
  - 卡池讀 `Gacha_Pool.json`（變數 `GACHA_POOL`）；每個角色有三個階級 `rarities`（例如 `["SR","SSR","UR"]`）與各階級稱號 `titles`。
  - 祈願：單抽 2,000、十連 20,000 賽錢；卡池空時**先中止再扣款**；稀有度權重 `[75, 22, 3]`；完整度 `generate_completeness`（高斯平方，0.001–1.0）；結果畫面可繼續單抽/十連/查看卡庫；非本人點按鈕會被 `interaction_check` 擋下。
  - **合成 `/card synthesis card1 card2`**：兩張不同的、同角色、同階級、完整度都未滿 1.0000 的卡 → 一張新卡。
    - autocomplete：`card1` 只列出有夥伴的卡；`card2` 依 `interaction.namespace.card1` 篩選（排除第一張本身）。
    - 公式 `calc_synthesis` / `roll_synthesis`：新完整度 = 較高那張 + 增幅；相對差距 `d = |a-b| / 較高那張`。
    - 增幅上限依**較低那張**的位數（`SYNTHESIS_CAPS`）：0.x → 0.2、0.0x → 0.05、0.00x → 0.01、0.000x → 0.005；增幅 = 上限 × (1 − d)，至少 0.0001，新完整度不超過 1.0000。
    - 加倍：機率 = 階級機率 × (1 − d)²（`SYNTHESIS_DOUBLE_CHANCE`：N 99%、R 50%、SR 30%、SSR 15%、UR 10%、LR 5%；完整度一模一樣時 d = 0 即原始機率）；加倍時增幅 ×2，可超過上限。
    - 確認畫面同時顯示一般結果、加倍結果與加倍機率，按「確認合成」才擲骰並消耗卡牌。
  - **融合 `/card fusion target`**：三張同角色、同階級、完整度 1.0000 的卡 → 該角色的下一個階級（稱號換成新階級的）；已是最高階不能融合。
    - autocomplete 選的是「角色＋階級」組合（value `角色key|階級`），只列出持有 3 張以上 1.0000 且還能升階的；系統自動取最早獲得的三張（滿完整度的卡除了 ID 都一樣）。
    - 新卡完整度與祈願相同（`generate_completeness`），`total_fusions + 1`。
  - 合成 / 融合共用 `CardActionConfirmView`（確認 / 取消，結果頁可查看卡庫）；`FUSION_COUNT = 3`、`AUTOCOMPLETE_LIMIT = 25`。
- **profile.py**：簽到運勢 0–5 對應賽錢區間 `MONEY_RANGES`，經驗 100–200；時區用台灣 UTC+8，每日 00:00 重置；`/profile` 可傳 `visibility` 設定公開/私人，私人資料卡他人看不到。
- **inventory.py / general_components.py**：背包每頁 10 件，排序為分類順序再依道具 ID；`get_avatar_dominant_color` 用 Pillow 取頭像主色（變數名 `accent_color`）。
- **Admin-user.py / Admin-item.py / Admin-sys.py**：管理員 ID 寫死在 `ADMIN_ID = 403895664666214400`，其他人使用回「無權限」。
  - `/admin-user`：`reset_daily`、`add_money`、`add_exp`、`take_item`、`clear_inventory`
  - `/admin-item`：`add_item`、`add_items_batch`、`edit_item`（V2 控制台：換分類、Modal 編輯、刪除確認）、`give_item`、`give_items`
  - `/admin-sys`：`reload`（V2 控制台，重載結果顯示在上方、選單保留可連續重載）、`sync`、`shutdown`
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

## 7. 驗證方式
- 本機已安裝 discord.py 2.7.1 與 aiosqlite，可以直接跑機器人與測試。
- 測試做法：把 `udm.DB_PATH` / `idm.DB_PATH` 指到暫存資料夾（道具資料庫用副本），用真實 discord.py 物件 + 假的 Interaction（response / followup / namespace）呼叫指令的 `callback` 與 autocomplete，並斷言回覆都是 `LayoutView`（沒有 content / embed）。**測試絕不碰真實的 Users.db / Item.db**（前後比對 sha256）。
- 最近一次：合成 / 融合 45 項、V2 通知 30 項全數通過；所有 Cog 都能載入；機器人實機啟動、同步 8 個斜線指令成功。V2 畫面細節仍以 Discord 實機為準。

## 8. 使用者的決定與工作習慣
- **開發階段 `Database/Users.db` 刻意跟著推上 git**（雖然 repo 公開、內含玩家資料）。不要再建議移出追蹤或加入 `.gitignore`。
  - Claude Code 的自動權限檢查可能會擋下「提交 / 推送 Users.db」，此時請使用者自己執行 git 指令，不要繞過。
- 直接推到 `main`（個人專案，不開 PR）。
- 兩台電腦切換：離開前 `commit` + `push`，開始前 `pull`；**機器人同一時間只在一台上執行**（同一個 Token，且 Users.db 是二進位無法合併）。
- 使用者會先在 Discord 實機測試再決定提交。

## 9. 給 Claude Code 的工作守則
- 動資料前先備份；遷移類工作**不得刪除或改動舊檔**。
- 修改後保持 LF 換行；沿用既有的程式風格與繁體中文註解/文案（emoji 標題風格）。
- 新增畫面或通知一律用 V2（優先用 `Utils/components.py`），注意 40 個元件上限，縮圖走 `Thumbnails.json` + `fill` 後備。
- 資料庫寫入涉及多表時用單一交易；日常領獎類操作用原子 `UPDATE … WHERE` 防重複；會消耗東西的操作先給確認畫面。
- 使用者可能繞過 autocomplete 直接輸入值，指令內一定要再驗證一次。
- 新 Cog 檔放進 `Cogs/load-*/`，不要留下舊的同名/過期檔案。
- 不要在回覆中貼大量 URL；完成後簡述結果與下一步即可。

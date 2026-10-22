# TouHou-Discord-Bot — 專案交接文件（給 Claude Code）

> 這份文件整理了先前對話中對本專案的所有理解與決策。放在專案根目錄命名為 `CLAUDE.md`，Claude Code 啟動時會自動載入。
> 使用者慣用**繁體中文**溝通；回覆請簡潔、用繁體中文，不要貼一堆網址。

## 1. 專案概觀
- 繁體中文的「東方 Project」主題 Discord 機器人，使用 `discord.py`（**需要 >= 2.6**，因為用了 Components V2）與 `aiosqlite`（SQLite）。
- 功能：抽卡（gacha）與卡冊、道具背包、角色圖鑑、個人資料卡 + 每日簽到 + 運勢、管理員指令、日誌。
- Repo 是**公開**的（GitHub：SKer001/TouHou-Discord-Bot）。圖片以 `raw.githubusercontent.com` 連結提供，剛 push 的圖片可能要等一下 GitHub 才抓得到（曾出現「載入圖片失敗」，實為 GitHub 延遲）。

## 2. 專案結構（目前狀態）
```
Main.py                      入口；setup_hook 先 init_db() 再 init_item_db()，並自動載入 Cogs/load-*/ 下所有 .py
migrate_legacy.py            一次性遷移腳本（舊資料 → Database/Users.db）
Database/
  User_DB_Manager.py         玩家資料庫（Users.db）所有存取
  Item_DB_Manager.py         道具資料庫（Item.db）所有存取
  Users.db / Item.db         SQLite 檔（Users.db 含玩家資料，勿推上 git）
  item.new.json              道具批次匯入用資料
Cogs/
  load-character/  character.py, Embeds/character_embeds.py, characters.json   # 圖鑑資料
  load-gacha/      gacha.py, Embeds/gacha_embeds.py, Gacha_Pool.json            # 卡池（與圖鑑資料分開）
  load-general/    profile.py, inventory.py, Admin-item.py, Admin-user.py, Embeds/general_embeds.py
  load-system/     Admin-sys.py
Logger/Logger.py             日誌與錯誤回報（需要 .env 的 LOG_CHANNEL_ID）
images/                      專案根目錄；Thumbnails.json = {"角色id": "圖片URL", ..., "fill": "預設圖URL"}
```
- Main.py 會把 `Cogs/<資料夾>/<檔名>.py` 以 `Cogs.<資料夾>.<檔名>` 載入；Cog 內可用相對匯入如 `from .Embeds.x import ...`（命名空間套件）。
- **載入器會載入資料夾內每一個 .py**：舊檔（例如已刪除的 `daily.py`）殘留會讓載入失敗。
- `.env` 需要 `DISCORD_TOKEN`、`LOG_CHANNEL_ID`（皆不進 git）。`.gitignore` 目前有 `/.env`、`/Logger/Logs/`、`__pycache__/` 等；**建議加入 `/Database/Users.db`**（公開 repo，避免玩家資料外洩）。
- 專案換行符為 **LF**。

## 3. 資料庫設計（重構後）
### Users.db（`User_DB_Manager.py`）
- `connect()`：`aiosqlite`、`row_factory=aiosqlite.Row`、`PRAGMA foreign_keys=ON`。
- 資料表：
  - `users(user_id PK, money DEFAULT 1000, level, exp, last_daily TEXT, fortune_level INTEGER DEFAULT NULL, inventory TEXT DEFAULT '{}', created_at, is_public DEFAULT 1)`
  - `gacha_stats(user_id PK → users ON DELETE CASCADE, total_draws, total_fusions)`
  - `gacha_cards(instance_id TEXT PK, user_id → users ON DELETE CASCADE, character_key, name, emoji, rarity, title, completeness REAL, obtained_at)`，索引 `idx_gacha_cards_user`
- 缺欄位用 `USERS_EXTRA_COLUMNS` 自動補。`init_db()` 若 `Users.db` 不存在但舊 `database.db` 存在，會印警告提示執行 `python migrate_legacy.py`（機器人仍會以空資料庫啟動）。
- 主要函式：`get_or_create_user`、`add_money`、`add_exp`（升級回傳 `leveled_up/old_p/new_p/is_max`）、`get_required_exp_for_level`、`get_total_exp_for_level`、`reset_daily`、`update_daily_time`、`add_item`、`update_user_inventory`、`get_top_money`、`update_visibility`。
- 簽到：`get_daily_status(user_id, today)`（唯讀，不替對方建資料）、`claim_daily(user_id, today, fortune_level)`（原子 `UPDATE … WHERE last_daily IS NULL OR last_daily != today`，連點/雙視窗只有一次成功）。
- 抽卡：`get_user_cards(user_id)`（依 rowid 排序）、`get_gacha_stats(user_id)`、`add_gacha_cards(user_id, cards, draw_count=None)`（卡牌 + 統計**同一個交易**）。
- 玩家 `inventory` 欄位是 JSON 字串（`{"道具id": 數量}`），讀取時需處理 str/dict 兩種型別。

### Item.db（`Item_DB_Manager.py`）
- `get_all_items`、`get_item`、`add_item_db`、`update_item_db`、`delete_item_db`、`batch_import_db`、`CATEGORY_NAMES`、`DEFAULT_ITEMS`；`init_item_db()` 在 Item.db 缺少時會警告。
- 道具分類：`consumable`（消耗品）、`collectible`（收藏品）、`special`（裝備與特殊）。

### 卡牌 ID
- 格式 `c_<角色uuid前4碼>_<隨機hex>`。`instance_id` 現在是**全域主鍵**，隨機段由 8 碼加長為 **12 碼**避免碰撞；舊的 8 碼 ID 仍有效。

## 4. Components V2 的做法與限制
- 使用 `ui.LayoutView`、`ui.Container(accent_color=…)`、`ui.Section(TextDisplay, accessory=Thumbnail|Button)`、`ui.Separator`、`ui.ActionRow`。
- **單則訊息最多 40 個元件**；V2 訊息不能帶 `content`/`embeds`，且一旦是 V2 之後只能以 V2 編輯。
- 互動回呼寫成 `button.callback = self.xxx` 並在 `build()` 內重組畫面（`clear_items()` 後重新 `add_item`）；逾時 `on_timeout` 把控制項反灰。
- 縮圖規則：用角色 `id` 查 `images/Thumbnails.json`，查不到用 `"fill"`，連 URL 都沒有就只顯示文字。
- 已全面改成 V2 的功能：`/card gacha`（單抽、十連、再抽按鈕）、`/card inventory`（卡冊）、道具背包 `/inventory`（分類 + 分頁 + 跳頁 Modal）、`/character` 圖鑑（分類→角色→檔案頁，三種狀態同一個 View）、`/profile`（含今日簽到狀態、運勢、簽到按鈕）、`/daily`（簽到快捷，顯示資料卡；重複簽到顯示私人提示）。
- 原本的 `/fortune` 已併入 `/profile`，已不存在。

## 5. 各 Cog 重點
- **gacha.py**：卡池讀 `Gacha_Pool.json`（變數 `GACHA_POOL`）；單抽 2,000、十連 20,000 賽錢；卡池空時**先中止再扣款**；稀有度權重 `[75, 22, 3]`；完整度 `generate_completeness`（高斯平方，0.001–1.0）；結果畫面可繼續單抽/十連/查看卡庫；非本人點按鈕會被 `interaction_check` 擋下。
- **profile.py**：簽到運勢 0–5 對應賽錢區間 `MONEY_RANGES`，經驗 100–200；時區用台灣 UTC+8，每日 00:00 重置；`/profile` 可傳 `visibility` 設定公開/私人，私人資料卡他人看不到。
- **inventory.py / general_embeds.py**：背包每頁 10 件，排序為分類順序再依道具 ID；`get_avatar_dominant_color` 用 Pillow 取頭像主色。
- **Admin-user.py / Admin-item.py**：管理員 ID 寫死在 `ADMIN_ID = 403895664666214400`，其他人使用回「無權限」。指令：`reset_daily`、`add_money`、`add_exp`、`take_item`、`clear_inventory`、`add_item`、`add_items_batch`、`edit_item`、`give_item`、`give_items`。
- **Logger.py**：記錄指令/元件互動並把重大事件回報到 `LOG_CHANNEL_ID`；`Admin-sys.py` 未改動。

## 6. 遷移腳本 `migrate_legacy.py`
用法（機器人關閉時，專案根目錄）：`python migrate_legacy.py --dry-run` → 無誤再 `python migrate_legacy.py`。
1. 以 sqlite backup API 複製 `database.db` → `Database/Users.db`
2. `init_db()` 補 `fortune_level` 欄位與新表
3. 合併 `Cogs/load-general/daily.db` 的 `last_daily`/`fortune_level`（有資料時以 daily.db 為準；舊的 money/level/exp **不搬**；缺的使用者會建立）
4. 匯入 `Cogs/load-gacha/users/*.json` 到 `gacha_cards`/`gacha_stats`（重複 `instance_id` 或缺必要欄位會中止）
- `verify()` 逐項比對所有欄位、簽到資料、卡牌數量/內容，並跑 `integrity_check`、`foreign_key_check`。
- 失敗會刪除半成品 `Users.db` 並結束；`Users.db` 已存在則拒絕執行；**不修改、不刪除任何舊檔**。

## 7. 重構歷程（時間順序）
1. 使用者要求抽卡結果與卡冊改 V2、縮圖用 `images/Thumbnails.json`（沒有就用 `fill`）。起初我誤解成「把 embed 合併」，後來澄清是要 10 張相連的畫面，最終採用 Components V2。
2. 背包 `/inventory` 改 V2 並優化（分類排序、分頁、道具說明）。
3. `images/` 移到專案根目錄，修正所有 `Thumbnails.json` 路徑。
4. `/character` 圖鑑改 V2（`characters.json` 格式為 main_character/characters 結構）。
5. 合併 `/profile`、`/daily`、`/fortune`（保留重複簽到提示）。
6. **資料庫與檔案結構重整**（本次）：
   - `item.db` → `Database/Item.db`；`item_data.py` → `Database/Item_DB_Manager.py`；`item.new.json` → `Database/`
   - `database.db` → `Database/Users.db`；`db_manager.py` → `Database/User_DB_Manager.py`
   - `daily.db` 併入 `Users.db`；gacha `users/*.json` 併入 `Users.db`
   - gacha `character.json` → `Gacha_Pool.json`，與 load-character 資料分開
   - 順手修好原本壞掉的 `/give_item`（背包寫不進去）

## 8. 目前狀態與待辦（請使用者自行完成）
已交付 `db_refactor.zip`（10 個檔案，路徑與專案相同）：`Database/User_DB_Manager.py`、`Database/Item_DB_Manager.py`、`migrate_legacy.py`、`Main.py`、`Cogs/load-gacha/gacha.py`、`Cogs/load-general/{profile,inventory,Admin-item,Admin-user}.py`、`Cogs/load-general/Embeds/general_embeds.py`。

使用者需手動：
1. 搬檔：`Utils/item.db`→`Database/Item.db`、`Utils/item.new.json`→`Database/`、`Cogs/load-gacha/character.json`→`Gacha_Pool.json`
2. 刪除 `Utils/item_data.py`、`Database/db_manager.py`、`Cogs/load-general/daily.py`（殘留會導致載入失敗）
3. 覆蓋新檔 → 跑 `migrate_legacy.py --dry-run` → 正式遷移 → 啟動機器人
4. 確認正常後，才刪舊的 `database.db`、`Cogs/load-general/daily.db`、`Cogs/load-gacha/users/`
5. 把 `/Database/Users.db` 加入 `.gitignore`

## 9. 驗證狀況與已知限制
- 沙盒無法安裝 discord.py / aiosqlite（pypi 回 403，**未繞過**），測試用「sqlite3 上的 aiosqlite 替身 + discord 替身」。**沒有真實 Discord 測試**，請在實機再確認 V2 畫面。
- 通過的測試：遷移（真實資料 2 位玩家、94 張卡、簽到合併，賽錢 9,088,968 保留，舊檔 sha256 不變）、5 種失敗情境都乾淨中止、資料庫層 43 項（含併發：25 個同時簽到只成功 1 次、60 個 add_money 不遺失、批次寫入回滾、外鍵）、Cog 流程 34 項（單抽/十連/按鈕再抽/餘額不足/空卡池/卡冊/簽到/重置/按鈕連點/私人資料卡/give_item/take_item/clear_inventory）。
- 靜態檢查的誤報：`from Database import User_DB_Manager as udm` 是子模組匯入（沒問題）；`Admin-item.py` 的 `item_data` 只是區域變數名。

## 10. 給 Claude Code 的工作守則
- 動資料前先備份；遷移類工作**不得刪除或改動舊檔**。
- 修改後保持 LF 換行；沿用既有的程式風格與繁體中文註解/文案（emoji 標題風格）。
- 新增 V2 畫面時注意 40 個元件上限，並確認縮圖走 `Thumbnails.json` + `fill` 後備。
- 資料庫寫入涉及多表時用單一交易；日常領獎類操作用原子 `UPDATE … WHERE` 防重複。
- 新 Cog 檔放進 `Cogs/load-*/`，不要留下舊的同名/過期檔案。
- 不要在回覆中貼大量 URL；完成後簡述結果與下一步即可。

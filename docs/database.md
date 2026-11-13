# 🗄️ 資料庫設計 (Users.db / Item.db / 角色資料 / 卡牌 ID)

> 從 `CLAUDE.md` 拆出來的細節文件 (2026-11-11)。要做這方面的工作時才讀；改了內容記得一起更新。

### Users.db（`User_DB_Manager.py`）
- `connect()`：`aiosqlite`、`row_factory=aiosqlite.Row`、`PRAGMA foreign_keys=ON`。
- 資料表：
  - `users(user_id PK, money DEFAULT 1000, level, exp, last_daily TEXT, fortune_level INTEGER DEFAULT NULL, inventory TEXT DEFAULT '{}', created_at, is_public DEFAULT 1, stamina DEFAULT 240, stamina_updated_at TEXT)`
  - `gacha_pity(user_id, pool, total_draws, since_ur, last_ur_at)`，主鍵 `(user_id, pool)`
  - `gacha_stats(user_id PK → users ON DELETE CASCADE, total_draws, total_fusions)`
  - `gacha_cards(instance_id TEXT PK, user_id → users ON DELETE CASCADE, character_key, name, emoji, rarity, title, completeness REAL, obtained_at)`，索引 `idx_gacha_cards_user`
    - (玩家稱號是另一回事：`users.equipped_title` 存戴著的稱號 id，清單在 `Database/title_data.py`；`get_title_stats` / `get_title_state` / `set_equipped_title`)
    - `name` / `emoji` / `title` 只是寫入當下的副本：讀卡時 (`get_user_cards`、`transform_cards`、`econ.get_listings`、通知的上架清單) 一律用 `Utils.character_data.apply_current_names` 換成目前角色檔的內容，角色改名、改稱號後舊卡跟著變 (角色檔快取 60 秒；角色檔刪掉才顯示副本)。2026-11-13 起。
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

### 🔔 主動通知（`Notify_DB_Manager.py`，資料也在 Users.db）
- 表由 `init_notify_db()` 自己建（notify Cog 的 `cog_load` 呼叫），不在 `User_DB_Manager.SCHEMA_STATEMENTS`；沒有外鍵。
  - `notify_settings(user_id, kind, enabled)`，主鍵 `(user_id, kind)`：玩家開關，**沒有紀錄 = 開啟**（預設全開）。
  - `notifications_sent(user_id, kind, key, sent_at, ok)`，主鍵 `(user_id, kind, key)`：去重，同一件事只發一次；`ok = 0` = 私訊失敗（不重試）；30 天前的紀錄由 `prune_sent` 清掉。
  - `notify_watch(user_id, kind, value, updated_at)`，主鍵 `(user_id, kind)`：上次看到的狀態（賽錢箱 / 妖怪 `full` / `not_full`、體力 `spent` / `full`）；`user_id = 0` 是全服狀態：`baseline`（系統第一次上線的時間，之前的成交不通知）、`event:<id>` = `狀態|started_at`。
  - `notify_listings(listing_id PK, seller_id, instance_id, name, emoji, rarity, price, listed_at)`：上次看到的上架清單；下次不見了、沒有成交紀錄、又過了 7 天 ➔ 到期退回通知。
- 種類登記表 `Database/notify_data.py` 的 `NOTIFY_TYPES`（`name / emoji / desc / dm`）；`dm=False` 的種類永遠不私訊、不能開啟（`can_dm`）。
- 純判斷：`check_shrine` / `check_stamina` / `check_sales` / `check_expired` / `check_events`；`collect_notices(now)` 讀資料庫跑一輪（會 `econ.get_shrine` 結算每座神社、`econ.expire_listings` 退回到期上架），回傳「開著、能私訊、還沒發過」的通知，發送前用 `claim` 佔位。常數：`CHECK_INTERVAL_MINUTES = 10`、`GUEST_LEAVING_WINDOW = 4 小時`、`SALES_LOOKBACK = 7 天`、`SENT_KEEP = 30 天`。

### Item.db（`Item_DB_Manager.py`）
- `get_all_items`、`get_item`、`add_item_db`、`update_item_db`、`delete_item_db`、`batch_import_db`、`replace_all_items(items)`、`CATEGORY_NAMES`、`DEFAULT_ITEMS`、`DAILY_REWARD_ITEM`；`init_item_db()` 在 Item.db 缺少時會警告，**資料表空白時會寫入 `DEFAULT_ITEMS`**（所以預設清單要跟實際想要的道具一致）。
- `item_templates(item_id PK, name, emoji, category, description, effect TEXT DEFAULT '{}')`；`effect` 是 JSON（目前支援 `{"stamina": N}`），讀出來是 dict；舊資料表缺 `effect` 會自動補。`update_item_db`（Modal 編輯）不會改動 effect。
- 道具分類：`consumable`（消耗品）、`cuisine`（招待料理）、`material`（素材）、`collectible`（收藏品）、`special`（裝備與特殊）。
- **目前道具（2026-10-28 使用者指定，舊的 demo 道具與所有玩家背包已清空）**：全部是 `consumable` 體力道具。
  | ID | 名稱 | 體力 |
  |---|---|---|
  | `yuyuko_dango` | 🍡 幽夢三色團子 | 120 |
  | `sakuya_scone_tea` | 🫖 咲夜特製司康與紅茶 | 120 |
  | `marisa_mushroom_soup` | 🍄 螢光蘑菇濃湯 | 67 |
  | `reimu_onigiri` | 🍙 陰陽梅干飯糰 | 60（每日簽到贈送 1 個，`DAILY_REWARD_ITEM`） |
  - 目前只有簽到能拿到 🍙；其他三個只能用管理員指令發放。`Database/item.new.json` 是全部道具的批次匯入範本。
  - **🍱 招待料理（`cuisine`，v0.26.000，名稱與說明由 Claude 依東方梗自訂，使用者同意）**：`effect.serve` = `food` / `drink` / `dessert`（`SERVE_TYPES`），招待參拜客用；目前沒有取得方式（之後跟素材副本一起做）。食物：`mystia_lamprey` 🍢 夜雀烤八目鰻、`ran_inari` 🍣 八雲特製豆皮壽司、`nitori_cucumber` 🥒 河童冰鎮小黃瓜；茶水：`reimu_bancha` 🍵 博麗神社粗茶、`eirin_herbal_tea` 🌿 永遠亭藥草茶、`suika_amazake` 🍶 伊吹甘酒；點心：`eientei_tsukimi_dango` 🌕 月見糰子、`cirno_kakigori` 🍧 琪露諾特製刨冰、`alice_cookie` 🍪 人偶師的手工餅乾。
- 動到真實資料前的備份放在 `Database/backups/`（已加入 `.gitignore`，只留在本機）。

- 管理員卡冊操作：`delete_gacha_cards(user_id, ids)`、`clear_gacha_cards(user_id)`、`update_cards_completeness(user_id, ids, value)`，都只動該玩家自己的卡並回傳實際影響張數。

### 角色資料（`Characters/<分類>/<id>.json`）
- 格式：`id`、`name`、`emoji`、`category`（`main_character` 或 `th01`…）、`profile{title, species, ability, description}`、`gacha{enabled, uuid, rarities, titles}`、`base_stats{hp, atk, def}`（目前都是 0）、`special_powers{id: "<id>_SP", name, levels{階級: {id: "<id>_SP_I|II|III", name, type, spent, cooldown, desc}}}`。
- SP 等級名稱 = `Easy・初陣` / `Lunatic・瘋狂` / `Phantasm・幻象` + `・` + SP 名稱；`spent` 是 B 點消耗（B 點系統尚未實作）。`type`、`spent`、`cooldown`、`desc` 目前只用於圖鑑顯示。
- 驗證：檔名必須等於 `id`、`special_powers.levels` 的鍵必須等於 `gacha.rarities`。分類顯示名稱在 `Utils/character_data.py` 的 `CATEGORY_INFO`。
- 舊作角色、大妖精、小惡魔的介紹與 SP 名稱是 Claude 依風格自訂的，使用者尚未確認。

### 卡牌 ID
- 格式 `c_<角色uuid前4碼>_<隨機hex>`。`instance_id` 是**全域主鍵**，隨機段為 **12 碼**；舊的 8 碼 ID 仍有效。合成的新卡沿用素材 ID 的前綴，融合的新卡用卡池中的 uuid。

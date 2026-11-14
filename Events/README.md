# 🎪 活動檔格式 (`Events/<id>.json`)

一個活動一個檔，放進這個資料夾就會被讀到，不用改程式（範例：`th06_scarlet_mist.json`）。
每個機制都是 **一般池 + 活動預留位**：活動進行中時，活動檔的內容會加進一般池（或取代某些欄位），活動結束就恢復原狀。
合併的程式在 `Database/events.py` 的 `game_rules()`。**數值要先跟使用者確認再填。**

## 基本資料
| 欄位 | 說明 |
|---|---|
| `id` / `name` / `emoji` / `series` / `description` | 活動 ID (要跟檔名一樣)、名稱、圖示、出自哪一作、介紹 |
| `duration_days` | 表定天數 (`/admin-event start` 沒給天數時用這個) |
| `auto_start` | `true` = 沒有紀錄時自動當成進行中 (測試用，沒有結束時間) |
| `items` | 活動道具 (素材 / 料理)，開機時自動寫進 Item.db；活動結束時從所有玩家倉庫清除 |

## 預留位
| 機制 | 一般池 | 活動欄位 | 合併方式 |
|---|---|---|---|
| 🍳 料理配方 | `shrine_data.RECIPES` | `recipes {料理: {素材: 數量}}` | 加進去 |
| 🍱 點餐池 | 一般料理 | `items` 裡 `effect.serve` 的料理自動進活動池；`order_event_chance` | 每道菜有這個機率從活動池抽 |
| ✨ 活動料理加成 | ×1 | `event_dish_bonus` | 每份活動料理 ×這個數 (多個活動取最大) |
| 🗺️ 採集地點 | 5 個一般地點 | `location` (一個) 或 `locations` (多個) | 加進去，標「活動限定」 |
| 🧺 一般地點的掉落 | 各地點的 `drops` | `extra_drops {地點: [素材]}` | 加進該地點 |
| 🍀 採集事件池 | 各地點 good / bad 各一個 | `explore_events {地點: {good: [事件], bad: [事件]}}` | 加進事件池，發生事件時隨機抽一個 |
| 🎲 採集事件機率 | 5% | `special_chance` | 取最大 |
| 🙏 客人池 | 10 種一般客人 | `guests {客人: {...}}` | 加進活動池 |
| 🎯 抽到活動客人的機率 | 沒設 = 全部客人平均抽 | `event_guest_chance` | 設了就先依機率決定抽活動池還是一般池 |
| 💬 一般客人的活動版 | `shrine_data.GUESTS` | `guest_overrides {客人: {favorite, hint, name, emoji, lines: {high/mid/low: [台詞]}}}` | `lines` 加進台詞池，其他欄位取代 |
| 🏪 雜貨店 | 人里 5 種素材 | `shop {素材: 價格}` | 加進去 (同名取代價格) |
| 📈 數值倍率 | 全部 ×1 | `modifiers {...}` (見下面) | 乘上去 (多個活動相乘) |
| 🎴 祈願機率提升 | 卡池角色平均抽 | `gacha.rate_up {角色: 倍率}` | 抽到該角色的權重 ×倍率 (多個活動相乘) |
| 🎴 祈願階級機率 | `RARITY_WEIGHTS` [75, 22, 3] | `gacha.rarity_weights [低, 中, 高]` | 取代 (後面的活動蓋前面)；保底不受影響 |
| 🎪 活動限定卡池 | 舊作 / 紅魔鄉兩個卡池 | `gacha.pool {name, desc, characters: [角色 id]}` | `/card gacha` 選「🎪 活動限定卡池」就抽這裡 (角色可以跨卡池)；保底獨立記在 `event_<活動 id>`；同時有多個活動時後面的蓋前面；`name` 沒寫 = 「<emoji> <活動名>卡池」 |
| 📅 簽到額外道具 | 🍙 飯糰 ×1 | `daily_items [[道具, 數量]]` | 加送 |
| 📜 活動任務 | 沒有 | `quests [{id, name, desc, type, target, count, reward: {money, exp}}]` | `/event quest` 看進度、按「🎁 領取」拿賽錢 + 經驗值 (見下面「活動任務」) |
| 🏷️ 活動稱號 | 沒有 | `quest_titles [{id, name, rarity, desc, min_quests}]` | 領取的任務數 ≥ `min_quests` 就**永久**獲得 (活動結束也保留) |

- `modifiers`：
  - 神社：`shrine_income` 每小時收入、`youkai_spawn` 妖怪出現機率、`guest_spawn` 參拜客來訪機率 (機率最多 100%)、`youkai_reward` 打退妖怪的賽錢
  - 廚房：`serve_reward` 招待報酬 (乘在全部加成之後)、`explore_stamina` 每趟採集的體力消耗
  - 簽到：`daily_money` 賽錢、`daily_exp` 經驗
  - 卡牌：`decompose` 分解拿到的賽錢 (不影響市值)
  - 祈願 / 交易：`gacha_cost` 祈願價格 (結果畫面與「繼續祈願」按鈕顯示實際價格；指令選項上的價格固定寫原價)、`market_fee` 市場買家手續費 (原本 5%)、`transfer_fee` 轉帳手續費 (原本 5%)；設 0 = 免手續費
- 台詞池用客人 ID 挑一句，同一位客人每次打開畫面都是同一句。
- 素材 / 料理要在 `items` 定義才會在活動結束時被清掉；`extra_drops` / `shop` 放一般素材也可以，但不會被清除。

## 📜 活動任務 (`quests` / `quest_titles`)
| `type` | `target` | 進度怎麼算 |
|---|---|---|
| `explore_location` | 地點 id | 在那個地點採集的趟數 |
| `cook_each` | `[料理 id, ...]` | 每種至少做 `count` 鍋 (預設 1)；進度 = 做過幾種 / 幾種 |
| `serve_guest` | 客人種類 id | 招待那種客人的位數 |
| `serve_event_dish` | — | 招待時端出**這個活動**的活動料理份數 (點的 + 額外招待都算) |
| `serve_favorite` | — | 成功招待 (額外端上客人最愛的料理) 的次數 |
| `gacha_event_pool` | — | 這個活動的活動限定卡池 (`gacha.pool`) 祈願抽數；活動沒有卡池時這個任務做不完 (畫面會提示) |
| `daily` | — | 活動期間簽到天數 |

- `count` = 目標數字 (`cook_each` 除外)；`reward.money` / `reward.exp` = 領取的賽錢與經驗值。
- **只在活動進行中計數**。一輪 = 「活動 id + 這次開始時間」：`/admin-event start` 重開同一個活動 ➔ 新的一輪，進度與領取都從 0 開始 (auto_start 沒有紀錄時那一輪叫 `<id>:auto`)。
- 領取：完成 + 這一輪沒領過 + 活動進行中才能領；**活動結束後沒領的就沒了**。結束前 24 小時內還有完成沒領的任務會私訊提醒一次 (`/notify` 的「⏰ 活動任務快結束」)。
- 活動稱號的 id = `event_<活動 id>_<稱號 id>` (放在 `/profile` 稱號分組「🎪 活動」)；`min_quests` 算的是**這個活動所有輪加總領過幾種不同的任務** (同一個任務在不同輪各領一次只算一種)。
- 格式檢查：`Database/events.validate_quests(活動)` (測試會檢查所有活動檔)。

## 注意
- 活動卡池的保底與抽數記在 `event_<id>`；另外每次抽都把「每張卡 (角色 × 階級) 的預期張數」記進 `daily_draws` 的 `card:<角色>:<階級>` (照活動的 `rate_up` 與 `rarity_weights` 算)，浮動市值結算時加進該卡的預期抽到量，活動期間熱門角色的市值不會因為賣出變多而被誤判下跌。

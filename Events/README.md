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
| 📈 數值倍率 | 全部 ×1 | `modifiers {shrine_income, youkai_reward, serve_reward, explore_stamina}` | 乘上去 (多個活動相乘) |

- `modifiers`：`shrine_income` 神社每小時收入、`youkai_reward` 打退妖怪的賽錢、`serve_reward` 招待報酬 (乘在全部加成之後)、`explore_stamina` 每趟採集的體力消耗。
- 台詞池用客人 ID 挑一句，同一位客人每次打開畫面都是同一句。
- 素材 / 料理要在 `items` 定義才會在活動結束時被清掉；`extra_drops` / `shop` 放一般素材也可以，但不會被清除。

## 還沒有預留位的系統
抽卡卡池與機率、每日簽到獎勵、市場 / 分解、妖怪與參拜客的生成機率 —— 需要時再加。

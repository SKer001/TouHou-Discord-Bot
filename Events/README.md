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
| ⚡ 體力料理配方 | `shrine_data.STAMINA_RECIPES` (5 道，一鍋 1 份) | `stamina_recipes {料理: {素材: 數量}}`；道具本身放 `items` (`category: consumable`、`effect: {"stamina": N}`) | 加進去，料理畫面「⚡ 體力料理」分類；不能招待 |
| 🍱 點餐池 | 一般料理 | `items` 裡 `effect.serve` 的料理自動進活動池；`order_event_chance` | 每道菜有這個機率從活動池抽 |
| ✨ 活動料理加成 | ×1 | `event_dish_bonus` | 每份活動料理 ×這個數 (多個活動取最大) |
| 🗺️ 採集地點 | 9 個一般地點 | `location` (一個) 或 `locations` (多個) | 加進去，標「活動限定」 |
| 🧺 一般地點的掉落 | 各地點的 `drops` | `extra_drops {地點: [素材]}` | 加進該地點 |
| 🍀 採集事件池 | 各地點 good / bad 各一個 | `explore_events {地點: {good: [事件], bad: [事件]}}` | 加進事件池，發生事件時隨機抽一個 |
| 🎲 採集事件機率 | 5% | `special_chance` | 取最大 |
| 🙏 客人池 | 10 種一般客人 | `guests {客人: {...}}` | 加進活動池 |
| 🗺️ 地點稱號 | 一般地點每個 SR / UR 各一個 (`title_data.TREK_TITLE_TEXT`) + 幻想鄉踏破 | `location.titles {sr: {name, desc}, ur: {name, desc}}` (`locations` 裡每個地點也可以寫) | 每個活動自動一組「🗺️ 足跡・<活動名>」；SR 採 200 趟、UR 採 1000 趟，次數跨活動累積；另外自動有「<活動名> • 踏破」SSR (活動地點都採過 1 趟，永久保留；說明寫在 `trek_title.desc`，照那個活動地點的特色寫，沒寫 = 通用句「<活動名>期間開放的地方，你全都去過了。」)；沒寫 `titles` = 「〇〇的熟客 / 〇〇的活地圖」 |
| 🏷️ 客人稱號 | 一般客人每種 SR / UR 各一個 (`title_data.GUEST_TITLE_TEXT`) | `guests.<客人>.titles {sr: {name, desc}, ur: {name, desc}}` (desc 的 `{n}` = 目前次數) | 每個活動自動一組「🙏 客人・<活動名>」；SR 招待 50 次、UR 成功招待 50 次，次數跨活動累積、稱號永久；沒寫 `titles` = 「〇〇的常客 / 〇〇的知己」 |
| 🎯 抽到活動客人的機率 | 沒設 = 全部客人平均抽 | `event_guest_chance` | 設了就先依機率決定抽活動池還是一般池 |
| 💬 一般客人的活動版 | `shrine_data.GUESTS` | `guest_overrides {客人: {favorite, hint, name, emoji, lines: {high/mid/low: [台詞]}}}` | `lines` 加進台詞池，其他欄位取代 |
| 🏪 雜貨店 | 人里 5 種素材 | `shop {素材: 價格}` | 加進去 (同名取代價格) |
| 📈 數值倍率 | 全部 ×1 | `modifiers {...}` (見下面) | 乘上去 (多個活動相乘) |
| 🎴 祈願機率提升 | 同階級的角色平均抽 | `gacha.rate_up {角色: 倍率}` | 抽到那個階級時，該角色的權重 ×倍率 (多個活動相乘)；階級機率不變 |
| 🎴 祈願階級機率 | `BASE_RATES` N 43.9 / R 27 / SR 18 / SSR 10.9 / UR 0.1 / LR 0.1 (%) | `gacha.rarity_weights {階級: %}` (例 `{"UR": 0.5, "LR": 0.3}`) | 有寫的階級取代起始機率，沒寫的照舊，再換算成總和 100% (後面的活動蓋前面)；UR 81 抽起升高的曲線與 100 抽保底照舊 (升高的部分加在活動的 UR 上)；舊格式 `[低, 中, 高]` 不再適用，會被略過 |
| 🎪 活動限定卡池 | 舊作 / 紅魔鄉兩個卡池 | `gacha.pool {name, desc, characters: [角色 id]}` | `/card gacha` 選「🎪 活動限定卡池」就抽這裡 (角色可以跨卡池)；保底獨立記在 `event_<活動 id>`；同時有多個活動時後面的蓋前面；`name` 沒寫 = 「<emoji> <活動名>卡池」 |
| 🍳 活動食譜稱號 | 沒有 | `recipe_title {desc}` (照那個活動的料理特色寫) | 有 `recipes` / `stamina_recipes` 的活動自動有「<活動名> • 食譜全收」SSR (活動料理全部做過，永久保留)，一組「🍳 美食家・<活動名>」；沒寫 desc = 「<活動名>的活動料理你全部做過了。」 |
| 📖 活動怪物圖鑑稱號 | 沒有 | `bestiary_title {desc}` | 有 `ura` 區塊 (活動怪) 的活動自動在 📖 怪物圖鑑多一區 (🎪)，並有「<活動名> • 怪物全收」SSR (那個活動的活動怪全部打倒或勸走過，永久保留；放在「🌀 裏世界」組)，全收獎勵 100,000 賽錢 + 300 經驗；沒寫 desc = 「<活動名>期間出現的怪物你全都打倒過了。」 |
| 🍀 卡池歐氣稱號 | 舊作 (普池) / 紅魔鄉各 3 個 (`title_data.LUCK_POOL_TEXT`) | `gacha.pool.luck_titles {ssr / ur / lr: {name, desc}}` | 有活動限定卡池的活動自動一組「🍀 運氣・<活動名>」：距離上次 UR 90 抽內就出 UR 1 / 5 / 10 次 = SSR / UR / LR；沒寫 = 「〇〇的幸運兒 / 寵兒 / 歐皇」 |
| 📅 簽到額外道具 | 🍙 飯糰 ×1 | `daily_items [[道具, 數量]]` | 加送 |
| 📜 活動任務 | 沒有 | `quests [{id, name, desc, type, target, count, reward: {money, exp}}]` | `/event quest` 看進度、按「🎁 領取」拿賽錢 + 經驗值 (見下面「活動任務」) |
| 🏷️ 活動稱號 | 沒有 | `quest_titles [{id, name, rarity, desc, min_quests}]` | 領取的任務數 ≥ `min_quests` 就**永久**獲得 (活動結束也保留) |
| 🌀 裏世界的活動關卡 | 沒有 | `ura {environment, normals, elite, boss, statuses, enemies, treasures, relics, events}` (見下面「裏世界」) | 活動期間每一關 10% 有一扇 🎪 門 (每區最多 2 扇)；內容不管活動有沒有在進行都會讀進來 (活動寶物活動結束也賣得掉) |

- `modifiers`：
  - 神社：`shrine_income` 每小時收入、`youkai_spawn` 妖怪出現機率、`guest_spawn` 參拜客來訪機率 (機率最多 100%)、`youkai_reward` 打退妖怪的賽錢
  - 廚房：`serve_reward` 招待報酬 (乘在全部加成之後)、`explore_stamina` 每趟採集的體力消耗
  - 簽到：`daily_money` 賽錢、`daily_exp` 經驗
  - 卡牌：`decompose` 分解拿到的賽錢 (不影響市值)
  - 祈願 / 交易：`gacha_cost` 祈願價格 (結果畫面與「繼續祈願」按鈕顯示實際價格；指令選項上的價格固定寫原價)、`market_fee` 市場買家手續費 (原本 5%)、`transfer_fee` 轉帳手續費 (原本 5%)；設 0 = 免手續費
- 台詞池用客人 ID 挑一句，同一位客人每次打開畫面都是同一句。
- 素材 / 料理要在 `items` 定義才會在活動結束時被清掉；`extra_drops` / `shop` 放一般素材也可以，但不會被清除。

## 🌀 裏世界 (`ura`，0.35.087 起；規則在 `docs/ura.md`「活動融入」)
- **規則是固定的** (`Database/ura/rules.py` 的 `FEST_*`)：活動期間每一關 10% 其中一扇門 (戰鬥 / 精英 / 寶箱 / 事件) 變成 🎪 活動門、保留原本房間類型；每區最多 2 扇；第 9 關 (商人)、第 10 關 (BOSS) 不換；同時有兩個活動時每扇門隨機挑一個。每走一關都看「當下」有沒有活動 (資料層寫進 `run["live_fests"]`)。
- **活動檔只放內容** (程式 `Database/ura/fest.py`、讀取 `Database/ura/data.fests()`)：
  | 欄位 | 內容 |
  |---|---|
  | `environment {name, emoji, desc, statuses: [狀態], class_statuses: {職業: [狀態]}, money_mult}` | 🎪 房間的戰鬥裡全隊套用 `statuses`，那個職業再加 `class_statuses`，打倒敵人的錢 × `money_mult`；狀態用 `duration: "battle"` (打完就消失)。`desc` 寫在門上和戰鬥畫面 |
  | `normals [敵人]`、`elite`、`boss` | 🎪 戰鬥的敵人從 `normals` 抽 (隻數照原本的門)；🎪 精英 = `elite` + `normals` 小弟；🎪 精英門 25% 換成 `boss` (一局最多一次，數值 HP ×6、ATK ×1.5、DEF ×1.4，當成 BOSS 戰：不能逃、有第二階段、不狂暴)；🎪 寶箱怪也用 `elite` |
  | `enemies {id: {...}}` | 格式同 `Database/ura/data/enemies.json`；招式施加的狀態要數值時寫 `status_value` (例 `debuff_atk` 0.15 = ATK −15%) |
  | `statuses {id: {...}}` | 格式同 `statuses.json`；新的修正：`dodge_pct` 閃避 (只閃單體)、`lifesteal_pct` 打出的傷害回成 HP |
  | `treasures {SSR / UR / LR: [[id, 名稱, emoji, 說明], ...]}` | 活動寶物 (說明 = 倉庫「🔍 看說明」顯示的那段，0.35.103 起；只有 SSR / UR / LR，同階級平均抽，賣價照 `treasures.json` 的階級價目)。**🎪 活動保留格**：🎪 房間裡本來就會掉寶物時多擲一格 0 / 1 / 2 個 (20 / 70 / 10%)；活動 BOSS 一定掉 1 / 2 個 (80 / 20%)。倉庫的區域篩選「🎪 活動寶物」；活動結束也保留 |
  | `relics {id: {...}}` | 格式同 `relics.json`；🎪 房間掉的法具 50% 換成活動法具 (等級不變)，活動 BOSS 一定給 1 個；一般掉落和流浪商人不會出現。御札的 `active.do` 多一種 `extra_action` (這回合多一次行動) |
  | `events {id: {...}}` | 格式同 `events.json` (`type` good / bad / special)；🎪 事件門照 40 / 30 / 30 抽這裡的事件；`effect.do` 多一種 `buy_fest_treasure` (`cost` × 區域數換 1 個活動寶物，`choice: true`) |
- id 不要跟一般資料撞名 (紅霧異變全部用 `fest_` 開頭或自己的名字)；測試會檢查招式用到的狀態都存在。

## 📜 活動任務 (`quests` / `quest_titles`)
| `type` | `target` | 進度怎麼算 |
|---|---|---|
| `explore_location` | 地點 id | 在那個地點採集的趟數 |
| `cook_each` | `[料理 id, ...]` | 每種至少做 `count` 鍋 (預設 1)；進度 = 做過幾種 / 幾種 |
| `serve_guest` | 客人種類 id | 招待那種客人的位數 |
| `serve_event_dish` | — | 招待時端出**這個活動**的活動料理份數 (點的 + 額外招待都算) |
| `serve_favorite` | — | 成功招待 (額外端上客人最愛的料理) 的次數 |
| `gacha_event_pool` | — | 這個活動的活動限定卡池 (`gacha.pool`) 祈願抽數；活動沒有卡池時這個任務做不完 (畫面會提示) |
| `gacha_pool` | 卡池 id (`classic` / `th06`) | 活動期間在那個一般卡池祈願的抽數 (紅霧異變算紅魔鄉卡池) |
| `daily` | — | 活動期間簽到天數 |
| `ura_kill` | 敵人 id 或 `[敵人 id, ...]` | 🌀 在裏世界打倒 / 勸走那些敵人的隻數 (好幾種就加總)；**打倒當下就算**，那一局後來失敗或放棄也算 |
| `ura_fest_boss` | — | 🌀 打倒這個活動的活動 BOSS (`ura.boss`) 次數；當下就算 |
| `ura_fest_treasure` | — | 🌀 **成功撤離**時帶出這個活動的活動寶物個數 (失敗 / 放棄不算) |
| `ura_evacuate` | — | 🌀 活動期間從裏世界**成功撤離**的次數 |

- `count` = 目標數字 (`cook_each` 除外)；`reward.money` / `reward.exp` = 領取的賽錢與經驗值。
- **只在活動進行中計數**。一輪 = 「活動 id + 這次開始時間」：`/admin-event start` 重開同一個活動 ➔ 新的一輪，進度與領取都從 0 開始 (auto_start 沒有紀錄時那一輪叫 `<id>:auto`)。
- 領取：完成 + 這一輪沒領過 + 活動進行中才能領；**活動結束後沒領的就沒了**。結束前 24 小時內還有完成沒領的任務會私訊提醒一次 (`/notify` 的「⏰ 活動任務快結束」)。
- 活動稱號的 id = `event_<活動 id>_<稱號 id>` (放在 `/profile` 稱號分組「🎪 活動」)；`min_quests` 算的是**這個活動所有輪加總領過幾種不同的任務** (同一個任務在不同輪各領一次只算一種)。
- 格式檢查：`Database/events.validate_quests(活動)` (測試會檢查所有活動檔)。

## 注意
- 活動卡池的保底與抽數記在 `event_<id>`；另外每次抽都把「每張卡 (角色 × 階級) 的預期張數」記進 `daily_draws` 的 `card:<角色>:<階級>` (照活動的 `rate_up` 與 `rarity_weights` 算長期平均，含 UR 曲線與保底)，浮動市值結算時加進該卡的預期抽到量，活動期間熱門角色的市值不會因為賣出變多而被誤判下跌。

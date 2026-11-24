# 開發紀錄 (CHANGELOG)

## 版本號規則：`X.XX.XXX`
| 位置 | 意義 | 例子 |
|---|---|---|
| 第一個數字 | **大版本**：新功能、新活動。開發階段為 `0` | 神社經營、市場上線 |
| 第二個數字 | **功能改動**：新 UI、規則調整、系統重構；進位時最後一段歸零 | 卡冊改疊卡、抽卡改價 |
| 最後三碼 | **瑣碎的 commit**：修正、文件、卡面、資料更新 | 新增某角色卡面 |

- 版本號寫在 `Utils/version.py`，開機時印在主控台與 log 頻道。
- **每次 commit 都要更新版本號，並在這份文件最上面補一筆**：做了什麼、遇到什麼問題、怎麼解決。
- 0.22.000 以前是依 git 歷史回推的版本號 (commit 雜湊附在後面)。
- **`1.00.000` 起為正式上線版本** (在那之前都是開發階段)。
- 0.38 以前的紀錄在 `docs/changelog/` (照第二段版本號分檔：`0.38.md`、`0.37.md` … `0.22.md`；0.21 以前合成 `early.md`)。

---

## 1.00.007 — 2026-11-24：拆檔後補上漏改的文件 (統整)
- `docs/dev/database.md`：開頭加「入口 ➔ 實作在哪裡」一段 (`Database/users/` 四個檔、`Database/economy/` 六個檔各放什麼)，各小節補上函式 / 資料表實際所在的子模組 (逐一對照程式確認)；原本的內容沒刪沒改。
- `ARCHITECTURE.md`：`RARITY_ORDER` 改寫成定義在 `Cogs/load-gacha/logic/rules.py` (入口 `gacha.py` 也拿得到)；`SCHEMA_STATEMENTS` 補上實際在 `Database/users/schema.py`。
- `docs/gameplay/ura.md`：`box_rows()` 改成在 `Cogs/load-ura/views/common.py`；`docs/gameplay/cogs.md`：`LUCKY_WITHIN` / `roll_pool_cards` 補上定義在 `logic/rules.py`。
- 只改文件，沒動程式；全部測試照舊通過。

## 1.00.006 — 2026-11-24：拆檔收尾：只重載同資料夾別的 Cog 時不動拆出去的規則 / 畫面 (統整)
- 檢查員發現拆檔後唯一的行為差異：`reload Admin-gacha` 會把同資料夾的 `logic/`、`views/` 重新執行，入口 `gacha.py` 卻不會 ➔ 入口手上是舊的類別、子模組是新的 (新舊混用)。
- `Utils/reloader.py` 加 `VIEW_OWNER`：`logic/`、`views/` 只跟著擁有它們的入口 (`gacha`、`ura`) 重載；重載同資料夾別的 Cog 時只重載 `Components/`，跟拆開前一樣。`test_console` 加 1 項。
- `README.md` 的專案結構補上 `load-market`、`load-ura`、`Database/users/`、`economy/`、`ura/`。
- 拆檔總結 (1.00.001～1.00.005)：4 個大檔案從 1,442～1,730 行變成入口 44～414 行；搬過去的程式跟原本逐一比對相同 (只有兩個路徑常數與一行函式內匯入是必要調整)；舊的 import 全部照舊能用。全部測試 11,134 項通過。
- 還超過 700 行的：`Database/ura/run.py` 1,089、`ura_components.py` 893、`title_data.py` 841 (大部分是稱號資料)、`shrine.py` 824、`ura/combat.py` 738；`tools/card_art/layered/hd_card.py` 1,849 (角色卡面設定，TH07 卡面開工前再拆成一角色一檔)。

## 1.00.005 — 2026-11-24：拆大檔案後的獨立檢查、補上沒跟到的文件 (統整)
- **檢查 1.00.001～004 (程式一行沒改)**：四個原始大檔每個頂層函式 / 類別 / 常數的語法樹跟拆開前逐一比對，只有三處不同，都是搬位置必要的：`Database/users/schema.py` 的 `DB_DIR` 與 `Cogs/load-gacha/logic/rules.py` 的 `BASE_DIR` 多往上一層 (值照舊)、`CardActionConfirmView.view_inventory` 多一行函式內匯入 (兩個畫面檔互相要對方)。原檔 import 區以外的每一行都還在，只有兩行說明文字跟著改寫 (經濟入口說明的「改這裡的常數」、`DB_DIR` 上面那行註解)。
- **相容**：原始檔的每個頂層名字 (含底線開頭的與 import 進來的，共 148 / 99 / 45 / 116 個) 從舊入口都拿得到，而且跟子模組是同一個物件；測試裡 7 種對入口賦值的寫法 (`DB_PATH`、`STARTING_MONEY`、`get_user_cards`、`get_rules`、`load_events`、`GUEST_SPAWN`、`_select`) 實際跑過都會傳到子模組。原始檔沒有 `global`，也沒有工具用路徑讀這四個檔。
- **重載**：真的建一個 bot 跑 `reload_all` / `reload_one`：20 個子模組 (加兩個套件的 `__init__`) 都會重載、子模組先入口後、重載後所有函式 / 類別都是新物件，入口、子模組、執行中的 Cog 互相對得上，`DB_PATH` 留在沙盒。照 `Main.py` 的方式載入是 19 個模組，`views/`、`logic/` 沒有被當成 Cog (`SHOW_UNRELEASED` 開 / 關都一樣)。
- ⚠️ **留給之後決定**：只重載 `Admin-gacha` 時，同資料夾的 `logic/`、`views/` 會跟著重載但入口 `gacha.py` 不會 ➔ 入口手上是舊的類別與舊的 `GACHA_POOL` (拆開前這個動作不會動到 gacha 的程式)。指令照常能用；要完全換新就重載 `gacha` 或全部重載。
- **文件**：`docs/dev/testing.md` 的測試總數改成 11,133；`TODO.md`、`docs/gameplay/cogs.md` 補上拆開後的位置；`ARCHITECTURE.md`「View 之間只能單向引用」補上函式內匯入那個例外。
- **測試**：`python tests/run_all.py` 11133 項全過；沒設 `SHOW_UNRELEASED` 的環境單跑 `tests/test_unreleased.py` 59 項全過。

## 1.00.004 — 2026-11-24：抽卡 Cog 拆成 `Cogs/load-gacha/logic/` (規則) + `views/` (畫面) (統整)
- **只搬位置、不改行為**：`Cogs/load-gacha/gacha.py` (1730 行) 只留 `GachaCardSys` 指令與 `setup` (414 行)。規則拆到 `logic/`：`rules.py` (卡池資料 `GACHA_POOL` / `THUMBNAILS`、⛩️ 祈願規則、⚗️ 合成 / 🔮 融合規則、📊 機率表的資料計算 `resolve_pool` / `rate_sheet_data` / `open_note`)、`detail.py` (🔍 `card_detail_info`)；畫面拆到 `views/`：`synthesis.py` (`CardActionConfirmView`、`SynthesisPickerView`、`find_synthesis_groups`)、`inventory.py` (`InventoryView`、`AlbumView`、`send_character_page`、疊卡 / 收集進度小工具)、`result.py` (`GachaResultView`、`send_rate_sheet`、`EventPoolPickerView`、`GachaHistoryView`)。
- **`gacha.py` 當入口**：跟 `ura.py` 同一套 (`_PARTS` + `_EntryModule`)，原本的 import 整段留著、再把每個子模組的名字全部轉出來 ➔ `Admin-gacha.py`、市場、教學書、19 個用 `importlib.import_module("Cogs.load-gacha.gacha")` 的檔案一行都不用改。拆之前先把模組的 118 個名字與常數值存下來，拆完比對：一個都沒少、值都一樣 (`BASE_DIR` 在 `logic/rules.py` 多退一層，值照舊是 `Cogs/load-gacha`)。
- ⚠️ **改入口屬性**：grep 過 Cogs / Database / Utils / tools / tests / deploy，沒有人直接對 gacha 模組賦值；測試改的是 `gacha.econ.get_rules` (改到的是經濟模組本身) 和 `random.choices` (全域的 random)，拆開後照舊生效。入口的 `__setattr__` 還是會一起改到有這個名字的子模組 (保險)，`test_console.py` 用 `gacha.DRAW_COST = 7 ➔ draw_cost(10) == 70` 驗證。
- ⚠️ **踩到的坑**：卡冊要開合成選卡 (`InventoryView` ➔ `SynthesisPickerView`)，合成結果又要開卡冊 (`CardActionConfirmView.view_inventory` ➔ `InventoryView`)，兩個檔互相要對方 ➔ 匯入方向定成 synthesis ➔ inventory ➔ result，`view_inventory` 裡多一行函式內的 `from .inventory import …` (唯一動到函式內容的地方)。`GACHA_POOL`、`THUMBNAILS`、`RARITY_ORDER` 只在 `rules.py` 定義一次，其他子模組都從那裡匯入 (同一個物件)。
- **`/admin-sys reload`**：`Utils/reloader.py` 的單一重載與全部重載都加上 `Cogs.*.logic.*`；`VIEW_ORDER` 列出 `Cogs.load-gacha.logic` (`rules`、`detail`) 與 `Cogs.load-gacha.views` (`synthesis`、`inventory`、`result`)，順序是 Components ➔ logic ➔ views ➔ 入口 (`reload_extension`)，所以「改了 Characters/ 之後 reload 抽卡模組會重讀卡池」照舊。只重載 `Admin-gacha` 時同資料夾的 logic / views 也會跟著重載、但入口 `gacha.py` 不會 (要換新就重載 gacha 或全部重載)。
- **測試**：`python tests/run_all.py` 11133 項全過 (`test_console.py` +14：順序、資料夾裡每個檔都有列、`reload all` / 單一重載後入口與子模組一致、入口賦值會傳到子模組)；botcli 走過 `/card gacha` 十連 ➔ 繼續十連 ➔ 📊 機率表 ➔ 🎒 查看卡庫、活動限定卡池、`/card inventory` ➔ 一疊 ➔ 單卡詳情 ➔ 📖 角色圖鑑 ➔ 🔒 放進收藏冊、`/card album`、`/card synthesis` 手動 (確認 ➔ 繼續合成 / 查看卡庫) 與 ⚡ 自動合成全部、`/card fusion` (確認 ➔ 查看卡庫)、`/admin-gacha give` / `view`、`/card history` ➔ 機率表、`/card help`，錯誤 0 個。

## 1.00.003 — 2026-11-24：裏世界 Cog 的畫面拆到 `Cogs/load-ura/views/` (統整)
- **只搬位置、不改行為**：`Cogs/load-ura/ura.py` (1442 行) 只留 `UraCog` 指令與 `setup` (163 行)；畫面拆到 `views/`：`common.py` (逾時 / 提示文字 / 每頁幾個、`_btn` / `_select` / `box_rows` / `_opt`)、`run.py` (`RunView` 進行中的一局)、`setup.py` (`PartyPickerView`、`PocketModal`、`LoadoutView`)、`shop_storage.py` (`ShopView`、`StorageView`)、`bestiary.py` (`BestiaryView`)。用腳本照行號從 git 裡的原檔切，切完比對過：原檔第 25 行以後每一行程式與註解都還在、順序一樣，各檔只多了開頭的說明與自己用到的 import。**沒有循環匯入**：`common` ➔ `run` ➔ `setup` (整裝按出發會開 `RunView`)，`shop_storage`、`bestiary` 只用 `common`；`RunView` 要用 Cog (`track` / `forget` / `announce`) 是建構子傳進來的 `self.cog`，views 不 import `ura.py`。
- **`ura.py` 當入口**：跟 `User_DB_Manager.py` 同一套 (`_PARTS` + `_EntryModule`)，把每個子模組的名字全部轉出來，原本的 import 也留著 ➔ `tests/test_ura_ui.py` (`cogmod.RunView` / `LoadoutView` / `B` / `load_thumbnails`…) 和教學書 (`importlib.import_module("Cogs.load-ura.ura").VIEW_TIMEOUT` / `STORAGE_PER_PAGE`) 一行都不用改。
- ⚠️ **改入口屬性**：全專案對這個模組賦值的只有 `tests/test_ura_ui.py` 的 `cogmod._select = 會記錄的版本` (檢查沒有選單被截成 25 個)。只 re-export 的話這個檢查會**默默失效** (測試照樣全過)，所以入口的 `__setattr__` 會一起改到有這個名字的子模組；測試在賦值後多一行 assert 確認 5 個子模組都換到了。
- ⚠️ **踩到的坑**：`views/setup.py` 在 `ura.py` 裡不能用 `setup` 這個名字匯入 (會蓋掉 Cog 的 `async def setup`，模組載不起來) ➔ 匯入時取別名 `_v_setup`。`views/` 是子資料夾，`Main.py` / botcli / `scan_extensions` 只掃第一層，不會被當成 Cog (botcli 還是 19 個模組)。
- **`/admin-sys reload`**：`reload_extension` 只重跑 `ura.py`，views 子模組還是舊的 ➔ `Utils/reloader.py` 的單一重載與全部重載都加上 `Cogs.*.views.*`；新的 `VIEW_ORDER` 讓它們排在全部 Components 後面、照依賴順序 (照字母排的話 `bestiary` 會比 `common` 先，拿到舊的小工具)。`test_console.py` +10 項 (順序、資料夾裡每個檔都有列、`reload all` / `reload ura` 後類別是新的而且入口 / 子模組 / 執行中的 Cog 互相對得上)。
- **測試**：`python tests/run_all.py` 11119 項全過；botcli 走過 `/ura explore` 選隊伍 ➔ 整裝 (挑道具、💾 儲存、⚡ 快速整裝、💰 帶賽錢) ➔ 出發 ➔ 選門 ➔ 普攻選目標打一回合 ➔ 📖 狀態表、背包、`resume` / `abandon` (確定放棄 ➔ 結算 + 公開訊息)、`/ura shop` 買東西、`/ura inventory` 換頁、`/ura bestiary` 換區 / 看一隻 / 回清單、`/ura status`，錯誤 0 個。文件：`docs/dev/structure.md`、`ARCHITECTURE.md` (Cog 太大時拆 `views/` 的寫法)。

## 1.00.002 — 2026-11-24：玩家資料庫資料層拆成 `Database/users/` 套件 (統整)
- **只搬位置、不改行為**：`Database/User_DB_Manager.py` (1620 行) 拆成 `Database/users/`：`schema.py` (🧱 資料表結構與初始化、`DB_PATH`、`connect`、`_ensure_user`)、`core.py` (👤 玩家資料、💰 貨幣經驗、📅 每日簽到、🎒 背包道具、🏆 排行榜與隱私、⚡ 體力)、`titles.py` (🏷️ 稱號、🖼️ 角色名片)、`cards.py` (🎴 抽卡：卡牌與統計、🛠️ 管理員卡冊操作)。
  - 用腳本照行號切：88 個函式 / 類別 / 常數的語法樹跟拆開前逐一相同 (只有下面的 `DB_DIR` 例外)，原檔每一行程式與註解都還在；各檔開頭只多了自己用到的 import。
  - 照原本的大標題切會循環匯入 (簽到 / 體力要記統計、稱號要讀玩家資料、體力要 `tw_day`)，所以大家都會用到的三小段放進 `core.py`：`TW` / `tw_day` (原本在抽卡那段)、📊 玩家統計與 🎪 活動任務計數 (原本夾在稱號那段)。依賴順序 schema ➔ core ➔ titles ➔ cards，沒有往回匯入。
- **舊檔名留著當入口**：跟 1.00.001 的 `Economy_DB_Manager.py` 同一套做法：入口把每個子模組的名字 (含底線開頭的、`json` / `aiosqlite` / `card_cache` 這類匯入進來的) 全部轉出來，引用它的 Cog、其他資料層、工具、測試一行都沒改。
- **改入口屬性照舊生效**：全專案對這個模組賦值的只有三種：`udm.DB_PATH = 沙盒` (32 個測試檔 + botcli；重載時 `Utils/reloader.py` 也會寫回去)、`udm.STARTING_MONEY = 1000` (4 個測試)、`udm.get_user_cards = fake` (`test_card_cache.py`)。入口的模組類別帶 `__setattr__`，賦值會一起改到 `schema.DB_PATH` 這類「本來就有這個名字」的子模組，`connect()` 讀到的就是沙盒路徑。
- ⚠️ **踩到的坑**：`DB_DIR = os.path.dirname(os.path.abspath(__file__))` 搬進 `Database/users/schema.py` 後會變成 `Database/users/` ➔ 正式環境會悄悄開一個空的 `Database/users/Users.db`，而測試與 botcli 全都會改 `DB_PATH`，所以完全測不出來。改成往上一層 (整個拆分唯一改到的一行程式)，新的 `test_users_split.py` 會查預設路徑還是 `Database/Users.db`。
- **`/admin-sys reload`**：`Utils/reloader.py` 原本只認 `Database.User_DB_Manager` 這個名字排最前面，子模組會掉到後面 ➔ 入口重載時轉出舊函式。`PACKAGE_ORDER` 加上 users 這一組，整組 (子模組照依賴順序、入口最後) 排在所有資料層之前。
- **測試**：新的 `test_users_split.py` 26 項 (預設路徑、入口轉出所有名字、改 `DB_PATH` / `STARTING_MONEY` / 函式會傳到子模組並真的被用到、還原)、`test_console.py` +11 (重載順序、子模組都有登記、全部重載後各檔拿到同一份新函式、`DB_PATH` 還在沙盒、資料庫照常能用)；`python tests/run_all.py` 共 11,108 項全過。botcli 走過 `/profile` (簽到、修改稱號)、`/daily`、神社 (回收、採集)、`/leaderboard`、`/card gacha` / `inventory` / `album` / `history`、`/admin-gacha give` / `view`、`/admin-user reset_daily`、`/trade`，以及 `/admin-sys reload` 全部重載後再簽到、抽卡，錯誤 0 個。

## 1.00.001 — 2026-11-24：經濟系統資料層拆成 `Database/economy/` 套件 (統整)
- **只搬位置、不改行為**：`Database/Economy_DB_Manager.py` (1523 行) 照原本的大標題拆成 `Database/economy/`：`common.py` (神社經營的數值常數、`_dt` / `modifier` / `economy_meta` 小工具)、`event_state.py` (🎪 活動狀態、`get_rules`、手續費倍率快取)、`shrine.py` (⛩️ 神社經營)、`gather.py` (🏮 打工、🗺️ 採集 / 🍳 料理 / 🏪 雜貨店 / 🍵 招待、🧺 快速採集)、`market_value.py` (💹 浮動市值)、`market.py` (♻️ 分解、🏪 市場、💸 轉帳)。依賴只有一個方向 (common ➔ event_state ➔ shrine ➔ gather；event_state ➔ market_value ➔ market)，沒有循環 import。
  - 用腳本照行號切：124 個函式 / 常數的語法樹跟拆開前逐一相同，原檔每一行程式與註解都還在；各檔開頭只多了自己用到的 import。
- **舊檔名留著當入口**：`Economy_DB_Manager.py` 把每個子模組的名字 (含 `_active_events` 這類底線開頭的、`load_events` / `apply_current_names` 這類匯入進來的) 全部轉出來，Cog、其他資料層、教學書的 `importlib.import_module("Database.Economy_DB_Manager")`、測試一行都不用改。
- **改入口屬性照舊生效**：測試會寫 `econ.get_rules = fake`、`econ.load_events = fake`、`econ.GUEST_SPAWN = […]` (共 12 處)；只是轉出名字的話改不到函式真正在用的那一份。入口把自己的模組類別換成帶 `__setattr__` 的子類別：對入口賦值時，「本來就有這個名字」的子模組一起改。新增子模組要加進入口的 `_PARTS`。
  - ⚠️ 踩到的坑：`importlib.reload(入口)` 會重設入口的 `__name__` / `__spec__` / `__file__`，一開始這些也被轉給子模組 ➔ 重載後子模組的名字全變成入口的。雙底線的名字現在不轉；`test_console.py` 有檢查。
- **`/admin-sys reload`**：原本照字母排，入口 (大寫 E) 會排在子模組前面、`gather` 也會排在 `shrine` 前面 ➔ 重載後拿到舊函式。`Utils/reloader.py` 新增 `PACKAGE_ORDER`：子模組照依賴順序先重載、入口最後，整組排在入口原本的位置 (還是在 Notify / Quest / Ura 之前)。
- **測試**：`test_economy.py` +16 (入口轉出所有名字、改常數 / 函式 / 匯入的名字會傳到子模組並真的被用到、還原、共用的手續費快取只有一份)、`test_console.py` +9 (重載順序、子模組都有登記、全部重載後各檔拿到的是同一份新函式)；`python tests/run_all.py` 共 11,071 項全過。botcli 走過神社主畫面 / 清掃 / 治退 / 回收、採集、打工、料理、快速採集、雜貨店、招待、市值、分解、上架、下架、市場購買、轉帳，錯誤 0 個。

## 1.00.000 — 2026-11-24：🎉 正式版：專案整理、文件分類成手冊、未公開卡池開關 (統整)
- **使用者**：整理各角色做的事與筆記做成手冊；不含 TH07 的版本同步到 `online`，版本 1.00.000；專案要有條有序、不要深度綁定 Claude。
- **文件分類**：`docs/` 分成 `handbook/` (工作手冊)、`gameplay/` (玩法規則)、`dev/` (開發)、`art/` (卡面)、`changelog/` (舊紀錄)，總目錄 `docs/README.md`；程式、測試、文件裡的引用 (33 個檔案) 都改成新路徑。
- **手冊**：
  - `docs/handbook/workflow.md`：溝通、先問再做、推送、版本號、分工 (統整 / 卡面 / 名片 / 玩法)、工作守則。
  - `docs/handbook/sessions.md`：每個角色做過什麼、踩過的坑、專案外 6 份筆記的去向、交接清單。
  - `docs/dev/structure.md` (專案結構，對照實際檔案更新)、`docs/dev/components-v2.md` (畫面寫法)。
- **`CLAUDE.md` 從 2 萬字縮成一頁**：只留繁體中文規則、5 條紅線、文件樹；其他都在手冊。文件裡的暫存路徑、對話代號、專屬工具名稱都拿掉，稱呼改成角色名。
- **CHANGELOG 存檔**：這份只留 0.39 起，更早的照第二段版本號搬到 `docs/changelog/` (18 份)；切前切後版本標題與內容逐字相同。
- **未公開卡池開關**：`Utils/gacha_pools.py` 完整定義改叫 `ALL_GACHA_POOLS`，`th07` 標 `"released": False`；`.env` 的 `SHOW_UNRELEASED` 沒開時妖妖夢整個不存在 (卡池、圖鑑、稱號、名片、裏世界、「幻想鄉緣起」的判定)。測試、botcli、`tools/ura_roster.py`、模擬工具預設打開；新增 `tests/test_unreleased.py` (59 項，關 / 開各跑一次)。之後要公開只要刪掉那個 `released`。
  - 這樣 `online` 跟 main 永遠是同一份程式，不用另外維護一份刪掉 TH07 的版本。
  - `deploy/handoff.py push-env` 上傳 `.env` 時自動濾掉 `SHOW_UNRELEASED`，開發旗標不會跑到正式機器人。⚠️ `take` 之後在本機用正式 Token 跑時，要先把 `.env` 的這一行拿掉。
- **清掉的東西 (使用者同意)**：根目錄 `JSON.json`、`override.txt`、`requirements.compiled`；已合併的分支 `ura-skill-desc`、`claude/gacha-rates-a49710` 與它的 worktree；`.gitignore` 兩行過時設定。TH07 模擬腳本收進 `tools/ura_sim/th07/`。
- 全部測試 11,046 項通過。下一階段：拆 4 個大檔案，先列拆法給使用者看。

## 1.00.008 — 2026-11-24：`online` 改成只在修 bug / 新活動時更新 (統整)
- **使用者**：「我的理想是 online 分支是穩定運行的版本，所以要盡可能不要一直 git，等修 bug 或是新活動再推」。
- 寫進 `CLAUDE.md` 紅線 3、`docs/handbook/workflow.md` 第 3、6 節、`docs/dev/deploy.md`：
  - 平常照常推 `main`，**不要每次推完就同步 `online`**。
  - 只有修 bug、新活動 (或新卡池) 要開放，而且使用者說可以，才 `python deploy/handoff.py deploy`。
  - 上線前要跑完全部測試，再用 `SHOW_UNRELEASED=0` 跑一次 botcli；中間會一起帶上去的 commit 先列給使用者看。
- `TODO.md` 第 0 節記下 `online` 目前的版本 (1.00.007)，之後每次上線都要更新。
- `docs/dev/deploy.md` 改掉一句舊說明：`push-env` 從 1.00.000 起會自動濾掉 `SHOW_UNRELEASED`，不用手動拿掉。
- 只改文件。全部測試 11,134 項通過。**這一版不上 `online`**。

## 1.00.009 — 2026-11-24：TODO 補上 TH07 的進度 (統整)
- `TODO.md` 還寫著 TH07「遊戲設計建角色檔、跑模擬中」，改成實際的進度：角色、卡池、符卡、卡池稱號在 0.40.000 就建好了 (未公開)。
- 剩下的拆成四項：名片、卡面 33 張 (先拆 `hd_card.py`)、春雪異變、公開。
- 「下一步建議」補一句：0.36.000 之後還沒在 Discord 上實際玩過，雲端上線前最好先玩一輪。
- 只改文件。全部測試 11,134 項通過。不上 `online`。

## 0.40.001 — 2026-11-24：fix：圖鑑「卡牌階級」下面的卡池狀態看活動有沒有開 (筆電，玩法 session)
- 統整 session 用 botcli 看幽幽子的角色頁時發現 (使用者同意小修)：`build_character_container` 只看 `gacha.enabled`，妖妖夢 (`th07`，event_only、現在沒有活動) 也寫「🎴 可在 `/card gacha` 祈願中獲得」，其實抽不到。
- 新的 `character_components.pool_state_text(char, folder, rules)`：一般卡池 (舊作) 照舊；event_only 卡池開著 ➔「🎪 紅霧異變期間開放：`/card gacha` 選「🎪 活動限定卡池」」(活動名稱從 `rules["gacha_event_pools"]` 的 `events` 來，好幾個活動開同一個卡池會全部列出)；沒開 ➔「🎪 只在活動期間開放 (目前沒有開)」；讀不到活動規則 ➔「🎪 只在活動期間開放：…」；沒開抽卡 / 不在任何卡池 ➔「🚫 目前不在卡池中」。
- `/character` 開圖鑑時讀一次活動規則 (`econ.get_rules()`，讀失敗就當作不知道)；卡冊單卡的「📖 角色圖鑑」(`gacha.send_character_page`) 也一樣，兩邊都傳角色所在的資料夾 (決定卡池)。
- 測試：`test_character` 加 9 項 (舊作、紅魔鄉開著、紅魔鄉沒開、妖妖夢沒開、讀不到規則、不在卡池；`/character` 畫面的舊作 / 紅魔鄉 / 妖妖夢)，`test_card_detail` 的 📖 角色圖鑑頁也檢查這一行。

## 0.40.000 — 2026-11-24：🌸 TH07 妖妖夢 11 位角色、妖妖夢卡池、裏世界符卡與三個新機制 (筆電，玩法 session)
- 統整 session 派工 (TH07 第二件)；定案資料在 `docs/new-characters.md` 第 5 節。數值表 (含 emoji、圖鑑簡介、模擬結果) 使用者 2026-11-24「都好」，兩題照建議改。
- **角色檔** `Characters/TH07/` 11 個：莉莉霍瓦特 🌷、蕾蒂 ☃️、橙 🐈、愛麗絲·瑪格特羅依德 🪆 (`alice_th07`，新角色)、露娜薩 🎻、梅露蘭 🎺、莉莉卡 🎹、魂魄妖夢 ✂️、西行寺幽幽子 🦋、八雲藍 🦊、八雲紫 ☂️。圖鑑稱號 = 妖妖夢的官方稱號 (最低階卡牌稱號)，種族 / 能力 / 簡介照萌娘百科 (橙怕水、紫冬眠、莉莉卡「現實中不存在的幻想之音」用內建瀏覽器對過原文)。
- **卡池** `Utils/gacha_pools.py` 加「🌸 妖妖夢卡池」`th07` (`event_only`，春雪異變才開，活動之後再設計)；分類 `Utils/character_data.py` 加 `TH07` (🌸 東方妖妖夢 (TH07) / Perfect Cherry Blossom)。卡池和角色檔一起加，「幻想鄉緣起」不會拿不到。
- **稱號** (`Database/title_data.py`，使用者「都好」)：卡池收集 `pool_th07_chars` SR「幽明結界的越境者」、`pool_th07_cards` UR「白玉樓賞花會的上賓」；歐氣 `LUCK_POOL_TEXT["th07"]` SSR「白玉樓的幸運兒」、UR「櫻吹雪裡的閃光」、LR「機率境界的操縱者」。推角稱號自動多 11 個。稱號分組 25 ➔ 27 組，分組選單會翻頁 (共用選單本來就支援)。
- **裏世界** (`Database/ura/`)：
  - 職業：攻擊手 妖夢 / 幽幽子 / 藍、守護者 蕾蒂 / 愛麗絲、輔助 莉莉 / 梅露蘭、斥候 橙 / 露娜薩、嚮導 莉莉卡 / 紫；`base_stats` 都在職業數值 ±10% 內。
  - 11 招符卡 (`spells.json`)。新狀態 🎎 人偶替身 `doll_guard` (受到的傷害 −value)、🌸 春之祝福 `spring_blessing` (莉莉的 ATK +10%；另開一個是因為同名狀態會被後放的蓋掉，梅露蘭 +30% 會被蓋成 +10%)。
  - 新機制：👻 **半靈追擊** (`damage` 的 `pursuit`：打倒目標 ➔ 再打另一隻 ATK × 1.0，沒有別隻不打)；🦋 **死蝶給敵人用** (`dot_max_hp_pct` 的 `boss_mult: 0.5`，BOSS 每回合 2.5%；跟我方一樣最多扣到剩 1 HP)；🎻 **騷靈合奏** (`rules.ENSEMBLES` + spells.json `ensemble`：三姊妹都在隊上而且活著 ➔ 三檔不同的數字 × 1.2，莉莉卡固定的賽錢 × 1.2 不放大)。莉莉卡的賽錢 × 1.2 跟小惡魔 × 1.3 不疊、取高的 (本來的 `spell_money` max)。
  - 說明文字 (`describe.py`)：半靈追擊、合奏 (列出放大哪些數字)、固定下數的連打「連打 3 下」、人偶替身 / 春之祝福 / 死蝶的作用。`python tools/ura_roster.py` 重產 `docs/ura_roster.md` (35 位) 並同步角色檔的符卡說明。
- **跟第三輪原案不一樣的地方** (數值表給使用者看過)：
  - 藍 0.55 / 0.65 / 0.75 ➔ **0.6 / 0.7 / 0.8**：引擎的「4～6 下」是越多越少 (平均 4.67 下不是 5 下)，改完平均合計 2.8 / 3.27 / 3.73 ≈ 原本想要的數字；說明文字也只顯示到小數一位。
  - **坑：我方放的「2 回合」攻擊類增益只蓋到 1 次我方行動** (一回合只有一人能動，放符卡那回合已經用掉) ➔ 莉莉的春之祝福、露娜薩的 DEF 弱化改 **3 回合**；防守類 (嘲諷、減傷、ATK 弱化、疾風、死蝶) 照算敵方回合，不動。寫進 `docs/ura.md`。
  - 莉莉回血 10 / 13 / 16% ➔ **15 / 20 / 25%** (模擬：原案第 5 區 2%，雪與舞 30%；改完 23%)。
- **模擬** (`tools/ura_sim/spells.py` 自動玩家，重裝，每格 200 局；腳本與結果在統整的筆記資料夾 `th07-sim/`)：
  - 新角色大多落在同職業範圍裡：妖夢 SR 第 5 區 86% (魔理沙 82%)；UR 第 7 區 妖夢 80% / 幽幽子 86% / 藍 84% (芙蘭 72%、神綺 94%)；LR 第 6 區 幽幽子 72% / 藍 70% (神綺 84%)；守護者同一檔 蕾蒂 84%、愛麗絲 SSR 75% (美鈴 89%、夢子 68%)；斥候第 4 區 橙 100% / 露娜薩 98% (露米婭 94%)；嚮導 紫 UR 第 7 區 64% (靈夢 66%)。
  - 全體攻擊隊換主攻 第 5 區：幽幽子 SSR 65% / 藍 SSR 74% (琪露諾 38%、神綺 77%)；紫 22% (嚮導 ATK 低，不能當主攻)。
  - 冥界整局 第 7 區 (強隊)：妖夢 65% / 幽幽子 68% / 藍 70% (芙蘭 52%)；冥界照舊最難，這次沒動。
  - 騷靈三姊妹整隊很弱 (第 3 區 1%)，合奏救不起來，算收集向。
  - ⚠️ 自動玩家只在敵人 2 隻以上才放全體 / 連打招 (幽幽子、藍、紫、橙一局只放 2～6 次)，這類符卡的倍率模擬量不出來；改成「只剩一隻 BOSS 也放」反而更差 (B 點用完，補師沒得用)。
  - 坑：第一次跑模擬時同一個工作行程沿用了上一組的主題 / 數值修改 ➔ 改成每組一個新行程 (`max_tasks_per_child=1`) 重跑。
- 模擬工具 `tools/ura_sim/spells.py`：莉莉算全隊補師、嚮導的回常識度招 (莉莉卡每場都放賺錢) 會放、`--theme netherworld` 整局固定主題、`--aoe-solo`。
- 測試：寫死的 24 位改 35 位 (`test_ura_engine`、`test_pools`、`test_character`、`test_inventory`)，卡池清單加 th07 (`test_admin_gacha`、`test_pity`：/card history 的機率表選單照舊只列抽得到的)，`test_titles` 加妖妖夢的卡 (幻想鄉緣起要連妖妖夢也收齊) 和分組翻頁；`test_ura_engine` 新機制 (半靈追擊有 / 沒打倒 / 沒有別隻、死蝶 BOSS 減半 / 扣到剩 1、合奏三人活著才算 / 不放大賽錢、莉莉卡跟小惡魔取高、人偶替身減傷、莉莉 + 梅露蘭相加、3 回合 = 2 次我方行動)。
- 文件：`docs/new-characters.md` 第 5 節 (進度、最後的數字、模擬、建檔時發現的坑)、`docs/ura.md` (35 位職業表、TH07 符卡表、N 回合的規則)。

## 0.39.007 — 2026-11-24：TH07 裏世界職業與符卡定案 (統整)
- 第三輪 grill，使用者回「都好」，全部照建議。寫進 `docs/new-characters.md` 第 5 節：
  - 11 位的職業：攻擊手 3、守護者 2、輔助 2、斥候 2、嚮導 2。
  - 每位的符卡名稱、效果〔低・中・高〕、B 點 / 冷卻。
- 三個新機制要做：
  - 妖夢打倒敵人時半靈追擊。
  - 死蝶也能給敵人用，對 BOSS 扣的量減半。
  - 騷靈三姊妹三位同隊時，符卡效果 × 1.2。
- 莉莉卡讓這場戰鬥的賽錢 × 1.2，跟小惡魔的 × 1.3 不疊加，同一場取高的。
- 數值都是暫定。遊戲設計跑模擬之後，數值表給使用者看過才建檔推送。卡池收集 / 歐氣稱號也要在推送前定好。
- `TODO.md` 第 3 節更新進度。

## 0.39.006 — 2026-11-24：新文件 docs/new-characters.md (加一代角色照這份做)、TH07 卡牌稱號定案 (統整)
- **使用者**：「做的時候順便紀錄，下次不用每次都找程式碼跟資料庫」。
- **新增 `docs/new-characters.md`**：
  - 流程與分工：哪幾步要 grill、哪個 session 做什麼。
  - 要改的檔案：用假角色跑全部測試查的，每個檔案寫了沒改會怎樣。也列了不用改的地方，以及兩個坑：空卡池讓全收集拿不到、活動的 `rarity_weights` 會套到所有卡池。
  - 慣例：名字照萌娘百科、id、卡池、階級範圍比例。卡牌稱號是低 = 官方、中 = 其他作品、高 = 符卡或能力，9 字以內。
  - 查萌娘百科的方法。
  - TH07 11 位的資料：id 建議、關卡、種族、能力、各作品的官方稱號、33 張卡牌稱號。
- **TH07 第二輪定案**：33 張卡牌稱號 (使用者 2026-11-24)。愛麗絲的名字照萌娘百科是「瑪格特羅依德」，第一輪寫成「洛依德」，已更正。
- `CLAUDE.md` 文件樹加一列；`TODO.md` 第 3 節改成指向新文件，進度打勾。
- 順手修文件裡過時的地方：`README.md` 的 `GACHA_POOLS` 位置改成 `Utils/gacha_pools.py`，`docs/database.md` 的角色檔格式補上 `ura_class`、`base_stats` 不再是 0。

## 0.39.005 — 2026-11-24：🎪 活動限定卡池可以同時開好幾個 (筆電，玩法 session)
- TH07 派工第一件 (統整 session 轉達，使用者「都好」)：之後的春雪異變會開妖妖夢卡池，但紅霧異變不限時一直開著；原本 `game_rules` 只有一個 `gacha_event_pool`，後面的活動會蓋掉前面的 ➔ 兩個活動一起開時紅魔鄉卡池抽不到。
- `events.game_rules` 的 `gacha_event_pool` (單一) ➔ **`gacha_event_pools` `{卡池 key: 卡池}`**，每個進行中、有寫 `gacha.pool` 的活動各一個。卡池內容抽成 `events.event_pool(ev)` (game_rules、任務文字、`/admin-event` 共用)，多一個 `events` 欄位 = 開這個卡池的活動；兩個活動 `from` 同一個卡池 ➔ 只開一個，兩個活動都列進去。舊欄位整個拿掉 (不留相容)，讀它的地方全部改。
- 抽卡 (`gacha.py`)：`event_pools(rules)` 讀卡池；`resolve_pool("event")` 剛好一個 ➔ 那個，一個都沒有或好幾個 ➔ None。`execute_gacha` 選「🎪 活動限定卡池」時：一個 ➔ 直接抽 (跟以前一樣)；**好幾個 ➔ 先跳 `EventPoolPickerView` 選單** (卡池名稱 + 說明、價格，只有祈願的人能選，選了才扣錢；連點擋掉、賽錢不足選單留著可以再選、180 秒逾時換成提示)；`execute_gacha` 改成回傳有沒有抽 (選單用來判斷要不要停)。
- 結果畫面的「繼續祈願」改記**實際的卡池 key** (`th06` / `event_<id>`，原本記 `"event"`)：好幾個卡池時不用每次重選，活動結束了就抽不到 (不會跳到別的活動卡池、不扣錢)。舊畫面記著 `"event"` 的按鈕遇到好幾個卡池會跳選單。📊 機率表收到 `"event"` 又有好幾個卡池 ➔ 提示用 `/card history` 選。
- `/card history` 列出全部進行中的活動卡池 (機率表選單也是)；教學書抽卡章「🟢 現在的活動限定卡池」列全部，多一行說明「好幾個活動同時進行時先跳選單問要抽哪個，保底和任務各算各的」。
- 活動任務：`draw_gacha(quest_events=…)`，`gacha_event_pool` 只記給**開這個卡池的活動**；`from` 開的一般卡池 (紅魔鄉) 現在也算那個活動的 `gacha_event_pool` (原本只算 `event_<id>`，任務文字還會提示「還沒有活動限定卡池」)。任務文字改成「在「<卡池名>」祈願 N 抽」。`gacha_pool:<卡池>` 照舊記給全部進行中的活動。
- `/admin-event`：`pool_close_text()` 統一「卡池也會跟著關」的提示，`characters` 卡池也會提 (原本只提 `from`)；別的還在進行 (而且不會結束) 的活動也開同一個卡池時不提。`/admin-event end` 讀當下規則算出這種卡池。
- 文件：`events.game_rules` 說明表、`Events/README.md` (卡池兩行、任務 `gacha_event_pool`)、`docs/cogs.md` 補一條。
- 測試：新的 `tests/test_event_pools_multi.py` (34 項：兩個假活動同時進行 (一個 `from: th06`、一個 `characters`，只在測試裡換掉 `load_events`，不放進 `Events/`) ➔ 跳選單不扣錢、別人選不了、連點只抽一次、兩個卡池都抽得到、保底各記各的、任務各算各的、賽錢不足、逾時、舊按鈕、機率表、history、教學書、`/admin-event` 提示；只剩一個活動 ➔ 直接抽、結束的卡池按繼續祈願抽不到也不扣錢)。改 `test_event_slots` (兩個活動都開、同一個 `from` 只開一個)、`test_pools`、`test_pity`、`test_event_schedule`、`test_event_quests` (紅霧異變的 `gacha_event_pool` 任務文字) 跟著新欄位。
- 還沒處理 (回報統整)：`gacha.rate_up` / `rarity_weights` 還是所有進行中的活動合在一起套用到每個卡池 (春雪異變的機率調整也會影響紅魔鄉卡池)。

## 0.39.004 — 2026-11-24：TODO.md 記下 TH07 妖妖夢第一輪定案 (統整)
- `TODO.md` 第 3 節：妖妖夢卡池只在活動期間開放、活動卡池要能同時開好幾個 (派給遊戲設計 session)、做的順序 (角色檔 ➔ 卡面 / 名片 ➔ 春雪異變)、11 位名單 (騷靈三姊妹 3 張、愛麗絲另開 `alice_th07`)、33 張卡的階級範圍、還沒定的項目，以及加一代角色要動的地方。
- **怎麼查到要動哪裡**：在統整 worktree 放一位假角色 + 妖妖夢卡池跑全部測試，壞掉的是裏世界符卡 (單卡詳情、裏世界引擎直接 KeyError)、卡池稱號、寫死的 24 位角色；查完已還原。另外發現**空卡池**會讓「幻想鄉緣起」(所有卡池全收集) 永遠拿不到，所以卡池要跟角色檔一起加。
- 第 0 節「下一步建議」的 TH07 改成進行中。

## 0.39.003 — 2026-11-24：docs：TODO.md 進度更新到 0.39.002 (筆電，統整 session)
- `TODO.md` 第 0 節進度更新到 0.39.002：抽卡 (自動合成、單卡詳情)、前期經濟定案 (起步 5 萬、🏮 人里打工、裏世界 BOSS 報酬照區域縮放方案 B、目標「第 1 天出征、第 2～3 天第一張 UR」)、裏世界 0.37.006～0.37.008 的調整、哪些還沒在正式機器人上試過；下一步建議第 1 項改成實機試玩新玩家流程。
- 0.1 玩法表補 `/shrine job`、自動合成、`/ura bestiary`、教學書；0.2 賽錢來源補起步金 5 萬、人里打工、裏世界 (BOSS 縮放)、裏世界商店花費、一般玩家一天的收入。
- 坑：統整 session 的 worktree 放在 Temp 資料夾，關機重開後被系統清掉 1,001 個檔案 (大多是圖片)。都是 git 追蹤的檔案、沒有未推的內容，`git checkout -- .` 還原。

## 0.39.002 — 2026-11-23：👹 裏世界 BOSS 報酬照區域縮放 (第 1 區少、越深越多) (筆電，玩法 session)
- 前期經濟調整第 2、3 題：模擬幾組倍率給使用者選，使用者「全部照建議」= 方案 B、前期目標改成「第 1 天就能出征、第 2～3 天抽到第一張 UR」、這次只動 BOSS (一般戰鬥、寶箱不動)。
- 模擬 (`week_sim.py`，一般玩家：起步 50,000、神社一天 2 次、簽到、人里打工 2 萬、裏世界第 1 區 3 局、有錢就抽)：
  - BOSS 一隻平均 (賽錢 + 寶物賣價) 第 1 / 3 / 5 / 8 區：現狀 2.8 萬 / 3.0 萬 / 3.1 萬 / 3.4 萬 ➔ B 0.9 萬 / 2.1 萬 / 3.1 萬 / 4.1 萬；第 1 區一整局中位約 4.1 萬 ➔ 2.2 萬。
  - **神社才是主要收入** (一天 2 次 9～15 萬)：不管 BOSS 怎麼調，第一張 UR 都在第 2～3 天；神社砍到一天 2 萬、最重的方案也要第 5 天 ➔ 「一週」只靠 BOSS 達不到，使用者同意改目標。第 1 天就能出征約 9 成。
- `rules.BOSS_MONEY_SCALE = (0.3, 0.175)`：區域 BOSS 賽錢 × (0.3 + 0.175 × (區 − 1)) ➔ 第 1 區 3,000～4,500、第 5 區 10,000～15,000 (原本)、第 9 區 17,000～25,500，之後照樣變多。`rules.BOSS_TREASURES_EARLY`：寶物第 1 區 1～2 個、第 2 區 2～3、第 3 區 2～4，第 4 區起照原本 3～5。`run.foe_loot` 用 `rules.boss_money_mult` / `boss_treasure_range`；🎪 活動 BOSS、寶箱怪不縮放。
- 教學書裏世界那本「🎒 背包與戰利品」的 BOSS 那行改成逐區列出 (從常數算)；`tests/test_guide.py ura` 過。`docs/ura.md` 補一段 (含模擬結論和新目標)。
- 測試：`test_ura_engine.py` 第 1 / 3 / 5 / 9 區 BOSS 各掉 300 次，賽錢都在範圍裡、寶物個數最少 / 最多剛好是範圍兩端、法具一定 1 個；活動 BOSS 照舊 10,000～15,000。

---

## 0.39.001 — 2026-11-23：🏮 人里打工、新手起步 50,000 (筆電，玩法 session)
- 統整 session 跟使用者 grill 定案 (人里打工「照修正版」、前期經濟第 1 題「都好」)。裏世界 BOSS 報酬照區域縮放還在等使用者選數值，這次沒動。
- 🏮 **人里打工** (`/shrine job`，神社主畫面「🗺️ 採集」旁邊多一顆「🏮 人里打工」)：花 `JOB_STAMINA = 100` 體力 ➔ `JOB_REWARD = 10,000` 賽錢 (固定，不吃神社效率)，**每天最多 `JOB_DAILY_LIMIT = 2` 次** (台灣時間 00:00 重置，跟體力道具同一套 `tw_day`)。
  - 資料層 `Economy_DB_Manager.do_job`：一個交易 (`BEGIN IMMEDIATE`) 結算體力 ➔ 檢查今天次數和體力 ➔ 扣體力、加錢、次數 +1、`player_stats` 記 `job`；失敗什麼都不改 (reason `daily_limit` / `stamina`)。users 新欄位 `job_day` / `job_used` (init_db 自動補)。
  - 活動倍率預留位 `modifiers.job_reward` (`events.MODIFIER_KEYS`、`shrine_components.MODIFIER_NAMES`「人里打工的工錢」)。
  - 畫面 (mode `job`，`build_job_container`)：體力、今天還能打幾次；按鈕「🏮 花 100 體力 ➔ 10,000 賽錢 (今天還能 N 次)」，打完或體力不夠反灰並寫原因；「⚡ 恢復體力」(共用 `Utils/stamina_modal.py`)、「🏠 返回神社」。
  - 教學書神社那本「🧺 採集與體力」補一段 (數字從常數讀)，`/shrine job` 寫進那章的 commands；`docs/cogs.md` 補一條。
- 💰 **新玩家起步 1,000 ➔ 50,000** (`User_DB_Manager.STARTING_MONEY`，10 抽)：`_ensure_user` 建立玩家時直接寫入 (舊的 Users.db 欄位預設還是 1000，SQLite 改不了欄位預設)；已經有資料的玩家不補。
- 測試：新的 `tests/test_job.py` (體力剛好 100 / 99、第 3 次被擋、台灣時間 23:59 ➔ 00:00 換日、活動倍率、一起送 3 次只成功 2 次、體力只夠 1 次時一起送 2 次只成功 1 次、從滿的掉下來開始計時、神社畫面按鈕 / 反灰 / 原因、`/shrine job`)。`test_economy.py` 查新玩家 50,000 (舊資料表預設 1000 也一樣)；原本照起步 1,000 算的測試改用 `udm.STARTING_MONEY` 或在測試裡設回 1,000 (`test_pity` / `test_v2` / `test_leaderboard`)；`test_help.py` 神社子指令 6 ➔ 7。

---
## 0.39.000 — 2026-11-23：🔍 單卡詳情改版 (角色資料、這張卡的實力、特殊能力、價值、狀態、📖 角色圖鑑) (筆電，抽卡 session)
- 統整 session 轉來，grill 5 題都照建議 (使用者回「都好」)。使用者原話：「看卡冊的詳細資料也要使用類似characters那樣的詳細資料 目前能看的只有這些」；舊版只有角色名稱、稀有度、專屬稱號、完整度品相、ID、獲得時間。
- **單卡詳情分段** (`gacha_components.build_card_detail_container(card, user_name, thumbnails, info)`)：
  - 卡片：角色、階級、這張卡的稱號、完整度品相。
  - 📜 角色資料：角色稱號、種族、能力、簡介 (讀 `Characters/`)。簡介超過 `DETAIL_DESC_MAX = 300` 字截斷，結尾寫「…完整介紹看📖 角色圖鑑」。
  - ⚔️ 這張卡的實力：HP / ATK / DEF、職業，用 `Database/ura/combat.make_member` 算，跟裏世界出征一模一樣；能不能出征看 `rules.MIN_COMPLETENESS`。
  - ✨ 這張卡的特殊能力：只寫這個階級那一檔 (I / II / III)。效果用 `describe.spell_text`，B 點和冷卻用出征時的值 (完整度 > 0.8 冷卻比平常短，會寫出來)。
  - 💹 價值：分解能拿多少 (`econ.card_value(市值, 完整度, 活動分解倍率)`，跟 `/market decompose` 一樣)。
  - 🗂️ 卡牌資訊：ID、取得時間、狀態。狀態是 🔒 收藏中 / 🌀 出征中 / ⚗️ 同角色同階級還有幾張能一起合成 / 🔮 完美卡幾張、能不能融合 其中一種。
- **📖 角色圖鑑按鈕**：另開一則 ephemeral 的 `/character` 角色頁 (`send_character_page()`)。用 `importlib` 在按的時候取 `character_components.build_character_container`，Cog 之間不互相 import；收集進度是按的人自己的。
- **三個地方一起換新版**：卡冊單卡、收藏冊單卡、管理員看別人卡冊。管理員那個本來就是同一個 `InventoryView`，看得到出征中的卡。
- 程式：`gacha.card_detail_info(card, owner_id)` 在選卡的 callback 裡先算好 (要讀市值和卡冊)，畫面 `build()` 照舊是同步的。SP 類型名稱 (⚔️ 傷害…) 跟角色頁同一份 `SP_TYPE_NAMES`。
- 文件：教學書抽卡那本第 2 章 (`guide/card.py` 的 `_album`) 的「🔍 單卡詳情」；`docs/cogs.md` 卡冊那段。
- 測試：新的 `tests/test_card_detail.py`。
  - 24 位角色 × 每個階級 × 5 種完整度全部畫一次 (含按鈕列 ≤ 40 元件、≤ 4000 字)；HP / ATK / DEF、能不能出征、B 點、冷卻、效果都跟 `make_member` 算的一樣。
  - 角色資料、只寫這一檔的特殊能力、價值、不能出征、簡介截斷。
  - 四種狀態 (出征中那張不算在可以一起合成的張數裡)。
  - 卡冊本人 / 管理員 / 收藏冊三個畫面的按鈕；📖 開出 ephemeral 角色頁、原本的畫面不變；找不到角色時的提示。
  - 標題保留「🎴 卡牌鑑定詳情：」、狀態保留「🔒 收藏中」的寫法 (`test_inventory.py` / `test_album.py` 照舊過)。全部測試 10,885 項過 (`python tests/run_all.py`)。

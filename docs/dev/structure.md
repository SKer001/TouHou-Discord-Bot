# 🗂️ 專案結構（docs/dev/structure.md）

> 專案是什麼、每個資料夾與檔案是做什麼的、環境上的注意事項。要找東西放在哪裡、新增或搬動檔案時讀。
> 新增 / 搬動 / 刪除檔案後記得回來更新這份 (最後對照實際檔案：2026-11-24，版本 0.40.001)。
> 程式怎麼分層、怎麼寫 ➔ `ARCHITECTURE.md`；所有文件的目錄 ➔ `docs/README.md`。

## 1. 專案概觀

- 繁體中文的「東方 Project」主題 Discord 機器人。
- **套件**：`discord.py` (**需要 >= 2.6**，因為用了 Components V2；目前用 2.7.1)、`aiosqlite`、`python-dotenv`、`Pillow`。安裝：`pip install -r requirements.txt`。
- **兩台開發電腦** (各有一份 clone，靠 GitHub 同步；2026-11-11 確認兩台的 discord.py 2.7.1、aiosqlite 0.22.1 一樣)：

  | | Python | Pillow | 顯示卡 |
  |---|---|---|---|
  | 筆電 | 3.11.9 | 11 | RTX 4060 Laptop 8GB |
  | 桌機 | 3.14.0 | 13 | RTX 5060 Ti 16GB (2026-11-12 換，生圖約筆電 2 倍快；兩台可以分工做卡面，見 `docs/art/card-art.md`) |

- **功能**：抽卡 (gacha)、卡冊 / 收藏冊、卡牌合成 / 融合、道具背包、角色圖鑑、個人資料卡 + 每日簽到 + 運勢、玩家稱號與角色名片、神社經營 (採集 / 料理 / 招待)、市場與交易、活動與活動任務、主動通知 (DM)、排行榜、📚 教學書、🌀 裏世界探索、管理員指令、日誌。各功能的規則見 `docs/gameplay/cogs.md`、`docs/gameplay/ura.md`。
- **Repo 是公開的** (GitHub：SKer001/TouHou-Discord-Bot)，分支 `main`；雲端正式機器人跑 `online` 分支 (見 `docs/dev/deploy.md`)。
- **圖片**以 `raw.githubusercontent.com` 連結提供：
  - 剛 push 的圖片可能要等一下 GitHub 才抓得到 (曾出現「載入圖片失敗」，實為 GitHub 延遲)。
  - **Discord 會依網址快取圖片**：卡面重做後檔名不變的話 Discord 會一直顯示舊圖，所以 `tools/card_art/build_cards.py` 寫進 `images/Thumbnails.json` 的網址會帶 `?v=<檔案雜湊>` (2026-10-31)，圖一改網址就變。名片、參拜客頭像也是同樣做法。

## 2. 目錄樹

### 2.1 根目錄
```
Main.py              入口；setup_hook 先 init_db() 再 init_item_db()，並自動載入 Cogs/load-*/ 下所有 .py
README.md            給人看的專案說明 (功能、指令、安裝、新增角色)
CLAUDE.md            給 AI 助手的一頁入口：最重要的規則 + 文件樹 (細節都在 docs/)
ARCHITECTURE.md      程式架構與寫法規則 (分層、Cog / View / 資料層慣例、新增功能檢查清單)
TODO.md              待做清單與目前進度
CHANGELOG.md         開發紀錄：版本號規則 + 最近幾個版本做了什麼、遇到的問題與解法 (更早的在 docs/changelog/)
requirements.txt     套件清單
.env                 設定 (不進 git，見第 3 節)
.claude/settings.json  Claude Code 的專案設定 (外掛 skill 開關，見 docs/handbook/skills.md)
```

### 2.2 `Characters/`：角色資料
```
Characters/<分類>/<角色id>.json   一角色一檔；圖鑑、卡池、裏世界都讀這裡 (格式見 docs/dev/database.md)
  Main/    主要主角 (靈夢、魔理沙)
  TH01/ ~ TH07/   各代角色 (TH07 = 妖妖夢，2026-11 新增)
```
- 哪個資料夾屬於哪個卡池，定義在 `Utils/gacha_pools.py`。新增一代角色照 `docs/dev/new-characters.md`。

### 2.3 `Database/`：資料層
```
User_DB_Manager.py     玩家資料庫 (Users.db) 的入口；實作在 users/，外面一律從這個檔匯入 (改 DB_PATH 也是改這個檔的)
users/                 👤 玩家資料庫的實作 (1.00.002 從 User_DB_Manager.py 拆出來；依賴順序 schema ➔ core ➔ titles ➔ cards)
  schema.py            🧱 資料表結構與初始化：DB_PATH、SCHEMA_STATEMENTS、connect、_ensure_user、init_db
  core.py              👤 玩家資料、💰 貨幣經驗、📅 每日簽到、🎒 背包道具、🏆 排行榜與隱私、tw_day、📊 玩家統計、🎪 活動任務計數、⚡ 體力
  titles.py            🏷️ 稱號、🖼️ 角色名片
  cards.py             🎴 抽卡：卡牌與統計、🛠️ 管理員卡冊操作
Item_DB_Manager.py     道具資料庫 (Item.db) 所有存取
Economy_DB_Manager.py  經濟系統的入口 (神社、採集 / 料理 / 雜貨店 / 招待、活動狀態、浮動市值、分解、市場、轉帳)，資料也在 Users.db；實作在 economy/，外面一律從這個檔匯入
economy/               💹 經濟系統的實作 (1.00.001 從 Economy_DB_Manager.py 拆出來；數值常數在各檔開頭)
  common.py            神社經營的數值常數、_dt / modifier / economy_meta 小工具
  event_state.py       🎪 活動狀態 (排程 / 開始 / 結束)、get_rules、手續費倍率快取
  shrine.py            ⛩️ 神社經營：賽錢箱、清潔度、妖怪、參拜客
  gather.py            🏮 人里打工、🗺️ 採集 / 🍳 料理 / 🏪 雜貨店 / 🍵 招待、🧺 快速採集
  market_value.py      💹 浮動市值：每日結算、查價、交易紀錄
  market.py            ♻️ 分解、🏪 市場、💸 轉帳
Quest_DB_Manager.py    📜 活動任務：進度、領取、永久活動稱號 (任務定義在活動檔)
Notify_DB_Manager.py   🔔 主動通知 (DM)：玩家開關、已發送紀錄、「要發哪些通知」的判斷
Ura_DB_Manager.py      🌀 裏世界的資料存取 (進行中的一局 ura_runs、倉庫、額外背包、紀錄、怪物圖鑑領獎 ura_bestiary_claims、出征鎖 gacha_cards.expedition)
events.py              讀 Events/*.json，把進行中的活動跟 shrine_data 合併成當下規則 (game_rules)
shrine_data.py         神社的遊戲資料：素材、料理配方、採集地點與事件、雜貨店價格、參拜客 (最愛、提示、台詞)
title_data.py          🏷️ 玩家稱號 (純資料)：名稱、等級、說明、解鎖條件
namecard_data.py       🖼️ 角色名片的名稱與說明 (純資料)
notify_data.py         🔔 通知種類登記表 (純資料)
Users.db / Item.db     SQLite 檔 (開發階段 Users.db 也刻意推上 git，見 docs/handbook/workflow.md 第 5 節)
item.new.json          道具批次匯入用資料
backups/               備份 (不進 git)
ura/                   🌀 裏世界探索的遊戲引擎 (純邏輯，不 import discord、亂數由呼叫端注入)
  rules.py / status.py / combat.py / run.py   規則、狀態、戰鬥、一局的流程
  fest.py              🎪 活動關卡：活動門、環境、活動 BOSS、活動保留格、活動法具
  bestiary.py          📖 怪物圖鑑：分區、解鎖、全收獎勵
  describe.py          職業特性、符卡、法具效果的白話說明 (🔍 查看詳情與 tools/ura_roster.py 共用)
  data.py              讀 ura/data/*.json (讀一次快取)，並把活動檔的 ura 區塊併進來
  data/*.json          資料檔：enemies 敵人、statuses 狀態、spells 符卡、items 道具、relics 法具、treasures 寶物、events 事件、zones 區域
```
- 裏世界的活動內容寫在 `Events/*.json` 的 `ura` 區塊；設計用模擬 `tools/ura_sim/spells.py` 直接呼叫這個引擎。
- 資料表與函式說明見 `docs/dev/database.md`。

### 2.4 `Events/`：活動資料
```
Events/README.md              活動檔格式與所有預留位
Events/th06_scarlet_mist.json 紅霧異變 (一個活動一檔)
```

### 2.5 `Cogs/`：指令
```
load-character/  character.py                                   圖鑑 /character
                 Components/character_components.py
load-gacha/      gacha.py, Admin-gacha.py                       抽卡 / 卡冊 / 合成 / 融合 / 卡冊管理
                 Components/gacha_components.py
                 logic/rules.py, detail.py                      gacha.py 只留 GachaCardSys 指令；規則拆在這裡 (卡池資料 + 祈願 / 合成 / 融合規則 + 機率表的資料 / 單卡詳情的資料)
                 views/synthesis.py, inventory.py, result.py    畫面 (View) 拆在這裡 (合成確認 + 選卡 / 卡冊 + 收藏冊 + 角色圖鑑頁 / 抽卡結果 + 活動卡池選單 + 祈願紀錄 + 機率表)；gacha.py 把名字全部轉出去
load-market/     market.py, Admin-market.py                     市值 / 分解 / 市場
                 Components/market_components.py
load-general/    profile.py, help.py, shrine.py, event.py, trade.py, leaderboard.py, notify.py
                 Admin-item.py, Admin-user.py, Admin-shrine.py, Admin-event.py, Admin-trade.py
                 Components/general_components.py, shrine_components.py, trade_components.py,
                            quest_components.py (活動任務), notify_components.py (通知),
                            help_components.py, guide_components.py
                 Components/guide/<分類>.py                     📚 教學書，一個分類一本 (card / event / market / profile / shrine / ura)
load-ura/        ura.py                                         🌀 裏世界探索 /ura (explore / resume / abandon / shop / inventory / status / bestiary / help)
                 Components/ura_components.py
                 views/common.py, run.py, setup.py,             ura.py 只留 UraCog 指令；畫面 (View) 拆在這裡，ura.py 把名字全部轉出去
                       shop_storage.py, bestiary.py             (共用小工具 / RunView / 選隊伍 + 整裝 / 商店 + 倉庫 / 怪物圖鑑)
load-system/     Admin-sys.py                                   /admin-sys reload / sync / shutdown
```
- `Main.py` 會把 `Cogs/<資料夾>/<檔名>.py` 以 `Cogs.<資料夾>.<檔名>` 載入；Cog 內可用相對匯入如 `from .Components.x import ...` (命名空間套件)。
- **載入器會載入 `Cogs/load-*/` 第一層的每一個 .py**：舊檔殘留會讓載入失敗；不是 Cog 的共用程式放 `Components/` 子資料夾 (畫面內容)、`views/` 子資料夾 (從大 Cog 檔拆出來的 View 類別：`load-ura/`、`load-gacha/`)、`logic/` 子資料夾 (從大 Cog 檔拆出來的純規則：`load-gacha/`) 或專案根的 `Utils/`。
- 畫面產生器的資料夾與檔名一律叫 `Components` / `*_components.py` (舊名 `Embeds` / `*_embeds.py` 已全部改掉)。畫面寫法見 `docs/dev/components-v2.md`。

### 2.6 `Utils/`：跨 Cog 共用工具
```
version.py         目前版本號 VERSION (開機時印在主控台與 log 頻道)
config.py          .env 設定：ADMIN_IDS 與 is_admin(user)、SHOW_UNRELEASED (未公開卡池開關)
components.py      共用的 Components V2 通知工具 (send_notice 等)
pagination.py      📄 共用分頁：paginate() / nav_buttons() / 跳頁彈窗 (卡冊、市場、任務、稱號選單…都用它，不要另寫)
picker.py          共用控制台 GroupPickerView：分組選單 ➔ 選項選單 (翻頁) ➔ 按鈕 (+ 預覽)；管理員稱號 / 名片、玩家修改稱號 / 名片都用
numbers.py         金額顯示 fmt_money() (一萬以上縮寫 1.5M / 12.35M，以下 5,000；2026-11-14 使用者定)：持有 / 餘額 / 累計 / 排行榜都用它；價格、花費、獎勵要看確切數字的照舊 f"{n:,}"。不要另寫縮寫
gacha_pools.py     🎰 卡池定義與卡池成員 (抽卡與卡池收集稱號共用)；新增卡池在 ALL_GACHA_POOLS 加一筆 ("released": False = 還沒公開，GACHA_POOLS 不含它)
character_data.py  Characters/ 載入器：load_categories() / load_characters()，壞檔印警告並略過
card_cache.py      🗂️ 卡冊快取 (只給 autocomplete 用；真正執行指令一律直接讀資料庫)
thumbnails.py      Thumbnails.json 共用讀取 load_thumbnails() / thumbnail_url() (/help 等使用；部分 Cog 還有各自的舊寫法)
namecards.py       🖼️ 角色名片的圖片網址與原圖下載 (讀 images/Namecards.json、NamecardOriginals.json)
guide.py           📚 教學書入口 open_guide()：各指令群組的 help 子指令 (/card help、/ura help…) 呼叫它
stamina_modal.py   ⚡ 恢復體力彈窗 (/profile 與神社採集畫面共用；每天最多吃 3 個體力道具)
reloader.py        模組重載 (/admin-sys reload 與主控台共用)；拆成套件的資料層照 PACKAGE_ORDER、Cog 的 logic/ 與 views/ 照 VIEW_ORDER 的順序重載
console.py         主控台指令：機器人執行中可在終端機輸入 help / status / reload / sync / money / stamina / shutdown
auto_handoff.py    ☁️ 本機 ⇄ 雲端自動交接：Main.py 開機前 take、關機後 release；雲端上什麼都不做 (docs/dev/deploy.md 4.1)
```

### 2.7 `Logger/`
```
Logger/Logger.py   日誌與錯誤回報 (需要 .env 的 LOG_CHANNEL_ID)
Logger/Logs/       日誌檔 (不進 git)
```

### 2.8 `images/`：圖片
```
Thumbnails.json          {"角色id_階級": URL, "角色id": URL, "guest_<種類>": URL, ..., "fill": 預設圖URL}
Thumbnails/              Discord 用的卡面縮圖 (460×640)：<角色id>_<階級>.png (有動態特效的階級是 .gif)、guest_<種類>.png 參拜客頭像、fill.png
Namecards.json           {"角色id": 名片網址}
NamecardOriginals.json   名片原圖在私人頻道的訊息 id (機器人靠它找原圖)
Namecards/               Discord 顯示用的名片 <角色id>.jpg (原圖不進 repo)
Original/Art/            沒有加框的角色原圖 <角色id>_<階級>.png (ComfyUI 生成、使用者挑選)
Original/<分類>/<角色id>/<階級>/   高清分層卡面的各步驟圖 (分類 = Main、TH01 ~ TH06；16 倍的 *_hd.png 太大，只留本機)
Original/Guests/         參拜客頭像原圖 <種類>.png
Original/Thumbnails/     fill.png 原圖、empty_greenscreen.jpg (使用者給的綠幕卡框，736×1024)、empty_greenscreen_hd.png (AI 放大版)、empty.png (去背後的空白卡框)
```
- 卡面、頭像、名片怎麼做見 `docs/art/card-art.md`。

### 2.9 `tools/`：開發工具 (不會被機器人載入)
```
botcli.py          指令列測試工具：假裝打指令、點按鈕、選選單；--live 會把畫面真的送到測試頻道
discord_peek.py    用機器人 Token 讀測試頻道最新訊息，把實機 V2 畫面印成文字
discord_rest.py    上面兩個工具共用的 Discord REST 小工具 (只用 REST，不連 Gateway)
ura_roster.py      🌀 產生 docs/gameplay/ura_roster.md，並同步角色檔的特殊能力說明
ura_sim/spells.py  🌀 裏世界設計用模擬 (直接呼叫 Database/ura 引擎)；combat.py 是過時的舊版，留著對照
ura_sim/th07/      🌸 TH07 定案前的數值模擬腳本 (th07_sim4.py 為主；說明在 docs/handbook/sessions.md 8.2；輸出 out/ 不進 git)
card_art/          卡面產生工具 (ComfyUI 生圖 ➔ 蓋卡框 ➔ 寫字 ➔ 縮圖)
  build_cards.py / card.py / candidates.py / make_workflow.py / make_empty.py / make_rarity.py / animate.py   卡面
  layered/         高清分層流程 (hd_card.py 為主；彈幕、翅膀、去背、補畫、PhotoCraft 等各一支)
  build_guests.py / guest_workflow.py   參拜客頭像
  build_namecards.py / upload_namecard.py   角色名片 (壓縮顯示版、原圖上傳私人頻道)
  fonts/ rarity/   字型 (HarukazeSolid.ttf 授權限制，不進 git)、等級圖 (rarity_greenscreen.jpg 是等級圖的綠幕原圖)
```
- 測試工具用法見 `docs/dev/testing.md`；卡面工具見 `docs/art/card-art.md`。

### 2.10 `tests/`、`deploy/`、`docs/`
```
tests/run_all.py + test_*.py   測試：python tests/run_all.py (自動找所有 test_*.py)，見 docs/dev/testing.md
deploy/                        雲端部署，見 docs/dev/deploy.md
  vm_ctl.py                    VM 上的控制腳本 (更新、備份、交接)
  handoff.py                   本機 ⇄ 雲端交接 (take / release / deploy)
  install.sh, systemd/, requirements.lock.txt, gcs-lifecycle.json
docs/README.md                 所有文件的總目錄
docs/handbook/                 怎麼在這個專案工作 (workflow.md 工作手冊、sessions.md 各角色的交接、skills.md 外掛 skill)
docs/gameplay/                 玩法與數值 (cogs.md、ura.md、ura_roster.md)
docs/dev/                      開發 (這份、components-v2、database、testing、new-characters、deploy、setup、history)
docs/art/                      美術 (card-art.md)
docs/changelog/                舊的開發紀錄 (0.38 以前，依版本分檔)
```

## 3. `.env` 與不進 git 的東西

`.env` 不進 git，**換電腦 (或開新的 worktree) 要手動複製**。

| 變數 | 用途 |
|---|---|
| `DISCORD_TOKEN` | 機器人 Token (必填) |
| `LOG_CHANNEL_ID` | 日誌頻道 (必填，`Logger/Logger.py`) |
| `ADMIN_IDS` | 管理員的 Discord 使用者 ID，逗號分隔；沒設定時所有管理員指令都不能用 |
| `NAMECARD_CHANNEL_ID` | 名片原圖的私人頻道 (2026-11-14 起) |
| `TEST_CHANNEL_ID` | (選填) 實機測試頻道；沒設定時測試工具用 `LOG_CHANNEL_ID` |
| `SHOW_UNRELEASED` | (選填，開發用) 設 `1` 看得到還沒公開的卡池；正式機器人不要設。測試與開發工具 (`tools/botcli.py`、`tools/ura_roster.py`、`tools/ura_sim/`、`tools/card_art/build_namecards.py`) 自己會打開。`deploy/handoff.py push-env` 上傳時會自動濾掉 (1.00.000) |
| `GCP_PROJECT`、`GCP_BUCKET`、`GCP_ZONE`、`GCP_VM` | 雲端交接 `deploy/handoff.py` 用 (前兩個必填才能交接；本機 `python Main.py` 沒有這兩個會拒絕啟動)，見 `docs/dev/deploy.md` |
| `SKIP_HANDOFF` | (選填，只在雲端壞掉時用) 設 `1`：本機開機不跟雲端交接、關機也不交回。雲端還在跑的話會兩邊同時上線。`push-env` 不會傳上雲端 |

`.gitignore` 裡的東西 (每台電腦各自有，不會同步)：`/.env`、`/Logger/Logs/`、`__pycache__/`、`/.vscode`、`/.botcli/`、`/Database/backups/`、`/card_stages/`、`/tools/card_art/fonts/HarukazeSolid.ttf`、`/images/Original/**/*_hd.png`、`/images/Original/**/_old_*/`、`/images/Original/Namecards/`、`/tools/ura_sim/th07/out/`、`/.mcp.json` (含本機路徑)、`/.codegraph/` (程式碼索引)。

## 4. 環境注意事項

- **換行符為 LF**：Windows 上 `core.autocrlf=true`，工作目錄可能是 CRLF，git 內部仍是 LF。新檔與修改都保持 LF。
- **Windows 主控台是 cp950**，印 emoji 會 `UnicodeEncodeError`：執行 Python 時設 `PYTHONIOENCODING=utf-8`。例如 PowerShell：`$env:PYTHONIOENCODING = 'utf-8'; python Main.py`。
- **機器人同一時間只在一台上執行** (同一個 Token)；雲端上線後本機要跑正式 Token 前先做交接，見 `docs/handbook/workflow.md` 第 6 節。
- **程式碼索引 CodeGraph** (選用)：安裝見 `docs/dev/setup.md`；筆電已裝，桌機還沒裝。改了很多檔案後可以跑 `codegraph sync` 更新索引。

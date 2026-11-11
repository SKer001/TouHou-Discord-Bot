# TouHou-Discord-Bot — 專案交接文件（給 Claude Code）

> 這份文件整理了先前對話中對本專案的所有理解與決策。放在專案根目錄命名為 `CLAUDE.md`，Claude Code 啟動時會自動載入。
> 專案在**筆電與桌機兩台電腦**上各有一份 clone，靠 GitHub 同步；對話紀錄與 Claude 記憶不會跨電腦，**重要的背景與決策都要寫進這份文件**。
> 使用者慣用**繁體中文**溝通；回覆請簡潔、用繁體中文，不要貼一堆網址。
> **程式架構與寫法規則（Cog 怎麼分、畫面 / 資料層怎麼寫、新增功能檢查清單）在 `ARCHITECTURE.md`，新增功能前先讀。**

## 📚 文件樹（先看這張表，只讀跟這次工作有關的）
| 要做什麼 | 讀這份 |
|---|---|
| 新增 / 修改功能前 | `ARCHITECTURE.md`（分層、寫法、新增功能檢查清單） |
| 指令、玩法規則、數值 (抽卡、神社、經濟、市場…) | `docs/cogs.md` |
| 資料表、資料庫函式、道具、角色檔格式 | `docs/database.md` |
| 卡面 / 頭像生圖、ComfyUI、PhotoCraft | `docs/card-art.md` |
| 跑測試、botcli、實機驗證 | `docs/testing.md` |
| 活動檔格式與預留位 | `Events/README.md` |
| 待做、目前進度 | `TODO.md` |
| 每個版本做了什麼、踩過的坑 | `CHANGELOG.md`（最上面幾筆就好） |
| 早期重構歷程 | `docs/history.md` |
| CodeGraph 安裝 | `docs/setup.md` |
| 找程式碼 | 先用 CodeGraph（`codegraph_explore`），不要整份檔案讀 |

## 1. 專案概觀
- 繁體中文的「東方 Project」主題 Discord 機器人，使用 `discord.py`（**需要 >= 2.6**，因為用了 Components V2；目前用 2.7.1）、`aiosqlite`、`python-dotenv`、`Pillow`。Python 3.11。
- 功能：抽卡（gacha）、卡冊、卡牌合成 / 融合、道具背包、角色圖鑑、個人資料卡 + 每日簽到 + 運勢、管理員指令、日誌。
- Repo 是**公開**的（GitHub：SKer001/TouHou-Discord-Bot），分支 `main`。圖片以 `raw.githubusercontent.com` 連結提供，剛 push 的圖片可能要等一下 GitHub 才抓得到（曾出現「載入圖片失敗」，實為 GitHub 延遲）。**Discord 會依網址快取圖片**：卡面重做後檔名不變的話 Discord 會一直顯示舊圖，所以 `build_cards.py` 寫進 Thumbnails.json 的網址會帶 `?v=<檔案雜湊>`（2026-10-31），圖一改網址就變。

## 2. 專案結構（目前狀態）
```
Main.py                      入口；setup_hook 先 init_db() 再 init_item_db()，並自動載入 Cogs/load-*/ 下所有 .py
README.md                    給人看的專案說明 (功能、指令、安裝、新增角色)
CHANGELOG.md                 開發紀錄：版本號規則 + 每個版本做了什麼、遇到的問題與解法
Utils/version.py             目前版本號 VERSION (開機時印在主控台與 log 頻道)
TODO.md                      待做清單：UR/LR 重做、未做卡面的角色、TH07 之後的角色、經濟系統計畫
ARCHITECTURE.md              程式架構與寫法規則 (分層、Cog / View / 資料層慣例、新增功能檢查清單)
requirements.txt             套件清單：pip install -r requirements.txt
tests/                       測試 (python tests/run_all.py)，見 `docs/testing.md`
tools/botcli.py              指令列測試工具：假裝打指令、點按鈕、選選單；--live 會把畫面真的送到測試頻道，見 `docs/testing.md`
tools/discord_peek.py        用機器人 Token 讀測試頻道最新訊息，把實機 V2 畫面印成文字，見 `docs/testing.md`
tools/discord_rest.py        上面兩個工具共用的 Discord REST 小工具 (只用 REST，不連 Gateway)
tools/card_art/              卡面產生工具 (ComfyUI 生圖 → 蓋卡框 → 寫字 → 縮圖)，見 `docs/card-art.md`
Characters/                  角色資料，一角色一檔：Main/ (主要主角)、TH01/ ~ TH06/ (各代)；圖鑑與卡池都讀這裡
Database/
  User_DB_Manager.py         玩家資料庫（Users.db）所有存取
  Item_DB_Manager.py         道具資料庫（Item.db）所有存取
  Economy_DB_Manager.py      經濟系統（神社、採集 / 料理 / 雜貨店 / 招待、活動狀態、浮動市值、分解、市場、轉帳），資料也在 Users.db；所有數值常數都在檔案開頭
  shrine_data.py             神社的遊戲資料：素材、料理配方、採集地點與事件、雜貨店價格、參拜客 (最愛、提示、台詞)
  events.py                  讀 Events/*.json，把進行中的活動跟 shrine_data 合併成當下規則 (game_rules)
Events/                      活動資料檔，一個活動一檔 (th06_scarlet_mist.json = 紅霧異變)；README.md = 格式與所有預留位
  Users.db / Item.db         SQLite 檔（開發階段 Users.db 也刻意推上 git，見第 5 節）
  item.new.json              道具批次匯入用資料
Cogs/
  load-character/  character.py, Components/character_components.py   # 圖鑑
  load-gacha/      gacha.py, Admin-gacha.py, Components/gacha_components.py   # 抽卡 / 卡冊 / 合成 / 融合 / 卡冊管理
  load-market/     market.py, Admin-market.py, Components/market_components.py   # 市值 / 分解 / 市場
  load-general/    profile.py, help.py, shrine.py, event.py, trade.py, leaderboard.py, Admin-item.py, Admin-user.py, Admin-shrine.py, Admin-event.py, Admin-trade.py, Components/general_components.py, shrine_components.py, trade_components.py, help_components.py
  load-system/     Admin-sys.py
Utils/components.py          共用的 Components V2 通知工具（send_notice 等）
Utils/character_data.py      Characters/ 載入器：load_categories() / load_characters()，壞檔印警告並略過
Utils/config.py              .env 設定：ADMIN_IDS 與 is_admin(user)
Utils/reloader.py            模組重載 (/admin-sys reload 與主控台共用)
Utils/console.py             主控台指令：機器人執行中可在終端機輸入 help / status / reload / sync / money / stamina / shutdown
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
- CodeGraph（程式碼索引 MCP）安裝見 `docs/setup.md`；筆電已裝，桌機還沒裝。改了很多檔案後可以跑 `codegraph sync` 更新索引。

## 3. Components V2 的做法與限制
- **所有介面與通知一律用 Components V2**，不要再用 `discord.Embed` 或純文字 `content` 回覆。
- 使用 `ui.LayoutView`、`ui.Container(accent_color=…)`、`ui.Section(TextDisplay, accessory=Thumbnail|Button)`、`ui.Separator`、`ui.ActionRow`。
- **單則訊息最多 40 個元件**；V2 訊息不能帶 `content`/`embeds`，且一旦是 V2 之後只能以 V2 編輯。
- 互動回呼寫成 `button.callback = self.xxx` 並在 `build()` 內重組畫面（`clear_items()` 後重新 `add_item`）；多種狀態（例如編輯 / 刪除確認 / 已刪除）放在同一個 View 用 `build(mode=...)` 切換。
- 縮圖規則：依序查 `images/Thumbnails.json` 的 `角色id_階級` → `角色id` → `"fill"`，連 URL 都沒有就只顯示文字。卡牌畫面用該卡的階級（融合預覽用升階後的階級）；圖鑑角色頁在「🏷️ 卡牌階級」**每個階級一行、右側各放該階級的卡面縮圖**（`ui.Section` + `Thumbnail`；該階級沒有專屬卡面時退回角色圖 / fill），標題右側不放縮圖；角色一張專屬卡面都沒有時才照舊只在標題右側放一張（fill）。
- **通知工具 `Utils/components.py`**：
  - `send_notice(interaction, text, color=None, footer=None, ephemeral=True)`：自動判斷用 `response` 或 `followup` 送出，預設 ephemeral。
  - `notice_container()` / `notice_view()`：需要自行加按鈕或嵌進其他畫面時使用。
  - 色條依開頭 emoji 自動上色：❌/🚫/🗑️ 紅、⚠️ 橘、✅/🎁/✨/🟢 綠、↩️/✖️/⚙️ 灰，其他 blurple。
- V2 畫面清單：`/card gacha`、`/card inventory`、`/card synthesis`、`/card fusion`、道具背包 `/inventory`（分類 + 分頁 + 跳頁 Modal）、`/character` 圖鑑（分類→角色→檔案頁）、`/profile`（含今日簽到狀態、運勢、簽到按鈕）、`/daily`、`/admin-item edit_item` 編輯控制台、`/admin-sys reload` 重載控制台、`/admin-gacha` 各畫面、Logger 重大事件通知，以及所有錯誤 / 成功提示。
- **autocomplete 最多 25 個選項**：選項可能變多的地方一律「先選代數 (pool) → 再選角色」，選卡改用分頁選單畫面（每頁 20 張），不要直接用 autocomplete 列出卡牌。
- 原本的 `/fortune` 已併入 `/profile`，已不存在。
- 卡面相關（縮圖網址帶 `?v=`、卡框、分層合成、生圖流程）全部在 `docs/card-art.md`。

## 4. 細節文件
資料庫設計 ➔ `docs/database.md`；各 Cog 重點 ➔ `docs/cogs.md`；驗證方式 ➔ `docs/testing.md`；重構歷程 ➔ `docs/history.md`。
- 最近一次測試：見 `docs/testing.md` 最後幾行（`python tests/run_all.py`）。

## 5. 使用者的決定與工作習慣
- **開發階段 `Database/Users.db` 刻意跟著推上 git**（雖然 repo 公開、內含玩家資料）。不要再建議移出追蹤或加入 `.gitignore`。
  - Claude Code 的自動權限檢查可能會擋下「提交 / 推送 Users.db」，此時請使用者自己執行 git 指令，不要繞過。
- 直接推到 `main`（個人專案，不開 PR）。
- **版本號與開發紀錄（2026-11-05 使用者指定）**：版本格式 `X.XX.XXX`（大版本：新功能 / 新活動，開發階段為 0；第二段：功能改動、新 UI；最後三碼：瑣碎 commit）。**每次 commit 都要更新 `Utils/version.py` 並在 `CHANGELOG.md` 最上面補一筆**（做了什麼、遇到的問題與解法）。
- **經濟系統的數值：使用者沒給的一定要先問，不要自己決定**（2026-11-05）。規格與待確認項目在 `TODO.md` 第 5 節。
- 兩台電腦切換：離開前 `commit` + `push`，開始前 `pull`；**機器人同一時間只在一台上執行**（同一個 Token，且 Users.db 是二進位無法合併）。
- **完成並測試通過後直接 commit + push 到 `main`，不用先問**（2026-10-28 使用者指示）。只有重大事件才先問，例如要開分支、改寫 git 歷史、刪除大量資料等。`Database/Users.db`、`Item.db` 有變動時也一起推。
- **卡面：一個角色（或一張卡）定案後才 commit + push**（2026-10-30 使用者指示，避免 git 歷史塞滿試作圖）。試作、調參數、使用者還在挑圖或要求調整時都只留在本機；使用者說「定案」「推送」或明確表示這版 OK 才推。程式碼改動也跟著那次定案一起推。

## 6. 給 Claude Code 的工作守則
- 動資料前先備份；遷移類工作**不得刪除或改動舊檔**。
- 修改後保持 LF 換行；沿用既有的程式風格與繁體中文註解/文案（emoji 標題風格）。
- 新增畫面或通知一律用 V2（優先用 `Utils/components.py`），注意 40 個元件上限，縮圖走 `Thumbnails.json`（角色_階級 → 角色 → `fill` 後備）。
- 資料庫寫入涉及多表時用單一交易；日常領獎類操作用原子 `UPDATE … WHERE` 防重複；會消耗東西的操作先給確認畫面。
- 使用者可能繞過 autocomplete 直接輸入值，指令內一定要再驗證一次。
- 新 Cog 檔放進 `Cogs/load-*/`，不要留下舊的同名/過期檔案。
- 不要在回覆中貼大量 URL；完成後簡述結果與下一步即可。
- **文件樹**：CLAUDE.md 只放每次都要知道的事；細節寫進 `docs/` 對應的檔案，新主題就開新檔並加進上面的文件樹表格。

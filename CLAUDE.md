# TouHou-Discord-Bot — 入口（給接手的人與 AI 助手）

繁體中文的「東方 Project」主題 Discord 機器人 (`discord.py` Components V2 + SQLite)：抽卡、卡冊、神社經營、市場、活動、🌀 裏世界探索。
這一頁只放每次都要知道的事；細節都在下面的文件裡，**只讀跟這次工作有關的**。

## 💬 最重要：一律繁體中文
**每一則給使用者看的文字都要用繁體中文，沒有例外。** 最容易切成英文的是前面沒有使用者訊息的輪次：背景工作通知或子任務回報之後、對話壓縮後的第一則、收尾的摘要與提問。回覆要簡潔，不要貼一堆網址。程式碼、指令、檔名可以保留原文。

## 🚫 紅線（使用者定的，不能違反）
1. **經濟 / 玩法數值：使用者沒給的一定要先問**，不要自己決定。
2. **有設計決定的工作 (新功能、改玩法、改畫面) 動手前先一輪一輪問**：每輪編號列問題、每題附建議答案，全部確認才動手。修 bug、小調整、講得很清楚的指示直接做。一組做完就停，不主動丟下一組的草案。
3. **不改寫 git 歷史、不開分支、不刪大量資料**，除非先問過。例行改動測試通過後直接 commit + push 到 `main` (不開 PR；卡面要等使用者說定案才推)。
4. **機器人同一時間只在一台上執行** (同一個 Token)。雲端上線後，本機用正式 Token 執行前一定要先 `python deploy/handoff.py take`，用完 `release`。
5. **`Database/Users.db` 開發階段刻意跟著推上 git**：不要建議移出追蹤；權限檢查擋下時請使用者自己執行，不要繞過。但交接期間 (`take` 之後、`release` 之前) 本機是玩家真實資料，**不要 commit / push `Database/*.db`**。

每次 commit 都要更新 `Utils/version.py` 與 `CHANGELOG.md`，版本號推送前才編。以上每一條的完整做法在 `docs/handbook/workflow.md`。

## 📚 文件樹
| 要做什麼 | 讀這份 |
|---|---|
| 找某份文件 (所有文件的總目錄) | `docs/README.md` |
| 開始工作前：溝通、先問的規則、推送、版本號、分工 (統整 / 卡面 / 名片 / 玩法)、工作守則 | `docs/handbook/workflow.md` |
| 接手某個角色的工作：做過什麼、踩過的坑、交接清單 | `docs/handbook/sessions.md` |
| 找東西放在哪、`.env`、環境注意事項 (LF、cp950) | `docs/dev/structure.md` |
| 新增 / 修改功能前：分層、寫法、新增功能檢查清單 | `ARCHITECTURE.md` |
| 寫或改 Discord 畫面 | `docs/dev/components-v2.md` |
| 指令、玩法規則、數值 | `docs/gameplay/cogs.md`、`docs/gameplay/ura.md` (🌀 裏世界) |
| 資料表、資料庫函式、道具、角色檔格式 | `docs/dev/database.md` |
| 跑測試 (`python tests/run_all.py`)、實機驗證 | `docs/dev/testing.md` |
| 卡面 / 頭像 / 名片 | `docs/art/card-art.md` |
| 新增一代角色 | `docs/dev/new-characters.md` |
| 活動檔格式 | `Events/README.md` |
| 雲端部署、本機 ⇄ 雲端交接 | `docs/dev/deploy.md` |
| 外掛 skill：哪些能用、哪些不要用 | `docs/handbook/workflow.md` 第 9 節、`docs/handbook/skills.md` |
| 待做、目前進度 | `TODO.md` |
| 每個版本做了什麼、踩過的坑 | `CHANGELOG.md` (最上面幾筆就好；0.38 以前在 `docs/changelog/`) |

找程式碼：有裝程式碼索引 (CodeGraph，見 `docs/dev/setup.md`) 就先用它查，不要整份檔案讀。
Windows 執行 Python 要設 `PYTHONIOENCODING=utf-8`；檔案一律 UTF-8、LF 換行。

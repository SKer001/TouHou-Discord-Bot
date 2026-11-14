# 🧪 驗證方式 (測試、botcli、實機)

> 從 `CLAUDE.md` 拆出來的細節文件 (2026-11-11)。要做這方面的工作時才讀；改了內容記得一起更新。

- 本機已安裝 discord.py 2.7.1 與 aiosqlite，可以直接跑機器人與測試。
- 測試做法：把 `udm.DB_PATH` / `idm.DB_PATH` 指到暫存資料夾（道具資料庫用副本），用真實 discord.py 物件 + 假的 Interaction（response / followup / namespace）呼叫指令的 `callback` 與 autocomplete，並斷言回覆都是 `LayoutView`（沒有 content / embed）。**測試絕不碰真實的 Users.db / Item.db**（前後比對 sha256）。
- **測試在 repo 的 `tests/`**：`python tests/run_all.py` 會逐一以子行程執行 `tests/test_*.py`、彙整結果，並在前後比對 `Database/*.db` 的 sha256（機器人同時在跑時可能誤報，跑測試前先關掉機器人）。
  - 🖥️ **給桌機端的 Claude**：pull 之後先跑一次 `python tests/run_all.py` 確認環境正常；改完功能要跑、也要在對應的 `tests/test_*.py` 補測試。新增測試檔沿用現有檔案的寫法（開頭把 `udm.DB_PATH` 指到 `tempfile.mkdtemp()`、最後印出 `passed N, failed M`），`run_all.py` 會自動找到它。
- **用 `tools/botcli.py` 實際操作機器人（改完功能後優先用它檢查畫面與流程）**：
  - 載入全部 Cog（不登入 Discord、不載入 Logger），用假的 Interaction 執行斜線指令，把 V2 畫面印成文字（按鈕編號 `b1`、選單編號 `s1`、元件數 / 40）。
  - 資料庫一律用沙盒 `.botcli/`（第一次從 `Database/` **唯讀**複製，已加進 `.gitignore`），資料會保留到下次；`--reset` 重新複製、`--fresh` 從空白開始、`--sandbox 路徑` 指定資料夾。
  - 畫面只存在於同一次執行中：指令和之後的點擊要寫在同一次執行的步驟裡，例如：
    `python tools/botcli.py "/card gacha pool:th06 pull_type:10" "click 繼續十連" "/card inventory" "select 卡池 th06"`
  - 步驟：`/指令 參數:值`（成員參數用 `me`、`@名稱` 或 ID；`@名稱` 會產生固定的假玩家）、`? /指令 參數 [已填:值] [current:文字]`（看 autocomplete）、`click b2|按鈕文字`、`select s1|選單文字 值…`、`modal 標籤:值`、`as me|@名稱`、`msg 編號`、`show`、`users`、`sql SELECT…`、`commands`、`help`。
  - 會自動抓的問題：回覆帶 content / embed、同一互動回應兩次、指令或元件沒有回應、元件超過 40 個、autocomplete 超過 25 個或選項超過 100 字、Discord 會擋下的參數（choices、Range）、程式例外（印出 traceback）。有任何錯誤時結束碼為 1。
  - 在 Git Bash 執行時 `/card` 可能被改寫成路徑，CLI 會自動還原；也可以省略開頭的 `/`（`card gacha …`）。
  - `tree.sync` 會被略過；頭像不會下載（主色退回預設紅色）。
  - 步驟還有 `wait 秒數`、`say 文字`（示範用）。
- **實機（真的 Discord）**：測試頻道 = `.env` 的 `TEST_CHANNEL_ID`，沒設定時用 `LOG_CHANNEL_ID`（目前就是 log 頻道 `#touhou-logs`）。兩個工具都只用機器人自己的 Token 走 REST，機器人正在跑也能用，完全在 Discord 規範內。**不要**用瀏覽器自動操作使用者的 Discord 帳號（self-bot 違反服務條款）。
  - `python tools/botcli.py --live 步驟…`：流程照樣在沙盒模擬，但每一步新增 / 更新的畫面都由機器人真的送到測試頻道（同一則會用編輯更新），讓 **Discord 驗證真實的 V2 內容**；Discord 拒絕時會印出錯誤欄位（例如 `components：Must be 40 or fewer`）並算成錯誤。鏡像訊息的按鈕全部停用、頂端加一行「🧪 botcli 鏡像」說明（元件已滿 40 時不加）。
  - `python tools/discord_peek.py [-n 5] [--bot-only] [--raw]`：讀測試頻道最新訊息（由舊到新），印出作者、時間、是否 V2、是哪位使用者的互動，以及畫面文字與元件數。使用者在 Discord 實機操作後，用它查看真正的結果。ephemeral 訊息 API 讀不到。
- 最近一次 (2026-11-14，0.33.000)：22 個測試檔全數通過，共 944 項 (稱號 101、名片 68、通知 87)。V2 畫面細節仍以 Discord 實機為準。
- 已知待改進與之後的計畫（卡面重做、未做的角色、TH07 之後的角色、經濟系統：探索 / 分解 / 浮動市值 / 市場 / 交易）統一記在根目錄 `TODO.md`。

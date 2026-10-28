# ⛩️ TouHou-Discord-Bot

以「東方 Project」為主題的繁體中文 Discord 機器人：祈願抽卡、卡冊收集、卡牌合成與融合、角色圖鑑、道具背包、個人資料卡與每日簽到。
所有畫面都使用 Discord **Components V2**。

## ✨ 功能

### 🎴 卡牌系統 `/card`
| 指令 | 說明 |
|---|---|
| `/card gacha pool pull_type` | 選擇卡池後單抽（2,000 賽錢）或十連（20,000 賽錢），結果畫面可以直接繼續祈願 |
| `/card inventory` | 卡冊：同角色、同階級的卡疊成一列，可依卡池 / 階級篩選，依階級、完整度、最新、數量排序；顯示收集進度，可直接從一疊卡進入合成 / 融合 |
| `/card synthesis pool character` | 合成：兩張同角色、同階級的卡合成一張完整度更高的卡（分頁選卡） |
| `/card fusion pool character rarity` | 融合：三張完整度 1.0000 的卡融合成高一階的卡 |
| `/card history` | 祈願紀錄：各卡池的累計抽數與保底進度 |

- **卡池依代數劃分**：📜 舊作卡池（主要主角 + TH01～TH05）、🔴 紅魔鄉卡池（TH06）。
- **保底**：每個卡池各自計算，連續 100 抽沒出 UR 以上，第 100 抽必定獲得 UR。
- **完整度**：每張卡有 0.001～1.0000 的完整度，越高越稀有。
- **合成規則**：
  - 新完整度 = 較高的那張 + 增幅；兩張越接近，增幅越大。
  - 增幅上限依較低那張的位數決定：0.x → 0.2、0.0x → 0.05、0.00x → 0.01、0.000x → 0.005。
  - 有機率觸發加倍；加倍機率依階級，完整度差距越大機率越低。
- **融合規則**：升到該角色的下一個階級，新卡完整度隨機；已經是最高階的卡不能融合。

### 📚 角色圖鑑 `/character`
依「主要主角 / 各代作品」分類瀏覽角色。每個角色頁面包含稱號、種族、能力、簡介、基礎數值（HP / ATK / DEF）、卡牌階級與稱號，以及特殊能力 SP（I / II / III 三個等級），並標示你自己擁有哪些階級。

### 🌸 個人與道具
| 指令 | 說明 |
|---|---|
| `/profile` | 個人資料卡，可以設定公開 / 私人，包含體力、今日簽到狀態與運勢 |
| `/daily` | 每日簽到：抽今日運勢，獲得賽錢與經驗值（台灣時間每天 00:00 重置） |
| `/inventory` | 道具背包，有分類與分頁 |
| `/leaderboard category` | 本伺服器排行榜：賽錢、P點、收集角色、卡牌總數、祈願次數、融合次數 |

- **體力**：上限 240，每 6 分鐘自然回復 1 點（自然回復最多到 240）。在自己的 `/profile` 按「⚡ 恢復體力」可以使用體力道具，道具可以讓體力超過上限。
- **體力道具**：🍡 幽夢三色團子 (+120)、🫖 咲夜特製司康與紅茶 (+120)、🍄 螢光蘑菇濃湯 (+67)、🍙 陰陽梅干飯糰 (+60，每日簽到贈送 1 個)。

### 🛠️ 管理員指令（只有設定的管理員可以使用）
| 群組 | 指令 |
|---|---|
| `/admin-gacha` | `view` 檢視卡冊、`give` 發放卡牌、`remove` 刪除卡牌、`set_completeness` 修改完整度、`clear` 清空卡冊 |
| `/admin-item` | `add_item`、`add_items_batch`、`edit_item`（編輯控制台）、`give_item`、`give_items` |
| `/admin-user` | `reset_daily`、`add_money`、`add_exp`、`take_item`、`clear_inventory`、`add_stamina` |
| `/admin-sys` | `reload`（重載模組控制台）、`sync`、`shutdown` |

## 📦 安裝與執行

需要 **Python 3.11** 以上。

```bash
pip install -r requirements.txt
```

在專案根目錄建立 `.env`（不要推上 git）：

```env
DISCORD_TOKEN=你的機器人 Token
LOG_CHANNEL_ID=接收重大事件通知的頻道 ID
ADMIN_IDS=管理員的 Discord 使用者 ID (多位用逗號分隔)
```

機器人需要在 Developer Portal 開啟 Privileged Intents（排行榜需要伺服器成員清單）。

啟動：

```bash
python Main.py
```

> Windows 主控台若出現 `UnicodeEncodeError`（無法顯示 emoji），請先設定 UTF-8 輸出：
> PowerShell：`$env:PYTHONIOENCODING = 'utf-8'; python Main.py`

## 🗂️ 專案結構

```
Main.py                  入口：初始化資料庫、自動載入 Cogs/load-*/ 底下所有模組、同步斜線指令
Characters/              角色資料 (一個角色一個 JSON)
  Main/                  主要主角
  TH01/ … TH06/          各代作品的角色
Cogs/
  load-gacha/            抽卡、卡冊、合成、融合 (gacha.py)、卡冊管理 (Admin-gacha.py)
  load-character/        角色圖鑑
  load-general/          個人資料卡、簽到、道具背包、道具與玩家管理
  load-system/           系統維護指令
  */Components/          各模組的 Components V2 畫面產生器
Database/
  User_DB_Manager.py     玩家資料庫 (Users.db)：賽錢、等級、簽到、卡牌
  Item_DB_Manager.py     道具資料庫 (Item.db)
Utils/
  components.py          共用的 V2 通知工具
  character_data.py      角色資料載入器
  config.py              .env 設定 (管理員 ID)
tests/                   測試 (python tests/run_all.py)
tools/botcli.py          指令列模擬器 (不連 Discord 測試指令)
Logger/Logger.py         日誌與錯誤回報
images/Thumbnails.json   角色縮圖對照表 {"角色id": "圖片URL", "fill": "預設圖URL"}
```

## 🧩 新增角色

1. 在 `Characters/<分類>/` 新增 `<角色id>.json`，格式可以參考 `Characters/Main/reimu.json`。
   - 檔名必須和 `id` 一致。
   - `special_powers.levels` 的階級必須和 `gacha.rarities` 一致。
2. 若要開放抽取，把 `gacha.enabled` 設為 `true`，並確認該分類資料夾已列在 `Cogs/load-gacha/gacha.py` 的 `GACHA_POOLS` 中。
3. （可選）在 `images/Thumbnails.json` 加入角色縮圖；沒有的話會使用 `fill` 預設圖。
4. `/character` 會即時讀取新資料；抽卡需要用 `/admin-sys reload` 重新載入抽卡模組。

格式錯誤的角色檔會在主控台印出警告並略過，不會影響其他角色。

## 🧪 測試

```bash
python tests/run_all.py
```

測試使用暫存資料庫與假的 Discord 互動，不會連上 Discord，也不會改動 `Database/` 裡的真實資料（執行前後會自動比對）。執行前請先關掉機器人。

### 🖥️ 指令列模擬器 `tools/botcli.py`

不用開 Discord，直接在終端機「假裝打指令」，畫面會印成文字，可以接著點按鈕、選選單：

```bash
python tools/botcli.py "/card gacha pool:th06 pull_type:10" "click 繼續十連" "/card inventory" "select 卡池 th06"
```

- 不帶步驟執行會進入互動模式，輸入 `help` 查看所有語法（`click`、`select`、`modal`、`as`、`? /指令 參數` 查 autocomplete …）。
- 使用沙盒資料庫 `.botcli/`（從 `Database/` 唯讀複製一份），不會動到真實資料；`--reset` 重新複製、`--fresh` 從空白開始。
- 遇到錯誤（程式例外、沒有回應、超過元件上限等）會標示出來，結束碼為 1。
- 加上 `--live` 會把每一步的畫面真的送到測試頻道（`.env` 的 `TEST_CHANNEL_ID`，沒有就用 `LOG_CHANNEL_ID`），讓 Discord 驗證實際內容；鏡像訊息的按鈕是停用的。

### 👀 讀取測試頻道 `tools/discord_peek.py`

```bash
python tools/discord_peek.py -n 5 --bot-only
```

用機器人的 Token 讀測試頻道最新的訊息，把實機的 V2 畫面印成文字（ephemeral 訊息讀不到）。

## 🔧 開發備註
- 新增模組：在 `Cogs/load-*/` 放入 `.py` 檔，並提供 `async def setup(bot)`。資料夾第一層的每個 `.py` 都會被當成模組載入，不要在那裡放非模組檔案。
- 單則 Components V2 訊息最多 40 個元件，新增畫面時要注意。
- 會消耗卡牌的操作（合成、融合、刪除）都在單一資料庫交易中完成，並先顯示確認畫面。

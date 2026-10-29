# 🏗️ 專案架構說明 (ARCHITECTURE.md)

> 這份文件說明**程式要怎麼寫、東西要放哪裡**，讓之後新增功能時（不管是哪台電腦、哪次對話）都維持同一套做法。
> 進度、使用者偏好、歷史決策請看 `CLAUDE.md`；給一般使用者看的功能介紹在 `README.md`。
> 新增功能前先讀這份；如果改變了下面任何一條規則，**一定要回來更新這份文件**。

---

## 1. 分層總覽

```
Discord ─▶ Main.py (TouHouBot)
             │ setup_hook：① init_db / init_item_db ② 載入 Logger ③ 掃描 Cogs/load-*/*.py
             ▼
          Cogs/load-<類別>/<功能>.py           ← 指令入口 (斜線指令、權限、參數驗證、流程)
             │            │
             │            ▼
             │   Cogs/load-<類別>/Components/*_components.py   ← 只負責「把資料畫成 V2 畫面」
             │            │
             ▼            ▼
          Utils/ (共用工具：通知、角色資料、設定)
             │
             ▼
          Database/*_DB_Manager.py              ← 唯一能碰 SQLite 的地方
             │
             ▼
          Database/Users.db、Item.db；Characters/*.json；images/Thumbnails.json
```

**依賴方向只能往下**：Cog → Components / Utils → Database。
- Components **不碰資料庫**、不呼叫 `interaction.response`，只回傳 `ui.Container`（或組好的 View 元件）。
- Database Manager **不 import discord**，只回傳 dict / list / 數字。
- Cog 之間**不互相 import**；真的要用另一個 Cog 的東西（例如 Admin-gacha 要用抽卡模組的卡池）時，用 `importlib.import_module` 在呼叫時才取（見 §3.4），這樣 `/admin-sys reload` 後才拿得到新版本。

---

## 2. 資料夾與命名規則

| 位置 | 放什麼 | 命名 |
|---|---|---|
| `Main.py` | 機器人主類別、啟動流程 | — |
| `Cogs/load-<類別>/` | 一個檔案 = 一個 Cog（或一組相關指令） | 一般功能小寫 `gacha.py`；管理員功能 `Admin-<對象>.py` |
| `Cogs/load-<類別>/Components/` | 該類別的畫面產生器 | `<類別>_components.py`（**不是** Embeds） |
| `Utils/` | 跨 Cog 共用、不是 Cog 的程式 | `snake_case.py` |
| `Database/` | 資料庫存取 + `.db` 檔 | `<名稱>_DB_Manager.py` |
| `Characters/<分類>/<id>.json` | 一角色一檔 | 檔名 = `id`；分類 `Main`、`TH01`～`TH06` |
| `Logger/` | 日誌 Cog（優先載入） | — |
| `tests/test_*.py` | 每個功能一個測試檔 | `run_all.py` 自動找 |
| `tools/` | 開發工具（不會被機器人載入） | `botcli.py`、`card_art/` 等 |
| `images/` | 縮圖、原圖、`Thumbnails.json` | 見 §6 |

目前的 Cog 類別：

| 資料夾 | 檔案 | 指令 |
|---|---|---|
| `load-character/` | `character.py` | `/character` 圖鑑 |
| `load-gacha/` | `gacha.py`、`Admin-gacha.py` | `/card …`（祈願、卡冊、合成、融合、history）、`/admin-gacha …` |
| `load-general/` | `profile.py`、`inventory.py`、`leaderboard.py`、`Admin-item.py`、`Admin-user.py` | `/profile`、`/daily`、`/inventory`、`/leaderboard`、`/admin-item …`、`/admin-user …` |
| `load-system/` | `Admin-sys.py` | `/admin-sys reload / sync / shutdown` |

⚠️ **載入器會載入 `Cogs/load-*/` 第一層的每一個 `.py`**（`Main.py` 的 `setup_hook`）。所以：
- 不是 Cog 的檔案**不能**放在第一層 → 放 `Components/` 或 `Utils/`。
- 不要留舊檔、備份檔（`gacha_old.py` 也會被載入而失敗）。
- 每個 Cog 檔案結尾都要有 `async def setup(bot): await bot.add_cog(...)`。
- 模組路徑是 `Cogs.load-gacha.gacha`（資料夾名有 `-`，所以 Cog 內用相對匯入 `from .Components.x import ...`）。

---

## 3. Cog 的寫法

### 3.1 一個 Cog 的基本骨架

```python
class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="🏆 …")
    async def leaderboard(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        rows = await get_leaderboard_stats(...)          # 1. 讀資料 (Database)
        view = ui.LayoutView()
        view.add_item(build_leaderboard_container(...))   # 2. 畫畫面 (Components)
        await interaction.response.send_message(view=view)  # 3. 回覆 (只能在 Cog)

async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
```

- 一組相關指令用 `commands.GroupCog`（例：`GachaCardSys(group_name="card")` ➔ `/card gacha`、`/card inventory`…）或 `app_commands.Group`（`/admin-xxx` 系列）。
- 指令描述開頭放 emoji，文案用繁體中文。

### 3.2 互動畫面 (View)

- **一律 Components V2**：`ui.LayoutView` + `ui.Container(accent_color=…)` + `ui.TextDisplay` / `ui.Section(…, accessory=Thumbnail|Button)` / `ui.Separator` / `ui.ActionRow`。不要用 `discord.Embed`、不要用 `content=` 回覆。
- 有狀態的畫面寫成 `class XxxView(ui.LayoutView)`：
  - 狀態存在 `self`（目前頁數、篩選、選到的卡…）。
  - `build(mode=...)` 先 `clear_items()` 再依狀態重組整個畫面；按鈕回呼改完狀態後呼叫 `build()` 再 `interaction.response.edit_message(view=self)`。
  - 按鈕寫成 `button = ui.Button(...); button.callback = self.on_xxx`，不用裝飾器（因為每次 build 都重建）。
  - 多個狀態（列表 / 詳情 / 確認 / 結果）放在同一個 View 用 `mode` 切換，不要開新訊息。
  - 只允許本人操作：覆寫 `interaction_check`，非本人用 `send_notice` 回「❌ 這不是你的畫面」並回傳 False。
- **單則訊息最多 40 個元件**（每個 Section/TextDisplay/Button 都算）；列表類畫面要先算好每頁筆數（例：卡冊每頁 7 疊）。
- **選單最多 25 個選項、autocomplete 最多 25 筆**：選項可能變多就分層（先選代數 pool → 再選角色 → 分頁選卡，每頁 20 張）。

### 3.3 通知 / 錯誤訊息

一律用 `Utils/components.py`：
- `send_notice(interaction, "❌ 賽錢不足", footer=...)`：自動判斷 response / followup，預設 ephemeral。
- 色條依開頭 emoji 自動上色（❌ 紅、⚠️ 橘、✅🎁 綠、↩️ 灰、其他 blurple），所以**訊息開頭一定放 emoji**。
- 要在通知裡加按鈕時用 `notice_container()` 自己組。

### 3.4 管理員指令

- 檔名 `Admin-<對象>.py`，指令群組 `/admin-<對象>`。
- 每個指令開頭：`if await self._deny(interaction): return`（內部用 `Utils.config.is_admin`，管理員名單在 `.env` 的 `ADMIN_IDS`）。
  **不要**用 Cog 層級的 `interaction_check` 擋（失敗會被 Logger 當成指令錯誤通報）。
- 需要用到其他 Cog 的資料（卡池、畫面類別）：`gacha_mod()` = `importlib.import_module("Cogs.load-gacha.gacha")`，每次呼叫時取，reload 後自動拿新版。
- 會刪除 / 清空資料的操作要有確認畫面。

### 3.5 參數驗證

使用者可以不用 autocomplete、直接打任意值 → **指令內一定再驗證一次**（角色是否存在、是否在該卡池、數量範圍…），失敗用 `send_notice("❌ …")` 回覆。

---

## 4. 資料層

### 4.1 Database Manager 的規則

- 所有 SQL 都在 `Database/User_DB_Manager.py`、`Item_DB_Manager.py`，Cog 只呼叫函式。
- 連線用 `connect()`（`aiosqlite`、`row_factory=Row`、`foreign_keys=ON`）。
- **會改到多個表或「先讀再寫」的操作，整個放在一個 `BEGIN IMMEDIATE` 交易裡**（例：`draw_gacha` 扣錢 + 寫卡 + 更新保底；`transform_cards` 刪素材 + 寫新卡）。這樣連點、兩個視窗同時按也只會成功一次。
- 每日領取類用原子 `UPDATE … WHERE last_daily != today`，看 `rowcount` 判斷有沒有成功。
- 新增欄位：加到 `USERS_EXTRA_COLUMNS`，`init_db()` 會自動 `ALTER TABLE` 補上，舊資料不用遷移腳本。
- 不夠 / 不合法時回傳 `{"ok": False, ...}` 或丟自訂例外（`InsufficientFunds`、`ValueError`），**不要寫一半**。

### 4.2 角色資料 `Characters/`

- 一角色一檔，格式見 `CLAUDE.md` §3；`Utils/character_data.py` 負責讀取與驗證（壞檔印警告略過，不會讓機器人掛掉）。
- 圖鑑每次指令都重讀；抽卡卡池 `GACHA_POOL` 在模組載入時讀 ➔ 改角色檔後要 `/admin-sys reload` 抽卡模組。
- 新增角色：放 json ➔（要進卡池就 `gacha.enabled: true`、放在卡池包含的資料夾）➔ reload ➔ 補卡面（§6）。

### 4.3 階級

全專案共用的順序：`N < R < SR < SSR < UR < LR`（`gacha.py` 的 `RARITY_ORDER`）。每個角色固定 3 個連續階級（`gacha.rarities`），稱號在 `gacha.titles`。

---

## 5. 日誌與錯誤

- `Logger/Logger.py` 是第一個載入的 Cog：記錄每個指令 / 元件互動到 `Logger/Logs/`，重大事件（開機、斷線、指令錯誤）用 V2 送到 `.env` 的 `LOG_CHANNEL_ID`。
- Cog 內不用自己 try/except 包整個指令；未處理的例外會由 `on_app_command_error` 統一通報。
- 預期中的錯誤（參數錯、錢不夠）自己 `send_notice` 回覆，不要丟例外。

---

## 6. 圖片與卡面

```
images/Thumbnails.json        {"角色_階級": URL, "角色": URL, "fill": 預設圖 URL}
images/Thumbnails/*.png       Discord 顯示用縮圖 460×640 (raw.githubusercontent.com 連結 ➔ 要 push 才看得到)
images/Original/Art/          沒加框的角色原圖 <角色>_<階級>.png
images/Original/Thumbnails/   卡框素材 (fill、empty、綠幕原圖)
tools/card_art/               卡面產生工具 (不會被機器人載入)
```

- 程式取縮圖的順序：`角色_階級` ➔ `角色` ➔ `fill` ➔ 都沒有就只顯示文字（`get_thumbnail_url`）。
- 卡面 = 原圖 ➔ 蓋卡框 `empty.png` ➔ 稱號與名字 ➔ 等級圖；`build_cards.py` 整批產生、`--stages` 輸出每一步（`card_stages/`，不進 git）。
- 生圖流程與各角色 prompt 在 `tools/card_art/make_workflow.py`，細節與使用者偏好見 `CLAUDE.md` §4「卡面」。
- **UR 與 LR 一律用分層合成**（2026-10-29 起）：背景 / 彈幕 / 人物分開做再合成（`tools/card_art/layered/`）。

---

## 7. 測試與驗證

- `python tests/run_all.py`：跑全部 `tests/test_*.py`，前後比對 `Database/*.db` 的雜湊，**測試絕不能碰真實資料庫**（每個測試檔開頭把 `DB_PATH` 指到暫存資料夾）。
- 新功能要在對應的 `tests/test_<功能>.py` 補測試；新檔沿用現有寫法，最後印 `passed N, failed M`。
- 測試會斷言回覆都是 `LayoutView`（沒有 content / embed）。
- 畫面與流程用 `tools/botcli.py` 實際點一遍（沙盒資料庫 `.botcli/`），需要 Discord 實際驗證時加 `--live`。

---

## 8. 新增功能的檢查清單

1. 指令放進哪個 `Cogs/load-<類別>/`？畫面放進同類別的 `Components/`。
2. 資料存取寫在 `Database/*_DB_Manager.py`，多表操作用單一交易。
3. 畫面全部 V2、元件 ≤ 40、選單 / autocomplete ≤ 25。
4. 通知用 `send_notice`，開頭放 emoji。
5. 管理員指令用 `_deny()`；會消耗 / 刪除東西的操作先給確認畫面。
6. 指令內再驗證一次使用者輸入。
7. 補 `tests/test_*.py`，`run_all.py` 全過，再用 botcli 點一次。
8. 更新 `CLAUDE.md`（進度、決策）與這份文件（如果改了規則），然後 commit + push。

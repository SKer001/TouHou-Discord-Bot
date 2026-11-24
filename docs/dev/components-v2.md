# 🧱 Components V2 的做法與限制（docs/dev/components-v2.md）

> 所有畫面與通知怎麼組、有哪些上限。新增或修改畫面前先讀；View 的完整寫法在 `ARCHITECTURE.md` 第 3 節。
> 改了共用通知工具或畫面慣例，記得一起更新這份。

## 1. 基本規則
- **所有介面與通知一律用 Components V2**，不要再用 `discord.Embed` 或純文字 `content` 回覆。(需要 `discord.py` >= 2.6)
- 使用 `ui.LayoutView`、`ui.Container(accent_color=…)`、`ui.Section(TextDisplay, accessory=Thumbnail|Button)`、`ui.Separator`、`ui.ActionRow`。
- 互動回呼寫成 `button.callback = self.xxx`，並在 `build()` 內重組畫面 (`clear_items()` 後重新 `add_item`)。
- 多種狀態 (例如編輯 / 刪除確認 / 已刪除) 放在同一個 View，用 `build(mode=...)` 切換。

## 2. 限制
- **單則訊息最多 40 個元件。**
- V2 訊息不能帶 `content` / `embeds`，而且一旦是 V2 之後只能以 V2 編輯。
- **autocomplete 最多 25 個選項**：選項可能變多的地方一律「先選代數 (pool) ➔ 再選角色」；選卡改用分頁選單畫面 (每頁 20 張)，不要直接用 autocomplete 列出卡牌。
- 使用者可能繞過 autocomplete 直接輸入值，指令內一定要再驗證一次。

## 3. 縮圖規則
- 依序查 `images/Thumbnails.json` 的 `角色id_階級` ➔ `角色id` ➔ `"fill"`；連 URL 都沒有就只顯示文字。
- 卡牌畫面用該卡的階級 (融合預覽用升階後的階級)。
- 圖鑑角色頁：
  - 在「🏷️ 卡牌階級」**每個階級一行、右側各放該階級的卡面縮圖** (`ui.Section` + `Thumbnail`；該階級沒有專屬卡面時退回角色圖 / fill)，標題右側不放縮圖。
  - 角色一張專屬卡面都沒有時，才照舊只在標題右側放一張 (fill)。
- 卡面相關 (縮圖網址帶 `?v=`、卡框、分層合成、生圖流程) 全部在 `docs/art/card-art.md`。

## 4. 通知工具 `Utils/components.py`
- `send_notice(interaction, text, color=None, footer=None, ephemeral=True)`：自動判斷用 `response` 或 `followup` 送出，預設 ephemeral。
- `notice_container()` / `notice_view()`：需要自行加按鈕或嵌進其他畫面時使用。
- 色條依開頭 emoji 自動上色：

  | 開頭 | 顏色 |
  |---|---|
  | ❌ / 🚫 / 🗑️ | 紅 |
  | ⚠️ | 橘 |
  | ✅ / 🎁 / ✨ / 🟢 | 綠 |
  | ↩️ / ✖️ / ⚙️ | 灰 |
  | 其他 | blurple |

## 5. 其他共用畫面工具
- `Utils/pagination.py`：共用分頁 (`paginate()` + `nav_buttons()` + 跳頁 `PageJumpModal`)，不要每個畫面各寫一套。
- `Utils/picker.py`：共用控制台 `GroupPickerView` (分組選單 ➔ 選項選單 (翻頁) ➔ 按鈕 + 預覽)。
- `Utils/thumbnails.py`：`load_thumbnails()` / `thumbnail_url()`，讀 `images/Thumbnails.json`。
- `Utils/numbers.py`：金額顯示 `fmt_money()`。
- 各工具的用途一覽在 `docs/dev/structure.md`。

## 6. V2 畫面清單
早期從 Embed 改成 V2 的畫面 (之後新增的畫面本來就都是 V2；目前所有指令見 `docs/gameplay/cogs.md`)：
- `/card gacha`、`/card inventory`、`/card synthesis`、`/card fusion`
- 道具背包 `/inventory` (分類 + 分頁 + 跳頁 Modal)
- `/character` 圖鑑 (分類 ➔ 角色 ➔ 檔案頁)
- `/profile` (含今日簽到狀態、運勢、簽到按鈕)、`/daily`
- `/admin-item edit_item` 編輯控制台、`/admin-sys reload` 重載控制台、`/admin-gacha` 各畫面
- Logger 重大事件通知，以及所有錯誤 / 成功提示
- 原本的 `/fortune` 已併入 `/profile`，已不存在。

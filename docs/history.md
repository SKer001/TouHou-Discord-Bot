# 📜 重構歷程 (CHANGELOG 之前)

> 從 `CLAUDE.md` 拆出來的細節文件 (2026-11-11)。要做這方面的工作時才讀；改了內容記得一起更新。

1. 抽卡結果與卡冊改 V2、縮圖用 `images/Thumbnails.json`（沒有就用 `fill`）。起初誤解成「把 embed 合併」，後來澄清是要 10 張相連的畫面，最終採用 Components V2。
2. 背包 `/inventory` 改 V2 並優化（分類排序、分頁、道具說明）。
3. `images/` 移到專案根目錄，修正所有 `Thumbnails.json` 路徑。
4. `/character` 圖鑑改 V2（`characters.json` 格式為 main_character/characters 結構）。
5. 合併 `/profile`、`/daily`、`/fortune`（保留重複簽到提示）。
6. 資料庫與檔案結構重整（提交 7b1bdf6）：`database.db`、`daily.db`、gacha `users/*.json` 全部併入 `Database/Users.db`；道具資料移到 `Database/Item.db`；gacha `character.json` → `Gacha_Pool.json`。一次性遷移腳本 `migrate_legacy.py` 已執行完畢並刪除，舊檔也已移除。
7. 新增卡牌合成 / 融合（提交 cbf85f1）。
8. 所有通知改用 Components V2、`Embeds` 改名 `Components`、新增 `Utils/components.py`（同一個提交 cbf85f1）。
9. 新增 `Characters/` 一角色一檔（24 位卡池角色），`/character` 圖鑑與抽卡卡池都改讀這裡；卡池分代數（舊作 / 紅魔鄉）。
10. 合成公式改為依位數動態決定上限、加倍改為依階級的機率；SP 改為 I/II/III 等級結構並加入 `spent`（B 點）。
11. 卡冊改成疊卡列表 + 卡池 / 階級篩選 + 排序；新增 `/admin-gacha`；合成、融合、管理員選卡都改成「代數 → 角色 → 分頁選卡」避開 25 個選項上限。新增 `README.md`。
12. 刪除已不再讀取的舊資料 `Cogs/load-gacha/Gacha_Pool.json`、`Cogs/load-character/characters.json`（舊圖鑑的 en_name / debut / location / theme_song / color / spell_cards 只存在 git 歷史中，需要時可從提交 d8fb060 以前取回）。`images/Original/` 是縮圖的高解析度原圖，保留。根目錄 `JSON.json` 是使用者的格式範本，不要動。
13. 管理員 ID 移到 `.env`（`Utils/config.py`）、新增 `requirements.txt`；祈願改為單一交易並加入每卡池 100 抽 UR 保底與 `/card history`；卡冊加上收集進度與合成 / 融合捷徑（只有卡冊主人看得到）；圖鑑顯示自己的收藏；新增體力系統與 `/leaderboard`；測試放進 `tests/`。
14. 新增 `tools/botcli.py`：不連 Discord 就能假裝打指令、點按鈕與選單、送出 Modal 來測試機器人（沙盒資料庫 `.botcli/`）。
15. 新增實機工具：`botcli --live` 把畫面真的送到測試頻道讓 Discord 驗證、`tools/discord_peek.py` 讀頻道看實機結果（測試頻道沿用 log 頻道）。
16. 道具改版：Item.db 加上 `effect` 欄位；刪除全部 83 個舊 demo 道具與所有玩家背包（備份在 `Database/backups/`），換成 4 個體力道具；簽到送 🍙；資料卡新增「⚡ 恢復體力」；`add_item` 改為原子操作；新增第二位管理員。
17. `/admin-item give_item` 與 `/admin-user take_item` 合併成 `/admin-item manage`（分類 + 分頁 + 堆疊列表 → Modal 輸入數量，正數給予、負數扣除，不能扣到小於 0）。
18. 卡面：ComfyUI 生成角色圖、套上綠幕去背的空白卡框、寫稱號 / 名字 / 等級圖（`tools/card_art/`）；縮圖改成依「角色＋階級」顯示。之後一位一位補角色卡面（進度見第 4 節「卡面」）。
19. 經濟系統 v0.23.000（2026-11-05）：背包改名神社倉庫、抽卡改價、神社經營、浮動市值、分解、市場、轉帳；新增 `CHANGELOG.md` 與版本號（之後的歷程以 CHANGELOG 為準）。

之後的歷程看根目錄 `CHANGELOG.md`。

# 🧩 外掛 skill：Matt Pocock skill 包

> 2026-11-19 使用者決定安裝 (統整查過內容後 grill 定案)。「不要用」的清單與使用規則在 `docs/handbook/workflow.md` 第 9 節，細節在這裡。

## 安裝方式
- **外掛 (plugin)** `mattpocock-skills@claude-plugins-official`，寫在專案的 `.claude/settings.json` (`enabledPlugins`)，跟著 git 走。**⚠️ 還沒確認真的會載入**：要在主資料夾 pull、開新對話，看 skill 清單有沒有 `mattpocock-skills:grill-me`；沒有的話改用 app 的外掛畫面或終端機 `claude plugin install mattpocock-skills@claude-plugins-official` 安裝。
- 官方商店收錄的版本：1.3.1 (repo `mattpocock/skills` commit `49dd158`，27 個 skill)，會自動更新；更新後如果多了新 skill，統整要再看一次這張表。
- skill 名字前面會加 `mattpocock-skills:` (例如 `/mattpocock-skills:grill-me`)，不會跟內建的 `/code-review` 撞名。
- **沒有跑 `/setup-matt-pocock-skills`** (使用者決定)：它會建 `docs/agents/*`、改 CLAUDE.md、要選 issue 追蹤。
- 「不要用」的 11 個另外在 `.claude/settings.json` 的 `skillOverrides` 設成 `user-invocable-only` (使用者選的：Claude 不會自己觸發，使用者打 `/mattpocock-skills:<名字>` 還是能用)。這個設定的 key 格式 (`外掛名:skill名`) 還沒實際確認有效，所以 `docs/handbook/workflow.md` 第 9 節也寫一份「不要用」當第二道防線。
- **MCP：27 個 skill 都不需要 MCP**，外掛本身也沒有附 MCP 伺服器、hook 或指令。

## 全部 27 個 skill
「自動」= Claude 覺得用得上就會自己觸發 (沒有 `disable-model-invocation`)；其他的要打 `/指令` 才會跑。

| skill | 做什麼 | 需要的工具 | 自動 | 本專案 |
|---|---|---|---|---|
| grill-me | 一直追問，把計畫想清楚 (轉呼叫 grilling) | 無 | | ✅ |
| grilling | grill 的本體：一輪一輪問、每題給建議答案 | 無 (查事實可用子任務) | ✅ | ✅ |
| handoff | 把對話濃縮成交接文件 | 無 (存到系統暫存資料夾) | | ✅ |
| teach | 教使用者一個新概念 | 無 | | ✅ |
| to-questionnaire | 把答不出來的決定做成問卷給別人填 | 無 | | ✅ |
| wait-what | 上一則沒講清楚，重講一次 | 無 | | ✅ |
| writing-for-agents | 寫給 AI 看的文件 (skill、CLAUDE.md) | 無 | ✅ | ✅ 改 CLAUDE.md / docs 時可用 |
| ask-matt | 問「這種情況用哪個 skill」 | 子任務 | | ✅ |
| diagnosing-bugs | 難抓的 bug / 效能問題的除錯流程 | Playwright (選用) | ✅ | ✅ |
| research | 查一手資料、整理成 Markdown | 背景子任務 | ✅ | ✅ 結果存到 `docs/` |
| tdd | 測試先行 (紅 → 綠) | 無 | ✅ | ✅ 照 `tests/` 的寫法 (`check()` + `run_all.py`)，不建 GLOSSARY；它說的「重構交給 `code-review`」改用內建 `/code-review` |
| codebase-design | 「深模組」設計用語 | 無 (範例偏 TypeScript) | ✅ | ✅ |
| improve-codebase-architecture | 找可以整併的地方、出 HTML 報告再 grill | 無 | | ✅ 統整巡視用；它會叫 `domain-modeling` 更新 GLOSSARY / ADR，**這步跳過** |
| prototype | 做一次性的原型試手感 | 瀏覽器 | ✅ | ✅ 原型放暫存資料夾；它說的「開拋棄式分支、貼到 issue」不要做 (開分支要先問使用者、沒有 issue) |
| retro | 回顧一段工作 | 無 | | ✅ |
| wizard | 產生一步一步帶人操作的 bash 精靈 (例如雲端設定) | bash + 瀏覽器 | ✅ | ✅ 雲端部署可用；`.env` 不進 git |
| pr | 寫 PR 說明 | 無 | ✅ | 🚫 不開 PR，直接推 main |
| code-review | 依標準 + 規格審程式 | git (要有規格 / issue) | ✅ | 🚫 用內建的 `/code-review` |
| triage | issue 分類流程 | issue 追蹤 (`gh` / `glab`) | | 🚫 沒在用 issue |
| to-spec | 把對話整理成規格發到 issue | issue 追蹤 | | 🚫 |
| to-tickets | 把計畫拆成工作票 | issue 追蹤 | | 🚫 |
| wayfinder | 超大型工作拆成決策票 | issue 追蹤 + 子任務 | | 🚫 |
| implement-spec | 照 to-spec / to-tickets 的結果實作 | 子任務 | | 🚫 |
| implement | 照規格 / 工作票實作 | 規格或工作票 | | 🚫 |
| setup-matt-pocock-skills | 設定 issue 追蹤、標籤、文件位置 | `gh` / `glab` | | 🚫 使用者決定不跑 |
| domain-modeling | 建 `GLOSSARY.md`、`docs/adr/` | 無 | ✅ | 🚫 跟本專案的文件樹衝突 |
| grill-with-docs | grill + 順便建 GLOSSARY / ADR | 無 | | 🚫 同上，改用 grill-me |

包裡另外有 `in-progress/`、`misc/` 資料夾的 skill，不在外掛裡，沒有安裝。

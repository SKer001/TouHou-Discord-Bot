# 🛠️ 開發工具安裝 (CodeGraph)

> 從 `CLAUDE.md` 拆出來的細節文件 (2026-11-11)。要做這方面的工作時才讀；改了內容記得一起更新。

- **CodeGraph（2026-11-05 筆電已安裝）**：colbymchenry/codegraph（MIT），幫 Claude Code 建程式碼索引的 MCP（`codegraph_explore` 等工具，一次查到符號原始碼與呼叫關係）。安裝：Node.js LTS（`winget install OpenJS.NodeJS.LTS`）→ `npm i -g @colbymchenry/codegraph` → `codegraph install --target claude --location global --yes`（會改 `~/.claude.json`、`~/.claude/settings.json` 的自動允許、`~/.claude/CLAUDE.md`）→ 專案根目錄 `codegraph init -y` 建索引（`.codegraph/` 已加入 `.gitignore`，每台電腦各自建）→ 重開 Claude Code。會收匿名使用統計，`codegraph telemetry off` 可關（筆電已關）。桌機還沒裝。

# 📚 文件總目錄

> 專案所有文件的目錄：每份一句「什麼時候讀」。只讀跟這次工作有關的，不用全部讀。
> 新增、搬動或刪掉文件時，記得回來改這張表。

## 🏠 根目錄
| 文件 | 什麼時候讀 |
|---|---|
| `README.md` | 第一次看這個專案：功能、指令、安裝與執行、怎麼新增角色、怎麼跑測試 |
| `ARCHITECTURE.md` | 新增 / 修改功能前：分層、Cog / 畫面 / 資料層的寫法、新增功能檢查清單 |
| `TODO.md` | 想知道目前進度、接下來要做什麼、哪些事還在等使用者決定 |
| `CHANGELOG.md` | 要 commit 時 (每次都要補一筆、編版本號)；想知道最近幾個版本 (0.39 起) 做了什麼、踩過什麼坑 |
| `Events/README.md` | 新增或修改活動檔 (`Events/<id>.json`)：格式與所有預留位 |

## 📒 handbook：怎麼在這個專案工作
| 文件 | 什麼時候讀 |
|---|---|
| `docs/handbook/workflow.md` | 開始工作前：工作手冊 (使用者的決定與工作習慣、分工、commit / 版本號 / 推送的規矩) |
| `docs/handbook/sessions.md` | 接手某個角色 (統整 / 玩法 / 卡面 / 名片) 的工作時：各角色做過什麼、交接事項 |
| `docs/handbook/skills.md` | 想用外掛 skill (Matt Pocock skill 包) 時：哪些能用、哪些不要用、需要什麼工具 |

## 🎮 gameplay：玩法與數值
| 文件 | 什麼時候讀 |
|---|---|
| `docs/gameplay/cogs.md` | 改指令、玩法規則、數值 (抽卡、神社、經濟、市場、交易…) 前：各 Cog 的重點 |
| `docs/gameplay/ura.md` | 改 🌀 裏世界 (`/ura`) 時：搜打撤玩法的規則、定案紀錄與進度 |
| `docs/gameplay/ura_roster.md` | 要查裏世界角色 / 敵人數值一覽時 (自動產生，不要手改；資料改了跑 `python tools/ura_roster.py` 重產) |

## 🛠️ dev：開發
| 文件 | 什麼時候讀 |
|---|---|
| `docs/dev/structure.md` | 要找東西放在哪裡、新增或搬動檔案時：專案結構 (每個資料夾與檔案是做什麼的) |
| `docs/dev/components-v2.md` | 寫或改 Discord 畫面時：Components V2 的寫法與限制 |
| `docs/dev/database.md` | 動資料表、資料庫函式、道具、角色檔格式時 |
| `docs/dev/testing.md` | 跑測試、補測試、用 botcli 模擬或做實機驗證時 |
| `docs/dev/new-characters.md` | 新增一代角色 (TH07 之後) 時：流程、要改的檔案、稱號 / 階級慣例、查過的角色資料 |
| `docs/dev/deploy.md` | 雲端部署 (Google Cloud)、本機 ⇄ 雲端交接、雲端資料庫備份時 |
| `docs/dev/setup.md` | 新電腦要裝開發工具 (CodeGraph 程式碼索引) 時 |
| `docs/dev/history.md` | 想知道早期重構的來龍去脈時 (平常不用讀) |

## 🎨 art：美術
| 文件 | 什麼時候讀 |
|---|---|
| `docs/art/card-art.md` | 做卡面 / 頭像 / 名片時：生圖流程、ComfyUI、PhotoCraft、使用者的偏好與踩過的坑 |

## 🗃️ changelog：舊的開發紀錄
0.39 起的紀錄在根目錄 `CHANGELOG.md`；更早的照第二段版本號分檔放在 `docs/changelog/`。要查某個舊功能當初怎麼做、為什麼這樣改時才讀。

| 文件 | 內容 |
|---|---|
| `docs/changelog/0.38.md` | 0.38.xxx：⚡ 自動合成全部、⚗️ 繼續合成 |
| `docs/changelog/0.37.md` | 0.37.xxx：抽卡機率改版、活動可以同時開好幾個 |
| `docs/changelog/0.36.md` | 0.36.xxx：📚 教學書 |
| `docs/changelog/0.35.md` | 0.35.xxx (最大的一份)：高清卡面、角色名片、🌀 裏世界從規劃到三階段完成 |
| `docs/changelog/0.34.md` | 0.34.xxx：📜 活動任務 `/event quest`、舊作角色的卡面與名片 |
| `docs/changelog/0.33.md` | 0.33.xxx：🖼️ 角色名片 |
| `docs/changelog/0.32.md` | 0.32.xxx：🔒 收藏冊、財富 / 火力 / 市場稱號 |
| `docs/changelog/0.31.md` | 0.31.xxx：玩家稱號系統 |
| `docs/changelog/0.30.md` | 0.30.xxx：主動通知 (DM)、紅魔鄉角色卡面 |
| `docs/changelog/0.29.md` | 0.29.xxx：兩台電腦環境對齊 |
| `docs/changelog/0.28.md` | 0.28.xxx：`/help` 指令說明 |
| `docs/changelog/0.27.md` | 0.27.xxx：神社廚房 (採集 → 料理 → 招待)、參拜客頭像 |
| `docs/changelog/0.26.md` | 0.26.xxx：神社倉庫搬家、招待料理、累積簽到 |
| `docs/changelog/0.25.md` | 0.25.xxx：重載控制台、市場與轉帳搬家 |
| `docs/changelog/0.24.md` | 0.24.xxx：經濟系統私人化 |
| `docs/changelog/0.23.md` | 0.23.xxx：經濟系統 (神社經營、浮動市值、分解、市場) |
| `docs/changelog/0.22.md` | 0.22.xxx：開始寫開發紀錄、神社倉庫、抽卡改價 |
| `docs/changelog/early.md` | 0.01 ～ 0.21：依 git 歷史回推的早期版本 (專案建立到高清分層卡面) |

# ☁️ 雲端部署 (Google Cloud，24 小時執行)

> 2026-11-17 建立。要做部署、交接、雲端備份相關的工作時才讀；改了流程記得一起更新這份。
> 部署用的檔案都在 `deploy/`：`vm_ctl.py` (VM 上)、`handoff.py` (筆電 / 桌機)、`install.sh`、`systemd/`、`requirements.lock.txt`、`gcs-lifecycle.json`。

## 1. 決定 (2026-11-17 使用者確認)
| 項目 | 決定 |
|---|---|
| 服務 | Compute Engine **e2-micro** (免費方案，1 GB RAM) + 30 GB 標準硬碟，Debian 12 (Python 3.11，跟筆電一樣) |
| 區域 | **us-west1** (奧勒岡，區 `us-west1-b`)；免費方案只限美國 3 區，Discord 伺服器也在美國 |
| 誰在跑 | 平常是雲端；**本機要實機測試時用交接腳本把雲端停掉、拿走 DB**，測完交回。同一個 Token，同一時間只有一邊在線 |
| 程式更新 | VM 跟 **`online` 分支**。main 照常推；`online` 是穩定版，**只有修 bug、新活動時，使用者說可以才** `python deploy/handoff.py deploy` 把 main 快轉推到 online (2026-11-24)，VM 每分鐘檢查、1 分鐘內自動更新 |
| DB 放哪 | **私人 Cloud Storage 儲存桶** (交接 + 每日備份)。主 repo 維持公開 (卡面網址要公開)，玩家的真實 DB 不進 git |
| 建資源 | 使用者同意後由 AI 助手用 `gcloud` 做；帳號、登入、計費由使用者自己處理 |
| Firebase | 這次不做 (要重寫整個資料層)；之後想改再另開任務 |

- **`online` 永遠等於某一版 main** (只快轉、不在 online 上單獨 commit)，所以部署檔也在 main，版本號 / CHANGELOG 不會分岔。
- 主 repo 的 `Database/Users.db` **從此只是開發 / 測試資料**，雲端不會讀它 (VM 同步程式時排除所有 `Database/*.db`)。

## 2. 運作方式
```
GitHub online 分支 ──(每分鐘 fetch)──▶ /opt/touhou-bot/repo   (root；稀疏 clone，約 13 MB，不抓卡面原圖)
                                         │ rsync (排除 .env、Database/*.db、Logger/Logs)
                                         ▼
                                  /opt/touhou-bot/app    (touhou 使用者；機器人在這裡跑)
                                         │  .env、Database/Users.db、Item.db、Logger/Logs 只在這裡
                                         ▼
                                  touhou-bot.service  ─ venv /opt/touhou-bot/venv (requirements.lock.txt)

/var/lib/touhou-bot/mode      cloud 或 local:<電腦名稱> (local 時 VM 不准啟動機器人)
/var/lib/touhou-bot/backups/  VM 本機快照 (留 7 天)
gs://<bucket>/live/           交接用：Users.db、Item.db、meta.json (雜湊)
gs://<bucket>/backups/        每日 04:00 (台灣) 快照 + 每次更新前的快照，30 天自動刪除
```
- **自動更新** (`touhou-update.timer`)：online 有新 commit ➔ 只有圖片 / 文件 / 測試 / `tools/` / `.md` 變動就只同步不重啟；其他變動 ➔ 停機器人 ➔ 先快照 DB (`pre-update`) ➔ 同步 ➔ (`requirements.lock.txt` 變了才 pip install；`deploy/systemd/` 變了才重裝設定) ➔ 啟動。
- **資料表結構改了**：不用搬 DB。`init_db()` / `init_item_db()` 開機時會自己 `ALTER TABLE` 補欄位，部署 = 重啟 = 遷移；萬一遷移出事，更新前那份快照在儲存桶 `backups/*-pre-update/`。所以**改結構時一定要寫在 init_db 的遷移裡**，不要只在本機手動改 DB。
- **主控台指令** (`help` / `reload` / `money`…) 在雲端不能用 (systemd 底下沒有終端機，`Utils/console.py` 會自動略過)；用 Discord 的 `/admin-*` 指令代替。
- `PYTHONIOENCODING=utf-8`、`PYTHONUNBUFFERED=1` 寫在 `touhou-bot.service`，log 用 `journalctl` 看。

## 3. 第一次設定 (照順序做)
### 3.1 使用者自己做 (帳號、登入、付款)
1. 開 Google Cloud 帳號、建一個專案 (記下**專案 ID**)、在主控台把專案**連結計費帳戶** (免費方案也要綁卡)。
2. 建議在「帳單 ➔ 預算與快訊」設一個小預算提醒 (例如 US$5)，超過免費額度會寄信。
3. 筆電 (之後桌機也要) 安裝 **Google Cloud CLI**，打開新的終端機執行：
   ```
   gcloud auth login
   gcloud config set project <專案ID>
   ```

### 3.2 建立資源 (AI 助手跑或自己跑；PowerShell 寫法)
```powershell
$P = "<專案ID>"; $B = "$P-touhou-db"; $Z = "us-west1-b"
gcloud services enable compute.googleapis.com storage.googleapis.com --project $P

# VM 用的服務帳戶：只給它這個儲存桶的權限
gcloud iam service-accounts create touhou-bot --display-name "TouHou Bot VM" --project $P

# 私人儲存桶 (同區域，傳輸免費)；禁止公開存取、30 天刪舊備份
gcloud storage buckets create gs://$B --project $P --location us-west1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://$B --lifecycle-file deploy/gcs-lifecycle.json
gcloud storage buckets add-iam-policy-binding gs://$B --member "serviceAccount:touhou-bot@$P.iam.gserviceaccount.com" --role roles/storage.objectAdmin

# VM：e2-micro、Debian 12、30 GB 標準硬碟
gcloud compute instances create touhou-bot --project $P --zone $Z --machine-type e2-micro `
  --image-family debian-12 --image-project debian-cloud --boot-disk-size 30GB --boot-disk-type pd-standard `
  --service-account "touhou-bot@$P.iam.gserviceaccount.com" --scopes cloud-platform
```
- **防火牆不用開任何埠**：機器人只往外連 Discord；預設網路本來就有允許 SSH (22) 的規則，`gcloud compute ssh` 用它。
- 第一次 `gcloud compute ssh` 會產生 SSH 金鑰 (Windows 會用內附的 PuTTY)，照提示按 Enter 即可。

### 3.3 VM 上安裝
```powershell
gcloud compute ssh touhou-bot --zone us-west1-b --command "curl -fsSL https://raw.githubusercontent.com/SKer001/TouHou-Discord-Bot/online/deploy/install.sh -o install.sh && sudo bash install.sh --bucket <儲存桶名稱>"
```
`install.sh` 可以重複執行。它會檢查 `python3 --version` ≥ 3.11、加 1 GB swap、建 `touhou` 使用者、稀疏 clone、建 venv、裝 systemd 設定並開啟更新 / 備份計時器。**機器人本體不會啟動** (模式 `local:setup`)。

### 3.4 `.env` 與第一次交上 DB
1. 本機 `.env` (不進 git) 加上：
   ```
   GCP_PROJECT=<專案ID>
   GCP_BUCKET=<儲存桶名稱>
   ```
   (`GCP_ZONE` 預設 `us-west1-b`、`GCP_VM` 預設 `touhou-bot`，有改才要寫。) 桌機的 `.env` 也要加。
2. `python deploy/handoff.py push-env` ➔ 把這台的 `.env` 上傳到 VM (`/opt/touhou-bot/app/.env`，權限 600，只有 touhou 讀得到)。Token 換了也是重跑這行。開發用的 `SHOW_UNRELEASED` (看得到未公開卡池) 上傳時會自動濾掉 (1.00.000)，正式機器人不會有這個變數。
3. **先關掉本機機器人**，在「最後跑機器人、有最新 Users.db」的那台執行 `python deploy/handoff.py release` ➔ 上傳 `Database/Users.db`、`Item.db`，雲端接手並啟動。
4. `python deploy/handoff.py status` 確認 `模式：cloud`、`🟢 執行中`，Discord 上看到機器人上線。

## 4. 日常
| 要做什麼 | 指令 (在筆電 / 桌機的專案資料夾) |
|---|---|
| 程式上線 | 只有修 bug / 新活動、使用者說可以時：測試過、`SHOW_UNRELEASED=0` 看過 ➔ `python deploy/handoff.py deploy` (把 origin/main 快轉推到 online，中間的 commit 會一起上去) |
| 本機實機測試 | `python deploy/handoff.py take` ➔ `python Main.py` ➔ 關掉 ➔ `python deploy/handoff.py release` |
| 拿雲端備份 | `python deploy/handoff.py backup` ➔ 存到 `Database/backups/cloud/<時間>/` (gitignore) |
| 看狀態 | `python deploy/handoff.py status` |
| 看 log / 進 VM | `python deploy/handoff.py ssh`，再 `sudo journalctl -u touhou-bot -f` (更新紀錄：`-u touhou-update`) |
| 手動重啟 / 強制更新 | VM 上 `sudo systemctl restart touhou-bot` / `sudo python3 /opt/touhou-bot/repo/deploy/vm_ctl.py update --force` |

- **take** 會先把本機原本的 `Database/*.db` (測試資料) 收到 `Database/backups/handoff/pre-take-*`，**release** 交回後再放回去，所以玩家真實資料不會被順手 commit 進公開 repo。交出去的那份也會在 `Database/backups/handoff/released-*` 留一份。
- 只有 take 的那台可以 release (VM 記著是哪台)。筆電 take 了、要換桌機交回，加 `--force`，**但要確定筆電那份已經沒在用**，不然筆電的資料會被蓋掉。
- take 期間 VM 照樣會自動更新程式，只是不啟動機器人。
- 機器人在雲端跑時，**本機不要用正式 Token 執行 `python Main.py`** (會兩邊同時上線)。`tools/botcli.py` 與測試不連 Discord Gateway，可以照常用；`botcli --live` 只用 REST 發訊息，也沒問題。

## 5. 疑難排解
- **`release` 被拒絕「雲端已經在跑了」**：代表沒有 take 過 (第一次上雲除外)；雲端那份才是最新的，不要硬蓋。真的要用本機那份蓋掉雲端：`release --force` (雲端舊的那份會先存到 VM 的 `before-takeback` 備份)。
- **`take` 中途失敗**：雲端已經停了的話，模式會是 `local:<這台>`，重跑 `take` 會被拒；到 VM 上看 `/var/lib/touhou-bot/backups/` 最新那份 `release-*`，或直接 `release` 交回去重來。
- **機器人起不來**：`sudo journalctl -u touhou-bot -n 100`。模式不是 cloud 時 `check-mode` 會擋下啟動 (這是故意的)。
- **VM 重開機**：模式是 cloud 就自動啟動；local 就不會。
- **記憶體**：e2-micro 1 GB + 1 GB swap；`free -h` 看。真的不夠再換 e2-small (要付費)。

## 6. 費用 (以帳單為準)
- 免費方案 (官方 2026-11 頁面)：每月 1 台 e2-micro (限 us-west1 / us-central1 / us-east1)、30 GB 標準硬碟、北美出站流量 1 GB。機器人回 Discord 的流量很小，備份傳到同區域的儲存桶不算出站。
- **外部 IPv4 位址**：機器人要連外網一定要有。官方免費方案頁沒寫是否收費，可能每月幾美元；開好後幾天去帳單看一下。
- Cloud Storage：DB 只有幾百 KB，30 天的每日備份遠低於免費額度。

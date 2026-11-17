#!/usr/bin/env bash
# ☁️ VM 第一次安裝 (Debian 12，在 VM 上以 root 執行；可以重複執行)
#
#   curl -fsSL https://raw.githubusercontent.com/SKer001/TouHou-Discord-Bot/online/deploy/install.sh -o install.sh
#   sudo bash install.sh --bucket <儲存桶名稱>
#
# 做的事：裝 git / rsync / python3-venv ➔ 建 touhou 使用者 ➔ 稀疏 clone online 分支 (不抓卡面原圖)
# ➔ 建 venv 裝套件 ➔ 同步到 /opt/touhou-bot/app ➔ 裝 systemd 設定、開更新 / 備份計時器。
# 機器人本體「不會」啟動：模式是 local:setup，要等本機跑 `python deploy/handoff.py release` 把 DB 交上來。
set -euo pipefail

BUCKET=""
BRANCH="online"
REPO_URL="https://github.com/SKer001/TouHou-Discord-Bot.git"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bucket) BUCKET="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --repo)   REPO_URL="$2"; shift 2 ;;
    *) echo "不認得的參數：$1"; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "❌ 要用 sudo 執行"; exit 1; }
[[ -n "$BUCKET" ]] || { echo "❌ 要給 --bucket <儲存桶名稱>"; exit 1; }

BASE=/opt/touhou-bot
REPO=$BASE/repo

echo "📦 安裝系統套件…"
apt-get update -qq
apt-get install -y -qq git rsync python3-venv python3-pip sqlite3 >/dev/null
command -v gcloud >/dev/null || { echo "❌ 找不到 gcloud (Google 的 Debian 映像檔應該內建)，請先安裝 google-cloud-cli"; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 11), sys.version' \
  || { echo "❌ Python 版本太舊 ($(python3 --version))，需要 3.11 以上"; exit 1; }
echo "🐍 $(python3 --version)"

# e2-micro 只有 1 GB 記憶體：加 1 GB swap，pip 裝 Pillow 或流量尖峰時比較不會被 OOM 砍掉
if ! swapon --show | grep -q /swapfile; then
  echo "💽 建立 1 GB swap…"
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

id touhou >/dev/null 2>&1 || useradd --system --home-dir $BASE --shell /usr/sbin/nologin touhou
mkdir -p $BASE /var/lib/touhou-bot/backups /etc/touhou-bot
chmod 755 /var/lib/touhou-bot

cat > /etc/touhou-bot/config <<EOF
# vm_ctl.py 的設定
BUCKET=$BUCKET
BRANCH=$BRANCH
EOF

if [[ ! -d $REPO/.git ]]; then
  echo "⬇️  稀疏 clone $BRANCH 分支 (只抓最新一版、不抓卡面原圖)…"
  git clone --quiet --depth 1 --filter=blob:none --no-checkout --single-branch --branch "$BRANCH" "$REPO_URL" $REPO
  # 執行時只需要 images/*.json，images/ 底下的子資料夾 (原圖、縮圖) 跟 tools/ 都不用
  git -C $REPO sparse-checkout set --no-cone '/*' '!/images/*/' '!/tools/'
  git -C $REPO checkout --quiet "$BRANCH"
else
  echo "🔄 已經 clone 過，抓最新…"
  git -C $REPO fetch --quiet --depth 1 origin "$BRANCH"
  git -C $REPO reset --quiet --hard FETCH_HEAD
fi
du -sh $REPO

if [[ ! -x $BASE/venv/bin/python ]]; then
  python3 -m venv $BASE/venv
fi
$BASE/venv/bin/pip install --quiet --upgrade pip
$BASE/venv/bin/pip install --quiet -r $REPO/deploy/requirements.lock.txt

[[ -f /var/lib/touhou-bot/mode ]] || echo "local:setup" > /var/lib/touhou-bot/mode

# 同步程式到 app/ 並裝 systemd 設定 (都走 vm_ctl.py，跟之後自動更新同一套)
python3 - <<'PY'
import sys
sys.path.insert(0, "/opt/touhou-bot/repo/deploy")
import vm_ctl
vm_ctl.sync_app()
vm_ctl.install_units()
vm_ctl.write_applied(vm_ctl.git("rev-parse", "HEAD"))
PY
mkdir -p $BASE/app/Logger/Logs && chown -R touhou:touhou $BASE/app

systemctl enable --now touhou-update.timer touhou-backup.timer
systemctl disable touhou-bot.service 2>/dev/null || true

echo
echo "✅ 安裝完成 (模式 $(cat /var/lib/touhou-bot/mode))"
[[ -f $BASE/app/.env ]] || echo "⚠️  還沒有 .env：在本機執行 python deploy/handoff.py push-env"
echo "下一步：在有最新 Users.db 的那台電腦執行 python deploy/handoff.py release"

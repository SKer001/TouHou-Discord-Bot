"""☁️ 雲端 VM 上的控制腳本 (在 VM 上以 root 執行；說明見 docs/dev/deploy.md)

    sudo python3 /opt/touhou-bot/repo/deploy/vm_ctl.py <指令>

指令：
  status            模式、版本、服務狀態、最近的備份
  update [--force]  抓 online 分支最新 commit ➔ 同步程式 ➔ 有需要才重啟 (每分鐘由 touhou-update.timer 執行)
  backup [--tag X]  用 SQLite 備份 API 快照 Users.db / Item.db ➔ 存 VM 本機 + 上傳 gs://<bucket>/backups/
  release HOLDER    雲端 ➔ 本機：停機器人、快照上傳 gs://<bucket>/live/、模式改成 local:HOLDER
  takeback HOLDER   本機 ➔ 雲端：從 gs://<bucket>/live/ 下載 DB、模式改回 cloud、啟動機器人
  install-units     把 deploy/systemd/ 的設定複製到 /etc/systemd/system/ 並重新載入
  check-mode        模式是 cloud 才回傳 0 (touhou-bot.service 啟動前的保險)

只用標準函式庫，Debian 內建的 python3 就能跑。
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys

BASE = "/opt/touhou-bot"
REPO = f"{BASE}/repo"            # git 稀疏 clone (root 擁有，只放程式，不放執行中的資料)
APP = f"{BASE}/app"              # 機器人實際執行的資料夾 (rsync 自 REPO；.env、DB、Logs 只在這裡)
VENV = f"{BASE}/venv"
STATE = "/var/lib/touhou-bot"
MODE_FILE = f"{STATE}/mode"      # cloud 或 local:<電腦名稱>
APPLIED_FILE = f"{STATE}/applied_commit"   # 上次成功同步到 app/ 的 commit
BACKUP_DIR = f"{STATE}/backups"
LOCK_FILE = f"{STATE}/vm_ctl.lock"
CONFIG_FILE = "/etc/touhou-bot/config"
SERVICE = "touhou-bot.service"
RUN_USER = "touhou"
DB_FILES = ("Users.db", "Item.db")
KEEP_LOCAL_BACKUP_DAYS = 7

# 這些路徑的變動不影響執行中的機器人 ➔ 只同步、不重啟
NO_RESTART_PREFIXES = ("docs/", "tests/", "tools/", ".claude/")
# rsync 時保護 APP 裡的執行資料 (不會被覆蓋或刪掉)
RSYNC_EXCLUDES = (
    "/.git", "/.env", "/Database/*.db", "/Database/*.db-journal", "/Database/*.db-wal", "/Database/*.db-shm",
    "/Database/backups/", "/Logger/Logs/", "/.botcli/", "__pycache__/",
)


# ---------------------------------------------------------
# 🧮 純邏輯 (tests/test_deploy.py 會測)
# ---------------------------------------------------------
def needs_restart(changed: list[str]) -> bool:
    """有任何會影響執行的檔案變動就要重啟；圖片子資料夾、文件、測試、工具、.md 不用"""
    for path in changed:
        path = path.strip()
        if not path:
            continue
        if path.startswith("images/") and path.count("/") >= 2:   # images/<子資料夾>/... 是圖片本體
            continue
        if path.startswith(NO_RESTART_PREFIXES) or path.endswith(".md"):
            continue
        return True
    return False


def safe_holder(name: str) -> str:
    """電腦名稱只留英數、底線、減號 (會放進 ssh 指令與模式檔)"""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", name or "")[:40]
    if not cleaned:
        raise ValueError("電腦名稱是空的")
    return cleaned


def parse_mode(text: str) -> tuple[str, str]:
    """'cloud' ➔ ('cloud', '')；'local:LAPTOP' ➔ ('local', 'LAPTOP')；其他當成 ('unknown', 原文)"""
    text = (text or "").strip()
    if text == "cloud":
        return "cloud", ""
    if text.startswith("local:"):
        return "local", text[len("local:"):]
    return "unknown", text


def can_takeback(mode_text: str, holder: str, force: bool) -> tuple[bool, str]:
    kind, who = parse_mode(mode_text)
    if force:
        return True, ""
    if kind == "cloud":
        return False, "雲端已經在跑了，不需要交回"
    if kind == "local" and who in (holder, "setup"):
        return True, ""
    return False, f"目前是 {mode_text.strip() or '(空白)'}，不是 local:{holder}；確定要交回請加 --force"


def parse_config(text: str) -> dict:
    config = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip().strip('"')
    return config


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_db(src: str, dst: str):
    """SQLite 備份 API：機器人還在寫也能拿到一致的快照 (不要直接 cp 執行中的 DB)"""
    if os.path.exists(dst):
        os.remove(dst)
    source = sqlite3.connect(src)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


# ---------------------------------------------------------
# 🔧 VM 上的動作
# ---------------------------------------------------------
def log(msg: str):
    print(f"[vm_ctl {datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def run(cmd: list[str], check=True, capture=False, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, cwd=cwd, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None)


def git(*args) -> str:
    return run(["git", "-C", REPO, *args], capture=True).stdout.strip()


def config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return parse_config(f.read())


def bucket() -> str:
    name = config().get("BUCKET", "")
    if not name:
        raise SystemExit(f"❌ {CONFIG_FILE} 沒有設定 BUCKET")
    return name


def read_mode() -> str:
    try:
        with open(MODE_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "local:setup"


def write_mode(text: str):
    os.makedirs(STATE, exist_ok=True)
    with open(MODE_FILE, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    log(f"模式 ➔ {text}")


def systemctl(*args, check=True):
    return run(["systemctl", *args], check=check)


def service_active() -> bool:
    return run(["systemctl", "is-active", "--quiet", SERVICE], check=False).returncode == 0


def stop_bot():
    if service_active():
        log("停止機器人…")
    systemctl("stop", SERVICE, check=False)


def start_bot():
    log("啟動機器人…")
    systemctl("start", SERVICE)


def gcs_cp(src: str, dst: str):
    run(["gcloud", "storage", "cp", "--quiet", src, dst])


def sync_app():
    """REPO ➔ APP (保留 .env、DB、Logs)"""
    os.makedirs(APP, exist_ok=True)
    cmd = ["rsync", "-a", "--delete", f"--chown={RUN_USER}:{RUN_USER}"]
    cmd += [f"--exclude={pattern}" for pattern in RSYNC_EXCLUDES]
    run(cmd + [f"{REPO}/", f"{APP}/"])


def pip_install():
    log("安裝套件 (requirements.lock.txt)…")
    run([f"{VENV}/bin/pip", "install", "--quiet", "-r", f"{REPO}/deploy/requirements.lock.txt"])


def install_units():
    for name in sorted(os.listdir(f"{REPO}/deploy/systemd")):
        shutil.copyfile(f"{REPO}/deploy/systemd/{name}", f"/etc/systemd/system/{name}")
    systemctl("daemon-reload")
    log("systemd 設定已更新")


def make_backup(tag: str, upload: bool = True) -> str:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = f"{BACKUP_DIR}/{stamp}-{tag}"
    os.makedirs(folder, exist_ok=True)
    for name in DB_FILES:
        src = f"{APP}/Database/{name}"
        if os.path.exists(src):
            snapshot_db(src, f"{folder}/{name}")
    log(f"備份 ➔ {folder}")
    if upload:
        try:
            for name in DB_FILES:
                if os.path.exists(f"{folder}/{name}"):
                    gcs_cp(f"{folder}/{name}", f"gs://{bucket()}/backups/{stamp}-{tag}/{name}")
        except subprocess.CalledProcessError as e:
            log(f"⚠️ 上傳備份失敗 (本機那份還在)：{e}")
    prune_local_backups()
    return folder


def prune_local_backups():
    cutoff = datetime.datetime.now() - datetime.timedelta(days=KEEP_LOCAL_BACKUP_DAYS)
    if not os.path.isdir(BACKUP_DIR):
        return
    for name in os.listdir(BACKUP_DIR):
        path = f"{BACKUP_DIR}/{name}"
        if os.path.isdir(path) and datetime.datetime.fromtimestamp(os.path.getmtime(path)) < cutoff:
            shutil.rmtree(path, ignore_errors=True)


def version() -> str:
    try:
        with open(f"{APP}/Utils/version.py", encoding="utf-8") as f:
            match = re.search(r'VERSION\s*=\s*"([^"]+)"', f.read())
        return match.group(1) if match else "?"
    except FileNotFoundError:
        return "?"


# ---------------------------------------------------------
# 📋 指令
# ---------------------------------------------------------
def cmd_status(_args):
    print(f"模式：{read_mode()}")
    print(f"版本：{version()}  (commit {git('rev-parse', '--short', 'HEAD')})")
    print(f"機器人：{'🟢 執行中' if service_active() else '⚪ 停止'}")
    if os.path.isdir(BACKUP_DIR):
        latest = sorted(os.listdir(BACKUP_DIR))[-3:]
        print(f"最近的備份：{', '.join(latest) or '(無)'}")


def read_applied() -> str:
    try:
        with open(APPLIED_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def write_applied(commit: str):
    with open(APPLIED_FILE, "w", encoding="utf-8") as f:
        f.write(commit + "\n")


def commit_exists(commit: str) -> bool:
    return bool(commit) and run(["git", "-C", REPO, "cat-file", "-e", f"{commit}^{{commit}}"], check=False).returncode == 0


def cmd_update(args):
    branch = config().get("BRANCH", "online")
    force = "--force" in args
    # 跟「上次成功套用的 commit」比，不跟 repo HEAD 比：同步到一半失敗時，下一分鐘會重試
    applied = read_applied()
    git("fetch", "--quiet", "--depth", "1", "origin", branch)
    new = git("rev-parse", "FETCH_HEAD")
    if applied == new and not force:
        return
    if commit_exists(applied) and applied != new:
        # --no-renames：稀疏 + blob:none 的 clone 做改名偵測會跑去下載圖片本體
        changed = git("diff", "--no-renames", "--name-only", applied, new).splitlines()
    else:
        changed, force = [], True   # 不知道上次套用到哪 ➔ 全部重來
    log(f"更新 {applied[:7] or '?'} ➔ {new[:7]}，{len(changed)} 個檔案變動{' (完整更新)' if force else ''}")
    git("reset", "--quiet", "--hard", new)

    restart = force or needs_restart(changed)
    running = parse_mode(read_mode())[0] == "cloud"
    if restart and running:
        stop_bot()
    try:
        if restart and running:
            make_backup("pre-update")
        sync_app()
        if force or "deploy/requirements.lock.txt" in changed:
            pip_install()
        if force or any(path.startswith("deploy/systemd/") for path in changed):
            install_units()
        write_applied(new)
    finally:
        # 中途失敗也要把機器人開回來 (沒寫 applied，下一分鐘會再試一次同步)
        if restart and running:
            start_bot()
    if restart and not running:
        log("程式已同步；目前模式不是 cloud，不啟動機器人")
    elif not restart:
        log("只有圖片 / 文件變動，不重啟")


def cmd_backup(args):
    tag = args[args.index("--tag") + 1] if "--tag" in args else "daily"
    if parse_mode(read_mode())[0] != "cloud":
        log(f"模式是 {read_mode()}，雲端的 DB 不是最新的，略過備份")
        return
    make_backup(tag)


def cmd_release(args):
    holder = safe_holder(args[0] if args else "")
    kind, who = parse_mode(read_mode())
    if kind == "local" and who == holder:
        # 同一台重跑 take (例如上次下載到一半失敗)：live/ 已經是交出去的那份，直接讓本機再下載
        log(f"已經交給 {holder} 了，live/ 裡就是最新的那份")
        return
    if kind != "cloud":
        raise SystemExit(f"❌ 雲端現在不是執行中 (模式 {read_mode()})，最新的 DB 在 {who or '?'} 手上")
    stop_bot()
    systemctl("disable", SERVICE, check=False)
    try:
        folder = make_backup(f"release-{holder}", upload=False)
        meta = {"holder": "cloud", "to": holder, "time": datetime.datetime.now(datetime.timezone.utc).isoformat(), "sha256": {}}
        for name in DB_FILES:
            meta["sha256"][name] = sha256(f"{folder}/{name}")
            gcs_cp(f"{folder}/{name}", f"gs://{bucket()}/live/{name}")
        with open(f"{folder}/meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        gcs_cp(f"{folder}/meta.json", f"gs://{bucket()}/live/meta.json")
    except BaseException:
        # 上傳失敗：模式還是 cloud，把機器人開回來，不要讓兩邊都沒在跑
        log("❌ 交出 DB 失敗，雲端機器人重新啟動")
        systemctl("enable", SERVICE, check=False)
        start_bot()
        raise
    write_mode(f"local:{holder}")
    log(f"✅ 已交給 {holder}，雲端機器人已停止")


def cmd_takeback(args):
    holder = safe_holder(args[0] if args else "")
    ok, reason = can_takeback(read_mode(), holder, "--force" in args)
    if not ok:
        raise SystemExit(f"❌ {reason}")
    incoming = f"{STATE}/incoming"
    shutil.rmtree(incoming, ignore_errors=True)
    os.makedirs(incoming)
    gcs_cp(f"gs://{bucket()}/live/meta.json", f"{incoming}/meta.json")
    with open(f"{incoming}/meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    for name in DB_FILES:
        gcs_cp(f"gs://{bucket()}/live/{name}", f"{incoming}/{name}")
        if sha256(f"{incoming}/{name}") != meta["sha256"].get(name):
            raise SystemExit(f"❌ {name} 的雜湊跟 meta.json 對不上，停止交接 (雲端維持停止)")
        conn = sqlite3.connect(f"{incoming}/{name}")
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        if result != "ok":
            raise SystemExit(f"❌ {name} 檢查失敗 ({result})，停止交接 (雲端維持停止)")

    stop_bot()
    if any(os.path.exists(f"{APP}/Database/{name}") for name in DB_FILES):
        make_backup("before-takeback", upload=False)   # 雲端原本那份舊 DB 也留一份
    os.makedirs(f"{APP}/Database", exist_ok=True)
    for name in DB_FILES:
        for suffix in ("-journal", "-wal", "-shm"):
            stale = f"{APP}/Database/{name}{suffix}"
            if os.path.exists(stale):
                os.remove(stale)
        shutil.copyfile(f"{incoming}/{name}", f"{APP}/Database/{name}")
        shutil.chown(f"{APP}/Database/{name}", RUN_USER, RUN_USER)
    write_mode("cloud")
    systemctl("enable", SERVICE)
    start_bot()
    log(f"✅ 已從 {meta.get('holder', '?')} 接回，雲端機器人啟動")


def cmd_check_mode(_args):
    raise SystemExit(0 if parse_mode(read_mode())[0] == "cloud" else 1)


COMMANDS = {
    "status": cmd_status,
    "update": cmd_update,
    "backup": cmd_backup,
    "release": cmd_release,
    "takeback": cmd_takeback,
    "install-units": lambda _args: install_units(),
    "check-mode": cmd_check_mode,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    name, args = argv[0], argv[1:]
    if name in ("status", "check-mode"):
        COMMANDS[name](args)
        return 0
    if os.geteuid() != 0:
        raise SystemExit("❌ 要用 sudo 執行")
    import fcntl   # 只有 Linux 有；避免 update 計時器跟交接同時動 DB
    os.makedirs(STATE, exist_ok=True)
    with open(LOCK_FILE, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        COMMANDS[name](args)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

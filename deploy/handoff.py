"""🔁 本機 ⇄ 雲端交接 (筆電 / 桌機執行；說明見 docs/deploy.md)

    python deploy/handoff.py status          雲端的模式、版本、機器人狀態
    python deploy/handoff.py take            雲端 ➔ 這台：雲端停機器人並交出最新 DB，下載到 Database/
    python deploy/handoff.py release         這台 ➔ 雲端：上傳 Database/ 的 DB，雲端接手並啟動 (先關掉本機機器人)
    python deploy/handoff.py backup          只下載雲端最新的每日備份到 Database/backups/cloud/ (不交接)
    python deploy/handoff.py deploy          把 origin/main 推到 online 分支 (雲端 1 分鐘內自動更新)
    python deploy/handoff.py push-env        把這台的 .env 上傳到 VM (Token 改了才需要)
    python deploy/handoff.py ssh             開一個 VM 的 SSH 視窗

需要：Google Cloud CLI (gcloud) 已安裝並 gcloud auth login；.env 加上
    GCP_PROJECT=<專案 ID>   GCP_BUCKET=<儲存桶名稱>   (選填) GCP_ZONE=us-west1-b   GCP_VM=touhou-bot
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(ROOT, "Database")
DB_FILES = ("Users.db", "Item.db")
HANDOFF_DIR = os.path.join(DB_DIR, "backups", "handoff")   # Database/backups/ 已在 .gitignore
LAST_TAKE = os.path.join(HANDOFF_DIR, "last_take.json")
VM_CTL = "sudo python3 /opt/touhou-bot/repo/deploy/vm_ctl.py"


def holder_name() -> str:
    """這台電腦的名字 (只留英數、底線、減號；跟 vm_ctl.safe_holder 同規則)"""
    return re.sub(r"[^A-Za-z0-9_-]", "", socket.gethostname())[:40] or "local"


def load_settings() -> dict:
    try:
        from dotenv import dotenv_values
        values = dotenv_values(os.path.join(ROOT, ".env"))
    except ImportError:
        values = {}
    settings = {
        "project": values.get("GCP_PROJECT") or os.getenv("GCP_PROJECT", ""),
        "bucket": values.get("GCP_BUCKET") or os.getenv("GCP_BUCKET", ""),
        "zone": values.get("GCP_ZONE") or os.getenv("GCP_ZONE") or "us-west1-b",
        "vm": values.get("GCP_VM") or os.getenv("GCP_VM") or "touhou-bot",
    }
    missing = [key for key in ("project", "bucket") if not settings[key]]
    if missing:
        raise SystemExit(f"❌ .env 缺少 {', '.join('GCP_' + key.upper() for key in missing)} (見 docs/deploy.md)")
    return settings


def gcloud_path() -> str:
    path = shutil.which("gcloud")
    if not path:
        raise SystemExit("❌ 找不到 gcloud，請先安裝 Google Cloud CLI 並執行 gcloud auth login")
    return path


def gcloud(*args, capture=False) -> subprocess.CompletedProcess:
    return subprocess.run([gcloud_path(), *args], check=True, text=True,
                          stdout=subprocess.PIPE if capture else None)


def vm(settings: dict, command: str):
    gcloud("compute", "ssh", settings["vm"], "--zone", settings["zone"], "--project", settings["project"],
           "--command", command)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_db(src: str, dst: str):
    """SQLite 備份 API 拿一致的快照"""
    if os.path.exists(dst):
        os.remove(dst)
    source, target = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------
# 📋 指令
# ---------------------------------------------------------
def cmd_status(settings, _args):
    vm(settings, f"{VM_CTL} status")


def cmd_take(settings, _args):
    holder = holder_name()
    print(f"☁️ ➔ 💻 請雲端停下並把 DB 交給 {holder}…")
    vm(settings, f"{VM_CTL} release {holder}")

    # 本機原本的 DB (git 裡的測試資料) 先收好，release 時放回去，玩家真實資料才不會被 commit 進公開 repo
    # 重跑 take (上次中途失敗) 時沿用第一次收好的那份，不要把半途的檔案當成本機原本的
    keep = ""
    if os.path.exists(LAST_TAKE):
        with open(LAST_TAKE, encoding="utf-8") as f:
            keep = json.load(f).get("pre_take", "")
    if not keep or not os.path.isdir(keep):
        keep = os.path.join(HANDOFF_DIR, f"pre-take-{stamp()}")
        os.makedirs(keep, exist_ok=True)
        for name in DB_FILES:
            if os.path.exists(os.path.join(DB_DIR, name)):
                shutil.copy2(os.path.join(DB_DIR, name), os.path.join(keep, name))
        with open(LAST_TAKE, "w", encoding="utf-8") as f:
            json.dump({"holder": holder, "time": stamp(), "pre_take": keep}, f, ensure_ascii=False, indent=2)

    with tempfile.TemporaryDirectory() as tmp:
        gcloud("storage", "cp", f"gs://{settings['bucket']}/live/meta.json", os.path.join(tmp, "meta.json"))
        with open(os.path.join(tmp, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        for name in DB_FILES:
            gcloud("storage", "cp", f"gs://{settings['bucket']}/live/{name}", os.path.join(tmp, name))
            if sha256(os.path.join(tmp, name)) != meta["sha256"].get(name):
                raise SystemExit(f"❌ {name} 雜湊對不上；雲端已停止，請重跑 take 或檢查儲存桶")
        for name in DB_FILES:
            for suffix in ("-journal", "-wal", "-shm"):
                stale = os.path.join(DB_DIR, name + suffix)
                if os.path.exists(stale):
                    os.remove(stale)
            shutil.copyfile(os.path.join(tmp, name), os.path.join(DB_DIR, name))

    print(f"✅ 最新 DB 已放進 Database/ (本機原本的存在 {os.path.relpath(keep, ROOT)})")
    print("   現在可以 python Main.py；用完一定要 python deploy/handoff.py release 交回雲端")


def cmd_release(settings, args):
    holder = holder_name()
    if "--yes" not in args:
        answer = input("本機的機器人已經關掉了嗎？(y/N) ").strip().lower()
        if answer != "y":
            raise SystemExit("已取消；先關掉 python Main.py 再來")
    print(f"💻 ➔ ☁️ 上傳 {holder} 的 DB…")
    with tempfile.TemporaryDirectory() as tmp:
        meta = {"holder": holder, "time": datetime.datetime.now(datetime.timezone.utc).isoformat(), "sha256": {}}
        for name in DB_FILES:
            src = os.path.join(DB_DIR, name)
            if not os.path.exists(src):
                raise SystemExit(f"❌ 找不到 {src}")
            snapshot_db(src, os.path.join(tmp, name))
            meta["sha256"][name] = sha256(os.path.join(tmp, name))
        with open(os.path.join(tmp, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        # 先傳 DB 再傳 meta：VM 會比對雜湊，傳到一半失敗不會被接走
        for name in (*DB_FILES, "meta.json"):
            gcloud("storage", "cp", os.path.join(tmp, name), f"gs://{settings['bucket']}/live/{name}")

    force = " --force" if "--force" in args else ""
    vm(settings, f"{VM_CTL} takeback {holder}{force}")

    # 把 take 之前的本機 DB 放回去 (第一次上雲沒有 take 過，就不動)
    if os.path.exists(LAST_TAKE):
        with open(LAST_TAKE, encoding="utf-8") as f:
            keep = json.load(f).get("pre_take", "")
        if keep and os.path.isdir(keep):
            # 交出去的那份也留一份在本機，方便事後查
            sent = os.path.join(HANDOFF_DIR, f"released-{stamp()}")
            os.makedirs(sent, exist_ok=True)
            for name in DB_FILES:
                shutil.copy2(os.path.join(DB_DIR, name), os.path.join(sent, name))
                if os.path.exists(os.path.join(keep, name)):
                    shutil.copyfile(os.path.join(keep, name), os.path.join(DB_DIR, name))
            print(f"↩️ Database/ 已放回 take 之前的本機 DB (交出去的那份在 {os.path.relpath(sent, ROOT)})")
        os.remove(LAST_TAKE)
    print("✅ 雲端已接手")


def cmd_backup(settings, _args):
    listing = gcloud("storage", "ls", f"gs://{settings['bucket']}/backups/", capture=True).stdout.split()
    folders = sorted(path for path in listing if path.endswith("/"))
    if not folders:
        raise SystemExit("雲端還沒有備份")
    latest = folders[-1].rstrip("/").rsplit("/", 1)[-1]
    target = os.path.join(DB_DIR, "backups", "cloud", latest)
    os.makedirs(target, exist_ok=True)
    for name in DB_FILES:
        gcloud("storage", "cp", f"{folders[-1]}{name}", os.path.join(target, name))
    print(f"✅ 已下載 {latest} ➔ {os.path.relpath(target, ROOT)}")


def cmd_deploy(_settings, _args):
    subprocess.run(["git", "-C", ROOT, "fetch", "origin"], check=True)
    log = subprocess.run(["git", "-C", ROOT, "log", "--oneline", "origin/online..origin/main"],
                         check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()
    if not log:
        print("online 已經是最新的 main，不用部署")
        return
    print(f"要上線的 commit：\n{log}")
    # 只允許快轉：online 永遠等於某一版 main，不會分岔
    subprocess.run(["git", "-C", ROOT, "push", "origin", "origin/main:refs/heads/online"], check=True)
    print("✅ 已推到 online，雲端 1 分鐘內會自動更新 (python deploy/handoff.py status 可以看)")


def cmd_push_env(settings, _args):
    env = os.path.join(ROOT, ".env")
    if not os.path.exists(env):
        raise SystemExit("❌ 找不到 .env")
    gcloud("compute", "scp", env, f"{settings['vm']}:/tmp/touhou.env",
           "--zone", settings["zone"], "--project", settings["project"])
    vm(settings, "sudo install -o touhou -g touhou -m 600 /tmp/touhou.env /opt/touhou-bot/app/.env && rm /tmp/touhou.env"
                 " && (systemctl is-active --quiet touhou-bot && sudo systemctl restart touhou-bot || true)")
    print("✅ .env 已上傳 (雲端機器人在跑的話已重啟)")


def cmd_ssh(settings, _args):
    gcloud("compute", "ssh", settings["vm"], "--zone", settings["zone"], "--project", settings["project"])


COMMANDS = {
    "status": cmd_status, "take": cmd_take, "release": cmd_release, "backup": cmd_backup,
    "deploy": cmd_deploy, "push-env": cmd_push_env, "ssh": cmd_ssh,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    settings = {} if argv[0] == "deploy" else load_settings()
    try:
        COMMANDS[argv[0]](settings, argv[1:])
    except subprocess.CalledProcessError as e:
        print(f"❌ 指令失敗 (結束碼 {e.returncode})：{' '.join(map(str, e.cmd[:4]))}…")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

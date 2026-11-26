"""☁️ 本機 ⇄ 雲端自動交接 (使用者 2026-11-26 定；說明見 docs/dev/deploy.md 第 4 節)

本機 `python Main.py`：
  1. 開機前先跟雲端拿資料 (= `deploy/handoff.py take`：雲端停機器人、最新 DB 下載到 Database/)，成功才連 Discord
     - 資料本來就在這台 (上次直接按視窗 ✕、沒交回) ➔ 沿用本機這份，不重新下載 (不然會被雲端舊的那份蓋掉)
     - 拿不到 (沒網路、資料在別台、雲端停不下來) ➔ 不啟動：同一個 Token 不能兩邊同時在線
     - `.env` 沒有 GCP_PROJECT / GCP_BUCKET 或找不到 gcloud ➔ 不啟動；雲端壞了要硬跑：`.env` 加 SKIP_HANDOFF=1
  2. 關機後交回 (= `handoff.py release`：上傳 DB、雲端開機、本機放回測試資料)
     /shutdown、主控台 shutdown / exit、Ctrl+C、程式出錯結束都會；直接按視窗 ✕ 來不及，下次開機沿用、關機時再交回
雲端 (systemd 設 TOUHOU_CLOUD=1，或有 /var/lib/touhou-bot)：什麼都不做；/shutdown 在雲端 = 重新啟動。
"""
import importlib.util
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLOUD_STATE_DIR = "/var/lib/touhou-bot"
TRUTHY = {"1", "true", "yes", "on"}
MODE_COMMAND = "cat /var/lib/touhou-bot/mode 2>/dev/null || echo local:setup"
SKIP_HINT = "   真的要在沒有雲端的情況下跑 (例如雲端壞了)：`.env` 加一行 SKIP_HANDOFF=1 (雲端還在跑的話會兩邊同時上線)"

_handoff = None
_session = ""   # before_start 決定：cloud / skip / handoff (這次有跟雲端交接，關機要交回)


def handoff():
    """載入 deploy/handoff.py (它是指令列腳本、不是套件，用檔案路徑載入)"""
    global _handoff
    if _handoff is None:
        spec = importlib.util.spec_from_file_location("handoff", os.path.join(ROOT, "deploy", "handoff.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _handoff = module
    return _handoff


def is_cloud() -> bool:
    return os.getenv("TOUHOU_CLOUD", "").strip().lower() in TRUTHY or os.path.isdir(CLOUD_STATE_DIR)


def skip_requested() -> bool:
    return os.getenv("SKIP_HANDOFF", "").strip().lower() in TRUTHY


def read_last_take() -> dict | None:
    try:
        with open(handoff().LAST_TAKE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def holding() -> bool:
    """這台現在拿著玩家的真實資料 (take 完整做完、還沒交回)"""
    last = read_last_take()
    return bool(last and last.get("done"))


def parse_mode(text: str) -> tuple[str, str]:
    """跟 deploy/vm_ctl.py 的 parse_mode 同規則：'cloud' / 'local:<電腦>' / 其他"""
    text = (text or "").strip()
    if text == "cloud":
        return "cloud", ""
    if text.startswith("local:"):
        return "local", text[len("local:"):]
    return "unknown", text


def decide(mode_text: str, holder: str, last_take: dict | None) -> tuple[str, str]:
    """開機要做什麼：('take' | 'reuse' | 'refuse', 給人看的說明)"""
    kind, who = parse_mode(mode_text)
    if kind == "cloud":
        return "take", "雲端機器人執行中 ➔ 停下來，把最新的資料拿到這台"
    if kind == "local" and who == holder:
        if last_take and last_take.get("done"):
            return "reuse", "上次關機沒交回，最新的資料還在這台 ➔ 直接沿用，不重新下載"
        return "take", "上次交接沒做完 ➔ 重新下載雲端交出來的那份"
    if kind == "local" and who != "setup":
        return "refuse", f"資料在 {who} 手上：先到那台關掉機器人 (會自動交回雲端)，再來這台開"
    return "refuse", f"雲端的模式是「{mode_text.strip() or '(空白)'}」，不知道最新的資料在哪：先用 python deploy/handoff.py status 看"


def vm_mode(settings: dict) -> str:
    out = handoff().gcloud("compute", "ssh", settings["vm"], "--zone", settings["zone"], "--project", settings["project"],
                           "--command", MODE_COMMAND, capture=True).stdout or ""
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def before_start() -> bool:
    """Main.py 連 Discord 之前呼叫；回傳 False = 不要啟動"""
    global _session
    if is_cloud():
        _session = "cloud"
        return True
    if skip_requested():
        _session = "skip"
        print("⚠️ SKIP_HANDOFF：不跟雲端交接，直接用本機 Database/ 的資料。雲端還在跑的話會兩邊同時上線！")
        return True
    h = handoff()
    try:
        settings = h.load_settings()
        h.gcloud_path()
    except SystemExit as e:
        print(e)
        print("   雲端上線後，本機開機器人會先跟雲端交接；這台還沒設定好 (見 docs/dev/deploy.md 第 3 節)。")
        print(SKIP_HINT)
        return False

    print("☁️ ➔ 💻 跟雲端交接中 (大約 1 分鐘)…")
    try:
        action, why = decide(vm_mode(settings), h.holder_name(), read_last_take())
        print(f"   {why}")
        if action == "refuse":
            print("❌ 本機機器人不啟動 (同一個 Token 不能兩邊同時在線)")
            return False
        if action == "take":
            h.cmd_take(settings, ["--force", "--auto"])   # decide() 已經確認過不會蓋掉本機比較新的那份
    except (subprocess.CalledProcessError, SystemExit, OSError) as e:
        print(f"❌ 交接失敗：{e}")
        print("   本機機器人不啟動 (同一個 Token 不能兩邊同時在線)。再開一次 python Main.py 會接著做；")
        print("   雲端狀態：python deploy/handoff.py status")
        return False
    if not holding():
        print("❌ 交接沒有做完 (資料沒有拿到這台)，本機機器人不啟動；再開一次 python Main.py 會接著做")
        return False
    _session = "handoff"
    print("✅ 資料已經在這台，雲端機器人已停止。關機 (/shutdown、主控台 shutdown、Ctrl+C) 時會自動交回雲端")
    return True


def after_stop():
    """Main.py 結束時呼叫 (不管正常關機還是出錯)：這次有交接、資料在這台 ➔ 交回雲端"""
    if _session != "handoff" or not holding():
        return
    print("\n⏳ 💻 ➔ ☁️ 把資料交回雲端 (大約 1 分鐘，請不要關掉視窗)…")
    h = handoff()
    retry = ("   資料還在這台：手動跑 python deploy/handoff.py release；"
             "或下次 python Main.py 開機會沿用這份，關機時再交回")
    try:
        h.cmd_release(h.load_settings(), ["--yes"])
    except KeyboardInterrupt:
        print(f"\n⚠️ 交回被中斷。\n{retry}")
    except (subprocess.CalledProcessError, SystemExit, OSError) as e:
        print(f"❌ 交回失敗：{e}\n{retry}")


def shutdown_notice() -> str:
    """/shutdown 跟主控台 shutdown 顯示的說明"""
    if is_cloud():
        return "♻️ 雲端機器人重新啟動中，大約 15 秒後回來 (要讓出雲端：在本機開機器人就會自動交接)"
    if _session == "handoff" and holding():
        return "⚙️ 本機機器人關機中，資料交回雲端後雲端會接手 (大約 1 分鐘)"
    return "⚙️ 機器人正在安全關閉中... 下次見！"

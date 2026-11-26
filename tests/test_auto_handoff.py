"""☁️ 本機 ⇄ 雲端自動交接 (Utils/auto_handoff.py + deploy/handoff.py 的 take / release 保險)
不連雲端：gcloud、ssh、take、release 全部換成假的，只檢查「什麼情況做什麼」"""
import os, sys, json, tempfile, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "deploy")); os.chdir(ROOT)
os.environ.pop("TOUHOU_CLOUD", None); os.environ.pop("SKIP_HANDOFF", None)
from Utils import auto_handoff as ah
import vm_ctl

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

h = ah.handoff()
tmp = tempfile.mkdtemp()
h.LAST_TAKE = os.path.join(tmp, "last_take.json")
h.HANDOFF_DIR = tmp
HOLDER = h.holder_name()

def set_last(data):
    if data is None:
        if os.path.exists(h.LAST_TAKE): os.remove(h.LAST_TAKE)
    else:
        json.dump(data, open(h.LAST_TAKE, "w", encoding="utf-8"))

# 🔤 模式解析跟 VM 上的 vm_ctl 一樣
for text in ("cloud", "local:LAPTOP", "local:setup", "", "  cloud\n", "weird"):
    check(f"parse_mode {text!r}", ah.parse_mode(text) == vm_ctl.parse_mode(text))

# 🧭 開機要做什麼
check("cloud ➔ take", ah.decide("cloud", HOLDER, None)[0] == "take")
check("cloud + 舊的 done 紀錄 ➔ 還是 take (雲端那份最新)", ah.decide("cloud", HOLDER, {"done": True})[0] == "take")
check("本來就在這台 ➔ reuse", ah.decide(f"local:{HOLDER}", HOLDER, {"done": True})[0] == "reuse")
check("這台 take 沒做完 ➔ take", ah.decide(f"local:{HOLDER}", HOLDER, {"done": False})[0] == "take")
check("這台、沒有紀錄 ➔ take", ah.decide(f"local:{HOLDER}", HOLDER, None)[0] == "take")
act, why = ah.decide("local:DESKTOP", HOLDER, None)
check("在別台 ➔ refuse", act == "refuse" and "DESKTOP" in why)
check("setup ➔ refuse", ah.decide("local:setup", HOLDER, None)[0] == "refuse")
check("空白 ➔ refuse", ah.decide("", HOLDER, None)[0] == "refuse")

# ☁️ 雲端判斷
check("本機不是雲端", not ah.is_cloud())
os.environ["TOUHOU_CLOUD"] = "1"
check("TOUHOU_CLOUD=1 ➔ 雲端", ah.is_cloud())
check("雲端 before_start 直接放行", ah.before_start() and ah._session == "cloud")
check("雲端的 /shutdown = 重新啟動", "重新啟動" in ah.shutdown_notice())
os.environ.pop("TOUHOU_CLOUD")

# 假的 handoff：記下呼叫了什麼
calls = []
real = {k: getattr(h, k) for k in ("load_settings", "gcloud_path", "cmd_take", "cmd_release", "gcloud")}
SETTINGS = {"project": "p", "bucket": "b", "zone": "z", "vm": "v"}
mode = {"text": "cloud"}
def fake_take(settings, args):
    calls.append(("take", args)); set_last({"holder": HOLDER, "pre_take": tmp, "done": True})
def fake_release(settings, args):
    calls.append(("release", args)); set_last(None)
h.load_settings = lambda: SETTINGS
h.gcloud_path = lambda: "gcloud"
h.cmd_take = fake_take
h.cmd_release = fake_release
ah.vm_mode = lambda settings: mode["text"]

def reset(last=None, text="cloud"):
    calls.clear(); set_last(last); mode["text"] = text; ah._session = ""

# 正常：雲端在跑 ➔ take ➔ 關機 release
reset()
check("雲端在跑 ➔ 啟動", ah.before_start())
check("有 take、帶 --force --auto", calls == [("take", ["--force", "--auto"])])
check("交接中的 /shutdown 說明", "交回雲端" in ah.shutdown_notice())
ah.after_stop()
check("關機 ➔ release --yes", calls[-1] == ("release", ["--yes"]))
check("release 完不再拿著", not ah.holding())

# 上次沒交回 ➔ 沿用，不重新下載
reset({"holder": HOLDER, "pre_take": tmp, "done": True}, f"local:{HOLDER}")
check("沿用 ➔ 啟動", ah.before_start())
check("沿用時沒有 take", not [c for c in calls if c[0] == "take"])
ah.after_stop()
check("沿用的關機也 release", calls[-1][0] == "release")

# 資料在別台 ➔ 不啟動
reset(None, "local:DESKTOP")
check("在別台 ➔ 不啟動", not ah.before_start() and calls == [])
ah.after_stop()
check("沒啟動就不 release", calls == [])

# take 失敗 ➔ 不啟動
reset()
def boom(settings, args):
    calls.append(("take", args)); raise subprocess.CalledProcessError(1, ["gcloud", "compute", "ssh"])
h.cmd_take = boom
check("take 失敗 ➔ 不啟動", not ah.before_start())
ah.after_stop()
check("take 失敗不 release", [c for c in calls if c[0] == "release"] == [])

# take 回來了但資料沒放好 (done 不是 True) ➔ 不啟動
reset()
h.cmd_take = lambda settings, args: (calls.append(("take", args)), set_last({"done": False}))
check("done 沒寫 ➔ 不啟動", not ah.before_start())
h.cmd_take = fake_take

# 連 ssh 都失敗 ➔ 不啟動
reset()
def ssh_fail(settings): raise subprocess.CalledProcessError(255, ["gcloud"])
ah.vm_mode = ssh_fail
check("ssh 失敗 ➔ 不啟動", not ah.before_start() and calls == [])
ah.vm_mode = lambda settings: mode["text"]

# release 失敗不會讓 Main.py 噴錯
reset()
ah.before_start()
def release_fail(settings, args): raise subprocess.CalledProcessError(1, ["gcloud"])
h.cmd_release = release_fail
try:
    ah.after_stop(); check("release 失敗吞掉", True)
except Exception:
    check("release 失敗吞掉", False)
check("release 失敗 ➔ 資料還在這台", ah.holding())
h.cmd_release = fake_release

# 沒設定雲端 / 沒有 gcloud ➔ 不啟動
reset()
def no_env(): raise SystemExit("❌ .env 缺少 GCP_PROJECT")
h.load_settings = no_env
check("沒設定 ➔ 不啟動", not ah.before_start() and calls == [])
h.load_settings = lambda: SETTINGS
def no_gcloud(): raise SystemExit("❌ 找不到 gcloud")
h.gcloud_path = no_gcloud
check("沒有 gcloud ➔ 不啟動", not ah.before_start() and calls == [])
h.gcloud_path = lambda: "gcloud"

# SKIP_HANDOFF ➔ 不交接、關機也不 release
reset({"holder": HOLDER, "pre_take": tmp, "done": True}, "cloud")
os.environ["SKIP_HANDOFF"] = "1"
check("SKIP ➔ 啟動", ah.before_start() and ah._session == "skip" and calls == [])
ah.after_stop()
check("SKIP 關機不 release", calls == [])
check("SKIP 的 /shutdown 說明", "安全關閉" in ah.shutdown_notice())
os.environ.pop("SKIP_HANDOFF")

# 🛡️ handoff.py 自己的保險 (手動跑 take / release 也擋得住)
for k, v in real.items(): setattr(h, k, v)
def no_cloud(*a, **k): raise AssertionError("不應該連雲端")
h.gcloud = no_cloud
set_last({"holder": HOLDER, "pre_take": tmp, "done": True})
try:
    h.cmd_take(SETTINGS, []); check("拿著資料時 take 被擋", False)
except SystemExit as e:
    check("拿著資料時 take 被擋", "上次沒交回" in str(e))
set_last({"holder": HOLDER, "pre_take": tmp, "done": False})
try:
    h.cmd_release(SETTINGS, ["--yes"]); check("take 沒做完時 release 被擋", False)
except SystemExit as e:
    check("take 沒做完時 release 被擋", "沒做完" in str(e))
set_last(None)

# 📄 接線
# Main.py 沒有別的測試會 import (1.00.015 推送前實測時抓到 Main.py 有語法錯誤，測試卻全過)
import py_compile
for path in ("Main.py", "deploy/handoff.py", "deploy/vm_ctl.py", "Utils/auto_handoff.py"):
    try:
        py_compile.compile(path, doraise=True, cfile=os.path.join(tmp, "compiled.pyc")); check(f"{path} 能編譯", True)
    except py_compile.PyCompileError as e:
        check(f"{path} 能編譯 ({e.msg.strip()[:80]})", False)
main_src = open("Main.py", encoding="utf-8").read()
i_before, i_run, i_after = main_src.find("auto_handoff.before_start()"), main_src.find("asyncio.run(main())"), main_src.find("auto_handoff.after_stop()")
check("Main.py：先交接再連 Discord", -1 < i_before < i_run)
check("Main.py：after_stop 在 finally", i_after > i_run and "finally:" in main_src[i_run:i_after])
check("/shutdown 用 shutdown_notice", "auto_handoff.shutdown_notice()" in open("Cogs/load-system/Admin-sys.py", encoding="utf-8").read())
check("主控台 shutdown 用 shutdown_notice", "auto_handoff.shutdown_notice()" in open("Utils/console.py", encoding="utf-8").read())
unit = open("deploy/systemd/touhou-bot.service", encoding="utf-8").read()
check("雲端標記 TOUHOU_CLOUD=1", "Environment=TOUHOU_CLOUD=1" in unit)
check("雲端 /shutdown 會自動開回來", "Restart=always" in unit)
check("SKIP_HANDOFF 不會上傳到雲端", "SKIP_HANDOFF" in h.DEV_ONLY_ENV)

print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

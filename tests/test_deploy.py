"""☁️ 雲端部署：vm_ctl.py 的純邏輯 (要不要重啟、模式、交接檢查、設定檔、SQLite 快照) 與 systemd / 套件設定檔"""
import os, sys, tempfile, sqlite3, configparser
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, os.path.join(ROOT, "deploy")); os.chdir(ROOT)
import vm_ctl
import handoff

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

# 🔄 要不要重啟：圖片本體、文件、測試、工具、.md 不用；程式、角色檔、images/*.json、部署檔要
check("png only", not vm_ctl.needs_restart(["images/Thumbnails/reimu_N.png", "images/Original/Art/x.png"]))
check("docs only", not vm_ctl.needs_restart(["docs/deploy.md", "CHANGELOG.md", "TODO.md", "tests/test_x.py", "tools/card_art/card.py"]))
check("empty", not vm_ctl.needs_restart(["", "  "]))
check("cog", vm_ctl.needs_restart(["images/Thumbnails/a.png", "Cogs/load-gacha/gacha.py"]))
check("thumbnails json", vm_ctl.needs_restart(["images/Thumbnails.json"]))
check("character", vm_ctl.needs_restart(["Characters/TH06/remilia.json"]))
check("version", vm_ctl.needs_restart(["Utils/version.py"]))
check("db in git", vm_ctl.needs_restart(["Database/Users.db"]))   # 不會覆蓋雲端 DB (rsync 排除)，但保守起見照樣重啟
check("lock", vm_ctl.needs_restart(["deploy/requirements.lock.txt"]))

# 🏷️ 電腦名稱與模式
check("holder clean", vm_ctl.safe_holder("DESKTOP-AB12; rm -rf /") == "DESKTOP-AB12rm-rf")
try:
    vm_ctl.safe_holder("！？")
    check("holder empty raises", False)
except ValueError:
    check("holder empty raises", True)
check("handoff holder same rule", handoff.holder_name() == vm_ctl.safe_holder(handoff.holder_name()))
check("mode cloud", vm_ctl.parse_mode("cloud\n") == ("cloud", ""))
check("mode local", vm_ctl.parse_mode("local:LAPTOP") == ("local", "LAPTOP"))
check("mode junk", vm_ctl.parse_mode("???")[0] == "unknown")

# 🔁 交回雲端：只有拿走 DB 的那台 (或第一次安裝的 setup) 可以交回，其他要 --force
check("takeback by holder", vm_ctl.can_takeback("local:LAPTOP", "LAPTOP", False)[0])
check("takeback first time", vm_ctl.can_takeback("local:setup", "DESKTOP", False)[0])
check("takeback other pc refused", not vm_ctl.can_takeback("local:LAPTOP", "DESKTOP", False)[0])
check("takeback other pc force", vm_ctl.can_takeback("local:LAPTOP", "DESKTOP", True)[0])
check("takeback while cloud refused", not vm_ctl.can_takeback("cloud", "LAPTOP", False)[0])

# ⚙️ 設定檔
cfg = vm_ctl.parse_config('# 註解\nBUCKET="touhou-db"\nBRANCH = online\n\nBAD LINE\n')
check("config", cfg == {"BUCKET": "touhou-db", "BRANCH": "online"})

# 💾 SQLite 快照：內容一致、雜湊穩定、覆蓋舊檔
tmp = tempfile.mkdtemp()
src, dst = os.path.join(tmp, "a.db"), os.path.join(tmp, "b.db")
con = sqlite3.connect(src); con.execute("CREATE TABLE t (x)"); con.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(100)]); con.commit()
open(dst, "wb").write(b"old junk")
vm_ctl.snapshot_db(src, dst)   # 來源連線還開著 (像機器人在跑) 也能快照
con.close()
c2 = sqlite3.connect(dst); n = c2.execute("SELECT COUNT(*) FROM t").fetchone()[0]; c2.close()
check("snapshot rows", n == 100)
handoff.snapshot_db(src, os.path.join(tmp, "c.db"))
check("snapshot same content", vm_ctl.sha256(dst) == handoff.sha256(os.path.join(tmp, "c.db")))

# 📄 設定檔本身
units = os.path.join(ROOT, "deploy", "systemd")
for name in ("touhou-bot.service", "touhou-update.service", "touhou-update.timer", "touhou-backup.service", "touhou-backup.timer"):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    try:
        parser.read(os.path.join(units, name), encoding="utf-8")
        check(f"{name} parses", parser.sections() != [])
    except configparser.Error as e:
        check(f"{name} parses ({e})", False)
bot = open(os.path.join(units, "touhou-bot.service"), encoding="utf-8").read()
check("utf-8 env", "PYTHONIOENCODING=utf-8" in bot and "PYTHONUNBUFFERED=1" in bot)
check("mode guard", "check-mode" in bot)
for path in ("deploy/install.sh", "deploy/vm_ctl.py", "deploy/handoff.py", *[f"deploy/systemd/{n}" for n in os.listdir(units)]):
    check(f"{path} LF", b"\r\n" not in open(os.path.join(ROOT, path), "rb").read())
lock = open(os.path.join(ROOT, "deploy", "requirements.lock.txt"), encoding="utf-8").read()
check("discord.py pinned", "discord.py==2.7.1" in lock)
req = open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read().lower()
for pkg in ("discord.py", "aiosqlite", "python-dotenv", "pillow"):
    check(f"lock has {pkg}", pkg in lock.lower() and pkg in req)

print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

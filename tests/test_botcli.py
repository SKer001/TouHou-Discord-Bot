import os, sys, subprocess, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else:
        fail += 1; print("FAIL:", name)

tmp = tempfile.mkdtemp()
CLI = os.path.join(ROOT, "tools", "botcli.py")
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "MSYS_NO_PATHCONV": "1"}


def run(*steps, extra=()):
    proc = subprocess.run(
        [sys.executable, CLI, "--sandbox", tmp, *extra, *steps],
        cwd=ROOT, env=ENV, capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode, proc.stdout + proc.stderr


# 1. 空白沙盒：發卡 ➔ 換人 ➔ 合成選卡 ➔ 確認
code, out = run(
    "as me",
    "/admin-user add_money target:@小明 amount:100000",
    "/admin-gacha give target:@小明 pool:th06 character:cirno rarity:SR amount:2 completeness:0.5",
    "as @小明",
    "/card synthesis pool:th06 character:cirno",
    "select s1 1",
    "select s1 1",
    "click 確認合成",
    "/card gacha pool:th06 pull_type:10",
    "click 繼續十連",
    "/card history",
    extra=("--fresh",),
)
check(f"flow exit code {code}", code == 0)
check("loaded modules", "已載入 9 個模組" in out)
check("give", "已發放" in out and "×`2`" in out)
check("synthesis confirm", "卡牌合成確認" in out and "合成成功" in out)
check("gacha ten + redraw", out.count("十連模式") == 2)
check("history", "累計 `20` 抽" in out)
check("no errors", "錯誤 0 個" in out)

# 2. 沙盒資料會保留到下一次執行 (同名的 @小明 對到同一位玩家)
code, out = run("as @小明", "/card inventory", "sql SELECT COUNT(*) AS n FROM gacha_cards")
check("persisted cards", "21" in out and "博麗神社卡冊" in out)

# 3. 錯誤會被回報並讓結束碼不為 0
code, out = run("/card gacha pool:nope pull_type:1", "click 不存在的按鈕", "/nope")
check("bad choice", "只能是" in out)
check("bad step counted", code == 1 and "錯誤 3 個" in out)

# 4. 權限與 autocomplete
code, out = run("as @小明", "/admin-gacha view target:me", "as me", "? /admin-gacha give character pool:th06 current:cir")
check("permission", "無權限" in out)
check("autocomplete", "cirno = 🧊 琪露諾" in out)

# 5. 不會碰到真實資料庫 (沙盒在暫存資料夾)
check("sandbox files", os.path.exists(os.path.join(tmp, "Users.db")))

shutil.rmtree(tmp, ignore_errors=True)
print(f"passed {ok}, failed {fail}")

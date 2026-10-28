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

# 6. 實機工具的離線部分 (不連網路)：元件轉文字、計數、錯誤說明、鏡像時停用按鈕
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
from discord_rest import render_components, count_components, describe_error
payload = [{"type": 17, "accent_color": 0xf1c40f, "components": [
    {"type": 10, "content": "## 標題"},
    {"type": 9, "components": [{"type": 10, "content": "內文"}], "accessory": {"type": 11, "media": {"url": "https://x/fill.png"}}},
    {"type": 14},
    {"type": 1, "components": [{"type": 2, "style": 1, "label": "按我", "custom_id": "a"}]},
    {"type": 1, "components": [{"type": 3, "custom_id": "s", "placeholder": "選單", "options": [{"label": "甲", "value": "a", "default": True}]}]},
]}]
text = "\n".join(render_components(payload))
check("render", "色條 #f1c40f" in text and "內文" in text and "fill.png" in text and "[藍] 按我" in text and "a = 甲 ✓" in text)
check(f"count {count_components(payload)}", count_components(payload) == 10)
err = describe_error({"message": "Invalid Form Body", "code": 50035,
                      "errors": {"components": {"_errors": [{"code": "BASE_TYPE_MAX_LENGTH", "message": "Must be 40 or fewer in length."}]}}})
check("describe error", "components：Must be 40 or fewer" in err)
import importlib.util
spec = importlib.util.spec_from_file_location("botcli_mod", os.path.join(ROOT, "tools", "botcli.py"))
botcli_mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(botcli_mod)
frozen = [dict(payload[0], components=[dict(c) for c in payload[0]["components"]])]
frozen[0]["components"][3] = {"type": 1, "components": [{"type": 2, "label": "x", "custom_id": "a"}]}
botcli_mod.BotCLI._freeze(frozen)
check("freeze buttons", frozen[0]["components"][3]["components"][0]["disabled"] is True)

shutil.rmtree(tmp, ignore_errors=True)
print(f"passed {ok}, failed {fail}")

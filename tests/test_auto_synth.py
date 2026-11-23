"""⚡ 自動合成全部 + ⚗️ 繼續合成 (2026-11-23)：最低兩張的順序、合到 1.0000 退出、多階級各自合、統計、收藏冊 / 出征不動、重讀、按鈕"""
import asyncio, os, sys, shutil, sqlite3, tempfile, importlib, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")   # 絕不碰真實 Users.db
gacha = importlib.import_module("Cogs.load-gacha.gacha")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

UID = 515
def card(iid, rarity="SR", comp=0.5, key="reimu", at="2026-11-01 00:00:00"):
    p = gacha.GACHA_POOL[key]
    return {"instance_id": iid, "character_key": key, "name": p["name"], "emoji": p["emoji"],
            "rarity": rarity, "title": p["titles"][rarity], "completeness": comp, "obtained_at": at}

class Resp:
    def __init__(s, it): s.it = it; s.done = False
    def is_done(s): return s.done
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
    async def defer(s, **kw): s.done = True
    async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view")
class Interaction:
    def __init__(s, uid=UID):
        s.user = types.SimpleNamespace(id=uid, display_name="tester"); s.response = Resp(s); s.followup = Followup(s)
        s.view = None; s.data = {}; s.type = discord.InteractionType.component
    async def edit_original_response(s, **kw): s.view = kw.get("view")

def texts(view):
    return "\n".join(i.content for i in view.walk_children() if isinstance(i, discord.ui.TextDisplay))
def button(view, label):
    return next((b for b in view.walk_children() if isinstance(b, discord.ui.Button) and b.label == label), None)
def synth_count():
    con = sqlite3.connect(udm.DB_PATH)
    r = con.execute("SELECT total_synths FROM gacha_stats WHERE user_id = ?", (UID,)).fetchone(); con.close()
    return r[0] if r else 0
def total(view):
    return sum(1 for _ in view.walk_children())

def fake_roll(log, inc=0.1, doubled=False):
    """記下每次拿哪兩張 (完整度)；新完整度 = 較高那張 + inc (最多 1.0)"""
    def roll(a, b, rarity):
        log.append((rarity, round(a, 4), round(b, 4)))
        return {"new_completeness": round(min(1.0, max(a, b) + inc), 4), "increase": inc, "doubled": doubled}
    return roll


async def main():
    await udm.init_db()

    # ---------- 純邏輯 ----------
    # 最低兩張先合，新卡放回去繼續比；一樣低先拿比較早取得的
    log = []
    cards = [card("c_t_a", comp=0.30), card("c_t_b", comp=0.10, at="2026-11-02 00:00:00"),
             card("c_t_c", comp=0.10, at="2026-11-01 00:00:00"), card("c_t_d", comp=0.20)]
    res = gacha.run_auto_synthesis(cards, fake_roll(log))
    check(f"lowest two first {log}", log[0] == ("SR", 0.1, 0.1) and log[1] == ("SR", 0.2, 0.2) and log[2] == ("SR", 0.3, 0.3))
    check("count n-1", res["count"] == 3 and res["rarities"]["SR"]["count"] == 3 and res["rarities"]["SR"]["before"] == 4)
    check("consumed originals only", sorted(res["consumed"]) == ["c_t_a", "c_t_b", "c_t_c", "c_t_d"] and len(res["created"]) == 1)
    check("last card", res["rarities"]["SR"]["last"] == 0.4 and res["created"][0]["completeness"] == 0.4
          and res["created"][0]["instance_id"].startswith("c_t_") and res["created"][0]["rarity"] == "SR")
    # 一樣低：比較早取得的 (c) 先 ➔ 用掉順序裡 c 在 b 前面
    check("tie earlier first", res["consumed"][:2] == ["c_t_c", "c_t_b"])
    # 合到 1.0000 就退出，不再參加
    log = []
    cards = [card("c_t_e", comp=0.95), card("c_t_f", comp=0.96), card("c_t_g", comp=0.97)]
    res = gacha.run_auto_synthesis(cards, fake_roll(log, inc=0.2))
    info = res["rarities"]["SR"]
    check(f"perfect exits {info}", info["count"] == 1 and info["perfect"] == 1 and info["last"] == 0.97 and log == [("SR", 0.95, 0.96)])
    check("perfect created, rest kept", [c["completeness"] for c in res["created"]] == [1.0] and sorted(res["consumed"]) == ["c_t_e", "c_t_f"])
    # 本來就 1.0000 的卡不參加；只有一張的階級不合；多個階級各自合
    log = []
    cards = [card("c_t_h", "SR", 0.2), card("c_t_i", "SR", 1.0), card("c_t_j", "SSR", 0.1), card("c_t_k", "SSR", 0.3),
             card("c_t_l", "SSR", 0.2), card("c_t_m", "UR", 0.5)]
    res = gacha.run_auto_synthesis(cards, fake_roll(log, doubled=True))
    check(f"per rarity {res['rarities']}", set(res["rarities"]) == {"SSR"} and res["rarities"]["SSR"]["count"] == 2
          and res["rarities"]["SSR"]["doubled"] == 2 and all(r == "SSR" for r, _, _ in log))
    check("preview", gacha.auto_synthesis_preview(cards) == {"SSR": 3}
          and gacha.auto_synthesis_preview(cards + [card("c_t_n", "SR", 0.4)]) == {"SR": 2, "SSR": 3})

    # ---------- 資料層 + 畫面 ----------
    await udm.get_or_create_user(UID)
    base = [card(f"c_db_r{i}", "SR", round(0.01 * (i + 1), 4)) for i in range(5)] + \
           [card(f"c_db_s{i}", "SSR", round(0.3 + 0.1 * i, 4)) for i in range(3)] + \
           [card("c_db_lock", "SR", 0.001), card("c_db_exp", "SR", 0.002), card("c_db_one", "UR", 0.5),
            card("c_db_other", "SR", 0.1, key="marisa")]
    await udm.add_gacha_cards(UID, base, draw_count=0)
    await udm.set_cards_locked(UID, ["c_db_lock"], True)
    con = sqlite3.connect(udm.DB_PATH)
    con.execute("UPDATE gacha_cards SET expedition = 1 WHERE instance_id = 'c_db_exp'"); con.commit(); con.close()

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    cog = gacha.GachaCardSys(bot)
    cmds = {c.name: c for c in cog.walk_app_commands()}
    it = Interaction(); await cmds["synthesis"].callback(cog, it, "classic", "reimu")
    picker = it.view
    auto_btn = button(picker, "⚡ 自動合成全部")
    check("picker has auto button", auto_btn is not None and total(picker) <= 40)
    it = Interaction(); await auto_btn.callback(it)
    confirm = it.view
    t = texts(confirm)
    check(f"confirm screen {t}", "`SR`：`5` 張 ➔ 最多合成 `4` 次" in t and "`SSR`：`3` 張 ➔ 最多合成 `2` 次" in t
          and "UR" not in t.split("自動合成全部")[1].split("⚠️")[0] and "不能還原" in t and "收藏冊" in t
          and total(confirm) <= 40 and len(t) <= 4000)
    check("confirm others blocked", await confirm.interaction_check(Interaction(uid=1)) is False)

    # 確認前卡牌變了 (多抽到一張 SR) ➔ 整筆不做、提示重按
    await udm.add_gacha_cards(UID, [card("c_db_new", "SR", 0.5)], draw_count=0)
    stats0 = synth_count()
    it = Interaction(); await button(confirm, "⚡ 確認自動合成").callback(it)
    t = texts(confirm)
    check(f"changed refused {t[:60]}", "沒有執行" in t and "重新按" in t and len(await udm.get_user_cards(UID)) == 11)
    check("changed has continue", button(confirm, "⚗️ 繼續合成") is not None and not button(confirm, "⚗️ 繼續合成").disabled)
    check("changed no stats", synth_count() == stats0)

    # 重新開 ➔ 這次照當下的卡 (SR 6 張)，連按兩下只做一次
    it = Interaction(); await auto_btn.callback(it)
    confirm = it.view
    check("reopen recount", "`SR`：`6` 張" in texts(confirm))
    i1, i2 = Interaction(), Interaction()
    await asyncio.gather(button(confirm, "⚡ 確認自動合成").callback(i1), button(confirm, "⚡ 確認自動合成").callback(i2))
    t = texts(confirm)
    check(f"result screen {t}", "自動合成完成" in t and "`SR`：合成" in t and "`SSR`：合成" in t and "剩下" in t
          and len(t) <= 4000 and total(confirm) <= 40)
    check("auto result only inventory", button(confirm, "🎒 查看卡庫") is not None and button(confirm, "⚗️ 繼續合成") is None)
    after = await udm.get_user_cards(UID, include_locked=True)
    reimu = [c for c in after if c["character_key"] == "reimu" and not c["locked"] and not c["expedition"]]
    left = {r: [c for c in reimu if c["rarity"] == r and not gacha.is_perfect(c)] for r in ("SR", "SSR", "UR")}
    check(f"one left per rarity {[(r, len(v)) for r, v in left.items()]}", len(left["SR"]) <= 1 and len(left["SSR"]) <= 1 and len(left["UR"]) == 1)
    ids = {c["instance_id"] for c in after}
    check("locked / expedition / other untouched", {"c_db_lock", "c_db_exp", "c_db_one", "c_db_other"} <= ids)
    check("originals gone", not any(i.startswith("c_db_r") or i.startswith("c_db_s") or i == "c_db_new" for i in ids))
    synths = synth_count() - stats0
    check(f"stats count {synths}", 3 <= synths <= 5 + 2 and synths == sum(int(x) for x in __import__("re").findall(r"合成 `(\d+)` 次", t)))

    # ---------- ⚗️ 繼續合成 (手動合成的結果畫面) ----------
    await udm.add_gacha_cards(UID, [card(f"c_m_{i}", "SR", round(0.1 + 0.01 * i, 4), key="marisa") for i in range(3)], draw_count=0)
    view = await cog.make_synthesis_view(UID, "tester", "c_m_0", "c_m_1")
    it = Interaction(); await button(view, "⚗️ 確認合成").callback(it)
    cont = button(view, "⚗️ 繼續合成")
    check("manual result has continue", "合成成功" in texts(view) and button(view, "🎒 查看卡庫") is not None
          and cont is not None and not cont.disabled)
    it = Interaction(); await cont.callback(it)
    check("continue opens picker", isinstance(it.view, gacha.SynthesisPickerView) and it.view.character_key == "marisa"
          and "霧雨魔理沙" in texts(it.view) and button(it.view, "⚡ 自動合成全部") is not None)
    # 再合一次 ➔ marisa 只剩一張未滿 1.0000 ➔ 繼續合成反灰
    mar = [c for c in await udm.get_user_cards(UID) if c["character_key"] == "marisa" and not gacha.is_perfect(c)]
    mar.sort(key=lambda c: c["completeness"])
    while len(mar) >= 2:
        view = await cog.make_synthesis_view(UID, "tester", mar[0]["instance_id"], mar[1]["instance_id"])
        it = Interaction(); await button(view, "⚗️ 確認合成").callback(it)
        mar = sorted([c for c in await udm.get_user_cards(UID) if c["character_key"] == "marisa" and not gacha.is_perfect(c)],
                     key=lambda c: c["completeness"])
    cont = button(view, "⚗️ 繼續合成")
    check("continue disabled when nothing left", cont is not None and cont.disabled)
    it = Interaction(); await cont.callback(it)
    check("continue notice when nothing left", "沒有可以合成" in texts(it.view))
    # 沒得合 ➔ 按自動合成也只是提示
    msg = await cog.make_auto_synthesis_view(UID, "tester", "marisa")
    check("auto nothing", isinstance(msg, str) and "沒有可以合成" in msg)


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

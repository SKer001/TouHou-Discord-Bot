import asyncio, os, sys, shutil, tempfile, importlib, types, random
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT)
os.chdir(ROOT)
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
    else:
        fail += 1; print("FAIL:", name)

UID = 111
def card(iid, key="reimu", rarity="SR", comp=0.5):
    p = gacha.GACHA_POOL[key]
    return {"instance_id": iid, "character_key": key, "name": p["name"], "emoji": p["emoji"],
            "rarity": rarity, "title": p["titles"][rarity], "completeness": comp, "obtained_at": "x"}

class Resp:
    def __init__(s, it): s.it = it; s.sent = []; s.done = False
    def is_done(s): return s.done
    async def send_message(s, content=None, **kw):
        s.done = True; s.sent.append((texts(kw["view"]), kw)); s.it.view = kw.get("view")
    async def defer(s, **kw): pass
    async def edit_message(s, **kw): s.it.view = kw.get("view")

class Interaction:
    def __init__(s, uid=UID, ns=None):
        s.user = types.SimpleNamespace(id=uid, display_name="tester")
        s.namespace = types.SimpleNamespace(**(ns or {}))
        s.response = Resp(s); s.view = None
        s.type = discord.InteractionType.application_command
    async def edit_original_response(s, **kw): s.view = kw.get("view")

def texts(view):
    return "\n".join(i.content for i in view.walk_children() if isinstance(i, discord.ui.TextDisplay))

BASE_IDS = {"c_th01_a3", "c_th01_b1", "c_th01_p1", "c_th01_p2", "c_th01_p3", "c_th01_p4",
            "c_th01_u1", "c_th01_u2", "c_th01_u3", "c_th02_m1"}

async def main():
    await udm.init_db()
    # --- 公式 ---
    c = gacha.calc_synthesis
    r = c(0.5, 0.5, "SR"); check(f"0.x equal {r}", r["normal_increase"] == 0.2 and r["doubled_increase"] == 0.4 and abs(r["double_chance"] - 0.3) < 1e-9)
    r = c(0.001, 0.001, "N"); check(f"0.00x equal {r}", r["normal_completeness"] == 0.011 and r["doubled_completeness"] == 0.021 and abs(r["double_chance"] - 0.99) < 1e-9)
    r = c(0.05, 0.05, "R"); check(f"0.0x equal {r}", r["normal_increase"] == 0.05)
    r = c(0.0005, 0.0005, "R"); check(f"0.000x equal {r}", r["normal_increase"] == 0.005)
    r = c(0.1, 0.01, "SR"); check(f"mixed uses lower tier {r}", r["normal_increase"] <= 0.05)
    r = c(0.4, 0.8, "SR"); check(f"rel diff .5 {r}", r["normal_increase"] == 0.1 and abs(r["double_chance"] - 0.3 * 0.25) < 1e-9)
    r = c(0.95, 0.9, "SR"); check("cap 1.0", r["normal_completeness"] <= 1.0 and r["doubled_completeness"] == 1.0)
    r = c(0.001, 0.9999, "LR"); check(f"far apart still > {r}", 0.9999 < r["normal_completeness"] <= 1.0 and r["double_chance"] < 0.0001)
    caps = [(0.1, 0.2), (0.01, 0.05), (0.001, 0.01), (0.0, 0.005)]
    bad = None
    for _ in range(30000):
        a, b = round(10 ** random.uniform(-4, -0.0001), 4), round(10 ** random.uniform(-4, -0.0001), 4)
        a, b = max(a, 0.0001), max(b, 0.0001)
        if random.random() < 0.1: b = a
        rar = random.choice(list(gacha.SYNTHESIS_DOUBLE_CHANCE))
        r = c(a, b, rar)
        cap = next(cc for f, cc in caps if min(a, b) >= f)
        rr = gacha.roll_synthesis(a, b, rar)
        if not (r["normal_completeness"] > max(a, b) and r["doubled_completeness"] <= 1.0
                and r["normal_increase"] <= max(cap, 0.0001) + 1e-9 and r["doubled_increase"] <= 2 * cap + 1e-9
                and 0 <= r["double_chance"] <= gacha.SYNTHESIS_DOUBLE_CHANCE[rar]
                and rr["new_completeness"] in (r["normal_completeness"], r["doubled_completeness"])):
            bad = (a, b, rar, r); break
    check(f"random invariant {bad}", bad is None)
    n = sum(gacha.roll_synthesis(0.3, 0.3, "SR")["doubled"] for _ in range(20000))
    check(f"SR equal chance ~30% ({n/200:.1f}%)", 0.28 < n / 20000 < 0.32)

    # --- 資料 ---
    await udm.add_gacha_cards(UID, [
        card("c_th01_a1", comp=0.4), card("c_th01_a2", comp=0.4), card("c_th01_a3", comp=0.7),
        card("c_th01_b1", rarity="SSR", comp=0.6),
        card("c_th01_p1", comp=1.0), card("c_th01_p2", comp=1.0), card("c_th01_p3", comp=1.0), card("c_th01_p4", comp=1.0),
        card("c_th01_u1", rarity="UR", comp=1.0), card("c_th01_u2", rarity="UR", comp=1.0), card("c_th01_u3", rarity="UR", comp=1.0),
        card("c_th02_m1", key="marisa", comp=0.2),
    ])
    await udm.add_gacha_cards(222, [card("c_th01_z1", comp=0.3)])

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    cog = gacha.GachaCardSys(bot)
    await bot.add_cog(cog)
    cmds = {c.name: c for c in cog.walk_app_commands()}
    check("commands registered", "synthesis" in cmds and "fusion" in cmds)
    syn_cmd, fus_cmd = cmds["synthesis"], cmds["fusion"]

    # --- autocomplete：代數 ➔ 角色 (➔ 階級) ---
    ch = await syn_cmd._params["pool"].autocomplete(cog, Interaction(), "")
    check(f"ac synth pool {[c.value for c in ch]}", [c.value for c in ch] == ["classic"])
    ch = await syn_cmd._params["character"].autocomplete(cog, Interaction(ns={"pool": "classic"}), "")
    check(f"ac synth char {[c.name for c in ch]}", [c.value for c in ch] == ["reimu"] and "3 張可用" in ch[0].name)
    check("ac synth char other pool", await syn_cmd._params["character"].autocomplete(cog, Interaction(ns={"pool": "th06"}), "") == [])
    ch = await fus_cmd._params["pool"].autocomplete(cog, Interaction(), "")
    check("ac fusion pool", [c.value for c in ch] == ["classic"])
    ch = await fus_cmd._params["character"].autocomplete(cog, Interaction(ns={"pool": "classic"}), "")
    check("ac fusion char", [c.value for c in ch] == ["reimu"])
    ch = await fus_cmd._params["rarity"].autocomplete(cog, Interaction(ns={"character": "reimu"}), "")
    check(f"ac fusion rarity {[c.name for c in ch]}", [c.value for c in ch] == ["SR"] and "SR → SSR" in ch[0].name)

    # --- 合成：指令驗證 ---
    for pool, char in [("classic", "marisa"), ("th06", "reimu"), ("classic", "ghost")]:
        it = Interaction(); await syn_cmd.callback(cog, it, pool, char)
        check(f"synth reject {pool} {char}", "無法合成" in it.response.sent[0][0] and it.response.sent[0][1].get("ephemeral"))
    for a, b, msg in [("c_th01_a1", "c_th01_b1", "無法合成"), ("c_th01_a1", "c_th01_a1", "無法合成"),
                      ("c_th01_a1", "c_th01_z1", "找不到"), ("c_th01_p1", "c_th01_p2", "無法合成")]:
        r = await cog.make_synthesis_view(UID, "tester", a, b)
        check(f"make view reject {a} {b}", isinstance(r, str) and msg in r)

    # --- 合成選卡畫面：第一張 ➔ 第二張 ➔ 確認畫面 ---
    it = Interaction(); await syn_cmd.callback(cog, it, "classic", "reimu")
    pv = it.view
    check("picker step1", "步驟 1 / 2" in texts(pv) and "共 3 張可選" in texts(pv))
    i2 = Interaction(); i2.data = {"values": ["c_th01_a1"]}; await pv.select_callback(i2)
    check("picker step2", "步驟 2 / 2" in texts(pv) and "共 2 張可選" in texts(pv) and "c_th01_a1" in texts(pv))
    await pv.back_callback(Interaction())
    check("picker back", "步驟 1 / 2" in texts(pv))
    i2 = Interaction(); i2.data = {"values": ["c_th01_a1"]}; await pv.select_callback(i2)
    i3 = Interaction(); i3.data = {"values": ["c_th01_a2"]}; await pv.select_callback(i3)
    check("picker -> confirm view", isinstance(i3.view, gacha.CardActionConfirmView) and "加倍" in texts(i3.view))
    check("picker others blocked", await pv.interaction_check(Interaction(uid=999)) is False)

    # --- 合成：取消 ---
    await i3.view.cancel_callback(i3)
    check("cancel keeps cards", len(await udm.get_user_cards(UID)) == 12)

    # --- 合成：確認 + 連點 ---
    view = await cog.make_synthesis_view(UID, "tester", "c_th01_a1", "c_th01_a2")
    it = Interaction(); it.view = view
    await asyncio.gather(view.confirm_callback(it), view.confirm_callback(it))
    cards = await udm.get_user_cards(UID)
    ids = {c["instance_id"] for c in cards}
    new = [c for c in cards if c["instance_id"] not in BASE_IDS]
    check("synth consumed", "c_th01_a1" not in ids and "c_th01_a2" not in ids and len(cards) == 11)
    check(f"synth new card {new}", len(new) == 1 and new[0]["completeness"] in (0.6, 0.8) and new[0]["rarity"] == "SR"
          and new[0]["instance_id"].startswith("c_th01_") and len(new[0]["instance_id"]) == len("c_th01_") + 12)
    check("synth result screen", "合成成功" in texts(it.view))
    check("component count", sum(1 for _ in it.view.walk_children()) <= 40)

    # --- 兩個預覽同時確認 (同一組卡) ---
    v1 = await cog.make_synthesis_view(UID, "tester", "c_th01_a3", new[0]["instance_id"])
    v2 = await cog.make_synthesis_view(UID, "tester", "c_th01_a3", new[0]["instance_id"])
    it1, it2 = Interaction(), Interaction()
    await asyncio.gather(v1.confirm_callback(it1), v2.confirm_callback(it2))
    t = texts(it1.view) + texts(it2.view)
    check("concurrent: one ok one fail", t.count("合成成功") == 1 and t.count("合成失敗") == 1)
    check("card count after", len(await udm.get_user_cards(UID)) == 10)

    # --- 合成選卡分頁：45 張可選 ---
    await udm.add_gacha_cards(333, [card(f"c_th06_q{i:02d}", key="cirno", rarity="SR", comp=round(0.01 * (i + 1), 4)) for i in range(45)])
    it = Interaction(uid=333); await syn_cmd.callback(cog, it, "th06", "cirno")
    pv = it.view
    sel = [x for x in pv.walk_children() if isinstance(x, discord.ui.Select)][0]
    check("picker page size", len(sel.options) == 20 and "1 / 3" in "".join(b.label for b in pv.walk_children() if isinstance(b, discord.ui.Button)))
    for _ in range(4): await pv.next_callback(Interaction(uid=333))
    sel = [x for x in pv.walk_children() if isinstance(x, discord.ui.Select)][0]
    check("picker last page", pv.page == 3 and len(sel.options) == 5 and sum(1 for _ in pv.walk_children()) <= 40)

    # --- 融合 ---
    for pool, char, rarity in [("classic", "reimu", "UR"), ("classic", "marisa", "SR"), ("x", "garbage", "SR"),
                               ("classic", "reimu", "SSR"), ("th06", "reimu", "SR")]:
        it = Interaction(); await fus_cmd.callback(cog, it, pool, char, rarity)
        check(f"fusion reject {pool} {char} {rarity}", "無法融合" in it.response.sent[0][0])
    it = Interaction(); await fus_cmd.callback(cog, it, "classic", "reimu", "SR")
    await it.view.confirm_callback(it)
    cards = await udm.get_user_cards(UID)
    ssr = [c for c in cards if c["rarity"] == "SSR" and c["instance_id"] != "c_th01_b1"]
    check("fusion result", len(ssr) == 1 and ssr[0]["title"] == gacha.GACHA_POOL["reimu"]["titles"]["SSR"]
          and 0.001 <= ssr[0]["completeness"] <= 1.0)
    check("fusion consumed 3", [c["instance_id"] for c in cards if c["instance_id"].startswith("c_th01_p")] == ["c_th01_p4"])
    check("fusion stat", (await udm.get_gacha_stats(UID))["total_fusions"] == 1)
    check("fusion screen", "融合成功" in texts(it.view))
    check("ac fusion empty now", await fus_cmd._params["pool"].autocomplete(cog, Interaction(), "") == [])
    check("other user untouched", len(await udm.get_user_cards(222)) == 1)

    # --- transform_cards 失敗回滾 ---
    before = len(await udm.get_user_cards(UID))
    def boom(c): raise ValueError("x")
    for ids_ in (["c_th02_m1"], ["c_th02_m1", "c_th02_m1"], ["c_th01_z1"]):
        try:
            await udm.transform_cards(UID, ids_, boom); check(f"raise {ids_}", False)
        except ValueError:
            check(f"raise {ids_}", True)
    check("rollback kept", len(await udm.get_user_cards(UID)) == before)

    view = gacha.CardActionConfirmView(UID, "t", cog, discord.ui.Container(), None, "x")
    check("interaction_check blocks others", await view.interaction_check(Interaction(uid=999)) is False)

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

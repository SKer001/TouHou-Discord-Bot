import asyncio, os, sys, shutil, tempfile, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

ADMIN = 403895664666214400
class Resp:
    def __init__(s, it): s.it = it; s.done = False
    def is_done(s): return s.done
    async def defer(s, **kw): s.done = True
    async def send_message(s, content=None, **kw):
        assert content is None and "embed" not in kw; s.done = True; s.it.view = kw.get("view"); s.it.kw = kw
    async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view")
class Interaction:
    def __init__(s, uid=ADMIN, ns=None):
        s.user = types.SimpleNamespace(id=uid, display_name="admin"); s.response = Resp(s); s.followup = Followup(s)
        s.view = None; s.kw = {}; s.namespace = types.SimpleNamespace(**(ns or {})); s.data = {}
        s.type = discord.InteractionType.application_command
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))

T = types.SimpleNamespace(id=555, display_name="目標")

async def main():
    await udm.init_db()
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    # 跟 Main.py 一樣依 listdir 順序載入 (Admin-gacha 會比 gacha 先載入)
    for f in sorted(os.listdir("Cogs/load-gacha")):
        if f.endswith(".py"):
            await bot.load_extension(f"Cogs.load-gacha.{f[:-3]}")
    cog = bot.get_cog("GachaAdmin")
    cmds = {c.name: c for c in cog.walk_app_commands()}
    check("commands", set(cmds) == {"view", "give", "remove", "set_completeness", "clear"})
    gmod = sys.modules["Cogs.load-gacha.gacha"]
    amod = sys.modules["Cogs.load-gacha.Admin-gacha"]
    check("uses extension module", amod.gacha_mod() is gmod)

    # 無權限
    for name, args in [("view", (T,)), ("give", (T, "classic", "reimu", "SR")), ("remove", (T, "classic", "reimu")), ("set_completeness", (T, "th06", "cirno", 0.5)), ("clear", (T,))]:
        it = Interaction(uid=1); await cmds[name].callback(cog, it, *args)
        check(f"{name} denied", "無權限" in texts(it.view))

    # autocomplete
    ch = await cmds["give"]._params["pool"].autocomplete(cog, Interaction(), "")
    check("pool ac", [c.value for c in ch] == ["classic", "th06"])
    ch = await cmds["give"]._params["character"].autocomplete(cog, Interaction(ns={"pool": "th06"}), "cir")
    check("char ac", [c.value for c in ch] == ["cirno"] and all(len(c.name) <= 100 for c in ch))
    ch = await cmds["give"]._params["character"].autocomplete(cog, Interaction(ns={"pool": "th06"}), "")
    check("char ac by pool", len(ch) == 9)
    check("char ac other pool", await cmds["give"]._params["character"].autocomplete(cog, Interaction(ns={"pool": "classic"}), "cir") == [])
    check("char ac no pool", await cmds["give"]._params["character"].autocomplete(cog, Interaction(), "") == [])
    ch = await cmds["give"]._params["rarity"].autocomplete(cog, Interaction(ns={"character": "remilia"}), "")
    check("rarity ac", [c.value for c in ch] == ["SSR", "UR", "LR"])
    check("rarity ac empty", await cmds["give"]._params["rarity"].autocomplete(cog, Interaction(), "") == [])

    # give
    it = Interaction(); await cmds["give"].callback(cog, it, T, "th06", "cirno", "SR", 3, 0.5)
    cards = await udm.get_user_cards(555)
    check("give 3 fixed", len(cards) == 3 and all(c["completeness"] == 0.5 and c["rarity"] == "SR" and c["instance_id"].startswith("c_th06_") for c in cards))
    check("give notice", "已發放" in texts(it.view) and it.kw.get("ephemeral"))
    check("no draw count", (await udm.get_gacha_stats(555))["total_draws"] == 0)
    it = Interaction(); await cmds["give"].callback(cog, it, T, "classic", "reimu", "UR", 1, None)
    check("give random", len(await udm.get_user_cards(555)) == 4)
    it = Interaction(); await cmds["give"].callback(cog, it, T, "classic", "reimu", "N", 1, None)
    check("bad rarity", "沒有 `N` 階級" in texts(it.view))
    it = Interaction(); await cmds["give"].callback(cog, it, T, "classic", "ghost", "N", 1, None)
    check("bad char", "找不到角色" in texts(it.view))
    it = Interaction(); await cmds["give"].callback(cog, it, T, "classic", "cirno", "SR", 1, None)
    check("char not in pool", "找不到角色" in texts(it.view))

    # set_completeness：代數 + 角色 ➔ 選卡畫面
    cid = cards[0]["instance_id"]
    check("set uses owned ac", cmds["set_completeness"]._params["pool"].autocomplete is not None)
    it = Interaction(); await cmds["set_completeness"].callback(cog, it, T, "th06", "reimu", 0.5)
    check("set wrong combo", "沒有角色" in texts(it.view))
    it = Interaction(); await cmds["set_completeness"].callback(cog, it, T, "th06", "cirno", 0.98765)
    sv = it.view
    check("set picker", "修改完整度 ➔ `0.9877`" in texts(sv) and "共 3 張" in texts(sv) and it.kw.get("ephemeral"))
    i1 = Interaction(); i1.data = {"values": [cid]}; await sv.select_callback(i1)
    check("set confirm screen", "修改完整度確認" in texts(sv) and "`0.5000` ➔ `0.9877`" in texts(sv))
    await asyncio.gather(sv.confirm_callback(Interaction()), sv.confirm_callback(Interaction()))
    now = {c["instance_id"]: c for c in await udm.get_user_cards(555)}
    check("set completeness", now[cid]["completeness"] == 0.9877 and "`1` 張卡牌完整度改為 `0.9877`" in texts(sv))
    check("set list refreshed", sv.cards[0]["instance_id"] == cid and sv.cards[0]["completeness"] == 0.9877)
    # 多選
    others = [c["instance_id"] for c in sv.cards[1:]]
    i1 = Interaction(); i1.data = {"values": others}; await sv.select_callback(i1)
    await sv.cancel_callback(Interaction())
    now = {c["instance_id"]: c for c in await udm.get_user_cards(555)}
    check("set cancel", all(now[i]["completeness"] == 0.5 for i in others) and "已取消" in texts(sv))
    check("set others user", await udm.update_cards_completeness(555, ["c_nope"], 0.3) == 0)

    # remove：代數 / 角色 autocomplete
    await udm.add_gacha_cards(555, [dict(cards[1], instance_id=f"c_th06_bulk{i:02d}", completeness=round(0.01 * (i + 1), 4)) for i in range(45)])
    ch = await cmds["remove"]._params["pool"].autocomplete(cog, Interaction(ns={"target": T}), "")
    check(f"owned pool ac {[c.value for c in ch]}", sorted(c.value for c in ch) == ["classic", "th06"])
    check("owned pool needs target", await cmds["remove"]._params["pool"].autocomplete(cog, Interaction(), "") == [])
    ch = await cmds["remove"]._params["character"].autocomplete(cog, Interaction(ns={"target": T, "pool": "th06"}), "")
    check("owned char ac", [c.value for c in ch] == ["cirno"] and "48 張" in ch[0].name)
    it = Interaction(); await cmds["remove"].callback(cog, it, T, "th06", "reimu")
    check("remove wrong combo", "沒有角色" in texts(it.view))
    it = Interaction(); await cmds["remove"].callback(cog, it, T, "th06", "cirno")
    rv = it.view
    check("remove view pages", rv.total_pages == 3 and "共 48 張" in texts(rv) and it.kw.get("ephemeral"))
    sel = [i for i in rv.walk_children() if isinstance(i, discord.ui.Select)][0]
    check("select size", len(sel.options) == 20 and sel.max_values == 20 and sum(1 for _ in rv.walk_children()) <= 40)
    await rv.next_callback(Interaction()); await rv.next_callback(Interaction()); await rv.next_callback(Interaction())
    check("page clamp", rv.page == 3 and len([i for i in rv.walk_children() if isinstance(i, discord.ui.Select)][0].options) == 8)
    pick = [c["instance_id"] for c in rv.cards[-3:]]
    i1 = Interaction(); i1.data = {"values": pick}; await rv.select_callback(i1)
    check("confirm screen", "刪除確認" in texts(rv) and "`3` 張" in texts(rv))
    await rv.cancel_callback(Interaction())
    check("cancel", len(await udm.get_user_cards(555)) == 49 and "已取消" in texts(rv))
    i1 = Interaction(); i1.data = {"values": pick}; await rv.select_callback(i1)
    await asyncio.gather(rv.confirm_callback(Interaction()), rv.confirm_callback(Interaction()))
    check("deleted 3", len(rv.cards) == 45 and "已刪除" in texts(rv) and "`3` 張" in texts(rv))
    check("db after delete", len([c for c in await udm.get_user_cards(555) if c["character_key"] == "cirno"]) == 45)
    # 刪除時已有一張被別處刪掉
    pick = [c["instance_id"] for c in rv.cards[:2]]
    i1 = Interaction(); i1.data = {"values": pick}; await rv.select_callback(i1)
    await udm.delete_gacha_cards(555, pick[:1])
    await rv.confirm_callback(Interaction())
    check("partial delete notice", "`1` 張" in texts(rv) and "已經不在" in texts(rv) and len(rv.cards) == 43)
    check("remove view non-admin", await rv.interaction_check(Interaction(uid=1)) is False)
    # 別人的卡不受影響
    await udm.add_gacha_cards(777, [dict(cards[1], instance_id="c_th06_other")])
    check("other user untouched", len(await udm.get_user_cards(777)) == 1)
    # 清掉 bulk 卡，讓後面的 clear 測試數量不變
    await udm.delete_gacha_cards(555, [c["instance_id"] for c in await udm.get_user_cards(555) if "bulk" in c["instance_id"]])
    left = await udm.get_user_cards(555)
    check(f"left {len(left)}", len(left) == 2)
    await udm.add_gacha_cards(555, [dict(cards[1], instance_id="c_th06_topup")])

    # view
    it = Interaction(); await cmds["view"].callback(cog, it, T)
    v = it.view
    check("view target inventory", isinstance(v, gmod.InventoryView) and "目標 的博麗神社卡冊" in texts(v) and it.kw.get("ephemeral"))
    check("admin can operate view", await v.interaction_check(Interaction()) is True)
    it = Interaction(); await cmds["view"].callback(cog, it, types.SimpleNamespace(id=999, display_name="空"))
    check("view empty", "空空如也" in texts(it.view))

    # clear：取消 → 確定 (連點)
    it = Interaction(); await cmds["clear"].callback(cog, it, T)
    cv = it.view
    check("clear confirm", "清空卡冊確認" in texts(cv) and "`3` 張" in texts(cv))
    await cv.cancel_callback(Interaction())
    check("cancel keeps", len(await udm.get_user_cards(555)) == 3)
    it = Interaction(); await cmds["clear"].callback(cog, it, T)
    cv = it.view
    i1, i2 = Interaction(), Interaction()
    await asyncio.gather(cv.confirm_callback(i1), cv.confirm_callback(i2))
    check("cleared", len(await udm.get_user_cards(555)) == 0 and "共刪除 `3` 張" in texts(cv))
    check("other user kept", len(await udm.get_user_cards(777)) == 1)
    check("clear non-admin blocked", await cv.interaction_check(Interaction(uid=1)) is False)
    it = Interaction(); await cmds["clear"].callback(cog, it, T)
    check("clear empty", "本來就是空的" in texts(it.view))

    # reload 抽卡模組後拿到新模組
    await bot.reload_extension("Cogs.load-gacha.gacha")
    check("after reload", amod.gacha_mod() is sys.modules["Cogs.load-gacha.gacha"] and amod.gacha_mod() is not gmod)

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

import asyncio, os, sys, shutil, tempfile, importlib, types, random
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
gacha = importlib.import_module("Cogs.load-gacha.gacha")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

class Resp:
    def __init__(s, it): s.it = it; s.done = False
    def is_done(s): return s.done
    async def defer(s, **kw): s.done = True
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view")
class Interaction:
    def __init__(s, uid=1, component=False):
        s.user = types.SimpleNamespace(id=uid, display_name="t"); s.response = Resp(s); s.followup = Followup(s); s.view = None
        s.type = discord.InteractionType.component if component else discord.InteractionType.application_command
    async def edit_original_response(s, **kw): s.view = kw.get("view")
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))

real_choices = random.choices
def lowest_only(population, weights=None, k=1):
    return [population[0]] * k

async def main():
    await udm.init_db()
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    cog = gacha.GachaCardSys(bot); await bot.add_cog(cog)
    cmds = {c.name: c for c in cog.walk_app_commands()}
    pool = lambda v: types.SimpleNamespace(value=v)

    # 賽錢不足：什麼都不寫
    it = Interaction(); await cmds["gacha"].callback(cog, it, pool("classic"), pool(10))
    check("poor", "賽錢不足" in texts(it.view) and "`1,000` 賽錢" in texts(it.view))
    check("poor nothing written", await udm.get_user_cards(1) == [] and await udm.get_gacha_pity(1) == {})
    check("poor money kept", (await udm.get_or_create_user(1))["money"] == 1000)

    await udm.add_money(1, 10_000_000)
    random.choices = lowest_only   # 永遠只抽到最低階 ➔ 一定靠保底出 UR
    try:
        for i in range(99):
            it = Interaction(); await cmds["gacha"].callback(cog, it, pool("classic"), pool(1))
        p = (await udm.get_gacha_pity(1))["classic"]
        check(f"99 draws {p}", p["since_ur"] == 99 and p["total_draws"] == 99 and p["last_ur_at"] is None)
        check("pity text", "`99 / 100`" in texts(it.view))
        it = Interaction(); await cmds["gacha"].callback(cog, it, pool("classic"), pool(1))
        cards = await udm.get_user_cards(1)
        check("100th is UR", cards[-1]["rarity"] == "UR" and all(c["rarity"] != "UR" for c in cards[:-1]))
        check("pity shown", "觸發保底" in texts(it.view) and "`0 / 100`" in texts(it.view))
        p = (await udm.get_gacha_pity(1))["classic"]
        check(f"reset {p}", p["since_ur"] == 0 and p["total_draws"] == 100 and p["last_ur_at"])
        # 十連跨過保底：95 + 10 ➔ 第 5 張是 UR，之後計數 5
        for _ in range(95):
            await cmds["gacha"].callback(cog, Interaction(), pool("classic"), pool(1))
        before = len(await udm.get_user_cards(1))
        it = Interaction(); await cmds["gacha"].callback(cog, it, pool("classic"), pool(10))
        new = (await udm.get_user_cards(1))[before:]
        check(f"ten crosses pity {[c['rarity'] for c in new]}", [c["rarity"] == "UR" for c in new] == [False] * 4 + [True] + [False] * 5)
        p = (await udm.get_gacha_pity(1))["classic"]
        check(f"after ten {p}", p["since_ur"] == 5 and p["total_draws"] == 205)
        check("ten pity marker", "🎯 保底" in texts(it.view) and sum(1 for _ in it.view.walk_children()) <= 40)
        # 另一個卡池獨立計數
        await cmds["gacha"].callback(cog, Interaction(), pool("th06"), pool(10))
        pt = await udm.get_gacha_pity(1)
        check("pools independent", pt["th06"]["since_ur"] == 10 and pt["classic"]["since_ur"] == 5)
    finally:
        random.choices = real_choices

    # 自然抽到 UR / LR 也會重置
    cards, since, got = gacha.roll_pool_cards("th06", 1, 50, lambda: 0.5)
    random.choices = lambda pop, weights=None, k=1: [pop[-1]] * k
    try:
        cards, since, got = gacha.roll_pool_cards("th06", 1, 50, lambda: 0.5)
        top = cards[0]["rarity"] in ("UR", "LR")
        check(f"natural top {cards[0]['rarity']}", (since == 0 and got) if top else (since == 51 and not got))
        orig_choice = random.choice
        random.choice = lambda seq: "remilia" if "remilia" in seq else orig_choice(seq)
        try:
            cards, since, got = gacha.roll_pool_cards("th06", 1, 50, lambda: 0.5)
            check("natural LR resets", cards[0]["rarity"] == "LR" and since == 0 and got)
        finally:
            random.choice = orig_choice
    finally:
        random.choices = real_choices

    stats = await udm.get_gacha_stats(1)
    check("total draws", stats["total_draws"] == 215)
    money = (await udm.get_or_create_user(1))["money"]
    check(f"money {money}", money == 1000 + 10_000_000 - 215 * 2000)

    # 併發：錢只夠一次十連
    await udm.add_money(2, 20_000 - 1000)
    i1, i2 = Interaction(uid=2), Interaction(uid=2)
    await asyncio.gather(cmds["gacha"].callback(cog, i1, pool("classic"), pool(10)), cmds["gacha"].callback(cog, i2, pool("classic"), pool(10)))
    t = texts(i1.view) + texts(i2.view)
    check("concurrent one ok", t.count("賽錢不足") == 1 and len(await udm.get_user_cards(2)) == 10)
    check("concurrent money 0", (await udm.get_or_create_user(2))["money"] == 0)

    # 繼續十連按鈕
    before = len(await udm.get_user_cards(1))
    it2 = Interaction(component=True); await it.view.draw_ten_again(it2)
    check("redraw button", len(await udm.get_user_cards(1)) == before + 10)

    # /card history
    it = Interaction(); await cmds["history"].callback(cog, it)
    t = texts(it.view)
    check("history", "祈願紀錄" in t and "舊作卡池" in t and "紅魔鄉卡池" in t and "`225` 抽" in t)
    it = Interaction(uid=99); await cmds["history"].callback(cog, it)
    check("history empty", "`0 / 100`" in texts(it.view) and "尚未獲得" in texts(it.view))

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

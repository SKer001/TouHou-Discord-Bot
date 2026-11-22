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
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view"); s.it.kw = kw
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view"); s.it.kw = kw
class Interaction:
    def __init__(s, uid=1, component=False):
        s.user = types.SimpleNamespace(id=uid, display_name="t"); s.response = Resp(s); s.followup = Followup(s); s.view = None; s.kw = {}
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
        check("pity text", "`99 / 100`" in texts(it.view) and "下一抽 UR `必出`" in texts(it.view))
        it = Interaction(); await cmds["gacha"].callback(cog, it, pool("classic"), pool(1))
        cards = await udm.get_user_cards(1)
        check("100th is UR", cards[-1]["rarity"] == "UR" and all(c["rarity"] != "UR" for c in cards[:-1]))
        check("pity shown", "觸發保底" in texts(it.view) and "`0 / 100`" in texts(it.view) and "下一抽 UR `0.1%`" in texts(it.view))
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

    # 自然抽到 UR 會重置、LR 不會 (2026-11-22 起 LR 固定 0.1%，不影響保底)
    random.choices = lambda pop, weights=None, k=1: [pop[-1]] * k   # 抽到最高的階級 = LR
    try:
        cards, since, got = gacha.roll_pool_cards("th06", 1, 50, lambda: 0.5)
        check(f"natural LR keeps pity {cards[0]['rarity']} {since}", cards[0]["rarity"] == "LR" and since == 51 and not got
              and cards[0]["character_key"] in ("flandre", "remilia"))
        random.choices = lambda pop, weights=None, k=1: ["UR"] * k if "UR" in pop else [pop[0]] * k
        cards, since, got = gacha.roll_pool_cards("th06", 1, 50, lambda: 0.5)
        check("natural UR resets", cards[0]["rarity"] == "UR" and since == 0 and got and not cards[0]["pity"])
        check("UR within 90 is lucky", cards[0]["lucky"])
        cards, since, got = gacha.roll_pool_cards("th06", 1, 94, lambda: 0.5)
        check("UR at 95 not lucky", cards[0]["rarity"] == "UR" and not cards[0]["lucky"] and not cards[0]["pity"])
        cards, since, got = gacha.roll_pool_cards("th06", 1, 89, lambda: 0.5)
        check("UR at 90 lucky", cards[0]["lucky"])
        cards, since, got = gacha.roll_pool_cards("th06", 1, 90, lambda: 0.5)
        check("UR at 91 not lucky", not cards[0]["lucky"])
    finally:
        random.choices = real_choices

    # 🎲 機率表 (2026-11-22 定案)：起始 N 43.9 / R 27 / SR 18 / SSR 10.9 / UR 0.1 / LR 0.1
    close = lambda a, b, eps=1e-9: abs(a - b) < eps
    t1 = gacha.rarity_table("classic", 1)
    check(f"start table {t1}", all(close(t1[r], v / 100) for r, v in gacha.BASE_RATES.items()))
    check("tables sum to 1", all(close(sum(gacha.rarity_table(p, n).values()), 1) for p in ("classic", "th06") for n in range(1, 101)))
    ur = lambda n: gacha.rarity_table("th06", n)["UR"]
    check("UR curve", close(ur(1), 0.001) and close(ur(80), 0.001) and close(ur(85), 0.013) and close(ur(86), 0.0154)
          and close(ur(90), 0.025) and close(ur(95), 0.025 + 0.012 * 5 / 9) and close(ur(99), 0.037) and ur(100) == 1)
    t95 = gacha.rarity_table("th06", 95)
    check("curve takes from N/R/SR only", close(t95["SSR"], 0.109) and close(t95["LR"], 0.001)
          and close(t95["N"] / t95["R"], 43.9 / 27) and close(t95["R"] / t95["SR"], 27 / 18))
    check("pity draw only UR", gacha.rarity_table("th06", 100)["UR"] == 1 and gacha.rarity_table("th06", 100)["LR"] == 0)
    st = gacha.ur_cycle_stats("classic")
    check(f"cumulative {st['cum'][80]:.4f} {st['cum'][90]:.4f} {st['cum'][99]:.4f} {st['pity']:.4f} {st['avg']:.2f}",
          abs(st["cum"][80] - 0.0769) < 5e-4 and abs(st["cum"][90] - 0.2001) < 5e-4 and abs(st["cum"][99] - 0.4013) < 5e-4
          and abs(st["pity"] - 0.5987) < 5e-4 and abs(st["avg"] - 92.76) < 0.01 and close(st["cum"][100], 1))
    check("long-run sums to 1", close(sum(st["rates"].values()), 1) and abs(st["rates"]["UR"] - 1 / st["avg"]) < 1e-9)
    check("rate text", gacha.rate_text(0.001) == "0.1%" and gacha.rate_text(gacha.next_ur_rate("th06", 85)) == "1.54%"
          and gacha.rate_text(gacha.next_ur_rate("th06", 99)) == "必出" and gacha.rate_text(0.025) == "2.5%")
    # 角色：同階級平分；每張卡的長期平均機率加起來 = 1
    cr = gacha.card_rates("th06")
    check("card rates sum", close(sum(cr.values()), 1) and close(cr[("flandre", "LR")], st["rates"]["LR"] / 2)
          and close(cr[("cirno", "UR")], st["rates"]["UR"] / 5) and close(cr[("daiyousei", "N")], st["rates"]["N"] / 2))
    # 卡池少了某些階級：那一份照比例分給其他階級，UR 照曲線；沒有 UR ➔ 沒有 UR 也沒有保底
    ev = {"gacha_event_pool": {"key": "event_x", "characters": ["reimu", "cirno"]}}   # 都是 SR / SSR / UR
    te = gacha.rarity_table("event_x", 1, ev)
    check(f"missing rarities {te}", te["N"] == te["R"] == te["LR"] == 0 and close(te["UR"], 0.001)
          and close(te["SR"] / te["SSR"], 18 / 10.9) and close(sum(te.values()), 1))
    check("missing keeps curve", close(gacha.rarity_table("event_x", 90, ev)["UR"], 0.025))
    no_ur = {"gacha_event_pool": {"key": "event_y", "characters": ["daiyousei", "meiling"]}}   # N/R/SR + R/SR/SSR
    ty = gacha.rarity_table("event_y", 100, no_ur)
    check(f"no UR pool {ty}", ty["UR"] == 0 and close(sum(ty.values()), 1) and gacha.ur_cycle_stats("event_y", no_ur)["avg"] is None)
    # 實際擲 20000 抽 (真的亂數)：UR 約 1.08%、LR 約 0.1%
    random.seed(7)
    cards, _, _ = gacha.roll_pool_cards("th06", 20000, 0, lambda: 0.5)
    n_ur = sum(c["rarity"] == "UR" for c in cards); n_lr = sum(c["rarity"] == "LR" for c in cards)
    check(f"monte carlo UR {n_ur} LR {n_lr}", 170 < n_ur < 265 and 5 < n_lr < 40)
    check("monte carlo pity", all(c["rarity"] == "UR" for c in cards if c["pity"]) and any(c["pity"] for c in cards))

    stats = await udm.get_gacha_stats(1)
    check("total draws", stats["total_draws"] == 215)
    money = (await udm.get_or_create_user(1))["money"]
    check(f"money {money}", money == 1000 + 10_000_000 - 215 * gacha.DRAW_COST)

    # 併發：錢只夠一次十連
    await udm.add_money(2, 10 * gacha.DRAW_COST - 1000)
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
    check("history next rate", "下一抽 UR `0.1%`" in texts(it.view) and "LR 不影響保底" in texts(it.view))
    check("history rates select", [o.value for o in it.view.select.options] == list(gacha.GACHA_POOLS))

    # 📊 機率表：只有按的人看得到；顯示按的人自己的保底進度
    await udm.add_money(3, 10_000_000)
    random.choices = lowest_only
    try:
        for _ in range(8):
            await cmds["gacha"].callback(cog, Interaction(uid=3), pool("th06"), pool(10))
        it = Interaction(uid=3); await cmds["gacha"].callback(cog, it, pool("th06"), pool(5))
    finally:
        random.choices = real_choices
    check("result next rate", "`85 / 100` · 下一抽 UR `1.54%`" in texts(it.view))
    view = it.view
    other = Interaction(uid=4, component=True); other.data = {"custom_id": view.rates_btn.custom_id}
    check("others can open rates", await view.interaction_check(other) is True)
    other.data = {"custom_id": "x"}
    check("others blocked elsewhere", await view.interaction_check(other) is False)
    sheet = Interaction(uid=3, component=True); await view.view_rates(sheet)
    t = texts(sheet.view)
    check("rate sheet", "機率表：🔴 紅魔鄉卡池" in t and "43.9%" in t and "第 81～90 抽：慢慢升到 2.5%" in t
          and "吃到保底：**59.9%**" in t and "`85 / 100` · 下一抽 UR `1.54%`" in t and "芙蘭朵露" in t)
    check("rate sheet ephemeral", sheet.kw.get("ephemeral") is True)
    sheet = Interaction(uid=4, component=True); await view.view_rates(sheet)
    check("rate sheet own progress", "`0 / 100` · 下一抽 UR `0.1%`" in texts(sheet.view))
    check("rate sheet within 40", sum(1 for _ in sheet.view.walk_children()) <= 40)
    sheet = Interaction(uid=3); await gacha.send_rate_sheet(sheet, "event")
    check("rate sheet no event", "沒有開放" in texts(sheet.view))

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

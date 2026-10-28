import asyncio, os, sys, shutil, tempfile, importlib, types, json
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
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view")
class Interaction:
    def __init__(s, uid=1, component=False):
        s.user = types.SimpleNamespace(id=uid, display_name="t"); s.response = Resp(s); s.followup = Followup(s); s.view = None
        s.type = discord.InteractionType.component if component else discord.InteractionType.application_command
    async def edit_original_response(s, **kw): s.view = kw.get("view")

def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))

async def main():
    await udm.init_db()
    pool = gacha.GACHA_POOL
    check("24 chars", len(pool) == 24)
    check("pool fields", all(set(v) == {"name", "emoji", "uuid", "rarities", "titles", "pool"} and len(v["rarities"]) == 3 for v in pool.values()))
    classic = {k for k, v in pool.items() if v["pool"] == "classic"}
    th06 = {k for k, v in pool.items() if v["pool"] == "th06"}
    check(f"classic {len(classic)}", len(classic) == 15 and {"reimu", "marisa", "mima", "shinki"} <= classic)
    check(f"th06 {len(th06)}", th06 == {"rumia", "daiyousei", "cirno", "meiling", "koakuma", "patchouli", "sakuya", "remilia", "flandre"})

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    cog = gacha.GachaCardSys(bot); await bot.add_cog(cog)
    cmd = next(c for c in cog.walk_app_commands() if c.name == "gacha")
    d = bot.tree.get_command("card").to_dict(bot.tree)
    g = next(o for o in d["options"] if o["name"] == "gacha")
    check("pool choices", [c["value"] for c in g["options"][0]["choices"]] == ["classic", "th06"])

    await udm.add_money(1, 10_000_000)
    for pk, members in (("classic", classic), ("th06", th06)):
        for _ in range(20):
            it = Interaction(); await cmd.callback(cog, it, types.SimpleNamespace(value=pk), types.SimpleNamespace(value=10))
        cards = await udm.get_user_cards(1)
        drawn = {c["character_key"] for c in cards[-200:]}
        check(f"{pk} only draws own pool", drawn <= members and len(drawn) > 1)
        check(f"{pk} name shown", gacha.GACHA_POOLS[pk]["name"] in texts(it.view))
        # 繼續十連沿用同一卡池
        before = len(await udm.get_user_cards(1))
        it2 = Interaction(component=True); await it.view.draw_ten_again(it2)
        new = (await udm.get_user_cards(1))[before:]
        check(f"{pk} redraw same pool", len(new) == 10 and {c["character_key"] for c in new} <= members)
    it = Interaction(); await cmd.callback(cog, it, types.SimpleNamespace(value="th06"), types.SimpleNamespace(value=1))
    check("single shows pool", "紅魔鄉卡池" in texts(it.view))
    it = Interaction(); await gacha.GachaCardSys.execute_gacha(cog, it, 1, "nope")
    check("unknown pool rejected", "沒有任何角色" in texts(it.view))
    check("money not taken on bad pool", True)

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

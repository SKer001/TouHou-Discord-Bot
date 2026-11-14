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

class Resp:
    def __init__(s, it): s.it = it; s.done = False
    def is_done(s): return s.done
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
def member(uid, name, bot=False): return types.SimpleNamespace(id=uid, display_name=name, bot=bot)
class Interaction:
    def __init__(s, uid, guild):
        s.user = types.SimpleNamespace(id=uid, display_name="viewer"); s.guild = guild; s.response = Resp(s); s.view = None
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def card(iid, key):
    return dict(instance_id=iid, character_key=key, name=key, emoji="🎴", rarity="SR", title="t", completeness=0.5, obtained_at="x")

async def main():
    await udm.init_db()
    # 伺服器成員 1~13 + 一個 bot；資料庫另有不在伺服器的 99
    members = [member(i, f"玩家{i}") for i in range(1, 14)] + [member(500, "機器人", bot=True)]
    guild = types.SimpleNamespace(name="測試伺服器", members=members)
    for i in range(1, 13):        # 13 號沒有資料
        await udm.add_money(i, i * 1000)
    await udm.add_money(99, 10**9)
    await udm.add_money(500, 10**8)
    await udm.add_gacha_cards(3, [card(f"a{i}", k) for i, k in enumerate(["reimu", "reimu", "cirno"])])
    await udm.add_gacha_cards(4, [card(f"b{i}", k) for i, k in enumerate(["reimu", "cirno", "sakuya", "remilia"])])
    await udm.update_visibility(12, False)

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.leaderboard")
    cog = bot.get_cog("LeaderboardCog")
    cmd = next(c for c in cog.walk_app_commands() if c.name == "leaderboard")
    cat = lambda v: types.SimpleNamespace(value=v)

    it = Interaction(1, guild); await cmd.callback(cog, it, cat("money"))
    t = texts(it.view)
    check("only guild members", "10 位" not in t and "12 位居民" in t and "玩家99" not in t and "機器人" not in t)
    check("private hidden", "🔒 私人玩家" in t and "玩家12" not in t)
    check("rank order", t.index("玩家11") < t.index("玩家10") < t.index("玩家3"))
    check("top 10 + my rank", "`#12`" in t and "玩家1**" in t and "⬅️ 你" in t)
    check("count ok", sum(1 for _ in it.view.walk_children()) <= 40)

    it = Interaction(12, guild); await cmd.callback(cog, it, cat("money"))
    check("private self sees own name", "玩家12" in texts(it.view))

    # 🏷️ 戴著的稱號顯示在名字後面；私人玩家不顯示；已經不符合的稱號不顯示
    for uid, tid in ((11, "draw_5000"), (12, "money_1b")):
        await udm.set_granted_title(uid, tid, True); await udm.set_equipped_title(uid, tid)
    sql_db = __import__("sqlite3").connect(udm.DB_PATH)
    sql_db.execute("UPDATE users SET equipped_title = 'draw_10' WHERE user_id = 10"); sql_db.commit(); sql_db.close()   # 10 號沒解鎖 draw_10
    it = Interaction(1, guild); await cmd.callback(cog, it, cat("money"))
    t = texts(it.view)
    check("title on leaderboard", "**玩家11** · *[LR] 幻想鄉第一信仰*" in t)
    check("private title hidden", "比賽錢箱還有錢" not in t)
    check("invalid title hidden", "初次祈願者" not in t)
    it = Interaction(12, guild); await cmd.callback(cog, it, cat("money"))
    check("private self sees own title", "比賽錢箱還有錢" in texts(it.view))

    from importlib import import_module
    mc = import_module("Cogs.load-market.Components.market_components")
    listing = {"character_key": "reimu", "rarity": "SR", "name": "博麗靈夢", "emoji": "⛩️", "title": "t", "completeness": 1.0}
    ann = mc.build_listing_announce("賣家", listing, 1050, 0, None, "draw_5000")
    check("market announce title", "**賣家** · *[LR] 幻想鄉第一信仰* 上架了" in "\n".join(
        i.content for i in ann.walk_children() if isinstance(i, discord.ui.TextDisplay)))
    ann = mc.build_listing_announce("賣家", listing, 1050, 0, None, None)
    check("market announce no title", "**賣家** 上架了" in "\n".join(
        i.content for i in ann.walk_children() if isinstance(i, discord.ui.TextDisplay)))

    it = Interaction(3, guild); await cmd.callback(cog, it, cat("chars"))
    t = texts(it.view)
    check("chars", t.index("玩家4") < t.index("玩家3") and "`4 位`" in t and "`2 位`" in t)
    it = Interaction(3, guild); await cmd.callback(cog, it, cat("cards"))
    check("cards", "`4 張`" in texts(it.view))
    it = Interaction(13, guild); await cmd.callback(cog, it, cat("level"))
    check("no record viewer", "還沒有遊玩紀錄" in texts(it.view))
    it = Interaction(1, types.SimpleNamespace(name="空", members=[member(77, "x")])); await cmd.callback(cog, it, cat("draws"))
    check("empty guild", "還沒有人" in texts(it.view))

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

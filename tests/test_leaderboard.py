import asyncio, json, os, sys, shutil, tempfile, types
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
    def _mark(s):
        assert not s.done, "回應兩次"
        s.done = True
    async def send_message(s, content=None, **kw): assert content is None; s._mark(); s.it.view = kw.get("view"); s.it.ephemeral = kw.get("ephemeral", False)
    async def edit_message(s, content=None, **kw): assert content is None; s._mark(); s.it.view = kw.get("view")
def member(uid, name, bot=False): return types.SimpleNamespace(id=uid, display_name=name, bot=bot)
class Interaction:
    def __init__(s, uid, guild, values=None):
        s.user = types.SimpleNamespace(id=uid, display_name="viewer"); s.guild = guild; s.response = Resp(s); s.view = None
        s.data = {"values": values} if values else {}
        s.followup = types.SimpleNamespace(send=None)
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def comp(v, label=None, select=False):
    for i in v.walk_children():
        if select and isinstance(i, discord.ui.Select): return i
        if label and isinstance(i, discord.ui.Button) and (i.label or "").startswith(label): return i
def card(iid, key, rarity="SR"):
    return dict(instance_id=iid, character_key=key, name=key, emoji="🎴", rarity=rarity, title="t", completeness=0.5, obtained_at="x")

async def press(view, uid, label=None, select_value=None):
    c = comp(view, label, select=select_value is not None)
    it = Interaction(uid, view.guild, [select_value] if select_value else None)
    if await view.interaction_check(it):
        await c.callback(it)
    return it

async def main():
    await udm.init_db()
    # 伺服器成員 1~13 + 一個 bot；資料庫另有不在伺服器的 99
    members = [member(i, f"玩家{i}") for i in range(1, 14)] + [member(500, "機器人", bot=True)]
    guild = types.SimpleNamespace(name="測試伺服器", members=members)
    for i in range(1, 13):        # 13 號沒有資料
        await udm.add_money(i, i * 1000)
    await udm.add_money(99, 10**9)
    await udm.add_money(500, 10**8)
    await udm.add_gacha_cards(3, [card(f"a{i}", k, r) for i, (k, r) in enumerate([("reimu", "SR"), ("reimu", "SR"), ("cirno", "SR"), ("reimu", "R")])])
    await udm.add_gacha_cards(4, [card(f"b{i}", k) for i, k in enumerate(["reimu", "cirno", "sakuya", "remilia"])])
    await udm.update_visibility(12, False)

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.leaderboard")
    cog = bot.get_cog("LeaderboardCog")
    cmd = next(c for c in cog.walk_app_commands() if c.name == "leaderboard")
    cat = lambda v: types.SimpleNamespace(value=v)

    it = Interaction(1, guild); await cmd.callback(cog, it, cat("money"))
    v = it.view; t = texts(v)
    check("only guild members", "12 位居民" in t and "玩家99" not in t and "機器人" not in t)
    check("private hidden", "🔒 私人玩家" in t and "玩家12" not in t)
    check("rank order", t.index("玩家11") < t.index("玩家10") < t.index("玩家3"))
    check("list layout", "🥇 **🔒 私人玩家**\n賽錢：13K 兩" in t and "`#5` **玩家8**\n賽錢：9,000 兩" in t)
    check("page 1 shows 10", "`#10`" in t and "`#11`" not in t)
    check("footer my rank", "📍 你目前是第 12 名" in t)
    check("public message", it.ephemeral is False)
    check("count ok", sum(1 for _ in v.walk_children()) <= 40)
    it = await press(v, 1, label="下一頁")
    t = texts(it.view)
    check("page 2", "`#11`" in t and "**玩家1**" in t and "⬅️ 你" in t and "📍 你目前" not in t)
    await press(v, 1, label="◀️")
    it = await press(v, 1, label="📍 跳到我的名次")
    check("jump to me", "⬅️ 你" in texts(it.view) and v.page == 2)
    it = Interaction(2, guild)
    check("others cannot press", not await v.interaction_check(it) and "不是你的排行榜" in texts(it.view))

    it = Interaction(12, guild); await cmd.callback(cog, it, cat("money"))
    check("private self sees own name", "玩家12" in texts(it.view))
    it = Interaction(1, guild); await cmd.callback(cog, it)
    check("default category money", "排行榜：💰 賽錢" in texts(it.view))

    # 🏷️ 戴著的稱號顯示在名字後面；私人玩家不顯示；已經不符合的稱號不顯示
    for uid, tid in ((11, "draw_5000"), (12, "money_1b")):
        await udm.set_granted_title(uid, tid, True); await udm.set_equipped_title(uid, tid)
    sql_db = __import__("sqlite3").connect(udm.DB_PATH)
    sql_db.execute("UPDATE users SET equipped_title = 'draw_10' WHERE user_id = 10"); sql_db.commit(); sql_db.close()   # 10 號沒解鎖 draw_10
    it = Interaction(1, guild); await cmd.callback(cog, it, cat("money"))
    t = texts(it.view)
    check("title on leaderboard", "**玩家11** · [LR] 幻想鄉第一信仰" in t)
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
    check("chars", t.index("玩家4") < t.index("玩家3") and "收集角色：4 位" in t and "收集角色：2 位" in t)
    # 🃏 收集卡種：同一位角色每個階級各算一種 (3 號：靈夢 SR / R + 琪露諾 SR = 3 種)
    it = await press(it.view, 3, select_value="kinds")
    t = texts(it.view)
    check("kinds", "排行榜：🃏 收集卡種" in t and "收集卡種：4 種" in t and "收集卡種：3 種" in t)
    it = Interaction(3, guild); await cmd.callback(cog, it, cat("cards"))
    check("cards", "卡牌總數：4 張" in texts(it.view))
    it = Interaction(13, guild); await cmd.callback(cog, it, cat("level"))
    check("no record viewer", "還沒有遊玩紀錄" in texts(it.view) and comp(it.view, "📍").disabled)
    it = Interaction(1, types.SimpleNamespace(name="空", members=[member(77, "x")])); await cmd.callback(cog, it, cat("draws"))
    check("empty guild", "還沒有人" in texts(it.view))

    # 🌀 裏世界兩項 (只有成功撤離過的上榜；一頁 5 名；同分先達成的在前；倒下 💀、法具一行；私人玩家藏角色)
    async with udm.connect() as db:
        for uid, money, at, floor, depth, dat in ((1, 50000, "2026-11-20T01", 12, 20, "2026-11-20T01"),
                                                   (2, 80000, "2026-11-20T02", 20, 20, "2026-11-20T00"),
                                                   (3, 80000, "2026-11-20T01", 10, 10, "2026-11-20T01"),
                                                   (4, 1000, "2026-11-20T01", 5, 5, "2026-11-20T01"),
                                                   (5, 2000, "2026-11-20T01", 6, 6, "2026-11-20T01"),
                                                   (12, 99999, "2026-11-20T03", 30, 30, "2026-11-20T03")):
            party = json.dumps({"party": [{"cid": "cirno", "rarity": "SR", "name": "琪露諾", "alive": False},
                                          {"cid": "daiyousei", "rarity": "N", "name": "大妖精", "alive": True}],
                                "relics": [{"rid": "nine_tails", "tier": 0}], "money": money + 3000, "brought": 3000,
                                "floor": floor}, ensure_ascii=False)
            await db.execute("INSERT INTO ura_records (user_id, best_money, best_money_at, best_money_party, deepest, deepest_at, deepest_party) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?)", (uid, money, at, party, depth, dat, party))
        await db.execute("INSERT INTO ura_records (user_id, loadout) VALUES (6, '{}')")   # 沒撤離過，只有快速整裝
        await db.commit()
    it = Interaction(1, guild); await cmd.callback(cog, it, cat("ura_money"))
    v = it.view; t = texts(v)
    check("ura count", "成功撤離過的 6 位" in t and "玩家6" not in t)
    check("ura private first", t.index("🔒 私人玩家") < t.index("玩家3"))
    check("ura tie earlier first", t.index("玩家3") < t.index("玩家2"))
    check("ura block", "**玩家3**\n角色：[SR] 琪露諾 💀 / [N] 大妖精\n法具：🦊 九尾式神\n賽錢：80K 兩\n探索深度：第 10 關" in t)
    check("ura private hides party", t.split("🔒 私人玩家")[1].split("\n\n")[0].count("角色：") == 0)
    check("ura 5 per page", "`#5`" in t and "`#6`" not in t and v.page == 1)
    it4 = Interaction(4, guild); await cmd.callback(cog, it4, cat("ura_money"))
    v4 = it4.view
    check("ura footer", "📍 你目前是第 6 名" in texts(v4))
    it = await press(v4, 4, label="📍 跳到我的名次")
    check("ura jump", "`#6` **玩家4**　⬅️ 你" in texts(it.view) and v4.page == 2)
    it = await press(v, 1, select_value="ura_depth")
    t = texts(it.view)
    check("ura depth order", t.index("🔒 私人玩家") < t.index("玩家2") < t.index("玩家1") < t.index("玩家3"))
    check("ura depth block", "**玩家2**\n角色：[SR] 琪露諾 💀 / [N] 大妖精\n法具：🦊 九尾式神\n探索深度：第 20 關\n賽錢：80K 兩" in t)
    it = Interaction(7, guild); await cmd.callback(cog, it, cat("ura_depth"))
    check("ura no record", "還沒有成功撤離過" in texts(it.view) and comp(it.view, "📍").disabled)
    check("ura limits", sum(1 for _ in it.view.walk_children()) <= 40 and len(texts(it.view)) <= 4000)

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

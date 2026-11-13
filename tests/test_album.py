"""🔒 收藏冊：鎖住的卡從卡冊、合成、融合、分解、上架、autocomplete 消失；資料層也擋；稱號 / 圖鑑照算；/card album 取出"""
import asyncio, os, sys, tempfile, types, sqlite3, importlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm
from Database import Item_DB_Manager as idm
from Database import Economy_DB_Manager as econ
from Utils import card_cache

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")   # 絕不碰真實 Users.db
idm.DB_PATH = os.path.join(tmp, "Item.db")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

def sql(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); con.execute(q, args); con.commit(); con.close()

class Resp:
    def __init__(s, it): s.it = it; s.done = False
    def is_done(s): return s.done
    async def defer(s, **kw): s.done = True
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
    async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw):
        assert content is None; s.it.views.append(kw.get("view"))
        if s.it.view is None: s.it.view = kw.get("view")
class Interaction:
    def __init__(s, uid=1, data=None):
        s.user = types.SimpleNamespace(id=uid, display_name="t", mention="@t")
        s.response = Resp(s); s.followup = Followup(s); s.view = None; s.views = []; s.data = data or {}
        s.type = discord.InteractionType.application_command
    async def original_response(s): return None
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def buttons(v): return {i.label: i for i in v.walk_children() if isinstance(i, discord.ui.Button)}

U = 1
CARDS = [("a1", "reimu", "SR", 1.0), ("a2", "reimu", "SR", 1.0), ("a3", "reimu", "SR", 1.0),
         ("b1", "cirno", "SR", 0.5), ("b2", "cirno", "SR", 0.6)]


async def main():
    await udm.init_db()
    await udm.get_or_create_user(U)
    sql("UPDATE users SET daily_count = 30 WHERE user_id = ?", (U,))   # 開通上架
    for iid, ck, r, c in CARDS:
        sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, title, completeness) "
            "VALUES (?, ?, ?, ?, ?, 't', ?)", (iid, U, ck, ck, r, c))

    # 舊版 gacha_cards 沒有 locked ➔ init_db 自動補上
    con = sqlite3.connect(udm.DB_PATH)
    check("locked column default 0", con.execute("SELECT locked FROM gacha_cards WHERE instance_id = 'a1'").fetchone() == (0,)); con.close()

    # --- 資料層 ---
    check("lock", await udm.set_cards_locked(U, ["a1", "b1"], True) == 2)
    check("lock twice no-op", await udm.set_cards_locked(U, ["a1"], True) == 0)
    check("lock others' card no-op", await udm.set_cards_locked(99, ["a2"], True) == 0)
    ids = [c["instance_id"] for c in await udm.get_user_cards(U)]
    check("hidden from cards", ids == ["a2", "a3", "b2"])
    check("include_locked", [c["instance_id"] for c in await udm.get_user_cards(U, include_locked=True)] == ["a1", "a2", "a3", "b1", "b2"])
    check("album cards", [c["instance_id"] for c in await udm.get_album_cards(U)] == ["a1", "b1"])
    card_cache.invalidate(U)
    check("autocomplete cache hides", "a1" not in {c["instance_id"] for c in await card_cache.cached_user_cards(U)})

    # 繞過選單直接拿鎖住的卡 ➔ 合成 / 融合 / 分解 / 上架全部擋下
    try:
        await udm.transform_cards(U, ["a1", "a2", "a3"], lambda cs: {**cs[0], "instance_id": "new", "rarity": "SSR"})
        check("fusion blocked", False)
    except ValueError:
        check("fusion blocked", True)
    try:
        await econ.decompose_cards(U, ["b1"]); check("decompose blocked", False)
    except ValueError:
        check("decompose blocked", True)
    check("list blocked", (await econ.list_card(U, "a1", 100))["reason"] == "not_found")
    check("still there", len(await udm.get_album_cards(U)) == 2)

    # 稱號照算 (完美卡：a1 鎖住也算 reimu SR 完美)
    check("titles count locked", (await udm.get_title_stats(U))["perfect_kinds"] == 1)

    # --- 畫面 ---
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-gacha.gacha")
    g = importlib.import_module("Cogs.load-gacha.gacha")
    cog = bot.get_cog("GachaCardSys")
    cmds = {c.name: c for c in cog.walk_app_commands()}

    # 合成 / 融合找組都看不到鎖住的卡 (reimu SR 只剩 2 張完美 ➔ 不能融合)
    groups = g.find_fusion_groups(await udm.get_user_cards(U))
    check("fusion group hides locked", ("reimu", "SR") not in groups)

    # /card inventory ➔ 卡片詳情有「🔒 放進收藏冊」
    it = Interaction(uid=U); await cmds["inventory"].callback(cog, it)
    inv = it.view
    check("inventory hides locked", "a1" not in {c["instance_id"] for c in inv.all_cards})
    inv.selected_stack = g._stack_value(inv.get_stack_by_key("cirno", "SR")) if hasattr(inv, "get_stack_by_key") else \
        next(g._stack_value(s) for s in inv.all_stacks if s["character_key"] == "cirno")
    inv.selected_card = next(c for c in inv.all_cards if c["instance_id"] == "b2")
    inv.build()
    check("lock button", "🔒 放進收藏冊" in buttons(inv))
    i2 = Interaction(uid=U); await inv.lock_callback(i2)
    check("locked via button", [c["instance_id"] for c in await udm.get_album_cards(U)] == ["a1", "b1", "b2"])
    check("stack gone ➔ back to list", inv.selected_stack is None and inv.selected_card is None
          and all(c["character_key"] != "cirno" for c in inv.all_cards))
    check("lock notice", any("放進收藏冊" in texts(v) for v in i2.views))

    # 管理員檢視別人的卡冊：看得到鎖住的卡，但沒有放進收藏冊按鈕
    adm = g.InventoryView(900, g.sort_cards(await udm.get_user_cards(U, include_locked=True)), "t", cog, owner_id=U)
    adm.selected_card = next(c for c in adm.all_cards if c["instance_id"] == "a1"); adm.selected_stack = "x"; adm.build()
    check("admin sees locked", "🔒 收藏中" in texts(adm) and "🔒 放進收藏冊" not in buttons(adm))

    # /card album ➔ 選卡 ➔ 取出
    it = Interaction(uid=U); await cmds["album"].callback(cog, it)
    av = it.view
    check("album list", "收藏中 `3` 張" in texts(av) and "琪露諾" in texts(av))
    i3 = Interaction(uid=U, data={"values": ["a1"]}); await av.select_callback(i3)
    check("album detail", "🔒 收藏中" in texts(av) and "📤 取出 (回到卡冊)" in buttons(av))
    i4 = Interaction(uid=U); await av.unlock_callback(i4)
    check("unlocked", "已把" in texts(av) and "收藏中 `2` 張" in texts(av)
          and "a1" in {c["instance_id"] for c in await udm.get_user_cards(U)})
    i5 = Interaction(uid=2); check("others blocked", not await av.interaction_check(i5))

    # 空的收藏冊
    it = Interaction(uid=5); await cmds["album"].callback(cog, it)
    check("empty album", "收藏冊是空的" in texts(it.view))

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

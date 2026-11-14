"""🖼️ 角色名片：推角只算收藏冊、第一次有推角稱號就永久拿到名片、戴上 / 收回、資料庫遷移、/profile 名片圖與選單、/admin-user namecard、私訊"""
import asyncio, os, sys, tempfile, types, sqlite3, json
from datetime import datetime, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from discord import app_commands
from Database import User_DB_Manager as udm
from Database import Item_DB_Manager as idm
from Database import Notify_DB_Manager as ndm
from Database import title_data as td
from Utils import namecards as nc
from Utils import gacha_pools as gp

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")   # 絕不碰真實 Users.db
idm.DB_PATH = os.path.join(tmp, "Item.db")
nc.NAMECARDS_FILE = os.path.join(tmp, "Namecards.json")   # 不碰真實的 images/Namecards.json

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

def sql(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); con.execute(q, args); con.commit(); con.close()
def rows(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); r = con.execute(q, args).fetchall(); con.close(); return r

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
avatar = types.SimpleNamespace(with_size=lambda n: types.SimpleNamespace(url="https://x/a.png"))
def member(uid, name="t"): return types.SimpleNamespace(id=uid, display_name=name, display_avatar=avatar, mention=f"@{name}")
class Interaction:
    def __init__(s, uid=1, data=None):
        s.user = member(uid)
        s.response = Resp(s); s.followup = Followup(s); s.view = None; s.views = []; s.data = data or {}
        s.type = discord.InteractionType.application_command
    async def original_response(s): return None
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def selects(v): return [i for i in v.walk_children() if isinstance(i, discord.ui.Select)]
def galleries(v): return [i for i in v.walk_children() if isinstance(i, discord.ui.MediaGallery)]
def count(v): return sum(1 for _ in v.walk_children())
def namecard_select(v): return next(s for s in selects(v) if s.placeholder.startswith("🖼️"))

POOL = gp.load_gacha_pool()
CIRNO = POOL["cirno"]["rarities"]   # SR / SSR / UR

def add_cards(uid, cid, rarities, completeness=1.0, locked=1, prefix="c"):
    for r in rarities:
        sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, completeness, locked) "
            "VALUES (?, ?, ?, 'x', ?, ?, ?)", (f"{prefix}{uid}{cid}{r}", uid, cid, r, completeness, locked))


async def main():
    # --- 🔧 資料庫遷移：舊 users 沒有 equipped_namecard、也沒有 namecards 表 ---
    old = udm.SCHEMA_STATEMENTS[0].replace(",\n        equipped_namecard TEXT DEFAULT NULL", "")
    check("old schema has no column", "equipped_namecard" not in old)
    con = sqlite3.connect(udm.DB_PATH); con.execute(old); con.execute("INSERT INTO users (user_id) VALUES (77)"); con.commit(); con.close()
    await udm.init_db()
    cols = [r[1] for r in rows("PRAGMA table_info(users)")]
    check("migrated equipped_namecard", "equipped_namecard" in cols and rows("SELECT equipped_namecard FROM users WHERE user_id = 77") == [(None,)])
    check("namecards table", rows("SELECT name FROM sqlite_master WHERE name = 'namecards'") == [("namecards",)])
    check("old player state", await udm.get_namecard_state(77) == {"equipped": None, "owned": []})
    await udm.init_db()   # 重複 init 沒問題

    # --- 💕 推角只算收藏冊 ---
    A = 1
    await udm.get_or_create_user(A)
    add_cards(A, "cirno", CIRNO, locked=0, prefix="book")   # 全部在卡冊 ➔ 不算
    st = await udm.get_title_stats(A)
    check("card book not counted", st["oshi:th06:cirno"] == 0 and "oshi_cirno" not in (await udm.get_title_state(A))["unlocked"])
    check("no namecard yet", await udm.get_namecards(A) == [])
    add_cards(A, "cirno", CIRNO[:-1], locked=1, prefix="alb")   # 收藏冊少一個階級
    check("album partial", (await udm.get_title_stats(A))["oshi:th06:cirno"] == len(CIRNO) - 1)
    add_cards(A, "cirno", CIRNO[-1:], completeness=0.9, locked=1, prefix="alb")   # 最後一階不完美
    check("album imperfect", "oshi_cirno" not in (await udm.get_title_state(A))["unlocked"])
    sql("UPDATE gacha_cards SET completeness = 1.0 WHERE instance_id = ?", (f"alb{A}cirno{CIRNO[-1]}",))
    st = await udm.get_title_state(A)
    check("album complete ➔ title", "oshi_cirno" in st["unlocked"])
    check("namecard unlocked", await udm.get_namecards(A) == ["cirno"]
          and rows("SELECT source FROM namecards WHERE user_id = ? AND character_key = 'cirno'", (A,)) == [("oshi",)])
    check("sync idempotent", await udm.sync_oshi_namecards(A, st["unlocked"]) == [] and await udm.get_namecards(A) == ["cirno"])
    check("sync no oshi", await udm.sync_oshi_namecards(A, ["draw_10"]) == [])

    # 戴著推角稱號 ➔ 拿出收藏冊：稱號撤掉 (戴著的自動當沒戴)，名片保留
    check("equip oshi title", await udm.set_equipped_title(A, "oshi_cirno"))
    check("equip namecard", await udm.set_equipped_namecard(A, "cirno")
          and await udm.get_namecard_state(A) == {"equipped": "cirno", "owned": ["cirno"]})
    check("take out", await udm.set_cards_locked(A, [f"alb{A}cirno{CIRNO[0]}"], False) == 1)
    st = await udm.get_title_state(A)
    check("title lost after take out", "oshi_cirno" not in st["unlocked"] and st["equipped"] is None)
    check("namecard kept", await udm.get_namecard_state(A) == {"equipped": "cirno", "owned": ["cirno"]})
    sql("DELETE FROM gacha_cards WHERE user_id = ?", (A,))   # 全部賣掉也一樣
    await udm.get_title_state(A)
    check("namecard kept after sold", await udm.get_namecards(A) == ["cirno"])

    # 沒擁有不能戴、不存在不能戴、卸下
    check("cannot equip not owned", await udm.set_equipped_namecard(A, "reimu") is False
          and (await udm.get_namecard_state(A))["equipped"] == "cirno")
    check("cannot equip unknown", await udm.set_equipped_namecard(A, "nope") is False)
    check("unequip", await udm.set_equipped_namecard(A, None) and (await udm.get_namecard_state(A))["equipped"] is None)

    # 給 / 收回：收回正戴著的會卸下
    check("grant", await udm.grant_namecard(A, "reimu", "admin") and not await udm.grant_namecard(A, "reimu", "admin"))
    check("owned order", await udm.get_namecards(A) == ["cirno", "reimu"])
    await udm.set_equipped_namecard(A, "reimu")
    check("revoke", await udm.revoke_namecard(A, "reimu") and not await udm.revoke_namecard(A, "reimu"))
    st = await udm.get_namecard_state(A)
    check("revoke unequips", st == {"equipped": None, "owned": ["cirno"]}
          and rows("SELECT equipped_namecard FROM users WHERE user_id = ?", (A,)) == [(None,)])
    await udm.set_equipped_namecard(A, "cirno")
    await udm.revoke_namecard(A, "reimu")   # 收回別張不影響戴著的
    check("revoke other keeps equipped", (await udm.get_namecard_state(A))["equipped"] == "cirno")
    # 資料庫裡戴著的名片已經不在 (例如直接被刪) ➔ 當成沒戴
    sql("UPDATE users SET equipped_namecard = 'marisa' WHERE user_id = ?", (A,))
    check("invalid equipped hidden", (await udm.get_namecard_state(A))["equipped"] is None)
    await udm.set_equipped_namecard(A, "cirno")

    # --- 🖼️ 圖片網址 (images/Namecards.json) ---
    check("no json ➔ None", nc.namecard_url("cirno") is None)
    with open(nc.NAMECARDS_FILE, "w", encoding="utf-8") as f: f.write("壞掉")
    check("broken json ➔ None", nc.namecard_url("cirno") is None)
    with open(nc.NAMECARDS_FILE, "w", encoding="utf-8") as f: json.dump({}, f)
    check("empty json ➔ None", nc.namecard_url("cirno") is None and nc.namecard_url(None) is None)
    real = json.load(open(os.path.join(ROOT, "images", "Namecards.json"), encoding="utf-8"))
    check("real json is a dict", isinstance(real, dict))

    # --- /profile 畫面 ---
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.profile")
    cog = bot.get_cog("Profile")
    cmds = {c.name: c for c in cog.walk_app_commands()}

    it = Interaction(uid=A); await cmds["profile"].callback(cog, it, None, None)
    pv = it.view
    check("no art ➔ no gallery", galleries(pv) == [])
    sel = namecard_select(pv)
    check("namecard select options", [o.value for o in sel.options] == ["cirno", "__none__"] and not sel.disabled)
    check("option label + emoji", sel.options[0].label == "琪露諾的名片" and str(sel.options[0].emoji) == POOL["cirno"]["emoji"]
          and sel.options[0].default and "製作中" in (sel.options[0].description or ""))

    url = "https://raw.githubusercontent.com/x/images/Namecards/cirno.jpg?v=abc"
    with open(nc.NAMECARDS_FILE, "w", encoding="utf-8") as f: json.dump({"cirno": url}, f)
    it = Interaction(uid=A); await cmds["profile"].callback(cog, it, None, None)
    pv = it.view
    g = galleries(pv)
    container = next(i for i in pv.walk_children() if isinstance(i, discord.ui.Container))
    check("gallery shown", len(g) == 1 and g[0].items[0].media.url == url)
    check("gallery on top", container.children[0] is g[0])
    check("option has art", namecard_select(pv).options[0].description is None)

    # 別人看得到名片圖，但沒有選單；私人卡本人看也有圖
    it = Interaction(uid=2); await cmds["profile"].callback(cog, it, member(A), None)
    check("others see namecard", len(galleries(it.view)) == 1 and not selects(it.view))
    await udm.update_visibility(A, False)
    it = Interaction(uid=A); await cmds["profile"].callback(cog, it, None, None)
    check("private card namecard", len(galleries(it.view)) == 1)
    await udm.update_visibility(A, True)

    # 選單：卸下 ➔ 圖不見；再戴上；沒擁有被擋
    i2 = Interaction(uid=A, data={"values": ["__none__"]}); await pv.on_namecard(i2)
    check("unequip via select", galleries(pv) == [] and (await udm.get_namecard_state(A))["equipped"] is None
          and namecard_select(pv).options[-1].default)
    i3 = Interaction(uid=A, data={"values": ["cirno"]}); await pv.on_namecard(i3)
    check("equip via select", len(galleries(pv)) == 1 and (await udm.get_namecard_state(A))["equipped"] == "cirno")
    i4 = Interaction(uid=A, data={"values": ["reimu"]}); await pv.on_namecard(i4)
    check("not owned rejected", "還沒有這張名片" in texts(i4.view) and (await udm.get_namecard_state(A))["equipped"] == "cirno")
    i5 = Interaction(uid=2, data={"values": ["__none__"]})
    check("others cannot change", not await pv.interaction_check(i5))

    # 沒有名片 ➔ 選單反灰，placeholder 寫怎麼拿
    it = Interaction(uid=3); await cmds["profile"].callback(cog, it, None, None)
    sel = namecard_select(it.view)
    check("disabled when none", sel.disabled and "收藏冊" in sel.placeholder and "完美卡" in sel.placeholder)

    # 最多名片 + 稱號 + 名片圖 + 剛簽到 ➔ 元件 ≤ 40；選單 ≤ 25 (超過 24 張時戴著的那張一定列出)
    M = 5
    for i, cid in enumerate(POOL):
        sql("INSERT INTO namecards (user_id, character_key, obtained_at, source) VALUES (?, ?, ?, 'admin')", (M, cid, f"2026-01-01T00:{i:02d}"))
    for i in range(10):
        sql("INSERT INTO namecards (user_id, character_key, obtained_at, source) VALUES (?, ?, ?, 'admin')", (M, f"fake{i}", f"2026-02-01T00:{i:02d}"))
    sql("INSERT INTO gacha_stats (user_id, total_draws, total_fusions, total_synths) VALUES (?, 5000, 1000, 1000)", (M,))
    await udm.set_equipped_namecard(M, "fake9")
    await udm.set_equipped_title(M, "draw_5000")
    with open(nc.NAMECARDS_FILE, "w", encoding="utf-8") as f: json.dump({cid: url for cid in POOL} | {"fake9": url}, f)
    it = Interaction(uid=M); await cmds["daily"].callback(cog, it)   # 簽到 ➔ 有獎勵那張卡
    pv = it.view
    sel = namecard_select(pv)
    check("max options 25", len(sel.options) == 25 and sel.options[-1].value == "__none__")
    check("equipped listed", "fake9" in [o.value for o in sel.options] and next(o for o in sel.options if o.value == "fake9").default)
    check("unknown character label", next(o for o in sel.options if o.value == "fake9").label == "fake9的名片")
    check(f"component count {count(pv)} ≤ 40", count(pv) <= 40 and len(galleries(pv)) == 1 and len(selects(pv)) == 3)

    # --- 🛠️ /admin-user namecard ---
    from Utils import config
    config.ADMIN_IDS = config.ADMIN_IDS | {900}
    await bot.load_extension("Cogs.load-general.Admin-user")
    acog = bot.get_cog("UserAdmin")
    nc_cmd = next(c for c in acog.walk_app_commands() if c.name == "namecard")
    act = lambda v: app_commands.Choice(name=v, value=v)
    G = 70
    it = Interaction(uid=900); await nc_cmd.callback(acog, it, act("grant"), "reimu", member(G, "g"))
    check("admin grant", await udm.get_namecards(G) == ["reimu"] and "已給" in texts(it.view)
          and rows("SELECT source FROM namecards WHERE user_id = ?", (G,)) == [("admin",)])
    it = Interaction(uid=900); await nc_cmd.callback(acog, it, act("grant"), "reimu", member(G, "g"))
    check("admin grant twice", "本來就有" in texts(it.view))
    it = Interaction(uid=900); await nc_cmd.callback(acog, it, act("equip"), "marisa", member(G, "g"))
    check("admin equip gives", await udm.get_namecard_state(G) == {"equipped": "marisa", "owned": ["reimu", "marisa"]}
          and "換上了" in texts(it.view))
    it = Interaction(uid=900); await nc_cmd.callback(acog, it, act("revoke"), "marisa", member(G, "g"))
    check("admin revoke unequips", await udm.get_namecard_state(G) == {"equipped": None, "owned": ["reimu"]} and "已收回" in texts(it.view))
    it = Interaction(uid=900); await nc_cmd.callback(acog, it, act("list"), None, member(G, "g"))
    check("admin list", "擁有 `1` 張" in texts(it.view) and "靈夢" in texts(it.view))
    it = Interaction(uid=900); await nc_cmd.callback(acog, it, act("grant"), "亂打", member(G, "g"))
    check("admin unknown character", "找不到這位角色" in texts(it.view) and await udm.get_namecards(G) == ["reimu"])
    it = Interaction(uid=900); await nc_cmd.callback(acog, it, act("equip"), None, None)
    check("admin missing character", "找不到這位角色" in texts(it.view))
    it = Interaction(uid=G); await nc_cmd.callback(acog, it, act("grant"), "cirno", None)
    check("non-admin blocked", "無權限" in texts(it.view) and await udm.get_namecards(G) == ["reimu"])
    it = Interaction(uid=900); await nc_cmd.callback(acog, it, act("grant"), "cirno", None)
    check("target empty = self", await udm.get_namecards(900) == ["cirno"])
    # 還有推角稱號的話，收回之後又會自動補回來 (訊息要說明)
    add_cards(G, "cirno", CIRNO, locked=1, prefix="g")
    await udm.get_title_state(G)
    it = Interaction(uid=900); await nc_cmd.callback(acog, it, act("revoke"), "cirno", member(G, "g"))
    check("revoke while oshi", "自動補回來" in texts(it.view) and "cirno" in await udm.get_namecards(G))
    choices = await acog.namecard_autocomplete(Interaction(uid=900), "")
    check("autocomplete ≤ 25", 0 < len(choices) <= 25)
    check("autocomplete filter", [c.value for c in await acog.namecard_autocomplete(Interaction(uid=900), "琪露")] == ["cirno"]
          and [c.value for c in await acog.namecard_autocomplete(Interaction(uid=900), "REMI")] == ["remilia"])

    # --- 🔔 通知 loop：推角稱號私訊多一句名片，並順便補名片 ---
    from importlib import import_module
    comps = import_module("Cogs.load-general.Components.notify_components")
    n, _ = ndm.check_titles(A, ["oshi_cirno", "draw_10"], "")
    oshi = next(x for x in n if x["key"] == "oshi_cirno")
    other = next(x for x in n if x["key"] == "draw_10")
    check("notice data namecard", oshi["data"]["namecard"] == "琪露諾" and other["data"]["namecard"] is None)
    t = comps.notice_text(oshi)
    check("oshi dm text", "還獲得了 **琪露諾** 的角色名片" in t and "🖼️ 更換名片" in t and "收藏冊裡有琪露諾" in t)
    check("other dm text no namecard", "名片" not in comps.notice_text(other))

    await ndm.init_notify_db()
    now = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
    await ndm.collect_notices(now)   # 第一輪：只記錄起點
    N = 80
    await udm.get_or_create_user(N)
    await ndm.collect_notices(now)
    add_cards(N, "cirno", CIRNO, locked=1, prefix="n")
    add_cards(N, "remilia", POOL["remilia"]["rarities"], locked=0, prefix="n")   # 卡冊裡的不算
    found = [x for x in await ndm.collect_notices(now) if x["user_id"] == N and x["kind"] == "title_unlocked"]
    keys = {x["key"] for x in found}
    check("loop oshi title", "oshi_cirno" in keys and "oshi_remilia" not in keys)
    check("loop syncs namecard", rows("SELECT character_key, source FROM namecards WHERE user_id = ?", (N,)) == [("cirno", "oshi")])
    check("loop dm says namecard", any("琪露諾" in comps.notice_text(x) and "角色名片" in comps.notice_text(x) for x in found))
    # 第一次上線那輪 (只記錄、不私訊) 也要補名片
    Q = 81
    await udm.get_or_create_user(Q)
    add_cards(Q, "reimu", POOL["reimu"]["rarities"], locked=1, prefix="q")
    sql("DELETE FROM notify_watch WHERE user_id = 0 AND kind = 'titles_baseline'")
    found = [x for x in await ndm.collect_notices(now) if x["user_id"] == Q and x["kind"] == "title_unlocked"]
    check("first run silent but synced", found == [] and await udm.get_namecards(Q) == ["reimu"])
    # 管理員給的推角稱號 (granted_titles)：通知 loop 也補名片 (不私訊)，不用等他打開 /profile
    G = 82
    await udm.get_or_create_user(G)
    sql("UPDATE users SET granted_titles = 'oshi_remilia,draw_10' WHERE user_id = ?", (G,))
    found = [x for x in await ndm.collect_notices(now) if x["user_id"] == G and x["kind"] == "title_unlocked"]
    check("granted oshi synced by loop", found == [] and await udm.get_namecards(G) == ["remilia"])

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

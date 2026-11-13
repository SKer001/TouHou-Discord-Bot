"""🏷️ 稱號：解鎖條件、戴上 / 卸下、沒解鎖不能戴、/profile 顯示稱號與說明、色條顏色、更換選單"""
import asyncio, os, sys, tempfile, types, sqlite3
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from discord import app_commands
from Database import User_DB_Manager as udm
from Database import Item_DB_Manager as idm
from Database import title_data as td

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
avatar = types.SimpleNamespace(with_size=lambda n: types.SimpleNamespace(url="https://x/a.png"))
class Interaction:
    def __init__(s, uid=1, data=None):
        s.user = types.SimpleNamespace(id=uid, display_name="t", display_avatar=avatar, mention="@t")
        s.response = Resp(s); s.followup = Followup(s); s.view = None; s.views = []; s.data = data or {}
        s.type = discord.InteractionType.application_command
    async def original_response(s): return None
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def selects(v): return [i for i in v.walk_children() if isinstance(i, discord.ui.Select)]
def accent(v): return next(i for i in v.walk_children() if isinstance(i, discord.ui.Container)).accent_color.value

# --- 純資料 ---
check("every title complete", all({"name", "rarity", "desc", "stat", "min"} <= set(t) and t["rarity"] in td.RARITY_COLORS
                                  for t in td.TITLES.values()))
check("draw titles", [td.TITLES[f"draw_{n}"]["rarity"] for n in (10, 100, 500, 1000, 2000, 5000)] == ["N", "R", "SR", "SSR", "UR", "LR"])
check("fusion titles", [td.TITLES[f"fusion_{n}"]["rarity"] for n in (1, 10, 50, 100, 500, 1000)] == ["N", "R", "SR", "SSR", "UR", "LR"])
check("fusion unlock", td.unlocked_titles({"total_fusions": 500}) == ["fusion_500", "fusion_100", "fusion_50", "fusion_10", "fusion_1"])
check("synth titles", [(td.TITLES[f"synth_{n}"]["rarity"], td.TITLES[f"synth_{n}"]["name"]) for n in (1, 10, 50, 100, 500, 1000)]
      == [("N", "初次合成"), ("R", "修卡匠"), ("SR", "精益求精"), ("SSR", "完美主義者"), ("UR", "匠心獨具"), ("LR", "千錘百鍊")])
check("synth condition", td.condition_text("synth_1") == "累計合成 1 次")
check("condition text", td.condition_text("fusion_500") == "累計融合 500 次")
check("unlock none", td.unlocked_titles({"total_draws": 9}) == [])
check("unlock order high first", td.unlocked_titles({"total_draws": 600}) == ["draw_500", "draw_100", "draw_10"])
check("ur/lr titles", [(td.TITLES[k]["rarity"], td.TITLES[k]["name"]) for k in ("ur_1", "ur_5", "ur_10", "lr_1", "lr_3")]
      == [("SR", "金色的奇蹟"), ("SSR", "傳說收藏家"), ("UR", "黃金卡冊"), ("UR", "觸及傳說之人"), ("LR", "幻想的頂點")])
check("lr needs 10 ur", td.unlocked_titles({"ur_kinds": 9, "lr_kinds": 3}) == ["ur_5", "ur_1"])
check("lr chain", td.unlocked_titles({"ur_kinds": 10, "lr_kinds": 3}) == ["lr_3", "ur_10", "lr_1", "ur_5", "ur_1"])
check("perfect titles", [(td.TITLES[f"perfect_{n}"]["rarity"], td.TITLES[f"perfect_{n}"]["name"]) for n in (1, 10, 30, 50)]
      == [("R", "一絲不苟"), ("SR", "收藏家的堅持"), ("SSR", "無瑕的卡冊"), ("UR", "完美的瀟灑")])
check("perfect condition", td.condition_text("perfect_10") == "卡冊有 10 種完美卡 (完整度 1.0000)")
check("requires text", td.condition_text("lr_1") == "卡冊有 1 種角色的 LR 卡，且已獲得「黃金卡冊」")
check("requires exist", all(t.get("requires", "ur_1") in td.TITLES for t in td.TITLES.values()))
check("every title grouped", all(td.title_group(t) for t in td.TITLES))
check("group sizes ok", len(td.TITLE_GROUPS) <= 25 and all(len(v) <= 24 for v in td.group_titles(list(td.TITLES)).values()))
check("group order", list(td.group_titles(["pool_all", "draw_10", "ur_1"])) == ["draw", "rare", "pool"])
check("label", td.title_label("draw_2000") == "[UR] 賽錢箱的守護神")
check("color", td.title_color("draw_5000") == 0xE74C3C and td.title_color(None) == td.NO_TITLE_COLOR == 0x5865F2)

async def main():
    # 舊版 gacha_stats 沒有 total_synths ➔ init_db 要自動補上
    con = sqlite3.connect(udm.DB_PATH)
    con.execute("CREATE TABLE gacha_stats (user_id INTEGER PRIMARY KEY, total_draws INTEGER NOT NULL DEFAULT 0, total_fusions INTEGER NOT NULL DEFAULT 0)")
    con.execute("INSERT INTO gacha_stats VALUES (99, 5, 2)"); con.commit(); con.close()
    await udm.init_db()
    con = sqlite3.connect(udm.DB_PATH)
    check("migrated total_synths", con.execute("SELECT total_synths FROM gacha_stats WHERE user_id = 99").fetchone() == (0,)); con.close()

    # 🌟 UR / LR：卡冊裡現在有幾種角色 (同角色多張只算一種，賣掉就沒了)
    U = 60
    await udm.get_or_create_user(U)
    for i, (ck, r) in enumerate([("reimu", "UR"), ("reimu", "UR"), ("marisa", "UR"), ("remilia", "LR"), ("cirno", "SSR")]):
        sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, completeness) VALUES (?, ?, ?, 'x', ?, 0.5)", (f"u{i}", U, ck, r))
    s = await udm.get_title_stats(U)
    check("ur/lr kinds", (s["ur_kinds"], s["lr_kinds"]) == (2, 1))
    check("lr locked without 10 ur", (await udm.get_title_state(U))["unlocked"] == ["ur_1"])
    sql("DELETE FROM gacha_cards WHERE user_id = ? AND character_key IN ('reimu', 'marisa')", (U,))
    check("sold ur lost", (await udm.get_title_stats(U))["ur_kinds"] == 0 and (await udm.get_title_state(U))["unlocked"] == [])

    # 💎 完美卡：完整度 1.0000 (四捨五入 4 位)，角色 + 階級一樣只算一種
    P = 61
    await udm.get_or_create_user(P)
    for i, (ck, r, c) in enumerate([("reimu", "SR", 1.0), ("reimu", "SR", 1.0), ("reimu", "SSR", 0.99996),
                                    ("cirno", "SR", 0.9999), ("rumia", "R", 0.5)]):
        sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, completeness) VALUES (?, ?, ?, 'x', ?, ?)", (f"p{i}", P, ck, r, c))
    check("perfect kinds", (await udm.get_title_stats(P))["perfect_kinds"] == 2)
    check("perfect title", (await udm.get_title_state(P))["unlocked"] == ["perfect_1"])

    # 📚 卡池收集：紅魔鄉角色到齊 (階級不限) ➔ 全卡 ➔ 再加舊作全卡 = LR
    from Utils import gacha_pools as gp
    members = gp.pool_members()
    check("pool sizes", (len(members["classic"]), len(members["th06"])) == (15, 9)
          and sum(len(r) for r in members["classic"].values()) == 45 and sum(len(r) for r in members["th06"].values()) == 27)
    C = 62
    await udm.get_or_create_user(C)
    def add(pool, every_rarity, prefix):
        for cid, rs in members[pool].items():
            for r in (rs if every_rarity else rs[:1]):
                sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, completeness) VALUES (?, ?, ?, 'x', ?, 0.5)",
                    (f"{prefix}{cid}{r}", C, cid, r))
    add("th06", False, "a")
    st = await udm.get_title_stats(C)
    check("th06 chars", st["pool_chars:th06"] == 1 and st["pool_cards:th06"] == 0 and st["all_cards"] == 0)
    check("th06 chars title", "pool_th06_chars" in (await udm.get_title_state(C))["unlocked"])
    add("th06", True, "b")
    add("classic", True, "c")
    unlocked = (await udm.get_title_state(C))["unlocked"]
    check("all pools LR", {"pool_th06_cards", "pool_classic_chars", "pool_classic_cards", "pool_all"} <= set(unlocked))
    sql("DELETE FROM gacha_cards WHERE user_id = ? AND character_key = 'remilia' AND rarity = 'LR'", (C,))
    unlocked = (await udm.get_title_state(C))["unlocked"]
    check("sold one ➔ lose cards titles", "pool_all" not in unlocked and "pool_th06_cards" not in unlocked
          and "pool_th06_chars" in unlocked and "pool_classic_cards" in unlocked)
    check("pool condition text", td.condition_text("pool_th06_chars") == "紅魔鄉卡池的角色全部到齊"
          and td.condition_text("pool_classic_cards") == "舊作卡池的卡全部收集 (每個階級)")
    # 💕 推角：同一位角色 10 張 (階級不限)，名稱「我是XXX的狗!!!」，每位角色自動一個
    O = 63
    await udm.get_or_create_user(O)
    for i in range(10):
        sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, completeness) VALUES (?, ?, 'cirno', 'x', ?, 0.5)",
            (f"o{i}", O, ["SR", "SSR", "UR"][i % 3]))
    for i in range(9):
        sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, completeness) VALUES (?, ?, 'reimu', 'x', 'SR', 0.5)",
            (f"q{i}", O))
    st = await udm.get_title_stats(O)
    check("oshi counts", st["oshi:th06:cirno"] == 10 and st["oshi:classic:reimu"] == 9 and st["oshi:th06:rumia"] == 0)
    unlocked = (await udm.get_title_state(O))["unlocked"]
    check("oshi unlocked", "oshi_cirno" in unlocked and "oshi_reimu" not in unlocked)
    check("oshi name", td.TITLES["oshi_cirno"]["name"] == "我是琪露諾的狗!!!" and td.TITLES["oshi_cirno"]["rarity"] == "SR")
    check("oshi every character", all(f"oshi_{cid}" in td.TITLES for m in members.values() for cid in m))
    check("oshi condition", td.condition_text("oshi_cirno") == "卡冊有 10 張琪露諾的卡 (階級不限)")
    check("oshi groups", td.title_group("oshi_reimu") == "oshi_classic" and td.title_group("oshi_cirno") == "oshi_th06"
          and td.TITLE_GROUPS["oshi_th06"]["name"] == "💕 推角・紅魔鄉")
    sql("DELETE FROM gacha_cards WHERE instance_id = 'o0'")
    check("oshi sold lost", "oshi_cirno" not in (await udm.get_title_state(O))["unlocked"])
    check("every pool has titles", all(any(t["stat"] == f"pool_{k}:{p}" for t in td.TITLES.values())
                                       for p in gp.GACHA_POOLS for k in ("chars", "cards")))

    # 📅 簽到稱號 (累積天數) 與連續簽到 (daily_streak / best_streak)
    D = 50
    check("daily titles", [td.TITLES[f"daily_{n}"]["name"] for n in (7, 30, 60, 100, 200, 365)]
          == ["三日坊主不再", "每日參拜", "風雨無阻", "百日參拜", "神社的一份子", "四季的參拜者"])
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        await udm.claim_daily(D, day, 3)
    def streak():
        con = sqlite3.connect(udm.DB_PATH); r = con.execute("SELECT daily_streak, best_streak, daily_count FROM users WHERE user_id = ?", (D,)).fetchone(); con.close(); return r
    check("streak 3", streak() == (3, 3, 3))
    check("same day twice", await udm.claim_daily(D, "2026-11-03", 3) is False and streak() == (3, 3, 3))
    await udm.claim_daily(D, "2026-11-05", 3)   # 11/04 沒簽 ➔ 斷掉
    check("streak broken, best kept", streak() == (1, 3, 4))
    await udm.claim_daily(D, "2026-11-06", 3)
    check("streak again", streak() == (2, 3, 5))
    await udm.claim_daily(D, "2026-12-01", 3)   # 跨月也照日期算
    sql("UPDATE users SET daily_count = 30, best_streak = 0 WHERE user_id = ?", (D,))
    check("daily titles unlocked", (await udm.get_title_state(D))["unlocked"] == ["daily_30", "daily_7"])
    check("daily stats", (await udm.get_title_stats(D))["daily_count"] == 30)
    check("daily condition", td.condition_text("daily_365") == "累積簽到 365 天")
    check("streak titles", [(td.TITLES[t]["rarity"], td.TITLES[t]["min"]) for t in ("streak_30", "streak_100", "streak_365")]
          == [("SSR", 30), ("UR", 100), ("LR", 365)])
    sql("UPDATE users SET best_streak = 100, daily_streak = 1 WHERE user_id = ?", (D,))
    check("streak uses best", (await udm.get_title_state(D))["unlocked"][:2] == ["streak_100", "streak_30"])
    check("streak condition", td.condition_text("streak_30") == "連續簽到 30 天")
    A = 1
    st = await udm.get_title_state(A)
    check("new player no titles", st == {"equipped": None, "unlocked": []})
    check("cannot equip locked", await udm.set_equipped_title(A, "draw_10") is False)
    check("cannot equip unknown", await udm.set_equipped_title(A, "nope") is False)

    sql("INSERT INTO gacha_stats (user_id, total_draws) VALUES (?, 120)", (A,))
    st = await udm.get_title_state(A)
    check("unlocked after draws", st["unlocked"] == ["draw_100", "draw_10"])
    check("equip", await udm.set_equipped_title(A, "draw_100") and (await udm.get_title_state(A))["equipped"] == "draw_100")
    check("equip higher locked", await udm.set_equipped_title(A, "draw_500") is False
          and (await udm.get_title_state(A))["equipped"] == "draw_100")
    # 資料庫裡的稱號已不符條件 (例如之後改了門檻) ➔ 當成沒戴
    sql("UPDATE users SET equipped_title = 'draw_5000' WHERE user_id = ?", (A,))
    check("invalid equipped hidden", (await udm.get_title_state(A))["equipped"] is None)
    sql("UPDATE gacha_stats SET total_fusions = 12 WHERE user_id = ?", (A,))
    check("fusion stat read", (await udm.get_title_state(A))["unlocked"] == ["draw_100", "fusion_10", "draw_10", "fusion_1"])
    sql("UPDATE gacha_stats SET total_fusions = 0 WHERE user_id = ?", (A,))
    # 合成次數 (2026-11-13 起記錄)：合成才加，融合不加
    card = {"instance_id": "s1", "character_key": "reimu", "name": "x", "emoji": "x", "rarity": "SR",
            "title": "x", "completeness": 0.5, "obtained_at": "x"}
    await udm.add_gacha_cards(A, [card, dict(card, instance_id="s2")], draw_count=0)
    await udm.transform_cards(A, ["s1", "s2"], lambda cs: dict(cs[0], instance_id="s3"), count_synthesis=True)
    check("synthesis counted", (await udm.get_title_stats(A))["total_synths"] == 1
          and "synth_1" in (await udm.get_title_state(A))["unlocked"])
    await udm.add_gacha_cards(A, [dict(card, instance_id="s4")], draw_count=0)
    await udm.transform_cards(A, ["s3", "s4"], lambda cs: dict(cs[0], instance_id="s5"))
    check("plain transform not counted", (await udm.get_title_stats(A))["total_synths"] == 1)
    check("unequip", await udm.set_equipped_title(A, None) and (await udm.get_title_state(A))["equipped"] is None)

    # --- /profile 畫面 ---
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.profile")
    cog = bot.get_cog("Profile")
    cmds = {c.name: c for c in cog.walk_app_commands()}

    it = Interaction(uid=A); await cmds["profile"].callback(cog, it, None, None)
    pv = it.view
    check("no title fixed color", accent(pv) == td.NO_TITLE_COLOR)
    sel = selects(pv)
    # 先選分組再選稱號 (Discord 選單最多 25 個，稱號全放一起放不下)；預設 = 最高等級稱號那組
    check("group + title selects", len(sel) == 2 and [o.value for o in sel[0].options] == ["draw", "synth"]
          and [o.label for o in sel[0].options] == ["🎰 祈願", "⚗️ 合成"] and sel[0].options[0].default)
    check("title select on own card", not sel[1].disabled and [o.value for o in sel[1].options] == ["draw_100", "draw_10", "__none__"])
    check("select shows desc", sel[1].options[0].description == td.TITLES["draw_100"]["desc"])
    ig = Interaction(uid=A, data={"values": ["synth"]}); await pv.on_title_group(ig)
    sel = selects(pv)
    check("switch group", [o.value for o in sel[1].options] == ["synth_1", "__none__"] and sel[0].options[1].default)
    ig = Interaction(uid=A, data={"values": ["draw"]}); await pv.on_title_group(ig)

    i2 = Interaction(uid=A, data={"values": ["draw_100"]}); await pv.on_title(i2)
    t = texts(pv)
    check("title shown", "**[R] 虔誠的參拜者**" in t and f"-# *{td.TITLES['draw_100']['desc']}*" in t)
    check("title under name", t.index("的幻想鄉通行證") < t.index("[R] 虔誠的參拜者") < t.index("資料卡 • TouHouBot"))
    check("title color", accent(pv) == td.RARITY_COLORS["R"])
    check("saved", (await udm.get_title_state(A))["equipped"] == "draw_100")

    i3 = Interaction(uid=A, data={"values": ["draw_5000"]}); await pv.on_title(i3)
    check("locked rejected", "還沒有解鎖" in texts(i3.view) and (await udm.get_title_state(A))["equipped"] == "draw_100")

    # 私人資料卡一樣用稱號顏色 (2026-11-13 使用者)
    await udm.update_visibility(A, False)
    it = Interaction(uid=A); await cmds["profile"].callback(cog, it, None, None)
    check("private same color", accent(it.view) == td.RARITY_COLORS["R"] and "[R] 虔誠的參拜者" in texts(it.view))
    await udm.update_visibility(A, True)

    # 別人看得到稱號，但沒有選單
    it = Interaction(uid=2); await cmds["profile"].callback(cog, it, types.SimpleNamespace(id=A, display_name="t", display_avatar=avatar), None)
    check("others see title", "[R] 虔誠的參拜者" in texts(it.view) and not selects(it.view))

    # 卸下
    i4 = Interaction(uid=A, data={"values": ["__none__"]}); await pv.on_title(i4)
    check("unequip via select", "虔誠的參拜者" not in texts(pv) and accent(pv) == td.NO_TITLE_COLOR)

    # 沒有任何稱號 ➔ 選單反灰
    it = Interaction(uid=3); await cmds["profile"].callback(cog, it, None, None)
    check("disabled when none", selects(it.view)[0].disabled)

    # 🛠️ /admin-user title：管理員直接給 / 戴上 / 收回稱號，不用符合條件
    from Utils import config
    config.ADMIN_IDS = config.ADMIN_IDS | {900}
    await bot.load_extension("Cogs.load-general.Admin-user")
    acog = bot.get_cog("UserAdmin")
    title_cmd = next(c for c in acog.walk_app_commands() if c.name == "title")
    act = lambda v: app_commands.Choice(name=v, value=v)
    G = 70
    it = Interaction(uid=900)
    await title_cmd.callback(acog, it, act("equip"), "draw_5000", types.SimpleNamespace(id=G, display_name="g"))
    st = await udm.get_title_state(G)
    check("admin equip any title", st["equipped"] == "draw_5000" and st["unlocked"] == ["draw_5000"] and "戴上了" in texts(it.view))
    await title_cmd.callback(acog, Interaction(uid=900), act("grant"), "streak_365", types.SimpleNamespace(id=G, display_name="g"))
    check("admin grant", (await udm.get_title_state(G))["unlocked"] == ["draw_5000", "streak_365"])
    await title_cmd.callback(acog, Interaction(uid=900), act("revoke"), "draw_5000", types.SimpleNamespace(id=G, display_name="g"))
    st = await udm.get_title_state(G)
    check("admin revoke drops equipped", st["unlocked"] == ["streak_365"] and st["equipped"] is None)
    it = Interaction(uid=900); await title_cmd.callback(acog, it, act("grant"), "亂打", None)
    check("admin bad title", "找不到這個稱號" in texts(it.view))
    it = Interaction(uid=G); await title_cmd.callback(acog, it, act("grant"), "draw_10", None)
    check("non-admin blocked", "無權限" in texts(it.view) and await udm.get_granted_titles(G) == ["streak_365"])
    choices = await acog.title_autocomplete(Interaction(uid=900), "")
    check("autocomplete ≤ 25", len(choices) == 25 and choices[0].name.startswith("[LR]"))
    check("autocomplete filter", [c.value for c in await acog.title_autocomplete(Interaction(uid=900), "黃金")] == ["ur_10"])
    # 自己達成條件的稱號收回也不會不見
    await title_cmd.callback(acog, Interaction(uid=900), act("revoke"), "draw_100", types.SimpleNamespace(id=A, display_name="a"))
    check("revoke earned keeps", "draw_100" in (await udm.get_title_state(A))["unlocked"])

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

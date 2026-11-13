"""🏷️ 稱號：解鎖條件、戴上 / 卸下、沒解鎖不能戴、/profile 顯示稱號與說明、色條顏色、更換選單"""
import asyncio, os, sys, tempfile, types, sqlite3
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
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
check("condition text", td.condition_text("fusion_500") == "累計融合 500 次")
check("unlock none", td.unlocked_titles({"total_draws": 9}) == [])
check("unlock order high first", td.unlocked_titles({"total_draws": 600}) == ["draw_500", "draw_100", "draw_10"])
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
    check("synthesis counted", (await udm.get_title_stats(A))["total_synths"] == 1)
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
    check("title select on own card", len(sel) == 1 and not sel[0].disabled
          and [o.value for o in sel[0].options] == ["draw_100", "draw_10", "__none__"])
    check("select shows desc", sel[0].options[0].description == td.TITLES["draw_100"]["desc"])

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

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

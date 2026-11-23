"""🎪 /admin-event start (2026-11-22)：一次開多個活動、排開始時間、持續天數、覆蓋舊活動；end 取消排程"""
import asyncio, copy, json, os, shutil, sqlite3, sys, tempfile, types
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm, Item_DB_Manager as idm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
shutil.copy(idm.DB_PATH, os.path.join(tmp, "Item.db")); idm.DB_PATH = os.path.join(tmp, "Item.db")
from Database import Economy_DB_Manager as econ, events

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

def rows(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); r = con.execute(q, args).fetchall(); con.close(); return r

def state(eid):
    r = rows("SELECT value FROM economy_meta WHERE key = ?", (f"event:{eid}",))
    return json.loads(r[0][0]) if r else None

# 假活動：a = 紅霧異變的複製 (auto_start、有活動道具、有任務、開放紅魔鄉卡池)；b = 最簡單的活動
REAL = events.load_events()["th06_scarlet_mist"]
A_EV = dict(copy.deepcopy(REAL), id="a")
B_EV = {"id": "b", "name": "測試祭", "emoji": "🎉", "description": "", "items": []}
FAKE = {"a": A_EV, "b": B_EV}
fake_load = lambda: copy.deepcopy(FAKE)
events.load_events = fake_load   # udm._event_runs 執行時才 import
econ.load_events = fake_load

ADMIN = 403895664666214400
U = 4242
T0 = datetime.now(timezone.utc).replace(second=0, microsecond=0)
H, DAY = timedelta(hours=1), timedelta(days=1)
A_ITEM = sorted(events.event_item_ids(A_EV))[0]


async def runs(now):
    async with udm.connect() as db:
        return await udm._event_runs(db, now)


class Resp:
    def __init__(s, it): s.it = it; s.done = False
    def is_done(s): return s.done
    async def defer(s, **kw): s.done = True
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view"); s.it.kw = kw
    async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view")
class Interaction:
    def __init__(s, uid=ADMIN):
        s.user = types.SimpleNamespace(id=uid, display_name="admin"); s.response = Resp(s); s.followup = Followup(s)
        s.view = None; s.kw = {}; s.data = {}; s.type = discord.InteractionType.application_command
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))


async def main():
    await udm.init_db()
    await udm.get_or_create_user(U)
    con = sqlite3.connect(udm.DB_PATH)
    con.execute("UPDATE users SET inventory = ? WHERE user_id = ?", (json.dumps({A_ITEM: 3}), U)); con.commit(); con.close()

    # 一開始：a 是 auto_start (沒有紀錄 = 進行中)，b 沒在進行
    check("phase start", await econ.get_event_phase("a", T0) == "running" and await econ.get_event_phase("b", T0) == "off")
    check("a quest run auto", (await runs(T0))["a"]["run"] == "a:auto")

    # 1. 現在開始 b、7 天：a 沒勾到 ➔ 馬上結束並清活動道具
    plan = await econ.preview_event_schedule(["b"], None, 7, T0)
    acts = {p["event"]["id"]: p["action"] for p in plan}
    check(f"preview {acts}", acts == {"a": "end_now", "b": "start"} and state("b") is None)   # 預覽不會寫入
    plan = await econ.admin_schedule_events(["b"], None, 7, T0)
    pa = next(p for p in plan if p["event"]["id"] == "a")
    check("a ended now", state("a")["status"] == "ended" and pa["cleared"] == 1)
    inv = json.loads(rows("SELECT inventory FROM users WHERE user_id = ?", (U,))[0][0])
    check("a items cleared", A_ITEM not in inv)
    sb = state("b")
    check(f"b started {sb}", sb["status"] == "active" and sb["started_at"] == T0.isoformat() and sb["ends_at"] == (T0 + 7 * DAY).isoformat())
    check("only b active", [e["id"] for e in await active(T0)] == ["b"])
    check("th06 closed with a", "th06" not in (await econ.get_rules(T0))["gacha_event_pools"])

    # 2. 排 a 在兩天後開始、3 天：b 沒勾到 ➔ 跑到 a 開始那一刻才結束
    start = T0 + 2 * DAY
    plan = await econ.admin_schedule_events(["a"], start, 3, T0)
    acts = {p["event"]["id"]: p["action"] for p in plan}
    check(f"schedule {acts}", acts == {"a": "start", "b": "end_at"})
    check("a scheduled", await econ.get_event_phase("a", T0) == "scheduled" and state("a")["started_at"] == start.isoformat()
          and state("a")["ends_at"] == (start + 3 * DAY).isoformat())
    check("b ends at a start", state("b")["ends_at"] == start.isoformat() and await econ.get_event_phase("b", T0) == "running")
    check("scheduled not active", [e["id"] for e in await active(T0 + H)] == ["b"] and "a" not in await runs(T0 + H))
    ov = {o["event"]["id"]: o for o in await econ.get_events_overview(T0 + H)}
    check("overview upcoming", ov["a"]["status"] == "upcoming" and ov["a"]["scheduled"] and ov["b"]["status"] == "active")
    sc = __import__("importlib").import_module("Cogs.load-general.Components.shrine_components")
    info = texts(sc.build_event_container(list(ov.values()), {}, {}))
    check("info shows start time", f"<t:{int(start.timestamp())}:f>開始" in info)
    # 時間到：b 結束、a 開始 (紅魔鄉卡池跟著開)
    t = start + timedelta(minutes=1)
    check("switch over", [e["id"] for e in await active(t)] == ["a"] and state("b")["status"] == "ended")
    check("th06 open again", "th06" in (await econ.get_rules(t))["gacha_event_pools"])
    check("a new run", (await runs(t))["a"]["run"] == f"a:{start.isoformat()}")

    # 3. 勾到本來就在進行中的 a ➔ 不重開，只改結束時間 (0 = 一直持續)；任務那一輪不變
    plan = await econ.admin_schedule_events(["a"], None, None, t + H)
    check("extend", [p["action"] for p in plan if p["event"]["id"] == "a"] == ["extend"]
          and state("a")["started_at"] == start.isoformat() and state("a")["ends_at"] is None)
    check("extend same run", (await runs(t + 2 * H))["a"]["run"] == f"a:{start.isoformat()}")

    # 4. 排 b 在 10 天後；之後只勾 a ➔ 還沒開始的 b 取消排程
    t2 = t + 3 * H
    await econ.admin_schedule_events(["b"], T0 + 10 * DAY, 5, t2)
    check("a ends at b start", state("a")["ends_at"] == (T0 + 10 * DAY).isoformat() and await econ.get_event_phase("b", t2) == "scheduled")
    plan = await econ.admin_schedule_events(["a"], None, 30, t2 + H)
    acts = {p["event"]["id"]: p["action"] for p in plan}
    check(f"cancel scheduled {acts}", acts == {"a": "extend", "b": "cancel"} and state("b")["status"] == "cancelled"
          and state("a")["ends_at"] == (t2 + H + 30 * DAY).isoformat())
    ov = {o["event"]["id"]: o for o in await econ.get_events_overview(t2 + 2 * H)}
    check("cancelled shows upcoming", ov["b"]["status"] == "upcoming" and not ov["b"]["scheduled"])

    # 5. end 還沒開始的活動 = 取消排程 (不清道具)；end 進行中的 = 結束
    await econ.admin_schedule_events(["a", "b"], T0 + 20 * DAY, 1, t2 + 3 * H)   # a 已在進行 ➔ extend；b ➔ 排在 20 天後
    check("both selected", await econ.get_event_phase("b", t2 + 3 * H) == "scheduled" and await econ.get_event_phase("a", t2 + 3 * H) == "running")
    check("end scheduled cancels", await econ.admin_end_event("b", t2 + 4 * H) == 0 and state("b")["status"] == "cancelled")
    check("unknown event", await econ.admin_schedule_events(["nope"], None, None, t2) is None
          and await econ.admin_schedule_events([], None, None, t2) is None)

    # 6. auto_start 沒紀錄的活動被延長 ➔ started_at 維持 None (任務那一輪還是 a:auto)
    con = sqlite3.connect(udm.DB_PATH); con.execute("DELETE FROM economy_meta WHERE key LIKE 'event:%'"); con.commit(); con.close()
    await econ.admin_schedule_events(["a"], None, 5, T0)
    check("auto extend keeps run", state("a")["started_at"] is None and (await runs(T0 + H))["a"]["run"] == "a:auto")
    # auto_start 的活動排在之後才結束 (沒勾到、開始時間在以後)
    con = sqlite3.connect(udm.DB_PATH); con.execute("DELETE FROM economy_meta WHERE key LIKE 'event:%'"); con.commit(); con.close()
    await econ.admin_schedule_events(["b"], T0 + DAY, None, T0)
    check("auto end_at", state("a")["ends_at"] == (T0 + DAY).isoformat() and state("a")["started_at"] is None
          and (await runs(T0 + H))["a"]["run"] == "a:auto")

    # ---- 指令與畫面 ----
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.Admin-event")
    amod = sys.modules["Cogs.load-general.Admin-event"]
    amod.load_events = fake_load
    cog = bot.get_cog("EventAdmin")
    cmds = {c.name: c for c in cog.walk_app_commands()}
    check("commands", set(cmds) == {"start", "end"})

    # 開始時間：台灣時間、可以省略年份、過去的時間擋掉
    now = datetime(2026, 11, 22, 4, 0, tzinfo=timezone.utc)   # 台灣 12:00
    check("parse full", amod.parse_start("2026-11-25 20:00", now) == datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc))
    check("parse no year", amod.parse_start("11/25 20:00", now) == datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc))
    check("parse date only", amod.parse_start("2026/11/30", now) == datetime(2026, 11, 29, 16, 0, tzinfo=timezone.utc))
    check("parse blank", amod.parse_start("  ", now) is None and amod.parse_start(None, now) is None)
    for bad in ("明天", "2026-13-01 10:00", "11-21 20:00"):
        try:
            amod.parse_start(bad, now); check(f"parse {bad} rejected", False)
        except ValueError as e:
            check(f"parse {bad} rejected", "看不懂" in str(e) or "已經過了" in str(e))

    it = Interaction(uid=1); await cmds["start"].callback(cog, it, None, None)
    check("start denied", "無權限" in texts(it.view))
    it = Interaction(); await cmds["start"].callback(cog, it, "後天", None)
    check("start bad time", "看不懂開始時間" in texts(it.view))
    con = sqlite3.connect(udm.DB_PATH); con.execute("DELETE FROM economy_meta WHERE key LIKE 'event:%'"); con.commit(); con.close()
    it = Interaction(); await cmds["start"].callback(cog, it, None, 0)
    view = it.view
    check("start screen", "開始活動" in texts(view) and "一直持續" in texts(view) and it.kw.get("ephemeral"))
    opts = {o.value: o for o in view.select.options}
    check("select options", set(opts) == {"a", "b"} and opts["a"].description == "🟢 進行中" and view.select.max_values == 2)
    ok_btn = next(b for b in view.walk_children() if isinstance(b, discord.ui.Button) and b.label == "✅ 確認開始")
    check("confirm disabled first", ok_btn.disabled)
    check("others blocked", await view.interaction_check(Interaction(uid=1)) is False)
    view.select._values = ["b"]
    it = Interaction(); await view.on_select(it)
    t = texts(view)
    check(f"preview screen {t}", "🟢 開始：🎉 **測試祭** — 現在開始，一直持續" in t and "馬上結束" in t
          and "紅魔鄉卡池也會跟著關" in t and state("b") is None)
    # 勾到進行中的紅霧異變、給結束時間 ➔ 也要提醒到時候紅魔鄉卡池會關、活動道具會清
    ext = await econ.preview_event_schedule(["a"], None, 5)
    lines = "\n".join(amod.plan_lines(ext, datetime.now(timezone.utc)))
    check(f"extend warns {lines}", "已經在進行中" in lines and "到結束時間會清掉活動素材" in lines and "紅魔鄉卡池也會跟著關" in lines)
    lines = "\n".join(amod.plan_lines(await econ.preview_event_schedule(["a"], None, None), datetime.now(timezone.utc)))
    check("extend forever no warning", "紅魔鄉卡池" not in lines and "清掉" not in lines)
    i1, i2 = Interaction(), Interaction()
    await view.on_ok(i1); await view.on_ok(i2)
    check("applied", "已套用" in texts(view) and state("b")["status"] == "active" and state("a")["status"] == "ended")
    # end：進行中 ➔ 結束確認；沒在進行 ➔ 提示；還沒開始 ➔ 取消排程
    it = Interaction(); await cmds["end"].callback(cog, it, "a")
    check("end off", "本來就沒在進行" in texts(it.view))
    await econ.admin_schedule_events(["a", "b"], datetime.now(timezone.utc) + 3 * DAY, 2)
    it = Interaction(); await cmds["end"].callback(cog, it, "a")
    ev_view = it.view
    check("end scheduled confirm", "取消" in texts(ev_view) and "紅魔鄉卡池也會跟著關" in texts(ev_view))
    it = Interaction(); await ev_view.on_ok(it)
    check("end scheduled done", "已取消" in texts(ev_view) and state("a")["status"] == "cancelled")
    it = Interaction(); await cmds["end"].callback(cog, it, "b")
    it2 = Interaction(); await it.view.on_ok(it2)
    check("end running", "已結束" in texts(it.view) and state("b")["status"] == "ended")


async def active(now):
    async with udm.connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            out = await econ._active_events(db, now)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return out


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

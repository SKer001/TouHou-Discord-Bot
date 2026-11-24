"""🎪 好幾個活動同時開活動限定卡池 (2026-11-24 使用者定案)：每個活動各一個卡池，選「🎪 活動限定卡池」時好幾個 ➔ 先跳選單

兩個假活動同時進行 (只在這個測試裡換掉 load_events，不放進 Events/)：
- fa：gacha.pool {"from": "th06"} (紅魔鄉卡池只在活動期間開放)
- fb：gacha.pool {"characters": [...]} (活動自己的卡池 event_fb)
兩個卡池都抽得到、保底各記各的、活動任務 gacha_event_pool 各算各的；只剩一個活動時行為跟以前一樣
"""
import asyncio, importlib, os, shutil, sqlite3, sys, tempfile, types
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
os.environ.setdefault("SHOW_UNRELEASED", "1")   # 🙈 測試預設看得到未公開卡池 (Utils/config.py)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm, Item_DB_Manager as idm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
shutil.copy(idm.DB_PATH, os.path.join(tmp, "Item.db")); idm.DB_PATH = os.path.join(tmp, "Item.db")
from Database import Economy_DB_Manager as econ, Quest_DB_Manager as qdm, events
gacha = importlib.import_module("Cogs.load-gacha.gacha")
amod = importlib.import_module("Cogs.load-general.Admin-event")
gc = importlib.import_module("Cogs.load-general.Components.guide_components")

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
    async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view"); s.it.kw = kw
class Interaction:
    def __init__(s, uid=1, component=False):
        s.user = types.SimpleNamespace(id=uid, display_name="t"); s.response = Resp(s); s.followup = Followup(s); s.view = None; s.kw = {}
        s.type = discord.InteractionType.component if component else discord.InteractionType.application_command
    async def edit_original_response(s, **kw): s.view = kw.get("view")

def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))

def quest(qid):
    return {"id": qid, "name": qid, "desc": "測試", "type": "gacha_event_pool", "count": 100, "reward": {"money": 1, "exp": 1}}

FA = {"id": "fa", "name": "測試紅霧", "emoji": "🔴", "auto_start": True, "gacha": {"pool": {"from": "th06"}}, "quests": [quest("qa")]}
FB = {"id": "fb", "name": "測試春雪", "emoji": "🌸", "auto_start": True,
      "gacha": {"pool": {"characters": ["reimu", "marisa"], "desc": "只有靈夢和魔理沙"}}, "quests": [quest("qb")]}
REAL_LOAD = events.load_events

def use_events(*evs):
    """換掉活動檔 (events / econ 兩邊的 load_events 都要換；udm._event_runs、pool_open_events 讀 events 的)"""
    fake = lambda: {e["id"]: e for e in evs}
    events.load_events = fake
    econ.load_events = fake

def run_stats(eid):
    con = sqlite3.connect(udm.DB_PATH)
    rows = dict(con.execute("SELECT stat, value FROM event_quest_stats WHERE user_id = 1 AND run = ?",
                            (udm.event_run_id(eid, None),)).fetchall())
    con.close()
    return rows

async def pity(key):
    return (await udm.get_gacha_pity(1)).get(key, {}).get("total_draws", 0)


async def main():
    await udm.init_db()
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    cog = gacha.GachaCardSys(bot); await bot.add_cog(cog)
    th06 = {k for k, v in gacha.GACHA_POOL.items() if v["pool"] == "th06"}
    await udm.add_money(1, 10_000_000)

    # ================= 兩個活動同時進行 ➔ 兩個卡池 =================
    use_events(FA, FB)
    rules = await econ.get_rules()
    pools = rules["gacha_event_pools"]
    check(f"two pools {list(pools)}", list(pools) == ["th06", "event_fb"])
    check("pool names", pools["th06"]["name"] == "🎪 🔴 紅魔鄉卡池・測試紅霧限定" and pools["event_fb"]["name"] == "🌸 測試春雪卡池")
    check("resolve event ambiguous", gacha.resolve_pool("event", rules) is None)
    check("resolve each", gacha.resolve_pool("th06", rules) == ("th06", pools["th06"]["name"])
          and gacha.resolve_pool("event_fb", rules) == ("event_fb", "🌸 測試春雪卡池")
          and gacha.resolve_pool("event_zz", rules) is None and gacha.resolve_pool("classic", rules)[0] == "classic")

    # 選「🎪 活動限定卡池」➔ 先跳選單 (不扣錢、不抽)
    money = (await udm.get_or_create_user(1))["money"]
    cards0 = len(await udm.get_user_cards(1))
    it = Interaction(); await cog.execute_gacha(it, 10, "event")
    picker = it.view
    check("picker shown", isinstance(picker, gacha.EventPoolPickerView) and "選擇活動限定卡池" in texts(picker)
          and "**2** 個" in texts(picker) and "50,000" in texts(picker))
    check("picker options", [(o.value, o.label) for o in picker.select.options]
          == [("th06", pools["th06"]["name"]), ("event_fb", "🌸 測試春雪卡池")]
          and picker.select.options[1].description == "只有靈夢和魔理沙")
    check("picker no charge", (await udm.get_or_create_user(1))["money"] == money and len(await udm.get_user_cards(1)) == cards0)
    check("picker others blocked", await picker.interaction_check(Interaction(uid=2)) is False
          and await picker.interaction_check(Interaction(uid=1)) is True)

    # 選紅魔鄉 ➔ 抽 th06，保底記 th06；連點不會抽兩次
    picker.select._values = ["th06"]
    i1, i2 = Interaction(component=True), Interaction(component=True)
    await asyncio.gather(picker.on_pick(i1), picker.on_pick(i2))
    new = (await udm.get_user_cards(1))[cards0:]
    check(f"picked th06 {len(new)}", len(new) == 10 and {c["character_key"] for c in new} <= th06)
    check("picked th06 pity", await pity("th06") == 10 and await pity("event_fb") == 0)
    res = i1.view if isinstance(i1.view, gacha.GachaResultView) else i2.view
    check("result view keeps th06", isinstance(res, gacha.GachaResultView) and res.pool_key == "th06"
          and "測試紅霧限定" in texts(res) and picker.is_finished())
    it2 = Interaction(component=True); await res.draw_single_again(it2)
    check("redraw th06 (no picker)", await pity("th06") == 11 and isinstance(it2.view, gacha.GachaResultView))

    # 再來一次，選 event_fb ➔ 只抽活動列的角色，保底記 event_fb
    it = Interaction(); await cog.execute_gacha(it, 10, "event")
    it.view.select._values = ["event_fb"]
    before = len(await udm.get_user_cards(1))
    pick = Interaction(component=True); await it.view.on_pick(pick)
    new = (await udm.get_user_cards(1))[before:]
    check("picked event_fb", len(new) == 10 and {c["character_key"] for c in new} <= {"reimu", "marisa"})
    check("pity separate", await pity("event_fb") == 10 and await pity("th06") == 11)
    check("result view keeps event_fb", pick.view.pool_key == "event_fb" and "測試春雪卡池" in texts(pick.view))

    # 活動任務：gacha_event_pool 各算各的 (fa 只算 th06、fb 只算 event_fb)；gacha_pool:th06 照舊記給全部活動
    sa, sb = run_stats("fa"), run_stats("fb")
    check(f"quest fa {sa}", sa.get("gacha_event_pool") == 11 and sa.get("gacha_pool:th06") == 11)
    check(f"quest fb {sb}", sb.get("gacha_event_pool") == 10 and sb.get("gacha_pool:th06") == 11)
    board = {b["event"]["id"]: b for b in await qdm.get_quest_board(1)}
    check("board progress", board["fa"]["quests"][0]["cur"] == 11 and board["fb"]["quests"][0]["cur"] == 10)
    check("quest goal names", events.quest_goal(FA["quests"][0], FA) == "在「🎪 🔴 紅魔鄉卡池・測試紅霧限定」祈願 {p} 抽"
          and events.quest_goal(FB["quests"][0], FB) == "在「🌸 測試春雪卡池」祈願 {p} 抽")

    # 賽錢不足：選單留著 (可以再選)，沒扣錢
    con = sqlite3.connect(udm.DB_PATH); con.execute("UPDATE users SET money = 0 WHERE user_id = 1"); con.commit(); con.close()
    it = Interaction(); await cog.execute_gacha(it, 10, "event")
    poor = it.view; poor.select._values = ["event_fb"]
    p = Interaction(component=True); await poor.on_pick(p)
    check("poor notice", "賽錢不足" in texts(p.view) and not poor.is_finished() and not poor.busy and await pity("event_fb") == 10)
    await udm.add_money(1, 10_000_000)

    # 選單逾時 ➔ 換成提示
    src = Interaction(); timed = gacha.EventPoolPickerView(1, cog, 1, pools, 5000, src)
    await timed.on_timeout()
    check("picker timeout", "放太久" in texts(src.view) and "/card gacha" in texts(src.view))

    # 繼續祈願按鈕在「好幾個活動卡池」時按到 "event" (舊畫面) ➔ 改成跳選單
    old = gacha.GachaResultView(1, "t", cog, discord.ui.Container(), "event")
    o = Interaction(component=True); await old.draw_ten_again(o)
    check("old event button ➔ picker", isinstance(o.view, gacha.EventPoolPickerView))

    # 📊 機率表 / 📜 祈願紀錄
    for key in ("th06", "event_fb"):
        sheet = Interaction(); await gacha.send_rate_sheet(sheet, key)
        check(f"rate sheet {key}", pools[key]["name"] in texts(sheet.view))
    sheet = Interaction(); await gacha.send_rate_sheet(sheet, "event")
    check("rate sheet event ambiguous", "好幾個活動限定卡池" in texts(sheet.view))
    hcmd = next(c for c in cog.walk_app_commands() if c.name == "history")
    it = Interaction(); await hcmd.callback(cog, it)
    check(f"history lists both {[o.value for o in it.view.select.options]}",
          [o.value for o in it.view.select.options] == ["classic", "th06", "event_fb"]
          and "🌸 測試春雪卡池" in texts(it.view) and "測試紅霧期間開放" in texts(it.view))

    # 📚 教學書：兩個都列出來
    ctx = {"active": [FA, FB], "rules": rules}
    pull = gc.load_book("card")["chapters"][0]
    body = gc.body_text(pull, ctx)
    check("guide lists both", f"現在的活動限定卡池：{pools['th06']['name']}、🌸 測試春雪卡池" in body and "現在開放中" in body
          and len(body) <= 3200)

    # 🛠️ /admin-event：結束時會跟著關的卡池 (別的活動也開同一個就不會關)
    check("close text characters", amod.pool_close_text(FB) == "🌸 測試春雪卡池也會跟著關")
    check("close text from", amod.pool_close_text(FA) == "🔴 紅魔鄉卡池也會跟著關 (平常抽不到)"
          and amod.pool_close_text(FA, {"th06"}) == "")
    FC = {"id": "fc", "name": "又一個", "gacha": {"pool": {"from": "th06"}}}
    plan = [{"event": FA, "action": "end_now"}, {"event": FC, "action": "start", "started_at": None, "ends_at": None}]
    lines = "\n".join(amod.plan_lines(plan, datetime.now(timezone.utc)))
    check(f"plan: th06 stays open {lines}", "結束：🔴 **測試紅霧**" in lines and "紅魔鄉卡池也會跟著關" not in lines)
    plan[1]["ends_at"] = datetime.now(timezone.utc) + timedelta(days=3)   # 新活動有結束時間 ➔ 照樣提醒
    check("plan: warns when both end", "紅魔鄉卡池也會跟著關" in "\n".join(amod.plan_lines(plan, datetime.now(timezone.utc))))

    # ================= 只剩一個活動 ➔ 跟以前一樣直接抽 =================
    use_events(FA)
    money = (await udm.get_or_create_user(1))["money"]
    fb_res = pick.view   # event_fb 的結果畫面：活動結束了 ➔ 繼續祈願抽不到，也不扣錢
    s = Interaction(component=True); await fb_res.draw_single_again(s)
    check("ended pool blocked", "沒有進行中的活動卡池" in texts(s.view) and (await udm.get_or_create_user(1))["money"] == money
          and await pity("event_fb") == 10)
    it = Interaction(); await cog.execute_gacha(it, 10, "event")
    check("single pool direct", isinstance(it.view, gacha.GachaResultView) and it.view.pool_key == "th06" and await pity("th06") == 21)
    check("single pool quest", run_stats("fa").get("gacha_event_pool") == 21)

    events.load_events = econ.load_events = REAL_LOAD


asyncio.run(main())
print(f"passed {ok}, failed {fail}")

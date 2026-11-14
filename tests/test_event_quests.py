"""🎪 活動任務：活動檔格式、計數 (只在進行中、重開重新計)、領取、永久活動稱號、/event quest 畫面、快結束提醒"""
import asyncio, importlib, json, os, shutil, sqlite3, sys, tempfile
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord import app_commands, ui
from discord.ext import commands
from Database import User_DB_Manager as udm, Item_DB_Manager as idm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
shutil.copy(idm.DB_PATH, os.path.join(tmp, "Item.db")); idm.DB_PATH = os.path.join(tmp, "Item.db")
from Database import Economy_DB_Manager as econ, Quest_DB_Manager as qdm, Notify_DB_Manager as ndm
from Database import title_data as td, notify_data, events

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

EV = "th06_scarlet_mist"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
A, B, C, D = 101, 202, 303, 404
VISITOR, RESOLVER = td.event_title_id(EV, "visitor"), td.event_title_id(EV, "resolver")


def sql(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); con.execute(q, args); con.commit(); con.close()

def rows(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); r = con.execute(q, args).fetchall(); con.close(); return r

def stats(uid, run):
    return {s: v for s, v in rows("SELECT stat, value FROM event_quest_stats WHERE user_id = ? AND run = ?", (uid, run))}

def set_stats(uid, run, **kv):
    for k, v in kv.items():
        sql("INSERT OR REPLACE INTO event_quest_stats (user_id, run, stat, value) VALUES (?, ?, ?, ?)", (uid, run, k.replace("__", ":"), v))

def money(uid):
    return rows("SELECT money FROM users WHERE user_id = ?", (uid,))[0][0]

def give(uid, inv):
    sql("UPDATE users SET inventory = ? WHERE user_id = ?", (json.dumps(inv), uid))

def count(item):
    n = 1 + sum(count(ch) for ch in getattr(item, "children", []))
    acc = getattr(item, "accessory", None)
    return n + (count(acc) if acc is not None else 0)

def walk(item):
    yield item
    for ch in getattr(item, "children", []):
        yield from walk(ch)
    if getattr(item, "accessory", None) is not None:
        yield from walk(item.accessory)

def texts(view):
    return "\n".join(i.content for top in view.children for i in walk(top) if isinstance(i, ui.TextDisplay))

def buttons(view):
    return [i for top in view.children for i in walk(top) if isinstance(i, ui.Button)]

def total(view):
    return sum(count(i) for i in view.children)


class FakeResponse:
    def __init__(s): s.sent = []; s.done = False
    async def send_message(s, content=None, *, view=None, ephemeral=False, **kw):
        s.sent.append(("send", content, view, ephemeral, kw)); s.done = True
    async def edit_message(s, content=None, *, view=None, **kw):
        s.sent.append(("edit", content, view, None, kw)); s.done = True
    def is_done(s): return s.done

class FakeFollowup:
    def __init__(s): s.sent = []
    async def send(s, content=None, *, view=None, ephemeral=False, **kw): s.sent.append((content, view, ephemeral))

class FakeUser:
    def __init__(s, uid): s.id = uid; s.display_name = f"玩家{uid}"; s.name = s.display_name

class FakeInteraction:
    def __init__(s, uid): s.user = FakeUser(uid); s.response = FakeResponse(); s.followup = FakeFollowup(); s.guild = None


async def serve(uid, kind, order, extra=None, now=NOW):
    """在神社放一位指定種類的客人，給齊料理後招待"""
    sql("DELETE FROM shrines WHERE user_id = ?", (uid,))
    s = (await econ.admin_set_shrine(uid, guests=1, guest_mood=100, now=now))["summary"]
    raw = json.loads(rows("SELECT guests FROM shrines WHERE user_id = ?", (uid,))[0][0])
    raw[0]["kind"], raw[0]["order"] = kind, list(order)
    sql("UPDATE shrines SET guests = ? WHERE user_id = ?", (json.dumps(raw), uid))
    need = {}
    for d in list(order) + ([extra] if extra else []):
        need[d] = need.get(d, 0) + 1
    give(uid, need)
    return await econ.serve_guest(uid, raw[0]["id"], extra=extra, now=now)


def roll_none(since_ur):
    return [], since_ur, False


async def main():
    await udm.init_db()
    await ndm.init_notify_db()
    items = await idm.get_all_items()

    # ================= 活動檔格式 =================
    ev = events.load_events()[EV]
    check("validate th06", events.validate_quests(ev) == [])
    check("8 quests", len(ev["quests"]) == 8 and len({q["id"] for q in ev["quests"]}) == 8)
    check("2 titles", [(t["rarity"], t["name"], t["min_quests"]) for t in ev["quest_titles"]]
          == [("R", "紅霧中的參拜者", 4), ("SSR", "紅霧異變的解決者", 8)])
    expect = [("初探紅魔館廚房", "explore_location", 10, 50000, 300), ("女僕長的食譜", "cook_each", 3, 50000, 300),
              ("款待妖精女僕", "serve_guest", 5, 50000, 300), ("使魔的晚餐", "serve_guest", 5, 50000, 300),
              ("紅色的午茶時間", "serve_event_dish", 30, 100000, 500), ("完美的款待", "serve_favorite", 10, 50000, 300),
              ("紅霧中的祈願", "gacha_pool", 50, 100000, 500), ("異變調查", "daily", 7, 100000, 500)]
    check("quest table", [(q["name"], q["type"], events.quest_need(q), q["reward"]["money"], q["reward"]["exp"])
                          for q in ev["quests"]] == expect)
    check("targets", ev["quests"][0]["target"] == "scarlet_kitchen" and ev["quests"][2]["target"] == "fairy_maid"
          and ev["quests"][3]["target"] == "familiar_bat"
          and ev["quests"][1]["target"] == ["evt_napolitan", "evt_darjeeling_tea", "evt_strawberry_cake"])
    check("all desc", all(q["desc"] for q in ev["quests"]))
    check("all events valid", all(events.validate_quests(e) == [] for e in events.load_events().values()))
    bad = {"quests": [{"id": "x", "name": "x", "desc": "x", "type": "nope", "count": 0},
                      {"id": "x", "name": "y", "desc": "y", "type": "cook_each", "target": "evt_egg"}],
           "quest_titles": [{"id": "t", "name": "t", "rarity": "XR", "min_quests": 9}]}
    check(f"validate catches {events.validate_quests(bad)}", len(events.validate_quests(bad)) >= 5)
    goal = events.quest_goal(ev["quests"][0], ev, items)
    check(f"goal text {goal}", goal == "在「🏰紅魔館廚房」採集 {p} 次")
    check("goal guest", "妖精女僕" in events.quest_goal(ev["quests"][2], ev, items))
    check("goal cook", "草莓鮮奶油蛋糕" in events.quest_goal(ev["quests"][1], ev, items))
    check("goal gacha pool", events.quest_goal(ev["quests"][6], ev, items) == "在「🔴 紅魔鄉卡池」祈願 {p} 抽")
    check("goal event pool warns", "還沒有活動限定卡池" in events.quest_goal({"type": "gacha_event_pool", "count": 5}, ev, items))

    # 稱號資料
    check("event titles in TITLES", td.TITLES[VISITOR]["name"] == "紅霧中的參拜者" and td.TITLES[RESOLVER]["rarity"] == "SSR")
    check("condition text", td.condition_text(VISITOR) == "紅霧異變完成 4 項活動任務"
          and td.condition_text(RESOLVER) == "紅霧異變完成 8 項活動任務")
    check("event group", td.title_group(VISITOR) == "event" and td.TITLE_GROUPS["event"]["name"] == "🎪 活動")
    check("not unlocked by stats", VISITOR not in td.unlocked_titles({f"evq:{EV}": 99}))
    check("every title grouped", all(td.title_group(t) for t in td.TITLES))
    check("notify type", notify_data.can_dm("event_quest_reminder"))

    # 通知系統第一輪 (只記錄)
    await ndm.collect_notices(NOW)

    # ================= 計數 (auto_start 沒有紀錄 = 「活動 id:auto」這一輪) =================
    AUTO = udm.event_run_id(EV, None)
    check("auto run id", AUTO == f"{EV}:auto")
    await udm.get_or_create_user(A)
    r = await econ.explore(A, "scarlet_kitchen", times=3, now=NOW)
    check("explore ok", r["ok"] and len(r["runs"]) == 3)
    await econ.explore(A, "village", times=1, now=NOW)
    st = stats(A, AUTO)
    check(f"explore counted {st}", st.get("explore:scarlet_kitchen") == 3 and st.get("explore:village") == 1)
    give(A, {"evt_tomato": 2, "mat_flour": 3, "mat_seasoning": 2, "evt_darjeeling": 1, "evt_strawberry": 1, "evt_egg": 1, "evt_butter": 1})
    for d, n in (("evt_napolitan", 2), ("evt_darjeeling_tea", 1), ("evt_strawberry_cake", 1)):
        check(f"cook {d}", (await econ.cook(A, d, times=n, now=NOW))["ok"])
    st = stats(A, AUTO)
    check(f"cook counted {st}", st.get("cook:evt_napolitan") == 2 and st.get("cook:evt_darjeeling_tea") == 1)
    r = await serve(A, "fairy_maid", ["evt_napolitan"], extra="evt_strawberry_cake")
    check("serve fairy ok", r["ok"] and r["reward"]["favorite_hit"])
    r = await serve(A, "familiar_bat", ["reimu_bancha"])
    check("serve bat ok", r["ok"] and not r["reward"]["favorite_hit"])
    st = stats(A, AUTO)
    check(f"serve counted {st}", st.get("serve_guest:fairy_maid") == 1 and st.get("serve_guest:familiar_bat") == 1
          and st.get("serve_event_dish") == 2 and st.get("serve_favorite") == 1)
    await udm.draw_gacha(A, f"event_{EV}", 10, 0, roll_none, now=NOW)
    await udm.draw_gacha(A, "th06", 10, 0, roll_none, now=NOW)   # 一般卡池記 gacha_pool:th06 (紅霧異變算紅魔鄉卡池)
    await udm.draw_gacha(A, "classic", 1, 0, roll_none, now=NOW)
    check("claim daily", await udm.claim_daily(A, "2026-11-14", 3, now=NOW))
    check("daily twice no", not await udm.claim_daily(A, "2026-11-14", 3, now=NOW))
    st = stats(A, AUTO)
    check(f"gacha + daily counted {st}", st.get("gacha_event_pool") == 10 and st.get("gacha_pool:th06") == 10
          and st.get("gacha_pool:classic") == 1 and st.get("daily") == 1)

    board = await qdm.get_quest_board(A, now=NOW)
    check("board one event", len(board) == 1 and board[0]["run"] == AUTO and board[0]["total"] == 8)
    qs = {q["id"]: q for q in board[0]["quests"]}
    check("progress explore", (qs["kitchen_explore"]["cur"], qs["kitchen_explore"]["need"]) == (3, 10) and not qs["kitchen_explore"]["done"])
    check("cook_each done", qs["maid_recipes"]["cur"] == 3 and qs["maid_recipes"]["done"])
    check("progress serve", qs["serve_fairy_maid"]["cur"] == 1 and qs["red_tea_time"]["cur"] == 2 and qs["perfect_service"]["cur"] == 1)
    check("progress gacha/daily", qs["mist_prayer"]["cur"] == 10 and qs["incident_survey"]["cur"] == 1)
    check("progress capped", events.quest_progress(ev["quests"][0], {"explore:scarlet_kitchen": 99}) == 10)

    # ================= 活動結束 ➔ 不計數；重開 ➔ 新的一輪重新計 =================
    await econ.admin_end_event(EV, now=NOW)
    before = rows("SELECT COUNT(*), COALESCE(SUM(value), 0) FROM event_quest_stats")[0]
    check("explore closed", (await econ.explore(A, "scarlet_kitchen", now=NOW))["reason"] == "not_found")
    give(A, {"mat_rice": 2, "mat_seasoning": 1})
    await econ.cook(A, "ran_inari", now=NOW)
    await udm.draw_gacha(A, f"event_{EV}", 10, 0, roll_none, now=NOW)
    await udm.claim_daily(A, "2026-11-15", 3, now=NOW)
    check("nothing counted after end", rows("SELECT COUNT(*), COALESCE(SUM(value), 0) FROM event_quest_stats")[0] == before)
    check("board empty after end", await qdm.get_quest_board(A, now=NOW) == [])
    check("claim after end", (await qdm.claim_quest(A, EV, "maid_recipes", now=NOW))["reason"] == "not_active")

    T1 = NOW + timedelta(minutes=1)
    await econ.admin_start_event(EV, days=14, now=T1)
    RUN1 = udm.event_run_id(EV, T1.isoformat())
    board = await qdm.get_quest_board(A, now=T1)
    check("restart new run", board[0]["run"] == RUN1 and all(q["cur"] == 0 for q in board[0]["quests"]))
    await econ.explore(A, "scarlet_kitchen", now=T1)
    check("restart counts fresh", stats(A, RUN1).get("explore:scarlet_kitchen") == 1 and stats(A, AUTO)["explore:scarlet_kitchen"] == 3)

    # ================= 領取 =================
    sql("UPDATE users SET money = 1000, level = 0, exp = 0 WHERE user_id = ?", (A,))
    check("not done", (await qdm.claim_quest(A, EV, "serve_fairy_maid", now=T1))["reason"] == "not_done")
    check("not found", (await qdm.claim_quest(A, EV, "nope", now=T1))["reason"] == "not_found")
    check("other event", (await qdm.claim_quest(A, "no_such_event", "kitchen_explore", now=T1))["reason"] == "not_active")
    set_stats(A, RUN1, explore__scarlet_kitchen=10)
    r = await qdm.claim_quest(A, EV, "kitchen_explore", now=T1)
    exp_expect = udm.calc_exp_change(0, 0, 300)
    lv = rows("SELECT level, exp FROM users WHERE user_id = ?", (A,))[0]
    check(f"claim ok {r}", r["ok"] and r["money"] == 50000 and r["exp"] == 300 and money(A) == 51000)
    check(f"exp added {lv}", lv == (exp_expect["new_level"], exp_expect["current_exp"]) and lv[0] > 0 and r["exp_result"]["leveled_up"])
    check("no title yet", r["new_titles"] == [])
    r2 = await qdm.claim_quest(A, EV, "kitchen_explore", now=T1)
    check("claim twice", r2["reason"] == "claimed" and money(A) == 51000
          and rows("SELECT level, exp FROM users WHERE user_id = ?", (A,))[0] == lv)
    # 連點 / 兩個視窗同時按：只成功一次
    set_stats(A, RUN1, daily=7)
    res = await asyncio.gather(*[qdm.claim_quest(A, EV, "incident_survey", now=T1) for _ in range(3)])
    check(f"concurrent once {[x.get('reason') for x in res]}", sum(1 for x in res if x["ok"]) == 1 and money(A) == 151000)
    check("claims rows", rows("SELECT COUNT(*) FROM event_quest_claims WHERE user_id = ? AND run = ?", (A, RUN1))[0][0] == 2)

    # ================= 永久活動稱號 =================
    set_stats(A, RUN1, serve_guest__fairy_maid=5, serve_guest__familiar_bat=5)
    check("claim 3", (await qdm.claim_quest(A, EV, "serve_fairy_maid", now=T1))["new_titles"] == [])
    r = await qdm.claim_quest(A, EV, "serve_familiar_bat", now=T1)
    check(f"4th claim earns R {r['new_titles']}", r["new_titles"] == [VISITOR] and r["claimed_all_runs"] == 4)
    state = await udm.get_title_state(A)
    check("title unlocked", VISITOR in state["unlocked"] and RESOLVER not in state["unlocked"])
    check("equip", await udm.set_equipped_title(A, VISITOR) and (await udm.get_title_state(A))["equipped"] == VISITOR)
    board = await qdm.get_quest_board(A, now=T1)
    check("board titles", [t["earned"] for t in board[0]["titles"]] == [True, False] and board[0]["claimed"] == 4)
    # 稱號私訊 (通知 loop 也把 earned_titles 算進已解鎖)
    found = [n for n in await ndm.collect_notices(T1) if n["kind"] == "title_unlocked" and n["user_id"] == A
             and n["key"].startswith("event_")]   # (其他稱號：祈願 / 財富 / 火力也剛好解鎖)
    check(f"title dm {[n['key'] for n in found]}", [n["key"] for n in found] == [VISITOR]
          and found[0]["data"]["condition"] == "紅霧異變完成 4 項活動任務")
    # 活動結束仍保留
    await econ.admin_end_event(EV, now=T1)
    state = await udm.get_title_state(A)
    check("kept after end", VISITOR in state["unlocked"] and state["equipped"] == VISITOR)
    check("claim after end", (await qdm.claim_quest(A, EV, "maid_recipes", now=T1))["reason"] == "not_active")

    # 再開一輪：同樣 4 個任務再領一次不算新的「項」，另外 4 個領完 ➔ 8 項全部 ➔ SSR
    T2 = T1 + timedelta(minutes=1)
    await econ.admin_start_event(EV, days=14, now=T2)
    RUN2 = udm.event_run_id(EV, T2.isoformat())
    set_stats(A, RUN2, explore__scarlet_kitchen=10, daily=7, serve_guest__fairy_maid=5, serve_guest__familiar_bat=5)
    for q in ("kitchen_explore", "incident_survey", "serve_fairy_maid", "serve_familiar_bat"):
        r = await qdm.claim_quest(A, EV, q, now=T2)
        check(f"run2 claim {q}", r["ok"] and r["new_titles"] == [] and r["claimed_all_runs"] == 4)
    set_stats(A, RUN2, cook__evt_napolitan=1, cook__evt_darjeeling_tea=1, cook__evt_strawberry_cake=1,
              serve_event_dish=30, serve_favorite=10, gacha_pool__th06=50)
    got = []
    for q in ("maid_recipes", "red_tea_time", "perfect_service", "mist_prayer"):
        got += (await qdm.claim_quest(A, EV, q, now=T2))["new_titles"]
    check(f"8 distinct ➔ SSR {got}", got == [RESOLVER])
    check("earned rows", sorted(r[0] for r in rows("SELECT title_id FROM earned_titles WHERE user_id = ?", (A,))) == sorted([VISITOR, RESOLVER]))
    state = await udm.get_title_state(A)
    check("both unlocked, high first", state["unlocked"].index(RESOLVER) < state["unlocked"].index(VISITOR))
    # 補發：稱號紀錄不見了 (例如之後才加的稱號 / 門檻改低) ➔ 打開 /event quest 時已達標的補進 earned_titles
    sql("DELETE FROM earned_titles WHERE user_id = ? AND title_id = ?", (A, VISITOR))
    board = await qdm.get_quest_board(A, now=T2)
    check("catch-up grant", [t["earned"] for t in board[0]["titles"]] == [True, True]
          and VISITOR in (await udm.get_title_state(A))["unlocked"])
    # 活動檔還沒全部重載、TITLES 裡沒有的稱號 id：結果文字不會壞掉
    check("unknown title text", "🎁 領到" in importlib.import_module("Cogs.load-general.event").claim_result_text(
        {"ok": True, "money": 1, "exp": 0, "quest": {"name": "x"}, "new_titles": ["event_nope_x"]}))

    # ================= /event quest 畫面 =================
    ev_mod = importlib.import_module("Cogs.load-general.event")
    qc = importlib.import_module("Cogs.load-general.Components.quest_components")
    T3 = T2 + timedelta(minutes=1)
    await econ.admin_start_event(EV, days=14, now=T3)
    RUN3 = udm.event_run_id(EV, T3.isoformat())
    await udm.get_or_create_user(B)
    set_stats(B, RUN3, explore__scarlet_kitchen=3, daily=7, serve_guest__fairy_maid=5)
    await qdm.claim_quest(B, EV, "serve_fairy_maid", now=T3)
    board = await qdm.get_quest_board(B, now=T3)
    view = ev_mod.QuestView(B, board, items)
    btns = {b.label: b for b in buttons(view)}
    labels = [b.label for b in buttons(view)]
    check(f"8 quest buttons {labels}", len(labels) == 8)
    check("claim button", labels.count("🎁 領取") == 1 and not btns["🎁 領取"].disabled
          and btns["🎁 領取"].style == discord.ButtonStyle.success)
    check("claimed button", labels.count("✅ 已領取") == 1 and btns["✅ 已領取"].disabled)
    check("not done buttons", labels.count("未完成") == 6 and all(b.disabled for b in buttons(view) if b.label == "未完成"))
    check(f"components {total(view)}", total(view) <= 40)
    t = texts(view)
    check("view texts", "紅霧異變任務" in t and "**1. 初探紅魔館廚房**" in t and "`3 / 10`" in t and "`50,000` 賽錢 + `300` EXP" in t)
    check("view footer", "已完成 `2 / 8`" in t and "已領取 `1 / 8`" in t and "紅霧中的參拜者" in t and "<t:" in t)
    check("text length", len(t) <= 4000)
    # 本人才能按
    it = FakeInteraction(C)
    check("others blocked", await view.interaction_check(it) is False and it.response.sent)
    check("owner ok", await view.interaction_check(FakeInteraction(B)) is True)
    # 按領取 ➔ 更新畫面 + 上方顯示結果
    claim_btn = next(b for b in buttons(view) if b.label == "🎁 領取")
    it = FakeInteraction(B)
    await claim_btn.callback(it)
    kind_, _, v, _, kw = it.response.sent[0]
    t = texts(v)
    check(f"after claim {t[:80]}", kind_ == "edit" and "🎁 領到 `100,000` 賽錢、`500` EXP" in t and "P 點提升" in t)
    check("after claim buttons", [b.label for b in buttons(v)].count("✅ 已領取") == 2 and "🎁 領取" not in [b.label for b in buttons(v)])
    check("result text claimed", "已經領過" in ev_mod.claim_result_text({"ok": False, "reason": "claimed"}))
    # 分頁：任務很多時每頁不超過 40 個元件
    many = dict(board[0]); many["quests"] = [dict(board[0]["quests"][0], id=f"q{i}", index=i + 1) for i in range(20)]
    many["total"] = 20
    v = ev_mod.QuestView(B, [many, board[0]], items)
    pages = ev_mod.quest_pages(v.board)
    check(f"pages {pages}", len(pages) == 4)
    worst = 0
    for p in range(len(pages)):
        v.page = p; v.build(); worst = max(worst, total(v))
    check(f"paged components {worst}", worst <= 40)
    it = FakeInteraction(B); v.page = 0; v.build()
    nxt = next(b for b in buttons(v) if b.label == "下一頁 ▶")
    await nxt.callback(it)
    check("next page", v.page == 1 and it.response.sent[0][0] == "edit")
    # 沒有活動
    v = ev_mod.QuestView(B, [], items)
    check("no event text", "目前沒有進行中的活動" in texts(v) and not buttons(v))

    # Cog：/event 是群組 (info + quest)
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.event")
    grp = bot.tree.get_command("event")
    check("event group", isinstance(grp, app_commands.Group) and sorted(c.name for c in grp.commands) == ["info", "quest"])
    cog = bot.get_cog("EventCog")
    it = FakeInteraction(B)
    await cog.quest.callback(cog, it)
    kind_, content, v, eph, kw = it.response.sent[0]
    check("quest cmd V2 ephemeral", isinstance(v, ui.LayoutView) and eph and content is None and "embed" not in kw)
    check("quest cmd text", "紅霧異變任務" in texts(v))
    it = FakeInteraction(B)
    await cog.info.callback(cog, it)
    check("info cmd", isinstance(it.response.sent[0][2], ui.LayoutView) and "活動一覽" in texts(it.response.sent[0][2]))

    # ================= 快結束提醒 =================
    await econ.admin_end_event(EV, now=T3)
    T4 = T3 + timedelta(hours=1)
    await econ.admin_start_event(EV, days=3, now=T4)   # 還有 3 天才結束 ➔ 不提醒
    RUN4 = udm.event_run_id(EV, T4.isoformat())
    await udm.get_or_create_user(C); await udm.get_or_create_user(D)
    set_stats(C, RUN4, daily=7, explore__scarlet_kitchen=10)   # 兩項完成、沒領
    set_stats(D, RUN4, daily=7)                               # 完成但領掉了 ➔ 不提醒
    await qdm.claim_quest(D, EV, "incident_survey", now=T4)
    check("not due yet", await qdm.pending_reminders(T4) == [])
    T5 = T4 + timedelta(days=2, hours=1)   # 結束前 23 小時
    pend = await qdm.pending_reminders(T5)
    check(f"pending {[(p['user_id'], p['count']) for p in pend]}", [(p["user_id"], p["count"]) for p in pend] == [(C, 2)])
    check("remind window", qdm.remind_due((T4 + timedelta(days=3)).isoformat(), T5) and not qdm.remind_due(None, T5))
    found = [n for n in await ndm.collect_notices(T5) if n["kind"] == "event_quest_reminder"]
    check(f"reminder notice {[(n['user_id'], n['key']) for n in found]}", [(n["user_id"], n["key"]) for n in found] == [(C, RUN4)])
    comps = importlib.import_module("Cogs.load-general.Components.notify_components")
    txt = comps.notice_text(found[0])
    check(f"reminder text {txt}", "活動任務快結束" in txt and "`2`" in txt and "/event quest" in txt)
    await ndm.claim(C, "event_quest_reminder", found[0]["key"], now=T5)   # 發過了
    again = [n for n in await ndm.collect_notices(T5 + timedelta(minutes=10)) if n["kind"] == "event_quest_reminder"]
    check("reminder only once", again == [])
    after = await qdm.pending_reminders(T4 + timedelta(days=3, minutes=1))
    check("no reminder after end", after == [])


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fail else 0)

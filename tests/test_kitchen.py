"""神社廚房：採集、料理、雜貨店、點餐與招待、活動 (道具清除)"""
import asyncio, os, sys, shutil, tempfile, sqlite3, json
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
from Database import User_DB_Manager as udm, Item_DB_Manager as idm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
shutil.copy(idm.DB_PATH, os.path.join(tmp, "Item.db")); idm.DB_PATH = os.path.join(tmp, "Item.db")
from Database import Economy_DB_Manager as econ, shrine_data as sd
from Database.events import load_events, game_rules

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

class Rng:
    def __init__(s, values=(), last=0.99): s.values = list(values); s.last = last
    def random(s): return s.values.pop(0) if s.values else s.last
    def choice(s, seq): return list(seq)[0]

T0 = datetime(2026, 11, 5, 4, 0, tzinfo=timezone.utc)
EV = "th06_scarlet_mist"

def sql(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); con.execute(q, args); con.commit(); con.close()

def inv(uid):
    con = sqlite3.connect(udm.DB_PATH); v = con.execute("SELECT inventory FROM users WHERE user_id=?", (uid,)).fetchone()[0]; con.close(); return json.loads(v)

def money(uid):
    con = sqlite3.connect(udm.DB_PATH); v = con.execute("SELECT money FROM users WHERE user_id=?", (uid,)).fetchone()[0]; con.close(); return v


async def main():
    await udm.init_db()
    items = await idm.get_all_items()
    # ---------------- 資料完整性 ----------------
    rules = game_rules(list(load_events().values()))
    check("15 base dishes", len(sd.RECIPES) == 15 and sorted(sd.DISH_TYPES.values()).count("food") == 5)
    check("all recipe items exist", all(d in items and all(m in items for m in r) for d, r in rules["recipes"].items()))
    check("all drops exist", all(m in items for loc in rules["locations"].values() for m in loc["drops"]))
    check("guest favorites exist", all(g["favorite"] in rules["dish_types"] for g in rules["guests"].values()))
    check("guest lines", all(set(g["lines"]) == {"high", "mid", "low"} and all(l and all("{order}" in x for x in l) for l in g["lines"].values()) for g in rules["guests"].values()))
    check("event items in db", all(i in items and items[i]["effect"].get("event") == EV for i in ["evt_strawberry", "evt_napolitan"]))
    check("shop only village", set(sd.SHOP_PRICES) <= set(sd.LOCATIONS["village"]["drops"]))
    # 雜貨店素材做成料理一定還是賺 (2 份滿心情報酬 > 素材成本)
    for d, r in sd.RECIPES.items():
        cost = sum(sd.SHOP_PRICES.get(m, 0) * k for m, k in r.items())
        check(f"profit {d}", cost < sd.COOK_YIELD * econ.SERVING_REWARD)

    # ---------------- 點餐 ----------------
    base_rules = game_rules([])
    for v in ([0.0], [0.5], [0.99]):
        o = econ.make_order(base_rules, Rng(v + [0.9] * 6))
        check(f"order size {o}", 1 <= len(o) <= 3 and len({base_rules['dish_types'][d] for d in o}) == len(o))
    o = econ.make_order(rules, Rng([0.99, 0.0, 0.0, 0.0]))   # 3 道、第一道走活動
    check(f"event order {o}", any(d in rules["event_dishes"] for d in o))
    o = econ.make_order(rules, Rng([0.99], 0.9))             # 沒抽中活動
    check("no event order", not any(d in rules["event_dishes"] for d in o) and len(o) == 3)

    # ---------------- 報酬公式 ----------------
    r = econ.calc_serve_reward(100, ["ran_inari", "reimu_bancha"], None, rules, "ran_inari")
    check("reward base", r["total"] == 4000)
    r = econ.calc_serve_reward(50, ["ran_inari"], "ran_inari", rules, "ran_inari")
    check(f"reward favorite {r}", r["favorite_hit"] and r["total"] == round(2 * 2000 * 0.25 * 1.5))
    r = econ.calc_serve_reward(100, ["evt_napolitan", "evt_darjeeling_tea"], "evt_napolitan", rules, "x")
    check(f"reward event 1.2^3 {r}", r["event_count"] == 3 and r["total"] == round(3 * 2000 * 1.2 ** 3))

    # ---------------- 採集 ----------------
    await udm.get_or_create_user(1)
    r = await econ.explore(1, "nowhere", now=T0)
    check("explore not found", r["reason"] == "not_found")
    r = await econ.explore(1, "misty_lake", times=1, now=T0, rng=Rng([0.99], 0.99))   # 5 個、沒有事件
    check(f"explore drops {r['total']}", sum(r["total"].values()) == 5 and r["stamina"]["stamina"] == 220)
    r = await econ.explore(1, "misty_lake", times=1, now=T0, rng=Rng([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]))   # 3 個 + 好事件 (琪露諾 +5 冰晶)
    check(f"cirno bonus {r['runs'][0]}", r["runs"][0]["event"]["good"] and r["total"] == {"mat_lamprey": 3, "mat_ice": 5})
    r = await econ.explore(1, "bamboo_forest", times=1, now=T0, rng=Rng([0.0, 0.0, 0.99]))   # 壞事件：迷路空手
    check("bad event empty", not r["runs"][0]["event"]["good"] and r["total"] == {})
    r = await econ.explore(1, "village", times=5, now=T0, rng=Rng(last=0.99))
    check(f"explore 5 limited by stamina {len(r['runs'])}", len(r["runs"]) == 5 and r["stamina"]["stamina"] == 80)
    r = await econ.explore(1, "village", times=5, now=T0, rng=Rng(last=0.99))
    check("explore partial", len(r["runs"]) == 4 and r["stamina"]["stamina"] == 0)
    check("no stamina", (await econ.explore(1, "village", now=T0))["reason"] == "no_stamina")
    check("event location open", (await econ.explore(2, "scarlet_kitchen", now=T0, rng=Rng(last=0.99)))["ok"])

    # ---------------- 料理 / 雜貨店 ----------------
    sql("UPDATE users SET inventory = '{}' , money = 10000 WHERE user_id = 3")
    await udm.get_or_create_user(3); sql("UPDATE users SET money = 10000 WHERE user_id = 3")
    check("cook missing", (await econ.cook(3, "ran_inari"))["missing"] == {"mat_rice": 2, "mat_seasoning": 1})
    r = await econ.shop_buy(3, "mat_rice", 4)
    check("shop", r["ok"] and r["cost"] == 2400 and money(3) == 7600)
    check("shop not sold", (await econ.shop_buy(3, "mat_ice", 1))["reason"] == "not_found")
    check("shop poor", (await econ.shop_buy(3, "mat_rice", 100))["reason"] == "not_enough")
    await econ.shop_buy(3, "mat_seasoning", 2)
    r = await econ.cook(3, "ran_inari", times=2)
    check(f"cook {r}", r["ok"] and r["made"] == 4 and inv(3).get("ran_inari") == 4 and "mat_rice" not in inv(3))

    # ---------------- 招待 ----------------
    sql("DELETE FROM shrines")
    s = (await econ.admin_set_shrine(3, guests=1, guest_mood=100, now=T0, rng=Rng(last=0.0)))["summary"]
    g = s["guests"][0]
    check(f"guest has order {g['order']}", g["order"] and g["id"] and "{order}" in g["line"])
    sql("UPDATE users SET inventory = ? WHERE user_id = 3", (json.dumps({d: 1 for d in g["order"][:-1]}),))
    r = await econ.serve_guest(3, g["id"], now=T0)
    check("serve missing", not r["ok"] and r["reason"] == "missing" and g["order"][-1] in r["missing"])
    fav = rules["guests"][g["kind"]]["favorite"]
    sql("UPDATE users SET inventory = ? WHERE user_id = 3", (json.dumps({**{d: 1 for d in g["order"]}, fav: 1}),))
    before = money(3)
    r = await econ.serve_guest(3, g["id"], extra=fav, now=T0)
    expect = econ.calc_serve_reward(100, g["order"], fav, game_rules(list(load_events().values())), fav)["total"]
    check(f"serve ok {r.get('reward')}", r["ok"] and r["reward"]["favorite_hit"] and money(3) == before + expect)
    check("guest left", r["summary"]["guests"] == [] and inv(3) == {})
    check("serve twice", (await econ.serve_guest(3, g["id"], now=T0))["reason"] == "not_found")

    # ---------------- 活動結束：清空活動道具、活動客人離開 ----------------
    sql("UPDATE users SET inventory = ? WHERE user_id = 3", (json.dumps({"evt_egg": 3, "evt_napolitan": 2, "mat_rice": 1}),))
    ov = await econ.get_events_overview(now=T0)
    check("event active", any(o["event"]["id"] == EV and o["status"] == "active" for o in ov))
    n = await econ.admin_end_event(EV, now=T0)
    check(f"end event cleared {n}", n >= 1 and inv(3) == {"mat_rice": 1})
    check("event location closed", (await econ.explore(2, "scarlet_kitchen", now=T0))["reason"] == "not_found")
    rules_now = await econ.get_rules(now=T0)
    check("no event dishes after end", not rules_now["event_dishes"] and "fairy_maid" not in rules_now["guests"])
    check("restart", await econ.admin_start_event(EV, days=14, now=T0))
    check("active again", (await econ.get_rules(now=T0))["event_dishes"])
    check("auto end after 14 days", not (await econ.get_rules(now=T0 + timedelta(days=15)))["event_dishes"])

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

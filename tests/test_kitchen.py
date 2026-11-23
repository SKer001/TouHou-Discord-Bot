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
    check("28 base dishes", len(sd.RECIPES) == 28 and list(sd.DISH_TYPES.values()).count("food") == 9 and set(sd.RECIPES) == set(sd.DISH_TYPES))
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

    # ---------------- 0.35.000：新地點 / 料理 / 體力料理 ----------------
    new_locs = {"magic_forest", "kourindou", "hakugyokurou", "old_hell_onsen"}
    check("9 locations", len(sd.LOCATIONS) == 9 and new_locs <= set(sd.LOCATIONS))
    check("every material droppable", all(any(m in loc["drops"] for loc in sd.LOCATIONS.values()) for m, *_ in sd.MATERIAL_ITEMS))
    stamina_ids = {"marisa_mushroom_soup", "yuyuko_dango", "sakuya_scone_tea", "onsen_zosui", "hell_nabe"}
    check("stamina recipes", set(sd.STAMINA_RECIPES) == stamina_ids and all(items[d]["effect"].get("stamina") for d in stamina_ids))
    check("stamina dishes not servable", not stamina_ids & set(rules["dish_types"]) and stamina_ids <= set(rules["recipes"])
          and rules["stamina_dishes"] == stamina_ids)
    new_ids = [i for i, *_ in sd.MATERIAL_ITEMS[15:]] + [i for i, *_ in sd.DISH_ITEMS[6:]] + [i for i, *_ in sd.STAMINA_DISH_ITEMS]
    check(f"new items {len(new_ids)}", len(new_ids) == 27 and all(items[i]["desc"] and items[i]["emoji"] for i in new_ids))
    check("cook yield", sd.cook_yield("hell_nabe", rules) == 1 and sd.cook_yield("ran_inari", rules) == 2)
    sql("UPDATE users SET inventory = ? WHERE user_id = 3", (json.dumps({"mat_glow_mushroom": 2, "mat_milk": 1, "mat_butter": 1}),))
    r = await econ.cook(3, "marisa_mushroom_soup")
    check(f"cook stamina dish 1 portion {r}", r["ok"] and r["made"] == 1 and inv(3) == {"marisa_mushroom_soup": 1})
    ps3 = await udm.get_player_stats(3)
    check(f"per-dish cook stats", ps3.get("cook:marisa_mushroom_soup") == 1 and ps3.get("cook:ran_inari") == 2)

    # ---------------- 🧺 快速採集：預估、總共 N 趟、先去最缺的、夠了提早停 ----------------
    base = game_rules([])
    check("per trip", abs(econ.expected_per_trip(base["locations"]["magic_forest"], "mat_glow_mushroom") - 4 / 3) < 1e-9
          and econ.expected_per_trip(base["locations"]["village"], "mat_glow_mushroom") == 0)
    check("rice best at bamboo", econ.best_location("mat_rice", base) == "bamboo_forest")   # 竹林 3 種 > 人里 5 種
    p = econ.plan_gather({"mat_glow_mushroom": 2, "mat_milk": 1, "mat_rice": 2, "evt_egg": 1}, base)
    check(f"plan {p}", [s["location"] for s in p["stops"]] == ["magic_forest", "bamboo_forest", "kourindou"]
          and [s["trips"] for s in p["stops"]] == [2, 2, 1] and p["trips"] == 5 and p["unavailable"] == {"evt_egg": 1})
    check("shop missing", econ.shop_missing({"mat_rice": 2, "mat_milk": 1}, base) == ({"mat_rice": 2}, 1200))
    soup = sd.STAMINA_RECIPES["marisa_mushroom_soup"]

    class CycleRng(Rng):   # choice 輪流拿 (讓一趟拿到不同素材)
        i = 0
        def choice(s, seq):
            seq = list(seq); s.i += 1; return seq[(s.i - 1) % len(seq)]
    await udm.get_or_create_user(5)
    r = await econ.quick_explore(5, soup, 1, now=T0, rng=Rng(last=0.99))   # 最缺 = 蘑菇 (要 2 趟) ➔ 魔法森林
    check(f"quick 1 {r['runs']}", r["ok"] and [x["location"] for x in r["runs"]] == ["magic_forest"] and r["stopped"] == "times"
          and r["missing"] == {"mat_milk": 1, "mat_butter": 1} and r["stamina"]["stamina"] == 220)
    r = await econ.quick_explore(5, soup, 10, now=T0, rng=CycleRng(last=0.99))
    check(f"quick done early {r['runs']}", r["ok"] and len(r["runs"]) == 1 and r["runs"][0]["location"] == "kourindou"
          and r["stopped"] == "done" and r["missing"] == {} and r["stamina"]["stamina"] == 200)
    check("nothing missing", (await econ.quick_explore(5, soup, 1, now=T0))["reason"] == "nothing_missing")
    check("unavailable", (await econ.quick_explore(5, {"mat_nowhere": 1}, 1, now=T0))["reason"] == "unavailable")
    sql("UPDATE users SET stamina = 30, stamina_updated_at = ? WHERE user_id = 5", (T0.isoformat(),))
    r = await econ.quick_explore(5, {"mat_hell_pepper": 10}, 5, now=T0, rng=Rng(last=0.99))   # 只拿到溫泉蛋，體力只夠 1 趟
    check(f"quick no stamina {r['stopped']}", r["ok"] and len(r["runs"]) == 1 and r["stopped"] == "no_stamina"
          and r["missing"] == {"mat_hell_pepper": 10} and r["stamina"]["stamina"] == 10)
    check("quick no stamina at start", (await econ.quick_explore(5, {"mat_hell_pepper": 10}, 1, now=T0))["reason"] == "no_stamina")
    con = sqlite3.connect(udm.DB_PATH)
    stat = con.execute("SELECT value FROM player_stats WHERE user_id = 5 AND stat = 'explore'").fetchone()
    con.close()
    check(f"quick counts explore stat {stat}", stat and stat[0] == 3)
    ps5 = await udm.get_player_stats(5)
    check(f"per-location stats", ps5.get("explore:magic_forest") == 1 and ps5.get("explore:kourindou") == 1
          and ps5.get("explore:old_hell_onsen") == 1)
    ps1 = await udm.get_player_stats(1)
    check(f"event stats {ps1.get('explore_good')} {ps1.get('explore_bad')}", ps1.get("explore_good") == 1 and ps1.get("explore_bad") == 1)
    check(f"explore per-location {ps1}", ps1.get("explore:misty_lake") == 2 and ps1.get("explore:village") == 9
          and ps1.get("explore:bamboo_forest") == 1)
    # 🏪 買齊人里素材
    await udm.get_or_create_user(6); sql("UPDATE users SET money = 10000, inventory = '{}' WHERE user_id = 6")
    scone = sd.STAMINA_RECIPES["sakuya_scone_tea"]
    r = await econ.shop_buy_missing(6, scone)
    check(f"buy missing {r}", r["ok"] and r["bought"] == {"mat_flour": 2} and r["cost"] == 1400 and money(6) == 8600
          and set(r["missing"]) == {"mat_butter", "mat_milk", "mat_tea_leaf"})
    check("nothing to buy", (await econ.shop_buy_missing(6, scone))["reason"] == "nothing_to_buy")
    sql("UPDATE users SET money = 0 WHERE user_id = 6")
    check("buy poor", (await econ.shop_buy_missing(6, {"mat_rice": 1}))["reason"] == "not_enough" and inv(6) == {"mat_flour": 2})

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
    ps = await udm.get_player_stats(3)
    check(f"per-guest stats {g['kind']}", ps.get(f"serve_guest:{g['kind']}") == 1 and ps.get(f"serve_fav:{g['kind']}") == 1)
    check("serve twice", (await econ.serve_guest(3, g["id"], now=T0))["reason"] == "not_found")

    # ---------------- 🖥️ 畫面連動：招待缺菜 ➔ 料理 ➔ 快速採集 ➔ 回去料理 ➔ 做完回去招待 ----------------
    import importlib, types, discord
    ShrineView = importlib.import_module("Cogs.load-general.shrine").ShrineView

    class Resp:
        def __init__(s, it): s.it = it; s.done = False
        def is_done(s): return s.done
        async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
        async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
        async def send_modal(s, m): s.done = True; s.it.modal = m
    class Followup:
        def __init__(s, it): s.it = it
        async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view")
    class It:
        def __init__(s, uid=8, data=None):
            s.user = types.SimpleNamespace(id=uid, display_name="t"); s.data = data or {}
            s.response, s.followup, s.view, s.modal = Resp(s), Followup(s), None, None
    def btns(v): return {b.label: b for b in v.walk_children() if isinstance(b, discord.ui.Button)}
    def btn(v, prefix): return next((b for label, b in btns(v).items() if label.startswith(prefix)), None)
    def vtext(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))

    await udm.get_or_create_user(8)
    shrine = await econ.admin_set_shrine(8, guests=1, guest_mood=100, rng=Rng(last=0.99))   # 點 3 道
    g = shrine["summary"]["guests"][0]
    sql("UPDATE users SET inventory = '{}', stamina = 240 WHERE user_id = 8")
    user8 = types.SimpleNamespace(id=8, display_name="t")
    view = await ShrineView.create(user8, shrine, mode="serve")
    view.guest_id, view.mode = g["id"], "serve"; view.build()
    go = btn(view, "🍳 去做")
    check(f"serve to cook button {list(btns(view))}", len(g["order"]) == 3 and go is not None and btns(view)["🍵 端上桌"].disabled)
    await go.callback(It())
    check(f"cook preselected {view.cook_sel}", view.mode == "cook" and view.cook_sel == g["order"][0]
          and view.serve_queue == list(g["order"]) and "客人還在等" in vtext(view))
    check("cook has gather + back", btn(view, "🧺 快速採集") and btn(view, "🍵 回去招待"))
    await btn(view, "🧺 快速採集").callback(It())
    check(f"gather screen", view.mode == "gather" and "📐 **預估**" in vtext(view) and "合計約" in vtext(view)
          and all(btn(view, f"🧺 {n} 趟") for n in (1, 3, 5, 10)) and btn(view, "⚡ 恢復體力"))
    await btn(view, "🧺 1 趟").callback(It())
    check("gather result", "剛剛採了 1 趟" in vtext(view) and view.stamina["stamina"] == 220)
    # ⚡ 恢復體力按鈕開彈窗 (有道具時)
    sql("UPDATE users SET inventory = ? WHERE user_id = 8", (json.dumps({"reimu_onigiri": 1}),))
    it = It(); await btn(view, "⚡ 恢復體力").callback(it)
    check("stamina modal from shrine", it.modal is not None)
    it.modal.item_select._values, it.modal.qty_select._values = ["reimu_onigiri"], ["1"]
    it2 = It(); await it.modal.on_submit(it2)
    check("back to gather after eating", it2.view is view and view.mode == "gather" and "`220` ➔ `280`" in vtext(view))
    # 素材給齊 ➔ 回去料理 ➔ 一道一道做 ➔ 都齊了回去招待
    need = {}
    for d in g["order"]:
        for m, k in rules["recipes"][d].items():
            need[m] = need.get(m, 0) + k
    sql("UPDATE users SET inventory = ? WHERE user_id = 8", (json.dumps(need),))
    await btn(view, "🍳 回去料理").callback(It())
    for i, d in enumerate(g["order"]):
        check(f"cooking {d}", view.cook_sel == d)
        await btns(view)["🍳 做 1 鍋"].callback(It())
        if i < len(g["order"]) - 1:
            check("next dish", "接著做" in vtext(view))
    check(f"all ready {vtext(view)[:80]}", "客人點的菜都齊了" in vtext(view) and not view.serve_queue)
    await btn(view, "🍵 回去招待").callback(It())
    check("back to serve", view.mode == "serve" and not btns(view)["🍵 端上桌"].disabled and btn(view, "🍳 去做") is None)
    await btns(view)["🍵 端上桌"].callback(It())
    check("served", view.mode == "main" and view.serve_return is None)
    # 料理分類選單：先選分類再選料理 (每個選單 ≤ 25)
    await view.on_cook_open(It())
    await view.on_pick_cook_cat(It(data={"values": ["stamina"]}))
    selects = [s for s in view.walk_children() if isinstance(s, discord.ui.Select)]
    check(f"cook category select {[len(s.options) for s in selects]}", len(selects) == 2 and len(selects[0].options) == 4
          and {o.value for o in selects[1].options} == stamina_ids)
    check("all selects <= 25", all(len(s.options) <= 25 for s in selects))

    # 🎁 額外招待 (0.36.001)：先選分類再選料理；原本全放一個選單，超過 24 道後面的選不到
    shrine_mod = sys.modules["Cogs.load-general.shrine"]
    shrine = await econ.admin_set_shrine(8, guests=1, guest_mood=100, rng=Rng(last=0.99))
    g = shrine["summary"]["guests"][0]
    view = await ShrineView.create(user8, shrine, mode="serve")
    sql("UPDATE users SET inventory = ? WHERE user_id = 8", (json.dumps({d: 3 for d in view.rules["dish_types"]}),))
    await view.on_pick_guest(It(data={"values": [g["id"]]}))
    def sels(v): return [s for s in v.walk_children() if isinstance(s, discord.ui.Select)]
    def by_type(t): return {d for d, x in view.rules["dish_types"].items() if x == t}
    check(f"extra all dishes > 24 {len(view.rules['dish_types'])}", len(view.rules["dish_types"]) > 24)
    s = sels(view)
    check(f"extra category select {[o.value for o in s[0].options]}", len(s) == 1
          and [o.value for o in s[0].options] == ["__none__", "food", "drink", "dessert"] and s[0].options[0].default)
    await view.on_pick_extra_cat(It(data={"values": ["drink"]}))
    s = sels(view)
    check("extra dish select", len(s) == 2 and {o.value for o in s[1].options} == by_type("drink")
          and view.extra is None and next(o for o in s[0].options if o.value == "drink").default)
    pick = sorted(by_type("drink"))[-1]   # 原本排在第 24 道之後選不到的那種
    await view.on_pick_extra(It(data={"values": [pick]}))
    s = sels(view)
    check("extra picked", view.extra == pick and next(o for o in s[1].options if o.value == pick).default
          and f"🎁 **額外招待**：{items[pick]['emoji']}{items[pick]['name']} 1 份" in vtext(view))
    await view.on_pick_extra_cat(It(data={"values": ["food"]}))
    check("extra switch category clears dish", view.extra is None and view.extra_cat == "food"
          and {o.value for o in sels(view)[1].options} == by_type("food"))
    await view.on_pick_extra_cat(It(data={"values": ["__none__"]}))
    check("extra none", view.extra is None and view.extra_cat is None and len(sels(view)) == 1)
    # 一個分類超過一頁 ➔ 翻頁 (現在一類最多 11 道，把一頁改小來測)
    old_per = shrine_mod.EXTRA_PER_PAGE; shrine_mod.EXTRA_PER_PAGE = 4
    await view.on_pick_extra_cat(It(data={"values": ["dessert"]}))
    pages = -(-len(by_type("dessert")) // 4)
    check("extra paged", len(sels(view)[1].options) == 4 and btn(view, "📄 1 / ") is not None)
    await view.set_extra_page(It(), pages)
    seen = {o.value for o in sels(view)[1].options}
    check("extra last page", view.extra_page == pages and seen and seen <= by_type("dessert")
          and len(seen) == len(by_type("dessert")) - 4 * (pages - 1))
    shrine_mod.EXTRA_PER_PAGE = old_per
    check(f"serve components {sum(1 for _ in view.walk_children())}", sum(1 for _ in view.walk_children()) <= 40
          and all(len(x.options) <= 25 for x in sels(view)))
    await btns(view)["🍵 端上桌"].callback(It())
    check("served without extra", view.mode == "main" and view.extra is None and view.extra_cat is None)

    # ⏳ 神社畫面逾時 (2026-11-23)：按鈕 / 選單反灰 + 提示；先用最近一次互動改，失敗再用第一次送出的訊息
    class Edits:
        def __init__(s, fail=False): s.views, s.fail = [], fail
        async def edit_original_response(s, view=None, **kw):
            if s.fail: raise discord.HTTPException(types.SimpleNamespace(status=404, reason="x"), "expired")
            s.views.append(view)
        async def edit(s, view=None, **kw): s.views.append(view)
    last = Edits()
    view.last = last
    await view.on_timeout()
    comps = [c for c in view.walk_children() if isinstance(c, (discord.ui.Button, discord.ui.Select))]
    check("shrine timeout disables", last.views == [view] and comps and all(c.disabled for c in comps)
          and shrine_mod.TIMEOUT_TEXT in vtext(view) and sum(1 for _ in view.walk_children()) <= 40)
    view2 = await ShrineView.create(user8, await econ.get_shrine(8))
    view2.last, view2.message = Edits(fail=True), Edits()
    await view2.on_timeout()
    check("shrine timeout fallback to message", view2.message.views == [view2] and view2.last.views == [])
    check("shrine view timeout", view2.timeout == shrine_mod.VIEW_TIMEOUT)

    # 🧺 神社倉庫的素材分類 (0.36.001：原本只在「全部道具」裡、分類數量也不算)
    gen = importlib.import_module("Cogs.load-general.Components.general_components")
    data = gen.get_inventory_view_data({"mat_rice": 2, "mat_flour": 1, "reimu_onigiri": 1}, items, "material", 1)
    check("storage material category", "material" in [v for v, *_ in shrine_mod.CATEGORY_OPTIONS]
          and data["kinds"] == 2 and data["category_counts"]["material"] == 2 and data["category_counts"]["all"] == 3
          and all(v in data["category_counts"] for v, *_ in shrine_mod.CATEGORY_OPTIONS))

    # 畫面上的數字照常數寫 (0.36.001：原本寫死)
    sc = importlib.import_module("Cogs.load-general.Components.shrine_components")
    s0 = shrine["summary"]
    lo, hi = econ.YOUKAI_REWARD
    check("youkai reward text", s0["youkai_reward"] == econ.YOUKAI_REWARD
          and f"+{lo:,}～{hi:,} 賽錢" in sc.build_shrine_container("t", dict(s0, youkai=1)).children[0].content)
    t = "\n".join(i.content for i in sc.build_shrine_container("t", dict(s0, guests=[])).walk_children()
                  if isinstance(i, discord.ui.TextDisplay))
    check("guest hours text", f"每 {econ.GUEST_EVERY_HOURS} 小時有機會來一位" in t)
    t = sc.build_explore_container(rules["locations"], {"stamina": 100, "max": 240}, 20, None, items).children[0].content
    check("explore drops text", f"帶回 {sd.EXPLORE_DROPS[0]}～{sd.EXPLORE_DROPS[1]} 個" in t)
    cook = shrine_mod.ShrineCog.cook   # GroupCog 的子指令 (app_commands.Command)
    check(f"cook description {cook.description}", f"一鍋 {sd.COOK_YIELD} 份" in cook.description
          and f"體力料理一鍋 {sd.STAMINA_COOK_YIELD} 份" in cook.description and len(cook.description) <= 100)
    # 🎪 /event info 的倍率：每個預留位都有名字 (2026-11-23 補祈願價格、市場買家手續費、轉帳手續費)
    from Database import events as ev_mod
    check("modifier names cover keys", set(sc.MODIFIER_NAMES) == set(ev_mod.MODIFIER_KEYS))
    fake = {"id": "x", "emoji": "🎪", "name": "測試活動", "modifiers": {"gacha_cost": 0.9, "market_fee": 0.5, "transfer_fee": 2}}
    t = "\n".join(i.content for i in sc.build_event_container([{"event": fake, "status": "active"}], items, {}).walk_children()
                  if isinstance(i, discord.ui.TextDisplay))
    check(f"event info fee modifiers", "祈願價格 ×0.9" in t and "市場買家手續費 ×0.5" in t and "轉帳手續費 ×2" in t)
    mc = importlib.import_module("Cogs.load-market.Components.market_components")
    t = mc.build_price_container({"emoji": "❄️", "name": "琪露諾", "key": "cirno"}, [], None).children[0].content
    check("market price header", f"最多漲 {econ.PRICE_IDLE_RISE:.0%}、最多跌 {econ.PRICE_DAILY_LIMIT:.0%}" in t and "±" not in t)

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

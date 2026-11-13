"""活動預留位 (一般池 + 活動池)：events.game_rules 合併、點餐 / 客人 / 採集 / 雜貨店 / 倍率 / 台詞 (純計算，不碰資料庫)"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
from Database import User_DB_Manager as udm
import tempfile
udm.DB_PATH = os.path.join(tempfile.mkdtemp(), "Users.db")
from Database import Economy_DB_Manager as econ, shrine_data as sd
from Database.events import game_rules, load_events, pick_line

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

class Rng:
    def __init__(s, values=(), last=0.99): s.values = list(values); s.last = last
    def random(s): return s.values.pop(0) if s.values else s.last
    def choice(s, seq): return list(seq)[0]

# 沒有活動：一般池，倍率都是 1
base = game_rules([])
check("no event pool", all(not p["event"] for p in base["order_pool"].values()))
check("base pool = all dishes", sum(len(p["base"]) for p in base["order_pool"].values()) == len(sd.RECIPES))
check("mods neutral", set(base["modifiers"].values()) == {1.0})
check("shop base", base["shop"] == sd.SHOP_PRICES)
check("guest pool base", base["guest_pool"]["base"] == sorted(sd.GUESTS) and not base["guest_pool"]["event"])
check("special base", base["special_chance"] == sd.SPECIAL_CHANCE)
check("explore cost", econ.explore_cost(base) == sd.EXPLORE_STAMINA)
check("events as lists", all(isinstance(l["good"], list) and isinstance(l["bad"], list) for l in base["locations"].values()))

# 紅霧異變：活動料理自動進活動點餐池
th06 = game_rules([load_events()["th06_scarlet_mist"]])
check("th06 event pool", th06["order_pool"]["food"]["event"] == ["evt_napolitan"]
      and "evt_napolitan" not in th06["order_pool"]["food"]["base"])
check("th06 guest pool", th06["guest_pool"]["event"] == ["fairy_maid", "familiar_bat"])
check("th06 guest chance unset", th06["event_guest_chance"] is None)
check("th06 mods neutral", set(th06["modifiers"].values()) == {1.0})

# 假活動：每個預留位都用一次
fake = {
    "id": "test", "items": [{"id": "evt_x", "category": "cuisine", "effect": {"serve": "drink"}}],
    "recipes": {"evt_x": {"mat_ice": 1}},
    "extra_drops": {"misty_lake": ["evt_frog", "mat_ice"]},
    "explore_events": {"village": {"good": {"text": "活動好事", "effect": {"add": {"mat_rice": 9}}}}},
    "guests": {"evt_guest": {"name": "活動客", "emoji": "🎃", "favorite": "evt_x", "hint": "", "lines": {"high": "要{order}"}}},
    "event_guest_chance": 0.3,
    "guest_overrides": {"kappa": {"favorite": "evt_x", "lines": {"high": ["紅霧好可怕，來份{order}"]}}},
    "shop": {"evt_frog": 1234},
    "modifiers": {"shrine_income": 1.5, "youkai_reward": 2, "serve_reward": 1.1, "explore_stamina": 0.5, "nope": 9},
    "special_chance": 0.2,
}
r = game_rules([fake])
check("extra drops no dup", r["locations"]["misty_lake"]["drops"] == sd.LOCATIONS["misty_lake"]["drops"] + ["evt_frog"])
check("base data untouched", "evt_frog" not in sd.LOCATIONS["misty_lake"]["drops"])
check("explore events pool", len(r["locations"]["village"]["good"]) == 2 and len(r["locations"]["village"]["bad"]) == 1)
check("override favorite", r["guests"]["kappa"]["favorite"] == "evt_x" and sd.GUESTS["kappa"]["favorite"] != "evt_x")
check("override lines added", len(r["guests"]["kappa"]["lines"]["high"]) == 2 and len(r["guests"]["kappa"]["lines"]["mid"]) == 1)
check("shop event item", r["shop"]["evt_frog"] == 1234 and r["shop"]["mat_rice"] == sd.SHOP_PRICES["mat_rice"])
check("mods", {k: v for k, v in r["modifiers"].items() if v != 1} == {"shrine_income": 1.5, "youkai_reward": 2, "serve_reward": 1.1, "explore_stamina": 0.5})
check("explore cost halved", econ.explore_cost(r) == 10)
check("special max", r["special_chance"] == 0.2)
check("two events multiply", game_rules([fake, fake])["modifiers"]["youkai_reward"] == 4)

# 客人池：有設 event_guest_chance 才分兩池抽
check("guest event pool hit", econ.pick_guest_kind(r, Rng([0.1])) == "evt_guest")
check("guest base pool", econ.pick_guest_kind(r, Rng([0.9])) == sorted(sd.GUESTS)[0])
check("no chance = uniform", econ.pick_guest_kind(th06, Rng([0.0])) == sorted(th06["guests"])[0])

# 點餐池：抽中機率 0 時只會點一般料理
r0 = {**r, "order_event_chance": 0.0}
for _ in range(20):
    import random
    check("order base only", not any(d in r["event_dishes"] for d in econ.make_order(r0, random.Random(_))))
r1 = {**r, "order_event_chance": 1.0}
orders = [econ.make_order(r1, random.Random(i)) for i in range(40)]
check("order event when drink", all(("evt_x" in o) == any(r["dish_types"][d] == "drink" for d in o) for o in orders))

# 採集事件池 + 機率
loc = r["locations"]["village"]
out = econ.roll_explore(loc, Rng([0.0, 0.0, 0.0, 0.1, 0.1]), special_chance=0.2)   # 3 個、觸發、好事 ➔ 事件池第一個
check("event pool roll", out["event"] and out["event"]["good"])
check("roll old dict still works", econ.roll_explore(sd.LOCATIONS["village"], Rng(last=0.0))["event"]["good"])
check("special chance blocks", econ.roll_explore(loc, Rng([0.0, 0.1]), special_chance=0.05)["event"] is None)

# 倍率：招待報酬
rw = econ.calc_serve_reward(100, ["mat_rice"], None, r, None)
check(f"serve mod {rw}", rw["total"] == round(2000 * 1.1))
check("serve neutral", econ.calc_serve_reward(100, ["mat_rice"], None, base, None)["total"] == 2000)

# 神社收入倍率
from datetime import datetime, timedelta, timezone
T0 = datetime(2026, 11, 5, 4, 30, tzinfo=timezone.utc)
st = econ._new_shrine(T0)
never = Rng(last=0.999)
a = econ.advance_shrine(st, T0 + timedelta(minutes=20), never, base)["box"]
b = econ.advance_shrine(st, T0 + timedelta(minutes=20), never, r)["box"]
check(f"income mod {a} {b}", abs(b - a * 1.5) < 1e-6 and a > 0)
check("summary income", econ.shrine_summary(st, T0, r)["income_per_hour"] == 7500)

# 台詞池：同一位客人每次看都是同一句
g = r["guests"]["kappa"]
check("line stable", pick_line(g, "high", "abc") == pick_line(g, "high", "abc"))
check("line pool both used", {pick_line(g, "high", s) for s in "abcdefgh"} == set(g["lines"]["high"]))
check("line fallback", pick_line({"lines": {}}, "high") == "{order}")
check("line old str", pick_line(sd.GUESTS["kappa"], "mid") == sd.GUESTS["kappa"]["lines"]["mid"])

# 生成機率倍率：0 = 不會來、很大 = 一定來 (上限 100%)
spawn0 = game_rules([{"id": "z", "modifiers": {"youkai_spawn": 0, "guest_spawn": 0}}])
spawn9 = game_rules([{"id": "z", "modifiers": {"youkai_spawn": 99, "guest_spawn": 99}}])
mid = Rng(last=0.5)
a0 = econ.advance_shrine(st, T0 + timedelta(hours=4), mid, spawn0)
a9 = econ.advance_shrine(st, T0 + timedelta(hours=4), Rng(last=0.999), spawn9)
check(f"spawn 0 {a0['youkai']} {len(a0['guests'])}", a0["youkai"] == 0 and not a0["guests"])
check(f"spawn max {a9['youkai']} {len(a9['guests'])}", a9["youkai"] == 4 and len(a9["guests"]) == 2)

# 分解倍率
check("decompose mult", econ.card_value(1000, 0.5, 1.5) == 1500 and econ.card_value(1000, 0.5) == 1000)

# 抽卡：機率提升 / 階級權重
import importlib, random as _r
gacha = importlib.import_module("Cogs.load-gacha.gacha")
keys = [k for k, v in gacha.GACHA_POOL.items() if v["pool"] == "th06"]
target = keys[0]
_r.seed(1)
cards, _, _ = gacha.roll_pool_cards("th06", 200, 0, lambda: 0.5, {"gacha_rate_up": {target: 1000}})
check("rate up", sum(c["character_key"] == target for c in cards) > 180)
_r.seed(2)
cards, _, _ = gacha.roll_pool_cards("th06", 50, 0, lambda: 0.5, {"gacha_rarity_weights": [0, 0, 1]})
check("rarity weights", all(c["rarity"] == gacha.GACHA_POOL[c["character_key"]]["rarities"][-1] for c in cards))
_r.seed(3)
cards, _, _ = gacha.roll_pool_cards("th06", 50, 0, lambda: 0.5)
check("no rules ok", len(cards) == 50)
g2 = game_rules([{"id": "a", "gacha": {"rate_up": {target: 2}}}, {"id": "b", "gacha": {"rate_up": {target: 3}}, "daily_items": [["reimu_onigiri", 2]]}])
check("rate up multiply", g2["gacha_rate_up"][target] == 6 and g2["gacha_rarity_weights"] is None)
check("daily items", g2["daily_items"] == [["reimu_onigiri", 2]])

# 🎴 活動限定卡池 (2026-11-13 補的預留位)：角色可以跨一般卡池；後面的活動蓋前面
check("no event pool", base["gacha_event_pool"] is None)
mixed = ["reimu", keys[0], "no_such_char"]
g3 = game_rules([{"id": "a", "name": "測試", "gacha": {"pool": {"characters": ["marisa"]}}},
                 {"id": "b", "name": "測試二", "emoji": "🎉", "gacha": {"pool": {"characters": mixed}}}])
ep = g3["gacha_event_pool"]
check("event pool later wins", ep["key"] == "event_b" and ep["event"] == "b" and ep["characters"] == mixed)
check("event pool default name", ep["name"] == "🎉 測試二卡池" and ep["desc"] == "活動限定")
check("event pool chars filtered", gacha.pool_characters("event_b", g3) == ["reimu", keys[0]])
cards, _, _ = gacha.roll_pool_cards("event_b", 60, 0, lambda: 0.5, g3)
check("event pool rolls only listed", {c["character_key"] for c in cards} <= {"reimu", keys[0]})
check("normal pool unaffected", set(gacha.pool_characters("th06", g3)) == set(keys))
check("empty pool ignored", game_rules([{"id": "c", "gacha": {"pool": {"characters": []}}}])["gacha_event_pool"] is None)

# 💰 祈願價格、市場 / 轉帳手續費倍率 (沒活動 = 原價)
check("draw cost base", gacha.draw_cost(10) == gacha.DRAW_COST * 10)
g4 = game_rules([{"id": "d", "modifiers": {"gacha_cost": 0.8, "market_fee": 0, "transfer_fee": 2}}])
check("draw cost event", gacha.draw_cost(10, g4["modifiers"]["gacha_cost"]) == round(gacha.DRAW_COST * 8))
check("market fee base", econ.buyer_total(1000, 1.0) == 1050)
check("market fee free", econ.buyer_total(1000, g4["modifiers"]["market_fee"]) == 1000)
check("transfer fee base", econ.transfer_fee(1000, 1.0) == 50)
check("transfer fee doubled", econ.transfer_fee(1000, g4["modifiers"]["transfer_fee"]) == 100)
econ._remember_fee_mods(g4)
check("cached fee mods", econ.buyer_total(1000) == 1000 and econ.transfer_fee(1000) == 100)
econ._remember_fee_mods(base)
check("cached fee reset", econ.buyer_total(1000) == 1050 and econ.transfer_fee(1000) == 50)

print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

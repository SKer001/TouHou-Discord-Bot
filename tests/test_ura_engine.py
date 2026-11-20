"""🌀 裏世界引擎 (Database/ura/)：公式、狀態效果、戰鬥、地圖、背包、結算 (純邏輯，不碰資料庫)"""
import json, math, os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from Database.ura import combat, data, rules, status, run as R

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

class Rng(random.Random):
    """random() 照順序給 values (給完用 last)，其他照 random.Random"""
    def __init__(s, values=(), last=0.99, seed=1):
        super().__init__(seed); s.values = list(values); s.last = last
    def random(s): return s.values.pop(0) if s.values else s.last
    def uniform(s, a, b): return 1.0

chars = data.characters()
def card(cid, r, c=0.65, i=0): return ({"instance_id": f"c{i}", "character_key": cid, "rarity": r, "completeness": c}, chars[cid])
def new(team=(("marisa", "SR"), ("meiling", "SR"), ("daiyousei", "SR")), bag=None, seed="s1", rng=None):
    return R.new_run(seed, [card(c, r, i=i) for i, (c, r) in enumerate(team)], bag or {}, 0, rng or random.Random(5))

# ---------------- 資料 ----------------
check("24 characters", len(chars) == 24 and all(c["class"] in rules.CLASS_NAMES for c in chars.values()))
check("every character has a spell", set(data.spells()) == set(chars))
check("spell statuses exist", all(e.get("status") is None or e["status"] in data.statuses()
                                  for s in data.spells().values() for e in s["effects"]))
check("enemy statuses exist", all(sk.get("status") is None or sk["status"] in data.statuses()
                                  for e in data.enemies().values() for sk in e["skills"]))
check("relic statuses exist", all(r.get("passive") is None or r["passive"] in data.statuses() for r in data.relics().values()))
check("item statuses exist", all(i["effect"].get("status") is None or i["effect"]["status"] in data.statuses() for i in data.items().values()))
check("15 treasures zone 1", [len(v) for v in data.treasures(1).values()] == [4, 3, 3, 2, 2, 1])
check("15 events", len(data.events()) == 15 and sorted(e["type"] for e in data.events().values()).count("good") == 5)
check("10 relics", len(data.relics()) == 10)
check("zones", [z["name"] for z in data.zones()] == ["迷途竹林", "魔界", "妖怪之山", "冥界", "彼岸"] and data.zone_info(6)["id"] == "bamboo")
from Database import shrine_data
check("zone materials exist", all(m in [x[0] for x in shrine_data.MATERIAL_ITEMS] for m in data.zone_info(1)["materials"]))
check("char file b / cd match spells", all(
    lv["spent"] == data.spells()[cid]["b"] and lv["cooldown"] == data.spells()[cid]["cd"]
    for cid in chars for lv in json.load(open(next(p for p in __import__("glob").glob(f"Characters/*/{cid}.json")), encoding="utf-8"))["special_powers"]["levels"].values()))

# ---------------- 公式 ----------------
check("zone mult", [round(rules.zone_mult(z), 2) for z in (1, 3, 4, 5, 7, 10)] == [1.0, 1.75, 2.69, 4.0, 5.0, 6.5])
check("enemy stats z5", rules.enemy_stats(5, "normal") == (120.0, 20.0, 12.5))
check("boss stats z1", rules.enemy_stats(1, "boss") == (300.0, 8.0, 7.5))
check("reduction", [round(rules.dmg_reduction(d) * 100) for d in (5, 20, 60, 100)] == [13, 38, 57, 60])
check("comp mult", (rules.comp_mult(0.3), rules.comp_mult(1.0)) == (0.8, 1.2))
check("cooldown >0.8", (rules.spell_cooldown(3, 0.81), rules.spell_cooldown(10, 0.9), rules.spell_cooldown(1, 1.0), rules.spell_cooldown(3, 0.8)) == (2, 9, 1, 3))
check("sanity per floor", (rules.sanity_per_floor(1, False), rules.sanity_per_floor(1, True), rules.sanity_per_floor(3, False)) == (10, 7, 20))
check("flee cost", (rules.flee_cost(1, False, "normal"), rules.flee_cost(1, False, "elite"), rules.flee_cost(1, True, "normal")) == (25, 40, 18))
check("persuade", (rules.persuade_chance(10, "normal"), rules.persuade_chance(50, "elite"), rules.persuade_chance(30, "boss"), rules.persuade_chance(200, "normal"))
      == (0.9, 0.4, 0.55, 0.01))
t3 = {k: round(v * 100, 1) for k, v in rules.rarity_table("monster", 3).items()}
check(f"curve z3 {t3}", t3 == {"N": 22.4, "R": 26.7, "SR": 24.9, "SSR": 14.4, "UR": 9.2, "LR": 2.3})
t10 = {k: round(v * 100, 1) for k, v in rules.rarity_table("boss", 10).items()}
check(f"curve boss z10 {t10}", t10 == {"SSR": 33.8, "UR": 54.6, "LR": 11.6})
check("curve flattens", abs(rules.rarity_table("monster", 20)["LR"] - rules.rarity_table("monster", 30)["LR"]) < 0.005)
counts = [rules.weighted_count(1, 3, random.Random(i)) for i in range(3000)]
check(f"weighted count {[counts.count(k) for k in (1, 2, 3)]}", counts.count(1) > counts.count(2) > counts.count(3))
check("money roll 10s", all(rules.money_roll(500, 1000, random.Random(i)) % 10 == 0 and 500 <= rules.money_roll(500, 1000, random.Random(i)) <= 1000 for i in range(50)))
check("mimic money", (rules.mimic_money(1), rules.mimic_money(6), rules.mimic_money(11)) == (10000, 12500, 20000))

# ---------------- 狀態效果 ----------------
u = {"statuses": [], "base_atk": 10}
status.apply(u, "buff_atk", value=0.2)
status.apply(u, "buff_atk", value=0.2, turns=3)
check("same status no stack", len(u["statuses"]) == 1 and u["statuses"][0]["stacks"] == 1)
status.apply(u, "doll_legion", value=0.25)
check("different names add", abs(status.stat_mult(u, "atk_pct") - 1.45) < 1e-9)
status.apply(u, "relic_atk", value=0.1)
check("groups multiply", abs(status.stat_mult(u, "atk_pct") - 1.45 * 1.1) < 1e-9)
for _ in range(5):
    status.apply(u, "mima_power")
check("mima stacks max 3", status.find(u, "mima_power")["stacks"] == 3)
u2 = {"statuses": []}
status.apply(u2, "burn", turns=3); status.tick(u2, "rounds"); status.tick(u2, "rounds")
check("tick", status.find(u2, "burn")["left"] == 1)
status.apply(u2, "burn")
check("refresh", status.find(u2, "burn")["left"] == 3)
status.apply(u2, "buff_atk", value=0.2)
check("cleanse bad only", status.cleanse(u2) == 1 and status.has(u2, "buff_atk"))
boss = {"statuses": [], "ctrl_count": 0}
check("boss immune seal", not status.apply(boss, "seal", is_boss=True))
check("boss half 1 ➔ none", not status.apply(boss, "freeze", turns=1, is_boss=True, rng=Rng()))
check("boss half 2 ➔ 1", status.apply(boss, "sleep", turns=2, is_boss=True, rng=Rng([0.0])) and status.find(boss, "sleep")["left"] == 1)
check("boss resist halves", boss["ctrl_count"] == 1 and not status.apply(boss, "sleep", turns=2, is_boss=True, rng=Rng([0.6])))
check("label", status.label({"id": "burn", "left": 2, "stacks": 1}) == "🔥 燒傷 (2)")

# ---------------- 隊伍 / 數值 ----------------
run = new()
m = run["party"][0]
check(f"member stats {m['base_atk']}", abs(m["base_atk"] - 33 * 1.2 * rules.comp_mult(0.65)) < 1e-9 and m["hp"] == rules.round_half(76 * 1.2))
check("spell tier", m["tier"] == 0 and m["b_cost"] == 8 and m["cd_max"] == 3)
check("json round trip", json.loads(json.dumps(run)) == run)
check("start", run["sanity"] == 1000 and run["b"] == 25 and run["phase"] == "doors" and run["floor"] == 0)

# ---------------- 地圖 ----------------
def doors_for(floor, seed="m"):
    r = new(seed=seed)
    r["floor"] = floor - 1
    return R.gen_doors(r, floor, random.Random(floor))
check("floor 10 boss", [d["type"] for d in doors_for(10)] == ["boss"])
check("floor 9 merchant", [d["type"] for d in doors_for(9)] == ["merchant"])
check("battle floors", all({d["type"] for d in doors_for(f)} <= {"battle", "elite"} for f in (2, 4, 6, 8)))
dup_ok = True
for s in range(40):
    for f in (1, 3, 5, 7):
        ds = [d for d in doors_for(f, f"x{s}") if not d.get("hidden")]
        ts = [d["type"] for d in ds]
        nonbattle = [t for t in ts if t != "battle"]
        extra = 1 if any(d.get("guaranteed") for d in ds) else 0   # 保底寶箱：原本沒有寶箱門時多一扇
        if len(nonbattle) != len(set(nonbattle)) or not 2 <= len(ts) <= 3 + extra:
            dup_ok = False
check("odd floors 2~3 doors, no duplicate types", dup_ok)
r = new(seed="caps")
for f in range(1, 10):
    r["floor"] = f - 1
    R.gen_doors(r, f, random.Random(f * 7))
caps = r["caps"]["1"]
check(f"zone caps {caps}", all(caps.get(k, 0) <= v + 0 for k, v in rules.ROOM_CAPS.items() if k != "chest"))
plan = R._guaranteed(new(seed="g1"), 1) and new(seed="g1")
r = new(seed="g1"); R._guaranteed(r, 1)
pl = r["guaranteed"]["0"]
check(f"guaranteed 2 LR + 5 UR {pl}", sorted(pl.values()) == ["LR"] * 2 + ["UR"] * 5 and all(int(k) % 10 in (1, 3, 5, 7) for k in pl))
gf = int(next(k for k, v in pl.items() if v == "LR"))
r["floor"] = gf - 1
ds = R.gen_doors(r, gf, random.Random(3))
check("guaranteed chest door", any(d["type"] == "chest" and d.get("guaranteed") == "LR" for d in ds))
check("door view hidden without scout", R.door_view(r, {"type": "event", "event": "tea_house", "etype": "good"}, False) == {"type": "event"})
check("door view revealed", R.door_view(r, {"type": "event", "event": "tea_house", "etype": "good"}, True)["etype"] == "good")
rs = new(team=(("rumia", "SR"),))
check("scout reveals", R.doors_revealed(rs))

# ---------------- 進一關 / 常識度 ----------------
run = new()
run["doors"] = [{"type": "trap"}]
R.choose_door(run, 0, Rng([0.0]))   # 陷阱：丟道具 (沒道具 ➔ 扣血)
check("enter floor", run["floor"] == 1 and run["step"] == 1 and run["sanity"] == 990 and run["b"] == 26 and run["exp"] == 10)
check("trap hp", run["phase"] == "trap" and run["room"]["result"] == "hp" and all(m["hp"] < combat.max_hp(m) for m in run["party"]))
run = new(team=(("reimu", "SR"),))
run["doors"] = [{"type": "trap"}]
R.choose_door(run, 0, Rng())
check("guide discount", run["sanity"] == 993)
run = new(); run["sanity"] = 5; run["doors"] = [{"type": "trap"}]
R.choose_door(run, 0, Rng())
check("sanity 0 fails", run["phase"] == "ended" and run["result"] == "failed")

# ---------------- 戰鬥 ----------------
def battle(team=(("marisa", "SR"), ("meiling", "SR"), ("daiyousei", "SR")), foes=("lost_spirit",), kind="normal", floor=1, bag=None, rng=None):
    r = new(team=team, bag=bag)
    r["floor"] = floor
    combat.start(r, kind, list(foes), rng or Rng())
    return r
b = battle(foes=("lost_spirit", "lost_spirit"))
check("names A / B", [f["name"] for f in b["battle"]["foes"]] == ["迷途怨靈 A", "迷途怨靈 B"])
f0 = b["battle"]["foes"][0]
mar = b["party"][0]
expect = max(1, rules.round_half(combat.eff_atk(mar) * (1 - rules.dmg_reduction(5))))
R.battle_action(b, "attack", Rng(), uid="p0", target="e0")
check(f"attack damage {30 - f0['hp']} vs {expect}", f0["hp"] == max(0, 30 - expect) or not f0["alive"])
check("one action per round ➔ enemy phase", b["battle"]["round"] == 2 and b["b"] in (27, 28))   # 打倒一隻 +1
b = battle(foes=("bamboo_wraith",) * 3)
check("must pick target when 2+", R.battle_action(b, "attack", Rng(), uid="p0", target=None) is not None)
# 守護者比重 × 4、嘲諷
b = battle()
alive = b["party"]
picks = [combat._choose_target(b, random.Random(i))["cls"] for i in range(2000)]
w_guard = alive[1]["hp"] * 4 / (alive[0]["hp"] + alive[1]["hp"] * 4 + alive[2]["hp"])
check(f"guard weight {picks.count('guard') / 2000:.2f} ~ {w_guard:.2f}", abs(picks.count("guard") / 2000 - w_guard) < 0.04)
status.apply(alive[0], "taunt")
check("taunt", all(combat._choose_target(b, random.Random(i))["uid"] == "p0" for i in range(30)))
# 閃避
b = battle(foes=("shadow_rabbit",))
d = combat.deal(b, b["party"][0], b["battle"]["foes"][0], 1.0, Rng([0.0]), single=True)
check("dodge single", d == 0)
d = combat.deal(b, b["party"][0], b["battle"]["foes"][0], 1.0, Rng([0.0]), single=False)
check("aoe always hits", d > 0)
# 狂暴
b = battle()
foe = b["battle"]["foes"][0]
b["battle"]["round"] = 12
check("enrage +20% at round 12", abs(combat.eff_atk(foe, b["battle"]) - foe["base_atk"] * 1.2) < 1e-9)
b["battle"]["kind"] = "boss"
check("boss no enrage", combat.eff_atk(foe, b["battle"]) == foe["base_atk"])
# 符卡
b = battle(foes=("lost_spirit", "lost_spirit", "lost_spirit"))
check("not enough b", combat.cast(b, "p0", "e0", Rng()) is None)   # 25 B 夠
check("cd set", b["party"][0]["cd"] >= 2 and b["b"] < 25 + 2)
b = battle(team=(("sakuya", "UR"), ("marisa", "SR"), ("meiling", "SR")), foes=("bamboo_wraith",) * 3)
b["b"] = 50
R.battle_action(b, "spell", Rng(), uid="p0")
check("time stop extra actions", b["battle"]["actions_left"] == 2 and b["battle"]["time_stop"] == 1.2 and b["battle"]["round"] == 1)
R.battle_action(b, "attack", Rng(), uid="p1", target="e0")
check("still round 1", b["battle"]["round"] == 1 and b["battle"]["actions_left"] == 1)
check("acted can't act again", R.battle_action(b, "attack", Rng(), uid="p1", target="e1") is not None)
R.battle_action(b, "attack", Rng(), uid="p2", target="e1")
check("round 2 after all acted", b["battle"]["round"] == 2 or b["phase"] != "battle")
b = battle(team=(("mima", "SR"),), foes=("ura_mokou", "bamboo_wraith"), kind="boss")
b["b"] = 50
R.battle_action(b, "spell", Rng(), uid="p0")
check("mima self buff", status.has(b["party"][0], "mima_power"))
b = battle(team=(("cirno", "SR"),), foes=("mad_rabbit", "bamboo_wraith"), kind="elite")
R.battle_action(b, "spell", Rng([0.0, 0.0, 0.99], 0.99), uid="p0")
check("cirno freeze 30%", [status.has(f, "freeze") or not f["alive"] for f in b["battle"]["foes"]].count(True) >= 1)
b = battle(team=(("daiyousei", "SR"), ("marisa", "SR")))
b["party"][1]["hp"] = 10
R.battle_action(b, "spell", Rng(), uid="p0", target="p1")
check("heal ally", b["party"][1]["hp"] > 10)
b = battle(team=(("remilia", "SSR"),), foes=("ura_mokou",), kind="boss", floor=10)
b["party"][0]["hp"] = 20
R.battle_action(b, "spell", Rng(), uid="p0", target="e0")
check("remilia drain", b["party"][0]["hp"] > 20 or not b["party"][0]["alive"])
check("boss can't flee", R.battle_action(b, "flee", Rng()) is not None)
# 逃跑、糰子
b = battle(foes=("lost_spirit", "lost_spirit"))
combat.deal(b, b["party"][0], b["battle"]["foes"][0], 100, Rng())
s0 = b["sanity"]
R.battle_action(b, "flee", Rng())
check("flee cost + keep killed loot", b["sanity"] == s0 - 25 and b["phase"] == "doors" and b["pocket"] > 0)
b = battle(foes=("lost_spirit",), bag={"dango": 2}, floor=10)
R.battle_action(b, "item", Rng([0.0]), item="dango", target=None)
check("persuade success ➔ win + loot", b["phase"] == "doors" and b["kills"].get("lost_spirit") == 1 and b["pocket"] >= 500)
b = battle(foes=("ura_mokou",), kind="boss", bag={"dango": 2}, floor=10)
R.battle_action(b, "item", Rng([0.0]), item="dango")
check("boss breach", status.has(b["battle"]["foes"][0], "breach"))
check("one try per foe", R.battle_action(b, "item", Rng([0.0]), item="dango") is not None)
foe = b["battle"]["foes"][0]
check("breach def floor", combat.eff_def(foe) == math.floor(foe["base_def"] * 0.9))
# 替身人形 / 復活
b = battle(team=(("marisa", "SR"),), bag={"substitute_doll": 1, "phoenix_feather": 1})
combat.deal(b, b["battle"]["foes"][0], b["party"][0], 999, Rng())
check("substitute doll", b["party"][0]["alive"] and b["party"][0]["hp"] == 1 and "substitute_doll" not in b["bag"]["items"])
# BOSS 第二階段 + 嘲諷改打守護者
b = battle(foes=("ura_mokou",), kind="boss", floor=10)
boss = b["battle"]["foes"][0]
boss["hp"] = combat.max_hp(boss) // 2 + 1
combat.deal(b, b["party"][0], boss, 0.5, Rng())
check("phase 2", boss["phase2"] and abs(combat.eff_atk(boss, b["battle"]) - boss["base_atk"] * 1.3) < 1e-9)
status.apply(b["party"][1], "taunt")
hp0 = [m["hp"] for m in b["party"]]
combat._foe_act(b, boss, Rng()) if False else None
sk = next(s for s in boss["skills"] if s["id"] == "phoenix")
boss["cds"] = {}
orig = combat._pick_skill
combat._pick_skill = lambda run, foe, rng: sk
combat._foe_act(b, boss, Rng())
combat._pick_skill = orig
check("phoenix redirect to taunt", b["party"][0]["hp"] == hp0[0] and b["party"][2]["hp"] == hp0[2] and b["party"][1]["hp"] < hp0[1])

# ---------------- 背包 ----------------
run = new(bag={"bamboo_herb": 5})
check("heal cat max", R.can_add(run, "items", "village_onigiri") is not None)
check("item max", R.item_limit_reason({"phoenix_feather": 1}, "phoenix_feather") is not None)
run = new(bag={"dango": 5})
check("stack slots", R.slots_used(run["bag"]) == 1)
run["bag"]["items"]["dango"] = 6
check("stack overflow slot", R.slots_used(run["bag"]) == 2)
run["bag"]["materials"] = {"mat_rice": 21}
check("material 20 per slot", R.slots_used(run["bag"]) == 4)
run["capacity"] = 4
R.stash(run, {"treasures": [{"id": "ura_pebble", "rarity": "N", "zone": 1}]})
check("full ➔ pending", len(run["pending"]) == 1 and not run["bag"]["treasures"])
R.discard(run, "materials", "mat_rice", 21)
check("take pending", R.take_pending(run, 0) is None and len(run["bag"]["treasures"]) == 1)

# ---------------- 寶箱 / 事件 / 商人 ----------------
run = new(bag={"chest_key": 1})
run["doors"] = [{"type": "chest", "locked": True, "mimic": False}]
R.choose_door(run, 0, Rng())
check("chest phase", run["phase"] == "chest")
check("open locked with key", R.open_chest(run, random.Random(1)) is None
      and run["bag"]["items"].get("chest_key", 0) == run["room"]["loot"]["items"].get("chest_key", 0)   # 原本那把用掉了 (寶箱也可能掉鑰匙)
      and run["pocket"] >= 3000 and 2 <= len(run["bag"]["treasures"]) <= 5)
check("chest treasures SR+", all(t["rarity"] in ("SR", "SSR", "UR", "LR") for t in run["bag"]["treasures"]))
run = new()
run["doors"] = [{"type": "chest", "locked": True, "mimic": False}]
R.choose_door(run, 0, Rng())
check("locked no key", R.open_chest(run, Rng()) is not None and R.leave_room(run, Rng()) is None and run["phase"] == "doors")
run = new()
run["doors"] = [{"type": "chest", "locked": False, "mimic": True, "foes": ["mad_rabbit"]}]
R.choose_door(run, 0, Rng())
R.open_chest(run, Rng())
check("mimic ➔ battle", run["phase"] == "battle" and run["battle"]["kind"] == "mimic")
run = new()
run["doors"] = [{"type": "event", "event": "dense_fog", "etype": "bad"}]
status.apply(run["team"], "clover")
R.choose_door(run, 0, random.Random(2))
check("clover ➔ good event", data.events()[run["room"]["event"]]["type"] == "good" and not status.has(run["team"], "clover"))
run = new()
run["doors"] = [{"type": "event", "event": "tengu_gamble", "etype": "special"}]
R.choose_door(run, 0, Rng())
check("gamble needs money", R.event_choice(run, True, Rng()) is not None)
run["pocket"] = 5000
R.event_choice(run, True, Rng([0.0]))
check("gamble win x3", run["pocket"] == 5000 - 1000 + 3000)
run = new()
run["floor"] = 8
run["doors"] = [{"type": "merchant"}]
R.choose_door(run, 0, random.Random(4))
stock = run["room"]["stock"]
check("merchant stock", run["phase"] == "merchant" and len([s for s in stock if s["kind"] == "item"]) == 4
      and all(s["id"] not in ("return_talisman", "phoenix_feather", "substitute_doll") for s in stock if s["kind"] == "item"))
check("merchant price x1.2", all(s["price"] == rules.round_half(data.items()[s["id"]]["price"] * 1.2) for s in stock if s["kind"] == "item"))
check("buy needs money", R.buy(run, 0) is not None)
run["pocket"] = 10 ** 6
check("buy", R.buy(run, 0) is None and run["pocket"] < 10 ** 6)

# ---------------- 道具 ----------------
run = new(bag={"bunbunmaru": 1, "reroll_dice": 1, "sukima": 1, "return_talisman": 1})
R.use_item(run, "bunbunmaru", None, Rng())
check("sanity item", run["sanity"] == 1300)
old = run["doors"]
R.use_item(run, "reroll_dice", None, random.Random(99))
check("reroll", "reroll_dice" not in run["bag"]["items"])
R.use_item(run, "sukima", None, random.Random(3))
check("sukima skip floor", run["floor"] == 1 and run["phase"] == "doors" and run["sanity"] == 1290)
R.use_item(run, "return_talisman", None, Rng())
check("return talisman", run["phase"] == "ended" and run["result"] == "evacuated")

# ---------------- 法具 ----------------
run = new(team=(("marisa", "SR"), ("meiling", "SR")))
run["bag"]["relics"] = [{"rid": "war_blessing", "tier": 0}, {"rid": "seal_ofuda", "tier": 0, "left": 2}]
atk0 = combat.eff_atk(run["party"][0])
R.equip_relic(run, 0, "p0")
check("war blessing + attacker bonus", abs(combat.eff_atk(run["party"][0]) - atk0 * 1.15) < 1e-9)
R.equip_relic(run, 0, "p0")
check("swap back to bag", run["bag"]["relics"][0]["rid"] == "war_blessing" and abs(combat.eff_atk(run["party"][0]) - atk0) < 1e-9)
run["bag"]["relics"].append({"rid": "life_blessing", "tier": 2})
hp0 = run["party"][1]["hp"]
R.equip_relic(run, 1, "p1")
check("life blessing hp up", run["party"][1]["hp"] > hp0)

# ---------------- 結算 ----------------
run = new()
run["exp"], run["pocket"] = 101, 5000
run["bag"]["treasures"] = [{"id": "ura_pebble", "rarity": "N", "zone": 1}]
run["party"][2]["alive"] = False
R._end(run, "evacuated", "")
s = R.settle(run)
check("evacuate settle", s["money"] == 5000 and s["exp"] == 101 and s["penalty"] == ["c2"] and len(s["treasures"]) == 1 and s["deepest"] == 0)
run["result"] = "failed"
s = R.settle(run)
check("fail settle", s["money"] == 0 and s["exp"] == 50 and s["penalty"] == ["c0", "c1", "c2"] and not s["treasures"] and s["deepest"] is None)

# ---------------- 決定性：同一個進度 + 同一個動作 = 同一個結果 ----------------
a = new(seed="det"); b2 = json.loads(json.dumps(a))
R.choose_door(a, 0, R.action_rng(a)); R.choose_door(b2, 0, R.action_rng(b2))
check("deterministic", a == b2)

# ---------------- 整局跑一次 (自動玩家) ----------------
import importlib.util
spec = importlib.util.spec_from_file_location("ura_sim", os.path.join(ROOT, "tools", "ura_sim", "spells.py"))
sim = importlib.util.module_from_spec(spec); spec.loader.exec_module(sim)
res = [sim.play([("flandre", "UR", 0.9), ("yumeko", "SSR", 0.9), ("daiyousei", "SR", 0.9)], dict(sim.BAGS["重裝"]), random.Random(i), 3) for i in range(5)]
check(f"full runs {[r['floor'] for r in res]}", all(r["floor"] >= 10 for r in res) and all(json.loads(json.dumps(r)) == r for r in res))

print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

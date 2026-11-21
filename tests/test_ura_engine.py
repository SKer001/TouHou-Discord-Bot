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
base_events = {k: e for k, e in data.events().items() if not e.get("fest")}
check("15 events", len(base_events) == 15 and sorted(e["type"] for e in base_events.values()).count("good") == 5)
check("10 relics", len(data.base_relics()) == 10)
# 🎪 紅霧異變的裏世界內容 (活動檔 "ura") 併進來，帶 fest 標記
F = "th06_scarlet_mist"
check("fest loaded", F in data.fests() and data.fests()[F]["boss"] == "scarlet_flandre")
check("fest events tagged", sorted(k for k, e in data.events().items() if e.get("fest") == F) == ["fest_imp_deal", "fest_maid_tea", "fest_thick_mist"])
check("fest relics tagged", sorted(k for k, r in data.relics().items() if r.get("fest") == F) == ["fest_maid_watch", "fest_vampire_pact"])
check("fest treasures SSR+", set(data.fest_treasures(F)) == {"SSR", "UR", "LR"} and data.treasure_info("fest_gungnir_shard")["zone_key"] == f"fest:{F}")
check("fest statuses / enemies", {"fest_scarlet_mist", "fest_quad", "fest_vampire"} <= set(data.statuses())
      and {"scarlet_fairy", "vampire_bat", "rogue_grimoire", "fairy_maid_chief", "scarlet_flandre"} <= set(data.enemies()))
bad_refs = [s["status"] for e in data.enemies().values() for s in e.get("skills", []) if s.get("status") and s["status"] not in data.statuses()]
check(f"enemy skill statuses exist {bad_refs}", not bad_refs)
check("zones", [z["name"] for z in data.zones()] == ["迷途竹林", "魔界", "妖怪之山", "冥界", "彼岸"] and data.zone_info(6)["id"] == "bamboo")
from Database import shrine_data
check("zone materials exist", all(m in [x[0] for x in shrine_data.MATERIAL_ITEMS] for m in data.zone_info(1)["materials"]))
# 🌌 魔界 (2026-11-21)：自己的名單，不再借竹林
mk = data.zone_by_id("makai")
check("makai own roster", not mk["borrowed"] and mk["treasure_zone"] == "makai" and mk["boss"] == "ura_shinki"
      and mk["normals"] == ["makai_wanderer", "floating_eye", "makai_statue"] and mk["elite"] == "greater_demon")
check("makai materials", mk["materials"] == ["mat_wild_berry", "mat_butter", "mat_milk", "mat_coffee_bean", "mat_ice"])
check("makai 15 treasures", [len(v) for v in data.theme_treasures(mk).values()] == [4, 3, 3, 2, 2, 1])
mats = [x[0] for x in shrine_data.MATERIAL_ITEMS]
real = [z for z in data.zones() if not z["borrowed"]]
check("real zones: enemies / materials exist", all(e in data.enemies() for z in real for e in z["normals"] + [z["elite"], z["boss"]])
      and all(m in mats for z in real for m in z["materials"]))
tids = [x[0] for z in real for lst in data.theme_treasures(z).values() for x in lst] + \
       [x[0] for f in data.fests() for lst in data.fest_treasures(f).values() for x in lst]
check("treasure ids unique", len(tids) == len(set(tids)))
check("makai treasure info", data.treasure_info("ura_genesis_seed") == {"id": "ura_genesis_seed", "name": "魔界的創世之種", "emoji": "🌌", "rarity": "LR", "zone_key": "makai"})
check("tea house text generic", "竹林" not in data.events()["tea_house"]["text"])
# 🌸 冥界 (2026-11-21)
nw = data.zone_by_id("netherworld")
check("netherworld own roster", not nw["borrowed"] and nw["boss"] == "ura_yuyuko" and nw["elite"] == "phantom_warrior"
      and nw["normals"] == ["netherworld_ghost", "sakura_youkai", "wandering_dead"])
check("netherworld materials", nw["materials"] == ["mat_sakura", "mat_shiratama", "mat_matcha", "mat_rice", "mat_sugar"])
check("netherworld 15 treasures", [len(v) for v in data.theme_treasures(nw).values()] == [4, 3, 3, 2, 2, 1])
check("death butterfly status", data.statuses()["death_butterfly"]["on"]["round_end"][0] == {"do": "dot_max_hp_pct", "value": 0.05}
      and "cleanse" in data.statuses()["death_butterfly"]["flags"])
# ⛰️ 妖怪之山 (2026-11-21)
mt = data.zone_by_id("mountain")
check("mountain own roster", not mt["borrowed"] and mt["boss"] == "ura_aya" and mt["elite"] == "great_tengu"
      and mt["normals"] == ["white_wolf_tengu", "crow_tengu", "kappa_engineer"])
check("mountain materials", mt["materials"] == ["mat_tea_leaf", "mat_cucumber", "mat_sweet_potato", "mat_spring_water", "mat_lamprey"])
check("mountain 15 treasures", [len(v) for v in data.theme_treasures(mt).values()] == [4, 3, 3, 2, 2, 1])
check("gale status", data.statuses()["gale"]["mods"] == {"dodge_pct": 0.3} and data.statuses()["gale"]["good"])
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
# 💚 輔助放符卡 ➔ 順便淨化全隊的壞狀態 (好狀態、不能淨化的留著)
b = battle(team=(("daiyousei", "SR"), ("marisa", "SR"), ("meiling", "SR")))
status.apply(b["party"][1], "debuff_def", value=0.25, turns=2)
status.apply(b["party"][1], "burn")
status.apply(b["party"][2], "madness")
status.apply(b["party"][2], "taunt")
R.battle_action(b, "spell", Rng(), uid="p0", target="p1")
check("sup spell cleanses party", not status.has(b["party"][1], "debuff_def") and not status.has(b["party"][1], "burn")
      and not status.has(b["party"][2], "madness") and status.has(b["party"][2], "taunt"))
check("cleanse logged", any("淨化" in x for x in b["battle"]["log"]))
b = battle(team=(("marisa", "SR"), ("meiling", "SR")), foes=("lost_spirit", "lost_spirit"))
status.apply(b["party"][1], "debuff_def", value=0.25, turns=2)
R.battle_action(b, "spell", Rng(), uid="p0", target="e0")
check("non-sup spell no cleanse", status.has(b["party"][1], "debuff_def"))
# 🧭 嚮導：敵人扣常識度的招式也少扣 30% (四捨五入)
def sanity_hit(team, eid, kind="normal", floor=1):
    b = battle(team=team, foes=(eid,), kind=kind, floor=floor)
    foe = b["battle"]["foes"][0]
    foe["skills"] = [s for s in foe["skills"] if s["do"] == "sanity"]
    if kind == "boss":
        b["battle"]["round"] = 2
    s0 = b["sanity"]
    combat._foe_act(b, foe, Rng([0.0]))
    return s0 - b["sanity"], b
lost, _ = sanity_hit((("marisa", "SR"),), "lost_spirit")
lost_g, bg = sanity_hit((("chiyuri", "R"),), "lost_spirit")
sak_g, _ = sanity_hit((("chiyuri", "R"),), "sakura_youkai")
yu, _ = sanity_hit((("marisa", "SR"),), "ura_yuyuko", "boss", 10)
yu_g, _ = sanity_hit((("chiyuri", "R"),), "ura_yuyuko", "boss", 10)
check(f"enemy sanity guide discount {lost, lost_g, sak_g, yu, yu_g}", (lost, lost_g, sak_g, yu, yu_g) == (10, 7, 11, 40, 28))
check("guide discount logged", any("嚮導少扣" in x for x in bg["battle"]["log"]))
b = battle(team=(("chiyuri", "R"), ("marisa", "SR")), foes=("lost_spirit",))
b["party"][0]["alive"] = False
foe = b["battle"]["foes"][0]; s0 = b["sanity"]
combat._foe_act(b, foe, Rng([0.0]))
check("dead guide no discount", s0 - b["sanity"] == 10)
# 🦋 死蝶：回合結束扣 5% 最大 HP (原本 3%，使用者 2026-11-21 改)
b = battle(team=(("marisa", "SR"),))
m0 = b["party"][0]
status.apply(m0, "death_butterfly")
hp0 = m0["hp"]
combat._trigger(b, m0, "round_end", Rng())
check(f"death butterfly dot {hp0 - m0['hp']}", hp0 - m0["hp"] == max(1, rules.round_half(combat.max_hp(m0) * 0.05)))
b = battle(foes=("ura_yuyuko",), kind="boss", floor=10)
check("yuyuko zone 1 full kit", [s["id"] for s in b["battle"]["foes"][0]["skills"]] == ["bomin_village", "death_butterflies", "resurrection_butterfly", "saigyouji_nirvana"])
# ⛰️ 連續打：hits 下分開算，目標倒下就停
b = battle(team=(("marisa", "SR"),), foes=("great_tengu",), kind="elite")
foe = b["battle"]["foes"][0]
foe["skills"] = [s for s in foe["skills"] if s.get("hits")]
hp0 = b["party"][0]["hp"]
combat._foe_act(b, foe, Rng([0.0]))
line = b["battle"]["log"][-1]
check(f"multi hit 3 {line}", line.count(" / ") == 2 and b["party"][0]["hp"] < hp0)
b = battle(team=(("marisa", "SR"),), foes=("great_tengu",), kind="elite")
foe = b["battle"]["foes"][0]
foe["skills"] = [s for s in foe["skills"] if s.get("hits")]
b["party"][0]["hp"] = 1
combat._foe_act(b, foe, Rng([0.0]))
check("multi hit stops when down", " / " not in b["battle"]["log"][-1] and not b["party"][0]["alive"])
# 🔍 斥候活著 ➔ 敵人閃避減半 (影兔 20% ➔ 10%；擲 0.15：沒斥候閃開、有斥候打中)
def rabbit_hit(team, kill_scout=False):
    b = battle(team=team, foes=("shadow_rabbit",))
    if kill_scout:
        b["party"][1]["alive"] = False
    return combat.deal(b, b["party"][0], b["battle"]["foes"][0], 1.0, Rng([0.15]), single=True)
check("no scout: dodged", rabbit_hit((("marisa", "SR"),)) == 0)
check("scout halves dodge", rabbit_hit((("marisa", "SR"), ("rumia", "SR"))) > 0)
check("dead scout no help", rabbit_hit((("marisa", "SR"), ("rumia", "SR")), kill_scout=True) == 0)
b = battle(team=(("marisa", "SR"), ("rumia", "SR")), foes=("ura_aya",), kind="boss", floor=10)
aya = b["battle"]["foes"][0]
status.apply(aya, "gale", turns=3)
check("aya gale 40% ➔ 20% with scout", combat.deal(b, b["party"][0], aya, 1.0, Rng([0.25]), single=True) > 0
      and combat.deal(b, b["party"][0], aya, 1.0, Rng([0.15]), single=True) == 0)
check("aya zone 1 full kit", [s["id"] for s in aya["skills"]] == ["wind_fan", "peerless_wind", "illusionary_dominance", "fake_scandal"])
check("aya zone 1 dodge 10%", aya["dodge"] == 0.1)
b = battle(foes=("ura_aya",), kind="boss", floor=20)
check("aya zone 2: no skills, no dodge", b["battle"]["foes"][0]["skills"] == [] and b["battle"]["foes"][0]["dodge"] == 0)
b = battle(foes=("crow_tengu",), floor=20)
check("crow tengu dodge 20% (zone 2 too)", b["battle"]["foes"][0]["dodge"] == 0.2)
b = battle(team=(("marisa", "SR"), ("rumia", "SR")), foes=("lost_spirit",))
status.apply(b["party"][0], "gale")
check("scout halving only for enemies", combat.deal(b, b["battle"]["foes"][0], b["party"][0], 1.0, Rng([0.2]), single=True) == 0)
b = battle(foes=("ura_shinki",), kind="boss", floor=10)
check("shinki zone 1 full kit", [s["id"] for s in b["battle"]["foes"][0]["skills"]] == ["genesis_light", "mother_curse", "makai_mercy", "six_wings"])
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

# 2026-11-20 使用者決定：區域 BOSS 只有第 1 區用完整招式 (第 2 區以後只普攻)、持續扣血最低留 1、常識度最多 1000
b = battle(foes=("ura_mokou",), kind="boss", floor=20)
check("zone 2 boss no skills", b["battle"]["foes"][0]["skills"] == [])
b = battle(foes=("ura_mokou",), kind="boss", floor=10)
check("zone 1 boss keeps skills", len(b["battle"]["foes"][0]["skills"]) == 4)
b = battle(foes=("ura_mokou",), kind="boss", floor=60)
check("zone 6 boss no skills too", b["battle"]["foes"][0]["skills"] == [])
# 每區隨機主題：不跟前三區重複、照 seed 決定、第 1 區也隨機
zone_ids = [z["id"] for z in data.zones()]
firsts, bad = set(), []
for i in range(300):
    r1 = {"seed": f"t{i}"}
    seq = [R.zone_theme(r1, z)["id"] for z in range(1, 13)]
    firsts.add(seq[0])
    if any(seq[k] in seq[max(0, k - 3):k] for k in range(len(seq))):
        bad.append(seq)
    r2 = {"seed": f"t{i}"}
    if [R.zone_theme(r2, z)["id"] for z in range(12, 0, -1)][::-1] != seq:   # 先問深的區也一樣
        bad.append(("order", seq))
check(f"themes no repeat in 4 {bad[:1]}", not bad)
check(f"zone 1 random {firsts}", firsts == set(zone_ids))
run = new(seed="th")
check("themes stored", len(run["themes"]) >= 1 and run["themes"][0] in zone_ids)
t0 = R.zone_theme(run, 1)
check("theme drives roster", set(f for d in run["doors"] if d["type"] in ("battle", "elite") for f in d["foes"]) <= set(t0["normals"]) | {t0["elite"]})
b = battle(team=(("marisa", "SR"),))
m0 = b["party"][0]; m0["hp"] = 2
status.apply(m0, "burn")
combat._trigger(b, m0, "round_end", Rng())
check("burn leaves 1", m0["alive"] and m0["hp"] == 1)
run = new(bag={"gensokyo_engi": 1}); run["sanity"] = 800
R.use_item(run, "gensokyo_engi", None, Rng())
check("sanity cap 1000", run["sanity"] == 1000)

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
check("sanity item (cap 1000)", run["sanity"] == 1000)
old = run["doors"]
R.use_item(run, "reroll_dice", None, random.Random(99))
check("reroll", "reroll_dice" not in run["bag"]["items"])
R.use_item(run, "sukima", None, random.Random(3))
check("sukima skip floor", run["floor"] == 1 and run["phase"] == "doors" and run["sanity"] == 990)
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

# ---------------- 🎪 活動關卡 (紅霧異變) ----------------
from Database.ura import fest
check("exp mult", rules.exp_for("normal", 1) == 5 and rules.exp_for("normal", 5) == 7 and rules.exp_floor(10) == 19
      and rules.exp_for("fest_boss", 1) == 100 and rules.exp_for("boss", 3) == 240)
# 沒有活動：完全不出 🎪 門，也不多擲亂數 (同一個 seed 的地圖跟以前一樣)
a, b2 = new(seed="nofest"), R.new_run("nofest", [card(c, r, i=i) for i, (c, r) in enumerate((("marisa", "SR"), ("meiling", "SR"), ("daiyousei", "SR")))], {}, 0, random.Random(5), live_fests=[])
check("no fest same doors", a["doors"] == b2["doors"] and not any(d.get("fest") for d in a["doors"]))
# 有活動：大約 10% 的關卡有一扇 🎪 門；第 9、10 關不換；每區最多 2 扇；保留房間類型
seen_types, per_zone, bad, fest_doors, total = set(), {}, [], 0, 0
for i in range(300):
    run = R.new_run(f"f{i}", [card("marisa", "SR")], {}, 0, random.Random(i), live_fests=[F])
    for floor in range(1, 31):
        ds = R.gen_doors(run, floor, random.Random(f"{i}:{floor}"))
        total += 1
        for d in ds:
            if d.get("fest"):
                fest_doors += 1
                seen_types.add(d["type"])
                per_zone[(i, rules.zone_of(floor))] = per_zone.get((i, rules.zone_of(floor)), 0) + 1
                if rules.floor_in_zone(floor) >= 9 or d["type"] not in rules.FEST_ROOM_TYPES or d.get("hidden"):
                    bad.append((floor, d))
                if d["type"] == "battle" and not set(d["foes"]) <= set(data.fests()[F]["normals"]):
                    bad.append(("foes", d))
                if d["type"] == "event" and data.events()[d["event"]].get("fest") != F:
                    bad.append(("event", d))
check(f"fest door rate {fest_doors}/{total}", 0.05 < fest_doors / total < 0.11)
check(f"fest door rules {bad[:2]}", not bad and max(per_zone.values()) <= rules.FEST_ZONE_CAP)
check(f"fest door types {seen_types}", {"battle", "event"} <= seen_types and "trap" not in seen_types)
# 活動 BOSS：精英門 25%，一局最多一次
run = new()
run["live_fests"] = [F]
d1, d2 = {"type": "elite", "foes": ["mad_rabbit", "lost_spirit"]}, {"type": "elite", "foes": ["mad_rabbit"]}
fest.convert(run, d1, F, Rng(values=[0.1] * 3))   # 假 Rng 的 choice() 也會吃 random() 的值 (先排精英小弟)
fest.convert(run, d2, F, Rng(values=[0.1] * 3))
check("fest boss doors", d1.get("fest_boss") and d1["foes"] == ["scarlet_flandre"] and d2.get("fest_boss")
      and not run.get("fest_boss_seen"))   # 「一局一次」等真的打到才算 (換門、偷看下下一關、選別扇都不會用掉)
view = R.door_view(run, d1, False)
check("door view fest", view.get("fest") == F and "foes" not in view)
run["floor"], run["doors"] = 2, [d1]
R.choose_door(run, 0, random.Random(1))
check("fight fest boss marks seen", run["battle"]["fest_boss"] and run["fest_boss_seen"])
run["phase"], run["battle"], run["doors"] = "doors", None, [d2]
R.choose_door(run, 0, random.Random(1))
check("second boss door falls back", not run["battle"]["fest_boss"] and run["battle"]["foes"][0]["eid"] == "fairy_maid_chief"
      and run["battle"]["kind"] == "elite")
gen_boss = 0
for i in range(400):   # 同一局一直生門：活動 BOSS 門可以出現很多次，但打過一次之後就不會再打到
    r2 = R.new_run(f"b{i}", [card("marisa", "SR")], {}, 0, random.Random(i), live_fests=[F])
    r2["fest_boss_seen"] = True
    dd = {"type": "elite", "foes": ["mad_rabbit"]}
    fest.convert(r2, dd, F, random.Random(i))
    gen_boss += bool(dd.get("fest_boss"))
check("seen stops new boss doors", gen_boss == 0)

# 敵人在敵方回合施加的「N 回合」狀態：從我方下一回合才開始算 ➔ 剛好蓋到我方 N 回合 (使用者 2026-11-20)
def our_turns_with(unit, sid, rng_seed=1):
    """敵方回合剛施加完 ➔ 數接下來我方有幾回合還帶著這個狀態 (每個敵方回合照真的流程跑)"""
    n = 0
    while status.has(unit, sid) and n < 10:
        n += 1                                    # 我方一回合
        for u in combat.living(run["party"]) + combat.living(run["battle"]["foes"]):
            combat._trigger(run, u, "round_end", Rng())
        for u in run["party"] + run["battle"]["foes"]:
            status.tick(u, "rounds")
    return n
run = battle(foes=("bamboo_wraith",))
fl = combat.make_foe(0, "scarlet_flandre", "fest_boss", 1)
fl["fest_boss"], fl["kind"] = True, "boss"
run["battle"]["foes"], run["battle"]["kind"] = [fl], "boss"
quad = next(s for s in fl["skills"] if s["id"] == "four_of_a_kind")
run["battle"]["round"] = 2                        # BOSS 偶數回合放招
fl["rot"] = fl["skills"].index(quad)
combat._foe_act(run, fl, Rng())                   # 芙蘭在敵方回合用「四重存在」
check("quad applied fresh", status.find(fl, "fest_quad") and status.find(fl, "fest_quad").get("fresh"))
for u in run["party"] + run["battle"]["foes"]:   # 那個敵方回合結尾
    status.tick(u, "rounds")
check(f"quad covers 2 of our turns", our_turns_with(fl, "fest_quad") == 2)
# 燒傷 3 回合：一樣扣 3 次，也蓋到我方 3 回合
run = battle(foes=("bamboo_wraith",))
mei = run["party"][1]
status.apply(mei, "burn", turns=3, fresh=True)
for u in combat.living(run["party"]):             # 施加的那個敵方回合結尾：還不扣
    combat._trigger(run, u, "round_end", Rng())
check("fresh burn no tick same round", mei["hp"] == combat.max_hp(mei))
for u in run["party"]:
    status.tick(u, "rounds")
hp0 = mei["hp"]
turns = our_turns_with(mei, "burn")
dot = max(1, rules.round_half(combat.max_hp(mei) * 0.05))
check(f"burn 3 turns 3 ticks {turns}", turns == 3 and mei["hp"] == hp0 - 3 * dot)
# 我方施加的照舊 (例：符卡的凍住、強化)：施加的那個敵方回合結尾就開始扣
run = battle(foes=("bamboo_wraith",))
status.apply(run["battle"]["foes"][0], "freeze", turns=1)
check("ally-applied unchanged", not status.find(run["battle"]["foes"][0], "freeze").get("fresh"))
# 環境：紅霧 (全隊回合結束 −2%、守護者受傷 −10%、錢 ×1.5)
run = new()
run["floor"], run["room"] = 1, {"type": "battle", "fest": F}
combat.start(run, "normal", ["scarlet_fairy"], Rng())
bt = run["battle"]
check("env statuses", all(status.has(m, "fest_scarlet_mist") for m in run["party"])
      and status.has(run["party"][1], "fest_mist_guard") and not status.has(run["party"][0], "fest_mist_guard")
      and bt["money_mult"] == 1.5 and bt["fest"] == F)
hp0 = [m["hp"] for m in run["party"]]
bt["foes"][0]["statuses"].append({"id": "freeze", "left": 3, "stacks": 1})   # 敵人不動，只看紅霧
combat.enemy_phase(run, Rng())
check("mist dot", all(m["hp"] == h - max(1, rules.round_half(combat.max_hp(m) * 0.02)) for m, h in zip(run["party"], hp0)))
combat.finish(run)
check("env ends with battle", not any(status.has(m, "fest_scarlet_mist") for m in run["party"]))
# 四重存在：單體攻擊 40% 閃開，全體必中
f0 = make = combat.make_foe(0, "scarlet_fairy", "normal", 1)
f0["dodge"] = 0
status.apply(f0, "fest_quad")
run = new(); run["floor"] = 1; combat.start(run, "normal", ["lost_spirit"], Rng()); run["battle"]["foes"] = [f0]
check("quad dodge single", combat.deal(run, run["party"][0], f0, 1.0, Rng(values=[0.3]), single=True) == 0)
check("quad no dodge all", combat.deal(run, run["party"][0], f0, 1.0, Rng(values=[0.3])) > 0)
# 吸血鬼的契約：打出的傷害 20% 回血
run = battle(foes=("bamboo_wraith",))
mar = run["party"][0]
mar["hp"] = 10
R._equip(mar, {"rid": "fest_vampire_pact", "tier": 2})
d = combat.deal(run, mar, run["battle"]["foes"][0], 1.0, Rng(), single=True)
check(f"lifesteal {d}", mar["hp"] == min(combat.max_hp(mar), 10 + max(1, rules.round_half(d * 0.25))))   # 攻擊手 +5%
# 女僕長的懷錶：這回合多一次行動
run = battle(foes=("bamboo_wraith",))
run["battle"]["foes"][0]["base_hp"] = run["battle"]["foes"][0]["hp"] = 9999   # 打不死，才看得到換敵方回合
R._equip(run["party"][2], {"rid": "fest_maid_watch", "tier": 0, "left": 1})
check("watch uses + sup bonus", run["party"][2]["relic"]["left"] == 2)
why = combat.use_ofuda(run, "p2", None, Rng())
check(f"watch extra action {why}", why is None and run["battle"]["actions_left"] == 2)
combat.attack(run, "p0", None, Rng())
check("still our turn", run["battle"]["round"] == 1 and run["battle"]["actions_left"] == 1)
combat.attack(run, "p1", None, Rng())
check("then enemy turn", run["battle"]["round"] == 2)
# 活動 BOSS 戰：當成 BOSS (不能逃)，數值 ×6 / ×1.5 / ×1.4；打完不是 boss_clear，給活動法具 + 保留格
run = new()
run["floor"], run["room"] = 3, {"type": "elite", "fest": F, "fest_boss": True}
combat.start(run, "elite", ["scarlet_flandre"], Rng(), fest_boss=True)
fb = run["battle"]["foes"][0]
hp, atk, df = rules.enemy_stats(1, "fest_boss")
check("fest boss stats", run["battle"]["kind"] == "boss" and fb["fest_boss"] and fb["base_hp"] == hp == 180
      and abs(atk - 7.5) < 1e-9 and fb["skills"])
check("fest boss no flee", R.battle_action(run, "flee", Rng()) == "BOSS 戰不能逃")
fb["hp"] = 1
exp0 = run["exp"]
R.battle_action(run, "attack", Rng(), uid="p0")
last = run["last"]
check("fest boss after", run["phase"] == "doors" and run["boss_cleared"] == 0 and run["exp"] - exp0 == 100)
loot = last["loot"]
fest_t = [t for t in loot["treasures"] if t.get("fest") == F]
check(f"fest boss loot {loot['relics']}", any(data.relics()[r["rid"]].get("fest") == F for r in loot["relics"])
      and 1 <= len(fest_t) <= 2 and all(t["rarity"] in ("SSR", "UR", "LR") for t in fest_t)
      and len(loot["treasures"]) == len(fest_t))
# 保留格：本來就有寶物才擲 (0 / 1 / 2 = 20 / 70 / 10%)；法具 50% 換成活動法具 (等級不變)
cnt = {0: 0, 1: 0, 2: 0}
g = random.Random(1)
for _ in range(4000):
    lt = {"treasures": [{"id": "ura_pebble", "rarity": "N", "zone": 1}], "relics": []}
    fest.decorate_loot({}, F, "normal", lt, 1, g)
    cnt[len(lt["treasures"]) - 1] += 1
check(f"slot dist {cnt}", abs(cnt[0] / 4000 - 0.2) < 0.03 and abs(cnt[1] / 4000 - 0.7) < 0.03 and abs(cnt[2] / 4000 - 0.1) < 0.03)
lt = {"treasures": [], "relics": []}
fest.decorate_loot({}, F, "normal", lt, 1, g)
check("no treasure no slot", lt["treasures"] == [])
lt = {"treasures": [], "relics": [{"rid": "war_blessing", "tier": 1}]}
fest.decorate_loot({}, F, "elite", lt, 1, Rng(values=[0.1]))
check("relic swapped keeps tier", data.relics()[lt["relics"][0]["rid"]].get("fest") == F and lt["relics"][0]["tier"] == 1)
check("normal relic pool no fest", all(not data.relics()[R.roll_relic(1, random.Random(i))["rid"]].get("fest") for i in range(200)))
check("normal event door no fest", all(not data.events()[R._event_door({}, random.Random(i))["event"]].get("fest") for i in range(200)))
# 🎪 寶箱：保留格；小惡魔的交易
run = new(bag={})
run["floor"], run["phase"], run["room"] = 1, "chest", {"type": "chest", "fest": F, "locked": False, "mimic": False}
R.open_chest(run, random.Random(3))
check("fest chest", "loot" in run["room"])
run = new()
run["floor"], run["phase"], run["pocket"] = 2, "event", 5000
run["room"] = {"type": "event", "fest": F, "event": "fest_imp_deal", "etype": "special", "pending_choice": "fest_imp_deal"}
why = R.event_choice(run, True, random.Random(1))
check(f"imp deal {why}", why is None and run["pocket"] == 2000 and run["bag"]["treasures"][-1].get("fest") == F)
run["room"]["pending_choice"], run["pocket"] = "fest_imp_deal", 100
check("imp deal poor", "不夠" in R.event_choice(run, True, random.Random(1)))
# 活動門進去：🎪 戰鬥的敵人是活動怪物、環境生效
run = new()
run["live_fests"] = [F]
run["doors"] = [{"type": "battle", "foes": ["scarlet_fairy", "vampire_bat"], "fest": F}]
R.choose_door(run, 0, random.Random(2))
check("enter fest battle", run["phase"] == "battle" and run["battle"]["fest"] == F
      and {f["eid"] for f in run["battle"]["foes"]} == {"scarlet_fairy", "vampire_bat"})

# ---------------- 給畫面用：要不要選目標、現在能用的道具 ----------------
run = battle(foes=("lost_spirit", "shadow_rabbit"), bag={"eientei_salve": 1, "dango": 1, "telescope": 1, "phoenix_feather": 1, "bomb": 1})
check("target attack 2 foes", R.target_kind(run, "attack", "p0") == "enemy")
check("target heal 3 allies", R.target_kind(run, "item", item="eientei_salve") == "ally")
check("target dango", R.target_kind(run, "item", item="dango") == "enemy")
check("target bomb none", R.target_kind(run, "item", item="bomb") is None)
check("target revive nobody dead", R.target_kind(run, "item", item="phoenix_feather") is None)
check("spell target", R.target_kind(run, "spell", "p0") in ("enemy", None))
u = R.usable_items(run)
check(f"usable in battle {u}", "dango" in u and "bomb" in u and "telescope" not in u and "phoenix_feather" not in u)
run["battle"]["foes"][1]["alive"] = False
check("target attack 1 foe", R.target_kind(run, "attack", "p0") is None)
run["party"][2]["alive"], run["party"][1]["alive"] = False, False
check("revive 2 dead", R.target_kind(run, "item", item="phoenix_feather") == "dead" and "phoenix_feather" in R.usable_items(run))
check("heal 1 alive", R.target_kind(run, "item", item="eientei_salve") is None)
run = new(bag={"telescope": 1, "dango": 1, "return_talisman": 1, "substitute_doll": 1})
u = R.usable_items(run)
check(f"usable at doors {u}", "telescope" in u and "return_talisman" in u and "dango" not in u and "substitute_doll" not in u)

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

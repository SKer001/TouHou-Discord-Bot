"""🌀 裏世界模擬：python tools/ura_sim/spells.py [-n 次數] [--teams 關鍵字] [--max-zone 10] [--theme netherworld] [--aoe-solo]
0.35.079 起直接呼叫正式引擎 (Database/ura/)，模擬跟遊戲用同一套規則，不會各算各的。
這裡只有「自動玩家」的決策 (選哪扇門、什麼時候放符卡 / 用道具)；戰鬥、地圖、獎勵全部是引擎算的。
"""
import argparse
import os
import random
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from Database.ura import combat, data, rules, run as R   # noqa: E402

# ---------------- 自動玩家 ----------------
HEAL_KINDS = {"daiyousei": "heal1", "yuki_mai": "healall", "lily_white": "healall"}
AOE_SOLO = False   # --aoe-solo：只剩一隻精英 / BOSS 時也放全體 / 連打的傷害符卡 (預設照舊：2 隻以上才放)
DOOR_PRIORITY = {"chest": 0, "event": 1, "battle": 2, "trap": 3, "elite": 4, "merchant": 0, "boss": 0}


def pick_door(run):
    revealed = R.doors_revealed(run)
    best, best_key = 0, None
    for i, d in enumerate(run["doors"]):
        key = DOOR_PRIORITY.get(R.door_view(run, d, revealed)["type"], 5)   # 看不穿時陷阱看起來是寶箱 (跟玩家一樣)
        if d["type"] == "chest" and revealed and (d.get("mimic") or (d.get("locked") and not run["bag"]["items"].get("chest_key"))):
            key = 6
        if d["type"] == "battle":
            key += len(d["foes"]) * 0.1
        if best_key is None or key < best_key:
            best, best_key = i, key
    return best


def use_sanity_items(run, rng):
    per = rules.sanity_per_floor(rules.zone_of(run["floor"] + 1), combat.has_guide(run))
    for iid in ("gensokyo_engi", "bunbunmaru", "shrine_tea"):
        while run["sanity"] <= per * 2 and run["bag"]["items"].get(iid):
            R.use_item(run, iid, None, rng)


def heal_items(run, rng):
    alive = combat.living(run["party"])
    low = [m for m in alive if m["hp"] < combat.max_hp(m) * 0.3]
    if not low:
        return
    bag = run["bag"]["items"]
    if len(low) >= 2 and bag.get("eirin_elixir"):
        return R.battle_action(run, "item", rng, item="eirin_elixir")
    m = min(low, key=lambda x: x["hp"] / combat.max_hp(x))
    for iid in ("eientei_salve", "bamboo_herb"):
        if bag.get(iid):
            return R.battle_action(run, "item", rng, item=iid, target=m["uid"])
    if bag.get("eirin_elixir"):
        return R.battle_action(run, "item", rng, item="eirin_elixir")


def try_spell(run, actors, rng):
    b = run["battle"]
    foes = combat.living(b["foes"])
    alive = combat.living(run["party"])
    healer = any(m["cid"] in HEAL_KINDS for m in alive)
    strong = any(f["kind"] in ("boss", "elite", "mimic") for f in foes)
    danger = len(foes) >= 2 or strong

    def ready(m, heal=False):
        reserve = 0 if heal or not healer else 6
        return combat.spell_ready(run, m) is None and run["b"] >= m["b_cost"] + reserve

    for m in actors:
        kind = HEAL_KINDS.get(m["cid"])
        if kind == "healall" and ready(m, True) and sum(x["hp"] < combat.max_hp(x) * 0.6 for x in alive) >= 2:
            return R.battle_action(run, "spell", rng, uid=m["uid"]) is None
        if kind == "heal1" and ready(m, True):
            low = min(alive, key=lambda x: x["hp"] / combat.max_hp(x))
            if low["hp"] < combat.max_hp(low) * 0.45:
                return R.battle_action(run, "spell", rng, uid=m["uid"], target=low["uid"]) is None
    for m in actors:
        if not ready(m):
            continue
        sp = data.spells()[m["cid"]]
        k = sp["kind"]
        if m["cid"] == "reimu" and danger and any(x["hp"] < combat.max_hp(x) * 0.5 for x in alive):
            return R.battle_action(run, "spell", rng, uid=m["uid"]) is None
        if k == "shield" and m["cid"] != "reimu" and danger:
            return R.battle_action(run, "spell", rng, uid=m["uid"]) is None
        if k in ("debuff", "buff", "control") and danger:
            tgt = max(foes, key=lambda f: f["hp"])["uid"]
            return R.battle_action(run, "spell", rng, uid=m["uid"], target=tgt) is None
        if sp["target"] in ("enemy_all", "none") and k == "damage" and (len(foes) >= 2 or (AOE_SOLO and strong)):
            return R.battle_action(run, "spell", rng, uid=m["uid"]) is None
        if k == "explore" and not sp.get("outside") and (
                run["sanity"] <= 600 or any(e["do"] == "money_mult" for e in sp["effects"])):   # 回常識度 / 莉莉卡多賺錢
            return R.battle_action(run, "spell", rng, uid=m["uid"]) is None
        if k == "action" and danger:
            return R.battle_action(run, "spell", rng, uid=m["uid"]) is None
        if sp["target"] == "enemy_one" and k == "damage":
            tgt = max(foes, key=lambda f: f["hp"])
            if tgt["hp"] > combat.eff_atk(m) * 1.5:
                return R.battle_action(run, "spell", rng, uid=m["uid"], target=tgt["uid"]) is None
    return False


def battle_turn(run, rng):
    b = run["battle"]
    heal_items(run, rng)
    if run["phase"] != "battle":
        return
    foes = combat.living(b["foes"])
    if len(foes) >= 2 and run["bag"]["items"].get("bomb") and b["round"] == 1:
        R.battle_action(run, "item", rng, item="bomb")
        if run["phase"] != "battle":
            return
    round_now = b["round"]
    while run["phase"] == "battle" and run["battle"]["round"] == round_now and run["battle"]["actions_left"] > 0:
        actors = [m for m in combat.living(run["party"]) if combat.can_act(run, m)]
        if not actors:
            break
        if try_spell(run, actors, rng):
            continue
        m = max(actors, key=lambda x: combat.eff_atk(x))
        tgt = min(combat.living(run["battle"]["foes"]), key=lambda f: f["hp"])
        R.battle_action(run, "attack", rng, uid=m["uid"], target=tgt["uid"])


def equip_relics(run):
    """背包裡的法具給還沒有法具的隊友 (職業對得上的優先)；戰鬥中不能裝，等戰鬥打完"""
    if run["phase"] == "battle":
        return
    while run["bag"]["relics"]:
        free = [m for m in combat.living(run["party"]) if not m.get("relic")]
        if not free:
            return
        rel = run["bag"]["relics"][0]
        cls = data.relics()[rel["rid"]].get("class")
        m = next((x for x in free if x["cls"] == cls), free[0])
        if R.equip_relic(run, 0, m["uid"]):
            return


def play(team, bag, rng, max_zone):
    chars = data.characters()
    cards = [({"instance_id": f"c{i}", "character_key": cid, "rarity": r, "completeness": c}, chars[cid])
             for i, (cid, r, c) in enumerate(team)]
    run = R.new_run(str(rng.random()), cards, bag, pocket=0, rng=rng)
    guard = 0
    while run["phase"] != "ended" and guard < 20000:
        guard += 1
        ph = run["phase"]
        equip_relics(run)
        if ph == "doors":
            if rules.zone_of(run["floor"] + 1) > max_zone:
                break
            use_sanity_items(run, rng)
            R.choose_door(run, pick_door(run), rng)
        elif ph == "battle":
            battle_turn(run, rng)
        elif ph == "chest":
            room = run["room"]
            if not room.get("opened") and (not room.get("locked") or run["bag"]["items"].get("chest_key")):
                R.open_chest(run, rng)
            if run["phase"] == "chest":
                R.leave_room(run, rng)
        elif ph == "event":
            if run["room"].get("pending_choice"):
                R.event_choice(run, False, rng)
            R.leave_room(run, rng)
        elif ph in ("trap", "merchant"):
            R.leave_room(run, rng)
        elif ph == "boss_clear":
            R.continue_after_boss(run, rng)
    return run


TEAMS = {
    "一般隊 (魔理沙 SR / 美鈴 SR / 大妖精 SR，完整度 0.65)": [("marisa", "SR", 0.65), ("meiling", "SR", 0.65), ("daiyousei", "SR", 0.65)],
    "一般隊・全體 (琪露諾 SR / 美鈴 SR / 雪與舞 SR，0.65)": [("cirno", "SR", 0.65), ("meiling", "SR", 0.65), ("yuki_mai", "SR", 0.65)],
    "沒有補師 (魔理沙 SR / 美鈴 SR / 露米婭 SR，0.65)": [("marisa", "SR", 0.65), ("meiling", "SR", 0.65), ("rumia", "SR", 0.65)],
    "強隊 (芙蘭 UR / 夢子 SSR / 大妖精 SR，0.9)": [("flandre", "UR", 0.9), ("yumeko", "SSR", 0.9), ("daiyousei", "SR", 0.9)],
    "靈夢隊 (靈夢 UR / 美鈴 SSR / 大妖精 SR，0.9)": [("reimu", "UR", 0.9), ("meiling", "SSR", 0.9), ("daiyousei", "SR", 0.9)],
    "頂尖 (神綺 LR / 蕾米莉亞 LR / 大妖精 SR，1.0)": [("shinki", "LR", 1.0), ("remilia", "LR", 1.0), ("daiyousei", "SR", 1.0)],
}
BAGS = {   # 道具 id ➔ 數量 (同 docs/ura.md 的輕裝 / 一般 / 重裝)
    "輕裝": {"bamboo_herb": 2, "shrine_tea": 2},
    "一般": {"eientei_salve": 2, "eirin_elixir": 1, "bamboo_herb": 2, "bunbunmaru": 3, "gensokyo_engi": 2, "bomb": 5},
    "重裝": {"eientei_salve": 2, "eirin_elixir": 1, "bamboo_herb": 2, "gensokyo_engi": 5, "bomb": 5,
             "phoenix_feather": 1, "substitute_doll": 1},
}


def bag_cost(bag):
    return sum(data.items()[i]["price"] * n for i, n in bag.items())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("--teams", default="")
    ap.add_argument("--max-zone", type=int, default=10)
    ap.add_argument("--theme", default="", help="整局固定一個主題 (bamboo / makai / mountain / netherworld / higan)")
    ap.add_argument("--aoe-solo", action="store_true", help="只剩一隻精英 / BOSS 時也放全體 / 連打的傷害符卡")
    args = ap.parse_args()
    AOE_SOLO = args.aoe_solo
    if args.theme:
        R.zone_theme = lambda run, zone: data.zone_by_id(args.theme)
    rng = random.Random(1)
    for tname, team in TEAMS.items():
        if args.teams and not any(k in tname for k in args.teams.split(",")):
            continue
        print(f"\n=== {tname} ===")
        for bname, bag in BAGS.items():
            runs = [play(team, bag, rng, args.max_zone) for _ in range(args.n)]
            cleared = [r["boss_cleared"] for r in runs]
            p = lambda k: sum(c >= k for c in cleared) / args.n
            why = statistics.mode([(r["result"] or "cap") + ":" + (r["log"][-1][:6] if r["log"] else "") for r in runs])
            money = statistics.median(r["pocket"] for r in runs)
            print(f"  {bname} ({bag_cost(bag) // 1000}K) 中位第 {statistics.median(r['floor'] for r in runs):.0f} 關 ({why})"
                  f" 口袋中位 {money / 1000:.0f}K | 打完 BOSS：" + " ".join(f"{k}區 {p(k):.0%}" for k in (3, 4, 5, 6, 7, 8, 10)))

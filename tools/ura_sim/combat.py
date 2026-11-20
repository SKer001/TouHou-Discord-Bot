"""🌀 裏世界戰鬥模擬 (設計用，還沒有正式程式；規則見 docs/ura.md)
只有普攻 + 道具，沒有符卡 / 法具 / 陷阱 / 事件。
用法：python tools/ura_sim/combat.py [--sup-heal N]   (N = 輔助每 N 回合回血 30%，粗估回血符卡；0 = 沒有)
"""
import math
import random
import statistics
import argparse

SUP_HEAL = 0   # 輔助每幾回合回血 30% (粗估符卡)；0 = 沒有

# ---------- 規則 (docs/ura.md) ----------
def red(d):                      # DEF 減傷
    return 0.6 * (1 - math.exp(-d / 20))

def mult(a):                     # 敵人倍率
    return 1 + 0.1875 * (a - 1) ** 2 if a <= 5 else 4 + (a - 5)

def enemy(a, kind):
    k = mult(a)
    hp, atk, df = 30 * k, 5 * k, 5 * (1 + (k - 1) / 2)
    if kind == "elite":
        hp, atk, df = hp * 2.5, atk * 1.5, df * 1.3
    if kind == "boss":
        hp, atk, df = hp * 10, atk * 2, df * 1.5
    return {"hp": hp, "max": hp, "atk": atk, "def": df, "kind": kind}

CLASS = {"atk": (80, 30, 8), "guard": (140, 15, 20), "sup": (100, 18, 12), "scout": (90, 22, 10), "guide": (100, 18, 12)}
RARITY = {"N": 1.0, "R": 1.1, "SR": 1.2, "SSR": 1.3, "UR": 1.4, "LR": 1.5}

def comp_mult(c):
    return 0.8 + 0.4 * (c - 0.3) / 0.7

def member(cls, rarity, comp):
    hp, atk, df = CLASS[cls]
    m = RARITY[rarity] * comp_mult(comp)
    return {"cls": cls, "hp": hp * m, "max": hp * m, "atk": atk * m, "def": df * m, "alive": True}

def per_floor_sanity(a, guide):
    return (10 + 5 * (a - 1)) * (0.7 if guide else 1)

def weighted_count(lo, hi, rng):  # 數量越多越少
    ks = list(range(lo, hi + 1))
    return rng.choices(ks, weights=list(range(len(ks), 0, -1)))[0]

# ---------- 一場戰鬥 ----------
def fight(party, foes, bag, rng, log):
    rnd = 0
    while True:
        rnd += 1
        if rnd > 200:
            return False
        alive = [m for m in party if m["alive"]]
        if not alive:
            return False
        # 輔助的回血符卡 (粗估)：每 SUP_HEAL 回合把血最少的人回 30%
        if SUP_HEAL and rnd % SUP_HEAL == 0 and any(m["alive"] and m["cls"] == "sup" for m in party):
            low = min((m for m in party if m["alive"]), key=lambda x: x["hp"] / x["max"])
            if low["hp"] < low["max"] * 0.7:
                low["hp"] = min(low["max"], low["hp"] + low["max"] * 0.3)
        # 道具 (不算回合)：有人 < 35% 先回血
        heal_items(party, bag)
        # 炸彈：2 隻以上
        living = [f for f in foes if f["hp"] > 0]
        if len(living) >= 2 and bag.get("bomb", 0) > 0:
            bag["bomb"] -= 1
            top = max(m["atk"] for m in party if m["alive"])
            for f in living:
                f["hp"] -= top * 1.5 * (1 - red(f["def"]))
            log["bombs"] += 1
        living = [f for f in foes if f["hp"] > 0]
        if not living:
            return True
        # 我方：攻擊最高的那位打血最少的敵人
        actor = max((m for m in party if m["alive"]), key=lambda m: m["atk"])
        tgt = min(living, key=lambda f: f["hp"])
        tgt["hp"] -= actor["atk"] * rng.uniform(0.9, 1.1) * (1 - red(tgt["def"]))
        living = [f for f in foes if f["hp"] > 0]
        if not living:
            return True
        # 敵方：每隻打一位
        for f in living:
            alive = [m for m in party if m["alive"]]
            if not alive:
                return False
            guard = [m for m in alive if m["cls"] == "guard"]
            if guard and rng.random() < 0.7:
                t = guard[0]
            else:
                t = rng.choices(alive, weights=[m["hp"] for m in alive])[0]
            atk = f["atk"] * (1.3 if f["kind"] == "boss" and f["hp"] < f["max"] / 2 else 1)
            t["hp"] -= atk * rng.uniform(0.9, 1.1) * (1 - red(t["def"]))
            if t["hp"] <= 0:
                if bag.get("doll", 0) > 0:
                    bag["doll"] -= 1
                    t["hp"] = 1
                else:
                    t["alive"] = False
                    t["hp"] = 0
                    if bag.get("revive", 0) > 0:
                        bag["revive"] -= 1
                        t["alive"] = True
                        t["hp"] = t["max"] / 2
                    else:
                        log["deaths"] += 1


def heal_items(party, bag):
    alive = [m for m in party if m["alive"]]
    low = [m for m in alive if m["hp"] < m["max"] * 0.35]
    if not low:
        return
    if len(low) >= 2:
        for k, pct in (("g30", 0.3), ("g10", 0.1)):
            if bag.get(k, 0):
                bag[k] -= 1
                for m in alive:
                    m["hp"] = min(m["max"], m["hp"] + m["max"] * pct)
                return
    m = min(low, key=lambda x: x["hp"] / x["max"])
    for k, pct in (("s50", 0.5), ("s30", 0.3), ("g30", 0.3), ("g10", 0.1)):
        if bag.get(k, 0):
            bag[k] -= 1
            targets = alive if k.startswith("g") else [m]
            for t in targets:
                t["hp"] = min(t["max"], t["hp"] + t["max"] * pct)
            return

# ---------- 一局 (一直打到倒下或常識度歸 0) ----------
def run(team, bag0, rng, max_area=15):
    party = [member(*t) for t in team]
    bag = dict(bag0)
    guide = any(t[0] == "guide" for t in team)
    sanity = 1000
    sanity_items = sorted(bag.pop("sanity", []), reverse=True)
    log = {"deaths": 0, "bombs": 0}
    floor = 0
    cleared_area = 0
    while floor < max_area * 10:
        floor += 1
        a = (floor - 1) // 10 + 1
        sanity -= per_floor_sanity(a, guide)
        while sanity <= 0 and sanity_items:
            sanity += sanity_items.pop()
        if sanity <= 0:
            return floor - 1, cleared_area, "sanity"
        pos = floor % 10
        if pos == 0:
            foes = [enemy(a, "boss")]
        elif pos in (2, 4, 6, 8):          # 每區 4 場一般戰鬥
            foes = [enemy(a, "normal") for _ in range(weighted_count(1, 3, rng))]
        elif pos == 5 or (pos == 7 and rng.random() < 0.5):   # 精英 1.5 場
            foes = [enemy(a, "elite")] + [enemy(a, "normal") for _ in range(weighted_count(0, 2, rng))]
        else:
            continue                        # 寶箱 / 事件 / 商人 (沒戰鬥)
        if not fight(party, foes, bag, rng, log):
            return floor, cleared_area, "wiped"
        if pos == 0:
            cleared_area = a
    return floor, cleared_area, "cap"

TEAMS = {
    "一般隊 (SR×3、完整度 0.65)": [("atk", "SR", 0.65), ("guard", "SR", 0.65), ("sup", "SR", 0.65)],
    "一般隊 + 嚮導 (SR×3)": [("atk", "SR", 0.65), ("guard", "SR", 0.65), ("guide", "SR", 0.65)],
    "強隊 (UR 攻擊手 / UR 守護者 / SSR 輔助、完整度 0.9)": [("atk", "UR", 0.9), ("guard", "UR", 0.9), ("sup", "SSR", 0.9)],
    "頂尖 (LR×2 + UR、完整度 1.0)": [("atk", "LR", 1.0), ("atk", "LR", 1.0), ("guard", "UR", 1.0)],
}
BAGS = {
    "空手": ({}, 0),
    "輕裝": ({"s30": 2, "sanity": [100, 100]}, 16_000),
    "一般": ({"s50": 2, "g30": 1, "s30": 2, "sanity": [300, 300, 300, 500, 500], "bomb": 5}, 45_000 + 50_000 + 50_000),
    "重裝": ({"s50": 2, "g30": 1, "s30": 2, "sanity": [500] * 5, "bomb": 5, "revive": 1, "doll": 1}, 45_000 + 65_000 + 50_000 + 40_000 + 20_000),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sup-heal", type=int, default=0)
    ap.add_argument("-n", type=int, default=800)
    args = ap.parse_args()
    SUP_HEAL = args.sup_heal
    rng = random.Random(1)
    N = args.n
    for tname, team in TEAMS.items():
        print(f"\n=== {tname} ===")
        for bname, (bag, cost) in BAGS.items():
            res = [run(team, bag, rng) for _ in range(N)]
            floors = [r[0] for r in res]
            clears = [r[1] for r in res]
            p = lambda k: sum(c >= k for c in clears) / N
            why = statistics.mode([r[2] for r in res])
            q = statistics.quantiles(floors, n=4)
            print(f"  {bname:<4} 成本 {cost/1000:>4.0f}K | 倒下 / 歸 0 在第 {q[0]:.0f}～{q[2]:.0f} 關 (中位 {statistics.median(floors):.0f}) 主因 {why} | "
                  f"打完 BOSS 機率：1區 {p(1):.0%} 3區 {p(3):.0%} 5區 {p(5):.0%} 7區 {p(7):.0%} 10區 {p(10):.0%}")

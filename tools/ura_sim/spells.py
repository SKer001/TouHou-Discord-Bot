"""🌀 裏世界戰鬥模擬 (含符卡)：python tools/ura_sim/spells.py [-n 次數]
規則照 docs/ura.md「戰鬥」「符卡設計」；設計用，還沒有正式程式。沒有法具 / 陷阱 / 事件 / 商人。
"""
import argparse
import math
import random
import statistics

# ---------------- 規則 ----------------
def red(d):
    return 0.6 * (1 - math.exp(-d / 20))

LATE_STEP = 0.5   # 第 6 區以後每區 +幾 (docs/ura.md：+0.5)

def mult(a):
    return 1 + 0.1875 * (a - 1) ** 2 if a <= 5 else 4 + LATE_STEP * (a - 5)

def enemy(a, kind):
    k = mult(a)
    hp, atk, df = 30 * k, 5 * k, 5 * (1 + (k - 1) / 2)
    if kind == "elite":
        hp, atk, df = hp * 2.5, atk * 1.5, df * 1.3
    if kind == "boss":
        hp, atk, df = hp * BOSS_HP, atk * BOSS_ATK, df * 1.5
    return {"hp": hp, "max": hp, "atk": atk, "def": df, "kind": kind, "skip": 0, "down": 0, "down_pct": 0}

CLASS = {"atk": (80, 30, 8), "guard": (140, 15, 20), "sup": (100, 18, 12), "scout": (90, 22, 10), "guide": (100, 18, 12)}
RARITY = {"N": 1.0, "R": 1.1, "SR": 1.2, "SSR": 1.3, "UR": 1.4, "LR": 1.5}

# 角色：職業、階級範圍、符卡 (種類, 特色)
CHARS = {
    "marisa": ("atk", ["SR", "SSR", "UR"], "single", {}),
    "flandre": ("atk", ["SSR", "UR", "LR"], "single", {"big": 1.2}),
    "remilia": ("atk", ["SSR", "UR", "LR"], "single", {"drain": 0.2}),
    "shinki": ("atk", ["SSR", "UR", "LR"], "aoe", {"bonus": 0.2}),
    "cirno": ("atk", ["SR", "SSR", "UR"], "aoe", {"freeze": 0.3}),
    "sakuya": ("atk", ["SR", "SSR", "UR"], "world", {}),
    "meiling": ("guard", ["R", "SR", "SSR"], "taunt", {"self_heal": 0.15}),
    "yumeko": ("guard", ["R", "SR", "SSR"], "shield", {}),
    "daiyousei": ("sup", ["N", "R", "SR"], "heal1", {}),
    "yuki_mai": ("sup", ["N", "R", "SR"], "healall", {}),
    "rumia": ("scout", ["R", "SR", "SSR"], "atkdown", {}),
    "reimu": ("guide", ["SR", "SSR", "UR"], "muso", {}),
}
COST = {"single": (8, 3), "aoe": (12, 4), "heal1": (6, 3), "healall": (10, 5), "taunt": (8, 4), "shield": (8, 4),
        "atkdown": (6, 4), "world": (20, 8), "muso": (20, 8)}
POWER = {"single": (2.5, 3.0, 3.5), "aoe": (1.2, 1.5, 1.8), "heal1": (0.30, 0.35, 0.40), "healall": (0.15, 0.20, 0.25),
         "atkdown": (0.20, 0.25, 0.30), "shield": (0.30, 0.35, 0.40), "muso": (1.2, 1.5, 1.8)}
B_MAX, B_START, B_FLOOR, B_ROUND, B_KILL = 50, 25, 1, 2, 1
BOSS_HP = 10   # BOSS HP 倍率 (docs/ura.md：×10)
BOSS_ATK = 1.6   # BOSS ATK 倍率 (docs/ura.md：×1.6)
RELIC = 0.12   # 粗估法具：每打完一隻 BOSS，還沒有法具的一位 ATK / DEF + 這個比例 (SSR +10%、UR +15%…)；0 = 不算

def comp_mult(c):
    return 0.8 + 0.4 * (c - 0.3) / 0.7

def member(cid, rarity, comp):
    cls, rarities, kind, extra = CHARS[cid]
    hp, atk, df = CLASS[cls]
    m = RARITY[rarity] * comp_mult(comp)
    cost, cd = COST[kind]
    if comp > 0.8:
        cd = max(1, math.floor(cd * 0.9))
    return {"id": cid, "cls": cls, "hp": hp * m, "max": hp * m, "atk": atk * m, "def": df * m, "alive": True,
            "kind": kind, "extra": extra, "tier": rarities.index(rarity), "cost": cost, "cd_max": cd, "cd": 0,
            "shield": 0}

def per_floor_sanity(a, guide):
    return (10 + 5 * (a - 1)) * (0.7 if guide else 1)

def weighted_count(lo, hi, rng):
    ks = list(range(lo, hi + 1))
    return rng.choices(ks, weights=list(range(len(ks), 0, -1)))[0]

# ---------------- 戰鬥 ----------------
class Battle:
    def __init__(self, party, foes, bag, st, rng):
        self.p, self.f, self.bag, self.st, self.rng = party, foes, bag, st, rng
        self.taunt = 0
        self.invuln = False

    def alive(self):
        return [m for m in self.p if m["alive"]]

    def living(self):
        return [f for f in self.f if f["hp"] > 0]

    def hit(self, f, dmg, ignore_half=False):
        df = f["def"] / 2 if ignore_half else f["def"]
        before = f["hp"] > 0
        f["hp"] -= dmg * self.rng.uniform(0.9, 1.1) * (1 - red(df))
        if before and f["hp"] <= 0:
            self.st["b"] = min(B_MAX, self.st["b"] + B_KILL)

    def basic(self, m, mul=1.0):
        live = self.living()
        if live:
            self.hit(min(live, key=lambda x: x["hp"]), m["atk"] * mul)

    def heal(self, m, pct):
        m["hp"] = min(m["max"], m["hp"] + m["max"] * pct)

    def try_spell(self):
        st, live, alive = self.st, self.living(), self.alive()
        healer = any(m["kind"] in ("heal1", "healall") for m in alive)
        reserve = 6 if healer else 0
        boss = any(f["kind"] in ("boss", "elite") for f in live)
        def ready(m, need_reserve=True):
            return m["alive"] and m["cd"] == 0 and st["b"] >= m["cost"] + (reserve if need_reserve and m["kind"] not in ("heal1", "healall") else 0)
        def cast(m):
            st["b"] -= m["cost"]
            m["cd"] = m["cd_max"]
        # 1. 回血
        for m in alive:
            if m["kind"] == "healall" and ready(m) and sum(x["hp"] < x["max"] * 0.6 for x in alive) >= 2:
                cast(m)
                for x in alive:
                    self.heal(x, POWER["healall"][m["tier"]])
                return True
            if m["kind"] == "heal1" and ready(m):
                low = min(alive, key=lambda x: x["hp"] / x["max"])
                if low["hp"] < low["max"] * 0.45:
                    cast(m)
                    self.heal(low, POWER["heal1"][m["tier"]])
                    return True
        danger = len(live) >= 2 or boss
        for m in alive:
            k = m["kind"]
            if not ready(m):
                continue
            if k == "muso" and danger and any(x["hp"] < x["max"] * 0.5 for x in alive):
                cast(m)
                self.invuln = True
                for f in live:
                    self.hit(f, m["atk"] * POWER["muso"][m["tier"]])
                return True
            if k == "taunt" and danger:
                cast(m)
                self.taunt = 2
                self.heal(m, m["extra"]["self_heal"])
                return True
            if k == "shield" and danger:
                cast(m)
                for x in alive:
                    x["shield"] = POWER["shield"][m["tier"]]
                return True
            if k == "atkdown" and danger:
                cast(m)
                for f in live:
                    f["down"], f["down_pct"] = 3, POWER["atkdown"][m["tier"]]
                return True
            if k == "aoe" and len(live) >= 2:
                cast(m)
                mul = POWER["aoe"][m["tier"]] + m["extra"].get("bonus", 0)
                for f in live:
                    self.hit(f, m["atk"] * mul)
                    if self.rng.random() < m["extra"].get("freeze", 0):
                        f["skip"] = max(f["skip"], 1)
                return True
            if k == "world" and danger:
                cast(m)
                for x in self.alive():
                    self.basic(x, 1.2 if m["tier"] == 2 else 1.0)
                return True
            if k == "single":
                tgt = max(live, key=lambda f: f["hp"])
                if tgt["hp"] > m["atk"] * 1.5:
                    cast(m)
                    mul = POWER["single"][m["tier"]] * (m["extra"].get("big", 1) if tgt["kind"] != "normal" else 1)
                    hp0 = tgt["hp"]
                    self.hit(tgt, m["atk"] * mul)
                    if m["extra"].get("drain"):
                        self.heal(m, 0)
                        m["hp"] = min(m["max"], m["hp"] + (hp0 - max(tgt["hp"], 0)) * m["extra"]["drain"])
                    return True
        return False

    def our_turn(self):
        if not self.try_spell():
            self.basic(max(self.alive(), key=lambda m: m["atk"]))

    def enemy_turn(self):
        for f in self.living():
            if f["skip"]:
                f["skip"] -= 1
                continue
            alive = self.alive()
            if not alive:
                return
            guard = [m for m in alive if m["cls"] == "guard"]
            if guard and (self.taunt or self.rng.random() < 0.7):
                t = guard[0]
            else:
                t = self.rng.choices(alive, weights=[m["hp"] for m in alive])[0]
            if self.invuln:
                continue
            atk = f["atk"] * (1.3 if f["kind"] == "boss" and f["hp"] < f["max"] / 2 else 1)
            if f["down"]:
                atk *= 1 - f["down_pct"]
            dmg = atk * self.rng.uniform(0.9, 1.1) * (1 - red(t["def"]))
            if t["shield"]:
                dmg *= 1 - t["shield"]
                t["shield"] = 0
            t["hp"] -= dmg
            if t["hp"] <= 0:
                if self.bag.get("doll", 0) > 0:
                    self.bag["doll"] -= 1
                    t["hp"] = 1
                elif self.bag.get("revive", 0) > 0:
                    self.bag["revive"] -= 1
                    t["hp"] = t["max"] / 2
                else:
                    t["alive"], t["hp"] = False, 0
        for f in self.f:
            if f["down"]:
                f["down"] -= 1
        self.invuln = False
        if self.taunt:
            self.taunt -= 1

    def items(self):
        alive = self.alive()
        low = [m for m in alive if m["hp"] < m["max"] * 0.3]
        if not low:
            return
        if len(low) >= 2 and self.bag.get("g30"):
            self.bag["g30"] -= 1
            for m in alive:
                self.heal(m, 0.3)
            return
        m = min(low, key=lambda x: x["hp"] / x["max"])
        for k, pct in (("s50", 0.5), ("s30", 0.3), ("g30", 0.3)):
            if self.bag.get(k):
                self.bag[k] -= 1
                for t in (alive if k.startswith("g") else [m]):
                    self.heal(t, pct)
                return

    def run(self):
        for rnd in range(1, 300):
            if not self.alive():
                return False
            self.items()
            live = self.living()
            if len(live) >= 2 and self.bag.get("bomb"):
                self.bag["bomb"] -= 1
                top = max(m["atk"] for m in self.alive())
                for f in live:
                    self.hit(f, top * 1.5)
            if not self.living():
                return True
            self.our_turn()
            if not self.living():
                return True
            self.enemy_turn()
            self.st["b"] = min(B_MAX, self.st["b"] + B_ROUND)
            for m in self.p:
                m["cd"] = max(0, m["cd"] - 1)
        return False

# ---------------- 一局 ----------------
def run(team, bag0, rng, max_area=15):
    party = [member(*t) for t in team]
    bag = dict(bag0)
    guide = any(CHARS[t[0]][0] == "guide" for t in team)
    sanity, sanity_items = 1000, sorted(bag.pop("sanity", []), reverse=True)
    st = {"b": B_START}
    cleared = 0
    for floor in range(1, max_area * 10 + 1):
        a = (floor - 1) // 10 + 1
        sanity -= per_floor_sanity(a, guide)
        while sanity <= 0 and sanity_items:
            sanity += sanity_items.pop()
        if sanity <= 0:
            return floor - 1, cleared, "sanity"
        st["b"] = min(B_MAX, st["b"] + B_FLOOR)
        for m in party:
            m["cd"] = max(0, m["cd"] - 1)
        pos = floor % 10
        if pos == 0:
            foes = [enemy(a, "boss")]
        elif pos in (2, 4, 6, 8):
            foes = [enemy(a, "normal") for _ in range(weighted_count(1, 3, rng))]
        elif pos == 5 or (pos == 7 and rng.random() < 0.5):
            foes = [enemy(a, "elite")] + [enemy(a, "normal") for _ in range(weighted_count(0, 2, rng))]
        else:
            continue
        if not Battle(party, foes, bag, st, rng).run():
            return floor, cleared, "wiped"
        if pos == 0:
            cleared = a
            free = [m for m in party if m["alive"] and not m.get("relic")]
            if RELIC and free:   # BOSS 一定掉 1 個法具 (依職業給)
                m = max(free, key=lambda x: x["atk"])
                m["relic"] = True
                m["atk"] *= 1 + RELIC
                m["def"] *= 1 + RELIC
    return max_area * 10, cleared, "cap"

TEAMS = {
    "一般隊 (魔理沙 SR / 美鈴 SR / 大妖精 SR，完整度 0.65)": [("marisa", "SR", 0.65), ("meiling", "SR", 0.65), ("daiyousei", "SR", 0.65)],
    "一般隊・全體 (琪露諾 SR / 美鈴 SR / 雪與舞 SR，0.65)": [("cirno", "SR", 0.65), ("meiling", "SR", 0.65), ("yuki_mai", "SR", 0.65)],
    "沒有補師 (魔理沙 SR / 美鈴 SR / 露米婭 SR，0.65)": [("marisa", "SR", 0.65), ("meiling", "SR", 0.65), ("rumia", "SR", 0.65)],
    "強隊 (芙蘭 UR / 夢子 SSR / 大妖精 SR，0.9)": [("flandre", "UR", 0.9), ("yumeko", "SSR", 0.9), ("daiyousei", "SR", 0.9)],
    "靈夢隊 (靈夢 UR / 美鈴 SSR / 大妖精 SR，0.9)": [("reimu", "UR", 0.9), ("meiling", "SSR", 0.9), ("daiyousei", "SR", 0.9)],
    "頂尖 (神綺 LR / 蕾米莉亞 LR / 大妖精 SR，1.0)": [("shinki", "LR", 1.0), ("remilia", "LR", 1.0), ("daiyousei", "SR", 1.0)],
}
BAGS = {
    "輕裝": ({"s30": 2, "sanity": [100, 100]}, 16_000),
    "一般": ({"s50": 2, "g30": 1, "s30": 2, "sanity": [300, 300, 300, 500, 500], "bomb": 5}, 145_000),
    "重裝": ({"s50": 2, "g30": 1, "s30": 2, "sanity": [500] * 5, "bomb": 5, "revive": 1, "doll": 1}, 220_000),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=600)
    ap.add_argument("--boss-hp", type=float, default=10)
    ap.add_argument("--boss-atk", type=float, default=1.6)
    ap.add_argument("--teams", default="")
    ap.add_argument("--late-step", type=float, default=0.5)
    ap.add_argument("--relic", type=float, default=0.12)
    args = ap.parse_args()
    BOSS_HP = args.boss_hp
    BOSS_ATK = args.boss_atk
    LATE_STEP = args.late_step
    RELIC = args.relic
    rng = random.Random(1)
    for tname, team in TEAMS.items():
        if args.teams and not any(k in tname for k in args.teams.split(",")):
            continue
        print(f"\n=== {tname} ===")
        for bname, (bag, cost) in BAGS.items():
            res = [run(team, bag, rng) for _ in range(args.n)]
            cl = [r[1] for r in res]
            p = lambda k: sum(c >= k for c in cl) / args.n
            why = statistics.mode([r[2] for r in res])
            print(f"  {bname} ({cost // 1000}K) 中位第 {statistics.median(r[0] for r in res):.0f} 關 ({why}) | 打完 BOSS："
                  + " ".join(f"{k}區 {p(k):.0%}" for k in (3, 4, 5, 6, 7, 8, 10)))

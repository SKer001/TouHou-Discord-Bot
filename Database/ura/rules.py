"""
🌀 裏世界的數值公式 (純計算，全部照 docs/ura.md；數字是使用者定的，改這裡就好)
"""
import math

RARITIES = ["N", "R", "SR", "SSR", "UR", "LR"]
RARITY_MULT = {"N": 1.0, "R": 1.1, "SR": 1.2, "SSR": 1.3, "UR": 1.4, "LR": 1.5}
CLASS_NAMES = {"atk": "⚔️ 攻擊手", "guard": "🛡️ 守護者", "sup": "💚 輔助", "scout": "🔍 斥候", "guide": "🧭 嚮導"}
CLASS_EMOJI = {"atk": "⚔️", "guard": "🛡️", "sup": "💚", "scout": "🔍", "guide": "🧭"}
# 🎻 合奏 (TH07 騷靈三姊妹，使用者 2026-11-24)：spells.json 寫 "ensemble": 名稱 的符卡，
#    members 全部在隊上而且活著時，那招的數字 ($ 參數：弱化 / 強化 / 常識度) × mult；固定的數字 (賽錢 × 1.2、回合數) 不變
ENSEMBLES = {"prismriver": {"name": "🎻 騷靈合奏", "members": ("lunasa", "merlin", "lyrica"), "mult": 1.2}}

# ---- 一局 ----
SANITY_START = 1000
MAX_PARTY = 3
MIN_COMPLETENESS = 0.3          # 出征門檻
COMP_PENALTY = 0.1              # 完整度懲罰 (一局每張卡最多扣一次)
BAG_SLOTS = 20
MATERIAL_STACK = 20             # 料理素材一格最多 20 個
B_MAX, B_START, B_STEP, B_KILL = 50, 25, 1, 1   # B 點：上限、進場、每一步、打倒一隻
GUIDE_DISCOUNT = 0.3            # 嚮導每關少扣 30% (不疊加)
FLEE_MULT = {"normal": 2.5, "elite": 4, "mimic": 4}
DOOR_COUNT = (2, 3)             # 一般關卡 2～3 扇門
ROOM_WEIGHTS = {"battle": 45, "event": 20, "chest": 15, "trap": 10, "elite": 10}
ROOM_CAPS = {"elite": 2, "trap": 2, "chest": 3, "event": 4}   # 每區每種房間最多出現在門上幾次
REPEAT_ROOMS = ("chest",)       # 同一關可以出現兩扇以上的房間 (戰鬥本來就可以；其他種類一關最多一扇)
BATTLE_FLOORS = (2, 4, 6, 8)    # 每區第幾關固定是戰鬥
HIDDEN_CHEST_CHANCE = 0.1       # 有斥候時多一扇隱藏寶箱門
MIMIC_CHANCE = 0.1
LOCKED_CHANCE = 0.5             # 寶箱上鎖機率 (2026-11-23 使用者：30% ➔ 50%)
TRAP_HP_PCT = 0.1

# ---- 戰鬥 ----
ENEMY_BASE = (30, 5, 5)         # 第 1 區一般怪 HP / ATK / DEF
ELITE_MULT = (2.5, 1.5, 1.3)
BOSS_MULT = (10, 1.6, 1.5)
BOSS_PHASE2_ATK = 0.3           # BOSS 血剩一半 ATK +30%
GUARD_WEIGHT = 4                # 敵人選目標時守護者的比重
ENRAGE_AFTER, ENRAGE_STEP = 10, 0.1
DAMAGE_VARIANCE = (0.9, 1.1)
SKILL_CHANCE = {"normal": 0.25, "elite": 0.35}
BREACH_ATK = 1.1
BREACH_DEF = 0.9

# ---- 獎勵 ----
# 經驗 = 基數 × (1 + (區域數 − 1) / 10) (使用者 2026-11-20 改，原本 × 區域數怕深處膨脹太快)
EXP_FLOOR, EXP_KILL = 10, {"normal": 5, "elite": 30, "mimic": 30, "boss": 200, "fest_boss": 100}
FAIL_EXP_RATIO = 0.5
REWARDS = {   # 一隻敵人 (含勸走) 給的東西
    "normal": {"materials": (3, 5), "money": (500, 1000), "treasure_chance": 0.1, "treasure_table": "monster"},
    "elite": {"items": (1, 3), "money": (1000, 5000), "relic_chance": 0.2, "treasure_chance": 0.5, "treasure_table": "monster"},
    "boss": {"materials": (3, 5), "items": (2, 3), "relics": (1, 1), "money": (10000, 15000), "treasures": (3, 5), "treasure_table": "boss"},
    # 🎪 活動 BOSS：照區域 BOSS 但不掉一般法具 / 寶物 (另外一定給 1 個活動法具 + 活動保留格，見 fest.py)
    "fest_boss": {"materials": (3, 5), "items": (2, 3), "money": (10000, 15000)},
}

# ---- 👹 區域 BOSS 的報酬照第幾區縮放 (2026-11-23 使用者選 B：第 1 區少、越深越多，第 5 區回到原本) ----
#      起因：前期經濟模擬，1 張 R 卡就能 96% 打完第 1 區、一局帶回約 4 萬，第 1 區變成最快的賺錢法
BOSS_MONEY_SCALE = (0.3, 0.175)   # BOSS 賽錢 × (0.3 + 0.175 × (區 − 1))：第 1 區 ×0.3、第 5 區 ×1、第 9 區 ×1.7 (之後照樣變多)
BOSS_TREASURES_EARLY = {1: (1, 2), 2: (2, 3), 3: (2, 4)}   # 寶物個數；第 4 區起照 REWARDS["boss"]["treasures"]


def boss_money_mult(zone: int) -> float:
    a, b = BOSS_MONEY_SCALE
    return a + b * (max(1, zone) - 1)


def boss_treasure_range(zone: int) -> tuple[int, int]:
    return BOSS_TREASURES_EARLY.get(zone, REWARDS["boss"]["treasures"])


# ---- 🎪 活動關卡 (docs/ura.md「活動融入」B 組，使用者 2026-11-20) ----
FEST_STAGE_CHANCE = 0.1         # 活動期間每一關有 10% 其中一扇門變成 🎪 活動門
FEST_ZONE_CAP = 2               # 每區最多 2 扇
FEST_ROOM_TYPES = ("battle", "elite", "chest", "event")   # 有活動版的房間 (陷阱沒有；商人關、BOSS 關不換)
FEST_BOSS_CHANCE = 0.25         # 🎪 精英門換成活動 BOSS (一局最多一次)
FEST_BOSS_MULT = (6, 1.5, 1.4)  # 活動 BOSS HP / ATK / DEF (跟同一區一般怪比；區域 BOSS 是 10 / 1.6 / 1.5)
FEST_TREASURE_SLOT = ((0, 20), (1, 70), (2, 10))   # 🎪 活動保留格：本來就會掉寶物時多擲 (0 / 1 / 2 個)
FEST_BOSS_TREASURE_SLOT = ((1, 80), (2, 20))       # 活動 BOSS 一定掉
FEST_RELIC_CHANCE = 0.5         # 🎪 房間掉法具時換成活動法具的機率

# ---- 👹 區域 BOSS 第 2 區起 (使用者 2026-11-21 選 T3；docs/ura.md「🧪 深區 BOSS 放招」) ----
#      招式照 enemies.json 的 deep_order 開放：第 2～5 區 1 招、6～10 區 2 招…；數值 × 0.8；每 4 回合才放一次；本身沒有閃避
DEEP_BOSS_SKILL_SCALE = 0.8
DEEP_BOSS_SKILL_EVERY = 4
DEEP_BOSS_UNLOCK_ZONES = 5


def deep_boss_skill_count(zone: int) -> int:
    """第 zone 區 (>= 2) 的區域 BOSS 開放幾招：第 2～5 區 1、6～10 區 2、11～15 區 3…"""
    return (zone - 1) // DEEP_BOSS_UNLOCK_ZONES + 1


# ---- 📖 怪物圖鑑的全收獎勵 (賽錢, 經驗)；使用者 2026-11-21 定 ----
BESTIARY_REWARDS = {"zone": (200000, 500), "all": (500000, 750), "fest": (100000, 300)}
CHESTS = {
    "normal": {"money": (1000, 3000), "materials": (3, 5), "items": (1, 2), "relic_chance": 0.15, "treasures": (1, 3), "table": "chest"},
    "locked": {"money": (3000, 5000), "materials": (3, 5), "items": (2, 3), "relic_chance": 0.7, "treasures": (2, 5), "table": "locked"},
}
MIMIC_ITEMS, MIMIC_RELICS = (3, 5), (1, 2)
MIMIC_TREASURES = (2, 5)        # 寶箱怪的寶物個數跟上鎖寶箱一樣 2～5 (SSR 起跳；使用者 2026-11-20)
MERCHANT_KINDS, MERCHANT_QTY, MERCHANT_MARKUP = 4, (1, 3), 1.2
MERCHANT_RELIC_CHANCE = 0.3
MERCHANT_RELIC = (("SSR", 0.8, 30000), ("UR", 0.2, 150000))

# 寶物：第 1 區的機率 (之後照曲線往 LR 移)
TREASURE_BASE = {
    "monster": {"N": 32, "R": 30, "SR": 22, "SSR": 10, "UR": 5, "LR": 1},
    "chest": {"R": 35, "SR": 35, "SSR": 18, "UR": 11, "LR": 1},
    "locked": {"SR": 54, "SSR": 28, "UR": 16.5, "LR": 1.5},
    "boss": {"SSR": 60, "UR": 37, "LR": 3},
}
CURVE_X = 0.12
GUARANTEED_PER_100 = {"LR": 2, "UR": 5}


def zone_of(floor: int) -> int:
    """第幾區 (第 1～10 關 = 1)"""
    return (max(1, floor) - 1) // 10 + 1


def floor_in_zone(floor: int) -> int:
    """這一區的第幾關 (1～10)"""
    return (floor - 1) % 10 + 1


def zone_mult(zone: int) -> float:
    if zone <= 5:
        return 1 + 0.1875 * (zone - 1) ** 2
    return 4 + 0.5 * (zone - 5)


def enemy_stats(zone: int, kind: str, mods: dict | None = None) -> tuple[float, float, float]:
    """(HP, ATK, DEF)；DEF 只長一半；kind = normal / elite / mimic / boss / fest_boss (🎪 活動 BOSS)；mods = 敵人自己的倍率"""
    k = zone_mult(zone)
    hp, atk, df = ENEMY_BASE[0] * k, ENEMY_BASE[1] * k, ENEMY_BASE[2] * (1 + (k - 1) / 2)
    if kind in ("elite", "mimic"):
        hp, atk, df = hp * ELITE_MULT[0], atk * ELITE_MULT[1], df * ELITE_MULT[2]
    elif kind == "boss":
        hp, atk, df = hp * BOSS_MULT[0], atk * BOSS_MULT[1], df * BOSS_MULT[2]
    elif kind == "fest_boss":
        hp, atk, df = hp * FEST_BOSS_MULT[0], atk * FEST_BOSS_MULT[1], df * FEST_BOSS_MULT[2]
    mods = mods or {}
    return hp * mods.get("hp", 1), atk * mods.get("atk", 1), df * mods.get("def", 1)


def dmg_reduction(defense: float) -> float:
    """減傷 = 60% × (1 − e^(−DEF / 20))，永遠不超過 60%"""
    return 0.6 * (1 - math.exp(-max(0.0, defense) / 20))


def comp_mult(completeness: float) -> float:
    """完整度 ➔ 數值倍率 (0.3 = ×0.8、1.0 = ×1.2，線性)"""
    return 0.8 + 0.4 * (completeness - 0.3) / 0.7


def round_half(x: float) -> int:
    """四捨五入 (0.5 進位)"""
    return int(math.floor(x + 0.5))


def spell_cooldown(cd: int, completeness: float) -> int:
    """完整度 > 0.8：冷卻 × 0.9 無條件捨去，最少 1"""
    if completeness > 0.8:
        return max(1, math.floor(cd * 0.9))
    return cd


def sanity_per_floor(zone: int, guide: bool) -> int:
    base = 10 + 5 * (zone - 1)
    return round_half(base * (1 - GUIDE_DISCOUNT)) if guide else base


def flee_cost(zone: int, guide: bool, kind: str) -> int:
    """逃跑扣的常識度 = 打折後的每關扣量 × 2.5 (一般) / × 4 (精英)"""
    base = 10 + 5 * (zone - 1)
    per = base * (1 - GUIDE_DISCOUNT) if guide else base
    return round_half(per * FLEE_MULT.get(kind, 2.5))


def persuade_chance(floor: int, kind: str) -> float:
    """糰子：一般怪 (100 − 關) / 100、精英 (100 − 關 × 1.2) / 100、BOSS 破綻 (100 − 關 × 1.5) / 100，最低 1%"""
    k = {"normal": 1.0, "elite": 1.2, "mimic": 1.2, "boss": 1.5}.get(kind, 1.0)
    return max(0.01, (100 - floor * k) / 100)


def weighted_count(lo: int, hi: int, rng) -> int:
    """「數量越多機率越低」：線性遞減權重 (1～3 ➔ 3 : 2 : 1)"""
    ks = list(range(lo, hi + 1))
    return rng.choices(ks, weights=list(range(len(ks), 0, -1)))[0]


def money_roll(lo: int, hi: int, rng, mult: float = 1.0) -> int:
    """範圍內平均隨機，取 10 的倍數"""
    lo10, hi10 = math.ceil(lo * mult / 10), math.floor(hi * mult / 10)
    return rng.randint(lo10, max(lo10, hi10)) * 10


def depth(zone: int) -> float:
    """會變平的深度函數 g(a) = a / (1 + (a / 9.81)^7.4)^(1 / 7.4)"""
    return zone / (1 + (zone / 9.81) ** 7.4) ** (1 / 7.4)


def rarity_table(table: str, zone: int) -> dict:
    """寶物 / 法具的階級機率 (總和 1)：p ∝ 第 1 區機率 × e^(k × 階級序號)，k = 0.12 × (g(區) − 1)"""
    base = TREASURE_BASE[table]
    k = CURVE_X * (depth(zone) - 1)
    raw = {r: p * math.exp(k * RARITIES.index(r)) for r, p in base.items()}
    total = sum(raw.values())
    return {r: v / total for r, v in raw.items()}


def roll_rarity(table: str, zone: int, rng) -> str:
    t = rarity_table(table, zone)
    return rng.choices(list(t), weights=list(t.values()))[0]


def relic_tier_table(zone: int) -> dict:
    """法具：所有來源都用 BOSS 那張 SSR 起跳的表"""
    return rarity_table("boss", zone)


def mimic_money(zone: int) -> int:
    return round_half(10000 * (1 + ((zone - 1) / 10) ** 2))


def exp_mult(zone: int) -> float:
    """經驗的區域倍率 1 + (區域數 − 1) / 10 (第 1 區 ×1、第 5 區 ×1.4、第 10 區 ×1.9)"""
    return 1 + (zone - 1) / 10


def exp_for(kind: str, zone: int) -> int:
    return round_half(EXP_KILL.get(kind, 0) * exp_mult(zone))


def exp_floor(zone: int) -> int:
    return round_half(EXP_FLOOR * exp_mult(zone))


def pick_weighted(table, rng) -> int:
    """((值, 權重), ...) 抽一個值 (活動保留格的 0 / 1 / 2 個)"""
    return rng.choices([v for v, _ in table], weights=[w for _, w in table])[0]

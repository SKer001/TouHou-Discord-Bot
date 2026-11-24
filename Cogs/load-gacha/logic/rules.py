"""
🎴 抽卡的純規則 (不碰 Discord、不讀寫資料庫)：卡池資料 GACHA_POOL / THUMBNAILS、⛩️ 祈願規則 (機率、UR 曲線、保底、抽卡)、
⚗️ 合成 / 🔮 融合規則、📊 機率表的資料計算
(從 Cogs/load-gacha/gacha.py 拆出來；gacha.py 會把這裡的名字全部轉出去)

⚠️ GACHA_POOL、THUMBNAILS、RARITY_ORDER 只在這裡定義一次，其他子模組都從這裡匯入 (同一個物件)
"""
import json
import os
import random
import uuid
from datetime import datetime

from Utils.gacha_pools import GACHA_POOLS, load_gacha_pool
from Database.events import pool_open_events   # 🎪 event_only 卡池 (紅魔鄉) 是哪個活動開放的

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Cogs/load-gacha (這個檔在 logic/ 裡，多退一層；值跟拆開前一樣)
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
THUMBNAILS_FILE = os.path.join(PROJECT_ROOT, "images", "Thumbnails.json")

# 🎰 卡池定義 GACHA_POOLS 與 load_gacha_pool 在 Utils/gacha_pools.py (稱號的卡池收集也要用)


# 角色資料在載入 Cog 時讀取一次；改了 Characters/ 之後用 /admin-sys reload 重新載入本模組
GACHA_POOL = load_gacha_pool()
if not GACHA_POOL:
    print("❌ [Gacha Error] Characters/ 中沒有任何可祈願的角色")

# 🖼️ 讀取 Thumbnails.json：{"角色ID": "圖片URL", ..., "fill": "預設圖URL"}
try:
    with open(THUMBNAILS_FILE, "r", encoding="utf-8") as f:
        THUMBNAILS = json.load(f)
except (json.JSONDecodeError, FileNotFoundError) as e:
    print(f"❌ [Gacha Error] 讀取 {THUMBNAILS_FILE} 失敗：{e}")
    THUMBNAILS = {}

RARITY_ORDER = {"N": 0, "R": 1, "SR": 2, "SSR": 3, "UR": 4, "LR": 5}

def sort_cards(cards: list) -> list:
    return sorted(cards, key=lambda c: (
        RARITY_ORDER.get(c.get("rarity", "N"), 0),
        c.get("character_key", ""),
        c.get("completeness", 0.0),
        c.get("obtained_at", "")
    ))


# ================= ⛩️ 祈願規則 =================
DRAW_COST = 5000                 # 每抽賽錢 (十連 = 10 倍，沒有折扣；2026-11-05 使用者指定)
EVENT_POOL = "event"             # /card gacha 的「活動限定卡池」選項；實際卡池 = 進行中活動的 gacha.pool (Events/README.md)


def event_pools(rules: dict | None) -> dict:
    """進行中的活動限定卡池 {卡池 key: {"key", "event", "events", "from", "name", "desc", "characters"}}
    (Database/events.game_rules；每個活動各一個，可以同時好幾個，2026-11-24)"""
    return (rules or {}).get("gacha_event_pools") or {}


def draw_cost(draw_count: int, mult: float = 1.0) -> int:
    """祈願價格 (活動可以用 modifiers.gacha_cost 調整)"""
    return round(draw_count * DRAW_COST * mult)


# 🎲 抽卡機率 (2026-11-22 使用者定案)：每一抽「先抽階級、再從卡池裡有這個階級的角色平均抽一位」，所有卡池同一張表
RARITIES = ["N", "R", "SR", "SSR", "UR", "LR"]
BASE_RATES = {"N": 43.9, "R": 27, "SR": 18, "SSR": 10.9, "UR": 0.1, "LR": 0.1}   # 起始機率 (%)
# 🎯 UR 動態機率：第 n 抽 = 距離上次 UR 的第幾抽 (since_ur + 1)
#    1～80 抽 0.1% ➔ 81～90 抽從 0.1% 線性升到 2.5% ➔ 91～99 抽從 2.5% 升到 3.7% ➔ 第 100 抽必出 UR
#    累積：80 抽 7.7%、90 抽 20%、99 抽 40%，約 60% 的人吃到保底；UR 多出來的機率從 N / R / SR 照比例扣
UR_CURVE = ((80, 0.1), (90, 2.5), (99, 3.7))   # (第幾抽, 那一抽的 UR %)，中間線性
PITY_THRESHOLD = 100             # 第 100 抽必出 UR
PITY_RARITY = "UR"
CURVE_SOURCES = ("N", "R", "SR")   # UR 升高時從這幾個階級照比例扣
LUCKY_WITHIN = 90                # 🍀 卡池運氣稱號：距離上次 UR 90 抽內就出 UR (ps:tenpull_2ur:<卡池>，沿用舊的計數)


def ur_curve(n: int) -> float:
    """第 n 抽 (距離上次 UR) 的 UR 機率 (%)，沒有活動、卡池階級齊全時；第 100 抽 = 100"""
    if n >= PITY_THRESHOLD:
        return 100.0
    if n <= UR_CURVE[0][0]:
        return UR_CURVE[0][1]
    for (n0, p0), (n1, p1) in zip(UR_CURVE, UR_CURVE[1:]):
        if n <= n1:
            return p0 + (p1 - p0) * (n - n0) / (n1 - n0)
    return UR_CURVE[-1][1]


def base_rates(rules: dict | None = None) -> dict:
    """起始機率 (%)：活動的 gacha.rarity_weights {階級: %} 有寫的階級取代 (沒寫的照舊)，再換算成總和 100"""
    rates = dict(BASE_RATES)
    override = (rules or {}).get("gacha_rarity_weights")
    if isinstance(override, dict):   # 舊格式 [低, 中, 高] 已經不適用，直接忽略
        rates.update({r: max(0.0, float(v)) for r, v in override.items() if r in rates})
    total = sum(rates.values())
    return {r: v * 100 / total for r, v in rates.items()} if total else dict(BASE_RATES)


def pool_characters(pool_key: str, rules: dict | None = None) -> list[str]:
    """卡池裡的角色；活動卡池 (event_xxx) 用活動檔列的角色 (一般卡池的角色都可以放)；
    活動開放的一般卡池 (gacha.pool.from，characters = None) 就是那個卡池本來的角色"""
    event_pool = event_pools(rules).get(pool_key)
    if event_pool and event_pool.get("characters") is not None:
        return [k for k in event_pool["characters"] if k in GACHA_POOL]
    return [k for k, v in GACHA_POOL.items() if v["pool"] == pool_key]


def pool_holders(pool_key: str, rules: dict | None = None) -> dict:
    """{階級: [卡池裡有這個階級的角色]} (沒有角色的階級不會出現)"""
    holders = {}
    for k in pool_characters(pool_key, rules):
        for r in GACHA_POOL[k]["rarities"]:
            holders.setdefault(r, []).append(k)
    return {r: holders[r] for r in RARITIES if r in holders}


def rarity_table(pool_key: str, n: int, rules: dict | None = None, holders: dict | None = None) -> dict:
    """
    第 n 抽 (距離上次 UR 的第幾抽) 各階級的機率 {階級: 0～1}，總和 1 (抽卡、下一抽顯示、機率表、市值都用這個)
    - 起始機率 = base_rates (活動可以改)；UR 照 ur_curve 升高，多出來的從 N / R / SR 照比例扣
    - 第 100 抽：UR 100% (保底)
    - 卡池裡沒有角色的階級：那一份照比例分給其他階級 (UR 照曲線不變)；卡池沒有 UR ➔ 沒有 UR 也沒有保底
    """
    holders = pool_holders(pool_key, rules) if holders is None else holders
    table = {r: 0.0 for r in RARITIES}
    if not holders:
        return table
    has_ur = PITY_RARITY in holders
    if has_ur and n >= PITY_THRESHOLD:
        table[PITY_RARITY] = 1.0
        return table
    rates = base_rates(rules)
    if has_ur:   # UR 升高的部分從 N / R / SR 照比例扣 (扣到 0 為止)
        source = sum(rates[r] for r in CURVE_SOURCES)
        bonus = min(ur_curve(n) - ur_curve(1), source)
        if source > 0:
            for r in CURVE_SOURCES:
                rates[r] -= bonus * rates[r] / source
            rates[PITY_RARITY] += bonus
    ur = min(rates[PITY_RARITY], 100.0) if has_ur else 0.0
    others = {r: rates[r] for r in RARITIES if r != PITY_RARITY and r in holders}
    rest = sum(others.values())
    if not rest:   # 只剩 UR 抽得到
        table[PITY_RARITY] = 1.0
        return table
    table[PITY_RARITY] = ur / 100
    for r, v in others.items():
        table[r] = (100 - ur) / 100 * v / rest
    return table


def next_ur_rate(pool_key: str, since_ur: int, rules: dict | None = None) -> float:
    """下一抽出 UR 的機率 (0～1)"""
    return rarity_table(pool_key, since_ur + 1, rules)[PITY_RARITY]


def rate_text(p: float) -> str:
    """機率顯示：0.001 ➔ 0.1%、0.01544 ➔ 1.54%、1 ➔ 必出"""
    if p >= 1:
        return "必出"
    return f"{p * 100:.2f}".rstrip("0").rstrip(".") + "%"


def ur_cycle_stats(pool_key: str, rules: dict | None = None) -> dict:
    """
    UR 週期 (從上次 UR 算起) 的統計，照 rarity_table 逐抽算：
    {"cum": {第 n 抽: n 抽內出 UR 的累積機率}, "pity": 吃到保底的比例, "avg": 平均幾抽一張 UR,
     "rates": {階級: 長期平均每抽機率 (含 UR 曲線與保底)}}；卡池沒有 UR ➔ avg None、pity 0
    """
    holders = pool_holders(pool_key, rules)
    has_ur = PITY_RARITY in holders
    reach, draws, acc, cum = 1.0, 0.0, {r: 0.0 for r in RARITIES}, {}
    for n in range(1, PITY_THRESHOLD + 1):
        table = rarity_table(pool_key, n, rules, holders)
        draws += reach
        for r in RARITIES:
            acc[r] += reach * table[r]
        reach *= 1 - table[PITY_RARITY]
        cum[n] = 1 - reach
    return {"cum": cum, "pity": (1 - cum[PITY_THRESHOLD - 1]) if has_ur else 0.0, "avg": draws if has_ur else None,
            "rates": {r: acc[r] / draws for r in RARITIES}}


def card_rates(pool_key: str, rules: dict | None = None) -> dict:
    """{(角色, 階級): 長期平均每抽抽中的機率 (含 UR 曲線與保底)}；同階級的角色平分 (活動 rate_up 照權重分)"""
    rate_up = (rules or {}).get("gacha_rate_up") or {}
    rates = ur_cycle_stats(pool_key, rules)["rates"]
    result = {}
    for r, keys in pool_holders(pool_key, rules).items():
        weights = {k: rate_up.get(k, 1.0) for k in keys}
        total = sum(weights.values())
        for k in keys:
            if total and rates[r] > 0:
                result[(k, r)] = rates[r] * weights[k] / total
    return result


def expected_cards(pool_key: str, count: int, rules: dict | None = None) -> dict:
    """count 抽預期抽到的張數 {(角色, 階級): 張數}，照長期平均機率 (card_rates，含 UR 曲線與保底)。
    活動卡池用：浮動市值的「預期新抽到張數」本來只看一般卡池，活動卡池的抽數要靠這個記進去"""
    return {key: count * p for key, p in card_rates(pool_key, rules).items()}


def roll_pool_cards(pool_key: str, count: int, since_ur: int, make_completeness, rules: dict | None = None) -> tuple[list, int, bool]:
    """
    依保底計數擲出 count 張卡：(cards, 新的 since_ur, 是否出了 UR)
    每一抽先照 rarity_table 抽階級，再從卡池裡有這個階級的角色抽一位 (活動 rate_up = 角色權重倍率)
    只有 UR 會重置保底計數 (LR 固定 0.1%，不影響保底)
    卡牌多帶兩個只用於顯示 / 統計、不寫入資料庫的欄位："pity" (保底送的)、"lucky" (90 抽內出的 UR，🍀 運氣稱號)
    rules = 活動規則 (econ.get_rules)：gacha_rate_up {角色: 權重倍率}、gacha_rarity_weights {階級: %} 取代起始機率、
            gacha_event_pools (pool_key 是活動卡池時用它的角色清單)
    """
    rules = rules or {}
    rate_up = rules.get("gacha_rate_up") or {}
    holders = pool_holders(pool_key, rules)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cards, got_ur = [], False

    for _ in range(count):
        since_ur += 1
        table = rarity_table(pool_key, since_ur, rules, holders)
        population = [r for r in RARITIES if table[r] > 0]
        rarity = random.choices(population, weights=[table[r] for r in population], k=1)[0]
        keys = holders[rarity]
        if any(k in rate_up for k in keys):
            char_key = random.choices(keys, weights=[rate_up.get(k, 1.0) for k in keys], k=1)[0]
        else:
            char_key = random.choice(keys)
        pity = rarity == PITY_RARITY and since_ur >= PITY_THRESHOLD
        lucky = rarity == PITY_RARITY and since_ur <= LUCKY_WITHIN
        if rarity == PITY_RARITY:
            since_ur, got_ur = 0, True

        char_data = GACHA_POOL[char_key]
        cards.append({
            "instance_id": f"c_{char_data['uuid'][:4]}_{uuid.uuid4().hex[:12]}",
            "character_key": char_key,
            "name": char_data["name"],
            "emoji": char_data["emoji"],
            "rarity": rarity,
            "title": char_data["titles"][rarity],
            "completeness": make_completeness(),
            "obtained_at": now,
            "pity": pity,
            "lucky": lucky,
        })
    return cards, since_ur, got_ur


# ================= ⚗️ 合成 / 🔮 融合規則 =================
# 合成增幅上限：依「較低那張」的小數位數決定 (完整度下限, 增幅上限)，由高到低比對
SYNTHESIS_CAPS = [
    (0.1, 0.2),      # 0.x
    (0.01, 0.05),    # 0.0x
    (0.001, 0.01),   # 0.00x
    (0.0, 0.005),    # 0.000x
]
# 完整度一模一樣時的加倍機率；差距越大機率越低 (× (1 - 相對差距)²)
SYNTHESIS_DOUBLE_CHANCE = {"N": 0.99, "R": 0.50, "SR": 0.30, "SSR": 0.15, "UR": 0.10, "LR": 0.05}
FUSION_COUNT = 3              # 融合需要的卡牌張數
AUTOCOMPLETE_LIMIT = 25        # Discord autocomplete 最多 25 個選項


def is_perfect(card: dict) -> bool:
    return round(card["completeness"], 4) >= 1.0


def can_synthesize(card_a: dict, card_b: dict) -> bool:
    """同角色、同階級、不同張，且兩張都還沒到 1.0000 (滿了就無法再「大於」)"""
    return (
        card_a["instance_id"] != card_b["instance_id"]
        and card_a["character_key"] == card_b["character_key"]
        and card_a["rarity"] == card_b["rarity"]
        and not is_perfect(card_a)
        and not is_perfect(card_b)
    )


def calc_synthesis(comp_a: float, comp_b: float, rarity: str) -> dict:
    """
    合成完整度計算 (結果還沒擲加倍)：新完整度 = 較高的那張 + 增幅
    - 增幅上限依較低那張的位數：0.x ➔ 0.2、0.0x ➔ 0.05、0.00x ➔ 0.01、0.000x ➔ 0.005
    - 相對差距 d = |a - b| / 較高那張 (0 = 一模一樣)，越接近越划算
    - 增幅 = 上限 × (1 - d)；加倍機率 = 階級機率 × (1 - d)²
    - 增幅至少 0.0001 (保證新卡一定比兩張都高)，新完整度不超過 1.0000
    """
    a, b = round(comp_a, 4), round(comp_b, 4)
    low, high = min(a, b), max(a, b)
    cap = next(c for floor, c in SYNTHESIS_CAPS if low >= floor)
    d = (high - low) / high if high > 0 else 0.0

    def apply(increase: float) -> tuple[float, float]:
        new = round(min(1.0, high + max(0.0001, round(increase, 4))), 4)
        return new, round(new - high, 4)   # 實際增幅 (被 1.0000 封頂時會變小)

    normal, normal_inc = apply(cap * (1 - d))
    doubled, doubled_inc = apply(cap * (1 - d) * 2)
    return {
        "normal_completeness": normal,
        "normal_increase": normal_inc,
        "doubled_completeness": doubled,
        "doubled_increase": doubled_inc,
        "double_chance": SYNTHESIS_DOUBLE_CHANCE.get(rarity, 0.0) * (1 - d) ** 2,
    }


def roll_synthesis(comp_a: float, comp_b: float, rarity: str) -> dict:
    """擲加倍，回傳最終結果 {"new_completeness", "increase", "doubled"}"""
    calc = calc_synthesis(comp_a, comp_b, rarity)
    doubled = random.random() < calc["double_chance"]
    key = "doubled" if doubled else "normal"
    return {
        "new_completeness": calc[f"{key}_completeness"],
        "increase": calc[f"{key}_increase"],
        "doubled": doubled,
    }


def synthesized_card(a: dict, completeness: float, now: str | None = None) -> dict:
    """合成出來的新卡 (角色、階級、稱號照素材 a；卡牌 ID 是新的)"""
    prefix = a["instance_id"].split("_")[1]
    return {
        "instance_id": f"c_{prefix}_{uuid.uuid4().hex[:12]}",
        "character_key": a["character_key"],
        "name": a["name"],
        "emoji": a["emoji"],
        "rarity": a["rarity"],
        "title": a["title"],
        "completeness": completeness,
        "obtained_at": now or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------- ⚡ 自動合成全部 (2026-11-23 使用者定案) ----------------
def auto_synthesis_preview(cards: list) -> dict:
    """{階級: 未滿 1.0000 的張數}，只列至少 2 張 (合得起來) 的階級，階級由低到高；確認畫面「R：12 張 ➔ 最多合成 11 次」"""
    counts = {}
    for c in cards:
        if not is_perfect(c):
            counts[c["rarity"]] = counts.get(c["rarity"], 0) + 1
    return {r: counts[r] for r in sorted(counts, key=lambda r: RARITY_ORDER.get(r, 0)) if counts[r] >= 2}


def run_auto_synthesis(cards: list, roll=None, now: str | None = None) -> dict:
    """
    ⚡ 自動合成全部 (純邏輯，cards = 一位角色、卡冊裡的卡，依取得順序)：
    - 每個階級各自合：每次拿完整度最低的兩張 (一樣低先拿比較早取得的)，新卡放回去繼續比
    - 合到 1.0000 的不再參加；合到只剩一張未滿 1.0000 為止；每次照樣 roll_synthesis 擲加倍
    回傳 {"consumed": [用掉的原本卡牌 ID], "created": [最後留下的新卡], "count": 合成次數,
          "rarities": {階級: {"before" 張數, "count" 合成次數, "doubled" 加倍次數, "perfect" 合到 1.0000 的張數,
                             "last" 剩下那張未滿 1.0000 的完整度 (都合滿了 = None)}}}
    中間合出來又被拿去合的卡不在 created 裡 (不會寫進資料庫)
    """
    roll = roll or roll_synthesis
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    groups = {}
    for seq, c in enumerate(cards):
        if not is_perfect(c):
            groups.setdefault(c["rarity"], []).append((seq, c))
    consumed, created, rarities = [], [], {}
    seq_next = len(cards)
    for rarity in sorted(groups, key=lambda r: RARITY_ORDER.get(r, 0)):
        pool = groups[rarity]
        if len(pool) < 2:
            continue
        info = {"before": len(pool), "count": 0, "doubled": 0, "perfect": 0, "last": None}
        made = {}   # 這個階級合出來、還留著的新卡
        while len(pool) >= 2:
            pool.sort(key=lambda sc: (round(sc[1]["completeness"], 4), sc[1].get("obtained_at") or "", sc[0]))
            (_, a), (_, b) = pool[0], pool[1]
            pool = pool[2:]
            result = roll(a["completeness"], b["completeness"], rarity)
            new = synthesized_card(a, result["new_completeness"], now)
            for x in (a, b):
                if made.pop(x["instance_id"], None) is None:   # 原本的卡 (中間合出來的卡直接丟掉，不用刪資料庫)
                    consumed.append(x["instance_id"])
            made[new["instance_id"]] = new
            info["count"] += 1
            info["doubled"] += bool(result["doubled"])
            if is_perfect(new):
                info["perfect"] += 1   # 合到 1.0000 就不再參加
            else:
                pool.append((seq_next, new))
                seq_next += 1
        info["last"] = round(pool[0][1]["completeness"], 4) if pool else None
        created += list(made.values())
        rarities[rarity] = info
    return {"consumed": consumed, "created": created, "count": sum(i["count"] for i in rarities.values()),
            "rarities": rarities}


def get_next_rarity(card: dict) -> str | None:
    """依卡池中該角色的三個階級找出高一階；已是最高階或角色不在卡池 ➔ None"""
    char_data = GACHA_POOL.get(card["character_key"])
    if not char_data or card["rarity"] not in char_data["rarities"]:
        return None
    idx = char_data["rarities"].index(card["rarity"])
    if idx + 1 >= len(char_data["rarities"]):
        return None
    return char_data["rarities"][idx + 1]


def find_fusion_groups(cards: list) -> dict:
    """{(角色, 階級): [滿完整度的卡, ...]}，只留下張數足夠且還能升階的組合"""
    groups = {}
    for card in cards:
        if is_perfect(card) and get_next_rarity(card):
            groups.setdefault((card["character_key"], card["rarity"]), []).append(card)
    return {k: v for k, v in groups.items() if len(v) >= FUSION_COUNT}


# ================= 📊 機率表 (只有按的人看得到) =================
def is_event_only(pool_key: str) -> bool:
    """平常不能抽、只在活動期間從「🎪 活動限定卡池」開放的一般卡池 (GACHA_POOLS 的 event_only，例 th06)"""
    return bool(GACHA_POOLS.get(pool_key, {}).get("event_only"))


def resolve_pool(choice_key: str, rules: dict) -> tuple[str, str] | None:
    """
    卡池選項 ➔ (實際卡池 key, 名稱)；抽卡、繼續祈願、機率表都用這個
    - "event"：進行中的活動卡池剛好一個 ➔ 那個；一個都沒有或好幾個 ➔ None (好幾個時 execute_gacha 先跳選單)
    - event_<id> / event_only 的一般卡池 (th06)：要是進行中活動的卡池才行，不然 ➔ None
    - 活動開放的一般卡池 (gacha.pool.from)：key 就是那個卡池 (保底照舊記在那裡)，名稱 = 「🎪 🔴 紅魔鄉卡池・紅霧異變限定」
    """
    pools = event_pools(rules)
    if choice_key == EVENT_POOL:
        if len(pools) != 1:
            return None
        choice_key = next(iter(pools))
    if choice_key in pools:
        return choice_key, pools[choice_key]["name"]
    if choice_key.startswith(f"{EVENT_POOL}_") or is_event_only(choice_key):
        return None
    return choice_key, GACHA_POOLS.get(choice_key, {}).get("name", "📦 其他")


def rate_sheet_data(pool_key: str, pool_name: str, rules: dict, since_ur: int) -> dict:
    """機率表要顯示的數字 (全部照 rarity_table 算，活動改了機率也會跟著變)"""
    holders = pool_holders(pool_key, rules)
    table = lambda n: rarity_table(pool_key, n, rules, holders)
    stats = ur_cycle_stats(pool_key, rules)
    marks = [n for n, _ in UR_CURVE]   # 80 / 90 / 99
    members = pool_characters(pool_key, rules)
    rate_up = {k: m for k, m in (rules.get("gacha_rate_up") or {}).items() if k in members and m != 1}
    return {
        "pool_name": pool_name,
        "start": table(1),
        "holders": {r: [GACHA_POOL[k]["name"] for k in keys] for r, keys in holders.items()},
        "has_ur": PITY_RARITY in holders,
        "curve": {n: table(n)[PITY_RARITY] for n in marks},
        "cum": {n: stats["cum"][n] for n in marks},
        "pity": stats["pity"],
        "avg": stats["avg"],
        "long_run": stats["rates"],
        "since_ur": since_ur,
        "next": table(since_ur + 1)[PITY_RARITY],
        "event_pool": pool_key.startswith(f"{EVENT_POOL}_"),
        "open_note": open_note(pool_key),
        "event_rates": isinstance(rules.get("gacha_rarity_weights"), dict),
        "rate_up": {GACHA_POOL[k]["name"]: m for k, m in rate_up.items()},
    }


def open_note(pool_key: str) -> str:
    """event_only 卡池的「🎪 紅霧異變期間開放」(哪些活動檔寫了 gacha.pool.from = 這個卡池)；其他卡池 ➔ 空字串"""
    if not is_event_only(pool_key):
        return ""
    names = pool_open_events(pool_key)
    return f"🎪 {'、'.join(names)}期間開放" if names else "🎪 活動期間開放"

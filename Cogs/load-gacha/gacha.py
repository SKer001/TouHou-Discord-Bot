import discord
from discord import ui
from discord.ext import commands
from discord import app_commands
import importlib
import json
import os
import random
import uuid
from datetime import datetime

from Database import Economy_DB_Manager as econ
from Utils import card_cache   # autocomplete 專用的卡冊快取
from Database.User_DB_Manager import (
    get_user_cards, transform_cards, draw_gacha, get_gacha_pity, get_gacha_stats, InsufficientFunds,
    get_album_cards, set_cards_locked, auto_synthesize_cards,
)
from .Components.gacha_components import (
    STACKS_PER_PAGE,
    STACK_CARDS_PER_PAGE,
    build_gacha_single_container,
    build_gacha_ten_container,
    build_gacha_history_container,
    build_rate_sheet_container,
    build_stack_list_container,
    build_stack_cards_container,
    build_card_detail_container,
    build_album_container,
    ALBUM_PER_PAGE,
    build_synthesis_preview_container,
    build_synthesis_result_container,
    build_auto_synthesis_preview_container,
    build_auto_synthesis_result_container,
    build_fusion_preview_container,
    build_fusion_result_container,
)
from Utils.components import send_notice, notice_view
from Utils.pagination import nav_buttons, paginate   # 📄 共用分頁
from Utils.gacha_pools import GACHA_POOLS, load_gacha_pool
from Database.events import pool_open_events   # 🎪 event_only 卡池 (紅魔鄉) 是哪個活動開放的
from Utils.numbers import fmt_money   # 持有金額一萬以上縮寫 (1.5M)
from Utils.guide import open_guide

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
    event_pool = (rules or {}).get("gacha_event_pool")
    if event_pool and pool_key == event_pool["key"] and event_pool.get("characters") is not None:
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
            gacha_event_pool (pool_key 是活動卡池時用它的角色清單)
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


# ================= 🎛️ 抽卡結果 View (Components V2) =================
class GachaResultView(ui.LayoutView):
    def __init__(self, user_id: int, user_name: str, gacha_cog, container: ui.Container, pool_key: str, cost_mult: float = 1.0):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.pool_key = pool_key   # 「繼續祈願」沿用同一個卡池 (活動卡池是 "event"，每次重新找進行中的活動)

        single_btn = ui.Button(label=f"🌸 繼續單抽 ({draw_cost(1, cost_mult):,})", style=discord.ButtonStyle.primary)
        single_btn.callback = self.draw_single_again
        ten_btn = ui.Button(label=f"⛩️ 繼續十連 ({draw_cost(10, cost_mult):,})", style=discord.ButtonStyle.success)
        ten_btn.callback = self.draw_ten_again
        inv_btn = ui.Button(label="🎒 查看卡庫", style=discord.ButtonStyle.secondary)
        inv_btn.callback = self.view_inventory
        # 📊 機率表：誰都可以按 (只有按的人看得到，顯示的是按的人自己的保底進度)
        self.rates_btn = ui.Button(label="📊 機率表", style=discord.ButtonStyle.secondary)
        self.rates_btn.callback = self.view_rates

        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(single_btn, ten_btn, inv_btn, self.rates_btn))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if (getattr(interaction, "data", None) or {}).get("custom_id") == self.rates_btn.custom_id:
            return True
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的祈願畫面！請輸入 `/card gacha` 開啟你自己的祈願。")
            return False
        return True

    async def draw_single_again(self, interaction: discord.Interaction):
        await self.gacha_cog.execute_gacha(interaction, draw_count=1, pool_key=self.pool_key)

    async def draw_ten_again(self, interaction: discord.Interaction):
        await self.gacha_cog.execute_gacha(interaction, draw_count=10, pool_key=self.pool_key)

    async def view_rates(self, interaction: discord.Interaction):
        await send_rate_sheet(interaction, self.pool_key)

    async def view_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cards = await get_user_cards(self.user_id)
        if not cards:
            await send_notice(interaction, "🎒 你的卡冊空空如也，快進行祈願吧！")
            return

        inv_view = InventoryView(self.user_id, sort_cards(cards), self.user_name, self.gacha_cog,
                                 owned_keys=await owned_character_keys(self.user_id))
        await interaction.edit_original_response(view=inv_view)


# ================= 📊 機率表 (只有按的人看得到) =================
def is_event_only(pool_key: str) -> bool:
    """平常不能抽、只在活動期間從「🎪 活動限定卡池」開放的一般卡池 (GACHA_POOLS 的 event_only，例 th06)"""
    return bool(GACHA_POOLS.get(pool_key, {}).get("event_only"))


def resolve_pool(choice_key: str, rules: dict) -> tuple[str, str] | None:
    """
    卡池選項 ➔ (實際卡池 key, 名稱)；抽卡、繼續祈願、機率表都用這個
    - "event" / event_<id> / event_only 的一般卡池 (th06)：要是進行中活動的卡池才行，不然 ➔ None
    - 活動開放的一般卡池 (gacha.pool.from)：key 就是那個卡池 (保底照舊記在那裡)，名稱 = 「🎪 🔴 紅魔鄉卡池・紅霧異變限定」
    """
    event_pool = rules.get("gacha_event_pool")
    if choice_key == EVENT_POOL or choice_key.startswith(f"{EVENT_POOL}_") or is_event_only(choice_key):
        if not event_pool or choice_key not in (EVENT_POOL, event_pool["key"]):
            return None
        return event_pool["key"], event_pool["name"]
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


async def send_rate_sheet(interaction: discord.Interaction, choice_key: str):
    """📊 機率表：按的時候才讀活動規則與按的人自己的保底進度"""
    rules = await econ.get_rules()
    resolved = resolve_pool(choice_key, rules)
    if not resolved or not pool_characters(resolved[0], rules):
        await send_notice(interaction, "🎪 這個卡池目前沒有開放，看不到機率表。")
        return
    pool_key, pool_name = resolved
    since_ur = (await get_gacha_pity(interaction.user.id)).get(pool_key, {}).get("since_ur", 0)
    view = ui.LayoutView()
    view.add_item(build_rate_sheet_container(rate_sheet_data(pool_key, pool_name, rules, since_ur), PITY_THRESHOLD, PITY_RARITY))
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)


def open_note(pool_key: str) -> str:
    """event_only 卡池的「🎪 紅霧異變期間開放」(哪些活動檔寫了 gacha.pool.from = 這個卡池)；其他卡池 ➔ 空字串"""
    if not is_event_only(pool_key):
        return ""
    names = pool_open_events(pool_key)
    return f"🎪 {'、'.join(names)}期間開放" if names else "🎪 活動期間開放"


class GachaHistoryView(ui.LayoutView):
    """📜 祈願紀錄 + 「📊 選卡池看機率表」選單 (誰都可以選，機率表只有選的人看得到；只列現在抽得到的卡池)"""
    def __init__(self, container: ui.Container, pools: dict):
        super().__init__(timeout=600)
        self.select = ui.Select(
            placeholder="📊 選一個卡池查看機率表",
            options=[discord.SelectOption(label=p["name"], value=key) for key, p in list(pools.items())[:25]],
        )
        self.select.callback = self.view_rates
        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(self.select))
        self.add_item(container)

    async def view_rates(self, interaction: discord.Interaction):
        await send_rate_sheet(interaction, self.select.values[0])


# ================= 🔍 單卡詳情的資料 (2026-11-23 使用者定案) =================
async def card_detail_info(card: dict, owner_id: int) -> dict:
    """
    單卡詳情 (卡冊 / 收藏冊 / 管理員看別人卡冊) 要多顯示的東西，build_card_detail_container 用：
    - "profile"：角色稱號、種族、能力、簡介 (Characters/ 的 profile)
    - "ura"：這張卡的 HP / ATK / DEF、職業、能不能出征 (跟裏世界出征一樣用 combat.make_member 算)
    - "spell"：這張卡階級那一檔的特殊能力 (效果 = ura describe.spell_text；B 點 / 冷卻 = 出征時的值)
    - "value"：分解能拿多少 (市值 × 完整度倍率 × 活動的分解倍率，跟 /market decompose 一樣)
    - "synth" / "fuse"：卡冊裡同角色同階級還有幾張能一起合成 / 湊滿幾張完美卡能融合 (收藏中、出征中的卡不算)
    """
    from Utils.character_data import load_characters
    from Database.ura import combat as ura_combat, data as ura_data, describe as ura_describe, rules as ura_rules
    cid, rarity, comp = card["character_key"], card["rarity"], float(card["completeness"])
    info = {}
    char = load_characters().get(cid) or {}
    profile = char.get("profile") or {}
    if profile:
        info["profile"] = {k: profile.get(k, "") for k in ("title", "species", "ability", "description")}
    sp = char.get("special_powers") or {}
    level = (sp.get("levels") or {}).get(rarity) or {}
    uchar = ura_data.characters().get(cid)
    if uchar and cid in ura_data.spells() and rarity in ura_rules.RARITY_MULT:
        u = ura_combat.make_member(0, card, uchar)
        info["ura"] = {"hp": ura_combat.max_hp(u), "atk": ura_describe.num(ura_combat.eff_atk(u)),
                       "def": ura_describe.num(ura_combat.eff_def(u)), "cls": ura_rules.CLASS_NAMES.get(u["cls"], u["cls"]),
                       "rarity_mult": ura_rules.RARITY_MULT[rarity], "comp_mult": ura_rules.comp_mult(comp),
                       "min": ura_rules.MIN_COMPLETENESS, "ok": comp >= ura_rules.MIN_COMPLETENESS}
        info["spell"] = {"sp_name": sp.get("name") or uchar.get("spell_name", ""), "name": level.get("name", ""),
                         "numeral": (level.get("id") or "").rsplit("_", 1)[-1], "type": level.get("type"),
                         "effect": ura_describe.spell_text(cid, u["tier"]), "b": u["b_cost"], "cd": u["cd_max"],
                         "cd_base": ura_data.spells()[cid]["cd"]}
    elif level:   # 不在裏世界資料裡的角色：照角色檔寫
        info["spell"] = {"sp_name": sp.get("name", ""), "name": level.get("name", ""),
                         "numeral": (level.get("id") or "").rsplit("_", 1)[-1], "type": level.get("type"),
                         "effect": level.get("desc", ""), "b": level.get("spent", 0), "cd": level.get("cooldown", 0),
                         "cd_base": level.get("cooldown", 0)}
    if info.get("spell"):   # ⚔️ 傷害 / 💚 治療…：跟 /character 角色頁同一份名稱 (呼叫時才取，Cog 之間不互相 import)
        names = getattr(importlib.import_module("Cogs.load-character.Components.character_components"), "SP_TYPE_NAMES", {})
        t = info["spell"]["type"]
        info["spell"]["type_name"] = names.get(t, t or "")
    rules = await econ.get_rules()
    price = econ.price_of(await econ.get_market_prices(), cid, rarity)
    mult = econ.modifier(rules, "decompose")
    info["value"] = {"price": price, "value": econ.card_value(price, comp, mult), "mult": mult}
    if not card.get("locked") and not card.get("expedition"):
        same = [c for c in await get_user_cards(owner_id)
                if c["character_key"] == cid and c["rarity"] == rarity and c["instance_id"] != card["instance_id"]]
        if is_perfect(card):
            nxt = get_next_rarity(card)
            if nxt:
                info["fuse"] = {"have": 1 + sum(1 for c in same if is_perfect(c)), "need": FUSION_COUNT, "next": nxt}
        else:
            info["synth"] = sum(1 for c in same if not is_perfect(c))
    return info


async def send_character_page(interaction: discord.Interaction, character_key: str):
    """📖 角色圖鑑：另開一則只有自己看得到的 /character 角色頁 (Cog 之間不互相 import，呼叫時才取)"""
    from Utils.character_data import load_categories
    cc = importlib.import_module("Cogs.load-character.Components.character_components")
    found = next(((ch, cat) for cat in load_categories().values() for ch in cat["characters"] if ch["id"] == character_key), None)
    if found is None:
        await send_notice(interaction, "❌ 圖鑑裡找不到這位角色。")
        return
    char, cat = found
    owned = {}   # 看的人自己的收藏 (收藏冊的卡也算)
    for c in await get_user_cards(interaction.user.id, include_locked=True):
        per = owned.setdefault(c["character_key"], {})
        per[c["rarity"]] = per.get(c["rarity"], 0) + 1
    view = ui.LayoutView()
    view.add_item(cc.build_character_container(char, cat["category_name"], THUMBNAILS, owned))
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)


# ================= 🎒 卡冊 View (Components V2) =================
# 疊卡排序方式：(key, 顯示名稱)；排序按鈕依序切換
INVENTORY_SORTS = [("rarity", "階級"), ("best", "完整度"), ("latest", "最新"), ("count", "數量")]
RARITY_FILTERS = ["ALL", "N", "R", "SR", "SSR", "UR", "LR"]
OTHER_POOL = "other"   # 角色已不在任何卡池中的卡


def card_pool_key(card: dict) -> str:
    return GACHA_POOL.get(card["character_key"], {}).get("pool", OTHER_POOL)


def build_stacks(cards: list) -> list[dict]:
    """同角色、同階級的卡疊成一疊；疊內依完整度由高到低"""
    stacks = {}
    for card in cards:
        stack = stacks.setdefault((card["character_key"], card["rarity"]), {
            "character_key": card["character_key"],
            "rarity": card["rarity"],
            "name": card["name"],
            "emoji": card.get("emoji", "🎴"),
            "title": card.get("title", ""),
            "pool": card_pool_key(card),
            "cards": [],
        })
        stack["cards"].append(card)
    for stack in stacks.values():
        stack["cards"].sort(key=lambda c: c["completeness"], reverse=True)
        stack["best"] = stack["cards"][0]["completeness"]
        stack["latest"] = max(c.get("obtained_at") or "" for c in stack["cards"])
        # 卡冊上的合成 / 融合提示 (與 find_synthesis_groups / find_fusion_groups 條件相同)
        stack["can_synth"] = sum(1 for c in stack["cards"] if not is_perfect(c)) >= 2
        stack["can_fuse"] = (
            sum(1 for c in stack["cards"] if is_perfect(c)) >= FUSION_COUNT
            and get_next_rarity(stack["cards"][0]) is not None
        )
    return list(stacks.values())


async def owned_character_keys(user_id: int) -> set[str]:
    """
    收集進度用的「已擁有角色」：卡冊 + 收藏冊 + 裏世界出征中的卡 (跟圖鑑「已擁有」、稱號、排行榜一致)
    2026-11-23 使用者定：卡冊畫面的收集進度也算收藏冊；張數、疊卡列表照舊只算卡冊裡的
    """
    return {c["character_key"] for c in await get_user_cards(user_id, include_locked=True)}


def collection_progress(owned: set) -> list[tuple[dict, int, int]]:
    """各卡池的收集進度：[(卡池設定, 已擁有角色數, 卡池角色數), ...]；owned = 擁有的角色 id"""
    result = []
    for key, pool in GACHA_POOLS.items():
        members = [k for k, v in GACHA_POOL.items() if v["pool"] == key]
        result.append((pool, sum(1 for k in members if k in owned), len(members)))
    return result


def sort_stacks(stacks: list, mode: str) -> list:
    if mode == "best":
        return sorted(stacks, key=lambda s: (-s["best"], s["character_key"]))
    if mode == "latest":
        return sorted(stacks, key=lambda s: s["latest"], reverse=True)
    if mode == "count":
        return sorted(stacks, key=lambda s: (-len(s["cards"]), -RARITY_ORDER.get(s["rarity"], 0), s["character_key"]))
    # 預設：階級由高到低，同階級依角色
    return sorted(stacks, key=lambda s: (-RARITY_ORDER.get(s["rarity"], 0), s["character_key"]))


def _stack_value(stack: dict) -> str:
    return f"{stack['character_key']}|{stack['rarity']}"


class InventoryView(ui.LayoutView):
    """
    卡冊：同一個 View 依狀態切換三種畫面
      疊卡列表 (卡池 / 階級篩選 + 排序) ➔ 單一疊的卡牌列表 ➔ 單卡詳情
    """
    def __init__(self, user_id: int, cards: list, user_name: str, gacha_cog, owner_id: int | None = None,
                 owned_keys: set | None = None):
        super().__init__(timeout=180)
        self.user_id = user_id                       # 操作畫面的人
        self.owner_id = owner_id or user_id          # 卡冊的主人 (管理員檢視別人卡冊時不同)
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.all_cards = cards
        self.all_stacks = build_stacks(cards)
        # 收集進度算的角色 (owned_character_keys：含收藏冊、出征中)；沒給就只看這些卡 (管理員畫面本來就含收藏冊)
        self.owned_keys = owned_keys if owned_keys is not None else {c["character_key"] for c in cards}

        self.pool_filter = "ALL"
        self.rarity_filter = "ALL"
        self.sort_index = 0
        self.page = 1

        self.selected_stack = None   # 疊的 value ("角色|階級")
        self.stack_page = 1
        self.selected_card = None
        self.build()

    # ---------------- 資料 ----------------
    @property
    def sort_mode(self) -> str:
        return INVENTORY_SORTS[self.sort_index][0]

    def filtered_stacks(self) -> list:
        stacks = [
            s for s in self.all_stacks
            if (self.pool_filter == "ALL" or s["pool"] == self.pool_filter)
            and (self.rarity_filter == "ALL" or s["rarity"] == self.rarity_filter)
        ]
        return sort_stacks(stacks, self.sort_mode)

    def get_stack(self, value: str) -> dict | None:
        return next((s for s in self.all_stacks if _stack_value(s) == value), None)

    def _filter_desc(self) -> str:
        pool = "全部卡池" if self.pool_filter == "ALL" else GACHA_POOLS.get(self.pool_filter, {}).get("name", "📦 其他")
        rarity = "全部階級" if self.rarity_filter == "ALL" else f"{self.rarity_filter} 階級"
        return f"篩選：{pool} · {rarity} · 排序：{INVENTORY_SORTS[self.sort_index][1]}"

    def _progress_text(self) -> str:
        return " · ".join(
            f"{p['name']} `{owned}/{total}`" for p, owned, total in collection_progress(self.owned_keys)
        )

    # ---------------- 畫面 ----------------
    def build(self):
        self.clear_items()
        if self.selected_card:
            self._build_card_detail()
        elif self.selected_stack:
            self._build_stack()
        else:
            self._build_list()

    def _button(self, label: str, callback, style=discord.ButtonStyle.primary, disabled: bool = False) -> ui.Button:
        btn = ui.Button(label=label, style=style, disabled=disabled)
        if callback is not None:   # 頁碼按鈕只是顯示用，沒有回呼
            btn.callback = callback
        return btn

    def _build_list(self):
        stacks = self.filtered_stacks()
        pg = paginate(stacks, self.page, STACKS_PER_PAGE)
        self.page, total_pages, start, page_stacks = pg.page, pg.total, pg.start, pg.items

        container = build_stack_list_container(
            page_stacks, self.page, total_pages, len(stacks), self.all_cards,
            self.user_name, THUMBNAILS, self._filter_desc(), start + 1, self._progress_text(),
        )
        container.add_item(ui.Separator())

        # 卡池篩選
        pool_options = [discord.SelectOption(label="全部卡池 (ALL)", value="ALL", default=(self.pool_filter == "ALL"))]
        pool_options += [
            discord.SelectOption(label=p["name"], value=key, description=p["desc"][:100], default=(self.pool_filter == key))
            for key, p in GACHA_POOLS.items()
        ]
        if any(s["pool"] == OTHER_POOL for s in self.all_stacks):
            pool_options.append(discord.SelectOption(label="📦 其他 (已不在卡池)", value=OTHER_POOL, default=(self.pool_filter == OTHER_POOL)))
        pool_select = ui.Select(placeholder="🎰 選擇卡池篩選...", options=pool_options)
        pool_select.callback = self.pool_select_callback
        container.add_item(ui.ActionRow(pool_select))

        # 階級篩選
        rarity_select = ui.Select(placeholder="🔍 選擇稀有度篩選...", options=[
            discord.SelectOption(label="全部階級 (ALL)" if r == "ALL" else f"{r} 階級", value=r, default=(self.rarity_filter == r))
            for r in RARITY_FILTERS
        ])
        rarity_select.callback = self.rarity_select_callback
        container.add_item(ui.ActionRow(rarity_select))

        # 當頁的疊 ➔ 點進去看這一疊的卡
        if page_stacks:
            stack_select = ui.Select(placeholder="🎴 選擇一疊卡牌查看內容...", options=[
                discord.SelectOption(
                    label=f"[{s['rarity']}] {s['name']} ×{len(s['cards'])}"[:100],
                    description=f"{s['title']} · 最高 {s['best']:.4f}"[:100],
                    value=_stack_value(s),
                    emoji=s.get("emoji") or "🎴",
                )
                for s in page_stacks
            ])
            stack_select.callback = self.stack_select_callback
            container.add_item(ui.ActionRow(stack_select))

        container.add_item(ui.ActionRow(
            *nav_buttons(self.page, total_pages, self.set_page),
            self._button(f"🔃 排序：{INVENTORY_SORTS[self.sort_index][1]}", self.sort_callback, discord.ButtonStyle.secondary),
        ))
        self.add_item(container)

    def _build_stack(self):
        stack = self.get_stack(self.selected_stack)
        cards = stack["cards"]
        pg = paginate(cards, self.stack_page, STACK_CARDS_PER_PAGE)
        self.stack_page, total_pages, start, page_cards = pg.page, pg.total, pg.start, pg.items

        container = build_stack_cards_container(
            stack, page_cards, self.stack_page, total_pages, self.user_name, THUMBNAILS, start + 1
        )
        container.add_item(ui.Separator())

        card_select = ui.Select(placeholder="🎴 選擇卡牌檢視詳細鑑定...", options=[
            discord.SelectOption(
                label=f"{start + i}. 完整度 {c['completeness']:.4f}",
                description=f"ID: {c['instance_id']}"[:100],
                value=c["instance_id"],
                emoji=c.get("emoji") or "🎴",
            )
            for i, c in enumerate(page_cards, start=1)
        ])
        card_select.callback = self.card_select_callback
        container.add_item(ui.ActionRow(card_select))

        container.add_item(ui.ActionRow(
            self._button("🔙 返回卡冊", self.back_to_list_callback, discord.ButtonStyle.secondary),
            *nav_buttons(self.stack_page, total_pages, self.set_stack_page),
        ))

        # 合成 / 融合捷徑：只有卡冊主人本人看得到 (管理員檢視別人卡冊時不顯示)
        if self.user_id == self.owner_id and (stack["can_synth"] or stack["can_fuse"]):
            shortcuts = []
            if stack["can_synth"]:
                shortcuts.append(self._button("⚗️ 合成這一疊", self.synth_shortcut_callback, discord.ButtonStyle.success))
            if stack["can_fuse"]:
                shortcuts.append(self._button(
                    f"🔮 融合 ➔ {get_next_rarity(stack['cards'][0])}", self.fuse_shortcut_callback, discord.ButtonStyle.success
                ))
            container.add_item(ui.ActionRow(*shortcuts))
        self.add_item(container)

    def _build_card_detail(self):
        container = build_card_detail_container(self.selected_card, self.user_name, THUMBNAILS,
                                                getattr(self, "detail_info", None))
        container.add_item(ui.Separator())
        buttons = [
            self._button("🔙 返回這一疊", self.back_to_stack_callback, discord.ButtonStyle.secondary),
            self._button("🎒 返回卡冊", self.back_to_list_callback, discord.ButtonStyle.secondary),
        ]
        # 🔒 放進收藏冊：只有卡冊主人本人 (管理員檢視別人卡冊時不顯示)
        if self.user_id == self.owner_id and not self.selected_card.get("locked"):
            buttons.append(self._button("🔒 放進收藏冊", self.lock_callback, discord.ButtonStyle.primary))
        buttons.append(self._button("📖 角色圖鑑", self.character_page_callback, discord.ButtonStyle.secondary))
        container.add_item(ui.ActionRow(*buttons))
        self.add_item(container)

    async def character_page_callback(self, interaction: discord.Interaction):
        """📖 角色圖鑑：另開一則只有自己看得到的角色頁 (這個畫面不動)"""
        await send_character_page(interaction, self.selected_card["character_key"])

    async def lock_callback(self, interaction: discord.Interaction):
        """放進收藏冊：之後卡冊、合成、融合、分解、上架都看不到這張卡"""
        card = self.selected_card
        if not await set_cards_locked(self.owner_id, [card["instance_id"]], True):
            await send_notice(interaction, "❌ 這張卡已經不在卡冊裡了，請重新開啟 `/card inventory`。")
            return
        self.all_cards = sort_cards(await get_user_cards(self.owner_id))
        self.all_stacks = build_stacks(self.all_cards)
        self.selected_card = None
        if self.get_stack(self.selected_stack) is None:   # 這一疊收完了 ➔ 回卡冊列表
            self.selected_stack = None
        if not self.all_cards:
            self.stop()
            await interaction.response.edit_message(view=notice_view(
                f"🔒 已把 {card.get('emoji') or '🎴'} `[{card['rarity']}]` **{card['name']}** 放進收藏冊。卡冊已經沒有其他卡了，可以用 `/card album` 查看。"))
            return
        await self.refresh(interaction)
        await send_notice(interaction, f"🔒 已把 {card.get('emoji') or '🎴'} `[{card['rarity']}]` **{card['name']}** "
                                       f"(`{card['completeness']:.4f}`) 放進收藏冊，用 `/card album` 查看或取出。")

    # ---------------- 互動 ----------------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的卡冊！")
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def pool_select_callback(self, interaction: discord.Interaction):
        self.pool_filter = interaction.data["values"][0]
        self.page = 1
        await self.refresh(interaction)

    async def rarity_select_callback(self, interaction: discord.Interaction):
        self.rarity_filter = interaction.data["values"][0]
        self.page = 1
        await self.refresh(interaction)

    async def sort_callback(self, interaction: discord.Interaction):
        self.sort_index = (self.sort_index + 1) % len(INVENTORY_SORTS)
        self.page = 1
        await self.refresh(interaction)

    async def set_page(self, interaction: discord.Interaction, page: int):
        self.page = page   # build() 會把頁數限制在範圍內
        await self.refresh(interaction)

    async def stack_select_callback(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        if self.get_stack(value) is None:
            await send_notice(interaction, "❌ 找不到這一疊卡牌，請重新開啟 `/card inventory`。")
            return
        self.selected_stack = value
        self.stack_page = 1
        await self.refresh(interaction)

    async def set_stack_page(self, interaction: discord.Interaction, page: int):
        self.stack_page = page
        await self.refresh(interaction)

    async def card_select_callback(self, interaction: discord.Interaction):
        instance_id = interaction.data["values"][0]
        card = next((c for c in self.all_cards if c["instance_id"] == instance_id), None)
        if card is None:
            await send_notice(interaction, "❌ 找不到這張卡牌，請重新開啟 `/card inventory`。")
            return
        self.selected_card = card
        self.detail_info = await card_detail_info(card, self.owner_id)   # 🔍 角色資料、實力、特殊能力、價值、狀態
        await self.refresh(interaction)

    async def back_to_stack_callback(self, interaction: discord.Interaction):
        self.selected_card = None
        await self.refresh(interaction)

    async def back_to_list_callback(self, interaction: discord.Interaction):
        self.selected_card = None
        self.selected_stack = None
        await self.refresh(interaction)

    async def synth_shortcut_callback(self, interaction: discord.Interaction):
        """從這一疊直接開啟合成選卡畫面 (重新讀取資料庫，避免用到已經用掉的卡)"""
        stack = self.get_stack(self.selected_stack)
        group = find_synthesis_groups(await get_user_cards(self.owner_id)).get((stack["character_key"], stack["rarity"]))
        if not group:
            await send_notice(interaction, "❌ 這一疊已經沒有可以合成的卡牌了，請重新開啟 `/card inventory`。")
            return
        self.stop()
        view = SynthesisPickerView(self.owner_id, self.user_name, self.gacha_cog, stack["character_key"], group)
        await interaction.response.edit_message(view=view)

    async def fuse_shortcut_callback(self, interaction: discord.Interaction):
        """從這一疊直接開啟融合確認畫面"""
        stack = self.get_stack(self.selected_stack)
        result = await self.gacha_cog.make_fusion_view(self.owner_id, self.user_name, stack["character_key"], stack["rarity"])
        if isinstance(result, str):
            await send_notice(interaction, result)
            return
        self.stop()
        await interaction.response.edit_message(view=result)


# ================= 🔒 收藏冊 View (Components V2) =================
class AlbumView(ui.LayoutView):
    """
    /card album：收藏冊裡的卡 (locked = 1)，分頁列表 ➔ 選一張看詳情 ➔ 📤 取出 (回到卡冊)
    放進去的入口在 /card inventory 的卡片詳情 (InventoryView.lock_callback)
    """
    def __init__(self, user_id: int, user_name: str, cards: list):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.cards = cards
        self.page = 1
        self.selected = None   # 正在看的卡
        self.result = None     # 畫面最上面的結果訊息 (取出後顯示)
        self.build()

    def _button(self, label: str, callback, style=discord.ButtonStyle.primary, disabled: bool = False) -> ui.Button:
        btn = ui.Button(label=label, style=style, disabled=disabled)
        if callback is not None:
            btn.callback = callback
        return btn

    def build(self):
        self.clear_items()
        if self.selected:
            container = build_card_detail_container({**self.selected, "locked": 1}, self.user_name, THUMBNAILS,
                                                    getattr(self, "detail_info", None))
            container.add_item(ui.Separator())
            container.add_item(ui.ActionRow(
                self._button("🔙 返回收藏冊", self.back_callback, discord.ButtonStyle.secondary),
                self._button("📤 取出 (回到卡冊)", self.unlock_callback, discord.ButtonStyle.danger),
                self._button("📖 角色圖鑑", self.character_page_callback, discord.ButtonStyle.secondary),
            ))
            self.add_item(container)
            return
        pg = paginate(self.cards, self.page, ALBUM_PER_PAGE)
        self.page, total_pages, start, page_cards = pg.page, pg.total, pg.start, pg.items
        container = build_album_container(page_cards, self.page, total_pages, len(self.cards), self.user_name, start + 1, self.result)
        if page_cards:
            container.add_item(ui.Separator())
            select = ui.Select(placeholder="🎴 選擇一張卡查看或取出...", options=[
                discord.SelectOption(
                    label=f"{start + i}. [{c['rarity']}] {c['name']} · {c['completeness']:.4f}"[:100],
                    description=f"ID: {c['instance_id']}"[:100], value=c["instance_id"], emoji=c.get("emoji") or "🎴",
                )
                for i, c in enumerate(page_cards, start=1)
            ])
            select.callback = self.select_callback
            container.add_item(ui.ActionRow(select))
            if total_pages > 1:
                container.add_item(ui.ActionRow(*nav_buttons(self.page, total_pages, self.set_page)))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的收藏冊！")
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def select_callback(self, interaction: discord.Interaction):
        instance_id = interaction.data["values"][0]
        self.selected = next((c for c in self.cards if c["instance_id"] == instance_id), None)
        if self.selected is None:
            await send_notice(interaction, "❌ 找不到這張卡，請重新開啟 `/card album`。")
            return
        self.result = None
        self.detail_info = await card_detail_info({**self.selected, "locked": 1}, self.user_id)
        await self.refresh(interaction)

    async def character_page_callback(self, interaction: discord.Interaction):
        """📖 角色圖鑑：另開一則只有自己看得到的角色頁"""
        await send_character_page(interaction, self.selected["character_key"])

    async def back_callback(self, interaction: discord.Interaction):
        self.selected = None
        await self.refresh(interaction)

    async def set_page(self, interaction: discord.Interaction, page: int):
        self.page = page
        await self.refresh(interaction)

    async def unlock_callback(self, interaction: discord.Interaction):
        card = self.selected
        ok = await set_cards_locked(self.user_id, [card["instance_id"]], False)
        self.cards = await get_album_cards(self.user_id)
        self.selected = None
        self.result = (f"📤 已把 {card.get('emoji') or '🎴'} `[{card['rarity']}]` **{card['name']}** 取出，回到卡冊了。" if ok
                       else "❌ 這張卡已經不在收藏冊裡了。")
        await self.refresh(interaction)


# ================= ✅ 合成 / 融合確認 View (Components V2) =================
class CardActionConfirmView(ui.LayoutView):
    """
    確認畫面：按「確認」才真的消耗卡牌。
    on_confirm(interaction) 回傳結果 Container；失敗時回傳 str (錯誤訊息)。
    continue_character = 合成用：結果畫面「🎒 查看卡庫」旁邊多「⚗️ 繼續合成」(回到這位角色的選卡畫面，沒得合時反灰)；
      continue_on_success=False (⚡ 自動合成) ➔ 成功時不放，失敗時才放
    """
    def __init__(self, user_id: int, user_name: str, gacha_cog, container: ui.Container, on_confirm, confirm_label: str,
                 continue_character: str | None = None, continue_on_success: bool = True):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.on_confirm = on_confirm
        self.continue_character = continue_character
        self.continue_on_success = continue_on_success
        self.done = False

        confirm_btn = ui.Button(label=confirm_label, style=discord.ButtonStyle.success)
        confirm_btn.callback = self.confirm_callback
        cancel_btn = ui.Button(label="✖️ 取消", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = self.cancel_callback

        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(confirm_btn, cancel_btn))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的卡牌！")
            return False
        return True

    async def confirm_callback(self, interaction: discord.Interaction):
        if self.done:   # 連點：第二下直接忽略
            await interaction.response.defer()
            return
        self.done = True
        await interaction.response.defer()

        result = await self.on_confirm(interaction)
        if isinstance(result, str):
            container = ui.Container(accent_color=discord.Color.red())
            container.add_item(ui.TextDisplay(result))
        else:
            container = result

        inv_btn = ui.Button(label="🎒 查看卡庫", style=discord.ButtonStyle.secondary)
        inv_btn.callback = self.view_inventory
        row = [inv_btn]
        if self.continue_character and (isinstance(result, str) or self.continue_on_success):
            cont_btn = ui.Button(label="⚗️ 繼續合成", style=discord.ButtonStyle.success,
                                 disabled=not await self._synthesis_cards())   # 這位角色已經沒得合 ➔ 反灰
            cont_btn.callback = self.continue_synthesis
            row.append(cont_btn)
        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(*row))
        self.clear_items()
        self.add_item(container)
        await interaction.edit_original_response(view=self)

    async def _synthesis_cards(self) -> list:
        """這位角色現在還能合成的卡 (重新讀資料庫)"""
        return [c for (key, _), group in find_synthesis_groups(await get_user_cards(self.user_id)).items()
                if key == self.continue_character for c in group]

    async def continue_synthesis(self, interaction: discord.Interaction):
        """⚗️ 繼續合成：回到同一位角色的選卡畫面 (重新讀卡)"""
        cards = await self._synthesis_cards()
        if not cards:
            await send_notice(interaction, "❌ 這位角色已經沒有可以合成的卡了。")
            return
        self.stop()
        view = SynthesisPickerView(self.user_id, self.user_name, self.gacha_cog, self.continue_character, cards)
        await interaction.response.edit_message(view=view)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.done = True
        self.clear_items()
        container = ui.Container(accent_color=discord.Color.dark_grey())
        container.add_item(ui.TextDisplay("✖️ 已取消，卡牌沒有任何變動。"))
        self.add_item(container)
        await interaction.response.edit_message(view=self)
        self.stop()

    async def view_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cards = await get_user_cards(self.user_id)
        if not cards:
            await send_notice(interaction, "🎒 你的卡冊空空如也，快進行祈願吧！")
            return
        inv_view = InventoryView(self.user_id, sort_cards(cards), self.user_name, self.gacha_cog,
                                 owned_keys=await owned_character_keys(self.user_id))
        await interaction.edit_original_response(view=inv_view)


# ================= ⚗️ 合成選卡 View (Components V2) =================
SYNTH_PICK_PER_PAGE = 20   # 每頁張數 (選單最多 25 個選項)


def find_synthesis_groups(cards: list) -> dict:
    """{(角色, 階級): [未滿 1.0000 的卡, ...]}，只留下至少兩張 (可以互相合成) 的組合"""
    groups = {}
    for card in cards:
        if not is_perfect(card):
            groups.setdefault((card["character_key"], card["rarity"]), []).append(card)
    return {k: v for k, v in groups.items() if len(v) >= 2}


class SynthesisPickerView(ui.LayoutView):
    """
    合成選卡：選第一張 ➔ 選第二張 (只列出可以配對的) ➔ 交給 CardActionConfirmView 確認
    兩個步驟都可以分頁，解決 autocomplete 最多 25 個選項的限制
    """
    def __init__(self, user_id: int, user_name: str, gacha_cog, character_key: str, cards: list):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.character_key = character_key
        self.cards = sorted(cards, key=lambda c: (-RARITY_ORDER.get(c["rarity"], 0), -c["completeness"]))
        self.first = None   # 已選的第一張
        self.page = 1
        self.build()

    def _candidates(self) -> list:
        if self.first is None:
            return self.cards
        return [c for c in self.cards if can_synthesize(self.first, c)]

    def _button(self, label: str, callback, style=discord.ButtonStyle.primary, disabled: bool = False) -> ui.Button:
        btn = ui.Button(label=label, style=style, disabled=disabled)
        if callback is not None:
            btn.callback = callback
        return btn

    def build(self):
        self.clear_items()
        candidates = self._candidates()
        pg = paginate(candidates, self.page, SYNTH_PICK_PER_PAGE)
        self.page, total_pages, start, page_cards = pg.page, pg.total, pg.start, pg.items

        sample = self.cards[0]
        if self.first is None:
            step = "**步驟 1 / 2**：選擇第一張素材卡"
        else:
            step = (
                f"**步驟 2 / 2**：選擇第二張素材卡\n"
                f"已選第一張：`[{self.first['rarity']}]` `{self.first['completeness']:.4f}` · `{self.first['instance_id']}`"
            )
        lines = "\n".join(
            f"**{i}.** `[{c['rarity']}]` `{c['completeness']:.4f}` · `{c['instance_id']}`"
            for i, c in enumerate(page_cards, start=start + 1)
        )

        container = ui.Container(accent_color=discord.Color.teal())
        container.add_item(ui.TextDisplay(
            f"## ⚗️ 卡牌合成：{sample.get('emoji', '🎴')} {sample['name']}\n{step}\n"
            f"-# 共 {len(candidates)} 張可選 · 依階級、完整度由高到低排列 · 兩張完整度越接近越划算"
        ))
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(lines))
        container.add_item(ui.Separator())

        select = ui.Select(
            placeholder="選擇第一張素材卡..." if self.first is None else "選擇第二張素材卡...",
            options=[
                discord.SelectOption(
                    label=f"{i}. [{c['rarity']}] {c['completeness']:.4f}",
                    description=c["instance_id"][:100],
                    value=c["instance_id"],
                    emoji=c.get("emoji") or "🎴",
                )
                for i, c in enumerate(page_cards, start=start + 1)
            ],
        )
        select.callback = self.select_callback
        container.add_item(ui.ActionRow(select))

        nav = nav_buttons(self.page, total_pages, self.set_page)
        if self.first is not None:
            nav.insert(0, self._button("🔙 重選第一張", self.back_callback, discord.ButtonStyle.secondary))
        container.add_item(ui.ActionRow(*nav))
        # ⚡ 這位角色每個階級都自動合完 (先出確認畫面)
        container.add_item(ui.ActionRow(self._button("⚡ 自動合成全部", self.auto_callback, discord.ButtonStyle.success)))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的合成畫面！")
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def select_callback(self, interaction: discord.Interaction):
        chosen = interaction.data["values"][0]
        card = next((c for c in self._candidates() if c["instance_id"] == chosen), None)
        if card is None:
            await send_notice(interaction, "❌ 找不到這張卡牌，請重新使用 `/card synthesis`。")
            return
        if self.first is None:
            self.first = card
            self.page = 1
            await self.refresh(interaction)
            return
        # 兩張都選好了 ➔ 換成確認畫面 (會重新讀取資料庫確認卡牌還在)
        result = await self.gacha_cog.make_synthesis_view(self.user_id, self.user_name, self.first["instance_id"], card["instance_id"])
        if isinstance(result, str):
            await send_notice(interaction, result)
            return
        self.stop()
        await interaction.response.edit_message(view=result)

    async def back_callback(self, interaction: discord.Interaction):
        self.first = None
        self.page = 1
        await self.refresh(interaction)

    async def auto_callback(self, interaction: discord.Interaction):
        """⚡ 自動合成全部 ➔ 確認畫面 (重新讀卡；範圍 = 這位角色，每個階級各自合)"""
        result = await self.gacha_cog.make_auto_synthesis_view(self.user_id, self.user_name, self.character_key)
        if isinstance(result, str):
            await send_notice(interaction, result)
            return
        self.stop()
        await interaction.response.edit_message(view=result)

    async def set_page(self, interaction: discord.Interaction, page: int):
        self.page = page
        await self.refresh(interaction)


# ================= 🎴 Cog 類別 =================
class GachaCardSys(commands.GroupCog, group_name="card", group_description="東方角色卡牌收集與合成系統"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def generate_completeness(self) -> float:
        val = (random.gauss(0, 0.35)) ** 2
        return round(max(0.001, min(1.000, val)), 4)

    async def execute_gacha(self, interaction: discord.Interaction, draw_count: int, pool_key: str):
        await interaction.response.defer()

        # 活動的機率提升、祈願價格倍率、活動限定卡池都在 rules
        rules = await econ.get_rules()
        choice_key = pool_key   # 「繼續祈願」用：活動卡池記 "event"，下次重新找進行中的活動
        resolved = resolve_pool(pool_key, rules)   # event_only 的卡池 (th06) 也只有活動期間抽得到
        if not resolved:
            await send_notice(interaction, "🎪 目前沒有進行中的活動卡池。")
            return
        pool_key, pool_name = resolved

        # 卡池沒有角色時直接中止
        if not pool_characters(pool_key, rules):
            await send_notice(interaction, "❌ 這個卡池目前沒有任何角色，暫時無法祈願，請聯絡管理員。")
            return

        user_id = interaction.user.id
        cost_mult = rules["modifiers"].get("gacha_cost", 1.0)
        total_cost = draw_cost(draw_count, cost_mult)

        # 扣款、擲卡 (含保底)、寫入卡牌與統計全部在同一個交易 (活動卡池的保底跟一般卡池分開算)
        try:
            result = await draw_gacha(
                user_id, pool_key, draw_count, total_cost,
                lambda since_ur: roll_pool_cards(pool_key, draw_count, since_ur, self.generate_completeness, rules),
                # 活動卡池：每張卡的預期抽數另外記，浮動市值才算得到 (一般卡池照舊用卡池抽數 × 機率)
                #  (活動開放的一般卡池 th06 不用：它本來就有卡池抽數 × 機率)
                expected=expected_cards(pool_key, draw_count, rules) if pool_key.startswith(f"{EVENT_POOL}_") else None,
            )
        except InsufficientFunds as e:
            msg = f"❌ **賽錢不足！**\n祈願需要 `{total_cost:,}` 賽錢，但你的口袋裡只有 `{fmt_money(e.money)}` 賽錢...\n*靈夢看了看空蕩蕩的賽錢箱，無奈地把你請出了神社。*"
            await send_notice(interaction, msg)
            return

        results = result["cards"]
        if PITY_RARITY in pool_holders(pool_key, rules):   # 卡池沒有 UR 就沒有保底
            next_ur = rate_text(next_ur_rate(pool_key, result["since_ur"], rules))
            pity_text = (f"🎯 保底：`{result['since_ur']} / {PITY_THRESHOLD}` · 下一抽 {PITY_RARITY} `{next_ur}`"
                         f" · 本池累計 `{result['pool_draws']:,}` 抽")
        else:
            pity_text = f"🎯 這個卡池沒有 {PITY_RARITY}，沒有保底 · 本池累計 `{result['pool_draws']:,}` 抽"
        if any(c.get("pity") for c in results):
            pity_text = f"🎯 **觸發保底！必定獲得 {PITY_RARITY}！**\n" + pity_text

        if draw_count == 1:
            container = build_gacha_single_container(
                results[0], interaction.user.display_name, total_cost, THUMBNAILS, pool_name, pity_text
            )
        else:
            container = build_gacha_ten_container(
                results, interaction.user.display_name, total_cost, THUMBNAILS, pool_name, pity_text
            )

        view = GachaResultView(user_id, interaction.user.display_name, self, container, choice_key, cost_mult)

        if interaction.type == discord.InteractionType.component:
            await interaction.edit_original_response(view=view)
        else:
            await interaction.followup.send(view=view)

    @app_commands.command(name="gacha", description="⛩️ 博麗神社祈願：消耗賽錢抽取角色卡牌")
    @app_commands.describe(pool="要祈願的卡池 (依作品代數劃分)", pull_type="單抽或十連")
    @app_commands.choices(
        pool=[app_commands.Choice(name=f"{p['name']} ({p['desc']})", value=key) for key, p in GACHA_POOLS.items()
              if not p.get("event_only")]   # 紅魔鄉 (event_only) 只在活動期間從「🎪 活動限定卡池」抽
             + [app_commands.Choice(name="🎪 活動限定卡池 (活動期間才開放)", value=EVENT_POOL)],
        pull_type=[
            app_commands.Choice(name=f"單次祈願 ({DRAW_COST:,} 賽錢)", value=1),
            app_commands.Choice(name=f"十連祈願 ({DRAW_COST * 10:,} 賽錢)", value=10),
        ],
    )
    async def gacha_card(self, interaction: discord.Interaction, pool: app_commands.Choice[str], pull_type: app_commands.Choice[int]):
        await self.execute_gacha(interaction, pull_type.value, pool.value)

    @app_commands.command(name="history", description="📜 查看各卡池的祈願次數與保底進度")
    async def history(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        pity = await get_gacha_pity(user_id)
        stats = await get_gacha_stats(user_id)
        pools = dict(GACHA_POOLS)
        rules = await econ.get_rules()
        event_pool = rules.get("gacha_event_pool")
        if event_pool and event_pool["key"] not in pools:   # 進行中的活動卡池也列出來 (保底跟一般卡池分開算)
            pools[event_pool["key"]] = {"name": event_pool["name"]}
        notes = {key: open_note(key) for key in pools if open_note(key)}   # 紅魔鄉：🎪 紅霧異變期間開放
        drawable = {key: p for key, p in pools.items() if resolve_pool(key, rules)}   # 📊 機率表選單只列現在抽得到的
        next_rates = {   # 下一抽 UR 的機率；卡池沒有 UR ➔ None
            key: rate_text(next_ur_rate(key, pity.get(key, {}).get("since_ur", 0), rules))
                 if PITY_RARITY in pool_holders(key, rules) else None
            for key in pools
        }
        container = build_gacha_history_container(
            interaction.user.display_name, pools, pity, stats, PITY_THRESHOLD, PITY_RARITY, next_rates, notes
        )
        await interaction.response.send_message(view=GachaHistoryView(container, drawable))

    @app_commands.command(name="inventory", description="🎒 查看個人的博麗神社卡冊與持有卡牌")
    async def view_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        cards = await get_user_cards(user_id)

        if not cards:
            await send_notice(interaction, "🎒 你的卡冊空空如也，快去使用 `/card gacha` 進行第一次祈願吧！")
            return

        view = InventoryView(user_id, sort_cards(cards), interaction.user.display_name, self,
                             owned_keys=await owned_character_keys(user_id))
        await interaction.followup.send(view=view)

    @app_commands.command(name="album", description="🔒 收藏冊：收進來的卡不會被合成、融合、分解或上架")
    async def view_album(self, interaction: discord.Interaction):
        cards = await get_album_cards(interaction.user.id)
        view = AlbumView(interaction.user.id, interaction.user.display_name, cards)
        await interaction.response.send_message(view=view)

    # ---------------- 共用：代數 / 角色 autocomplete ----------------
    def _pool_label(self, pool_key: str) -> str:
        return GACHA_POOLS[pool_key]["name"] if pool_key in GACHA_POOLS else "📦 其他 (已不在卡池)"

    def _pool_choices(self, groups: dict, current: str) -> list[app_commands.Choice[str]]:
        """groups = {(角色, 階級): [卡...]}；依代數彙整成選項"""
        counts = {}
        for cards in groups.values():
            pool_key = card_pool_key(cards[0])
            counts[pool_key] = counts.get(pool_key, 0) + 1
        choices = []
        for pool_key, count in counts.items():
            label = self._pool_label(pool_key)
            if current.lower() in f"{pool_key} {label}".lower():
                choices.append(app_commands.Choice(name=f"{label} · {count} 組可用", value=pool_key))
        return choices[:AUTOCOMPLETE_LIMIT]

    def _character_choices(self, groups: dict, pool_key: str | None, current: str) -> list[app_commands.Choice[str]]:
        """依已選的代數列出有可用組合的角色"""
        owned = {}
        for (char_key, _), cards in groups.items():
            if card_pool_key(cards[0]) != pool_key:
                continue
            entry = owned.setdefault(char_key, {"name": cards[0]["name"], "emoji": cards[0].get("emoji", "🎴"), "count": 0})
            entry["count"] += len(cards)
        current = current.strip().lower()
        return [
            app_commands.Choice(name=f"{e['emoji']} {e['name']} ({key}) · {e['count']} 張可用"[:100], value=key)
            for key, e in owned.items()
            if not current or current in key.lower() or current in e["name"].lower()
        ][:AUTOCOMPLETE_LIMIT]

    # ---------------- ⚗️ 合成 ----------------
    async def synthesis_pool_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._pool_choices(find_synthesis_groups(await card_cache.cached_user_cards(interaction.user.id)), current)

    async def synthesis_character_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        groups = find_synthesis_groups(await card_cache.cached_user_cards(interaction.user.id))
        return self._character_choices(groups, getattr(interaction.namespace, "pool", None), current)

    async def make_synthesis_view(self, user_id: int, user_name: str, card1: str, card2: str):
        """建立合成確認畫面；卡牌不存在或條件不符時回傳錯誤訊息 (str)"""
        cards = {c["instance_id"]: c for c in await get_user_cards(user_id)}
        card_a, card_b = cards.get(card1), cards.get(card2)
        if card_a is None or card_b is None:
            return "❌ 找不到指定的卡牌，可能已經被合成或融合掉了。"
        if not can_synthesize(card_a, card_b):
            return "❌ **無法合成！**\n合成需要兩張「不同的」、「同角色」、「同階級」的卡牌，且完整度都未達 `1.0000`。"

        preview = calc_synthesis(card_a["completeness"], card_b["completeness"], card_a["rarity"])
        container = build_synthesis_preview_container(card_a, card_b, preview, user_name, THUMBNAILS)

        def build_new_card(consumed: list) -> dict:
            a, b = consumed
            if not can_synthesize(a, b):
                raise ValueError("卡牌狀態已改變，無法合成")
            result = roll_synthesis(a["completeness"], b["completeness"], a["rarity"])
            return {**synthesized_card(a, result["new_completeness"]), "_result": result}

        async def on_confirm(_interaction: discord.Interaction):
            try:
                _, new_card = await transform_cards(user_id, [card1, card2], build_new_card, count_synthesis=True)
            except ValueError as e:
                return f"❌ **合成失敗**：{e}\n-# 卡牌沒有任何變動。"
            result = new_card.pop("_result")
            return build_synthesis_result_container(new_card, result["increase"], result["doubled"], user_name, THUMBNAILS)

        return CardActionConfirmView(user_id, user_name, self, container, on_confirm, "⚗️ 確認合成",
                                     continue_character=card_a["character_key"])

    async def make_auto_synthesis_view(self, user_id: int, user_name: str, character_key: str):
        """⚡ 自動合成全部的確認畫面 (這位角色每個階級各自合)；沒有可以合的卡 ➔ 錯誤訊息 (str)"""
        cards = [c for c in await get_user_cards(user_id) if c["character_key"] == character_key]
        preview = auto_synthesis_preview(cards)
        if not preview:
            return "❌ 這位角色已經沒有可以合成的卡了 (同一個階級至少要兩張未滿 `1.0000` 的卡)。"
        sample = cards[0]
        container = build_auto_synthesis_preview_container(sample, preview, user_name, THUMBNAILS)

        def run(current: list) -> dict:   # 在交易裡，用當下的卡重算；跟確認畫面不一樣就整筆不做
            if auto_synthesis_preview(current) != preview:
                raise ValueError("卡牌跟確認畫面不一樣了 (有卡被用掉、收進收藏冊或新抽到)，請回到選卡畫面重新按「⚡ 自動合成全部」")
            return run_auto_synthesis(current)

        async def on_confirm(_interaction: discord.Interaction):
            try:
                result = await auto_synthesize_cards(user_id, character_key, run)
            except ValueError as e:
                return f"❌ **自動合成沒有執行**：{e}\n-# 卡牌沒有任何變動。"
            return build_auto_synthesis_result_container(sample, result, user_name, THUMBNAILS)

        # 自動合成完只留「🎒 查看卡庫」(失敗時才有「⚗️ 繼續合成」回選卡畫面)
        return CardActionConfirmView(user_id, user_name, self, container, on_confirm, "⚡ 確認自動合成",
                                     continue_character=character_key, continue_on_success=False)

    @app_commands.command(name="synthesis", description="⚗️ 合成卡牌：兩張同角色、同階級的卡合成一張完整度更高的卡")
    @app_commands.describe(pool="代數 (只列出有可合成卡牌的)", character="角色 (只列出該代數中有可合成卡牌的)")
    @app_commands.autocomplete(pool=synthesis_pool_autocomplete, character=synthesis_character_autocomplete)
    async def synthesis(self, interaction: discord.Interaction, pool: str, character: str):
        user_id = interaction.user.id
        # 使用者也可能不透過 autocomplete 直接輸入，所以這裡一樣要檢查
        cards = [
            c for group in find_synthesis_groups(await get_user_cards(user_id)).values() for c in group
            if c["character_key"] == character and card_pool_key(c) == pool
        ]
        if not cards:
            await send_notice(interaction, "❌ **無法合成！**\n這個角色沒有可以合成的卡牌：合成需要兩張「同角色」、「同階級」且完整度都未達 `1.0000` 的卡牌。")
            return
        view = SynthesisPickerView(user_id, interaction.user.display_name, self, character, cards)
        await interaction.response.send_message(view=view)

    # ---------------- 🔮 融合 ----------------
    async def fusion_pool_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._pool_choices(find_fusion_groups(await card_cache.cached_user_cards(interaction.user.id)), current)

    async def fusion_character_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        groups = find_fusion_groups(await card_cache.cached_user_cards(interaction.user.id))
        return self._character_choices(groups, getattr(interaction.namespace, "pool", None), current)

    async def fusion_rarity_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """依已選的角色列出可以融合的階級 (每個角色最多 2 個)"""
        char_key = getattr(interaction.namespace, "character", None)
        groups = find_fusion_groups(await card_cache.cached_user_cards(interaction.user.id))
        choices = []
        for (key, rarity), group in sorted(groups.items(), key=lambda kv: RARITY_ORDER.get(kv[0][1], 0)):
            if key != char_key or current.upper() not in rarity:
                continue
            name = f"[{rarity} → {get_next_rarity(group[0])}] · 持有 {len(group)} 張 1.0000"
            choices.append(app_commands.Choice(name=name, value=rarity))
        return choices

    @app_commands.command(name="fusion", description="🔮 融合卡牌：三張同角色、同階級且完整度 1.0000 的卡融合成高一階的卡")
    @app_commands.describe(
        pool="代數 (只列出有可融合卡牌的)",
        character="角色 (只列出該代數中有可融合卡牌的)",
        rarity="要融合的階級 (只列出符合條件的)",
    )
    @app_commands.autocomplete(pool=fusion_pool_autocomplete, character=fusion_character_autocomplete, rarity=fusion_rarity_autocomplete)
    async def fusion(self, interaction: discord.Interaction, pool: str, character: str, rarity: str):
        result = await self.make_fusion_view(interaction.user.id, interaction.user.display_name, character, rarity, pool)
        if isinstance(result, str):
            await send_notice(interaction, result)
            return
        await interaction.response.send_message(view=result)

    async def make_fusion_view(self, user_id: int, user_name: str, char_key: str, rarity: str, pool: str | None = None):
        """建立融合確認畫面；條件不符時回傳錯誤訊息 (str)。pool 有給時會一併檢查卡池"""
        group = find_fusion_groups(await get_user_cards(user_id)).get((char_key, rarity))
        if not group or (pool is not None and card_pool_key(group[0]) != pool):
            return (f"❌ **無法融合！**\n融合需要 **{FUSION_COUNT}** 張「同角色」、「同階級」且完整度 `1.0000` 的卡牌，"
                    f"而且該角色必須還有更高的階級。")

        materials = group[:FUSION_COUNT]   # 滿完整度的卡都一樣，取最早獲得的三張
        material_ids = [c["instance_id"] for c in materials]
        next_rarity = get_next_rarity(materials[0])
        next_title = GACHA_POOL[char_key]["titles"][next_rarity]
        container = build_fusion_preview_container(materials, next_rarity, next_title, user_name, THUMBNAILS)

        def build_new_card(consumed: list) -> dict:
            base = consumed[0]
            if not all(
                is_perfect(c) and c["character_key"] == base["character_key"] and c["rarity"] == base["rarity"]
                for c in consumed
            ):
                raise ValueError("卡牌狀態已改變，無法融合")
            new_rarity = get_next_rarity(base)
            if new_rarity is None:
                raise ValueError("這張卡已經是最高階級")
            char_data = GACHA_POOL[base["character_key"]]
            return {
                "instance_id": f"c_{char_data['uuid'][:4]}_{uuid.uuid4().hex[:12]}",
                "character_key": base["character_key"],
                "name": char_data["name"],
                "emoji": char_data["emoji"],
                "rarity": new_rarity,
                "title": char_data["titles"][new_rarity],
                "completeness": self.generate_completeness(),
                "obtained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        async def on_confirm(_interaction: discord.Interaction):
            try:
                _, new_card = await transform_cards(user_id, material_ids, build_new_card, count_fusion=True)
            except ValueError as e:
                return f"❌ **融合失敗**：{e}\n-# 卡牌沒有任何變動。"
            return build_fusion_result_container(new_card, rarity, user_name, THUMBNAILS)

        return CardActionConfirmView(user_id, user_name, self, container, on_confirm, "🔮 確認融合")

    @app_commands.command(name="help", description="📖 教學書：抽卡、卡冊、合成與融合的玩法與指令 (只有自己看得到)")
    async def help_book(self, interaction: discord.Interaction):
        await open_guide(interaction, "card")


async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCardSys(bot))
"""
🎪 活動資料 (Events/<id>.json) 的讀取與合併 (純資料，不碰資料庫)

活動的狀態 (進行中 / 已結束、開始與結束時間) 存在 Users.db 的 economy_meta (Economy_DB_Manager)。
這裡只負責：讀活動檔、把「進行中的活動」跟基本資料 (shrine_data) 合併成這一刻的遊戲規則。
新增活動：放一個 Events/<id>.json (格式照 th06_scarlet_mist.json)，不用改程式。
"""
import json
import os

from Database import shrine_data as base

EVENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Events")


def load_events() -> dict:
    """{活動 ID: 活動資料}；壞掉的檔案印警告後略過"""
    events = {}
    if not os.path.isdir(EVENTS_DIR):
        return events
    for filename in sorted(os.listdir(EVENTS_DIR)):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(EVENTS_DIR, filename), encoding="utf-8") as f:
                data = json.load(f)
            events[data["id"]] = data
        except (OSError, ValueError, KeyError) as e:
            print(f"⚠️ [Events] 讀取 {filename} 失敗：{e}")
    return events


def event_item_ids(event: dict) -> set[str]:
    return {item["id"] for item in event.get("items", [])}


# 數值倍率的預留位：活動檔的 "modifiers" 可以設定，沒設定 = 1 (不影響)；同時有多個活動時相乘
MODIFIER_KEYS = ("shrine_income", "youkai_reward", "serve_reward", "explore_stamina",
                 "youkai_spawn", "guest_spawn", "daily_money", "daily_exp", "decompose",
                 "gacha_cost", "market_fee", "transfer_fee")   # 祈願價格、市場買家手續費、轉帳手續費 (2026-11-13 補的預留位)


def _as_list(x) -> list:
    return list(x) if isinstance(x, list) else ([x] if x else [])


def game_rules(active: list[dict]) -> dict:
    """
    基本資料 + 進行中的活動 ➔ 這一刻的規則。每個機制都是「一般池 + 活動預留位」：

    | 規則 | 一般 | 活動檔可以加的欄位 |
    |---|---|---|
    | recipes / dish_types | shrine_data.RECIPES | items (料理)、recipes |
    | order_pool {種類: {base, event}} | 一般料理 | 活動料理自動進 event 池；order_event_chance = 抽 event 池的機率 |
    | locations | shrine_data.LOCATIONS | location (限定地點)；extra_drops {地點: [素材]}、explore_events {地點: {good: [..], bad: [..]}} 加進一般地點 |
    | guest_pool {base, event} / guests | shrine_data.GUESTS | guests (限定客人)；event_guest_chance = 來 event 客人的機率 (沒設 = 全部平均抽)；
    |   |   | guest_overrides {客人: {favorite, hint, lines: {high/mid/low: [台詞]}}} (lines 是加進台詞池，其他是取代) |
    | shop | shrine_data.SHOP_PRICES | shop {素材: 價格} |
    | modifiers | 全部 1 | modifiers {shrine_income, youkai_reward, serve_reward, explore_stamina: 倍率} |
    | special_chance | shrine_data.SPECIAL_CHANCE | special_chance (取最大) |
    | gacha_rate_up {角色: 倍率} | 卡池角色平均抽 | gacha.rate_up (抽到該角色的權重 ×倍率，多個活動相乘) |
    | gacha_rarity_weights | 沒有 = 抽卡用預設 RARITY_WEIGHTS | gacha.rarity_weights [低, 中, 高] (後面的活動蓋前面) |
    | gacha_event_pool | None | gacha.pool {name, desc, characters: [角色 id]} (活動限定卡池；後面的活動蓋前面) |
    | daily_items [[道具, 數量]] | 沒有 (🍙 由簽到本身送) | daily_items (簽到額外送) |
    | event_dish_bonus | 1 | event_dish_bonus (取最大) |
    """
    recipes = dict(base.RECIPES)
    dish_types = dict(base.DISH_TYPES)
    locations = {}
    for k, v in base.LOCATIONS.items():
        locations[k] = {**v, "drops": list(v["drops"]), "good": _as_list(v.get("good")), "bad": _as_list(v.get("bad")), "event": None}
    guests = {k: {**v, "lines": {t: _as_list(l) for t, l in v.get("lines", {}).items()}, "event": None}
              for k, v in base.GUESTS.items()}
    shop = dict(base.SHOP_PRICES)
    mods = {k: 1.0 for k in MODIFIER_KEYS}
    event_dishes, event_guests = {}, set()
    chance, bonus, guest_chance, special = 0.0, 1.0, None, base.SPECIAL_CHANCE
    rate_up, rarity_weights, daily_items, event_pool = {}, None, [], None
    for ev in active:
        eid = ev["id"]
        recipes.update(ev.get("recipes", {}))
        for item in ev.get("items", []):
            serve = (item.get("effect") or {}).get("serve")
            if serve:
                dish_types[item["id"]] = serve
                event_dishes[item["id"]] = eid
        for loc in _as_list(ev.get("location")) + list(ev.get("locations", [])):
            locations[loc["id"]] = {**loc, "drops": list(loc["drops"]), "good": _as_list(loc.get("good")),
                                    "bad": _as_list(loc.get("bad")), "event": eid}
        for loc_id, drops in ev.get("extra_drops", {}).items():
            if loc_id in locations:
                locations[loc_id]["drops"] += [m for m in drops if m not in locations[loc_id]["drops"]]
        for loc_id, evs in ev.get("explore_events", {}).items():
            if loc_id in locations:
                for side in ("good", "bad"):
                    locations[loc_id][side] = locations[loc_id][side] + _as_list(evs.get(side))
        for key, g in ev.get("guests", {}).items():
            guests[key] = {**g, "lines": {t: _as_list(l) for t, l in g.get("lines", {}).items()}, "event": eid}
            event_guests.add(key)
        for key, ov in ev.get("guest_overrides", {}).items():
            if key not in guests:
                continue
            g = guests[key] = {**guests[key], "lines": {t: list(l) for t, l in guests[key]["lines"].items()}}
            for field in ("favorite", "hint", "name", "emoji"):
                if field in ov:
                    g[field] = ov[field]
            for t, l in ov.get("lines", {}).items():
                g["lines"][t] = g["lines"].get(t, []) + _as_list(l)
        shop.update(ev.get("shop", {}))
        for k, v in ev.get("modifiers", {}).items():
            if k in mods:
                mods[k] *= v
        chance = max(chance, ev.get("order_event_chance", 0.0))
        bonus = max(bonus, ev.get("event_dish_bonus", 1.0))
        special = max(special, ev.get("special_chance", 0.0))
        gacha = ev.get("gacha", {})
        for key, mult in gacha.get("rate_up", {}).items():
            rate_up[key] = rate_up.get(key, 1.0) * mult
        if gacha.get("rarity_weights"):
            rarity_weights = list(gacha["rarity_weights"])
        if gacha.get("pool", {}).get("characters"):
            pool = gacha["pool"]
            event_pool = {"key": f"event_{eid}", "event": eid,
                          "name": pool.get("name") or f"{ev.get('emoji', '🎪')} {ev.get('name', eid)}卡池",
                          "desc": pool.get("desc", "活動限定"), "characters": list(pool["characters"])}
        daily_items += [list(x) for x in ev.get("daily_items", [])]
        if "event_guest_chance" in ev:
            guest_chance = max(guest_chance or 0.0, ev["event_guest_chance"])
    order_pool = {}
    for d, t in dish_types.items():
        pool = order_pool.setdefault(t, {"base": [], "event": []})
        pool["event" if d in event_dishes else "base"].append(d)
    return {
        "recipes": recipes, "dish_types": dish_types, "locations": locations, "guests": guests,
        "event_dishes": event_dishes, "event_guests": event_guests,
        "order_pool": order_pool, "order_event_chance": chance, "event_dish_bonus": bonus,
        "guest_pool": {"base": sorted(k for k in guests if k not in event_guests), "event": sorted(event_guests)},
        "event_guest_chance": guest_chance, "shop": shop, "modifiers": mods, "special_chance": special,
        "gacha_rate_up": rate_up, "gacha_rarity_weights": rarity_weights, "gacha_event_pool": event_pool,
        "daily_items": daily_items,
    }


def pick_line(guest: dict, tier: str, seed: str = "") -> str:
    """從台詞池挑一句 (用客人 id 當種子，同一位客人每次看都是同一句)"""
    pool = _as_list(guest.get("lines", {}).get(tier))
    if not pool:
        return "{order}"
    return pool[sum(map(ord, seed)) % len(pool)]


# =========================================================
# 📜 活動任務 (活動檔的 "quests" / "quest_titles"；計數、領取在 Database/Quest_DB_Manager.py)
# =========================================================
# type ➔ target 要填什麼 (None = 不用填)
QUEST_TYPES = {
    "explore_location": "地點 id",          # 在那個地點採集的趟數
    "cook_each": "[料理 id, ...]",          # 每種至少做 count 鍋 (預設 1)；進度 = 做過幾種 / 幾種
    "serve_guest": "客人種類 id",           # 招待那種客人的位數
    "serve_event_dish": None,               # 招待時端出這個活動的活動料理份數
    "serve_favorite": None,                 # 成功招待 (額外端上客人最愛的料理) 的次數
    "gacha_event_pool": None,               # 這個活動的活動限定卡池祈願抽數
    "gacha_pool": "卡池 id (classic / th06)",  # 活動期間在那個一般卡池祈願的抽數 (2026-11-14：紅霧異變算紅魔鄉卡池)
    "daily": None,                          # 活動期間簽到天數
}
TITLE_RARITIES = ("N", "R", "SR", "SSR", "UR", "LR")


def validate_quests(event: dict) -> list[str]:
    """活動檔的任務 / 任務稱號格式檢查 ➔ 問題清單 (空的 = 沒問題)"""
    problems, ids = [], set()
    for q in event.get("quests", []):
        qid = q.get("id")
        if not qid or qid in ids:
            problems.append(f"任務 id 重複或沒填：{qid}")
        ids.add(qid)
        for key in ("name", "desc", "type"):
            if not q.get(key):
                problems.append(f"{qid}：缺少 {key}")
        if q.get("type") not in QUEST_TYPES:
            problems.append(f"{qid}：不認識的 type {q.get('type')}")
        elif QUEST_TYPES[q["type"]] and not q.get("target"):
            problems.append(f"{qid}：{q['type']} 要填 target ({QUEST_TYPES[q['type']]})")
        if q.get("type") == "cook_each" and not isinstance(q.get("target"), list):
            problems.append(f"{qid}：cook_each 的 target 要是料理 id 清單")
        if q.get("type") != "cook_each" and not (isinstance(q.get("count"), int) and q["count"] >= 1):
            problems.append(f"{qid}：count 要是 >= 1 的整數")
        reward = q.get("reward", {})
        if not all(isinstance(reward.get(k, 0), int) and reward.get(k, 0) >= 0 for k in ("money", "exp")):
            problems.append(f"{qid}：reward 的 money / exp 要是 >= 0 的整數")
    tids = set()
    for t in event.get("quest_titles", []):
        if not t.get("id") or t["id"] in tids:
            problems.append(f"任務稱號 id 重複或沒填：{t.get('id')}")
        tids.add(t.get("id"))
        if t.get("rarity") not in TITLE_RARITIES:
            problems.append(f"任務稱號 {t.get('id')}：rarity 要是 N～LR")
        if not (isinstance(t.get("min_quests"), int) and 1 <= t["min_quests"] <= len(ids)):
            problems.append(f"任務稱號 {t.get('id')}：min_quests 要在 1～任務數之間")
    return problems


def quest_need(quest: dict) -> int:
    """完成要多少 (cook_each = 料理種類數)"""
    if quest["type"] == "cook_each":
        return len(quest.get("target") or [])
    return int(quest.get("count", 1))


def quest_progress(quest: dict, stats: dict) -> int:
    """
    (純計算) 任務進度 (stats = 這一輪的計數 {項目: 數量}，Database/User_DB_Manager.add_quest_stats 記的)
    回傳目前的數字 (不會超過 quest_need)
    """
    t, target = quest["type"], quest.get("target")
    if t == "explore_location":
        cur = stats.get(f"explore:{target}", 0)
    elif t == "cook_each":
        each = int(quest.get("count", 1) or 1)
        cur = sum(1 for d in (target or []) if stats.get(f"cook:{d}", 0) >= each)
    elif t == "serve_guest":
        cur = stats.get(f"serve_guest:{target}", 0)
    elif t == "gacha_pool":
        cur = stats.get(f"gacha_pool:{target}", 0)
    elif t in ("serve_event_dish", "serve_favorite", "gacha_event_pool", "daily"):
        cur = stats.get(t, 0)
    else:
        cur = 0
    return min(cur, quest_need(quest))


def quest_goal(quest: dict, event: dict, items: dict | None = None) -> str:
    """
    任務目標的文字，進度的位置留 {p} (畫面換成 `3 / 10`)
    items = Item.db 的道具 {id: {name, emoji}} (料理名稱用；沒有就找活動檔的 items)
    """
    items = items or {}
    ev_items = {i["id"]: i for i in event.get("items", [])}

    def dish(d):
        info = items.get(d) or ev_items.get(d) or {}
        return f"{info.get('emoji', '')}{info.get('name', d)}"

    t, target = quest["type"], quest.get("target")
    if t == "explore_location":
        locs = {loc["id"]: loc for loc in _as_list(event.get("location")) + list(event.get("locations", []))}
        loc = locs.get(target) or base.LOCATIONS.get(target) or {}
        return f"在「{loc.get('emoji', '')}{loc.get('name', target)}」採集 {{p}} 次"
    if t == "cook_each":
        each = int(quest.get("count", 1) or 1)
        return f"{'、'.join(dish(d) for d in target or [])}各做 {each} 鍋 · {{p}} 種"
    if t == "serve_guest":
        g = event.get("guests", {}).get(target) or base.GUESTS.get(target) or {}
        return f"招待{g.get('emoji', '')}{g.get('name', target)} {{p}} 位"
    if t == "serve_event_dish":
        return "招待時端出活動料理 {p} 份"
    if t == "serve_favorite":
        return "成功招待 (額外端上客人最愛的料理) {p} 次"
    if t == "gacha_event_pool":
        text = "在活動限定卡池祈願 {p} 抽"
        if not event.get("gacha", {}).get("pool", {}).get("characters"):
            text += "\n-# ⚠️ 這個活動目前還沒有活動限定卡池"
        return text
    if t == "gacha_pool":
        from Utils.gacha_pools import GACHA_POOLS
        return f"在「{GACHA_POOLS.get(target, {}).get('name', target)}」祈願 {{p}} 抽"
    if t == "daily":
        return "活動期間簽到 {p} 天"
    return "{p}"


def all_guests() -> dict:
    """包含所有活動 (不管有沒有進行中) 的客人資料：顯示已在神社裡的活動客人時用"""
    guests = {k: {**v, "event": None} for k, v in base.GUESTS.items()}
    for ev in load_events().values():
        for key, g in ev.get("guests", {}).items():
            guests[key] = {**g, "event": ev["id"]}
    return guests

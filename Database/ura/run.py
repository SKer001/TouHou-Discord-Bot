"""
🗺️ 裏世界一局的流程 (docs/ura.md)：選門 ➔ 房間 (戰鬥 / 精英 / 寶箱 / 事件 / 陷阱 / 商人 / BOSS) ➔ … ➔ 撤離 / 失敗 / 放棄

run["phase"]：doors 選門 / battle 戰鬥 / chest 寶箱 / event 事件 / trap 陷阱結果 / merchant 商人 / boss_clear 打完 BOSS / ended 結束
所有動作都是 xxx(run, ..., rng) ➔ 失敗回傳原因字串，成功回傳 None；狀態直接改在 run 裡 (JSON 可存)。
每一步 (進一關) run["step"] +1；資料庫用 `UPDATE … WHERE step = ?` 防重複。
"""
import math
import random

from Database.ura import combat, data, fest, rules, status

VERSION = 1


def action_rng(run: dict) -> random.Random:
    """每個動作用一個新的亂數 (seed + 第幾個動作)：同樣的進度重新顯示不會重擲"""
    run["act"] = run.get("act", 0) + 1
    return random.Random(f"{run['seed']}:{run['act']}")


# =========================================================
# 🎒 背包
# =========================================================
def slots_used(bag: dict) -> int:
    items = data.items()
    n = sum(math.ceil(c / max(1, items.get(i, {}).get("stack", 1))) for i, c in bag["items"].items() if c > 0)
    n += sum(math.ceil(c / rules.MATERIAL_STACK) for c in bag["materials"].values() if c > 0)
    return n + len(bag["treasures"]) + len(bag["relics"])


def _slots_after(bag: dict, kind: str, key, n: int = 1) -> int:
    trial = {"items": dict(bag["items"]), "materials": dict(bag["materials"]),
             "treasures": list(bag["treasures"]), "relics": list(bag["relics"])}
    if kind in ("items", "materials"):
        trial[kind][key] = trial[kind].get(key, 0) + n
    else:
        trial[kind] = trial[kind] + [key] * n
    return slots_used(trial)


def item_limit_reason(bag_items: dict, iid: str, n: int = 1) -> str | None:
    """一局最多帶幾個 (同一個道具 / 回血類 / 常識度類合計)"""
    it = data.items()[iid]
    if it.get("max") and bag_items.get(iid, 0) + n > it["max"]:
        return f"{it['name']}最多 {it['max']} 個"
    cat = it.get("cat")
    if cat:
        cap = data.category_max()[cat]
        cur = sum(c for i, c in bag_items.items() if data.items().get(i, {}).get("cat") == cat)
        if cur + n > cap:
            return {"heal": "回血類", "sanity": "回常識度類"}.get(cat, cat) + f"合計最多 {cap} 個"
    return None


def can_add(run: dict, kind: str, key, n: int = 1) -> str | None:
    if kind == "items":
        why = item_limit_reason(run["bag"]["items"], key, n)
        if why:
            return why
    if _slots_after(run["bag"], kind, key, n) > run["capacity"]:
        return "背包滿了"
    return None


def stash(run: dict, loot: dict):
    """撿東西：放得下的放進背包，放不下的放到 run["pending"] (整理背包後可以再撿，離開這關就沒了)"""
    bag = run["bag"]
    for iid, n in loot.get("items", {}).items():
        for _ in range(n):
            if not can_add(run, "items", iid):
                bag["items"][iid] = bag["items"].get(iid, 0) + 1
            else:
                run["pending"].append({"kind": "items", "key": iid})
    for mid, n in loot.get("materials", {}).items():
        for _ in range(n):
            if not can_add(run, "materials", mid):
                bag["materials"][mid] = bag["materials"].get(mid, 0) + 1
            else:
                run["pending"].append({"kind": "materials", "key": mid})
    for t in loot.get("treasures", []):
        if not can_add(run, "treasures", t):
            bag["treasures"].append(t)
        else:
            run["pending"].append({"kind": "treasures", "key": t})
    for r in loot.get("relics", []):
        if not can_add(run, "relics", r):
            bag["relics"].append(r)
        else:
            run["pending"].append({"kind": "relics", "key": r})


def take_pending(run: dict, idx: int) -> str | None:
    if not 0 <= idx < len(run["pending"]):
        return "沒有這個東西"
    p = run["pending"][idx]
    why = can_add(run, p["kind"], p["key"])
    if why:
        return why
    run["pending"].pop(idx)
    stash(run, {p["kind"]: ({p["key"]: 1} if p["kind"] in ("items", "materials") else [p["key"]])})
    return None


def discard(run: dict, kind: str, key, n: int = 1) -> str | None:
    """丟掉背包裡的東西 (key：道具 / 素材 id，寶物 / 法具是清單位置)"""
    bag = run["bag"]
    if kind in ("items", "materials"):
        if bag[kind].get(key, 0) < n:
            return "沒有這麼多"
        bag[kind][key] -= n
        if bag[kind][key] <= 0:
            del bag[kind][key]
        return None
    if not 0 <= key < len(bag[kind]):
        return "沒有這個東西"
    bag[kind].pop(key)
    return None


def _take_item(run: dict, iid: str) -> bool:
    bag = run["bag"]["items"]
    if bag.get(iid, 0) <= 0:
        return False
    bag[iid] -= 1
    if not bag[iid]:
        del bag[iid]
    return True


# =========================================================
# 🎲 隨機掉落
# =========================================================
def roll_cheap_items(n: int, rng) -> dict:
    """精英 / 事件 / 寶箱掉的便宜道具 (藥草、飯糰、茶、糰子、鑰匙、欠條各 15%，新聞 10%)"""
    pool = {i: it["cheap"] for i, it in data.items().items() if it.get("cheap")}
    out = {}
    for _ in range(n):
        i = rng.choices(list(pool), weights=list(pool.values()))[0]
        out[i] = out.get(i, 0) + 1
    return out


def zone_theme(run: dict, zone: int) -> dict:
    """
    這一局第 zone 區的主題 (使用者 2026-11-20)：每區隨機抽一個主題，不跟前三區重複 (5 個主題 ➔ 第 4 區起剩 2 個可以抽)；
    照 seed 決定 (同一個 seed 每區主題一樣)，抽過的存在 run["themes"]。主題只是模板 (敵人 / BOSS / 素材 / 寶物)，難度只看第幾區
    """
    themes = run.setdefault("themes", [])
    ids = [z["id"] for z in data.zones()]
    while len(themes) < zone:
        rng = random.Random(f"{run.get('seed', '')}:theme:{len(themes) + 1}")
        recent = set(themes[-3:])
        themes.append(rng.choice([i for i in ids if i not in recent] or ids))
    return data.zone_by_id(themes[zone - 1])


def roll_materials(zone: int, n: int, rng, theme: dict | None = None) -> dict:
    mats = (theme or data.zone_info(zone))["materials"]
    out = {}
    for _ in range(n):
        m = rng.choice(mats)
        out[m] = out.get(m, 0) + 1
    return out


def roll_treasure(table: str, zone: int, rng, rarity: str | None = None, theme: dict | None = None) -> dict:
    """寶物：階級看第幾區 (越深越好)，名單看這區的主題 (theme 沒給 = 照順序輪的 data.zone_info)"""
    r = rarity or rules.roll_rarity(table, zone, rng)
    pool = data.theme_treasures(theme) if theme else data.treasures(zone)
    tid = rng.choice(pool[r])[0]
    return {"id": tid, "rarity": r, "zone": zone}


def roll_relic(zone: int, rng, classes: list[str] | None = None, shift: int = 0) -> dict:
    """法具：等級用 BOSS 那張表 (SSR 起跳)；classes = 只挑隊上有人職業對得上的 (BOSS)"""
    pool = data.base_relics()   # 活動法具只從 🎪 房間來 (fest.py)
    keys = [k for k, r in pool.items() if not classes or r.get("class") in classes] or list(pool)
    rid = rng.choice(keys)
    order = ["SSR", "UR", "LR"]
    tier = order.index(rules.roll_rarity("boss", zone, rng))
    tier = max(0, min(2, tier + shift))
    rel = {"rid": rid, "tier": tier}
    if pool[rid]["type"] == "ofuda":
        rel["left"] = pool[rid]["uses"][tier]
    return rel


def _merge(a: dict, b: dict):
    for k in ("items", "materials"):
        for i, n in b.get(k, {}).items():
            a.setdefault(k, {})[i] = a.setdefault(k, {}).get(i, 0) + n
    for k in ("treasures", "relics"):
        a.setdefault(k, []).extend(b.get(k, []))
    a["money"] = a.get("money", 0) + b.get("money", 0)


def foe_loot(run: dict, kind: str, rng, money_mult: float = 1.0) -> dict:
    """打倒 / 勸走一隻敵人給的東西"""
    zone = rules.zone_of(run["floor"])
    theme = zone_theme(run, zone)
    loot = {"items": {}, "materials": {}, "treasures": [], "relics": [], "money": 0}
    if kind == "mimic":
        loot["money"] = rules.round_half(rules.mimic_money(zone) * money_mult)
        loot["items"] = roll_cheap_items(rules.weighted_count(*rules.MIMIC_ITEMS, rng), rng)
        n = rules.weighted_count(*rules.MIMIC_RELICS, rng)
        loot["relics"] = [roll_relic(zone, rng, shift=1 if n == 1 else -1) for _ in range(n)]
        loot["treasures"] = [roll_treasure("boss", zone, rng, theme=theme) for _ in range(rules.weighted_count(*rules.MIMIC_TREASURES, rng))]
        return loot
    r = rules.REWARDS[kind]
    lo, hi = r["money"]
    loot["money"] = rules.money_roll(lo, hi, rng, money_mult)
    if "materials" in r:
        loot["materials"] = roll_materials(zone, rules.weighted_count(*r["materials"], rng), rng, theme=theme)
    if "items" in r:
        loot["items"] = roll_cheap_items(rules.weighted_count(*r["items"], rng), rng)
    if r.get("relic_chance") and rng.random() < r["relic_chance"]:
        loot["relics"].append(roll_relic(zone, rng))
    if "relics" in r:
        classes = sorted({m["cls"] for m in combat.living(run["party"])})
        loot["relics"].append(roll_relic(zone, rng, classes=classes))
    if r.get("treasure_chance") and rng.random() < r["treasure_chance"]:
        loot["treasures"].append(roll_treasure(r["treasure_table"], zone, rng, theme=theme))
    if "treasures" in r:
        loot["treasures"] += [roll_treasure(r["treasure_table"], zone, rng, theme=theme) for _ in range(rules.weighted_count(*r["treasures"], rng))]
    return loot


# =========================================================
# 🚪 選門
# =========================================================
def _guaranteed(run: dict, floor: int) -> str | None:
    """每 100 關先放好 LR 2 個、UR 5 個在寶箱 (生成地圖時就分配，位置只跟 seed 有關)"""
    block = (floor - 1) // 100
    key = str(block)
    if key not in run["guaranteed"]:
        rng = random.Random(f"{run['seed']}:g{block}")
        cand = [block * 100 + z * 10 + f for z in range(10) for f in (1, 3, 5, 7)]
        picks = rng.sample(cand, sum(rules.GUARANTEED_PER_100.values()))
        plan, i = {}, 0
        for rarity, n in rules.GUARANTEED_PER_100.items():
            for p in picks[i:i + n]:
                plan[str(p)] = rarity
            i += n
        run["guaranteed"][key] = plan
    return run["guaranteed"][key].get(str(floor))


def _battle_door(run: dict, floor: int, rng) -> dict:
    z = zone_theme(run, rules.zone_of(floor))
    n = rules.weighted_count(1, 3, rng)
    return {"type": "battle", "foes": [rng.choice(z["normals"]) for _ in range(n)]}


def _elite_door(run: dict, floor: int, rng) -> dict:
    z = zone_theme(run, rules.zone_of(floor))
    return {"type": "elite", "foes": [z["elite"]] + [rng.choice(z["normals"]) for _ in range(rules.weighted_count(0, 2, rng))]}


def _chest_door(run: dict, floor: int, rng, hidden: bool = False) -> dict:
    d = {"type": "chest", "locked": rng.random() < rules.LOCKED_CHANCE, "mimic": rng.random() < rules.MIMIC_CHANCE}
    if hidden:
        d["hidden"] = True
    if d["mimic"]:
        d["foes"] = _elite_door(run, floor, rng)["foes"]
    return d


def _event_door(run: dict, rng) -> dict:
    w = data.event_weights()
    etype = rng.choices(list(w), weights=list(w.values()))[0]
    ids = [k for k, e in data.events().items() if e["type"] == etype and not e.get("fest")]
    return {"type": "event", "event": rng.choice(ids), "etype": etype}


def _make_door(run: dict, floor: int, kind: str, rng) -> dict:
    if kind == "battle":
        return _battle_door(run, floor, rng)
    if kind == "elite":
        return _elite_door(run, floor, rng)
    if kind == "chest":
        return _chest_door(run, floor, rng)
    if kind == "event":
        return _event_door(run, rng)
    return {"type": kind}


def gen_doors(run: dict, floor: int, rng) -> list[dict]:
    """這一關要選的 2～3 扇門 (第 2 / 4 / 6 / 8 關固定戰鬥、第 9 關商人、第 10 關 BOSS)"""
    fz, zone = rules.floor_in_zone(floor), rules.zone_of(floor)
    caps = run["caps"].setdefault(str(zone), {})
    team = run["team"]
    force_chest = status.has_flag(team, "force_chest")
    force_elite = status.has_flag(team, "force_elite")
    doors: list[dict] = []
    if fz == 10:
        doors = [{"type": "boss", "foes": [zone_theme(run, zone)["boss"]]}]
    elif fz == 9:
        doors = [{"type": "merchant"}]
    elif fz in rules.BATTLE_FLOORS:
        doors = [_battle_door(run, floor, rng)]
        if caps.get("elite", 0) < rules.ROOM_CAPS["elite"] or force_elite:
            doors.append(_elite_door(run, floor, rng))
        else:
            doors.append(_battle_door(run, floor, rng))
        if force_elite:
            status.consume_flag(team, "force_elite")
    else:
        n = rules.weighted_count(*rules.DOOR_COUNT, rng)
        kinds: list[str] = []
        if force_chest:
            kinds.append("chest")
            status.consume_flag(team, "force_chest")
        if force_elite:
            kinds.append("elite")
            status.consume_flag(team, "force_elite")
        while len(kinds) < n:
            pool = {k: w for k, w in rules.ROOM_WEIGHTS.items()
                    if k == "battle" or (k not in kinds and caps.get(k, 0) + kinds.count(k) < rules.ROOM_CAPS[k])}
            kinds.append(rng.choices(list(pool), weights=list(pool.values()))[0])
        doors = [_make_door(run, floor, k, rng) for k in kinds]
        g = _guaranteed(run, floor)
        if g:
            chest = next((d for d in doors if d["type"] == "chest" and not d.get("mimic")), None)
            if chest is None:
                chest = {"type": "chest", "locked": False, "mimic": False}
                doors.append(chest)
            chest["guaranteed"] = g
    if fz < 9 and combat.has_scout(run) and rng.random() < rules.HIDDEN_CHEST_CHANCE:
        doors.append(_chest_door(run, floor, rng, hidden=True))
    for d in doors:
        if d["type"] in rules.ROOM_CAPS and not d.get("hidden"):
            caps[d["type"]] = caps.get(d["type"], 0) + 1
    fest.maybe_convert(run, floor, doors, rng)   # 🎪 活動期間 10% 其中一扇變成活動門
    return doors


def door_view(run: dict, door: dict, revealed: bool) -> dict:
    """門上顯示的東西 (沒有斥候只看得到類型；有斥候 / 望遠鏡 / 提燈多看細節)"""
    t = door["type"]
    v = {"type": t}
    if door.get("fest"):
        v["fest"] = door["fest"]   # 🎪 一定看得到 (環境也寫在門上)
    if t == "battle":
        v["count"] = len(door["foes"])
    if not revealed:
        return v
    if t in ("battle", "elite", "boss") or (t == "chest" and door.get("mimic")):
        es = data.enemies()
        v["foes"] = [es[e]["name"] for e in door.get("foes", [])]
    if t == "chest":
        v["locked"], v["mimic"] = door.get("locked"), door.get("mimic")
    if t == "event":
        v["etype"] = door["etype"]
    return v


def doors_revealed(run: dict) -> bool:
    return combat.has_scout(run) or run.get("revealed") == run["floor"] + 1


def _set_doors(run: dict, rng):
    nxt = run["floor"] + 1
    if run.get("peek") and run["peek"]["floor"] == nxt:
        run["doors"] = run["peek"]["doors"]
        run["peek"] = None
    else:
        run["doors"] = gen_doors(run, nxt, rng)
    run["phase"] = "doors"
    run["room"] = None


# =========================================================
# 🆕 開局
# =========================================================
def new_run(seed: str, cards: list[tuple[dict, dict]], bag_items: dict, pocket: int, rng,
            capacity: int = rules.BAG_SLOTS, live_fests: list[str] | None = None) -> dict:
    """cards = [(卡牌 {instance_id, character_key, rarity, completeness}, 角色資料 data.characters()[id]), ...]"""
    party = [combat.make_member(i, card, char) for i, (card, char) in enumerate(cards)]
    run = {"v": VERSION, "seed": seed, "act": 0, "step": 0, "floor": 0, "sanity": rules.SANITY_START, "b": rules.B_START,
           "pocket": int(pocket), "brought": int(pocket), "party": party, "capacity": capacity,
           "bag": {"items": {k: v for k, v in bag_items.items() if v > 0}, "materials": {}, "treasures": [], "relics": []},
           "team": {"statuses": []}, "phase": "doors", "doors": [], "room": None, "battle": None, "last": None,
           "caps": {}, "guaranteed": {}, "peek": None, "revealed": None, "pending": [], "exp": 0,
           "kills": {}, "boss_cleared": 0, "result": None, "log": [], "live_fests": list(live_fests or []), "themes": []}
    zone_theme(run, 1)   # 第 1 區的主題先抽好 (畫面一開始就要顯示)
    _set_doors(run, rng)
    return run


def note(run: dict, text: str):
    run["log"].append(text)
    run["log"] = run["log"][-8:]


# =========================================================
# 👣 進一關
# =========================================================
def choose_door(run: dict, idx: int, rng) -> str | None:
    if run["phase"] != "doors":
        return "現在不能選門"
    if not 0 <= idx < len(run["doors"]):
        return "沒有這扇門"
    door = run["doors"][idx]
    _enter_floor(run, rng)
    if run["phase"] == "ended":
        return None
    _start_room(run, door, rng)
    return None


def _enter_floor(run: dict, rng):
    run["step"] += 1
    run["floor"] += 1
    run["pending"] = []
    run["doors"] = []
    zone = rules.zone_of(run["floor"])
    run["sanity"] -= rules.sanity_per_floor(zone, combat.has_guide(run))
    combat.add_b(run, rules.B_STEP)
    for m in run["party"]:
        m["cd"] = max(0, m["cd"] - 1)
        status.tick(m, "steps")
    status.tick(run["team"], "steps")
    for m in combat.living(run["party"]):
        for inst, act in status.actions(m, "floor_enter"):
            if act["do"] == "b_point":
                combat.add_b(run, act["value"])
    run["exp"] += rules.exp_floor(zone)
    _check_sanity(run)


def _check_sanity(run: dict) -> bool:
    if run["sanity"] <= 0 and run["phase"] != "ended":
        run["sanity"] = 0
        _end(run, "failed", "🌀 常識度歸零，全隊迷失在裏世界……")
        return True
    return False


def _start_room(run: dict, door: dict, rng):
    t = door["type"]
    run["room"] = dict(door)
    if t == "battle":
        if status.consume_flag(run["team"], "skip_normal_battle"):
            note(run, "🌫️ 光學迷彩：悄悄繞過了這場戰鬥")
            return _set_doors(run, rng)
        combat.start(run, "normal", door["foes"], rng)
    elif t == "elite":
        boss = bool(door.get("fest_boss"))
        if boss and run.get("fest_boss_seen"):   # 🎪 活動 BOSS 一局只打一次：已經打過 ➔ 這扇退回活動精英
            boss = False
            run["room"]["fest_boss"] = False
            run["room"]["foes"] = list(door.get("elite_foes") or door["foes"])
        if boss:
            run["fest_boss_seen"] = True
        combat.start(run, "elite", run["room"]["foes"], rng, fest_boss=boss)
    elif t == "boss":
        combat.start(run, "boss", door["foes"], rng)
    elif t == "chest":
        run["phase"] = "chest"
    elif t == "event":
        _start_event(run, door, rng)
    elif t == "trap":
        _trap(run, rng)
    elif t == "merchant":
        run["room"]["stock"] = _merchant_stock(run, rng)
        run["phase"] = "merchant"


def leave_room(run: dict, rng) -> str | None:
    """離開寶箱 / 事件 / 陷阱 / 商人 ➔ 下一關的門"""
    if run["phase"] not in ("chest", "event", "trap", "merchant"):
        return "現在不能離開"
    if run["phase"] == "event" and run["room"].get("pending_choice") is None and not run["room"].get("done"):
        run["room"]["done"] = True
    _set_doors(run, rng)
    return None


# =========================================================
# ⚔️ 戰鬥 (包一層：每個動作做完檢查戰鬥結束)
# =========================================================
def battle_action(run: dict, action: str, rng, uid: str | None = None, target: str | None = None,
                  item: str | None = None) -> str | None:
    if run["phase"] != "battle" or not run.get("battle"):
        return "現在不在戰鬥中"
    why = None
    if action == "attack":
        why = None if combat.attack(run, uid, target, rng) else "這位不能行動 / 要選目標"
    elif action == "spell":
        why = combat.cast(run, uid, target, rng)
    elif action == "item":
        why = use_item(run, item, target, rng)
    elif action == "ofuda":
        why = combat.use_ofuda(run, uid, target, rng)
    elif action == "flee":
        why = combat.flee(run, rng)
    else:
        why = "不認識的動作"
    if why is None:
        _after_battle_step(run, rng)
    return why


def target_kind(run: dict, action: str, uid: str | None = None, item: str | None = None) -> str | None:
    """
    (給畫面用) 這個動作要不要先選目標：enemy / ally (活著的隊友) / dead (倒下的隊友)；
    不用選或只有一個可以選 ➔ None (引擎會自動挑那一個)
    """
    b = run.get("battle")
    foes = combat.living(b["foes"]) if b else []

    def need(kind: str) -> str | None:
        if kind == "enemy":
            return "enemy" if len(foes) > 1 else None
        pool = [m for m in run["party"] if (not m["alive"]) == (kind == "dead")]
        return kind if len(pool) > 1 else None

    if action == "attack":
        return need("enemy")
    u = combat.find_unit(run, uid) if uid else None
    if action == "spell" and u:
        t = data.spells()[u["cid"]]["target"]
        return need("enemy") if t == "enemy_one" else need("ally") if t == "ally_one" else None
    if action == "ofuda" and u and u.get("relic"):
        act = data.relics()[u["relic"]["rid"]].get("active") or {}
        return need("enemy") if act.get("do") == "apply" and act.get("target") == "enemy_one" else None
    if action == "item" and item in data.items():
        do = data.items()[item]["effect"]["do"]
        if do == "heal":
            return need("ally")
        if do == "revive":
            return need("dead")
        if do in ("persuade", "apply"):
            return need("enemy")
    return None


def usable_items(run: dict) -> list[str]:
    """(給畫面用) 現在背包裡用得到的道具 (被動的、這個階段不能用的不列)"""
    phase = run["phase"]
    out = []
    for iid, n in run["bag"]["items"].items():
        it = data.items().get(iid)
        if not it or n <= 0:
            continue
        use = it.get("use")
        if use == "passive" or (use == "battle" and phase != "battle") or (use == "doors" and phase != "doors"):
            continue
        do = it["effect"]["do"]
        if (do == "evacuate" and phase == "battle") or (do == "revive" and all(m["alive"] for m in run["party"])):
            continue
        out.append(iid)
    return out


def _after_battle_step(run: dict, rng):
    if _check_sanity(run):
        return
    over = combat.is_over(run)
    if not over:
        return
    b = run["battle"]
    if over == "wipe":
        combat.finish(run)
        return _end(run, "failed", "💀 全隊倒下了……")
    zone = rules.zone_of(run["floor"])
    mult = b["money_mult"] * b["spell_money"]
    total = {"items": {}, "materials": {}, "treasures": [], "relics": [], "money": 0}
    for k in b["killed"]:
        loot = foe_loot(run, k["kind"], rng, mult)
        if b.get("fest"):
            fest.decorate_loot(run, b["fest"], k["kind"], loot, zone, rng)   # 🎪 活動保留格 / 活動法具
        _merge(total, loot)
        run["exp"] += rules.exp_for(k["kind"], zone)
        run["kills"][k["eid"]] = run["kills"].get(k["eid"], 0) + 1
    money = total.pop("money")
    run["pocket"] += money
    stash(run, total)
    run["last"] = {"kind": b["kind"], "over": over, "killed": list(b["killed"]), "loot": total, "money": money,
                   "floor": run["floor"]}
    combat.finish(run)
    if over == "win" and b["kind"] == "boss" and not b.get("fest_boss"):
        run["boss_cleared"] = zone
        run["phase"] = "boss_clear"
        run["battle"] = None
        return
    run["battle"] = None
    _set_doors(run, rng)


# =========================================================
# 💰 寶箱
# =========================================================
def open_chest(run: dict, rng, force: bool = False) -> str | None:
    """打開寶箱 (上鎖的要鑰匙)；寶箱怪 ➔ 精英戰"""
    if run["phase"] not in ("chest", "event"):
        return "這裡沒有寶箱"
    room = run["room"]
    if room.get("opened"):
        return "已經打開了"
    if room.get("mimic"):
        room["opened"] = True
        note(run, "📦 寶箱突然張開大嘴——是寶箱怪！")
        combat.start(run, "mimic", room["foes"], rng)
        return None
    if room.get("locked") and not force:
        if not _take_item(run, "chest_key"):
            return "要 🗝️ 寶箱鑰匙才打得開"
    room["opened"] = True
    zone = rules.zone_of(run["floor"])
    c = rules.CHESTS["locked" if room.get("locked") else "normal"]
    lo, hi = c["money"]
    loot = {"items": roll_cheap_items(rules.weighted_count(*c["items"], rng), rng),
            "materials": roll_materials(zone, rules.weighted_count(*c["materials"], rng), rng, theme=zone_theme(run, zone)),
            "treasures": [roll_treasure(c["table"], zone, rng, theme=zone_theme(run, zone))
                          for _ in range(rules.weighted_count(*c["treasures"], rng))],
            "relics": [roll_relic(zone, rng)] if rng.random() < c["relic_chance"] else []}
    if room.get("guaranteed"):
        loot["treasures"].append(roll_treasure(c["table"], zone, rng, rarity=room["guaranteed"], theme=zone_theme(run, zone)))
    if room.get("fest"):
        fest.decorate_loot(run, room["fest"], "chest", loot, zone, rng)   # 🎪 活動保留格 / 活動法具
    money = rules.money_roll(lo * zone, hi * zone, rng)
    run["pocket"] += money
    stash(run, loot)
    room["loot"] = {**loot, "money": money}
    return None


# =========================================================
# 🕳️ 陷阱
# =========================================================
def _trap(run: dict, rng):
    run["phase"] = "trap"
    room = run["room"]
    if combat.has_scout(run):
        room["result"] = "scout"
        return
    if status.consume_flag(run["team"], "trap_immune"):
        room["result"] = "amulet"
        return
    items = [i for i, n in run["bag"]["items"].items() if n > 0]
    if items and rng.random() < 0.5:
        lost = rng.choice(items)
        _take_item(run, lost)
        room["result"], room["lost"] = "item", lost
    else:
        for m in combat.living(run["party"]):
            d = max(1, rules.round_half(combat.max_hp(m) * rules.TRAP_HP_PCT))
            m["hp"] = max(1, m["hp"] - d)
        room["result"] = "hp"


# =========================================================
# ❓ 事件
# =========================================================
def _start_event(run: dict, door: dict, rng):
    run["phase"] = "event"
    eid = door["event"]
    ev = data.events()[eid]
    if ev["type"] != "good" and status.consume_flag(run["team"], "good_event"):
        fid = door.get("fest")
        pool = ([k for k, e in data.events().items() if e["type"] == "good" and e.get("fest") == fid]
                or [k for k, e in data.events().items() if e["type"] == "good" and not e.get("fest")])
        eid = rng.choice(pool)
        ev = data.events()[eid]
    room = run["room"]
    room["event"], room["etype"] = eid, ev["type"]
    if ev.get("choice"):
        room["pending_choice"] = eid
        return
    room["result"] = _event_effect(run, ev["effect"], rng)


def _event_effect(run: dict, eff: dict, rng, choice: dict | None = None) -> dict:
    zone = rules.zone_of(run["floor"])
    do = eff["do"]
    res = {"do": do}
    if do == "heal_all":
        for m in combat.living(run["party"]):
            combat.heal(m, eff["pct"])
    elif do == "money":
        lo, hi = eff["range"]
        k = zone if eff.get("per_zone") else 1
        res["money"] = rules.money_roll(lo * k, hi * k, rng)
        run["pocket"] += res["money"]
    elif do == "cheap_item":
        loot = {"items": roll_cheap_items(eff.get("count", 1), rng)}
        stash(run, loot)
        res["items"] = loot["items"]
    elif do == "b_point":
        combat.add_b(run, eff["value"])
    elif do == "team_status":
        status.apply(run["team"], eff["status"])
    elif do == "sanity":
        v = rules.sanity_per_floor(zone, combat.has_guide(run)) * eff["floor_mult"]
        run["sanity"] += v
        res["sanity"] = v
        _check_sanity(run)
    elif do == "damage_all_pct":
        for m in combat.living(run["party"]):
            d = max(1, rules.round_half(combat.max_hp(m) * eff["pct"]))
            m["hp"] = max(eff.get("min_hp", 1), m["hp"] - d)
    elif do == "lose_money_pct":
        lost = rules.round_half(run["pocket"] * eff["pct"])
        run["pocket"] -= lost
        res["money"] = -lost
    elif do == "cooldown_all":
        for m in run["party"]:
            m["cd"] += eff["value"]
    elif do == "apply_random_ally":
        alive = combat.living(run["party"])
        if alive:
            t = rng.choice(alive)
            status.apply(t, eff["status"], turns=eff.get("steps"))
            res["target"] = t["name"]
    return res


def event_choice(run: dict, accept: bool, rng, pick=None) -> str | None:
    """特殊事件：accept = 要不要做；pick = 選的東西 (祠堂：寶物位置、試煉：隊友 uid、狐狸：3 個道具 id)"""
    room = run.get("room") or {}
    if run["phase"] != "event" or not room.get("pending_choice"):
        return "現在沒有要選的事件"
    ev = data.events()[room["pending_choice"]]
    eff = ev["effect"]
    zone = rules.zone_of(run["floor"])
    if not accept:
        room["pending_choice"], room["result"] = None, {"do": "declined"}
        return None
    do = eff["do"]
    res = {"do": do}
    if do == "gamble":
        cost = eff["cost"] * (zone if eff.get("per_zone") else 1)
        if run["pocket"] < cost:
            return f"口袋的錢不夠 (要 {cost:,})"
        run["pocket"] -= cost
        win = rng.random() < eff["chance"]
        if win:
            run["pocket"] += cost * eff["payout"]
        res.update(cost=cost, win=win)
    elif do == "upgrade_treasure":
        ts = run["bag"]["treasures"]
        if pick is None or not 0 <= pick < len(ts) or ts[pick]["rarity"] == "LR":
            return "要選一個還不是 LR 的寶物"
        old = ts[pick]
        nr = rules.RARITIES[rules.RARITIES.index(old["rarity"]) + 1]
        ts[pick] = roll_treasure("monster", zone, rng, rarity=nr, theme=zone_theme(run, zone))
        res.update(old=old, new=ts[pick])
    elif do == "trial":
        t = combat.find_unit(run, pick) if pick else None
        if not t or not t["alive"] or t["side"] != "ally":
            return "要選一位隊友"
        d = max(1, rules.round_half(combat.max_hp(t) * eff["hp_pct"]))
        t["hp"] = max(1, t["hp"] - d)
        left = 10 - rules.floor_in_zone(run["floor"]) + 1
        for m in combat.living(run["party"]):
            status.apply(m, eff["status"], turns=left)
        res.update(target=t["name"])
    elif do == "trade_items_for_relic":
        picks = list(pick or [])
        if len(picks) != eff["items"]:
            return f"要選 {eff['items']} 個道具"
        need = {}
        for i in picks:
            need[i] = need.get(i, 0) + 1
        if any(run["bag"]["items"].get(i, 0) < n for i, n in need.items()):
            return "背包裡沒有這些道具"
        for i in picks:
            _take_item(run, i)
        rel = roll_relic(zone, rng)
        stash(run, {"relics": [rel]})
        res.update(relic=rel)
    elif do == "buy_fest_treasure":   # 😈 小惡魔的交易：付錢換 1 個活動寶物
        cost = eff["cost"] * (zone if eff.get("per_zone") else 1)
        if run["pocket"] < cost:
            return f"口袋的錢不夠 (要 {cost:,})"
        t = fest.roll_treasure(room.get("fest") or ev.get("fest"), zone, rng)
        if not t:
            return "這個活動沒有活動寶物"
        run["pocket"] -= cost
        stash(run, {"treasures": [t]})
        res.update(cost=cost, treasure=t)
    elif do == "sealed_box":
        room["mimic"] = False
        if run["bag"]["items"].get("chest_key", 0) > 0:
            room["locked"] = True
            room["pending_choice"] = None
            res.update(how="key")
            room["result"] = res
            return open_chest(run, rng)
        if rng.random() < eff["force_chance"]:
            room["locked"] = True
            room["pending_choice"] = None
            res.update(how="forced")
            room["result"] = res
            return open_chest(run, rng, force=True)
        room["mimic"] = True
        room["foes"] = _elite_door(run, run["floor"], rng)["foes"]
        room["pending_choice"] = None
        res.update(how="mimic")
        room["result"] = res
        return open_chest(run, rng)
    room["pending_choice"], room["result"] = None, res
    return None


# =========================================================
# 🛒 流浪商人
# =========================================================
def _merchant_stock(run: dict, rng) -> list[dict]:
    pool = [i for i, it in data.items().items() if it.get("merchant", True) and it.get("price")]
    picks = rng.sample(pool, min(rules.MERCHANT_KINDS, len(pool)))
    stock = [{"kind": "item", "id": i, "qty": rules.weighted_count(*rules.MERCHANT_QTY, rng),
              "price": rules.round_half(data.items()[i]["price"] * rules.MERCHANT_MARKUP)} for i in picks]
    if rng.random() < rules.MERCHANT_RELIC_CHANCE:
        r = rng.random()
        tier, price = (0, rules.MERCHANT_RELIC[0][2]) if r < rules.MERCHANT_RELIC[0][1] else (1, rules.MERCHANT_RELIC[1][2])
        rid = rng.choice(list(data.base_relics()))
        rel = {"rid": rid, "tier": tier}
        if data.relics()[rid]["type"] == "ofuda":
            rel["left"] = data.relics()[rid]["uses"][tier]
        stock.append({"kind": "relic", "relic": rel, "qty": 1, "price": price})
    return stock


def buy(run: dict, idx: int) -> str | None:
    if run["phase"] != "merchant":
        return "這裡沒有商人"
    stock = run["room"]["stock"]
    if not 0 <= idx < len(stock) or stock[idx]["qty"] <= 0:
        return "賣完了"
    s = stock[idx]
    if run["pocket"] < s["price"]:
        return f"口袋的錢不夠 (要 {s['price']:,})"
    if s["kind"] == "item":
        why = can_add(run, "items", s["id"])
        if why:
            return why
        run["bag"]["items"][s["id"]] = run["bag"]["items"].get(s["id"], 0) + 1
    else:
        why = can_add(run, "relics", s["relic"])
        if why:
            return why
        run["bag"]["relics"].append(dict(s["relic"]))
    run["pocket"] -= s["price"]
    s["qty"] -= 1
    return None


# =========================================================
# 🧪 道具
# =========================================================
def use_item(run: dict, iid: str, target: str | None, rng) -> str | None:
    """用道具 (不算行動)；target = 隊友 / 敵人 uid"""
    it = data.items().get(iid)
    if not it or run["bag"]["items"].get(iid, 0) <= 0:
        return "背包裡沒有這個道具"
    phase = run["phase"]
    in_battle = phase == "battle"
    use = it.get("use")
    if use == "passive":
        return "這個道具會自動生效"
    if use == "battle" and not in_battle:
        return "只能在戰鬥中用"
    if use == "doors" and phase != "doors":
        return "只能在選門時用"
    if phase == "ended":
        return "這局已經結束了"
    eff = it["effect"]
    do = eff["do"]
    if do == "heal":
        t = combat._pick_ally(run, target)
        if not t:
            return "要選一位隊友"
        combat.heal(t, eff["pct"])
    elif do == "heal_all":
        for m in combat.living(run["party"]):
            combat.heal(m, eff["pct"])
    elif do == "sanity":
        combat.add_sanity(run, eff["value"])
    elif do == "revive":
        t = combat._pick_ally(run, target, dead=True)
        if not t:
            return "要選一位倒下的隊友"
        t["alive"] = True
        t["hp"] = max(1, rules.round_half(combat.max_hp(t) * eff["pct"]))
    elif do == "persuade":
        why = combat.persuade(run, target, rng)
        if why:
            return why
    elif do == "b_point":
        combat.add_b(run, eff["value"])
    elif do == "reveal_doors":
        run["revealed"] = run["floor"] + 1
    elif do == "peek_next":
        nxt = run["floor"] + 2
        if run.get("peek") and run["peek"]["floor"] == nxt:
            return "已經看過下下一關了"
        run["peek"] = {"floor": nxt, "doors": gen_doors(run, nxt, rng)}
    elif do == "reroll_doors":
        run["doors"] = gen_doors(run, run["floor"] + 1, rng)
    elif do == "team_status":
        status.apply(run["team"], eff["status"])
    elif do == "skip_floor":
        if rules.floor_in_zone(run["floor"] + 1) == 10:
            return "不能跳過 BOSS"
        _take_item(run, iid)
        _enter_floor(run, rng)
        if run["phase"] != "ended":
            note(run, "🌀 穿過隙間，跳過了一關")
            _set_doors(run, rng)
        return None
    elif do == "bomb":
        top = max(combat.eff_atk(m) for m in combat.living(run["party"]))
        for f in combat.living(run["battle"]["foes"]):
            combat.deal(run, None, f, eff["mult"], rng, source_atk=top)
        combat._log(run, "💣 炸彈！敵人全體受傷")
    elif do == "apply":
        t = combat._pick_foe(run, target, rng)
        if not t:
            return "要選一隻敵人"
        if t["kind"] == "boss" and "boss_immune" in status.info(eff["status"]).get("flags", []):
            return "對 BOSS 無效"
        status.apply(t, eff["status"], turns=eff.get("turns"), is_boss=t["kind"] == "boss", rng=rng)
    elif do == "evacuate":
        if in_battle:
            return "戰鬥中不能用"
        _take_item(run, iid)
        _end(run, "evacuated", "🔙 用歸還符回到了幻想鄉")
        return None
    else:
        return "這個道具現在不能用"
    _take_item(run, iid)
    return None


def cast_outside(run: dict, uid: str, rng) -> str | None:
    """戰鬥外放符卡 (千百合：重抽這一關的門)"""
    if run["phase"] != "doors":
        return "只能在選門時用"
    u = combat.find_unit(run, uid)
    if not u:
        return "找不到這位角色"
    why = combat.spell_ready(run, u, in_battle=False)
    if why:
        return why
    run["b"] -= u["b_cost"]
    u["cd"] = u["cd_max"]
    run["doors"] = gen_doors(run, run["floor"] + 1, rng)
    note(run, f"🚢 {u['name']}：可能性移動船，重抽了門")
    return None


# =========================================================
# 🦊 法具
# =========================================================
def equip_relic(run: dict, bag_idx: int, uid: str) -> str | None:
    """背包裡的法具給一位隊友 (換下來的放回背包)"""
    relics = run["bag"]["relics"]
    if not 0 <= bag_idx < len(relics):
        return "沒有這個法具"
    u = combat.find_unit(run, uid)
    if not u or u["side"] != "ally":
        return "要選一位隊友"
    rel = relics.pop(bag_idx)
    old = u.get("relic")
    if old:
        _unequip(u)
        relics.append(old)
    _equip(u, rel)
    return None


def unequip_relic(run: dict, uid: str) -> str | None:
    """隊友身上的法具卸下來放回背包 (使用者 2026-11-21 要加；戰鬥中不行、背包要放得下；御札的職業加成次數只加一次，卸下也不會重算)"""
    if run["phase"] == "battle":
        return "戰鬥中不能卸下法具"
    u = combat.find_unit(run, uid)
    if not u or u["side"] != "ally" or not u.get("relic"):
        return "這位隊友沒有裝法具"
    if can_add(run, "relics", u["relic"]):
        return "背包滿了，先丟掉一些東西"
    rel = u["relic"]
    _unequip(u)
    run["bag"]["relics"].append(rel)
    return None


def _equip(u: dict, rel: dict):
    rd = data.relics()[rel["rid"]]
    u["relic"] = rel
    match = u["cls"] == rd.get("class")
    if rd.get("passive"):
        v = rd["values"][rel["tier"]]
        bonus = rd.get("class_bonus", {}) if match else {}
        v = v * bonus.get("mult", 1) + bonus.get("add", 0)
        before = combat.max_hp(u)
        status.apply(u, rd["passive"], value=v)
        if rd["passive"] == "relic_life":   # 最大 HP 變多：多出來的部分直接補上
            u["hp"] += combat.max_hp(u) - before
    if rd["type"] == "ofuda" and match and not rel.get("bonus"):
        rel["left"] = rel.get("left", 0) + rd.get("class_bonus", {}).get("uses", 0)
        rel["bonus"] = True


def _unequip(u: dict):
    rel = u.get("relic")
    if not rel:
        return
    rd = data.relics()[rel["rid"]]
    if rd.get("passive"):
        status.remove(u, rd["passive"])
        u["hp"] = min(u["hp"], combat.max_hp(u))
    u["relic"] = None


# =========================================================
# 🏁 結束 / 結算
# =========================================================
def evacuate(run: dict) -> str | None:
    """打完 BOSS 之後撤離"""
    if run["phase"] != "boss_clear":
        return "打完 BOSS 才能撤離"
    _end(run, "evacuated", "🏁 成功撤離！")
    return None


def continue_after_boss(run: dict, rng) -> str | None:
    if run["phase"] != "boss_clear":
        return "現在不能繼續"
    _set_doors(run, rng)
    return None


def abandon(run: dict) -> str | None:
    if run["phase"] == "ended":
        return "這局已經結束了"
    _end(run, "abandoned", "🏳️ 放棄了探索")
    return None


def _end(run: dict, result: str, text: str):
    run["result"] = result
    run["phase"] = "ended"
    note(run, text)


def settle(run: dict) -> dict:
    """
    結算 (純計算，交給資料層在同一個交易裡發 / 扣)：
    成功撤離 ➔ 口袋的錢、背包的道具 / 素材 / 寶物全部帶回，經驗 100%，只有倒下的卡完整度 −0.1
    失敗 / 放棄 ➔ 全部掉光，經驗 50%，派出的每張卡完整度 −0.1
    """
    ok = run["result"] == "evacuated"
    exp = run["exp"] if ok else math.floor(run["exp"] * rules.FAIL_EXP_RATIO)
    penalty = [m["card_id"] for m in run["party"] if (not ok) or (not m["alive"])]
    z = zone_theme(run, rules.zone_of(max(1, run["floor"])))   # 結束在哪個主題 (公開結算顯示用)
    return {"result": run["result"], "floor": run["floor"], "exp": exp, "penalty": penalty,
            "money": run["pocket"] if ok else 0, "brought": run.get("brought", 0),
            "items": dict(run["bag"]["items"]) if ok else {},
            "materials": dict(run["bag"]["materials"]) if ok else {},
            "treasures": list(run["bag"]["treasures"]) if ok else [],
            "deepest": run["floor"] if ok else None,
            "party": [{"cid": m["cid"], "rarity": m["rarity"], "name": m["name"], "alive": m["alive"]} for m in run["party"]],
            "relics": [m["relic"] for m in run["party"] if m.get("relic")],
            "kills": dict(run["kills"]),
            "zone_name": f"{z.get('emoji', '')} {z.get('name', '')}"}

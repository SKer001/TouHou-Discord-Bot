"""
⚔️ 裏世界的回合制戰鬥 (docs/ura.md「戰鬥」)：純邏輯，狀態存在 run["battle"] / run["party"]

一回合：輪到我方 (B +1、冷卻 −1) ➔ 選一位角色做一件事 (普攻 / 符卡；用道具、御札不算行動) ➔
        敵方回合 (B +1，每隻活著的敵人各動一下) ➔ 回合結束 (中毒、式神…) ➔ 狀態回合數 −1
呼叫端每個動作傳入 rng，結果都寫回 dict。
"""
import math

from Database.ura import data, fest, rules, status

ALLY, ENEMY = "ally", "enemy"


# =========================================================
# 🧍 單位
# =========================================================
def make_member(idx: int, card: dict, char: dict) -> dict:
    """出征的卡 ➔ 隊伍成員；card = {"instance_id", "character_key", "rarity", "completeness"}"""
    cid, rarity, comp = card["character_key"], card["rarity"], float(card["completeness"])
    m = rules.RARITY_MULT[rarity] * rules.comp_mult(comp)
    sp = data.spells()[cid]
    base = char["base"]
    u = {"uid": f"p{idx}", "side": ALLY, "cid": cid, "card_id": card["instance_id"], "name": char["name"],
         "emoji": char["emoji"], "cls": char["class"], "rarity": rarity, "comp": comp,
         "tier": char["rarities"].index(rarity) if rarity in char["rarities"] else 0,
         "base_hp": base["hp"] * m, "base_atk": base["atk"] * m, "base_def": base["def"] * m,
         "alive": True, "cd": 0, "cd_max": rules.spell_cooldown(sp["cd"], comp), "b_cost": sp["b"],
         "spell_name": char.get("spell_name", ""), "statuses": [], "relic": None}
    u["hp"] = max_hp(u)
    return u


def make_foe(idx: int, eid: str, kind: str, zone: int, suffix: str = "") -> dict:
    """kind = fest_boss (🎪 活動 BOSS)：數值用活動 BOSS 的倍率，之後當成 BOSS (kind = boss + fest_boss 標記)"""
    e = data.enemies()[eid]
    hp, atk, df = rules.enemy_stats(zone, kind, e)
    if kind == "fest_boss":
        kind = "boss"
    u = {"uid": f"e{idx}", "side": ENEMY, "eid": eid, "name": e["name"] + suffix, "emoji": e["emoji"], "kind": kind,
         "base_hp": hp, "base_atk": atk, "base_def": df, "alive": True, "dodge": e.get("dodge", 0),
         "skills": list(e.get("skills", [])), "cds": {}, "phase2": False, "ctrl_count": 0, "rot": 0, "statuses": []}
    u["hp"] = max_hp(u)
    return u


def max_hp(u: dict) -> int:
    return max(1, rules.round_half(u["base_hp"] * (1 + status.mod(u, "max_hp_pct"))))


def eff_atk(u: dict, battle: dict | None = None) -> float:
    atk = u["base_atk"] * status.stat_mult(u, "atk_pct")
    if u["side"] == ENEMY:
        if u.get("phase2"):
            atk *= 1 + rules.BOSS_PHASE2_ATK
        if battle and battle["kind"] != "boss" and battle["round"] > rules.ENRAGE_AFTER:
            atk *= 1 + rules.ENRAGE_STEP * (battle["round"] - rules.ENRAGE_AFTER)
    return atk


def eff_def(u: dict) -> float:
    df = u["base_def"] * status.stat_mult(u, "def_pct")
    fm = status.final_mult(u, "def_final_mult")
    return math.floor(df * fm) if fm != 1 else df


def living(units: list) -> list:
    return [u for u in units if u["alive"]]


def find_unit(run: dict, uid: str) -> dict | None:
    for u in run["party"] + (run.get("battle") or {}).get("foes", []):
        if u["uid"] == uid:
            return u
    return None


def has_guide(run: dict) -> bool:
    return any(m["alive"] and m["cls"] == "guide" for m in run["party"])


def has_scout(run: dict) -> bool:
    return any(m["alive"] and m["cls"] == "scout" for m in run["party"]) or status.has_flag(run["team"], "scout")


def add_sanity(run: dict, n: int):
    """回常識度，最多 1000 (超過的浪費掉；使用者 2026-11-20)"""
    run["sanity"] = min(rules.SANITY_START, run["sanity"] + int(n))


def add_b(run: dict, n: float):
    run["b"] = max(0, min(rules.B_MAX, run["b"] + int(n)))


def _log(run: dict, text: str):
    b = run.get("battle")
    if b is not None:
        b["log"].append(text)
        b["log"] = b["log"][-14:]


# =========================================================
# 🎬 開始 / 結束
# =========================================================
def start(run: dict, kind: str, foe_ids: list[str], rng, fest_boss: bool = False) -> dict:
    """
    kind = normal / elite / mimic / boss；foe_ids[0] 是主角 (精英 / BOSS)，其他是小弟
    fest_boss = 🎪 活動 BOSS (從精英門換來的)：當成 BOSS 戰 (不能逃、第二階段、不狂暴)，數值用活動 BOSS 倍率
    🎪 活動房間 (run["room"]["fest"]) 的戰鬥套用那個活動的環境
    """
    zone = rules.zone_of(run["floor"])
    fid = (run.get("room") or {}).get("fest")
    if fest_boss:
        kind = "boss"
    foes = []
    names = {}
    for i, eid in enumerate(foe_ids):
        fkind = kind if i == 0 and kind != "normal" else "normal"
        names[eid] = names.get(eid, 0) + 1
        foe = make_foe(i, eid, "fest_boss" if fest_boss and i == 0 else fkind, zone)
        if fest_boss and i == 0:
            foe["fest_boss"] = True
        elif fkind == "boss" and zone > 1:   # 區域 BOSS 只有第 1 區用完整招式，第 2 區以後先只普攻 (使用者 2026-11-20；各區有自己的 BOSS 再調)
            foe["skills"] = []
        foes.append(foe)
    seen = {}
    for f in foes:   # 同名的加 A / B / C
        if foe_ids.count(f["eid"]) > 1:
            seen[f["eid"]] = seen.get(f["eid"], 0) + 1
            f["name"] += f" {'ABCDE'[seen[f['eid']] - 1]}"
    money_mult = 1.0
    if status.consume_flag(run["team"], "money_x1.5"):
        money_mult = 1.5
    run["battle"] = {"kind": kind, "foes": foes, "round": 1, "acted": [], "actions_left": 1, "time_stop": None,
                     "ofuda_used": False, "persuade_tried": [], "money_mult": money_mult, "spell_money": 1.0,
                     "killed": [], "log": [], "over": None, "fest": fid, "fest_boss": fest_boss}
    run["phase"] = "battle"
    if fid:
        fest.apply_environment(run, run["battle"], fid)   # 🌫️ 環境 (這場戰鬥有效)
    for u in living(run["party"]) + foes:
        _trigger(run, u, "battle_start", rng)
    return run["battle"]


def is_over(run: dict) -> str | None:
    b = run.get("battle")
    if not b:
        return None
    if b["over"]:
        return b["over"]
    if not living(run["party"]):
        b["over"] = "wipe"
    elif not living(b["foes"]):
        b["over"] = "win"
    return b["over"]


# =========================================================
# 💥 傷害
# =========================================================
def deal(run: dict, attacker: dict | None, target: dict, mult: float, rng, *, single: bool = False,
         ignore_def: float = 0.0, source_atk: float | None = None, counter: bool = False) -> int:
    """attacker 打 target (攻擊 × mult)；回傳造成的傷害 (閃避 / 無敵 = 0)"""
    b = run.get("battle")
    if not target["alive"]:
        return 0
    dodge = (target.get("dodge") or 0) + status.mod(target, "dodge_pct")
    if single and dodge > 0 and rng.random() < dodge:
        _log(run, f"💨 {target['name']} 閃開了！")
        return 0
    atk = (source_atk if source_atk is not None else eff_atk(attacker, b)) * mult
    if attacker is not None and attacker["side"] == ALLY and b and b.get("time_stop"):
        atk *= b["time_stop"]
    atk *= status.final_mult(target, "incoming_atk_mult")
    df = eff_def(target) * (1 - ignore_def)
    if status.has_flag(target, "invuln"):
        _log(run, f"🌟 {target['name']} 無敵，沒有受傷")
        return 0
    dmg = atk * rng.uniform(*rules.DAMAGE_VARIANCE) * (1 - rules.dmg_reduction(df)) * (1 + status.mod(target, "dmg_taken_pct"))
    block = status.mod(target, "block_pct")
    if block:
        dmg *= 1 - block
        status.consume(target, "shield")
    dmg = max(1, rules.round_half(dmg))
    target["hp"] -= dmg
    if attacker is not None and attacker["alive"] and not counter:
        steal = status.mod(attacker, "lifesteal_pct")   # 🦇 吸血鬼的契約
        if steal > 0:
            heal_amt = max(1, rules.round_half(dmg * steal))
            attacker["hp"] = min(max_hp(attacker), attacker["hp"] + heal_amt)
    if status.has(target, "sleep"):
        status.remove(target, "sleep")
    if not counter and attacker is not None and attacker["alive"]:
        for inst, act in status.actions(target, "on_hit"):
            if act["do"] == "reflect_pct":
                r = max(1, rules.round_half(dmg * act["value"]))
                attacker["hp"] -= r
                _log(run, f"♨️ {attacker['name']} 被反彈 {r}")
                if attacker["hp"] <= 0:
                    down(run, attacker)
            elif act["do"] == "counter" and target["hp"] > 0:
                c = deal(run, target, attacker, act["mult"], rng, single=False, counter=True)
                _log(run, f"🌀 {target['name']} 反擊 {attacker['name']} {c}")
    if target["hp"] <= 0:
        down(run, target)
    elif target["side"] == ENEMY and target["kind"] == "boss" and not target["phase2"] and target["hp"] <= max_hp(target) / 2:
        target["phase2"] = True
        _log(run, f"🔥 {target['name']} 進入第二階段！ATK 上升")
    return dmg


def heal(u: dict, pct: float) -> int:
    if not u["alive"]:
        return 0
    mh = max_hp(u)
    before = u["hp"]
    u["hp"] = min(mh, u["hp"] + max(1, rules.round_half(mh * pct)))
    return u["hp"] - before


def down(run: dict, u: dict):
    """HP 歸 0：我方有替身人形就留 1；敵人倒下記錄獎勵、B +1"""
    if u["side"] == ALLY:
        bag = run["bag"]["items"]
        if bag.get("substitute_doll", 0) > 0:
            bag["substitute_doll"] -= 1
            if not bag["substitute_doll"]:
                del bag["substitute_doll"]
            u["hp"] = 1
            _log(run, f"🎎 替身人形救了 {u['name']} 一命！")
            return
        u["hp"], u["alive"] = 0, False
        _log(run, f"💀 {u['name']} 倒下了")
        return
    u["hp"], u["alive"] = 0, False
    b = run["battle"]
    b["killed"].append({"eid": u["eid"], "kind": "fest_boss" if u.get("fest_boss") else u["kind"], "how": "killed"})
    add_b(run, rules.B_KILL)
    _log(run, f"✨ 打倒了 {u['name']}")


# =========================================================
# 🙋 我方行動
# =========================================================
def can_act(run: dict, u: dict) -> bool:
    b = run["battle"]
    return b and not b["over"] and u["side"] == ALLY and u["alive"] and u["uid"] not in b["acted"] and b["actions_left"] > 0


def spell_ready(run: dict, u: dict, in_battle: bool = True) -> str | None:
    """不能放的原因 (None = 可以放)"""
    sp = data.spells()[u["cid"]]
    if not u["alive"]:
        return "倒下了"
    if u["cd"] > 0:
        return f"冷卻中 ({u['cd']})"
    if run["b"] < u["b_cost"]:
        return f"B 點不夠 (要 {u['b_cost']})"
    if not in_battle and not sp.get("outside"):
        return "只能在戰鬥中用"
    if in_battle and u["cid"] == "chiyuri" and run["battle"]["kind"] != "normal":
        return "只能跳過一般戰鬥"
    return None


def attack(run: dict, uid: str, target_uid: str | None, rng) -> bool:
    """普攻 (攻擊 × 1，不花 B 點)"""
    u, b = find_unit(run, uid), run["battle"]
    if not u or not can_act(run, u):
        return False
    t = _pick_foe(run, target_uid, rng)
    if not t:
        return False
    d = deal(run, u, t, 1.0, rng, single=True)
    _log(run, f"{u['emoji']} {u['name']} 普攻 {t['name']} {d}")
    _used(run, u, rng)
    return True


def _pick_foe(run: dict, target_uid: str | None, rng) -> dict | None:
    live = living(run["battle"]["foes"])
    if not live:
        return None
    if len(live) == 1:
        return live[0]
    t = find_unit(run, target_uid) if target_uid else None
    return t if t in live else None


def _pick_ally(run: dict, target_uid: str | None, dead: bool = False) -> dict | None:
    pool = [m for m in run["party"] if (not m["alive"]) == dead]
    if len(pool) == 1:
        return pool[0]
    t = find_unit(run, target_uid) if target_uid else None
    return t if t in pool else None


def cast(run: dict, uid: str, target_uid: str | None, rng) -> str | None:
    """放符卡；成功回傳 None，失敗回傳原因。戰鬥外 (千百合) 由 run.py 處理"""
    u = find_unit(run, uid)
    in_battle = run.get("phase") == "battle"
    if not u:
        return "找不到這位角色"
    why = spell_ready(run, u, in_battle)
    if why:
        return why
    if in_battle and not can_act(run, u):
        return "這回合不能行動"
    sp = data.spells()[u["cid"]]
    params = sp["tiers"][min(u["tier"], len(sp["tiers"]) - 1)]

    def val(v):
        return params.get(v[1:]) if isinstance(v, str) and v.startswith("$") else v

    target = None
    if sp["target"] == "enemy_one":
        target = _pick_foe(run, target_uid, rng)
        if not target:
            return "要選一隻敵人"
    elif sp["target"] == "ally_one":
        target = _pick_ally(run, target_uid)
        if not target:
            return "要選一位隊友"
    run["b"] -= u["b_cost"]
    u["cd"] = u["cd_max"]
    _log(run, f"{u['emoji']} {u['name']}：{u.get('spell_name') or sp.get('desc', '')}")
    hit = []
    foes = living(run["battle"]["foes"]) if in_battle else []
    for eff in sp["effects"]:
        e = {k: val(v) for k, v in eff.items()}
        do = e["do"]
        if do == "damage" and target:
            mult = e["mult"] * (e.get("vs_strong", 1) if target.get("kind") in ("elite", "mimic", "boss") else 1)
            hp0 = target["hp"]
            d = deal(run, u, target, mult, rng, single=True, ignore_def=e.get("ignore_def", 0))
            if d:
                hit.append(target)
            _log(run, f"💥 {target['name']} {d}")
            if e.get("drain") and d:
                heal_amt = max(1, rules.round_half((hp0 - max(0, target["hp"])) * e["drain"]))
                u["hp"] = min(max_hp(u), u["hp"] + heal_amt)
                _log(run, f"🩸 {u['name']} 吸血 {heal_amt}")
        elif do == "damage_all":
            for f in foes:
                d = deal(run, u, f, e["mult"], rng)
                if d:
                    hit.append(f)
            _log(run, "🌟 全體攻擊")
        elif do == "multi_hit":
            n = rules.weighted_count(e["hits"][0], e["hits"][1], rng)
            for _ in range(n):
                live = living(run["battle"]["foes"])
                if not live:
                    break
                f = rng.choice(live)
                d = deal(run, u, f, e["mult"], rng, single=True)
                hit.append(f)
            _log(run, f"✴️ 打了 {n} 下")
        elif do == "heal" and target:
            _log(run, f"💚 {target['name']} 回復 {heal(target, e['pct'])}")
        elif do == "heal_all":
            for m in living(run["party"]):
                heal(m, e["pct"])
            _log(run, "💚 全隊回血")
        elif do == "heal_self":
            heal(u, e["pct"])
        elif do == "apply":
            to = e.get("to")
            turns = e.get("turns")
            if e.get("turns_choice"):
                a, z = e["turns_choice"]
                turns = a if a == z else rng.choice([a, z])
            src = eff_atk(u) if e["status"] == "doll_legion" else None
            if to == "self":
                tgts = [u]
            elif to == "allies":
                tgts = living(run["party"])
            elif to == "enemies":
                tgts = living(run["battle"]["foes"]) if in_battle else []
            elif to == "target":
                tgts = [target] if target else []
            else:   # hit：這招打中的敵人 (同一隻只算一次)
                tgts, seen = [], set()
                for f in hit:
                    if f["alive"] and f["uid"] not in seen:
                        seen.add(f["uid"])
                        tgts.append(f)
            for t in tgts:
                if e.get("chance") is not None and rng.random() >= e["chance"]:
                    continue
                ok = status.apply(t, e["status"], turns=turns, value=e.get("value"), src_atk=src,
                                  is_boss=t.get("kind") == "boss", rng=rng)
                if ok:
                    _log(run, f"{status.info(e['status'])['emoji']} {t['name']} {status.info(e['status'])['name']}")
        elif do == "time_stop" and in_battle:
            b = run["battle"]
            others = [m for m in living(run["party"]) if m is not u and m["uid"] not in b["acted"]]
            b["time_stop"] = e.get("mult", 1.0)
            b["actions_left"] += len(others)
            _log(run, "⏱️ 時間停止！全員再行動一次")
        elif do == "sanity":
            add_sanity(run, int(e["value"]))
            _log(run, f"🧭 常識度 +{int(e['value'])}")
        elif do == "money_mult" and in_battle:
            run["battle"]["spell_money"] = max(run["battle"]["spell_money"], e["value"])
        elif do == "skip_battle" and in_battle:
            run["battle"]["over"] = "skipped"
            _log(run, "🚢 可能性移動船：跳過了這場戰鬥")
    if u["cls"] == "sup":   # 💚 輔助放任何符卡 ➔ 順便淨化全隊可以清除的壞狀態 (裏・神綺的破解，2026-11-21 使用者定)
        n = sum(status.cleanse(m) for m in living(run["party"]))
        if n:
            _log(run, f"✨ 淨化：清掉了全隊 {n} 個壞狀態")
    if in_battle:
        _used(run, u, rng)
    return None


def _used(run: dict, u: dict, rng):
    b = run["battle"]
    b["acted"].append(u["uid"])
    b["actions_left"] -= 1
    if is_over(run):
        return
    if b["actions_left"] <= 0:
        enemy_phase(run, rng)


def use_ofuda(run: dict, uid: str, target_uid: str | None, rng) -> str | None:
    """📜 御札：主動、有次數、一回合一次、不算行動"""
    u, b = find_unit(run, uid), run.get("battle")
    if not b or b["over"]:
        return "只能在戰鬥中用"
    if b["ofuda_used"]:
        return "一回合只能用一次御札"
    rel = u.get("relic") if u else None
    if not rel or data.relics()[rel["rid"]]["type"] != "ofuda" or not u["alive"]:
        return "沒有可以用的御札"
    if rel.get("left", 0) <= 0:
        return "御札用完了"
    rd = data.relics()[rel["rid"]]
    act = rd["active"]
    value = (rd.get("values") or [None] * 3)[rel["tier"]]
    if act["do"] == "apply" and act["target"] == "enemy_one":
        t = _pick_foe(run, target_uid, rng)
        if not t:
            return "要選一隻敵人"
        if t["kind"] == "boss" and "boss_immune" in status.info(act["status"]).get("flags", []):
            return "對 BOSS 無效"
        status.apply(t, act["status"], turns=act.get("turns"), is_boss=t["kind"] == "boss", rng=rng)
        _log(run, f"📜 {t['name']} {status.info(act['status'])['name']}")
    elif act["do"] == "apply":
        for m in living(run["party"]):
            status.apply(m, act["status"], value=value)
        _log(run, f"📜 全隊 {status.info(act['status'])['name']}")
    elif act["do"] == "extra_action":   # ⏱️ 女僕長的懷錶：這回合多一次行動 (另一位隊友也能動)
        if not any(m["alive"] and m["uid"] not in b["acted"] for m in run["party"]) or b["actions_left"] >= len(living(run["party"])):
            return "沒有其他隊友可以多行動"
        b["actions_left"] += 1
        _log(run, "⏱️ 這回合多一次行動！")
    elif act["do"] == "damage_all":
        mult = value * (rd.get("class_bonus", {}).get("mult", 1) if u["cls"] == rd.get("class") else 1)
        for f in living(b["foes"]):
            deal(run, u, f, mult, rng)
        _log(run, "📜 爆符：全體攻擊")
    rel["left"] -= 1
    b["ofuda_used"] = True
    is_over(run)
    return None


def persuade(run: dict, target_uid: str | None, rng) -> str | None:
    """🍡 糰子：一般怪 / 精英有機率離開 (獎勵照算)、BOSS 有機率露出破綻；同一隻每場只能試一次 (用了就沒了)"""
    b = run["battle"]
    t = _pick_foe(run, target_uid, rng)
    if not t:
        return "要選一隻敵人"
    if t["uid"] in b["persuade_tried"]:
        return "這隻已經試過了"
    b["persuade_tried"].append(t["uid"])
    chance = rules.persuade_chance(run["floor"], t["kind"])
    if rng.random() < chance:
        if t["kind"] == "boss":
            status.apply(t, "breach")
            _log(run, f"💢 {t['name']} 露出了破綻！")
        else:
            t["alive"], t["hp"] = False, 0
            b["killed"].append({"eid": t["eid"], "kind": t["kind"], "how": "persuaded"})
            add_b(run, rules.B_KILL)
            _log(run, f"🍡 {t['name']} 吃了糰子，心滿意足地離開了")
    else:
        _log(run, f"🍡 {t['name']} 不理你……")
    is_over(run)
    return None


def flee(run: dict, rng) -> str | None:
    """🏃 逃跑：一定成功；扣常識度 (煙霧彈不扣)；BOSS 戰不能逃"""
    b = run["battle"]
    if b["kind"] == "boss":
        return "BOSS 戰不能逃"
    bag = run["bag"]["items"]
    if bag.get("smoke_bomb", 0) > 0:
        bag["smoke_bomb"] -= 1
        if not bag["smoke_bomb"]:
            del bag["smoke_bomb"]
        _log(run, "💨 用煙霧彈逃跑了")
    else:
        cost = rules.flee_cost(rules.zone_of(run["floor"]), has_guide(run), b["kind"])
        run["sanity"] -= cost
        _log(run, f"🏃 逃跑了 (常識度 −{cost})")
    b["over"] = "fled"
    return None


# =========================================================
# 👹 敵方回合
# =========================================================
def _choose_target(run: dict, rng) -> dict | None:
    alive = living(run["party"])
    if not alive:
        return None
    taunt = [m for m in alive if status.has_flag(m, "taunt")]
    if taunt:
        return taunt[0]
    w = [max(1, m["hp"]) * (rules.GUARD_WEIGHT if m["cls"] == "guard" else 1) for m in alive]
    return rng.choices(alive, weights=w)[0]


def _available_skills(foe: dict) -> list[dict]:
    out = []
    for s in foe["skills"]:
        if s.get("phase2") and not foe["phase2"]:
            continue
        if foe["cds"].get(s["id"], 0) > 0:
            continue
        if s.get("when_hp_below") and foe["hp"] / max_hp(foe) >= s["when_hp_below"]:
            continue
        out.append(s)
    return out


def _pick_skill(run: dict, foe: dict, rng) -> dict | None:
    avail = _available_skills(foe)
    if not avail:
        return None
    if foe["kind"] == "boss":
        if run["battle"]["round"] % 2:
            return None
        order = foe["skills"]
        for i in range(len(order)):
            s = order[(foe["rot"] + i) % len(order)]
            if s in avail:
                foe["rot"] = (order.index(s) + 1) % len(order)
                return s
        return None
    if rng.random() < rules.SKILL_CHANCE.get(foe["kind"], 0.35):
        return rng.choice(avail)
    return None


def _foe_act(run: dict, foe: dict, rng):
    b = run["battle"]
    skill = _pick_skill(run, foe, rng)
    if skill is None:
        t = _choose_target(run, rng)
        if t:
            d = deal(run, foe, t, 1.0, rng)
            _log(run, f"{foe['emoji']} {foe['name']} 攻擊 {t['name']} {d}")
        return
    if skill.get("cd"):
        foe["cds"][skill["id"]] = skill["cd"] + 1   # +1：這回合結束就會 −1
    do = skill["do"]
    name = f"{foe['emoji']} {foe['name']}「{skill['name']}」"
    if do == "attack_one":
        t = _choose_target(run, rng)
        if t:
            d = deal(run, foe, t, skill.get("mult", 1.0), rng)
            _log(run, f"{name} ➔ {t['name']} {d}")
            if skill.get("status") and d and t["alive"]:
                status.apply(t, skill["status"], turns=skill.get("turns"), value=skill.get("status_value"), fresh=True)
    elif do == "attack_all":
        alive = living(run["party"])
        taunt = [m for m in alive if status.has_flag(m, "taunt")]
        tgts = taunt[:1] if skill.get("taunt_redirect") and taunt else alive
        for t in tgts:
            deal(run, foe, t, skill.get("mult", 1.0), rng)
        _log(run, f"{name} 打" + ("嘲諷中的 " + tgts[0]["name"] if len(tgts) == 1 and taunt else "全隊"))
    elif do == "sanity":   # 🧭 嚮導的「少扣 30%」也算在敵人扣常識度的招式上 (裏・幽幽子的破解，2026-11-21 使用者定)
        n = int(skill["value"])
        guide = has_guide(run)
        if guide:
            n = rules.round_half(n * (1 - rules.GUIDE_DISCOUNT))
        run["sanity"] -= n
        _log(run, f"{name}：常識度 −{n}" + (" (🧭 嚮導少扣 30%)" if guide else ""))
    elif do == "heal_self":
        _log(run, f"{name}：回復 {heal(foe, skill['value'])}")
    elif do == "apply_party":
        for m in living(run["party"]):
            status.apply(m, skill["status"], turns=skill.get("turns"), value=skill.get("status_value"), fresh=True)
        _log(run, f"{name}：全隊 {status.info(skill['status'])['name']}")
    elif do == "apply_self":
        status.apply(foe, skill["status"], turns=skill.get("turns"), value=skill.get("status_value"), fresh=True)
        _log(run, f"{name}：{status.info(skill['status'])['name']}")


def _trigger(run: dict, u: dict, trigger: str, rng):
    for inst, act in status.actions(u, trigger):
        if not u["alive"]:
            return
        do = act["do"]
        if do == "dot_max_hp_pct":
            d = max(1, rules.round_half(max_hp(u) * act["value"]))
            floor_hp = act.get("min_hp", 1)   # 持續扣血最多扣到剩 1，不會直接打死 (使用者 2026-11-20)
            u["hp"] = max(floor_hp, u["hp"] - d)
            _log(run, f"{status.info(inst['id'])['emoji']} {u['name']} −{d}")
            if u["hp"] <= 0:
                down(run, u)
        elif do == "auto_attack" and run.get("battle"):
            live = living(run["battle"]["foes"])
            if live:
                src = inst.get("src_atk") if act.get("use") == "source_atk" else None
                if src is None:
                    src = eff_atk(u)
                f = rng.choice(live)
                d = deal(run, u, f, act["mult"], rng, source_atk=src)
                _log(run, f"{status.info(inst['id'])['emoji']} 幫忙攻擊 {f['name']} {d}")
        elif do == "heal_lowest_pct":
            alive = living(run["party"])
            if alive:
                t = min(alive, key=lambda m: m["hp"] / max_hp(m))
                heal(t, act["value"])
        elif do == "b_point":
            add_b(run, act["value"])


def enemy_phase(run: dict, rng):
    """敵方回合 + 回合結束 + 下一回合開始"""
    b = run["battle"]
    add_b(run, 1)
    for foe in list(b["foes"]):
        if not foe["alive"] or not living(run["party"]):
            continue
        if status.has_flag(foe, "skip_turn"):
            _log(run, f"{foe['emoji']} {foe['name']} 動不了")
            continue
        _foe_act(run, foe, rng)
    # 回合結束
    for u in living(run["party"]) + living(b["foes"]):
        _trigger(run, u, "round_end", rng)
    for u in run["party"] + b["foes"]:
        status.tick(u, "rounds")
    for foe in b["foes"]:
        for k in list(foe["cds"]):
            foe["cds"][k] = max(0, foe["cds"][k] - 1)
    if b["kind"] != "boss" and b["round"] >= rules.ENRAGE_AFTER:
        for foe in living(b["foes"]):
            status.apply(foe, "enrage")
    if is_over(run):
        return
    # 下一回合
    b["round"] += 1
    b["acted"], b["actions_left"], b["time_stop"], b["ofuda_used"] = [], 1, None, False
    add_b(run, 1)
    for m in run["party"]:
        m["cd"] = max(0, m["cd"] - 1)
    for u in living(run["party"]) + living(b["foes"]):
        _trigger(run, u, "round_start", rng)
    is_over(run)


def finish(run: dict):
    """戰鬥結束：清掉只在戰鬥中有效的狀態"""
    b = run.get("battle")
    for u in run["party"] + (b["foes"] if b else []):
        status.end_battle(u)

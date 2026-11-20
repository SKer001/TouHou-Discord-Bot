"""
🎪 裏世界的活動關卡 (docs/ura.md「活動融入」B 組，使用者 2026-11-20)：純邏輯

- run["live_fests"] = 現在進行中、有裏世界內容的活動 id (資料層每一步更新；活動一結束就不再出 🎪 門)
- 活動期間每一關 10%：其中一扇門 (戰鬥 / 精英 / 寶箱 / 事件) 變成 🎪 活動門，保留原本房間類型；
  每區最多 2 扇；第 9 關 (商人)、第 10 關 (BOSS) 不換
- 🎪 戰鬥 / 精英：敵人換成活動怪物；🎪 精英門 25% 換成活動 BOSS (一局最多一次)
- 環境 (例 🌫️ 紅霧)：在那個活動房間的戰鬥裡才有效 (狀態 duration = battle)，另外有錢的倍率
- 🎪 活動保留格：🎪 房間裡「本來就會掉寶物」時多擲一格 (0 / 1 / 2 個 = 20 / 70 / 10%)，只有 SSR / UR / LR；
  活動 BOSS 一定掉 (1 / 2 個 = 80 / 20%) + 一定給 1 個活動法具；其他法具 50% 換成活動法具
"""
from Database.ura import data, rules, status


def live(run: dict) -> list[str]:
    return [f for f in run.get("live_fests") or [] if f in data.fests()]


def info(fid: str | None) -> dict:
    return data.fests().get(fid or "", {})


# =========================================================
# 🚪 活動門
# =========================================================
def maybe_convert(run: dict, floor: int, doors: list[dict], rng):
    """gen_doors 最後呼叫：這一關要不要有一扇 🎪 門 (沒有進行中的活動就完全不擲亂數)"""
    fids = live(run)
    if not fids:
        return
    fz, zone = rules.floor_in_zone(floor), rules.zone_of(floor)
    if fz >= 9:
        return
    caps = run.setdefault("fest_caps", {})
    if caps.get(str(zone), 0) >= rules.FEST_ZONE_CAP:
        return
    if rng.random() >= rules.FEST_STAGE_CHANCE:
        return
    cand = [d for d in doors if d["type"] in rules.FEST_ROOM_TYPES and not d.get("hidden") and not d.get("fest")]
    if not cand:
        return
    door = rng.choice(cand)
    convert(run, door, rng.choice(fids), rng)
    caps[str(zone)] = caps.get(str(zone), 0) + 1


def convert(run: dict, door: dict, fid: str, rng):
    """把一扇門變成那個活動的版本 (保留房間類型)"""
    f = info(fid)
    door["fest"] = fid
    t = door["type"]
    normals = f.get("normals") or []
    if t == "battle" and normals:
        door["foes"] = [rng.choice(normals) for _ in door.get("foes", [None])]
    elif t == "elite":
        if f.get("elite"):   # 先照活動精英排好 (活動 BOSS 已經打過時，進門會退回這一組)
            door["foes"] = [f["elite"]] + [rng.choice(normals) for _ in door.get("foes", [None])[1:]] if normals else [f["elite"]]
        if f.get("boss") and not run.get("fest_boss_seen") and rng.random() < rules.FEST_BOSS_CHANCE:
            door["elite_foes"] = list(door.get("foes", []))
            door["foes"], door["fest_boss"] = [f["boss"]], True   # 「一局一次」等真的打到才算 (run.start_room)
    elif t == "chest" and door.get("mimic") and f.get("elite"):
        door["foes"] = [f["elite"]] + ([rng.choice(normals) for _ in door.get("foes", [None])[1:]] if normals else [])
    elif t == "event":
        evs = {k: e for k, e in data.events().items() if e.get("fest") == fid}
        if evs:
            w = {k: v for k, v in data.event_weights().items() if any(e["type"] == k for e in evs.values())}
            etype = rng.choices(list(w), weights=list(w.values()))[0]
            door["event"] = rng.choice([k for k, e in evs.items() if e["type"] == etype])
            door["etype"] = etype


# =========================================================
# 🌫️ 環境 (戰鬥開始時)
# =========================================================
def apply_environment(run: dict, battle: dict, fid: str):
    env = info(fid).get("environment") or {}
    for m in run["party"]:
        if not m["alive"]:
            continue
        for sid in env.get("statuses", []):
            status.apply(m, sid)
        for sid in (env.get("class_statuses") or {}).get(m["cls"], []):
            status.apply(m, sid)
    battle["money_mult"] *= env.get("money_mult", 1)


def env_text(fid: str | None) -> str | None:
    """「🌫️ 紅霧：我方每回合 −2% HP…」(選門、戰鬥畫面用)"""
    env = info(fid).get("environment")
    if not env:
        return None
    return f"{env.get('emoji', '')} {env.get('name', '')}：{env.get('desc', '')}".strip("：")


# =========================================================
# 💎 活動寶物 / 🦊 活動法具
# =========================================================
def roll_treasure(fid: str, zone: int, rng) -> dict | None:
    """活動寶物：階級用 BOSS 那張 SSR 起跳的表 (越深往 LR 移)，同階級平均抽"""
    pool = data.fest_treasures(fid)
    if not pool:
        return None
    r = rules.roll_rarity("boss", zone, rng)
    lst = pool.get(r) or next(v for v in pool.values() if v)   # 活動檔少寫某一階就用有寫的那一階
    tid = rng.choice(lst)[0]
    return {"id": tid, "rarity": data.treasure_info(tid)["rarity"], "zone": zone, "fest": fid}


def roll_relic(fid: str, zone: int, rng, tier: int | None = None) -> dict | None:
    pool = {k: v for k, v in data.relics().items() if v.get("fest") == fid}
    if not pool:
        return None
    rid = rng.choice(list(pool))
    if tier is None:
        tier = ["SSR", "UR", "LR"].index(rules.roll_rarity("boss", zone, rng))
    rel = {"rid": rid, "tier": tier}
    if pool[rid]["type"] == "ofuda":
        rel["left"] = pool[rid]["uses"][tier]
    return rel


def decorate_loot(run: dict, fid: str, kind: str, loot: dict, zone: int, rng):
    """
    🎪 房間的戰利品加料 (kind = 敵人種類 normal / elite / mimic / fest_boss，或 chest)：
    - 活動 BOSS：一定 1 個活動法具 + 保留格 1～2 個
    - 其他：這次本來就有掉寶物 ➔ 擲保留格 0～2 個；掉的法具 50% 換成活動法具 (等級不變)
    """
    if not info(fid):
        return
    loot.setdefault("treasures", [])
    loot.setdefault("relics", [])
    loot["relics"] = [(roll_relic(fid, zone, rng, tier=r["tier"]) or r) if rng.random() < rules.FEST_RELIC_CHANCE else r
                      for r in loot["relics"]]
    if kind == "fest_boss":
        rel = roll_relic(fid, zone, rng)
        if rel:
            loot["relics"].append(rel)
        n = rules.pick_weighted(rules.FEST_BOSS_TREASURE_SLOT, rng)
    elif loot["treasures"]:
        n = rules.pick_weighted(rules.FEST_TREASURE_SLOT, rng)
    else:
        n = 0
    for _ in range(n):
        t = roll_treasure(fid, zone, rng)
        if t:
            loot["treasures"].append(t)

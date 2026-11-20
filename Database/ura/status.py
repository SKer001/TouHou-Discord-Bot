"""
✨ 統一的「狀態效果」系統 (docs/ura.md「狀態效果」)：狀態本身寫在 data/statuses.json

一個單位 (角色 / 敵人) 的 u["statuses"] = [{"id", "left", "stacks", "value", "src_atk"}, ...]
- 同一個狀態只有 1 層 (max_stacks > 1 的才能疊)；再被施加 ➔ 刷新持續時間
- 名字不同的狀態可以同時存在、效果互加
- 倍率：同一類 (group：item / relic / spell / env) 相加，不同類相乘
"""
from Database.ura import data

GROUPS = ("item", "relic", "spell", "env")


def defs() -> dict:
    return data.statuses()


def info(sid: str) -> dict:
    return defs().get(sid, {"name": sid, "emoji": "❔", "good": False, "duration": "rounds", "default": 1, "max_stacks": 1})


def _resolve(v, inst: dict):
    """mods / 動作裡的 "value" / "-value" 換成施加時給的數字"""
    if v == "value":
        return inst.get("value") or 0
    if v == "-value":
        return -(inst.get("value") or 0)
    return v


def find(u: dict, sid: str) -> dict | None:
    return next((s for s in u.get("statuses", []) if s["id"] == sid), None)


def has(u: dict, sid: str) -> bool:
    return find(u, sid) is not None


def has_flag(u: dict, flag: str) -> bool:
    return any(flag in info(s["id"]).get("flags", []) for s in u.get("statuses", []))


def apply(u: dict, sid: str, turns: int | None = None, value=None, src_atk: float | None = None,
          is_boss: bool = False, rng=None) -> bool:
    """
    施加狀態；成功回傳 True
    BOSS：boss_immune 的無效；boss_half 的回合數減半 (無條件捨去，0 = 無效)，每被控一次下次成功率再減半 (u["ctrl_count"])
    """
    d = info(sid)
    flags = d.get("flags", [])
    left = d.get("default", 1) if turns is None else turns
    if is_boss and "boss_immune" in flags:
        return False
    if is_boss and "boss_half" in flags:
        left //= 2
        chance = 0.5 ** u.get("ctrl_count", 0)
        if left <= 0 or (rng is not None and rng.random() >= chance):
            return False
        u["ctrl_count"] = u.get("ctrl_count", 0) + 1
    if d.get("duration") in ("battle", "run"):
        left = 1
    cur = find(u, sid)
    if cur:
        cur["left"] = max(cur["left"], left) if d.get("duration") == "count" else left
        if cur["stacks"] < d.get("max_stacks", 1):
            cur["stacks"] += 1
        if value is not None:
            cur["value"] = value
        if src_atk is not None:
            cur["src_atk"] = src_atk
        return True
    inst = {"id": sid, "left": left, "stacks": 1}
    if value is not None:
        inst["value"] = value
    if src_atk is not None:
        inst["src_atk"] = src_atk
    u.setdefault("statuses", []).append(inst)
    return True


def remove(u: dict, sid: str):
    u["statuses"] = [s for s in u.get("statuses", []) if s["id"] != sid]


def cleanse(u: dict) -> int:
    """淨化：清掉可以清除的壞狀態，回傳清了幾個"""
    before = len(u.get("statuses", []))
    u["statuses"] = [s for s in u.get("statuses", [])
                     if info(s["id"]).get("good") or "cleanse" not in info(s["id"]).get("flags", [])]
    return before - len(u["statuses"])


def mod(u: dict, key: str) -> float:
    """所有狀態的某個修正加總 (含層數)"""
    total = 0.0
    for s in u.get("statuses", []):
        v = info(s["id"]).get("mods", {}).get(key)
        if v is not None:
            total += _resolve(v, s) * s.get("stacks", 1)
    return total


def stat_mult(u: dict, key: str) -> float:
    """atk_pct / def_pct：同一類相加、不同類相乘 ➔ 總倍率"""
    sums = {}
    for s in u.get("statuses", []):
        d = info(s["id"])
        v = d.get("mods", {}).get(key)
        if v is not None:
            g = d.get("group", "spell")
            sums[g] = sums.get(g, 0.0) + _resolve(v, s) * s.get("stacks", 1)
    m = 1.0
    for v in sums.values():
        m *= max(0.0, 1 + v)
    return m


def final_mult(u: dict, key: str) -> float:
    """最後才乘的倍率 (例：破綻 def_final_mult / incoming_atk_mult)，有就乘、沒有就是 1"""
    m = 1.0
    for s in u.get("statuses", []):
        v = info(s["id"]).get("mods", {}).get(key)
        if v is not None:
            m *= v
    return m


def actions(u: dict, trigger: str) -> list[tuple[dict, dict]]:
    """這個時機要做的動作：[(狀態實例, 動作 dict (value / mult 已換成數字)), ...]"""
    out = []
    for s in list(u.get("statuses", [])):
        for act in info(s["id"]).get("on", {}).get(trigger, []):
            a = {k: _resolve(v, s) for k, v in act.items()}
            out.append((s, a))
    return out


def tick(u: dict, duration: str):
    """持續方式是 duration (rounds / steps) 的狀態 −1，用完的拿掉"""
    keep = []
    for s in u.get("statuses", []):
        if info(s["id"]).get("duration") == duration:
            s["left"] -= 1
            if s["left"] <= 0:
                continue
        keep.append(s)
    u["statuses"] = keep


def consume(u: dict, sid: str) -> bool:
    """次數型的狀態用掉一次；用完拿掉"""
    s = find(u, sid)
    if not s:
        return False
    s["left"] -= 1
    if s["left"] <= 0:
        remove(u, sid)
    return True


def consume_flag(u: dict, flag: str) -> bool:
    """有這個 flag 的次數型狀態用掉一次"""
    for s in u.get("statuses", []):
        if flag in info(s["id"]).get("flags", []):
            return consume(u, s["id"])
    return False


def end_battle(u: dict):
    """這場戰鬥的狀態清掉 (duration = battle / rounds 都只在戰鬥中有效)"""
    u["statuses"] = [s for s in u.get("statuses", []) if info(s["id"]).get("duration") not in ("battle", "rounds")
                     and "battle_only" not in info(s["id"]).get("flags", [])]


def label(s: dict) -> str:
    """戰鬥畫面上的「☠️ 中毒 (2)」"""
    d = info(s["id"])
    left = "" if d.get("duration") in ("battle", "run") else f" ({s['left']})"
    stacks = f"×{s['stacks']}" if s.get("stacks", 1) > 1 else ""
    return f"{d.get('emoji', '')} {d.get('name', s['id'])}{stacks}{left}"

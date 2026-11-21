"""
📖 裏世界怪物圖鑑 (純邏輯，不 import discord；規格 docs/ura.md「📖 怪物圖鑑」，使用者 2026-11-21 定)

- 解鎖 = 打倒或用糰子勸走過 (player_stats 的 ura_kill:<敵人> >= 1；打倒當下就記)；寶箱怪算那一區的精英
- 分區：每個主題一區 (zones.json 的順序；copy_of 借名單的主題不列) + 每個有裏世界內容的活動一區 (🎪)
- 完成度：一般主題的怪合計 (📖 x / 25)，活動怪另外算 (🎪 x / 5)
- 獎勵 (rules.BESTIARY_REWARDS)：每區全收 / 一般主題全收 / 每個活動的活動怪全收；領取紀錄 ura_bestiary_claims
"""
from Database.ura import data, rules

ROLE_NAMES = {"normal": "一般", "elite": "💀 精英", "boss": "👹 BOSS", "fest_boss": "👹 活動 BOSS"}
ALL_REWARD = "all"
# 區域 BOSS 第 2 區起的規則 (combat.start / rules.DEEP_BOSS_*；使用者 2026-11-21 選 T3)；圖鑑在招式下面註明
BOSS_DEEP_NOTE = (f"第 2 區起：沒有閃避、招式數值 × {rules.DEEP_BOSS_SKILL_SCALE:g}、每 {rules.DEEP_BOSS_SKILL_EVERY} 回合放一次；"
                  f"第 2～{rules.DEEP_BOSS_UNLOCK_ZONES} 區只開下面順序的第 1 招，每深 {rules.DEEP_BOSS_UNLOCK_ZONES} 區多開一招")


def sections() -> list[dict]:
    """
    圖鑑的分區：[{key, kind (zone / fest), id, name, emoji, enemies: [(敵人 id, role)]}]
    role = normal / elite / boss / fest_boss；同一隻怪只列在第一次出現的那一區
    """
    out, seen = [], set()
    enemies = data.enemies()

    def pick(rows):
        got = [(e, r) for e, r in rows if e and e in enemies and e not in seen]
        seen.update(e for e, _ in got)
        return got

    for z in data.zones():
        if z.get("borrowed"):
            continue
        rows = [(e, "normal") for e in z.get("normals", [])] + [(z.get("elite"), "elite"), (z.get("boss"), "boss")]
        out.append({"key": f"zone:{z['id']}", "kind": "zone", "id": z["id"], "name": z["name"], "emoji": z["emoji"],
                    "enemies": pick(rows)})
    for fid, f in data.fests().items():
        rows = [(e, "normal") for e in f.get("normals", [])] + [(f.get("elite"), "elite"), (f.get("boss"), "fest_boss")]
        got = pick(rows)
        if got:
            out.append({"key": f"fest:{fid}", "kind": "fest", "id": fid, "name": f.get("name", fid),
                        "emoji": f.get("emoji", "🎪"), "enemies": got})
    return out


def section(key: str) -> dict | None:
    return next((s for s in sections() if s["key"] == key), None)


def unlocked(kills: dict, eid: str) -> bool:
    return kills.get(eid, 0) >= 1


def done_count(kills: dict, sec: dict) -> int:
    return sum(1 for e, _ in sec["enemies"] if unlocked(kills, e))


def kills_from_stats(stats: dict) -> dict:
    """稱號統計 (ps:ura_kill:<敵人>) 或玩家統計 (ura_kill:<敵人>) ➔ {敵人: 隻數}"""
    out = {}
    for k, v in stats.items():
        for prefix in ("ps:ura_kill:", "ura_kill:"):
            if k.startswith(prefix):
                out[k[len(prefix):]] = out.get(k[len(prefix):], 0) + int(v)
    return out


def progress(kills: dict) -> dict:
    """{base: (已登錄, 總數) 一般主題合計, fest: {活動: (已登錄, 總數)}, sections: {key: (已登錄, 總數)}}"""
    secs = sections()
    per = {s["key"]: (done_count(kills, s), len(s["enemies"])) for s in secs}
    zones = [per[s["key"]] for s in secs if s["kind"] == "zone"]
    return {"base": (sum(d for d, _ in zones), sum(t for _, t in zones)),
            "fest": {s["id"]: per[s["key"]] for s in secs if s["kind"] == "fest"},
            "sections": per}


# =========================================================
# 🎁 全收獎勵
# =========================================================
def rewards() -> list[dict]:
    """[{id, label, money, exp, kind}]：每區 (zone:<主題>)、一般主題全收 (all)、每個活動 (fest:<活動>)"""
    out = []
    for s in sections():
        money, exp = rules.BESTIARY_REWARDS[s["kind"]]
        label = f"{s['emoji']} {s['name']}全收" if s["kind"] == "zone" else f"🎪 {s['name']}的活動怪全收"
        out.append({"id": s["key"], "label": label, "money": money, "exp": exp, "kind": s["kind"]})
    money, exp = rules.BESTIARY_REWARDS["all"]
    out.append({"id": ALL_REWARD, "label": "📖 一般主題的怪物全收", "money": money, "exp": exp, "kind": "all"})
    return out


def reward_info(rid: str) -> dict | None:
    return next((r for r in rewards() if r["id"] == rid), None)


def reward_ready(kills: dict, rid: str) -> bool:
    """這個獎勵的條件達成了沒 (全部登錄)"""
    if rid == ALL_REWARD:
        done, total = progress(kills)["base"]
        return total > 0 and done >= total
    sec = section(rid)
    return bool(sec) and done_count(kills, sec) >= len(sec["enemies"]) > 0


# =========================================================
# 📜 圖鑑內容 (數值、招式說明)
# =========================================================
def zone1_stats(eid: str, role: str) -> tuple[int, int, int]:
    """第 1 區時的 HP / ATK / DEF (精英 / BOSS 倍率算進去，四捨五入)"""
    hp, atk, df = rules.enemy_stats(1, role, data.enemies()[eid])
    return rules.round_half(hp), rules.round_half(atk), rules.round_half(df)


def _status_text(sid: str, value, turns) -> str:
    info = data.statuses().get(sid, {})
    text = f"{info.get('emoji', '')} {info.get('name', sid)}".strip()
    if value is not None:
        text += f" {round(float(value) * 100):g}%"
    if turns:
        text += f" {turns} 回合"
    return text


def skill_text(skill: dict) -> str:
    """招式 ➔ 白話說明，例如「打一位 ATK × 1.4，附加 🔥 燒傷 2 回合」"""
    do = skill["do"]
    mult = f"{skill.get('mult', 1.0):g}"
    st = skill.get("status")
    if do == "attack_one":
        text = f"打一位 ATK × {mult}"
        if int(skill.get("hits", 1)) > 1:
            text += f"，連打 {int(skill['hits'])} 下"
        if st:
            text += f"，附加 {_status_text(st, skill.get('status_value'), skill.get('turns'))}"
    elif do == "attack_all":
        text = f"打全體 ATK × {mult}"
        if skill.get("taunt_redirect"):
            text += "；有人嘲諷時只打那一位"
    elif do == "sanity":
        text = f"常識度 −{int(skill['value'])}"
    elif do == "heal_self":
        text = f"自己回 {round(float(skill['value']) * 100):g}% HP"
    elif do == "apply_party":
        text = f"我方全隊 {_status_text(st, skill.get('status_value'), skill.get('turns'))}"
    elif do == "apply_self":
        text = f"自己 {_status_text(st, skill.get('status_value'), skill.get('turns'))}"
    else:
        text = do
    return text


def skill_conditions(skill: dict) -> list[str]:
    out = []
    if skill.get("cd"):
        out.append(f"冷卻 {skill['cd']} 回合")
    if skill.get("when_hp_below"):
        out.append(f"HP 低於 {round(float(skill['when_hp_below']) * 100):g}% 才用")
    if skill.get("phase2"):
        out.append("第二階段才用")
    if skill.get("deep_turns"):
        out.append(f"深區狀態 {skill['deep_turns']} 回合")
    return out


def entry(eid: str, role: str, kills: dict) -> dict:
    """一隻怪的圖鑑頁 (已解鎖才有內容)：{eid, role, role_name, unlocked, kills, name, emoji, desc, hint, stats, dodge, skills}"""
    e = data.enemies()[eid]
    out = {"eid": eid, "role": role, "role_name": ROLE_NAMES.get(role, role), "unlocked": unlocked(kills, eid),
           "kills": kills.get(eid, 0)}
    if not out["unlocked"]:
        return out
    out.update(name=e["name"], emoji=e["emoji"], desc=e.get("desc", ""), hint=e.get("hint", ""),
               stats=zone1_stats(eid, role), dodge=float(e.get("dodge", 0)),
               skills=[{"name": s["name"], "text": skill_text(s), "conds": skill_conditions(s)} for s in e.get("skills", [])])
    if role == "boss":   # 深區開招順序 (deep_order)
        names = {s["id"]: s["name"] for s in e.get("skills", [])}
        out["deep_order"] = [names.get(sid, sid) for sid in e.get("deep_order", [])]
    return out

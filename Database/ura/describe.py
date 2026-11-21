"""
📝 裏世界的白話說明 (純函式，不 import discord)：職業特性、符卡效果
- tools/ura_roster.py (docs/ura_roster.md) 跟 /ura 的「🔍 查看」角色詳情共用這裡，兩邊的寫法一樣
- 敵人招式的說明在 bestiary.skill_text
"""
from Database.ura import data

CLASS_NOTE = {
    "atk": "普攻 / 單體符卡打中有 ⚖️ 審判的敵人 ➔ 審判破掉 (裏・四季映姬的破解)",
    "guard": "敵人選目標時比重 × 4 (大多打守護者)；嘲諷時全部打這位 (裏・藤原妹紅的破解：嘲諷時火之鳥只打守護者)",
    "sup": "放任何符卡都順便淨化全隊的壞狀態 (裏・神綺的破解)",
    "scout": "看穿陷阱、門後面多看一點、隱藏寶箱；活著時所有敵人的閃避減半 (裏・射命丸文的破解)",
    "guide": "每關少扣 30% 常識度 (逃跑也算)；敵人扣常識度的招式也少扣 30% (裏・西行寺幽幽子的破解)",
}
TO_TEXT = {"self": "自己", "allies": "全隊", "target": "目標", "enemies": "敵人全體", "hit": "打中的敵人"}


def num(v) -> str:
    v = round(float(v), 1)
    return str(int(v)) if v == int(v) else f"{v:g}"


def pct(v) -> str:
    return f"{round(float(v) * 100, 1):g}%"


def tier_vals(sp: dict, key: str) -> list:
    return [t.get(key[1:]) for t in sp["tiers"]]


def show(sp: dict, v, fmt=num, tier: int | None = None) -> str:
    """
    $x ➔ 符卡那一檔的數字；tier = None 寫三檔「a / b / c」(三檔一樣就寫一個)，給 tier 只寫那一檔
    不是 $ 開頭就直接格式化
    """
    if isinstance(v, str) and v.startswith("$"):
        vals = tier_vals(sp, v)
        if tier is not None:
            vals = [vals[min(tier, len(vals) - 1)]]
        if any(isinstance(x, list) for x in vals):
            vals_txt = ["～".join(str(y) for y in x) if x[0] != x[-1] else str(x[0]) for x in vals]
            return " / ".join(vals_txt) if len(set(vals_txt)) > 1 else vals_txt[0]
        txt = [fmt(x) for x in vals]
        return " / ".join(txt) if len(set(txt)) > 1 else txt[0]
    return fmt(v)


def status_name(sid: str) -> str:
    st = data.statuses().get(sid, {})
    return f"{st.get('emoji', '')} {st.get('name', sid)}".strip()


def effect_text(sp: dict, e: dict, tier: int | None = None) -> str:
    """符卡的一個效果 ➔ 白話；tier = 那位角色的符卡檔次 (None = 三檔都寫)"""
    do = e["do"]
    s = lambda v, fmt=num: show(sp, v, fmt, tier)
    if do == "damage":
        t = f"單體 ATK × {s(e['mult'])}"
        if e.get("vs_strong"):
            t += f" (對精英 / BOSS 再 × {num(e['vs_strong'])})"
        if e.get("ignore_def"):
            t += f"，無視 {pct(e['ignore_def'])} DEF"
        if e.get("drain"):
            t += f"，回自己造成傷害的 {pct(e['drain'])}"
        return t
    if do == "damage_all":
        return f"全體 ATK × {s(e['mult'])}"
    if do == "multi_hit":
        lo, hi = e["hits"]
        return f"打 {lo}～{hi} 下 (下數 {lo} 多、{hi} 少)，每下 ATK × {s(e['mult'])}，每下隨機一隻"
    if do == "heal":
        return f"一位隊友回 {s(e['pct'], pct)} HP"
    if do == "heal_all":
        return f"全隊回 {s(e['pct'], pct)} HP"
    if do == "heal_self":
        return f"自己回 {s(e['pct'], pct)} HP"
    if do == "apply":
        t = f"{TO_TEXT.get(e.get('to'), e.get('to', ''))} {status_name(e['status'])}"
        if e.get("value") is not None:
            t += f" {s(e['value'], pct)}"
        if e.get("turns_choice"):
            t += f" {s(e['turns_choice'])} 回合"
        elif e.get("turns"):
            t += f" {num(e['turns'])} 回合"
        if e.get("chance") is not None:
            t = f"{pct(e['chance'])} 機率 " + t
        return t
    if do == "time_stop":
        return f"時間停止：這回合我方全員各行動一次 (我方傷害 × {s(e['mult'])})"
    if do == "sanity":
        return f"常識度 +{s(e['value'])}"
    if do == "money_mult":
        return f"這場戰鬥的錢 × {num(e['value'])} (不疊)"
    if do == "reroll_doors":
        return "重抽這一關的門 (選門時)"
    if do == "skip_battle":
        return "跳過一場一般戰鬥 (沒有獎勵)"
    return do


def spell_text(cid: str, tier: int | None = None) -> str:
    """一位角色的符卡全部效果 (用「；」接起來)"""
    sp = data.spells()[cid]
    return "；".join(effect_text(sp, e, tier) for e in sp["effects"])


def relic_effect(rel: dict, cls: str | None = None) -> str:
    """法具效果：說明 + 這一檔的數字 (+ 職業對上的加成)；cls = 裝的人的職業"""
    rd = data.relics().get(rel["rid"], {})
    tier = rel.get("tier", 0)
    bits = [rd.get("desc", "")]
    vals = rd.get("values")
    if vals:
        v = vals[min(tier, len(vals) - 1)]
        bits.append(f"這一檔 {pct(v) if v < 1 else num(v)}")
    bonus = rd.get("class_bonus") or {}
    if bonus and cls == rd.get("class"):
        b = (f"× {num(bonus['mult'])}" if "mult" in bonus else f"+{pct(bonus['add']) if bonus['add'] < 1 else num(bonus['add'])}"
             if "add" in bonus else f"次數 +{bonus['uses']}")
        bits.append(f"職業對上 {b}")
    return "，".join(b for b in bits if b)

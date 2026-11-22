"""
📝 裏世界的白話說明 (純函式，不 import discord)：職業特性、符卡效果、法具效果
- 🔍 查看詳情、出發選角色、/character 圖鑑的特殊能力、tools/ura_roster.py (docs/ura_roster.md) 都用這裡，寫法一樣
- 敵人招式的說明在 bestiary.skill_text

符卡「效果」的寫法 (使用者 2026-11-22 定，分支 ura-skill-desc)：
- 效果從數值自動產生；給 tier 只寫那一檔的數字，沒給就三檔都寫、標出階級「〔SR 2.8・SSR 3.3・UR 3.8〕」
- 傷害「對一隻敵人 / 全部敵人造成 ATK × 2.8 的傷害」；狀態寫出作用和數字「自己 🌀 反擊架式 2 回合（被打時反擊 ATK × 50%）」
- spells.json 的 desc = 一句定位 / 用法 (不重複效果的機制)，空的就不顯示
"""
from Database.ura import data

CLASS_NOTE = {
    "atk": "普攻 / 單體符卡打中有 ⚖️ 審判的敵人 ➔ 審判破掉 (裏・四季映姬的破解)",
    "guard": "敵人選目標時比重 × 4 (大多打守護者)；嘲諷時全部打這位 (裏・藤原妹紅的破解：嘲諷時火之鳥只打守護者)",
    "sup": "放任何符卡都順便淨化全隊的壞狀態 (裏・神綺的破解)",
    "scout": "看穿陷阱、門後面多看一點、隱藏寶箱；活著時所有敵人的閃避減半 (裏・射命丸文的破解)",
    "guide": "每關少扣 30% 常識度 (逃跑也算)；敵人扣常識度的招式也少扣 30% (裏・西行寺幽幽子的破解)",
}
COOLDOWN_NOTE = "冷卻：戰鬥中每回合減 1，戰鬥外每過一關也減 1"
# 狀態的作用 ({v} = 這一檔的數字)；沒列的用 statuses.json 的 desc
STATUS_PHRASE = {
    "taunt": "敵人全部打這位",
    "counter": "被打時反擊 ATK × {v}",
    "shield": "下一次受到的傷害少 {v}",
    "invuln": "不會受到傷害",
    "buff_def": "DEF +{v}",
    "buff_atk": "ATK +{v}",
    "debuff_def": "DEF −{v}",
    "debuff_atk": "ATK −{v}",
    "evil_eye": "DEF −{v}",
    "sleep": "跳過行動，被打就醒",
    "freeze": "跳過行動，被打也不會醒",
}
WHO = {"self": "自己", "allies": "全隊", "enemies": "讓敵人全體", "target": "讓一隻敵人"}
DAMAGE_DOS = ("damage", "damage_all", "multi_hit")


def num(v) -> str:
    v = round(float(v), 1)
    return str(int(v)) if v == int(v) else f"{v:g}"


def pct(v) -> str:
    return f"{round(float(v) * 100, 1):g}%"


def tier_vals(sp: dict, key: str) -> list:
    return [t.get(key[1:]) for t in sp["tiers"]]


def _one(x, fmt) -> str:
    if isinstance(x, list):
        return str(x[0]) if x[0] == x[-1] else f"{x[0]}～{x[-1]}"
    return fmt(x)


def show(sp: dict, v, fmt=num, tier: int | None = None, rarities: list | None = None) -> str:
    """
    $x ➔ 符卡那一檔的數字；給 tier 只寫那一檔 (跟引擎一樣：第 tier 檔，超過就用最後一檔)
    沒給 tier：三檔一樣寫一個，不一樣的話有 rarities 就標出階級「〔SR 2.8・SSR 3.3・UR 3.8〕」，沒有就「a / b / c」
    不是 $ 開頭就直接格式化
    """
    if not (isinstance(v, str) and v.startswith("$")):
        return fmt(v)
    vals = tier_vals(sp, v)
    if tier is not None:
        return _one(vals[min(tier, len(vals) - 1)], fmt)
    n = len(rarities) if rarities else len(vals)
    txt = [_one(vals[min(i, len(vals) - 1)], fmt) for i in range(n)]
    if len(set(txt)) == 1:
        return txt[0]
    if rarities:
        return "〔" + "・".join(f"{r} {t}" for r, t in zip(rarities, txt)) + "〕"
    return " / ".join(txt)


def _tier_values(sp: dict, v, tier: int | None) -> list:
    """一個欄位會用到的所有數字 (給 tier 只有那一檔)"""
    if not (isinstance(v, str) and v.startswith("$")):
        return [v]
    vals = tier_vals(sp, v)
    return [vals[min(tier, len(vals) - 1)]] if tier is not None else vals


def status_name(sid: str) -> str:
    st = data.statuses().get(sid, {})
    return f"{st.get('emoji', '')} {st.get('name', sid)}".strip()


def _status_phrase(sid: str, value_txt: str, caster: str | None) -> str:
    st = data.statuses().get(sid, {})
    if sid == "doll_legion":   # 人形：每位有這個狀態的隊友回合結束各打一隻 (用放的人的 ATK)
        mult = next((a.get("mult") for a in st.get("on", {}).get("round_end", []) if a.get("do") == "auto_attack"), 0.3)
        return f"ATK +{value_txt}；每回合結束，每位隊友的人形各幫忙打一隻敵人：{caster or '放的人'} ATK × {num(mult)}"
    if sid == "mima_power":
        return f"ATK +{pct(st.get('mods', {}).get('atk_pct', 0.1))}"
    tmpl = STATUS_PHRASE.get(sid)
    return tmpl.format(v=value_txt) if tmpl else st.get("desc", "")


def _boss_note(sid: str, turns: list) -> str:
    """控場類對 BOSS：boss_immune 無效；boss_half 回合數減半 (1 回合的減半 = 0 = 無效)"""
    flags = data.statuses().get(sid, {}).get("flags", [])
    if "boss_immune" in flags:
        return "BOSS 無效"
    if "boss_half" in flags:
        flat = [t for x in turns for t in (x if isinstance(x, list) else [x])]
        if max(flat) <= 1:
            return "BOSS 無效"
        if min(flat) <= 1:
            return "BOSS 回合數減半、1 回合的對 BOSS 無效，每控一次下次成功率再減半"
        return "BOSS 回合數減半，每控一次下次成功率再減半"
    return ""


def _apply_text(sp: dict, e: dict, tier, rarities, caster, after_damage: bool) -> str:
    sid = e["status"]
    st = data.statuses().get(sid, {})
    if e.get("turns_choice"):
        turns = _tier_values(sp, e["turns_choice"], tier)
        t_txt = show(sp, e["turns_choice"], tier=tier, rarities=rarities) + " 回合"
        if tier is not None and isinstance(turns[0], list) and turns[0][0] != turns[0][-1]:
            coin = f"{turns[0][0]}、{turns[0][-1]} 回合各一半機率"
        else:
            coin = ""
    else:
        turns = [e.get("turns", st.get("default", 1))]
        t_txt, coin = f"{num(turns[0])} 回合", ""
    length = f" {t_txt}" if st.get("duration") == "rounds" else ""
    value_txt = show(sp, e["value"], pct, tier, rarities) if e.get("value") is not None else ""
    phrase = _status_phrase(sid, value_txt, caster)
    if coin:
        phrase = f"{coin}；{phrase}" if phrase else coin
    to = e.get("to")
    if to in ("enemies", "target", "hit"):
        note = _boss_note(sid, turns)
        if note:
            phrase = f"{phrase}；{note}" if phrase else note
    if to == "hit":
        lead = f"打中的每一隻各有 {pct(e['chance'])} 機率" if e.get("chance") is not None else "打中的敵人"
        text = f"{lead} {status_name(sid)}{length}"
    else:
        text = f"{WHO.get(to, to or '')} {status_name(sid)}{length}"
        if e.get("chance") is not None:
            text = f"{pct(e['chance'])} 機率{text}"
    if to == "self" and after_damage:
        text = "之後" + text
    return text + (f"（{phrase}）" if phrase else "")


def effect_text(sp: dict, e: dict, tier: int | None = None, rarities: list | None = None,
                caster: str | None = None, after_damage: bool = False) -> str:
    """
    符卡的一個效果 ➔ 白話；tier = 那張卡的符卡檔次 (None = 三檔都寫，有 rarities 就標出階級)
    caster = 放的人的名字 (人形助陣用)；after_damage = 前面有傷害效果 (自己的增益寫「之後」)
    """
    text = _effect_text(sp, e, tier, rarities, caster, after_damage)
    return text.replace(" 〔", "〔").replace("〕 ", "〕")


def _effect_text(sp, e, tier, rarities, caster, after_damage) -> str:
    do = e["do"]

    def s(v, fmt=num):
        return show(sp, v, fmt, tier, rarities)
    if do == "damage":
        t = f"對一隻敵人造成 ATK × {s(e['mult'])} 的傷害"
        if e.get("ignore_def"):
            t += f"，無視敵人 {pct(e['ignore_def'])} 的 DEF"
        if e.get("drain"):
            t += f"，回自己造成傷害的 {pct(e['drain'])} HP"
        if e.get("vs_strong"):
            t += f"（打精英 / 寶箱怪 / BOSS 再 × {num(e['vs_strong'])}）"
        return t
    if do == "damage_all":
        return f"對全部敵人造成 ATK × {s(e['mult'])} 的傷害"
    if do == "multi_hit":
        lo, hi = e["hits"]
        ks = list(range(lo, hi + 1))
        ws = list(range(len(ks), 0, -1))   # 跟 rules.weighted_count 一樣：下數越多機率越低
        dist = "、".join(f"{k} 下 {round(w * 100 / sum(ws))}%" for k, w in zip(ks, ws))
        return f"連打 {lo}～{hi} 下（{dist}），每下對隨機一隻敵人造成 ATK × {s(e['mult'])} 的傷害"
    if do == "heal":
        return f"一位隊友回最大 HP 的 {s(e['pct'], pct)}"
    if do == "heal_all":
        return f"全隊回最大 HP 的 {s(e['pct'], pct)}"
    if do == "heal_self":
        return f"自己回最大 HP 的 {s(e['pct'], pct)}"
    if do == "apply":
        return _apply_text(sp, e, tier, rarities, caster, after_damage)
    if do == "time_stop":
        t = "時間停止：這回合其他隊友也都能行動（平常一回合只有一位能行動）"
        m = e.get("mult", 1.0)
        if isinstance(m, str) and m.startswith("$"):
            vals = _tier_values(sp, m, tier)
            if tier is not None:
                if vals[0] != 1:
                    t += f"，這回合我方的傷害再 × {num(vals[0])}"
            else:
                n = len(rarities) if rarities else len(vals)
                full = [tier_vals(sp, m)[min(i, len(tier_vals(sp, m)) - 1)] for i in range(n)]
                up = [(rarities[i] if rarities else f"第 {i + 1} 檔", v) for i, v in enumerate(full) if v != 1]
                if up:
                    t += "；" + "・".join(f"{r}" for r, _ in up) + f" 時這回合我方的傷害再 × {'／'.join(sorted({num(v) for _, v in up}))}"
        elif m != 1:
            t += f"，這回合我方的傷害再 × {num(m)}"
        return t
    if do == "sanity":
        return f"常識度 +{s(e['value'])}"
    if do == "money_mult":
        return f"這場戰鬥的賽錢 × {num(e['value'])}（不疊）"
    if do == "reroll_doors":
        return "選門時：重抽這一關的門"
    if do == "skip_battle":
        return "戰鬥中：跳過一場一般戰鬥（沒有獎勵；精英 / BOSS 戰不能用）"
    return do


def spell_text(cid: str, tier: int | None = None) -> str:
    """一位角色的符卡全部效果 (用「；」接起來)；tier = None 三檔都寫 (標出階級)"""
    sp = data.spells()[cid]
    ch = data.characters().get(cid, {})
    out, after = [], False
    for e in sp["effects"]:
        out.append(effect_text(sp, e, tier, ch.get("rarities"), ch.get("name"), after))
        after = after or e["do"] in DAMAGE_DOS
    return "；".join(out)


def spell_note(cid: str) -> str:
    """符卡的一句定位 / 用法 (spells.json 的 desc；空的 = 不顯示)"""
    return data.spells().get(cid, {}).get("desc", "")


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

"""
🌀 裏世界：角色與敵人一覽 (自動產生 docs/ura_roster.md)

用法：python tools/ura_roster.py
資料全部從 Characters/、Database/ura/data/*.json、Events/*.json 的 ura 區塊讀；改了數值重跑一次就好。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from Database import shrine_data   # noqa: E402
from Database.ura import bestiary, data, rules   # noqa: E402
from Database.ura.describe import CLASS_NOTE, effect_text, num, pct   # noqa: E402
from Utils.version import VERSION   # noqa: E402

OUT = os.path.join(ROOT, "docs", "ura_roster.md")
CLASS_ORDER = ["atk", "guard", "sup", "scout", "guide"]


def stat_line(hp, atk, df) -> str:
    return f"HP {num(hp)}／ATK {num(atk)}／DEF {num(df)}"


# 符卡效果的白話說明、職業特性：跟 /ura 的「🔍 查看」共用 Database/ura/describe.py


def character_block(cid: str, c: dict) -> list[str]:
    sp = data.spells()[cid]
    b = c["base"]
    comp = rules.comp_mult(0.65)
    per = "、".join(f"{r} {stat_line(b['hp'] * rules.RARITY_MULT[r] * comp, b['atk'] * rules.RARITY_MULT[r] * comp, b['def'] * rules.RARITY_MULT[r] * comp)}"
                   for r in c["rarities"])
    tiers = " / ".join(c["rarities"][:1] + ([c["rarities"][len(c["rarities"]) // 2]] if len(c["rarities"]) > 2 else []) + c["rarities"][-1:])
    effects = "；".join(effect_text(sp, e) for e in sp["effects"])
    where = "選門時也能放" if sp.get("outside") else ""
    return [
        f"#### {c['emoji']} {c['name']}",
        f"- 卡牌階級：{' / '.join(c['rarities'])}　基礎 (N、完整度 0.65)：{stat_line(b['hp'], b['atk'], b['def'])}",
        f"- 各階級 (完整度 0.65)：{per}",
        f"- ✨ 符卡 {c.get('spell_name') or ''}：B 點 {sp['b']}、冷卻 {sp['cd']} 回合{('、' + where) if where else ''}",
        f"  - 效果 (三檔 = {tiers})：{effects}",
        f"  - 說明：{sp.get('desc', '')}",
        "",
    ]


# =========================================================
# 👹 敵人
# =========================================================
def enemy_block(eid: str, role: str, kind_zone: str) -> list[str]:
    e = data.enemies()[eid]
    kind = role
    z1, z5 = rules.enemy_stats(1, kind, e), rules.enemy_stats(5, kind, e)
    mods = f"HP × {num(e.get('hp', 1))}／ATK × {num(e.get('atk', 1))}／DEF × {num(e.get('def', 1))}"
    dodge = f"、閃避 {pct(e['dodge'])}" if e.get("dodge") else ""
    lines = [f"#### {e['emoji']} {e['name']}（{bestiary.ROLE_NAMES.get(role, role)}）",
             f"- 倍率 (跟一般怪基本值比)：{mods}{dodge}",
             f"- 第 1 區：{stat_line(*z1)}　第 5 區：{stat_line(*z5)}"]
    if e.get("skills"):
        lines.append("- 招式：")
        for s in e["skills"]:
            conds = bestiary.skill_conditions(s)
            lines.append(f"  - **{s['name']}**：{bestiary.skill_text(s)}" + (f"（{'、'.join(conds)}）" if conds else ""))
    else:
        lines.append("- 招式：只會普攻")
    if role == "boss" and e.get("deep_order"):
        names = {s["id"]: s["name"] for s in e["skills"]}
        lines.append(f"- 深區 (第 2 區起) 開招順序：{' ➔ '.join(names.get(x, x) for x in e['deep_order'])}")
    if e.get("hint"):
        lines.append(f"- 💡 破解：{e['hint']}")
    lines.append(f"- 📖 {e.get('desc', '')}")
    lines.append("")
    return lines


def main():
    chars = data.characters()
    out = [
        "# 🌀 裏世界：角色與敵人一覽",
        "",
        f"> 自動產生 (版本 {VERSION})：`python tools/ura_roster.py`。資料改了重跑一次就好，**不要手改這份**。規則細節看 `docs/ura.md`。",
        "",
        "## 📐 數值怎麼算",
        f"- **角色**：基礎數值 (N 階、完整度 0.65) × 階級倍率 ({'、'.join(f'{r} ×{num(m)}' for r, m in rules.RARITY_MULT.items())}) × 完整度倍率 (0.3 = ×0.8、0.65 = ×1.0、1.0 = ×1.2，線性)。完整度 > 0.8 符卡冷卻 × 0.9 (無條件捨去，最少 1)。",
        "- **符卡三檔**：角色的最低階 = 第一檔、中間 = 第二檔、最高階 = 第三檔 (兩個階級的角色只有兩檔，取第一和第三)。",
        f"- **一般怪**：基本值 HP {rules.ENEMY_BASE[0]}／ATK {rules.ENEMY_BASE[1]}／DEF {rules.ENEMY_BASE[2]} × 區域倍率 (DEF 只長一半) × 那隻怪自己的倍率。",
        f"- **精英** 再 × {'／'.join(num(x) for x in rules.ELITE_MULT)} (HP／ATK／DEF)；**區域 BOSS** 再 × {'／'.join(num(x) for x in rules.BOSS_MULT)}，血剩一半 ATK +{pct(rules.BOSS_PHASE2_ATK)} 並多用第二階段的招；**🎪 活動 BOSS** × {'／'.join(num(x) for x in rules.FEST_BOSS_MULT)}。",
        "- **區域倍率**：" + "、".join(f"第 {z} 區 ×{num(rules.zone_mult(z))}" for z in range(1, 11)) + "。",
        f"- **放特殊技**：一般怪每回合 {pct(rules.SKILL_CHANCE['normal'])}、精英 {pct(rules.SKILL_CHANCE['elite'])}；BOSS 照招式輪流 (第 1 區每 2 回合一次，深區每 {rules.DEEP_BOSS_SKILL_EVERY} 回合一次)。",
        f"- **深區 BOSS (第 2 區起)**：本身沒有閃避；招式照「深區開招順序」開放 (第 2～{rules.DEEP_BOSS_UNLOCK_ZONES} 區 1 招，每深 {rules.DEEP_BOSS_UNLOCK_ZONES} 區多開一招)，倍率／狀態數值／回血／扣常識度 × {num(rules.DEEP_BOSS_SKILL_SCALE)}；活動 BOSS 不受影響。",
        f"- **狂暴**：一般 / 精英戰超過 {rules.ENRAGE_AFTER} 回合，敵人每回合 ATK +{pct(rules.ENRAGE_STEP)} (BOSS 戰不算)。",
        "",
        "## 🧑‍🤝‍🧑 角色",
        "",
    ]
    for cls in CLASS_ORDER:
        members = [(cid, c) for cid, c in chars.items() if c["class"] == cls]
        if not members:
            continue
        out += [f"### {rules.CLASS_NAMES[cls]} ({len(members)} 位)", f"> 職業能力：{CLASS_NOTE[cls]}", ""]
        for cid, c in members:
            out += character_block(cid, c)
    out += ["## 👹 敵人", "",
            "> 每個主題 3 種一般怪 + 1 精英 (會帶 0～2 隻小弟；寶箱怪也是牠) + 1 區域 BOSS。數值是那隻怪在第 1 區 / 第 5 區的樣子 (精英 / BOSS 倍率算進去)。", ""]
    for sec in bestiary.sections():
        if sec["kind"] == "zone":
            z = data.zone_by_id(sec["id"])
            names = {m[0]: f"{m[2]} {m[1]}" for m in shrine_data.MATERIAL_ITEMS}
            mats = "、".join(names.get(m, m) for m in z.get("materials", []))
            out += [f"### {sec['emoji']} {sec['name']}", f"掉的料理素材：{mats}", ""]
        else:
            out += [f"### 🎪 {sec['name']} (活動怪，只在活動期間的 🎪 門出現)", ""]
        for eid, role in sec["enemies"]:
            out += enemy_block(eid, role, sec["key"])
    out += ["## ✨ 狀態效果", "", "| 狀態 | 好 / 壞 | 持續 | 效果 |", "|---|---|---|---|"]
    dur = {"rounds": "回合", "count": "次", "battle": "這場戰鬥", "steps": "關", "run": "整局"}
    for sid, st in data.statuses().items():
        d = dur.get(st.get("duration"), st.get("duration", ""))
        length = f"{st.get('default', '')} {d}" if st.get("duration") in ("rounds", "count", "steps") else d
        out.append(f"| {st.get('emoji', '')} {st.get('name', sid)} | {'🟢' if st.get('good') else '🔴'} | {length} | {st.get('desc', '')} |")
    out.append("")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))
    print(f"寫好了：{OUT} (角色 {len(chars)} 位、敵人 {sum(len(s['enemies']) for s in bestiary.sections())} 隻)")


if __name__ == "__main__":
    main()

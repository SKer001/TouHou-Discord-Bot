"""
🌀 裏世界探索的畫面產生器 (純函式：進度 dict ➔ 文字 / Container；不碰資料庫、不回應互動)
規則全在 Database/ura/ (引擎)；版面照 docs/ura.md「狀態效果」的兩行排版、「第二階段第一輪：畫面」。
"""
import discord
from discord import ui

from Database.ura import bestiary, combat, data, describe, fest, rules, run as R, status
from Database import shrine_data

DOOR_NAMES = {"battle": "⚔️ 戰鬥", "elite": "💀 精英", "chest": "💰 寶箱", "event": "❓ 事件", "trap": "🕳️ 陷阱",
              "merchant": "🛒 流浪商人", "boss": "👹 BOSS"}
EVENT_TYPES = {"good": "🟢 好事件", "bad": "🔴 壞事件", "special": "✨ 特殊事件"}
RESULT_TITLES = {"evacuated": "🏁 成功撤離！", "failed": "💀 探索失敗……", "abandoned": "🏳️ 放棄了探索"}
CLASS_NAMES = {"atk": "⚔️ 攻擊手", "guard": "🛡️ 守護者", "sup": "💚 輔助", "scout": "🔍 斥候", "guide": "🧭 嚮導"}
RARITY_SORT = {r: i for i, r in enumerate(rules.RARITIES)}

COLOR_RUN = discord.Color.dark_purple()
COLOR_BATTLE = discord.Color.red()
COLOR_GOOD = discord.Color.green()
COLOR_WARN = discord.Color.orange()


# =========================================================
# 🔢 小工具
# =========================================================
def num(v: float) -> str:
    """數值：整數照寫、有小數留一位 (ATK 9.6)"""
    v = round(float(v), 1)
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def material_info(mid: str) -> tuple[str, str]:
    for m in shrine_data.MATERIAL_ITEMS:
        if m[0] == mid:
            return m[1], m[2]
    return mid, "📦"


def item_name(iid: str) -> str:
    it = data.items().get(iid) or data.bags().get(iid) or {}
    return f"{it.get('emoji', '📦')} {it.get('name', iid)}"


def treasure_name(tid: str) -> str:
    info = data.treasure_info(tid) or {}
    return f"{info.get('emoji', '💎')} {info.get('name', tid)}"


def relic_name(rel: dict) -> str:
    rd = data.relics().get(rel["rid"], {})
    tier = ["SSR", "UR", "LR"][rel.get("tier", 0)]
    left = f" (剩 {rel['left']} 次)" if "left" in rel else ""
    return f"{rd.get('emoji', '🦊')} {rd.get('name', rel['rid'])}〔{tier}〕{left}"


def zone_title(run: dict | None, floor: int) -> str:
    """這一局第幾區的主題名稱 (每區隨機，run.zone_theme)"""
    zone = rules.zone_of(max(1, floor))
    z = R.zone_theme(run, zone) if run else data.zone_info(zone)
    return f"{z.get('emoji', '🌀')} {z.get('name', '裏世界')}"


def sanity_bar(n: int) -> str:
    """常識度 10 格：> 30% 🟦、≤ 30% 🟧、≤ 10% 🟥，空格 ⬜ (docs/ura.md「常識度」)"""
    ratio = max(0, n) / rules.SANITY_START
    cells = min(10, max(0, round(ratio * 10)))
    if n > 0 and cells == 0:
        cells = 1
    color = "🟥" if ratio <= 0.1 else "🟧" if ratio <= 0.3 else "🟦"
    warn = "　🚨 快撐不住了！" if ratio <= 0.1 else "　⚠️ 常識度偏低" if ratio <= 0.3 else ""
    return f"{color * cells}{'⬜' * (10 - cells)}{warn}"


def loot_lines(loot: dict, money: int | None = None) -> list[str]:
    """戰利品一行一類"""
    out = []
    if money:
        out.append(f"💰 賽錢 +{money:,}")
    if loot.get("items"):
        out.append("🎒 " + "、".join(f"{item_name(i)} ×{n}" for i, n in loot["items"].items()))
    if loot.get("materials"):
        out.append("🧺 " + "、".join(f"{material_info(m)[1]} {material_info(m)[0]} ×{n}" for m, n in loot["materials"].items()))
    if loot.get("treasures"):
        ts = sorted(loot["treasures"], key=lambda t: -RARITY_SORT.get(t["rarity"], 0))
        out.append("💎 " + "、".join(f"{'🎪 ' if t.get('fest') else ''}{treasure_name(t['id'])}〔{t['rarity']}〕" for t in ts))
    if loot.get("relics"):
        out.append("🦊 " + "、".join(relic_name(r) for r in loot["relics"]))
    return out


# =========================================================
# 🧍 單位 (兩行：名字 + 血量 / 小字放數值和狀態)
# =========================================================
def status_text(u: dict) -> str:
    return "　".join(status.label(s) for s in u.get("statuses", []))


def ally_lines(run: dict, m: dict, battle: dict | None = None) -> str:
    if not m["alive"]:
        first = f"{m['emoji']} ~~{m['name']}~~　💀 倒下"
    else:
        first = f"{m['emoji']} **{m['name']}**　❤️ {m['hp']} / {combat.max_hp(m)}"
        if battle and m["uid"] in battle["acted"]:
            first += "　✔️"
    why = combat.spell_ready(run, m, in_battle=True) if m["alive"] and battle else None
    spell = "✨ 符卡 OK" if m["alive"] and not why and m["cd"] <= 0 else f"⏳ 冷卻 {m['cd']}" if m["cd"] > 0 else ""
    parts = [f"⚔️ {num(combat.eff_atk(m))}　🛡️ {num(combat.eff_def(m))}", CLASS_NAMES.get(m["cls"], "")]
    if spell:
        parts.append(spell)
    if m.get("relic"):
        parts.append(relic_name(m["relic"]))
    st = status_text(m)
    if st:
        parts.append(st)
    return f"{first}\n-# " + "　｜ ".join(p for p in parts if p)


def foe_lines(run: dict, f: dict) -> str:
    if not f["alive"]:
        return f"{f['emoji']} ~~{f['name']}~~"
    tag = "🎪 👹 " if f.get("fest_boss") else {"elite": "💀 ", "boss": "👹 ", "mimic": "📦 "}.get(f["kind"], "")
    first = f"{f['emoji']} {tag}**{f['name']}**　❤️ {f['hp']} / {combat.max_hp(f)}"
    if f.get("phase2"):
        first += "　🔥"
    parts = [f"⚔️ {num(combat.eff_atk(f, run.get('battle')))}　🛡️ {num(combat.eff_def(f))}"]
    st = status_text(f)
    if st:
        parts.append(st)
    return f"{first}\n-# " + "　｜ ".join(parts)


def party_block(run: dict, battle: dict | None = None) -> str:
    """戰鬥畫面的我方 (一人兩行)"""
    return "\n".join(ally_lines(run, m, battle) for m in run["party"])


def party_line(run: dict) -> str:
    """探索畫面 (選門、房間) 的隊伍：一人一行，只寫名字、血量、狀態 emoji (詳情用 🔍 查看；使用者 2026-11-21)"""
    out = []
    for m in run["party"]:
        if not m["alive"]:
            out.append(f"{m['emoji']} ~~{m['name']}~~　💀")
            continue
        emo = "".join(data.statuses().get(s["id"], {}).get("emoji", "") for s in m.get("statuses", []))
        out.append(f"{m['emoji']} **{m['name']}**　❤️ {m['hp']} / {combat.max_hp(m)}" + (f"　{emo}" if emo else ""))
    return "\n".join(out)


# =========================================================
# 🔍 查看角色 / 敵人的詳情 (另外一則私人訊息；使用者 2026-11-21)
# =========================================================
def _status_lines(u: dict) -> list[str]:
    return [f"{status.label(s)}：{data.statuses().get(s['id'], {}).get('desc', '')}" for s in u.get("statuses", [])]


def _hp_line(u: dict, battle: dict | None = None) -> str:
    def stat(now, base):
        return num(now) + (f" (原本 {num(base)})" if abs(now - base) > 0.05 else "")
    hp = f"❤️ HP {u['hp']} / {combat.max_hp(u)}" if u["alive"] else "💀 倒下"
    return f"{hp}　⚔️ ATK {stat(combat.eff_atk(u, battle), u['base_atk'])}　🛡️ DEF {stat(combat.eff_def(u), u['base_def'])}"


def build_unit_detail(run: dict, u: dict, kills: dict | None = None, thumb: str | None = None) -> ui.Container:
    """
    我方：卡面縮圖、階級、完整度、職業特性、HP / ATK / DEF (含狀態加成)、符卡 (B 點、冷卻)、法具、狀態
    敵人：數值、閃避、招式 (圖鑑還沒解鎖 = 沒打倒過的話不顯示招式和攻略)、深區 BOSS 規則、狀態
    """
    battle = run.get("battle") if run.get("phase") == "battle" else None
    if u["side"] == "ally":
        c = ui.Container(accent_color=COLOR_RUN)
        head = (f"## {u['emoji']} {u['name']}〔{u['rarity']}〕\n完整度 `{u['comp']:.4f}`　{CLASS_NAMES.get(u['cls'], '')}\n"
                f"-# 職業特性：{describe.CLASS_NOTE.get(u['cls'], '')}")
        c.add_item(ui.Section(ui.TextDisplay(head), accessory=ui.Thumbnail(thumb)) if thumb else ui.TextDisplay(head))
        c.add_item(ui.Separator())
        sp = data.spells().get(u["cid"], {})
        cd = f"⏳ 還要 {u['cd']} 回合" if u["cd"] > 0 else "✅ 冷卻好了"
        effect = describe.spell_text(u["cid"], u["tier"])
        lines = [_hp_line(u, battle), "",
                 f"✨ **{u.get('spell_name') or '符卡'}**　B 點 {u['b_cost']}・冷卻 {u['cd_max']} 回合（{cd}）",
                 f"效果：{effect}" + ("　(選門時也能放)" if sp.get("outside") and "選門時" not in effect else "")]
        note = describe.spell_note(u["cid"])
        if note:   # 一句定位 / 用法 (使用者 2026-11-22：不重複效果)
            lines.append(f"-# {note}")
        lines.append(f"-# {describe.COOLDOWN_NOTE}")
        rel = u.get("relic")
        lines += ["", f"🦊 法具：{relic_name(rel)}\n-# {describe.relic_effect(rel, u['cls'])}" if rel else "🦊 法具：沒有裝"]
        c.add_item(ui.TextDisplay("\n".join(lines)))
    else:
        e = data.enemies().get(u.get("eid"), {})
        open_ = bestiary.unlocked(kills or {}, u.get("eid"))
        c = ui.Container(accent_color=COLOR_BATTLE)
        tag = "🎪 👹 活動 BOSS " if u.get("fest_boss") else {"elite": "💀 精英 ", "boss": "👹 BOSS ", "mimic": "📦 寶箱怪 "}.get(u["kind"], "")
        dodge = float(u.get("dodge", 0))
        dline = ""
        if dodge > 0:
            dline = f"　💨 閃避 {describe.pct(dodge / 2 if combat.scout_alive(run) else dodge)}" + ("（🔍 斥候在場減半）" if combat.scout_alive(run) else "")
        lines = [f"## {u['emoji']} {tag}{u['name']}" + ("　🔥 第二階段" if u.get("phase2") else ""), _hp_line(u, battle) + dline]
        if open_ and e.get("desc"):
            lines.append(f"-# {e['desc']}")
        c.add_item(ui.TextDisplay("\n".join(lines)))
        c.add_item(ui.Separator())
        if open_:
            sk = [f"**{s['name']}**：{bestiary.skill_text(s)}" + (f"（{'、'.join(bestiary.skill_conditions(s))}）" if bestiary.skill_conditions(s) else "")
                  for s in u.get("skills", [])]
            body = ["**招式**"] + (sk or ["只會普攻"])
            if u["kind"] == "boss" and not u.get("fest_boss") and rules.zone_of(max(1, run["floor"])) > 1:
                body.append(f"-# 👹 {bestiary.BOSS_DEEP_NOTE}")
            if e.get("hint"):
                body.append(f"💡 {e['hint']}")
        else:
            body = ["**招式**", "❓ 還沒打倒過這種敵人：打倒一次 (`/ura bestiary` 圖鑑登錄) 後才看得到招式和攻略提示"]
        c.add_item(ui.TextDisplay("\n".join(body)))
    c.add_item(ui.Separator())
    st = _status_lines(u)
    c.add_item(ui.TextDisplay("**狀態**\n" + ("\n".join(st) if st else "-# 沒有狀態")))
    return c


# =========================================================
# 🧭 每個畫面上面的狀態列
# =========================================================
def header_text(run: dict) -> str:
    floor = run["floor"]
    where = f"第 {floor} 關" if floor else "入口"
    fz = rules.floor_in_zone(floor) if floor else 0
    zone = rules.zone_of(max(1, floor))
    lines = [f"## 🌀 裏世界・{zone_title(run, floor)}　{where}" + (f"（第 {zone} 區 {fz} / 10）" if floor else ""),
             f"🧭 常識度 `{max(0, run['sanity'])} / {rules.SANITY_START}`　{sanity_bar(run['sanity'])}",
             f"✨ B 點 `{run['b']} / {rules.B_MAX}`　💰 口袋 `{run['pocket']:,}`　🎒 背包 `{R.slots_used(run['bag'])} / {run['capacity']}`"]
    return "\n".join(lines)


def log_text(lines: list[str], n: int = 6) -> str | None:
    lines = [x for x in lines if x][-n:]
    return "\n".join(f"-# {x}" for x in lines) if lines else None


# =========================================================
# 🚪 選門
# =========================================================
def door_label(run: dict, idx: int, door: dict, revealed: bool) -> str:
    v = R.door_view(run, door, revealed)
    label = DOOR_NAMES.get(v["type"], v["type"])
    if door.get("hidden"):
        label = "🔍 隱藏寶箱"
    if v["type"] == "battle":
        label += f" ×{v['count']}"
    if v.get("fest"):
        label = "🎪 " + label
    return f"{idx + 1}. {label}"


def door_detail(run: dict, door: dict, revealed: bool) -> str | None:
    v = R.door_view(run, door, revealed)
    bits = []
    if v.get("fest"):   # 🎪 活動門：活動名稱和環境一定看得到
        f = fest.info(v["fest"])
        bits.append(f"🎪 {f.get('name', '')}" + (f"｜{fest.env_text(v['fest'])}" if fest.env_text(v["fest"]) else ""))
    if not revealed:
        return "　".join(bits) or None
    if v.get("foes"):
        bits.append("、".join(v["foes"]))
    if v["type"] == "chest":
        if v.get("mimic"):
            bits.append("⚠️ 是寶箱怪！")
        elif v.get("locked"):
            bits.append("🔒 上鎖 (要鑰匙)")
        else:
            bits.append("沒上鎖")
    if v.get("etype"):
        bits.append(EVENT_TYPES.get(v["etype"], v["etype"]))
    return "　".join(bits) or None


def doors_text(run: dict) -> str:
    revealed = R.doors_revealed(run)
    nxt = run["floor"] + 1
    lines = [f"### 🚪 第 {nxt} 關：選一扇門" + ("\n-# 🔍 看得到門後的細節" if revealed else "")]
    for i, d in enumerate(run["doors"]):
        detail = door_detail(run, d, revealed)
        lines.append(door_label(run, i, d, revealed) + (f"\n-# 　{detail}" if detail else ""))
    peek = run.get("peek")
    if peek and peek["floor"] == nxt + 1:
        lines.append("-# 🗺️ 下下一關：" + "　".join(DOOR_NAMES.get(d["type"], d["type"]) for d in peek["doors"]))
    return "\n".join(lines)


# =========================================================
# 🏠 房間 (寶箱 / 事件 / 陷阱 / 商人 / BOSS 打完)
# =========================================================
def event_result_text(run: dict, res: dict | None) -> str | None:
    if not res:
        return None
    do = res.get("do")
    if do == "declined":
        return "-# 你決定不理它，繼續往前走。"
    if do == "money" and "money" in res:
        return f"💰 賽錢 {res['money']:+,}"
    if do == "lose_money_pct":
        return f"💸 口袋少了 {-res['money']:,} 賽錢"
    if do == "cheap_item":
        return "🎁 拿到 " + "、".join(f"{item_name(i)} ×{n}" for i, n in res.get("items", {}).items())
    if do == "sanity":
        return f"🧭 常識度 {res['sanity']:+}"
    if do == "apply_random_ally":
        return f"👻 {res.get('target', '有人')} 受到影響"
    if do == "gamble":
        return f"🎲 {'贏了！拿回 ' + format(res['cost'] * 3, ',') + ' 賽錢' if res['win'] else '輸了…… 賭金 ' + format(res['cost'], ',') + ' 沒了'}"
    if do == "upgrade_treasure":
        return f"⛩️ {treasure_name(res['old']['id'])}〔{res['old']['rarity']}〕➔ {treasure_name(res['new']['id'])}〔{res['new']['rarity']}〕"
    if do == "trial":
        return f"🔥 {res['target']} 承受了試煉，全隊 ATK 提升到這區 BOSS 為止"
    if do == "trade_items_for_relic":
        return f"🦊 換到了 {relic_name(res['relic'])}"
    if do == "buy_fest_treasure":
        t = res["treasure"]
        return f"😈 付了 {res['cost']:,} 賽錢，換到 🎪 {treasure_name(t['id'])}〔{t['rarity']}〕"
    if do == "sealed_box":
        return {"key": "🗝️ 用鑰匙打開了箱子", "forced": "💪 硬撬開了箱子！", "mimic": "😱 箱子張開大嘴——是寶箱怪！"}.get(res.get("how"))
    return None


def room_text(run: dict) -> str:
    """房間的內容；🎪 活動房間上面多一行活動名稱"""
    text = _room_text(run)
    fid = (run.get("room") or {}).get("fest")
    if fid and run["phase"] in ("chest", "event"):
        return f"-# 🎪 {fest.info(fid).get('name', '活動')}的特別關卡\n{text}"
    return text


def _room_text(run: dict) -> str:
    phase, room = run["phase"], run.get("room") or {}
    if phase == "chest":
        if room.get("opened"):
            lines = ["### 💰 打開了寶箱"] + loot_lines(room.get("loot", {}), room.get("loot", {}).get("money"))
        else:
            keys = run["bag"]["items"].get("chest_key", 0)
            lines = ["### 💰 寶箱", "🔒 上了鎖的寶箱 (要 🗝️ 寶箱鑰匙，你有 " + str(keys) + " 把)" if room.get("locked") else "一個沒上鎖的寶箱。"]
            if room.get("mimic") and combat.has_scout(run):
                lines.append("-# 🔍 斥候：這個寶箱好像在呼吸……")
        return "\n".join(lines)
    if phase == "event":
        ev = data.events().get(room.get("event"), {})
        lines = [f"### {ev.get('emoji', '❓')} {ev.get('name', '事件')}", f"-# {EVENT_TYPES.get(ev.get('type'), '')}", ev.get("text", "")]
        if room.get("pending_choice"):
            lines.append("-# 要怎麼做？")
        res = event_result_text(run, room.get("result"))
        if res:
            lines.append(res)
        if room.get("loot"):
            lines += loot_lines(room["loot"], room["loot"].get("money"))
        return "\n".join(lines)
    if phase == "trap":
        r = room.get("result")
        text = {"scout": "🔍 斥候看穿了陷阱，大家安全通過。", "amulet": "🧿 避邪護符擋下了陷阱！",
                "hp": f"🕳️ 掉進陷阱了！全隊 −{int(rules.TRAP_HP_PCT * 100)}% HP (最低留 1)",
                "item": f"🕳️ 掉進陷阱，慌亂中弄丟了 {item_name(room.get('lost', ''))}"}.get(r, "🕳️ 陷阱")
        return f"### 🕳️ 陷阱\n{text}"
    if phase == "merchant":
        lines = ["### 🛒 流浪商人", "-# 「用你口袋裡的錢買吧，嘿嘿。」(價格 = 商店 × 1.2)"]
        for i, s in enumerate(room.get("stock", [])):
            name = item_name(s["id"]) if s["kind"] == "item" else relic_name(s["relic"])
            lines.append(f"{i + 1}. {name}　`{s['price']:,}`　" + (f"剩 {s['qty']}" if s["qty"] > 0 else "~~賣完了~~"))
        return "\n".join(lines)
    if phase == "boss_clear":
        lines = [f"### 👹 打倒了第 {run['boss_cleared']} 區的 BOSS！", "可以現在 **🏁 撤離** 把東西帶回去，或 **➡️ 繼續** 往下一區 (越深越危險、寶物越好)。"]
        return "\n".join(lines)
    return ""


def last_battle_text(run: dict) -> str | None:
    """剛打完的那一場 (還在同一關才顯示)"""
    last = run.get("last")
    if not last or last.get("floor") != run["floor"]:
        return None
    head = {"win": "✨ 戰鬥勝利！", "fled": "🏃 逃出了戰鬥", "skipped": "🚢 跳過了戰鬥"}.get(last["over"], "戰鬥結束")
    lines = [f"**{head}**"] + loot_lines(last.get("loot", {}), last.get("money"))
    return "\n".join(lines)


def pending_text(run: dict) -> str | None:
    if not run.get("pending"):
        return None
    return f"📦 有 {len(run['pending'])} 樣東西放不下 (整理背包後可以再撿，離開這關就沒了)"


def pending_label(p: dict) -> str:
    k = p["kind"]
    if k == "items":
        return item_name(p["key"])
    if k == "materials":
        name, emoji = material_info(p["key"])
        return f"{emoji} {name}"
    if k == "treasures":
        return f"{treasure_name(p['key']['id'])}〔{p['key']['rarity']}〕"
    return relic_name(p["key"])


# =========================================================
# 🎒 背包 (分類頁籤：一次只看一類、一樣一行，寫數量和佔幾格；使用者 2026-11-21 grill 定)
# =========================================================
BAG_KINDS = {"items": "🧪 道具", "materials": "🧺 素材", "treasures": "💎 寶物", "relics": "🦊 法具"}
CAT_NAMES = {"heal": "回血類", "sanity": "回常識度類"}


def kind_slots(bag: dict, kind: str) -> int:
    """背包裡某一類佔幾格"""
    only = {"items": {}, "materials": {}, "treasures": [], "relics": []}
    only[kind] = bag[kind]
    return R.slots_used(only)


def bag_summary(run: dict) -> str:
    """最上面一行總覽：🎒 39 / 50 格｜🧪 道具 18 格・🧺 素材 0・💎 寶物 15・🦊 法具 1"""
    bag = run["bag"]
    s = {k: kind_slots(bag, k) for k in BAG_KINDS}
    line = (f"**🎒 {R.slots_used(bag)} / {run['capacity']} 格**｜🧪 道具 {s['items']} 格・🧺 素材 {s['materials']}・"
            f"💎 寶物 {s['treasures']}・🦊 法具 {s['relics']}")
    if run.get("bag_name"):
        line += f"\n-# 額外背包：{run['bag_name']}"
    return line


def item_limit(bag_items: dict, iid: str) -> tuple[str, bool]:
    """道具的上限說明 (上限 10 / 回血類合計上限 5) 和到上限了沒 (✅ = 撿不了更多)"""
    it = data.items().get(iid, {})
    n = bag_items.get(iid, 0)
    parts, full = [], False
    cat = it.get("cat") if it.get("cat") in data.category_max() else None
    cap = data.category_max()[cat] if cat else None
    if it.get("max") and (cap is None or it["max"] < cap):   # 同一類合計上限一樣的話只寫合計 (例：回血類合計上限 5)
        parts.append(f"上限 {it['max']}")
    if it.get("max"):
        full = n >= it["max"]
    if cat:
        cur = sum(c for i, c in bag_items.items() if data.items().get(i, {}).get("cat") == cat)
        parts.append(f"{CAT_NAMES.get(cat, cat)}合計上限 {cap}")
        full = full or cur >= cap
    return "・".join(parts), full


def bag_entries(run: dict, kind: str) -> list[dict]:
    """
    某一類的每一樣 ➔ [{key (選單的值), line (清單那一行), label / desc (選單)}]
    kind = items / materials / treasures (同名同階合併，key = 第一個的位置) / relics (key = 位置) / pending (待撿，key = 位置)
    """
    bag, out = run["bag"], []
    if kind == "items":
        for iid, n in bag["items"].items():
            it = data.items().get(iid, {})
            stack = max(1, it.get("stack", 1))
            limit, full = item_limit(bag["items"], iid)
            line = (f"{item_name(iid)} ×{n}" + (f"（{limit}）" if limit else "") + (" ✅" if full else "")
                    + f"　🔲 {-(-n // stack)} 格・一格 {stack} 個")
            out.append({"key": iid, "line": line, "label": item_name(iid), "desc": item_option_desc(iid, n)})
    elif kind == "materials":
        for mid, n in bag["materials"].items():
            name, emoji = material_info(mid)
            line = f"{emoji} {name} ×{n}　🔲 {-(-n // rules.MATERIAL_STACK)} 格・一格 {rules.MATERIAL_STACK} 個"
            out.append({"key": mid, "line": line, "label": f"{emoji} {name}", "desc": f"有 {n} 個"})
    elif kind == "treasures":
        first, count = {}, {}
        for i, t in enumerate(bag["treasures"]):
            key = (t["id"], t["rarity"])
            first.setdefault(key, i)
            count[key] = count.get(key, 0) + 1
        for (tid, r), i in sorted(first.items(), key=lambda kv: -RARITY_SORT.get(kv[0][1], 0)):
            n = count[(tid, r)]
            out.append({"key": str(i), "line": f"{treasure_name(tid)}〔{r}〕×{n}　🔲 {n} 格",
                        "label": f"{treasure_name(tid)}〔{r}〕", "desc": f"有 {n} 個"})
    elif kind == "relics":
        for i, rel in enumerate(bag["relics"]):
            out.append({"key": str(i), "line": f"{relic_name(rel)}　🔲 1 格", "label": relic_name(rel),
                        "desc": data.relics().get(rel["rid"], {}).get("desc", "")})
    elif kind == "pending":
        for i, p in enumerate(run.get("pending") or []):
            out.append({"key": str(i), "line": pending_label(p), "label": pending_label(p), "desc": None})
    return out


def bag_tab_desc(run: dict, kind: str) -> str:
    if kind == "pending":
        return f"{len(run.get('pending') or [])} 樣放不下的東西"
    return f"{kind_slots(run['bag'], kind)} 格"


def bag_body(run: dict, kind: str, entries: list[dict], page: int = 1, total: int = 1) -> str:
    """背包畫面中間：總覽 + 這一類 (這一頁) 一樣一行；法具頁多列裝備中的 (不佔格)"""
    lines = [bag_summary(run), ""]
    if kind == "pending":
        lines += [f"### 📦 放不下的東西（{len(run.get('pending') or [])} 樣）", "-# 整理背包空出位置就能撿；離開這關就沒了"]
    else:
        lines.append(f"### {BAG_KINDS[kind]}（{kind_slots(run['bag'], kind)} 格）")
    lines += [e["line"] for e in entries] or ["-# 空空的。"]
    if total > 1:
        lines.append(f"-# 第 {page} / {total} 頁")
    if kind == "relics":
        worn = [f"{m['emoji']} {m['name']}：{relic_name(m['relic'])}" for m in run["party"] if m.get("relic")]
        if worn:
            lines += ["", "**裝備中** (不佔格)"] + worn
    return "\n".join(lines)


def item_option_desc(iid: str, n: int) -> str:
    it = data.items().get(iid, {})
    return f"有 {n} 個｜{it.get('desc', '')}"[:100]


# =========================================================
# 🏁 結算
# =========================================================
def _money_block(settle: dict) -> list[str]:
    if settle["result"] == "evacuated":
        return [f"# 💰 {settle['money']:,} 賽錢", f"-# 淨賺 {settle['money'] - settle['brought']:+,}（帶進 {settle['brought']:,}）"]
    return [f"# 💀 迷失在第 {settle['floor']} 關", f"-# 口袋的賽錢、背包的東西全部沒了 (帶進 {settle['brought']:,})"]


def _party_result(run: dict, settle: dict) -> str:
    pen = set(settle.get("penalty", []))
    out = []
    for m in run["party"]:
        mark = "✅" if m["alive"] else "💀"
        out.append(f"{mark} {m['emoji']} {m['name']}〔{m['rarity']}〕" + ("　📉 完整度 −0.1" if m["card_id"] in pen else ""))
    return "\n".join(out)


def build_settle_container(run: dict, settle: dict) -> ui.Container:
    ok = settle["result"] == "evacuated"
    c = ui.Container(accent_color=COLOR_GOOD if ok else discord.Color.dark_grey())
    c.add_item(ui.TextDisplay(f"## {RESULT_TITLES.get(settle['result'], '探索結束')}\n" + "\n".join(_money_block(settle))))
    c.add_item(ui.Separator())
    exp = settle.get("exp_result") or {}
    lines = [f"🕳️ 走到 **第 {settle['floor']} 關** ({zone_title(run, settle['floor'])})", f"📈 經驗 +{settle['exp']:,}"]
    if exp.get("leveled_up"):
        lines[-1] += f"　🎉 升到 {exp.get('new_p', 0):.1f} P"
    kills = sum(settle.get("kills", {}).values())
    if kills:
        lines.append(f"⚔️ 打倒 {kills} 隻")
    new = [data.enemies()[e] for e in settle.get("dex_new", []) if e in data.enemies()]
    if new:   # 📖 只寫在自己看得到的結算 (公開的不寫)
        lines.append("📖 圖鑑新登錄：" + "、".join(f"{e['emoji']} {e['name']}" for e in new) + "\n-# 用 `/ura bestiary` 看圖鑑")
    c.add_item(ui.TextDisplay("\n".join(lines)))
    if ok:
        got = loot_lines({"items": settle["items"], "materials": settle["materials"], "treasures": settle["treasures"]})
        if got:
            c.add_item(ui.Separator())
            c.add_item(ui.TextDisplay("**帶回來的東西**\n" + "\n".join(got) + "\n-# 道具、寶物在 `/ura inventory`；素材在神社倉庫"))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay("**隊伍**\n" + _party_result(run, settle)))
    return c


def build_public_settle_container(user_name: str, settle: dict) -> ui.Container:
    """在頻道公開的結算 (只放重點)"""
    ok = settle["result"] == "evacuated"
    c = ui.Container(accent_color=COLOR_GOOD if ok else discord.Color.dark_grey())
    head = f"## 🌀 {user_name} 的裏世界探索：{RESULT_TITLES.get(settle['result'], '結束')}"
    c.add_item(ui.TextDisplay(head + "\n" + "\n".join(_money_block(settle))))
    c.add_item(ui.Separator())
    party = "　".join(f"{'✅' if p['alive'] else '💀'} {p['name']}〔{p['rarity']}〕" for p in settle["party"])
    extra = f"🕳️ 第 {settle['floor']} 關 ({settle.get('zone_name') or zone_title(None, settle['floor'])})"
    if ok and settle["treasures"]:
        best = max(settle["treasures"], key=lambda t: RARITY_SORT.get(t["rarity"], 0))
        extra += f"　💎 寶物 {len(settle['treasures'])} 個 (最好：{treasure_name(best['id'])}〔{best['rarity']}〕)"
    c.add_item(ui.TextDisplay(f"{extra}\n-# {party}"))
    return c


# =========================================================
# 🏃 進行中的一局：主畫面文字 (按鈕 / 選單由 Cog 組)
# =========================================================
def build_run_container(run: dict, notice: str | None = None, body: str | None = None) -> ui.Container:
    """
    body = 換掉中間的內容 (背包、確認放棄、選目標…)；None ➔ 依 phase 顯示
    """
    phase = run["phase"]
    c = ui.Container(accent_color=COLOR_BATTLE if phase == "battle" else COLOR_RUN)
    if notice:
        c.add_item(ui.TextDisplay(notice))
        c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay(header_text(run)))
    c.add_item(ui.Separator())
    if body is not None:
        c.add_item(ui.TextDisplay(body))
        return c
    if phase == "battle":
        b = run["battle"]
        kind = {"normal": "⚔️ 戰鬥", "elite": "💀 精英戰", "mimic": "📦 寶箱怪", "boss": "👹 BOSS 戰"}.get(b["kind"], "戰鬥")
        if b.get("fest_boss"):
            kind = "🎪 👹 活動 BOSS 戰"
        elif b.get("fest"):
            kind = "🎪 " + kind
        enrage = "　😡 狂暴中" if b["kind"] != "boss" and b["round"] > rules.ENRAGE_AFTER else ""
        env = fest.env_text(b.get("fest"))
        envline = f"-# 🎪 {fest.info(b['fest']).get('name', '')}｜{env}\n" if env else ""
        c.add_item(ui.TextDisplay(f"### {kind}　第 {b['round']} 回合{enrage}\n{envline}" + "\n".join(foe_lines(run, f) for f in b["foes"])))
        c.add_item(ui.Separator())
        left = f"-# 這回合還能行動 {b['actions_left']} 次" + ("　📜 御札已用" if b["ofuda_used"] else "")
        c.add_item(ui.TextDisplay("**我方**\n" + party_block(run, b) + "\n" + left))
        log = log_text(b["log"], 6)
        if log:
            c.add_item(ui.Separator())
            c.add_item(ui.TextDisplay(log))
        return c
    parts = []
    if phase == "doors":
        last = last_battle_text(run)
        if last:
            parts.append(last)
        parts.append(doors_text(run))
    else:
        parts.append(room_text(run))
    pend = pending_text(run)
    if pend:
        parts.append(pend)
    c.add_item(ui.TextDisplay("\n\n".join(p for p in parts if p)))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay("**隊伍**\n" + party_line(run)))
    log = log_text(run.get("log", []), 3)
    if log:
        c.add_item(ui.TextDisplay(log))
    return c


# =========================================================
# 📖 狀態表 / 🛒 商店 / 📦 倉庫
# =========================================================
def build_status_table() -> ui.Container:
    c = ui.Container(accent_color=COLOR_RUN)
    good, bad = [], []
    for sid, s in data.statuses().items():
        if sid.startswith("_"):
            continue
        line = f"{s.get('emoji', '')} **{s.get('name', sid)}**：{s.get('desc', '')}"
        (good if s.get("good") else bad).append(line)
    c.add_item(ui.TextDisplay("## 📖 裏世界・狀態表\n-# 戰鬥畫面上的狀態後面括號 = 剩幾回合 / 幾次"))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay("### 🟢 好的狀態\n" + "\n".join(good)))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay("### 🔴 壞的狀態\n" + "\n".join(bad)))
    return c


SHOP_GROUPS = {"heal": "🩹 回血", "sanity": "🍵 回常識度", "battle": "⚔️ 戰鬥用", "doors": "🚪 選門 / 探索",
               "other": "🧰 其他", "bags": "🎒 額外背包"}


def shop_group_of(iid: str) -> str:
    if iid in data.bags():
        return "bags"
    it = data.items()[iid]
    if it.get("cat") in ("heal", "sanity"):
        return it["cat"]
    if it.get("use") == "battle" or it["effect"]["do"] in ("free_flee", "survive_down"):
        return "battle"
    if it.get("use") == "doors" or it["effect"]["do"] in ("team_status",):
        return "doors"
    return "other"


def shop_items(group: str) -> list[str]:
    if group == "bags":
        return list(data.bags())
    return [i for i, it in data.items().items() if it.get("price") and shop_group_of(i) == group]


def build_shop_container(group: str, money: int, storage: dict, selected: str | None, notice: str | None) -> ui.Container:
    c = ui.Container(accent_color=COLOR_RUN)
    if notice:
        c.add_item(ui.TextDisplay(notice))
        c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay(f"## 🛒 裏世界商店　{SHOP_GROUPS[group]}\n-# 買的東西放進裏世界倉庫，出發時再挑要帶哪些　💰 持有 `{money:,}`"))
    c.add_item(ui.Separator())
    lines = []
    for iid in shop_items(group):
        if group == "bags":
            b = data.bags()[iid]
            have = sum(1 for x in storage["bags"] if x["bag_id"] == iid)
            lines.append(f"{'▶️ ' if iid == selected else ''}🎒 **{b['name']}**〔{b['rarity']}〕　+{b['slots']} 格　`{b['price']:,}`" + (f"（倉庫 {have} 個）" if have else ""))
        else:
            it = data.items()[iid]
            cap = f"一局最多 {it['max']}" if it.get("max") else "不限"
            have = storage["items"].get(iid, 0)
            lines.append(f"{'▶️ ' if iid == selected else ''}{it['emoji']} **{it['name']}**　`{it['price']:,}`\n-# {it.get('desc', '')}｜{cap}" + (f"｜倉庫 {have}" if have else ""))
    c.add_item(ui.TextDisplay("\n".join(lines) or "-# 沒有東西"))
    if group == "bags":
        c.add_item(ui.TextDisplay("-# 額外背包用 3 次就壞 (出發時選要不要帶)"))
    return c


def treasure_rows(storage: dict, rarity: str | None = None, zone: str | None = None) -> list[tuple[str, dict, int]]:
    """倉庫的寶物 (照階級高到低)：[(id, info, 數量)]，可以篩選階級 / 區域 (zone_key)"""
    rows = []
    for tid, n in storage["treasures"].items():
        info = data.treasure_info(tid) or {"name": tid, "emoji": "💎", "rarity": "N", "zone_key": "?"}
        if rarity and info["rarity"] != rarity:
            continue
        if zone == "fest" and not str(info.get("zone_key", "")).startswith("fest:"):
            continue
        if zone and zone != "fest" and info.get("zone_key") != zone:
            continue
        rows.append((tid, info, n))
    return sorted(rows, key=lambda r: (-RARITY_SORT.get(r[1]["rarity"], 0), r[1]["name"]))


def build_storage_container(page: str, storage: dict, rows: list, page_items: list, filters: str, notice: str | None,
                            confirm_total: int | None = None, peek: str | None = None) -> ui.Container:
    """peek = 選了「🔍 看說明」的寶物 id (在寶物清單下面顯示它的說明)"""
    c = ui.Container(accent_color=COLOR_WARN if confirm_total is not None else COLOR_RUN)
    if notice:
        c.add_item(ui.TextDisplay(notice))
        c.add_item(ui.Separator())
    title = {"treasures": "💎 寶物", "items": "🧪 道具", "bags": "🎒 額外背包"}[page]
    c.add_item(ui.TextDisplay(f"## 📦 裏世界倉庫　{title}"))
    c.add_item(ui.Separator())
    if page == "treasures":
        prices = data.treasure_prices()
        total = sum(prices[info["rarity"]] * n for _, info, n in rows)
        head = f"-# {filters}　共 {sum(n for *_, n in rows)} 個，全部賣掉 `{total:,}` 賽錢"
        lines = [f"{info['emoji']} **{info['name']}**〔{info['rarity']}〕 ×{n}（一個 {prices[info['rarity']]:,}）"
                 for _, info, n in page_items]
        c.add_item(ui.TextDisplay(head + "\n" + ("\n".join(lines) or "-# 沒有寶物")))
        info = data.treasure_info(peek) if peek else None
        if info and confirm_total is None:
            c.add_item(ui.Separator())
            c.add_item(ui.TextDisplay(f"🔍 {info['emoji']} **{info['name']}**〔{info['rarity']}〕\n{info.get('desc') or '-# 還沒有說明'}"))
        if confirm_total is not None:
            c.add_item(ui.Separator())
            c.add_item(ui.TextDisplay(f"⚠️ 確定要把上面篩選出來的寶物**全部賣掉**嗎？可以拿到 `{confirm_total:,}` 賽錢，賣掉就拿不回來。"))
    elif page == "items":
        lines = [f"{item_name(i)} ×{n}\n-# {data.items().get(i, {}).get('desc', '')}" for i, n in page_items]
        c.add_item(ui.TextDisplay("\n".join(lines) or "-# 沒有道具 (用 `/ura shop` 買)"))
    else:
        lines = [f"🎒 **{data.bags()[b['bag_id']]['name']}**〔{data.bags()[b['bag_id']]['rarity']}〕 +{data.bags()[b['bag_id']]['slots']} 格（還能用 {b['uses_left']} 次）"
                 for b in page_items if b["bag_id"] in data.bags()]
        c.add_item(ui.TextDisplay("\n".join(lines) or "-# 沒有額外背包 (用 `/ura shop` 買)"))
    return c


# =========================================================
# 🚀 出發：整裝畫面
# =========================================================
def build_loadout_container(party: list[dict], carry: dict, storage: dict, capacity: int, bag_name: str | None,
                            pocket: int, money: int, notice: str | None) -> ui.Container:
    c = ui.Container(accent_color=COLOR_RUN)
    if notice:
        c.add_item(ui.TextDisplay(notice))
        c.add_item(ui.Separator())
    team = "\n".join(f"{p['emoji']} **{p['name']}**〔{p['rarity']}〕 完整度 {p['completeness']:.4f}（{CLASS_NAMES.get(p['cls'], '')}）"
                     for p in party)
    c.add_item(ui.TextDisplay(f"## 🚀 出發準備\n**隊伍**\n{team}"))
    c.add_item(ui.Separator())
    used = R.slots_used({"items": carry, "materials": {}, "treasures": [], "relics": []})
    carry_text = "、".join(f"{item_name(i)} ×{n}" for i, n in carry.items()) or "-# 什麼都沒帶"
    c.add_item(ui.TextDisplay(
        f"**🎒 要帶的道具** `{used} / {capacity}` 格" + (f"（額外背包：{bag_name}）" if bag_name else "") + f"\n{carry_text}\n"
        f"**💰 帶進去的賽錢** `{pocket:,}`\n-# 持有 {money:,}；口袋的錢只有成功撤離才帶得回來"))
    stock = "、".join(f"{item_name(i)} ×{n - carry.get(i, 0)}" for i, n in storage["items"].items() if n - carry.get(i, 0) > 0)
    c.add_item(ui.TextDisplay(f"-# 倉庫剩下：{stock or '沒有道具 (用 /ura shop 買)'}"))
    return c


# =========================================================
# 📖 怪物圖鑑 (/ura bestiary)
# =========================================================
def _reward_state(rid: str, kills: dict, claimed: set) -> str:
    from Database.ura import bestiary as B
    if rid in claimed:
        return "✅ 已領"
    if B.reward_ready(kills, rid):
        return "🎁 可以領"
    if rid == B.ALL_REWARD:
        done, total = B.progress(kills)["base"]
    else:
        sec = B.section(rid)
        done, total = B.done_count(kills, sec), len(sec["enemies"])
    return f"還差 {total - done} 隻"


def _reward_line(rid: str, kills: dict, claimed: set) -> str:
    from Database.ura import bestiary as B
    info = B.reward_info(rid)
    return f"🎁 {info['label']}：{info['money']:,} 賽錢 + {info['exp']:,} 經驗（{_reward_state(rid, kills, claimed)}）"


def build_bestiary_container(key: str, idx: int | None, kills: dict, claimed: set, notice: str | None = None) -> ui.Container:
    """圖鑑畫面：idx = None 是那一區的清單，數字是那一區第幾隻的圖鑑頁 (一隻一頁)"""
    from Database.ura import bestiary as B
    sec = B.section(key) or B.sections()[0]
    prog = B.progress(kills)
    c = ui.Container(accent_color=COLOR_RUN)
    if notice:
        c.add_item(ui.TextDisplay(notice))
        c.add_item(ui.Separator())
    fest_text = "　".join(f"🎪 {B.section('fest:' + f)['name']} {d} / {t}" for f, (d, t) in prog["fest"].items())
    c.add_item(ui.TextDisplay(f"## 📖 裏世界怪物圖鑑\n-# 📖 一般主題 {prog['base'][0]} / {prog['base'][1]}" +
                              (f"　{fest_text}" if fest_text else "") + "　(打倒或用糰子勸走過就登錄)"))
    c.add_item(ui.Separator())
    done, total = prog["sections"][sec["key"]]
    if idx is None:
        lines = []
        for eid, role in sec["enemies"]:
            e = B.entry(eid, role, kills)
            if e["unlocked"]:
                lines.append(f"✅ {e['emoji']} **{e['name']}**（{e['role_name']}）打倒 {e['kills']:,} 次")
            else:
                lines.append(f"❓ ？？？（{e['role_name']}）")
        c.add_item(ui.TextDisplay(f"### {sec['emoji']} {sec['name']}　{done} / {total}\n" + "\n".join(lines)))
        c.add_item(ui.Separator())
        rws = [sec["key"]] + ([B.ALL_REWARD] if sec["kind"] == "zone" else [])
        foot = "\n".join(_reward_line(r, kills, claimed) for r in rws)
        if sec["kind"] == "fest":
            foot += "\n-# 🎪 活動怪只在活動期間出現；活動結束後已登錄的照樣保留"
        c.add_item(ui.TextDisplay(foot + "\n-# 用下面的選單看每一隻的圖鑑頁"))
        return c
    eid, role = sec["enemies"][max(0, min(idx, len(sec["enemies"]) - 1))]
    e = B.entry(eid, role, kills)
    where = f"{sec['emoji']} {sec['name']}"
    if not e["unlocked"]:
        text = f"## ❓ ？？？\n-# {e['role_name']}・出沒：{where}\n還沒打倒過。"
        if sec["kind"] == "fest":
            text += "\n-# 🎪 活動期間才會出現"
        c.add_item(ui.TextDisplay(text))
    else:
        c.add_item(ui.TextDisplay(f"## {e['emoji']} {e['name']}\n-# {e['role_name']}・出沒：{where}\n{e['desc']}"))
        c.add_item(ui.Separator())
        hp, atk, df = e["stats"]
        stat = f"❤️ {hp:,}　⚔️ {atk:,}　🛡️ {df:,}" + (f"　💨 閃避 {round(e['dodge'] * 100):g}%" if e["dodge"] else "")
        if e["skills"]:
            sk = "\n".join(f"・**{s['name']}**：{s['text']}" + (f"（{'、'.join(s['conds'])}）" if s["conds"] else "") for s in e["skills"])
        else:
            sk = "-# 只會普攻"
        extra = []
        if role == "boss":
            extra.append(f"-# 區域 BOSS {B.BOSS_DEEP_NOTE}")
            if e.get("deep_order"):
                extra.append("-# 深區開招順序：" + " ➔ ".join(e["deep_order"]))
        if e["hint"]:
            extra.append(f"💡 {e['hint']}")
        c.add_item(ui.TextDisplay(f"{stat}\n-# 第 1 區時的數值 (越深的區越強)\n**招式**\n{sk}" + ("\n" + "\n".join(extra) if extra else "")))
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(f"⚔️ 打倒 {e['kills']:,} 次 (含勸走)"))
    c.add_item(ui.TextDisplay(f"-# {sec['emoji']} {sec['name']}　第 {idx + 1} / {len(sec['enemies'])} 隻"))
    return c

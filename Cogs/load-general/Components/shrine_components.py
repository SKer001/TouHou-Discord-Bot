"""
⛩️ 神社經營畫面 (Components V2)：只負責把資料畫成畫面，不碰資料庫
"""
import discord
from discord import ui

from Database import shrine_data
from Utils.numbers import fmt_money   # 持有金額一萬以上縮寫 (1.5M)
from Utils.gacha_pools import GACHA_POOLS   # /event info 的「🎴 活動卡池」名稱


def ts(dt, style: str = "R") -> str:
    """Discord 時間戳記 (會依觀看者時區顯示，R = 「3 小時後」)"""
    return f"<t:{int(dt.timestamp())}:{style}>"


def _bar(value: float, maximum: float, width: int = 10) -> str:
    filled = 0 if maximum <= 0 else round(width * min(1.0, value / maximum))
    return "▰" * filled + "▱" * (width - filled)


DIRT_NAMES = ["✨ 一塵不染", "🍃 有點落葉", "🍂 落葉滿地", "🕸️ 蜘蛛網", "🏚️ 荒廢"]
MOOD_EMOJI = [(80, "😊"), (50, "🙂"), (20, "😐"), (0, "😠")]
LOCATION_NAMES = {k: f"{v['emoji']} {v['name']}" for k, v in shrine_data.LOCATIONS.items()}
MODIFIER_NAMES = {"shrine_income": "神社收入", "youkai_reward": "打退妖怪的賽錢", "serve_reward": "招待報酬", "explore_stamina": "採集體力消耗",
                  "youkai_spawn": "妖怪出現機率", "guest_spawn": "參拜客來訪機率", "daily_money": "簽到賽錢",
                  "daily_exp": "簽到經驗", "decompose": "分解拿到的賽錢"}


def _mood_emoji(mood: int) -> str:
    return next(e for limit, e in MOOD_EMOJI if mood >= limit)


def item_label(items: dict, item_id: str) -> str:
    info = items.get(item_id) or {}
    return f"{info.get('emoji', '❓')}{info.get('name', item_id)}"


def order_text(items: dict, order: list[str]) -> str:
    return "、".join(f"**{item_label(items, d)}**" for d in order)


def build_shrine_container(user_name: str, s: dict, notice: str | None = None, items: dict | None = None) -> ui.Container:
    """神社主畫面：賽錢箱 / 效率 / 清潔度 / 妖怪 / 參拜客"""
    eff = s["efficiency"]
    color = discord.Color.green() if eff >= 0.8 else discord.Color.orange() if eff >= 0.5 else discord.Color.red()
    container = ui.Container(accent_color=color)
    if notice:
        container.add_item(ui.TextDisplay(notice))
        container.add_item(ui.Separator())

    box_line = f"💰 **賽錢箱**　`{fmt_money(s['box'])} / {fmt_money(s['box_max'])}`\n{_bar(s['box'], s['box_max'])}"
    if s["box"] >= s["box_max"]:
        box_line += "\n-# ⚠️ 賽錢箱滿了！不回收就不會再累積"
    elif s["box_full_at"]:
        box_line += f"\n-# 每小時 +`{s['income_per_hour']:,}`，{ts(s['box_full_at'])}裝滿"

    penalties = []
    if s["dirt_penalty"]:
        penalties.append(f"髒亂 −{s['dirt_penalty']:.0%}")
    if s["youkai_penalty"]:
        penalties.append(f"妖怪 −{s['youkai_penalty']:.0%}")
    eff_line = f"⚙️ **神社效率**　`{eff:.0%}`" + (f"（{'、'.join(penalties)}）" if penalties else "")

    dirt_line = f"🧹 **清潔度**　{DIRT_NAMES[s['dirt']]}　`{s['dirt']} / {s['dirt_max']}`"
    if s["next_dirt_at"]:
        dirt_line += f"\n-# {ts(s['next_dirt_at'])}會再髒一階"

    youkai_line = f"👹 **作亂的妖怪**　`{s['youkai']} / {s['youkai_max']}` 隻"
    if s["youkai"]:
        youkai_line += "\n-# 打退一隻 +800～1,500 賽錢，但會留下晦氣（清潔度 −1 階）"

    container.add_item(ui.TextDisplay(f"## ⛩️ {user_name} 的神社\n{box_line}\n\n{eff_line}\n{dirt_line}\n{youkai_line}"))
    container.add_item(ui.Separator())

    if s["guests"]:
        lines = [f"🙏 **參拜的妖怪**　`{len(s['guests'])} / {s['guest_max']}` 位"]
        # 對齊：名字用全形空白補到一樣長 (中文字等寬)，數字在 code 等寬字型裡靠右對齊
        name_w = max(len(g["name"]) for g in s["guests"])
        for g in s["guests"]:
            name = g["name"] + "　" * (name_w - len(g["name"]))
            ordered = "、".join(item_label(items or {}, d) for d in g["order"])
            lines.append(
                f"{_mood_emoji(g['mood'])} {g['emoji']} **{name}**　心情 `{g['mood']:>3}%`　"
                f"每份 `{g['reward_per_portion']:>5,}` 賽錢 · {ts(g['next_drop_at'])}心情變差\n-# 　點了：{ordered}"
            )
        lines.append("-# 🍵 按「招待」選一位客人端上料理；料理用「🍳 料理」做，素材靠「🗺️ 採集」或「🏪 雜貨店」")
    else:
        lines = ["🙏 **參拜的妖怪**　目前沒有客人", "-# 每 2 小時有機會來一位"]
    lines.append(f"-# 下一次妖怪 / 參拜客判定：{ts(s['next_event_at'])}")
    container.add_item(ui.TextDisplay("\n".join(lines)))
    return container


# =========================================================
# 🍵 招待
# =========================================================
def build_serve_container(g: dict, items: dict, inventory: dict, extra: str | None, preview: dict,
                          image_url: str | None, event_bonus: float) -> ui.Container:
    """
    招待畫面：客人圖 + 依心情變化的點餐台詞、點的料理 (有沒有)、額外招待、報酬預估
    preview = calc_serve_reward 的結果 (正中最愛的加成不先講，只給提示)
    """
    container = ui.Container(accent_color=discord.Color.from_rgb(232, 120, 150))
    line = g["line"].format(order="、".join(item_label(items, d) for d in g["order"]))
    head = (f"## {g['emoji']} {g['name']}" + ("　🎪 活動客人" if g.get("event") else "") + "\n"
            f"「{line}」\n-# {_mood_emoji(g['mood'])} 心情 `{g['mood']}%` · {ts(g['leave_at'])}會生氣離開")
    if image_url:
        container.add_item(ui.Section(ui.TextDisplay(head), accessory=ui.Thumbnail(image_url)))
    else:
        container.add_item(ui.TextDisplay(head))
    container.add_item(ui.Separator())

    need = {}
    for d in g["order"] + ([extra] if extra else []):
        need[d] = need.get(d, 0) + 1
    rows = ["🧾 **點餐**（每道 1 份，一定要給齊）"]
    for d in g["order"]:
        have = inventory.get(d, 0)
        mark = "✅" if have >= need[d] else "❌"
        evt = "　🎪×1.2" if items.get(d, {}).get("effect", {}).get("event") else ""
        rows.append(f"{mark} {item_label(items, d)}　倉庫 `{have}` 份{evt}")
    rows.append("")
    if extra:
        have = inventory.get(extra, 0)
        rows.append(f"🎁 **額外招待**：{item_label(items, extra)} 1 份" + ("" if have >= need[extra] else "　❌ 不夠"))
    else:
        rows.append("🎁 **額外招待**：不招待")
    rows.append("-# 用下面的選單挑一份額外招待（可以不選）；點的菜會全部端上，不用選")
    rows.append(f"-# 💡 {g['hint']}")
    bonus = f"（含活動料理 ×{event_bonus:g}^{preview['event_count']}）" if preview["event_count"] else ""
    rows.append(f"\n💰 預估報酬 `{preview['total']:,}` 賽錢{bonus}\n-# 份數 × 2,000 × 心情²；額外招待正中客人的最愛時，整筆再 ×1.5")
    container.add_item(ui.TextDisplay("\n".join(rows)))
    return container


# =========================================================
# 🗺️ 採集 / 🍳 料理 / 🏪 雜貨店
# =========================================================
def build_explore_container(locations: dict, stamina: dict, cost: int, result: dict | None, items: dict) -> ui.Container:
    container = ui.Container(accent_color=discord.Color.dark_green())
    text = (f"## 🗺️ 採集素材\n每趟消耗 `{cost}` 體力，帶回 3～5 個素材（偶爾會遇到好事或倒楣事）\n"
            f"⚡ 體力 `{stamina['stamina']} / {stamina['max']}`")
    if stamina.get("next_in"):
        text += f"\n-# 下一點 {stamina['next_in'] // 60} 分 {stamina['next_in'] % 60} 秒後回復"
    container.add_item(ui.TextDisplay(text))
    if result:
        container.add_item(ui.Separator())
        loc = result["location"]
        lines = [f"### {loc['emoji']} {loc['name']} × {len(result['runs'])} 趟"]
        if len(result["runs"]) < result["requested"]:
            lines.append(f"-# ⚠️ 體力只夠 {len(result['runs'])} 趟")
        for i, r in enumerate(result["runs"], 1):
            got = "、".join(f"{item_label(items, m)}×{k}" for m, k in sorted(r["drops"].items())) or "什麼都沒有"
            prefix = f"`{i}.` " if len(result["runs"]) > 1 else ""
            lines.append(f"{prefix}{got}")
            if r["event"]:
                lines.append(f"-# {'🍀' if r['event']['good'] else '💥'} {r['event']['text']}")
        total = "、".join(f"{item_label(items, m)}×{k}" for m, k in sorted(result["total"].items())) or "（無）"
        lines.append(f"\n🧺 **合計**：{total}")
        container.add_item(ui.TextDisplay("\n".join(lines)))
    container.add_item(ui.Separator())
    loc_lines = []
    for loc in locations.values():
        drops = "、".join(item_label(items, m) for m in loc["drops"])
        loc_lines.append(f"{loc['emoji']} **{loc['name']}**{'　🎪 活動限定' if loc.get('event') else ''}\n-# 　{drops}")
    container.add_item(ui.TextDisplay("\n".join(loc_lines)))
    return container


# 料理畫面的分類 (Discord 選單最多 25 個，料理變多後改成先選分類再選料理；0.35.000)
COOK_CATEGORIES = {"food": "🍚 食物", "drink": "🍵 茶水", "dessert": "🍮 點心", "stamina": "⚡ 體力料理"}


def dish_category(dish_id: str, rules: dict) -> str:
    """料理畫面的分類：體力料理 = stamina，其他照 dish_types (food / drink / dessert)"""
    if dish_id in rules.get("stamina_dishes", ()):
        return "stamina"
    return rules["dish_types"].get(dish_id, "food")


def build_cook_container(rules: dict, items: dict, inventory: dict, selected: str | None,
                         notice: str | None = None, serve_queue: list[str] | None = None) -> ui.Container:
    """
    料理畫面：說明 + 選到的料理 (配方、有沒有素材)
    serve_queue = 從招待畫面跳過來時，客人點的還沒做的菜 (第一道就是 selected)
    """
    container = ui.Container(accent_color=discord.Color.orange())
    if notice:
        container.add_item(ui.TextDisplay(notice))
        container.add_item(ui.Separator())
    text = (f"## 🍳 料理\n先選分類、再選料理。招待料理一鍋 `{shrine_data.COOK_YIELD}` 份，"
            f"⚡ 體力料理一鍋 `{shrine_data.STAMINA_COOK_YIELD}` 份")
    if serve_queue:
        text += "\n-# 🍵 客人還在等：" + "、".join(item_label(items, d) for d in serve_queue)
    if selected:
        recipe = rules["recipes"][selected]
        parts = []
        for m, k in recipe.items():
            have = inventory.get(m, 0)
            parts.append(f"{'✅' if have >= k else '❌'} {item_label(items, m)}×{k}（有 {have}）")
        can = min(inventory.get(m, 0) // k for m, k in recipe.items())
        info = items.get(selected, {})
        kind = COOK_CATEGORIES.get(dish_category(selected, rules), "")
        restore = info.get("effect", {}).get("stamina")
        extra = f" · 吃了回復 `{restore}` 體力" if restore else ""
        text += (f"\n\n### {item_label(items, selected)}\n-# {kind} · {info.get('desc', '')}\n"
                 + "\n".join(parts)
                 + f"\n倉庫裡有 `{inventory.get(selected, 0)}` 份 · 素材夠做 `{can}` 鍋"
                 + f"（一鍋 {shrine_data.cook_yield(selected, rules)} 份）{extra}")
        if can < 1:
            text += "\n-# 素材不夠的話，可以按「🧺 快速採集」自動去採缺的素材"
    container.add_item(ui.TextDisplay(text))
    return container


def build_gather_container(dish_id: str, missing: dict, plan: dict, rules: dict, items: dict, stamina: dict,
                           cost: int, buy: dict, buy_cost: int, result: dict | None = None,
                           notice: str | None = None) -> ui.Container:
    """
    🧺 快速採集畫面：還差什麼 ➔ 預估要去哪裡、幾趟 (計算過程) ➔ 剛剛採集的結果
    plan = Economy_DB_Manager.plan_gather(missing)；buy / buy_cost = 雜貨店能直接買的部分
    """
    container = ui.Container(accent_color=discord.Color.dark_green())
    if notice:
        container.add_item(ui.TextDisplay(notice))
        container.add_item(ui.Separator())
    locs = rules["locations"]

    def mats(d: dict) -> str:
        return "、".join(f"{item_label(items, m)}×{k}" for m, k in d.items())

    head = f"## 🧺 快速採集：{item_label(items, dish_id)}\n⚡ 體力 `{stamina['stamina']} / {stamina['max']}` · 每趟 `{cost}` 體力"
    if stamina.get("next_in"):
        head += f"\n-# 下一點 {stamina['next_in'] // 60} 分 {stamina['next_in'] % 60} 秒後回復"
    container.add_item(ui.TextDisplay(head))

    if result:
        container.add_item(ui.Separator())
        lines = [f"### 🗺️ 剛剛採了 {len(result['runs'])} 趟"]
        for i, r in enumerate(result["runs"], 1):
            loc = locs.get(r["location"], {})
            got = mats(dict(sorted(r["drops"].items()))) or "什麼都沒有"
            lines.append(f"`{i}.` {loc.get('emoji', '')} {loc.get('name', r['location'])}：{got}")
            if r["event"]:
                lines.append(f"-# {'🍀' if r['event']['good'] else '💥'} {r['event']['text']}")
        if result["stopped"] == "no_stamina":
            lines.append("-# ⚡ 體力不夠，先停在這裡")
        elif result["stopped"] == "done" and len(result["runs"]) < result["requested"]:
            lines.append(f"-# ✨ 素材採齊了，提早收工（省下 {result['requested'] - len(result['runs'])} 趟）")
        container.add_item(ui.TextDisplay("\n".join(lines)))

    container.add_item(ui.Separator())
    if not missing:
        container.add_item(ui.TextDisplay("✅ **素材都齊了！** 按「🍳 回去料理」把菜做出來吧。"))
        return container
    lines = [("⚠️ **還沒採齊，還差**：" if result else "🧾 **做 1 鍋還差**：") + mats(missing)]
    if plan["stops"]:
        lines.append("\n📐 **預估**（一趟平均 = 3～5 個 ÷ 那個地點的素材種類）")
        for i, s in enumerate(plan["stops"], 1):
            loc = locs.get(s["location"], {})
            parts = [f"{item_label(items, m)}×{n}（一趟約 {s['per_trip'][m]:.1f} 個）" for m, n in s["materials"].items()]
            lines.append(f"`{i}.` {loc.get('emoji', '')} **{loc.get('name', s['location'])}**：{'、'.join(parts)} ➔ 約 `{s['trips']}` 趟")
        lines.append(f"合計約 **{plan['trips']} 趟**、`{plan['trips'] * cost}` 體力")
        lines.append("-# 按幾趟就總共採幾趟：先去最缺的地方，那邊夠了就換下一個；全部採齊會提早停，不會多花體力")
        lines.append("-# 採集是隨機的，運氣不好可能要多跑幾趟" + ("，跑完還不夠會提醒你再按一次" if not result else ""))
    if plan["unavailable"]:
        lines.append(f"\n🚫 現在採不到：{mats(plan['unavailable'])}（可能是活動素材）")
    if buy:
        lines.append(f"\n🏪 人里的素材也可以直接買：{mats(buy)} = `{buy_cost:,}` 賽錢")
    container.add_item(ui.TextDisplay("\n".join(lines)))
    return container


def build_shop_container(prices: dict, items: dict, inventory: dict, money: int, selected: str | None,
                         notice: str | None = None) -> ui.Container:
    container = ui.Container(accent_color=discord.Color.from_rgb(180, 140, 90))
    if notice:
        container.add_item(ui.TextDisplay(notice))
        container.add_item(ui.Separator())
    lines = ["## 🏪 人間之里雜貨店", "「歡迎光臨！巫女大人今天也是來賒帳的嗎？」", ""]
    for m, p in prices.items():
        pick = "▶ " if m == selected else ""
        lines.append(f"{pick}{item_label(items, m)}　`{p:,}` 賽錢 / 個　（倉庫 {inventory.get(m, 0)}）")
    lines.append(f"\n💰 你的賽錢 `{fmt_money(money)}`\n-# 只賣人里的基本食材；八目鰻、冰晶這些要自己去採集")
    container.add_item(ui.TextDisplay("\n".join(lines)))
    return container


# =========================================================
# 🎪 活動
# =========================================================
def build_event_container(overview: list[dict], items: dict, recipes: dict) -> ui.Container:
    container = ui.Container(accent_color=discord.Color.red())
    container.add_item(ui.TextDisplay("## 🎪 活動一覽"))
    status_text = {"active": "🟢 進行中", "upcoming": "⏳ 尚未開始", "ended": "⚫ 已結束"}
    if not overview:
        container.add_item(ui.TextDisplay("目前沒有活動。"))
    for o in overview:
        ev = o["event"]
        when = ""
        if o["status"] == "active":
            when = f"　{ts(_iso(o['ends_at']))}結束" if o.get("ends_at") else "　（測試中，沒有結束時間）"
        lines = [f"### {ev['emoji']} {ev['name']}　{status_text[o['status']]}{when}",
                 f"-# {ev.get('series', '')} · 表定 {ev.get('duration_days', '?')} 天", ev.get("description", "")]
        loc = ev.get("location")
        if loc:
            drops = "、".join(item_label(items, m) for m in loc["drops"])
            lines.append(f"\n🗺️ **限定採集地點**：{loc['emoji']} {loc['name']}\n-# {drops}")
        dishes = [it for it in ev.get("items", []) if it.get("category") == "cuisine"]
        if dishes:
            lines.append("\n🍱 **限定料理**（點餐有機率出現，端上桌報酬 ×" + f"{ev.get('event_dish_bonus', 1):g}" + "）")
            for d in dishes:
                r = recipes.get(d["id"], {})
                need = " + ".join(f"{item_label(items, m)}×{k}" for m, k in r.items())
                lines.append(f"{d['emoji']} **{d['name']}**\n-# 　{need}")
        guests = ev.get("guests", {})
        if guests:
            lines.append("\n🙏 **限定客人**：" + "、".join(f"{g['emoji']} {g['name']}" for g in guests.values()))
        pool = (ev.get("gacha") or {}).get("pool") or {}   # 🎴 活動卡池 (Events/README.md)
        if pool.get("from") in GACHA_POOLS:   # 一般卡池只在活動期間開放 (紅霧異變 ➔ 紅魔鄉卡池)
            lines.append(f"\n🎴 **活動卡池**：{GACHA_POOLS[pool['from']]['name']}\n"
                         "-# `/card gacha` 選「🎪 活動限定卡池」，活動期間才抽得到；保底照樣記在這個卡池")
        elif pool.get("characters"):
            name = pool.get("name") or f"{ev.get('emoji', '🎪')} {ev.get('name', '')}卡池"
            lines.append(f"\n🎴 **活動卡池**：{name}\n-# `/card gacha` 選「🎪 活動限定卡池」")
        # 加在一般機制上的活動內容 (預留位，見 Database/events.py 的 game_rules)
        extra = []
        for loc_id, drops in ev.get("extra_drops", {}).items():
            extra.append(f"🗺️ {LOCATION_NAMES.get(loc_id, loc_id)} 可以採到：" + "、".join(item_label(items, m) for m in drops))
        if ev.get("explore_events"):
            extra.append("🍀 一般採集地點有活動限定的事件")
        if ev.get("shop"):
            extra.append("🏪 雜貨店活動商品：" + "、".join(f"{item_label(items, m)} `{p:,}`" for m, p in ev["shop"].items()))
        gacha = ev.get("gacha", {})
        if gacha.get("rate_up"):
            extra.append("🎴 祈願機率提升：" + "、".join(f"{k} ×{v:g}" for k, v in gacha["rate_up"].items()))
        if isinstance(gacha.get("rarity_weights"), dict) and gacha["rarity_weights"]:   # {階級: %} (2026-11-22 起)
            extra.append("🎴 祈願起始機率調整：" + " / ".join(f"{r} {v:g}%" for r, v in gacha["rarity_weights"].items()))
        if ev.get("daily_items"):
            extra.append("📅 簽到額外送：" + "、".join(f"{item_label(items, i)} ×{n}" for i, n in ev["daily_items"]))
        if ev.get("guest_overrides"):
            extra.append("🙏 有些一般客人在活動期間口味或台詞不一樣")
        mods = {k: v for k, v in ev.get("modifiers", {}).items() if v != 1 and k in MODIFIER_NAMES}
        if mods:
            extra.append("📈 " + "、".join(f"{MODIFIER_NAMES[k]} ×{v:g}" for k, v in mods.items()))
        if extra:
            lines.append("\n✨ **活動期間**\n" + "\n".join(extra))
        lines.append("\n-# ⚠️ 活動結束時，所有活動素材與活動料理會從神社倉庫清除")
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay("\n".join(lines)))
    return container


def _iso(value):
    from datetime import datetime
    return datetime.fromisoformat(value)

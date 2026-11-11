"""
⛩️ 神社經營畫面 (Components V2)：只負責把資料畫成畫面，不碰資料庫
"""
import discord
from discord import ui

from Database import shrine_data


def ts(dt, style: str = "R") -> str:
    """Discord 時間戳記 (會依觀看者時區顯示，R = 「3 小時後」)"""
    return f"<t:{int(dt.timestamp())}:{style}>"


def _bar(value: float, maximum: float, width: int = 10) -> str:
    filled = 0 if maximum <= 0 else round(width * min(1.0, value / maximum))
    return "▰" * filled + "▱" * (width - filled)


DIRT_NAMES = ["✨ 一塵不染", "🍃 有點落葉", "🍂 落葉滿地", "🕸️ 蜘蛛網", "🏚️ 荒廢"]
MOOD_EMOJI = [(80, "😊"), (50, "🙂"), (20, "😐"), (0, "😠")]
LOCATION_NAMES = {k: f"{v['emoji']} {v['name']}" for k, v in shrine_data.LOCATIONS.items()}
MODIFIER_NAMES = {"shrine_income": "神社收入", "youkai_reward": "打退妖怪的賽錢", "serve_reward": "招待報酬", "explore_stamina": "採集體力消耗"}


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

    box_line = f"💰 **賽錢箱**　`{s['box']:,} / {s['box_max']:,}`\n{_bar(s['box'], s['box_max'])}"
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
        rows.append(f"🎁 **額外招待**：{item_label(items, extra)}" + ("" if have >= need[extra] else "　❌ 不夠"))
    else:
        rows.append("🎁 **額外招待**：（沒有）")
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
        drops = " ".join(items.get(m, {}).get("emoji", "❓") for m in loc["drops"])
        loc_lines.append(f"{loc['emoji']} **{loc['name']}**{'　🎪 活動限定' if loc.get('event') else ''}　{drops}")
    container.add_item(ui.TextDisplay("\n".join(loc_lines)))
    return container


def build_cook_container(recipes: dict, dish_types: dict, items: dict, inventory: dict, selected: str | None,
                         cook_yield: int, notice: str | None = None) -> ui.Container:
    container = ui.Container(accent_color=discord.Color.orange())
    if notice:
        container.add_item(ui.TextDisplay(notice))
        container.add_item(ui.Separator())
    text = f"## 🍳 料理\n選一道料理，一次做一鍋 = `{cook_yield}` 份"
    if selected:
        recipe = recipes[selected]
        parts = []
        for m, k in recipe.items():
            have = inventory.get(m, 0)
            parts.append(f"{'✅' if have >= k else '❌'} {item_label(items, m)}×{k}（有 {have}）")
        can = min(inventory.get(m, 0) // k for m, k in recipe.items())
        info = items.get(selected, {})
        text += (f"\n\n### {item_label(items, selected)}\n-# {info.get('desc', '')}\n"
                 + "\n".join(parts) + f"\n倉庫裡有 `{inventory.get(selected, 0)}` 份 · 素材夠做 `{can}` 鍋")
    container.add_item(ui.TextDisplay(text))
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
    lines.append(f"\n💰 你的賽錢 `{money:,}`\n-# 只賣人里的基本食材；八目鰻、冰晶這些要自己去採集")
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
        # 加在一般機制上的活動內容 (預留位，見 Database/events.py 的 game_rules)
        extra = []
        for loc_id, drops in ev.get("extra_drops", {}).items():
            extra.append(f"🗺️ {LOCATION_NAMES.get(loc_id, loc_id)} 可以採到：" + "、".join(item_label(items, m) for m in drops))
        if ev.get("explore_events"):
            extra.append("🍀 一般採集地點有活動限定的事件")
        if ev.get("shop"):
            extra.append("🏪 雜貨店活動商品：" + "、".join(f"{item_label(items, m)} `{p:,}`" for m, p in ev["shop"].items()))
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

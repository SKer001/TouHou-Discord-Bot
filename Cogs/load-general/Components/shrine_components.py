"""
⛩️ 神社經營畫面 (Components V2)：只負責把資料畫成畫面，不碰資料庫
"""
import discord
from discord import ui


def ts(dt, style: str = "R") -> str:
    """Discord 時間戳記 (會依觀看者時區顯示，R = 「3 小時後」)"""
    return f"<t:{int(dt.timestamp())}:{style}>"


def _bar(value: float, maximum: float, width: int = 10) -> str:
    filled = 0 if maximum <= 0 else round(width * min(1.0, value / maximum))
    return "▰" * filled + "▱" * (width - filled)


DIRT_NAMES = ["✨ 一塵不染", "🍃 有點落葉", "🍂 落葉滿地", "🕸️ 蜘蛛網", "🏚️ 荒廢"]
MOOD_EMOJI = [(80, "😊"), (50, "🙂"), (20, "😐"), (0, "😠")]


def _mood_emoji(mood: int) -> str:
    return next(e for limit, e in MOOD_EMOJI if mood >= limit)


def build_shrine_container(user_name: str, s: dict, notice: str | None = None) -> ui.Container:
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
        youkai_line += "\n-# 打退一隻 +1,000 賽錢，但會留下晦氣（清潔度 −1 階）"

    container.add_item(ui.TextDisplay(f"## ⛩️ {user_name} 的神社\n{box_line}\n\n{eff_line}\n{dirt_line}\n{youkai_line}"))
    container.add_item(ui.Separator())

    if s["guests"]:
        lines = [f"🙏 **參拜的妖怪**　`{len(s['guests'])} / {s['guest_max']}` 位"]
        # 對齊：名字用全形空白補到一樣長 (中文字等寬)，數字在 code 等寬字型裡靠右對齊
        name_w = max(len(g["kind"]) for g in s["guests"])
        for g in s["guests"]:
            name = g["kind"] + "　" * (name_w - len(g["kind"]))
            lines.append(
                f"{_mood_emoji(g['mood'])} **{name}**　心情 `{g['mood']:>3}%`　"
                f"每份餐點 `{g['reward_per_portion']:>5,}` 賽錢 · {ts(g['next_drop_at'])}心情變差"
            )
        lines.append("-# 🍵 招待需要餐點（食物 / 茶水 / 點心），素材副本開放後就能製作")
    else:
        lines = ["🙏 **參拜的妖怪**　目前沒有客人", "-# 每 2 小時有機會來一位"]
    lines.append(f"-# 下一次妖怪 / 參拜客判定：{ts(s['next_event_at'])}")
    container.add_item(ui.TextDisplay("\n".join(lines)))
    return container

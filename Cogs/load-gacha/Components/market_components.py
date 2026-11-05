"""
💹 市值 / 分解 / 市場 / 轉帳畫面 (Components V2)：只負責把資料畫成畫面，不碰資料庫
"""
import discord
from discord import ui

from .gacha_components import get_thumbnail_url


def card_label(card: dict) -> str:
    return f"{card.get('emoji') or '🎴'} {card['name']} [{card['rarity']}] {card['completeness']:.4f}"


def short_id(instance_id: str) -> str:
    return instance_id.rsplit("_", 1)[-1][:6]


def build_price_container(char: dict, rows: list[dict], thumbnails: dict | None) -> ui.Container:
    """
    /market price：一個角色每個階級的市值
    rows = [{"rarity", "title", "price", "official", "sold_today", "values": {完整度: 價值}, "history": [...]}]
    """
    container = ui.Container(accent_color=discord.Color.gold())
    container.add_item(ui.TextDisplay(
        f"## 💹 {char['emoji']} {char['name']} 的市值\n"
        "-# 市值 = 完整度 0.5 的價格；每天台灣時間 00:00 結算（±10%），不會低於官方回收價"
    ))
    for row in rows:
        values = "｜".join(f"`{c:.4f}` ➔ `{v:,}`" for c, v in row["values"].items())
        hist = " → ".join(f"{h['day'][5:].replace('-', '/')} `{h['change']:+.1%}`" for h in row["history"]) or "還沒有結算紀錄"
        text = (
            f"**[{row['rarity']}]** *{row['title']}*\n"
            f"市值 `{row['price']:,.0f}`（官方價 `{row['official']:,}`）· 今天已賣出 `{row['sold_today']}` 張\n"
            f"{values}\n-# 近 7 天：{hist}"
        )
        url = get_thumbnail_url(char["key"], thumbnails, row["rarity"])
        container.add_item(ui.Separator())
        if url:
            container.add_item(ui.Section(ui.TextDisplay(text), accessory=ui.Thumbnail(url)))
        else:
            container.add_item(ui.TextDisplay(text))
    return container


def build_listing_lines(listings: list[dict], buyer_total, me: int | None = None) -> str:
    lines = []
    for i, l in enumerate(listings, 1):
        mine = "（你的）" if me is not None and l["seller_id"] == me else ""
        lines.append(
            f"`{i:>2}.` {card_label(l)} · 售價 `{buyer_total(l['price']):,}`{mine}\n"
            f"-# ⌛ <t:{l['expires_ts']}:R>下架 · ID `{short_id(l['instance_id'])}`"
        )
    return "\n".join(lines)


def simple_container(text: str, color: discord.Color | None = None) -> ui.Container:
    container = ui.Container(accent_color=color or discord.Color.blurple())
    container.add_item(ui.TextDisplay(text))
    return container

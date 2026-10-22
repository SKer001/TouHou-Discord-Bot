"""
🧩 共用的 Components V2 通知工具

所有「回傳通知」(成功 / 失敗 / 提示) 都用這裡產生，畫面風格一致：
  - notice_container()：一個帶左側色條的 Container (可再自行 add_item 按鈕等)
  - notice_view()     ：把 Container 包成 LayoutView，可直接 send / edit
  - send_notice()     ：自動判斷要用 response 還是 followup 送出

⚠️ Components V2 訊息不能同時帶 content / embeds，且一旦是 V2 之後只能以 V2 編輯。
"""
import discord
from discord import ui

# 依開頭 emoji 自動決定色條顏色；都不符合時用 DEFAULT_COLOR
PREFIX_COLORS = [
    (("❌", "🚫", "🗑️"), discord.Color.red()),
    (("⚠️",), discord.Color.orange()),
    (("✅", "🎁", "✨", "🟢"), discord.Color.green()),
    (("↩️", "✖️", "⚙️"), discord.Color.dark_grey()),
]
DEFAULT_COLOR = discord.Color.blurple()


def pick_color(text: str) -> discord.Color:
    stripped = text.lstrip()
    for prefixes, color in PREFIX_COLORS:
        if stripped.startswith(prefixes):
            return color
    return DEFAULT_COLOR


def notice_container(text: str, color: discord.Color | None = None, footer: str | None = None) -> ui.Container:
    """一段文字的通知 Container；footer 會以小字顯示在分隔線下方"""
    container = ui.Container(accent_color=color or pick_color(text))
    container.add_item(ui.TextDisplay(text))
    if footer:
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(f"-# {footer}"))
    return container


def notice_view(text: str, color: discord.Color | None = None, footer: str | None = None) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    view.add_item(notice_container(text, color, footer))
    return view


async def send_notice(
    interaction: discord.Interaction,
    text: str,
    color: discord.Color | None = None,
    footer: str | None = None,
    ephemeral: bool = True,
):
    """還沒回應過就用 response，已 defer / 回應過就用 followup"""
    view = notice_view(text, color, footer)
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(view=view, ephemeral=ephemeral)

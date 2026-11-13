"""
💸 轉帳畫面 (Components V2)：只負責把資料畫成畫面，不碰資料庫
"""
import discord
from discord import ui


def simple_container(text: str, color: discord.Color | None = None) -> ui.Container:
    container = ui.Container(accent_color=color or discord.Color.blurple())
    container.add_item(ui.TextDisplay(text))
    return container


def build_transfer_dm(sender_name: str, guild_name: str | None, amount: int, fee: int, test: bool = False) -> ui.Container:
    """轉帳收款人收到的私訊"""
    where = f"（來自伺服器 **{guild_name}**）" if guild_name else ""
    text = (
        f"## 💸 你收到一筆轉帳\n**{sender_name}** 轉給你 `{amount:,}` 賽錢{where}\n"
        f"扣掉手續費 `{fee:,}`，實收 **`{amount - fee:,}`** 賽錢"
    )
    if test:
        text += "\n-# 🧪 這是管理員發送的測試訊息，賽錢沒有實際變動"
    return simple_container(text, discord.Color.green())

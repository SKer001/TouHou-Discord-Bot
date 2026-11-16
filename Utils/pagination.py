"""
📄 共用分頁 (0.35.014 統整：原本卡冊、收藏冊、卡冊管理、道具管理、道具倉庫、市場、活動任務、稱號選單各寫一套)

用法 (View 自己存頁數，每次 build() 重組畫面)：
    page = paginate(self.cards, self.page, PER_PAGE)          # 頁數會被限制在 1 ~ 總頁數
    self.page = page.page
    ... 用 page.items 畫這一頁、page.start + 1 是這頁第一筆的編號 ...
    row = ui.ActionRow(*nav_buttons(page.page, page.total, self.set_page), 其他按鈕...)

    async def set_page(self, interaction, page):              # on_change：換頁後重組畫面
        self.page = page
        self.build()
        await interaction.response.edit_message(view=self)

按鈕樣式 (preset) 照各畫面原本的樣子，沒有統一：
    default  ◀️ 上一頁 / 📄 1 / 3 頁 / 下一頁 ▶️   藍色、到頭到尾反灰 (大部分畫面)
    compact  ◀️ / 1 / 3 / ▶️                       灰色、頭尾相接、只有一頁時反灰 (市場)
    simple   ◀ 上一頁 / 下一頁 ▶                   灰色、沒有頁碼、到頭到尾反灰 (活動任務)
    jump     ◀️ 上一頁 /  1 / 3  / 下一頁 ▶️       頭尾相接、按頁碼跳出輸入頁數的彈窗 (道具倉庫)
"""
from typing import Awaitable, Callable, NamedTuple

import discord
from discord import ui

from Utils.components import send_notice

OnChange = Callable[[discord.Interaction, int], Awaitable[None]]

PRESETS = {
    "default": {"prev": "◀️ 上一頁", "label": "📄 {page} / {total} 頁", "next": "下一頁 ▶️",
                "style": discord.ButtonStyle.primary, "wrap": False},
    "compact": {"prev": "◀️", "label": "{page} / {total}", "next": "▶️",
                "style": discord.ButtonStyle.secondary, "wrap": True, "lock_single": True},
    "simple":  {"prev": "◀ 上一頁", "label": None, "next": "下一頁 ▶",
                "style": discord.ButtonStyle.secondary, "wrap": False},
    "jump":    {"prev": "◀️ 上一頁", "label": " {page} / {total} ", "next": "下一頁 ▶️",
                "style": discord.ButtonStyle.primary, "wrap": True, "jump": True},
}


class Page(NamedTuple):
    items: list     # 這一頁的資料
    page: int       # 限制在範圍內的頁數 (1 起算)
    total: int      # 總頁數 (至少 1)
    start: int      # 這一頁第一筆在整個清單的位置 (0 起算)


def page_count(n: int, per_page: int) -> int:
    """n 筆資料要幾頁 (至少 1 頁)"""
    return max(1, (n + per_page - 1) // per_page)


def paginate(items: list, page: int, per_page: int) -> Page:
    total = page_count(len(items), per_page)
    page = min(max(1, page), total)
    start = (page - 1) * per_page
    return Page(items[start:start + per_page], page, total, start)


def step(page: int, delta: int, total: int, wrap: bool = False) -> int:
    """往前 / 往後翻 delta 頁：wrap = 頭尾相接 (第一頁按上一頁跳到最後一頁)，否則停在頭尾"""
    if wrap:
        return (page - 1 + delta) % max(1, total) + 1
    return min(max(1, page + delta), max(1, total))


class PageJumpModal(ui.Modal):
    """按頁碼跳出的彈窗：輸入頁數 ➔ on_change (頁數超出範圍由畫面自己限制)"""

    def __init__(self, title: str, total: int, on_change: OnChange):
        super().__init__(title=title)
        self.on_change = on_change
        self.page_input = ui.TextInput(label="請輸入要跳轉的頁數", style=discord.TextStyle.short,
                                       placeholder="例如: 1, 2, 3...", required=True, max_length=3)
        self.add_item(self.page_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_input.value)
        except ValueError:
            await send_notice(interaction, "❌ 請輸入有效的整數！")
            return
        await self.on_change(interaction, page)


def nav_buttons(page: int, total: int, on_change: OnChange, preset: str = "default",
                jump_title: str = "跳轉頁面") -> list[ui.Button]:
    """
    翻頁按鈕 [上一頁, 頁碼, 下一頁] (simple 沒有頁碼)；回傳 list，可以跟其他按鈕放同一排
    on_change(interaction, 新頁數)：畫面改頁數、重組、edit_message
    """
    p = PRESETS[preset]
    wrap = p["wrap"]
    if wrap:
        lock = p.get("lock_single", False) and total <= 1
        prev_off = next_off = lock
    else:
        prev_off, next_off = page <= 1, page >= total

    def go(delta: int):
        async def callback(interaction: discord.Interaction):
            await on_change(interaction, step(page, delta, total, wrap))
        return callback

    prev = ui.Button(label=p["prev"], style=p["style"], disabled=prev_off)
    prev.callback = go(-1)
    nxt = ui.Button(label=p["next"], style=p["style"], disabled=next_off)
    nxt.callback = go(1)
    if p["label"] is None:
        return [prev, nxt]

    label = ui.Button(label=p["label"].format(page=page, total=total), style=discord.ButtonStyle.secondary,
                      disabled=not p.get("jump"))
    if p.get("jump"):
        async def open_jump(interaction: discord.Interaction):
            await interaction.response.send_modal(PageJumpModal(jump_title, total, on_change))
        label.callback = open_jump
    return [prev, label, nxt]

"""
🌀 裏世界畫面共用的小工具：逾時 / 提示文字 / 每頁幾個、按鈕與選單的簡寫、box_rows (按鈕包進框裡)
(從 Cogs/load-ura/ura.py 拆出來；ura.py 會把這裡的名字全部轉出去)
"""
import discord
from discord import ui

VIEW_TIMEOUT = 840   # 14 分鐘：互動 token 只有 15 分鐘，逾時時還來得及把畫面改成「已收起來」
DENY = "❌ 這不是你的畫面"
STALE = "⌛ 這個畫面已經過期了，請用 `/ura resume` 接回"
STORAGE_PER_PAGE = 10
LIST_PER_PAGE = 25   # 會變長的選單 (背包、待撿、獻寶物、狐狸、整裝道具)：超過就翻頁

PRIMARY, SECONDARY = discord.ButtonStyle.primary, discord.ButtonStyle.secondary
SUCCESS, DANGER = discord.ButtonStyle.success, discord.ButtonStyle.danger


def _btn(label: str, style, callback, disabled: bool = False) -> ui.Button:
    b = ui.Button(label=label[:80], style=style, disabled=disabled)
    b.callback = callback
    return b


def _select(placeholder: str, options: list[discord.SelectOption], callback, max_values: int = 1,
            min_values: int = 1) -> ui.ActionRow:
    n = len(options[:25])
    s = ui.Select(placeholder=placeholder[:150], options=options[:25], max_values=min(max_values, n),
                  min_values=min(min_values, n))
    s.callback = callback
    return ui.ActionRow(s)


def box_rows(view: ui.LayoutView):
    """
    畫好之後把直接放在畫面上的按鈕排 / 選單移進最後一個框 (Container) 最下面，中間用 Separator 隔開
    (按鈕包在框裡；使用者 2026-11-21 grill 定，/ura 每個畫面 build() 最後都呼叫)
    """
    kids = list(view.children)
    boxes = [c for c in kids if isinstance(c, ui.Container)]
    rows = [c for c in kids if isinstance(c, ui.ActionRow)]
    if not boxes or not rows:
        return
    for r in rows:
        view.remove_item(r)
    boxes[-1].add_item(ui.Separator())
    for r in rows:
        boxes[-1].add_item(r)


def _opt(label: str, value: str, description: str | None = None, default: bool = False) -> discord.SelectOption:
    return discord.SelectOption(label=label[:100], value=value[:100], description=(description or None) and description[:100],
                                default=default)

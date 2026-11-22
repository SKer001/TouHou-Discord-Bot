"""
❓ /help：幻想鄉指南 (0.35.034 重做；0.36.000 分類頁改成📚 教學書)
- 總覽：每個分類一行 + 「📖 教學書」按鈕 ➔ 在同一則訊息翻開那本書 (GuideView，書裡有「🏠 回到總覽」)
- 📚 教學書：/card help、/shrine help、/ura help、/market help、/event help 也打得開 (open_guide，
  另開一則只有自己看得到的訊息，按「⛩️ 其他模式」換成 /help 總覽)；🪪 資料卡那本只能從 /help 進
- 管理員 (Utils.config.is_admin)：多一個「🛠️ 管理員指令表」(依 admin-user、admin-item… 分段，放不下自動分頁)；
  一般玩家看不到這頁，就算傳了管理員頁的 key 也會回到總覽
- 還沒分類的新指令在「📌 其他」，照舊是一頁指令表
指令說明與參數直接從 bot.tree 讀；分類在 Components/help_components.py，書的內容在 Components/guide/<分類>.py，
書的畫面在 Components/guide_components.py。
"""
import importlib

import discord
from discord import app_commands, ui
from discord.ext import commands

from Utils.config import is_admin


def help_components():
    return importlib.import_module("Cogs.load-general.Components.help_components")


def guide_components():
    return importlib.import_module("Cogs.load-general.Components.guide_components")


def book_chapter_counts() -> dict[str, int]:
    """有教學書的分類 ➔ 章數 (含最後的指令速查)"""
    gc = guide_components()
    return {key: len(gc.chapters(book)) for key in gc.BOOK_KEYS if (book := gc.load_book(key))}


class HelpView(ui.LayoutView):
    def __init__(self, bot: commands.Bot, page: str = "overview", admin: bool = False):
        super().__init__(timeout=600)
        self.bot = bot
        self.page = page
        self.admin = admin   # 只在 /help 指令開頭判斷一次；預設一般玩家
        self.build()

    def build(self):
        self.clear_items()
        hc = help_components()
        tree = self.bot.tree
        categories = hc.categorize(tree)
        books = book_chapter_counts()
        keys = hc.page_keys(tree, self.admin)
        if self.page != "overview" and (self.page not in keys or self.page in books):   # 一般玩家拿不到 admin 頁；書在 GuideView
            self.page = "overview"

        if self.page == "overview":
            admin_count = sum(len(cs) for cs in hc.walk_commands(tree, admin=True).values()) if self.admin else 0
            self.add_item(hc.build_overview_container(categories, self.admin, admin_count, on_open=self._opener, books=books))
            return
        if self.page.startswith("admin"):
            pages = hc.admin_pages(tree)
            index = int(self.page[5:])
            container = hc.build_admin_container(pages[index - 1], index, len(pages))
        else:
            container = hc.build_category_container(self.page, categories[self.page], hc.load_thumbnails())

        select = ui.Select(placeholder="📖 換一個分類…", options=[
            discord.SelectOption(label=title, value=key, default=key == self.page,
                                 description=(hc.category_info(key)["short"] if not key.startswith("admin")
                                              else "只有管理員看得到")[:100])
            for key, title in keys.items()
        ])
        select.callback = self.on_select
        back = ui.Button(label="🏠 回到總覽", style=discord.ButtonStyle.secondary)
        back.callback = self.on_back
        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(select))
        container.add_item(ui.ActionRow(back))
        self.add_item(container)

    def _opener(self, key: str):
        async def callback(interaction: discord.Interaction):
            await self.set_page(interaction, key)
        return callback

    async def set_page(self, interaction: discord.Interaction, page: str):
        if page in book_chapter_counts():   # 📚 有教學書的分類 ➔ 同一則訊息翻開那本書
            await interaction.response.edit_message(view=GuideView(self.bot, page, admin=self.admin, from_help=True))
            return
        self.page = page
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_select(self, interaction: discord.Interaction):
        await self.set_page(interaction, interaction.data["values"][0])

    async def on_back(self, interaction: discord.Interaction):
        await self.set_page(interaction, "overview")


class GuideView(ui.LayoutView):
    """
    📚 教學書：chapter 0 = 目錄，1～N = 第幾章 (最後一章是指令速查)
    from_help=True (從 /help 翻開) ➔「🏠 回到總覽」；False (/xxx help) ➔「⛩️ 其他模式」，兩個都換成 /help 總覽
    """

    def __init__(self, bot: commands.Bot, key: str, chapter: int = 0, *, admin: bool = False, from_help: bool = False):
        super().__init__(timeout=600)
        self.bot = bot
        self.key = key
        self.chapter = chapter
        self.admin = admin
        self.from_help = from_help
        self.build()

    def build(self):
        self.clear_items()
        gc = guide_components()
        hc = help_components()
        book = gc.load_book(self.key)
        chs = gc.chapters(book)
        self.chapter = max(0, min(self.chapter, len(chs)))
        home = ui.Button(label="🏠 回到總覽" if self.from_help else "⛩️ 其他模式", style=discord.ButtonStyle.secondary)
        home.callback = self.on_home

        if self.chapter == 0:
            buttons = []
            for i, ch in enumerate(chs, 1):
                btn = ui.Button(label=ch["title"][:80], style=discord.ButtonStyle.secondary)
                btn.callback = self._goto(i)
                buttons.append(btn)
            per = gc.CHAPTER_BUTTONS_PER_ROW
            rows = [ui.ActionRow(*buttons[i:i + per]) for i in range(0, len(buttons), per)]
            self.add_item(gc.build_cover_container(self.key, book, hc.load_thumbnails(), rows, ui.ActionRow(home)))
            return

        prev_btn = ui.Button(label="◀ 上一章", style=discord.ButtonStyle.secondary, disabled=self.chapter <= 1)
        prev_btn.callback = self._goto(self.chapter - 1)
        toc = ui.Button(label="📚 目錄", style=discord.ButtonStyle.primary)
        toc.callback = self._goto(0)
        next_btn = ui.Button(label="下一章 ▶", style=discord.ButtonStyle.secondary, disabled=self.chapter >= len(chs))
        next_btn.callback = self._goto(self.chapter + 1)
        jump = ui.Select(placeholder="📖 跳到其他章…", options=[
            discord.SelectOption(label=f"第 {i} 章　{ch['title']}"[:100], value=str(i), description=ch["short"][:100],
                                 default=i == self.chapter)
            for i, ch in enumerate(chs, 1)
        ])
        jump.callback = self.on_jump
        cmds = hc.categorize(self.bot.tree).get(self.key, [])
        rows = [ui.ActionRow(prev_btn, toc, next_btn, home), ui.ActionRow(jump)]
        self.add_item(gc.build_chapter_container(self.key, book, self.chapter, cmds, rows))

    def _goto(self, chapter: int):
        async def callback(interaction: discord.Interaction):
            await self.set_chapter(interaction, chapter)
        return callback

    async def set_chapter(self, interaction: discord.Interaction, chapter: int):
        self.chapter = chapter
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_jump(self, interaction: discord.Interaction):
        await self.set_chapter(interaction, int(interaction.data["values"][0]))

    async def on_home(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=HelpView(self.bot, admin=self.admin))


async def open_guide(interaction: discord.Interaction, key: str):
    """/card help、/ura help…：另開一則只有自己看得到的教學書 (目錄頁)"""
    view = GuideView(interaction.client, key, admin=is_admin(interaction.user), from_help=False)
    await interaction.response.send_message(view=view, ephemeral=True)


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="❓ 幻想鄉指南：每個模式的教學書 (玩法與指令)")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.send_message(view=HelpView(self.bot, admin=is_admin(interaction.user)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))

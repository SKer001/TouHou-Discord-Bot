"""
❓ /help：幻想鄉指南 (0.35.034 重做)
- 一般玩家：總覽 + 各分類頁 (玩法說明和指令在同一頁)
- 管理員 (Utils.config.is_admin)：多一個「🛠️ 管理員指令表」(依 admin-user、admin-item… 分段，放不下自動分頁)；
  一般玩家看不到這頁，就算傳了管理員頁的 key 也會回到總覽
指令說明與參數直接從 bot.tree 讀，分類、玩法說明、管理員群組標題在 Components/help_components.py。
"""
import importlib

import discord
from discord import app_commands, ui
from discord.ext import commands

from Utils.config import is_admin


def help_components():
    return importlib.import_module("Cogs.load-general.Components.help_components")


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
        keys = hc.page_keys(tree, self.admin)
        if self.page != "overview" and self.page not in keys:   # 一般玩家拿不到 admin 頁
            self.page = "overview"

        if self.page == "overview":
            admin_count = sum(len(cs) for cs in hc.walk_commands(tree, admin=True).values()) if self.admin else 0
            self.add_item(hc.build_overview_container(categories, self.admin, admin_count, on_open=self._opener))
        elif self.page.startswith("admin"):
            pages = hc.admin_pages(tree)
            index = int(self.page[5:])
            self.add_item(hc.build_admin_container(pages[index - 1], index, len(pages)))
        else:
            self.add_item(hc.build_category_container(self.page, categories[self.page], hc.load_thumbnails()))

        if self.page != "overview":
            select = ui.Select(placeholder="📖 換一個分類…", options=[
                discord.SelectOption(label=title, value=key, default=key == self.page,
                                     description=(hc.category_info(key)["short"] if not key.startswith("admin")
                                                  else "只有管理員看得到")[:100])
                for key, title in keys.items()
            ])
            select.callback = self.on_select
            self.add_item(ui.ActionRow(select))
            back = ui.Button(label="🏠 回到總覽", style=discord.ButtonStyle.secondary)
            back.callback = self.on_back
            self.add_item(ui.ActionRow(back))

    def _opener(self, key: str):
        async def callback(interaction: discord.Interaction):
            await self.set_page(interaction, key)
        return callback

    async def set_page(self, interaction: discord.Interaction, page: str):
        self.page = page
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_select(self, interaction: discord.Interaction):
        await self.set_page(interaction, interaction.data["values"][0])

    async def on_back(self, interaction: discord.Interaction):
        await self.set_page(interaction, "overview")


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="❓ 幻想鄉指南：每個分類的玩法說明與指令")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.send_message(view=HelpView(self.bot, admin=is_admin(interaction.user)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))

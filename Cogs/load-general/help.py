"""
❓ /help：依分類介紹所有指令 (不含管理員指令)
指令說明與參數直接從 bot.tree 讀，分類與玩法說明在 Components/help_components.py 的 CATEGORIES。
"""
import importlib

import discord
from discord import app_commands, ui
from discord.ext import commands


def help_components():
    return importlib.import_module("Cogs.load-general.Components.help_components")


class HelpView(ui.LayoutView):
    def __init__(self, bot: commands.Bot, page: str = "overview"):
        super().__init__(timeout=600)
        self.bot = bot
        self.page = page
        self.build()

    def build(self):
        self.clear_items()
        hc = help_components()
        categories = hc.categorize(self.bot.tree)
        if self.page not in categories:
            self.page = "overview"
        if self.page == "overview":
            self.add_item(hc.build_overview_container(categories))
        else:
            self.add_item(hc.build_category_container(self.page, categories[self.page]))

        select = ui.Select(placeholder="📖 選擇分類…", options=[
            discord.SelectOption(label=hc.category_info(key)[0], value=key, description=hc.category_info(key)[1][:100],
                                 default=key == self.page)
            for key in categories
        ])
        select.callback = self.on_select
        self.add_item(ui.ActionRow(select))
        if self.page != "overview":
            back = ui.Button(label="🏠 總覽", style=discord.ButtonStyle.secondary)
            back.callback = self.on_back
            self.add_item(ui.ActionRow(back))

    async def on_select(self, interaction: discord.Interaction):
        self.page = interaction.data["values"][0]
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_back(self, interaction: discord.Interaction):
        self.page = "overview"
        self.build()
        await interaction.response.edit_message(view=self)


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="❓ 指令說明：依分類介紹所有玩法與指令")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.send_message(view=HelpView(self.bot), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))

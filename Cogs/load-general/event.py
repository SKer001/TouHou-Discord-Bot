"""
🎪 /event：查看活動內容 (限定地點、限定料理與配方、限定客人、剩餘時間)
活動資料在 Events/<id>.json，狀態在 Database/Economy_DB_Manager.py
"""
import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Database.Item_DB_Manager import get_all_items
from Database.events import game_rules, load_events
from .Components.shrine_components import build_event_container


class EventCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="event", description="🎪 查看目前的活動：限定地點、限定料理、限定客人")
    async def event(self, interaction: discord.Interaction):
        overview = await econ.get_events_overview()
        overview.sort(key=lambda o: {"active": 0, "upcoming": 1, "ended": 2}[o["status"]])
        recipes = game_rules(list(load_events().values()))["recipes"]
        view = ui.LayoutView()
        view.add_item(build_event_container(overview, await get_all_items(), recipes))
        await interaction.response.send_message(view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventCog(bot))

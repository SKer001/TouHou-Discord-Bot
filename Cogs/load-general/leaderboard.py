import discord
from discord import ui
from discord import app_commands
from discord.ext import commands

from Database.User_DB_Manager import get_leaderboard_stats
from Utils.components import send_notice
from .Components.general_components import LEADERBOARD_TYPES, build_leaderboard_container


class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="🏆 本伺服器的排行榜 (只比較同伺服器、有遊玩紀錄的玩家)")
    @app_commands.describe(category="排行項目")
    @app_commands.choices(category=[app_commands.Choice(name=v[0], value=k) for k, v in LEADERBOARD_TYPES.items()])
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        guild = interaction.guild
        if guild is None:
            await send_notice(interaction, "❌ 排行榜只能在伺服器中使用。")
            return

        members = {m.id: m for m in guild.members if not m.bot}
        stats = await get_leaderboard_stats(list(members))
        _, field, _ = LEADERBOARD_TYPES[category.value]
        rows = sorted(stats, key=lambda r: (-r[field], r["user_id"]))
        for row in rows:
            row["member"] = members[row["user_id"]]

        view = ui.LayoutView()
        view.add_item(build_leaderboard_container(guild, category.value, rows, interaction.user.id))
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))

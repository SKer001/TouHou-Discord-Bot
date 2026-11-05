"""
🛠️ /admin-trade：發送「收到轉帳」的測試私訊 (賽錢不會變動)
"""
import importlib

import discord
from discord import app_commands
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Utils.config import is_admin
from Utils.components import send_notice


def market_mod():
    return importlib.import_module("Cogs.load-gacha.market")


class TradeAdmin(commands.GroupCog, group_name="admin-trade", group_description="【開發者專用】轉帳測試"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="test_dm", description="【開發者專用】讓指定玩家收到一則轉帳通知私訊 (測試用，賽錢不變)")
    @app_commands.describe(target="要收到私訊的玩家", amount="通知上的金額 (預設 1000)")
    async def test_dm(self, interaction: discord.Interaction, target: discord.User, amount: app_commands.Range[int, 1] = 1000):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return
        if target.bot:
            await send_notice(interaction, "❌ 不能私訊機器人。")
            return
        ok = await market_mod().send_transfer_dm(
            target, interaction.user.display_name, interaction.guild.name if interaction.guild else None,
            amount, econ.transfer_fee(amount), test=True,
        )
        if ok:
            await send_notice(interaction, f"✅ 已私訊 **{target.display_name}** 測試轉帳通知（`{amount:,}` 賽錢，賽錢沒有變動）。")
        else:
            await send_notice(interaction, f"⚠️ 私訊 **{target.display_name}** 失敗：對方可能關閉了伺服器成員私訊。")


async def setup(bot: commands.Bot):
    await bot.add_cog(TradeAdmin(bot))

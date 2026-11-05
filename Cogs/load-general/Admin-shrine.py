"""
🛠️ /admin-shrine：查看 / 調整指定玩家的神社 (測試用)
"""
import importlib

import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Database.Item_DB_Manager import get_all_items
from Utils.config import is_admin
from Utils.components import send_notice


def shrine_components():
    return importlib.import_module("Cogs.load-general.Components.shrine_components")


class ShrineAdmin(commands.GroupCog, group_name="admin-shrine", group_description="【開發者專用】神社狀態管理"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _deny(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return True
        return False

    async def _show(self, interaction: discord.Interaction, target: discord.abc.User, result: dict, notice: str):
        view = ui.LayoutView()
        view.add_item(shrine_components().build_shrine_container(target.display_name, result["summary"], notice, await get_all_items()))
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="view", description="【開發者專用】查看指定玩家的神社")
    @app_commands.describe(target="要查看的玩家")
    async def view(self, interaction: discord.Interaction, target: discord.User):
        if await self._deny(interaction):
            return
        await self._show(interaction, target, await econ.get_shrine(target.id), f"🛠️ [Dev] **{target.display_name}** 的神社")

    @app_commands.command(name="set", description="【開發者專用】調整神社狀態 (留空的項目不變)")
    @app_commands.describe(
        target="要調整的玩家",
        box=f"賽錢箱金額 (0 ~ {econ.SHRINE_BOX_MAX:,})",
        dirt=f"清潔度階段 (0 乾淨 ~ {econ.DIRT_MAX})，從現在開始重新計時",
        youkai=f"妖怪數 (0 ~ {econ.YOUKAI_MAX})",
        guests=f"參拜客人數 (0 ~ {econ.GUEST_MAX})，會取代現有的客人",
        guest_mood="參拜客心情 % (10 ~ 100，預設 100)",
    )
    async def set_state(
        self, interaction: discord.Interaction, target: discord.User,
        box: app_commands.Range[int, 0, econ.SHRINE_BOX_MAX] | None = None,
        dirt: app_commands.Range[int, 0, econ.DIRT_MAX] | None = None,
        youkai: app_commands.Range[int, 0, econ.YOUKAI_MAX] | None = None,
        guests: app_commands.Range[int, 0, econ.GUEST_MAX] | None = None,
        guest_mood: app_commands.Range[int, 10, 100] = 100,
    ):
        if await self._deny(interaction):
            return
        if box is None and dirt is None and youkai is None and guests is None:
            await send_notice(interaction, "⚠️ 沒有指定要調整的項目。")
            return
        r = await econ.admin_set_shrine(target.id, box=box, dirt=dirt, youkai=youkai, guests=guests, guest_mood=guest_mood)
        await self._show(interaction, target, r, f"🛠️ [Dev] 已調整 **{target.display_name}** 的神社")

    @app_commands.command(name="reset", description="【開發者專用】重置指定玩家的神社 (賽錢箱、妖怪、客人全部歸零)")
    @app_commands.describe(target="要重置的玩家")
    async def reset(self, interaction: discord.Interaction, target: discord.User):
        if await self._deny(interaction):
            return
        await econ.admin_reset_shrine(target.id)
        await self._show(interaction, target, await econ.get_shrine(target.id), f"🛠️ [Dev] 已重置 **{target.display_name}** 的神社")


async def setup(bot: commands.Bot):
    await bot.add_cog(ShrineAdmin(bot))

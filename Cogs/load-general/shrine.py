"""
⛩️ 神社經營 /shrine：賽錢箱定時進帳、清掃、治退妖怪、參拜客
數值與結算規則在 Database/Economy_DB_Manager.py
"""
import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Utils.components import send_notice
from .Components.shrine_components import build_shrine_container


class ShrineView(ui.LayoutView):
    """神社主畫面：回收賽錢箱 / 清掃 / 治退妖怪 / 招待 (未開放) / 重新整理"""

    def __init__(self, user: discord.abc.User, result: dict, notice: str | None = None):
        super().__init__(timeout=300)
        self.user = user
        self.build(result, notice)

    def build(self, result: dict, notice: str | None = None):
        s = result["summary"]
        self.clear_items()
        container = build_shrine_container(self.user.display_name, s, notice)
        container.add_item(ui.Separator())

        collect = ui.Button(label=f"💰 回收賽錢箱 ({s['box']:,})", style=discord.ButtonStyle.success, disabled=s["box"] < 1)
        collect.callback = self.on_collect
        clean = ui.Button(label="🧹 清掃", style=discord.ButtonStyle.primary, disabled=s["dirt"] == 0)
        clean.callback = self.on_clean
        defeat = ui.Button(label=f"⚔️ 治退妖怪 ({s['youkai']})", style=discord.ButtonStyle.danger, disabled=s["youkai"] == 0)
        defeat.callback = self.on_defeat
        serve = ui.Button(label="🍵 招待", style=discord.ButtonStyle.secondary, disabled=True)
        refresh = ui.Button(label="🔄", style=discord.ButtonStyle.secondary)
        refresh.callback = self.on_refresh
        container.add_item(ui.ActionRow(collect, clean, defeat, serve, refresh))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await send_notice(interaction, "❌ 這不是你的神社！用 `/shrine manage` 打開自己的神社吧。")
            return False
        return True

    async def _update(self, interaction: discord.Interaction, result: dict, notice: str | None):
        self.build(result, notice)
        await interaction.response.edit_message(view=self)

    async def on_collect(self, interaction: discord.Interaction):
        r = await econ.shrine_collect(self.user.id)
        notice = f"💰 回收了 `{r['collected']:,}` 賽錢！目前持有 `{r['money']:,}` 賽錢。" if r["collected"] else "⚠️ 賽錢箱裡還沒有錢。"
        await self._update(interaction, r, notice)

    async def on_clean(self, interaction: discord.Interaction):
        r = await econ.shrine_clean(self.user.id)
        notice = "✨ 神社打掃得一塵不染！" if r["before"] else "✨ 神社本來就很乾淨。"
        await self._update(interaction, r, notice)

    async def on_defeat(self, interaction: discord.Interaction):
        r = await econ.shrine_defeat(self.user.id)
        if r["ok"]:
            notice = f"⚔️ 打退了一隻妖怪！獲得 `{r['reward']:,}` 賽錢。\n-# 妖怪留下了晦氣，清潔度掉了一階…"
        else:
            notice = "⚠️ 現在沒有妖怪在作亂。"
        await self._update(interaction, r, notice)

    async def on_refresh(self, interaction: discord.Interaction):
        await self._update(interaction, await econ.get_shrine(self.user.id), None)


class ShrineCog(commands.GroupCog, group_name="shrine", group_description="⛩️ 神社經營"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="manage", description="⛩️ 打開自己的神社：賽錢箱、清掃、治退妖怪、參拜客")
    async def manage(self, interaction: discord.Interaction):
        result = await econ.get_shrine(interaction.user.id)
        await interaction.response.send_message(view=ShrineView(interaction.user, result), ephemeral=True)

    @app_commands.command(name="collect", description="💰 回收神社賽錢箱裡的賽錢")
    async def collect(self, interaction: discord.Interaction):
        r = await econ.shrine_collect(interaction.user.id)
        notice = f"💰 回收了 `{r['collected']:,}` 賽錢！目前持有 `{r['money']:,}` 賽錢。" if r["collected"] else "⚠️ 賽錢箱裡還沒有錢。"
        await interaction.response.send_message(view=ShrineView(interaction.user, r, notice), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShrineCog(bot))

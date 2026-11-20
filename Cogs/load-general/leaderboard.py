"""
🏆 /leaderboard：本伺服器的排行榜 (公開訊息)
- 選單切換項目、◀️ ▶️ 翻頁、📍 跳到我的名次 (0.35.086；規格在 docs/ura.md「排行榜」)
- 條列式：每位玩家一塊「名次 名字 · 稱號」+ 那一項的數字；🌀 裏世界兩項多列角色 (倒下 💀) 和法具
- 一頁 10 名 (裏世界兩項 5 名)；只有打指令的人能操作
"""
import discord
from discord import ui
from discord import app_commands
from discord.ext import commands

from Database.User_DB_Manager import get_leaderboard_stats, get_title_state
from Database.Economy_DB_Manager import get_card_values
from Database import Ura_DB_Manager as ura
from Utils.components import send_notice
from Utils.pagination import nav_buttons, paginate
from .Components.general_components import (
    LEADERBOARD_TYPES, URA_TYPES, build_leaderboard_container, leaderboard_per_page,
)

DEFAULT_TYPE = "money"


async def leaderboard_rows(guild, type_key: str) -> list[dict]:
    """這個伺服器 (排除機器人) 在這一項的排名 (高到低)；每筆含 "member"，裏世界兩項含 "ura" (那一筆紀錄)"""
    members = {m.id: m for m in guild.members if not m.bot}
    stats = await get_leaderboard_stats(list(members))
    _, field, _ = LEADERBOARD_TYPES[type_key]
    if type_key == "assets":   # 資產總值 = 賽錢 + 卡牌市值 (含上架中的卡)
        values = await get_card_values([r["user_id"] for r in stats])
        for r in stats:
            r["assets"] = r["money"] + values.get(r["user_id"], 0)
    if type_key in URA_TYPES:   # 只有成功撤離過的上榜；同分 ➔ 先達成的在前
        records = await ura.get_leaderboard_records([r["user_id"] for r in stats])
        key = "money" if type_key == "ura_money" else "depth"
        rows = []
        for r in stats:
            rec = records.get(r["user_id"], {}).get(key)
            if rec:
                rows.append({**r, "ura": rec, field: rec["value"]})
        rows.sort(key=lambda r: (-r[field], r["ura"]["at"], r["user_id"]))
    else:
        rows = sorted(stats, key=lambda r: (-r[field], r["user_id"]))
    for row in rows:
        row["member"] = members[row["user_id"]]
    return rows


class LeaderboardView(ui.LayoutView):
    def __init__(self, owner_id: int, guild, type_key: str):
        super().__init__(timeout=600)
        self.owner_id, self.guild = owner_id, guild
        self.type_key, self.page = type_key, 1
        self.rows: list[dict] = []
        self.titles: dict[int, str | None] = {}   # 戴著的稱號 (只查顯示到的人；get_title_state 會檢查還符不符合條件)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await send_notice(interaction, "❌ 這不是你的排行榜，自己打 `/leaderboard` 看看吧")
            return False
        return True

    async def load(self):
        self.rows = await leaderboard_rows(self.guild, self.type_key)

    def my_rank(self) -> int | None:
        return next((i for i, r in enumerate(self.rows, start=1) if r["user_id"] == self.owner_id), None)

    async def build(self):
        self.clear_items()
        per = leaderboard_per_page(self.type_key)
        page = paginate(self.rows, self.page, per)
        self.page = page.page
        for row in page.items:
            uid = row["user_id"]
            if uid not in self.titles:
                self.titles[uid] = (await get_title_state(uid))["equipped"]
            row["title"] = self.titles[uid]
        self.add_item(build_leaderboard_container(self.guild, self.type_key, self.rows, page, self.owner_id))

        sel = ui.Select(placeholder="🏆 換一個排行項目", options=[
            discord.SelectOption(label=name, value=key, default=key == self.type_key) for key, (name, _, _) in LEADERBOARD_TYPES.items()])
        sel.callback = self.on_type
        self.add_item(ui.ActionRow(sel))
        mine = ui.Button(label="📍 跳到我的名次", style=discord.ButtonStyle.secondary, disabled=self.my_rank() is None)
        mine.callback = self.on_mine
        self.add_item(ui.ActionRow(*nav_buttons(page.page, page.total, self.set_page), mine))

    async def redraw(self, interaction: discord.Interaction):
        await self.build()
        await interaction.response.edit_message(view=self)

    async def set_page(self, interaction: discord.Interaction, page: int):
        self.page = page
        await self.redraw(interaction)

    async def on_type(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        if value in LEADERBOARD_TYPES:
            self.type_key, self.page = value, 1
            await self.load()
        await self.redraw(interaction)

    async def on_mine(self, interaction: discord.Interaction):
        rank = self.my_rank()
        if rank:
            self.page = (rank - 1) // leaderboard_per_page(self.type_key) + 1
        await self.redraw(interaction)


class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="🏆 本伺服器的排行榜 (只比較同伺服器、有遊玩紀錄的玩家)")
    @app_commands.describe(category="排行項目 (不填 = 💰 賽錢；打開後也可以用選單切換)")
    @app_commands.choices(category=[app_commands.Choice(name=v[0], value=k) for k, v in LEADERBOARD_TYPES.items()])
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction, category: app_commands.Choice[str] | None = None):
        guild = interaction.guild
        if guild is None:
            await send_notice(interaction, "❌ 排行榜只能在伺服器中使用。")
            return
        type_key = category.value if category and category.value in LEADERBOARD_TYPES else DEFAULT_TYPE
        view = LeaderboardView(interaction.user.id, guild, type_key)
        await view.load()
        await view.build()
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))

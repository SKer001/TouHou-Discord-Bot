"""
⛩️ 神社經營 /shrine：賽錢箱定時進帳、清掃、治退妖怪、參拜客；/shrine storage 神社倉庫 (道具)
數值與結算規則在 Database/Economy_DB_Manager.py
"""
import json

import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Database.User_DB_Manager import get_or_create_user
from Database.Item_DB_Manager import get_all_items
from Utils.components import send_notice
from .Components.shrine_components import build_shrine_container
from .Components.general_components import get_inventory_view_data, build_inventory_container


# =========================================================
# 📦 神社倉庫 (原本的 /inventory，v0.26.000 搬到 /shrine storage)
# =========================================================
# 分類選單：(value, 名稱, emoji, 說明)
CATEGORY_OPTIONS = [
    ("all", "全部道具", "🌸", "顯示倉庫內所有道具"),
    ("consumable", "消耗品 / 食物", "🍵", "可以使用的日常消耗品"),
    ("collectible", "符卡 / 收藏品", "🎴", "具有特殊意義的收藏"),
    ("special", "特殊 / 裝備", "🛠️", "關鍵道具或強化裝備"),
    ("cuisine", "招待料理", "🍱", "招待參拜客用的食物 / 茶水 / 點心"),
]


# ---------------------------------------------------------
# 🪟 跳轉頁數彈窗 (Modal)
# ---------------------------------------------------------
class PageJumpModal(ui.Modal, title='跳轉倉庫頁面'):
    def __init__(self, view_ref: "InventoryView"):
        super().__init__()
        self.view_ref = view_ref

    page_input = ui.TextInput(
        label='請輸入要跳轉的頁數',
        style=discord.TextStyle.short,
        placeholder='例如: 1, 2, 3...',
        required=True,
        max_length=3
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.view_ref.current_page = int(self.page_input.value)
        except ValueError:
            await send_notice(interaction, "❌ 請輸入有效的整數！")
            return
        await self.view_ref.update_message(interaction)


# ---------------------------------------------------------
# 🕹️ 背包互動 UI 控制器 (Components V2 LayoutView)
# ---------------------------------------------------------
class InventoryView(ui.LayoutView):
    def __init__(self, invoker_id: int, user: discord.User, inventory: dict, item_templates: dict, color: discord.Color):
        super().__init__(timeout=120)
        self.invoker_id = invoker_id
        self.user = user
        self.inventory = inventory
        self.item_templates = item_templates
        self.color = color
        self.category = "all"
        self.current_page = 1
        self.total_pages = 1
        self.message = None  # 送出後由指令填入，供逾時時停用按鈕

        self.build()

    def build(self):
        """依目前的分類與頁數，重新組出整個畫面 (資料只算一次)"""
        data = get_inventory_view_data(self.inventory, self.item_templates, self.category, self.current_page)
        self.current_page = data["page"]
        self.total_pages = data["total_pages"]

        container = build_inventory_container(self.user, data, self.category, self.color)
        container.add_item(ui.Separator())

        # 分類選單 (顯示各分類的道具種類數)
        counts = data["category_counts"]
        self.select_category = ui.Select(
            placeholder="🌸 選擇道具分類...",
            options=[
                discord.SelectOption(
                    label=label, value=value, emoji=emoji,
                    description=f"{desc} · {counts.get(value, 0)} 種",
                    default=(value == self.category),
                )
                for value, label, emoji, desc in CATEGORY_OPTIONS
            ],
        )
        self.select_category.callback = self.on_select_category

        # 翻頁按鈕 (中間的頁碼按鈕可點擊跳頁)
        self.btn_prev = ui.Button(label="◀️ 上一頁", style=discord.ButtonStyle.primary)
        self.btn_prev.callback = self.on_prev
        self.btn_page = ui.Button(label=f" {self.current_page} / {self.total_pages} ", style=discord.ButtonStyle.secondary)
        self.btn_page.callback = self.on_page
        self.btn_next = ui.Button(label="下一頁 ▶️", style=discord.ButtonStyle.primary)
        self.btn_next.callback = self.on_next

        container.add_item(ui.ActionRow(self.select_category))
        container.add_item(ui.ActionRow(self.btn_prev, self.btn_page, self.btn_next))

        self.clear_items()
        self.add_item(container)

    async def update_message(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await send_notice(interaction, "❌ 只有該指令的使用者才能操作此選單！")
            return False
        return True

    async def on_timeout(self):
        """逾時後把選單與按鈕反灰，避免使用者點到沒反應的控制項"""
        for item in (self.select_category, self.btn_prev, self.btn_page, self.btn_next):
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_select_category(self, interaction: discord.Interaction):
        self.category = interaction.data["values"][0]
        self.current_page = 1
        await self.update_message(interaction)

    async def on_prev(self, interaction: discord.Interaction):
        self.current_page = self.current_page - 1 if self.current_page > 1 else self.total_pages
        await self.update_message(interaction)

    async def on_page(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PageJumpModal(self))

    async def on_next(self, interaction: discord.Interaction):
        self.current_page = self.current_page + 1 if self.current_page < self.total_pages else 1
        await self.update_message(interaction)




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


class ShrineCog(commands.GroupCog, group_name="shrine", group_description="⛩️ 神社經營與神社倉庫"):
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


    @app_commands.command(name="storage", description="📦 檢視自己或他人的神社倉庫 (道具)")
    @app_commands.describe(target="要檢視的成員 (留空則檢視自己)")
    async def storage(self, interaction: discord.Interaction, target: discord.User = None):
        await interaction.response.defer(ephemeral=True)
        target_user = target or interaction.user
        user_data = await get_or_create_user(target_user.id)
        if target and not bool(user_data.get("is_public", 1)) and target.id != interaction.user.id:
            await send_notice(interaction, f"🔒 **{target_user.display_name}** 已設定個人卡片為私密，無法檢視其神社倉庫！")
            return

        raw_inv = user_data.get("inventory", "{}")
        if isinstance(raw_inv, str):
            try:
                inventory = json.loads(raw_inv)
            except json.JSONDecodeError:
                inventory = {}
        else:
            inventory = raw_inv or {}
        item_templates = await get_all_items()
        color = getattr(target_user, "color", discord.Color.default())
        accent_color = color if color != discord.Color.default() else discord.Color.dark_theme()
        view = InventoryView(interaction.user.id, target_user, inventory, item_templates, accent_color)
        view.message = await interaction.followup.send(view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShrineCog(bot))

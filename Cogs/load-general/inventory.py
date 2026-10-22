import discord
import json
from discord import app_commands, ui
from discord.ext import commands
from Database.User_DB_Manager import get_or_create_user
from Database.Item_DB_Manager import get_all_items
from .Embeds.general_embeds import get_inventory_view_data, build_inventory_container

# 分類選單：(value, 名稱, emoji, 說明)
CATEGORY_OPTIONS = [
    ("all", "全部道具", "🌸", "顯示背包內所有道具"),
    ("consumable", "消耗品 / 食物", "🍵", "可以使用的日常消耗品"),
    ("collectible", "符卡 / 收藏品", "🎴", "具有特殊意義的收藏"),
    ("special", "特殊 / 裝備", "🛠️", "關鍵道具或強化裝備"),
]


# ---------------------------------------------------------
# 🪟 跳轉頁數彈窗 (Modal)
# ---------------------------------------------------------
class PageJumpModal(ui.Modal, title='跳轉背包頁面'):
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
            await interaction.response.send_message("❌ 請輸入有效的整數！", ephemeral=True)
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
            await interaction.response.send_message("❌ 只有該指令的使用者才能操作此選單！", ephemeral=True)
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


# ---------------------------------------------------------
# 📦 Inventory Cog
# ---------------------------------------------------------
class InventoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="inventory", description="檢視自己或他人的背包道具")
    @app_commands.describe(target="要檢視的成員 (留空則檢視自己)")
    async def inventory_cmd(self, interaction: discord.Interaction, target: discord.User = None):
        await interaction.response.defer()

        target_user = target or interaction.user
        user_data = await get_or_create_user(target_user.id)

        is_public = bool(user_data.get("is_public", 1))
        if target and not is_public and target.id != interaction.user.id:
            await interaction.followup.send(f"🔒 **{target_user.display_name}** 已設定個人卡片為私密，無法檢視其背包！", ephemeral=True)
            return

        # 讀取 JSON 背包
        raw_inv = user_data.get("inventory", "{}")
        if isinstance(raw_inv, str):
            try:
                inventory = json.loads(raw_inv)
            except json.JSONDecodeError:
                inventory = {}
        else:
            inventory = raw_inv if raw_inv else {}

        # 向 SQLite 查詢所有的道具設定檔
        item_templates = await get_all_items()

        embed_color = target_user.color if target_user.color != discord.Color.default() else discord.Color.dark_theme()

        view = InventoryView(interaction.user.id, target_user, inventory, item_templates, embed_color)
        view.message = await interaction.followup.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCog(bot))
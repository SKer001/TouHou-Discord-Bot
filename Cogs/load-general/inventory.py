import discord
import json
from discord import app_commands
from discord.ext import commands
from Database.db_manager import get_or_create_user
from Utils.embed_builder import build_inventory_embed


# ---------------------------------------------------------
# 🪟 跳轉頁數彈窗 (Modal)
# ---------------------------------------------------------
class PageJumpModal(discord.ui.Modal, title='跳轉背包頁面'):
    def __init__(self, view_ref):
        super().__init__()
        self.view_ref = view_ref

    page_input = discord.ui.TextInput(
        label='請輸入要跳轉的頁數',
        style=discord.TextStyle.short,
        placeholder='例如: 1, 2, 3...',
        required=True,
        max_length=3
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_page = int(self.page_input.value)
            self.view_ref.current_page = target_page
            await self.view_ref.update_message(interaction)
        except ValueError:
            await interaction.response.send_message("❌ 請輸入有效的整數！", ephemeral=True)


# ---------------------------------------------------------
# 🕹️ 背包互動 UI 控制器 (View)
# ---------------------------------------------------------
class InventoryView(discord.ui.View):
    def __init__(self, invoker_id: int, user: discord.User, inventory: dict, color: discord.Color):
        super().__init__(timeout=120)  # 選單 2 分鐘後逾時
        self.invoker_id = invoker_id
        self.user = user
        self.inventory = inventory
        self.color = color
        self.current_page = 1
        self.category = "all"
        self.total_pages = 1

        self.update_components()

    def update_components(self):
        # 預渲染一次以取得正確的總頁數
        _, self.total_pages = build_inventory_embed(
            self.user, self.inventory, self.category, self.current_page, self.color
        )
        # 防呆修正是界線
        self.current_page = max(1, min(self.current_page, self.total_pages))
        self.btn_page.label = f" {self.current_page} / {self.total_pages} "

    async def update_message(self, interaction: discord.Interaction):
        self.update_components()
        embed, _ = build_inventory_embed(
            self.user, self.inventory, self.category, self.current_page, self.color
        )
        await interaction.response.edit_message(embed=embed, view=self)

    # 確保只有指令使用者能按按鈕
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("❌ 只有該指令的使用者才能操作此選單！", ephemeral=True)
            return False
        return True

    # --- 下拉選單 (分類切換) ---
    @discord.ui.select(
        placeholder="🌸 選擇道具分類...",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="全部道具", value="all", emoji="🌸", description="顯示背包內所有道具"),
            discord.SelectOption(label="消耗品 / 食物", value="consumable", emoji="🍵", description="可以使用的日常消耗品"),
            discord.SelectOption(label="符卡 / 收藏品", value="collectible", emoji="🎴", description="具有特殊意義的收藏"),
            discord.SelectOption(label="特殊 / 裝備", value="special", emoji="🛠️", description="關鍵道具或強化裝備")
        ]
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.category = select.values[0]
        self.current_page = 1  # 切換分類強制回到第 1 頁
        
        # 更新下拉選單的預設顯示選項
        for opt in select.options:
            opt.default = (opt.value == self.category)
            
        await self.update_message(interaction)

    # --- 左翻頁按鈕 ---
    @discord.ui.button(label="◀️ 上一頁", style=discord.ButtonStyle.primary, row=1)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        if self.current_page < 1:
            self.current_page = self.total_pages  # 循環到最後一頁
        await self.update_message(interaction)

    # --- 當前頁數 (點擊跳轉) ---
    @discord.ui.button(label=" 1 / 1 ", style=discord.ButtonStyle.secondary, row=1)
    async def btn_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PageJumpModal(self)
        await interaction.response.send_modal(modal)

    # --- 右翻頁按鈕 ---
    @discord.ui.button(label="下一頁 ▶️", style=discord.ButtonStyle.primary, row=1)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        if self.current_page > self.total_pages:
            self.current_page = 1  # 循環到第一頁
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
        
        # 隱私權限檢查 (非本人 且 設定為不公開)
        is_public = bool(user_data.get("is_public", 1))
        if target and not is_public and target.id != interaction.user.id:
            await interaction.followup.send(f"🔒 **{target_user.display_name}** 已設定個人卡片為私密，無法檢視其背包！", ephemeral=True)
            return

        # 讀取並轉換資料庫的 JSON 庫存字串
        raw_inv = user_data.get("inventory", "{}")
        if isinstance(raw_inv, str):
            try:
                inventory = json.loads(raw_inv)
            except:
                inventory = {}
        else:
            inventory = raw_inv if raw_inv else {}

        # 這裡為了簡化載入，使用 Discord 原生抓取用戶的主題色
        embed_color = target_user.color if target_user.color != discord.Color.default() else discord.Color.dark_theme()

        # 初始化 View 與 Embed
        view = InventoryView(interaction.user.id, target_user, inventory, embed_color)
        embed, _ = build_inventory_embed(target_user, inventory, "all", 1, embed_color)
        
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCog(bot))
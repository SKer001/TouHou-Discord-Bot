import os
import json
import random
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from Database.db_manager import get_or_create_user, update_user_inventory
from Utils.item_data import (
    get_all_items, get_item, add_item_db, 
    update_item_db, delete_item_db, batch_import_db, CATEGORY_NAMES
)

ADMIN_ID = 403895664666214400
MAIN_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "Database", "database.db")


# ---------------------------------------------------------
# 🛠️ 內部資料庫輔助函式：更新玩家背包
# ---------------------------------------------------------
async def save_user_inventory(user_id: int, inventory: dict):
    async with aiosqlite.connect(MAIN_DB_PATH) as db:
        await db.execute(
            "UPDATE users SET inventory = ? WHERE user_id = ?",
            (json.dumps(inventory, ensure_ascii=False), user_id)
        )
        await db.commit()


# ---------------------------------------------------------
# 🪟 UI 元件
# ---------------------------------------------------------
class ItemEditModal(discord.ui.Modal, title="✏️ 編輯道具詳細資料"):
    def __init__(self, view_ref, item_data: dict):
        super().__init__()
        self.view_ref = view_ref
        self.item_data = item_data

        self.name_input = discord.ui.TextInput(
            label="道具名稱", style=discord.TextStyle.short, default=item_data["name"], required=True
        )
        self.emoji_input = discord.ui.TextInput(
            label="道具圖示 (Emoji)", style=discord.TextStyle.short, default=item_data["emoji"], required=True, max_length=10
        )
        self.desc_input = discord.ui.TextInput(
            label="道具描述 (背景故事/效果)", style=discord.TextStyle.paragraph, default=item_data["desc"], required=True
        )

        self.add_item(self.name_input)
        self.add_item(self.emoji_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        await update_item_db(
            self.item_data["item_id"],
            self.name_input.value,
            self.emoji_input.value,
            self.item_data["category"],
            self.desc_input.value
        )
        self.view_ref.item_data["name"] = self.name_input.value
        self.view_ref.item_data["emoji"] = self.emoji_input.value
        self.view_ref.item_data["desc"] = self.desc_input.value

        await self.view_ref.update_message(interaction, "✅ 道具資料已成功更新！")


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__(timeout=60)
        self.parent_view = parent_view

    @discord.ui.button(label="✔️ 確定刪除", style=discord.ButtonStyle.danger)
    async def btn_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await delete_item_db(self.parent_view.item_data["item_id"])
        embed = discord.Embed(
            title="🗑️ 道具已刪除",
            description=f"已成功從資料庫中移除 `{self.parent_view.item_data['item_id']}`！",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.secondary)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.parent_view.update_message(interaction, "↩️ 已取消刪除操作。")


class ItemEditView(discord.ui.View):
    def __init__(self, item_data: dict):
        super().__init__(timeout=300)
        self.item_data = item_data
        self.update_category_select()

    def update_category_select(self):
        for opt in self.select_category.options:
            opt.default = (opt.value == self.item_data["category"])

    async def update_message(self, interaction: discord.Interaction, notice: str = None):
        self.update_category_select()
        embed = discord.Embed(title=f"🛠️ 編輯道具：{self.item_data['item_id']}", color=discord.Color.orange())
        embed.add_field(name="名稱", value=f"{self.item_data['emoji']} {self.item_data['name']}", inline=True)
        embed.add_field(name="分類", value=CATEGORY_NAMES.get(self.item_data["category"], "未知"), inline=True)
        embed.add_field(name="描述", value=self.item_data["desc"], inline=False)
        if notice:
            embed.set_footer(text=notice)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.select(
        placeholder="更換分類...", row=0,
        options=[
            discord.SelectOption(label="🍵 消耗品", value="consumable"),
            discord.SelectOption(label="🎴 收藏品", value="collectible"),
            discord.SelectOption(label="🛠️ 裝備與特殊", value="special")
        ]
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        new_category = select.values[0]
        self.item_data["category"] = new_category
        await update_item_db(
            self.item_data["item_id"], self.item_data["name"], 
            self.item_data["emoji"], new_category, self.item_data["desc"]
        )
        await self.update_message(interaction, f"✅ 分類已更改為：{CATEGORY_NAMES[new_category]}")

    @discord.ui.button(label="✏️ 編輯詳細資料", style=discord.ButtonStyle.primary, row=1)
    async def btn_edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ItemEditModal(self, self.item_data))

    @discord.ui.button(label="🗑️ 刪除物品", style=discord.ButtonStyle.danger, row=1)
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="⚠️ 刪除確認",
            description=f"確定要永久刪除道具 **{self.item_data['name']}** (`{self.item_data['item_id']}`) 嗎？\n*(玩家背包內的該道具將會變成無效資料)*",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=ConfirmDeleteView(self))


# ---------------------------------------------------------
# 🤖 ItemAdmin Cog
# ---------------------------------------------------------
class ItemAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        items = await get_all_items()
        choices = []
        for item_id, data in items.items():
            if current.lower() in item_id.lower() or current.lower() in data['name'].lower():
                choices.append(app_commands.Choice(name=f"{data['emoji']} {item_id} ({data['name']})", value=item_id))
        return choices[:25]

    # 1. 📦 /add_item 新增單個道具
    @app_commands.command(name="add_item", description="【開發者專用】新增單一道具")
    @app_commands.describe(item_id="道具的英文唯一 ID", name="道具中文名稱", emoji="道具圖示 (Emoji)", category="所屬分類", desc="道具詳細描述")
    @app_commands.choices(category=[
        app_commands.Choice(name="🍵 消耗品", value="consumable"),
        app_commands.Choice(name="🎴 收藏品", value="collectible"),
        app_commands.Choice(name="🛠️ 裝備與特殊", value="special")
    ])
    @app_commands.default_permissions(administrator=True)
    async def add_item_cmd(self, interaction: discord.Interaction, item_id: str, name: str, emoji: str, category: app_commands.Choice[str], desc: str):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 無權限", ephemeral=True)
            return
            
        success = await add_item_db(item_id, name, emoji, category.value, desc)
        if success:
            await interaction.response.send_message(f"✅ 成功新增道具：{emoji} **{name}** (`{item_id}`)", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ 新增失敗！道具 ID `{item_id}` 已存在。", ephemeral=True)

    # 2. 📦 /add_items_batch 批量上傳
    @app_commands.command(name="add_items_batch", description="【開發者專用】上傳 JSON 檔案批量新增/覆寫道具")
    @app_commands.describe(file="包含道具資料的 .json 檔案", overwrite="若道具已存在，是否要覆蓋舊資料？ (預設為 False)")
    @app_commands.default_permissions(administrator=True)
    async def add_items_batch_cmd(self, interaction: discord.Interaction, file: discord.Attachment, overwrite: bool = False):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 無權限", ephemeral=True)
            return

        if not file.filename.endswith(".json"):
            await interaction.response.send_message("❌ 請上傳 `.json` 格式的檔案！", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            content = await file.read()
            items_dict = json.loads(content.decode('utf-8'))
            
            success, skipped = await batch_import_db(items_dict, overwrite)
            await interaction.followup.send(f"✅ 批量匯入完成！\n成功新增/更新：`{success}` 件\n略過(重複)：`{skipped}` 件")
        except Exception as e:
            await interaction.followup.send(f"❌ JSON 解析失敗，請檢查檔案格式！\n```py\n{e}\n```")

    # 3. 📦 /edit_item 編輯控制台
    @app_commands.command(name="edit_item", description="【開發者專用】開啟道具編輯控制台")
    @app_commands.autocomplete(item_id=item_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def edit_item_cmd(self, interaction: discord.Interaction, item_id: str):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 無權限", ephemeral=True)
            return

        item_data = await get_item(item_id)
        if not item_data:
            await interaction.response.send_message(f"❌ 找不到道具 ID `{item_id}`，請確認是否輸入正確。", ephemeral=True)
            return

        view = ItemEditView(item_data)
        embed = discord.Embed(title=f"🛠️ 編輯道具：{item_id}", color=discord.Color.orange())
        embed.add_field(name="名稱", value=f"{item_data['emoji']} {item_data['name']}", inline=True)
        embed.add_field(name="分類", value=CATEGORY_NAMES.get(item_data["category"], "未知"), inline=True)
        embed.add_field(name="描述", value=item_data["desc"], inline=False)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # 4. 🎁 /give_item 給予指定道具與數量
    @app_commands.command(name="give_item", description="【開發者專用】給予指定成員特定道具與數量")
    @app_commands.describe(
        category="道具分類",
        item_id="道具 ID / 名稱",
        amount="給予數量 (預設為 1)",
        target="目標成員 (留空則給予自己)"
    )
    @app_commands.choices(category=[
        app_commands.Choice(name="🍵 消耗品", value="consumable"),
        app_commands.Choice(name="🎴 收藏品", value="collectible"),
        app_commands.Choice(name="🛠️ 裝備與特殊", value="special")
    ])
    @app_commands.autocomplete(item_id=item_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def give_item_cmd(
        self, 
        interaction: discord.Interaction, 
        category: app_commands.Choice[str], 
        item_id: str, 
        amount: int = 1, 
        target: discord.User | discord.Member = None
    ):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 無權限", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ 給予數量必須大於 0！", ephemeral=True)
            return

        item_info = await get_item(item_id)
        if not item_info:
            await interaction.response.send_message(f"❌ 道具 ID `{item_id}` 不存在於資料庫中！", ephemeral=True)
            return

        target_user = target or interaction.user
        user_data = await get_or_create_user(target_user.id)
        
        # 解析玩家 JSON 背包
        raw_inv = user_data.get("inventory", "{}")
        inventory = json.loads(raw_inv) if isinstance(raw_inv, str) else (raw_inv or {})

        # 增加道具數量
        inventory[item_id] = inventory.get(item_id, 0) + amount
        await save_user_inventory(target_user.id, inventory)

        await interaction.response.send_message(
            f"🎁 成功向 **{target_user.display_name}** 發放 {item_info['emoji']} **{item_info['name']}** x `{amount}`！",
            ephemeral=True
        )

    # 5. 🎲 /give_items 隨機給予多件道具 (方案 A 獨立抽取)
    @app_commands.command(name="give_items", description="【開發者專用】隨機給予指定成員多件道具")
    @app_commands.describe(
        number="隨機抽取的道具總件數",
        target="目標成員 (留空則給予自己)"
    )
    @app_commands.default_permissions(administrator=True)
    async def give_items_cmd(self, interaction: discord.Interaction, number: int, target: discord.User | discord.Member = None):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 無權限", ephemeral=True)
            return

        if number <= 0:
            await interaction.response.send_message("❌ 抽取數量必須大於 0！", ephemeral=True)
            return

        all_items = await get_all_items()
        if not all_items:
            await interaction.response.send_message("❌ 目前道具資料庫庫存為空，無法進行隨機抽樣！", ephemeral=True)
            return

        target = target or interaction.user
        user_data = await get_or_create_user(target.id)
        
        raw_inv = user_data.get("inventory", "{}")
        inventory = json.loads(raw_inv) if isinstance(raw_inv, str) else (raw_inv or {})

        # 🎲 進行 number 次獨立隨機抽樣 (方案 A)
        item_keys = list(all_items.keys())
        gained_summary = {}

        for _ in range(number):
            picked_id = random.choice(item_keys)
            gained_summary[picked_id] = gained_summary.get(picked_id, 0) + 1
            inventory[picked_id] = inventory.get(picked_id, 0) + 1

        await update_user_inventory(target.id, inventory)

        # 繪製獲得結果清單 Embed
        embed = discord.Embed(
            title="🎁 隨機道具發放完成",
            description=f"成功向 **{target.display_name}** 發放了 `{number}` 件隨機道具：",
            color=discord.Color.gold()
        )
        for g_id, g_count in gained_summary.items():
            info = all_items.get(g_id, {"name": g_id, "emoji": "📦"})
            embed.add_field(name=f"{info['emoji']} {info['name']}", value=f"x `{g_count}`", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ItemAdmin(bot))
import json
import random
import discord
from discord import app_commands
from discord.ext import commands

from Database.User_DB_Manager import get_or_create_user, update_user_inventory
from Database.Item_DB_Manager import (
    get_all_items, get_item, add_item_db,
    update_item_db, delete_item_db, batch_import_db, CATEGORY_NAMES
)
from Utils.components import send_notice, notice_container

ADMIN_ID = 403895664666214400


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


CATEGORY_OPTIONS = [
    ("🍵 消耗品", "consumable"),
    ("🎴 收藏品", "collectible"),
    ("🛠️ 裝備與特殊", "special"),
]


class ItemEditView(discord.ui.LayoutView):
    """道具編輯控制台 (Components V2)：編輯畫面 / 刪除確認 / 已刪除，三種狀態同一個 View"""
    def __init__(self, item_data: dict):
        super().__init__(timeout=300)
        self.item_data = item_data
        self.build()

    def build(self, notice: str = None, mode: str = "edit"):
        self.clear_items()
        item = self.item_data

        # ---- 已刪除 ----
        if mode == "deleted":
            self.add_item(notice_container(f"### 🗑️ 道具已刪除\n已成功從資料庫中移除 `{item['item_id']}`！"))
            return

        # ---- 刪除確認 ----
        if mode == "confirm_delete":
            confirm_btn = discord.ui.Button(label="✔️ 確定刪除", style=discord.ButtonStyle.danger)
            confirm_btn.callback = self.confirm_delete_callback
            cancel_btn = discord.ui.Button(label="❌ 取消", style=discord.ButtonStyle.secondary)
            cancel_btn.callback = self.cancel_delete_callback

            container = discord.ui.Container(accent_color=discord.Color.red())
            container.add_item(discord.ui.TextDisplay(
                f"## ⚠️ 刪除確認\n"
                f"確定要永久刪除道具 **{item['name']}** (`{item['item_id']}`) 嗎？\n"
                f"*(玩家背包內的該道具將會變成無效資料)*"
            ))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.ActionRow(confirm_btn, cancel_btn))
            self.add_item(container)
            return

        # ---- 編輯畫面 ----
        category_select = discord.ui.Select(
            placeholder="更換分類...",
            options=[
                discord.SelectOption(label=label, value=value, default=(value == item["category"]))
                for label, value in CATEGORY_OPTIONS
            ],
        )
        category_select.callback = self.select_category_callback
        edit_btn = discord.ui.Button(label="✏️ 編輯詳細資料", style=discord.ButtonStyle.primary)
        edit_btn.callback = self.edit_callback
        delete_btn = discord.ui.Button(label="🗑️ 刪除物品", style=discord.ButtonStyle.danger)
        delete_btn.callback = self.delete_callback

        container = discord.ui.Container(accent_color=discord.Color.orange())
        container.add_item(discord.ui.TextDisplay(
            f"## 🛠️ 編輯道具：{item['item_id']}\n"
            f"**名稱**：{item['emoji']} {item['name']}\n"
            f"**分類**：{CATEGORY_NAMES.get(item['category'], '未知')}\n"
            f"**描述**：\n{item['desc']}"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(category_select))
        container.add_item(discord.ui.ActionRow(edit_btn, delete_btn))
        if notice:
            container.add_item(discord.ui.TextDisplay(f"-# {notice}"))
        self.add_item(container)

    async def update_message(self, interaction: discord.Interaction, notice: str = None, mode: str = "edit"):
        self.build(notice, mode)
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != ADMIN_ID:
            await send_notice(interaction, "❌ 無權限")
            return False
        return True

    async def select_category_callback(self, interaction: discord.Interaction):
        new_category = interaction.data["values"][0]
        self.item_data["category"] = new_category
        await update_item_db(
            self.item_data["item_id"], self.item_data["name"],
            self.item_data["emoji"], new_category, self.item_data["desc"]
        )
        await self.update_message(interaction, f"✅ 分類已更改為：{CATEGORY_NAMES[new_category]}")

    async def edit_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ItemEditModal(self, self.item_data))

    async def delete_callback(self, interaction: discord.Interaction):
        await self.update_message(interaction, mode="confirm_delete")

    async def confirm_delete_callback(self, interaction: discord.Interaction):
        await delete_item_db(self.item_data["item_id"])
        await self.update_message(interaction, mode="deleted")
        self.stop()

    async def cancel_delete_callback(self, interaction: discord.Interaction):
        await self.update_message(interaction, "↩️ 已取消刪除操作。")


# ---------------------------------------------------------
# 🤖 ItemAdmin Cog
# ---------------------------------------------------------
class ItemAdmin(commands.GroupCog, group_name="admin-item", group_description="【開發者專用】道具資料庫管理指令"):
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
            await send_notice(interaction, "❌ 無權限")
            return
            
        success = await add_item_db(item_id, name, emoji, category.value, desc)
        if success:
            await send_notice(interaction, f"✅ 成功新增道具：{emoji} **{name}** (`{item_id}`)")
        else:
            await send_notice(interaction, f"❌ 新增失敗！道具 ID `{item_id}` 已存在。")

    # 2. 📦 /add_items_batch 批量上傳
    @app_commands.command(name="add_items_batch", description="【開發者專用】上傳 JSON 檔案批量新增/覆寫道具")
    @app_commands.describe(file="包含道具資料的 .json 檔案", overwrite="若道具已存在，是否要覆蓋舊資料？ (預設為 False)")
    @app_commands.default_permissions(administrator=True)
    async def add_items_batch_cmd(self, interaction: discord.Interaction, file: discord.Attachment, overwrite: bool = False):
        if interaction.user.id != ADMIN_ID:
            await send_notice(interaction, "❌ 無權限")
            return

        if not file.filename.endswith(".json"):
            await send_notice(interaction, "❌ 請上傳 `.json` 格式的檔案！")
            return

        await interaction.response.defer(ephemeral=True)

        try:
            content = await file.read()
            items_dict = json.loads(content.decode('utf-8'))
            
            success, skipped = await batch_import_db(items_dict, overwrite)
            await send_notice(interaction, f"✅ 批量匯入完成！\n成功新增/更新：`{success}` 件\n略過(重複)：`{skipped}` 件")
        except Exception as e:
            await send_notice(interaction, f"❌ JSON 解析失敗，請檢查檔案格式！\n```py\n{e}\n```")

    # 3. 📦 /edit_item 編輯控制台
    @app_commands.command(name="edit_item", description="【開發者專用】開啟道具編輯控制台")
    @app_commands.autocomplete(item_id=item_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def edit_item_cmd(self, interaction: discord.Interaction, item_id: str):
        if interaction.user.id != ADMIN_ID:
            await send_notice(interaction, "❌ 無權限")
            return

        item_data = await get_item(item_id)
        if not item_data:
            await send_notice(interaction, f"❌ 找不到道具 ID `{item_id}`，請確認是否輸入正確。")
            return

        view = ItemEditView(item_data)
        await interaction.response.send_message(view=view, ephemeral=True)

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
            await send_notice(interaction, "❌ 無權限")
            return

        if amount <= 0:
            await send_notice(interaction, "❌ 給予數量必須大於 0！")
            return

        item_info = await get_item(item_id)
        if not item_info:
            await send_notice(interaction, f"❌ 道具 ID `{item_id}` 不存在於資料庫中！")
            return

        target_user = target or interaction.user
        user_data = await get_or_create_user(target_user.id)
        
        # 解析玩家 JSON 背包
        raw_inv = user_data.get("inventory", "{}")
        inventory = json.loads(raw_inv) if isinstance(raw_inv, str) else (raw_inv or {})

        # 增加道具數量
        inventory[item_id] = inventory.get(item_id, 0) + amount
        await update_user_inventory(target_user.id, inventory)

        await send_notice(interaction, f"🎁 成功向 **{target_user.display_name}** 發放 {item_info['emoji']} **{item_info['name']}** x `{amount}`！")

    # 5. 🎲 /give_items 隨機給予多件道具 (方案 A 獨立抽取)
    @app_commands.command(name="give_items", description="【開發者專用】隨機給予指定成員多件道具")
    @app_commands.describe(
        number="隨機抽取的道具總件數",
        target="目標成員 (留空則給予自己)"
    )
    @app_commands.default_permissions(administrator=True)
    async def give_items_cmd(self, interaction: discord.Interaction, number: int, target: discord.User | discord.Member = None):
        if interaction.user.id != ADMIN_ID:
            await send_notice(interaction, "❌ 無權限")
            return

        if number <= 0:
            await send_notice(interaction, "❌ 抽取數量必須大於 0！")
            return

        all_items = await get_all_items()
        if not all_items:
            await send_notice(interaction, "❌ 目前道具資料庫庫存為空，無法進行隨機抽樣！")
            return

        target = target or interaction.user
        user_data = await get_or_create_user(target.id)
        
        raw_inv = user_data.get("inventory", "{}")
        inventory = json.loads(raw_inv) if isinstance(raw_inv, str) else (raw_inv or {})

        # 🎲 進行 number 次獨立隨機抽樣
        item_keys = list(all_items.keys())
        gained_summary = {}

        for _ in range(number):
            picked_id = random.choice(item_keys)
            gained_summary[picked_id] = gained_summary.get(picked_id, 0) + 1
            inventory[picked_id] = inventory.get(picked_id, 0) + 1

        await update_user_inventory(target.id, inventory)

        # 🟢 取出所有抽到的道具種類清單
        summary_items = list(gained_summary.items())
        
        # 🟢 開頭說明
        header = f"成功向 **{target.display_name}** 發放了 `{number}` 件隨機道具：\n\n"
        
        # 🟢 只取前 25 種道具建立完整字串
        lines = []
        for g_id, g_count in summary_items[:25]:
            info = all_items.get(g_id, {"name": g_id, "emoji": "📦"})
            lines.append(f"• {info['emoji']} **{info['name']}** x `{g_count}`")

        # 🟢 超過 25 種時補上提示
        if len(summary_items) > 25:
            lines.append(f"\n…（另有 `{len(summary_items) - 25}` 種道具已成功寫入背包，此處省略顯示）")

        await send_notice(interaction, "## 🎁 隨機道具發放完成\n" + header + "\n".join(lines), color=discord.Color.gold())

async def setup(bot: commands.Bot):
    await bot.add_cog(ItemAdmin(bot))
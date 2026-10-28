import json
import random
import discord
from discord import app_commands
from discord.ext import commands

from Database.User_DB_Manager import get_or_create_user, update_user_inventory, adjust_item
from Database.Item_DB_Manager import (
    get_all_items, get_item, add_item_db,
    update_item_db, delete_item_db, batch_import_db, CATEGORY_NAMES
)
from Utils.config import is_admin
from Utils.components import send_notice, notice_container



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
        if not is_admin(interaction.user):
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
# 🎁 道具管理 (給予 / 扣除)：分類 + 分頁 + 堆疊列表 ➔ 選道具 ➔ Modal 輸入數量
# ---------------------------------------------------------
MANAGE_PER_PAGE = 10
OWNED_FILTER = "owned"   # 分類選單裡的「只看對方持有的」


class ItemAmountModal(discord.ui.Modal):
    """輸入數量：正數給予、負數扣除"""
    def __init__(self, view_ref, item_id: str, item: dict, owned: int):
        super().__init__(title=f"調整：{item['name']}"[:45])
        self.view_ref = view_ref
        self.item_id = item_id
        self.item = item
        self.amount_input = discord.ui.TextInput(
            label=f"數量（目前持有 {owned}）正數給予、負數扣除"[:45],
            placeholder="例如 5 或 -3",
            required=True,
            max_length=7,
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = (self.amount_input.value or "").strip().replace("＋", "+").replace("－", "-")
        try:
            delta = int(raw)
        except ValueError:
            await self.view_ref.refresh(interaction, f"❌ `{raw}` 不是整數，請輸入例如 `5` 或 `-3`。")
            return
        if delta == 0:
            await self.view_ref.refresh(interaction, "❌ 數量不能是 0。")
            return

        result = await adjust_item(self.view_ref.target.id, self.item_id, delta)
        name = f"{self.item['emoji']} **{self.item['name']}**"
        who = f"**{self.view_ref.target.display_name}**"
        if not result["ok"]:
            notice = f"❌ {who} 只有 {name} `×{result['before']}`，不能扣除 `{abs(delta)}` 個（扣完會小於 0）。"
        elif result["after"] == 0:
            notice = f"🗑️ 已扣除 {who} 的 {name} `×{abs(delta)}`，數量歸零，已從背包移除。"
        elif delta > 0:
            notice = f"🎁 已給予 {who} {name} `×{delta}`（`{result['before']}` ➔ `{result['after']}`）"
        else:
            notice = f"🔻 已扣除 {who} 的 {name} `×{abs(delta)}`（`{result['before']}` ➔ `{result['after']}`）"
        await self.view_ref.refresh(interaction, notice)


class ItemManageView(discord.ui.LayoutView):
    """對指定成員給予 / 扣除道具；同一個道具疊成一列並顯示對方目前的持有數"""
    def __init__(self, target, items: dict, inventory: dict):
        super().__init__(timeout=300)
        self.target = target
        self.items = items
        self.inventory = inventory
        self.category = "all"
        self.page = 1
        self.notice = None
        self.build()

    def _rows(self) -> list[tuple[str, dict, int]]:
        order = list(CATEGORY_NAMES)
        rows = []
        for iid, item in self.items.items():
            owned = self.inventory.get(iid, 0)
            if self.category == OWNED_FILTER and owned <= 0:
                continue
            if self.category not in ("all", OWNED_FILTER) and item["category"] != self.category:
                continue
            rows.append((iid, item, owned))
        rows.sort(key=lambda r: (order.index(r[1]["category"]) if r[1]["category"] in order else 99, r[0]))
        return rows

    def _button(self, label, callback, disabled=False, style=discord.ButtonStyle.primary):
        btn = discord.ui.Button(label=label, style=style, disabled=disabled)
        if callback is not None:
            btn.callback = callback
        return btn

    def build(self):
        self.clear_items()
        rows = self._rows()
        total_pages = max(1, (len(rows) + MANAGE_PER_PAGE - 1) // MANAGE_PER_PAGE)
        self.page = min(self.page, total_pages)
        start = (self.page - 1) * MANAGE_PER_PAGE
        page_rows = rows[start:start + MANAGE_PER_PAGE]

        total_owned = sum(v for v in self.inventory.values() if v > 0)
        container = discord.ui.Container(accent_color=discord.Color.gold())
        container.add_item(discord.ui.TextDisplay(
            f"## 🎁 道具管理：{self.target.display_name}\n"
            f"🎒 對方背包共 `{total_owned}` 件道具\n"
            f"-# 選擇道具後輸入數量：正數給予、負數扣除（扣完不能小於 0，剛好 0 會移除）"
        ))
        if self.notice:
            container.add_item(discord.ui.TextDisplay(self.notice))
        container.add_item(discord.ui.Separator())

        if page_rows:
            lines = [
                f"**{i}.** {item['emoji']} **{item['name']}**　{'`×' + str(owned) + '`' if owned else '*未持有*'}\n"
                f"-# {CATEGORY_NAMES.get(item['category'], '未知')} · `{iid}`"
                for i, (iid, item, owned) in enumerate(page_rows, start=start + 1)
            ]
            container.add_item(discord.ui.TextDisplay("\n".join(lines)))
        else:
            container.add_item(discord.ui.TextDisplay("*（這個分類沒有任何道具）*"))
        container.add_item(discord.ui.Separator())

        category_select = discord.ui.Select(placeholder="📂 選擇分類...", options=[
            discord.SelectOption(label=label, value=value, default=(value == self.category))
            for value, label in [(k, v) for k, v in CATEGORY_NAMES.items()] + [(OWNED_FILTER, "🎒 只看對方持有的")]
        ])
        category_select.callback = self.category_callback
        container.add_item(discord.ui.ActionRow(category_select))

        if page_rows:
            item_select = discord.ui.Select(placeholder="✏️ 選擇要調整的道具...", options=[
                discord.SelectOption(
                    label=f"{i}. {item['name']}"[:100],
                    description=f"持有 {owned} · {iid}"[:100],
                    value=iid,
                    emoji=item["emoji"] or None,
                )
                for i, (iid, item, owned) in enumerate(page_rows, start=start + 1)
            ])
            item_select.callback = self.item_callback
            container.add_item(discord.ui.ActionRow(item_select))

        container.add_item(discord.ui.ActionRow(
            self._button("◀️ 上一頁", self.prev_callback, disabled=(self.page <= 1)),
            self._button(f"📄 {self.page} / {total_pages} 頁", None, disabled=True, style=discord.ButtonStyle.secondary),
            self._button("下一頁 ▶️", self.next_callback, disabled=(self.page >= total_pages)),
        ))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return False
        return True

    async def refresh(self, interaction: discord.Interaction, notice: str | None = None):
        """重新讀取道具與對方背包後更新畫面"""
        self.items = await get_all_items()
        self.inventory = (await get_or_create_user(self.target.id))["inventory"]
        self.notice = notice
        self.build()
        await interaction.response.edit_message(view=self)

    async def category_callback(self, interaction: discord.Interaction):
        self.category = interaction.data["values"][0]
        self.page = 1
        await self.refresh(interaction)

    async def item_callback(self, interaction: discord.Interaction):
        iid = interaction.data["values"][0]
        item = self.items.get(iid)
        if item is None:
            await self.refresh(interaction, f"❌ 道具 `{iid}` 已不存在。")
            return
        owned = (await get_or_create_user(self.target.id))["inventory"].get(iid, 0)
        await interaction.response.send_modal(ItemAmountModal(self, iid, item, owned))

    async def prev_callback(self, interaction: discord.Interaction):
        self.page = max(1, self.page - 1)
        await self.refresh(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        self.page += 1
        await self.refresh(interaction)


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
        if not is_admin(interaction.user):
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
        if not is_admin(interaction.user):
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
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return

        item_data = await get_item(item_id)
        if not item_data:
            await send_notice(interaction, f"❌ 找不到道具 ID `{item_id}`，請確認是否輸入正確。")
            return

        view = ItemEditView(item_data)
        await interaction.response.send_message(view=view, ephemeral=True)

    # 4. 🎁 /manage 給予 / 扣除道具 (分類 + 分頁 + 堆疊列表 ➔ Modal 輸入數量)
    @app_commands.command(name="manage", description="【開發者專用】給予或扣除指定成員的道具 (正數給予、負數扣除)")
    @app_commands.describe(target="目標成員 (留空則為自己)")
    @app_commands.default_permissions(administrator=True)
    async def manage_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member = None):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return
        target = target or interaction.user
        items = await get_all_items()
        if not items:
            await send_notice(interaction, "❌ 道具資料庫是空的，請先用 `/admin-item add_item` 新增道具。")
            return
        inventory = (await get_or_create_user(target.id))["inventory"]
        await interaction.response.send_message(view=ItemManageView(target, items, inventory), ephemeral=True)

    # 5. 🎲 /give_items 隨機給予多件道具 (方案 A 獨立抽取)
    @app_commands.command(name="give_items", description="【開發者專用】隨機給予指定成員多件道具")
    @app_commands.describe(
        number="隨機抽取的道具總件數",
        target="目標成員 (留空則給予自己)"
    )
    @app_commands.default_permissions(administrator=True)
    async def give_items_cmd(self, interaction: discord.Interaction, number: int, target: discord.User | discord.Member = None):
        if not is_admin(interaction.user):
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
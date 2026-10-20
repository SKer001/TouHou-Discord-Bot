import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random
import uuid
from datetime import datetime

from Database.db_manager import get_or_create_user, add_money
from .Embeds.gacha_embeds import (
    build_gacha_single_embed, 
    build_gacha_ten_embeds,
    build_card_inventory_embeds,
    build_card_detail_embed
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "users")
CHAR_FILE = os.path.join(BASE_DIR, "character.json")
THUMBNAILS_DIR = os.path.join(BASE_DIR, "images", "Thumbnails")

os.makedirs(USERS_DIR, exist_ok=True)
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

try:
    with open(CHAR_FILE, "r", encoding="utf-8") as f:
        ALL_CHARACTERS = json.load(f)
except (json.JSONDecodeError, FileNotFoundError) as e:
    print(f"❌ [Gacha Error] 讀取 {CHAR_FILE} 失敗：{e}")
    ALL_CHARACTERS = {}

RARITY_ORDER = {"N": 0, "R": 1, "SR": 2, "SSR": 3, "UR": 4, "LR": 5}

def sort_cards(cards: list) -> list:
    return sorted(cards, key=lambda c: (
        RARITY_ORDER.get(c.get("rarity", "N"), 0),
        c.get("character_key", ""),
        c.get("completeness", 0.0),
        c.get("obtained_at", "")
    ))


# ================= 🎛️ 抽卡結果控制按鈕 View =================
class GachaResultView(discord.ui.View):
    def __init__(self, user_id: int, user_name: str, gacha_cog):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的祈願畫面！請輸入 `/card gacha` 開啟你自己的祈願。", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🌸 繼續單抽 (2,000)", style=discord.ButtonStyle.primary, row=0)
    async def draw_single_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.gacha_cog.execute_gacha(interaction, draw_count=1)

    @discord.ui.button(label="⛩️ 繼續十連 (20,000)", style=discord.ButtonStyle.success, row=0)
    async def draw_ten_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.gacha_cog.execute_gacha(interaction, draw_count=10)

    @discord.ui.button(label="🎒 查看卡庫", style=discord.ButtonStyle.secondary, row=0)
    async def view_inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        cards = self.gacha_cog.get_user_cards(self.user_id)
        if not cards:
            await interaction.followup.send("🎒 你的卡冊空空如也，快進行祈願吧！", ephemeral=True)
            return

        sorted_cards = sort_cards(cards)
        inv_view = InventoryView(self.user_id, sorted_cards, self.user_name, self.gacha_cog)
        embeds, files = build_card_inventory_embeds(
            inv_view.get_current_page_cards(),
            inv_view.current_page,
            inv_view.total_pages,
            len(sorted_cards),
            sorted_cards,
            self.user_name,
            THUMBNAILS_DIR
        )
        await interaction.edit_original_response(content=None, embeds=embeds, attachments=files, view=inv_view)


# ================= 🎒 背包互動 View =================
class InventoryView(discord.ui.View):
    def __init__(self, user_id: int, cards: list, user_name: str, gacha_cog):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.all_cards = sort_cards(cards)
        self.current_filter = "ALL"
        self.filtered_cards = self.all_cards
        self.current_page = 1
        self.per_page = 10
        self.selected_card = None
        self.update_components()

    @property
    def total_pages(self) -> int:
        return max(1, (len(self.filtered_cards) + self.per_page - 1) // self.per_page)

    def get_current_page_cards(self) -> list:
        start = (self.current_page - 1) * self.per_page
        end = start + self.per_page
        return self.filtered_cards[start:end]

    def update_components(self):
        self.clear_items()

        if self.selected_card:
            back_btn = discord.ui.Button(label="🔙 返回卡冊", style=discord.ButtonStyle.secondary, row=0)
            back_btn.callback = self.back_button_callback
            self.add_item(back_btn)
            return

        filter_options = [
            discord.SelectOption(label="全部階級 (ALL)", value="ALL", default=(self.current_filter == "ALL")),
            discord.SelectOption(label="N 階級", value="N", default=(self.current_filter == "N")),
            discord.SelectOption(label="R 階級", value="R", default=(self.current_filter == "R")),
            discord.SelectOption(label="SR 階級", value="SR", default=(self.current_filter == "SR")),
            discord.SelectOption(label="SSR 階級", value="SSR", default=(self.current_filter == "SSR")),
            discord.SelectOption(label="UR 階級", value="UR", default=(self.current_filter == "UR")),
            discord.SelectOption(label="LR 階級", value="LR", default=(self.current_filter == "LR")),
        ]
        filter_select = discord.ui.Select(placeholder="🔍 選擇稀有度篩選...", options=filter_options, row=0)
        filter_select.callback = self.filter_select_callback
        self.add_item(filter_select)

        page_cards = self.get_current_page_cards()
        if page_cards:
            card_options = []
            for card in page_cards:
                card_options.append(discord.SelectOption(
                    label=f"[{card['rarity']}] {card['name']} - {card['title']}",
                    description=f"Float: {card['completeness']:.4f} | ID: {card['instance_id']}",
                    value=card["instance_id"],
                    emoji=card.get("emoji", "🎴")
                ))
            card_select = discord.ui.Select(placeholder="🎴 選擇卡牌檢視詳細鑑定...", options=card_options, row=1)
            card_select.callback = self.card_select_callback
            self.add_item(card_select)

        prev_btn = discord.ui.Button(label="◀️ 上一頁", style=discord.ButtonStyle.primary, disabled=(self.current_page <= 1), row=2)
        prev_btn.callback = self.prev_page_callback
        self.add_item(prev_btn)

        page_btn = discord.ui.Button(label=f"📄 {self.current_page} / {self.total_pages} 頁", style=discord.ButtonStyle.secondary, disabled=True, row=2)
        self.add_item(page_btn)

        next_btn = discord.ui.Button(label="下一頁 ▶️", style=discord.ButtonStyle.primary, disabled=(self.current_page >= self.total_pages), row=2)
        next_btn.callback = self.next_page_callback
        self.add_item(next_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是你的卡冊！", ephemeral=True)
            return False
        return True

    async def filter_select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        select_val = interaction.data["values"][0]
        self.current_filter = select_val
        self.filtered_cards = self.all_cards if select_val == "ALL" else [c for c in self.all_cards if c.get("rarity") == select_val]
        self.current_page = 1
        self.update_components()
        embeds, files = build_card_inventory_embeds(self.get_current_page_cards(), self.current_page, self.total_pages, len(self.all_cards), self.all_cards, self.user_name, THUMBNAILS_DIR)
        await interaction.edit_original_response(embeds=embeds, attachments=files, view=self)

    async def card_select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        instance_id = interaction.data["values"][0]
        card = next((c for c in self.all_cards if c["instance_id"] == instance_id), None)
        if card:
            self.selected_card = card
            self.update_components()
            embed, files = build_card_detail_embed(card, self.user_name, THUMBNAILS_DIR)
            await interaction.edit_original_response(embeds=[embed], attachments=files, view=self)

    async def back_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.selected_card = None
        self.update_components()
        embeds, files = build_card_inventory_embeds(self.get_current_page_cards(), self.current_page, self.total_pages, len(self.all_cards), self.all_cards, self.user_name, THUMBNAILS_DIR)
        await interaction.edit_original_response(embeds=embeds, attachments=files, view=self)

    async def prev_page_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.current_page > 1:
            self.current_page -= 1
            self.update_components()
            embeds, files = build_card_inventory_embeds(self.get_current_page_cards(), self.current_page, self.total_pages, len(self.all_cards), self.all_cards, self.user_name, THUMBNAILS_DIR)
            await interaction.edit_original_response(embeds=embeds, attachments=files, view=self)

    async def next_page_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_components()
            embeds, files = build_card_inventory_embeds(self.get_current_page_cards(), self.current_page, self.total_pages, len(self.all_cards), self.all_cards, self.user_name, THUMBNAILS_DIR)
            await interaction.edit_original_response(embeds=embeds, attachments=files, view=self)


# ================= 🎴 Cog 類別 =================
class GachaCardSys(commands.GroupCog, group_name="card", group_description="東方角色卡牌收集與合成系統"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_user_data(self, user_id: int) -> dict:
        path = f"{USERS_DIR}/{user_id}.json"
        if not os.path.exists(path):
            return {"user_id": user_id, "stats": {"total_draws": 0, "total_fusions": 0}, "cards": []}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_user_cards(self, user_id: int) -> list:
        return self.get_user_data(user_id).get("cards", [])

    def save_user_data(self, user_id: int, data: dict):
        path = f"{USERS_DIR}/{user_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def generate_completeness(self) -> float:
        val = (random.gauss(0, 0.35)) ** 2
        return round(max(0.001, min(1.000, val)), 4)

    async def execute_gacha(self, interaction: discord.Interaction, draw_count: int):
        await interaction.response.defer()
        user_id = interaction.user.id
        total_cost = draw_count * 2000

        user_db = await get_or_create_user(user_id)
        current_money = user_db.get("money", 0)

        if current_money < total_cost:
            msg = f"❌ **賽錢不足！**\n祈願需要 `{total_cost:,}` 賽錢，但你的口袋裡只有 `{current_money:,}` 賽錢...\n*靈夢看了看空蕩蕩的賽錢箱，無奈地把你請出了神社。*"
            await interaction.followup.send(msg, ephemeral=True)
            return

        await add_money(user_id, -total_cost)

        user_data = self.get_user_data(user_id)
        results = []
        char_keys = list(ALL_CHARACTERS.keys())

        for _ in range(draw_count):
            char_key = random.choice(char_keys)
            char_data = ALL_CHARACTERS[char_key]
            
            rarity = random.choices(char_data["rarities"], weights=[75, 22, 3], k=1)[0]
            title = char_data["titles"][rarity]
            
            new_card = {
                "instance_id": f"c_{char_data['uuid'][:4]}_{uuid.uuid4().hex[:8]}",
                "character_key": char_key,
                "name": char_data["name"],
                "emoji": char_data["emoji"],
                "rarity": rarity,
                "title": title,
                "completeness": self.generate_completeness(),
                "obtained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            results.append(new_card)
            user_data["cards"].append(new_card)

        user_data["stats"]["total_draws"] += draw_count
        self.save_user_data(user_id, user_data)

        view = GachaResultView(user_id, interaction.user.display_name, self)

        if draw_count == 1:
            embed, files = build_gacha_single_embed(
                results[0], interaction.user.display_name, total_cost, THUMBNAILS_DIR
            )
            embeds = [embed]
        else:
            embeds, files = build_gacha_ten_embeds(
                results, interaction.user.display_name, total_cost, THUMBNAILS_DIR
            )

        if interaction.type == discord.InteractionType.component:
            await interaction.edit_original_response(content=None, embeds=embeds, attachments=files, view=view)
        else:
            await interaction.followup.send(embeds=embeds, files=files, view=view)

    @app_commands.command(name="gacha", description="⛩️ 博麗神社祈願：消耗賽錢抽取角色卡牌")
    @app_commands.choices(pull_type=[
        app_commands.Choice(name="單次祈願 (2,000 賽錢)", value=1),
        app_commands.Choice(name="十連祈願 (20,000 賽錢)", value=10)
    ])
    async def gacha_card(self, interaction: discord.Interaction, pull_type: app_commands.Choice[int]):
        await self.execute_gacha(interaction, pull_type.value)

    @app_commands.command(name="inventory", description="🎒 查看個人的博麗神社卡冊與持有卡牌")
    async def view_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        cards = self.get_user_cards(user_id)

        if not cards:
            await interaction.followup.send("🎒 你的卡冊空空如也，快去使用 `/card gacha` 進行第一次祈願吧！", ephemeral=True)
            return

        sorted_user_cards = sort_cards(cards)
        view = InventoryView(user_id, sorted_user_cards, interaction.user.display_name, self)
        embeds, files = build_card_inventory_embeds(
            view.get_current_page_cards(),
            view.current_page,
            view.total_pages,
            len(sorted_user_cards),
            sorted_user_cards,
            interaction.user.display_name,
            THUMBNAILS_DIR
        )

        await interaction.followup.send(embeds=embeds, files=files, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCardSys(bot))
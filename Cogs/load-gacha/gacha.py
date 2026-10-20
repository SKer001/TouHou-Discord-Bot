import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random
import uuid
from datetime import datetime

from Database.db_manager import get_or_create_user, add_money
from .gacha_embeds import (
    build_gacha_single_embed, 
    build_gacha_ten_embed,
    build_card_inventory_embed,
    build_card_detail_embed
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "users")
CHAR_FILE = os.path.join(BASE_DIR, "character.json")

os.makedirs(USERS_DIR, exist_ok=True)

try:
    with open(CHAR_FILE, "r", encoding="utf-8") as f:
        ALL_CHARACTERS = json.load(f)
except (json.JSONDecodeError, FileNotFoundError) as e:
    print(f"❌ [Gacha Error] 讀取 {CHAR_FILE} 失敗：{e}")
    ALL_CHARACTERS = {}

# 稀有度排序權重
RARITY_ORDER = {"N": 0, "R": 1, "SR": 2, "SSR": 3, "UR": 4, "LR": 5}

def sort_cards(cards: list) -> list:
    """
    多重排序邏輯：
    1. 稀有度 [N-LR]
    2. character_key (a-z)
    3. completeness 升冪 (小到大)
    4. obtained_at 時間升冪 (舊到新)
    """
    return sorted(cards, key=lambda c: (
        RARITY_ORDER.get(c.get("rarity", "N"), 0),
        c.get("character_key", ""),
        c.get("completeness", 0.0),
        c.get("obtained_at", "")
    ))


# ================= 🎛️ 背包互動 View =================
class InventoryView(discord.ui.View):
    def __init__(self, user_id: int, cards: list, user_name: str):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.all_cards = sort_cards(cards)
        self.current_filter = "ALL"
        self.filtered_cards = self.all_cards
        self.current_page = 1
        self.per_page = 8
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
        """依據目前狀態重新配置下拉選單與按鈕"""
        self.clear_items()

        # 🔍 詳情檢視模式：只顯示「返回」按鈕
        if self.selected_card:
            back_btn = discord.ui.Button(label="🔙 返回卡冊", style=discord.ButtonStyle.secondary, row=0)
            back_btn.callback = self.back_button_callback
            self.add_item(back_btn)
            return

        # 📋 卡冊列表模式
        # 1. 稀有度篩選選單
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

        # 2. 當頁卡牌選擇選單 (進行精準點選與檢視)
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

        # 3. 翻頁按鈕列
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
            await interaction.response.send_message("❌ 這不是你的卡冊！請輸入 `/card inventory` 開啟你自己的卡冊。", ephemeral=True)
            return False
        return True

    async def filter_select_callback(self, interaction: discord.Interaction):
        select_val = interaction.data["values"][0]
        self.current_filter = select_val
        if select_val == "ALL":
            self.filtered_cards = self.all_cards
        else:
            self.filtered_cards = [c for c in self.all_cards if c.get("rarity") == select_val]
        self.current_page = 1
        self.update_components()
        embed = build_card_inventory_embed(self.get_current_page_cards(), self.current_page, self.total_pages, len(self.all_cards), self.all_cards, self.user_name)
        await interaction.response.edit_message(embed=embed, view=self)

    async def card_select_callback(self, interaction: discord.Interaction):
        instance_id = interaction.data["values"][0]
        card = next((c for c in self.all_cards if c["instance_id"] == instance_id), None)
        if card:
            self.selected_card = card
            self.update_components()
            embed = build_card_detail_embed(card, self.user_name)
            await interaction.response.edit_message(embed=embed, view=self)

    async def back_button_callback(self, interaction: discord.Interaction):
        self.selected_card = None
        self.update_components()
        embed = build_card_inventory_embed(self.get_current_page_cards(), self.current_page, self.total_pages, len(self.all_cards), self.all_cards, self.user_name)
        await interaction.response.edit_message(embed=embed, view=self)

    async def prev_page_callback(self, interaction: discord.Interaction):
        if self.current_page > 1:
            self.current_page -= 1
            self.update_components()
            embed = build_card_inventory_embed(self.get_current_page_cards(), self.current_page, self.total_pages, len(self.all_cards), self.all_cards, self.user_name)
            await interaction.response.edit_message(embed=embed, view=self)

    async def next_page_callback(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_components()
            embed = build_card_inventory_embed(self.get_current_page_cards(), self.current_page, self.total_pages, len(self.all_cards), self.all_cards, self.user_name)
            await interaction.response.edit_message(embed=embed, view=self)


# ================= 🎴 Cog 類別擴充 =================
class GachaCardSys(commands.GroupCog, group_name="card", group_description="東方角色卡牌收集與合成系統"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_user_data(self, user_id: int) -> dict:
        path = f"{USERS_DIR}/{user_id}.json"
        if not os.path.exists(path):
            return {"user_id": user_id, "stats": {"total_draws": 0, "total_fusions": 0}, "cards": []}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_user_data(self, user_id: int, data: dict):
        path = f"{USERS_DIR}/{user_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def generate_completeness(self) -> float:
        val = (random.gauss(0, 0.35)) ** 2
        return round(max(0.001, min(1.000, val)), 4)

    @app_commands.command(name="gacha", description="⛩️ 博麗神社祈願：消耗賽錢抽取角色卡牌")
    @app_commands.choices(pull_type=[
        app_commands.Choice(name="單次祈願 (2,000 賽錢)", value=1),
        app_commands.Choice(name="十連祈願 (20,000 賽錢)", value=10)
    ])
    async def gacha_card(self, interaction: discord.Interaction, pull_type: app_commands.Choice[int]):
        user_id = interaction.user.id
        draw_count = pull_type.value
        total_cost = draw_count * 2000

        user_db = await get_or_create_user(user_id)
        current_money = user_db.get("money", 0)

        if current_money < total_cost:
            await interaction.response.send_message(
                f"❌ **賽錢不足！**\n祈願需要 `{total_cost}` 賽錢，但你的口袋裡只有 `{current_money}` 賽錢...\n*靈夢看了看空蕩蕩的賽錢箱，無奈地把你請出了神社。*", 
                ephemeral=True
            )
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

        if draw_count == 1:
            embed = build_gacha_single_embed(results[0], interaction.user.display_name, total_cost)
        else:
            embed = build_gacha_ten_embed(results, interaction.user.display_name, total_cost)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="inventory", description="🎒 查看個人的博麗神社卡冊與持有卡牌")
    async def view_inventory(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_data = self.get_user_data(user_id)
        cards = user_data.get("cards", [])

        if not cards:
            await interaction.response.send_message("🎒 你的卡冊空空如也，快去使用 `/card gacha` 進行第一次祈願吧！", ephemeral=True)
            return

        sorted_user_cards = sort_cards(cards)
        view = InventoryView(user_id, sorted_user_cards, interaction.user.display_name)
        
        # 初始第一頁的 Embed
        embed = build_card_inventory_embed(
            view.get_current_page_cards(),
            view.current_page,
            view.total_pages,
            len(sorted_user_cards),
            sorted_user_cards,
            interaction.user.display_name
        )

        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCardSys(bot))
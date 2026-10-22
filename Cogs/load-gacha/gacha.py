import discord
from discord import ui
from discord.ext import commands
from discord import app_commands
import json
import os
import random
import uuid
from datetime import datetime

from Database.User_DB_Manager import get_or_create_user, add_money, get_user_cards, add_gacha_cards, transform_cards
from .Components.gacha_components import (
    INVENTORY_PER_PAGE,
    build_gacha_single_container,
    build_gacha_ten_container,
    build_card_inventory_container,
    build_card_detail_container,
    build_synthesis_preview_container,
    build_synthesis_result_container,
    build_fusion_preview_container,
    build_fusion_result_container,
)
from Utils.components import send_notice

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_FILE = os.path.join(BASE_DIR, "Gacha_Pool.json")   # 卡池：哪些角色、稀有度、稱號
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
THUMBNAILS_FILE = os.path.join(PROJECT_ROOT, "images", "Thumbnails.json")

try:
    with open(POOL_FILE, "r", encoding="utf-8") as f:
        GACHA_POOL = json.load(f)
except (json.JSONDecodeError, FileNotFoundError) as e:
    print(f"❌ [Gacha Error] 讀取 {POOL_FILE} 失敗：{e}")
    GACHA_POOL = {}

# 🖼️ 讀取 Thumbnails.json：{"角色ID": "圖片URL", ..., "fill": "預設圖URL"}
try:
    with open(THUMBNAILS_FILE, "r", encoding="utf-8") as f:
        THUMBNAILS = json.load(f)
except (json.JSONDecodeError, FileNotFoundError) as e:
    print(f"❌ [Gacha Error] 讀取 {THUMBNAILS_FILE} 失敗：{e}")
    THUMBNAILS = {}

RARITY_ORDER = {"N": 0, "R": 1, "SR": 2, "SSR": 3, "UR": 4, "LR": 5}

def sort_cards(cards: list) -> list:
    return sorted(cards, key=lambda c: (
        RARITY_ORDER.get(c.get("rarity", "N"), 0),
        c.get("character_key", ""),
        c.get("completeness", 0.0),
        c.get("obtained_at", "")
    ))


# ================= ⚗️ 合成 / 🔮 融合規則 =================
# 合成增幅上限：依「較低那張」的小數位數決定 (完整度下限, 增幅上限)，由高到低比對
SYNTHESIS_CAPS = [
    (0.1, 0.2),      # 0.x
    (0.01, 0.05),    # 0.0x
    (0.001, 0.01),   # 0.00x
    (0.0, 0.005),    # 0.000x
]
# 完整度一模一樣時的加倍機率；差距越大機率越低 (× (1 - 相對差距)²)
SYNTHESIS_DOUBLE_CHANCE = {"N": 0.99, "R": 0.50, "SR": 0.30, "SSR": 0.15, "UR": 0.10, "LR": 0.05}
FUSION_COUNT = 3              # 融合需要的卡牌張數
AUTOCOMPLETE_LIMIT = 25        # Discord autocomplete 最多 25 個選項


def is_perfect(card: dict) -> bool:
    return round(card["completeness"], 4) >= 1.0


def can_synthesize(card_a: dict, card_b: dict) -> bool:
    """同角色、同階級、不同張，且兩張都還沒到 1.0000 (滿了就無法再「大於」)"""
    return (
        card_a["instance_id"] != card_b["instance_id"]
        and card_a["character_key"] == card_b["character_key"]
        and card_a["rarity"] == card_b["rarity"]
        and not is_perfect(card_a)
        and not is_perfect(card_b)
    )


def calc_synthesis(comp_a: float, comp_b: float, rarity: str) -> dict:
    """
    合成完整度計算 (結果還沒擲加倍)：新完整度 = 較高的那張 + 增幅
    - 增幅上限依較低那張的位數：0.x ➔ 0.2、0.0x ➔ 0.05、0.00x ➔ 0.01、0.000x ➔ 0.005
    - 相對差距 d = |a - b| / 較高那張 (0 = 一模一樣)，越接近越划算
    - 增幅 = 上限 × (1 - d)；加倍機率 = 階級機率 × (1 - d)²
    - 增幅至少 0.0001 (保證新卡一定比兩張都高)，新完整度不超過 1.0000
    """
    a, b = round(comp_a, 4), round(comp_b, 4)
    low, high = min(a, b), max(a, b)
    cap = next(c for floor, c in SYNTHESIS_CAPS if low >= floor)
    d = (high - low) / high if high > 0 else 0.0

    def apply(increase: float) -> tuple[float, float]:
        new = round(min(1.0, high + max(0.0001, round(increase, 4))), 4)
        return new, round(new - high, 4)   # 實際增幅 (被 1.0000 封頂時會變小)

    normal, normal_inc = apply(cap * (1 - d))
    doubled, doubled_inc = apply(cap * (1 - d) * 2)
    return {
        "normal_completeness": normal,
        "normal_increase": normal_inc,
        "doubled_completeness": doubled,
        "doubled_increase": doubled_inc,
        "double_chance": SYNTHESIS_DOUBLE_CHANCE.get(rarity, 0.0) * (1 - d) ** 2,
    }


def roll_synthesis(comp_a: float, comp_b: float, rarity: str) -> dict:
    """擲加倍，回傳最終結果 {"new_completeness", "increase", "doubled"}"""
    calc = calc_synthesis(comp_a, comp_b, rarity)
    doubled = random.random() < calc["double_chance"]
    key = "doubled" if doubled else "normal"
    return {
        "new_completeness": calc[f"{key}_completeness"],
        "increase": calc[f"{key}_increase"],
        "doubled": doubled,
    }


def get_next_rarity(card: dict) -> str | None:
    """依卡池中該角色的三個階級找出高一階；已是最高階或角色不在卡池 ➔ None"""
    char_data = GACHA_POOL.get(card["character_key"])
    if not char_data or card["rarity"] not in char_data["rarities"]:
        return None
    idx = char_data["rarities"].index(card["rarity"])
    if idx + 1 >= len(char_data["rarities"]):
        return None
    return char_data["rarities"][idx + 1]


def find_fusion_groups(cards: list) -> dict:
    """{(角色, 階級): [滿完整度的卡, ...]}，只留下張數足夠且還能升階的組合"""
    groups = {}
    for card in cards:
        if is_perfect(card) and get_next_rarity(card):
            groups.setdefault((card["character_key"], card["rarity"]), []).append(card)
    return {k: v for k, v in groups.items() if len(v) >= FUSION_COUNT}


def _card_choice_name(card: dict) -> str:
    name = f"{card.get('emoji', '🎴')} [{card['rarity']}] {card['name']} · {card['completeness']:.4f} · {card['instance_id']}"
    return name[:100]


def _match_current(card: dict, current: str) -> bool:
    current = current.strip().lower()
    if not current:
        return True
    return any(current in str(card.get(k, "")).lower() for k in ("name", "instance_id", "title", "rarity", "character_key"))


# ================= 🎛️ 抽卡結果 View (Components V2) =================
class GachaResultView(ui.LayoutView):
    def __init__(self, user_id: int, user_name: str, gacha_cog, container: ui.Container):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog

        single_btn = ui.Button(label="🌸 繼續單抽 (2,000)", style=discord.ButtonStyle.primary)
        single_btn.callback = self.draw_single_again
        ten_btn = ui.Button(label="⛩️ 繼續十連 (20,000)", style=discord.ButtonStyle.success)
        ten_btn.callback = self.draw_ten_again
        inv_btn = ui.Button(label="🎒 查看卡庫", style=discord.ButtonStyle.secondary)
        inv_btn.callback = self.view_inventory

        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(single_btn, ten_btn, inv_btn))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的祈願畫面！請輸入 `/card gacha` 開啟你自己的祈願。")
            return False
        return True

    async def draw_single_again(self, interaction: discord.Interaction):
        await self.gacha_cog.execute_gacha(interaction, draw_count=1)

    async def draw_ten_again(self, interaction: discord.Interaction):
        await self.gacha_cog.execute_gacha(interaction, draw_count=10)

    async def view_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cards = await get_user_cards(self.user_id)
        if not cards:
            await send_notice(interaction, "🎒 你的卡冊空空如也，快進行祈願吧！")
            return

        inv_view = InventoryView(self.user_id, sort_cards(cards), self.user_name, self.gacha_cog)
        await interaction.edit_original_response(view=inv_view)


# ================= 🎒 背包互動 View (Components V2) =================
class InventoryView(ui.LayoutView):
    def __init__(self, user_id: int, cards: list, user_name: str, gacha_cog):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.all_cards = sort_cards(cards)
        self.current_filter = "ALL"
        self.filtered_cards = self.all_cards
        self.current_page = 1
        self.per_page = INVENTORY_PER_PAGE
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
        """依目前狀態 (卡冊列表 / 單卡詳情) 重新組出整個畫面"""
        self.clear_items()

        # ---- 單卡詳情 ----
        if self.selected_card:
            container = build_card_detail_container(self.selected_card, self.user_name, THUMBNAILS)
            back_btn = ui.Button(label="🔙 返回卡冊", style=discord.ButtonStyle.secondary)
            back_btn.callback = self.back_button_callback
            container.add_item(ui.Separator())
            container.add_item(ui.ActionRow(back_btn))
            self.add_item(container)
            return

        # ---- 卡冊列表 ----
        container = build_card_inventory_container(
            self.get_current_page_cards(),
            self.current_page,
            self.total_pages,
            len(self.all_cards),
            self.all_cards,
            self.user_name,
            THUMBNAILS,
            self.per_page,
        )
        container.add_item(ui.Separator())

        filter_options = [
            discord.SelectOption(label="全部階級 (ALL)", value="ALL", default=(self.current_filter == "ALL")),
            discord.SelectOption(label="N 階級", value="N", default=(self.current_filter == "N")),
            discord.SelectOption(label="R 階級", value="R", default=(self.current_filter == "R")),
            discord.SelectOption(label="SR 階級", value="SR", default=(self.current_filter == "SR")),
            discord.SelectOption(label="SSR 階級", value="SSR", default=(self.current_filter == "SSR")),
            discord.SelectOption(label="UR 階級", value="UR", default=(self.current_filter == "UR")),
            discord.SelectOption(label="LR 階級", value="LR", default=(self.current_filter == "LR")),
        ]
        filter_select = ui.Select(placeholder="🔍 選擇稀有度篩選...", options=filter_options)
        filter_select.callback = self.filter_select_callback
        container.add_item(ui.ActionRow(filter_select))

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
            card_select = ui.Select(placeholder="🎴 選擇卡牌檢視詳細鑑定...", options=card_options)
            card_select.callback = self.card_select_callback
            container.add_item(ui.ActionRow(card_select))

        prev_btn = ui.Button(label="◀️ 上一頁", style=discord.ButtonStyle.primary, disabled=(self.current_page <= 1))
        prev_btn.callback = self.prev_page_callback
        page_btn = ui.Button(label=f"📄 {self.current_page} / {self.total_pages} 頁", style=discord.ButtonStyle.secondary, disabled=True)
        next_btn = ui.Button(label="下一頁 ▶️", style=discord.ButtonStyle.primary, disabled=(self.current_page >= self.total_pages))
        next_btn.callback = self.next_page_callback
        container.add_item(ui.ActionRow(prev_btn, page_btn, next_btn))

        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的卡冊！")
            return False
        return True

    async def filter_select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        select_val = interaction.data["values"][0]
        self.current_filter = select_val
        self.filtered_cards = self.all_cards if select_val == "ALL" else [c for c in self.all_cards if c.get("rarity") == select_val]
        self.current_page = 1
        self.update_components()
        await interaction.edit_original_response(view=self)

    async def card_select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        instance_id = interaction.data["values"][0]
        card = next((c for c in self.all_cards if c["instance_id"] == instance_id), None)
        if card:
            self.selected_card = card
            self.update_components()
            await interaction.edit_original_response(view=self)

    async def back_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.selected_card = None
        self.update_components()
        await interaction.edit_original_response(view=self)

    async def prev_page_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.current_page > 1:
            self.current_page -= 1
            self.update_components()
            await interaction.edit_original_response(view=self)

    async def next_page_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_components()
            await interaction.edit_original_response(view=self)


# ================= ✅ 合成 / 融合確認 View (Components V2) =================
class CardActionConfirmView(ui.LayoutView):
    """
    確認畫面：按「確認」才真的消耗卡牌。
    on_confirm(interaction) 回傳結果 Container；失敗時回傳 str (錯誤訊息)。
    """
    def __init__(self, user_id: int, user_name: str, gacha_cog, container: ui.Container, on_confirm, confirm_label: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.on_confirm = on_confirm
        self.done = False

        confirm_btn = ui.Button(label=confirm_label, style=discord.ButtonStyle.success)
        confirm_btn.callback = self.confirm_callback
        cancel_btn = ui.Button(label="✖️ 取消", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = self.cancel_callback

        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(confirm_btn, cancel_btn))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的卡牌！")
            return False
        return True

    async def confirm_callback(self, interaction: discord.Interaction):
        if self.done:   # 連點：第二下直接忽略
            await interaction.response.defer()
            return
        self.done = True
        await interaction.response.defer()

        result = await self.on_confirm(interaction)
        if isinstance(result, str):
            container = ui.Container(accent_color=discord.Color.red())
            container.add_item(ui.TextDisplay(result))
        else:
            container = result

        inv_btn = ui.Button(label="🎒 查看卡庫", style=discord.ButtonStyle.secondary)
        inv_btn.callback = self.view_inventory
        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(inv_btn))
        self.clear_items()
        self.add_item(container)
        await interaction.edit_original_response(view=self)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.done = True
        self.clear_items()
        container = ui.Container(accent_color=discord.Color.dark_grey())
        container.add_item(ui.TextDisplay("✖️ 已取消，卡牌沒有任何變動。"))
        self.add_item(container)
        await interaction.response.edit_message(view=self)
        self.stop()

    async def view_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cards = await get_user_cards(self.user_id)
        if not cards:
            await send_notice(interaction, "🎒 你的卡冊空空如也，快進行祈願吧！")
            return
        inv_view = InventoryView(self.user_id, sort_cards(cards), self.user_name, self.gacha_cog)
        await interaction.edit_original_response(view=inv_view)


# ================= 🎴 Cog 類別 =================
class GachaCardSys(commands.GroupCog, group_name="card", group_description="東方角色卡牌收集與合成系統"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def generate_completeness(self) -> float:
        val = (random.gauss(0, 0.35)) ** 2
        return round(max(0.001, min(1.000, val)), 4)

    async def execute_gacha(self, interaction: discord.Interaction, draw_count: int):
        await interaction.response.defer()

        # 卡池沒載入時直接中止，避免「賽錢已扣、卻抽不到卡」
        if not GACHA_POOL:
            await send_notice(interaction, "❌ 卡池資料 `Gacha_Pool.json` 載入失敗，暫時無法祈願，請聯絡管理員。")
            return

        user_id = interaction.user.id
        total_cost = draw_count * 2000

        user_db = await get_or_create_user(user_id)
        current_money = user_db.get("money", 0)

        if current_money < total_cost:
            msg = f"❌ **賽錢不足！**\n祈願需要 `{total_cost:,}` 賽錢，但你的口袋裡只有 `{current_money:,}` 賽錢...\n*靈夢看了看空蕩蕩的賽錢箱，無奈地把你請出了神社。*"
            await send_notice(interaction, msg)
            return

        await add_money(user_id, -total_cost)

        results = []
        char_keys = list(GACHA_POOL.keys())

        for _ in range(draw_count):
            char_key = random.choice(char_keys)
            char_data = GACHA_POOL[char_key]
            
            rarity = random.choices(char_data["rarities"], weights=[75, 22, 3], k=1)[0]
            title = char_data["titles"][rarity]
            
            new_card = {
                "instance_id": f"c_{char_data['uuid'][:4]}_{uuid.uuid4().hex[:12]}",
                "character_key": char_key,
                "name": char_data["name"],
                "emoji": char_data["emoji"],
                "rarity": rarity,
                "title": title,
                "completeness": self.generate_completeness(),
                "obtained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            results.append(new_card)

        # 卡牌與抽卡統計一起寫入 Users.db (同一個交易)
        await add_gacha_cards(user_id, results, draw_count)

        if draw_count == 1:
            container = build_gacha_single_container(
                results[0], interaction.user.display_name, total_cost, THUMBNAILS
            )
        else:
            container = build_gacha_ten_container(
                results, interaction.user.display_name, total_cost, THUMBNAILS
            )

        view = GachaResultView(user_id, interaction.user.display_name, self, container)

        if interaction.type == discord.InteractionType.component:
            await interaction.edit_original_response(view=view)
        else:
            await interaction.followup.send(view=view)

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
        cards = await get_user_cards(user_id)

        if not cards:
            await send_notice(interaction, "🎒 你的卡冊空空如也，快去使用 `/card gacha` 進行第一次祈願吧！")
            return

        view = InventoryView(user_id, sort_cards(cards), interaction.user.display_name, self)
        await interaction.followup.send(view=view)

    # ---------------- ⚗️ 合成 ----------------
    async def synthesis_card1_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """第一張：只列出「卡冊裡至少有另一張可以一起合成」的卡"""
        cards = sort_cards(await get_user_cards(interaction.user.id))
        choices = []
        for card in cards:
            if not _match_current(card, current):
                continue
            if any(can_synthesize(card, other) for other in cards):
                choices.append(app_commands.Choice(name=_card_choice_name(card), value=card["instance_id"]))
            if len(choices) >= AUTOCOMPLETE_LIMIT:
                break
        return choices

    async def synthesis_card2_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """第二張：依已選的第一張篩選 (同角色、同階級、排除第一張本身)；還沒選第一張時跟第一張一樣"""
        first_id = getattr(interaction.namespace, "card1", None)
        cards = sort_cards(await get_user_cards(interaction.user.id))
        first = next((c for c in cards if c["instance_id"] == first_id), None)
        if first is None:
            return await self.synthesis_card1_autocomplete(interaction, current)

        choices = []
        for card in cards:
            if _match_current(card, current) and can_synthesize(first, card):
                choices.append(app_commands.Choice(name=_card_choice_name(card), value=card["instance_id"]))
            if len(choices) >= AUTOCOMPLETE_LIMIT:
                break
        return choices

    @app_commands.command(name="synthesis", description="⚗️ 合成卡牌：兩張同角色、同階級的卡合成一張完整度更高的卡")
    @app_commands.describe(card1="第一張素材卡", card2="第二張素材卡 (會依第一張自動篩選)")
    @app_commands.autocomplete(card1=synthesis_card1_autocomplete, card2=synthesis_card2_autocomplete)
    async def synthesis(self, interaction: discord.Interaction, card1: str, card2: str):
        user_id = interaction.user.id
        user_name = interaction.user.display_name
        cards = {c["instance_id"]: c for c in await get_user_cards(user_id)}
        card_a, card_b = cards.get(card1), cards.get(card2)

        # 使用者也可能不透過 autocomplete 直接輸入，所以這裡一樣要檢查
        if card_a is None or card_b is None:
            await send_notice(interaction, "❌ 找不到指定的卡牌，請從選單中選擇你卡冊裡的卡。")
            return
        if not can_synthesize(card_a, card_b):
            await send_notice(interaction, "❌ **無法合成！**\n合成需要兩張「不同的」、「同角色」、「同階級」的卡牌，且完整度都未達 `1.0000`。")
            return

        preview = calc_synthesis(card_a["completeness"], card_b["completeness"], card_a["rarity"])
        container = build_synthesis_preview_container(card_a, card_b, preview, user_name, THUMBNAILS)

        def build_new_card(consumed: list) -> dict:
            a, b = consumed
            if not can_synthesize(a, b):
                raise ValueError("卡牌狀態已改變，無法合成")
            result = roll_synthesis(a["completeness"], b["completeness"], a["rarity"])
            prefix = a["instance_id"].split("_")[1]
            return {
                "instance_id": f"c_{prefix}_{uuid.uuid4().hex[:12]}",
                "character_key": a["character_key"],
                "name": a["name"],
                "emoji": a["emoji"],
                "rarity": a["rarity"],
                "title": a["title"],
                "completeness": result["new_completeness"],
                "obtained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "_result": result,
            }

        async def on_confirm(_interaction: discord.Interaction):
            try:
                _, new_card = await transform_cards(user_id, [card1, card2], build_new_card)
            except ValueError as e:
                return f"❌ **合成失敗**：{e}\n-# 卡牌沒有任何變動。"
            result = new_card.pop("_result")
            return build_synthesis_result_container(new_card, result["increase"], result["doubled"], user_name, THUMBNAILS)

        view = CardActionConfirmView(user_id, user_name, self, container, on_confirm, "⚗️ 確認合成")
        await interaction.response.send_message(view=view)

    # ---------------- 🔮 融合 ----------------
    async def fusion_target_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """只列出「有 3 張以上 1.0000 且還能升階」的角色＋階級"""
        groups = find_fusion_groups(await get_user_cards(interaction.user.id))
        choices = []
        for (char_key, rarity), group in sorted(groups.items(), key=lambda kv: (RARITY_ORDER.get(kv[0][1], 0), kv[0][0])):
            sample = group[0]
            if not _match_current(sample, current):
                continue
            name = (
                f"{sample.get('emoji', '🎴')} {sample['name']} [{rarity} → {get_next_rarity(sample)}]"
                f" · 持有 {len(group)} 張 1.0000"
            )
            choices.append(app_commands.Choice(name=name[:100], value=f"{char_key}|{rarity}"))
            if len(choices) >= AUTOCOMPLETE_LIMIT:
                break
        return choices

    @app_commands.command(name="fusion", description="🔮 融合卡牌：三張同角色、同階級且完整度 1.0000 的卡融合成高一階的卡")
    @app_commands.describe(target="要融合的角色與階級 (只會列出符合條件的組合)")
    @app_commands.autocomplete(target=fusion_target_autocomplete)
    async def fusion(self, interaction: discord.Interaction, target: str):
        user_id = interaction.user.id
        user_name = interaction.user.display_name
        char_key, _, rarity = target.partition("|")
        group = find_fusion_groups(await get_user_cards(user_id)).get((char_key, rarity))

        if not group:
            await send_notice(interaction, f"❌ **無法融合！**\n融合需要 **{FUSION_COUNT}** 張「同角色」、「同階級」且完整度 `1.0000` 的卡牌，"
                f"而且該角色必須還有更高的階級。")
            return

        materials = group[:FUSION_COUNT]   # 滿完整度的卡都一樣，取最早獲得的三張
        material_ids = [c["instance_id"] for c in materials]
        next_rarity = get_next_rarity(materials[0])
        next_title = GACHA_POOL[char_key]["titles"][next_rarity]
        container = build_fusion_preview_container(materials, next_rarity, next_title, user_name, THUMBNAILS)

        def build_new_card(consumed: list) -> dict:
            base = consumed[0]
            if not all(
                is_perfect(c) and c["character_key"] == base["character_key"] and c["rarity"] == base["rarity"]
                for c in consumed
            ):
                raise ValueError("卡牌狀態已改變，無法融合")
            new_rarity = get_next_rarity(base)
            if new_rarity is None:
                raise ValueError("這張卡已經是最高階級")
            char_data = GACHA_POOL[base["character_key"]]
            return {
                "instance_id": f"c_{char_data['uuid'][:4]}_{uuid.uuid4().hex[:12]}",
                "character_key": base["character_key"],
                "name": char_data["name"],
                "emoji": char_data["emoji"],
                "rarity": new_rarity,
                "title": char_data["titles"][new_rarity],
                "completeness": self.generate_completeness(),
                "obtained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        async def on_confirm(_interaction: discord.Interaction):
            try:
                _, new_card = await transform_cards(user_id, material_ids, build_new_card, count_fusion=True)
            except ValueError as e:
                return f"❌ **融合失敗**：{e}\n-# 卡牌沒有任何變動。"
            return build_fusion_result_container(new_card, rarity, user_name, THUMBNAILS)

        view = CardActionConfirmView(user_id, user_name, self, container, on_confirm, "🔮 確認融合")
        await interaction.response.send_message(view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCardSys(bot))
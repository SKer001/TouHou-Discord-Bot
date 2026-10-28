import discord
from discord import ui
from discord.ext import commands
from discord import app_commands
import json
import os
import random
import uuid
from datetime import datetime

from Database.User_DB_Manager import (
    get_user_cards, transform_cards, draw_gacha, get_gacha_pity, get_gacha_stats, InsufficientFunds,
)
from .Components.gacha_components import (
    STACKS_PER_PAGE,
    STACK_CARDS_PER_PAGE,
    build_gacha_single_container,
    build_gacha_ten_container,
    build_gacha_history_container,
    build_stack_list_container,
    build_stack_cards_container,
    build_card_detail_container,
    build_synthesis_preview_container,
    build_synthesis_result_container,
    build_fusion_preview_container,
    build_fusion_result_container,
)
from Utils.components import send_notice
from Utils.character_data import load_categories

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
THUMBNAILS_FILE = os.path.join(PROJECT_ROOT, "images", "Thumbnails.json")

# 🎰 卡池依代數劃分：每個卡池包含哪些 Characters/ 分類資料夾
#    新增卡池 ➔ 在這裡加一筆，並把角色檔放進對應資料夾即可
GACHA_POOLS = {
    "classic": {"name": "📜 舊作卡池", "desc": "主要主角 + TH01 ~ TH05", "folders": ["Main", "TH01", "TH02", "TH03", "TH04", "TH05"]},
    "th06":    {"name": "🔴 紅魔鄉卡池", "desc": "TH06 東方紅魔鄉", "folders": ["TH06"]},
}


def load_gacha_pool() -> dict:
    """
    從 Characters/ 讀取 gacha.enabled 的角色：
    {"角色id": {"name", "emoji", "uuid", "rarities", "titles", "pool"}, ...}
    """
    folder_to_pool = {folder: key for key, pool in GACHA_POOLS.items() for folder in pool["folders"]}
    result = {}
    for folder, category in load_categories().items():
        pool_key = folder_to_pool.get(folder)
        for char in category["characters"]:
            gacha = char["gacha"]
            if pool_key is None or not gacha.get("enabled"):
                continue
            result[char["id"]] = {
                "name": char["name"],
                "emoji": char["emoji"],
                "uuid": gacha["uuid"],
                "rarities": gacha["rarities"],
                "titles": gacha["titles"],
                "pool": pool_key,
            }
    return result


# 角色資料在載入 Cog 時讀取一次；改了 Characters/ 之後用 /admin-sys reload 重新載入本模組
GACHA_POOL = load_gacha_pool()
if not GACHA_POOL:
    print("❌ [Gacha Error] Characters/ 中沒有任何可祈願的角色")

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


# ================= ⛩️ 祈願規則 =================
DRAW_COST = 2000                 # 每抽賽錢
RARITY_WEIGHTS = [75, 22, 3]     # 角色三個階級 (低 ➔ 高) 的權重
PITY_THRESHOLD = 100             # 每個卡池連續 100 抽沒出 UR ➔ 第 100 抽必出 UR
PITY_RARITY = "UR"
PITY_RESET_RARITIES = {"UR", "LR"}   # 抽到這些階級就重置保底計數


def roll_pool_cards(pool_key: str, count: int, since_ur: int, make_completeness) -> tuple[list, int, bool]:
    """
    依保底計數擲出 count 張卡：(cards, 新的 since_ur, 是否出了 UR 以上)
    觸發保底的卡會帶 "pity": True (只用於顯示，不寫入資料庫)
    """
    char_keys = [k for k, v in GACHA_POOL.items() if v["pool"] == pool_key]
    pity_keys = [k for k in char_keys if PITY_RARITY in GACHA_POOL[k]["rarities"]]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cards, got_ur = [], False

    for _ in range(count):
        since_ur += 1
        char_key = random.choice(char_keys)
        rarity = random.choices(GACHA_POOL[char_key]["rarities"], weights=RARITY_WEIGHTS, k=1)[0]
        pity = False
        if rarity not in PITY_RESET_RARITIES and since_ur >= PITY_THRESHOLD and pity_keys:
            char_key, rarity, pity = random.choice(pity_keys), PITY_RARITY, True
        if rarity in PITY_RESET_RARITIES:
            since_ur, got_ur = 0, True

        char_data = GACHA_POOL[char_key]
        cards.append({
            "instance_id": f"c_{char_data['uuid'][:4]}_{uuid.uuid4().hex[:12]}",
            "character_key": char_key,
            "name": char_data["name"],
            "emoji": char_data["emoji"],
            "rarity": rarity,
            "title": char_data["titles"][rarity],
            "completeness": make_completeness(),
            "obtained_at": now,
            "pity": pity,
        })
    return cards, since_ur, got_ur


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


# ================= 🎛️ 抽卡結果 View (Components V2) =================
class GachaResultView(ui.LayoutView):
    def __init__(self, user_id: int, user_name: str, gacha_cog, container: ui.Container, pool_key: str):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.pool_key = pool_key   # 「繼續祈願」沿用同一個卡池

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
        await self.gacha_cog.execute_gacha(interaction, draw_count=1, pool_key=self.pool_key)

    async def draw_ten_again(self, interaction: discord.Interaction):
        await self.gacha_cog.execute_gacha(interaction, draw_count=10, pool_key=self.pool_key)

    async def view_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cards = await get_user_cards(self.user_id)
        if not cards:
            await send_notice(interaction, "🎒 你的卡冊空空如也，快進行祈願吧！")
            return

        inv_view = InventoryView(self.user_id, sort_cards(cards), self.user_name, self.gacha_cog)
        await interaction.edit_original_response(view=inv_view)


# ================= 🎒 卡冊 View (Components V2) =================
# 疊卡排序方式：(key, 顯示名稱)；排序按鈕依序切換
INVENTORY_SORTS = [("rarity", "階級"), ("best", "完整度"), ("latest", "最新"), ("count", "數量")]
RARITY_FILTERS = ["ALL", "N", "R", "SR", "SSR", "UR", "LR"]
OTHER_POOL = "other"   # 角色已不在任何卡池中的卡


def card_pool_key(card: dict) -> str:
    return GACHA_POOL.get(card["character_key"], {}).get("pool", OTHER_POOL)


def build_stacks(cards: list) -> list[dict]:
    """同角色、同階級的卡疊成一疊；疊內依完整度由高到低"""
    stacks = {}
    for card in cards:
        stack = stacks.setdefault((card["character_key"], card["rarity"]), {
            "character_key": card["character_key"],
            "rarity": card["rarity"],
            "name": card["name"],
            "emoji": card.get("emoji", "🎴"),
            "title": card.get("title", ""),
            "pool": card_pool_key(card),
            "cards": [],
        })
        stack["cards"].append(card)
    for stack in stacks.values():
        stack["cards"].sort(key=lambda c: c["completeness"], reverse=True)
        stack["best"] = stack["cards"][0]["completeness"]
        stack["latest"] = max(c.get("obtained_at") or "" for c in stack["cards"])
        # 卡冊上的合成 / 融合提示 (與 find_synthesis_groups / find_fusion_groups 條件相同)
        stack["can_synth"] = sum(1 for c in stack["cards"] if not is_perfect(c)) >= 2
        stack["can_fuse"] = (
            sum(1 for c in stack["cards"] if is_perfect(c)) >= FUSION_COUNT
            and get_next_rarity(stack["cards"][0]) is not None
        )
    return list(stacks.values())


def collection_progress(cards: list) -> list[tuple[dict, int, int]]:
    """各卡池的收集進度：[(卡池設定, 已擁有角色數, 卡池角色數), ...]"""
    owned = {c["character_key"] for c in cards}
    result = []
    for key, pool in GACHA_POOLS.items():
        members = [k for k, v in GACHA_POOL.items() if v["pool"] == key]
        result.append((pool, sum(1 for k in members if k in owned), len(members)))
    return result


def sort_stacks(stacks: list, mode: str) -> list:
    if mode == "best":
        return sorted(stacks, key=lambda s: (-s["best"], s["character_key"]))
    if mode == "latest":
        return sorted(stacks, key=lambda s: s["latest"], reverse=True)
    if mode == "count":
        return sorted(stacks, key=lambda s: (-len(s["cards"]), -RARITY_ORDER.get(s["rarity"], 0), s["character_key"]))
    # 預設：階級由高到低，同階級依角色
    return sorted(stacks, key=lambda s: (-RARITY_ORDER.get(s["rarity"], 0), s["character_key"]))


def _stack_value(stack: dict) -> str:
    return f"{stack['character_key']}|{stack['rarity']}"


class InventoryView(ui.LayoutView):
    """
    卡冊：同一個 View 依狀態切換三種畫面
      疊卡列表 (卡池 / 階級篩選 + 排序) ➔ 單一疊的卡牌列表 ➔ 單卡詳情
    """
    def __init__(self, user_id: int, cards: list, user_name: str, gacha_cog, owner_id: int | None = None):
        super().__init__(timeout=180)
        self.user_id = user_id                       # 操作畫面的人
        self.owner_id = owner_id or user_id          # 卡冊的主人 (管理員檢視別人卡冊時不同)
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.all_cards = cards
        self.all_stacks = build_stacks(cards)

        self.pool_filter = "ALL"
        self.rarity_filter = "ALL"
        self.sort_index = 0
        self.page = 1

        self.selected_stack = None   # 疊的 value ("角色|階級")
        self.stack_page = 1
        self.selected_card = None
        self.build()

    # ---------------- 資料 ----------------
    @property
    def sort_mode(self) -> str:
        return INVENTORY_SORTS[self.sort_index][0]

    def filtered_stacks(self) -> list:
        stacks = [
            s for s in self.all_stacks
            if (self.pool_filter == "ALL" or s["pool"] == self.pool_filter)
            and (self.rarity_filter == "ALL" or s["rarity"] == self.rarity_filter)
        ]
        return sort_stacks(stacks, self.sort_mode)

    def get_stack(self, value: str) -> dict | None:
        return next((s for s in self.all_stacks if _stack_value(s) == value), None)

    @staticmethod
    def _pages(count: int, per_page: int) -> int:
        return max(1, (count + per_page - 1) // per_page)

    def _filter_desc(self) -> str:
        pool = "全部卡池" if self.pool_filter == "ALL" else GACHA_POOLS.get(self.pool_filter, {}).get("name", "📦 其他")
        rarity = "全部階級" if self.rarity_filter == "ALL" else f"{self.rarity_filter} 階級"
        return f"篩選：{pool} · {rarity} · 排序：{INVENTORY_SORTS[self.sort_index][1]}"

    def _progress_text(self) -> str:
        return " · ".join(
            f"{p['name']} `{owned}/{total}`" for p, owned, total in collection_progress(self.all_cards)
        )

    # ---------------- 畫面 ----------------
    def build(self):
        self.clear_items()
        if self.selected_card:
            self._build_card_detail()
        elif self.selected_stack:
            self._build_stack()
        else:
            self._build_list()

    def _button(self, label: str, callback, style=discord.ButtonStyle.primary, disabled: bool = False) -> ui.Button:
        btn = ui.Button(label=label, style=style, disabled=disabled)
        if callback is not None:   # 頁碼按鈕只是顯示用，沒有回呼
            btn.callback = callback
        return btn

    def _build_list(self):
        stacks = self.filtered_stacks()
        total_pages = self._pages(len(stacks), STACKS_PER_PAGE)
        self.page = min(self.page, total_pages)
        start = (self.page - 1) * STACKS_PER_PAGE
        page_stacks = stacks[start:start + STACKS_PER_PAGE]

        container = build_stack_list_container(
            page_stacks, self.page, total_pages, len(stacks), self.all_cards,
            self.user_name, THUMBNAILS, self._filter_desc(), start + 1, self._progress_text(),
        )
        container.add_item(ui.Separator())

        # 卡池篩選
        pool_options = [discord.SelectOption(label="全部卡池 (ALL)", value="ALL", default=(self.pool_filter == "ALL"))]
        pool_options += [
            discord.SelectOption(label=p["name"], value=key, description=p["desc"][:100], default=(self.pool_filter == key))
            for key, p in GACHA_POOLS.items()
        ]
        if any(s["pool"] == OTHER_POOL for s in self.all_stacks):
            pool_options.append(discord.SelectOption(label="📦 其他 (已不在卡池)", value=OTHER_POOL, default=(self.pool_filter == OTHER_POOL)))
        pool_select = ui.Select(placeholder="🎰 選擇卡池篩選...", options=pool_options)
        pool_select.callback = self.pool_select_callback
        container.add_item(ui.ActionRow(pool_select))

        # 階級篩選
        rarity_select = ui.Select(placeholder="🔍 選擇稀有度篩選...", options=[
            discord.SelectOption(label="全部階級 (ALL)" if r == "ALL" else f"{r} 階級", value=r, default=(self.rarity_filter == r))
            for r in RARITY_FILTERS
        ])
        rarity_select.callback = self.rarity_select_callback
        container.add_item(ui.ActionRow(rarity_select))

        # 當頁的疊 ➔ 點進去看這一疊的卡
        if page_stacks:
            stack_select = ui.Select(placeholder="🎴 選擇一疊卡牌查看內容...", options=[
                discord.SelectOption(
                    label=f"[{s['rarity']}] {s['name']} ×{len(s['cards'])}"[:100],
                    description=f"{s['title']} · 最高 {s['best']:.4f}"[:100],
                    value=_stack_value(s),
                    emoji=s.get("emoji") or "🎴",
                )
                for s in page_stacks
            ])
            stack_select.callback = self.stack_select_callback
            container.add_item(ui.ActionRow(stack_select))

        container.add_item(ui.ActionRow(
            self._button("◀️ 上一頁", self.prev_page_callback, disabled=(self.page <= 1)),
            self._button(f"📄 {self.page} / {total_pages} 頁", None, discord.ButtonStyle.secondary, disabled=True),
            self._button("下一頁 ▶️", self.next_page_callback, disabled=(self.page >= total_pages)),
            self._button(f"🔃 排序：{INVENTORY_SORTS[self.sort_index][1]}", self.sort_callback, discord.ButtonStyle.secondary),
        ))
        self.add_item(container)

    def _build_stack(self):
        stack = self.get_stack(self.selected_stack)
        cards = stack["cards"]
        total_pages = self._pages(len(cards), STACK_CARDS_PER_PAGE)
        self.stack_page = min(self.stack_page, total_pages)
        start = (self.stack_page - 1) * STACK_CARDS_PER_PAGE
        page_cards = cards[start:start + STACK_CARDS_PER_PAGE]

        container = build_stack_cards_container(
            stack, page_cards, self.stack_page, total_pages, self.user_name, THUMBNAILS, start + 1
        )
        container.add_item(ui.Separator())

        card_select = ui.Select(placeholder="🎴 選擇卡牌檢視詳細鑑定...", options=[
            discord.SelectOption(
                label=f"{start + i}. 完整度 {c['completeness']:.4f}",
                description=f"ID: {c['instance_id']}"[:100],
                value=c["instance_id"],
                emoji=c.get("emoji") or "🎴",
            )
            for i, c in enumerate(page_cards, start=1)
        ])
        card_select.callback = self.card_select_callback
        container.add_item(ui.ActionRow(card_select))

        container.add_item(ui.ActionRow(
            self._button("🔙 返回卡冊", self.back_to_list_callback, discord.ButtonStyle.secondary),
            self._button("◀️ 上一頁", self.stack_prev_callback, disabled=(self.stack_page <= 1)),
            self._button(f"📄 {self.stack_page} / {total_pages} 頁", None, discord.ButtonStyle.secondary, disabled=True),
            self._button("下一頁 ▶️", self.stack_next_callback, disabled=(self.stack_page >= total_pages)),
        ))

        # 合成 / 融合捷徑：只有卡冊主人本人看得到 (管理員檢視別人卡冊時不顯示)
        if self.user_id == self.owner_id and (stack["can_synth"] or stack["can_fuse"]):
            shortcuts = []
            if stack["can_synth"]:
                shortcuts.append(self._button("⚗️ 合成這一疊", self.synth_shortcut_callback, discord.ButtonStyle.success))
            if stack["can_fuse"]:
                shortcuts.append(self._button(
                    f"🔮 融合 ➔ {get_next_rarity(stack['cards'][0])}", self.fuse_shortcut_callback, discord.ButtonStyle.success
                ))
            container.add_item(ui.ActionRow(*shortcuts))
        self.add_item(container)

    def _build_card_detail(self):
        container = build_card_detail_container(self.selected_card, self.user_name, THUMBNAILS)
        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(
            self._button("🔙 返回這一疊", self.back_to_stack_callback, discord.ButtonStyle.secondary),
            self._button("🎒 返回卡冊", self.back_to_list_callback, discord.ButtonStyle.secondary),
        ))
        self.add_item(container)

    # ---------------- 互動 ----------------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的卡冊！")
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def pool_select_callback(self, interaction: discord.Interaction):
        self.pool_filter = interaction.data["values"][0]
        self.page = 1
        await self.refresh(interaction)

    async def rarity_select_callback(self, interaction: discord.Interaction):
        self.rarity_filter = interaction.data["values"][0]
        self.page = 1
        await self.refresh(interaction)

    async def sort_callback(self, interaction: discord.Interaction):
        self.sort_index = (self.sort_index + 1) % len(INVENTORY_SORTS)
        self.page = 1
        await self.refresh(interaction)

    async def prev_page_callback(self, interaction: discord.Interaction):
        self.page = max(1, self.page - 1)
        await self.refresh(interaction)

    async def next_page_callback(self, interaction: discord.Interaction):
        self.page += 1   # build() 會把頁數限制在範圍內
        await self.refresh(interaction)

    async def stack_select_callback(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        if self.get_stack(value) is None:
            await send_notice(interaction, "❌ 找不到這一疊卡牌，請重新開啟 `/card inventory`。")
            return
        self.selected_stack = value
        self.stack_page = 1
        await self.refresh(interaction)

    async def stack_prev_callback(self, interaction: discord.Interaction):
        self.stack_page = max(1, self.stack_page - 1)
        await self.refresh(interaction)

    async def stack_next_callback(self, interaction: discord.Interaction):
        self.stack_page += 1
        await self.refresh(interaction)

    async def card_select_callback(self, interaction: discord.Interaction):
        instance_id = interaction.data["values"][0]
        card = next((c for c in self.all_cards if c["instance_id"] == instance_id), None)
        if card is None:
            await send_notice(interaction, "❌ 找不到這張卡牌，請重新開啟 `/card inventory`。")
            return
        self.selected_card = card
        await self.refresh(interaction)

    async def back_to_stack_callback(self, interaction: discord.Interaction):
        self.selected_card = None
        await self.refresh(interaction)

    async def back_to_list_callback(self, interaction: discord.Interaction):
        self.selected_card = None
        self.selected_stack = None
        await self.refresh(interaction)

    async def synth_shortcut_callback(self, interaction: discord.Interaction):
        """從這一疊直接開啟合成選卡畫面 (重新讀取資料庫，避免用到已經用掉的卡)"""
        stack = self.get_stack(self.selected_stack)
        group = find_synthesis_groups(await get_user_cards(self.owner_id)).get((stack["character_key"], stack["rarity"]))
        if not group:
            await send_notice(interaction, "❌ 這一疊已經沒有可以合成的卡牌了，請重新開啟 `/card inventory`。")
            return
        self.stop()
        view = SynthesisPickerView(self.owner_id, self.user_name, self.gacha_cog, stack["character_key"], group)
        await interaction.response.edit_message(view=view)

    async def fuse_shortcut_callback(self, interaction: discord.Interaction):
        """從這一疊直接開啟融合確認畫面"""
        stack = self.get_stack(self.selected_stack)
        result = await self.gacha_cog.make_fusion_view(self.owner_id, self.user_name, stack["character_key"], stack["rarity"])
        if isinstance(result, str):
            await send_notice(interaction, result)
            return
        self.stop()
        await interaction.response.edit_message(view=result)


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


# ================= ⚗️ 合成選卡 View (Components V2) =================
SYNTH_PICK_PER_PAGE = 20   # 每頁張數 (選單最多 25 個選項)


def find_synthesis_groups(cards: list) -> dict:
    """{(角色, 階級): [未滿 1.0000 的卡, ...]}，只留下至少兩張 (可以互相合成) 的組合"""
    groups = {}
    for card in cards:
        if not is_perfect(card):
            groups.setdefault((card["character_key"], card["rarity"]), []).append(card)
    return {k: v for k, v in groups.items() if len(v) >= 2}


class SynthesisPickerView(ui.LayoutView):
    """
    合成選卡：選第一張 ➔ 選第二張 (只列出可以配對的) ➔ 交給 CardActionConfirmView 確認
    兩個步驟都可以分頁，解決 autocomplete 最多 25 個選項的限制
    """
    def __init__(self, user_id: int, user_name: str, gacha_cog, character_key: str, cards: list):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.character_key = character_key
        self.cards = sorted(cards, key=lambda c: (-RARITY_ORDER.get(c["rarity"], 0), -c["completeness"]))
        self.first = None   # 已選的第一張
        self.page = 1
        self.build()

    def _candidates(self) -> list:
        if self.first is None:
            return self.cards
        return [c for c in self.cards if can_synthesize(self.first, c)]

    def _button(self, label: str, callback, style=discord.ButtonStyle.primary, disabled: bool = False) -> ui.Button:
        btn = ui.Button(label=label, style=style, disabled=disabled)
        if callback is not None:
            btn.callback = callback
        return btn

    def build(self):
        self.clear_items()
        candidates = self._candidates()
        total_pages = max(1, (len(candidates) + SYNTH_PICK_PER_PAGE - 1) // SYNTH_PICK_PER_PAGE)
        self.page = min(self.page, total_pages)
        start = (self.page - 1) * SYNTH_PICK_PER_PAGE
        page_cards = candidates[start:start + SYNTH_PICK_PER_PAGE]

        sample = self.cards[0]
        if self.first is None:
            step = "**步驟 1 / 2**：選擇第一張素材卡"
        else:
            step = (
                f"**步驟 2 / 2**：選擇第二張素材卡\n"
                f"已選第一張：`[{self.first['rarity']}]` `{self.first['completeness']:.4f}` · `{self.first['instance_id']}`"
            )
        lines = "\n".join(
            f"**{i}.** `[{c['rarity']}]` `{c['completeness']:.4f}` · `{c['instance_id']}`"
            for i, c in enumerate(page_cards, start=start + 1)
        )

        container = ui.Container(accent_color=discord.Color.teal())
        container.add_item(ui.TextDisplay(
            f"## ⚗️ 卡牌合成：{sample.get('emoji', '🎴')} {sample['name']}\n{step}\n"
            f"-# 共 {len(candidates)} 張可選 · 依階級、完整度由高到低排列 · 兩張完整度越接近越划算"
        ))
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(lines))
        container.add_item(ui.Separator())

        select = ui.Select(
            placeholder="選擇第一張素材卡..." if self.first is None else "選擇第二張素材卡...",
            options=[
                discord.SelectOption(
                    label=f"{i}. [{c['rarity']}] {c['completeness']:.4f}",
                    description=c["instance_id"][:100],
                    value=c["instance_id"],
                    emoji=c.get("emoji") or "🎴",
                )
                for i, c in enumerate(page_cards, start=start + 1)
            ],
        )
        select.callback = self.select_callback
        container.add_item(ui.ActionRow(select))

        nav = [
            self._button("◀️ 上一頁", self.prev_callback, disabled=(self.page <= 1)),
            self._button(f"📄 {self.page} / {total_pages} 頁", None, discord.ButtonStyle.secondary, disabled=True),
            self._button("下一頁 ▶️", self.next_callback, disabled=(self.page >= total_pages)),
        ]
        if self.first is not None:
            nav.insert(0, self._button("🔙 重選第一張", self.back_callback, discord.ButtonStyle.secondary))
        container.add_item(ui.ActionRow(*nav))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的合成畫面！")
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def select_callback(self, interaction: discord.Interaction):
        chosen = interaction.data["values"][0]
        card = next((c for c in self._candidates() if c["instance_id"] == chosen), None)
        if card is None:
            await send_notice(interaction, "❌ 找不到這張卡牌，請重新使用 `/card synthesis`。")
            return
        if self.first is None:
            self.first = card
            self.page = 1
            await self.refresh(interaction)
            return
        # 兩張都選好了 ➔ 換成確認畫面 (會重新讀取資料庫確認卡牌還在)
        result = await self.gacha_cog.make_synthesis_view(self.user_id, self.user_name, self.first["instance_id"], card["instance_id"])
        if isinstance(result, str):
            await send_notice(interaction, result)
            return
        self.stop()
        await interaction.response.edit_message(view=result)

    async def back_callback(self, interaction: discord.Interaction):
        self.first = None
        self.page = 1
        await self.refresh(interaction)

    async def prev_callback(self, interaction: discord.Interaction):
        self.page = max(1, self.page - 1)
        await self.refresh(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        self.page += 1
        await self.refresh(interaction)


# ================= 🎴 Cog 類別 =================
class GachaCardSys(commands.GroupCog, group_name="card", group_description="東方角色卡牌收集與合成系統"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def generate_completeness(self) -> float:
        val = (random.gauss(0, 0.35)) ** 2
        return round(max(0.001, min(1.000, val)), 4)

    async def execute_gacha(self, interaction: discord.Interaction, draw_count: int, pool_key: str):
        await interaction.response.defer()

        # 卡池沒有角色時直接中止
        if not any(v["pool"] == pool_key for v in GACHA_POOL.values()):
            await send_notice(interaction, "❌ 這個卡池目前沒有任何角色，暫時無法祈願，請聯絡管理員。")
            return

        user_id = interaction.user.id
        total_cost = draw_count * DRAW_COST

        # 扣款、擲卡 (含保底)、寫入卡牌與統計全部在同一個交易
        try:
            result = await draw_gacha(
                user_id, pool_key, draw_count, total_cost,
                lambda since_ur: roll_pool_cards(pool_key, draw_count, since_ur, self.generate_completeness),
            )
        except InsufficientFunds as e:
            msg = f"❌ **賽錢不足！**\n祈願需要 `{total_cost:,}` 賽錢，但你的口袋裡只有 `{e.money:,}` 賽錢...\n*靈夢看了看空蕩蕩的賽錢箱，無奈地把你請出了神社。*"
            await send_notice(interaction, msg)
            return

        results = result["cards"]
        pity_text = f"🎯 保底：`{result['since_ur']} / {PITY_THRESHOLD}` · 本池累計 `{result['pool_draws']:,}` 抽"
        if any(c.get("pity") for c in results):
            pity_text = f"🎯 **觸發保底！必定獲得 {PITY_RARITY}！**\n" + pity_text

        pool_name = GACHA_POOLS[pool_key]["name"]
        if draw_count == 1:
            container = build_gacha_single_container(
                results[0], interaction.user.display_name, total_cost, THUMBNAILS, pool_name, pity_text
            )
        else:
            container = build_gacha_ten_container(
                results, interaction.user.display_name, total_cost, THUMBNAILS, pool_name, pity_text
            )

        view = GachaResultView(user_id, interaction.user.display_name, self, container, pool_key)

        if interaction.type == discord.InteractionType.component:
            await interaction.edit_original_response(view=view)
        else:
            await interaction.followup.send(view=view)

    @app_commands.command(name="gacha", description="⛩️ 博麗神社祈願：消耗賽錢抽取角色卡牌")
    @app_commands.describe(pool="要祈願的卡池 (依作品代數劃分)", pull_type="單抽或十連")
    @app_commands.choices(
        pool=[app_commands.Choice(name=f"{p['name']} ({p['desc']})", value=key) for key, p in GACHA_POOLS.items()],
        pull_type=[
            app_commands.Choice(name="單次祈願 (2,000 賽錢)", value=1),
            app_commands.Choice(name="十連祈願 (20,000 賽錢)", value=10),
        ],
    )
    async def gacha_card(self, interaction: discord.Interaction, pool: app_commands.Choice[str], pull_type: app_commands.Choice[int]):
        await self.execute_gacha(interaction, pull_type.value, pool.value)

    @app_commands.command(name="history", description="📜 查看各卡池的祈願次數與保底進度")
    async def history(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        pity = await get_gacha_pity(user_id)
        stats = await get_gacha_stats(user_id)
        container = build_gacha_history_container(
            interaction.user.display_name, GACHA_POOLS, pity, stats, PITY_THRESHOLD, PITY_RARITY
        )
        view = ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view)

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

    # ---------------- 共用：代數 / 角色 autocomplete ----------------
    def _pool_label(self, pool_key: str) -> str:
        return GACHA_POOLS[pool_key]["name"] if pool_key in GACHA_POOLS else "📦 其他 (已不在卡池)"

    def _pool_choices(self, groups: dict, current: str) -> list[app_commands.Choice[str]]:
        """groups = {(角色, 階級): [卡...]}；依代數彙整成選項"""
        counts = {}
        for cards in groups.values():
            pool_key = card_pool_key(cards[0])
            counts[pool_key] = counts.get(pool_key, 0) + 1
        choices = []
        for pool_key, count in counts.items():
            label = self._pool_label(pool_key)
            if current.lower() in f"{pool_key} {label}".lower():
                choices.append(app_commands.Choice(name=f"{label} · {count} 組可用", value=pool_key))
        return choices[:AUTOCOMPLETE_LIMIT]

    def _character_choices(self, groups: dict, pool_key: str | None, current: str) -> list[app_commands.Choice[str]]:
        """依已選的代數列出有可用組合的角色"""
        owned = {}
        for (char_key, _), cards in groups.items():
            if card_pool_key(cards[0]) != pool_key:
                continue
            entry = owned.setdefault(char_key, {"name": cards[0]["name"], "emoji": cards[0].get("emoji", "🎴"), "count": 0})
            entry["count"] += len(cards)
        current = current.strip().lower()
        return [
            app_commands.Choice(name=f"{e['emoji']} {e['name']} ({key}) · {e['count']} 張可用"[:100], value=key)
            for key, e in owned.items()
            if not current or current in key.lower() or current in e["name"].lower()
        ][:AUTOCOMPLETE_LIMIT]

    # ---------------- ⚗️ 合成 ----------------
    async def synthesis_pool_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._pool_choices(find_synthesis_groups(await get_user_cards(interaction.user.id)), current)

    async def synthesis_character_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        groups = find_synthesis_groups(await get_user_cards(interaction.user.id))
        return self._character_choices(groups, getattr(interaction.namespace, "pool", None), current)

    async def make_synthesis_view(self, user_id: int, user_name: str, card1: str, card2: str):
        """建立合成確認畫面；卡牌不存在或條件不符時回傳錯誤訊息 (str)"""
        cards = {c["instance_id"]: c for c in await get_user_cards(user_id)}
        card_a, card_b = cards.get(card1), cards.get(card2)
        if card_a is None or card_b is None:
            return "❌ 找不到指定的卡牌，可能已經被合成或融合掉了。"
        if not can_synthesize(card_a, card_b):
            return "❌ **無法合成！**\n合成需要兩張「不同的」、「同角色」、「同階級」的卡牌，且完整度都未達 `1.0000`。"

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

        return CardActionConfirmView(user_id, user_name, self, container, on_confirm, "⚗️ 確認合成")

    @app_commands.command(name="synthesis", description="⚗️ 合成卡牌：兩張同角色、同階級的卡合成一張完整度更高的卡")
    @app_commands.describe(pool="代數 (只列出有可合成卡牌的)", character="角色 (只列出該代數中有可合成卡牌的)")
    @app_commands.autocomplete(pool=synthesis_pool_autocomplete, character=synthesis_character_autocomplete)
    async def synthesis(self, interaction: discord.Interaction, pool: str, character: str):
        user_id = interaction.user.id
        # 使用者也可能不透過 autocomplete 直接輸入，所以這裡一樣要檢查
        cards = [
            c for group in find_synthesis_groups(await get_user_cards(user_id)).values() for c in group
            if c["character_key"] == character and card_pool_key(c) == pool
        ]
        if not cards:
            await send_notice(interaction, "❌ **無法合成！**\n這個角色沒有可以合成的卡牌：合成需要兩張「同角色」、「同階級」且完整度都未達 `1.0000` 的卡牌。")
            return
        view = SynthesisPickerView(user_id, interaction.user.display_name, self, character, cards)
        await interaction.response.send_message(view=view)

    # ---------------- 🔮 融合 ----------------
    async def fusion_pool_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._pool_choices(find_fusion_groups(await get_user_cards(interaction.user.id)), current)

    async def fusion_character_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        groups = find_fusion_groups(await get_user_cards(interaction.user.id))
        return self._character_choices(groups, getattr(interaction.namespace, "pool", None), current)

    async def fusion_rarity_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """依已選的角色列出可以融合的階級 (每個角色最多 2 個)"""
        char_key = getattr(interaction.namespace, "character", None)
        groups = find_fusion_groups(await get_user_cards(interaction.user.id))
        choices = []
        for (key, rarity), group in sorted(groups.items(), key=lambda kv: RARITY_ORDER.get(kv[0][1], 0)):
            if key != char_key or current.upper() not in rarity:
                continue
            name = f"[{rarity} → {get_next_rarity(group[0])}] · 持有 {len(group)} 張 1.0000"
            choices.append(app_commands.Choice(name=name, value=rarity))
        return choices

    @app_commands.command(name="fusion", description="🔮 融合卡牌：三張同角色、同階級且完整度 1.0000 的卡融合成高一階的卡")
    @app_commands.describe(
        pool="代數 (只列出有可融合卡牌的)",
        character="角色 (只列出該代數中有可融合卡牌的)",
        rarity="要融合的階級 (只列出符合條件的)",
    )
    @app_commands.autocomplete(pool=fusion_pool_autocomplete, character=fusion_character_autocomplete, rarity=fusion_rarity_autocomplete)
    async def fusion(self, interaction: discord.Interaction, pool: str, character: str, rarity: str):
        result = await self.make_fusion_view(interaction.user.id, interaction.user.display_name, character, rarity, pool)
        if isinstance(result, str):
            await send_notice(interaction, result)
            return
        await interaction.response.send_message(view=result)

    async def make_fusion_view(self, user_id: int, user_name: str, char_key: str, rarity: str, pool: str | None = None):
        """建立融合確認畫面；條件不符時回傳錯誤訊息 (str)。pool 有給時會一併檢查卡池"""
        group = find_fusion_groups(await get_user_cards(user_id)).get((char_key, rarity))
        if not group or (pool is not None and card_pool_key(group[0]) != pool):
            return (f"❌ **無法融合！**\n融合需要 **{FUSION_COUNT}** 張「同角色」、「同階級」且完整度 `1.0000` 的卡牌，"
                    f"而且該角色必須還有更高的階級。")

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

        return CardActionConfirmView(user_id, user_name, self, container, on_confirm, "🔮 確認融合")

async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCardSys(bot))
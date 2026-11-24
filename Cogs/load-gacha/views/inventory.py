"""
🎒 卡冊 InventoryView、🔒 收藏冊 AlbumView、📖 角色圖鑑頁 send_character_page，以及卡冊用的疊卡 / 收集進度小工具
(從 Cogs/load-gacha/gacha.py 拆出來；gacha.py 會把這裡的名字全部轉出去)
"""
import importlib

import discord
from discord import ui

from Database import Economy_DB_Manager as econ
from Database.User_DB_Manager import get_user_cards, get_album_cards, set_cards_locked
from Utils.components import send_notice, notice_view
from Utils.pagination import nav_buttons, paginate   # 📄 共用分頁
from Utils.gacha_pools import GACHA_POOLS
from ..Components.gacha_components import (
    STACKS_PER_PAGE,
    STACK_CARDS_PER_PAGE,
    build_stack_list_container,
    build_stack_cards_container,
    build_card_detail_container,
    build_album_container,
    ALBUM_PER_PAGE,
)
from ..logic.rules import GACHA_POOL, THUMBNAILS, RARITY_ORDER, FUSION_COUNT, sort_cards, is_perfect, get_next_rarity
from ..logic.detail import card_detail_info
from .synthesis import SynthesisPickerView, find_synthesis_groups


async def send_character_page(interaction: discord.Interaction, character_key: str):
    """📖 角色圖鑑：另開一則只有自己看得到的 /character 角色頁 (Cog 之間不互相 import，呼叫時才取)"""
    from Utils.character_data import load_categories
    cc = importlib.import_module("Cogs.load-character.Components.character_components")
    found = next(((ch, cat, folder) for folder, cat in load_categories().items() for ch in cat["characters"]
                  if ch["id"] == character_key), None)
    if found is None:
        await send_notice(interaction, "❌ 圖鑑裡找不到這位角色。")
        return
    char, cat, folder = found
    owned = {}   # 看的人自己的收藏 (收藏冊的卡也算)
    for c in await get_user_cards(interaction.user.id, include_locked=True):
        per = owned.setdefault(c["character_key"], {})
        per[c["rarity"]] = per.get(c["rarity"], 0) + 1
    view = ui.LayoutView()
    view.add_item(cc.build_character_container(char, cat["category_name"], THUMBNAILS, owned,
                                               folder=folder, rules=await econ.get_rules()))
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)


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


async def owned_character_keys(user_id: int) -> set[str]:
    """
    收集進度用的「已擁有角色」：卡冊 + 收藏冊 + 裏世界出征中的卡 (跟圖鑑「已擁有」、稱號、排行榜一致)
    2026-11-23 使用者定：卡冊畫面的收集進度也算收藏冊；張數、疊卡列表照舊只算卡冊裡的
    """
    return {c["character_key"] for c in await get_user_cards(user_id, include_locked=True)}


def collection_progress(owned: set) -> list[tuple[dict, int, int]]:
    """各卡池的收集進度：[(卡池設定, 已擁有角色數, 卡池角色數), ...]；owned = 擁有的角色 id"""
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
    def __init__(self, user_id: int, cards: list, user_name: str, gacha_cog, owner_id: int | None = None,
                 owned_keys: set | None = None):
        super().__init__(timeout=180)
        self.user_id = user_id                       # 操作畫面的人
        self.owner_id = owner_id or user_id          # 卡冊的主人 (管理員檢視別人卡冊時不同)
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.all_cards = cards
        self.all_stacks = build_stacks(cards)
        # 收集進度算的角色 (owned_character_keys：含收藏冊、出征中)；沒給就只看這些卡 (管理員畫面本來就含收藏冊)
        self.owned_keys = owned_keys if owned_keys is not None else {c["character_key"] for c in cards}

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

    def _filter_desc(self) -> str:
        pool = "全部卡池" if self.pool_filter == "ALL" else GACHA_POOLS.get(self.pool_filter, {}).get("name", "📦 其他")
        rarity = "全部階級" if self.rarity_filter == "ALL" else f"{self.rarity_filter} 階級"
        return f"篩選：{pool} · {rarity} · 排序：{INVENTORY_SORTS[self.sort_index][1]}"

    def _progress_text(self) -> str:
        return " · ".join(
            f"{p['name']} `{owned}/{total}`" for p, owned, total in collection_progress(self.owned_keys)
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
        pg = paginate(stacks, self.page, STACKS_PER_PAGE)
        self.page, total_pages, start, page_stacks = pg.page, pg.total, pg.start, pg.items

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
            *nav_buttons(self.page, total_pages, self.set_page),
            self._button(f"🔃 排序：{INVENTORY_SORTS[self.sort_index][1]}", self.sort_callback, discord.ButtonStyle.secondary),
        ))
        self.add_item(container)

    def _build_stack(self):
        stack = self.get_stack(self.selected_stack)
        cards = stack["cards"]
        pg = paginate(cards, self.stack_page, STACK_CARDS_PER_PAGE)
        self.stack_page, total_pages, start, page_cards = pg.page, pg.total, pg.start, pg.items

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
            *nav_buttons(self.stack_page, total_pages, self.set_stack_page),
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
        container = build_card_detail_container(self.selected_card, self.user_name, THUMBNAILS,
                                                getattr(self, "detail_info", None))
        container.add_item(ui.Separator())
        buttons = [
            self._button("🔙 返回這一疊", self.back_to_stack_callback, discord.ButtonStyle.secondary),
            self._button("🎒 返回卡冊", self.back_to_list_callback, discord.ButtonStyle.secondary),
        ]
        # 🔒 放進收藏冊：只有卡冊主人本人 (管理員檢視別人卡冊時不顯示)
        if self.user_id == self.owner_id and not self.selected_card.get("locked"):
            buttons.append(self._button("🔒 放進收藏冊", self.lock_callback, discord.ButtonStyle.primary))
        buttons.append(self._button("📖 角色圖鑑", self.character_page_callback, discord.ButtonStyle.secondary))
        container.add_item(ui.ActionRow(*buttons))
        self.add_item(container)

    async def character_page_callback(self, interaction: discord.Interaction):
        """📖 角色圖鑑：另開一則只有自己看得到的角色頁 (這個畫面不動)"""
        await send_character_page(interaction, self.selected_card["character_key"])

    async def lock_callback(self, interaction: discord.Interaction):
        """放進收藏冊：之後卡冊、合成、融合、分解、上架都看不到這張卡"""
        card = self.selected_card
        if not await set_cards_locked(self.owner_id, [card["instance_id"]], True):
            await send_notice(interaction, "❌ 這張卡已經不在卡冊裡了，請重新開啟 `/card inventory`。")
            return
        self.all_cards = sort_cards(await get_user_cards(self.owner_id))
        self.all_stacks = build_stacks(self.all_cards)
        self.selected_card = None
        if self.get_stack(self.selected_stack) is None:   # 這一疊收完了 ➔ 回卡冊列表
            self.selected_stack = None
        if not self.all_cards:
            self.stop()
            await interaction.response.edit_message(view=notice_view(
                f"🔒 已把 {card.get('emoji') or '🎴'} `[{card['rarity']}]` **{card['name']}** 放進收藏冊。卡冊已經沒有其他卡了，可以用 `/card album` 查看。"))
            return
        await self.refresh(interaction)
        await send_notice(interaction, f"🔒 已把 {card.get('emoji') or '🎴'} `[{card['rarity']}]` **{card['name']}** "
                                       f"(`{card['completeness']:.4f}`) 放進收藏冊，用 `/card album` 查看或取出。")

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

    async def set_page(self, interaction: discord.Interaction, page: int):
        self.page = page   # build() 會把頁數限制在範圍內
        await self.refresh(interaction)

    async def stack_select_callback(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        if self.get_stack(value) is None:
            await send_notice(interaction, "❌ 找不到這一疊卡牌，請重新開啟 `/card inventory`。")
            return
        self.selected_stack = value
        self.stack_page = 1
        await self.refresh(interaction)

    async def set_stack_page(self, interaction: discord.Interaction, page: int):
        self.stack_page = page
        await self.refresh(interaction)

    async def card_select_callback(self, interaction: discord.Interaction):
        instance_id = interaction.data["values"][0]
        card = next((c for c in self.all_cards if c["instance_id"] == instance_id), None)
        if card is None:
            await send_notice(interaction, "❌ 找不到這張卡牌，請重新開啟 `/card inventory`。")
            return
        self.selected_card = card
        self.detail_info = await card_detail_info(card, self.owner_id)   # 🔍 角色資料、實力、特殊能力、價值、狀態
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


# ================= 🔒 收藏冊 View (Components V2) =================
class AlbumView(ui.LayoutView):
    """
    /card album：收藏冊裡的卡 (locked = 1)，分頁列表 ➔ 選一張看詳情 ➔ 📤 取出 (回到卡冊)
    放進去的入口在 /card inventory 的卡片詳情 (InventoryView.lock_callback)
    """
    def __init__(self, user_id: int, user_name: str, cards: list):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.cards = cards
        self.page = 1
        self.selected = None   # 正在看的卡
        self.result = None     # 畫面最上面的結果訊息 (取出後顯示)
        self.build()

    def _button(self, label: str, callback, style=discord.ButtonStyle.primary, disabled: bool = False) -> ui.Button:
        btn = ui.Button(label=label, style=style, disabled=disabled)
        if callback is not None:
            btn.callback = callback
        return btn

    def build(self):
        self.clear_items()
        if self.selected:
            container = build_card_detail_container({**self.selected, "locked": 1}, self.user_name, THUMBNAILS,
                                                    getattr(self, "detail_info", None))
            container.add_item(ui.Separator())
            container.add_item(ui.ActionRow(
                self._button("🔙 返回收藏冊", self.back_callback, discord.ButtonStyle.secondary),
                self._button("📤 取出 (回到卡冊)", self.unlock_callback, discord.ButtonStyle.danger),
                self._button("📖 角色圖鑑", self.character_page_callback, discord.ButtonStyle.secondary),
            ))
            self.add_item(container)
            return
        pg = paginate(self.cards, self.page, ALBUM_PER_PAGE)
        self.page, total_pages, start, page_cards = pg.page, pg.total, pg.start, pg.items
        container = build_album_container(page_cards, self.page, total_pages, len(self.cards), self.user_name, start + 1, self.result)
        if page_cards:
            container.add_item(ui.Separator())
            select = ui.Select(placeholder="🎴 選擇一張卡查看或取出...", options=[
                discord.SelectOption(
                    label=f"{start + i}. [{c['rarity']}] {c['name']} · {c['completeness']:.4f}"[:100],
                    description=f"ID: {c['instance_id']}"[:100], value=c["instance_id"], emoji=c.get("emoji") or "🎴",
                )
                for i, c in enumerate(page_cards, start=1)
            ])
            select.callback = self.select_callback
            container.add_item(ui.ActionRow(select))
            if total_pages > 1:
                container.add_item(ui.ActionRow(*nav_buttons(self.page, total_pages, self.set_page)))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的收藏冊！")
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def select_callback(self, interaction: discord.Interaction):
        instance_id = interaction.data["values"][0]
        self.selected = next((c for c in self.cards if c["instance_id"] == instance_id), None)
        if self.selected is None:
            await send_notice(interaction, "❌ 找不到這張卡，請重新開啟 `/card album`。")
            return
        self.result = None
        self.detail_info = await card_detail_info({**self.selected, "locked": 1}, self.user_id)
        await self.refresh(interaction)

    async def character_page_callback(self, interaction: discord.Interaction):
        """📖 角色圖鑑：另開一則只有自己看得到的角色頁"""
        await send_character_page(interaction, self.selected["character_key"])

    async def back_callback(self, interaction: discord.Interaction):
        self.selected = None
        await self.refresh(interaction)

    async def set_page(self, interaction: discord.Interaction, page: int):
        self.page = page
        await self.refresh(interaction)

    async def unlock_callback(self, interaction: discord.Interaction):
        card = self.selected
        ok = await set_cards_locked(self.user_id, [card["instance_id"]], False)
        self.cards = await get_album_cards(self.user_id)
        self.selected = None
        self.result = (f"📤 已把 {card.get('emoji') or '🎴'} `[{card['rarity']}]` **{card['name']}** 取出，回到卡冊了。" if ok
                       else "❌ 這張卡已經不在收藏冊裡了。")
        await self.refresh(interaction)

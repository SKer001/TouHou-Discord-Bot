import uuid
import importlib
import discord
from discord import ui
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from Database.User_DB_Manager import (
    get_user_cards, add_gacha_cards, delete_gacha_cards,
    clear_gacha_cards, update_cards_completeness,
)
from Utils.config import is_admin
from Utils.components import send_notice, notice_container

AUTOCOMPLETE_LIMIT = 25


def gacha_mod():
    """
    取得目前載入中的抽卡模組 (Cogs.load-gacha.gacha)。
    每次呼叫時才取：/admin-sys reload 抽卡模組後，這裡會拿到最新的卡池與畫面。
    """
    return importlib.import_module(f"{__package__}.gacha")


def _target_id(interaction: discord.Interaction) -> int | None:
    """autocomplete 時從已填的 target 參數取出成員 ID (還沒填時為 None)"""
    target = getattr(interaction.namespace, "target", None)
    return getattr(target, "id", None)


# ---------------------------------------------------------
# 🧹 清空卡冊確認 View (Components V2)
# ---------------------------------------------------------
class ClearConfirmView(ui.LayoutView):
    def __init__(self, target: discord.abc.User, card_count: int):
        super().__init__(timeout=60)
        self.target = target
        self.done = False

        confirm_btn = ui.Button(label="✔️ 確定清空", style=discord.ButtonStyle.danger)
        confirm_btn.callback = self.confirm_callback
        cancel_btn = ui.Button(label="❌ 取消", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = self.cancel_callback

        container = ui.Container(accent_color=discord.Color.red())
        container.add_item(ui.TextDisplay(
            f"## ⚠️ 清空卡冊確認\n"
            f"確定要清空 **{target.display_name}** 的整本卡冊嗎？\n"
            f"共 `{card_count}` 張卡牌將被永久刪除 *(抽卡與融合統計會保留)*"
        ))
        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(confirm_btn, cancel_btn))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return False
        return True

    async def _finish(self, interaction: discord.Interaction, text: str):
        self.clear_items()
        self.add_item(notice_container(text))
        await interaction.response.edit_message(view=self)
        self.stop()

    async def confirm_callback(self, interaction: discord.Interaction):
        if self.done:   # 連點：第二下直接忽略
            await interaction.response.defer()
            return
        self.done = True
        deleted = await clear_gacha_cards(self.target.id)
        await self._finish(interaction, f"🗑️ 已清空 **{self.target.display_name}** 的卡冊，共刪除 `{deleted}` 張卡牌。")

    async def cancel_callback(self, interaction: discord.Interaction):
        self.done = True
        await self._finish(interaction, "↩️ 已取消，卡冊沒有任何變動。")


# ---------------------------------------------------------
# 🗂️ 選卡 View (Components V2)：remove / set_completeness 共用
#   列出某成員某角色的所有卡 (分頁，每頁最多 20 張 = 選單上限內)
#   ➔ 選單多選 ➔ 確認畫面 ➔ 執行後回到列表 (自動重新讀取)
# ---------------------------------------------------------
PICKER_PER_PAGE = 20


class CardPickerView(ui.LayoutView):
    """
    action = "remove"：刪除選取的卡
    action = "set"   ：把選取的卡完整度設為 value
    """
    def __init__(self, target: discord.abc.User, pool_key: str, character_key: str, cards: list,
                 action: str, value: float | None = None):
        super().__init__(timeout=300)
        self.target = target
        self.pool_key = pool_key
        self.character_key = character_key
        self.cards = self._sort(cards)
        self.action = action
        self.value = value
        self.page = 1
        self.pending = []      # 確認畫面中等待處理的卡
        self.notice = None     # 上一次操作的結果
        self.done = False      # 確認按鈕連點保護
        self.build()

    @staticmethod
    def _sort(cards: list) -> list:
        order = gacha_mod().RARITY_ORDER
        return sorted(cards, key=lambda c: (-order.get(c["rarity"], 0), -c["completeness"]))

    @property
    def total_pages(self) -> int:
        return max(1, (len(self.cards) + PICKER_PER_PAGE - 1) // PICKER_PER_PAGE)

    def _title(self) -> str:
        sample = self.cards[0] if self.cards else {}
        return f"{sample.get('emoji', '🎴')} **{sample.get('name', self.character_key)}**　·　{self.target.display_name}"

    def _button(self, label: str, callback, style=discord.ButtonStyle.primary, disabled: bool = False) -> ui.Button:
        btn = ui.Button(label=label, style=style, disabled=disabled)
        if callback is not None:
            btn.callback = callback
        return btn

    def _card_line(self, card: dict, index: int | None = None) -> str:
        head = f"**{index}.** " if index is not None else "• "
        line = f"{head}`[{card['rarity']}]` `{card['completeness']:.4f}`"
        if self.action == "set" and index is None:
            line += f" ➔ `{self.value:.4f}`"
        return f"{line} · `{card['instance_id']}`"

    def build(self):
        self.clear_items()
        is_remove = self.action == "remove"

        # ---- 確認畫面 ----
        if self.pending:
            lines = "\n".join(self._card_line(c) for c in self.pending)
            if is_remove:
                head = f"## ⚠️ 刪除確認\n{self._title()}\n確定要永久刪除以下 `{len(self.pending)}` 張卡牌嗎？"
                confirm = self._button("✔️ 確定刪除", self.confirm_callback, discord.ButtonStyle.danger)
            else:
                head = f"## ✏️ 修改完整度確認\n{self._title()}\n確定要把以下 `{len(self.pending)}` 張卡牌的完整度改為 `{self.value:.4f}` 嗎？"
                confirm = self._button("✔️ 確定修改", self.confirm_callback, discord.ButtonStyle.success)
            container = ui.Container(accent_color=discord.Color.red() if is_remove else discord.Color.orange())
            container.add_item(ui.TextDisplay(f"{head}\n{lines}"))
            container.add_item(ui.Separator())
            container.add_item(ui.ActionRow(confirm, self._button("❌ 取消", self.cancel_callback, discord.ButtonStyle.secondary)))
            self.add_item(container)
            return

        if self.notice:
            self.add_item(notice_container(self.notice))

        # ---- 沒有卡了 (全部刪光) ----
        if not self.cards:
            self.add_item(notice_container(f"🎒 {self._title()}\n這個角色已經沒有任何卡牌了。"))
            return

        # ---- 列表畫面 ----
        self.page = min(self.page, self.total_pages)
        start = (self.page - 1) * PICKER_PER_PAGE
        page_cards = self.cards[start:start + PICKER_PER_PAGE]
        lines = "\n".join(self._card_line(c, i) for i, c in enumerate(page_cards, start=start + 1))

        if is_remove:
            head = "## 🗑️ 刪除卡牌"
            placeholder = "選擇要刪除的卡牌 (可多選)..."
        else:
            head = f"## ✏️ 修改完整度 ➔ `{self.value:.4f}`"
            placeholder = "選擇要修改完整度的卡牌 (可多選)..."

        container = ui.Container(accent_color=discord.Color.orange())
        container.add_item(ui.TextDisplay(
            f"{head}\n{self._title()}\n-# 共 {len(self.cards)} 張 · 依階級、完整度由高到低排列 · 可一次多選"
        ))
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(lines))
        container.add_item(ui.Separator())

        select = ui.Select(
            placeholder=placeholder,
            min_values=1,
            max_values=len(page_cards),
            options=[
                discord.SelectOption(
                    label=f"{i}. [{c['rarity']}] {c['completeness']:.4f}",
                    description=c["instance_id"][:100],
                    value=c["instance_id"],
                )
                for i, c in enumerate(page_cards, start=start + 1)
            ],
        )
        select.callback = self.select_callback
        container.add_item(ui.ActionRow(select))
        container.add_item(ui.ActionRow(
            self._button("◀️ 上一頁", self.prev_callback, disabled=(self.page <= 1)),
            self._button(f"📄 {self.page} / {self.total_pages} 頁", None, discord.ButtonStyle.secondary, disabled=True),
            self._button("下一頁 ▶️", self.next_callback, disabled=(self.page >= self.total_pages)),
        ))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def reload_cards(self):
        """重新讀取，反映其他地方 (合成、融合、刪除等) 造成的變動"""
        g = gacha_mod()
        self.cards = self._sort([
            c for c in await get_user_cards(self.target.id)
            if c["character_key"] == self.character_key and g.card_pool_key(c) == self.pool_key
        ])

    async def select_callback(self, interaction: discord.Interaction):
        chosen = set(interaction.data["values"])
        self.pending = [c for c in self.cards if c["instance_id"] in chosen]
        self.notice = None
        self.done = False
        await self.refresh(interaction)

    async def confirm_callback(self, interaction: discord.Interaction):
        if self.done:   # 連點：第二下直接忽略
            await interaction.response.defer()
            return
        self.done = True
        ids = [c["instance_id"] for c in self.pending]

        if self.action == "remove":
            changed = await delete_gacha_cards(self.target.id, ids)
            self.notice = f"🗑️ 已刪除 **{self.target.display_name}** 的 `{changed}` 張卡牌。"
        else:
            changed = await update_cards_completeness(self.target.id, ids, self.value)
            self.notice = f"✅ 已將 **{self.target.display_name}** 的 `{changed}` 張卡牌完整度改為 `{self.value:.4f}`。"
        if changed != len(ids):
            self.notice += f"\n-# 有 `{len(ids) - changed}` 張已經不在對方的卡冊中 (可能已被合成、融合或刪除)。"
        self.pending = []

        await self.reload_cards()
        await self.refresh(interaction)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.pending = []
        self.notice = "↩️ 已取消，卡牌沒有任何變動。"
        await self.refresh(interaction)

    async def prev_callback(self, interaction: discord.Interaction):
        self.page = max(1, self.page - 1)
        self.notice = None
        await self.refresh(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        self.page += 1
        self.notice = None
        await self.refresh(interaction)


# ---------------------------------------------------------
# 🤖 GachaAdmin Cog
# ---------------------------------------------------------
class GachaAdmin(commands.GroupCog, group_name="admin-gacha", group_description="【開發者專用】玩家卡冊管理指令"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _deny(self, interaction: discord.Interaction) -> bool:
        """不是管理員 ➔ 回覆無權限並回傳 True"""
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return True
        return False

    # ---------------- autocomplete ----------------
    async def pool_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """give 用：列出所有卡池 (代數)"""
        g = gacha_mod()
        counts = {}
        for data in g.GACHA_POOL.values():
            counts[data["pool"]] = counts.get(data["pool"], 0) + 1
        return [
            app_commands.Choice(name=f"{p['name']} ({p['desc']}) · {counts.get(key, 0)} 位角色"[:100], value=key)
            for key, p in g.GACHA_POOLS.items()
            if current.lower() in f"{key} {p['name']} {p['desc']}".lower()
        ]

    async def character_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """give 用：依已選的卡池列出角色"""
        g = gacha_mod()
        pool_key = getattr(interaction.namespace, "pool", None)
        current = current.strip().lower()
        choices = []
        for key, data in g.GACHA_POOL.items():
            if data["pool"] != pool_key:
                continue
            if current and current not in key.lower() and current not in data["name"].lower():
                continue
            name = f"{data['emoji']} {data['name']} ({key}) · {'/'.join(data['rarities'])}"
            choices.append(app_commands.Choice(name=name[:100], value=key))
            if len(choices) >= AUTOCOMPLETE_LIMIT:
                break
        return choices

    async def owned_pool_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """remove 用：列出 target 有卡的卡池 (含已不在卡池的「其他」)"""
        target_id = _target_id(interaction)
        if target_id is None:
            return []
        g = gacha_mod()
        counts = {}
        for card in await get_user_cards(target_id):
            pool_key = g.card_pool_key(card)
            counts[pool_key] = counts.get(pool_key, 0) + 1
        choices = []
        for key, count in counts.items():
            label = g.GACHA_POOLS[key]["name"] if key in g.GACHA_POOLS else "📦 其他 (已不在卡池)"
            if current.lower() in f"{key} {label}".lower():
                choices.append(app_commands.Choice(name=f"{label} · {count} 張", value=key))
        return choices[:AUTOCOMPLETE_LIMIT]

    async def owned_character_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """remove 用：列出 target 在該卡池中擁有的角色與張數"""
        target_id = _target_id(interaction)
        pool_key = getattr(interaction.namespace, "pool", None)
        if target_id is None or pool_key is None:
            return []
        g = gacha_mod()
        owned = {}
        for card in await get_user_cards(target_id):
            if g.card_pool_key(card) != pool_key:
                continue
            entry = owned.setdefault(card["character_key"], {"name": card["name"], "emoji": card.get("emoji", "🎴"), "count": 0})
            entry["count"] += 1
        current = current.strip().lower()
        choices = [
            app_commands.Choice(name=f"{e['emoji']} {e['name']} ({key}) · {e['count']} 張"[:100], value=key)
            for key, e in owned.items()
            if not current or current in key.lower() or current in e["name"].lower()
        ]
        return choices[:AUTOCOMPLETE_LIMIT]

    async def rarity_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """依已選的角色列出它的三個階級"""
        char = gacha_mod().GACHA_POOL.get(getattr(interaction.namespace, "character", None) or "")
        if char is None:
            return []
        return [
            app_commands.Choice(name=f"[{r}] {char['titles'].get(r, '')}"[:100], value=r)
            for r in char["rarities"] if current.upper() in r
        ]

    # 1. 🎒 /view 檢視指定成員的卡冊
    @app_commands.command(name="view", description="【開發者專用】檢視指定成員的卡冊")
    @app_commands.describe(target="要檢視的成員")
    @app_commands.default_permissions(administrator=True)
    async def view_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member):
        if await self._deny(interaction):
            return
        cards = await get_user_cards(target.id)
        if not cards:
            await send_notice(interaction, f"🎒 **{target.display_name}** 的卡冊空空如也。")
            return
        # 操作者是管理員本人，畫面顯示的是目標成員的卡冊
        view = gacha_mod().InventoryView(
            interaction.user.id, gacha_mod().sort_cards(cards), target.display_name,
            self.bot.get_cog("GachaCardSys"), owner_id=target.id,
        )
        await interaction.response.send_message(view=view, ephemeral=True)

    # 2. 🎁 /give 發放指定角色的卡牌
    @app_commands.command(name="give", description="【開發者專用】發放指定角色與階級的卡牌給成員")
    @app_commands.describe(
        target="目標成員",
        pool="代數 (卡池)",
        character="角色 (依代數列出)",
        rarity="階級 (依角色列出)",
        amount="張數 (1 ~ 20，預設 1)",
        completeness="完整度 0.0001 ~ 1.0 (留空則與祈願相同隨機)",
    )
    @app_commands.autocomplete(pool=pool_autocomplete, character=character_autocomplete, rarity=rarity_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def give_cmd(
        self,
        interaction: discord.Interaction,
        target: discord.User | discord.Member,
        pool: str,
        character: str,
        rarity: str,
        amount: app_commands.Range[int, 1, 20] = 1,
        completeness: app_commands.Range[float, 0.0001, 1.0] = None,
    ):
        if await self._deny(interaction):
            return
        char = gacha_mod().GACHA_POOL.get(character)
        if char is None or char["pool"] != pool:
            await send_notice(interaction, f"❌ 卡池 `{pool}` 中找不到角色 `{character}`，請依序從選單中選擇代數與角色。")
            return
        if rarity not in char["rarities"]:
            await send_notice(interaction, f"❌ **{char['name']}** 沒有 `{rarity}` 階級，可用階級：`{'/'.join(char['rarities'])}`")
            return

        cog = self.bot.get_cog("GachaCardSys")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cards = [
            {
                "instance_id": f"c_{char['uuid'][:4]}_{uuid.uuid4().hex[:12]}",
                "character_key": character,
                "name": char["name"],
                "emoji": char["emoji"],
                "rarity": rarity,
                "title": char["titles"][rarity],
                "completeness": round(completeness, 4) if completeness is not None else cog.generate_completeness(),
                "obtained_at": now,
            }
            for _ in range(amount)
        ]
        await add_gacha_cards(target.id, cards, draw_count=0)   # 管理員發放不算抽卡次數

        lines = "\n".join(f"• `{c['instance_id']}` · 完整度 `{c['completeness']:.4f}`" for c in cards)
        await send_notice(
            interaction,
            f"🎁 已發放 {char['emoji']} `[{rarity}]` **{char['name']}** ×`{amount}` 給 **{target.display_name}**\n{lines}",
        )

    async def _open_picker(self, interaction: discord.Interaction, target, pool: str, character: str,
                           action: str, value: float | None = None):
        """remove / set_completeness 共用：找出對方該代數該角色的卡，開啟選卡畫面"""
        g = gacha_mod()
        cards = [c for c in await get_user_cards(target.id)
                 if c["character_key"] == character and g.card_pool_key(c) == pool]
        if not cards:
            await send_notice(interaction, f"❌ **{target.display_name}** 在這個代數中沒有角色 `{character}` 的卡牌。")
            return
        view = CardPickerView(target, pool, character, cards, action, value)
        await interaction.response.send_message(view=view, ephemeral=True)

    # 3. 🗑️ /remove 開啟刪除卡牌畫面 (依代數 ➔ 角色，可分頁、多選)
    @app_commands.command(name="remove", description="【開發者專用】刪除成員卡冊中的卡牌 (依代數與角色篩選，可分頁多選)")
    @app_commands.describe(target="目標成員", pool="代數 (只列出對方有卡的)", character="角色 (只列出對方在該代數擁有的)")
    @app_commands.autocomplete(pool=owned_pool_autocomplete, character=owned_character_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def remove_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member, pool: str, character: str):
        if await self._deny(interaction):
            return
        await self._open_picker(interaction, target, pool, character, "remove")

    # 4. ✏️ /set_completeness 開啟修改完整度畫面 (依代數 ➔ 角色，可分頁、多選)
    @app_commands.command(name="set_completeness", description="【開發者專用】修改成員卡牌的完整度 (依代數與角色篩選，可分頁多選)")
    @app_commands.describe(
        target="目標成員",
        pool="代數 (只列出對方有卡的)",
        character="角色 (只列出對方在該代數擁有的)",
        value="新的完整度 0.0001 ~ 1.0 (選取的卡都會改成這個值)",
    )
    @app_commands.autocomplete(pool=owned_pool_autocomplete, character=owned_character_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def set_completeness_cmd(
        self,
        interaction: discord.Interaction,
        target: discord.User | discord.Member,
        pool: str,
        character: str,
        value: app_commands.Range[float, 0.0001, 1.0],
    ):
        if await self._deny(interaction):
            return
        await self._open_picker(interaction, target, pool, character, "set", round(value, 4))

    # 5. 🧹 /clear 清空整本卡冊 (需確認)
    @app_commands.command(name="clear", description="【開發者專用】清空成員的整本卡冊 (會先要求確認)")
    @app_commands.describe(target="目標成員")
    @app_commands.default_permissions(administrator=True)
    async def clear_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member):
        if await self._deny(interaction):
            return
        cards = await get_user_cards(target.id)
        if not cards:
            await send_notice(interaction, f"🎒 **{target.display_name}** 的卡冊本來就是空的。")
            return
        await interaction.response.send_message(view=ClearConfirmView(target, len(cards)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GachaAdmin(bot))

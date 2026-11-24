"""
⚗️ 合成 / 🔮 融合的畫面：CardActionConfirmView (確認 ➔ 結果)、SynthesisPickerView (合成選卡)
(從 Cogs/load-gacha/gacha.py 拆出來；gacha.py 會把這裡的名字全部轉出去)

引用方向：synthesis ➔ inventory ➔ result (後面的可以匯入前面的)。這個檔不能在最上面匯入 inventory；
CardActionConfirmView.view_inventory 要開卡冊，在函式裡才匯入。Cog 由建構子傳進來 (gacha_cog)，不 import gacha.py
"""
import discord
from discord import ui

from Database.User_DB_Manager import get_user_cards
from Utils.components import send_notice
from Utils.pagination import nav_buttons, paginate   # 📄 共用分頁
from ..logic.rules import RARITY_ORDER, sort_cards, is_perfect, can_synthesize


# ================= ✅ 合成 / 融合確認 View (Components V2) =================
class CardActionConfirmView(ui.LayoutView):
    """
    確認畫面：按「確認」才真的消耗卡牌。
    on_confirm(interaction) 回傳結果 Container；失敗時回傳 str (錯誤訊息)。
    continue_character = 合成用：結果畫面「🎒 查看卡庫」旁邊多「⚗️ 繼續合成」(回到這位角色的選卡畫面，沒得合時反灰)；
      continue_on_success=False (⚡ 自動合成) ➔ 成功時不放，失敗時才放
    """
    def __init__(self, user_id: int, user_name: str, gacha_cog, container: ui.Container, on_confirm, confirm_label: str,
                 continue_character: str | None = None, continue_on_success: bool = True):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.on_confirm = on_confirm
        self.continue_character = continue_character
        self.continue_on_success = continue_on_success
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
        row = [inv_btn]
        if self.continue_character and (isinstance(result, str) or self.continue_on_success):
            cont_btn = ui.Button(label="⚗️ 繼續合成", style=discord.ButtonStyle.success,
                                 disabled=not await self._synthesis_cards())   # 這位角色已經沒得合 ➔ 反灰
            cont_btn.callback = self.continue_synthesis
            row.append(cont_btn)
        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(*row))
        self.clear_items()
        self.add_item(container)
        await interaction.edit_original_response(view=self)

    async def _synthesis_cards(self) -> list:
        """這位角色現在還能合成的卡 (重新讀資料庫)"""
        return [c for (key, _), group in find_synthesis_groups(await get_user_cards(self.user_id)).items()
                if key == self.continue_character for c in group]

    async def continue_synthesis(self, interaction: discord.Interaction):
        """⚗️ 繼續合成：回到同一位角色的選卡畫面 (重新讀卡)"""
        cards = await self._synthesis_cards()
        if not cards:
            await send_notice(interaction, "❌ 這位角色已經沒有可以合成的卡了。")
            return
        self.stop()
        view = SynthesisPickerView(self.user_id, self.user_name, self.gacha_cog, self.continue_character, cards)
        await interaction.response.edit_message(view=view)

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
        from .inventory import InventoryView, owned_character_keys   # 卡冊畫面會用到這個檔 (單向引用)，回頭用的只有這裡，呼叫時才取
        inv_view = InventoryView(self.user_id, sort_cards(cards), self.user_name, self.gacha_cog,
                                 owned_keys=await owned_character_keys(self.user_id))
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
        pg = paginate(candidates, self.page, SYNTH_PICK_PER_PAGE)
        self.page, total_pages, start, page_cards = pg.page, pg.total, pg.start, pg.items

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

        nav = nav_buttons(self.page, total_pages, self.set_page)
        if self.first is not None:
            nav.insert(0, self._button("🔙 重選第一張", self.back_callback, discord.ButtonStyle.secondary))
        container.add_item(ui.ActionRow(*nav))
        # ⚡ 這位角色每個階級都自動合完 (先出確認畫面)
        container.add_item(ui.ActionRow(self._button("⚡ 自動合成全部", self.auto_callback, discord.ButtonStyle.success)))
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

    async def auto_callback(self, interaction: discord.Interaction):
        """⚡ 自動合成全部 ➔ 確認畫面 (重新讀卡；範圍 = 這位角色，每個階級各自合)"""
        result = await self.gacha_cog.make_auto_synthesis_view(self.user_id, self.user_name, self.character_key)
        if isinstance(result, str):
            await send_notice(interaction, result)
            return
        self.stop()
        await interaction.response.edit_message(view=result)

    async def set_page(self, interaction: discord.Interaction, page: int):
        self.page = page
        await self.refresh(interaction)

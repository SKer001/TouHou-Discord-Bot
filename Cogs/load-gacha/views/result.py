"""
🎛️ 抽卡結果 GachaResultView、📊 機率表的送出 send_rate_sheet、🎪 活動卡池選單 EventPoolPickerView、📜 祈願紀錄 GachaHistoryView
(從 Cogs/load-gacha/gacha.py 拆出來；gacha.py 會把這裡的名字全部轉出去)
"""
import discord
from discord import ui

from Database import Economy_DB_Manager as econ
from Database.User_DB_Manager import get_user_cards, get_gacha_pity
from Utils.components import send_notice, notice_container
from ..Components.gacha_components import build_rate_sheet_container
from ..logic.rules import (
    EVENT_POOL, PITY_RARITY, PITY_THRESHOLD,
    sort_cards, draw_cost, event_pools, pool_characters, resolve_pool, rate_sheet_data,
)
from .inventory import InventoryView, owned_character_keys


# ================= 🎛️ 抽卡結果 View (Components V2) =================
class GachaResultView(ui.LayoutView):
    def __init__(self, user_id: int, user_name: str, gacha_cog, container: ui.Container, pool_key: str, cost_mult: float = 1.0):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.user_name = user_name
        self.gacha_cog = gacha_cog
        self.pool_key = pool_key   # 「繼續祈願」沿用同一個卡池 (實際的卡池 key；活動結束了就抽不到，不會換成別的活動卡池)

        single_btn = ui.Button(label=f"🌸 繼續單抽 ({draw_cost(1, cost_mult):,})", style=discord.ButtonStyle.primary)
        single_btn.callback = self.draw_single_again
        ten_btn = ui.Button(label=f"⛩️ 繼續十連 ({draw_cost(10, cost_mult):,})", style=discord.ButtonStyle.success)
        ten_btn.callback = self.draw_ten_again
        inv_btn = ui.Button(label="🎒 查看卡庫", style=discord.ButtonStyle.secondary)
        inv_btn.callback = self.view_inventory
        # 📊 機率表：誰都可以按 (只有按的人看得到，顯示的是按的人自己的保底進度)
        self.rates_btn = ui.Button(label="📊 機率表", style=discord.ButtonStyle.secondary)
        self.rates_btn.callback = self.view_rates

        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(single_btn, ten_btn, inv_btn, self.rates_btn))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if (getattr(interaction, "data", None) or {}).get("custom_id") == self.rates_btn.custom_id:
            return True
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的祈願畫面！請輸入 `/card gacha` 開啟你自己的祈願。")
            return False
        return True

    async def draw_single_again(self, interaction: discord.Interaction):
        await self.gacha_cog.execute_gacha(interaction, draw_count=1, pool_key=self.pool_key)

    async def draw_ten_again(self, interaction: discord.Interaction):
        await self.gacha_cog.execute_gacha(interaction, draw_count=10, pool_key=self.pool_key)

    async def view_rates(self, interaction: discord.Interaction):
        await send_rate_sheet(interaction, self.pool_key)

    async def view_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cards = await get_user_cards(self.user_id)
        if not cards:
            await send_notice(interaction, "🎒 你的卡冊空空如也，快進行祈願吧！")
            return

        inv_view = InventoryView(self.user_id, sort_cards(cards), self.user_name, self.gacha_cog,
                                 owned_keys=await owned_character_keys(self.user_id))
        await interaction.edit_original_response(view=inv_view)


# 📊 機率表的送出 (資料計算 rate_sheet_data 在 logic/rules.py)
async def send_rate_sheet(interaction: discord.Interaction, choice_key: str):
    """📊 機率表：按的時候才讀活動規則與按的人自己的保底進度"""
    rules = await econ.get_rules()
    resolved = resolve_pool(choice_key, rules)
    if choice_key == EVENT_POOL and len(event_pools(rules)) > 1:
        await send_notice(interaction, "🎪 現在有好幾個活動限定卡池，請用 `/card history` 的選單選要看哪一個的機率表。")
        return
    if not resolved or not pool_characters(resolved[0], rules):
        await send_notice(interaction, "🎪 這個卡池目前沒有開放，看不到機率表。")
        return
    pool_key, pool_name = resolved
    since_ur = (await get_gacha_pity(interaction.user.id)).get(pool_key, {}).get("since_ur", 0)
    view = ui.LayoutView()
    view.add_item(build_rate_sheet_container(rate_sheet_data(pool_key, pool_name, rules, since_ur), PITY_THRESHOLD, PITY_RARITY))
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=True)
    else:
        await interaction.response.send_message(view=view, ephemeral=True)


class EventPoolPickerView(ui.LayoutView):
    """🎪 同時有好幾個活動限定卡池時 (2026-11-24)：先選要抽哪一個；只有祈願的人能選，選了才扣錢、抽卡 (用選的當下的活動規則)"""
    def __init__(self, user_id: int, gacha_cog, draw_count: int, pools: dict, cost: int, source: discord.Interaction):
        super().__init__(timeout=180)
        self.user_id, self.gacha_cog, self.draw_count = user_id, gacha_cog, draw_count
        self.source = source   # 逾時要改的訊息 = 打指令 / 按繼續祈願的那個互動的原始回應
        self.busy = False
        kind = "十連" if draw_count == 10 else ("單抽" if draw_count == 1 else f"{draw_count} 抽")
        container = ui.Container(accent_color=discord.Color.gold())
        container.add_item(ui.TextDisplay(
            f"## 🎪 選擇活動限定卡池\n"
            f"現在有 **{len(pools)}** 個活動限定卡池同時開放，選一個開始{kind}祈願 (`{cost:,}` 賽錢)\n"
            f"-# 每個卡池的保底各自計算 (用 `/card history` 看)"
        ))
        self.select = ui.Select(
            placeholder="🎪 選要祈願的卡池",
            options=[discord.SelectOption(label=p["name"][:100], value=key, description=(p.get("desc") or "")[:100] or None)
                     for key, p in list(pools.items())[:25]],
        )
        self.select.callback = self.on_pick
        container.add_item(ui.ActionRow(self.select))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的祈願畫面！請輸入 `/card gacha` 開啟你自己的祈願。")
            return False
        return True

    async def on_pick(self, interaction: discord.Interaction):
        if self.busy:   # 連點：第二下直接忽略 (不會抽兩次)
            await interaction.response.defer()
            return
        self.busy = True
        try:
            if await self.gacha_cog.execute_gacha(interaction, self.draw_count, self.select.values[0]):
                self.stop()   # 畫面已經換成抽卡結果，逾時不用再改
        finally:
            self.busy = False

    async def on_timeout(self):
        self.clear_items()
        self.add_item(notice_container("⏳ 選單放太久已經停用了；要祈願請再打一次 `/card gacha`。"))
        try:
            await self.source.edit_original_response(view=self)
        except discord.HTTPException:
            pass


class GachaHistoryView(ui.LayoutView):
    """📜 祈願紀錄 + 「📊 選卡池看機率表」選單 (誰都可以選，機率表只有選的人看得到；只列現在抽得到的卡池)"""
    def __init__(self, container: ui.Container, pools: dict):
        super().__init__(timeout=600)
        self.select = ui.Select(
            placeholder="📊 選一個卡池查看機率表",
            options=[discord.SelectOption(label=p["name"], value=key) for key, p in list(pools.items())[:25]],
        )
        self.select.callback = self.view_rates
        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(self.select))
        self.add_item(container)

    async def view_rates(self, interaction: discord.Interaction):
        await send_rate_sheet(interaction, self.select.values[0])

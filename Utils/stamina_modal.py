"""
⚡ 恢復體力的彈窗 (Modal)：/profile「⚡ 恢復體力」和神社採集 / 快速採集畫面共用 (0.35.000)

彈窗裡兩個下拉選單：要吃哪一個 (列出擁有的體力料理) ➔ 吃幾個 (1 ~ 今天剩下的額度)
Discord 的 Modal 不能用 autocomplete (那只有斜線指令有)，所以用選單。
送出後呼叫 on_done(interaction, notice)：由開彈窗的畫面決定怎麼更新自己的訊息。
"""
from typing import Awaitable, Callable

import discord
from discord import ui

from Database.User_DB_Manager import (
    get_or_create_user, use_stamina_item, calc_stamina, stamina_items_left, STAMINA_ITEM_DAILY_LIMIT,
)
from Database.Item_DB_Manager import get_all_items
from Utils.components import send_notice

OnDone = Callable[[discord.Interaction, str], Awaitable[None]]


async def get_owned_stamina_items(user_id: int, inventory: dict | None = None) -> list[tuple[str, dict, int]]:
    """玩家背包裡有回復體力效果的道具：[(道具ID, 道具資料, 數量), ...]，依回復量由大到小"""
    if inventory is None:
        inventory = (await get_or_create_user(user_id))["inventory"]
    templates = await get_all_items()
    owned = [
        (iid, templates[iid], count) for iid, count in inventory.items()
        if count > 0 and iid in templates and templates[iid]["effect"].get("stamina", 0) > 0
    ]
    return sorted(owned, key=lambda x: (-x[1]["effect"]["stamina"], x[0]))


class StaminaItemModal(ui.Modal):
    def __init__(self, owned: list, daily_left: int, stamina: dict, on_done: OnDone):
        super().__init__(title="⚡ 恢復體力", timeout=300)
        self.owned = {iid: (info, count) for iid, info, count in owned}
        self.on_done = on_done
        self.item_select = ui.Select(placeholder="選一個體力料理…", options=[
            discord.SelectOption(
                label=f"{info['name']} ×{count}"[:100], value=iid, emoji=info.get("emoji") or None,
                description=f"回復 {info['effect']['stamina']} 體力"[:100], default=(i == 0))
            for i, (iid, info, count) in enumerate(owned[:25])
        ])
        self.qty_select = ui.Select(placeholder="吃幾個…", options=[
            discord.SelectOption(label=f"{n} 個", value=str(n), default=(n == 1)) for n in range(1, daily_left + 1)
        ])
        self.add_item(ui.Label(text="要吃哪一個？", component=self.item_select,
                               description=f"目前體力 {stamina['stamina']} / {stamina['max']}，道具可以讓體力超過上限"))
        self.add_item(ui.Label(text="吃幾個？", component=self.qty_select,
                               description=f"今天還能吃 {daily_left} 個（每天最多 {STAMINA_ITEM_DAILY_LIMIT} 個，含簽到的飯糰）"))

    async def on_submit(self, interaction: discord.Interaction):
        iid = self.item_select.values[0] if self.item_select.values else None
        qty = int(self.qty_select.values[0]) if self.qty_select.values else 1
        if iid not in self.owned:   # 使用者不可能選到清單外的，但還是再驗證一次
            await self.on_done(interaction, "❌ 找不到這個道具，請重新選擇。")
            return
        info = self.owned[iid][0]
        r = await use_stamina_item(interaction.user.id, iid, info["effect"]["stamina"], qty)
        if r["ok"]:
            notice = (f"✅ 吃了 {info['emoji']} **{info['name']}** ×{qty}！體力 `{r['before']}` ➔ `{r['stamina']}`"
                      f"\n-# 剩下 `{r['left']}` 個 · 今天還能吃 `{r['daily_left']}` 個")
        elif r["reason"] == "daily_limit":
            notice = f"⚠️ 今天只能再吃 `{r['daily_left']}` 個體力道具了（每天最多 {STAMINA_ITEM_DAILY_LIMIT} 個）。"
        else:
            notice = f"❌ 倉庫裡的 {info['name']} 不夠了（剩 `{r['left']}` 個）。"
        await self.on_done(interaction, notice)


async def open_stamina_modal(interaction: discord.Interaction, on_done: OnDone):
    """按下「⚡ 恢復體力」：沒有體力道具 / 今天額度用完就直接提示，不然打開彈窗"""
    user = await get_or_create_user(interaction.user.id)
    owned = await get_owned_stamina_items(interaction.user.id, user["inventory"])
    left = stamina_items_left(user.get("stamina_item_day"), user.get("stamina_item_used"))
    if not owned:
        await send_notice(interaction, "⚠️ 神社倉庫裡沒有體力道具。\n-# 每日簽到送 🍙 飯糰；其他體力料理可以在「🍳 料理」的「⚡ 體力料理」做。")
        return
    if left <= 0:
        await send_notice(interaction, f"⚠️ 今天已經吃了 {STAMINA_ITEM_DAILY_LIMIT} 個體力道具，明天 (台灣時間 00:00) 再來吧！")
        return
    stamina = calc_stamina(user.get("stamina"), user.get("stamina_updated_at"))
    await interaction.response.send_modal(StaminaItemModal(owned, left, stamina, on_done))

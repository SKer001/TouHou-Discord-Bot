"""
💸 /trade：玩家之間轉賽錢 (手續費 5% 從金額扣、每天最多轉出 500K、雙方都要累積簽到 7 天)
確認與結果只有轉出人看得到；收款人會收到私訊。規則與數值在 Database/Economy_DB_Manager.py
"""
import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Utils.components import send_notice
from .Components.trade_components import simple_container, build_transfer_dm


def reason_text(r: dict, status: dict | None = None) -> str:
    reason = r.get("reason")
    if reason == "locked":
        n = status["daily_count"] if status else 0
        return f"🔒 累積簽到 `{econ.TRADE_UNLOCK_DAILY}` 天才能使用市場與轉帳（目前 `{n}` 天）。"
    return {
        "target_locked": f"🔒 對方還沒開通交易（要累積簽到 `{econ.TRADE_UNLOCK_DAILY}` 天）。",
        "not_enough": f"❌ 賽錢不足！要轉 `{r.get('amount', 0):,}`，你只有 `{r.get('money', 0):,}`。",
        "limit": f"❌ 超過今天的轉帳額度！今天還能轉 `{r.get('left', 0):,}` 賽錢。",
        "self": "❌ 不能轉給自己。",
        "bad_amount": "❌ 金額要大於 0。",
    }.get(reason, f"❌ 轉帳失敗（{reason}）")


async def send_transfer_dm(target: discord.abc.User, sender_name: str, guild_name: str | None, amount: int, fee: int, test: bool = False) -> bool:
    """私訊收款人；對方關閉私訊時回傳 False (轉帳照樣成功)"""
    view = ui.LayoutView()
    view.add_item(build_transfer_dm(sender_name, guild_name, amount, fee, test))
    try:
        await target.send(view=view)
        return True
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        return False


class TransferView(ui.LayoutView):
    def __init__(self, user_id: int, target: discord.abc.User, amount: int, sent_today: int):
        super().__init__(timeout=120)
        self.user_id, self.target, self.amount = user_id, target, amount
        fee = econ.transfer_fee(amount)
        container = simple_container(
            f"## 💸 確認轉帳\n給 **{target.display_name}** `{amount:,}` 賽錢\n"
            f"手續費 5%：`{fee:,}` ➔ 對方實收 `{amount - fee:,}`\n"
            f"-# 今天已轉出 `{sent_today:,} / {econ.TRANSFER_DAILY_LIMIT:,}`", discord.Color.orange())
        ok = ui.Button(label="💸 確認轉帳", style=discord.ButtonStyle.success)
        ok.callback = self.on_confirm
        cancel = ui.Button(label="✖️ 取消", style=discord.ButtonStyle.secondary)
        cancel.callback = self.on_cancel
        container.add_item(ui.ActionRow(ok, cancel))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的畫面！")
            return False
        return True

    async def on_confirm(self, interaction):
        r = await econ.transfer_money(self.user_id, self.target.id, self.amount)
        if not r["ok"]:
            await send_notice(interaction, reason_text({**r, "amount": self.amount}, await econ.get_trade_status(self.user_id)))
            return
        dm_ok = await send_transfer_dm(self.target, interaction.user.display_name,
                                        interaction.guild.name if interaction.guild else None, self.amount, r["fee"])
        self.clear_items()
        self.add_item(simple_container(
            f"✅ 已轉給 **{self.target.display_name}** `{self.amount:,}` 賽錢（對方實收 `{r['received']:,}`，手續費 `{r['fee']:,}`）\n"
            f"你剩下 `{r['money']:,}` 賽錢 · 今天還能轉 `{r['left_today']:,}`" +
            ("\n-# 📨 已私訊通知對方" if dm_ok else "\n-# ⚠️ 對方關閉了私訊，沒有收到通知"), discord.Color.green()))
        await interaction.response.edit_message(view=self)

    async def on_cancel(self, interaction):
        self.clear_items()
        self.add_item(simple_container("✖️ 已取消轉帳。", discord.Color.light_grey()))
        await interaction.response.edit_message(view=self)


class TradeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="trade", description="💸 轉賽錢給其他玩家 (手續費 5%，每天最多轉出 500,000)")
    @app_commands.describe(target="收款的玩家", amount="轉出金額 (手續費從這裡扣)")
    async def trade(self, interaction: discord.Interaction, target: discord.User, amount: app_commands.Range[int, 1]):
        if target.bot:
            await send_notice(interaction, "❌ 不能轉給機器人。")
            return
        if target.id == interaction.user.id:
            await send_notice(interaction, "❌ 不能轉給自己。")
            return
        if amount > econ.TRANSFER_DAILY_LIMIT:
            await send_notice(interaction, f"❌ 每天最多轉出 `{econ.TRANSFER_DAILY_LIMIT:,}` 賽錢。")
            return
        status = await econ.get_trade_status(interaction.user.id)
        if not status["unlocked"]:
            await send_notice(interaction, reason_text({"reason": "locked"}, status))
            return
        sent = await econ.get_transfer_today(interaction.user.id)
        await interaction.response.send_message(view=TransferView(interaction.user.id, target, amount, sent), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TradeCog(bot))

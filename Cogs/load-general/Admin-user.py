import json
import discord
from discord import app_commands
from discord.ext import commands
from Database.User_DB_Manager import reset_daily, add_money, add_exp, get_or_create_user, update_user_inventory, add_stamina
from Database.Item_DB_Manager import get_all_items, get_item
from Utils.config import is_admin
from Utils.components import send_notice



class UserAdmin(commands.GroupCog, group_name="admin-user", group_description="【開發者專用】玩家數據與經濟管理指令"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        items = await get_all_items()
        choices = []
        for item_id, data in items.items():
            if current.lower() in item_id.lower() or current.lower() in data['name'].lower():
                choices.append(app_commands.Choice(name=f"{data['emoji']} {item_id} ({data['name']})", value=item_id))
        return choices[:25]

    # 1. 🛠️ /reset_daily 重置簽到
    @app_commands.command(name="reset_daily", description="【開發者專用】重置指定成員或自己的每日簽到狀態")
    @app_commands.describe(target="【可選】指定要重置的成員 (留空則重置自己)")
    @app_commands.default_permissions(administrator=True)
    async def reset_daily_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member = None):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 您沒有權限使用此開發者指令！")
            return

        target_user = target or interaction.user
        await reset_daily(target_user.id)

        await send_notice(interaction, f"🛠️ [Dev] 已成功重置 **{target_user.display_name}** 的 `/daily` 簽到狀態！")

    # 2. 💰 /add_money 調整賽錢
    @app_commands.command(name="add_money", description="【開發者專用】給予或扣除指定成員的賽錢")
    @app_commands.describe(target="要調整賽錢的成員", amount="要調整的數額 (輸入負數則為扣除)")
    @app_commands.default_permissions(administrator=True)
    async def add_money_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member, amount: int):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 您沒有權限使用此開發者指令！")
            return

        current_money = await add_money(target.id, amount)
        action_text = "給予" if amount >= 0 else "扣除"
        await send_notice(interaction, f"🛠️ [Dev] 已成功向 **{target.display_name}** {action_text} 賽錢 `{abs(amount):,}` 兩！\n目前總金額：`{current_money:,}` 兩")

    # 3. ✨ /add_exp 調整經驗值與火力
    @app_commands.command(name="add_exp", description="【開發者專用】給予或扣除指定成員經驗值 (自動驗算對應 P點)")
    @app_commands.describe(target="要調整經驗值的成員", amount="要調整的經驗值數量 (輸入負數則為扣除)")
    @app_commands.default_permissions(administrator=True)
    async def add_exp_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member, amount: int):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 您沒有權限使用此開發者指令！")
            return

        exp_result = await add_exp(target.id, amount)
        old_p, new_p, current_exp = exp_result["old_p"], exp_result["new_p"], exp_result["current_exp"]

        status_text = "給予" if amount >= 0 else "扣除"
        msg = f"🛠️ [Dev] 已成功向 **{target.display_name}** {status_text} `{abs(amount):,}` EXP！\n🔴 火力變化：`{old_p:.1f} P` ➔ **`{new_p:.1f} P`**\n✨ 剩餘經驗：`{current_exp:,}` EXP"
        
        if exp_result.get("leveled_up"): msg += "\n💥 **(POWER UP! 火力提升)**"
        elif exp_result.get("is_degraded"): msg += "\n📉 **(火力降階)**"

        await send_notice(interaction, msg)

    # 4. 🔻 /take_item 扣除指定成員特定道具 (數量<=0自動移除 Key)
    @app_commands.command(name="take_item", description="【開發者專用】扣除或移除指定成員的特定道具")
    @app_commands.describe(
        target="要扣除道具的目標成員",
        item_id="道具 ID / 名稱",
        amount="要扣除的數量"
    )
    @app_commands.autocomplete(item_id=item_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def take_item_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member, item_id: str, amount: int):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return

        if amount <= 0:
            await send_notice(interaction, "❌ 扣除數量必須大於 0！")
            return

        user_data = await get_or_create_user(target.id)
        raw_inv = user_data.get("inventory", "{}")
        inventory = json.loads(raw_inv) if isinstance(raw_inv, str) else (raw_inv or {})

        if item_id not in inventory or inventory[item_id] <= 0:
            await send_notice(interaction, f"❌ **{target.display_name}** 的背包內並沒有道具 `{item_id}`！")
            return

        current_amount = inventory[item_id]
        new_amount = current_amount - amount

        item_info = await get_item(item_id)
        item_name = f"{item_info['emoji']} {item_info['name']}" if item_info else f"`{item_id}`"

        if new_amount <= 0:
            del inventory[item_id]
            msg = f"🗑️ 已從 **{target.display_name}** 的背包中完全移除 {item_name}！"
        else:
            inventory[item_id] = new_amount
            msg = f"🔻 已成功扣除 **{target.display_name}** 的 {item_name} x `{amount}`！ (剩餘：`{new_amount}` 件)"

        await update_user_inventory(target.id, inventory)
        await send_notice(interaction, msg)

    # 5. 🧹 /clear_inventory 清空指定成員背包
    @app_commands.command(name="clear_inventory", description="【開發者專用】完全清空指定成員的背包庫存")
    @app_commands.describe(target="要清空背包的目標成員")
    @app_commands.default_permissions(administrator=True)
    async def clear_inventory_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return
        await update_user_inventory(target.id, {})
        await send_notice(interaction, f"🧹 已成功清空 **{target.display_name}** 的背包，所有道具皆已歸零移除！")

    # 6. ⚡ /add_stamina 調整體力
    @app_commands.command(name="add_stamina", description="【開發者專用】增加或扣除指定成員的體力 (可超過自然回復上限 240)")
    @app_commands.describe(target="目標成員", amount="增加的體力 (負數為扣除，最多扣到 0)")
    @app_commands.default_permissions(administrator=True)
    async def add_stamina_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member, amount: int):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return
        info = await add_stamina(target.id, amount)
        action = "增加" if amount >= 0 else "扣除"
        await send_notice(
            interaction,
            f"⚡ 已{action} **{target.display_name}** 的體力 `{abs(amount)}` 點\n目前體力：`{info['stamina']} / {info['max']}`",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(UserAdmin(bot))
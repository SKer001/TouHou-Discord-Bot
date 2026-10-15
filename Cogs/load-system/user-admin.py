import os
import json
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from Database.db_manager import reset_daily as reset_main_daily, add_money, add_exp, get_or_create_user
from Utils.item_data import get_all_items, get_item

ADMIN_ID = 403895664666214400
MAIN_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "Database", "database.db")


# ---------------------------------------------------------
# 🛠️ 內部資料庫輔助函式：更新玩家背包
# ---------------------------------------------------------
async def save_user_inventory(user_id: int, inventory: dict):
    async with aiosqlite.connect(MAIN_DB_PATH) as db:
        await db.execute(
            "UPDATE users SET inventory = ? WHERE user_id = ?",
            (json.dumps(inventory, ensure_ascii=False), user_id)
        )
        await db.commit()


class UserAdmin(commands.Cog):
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
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限使用此開發者指令！", ephemeral=True)
            return

        target_user = target or interaction.user
        await reset_main_daily(target_user.id)

        try:
            daily_db_path = os.path.join(os.path.dirname(__file__), "..", "load-general", "daily.db")
            if os.path.exists(daily_db_path):
                async with aiosqlite.connect(daily_db_path) as db:
                    await db.execute("UPDATE users_daily SET last_daily = NULL WHERE user_id = ?", (target_user.id,))
                    await db.commit()
        except Exception as e:
            print(f"⚠️ [UserAdmin] 同步重置 daily.db 時出錯: {e}")

        await interaction.response.send_message(f"🛠️ [Dev] 已成功重置 **{target_user.display_name}** 的 `/daily` 簽到狀態！", ephemeral=True)

    # 2. 💰 /add_money 調整賽錢
    @app_commands.command(name="add_money", description="【開發者專用】給予或扣除指定成員的賽錢")
    @app_commands.describe(target="要調整賽錢的成員", amount="要調整的數額 (輸入負數則為扣除)")
    @app_commands.default_permissions(administrator=True)
    async def add_money_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member, amount: int):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限使用此開發者指令！", ephemeral=True)
            return

        current_money = await add_money(target.id, amount)
        action_text = "給予" if amount >= 0 else "扣除"
        await interaction.response.send_message(
            f"🛠️ [Dev] 已成功向 **{target.display_name}** {action_text} 賽錢 `{abs(amount):,}` 兩！\n目前總金額：`{current_money:,}` 兩", ephemeral=True
        )

    # 3. ✨ /add_exp 調整經驗值與火力
    @app_commands.command(name="add_exp", description="【開發者專用】給予或扣除指定成員經驗值 (自動驗算對應 P點)")
    @app_commands.describe(target="要調整經驗值的成員", amount="要調整的經驗值數量 (輸入負數則為扣除)")
    @app_commands.default_permissions(administrator=True)
    async def add_exp_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member, amount: int):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 您沒有權限使用此開發者指令！", ephemeral=True)
            return

        exp_result = await add_exp(target.id, amount)
        old_p, new_p, current_exp = exp_result["old_p"], exp_result["new_p"], exp_result["current_exp"]

        status_text = "給予" if amount >= 0 else "扣除"
        msg = f"🛠️ [Dev] 已成功向 **{target.display_name}** {status_text} `{abs(amount):,}` EXP！\n🔴 火力變化：`{old_p:.1f} P` ➔ **`{new_p:.1f} P`**\n✨ 剩餘經驗：`{current_exp:,}` EXP"
        
        if exp_result.get("leveled_up"): msg += "\n💥 **(POWER UP! 火力提升)**"
        elif exp_result.get("is_degraded"): msg += "\n📉 **(火力降階)**"

        await interaction.response.send_message(msg, ephemeral=True)

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
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 無權限", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ 扣除數量必須大於 0！", ephemeral=True)
            return

        user_data = await get_or_create_user(target.id)
        raw_inv = user_data.get("inventory", "{}")
        inventory = json.loads(raw_inv) if isinstance(raw_inv, str) else (raw_inv or {})

        if item_id not in inventory or inventory[item_id] <= 0:
            await interaction.response.send_message(f"❌ **{target.display_name}** 的背包內並沒有道具 `{item_id}`！", ephemeral=True)
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

        await save_user_inventory(target.id, inventory)
        await interaction.response.send_message(msg, ephemeral=True)

    # 5. 🧹 /clear_inventory 清空指定成員背包
    @app_commands.command(name="clear_inventory", description="【開發者專用】完全清空指定成員的背包庫存")
    @app_commands.describe(target="要清空背包的目標成員")
    @app_commands.default_permissions(administrator=True)
    async def clear_inventory_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ 無權限", ephemeral=True)
            return

        await save_user_inventory(target.id, {})
        await interaction.response.send_message(
            f"🧹 已成功清空 **{target.display_name}** 的背包，所有道具皆已歸零移除！",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(UserAdmin(bot))
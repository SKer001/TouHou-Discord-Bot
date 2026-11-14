import discord
from discord import app_commands
from discord.ext import commands
from Database.User_DB_Manager import (
    reset_daily, add_money, add_exp, update_user_inventory, add_stamina,
    get_title_state, get_granted_titles, set_granted_title, set_equipped_title,
    get_namecard_state, grant_namecard, revoke_namecard, set_equipped_namecard,
)
from Database import title_data
from Utils.config import is_admin
from Utils.gacha_pools import load_gacha_pool
from Utils.namecards import namecard_url
from Utils.components import send_notice



class UserAdmin(commands.GroupCog, group_name="admin-user", group_description="【開發者專用】玩家數據與經濟管理指令"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

    # 4. 🧹 /clear_inventory 清空指定成員背包
    @app_commands.command(name="clear_inventory", description="【開發者專用】完全清空指定成員的神社倉庫")
    @app_commands.describe(target="要清空神社倉庫的目標成員")
    @app_commands.default_permissions(administrator=True)
    async def clear_inventory_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return
        await update_user_inventory(target.id, {})
        await send_notice(interaction, f"🧹 已成功清空 **{target.display_name}** 的神社倉庫，所有道具皆已歸零移除！")

    # 5. ⚡ /add_stamina 調整體力
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

    # 6. 🏷️ /admin-user title 管理員直接給 / 收回 / 戴上稱號 (不用符合條件；2026-11-13 使用者要求)
    TITLE_ACTIONS = [
        app_commands.Choice(name="🏷️ 戴上 (順便給)", value="equip"),
        app_commands.Choice(name="🎁 給稱號", value="grant"),
        app_commands.Choice(name="🗑️ 收回稱號", value="revoke"),
        app_commands.Choice(name="✖️ 卸下稱號", value="unequip"),
        app_commands.Choice(name="📋 查看", value="list"),
    ]

    async def title_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """稱號超過 25 個：依輸入的文字 (名稱 / id / 等級) 篩選，等級高的在前"""
        cur = current.strip().lower()
        tids = sorted(title_data.TITLES, key=lambda t: -title_data.RARITY_ORDER[title_data.TITLES[t]["rarity"]])
        return [app_commands.Choice(name=title_data.title_label(t), value=t) for t in tids
                if not cur or cur in t.lower() or cur in title_data.title_label(t).lower()][:25]

    @app_commands.command(name="title", description="【開發者專用】直接給、收回、戴上稱號 (不用符合解鎖條件)")
    @app_commands.describe(action="要做什麼", title="稱號 (可以打名稱篩選；卸下 / 查看不用填)", target="【可選】目標成員 (留空 = 自己)")
    @app_commands.choices(action=TITLE_ACTIONS)
    @app_commands.autocomplete(title=title_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def title_cmd(self, interaction: discord.Interaction, action: app_commands.Choice[str],
                        title: str | None = None, target: discord.User | discord.Member = None):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return
        user = target or interaction.user
        act = action.value
        if act in ("equip", "grant", "revoke"):
            if title not in title_data.TITLES:   # 可能繞過 autocomplete 亂打
                await send_notice(interaction, "❌ 找不到這個稱號，請從選單選。")
                return
            label = title_data.title_label(title)
        if act == "equip":
            await set_granted_title(user.id, title, True)
            await set_equipped_title(user.id, title)
            msg = f"🏷️ **{user.display_name}** 戴上了 **{label}**"
        elif act == "grant":
            await set_granted_title(user.id, title, True)
            msg = f"🎁 已給 **{user.display_name}** 稱號 **{label}** (到 /profile 可以戴上)"
        elif act == "revoke":
            await set_granted_title(user.id, title, False)
            still = title in (await get_title_state(user.id))["unlocked"]
            msg = f"🗑️ 已收回 **{user.display_name}** 的 **{label}**" + ("\n-# 他自己有達成條件，所以還是有這個稱號" if still else "")
        elif act == "unequip":
            await set_equipped_title(user.id, None)
            msg = f"✖️ **{user.display_name}** 已卸下稱號"
        else:
            msg = f"📋 **{user.display_name}** 的稱號"
        state = await get_title_state(user.id)
        granted = await get_granted_titles(user.id)
        equipped = title_data.title_label(state["equipped"]) if state["equipped"] else "沒戴"
        given = "、".join(title_data.title_label(t) for t in granted if t in title_data.TITLES) or "無"
        msg += f"\n戴著：`{equipped}`\n已解鎖 `{len(state['unlocked'])}` 個 (管理員給的：{given})"
        await send_notice(interaction, msg)

    # 7. 🖼️ /admin-user namecard 管理員直接給 / 收回 / 戴上角色名片 (2026-11-14 使用者要求)
    NAMECARD_ACTIONS = [
        app_commands.Choice(name="🎁 給名片", value="grant"),
        app_commands.Choice(name="🗑️ 收回名片", value="revoke"),
        app_commands.Choice(name="🖼️ 戴上 (順便給)", value="equip"),
        app_commands.Choice(name="📋 查看", value="list"),
    ]

    async def namecard_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """角色超過 25 位：依輸入的文字 (名字 / id) 篩選"""
        cur = current.strip().lower()
        return [app_commands.Choice(name=f"{c['name']} ({cid})"[:100], value=cid) for cid, c in load_gacha_pool().items()
                if not cur or cur in cid.lower() or cur in c["name"].lower()][:25]

    @app_commands.command(name="namecard", description="【開發者專用】直接給、收回、戴上角色名片 (不用推角稱號)")
    @app_commands.describe(action="要做什麼", character="角色 (可以打名字篩選；查看不用填)", target="【可選】目標成員 (留空 = 自己)")
    @app_commands.choices(action=NAMECARD_ACTIONS)
    @app_commands.autocomplete(character=namecard_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def namecard_cmd(self, interaction: discord.Interaction, action: app_commands.Choice[str],
                           character: str | None = None, target: discord.User | discord.Member = None):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return
        user = target or interaction.user
        act = action.value
        pool = load_gacha_pool()
        if act in ("grant", "revoke", "equip"):
            if character not in pool:   # 可能繞過 autocomplete 亂打
                await send_notice(interaction, "❌ 找不到這位角色，請從選單選。")
                return
            name = f"{pool[character]['emoji']} {pool[character]['name']}"
        if act == "grant":
            added = await grant_namecard(user.id, character, "admin")
            msg = (f"🎁 已給 **{user.display_name}** {name} 的名片 (到 /profile 可以換上)" if added
                   else f"⚠️ **{user.display_name}** 本來就有 {name} 的名片")
        elif act == "equip":
            await grant_namecard(user.id, character, "admin")
            await set_equipped_namecard(user.id, character)
            msg = f"🖼️ **{user.display_name}** 換上了 {name} 的名片"
            if namecard_url(character) is None:
                msg += "\n-# 這位角色的名片圖還沒做，資料卡暫時不會顯示圖片"
        elif act == "revoke":
            removed = await revoke_namecard(user.id, character)
            msg = (f"🗑️ 已收回 **{user.display_name}** 的 {name} 名片" if removed
                   else f"⚠️ **{user.display_name}** 沒有 {name} 的名片")
            if f"oshi_{character}" in (await get_title_state(user.id))["unlocked"]:
                msg += "\n-# 他現在還有這位角色的推角稱號，名片已經自動補回來了"
        else:
            msg = f"📋 **{user.display_name}** 的角色名片"
        state = await get_namecard_state(user.id)
        label = lambda cid: pool[cid]["name"] if cid in pool else cid
        equipped = label(state["equipped"]) if state["equipped"] else "沒放"
        owned = "、".join(label(c) for c in state["owned"]) or "無"
        msg += f"\n戴著：`{equipped}`\n擁有 `{len(state['owned'])}` 張：{owned}"
        await send_notice(interaction, msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserAdmin(bot))
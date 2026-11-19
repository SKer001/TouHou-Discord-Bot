import discord
from discord import app_commands, ui
from discord.ext import commands
from Database.User_DB_Manager import (
    reset_daily, add_money, add_exp, update_user_inventory, add_stamina,
    get_title_state, get_granted_titles, set_granted_title, set_equipped_title,
    get_namecard_state, grant_namecard, revoke_namecard, set_equipped_namecard,
)
from Database import title_data
from Utils.config import is_admin
from Utils.gacha_pools import load_gacha_pool
from Utils.namecards import namecard_url, fetch_original_file
from .Components.general_components import build_namecard_dm_view
from Utils.components import send_notice
from Utils.pagination import nav_buttons, paginate   # 📄 共用分頁



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
    #    0.35.035 改成控制台 (AdminTitleView)：稱號快 200 個，autocomplete 只列得出 25 個 (使用者要求改成選單 + 翻頁)
    @app_commands.command(name="title", description="【開發者專用】稱號控制台：選分組 ➔ 選稱號 ➔ 戴上 / 給 / 收回 (不用符合解鎖條件)")
    @app_commands.describe(target="【可選】目標成員 (留空 = 自己)")
    @app_commands.default_permissions(administrator=True)
    async def title_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member = None):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return
        view = AdminTitleView(interaction.user.id, target or interaction.user)
        await view.refresh()
        await interaction.response.send_message(view=view, ephemeral=True)

    # 7. 🖼️ /admin-user namecard 管理員直接給 / 收回 / 戴上角色名片 (2026-11-14 使用者要求)
    NAMECARD_ACTIONS = [
        app_commands.Choice(name="🎁 給名片", value="grant"),
        app_commands.Choice(name="🗑️ 收回名片", value="revoke"),
        app_commands.Choice(name="🖼️ 戴上 (順便給)", value="equip"),
        app_commands.Choice(name="📋 查看", value="list"),
        app_commands.Choice(name="📥 原檔 (私訊給我)", value="full"),
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
        if act in ("grant", "revoke", "equip", "full"):
            if character not in pool:   # 可能繞過 autocomplete 亂打
                await send_notice(interaction, "❌ 找不到這位角色，請從選單選。")
                return
            name = f"{pool[character]['emoji']} {pool[character]['name']}"
        if act == "full":   # 📥 名片原檔 (PNG / 無損 WebP) 私訊給下指令的管理員本人
            await interaction.response.defer(ephemeral=True, thinking=True)
            file = await fetch_original_file(self.bot, character, "full")
            if file is None:
                await send_notice(interaction, f"⚠️ {name} 的名片原圖還沒上傳 (tools/card_art/upload_namecard.py)，或私人頻道抓不到。")
                return
            try:
                await interaction.user.send(view=build_namecard_dm_view(pool[character]["name"], file, full=True), file=file)
            except discord.Forbidden:
                await send_notice(interaction, "❌ 沒辦法私訊你：請打開伺服器的「私人訊息」設定。")
                return
            await send_notice(interaction, f"📥 已把 {name} 的名片原檔 `{file.filename}` 私訊給你")
            return
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


# =========================================================
# 🏷️ /admin-user title 控制台 (0.35.035)
# =========================================================
ADMIN_TITLES_PER_PAGE = 25   # 稱號選單一頁幾個 (Discord 上限 25)
ADMIN_GROUPS_PER_PAGE = 25   # 分組選單一頁幾組


class AdminTitleView(ui.LayoutView):
    """
    ① 分組選單 (全部分組，超過 25 組才多一排翻頁) ➔ ② 那組的稱號選單 (一頁 25 個，超過才多一排翻頁)
    ➔ ③ 選好的稱號：🏷️ 戴上 (順便給) / 🎁 給 / 🗑️ 收回；另外隨時可以 ✖️ 卸下
    每次操作後重新讀對方的稱號狀態，結果顯示在最上面。只有下指令的管理員能按。
    """

    def __init__(self, admin_id: int, user):
        super().__init__(timeout=900)
        self.admin_id = admin_id
        self.user = user
        order = sorted(title_data.TITLES, key=lambda t: -title_data.RARITY_ORDER[title_data.TITLES[t]["rarity"]])
        self.groups = title_data.group_titles(order)   # {分組: [稱號 id (等級高的在前)]}
        self.group = next(iter(self.groups))
        self.group_page = 1
        self.title_page = 1
        self.selected = None                  # 選好的稱號 id
        self.notice = None                    # 上一次操作的結果
        self.state = {"equipped": None, "unlocked": [], "stats": {}}
        self.granted = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id or not is_admin(interaction.user):
            await send_notice(interaction, "❌ 這不是你的控制台")
            return False
        return True

    async def refresh(self):
        self.state = await get_title_state(self.user.id)
        self.granted = [t for t in await get_granted_titles(self.user.id) if t in title_data.TITLES]
        self.build()

    def _group_name(self, key: str) -> str:
        return title_data.TITLE_GROUPS.get(key, {}).get("name", "📌 其他")

    def _status(self, tid: str) -> str:
        tags = []
        if tid == self.state["equipped"]:
            tags.append("🏷️ 戴著")
        if tid in self.granted:
            tags.append("🎁 管理員給的")
        elif tid in self.state["unlocked"]:
            tags.append("✅ 自己達成")
        return "、".join(tags) or "🔒 沒有"

    def build(self):
        self.clear_items()
        unlocked, equipped = self.state["unlocked"], self.state["equipped"]
        c = ui.Container(accent_color=discord.Color(title_data.title_color(self.selected or equipped)))
        if self.notice:
            c.add_item(ui.TextDisplay(self.notice))
            c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(
            f"## 🏷️ 稱號控制台：{self.user.display_name}\n"
            f"戴著：`{title_data.title_label(equipped) if equipped else '沒戴'}`　"
            f"已解鎖 `{len(unlocked)}` / `{len(title_data.TITLES)}` 個 (管理員給的 `{len(self.granted)}` 個)\n"
            "-# 選分組 ➔ 選稱號 ➔ 按下面的按鈕；管理員給的稱號不用符合解鎖條件"))
        if self.selected:
            c.add_item(ui.Separator())
            c.add_item(ui.TextDisplay(
                f"**{title_data.title_label(self.selected)}**　{self._group_name(title_data.title_group(self.selected) or 'other')}\n"
                f"-# {title_data.title_desc(self.selected, self.state.get('stats'))}\n狀態：{self._status(self.selected)}"))
        self.add_item(c)

        # ① 分組選單
        gp = paginate(list(self.groups), self.group_page, ADMIN_GROUPS_PER_PAGE)
        self.group_page = gp.page
        gsel = ui.Select(placeholder="🗂️ 稱號分組" + (f" (第 {gp.page} / {gp.total} 頁)" if gp.total > 1 else ""), options=[
            discord.SelectOption(label=self._group_name(k)[:100], value=k, default=k == self.group,
                                 description=f"{sum(t in unlocked for t in self.groups[k])} / {len(self.groups[k])} 個已解鎖")
            for k in gp.items])
        gsel.callback = self.on_group
        self.add_item(ui.ActionRow(gsel))
        if gp.total > 1:
            self.add_item(ui.ActionRow(*nav_buttons(gp.page, gp.total, self.set_group_page, "compact")))

        # ② 那組的稱號選單
        tp = paginate(self.groups[self.group], self.title_page, ADMIN_TITLES_PER_PAGE)
        self.title_page = tp.page
        tsel = ui.Select(
            placeholder=f"🏷️ 選稱號：{self._group_name(self.group)}" + (f" (第 {tp.page} / {tp.total} 頁)" if tp.total > 1 else ""),
            options=[discord.SelectOption(label=title_data.title_label(t)[:100], value=t, default=t == self.selected,
                                          description=self._status(t)[:100]) for t in tp.items])
        tsel.callback = self.on_title
        self.add_item(ui.ActionRow(tsel))
        if tp.total > 1:
            self.add_item(ui.ActionRow(*nav_buttons(tp.page, tp.total, self.set_title_page)))

        # ③ 操作按鈕
        sel = self.selected
        row = []
        for label, style, cb, disabled in [
            ("🏷️ 戴上 (順便給)", discord.ButtonStyle.success, self.on_equip, sel is None or sel == equipped),
            ("🎁 給", discord.ButtonStyle.primary, self.on_grant, sel is None or sel in self.granted),
            ("🗑️ 收回", discord.ButtonStyle.danger, self.on_revoke, sel is None or sel not in self.granted),
            ("✖️ 卸下稱號", discord.ButtonStyle.secondary, self.on_unequip, equipped is None),
        ]:
            b = ui.Button(label=label, style=style, disabled=disabled)
            b.callback = cb
            row.append(b)
        self.add_item(ui.ActionRow(*row))

    async def _done(self, interaction: discord.Interaction, notice: str | None = None):
        self.notice = notice
        await self.refresh()
        await interaction.response.edit_message(view=self)

    async def on_group(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        if value in self.groups:
            self.group, self.title_page, self.selected = value, 1, None
        await self._done(interaction)

    async def set_group_page(self, interaction: discord.Interaction, page: int):
        self.group_page = page
        await self._done(interaction)

    async def set_title_page(self, interaction: discord.Interaction, page: int):
        self.title_page = page
        await self._done(interaction)

    async def on_title(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        self.selected = value if value in title_data.TITLES else None
        await self._done(interaction)

    async def on_equip(self, interaction: discord.Interaction):
        await set_granted_title(self.user.id, self.selected, True)
        await set_equipped_title(self.user.id, self.selected)
        await self._done(interaction, f"🏷️ **{self.user.display_name}** 戴上了 **{title_data.title_label(self.selected)}**")

    async def on_grant(self, interaction: discord.Interaction):
        await set_granted_title(self.user.id, self.selected, True)
        await self._done(interaction, f"🎁 已給 **{self.user.display_name}** 稱號 **{title_data.title_label(self.selected)}** (到 /profile 可以戴上)")

    async def on_revoke(self, interaction: discord.Interaction):
        await set_granted_title(self.user.id, self.selected, False)
        still = self.selected in (await get_title_state(self.user.id))["unlocked"]
        await self._done(interaction, f"🗑️ 已收回 **{self.user.display_name}** 的 **{title_data.title_label(self.selected)}**"
                         + ("\n-# 他自己有達成條件，所以還是有這個稱號" if still else ""))

    async def on_unequip(self, interaction: discord.Interaction):
        await set_equipped_title(self.user.id, None)
        await self._done(interaction, f"✖️ **{self.user.display_name}** 已卸下稱號")


async def setup(bot: commands.Bot):
    await bot.add_cog(UserAdmin(bot))
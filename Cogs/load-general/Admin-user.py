import discord
from discord import app_commands, ui
from discord.ext import commands
from Database.User_DB_Manager import (
    reset_daily, add_money, add_exp, update_user_inventory, add_stamina,
    get_title_state, get_granted_titles, set_granted_title, set_equipped_title,
    get_namecard_state, grant_namecard, revoke_namecard, set_equipped_namecard,
)
from Database import title_data, namecard_data
from Utils.config import is_admin
from Utils.gacha_pools import GACHA_POOLS, load_gacha_pool
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
    #    0.35.036 改成控制台 (AdminNamecardView)：角色加上 TH07 之後會超過 25 位，autocomplete 列不完
    @app_commands.command(name="namecard", description="【開發者專用】名片控制台：選卡池 ➔ 選角色 ➔ 戴上 / 給 / 收回 / 原檔 (不用推角稱號)")
    @app_commands.describe(target="【可選】目標成員 (留空 = 自己)")
    @app_commands.default_permissions(administrator=True)
    async def namecard_cmd(self, interaction: discord.Interaction, target: discord.User | discord.Member = None):
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return
        view = AdminNamecardView(self.bot, interaction.user.id, target or interaction.user)
        await view.refresh()
        await interaction.response.send_message(view=view, ephemeral=True)


# =========================================================
# 🗂️ 管理員控制台共用：分組選單 ➔ 選項選單 (翻頁) ➔ 按鈕 (0.35.035 稱號、0.35.036 名片)
# =========================================================
PICKER_PAGE = 25   # 分組 / 選項選單一頁幾個 (Discord 上限 25)；超過才多一排翻頁按鈕


class AdminPickerView(ui.LayoutView):
    """
    子類別要給：
    - groups：{分組 key: [選項 id, ...]} (照顯示順序)
    - group_name(key)、item_label(id)、item_status(id) (選項說明)、header() (標題文字)、detail(id) (選好後的說明)
    - accent()、actions() ➔ [(按鈕文字, 樣式, callback, 停用?), ...]
    - load()：重新讀對方的資料 (每次操作後呼叫)
    每次操作後重新讀資料，結果顯示在最上面 (self.notice)。只有下指令的管理員能按。
    """
    GROUP_PLACEHOLDER = "🗂️ 分組"
    ITEM_PLACEHOLDER = "選一個…"

    def __init__(self, admin_id: int, user, groups: dict[str, list[str]]):
        super().__init__(timeout=900)
        self.admin_id = admin_id
        self.user = user
        self.groups = {k: v for k, v in groups.items() if v}
        self.group = next(iter(self.groups))
        self.group_page = 1
        self.item_page = 1
        self.selected = None   # 選好的選項 id
        self.notice = None     # 上一次操作的結果

    # ---------- 子類別要實作 ----------
    async def load(self): ...
    def group_name(self, key: str) -> str: return key
    def item_label(self, item: str) -> str: return item
    def item_status(self, item: str) -> str: return ""
    def header(self) -> str: return ""
    def detail(self, item: str) -> str: return ""
    def accent(self) -> discord.Color | None: return None
    def actions(self) -> list: return []

    # ---------- 共用 ----------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id or not is_admin(interaction.user):
            await send_notice(interaction, "❌ 這不是你的控制台")
            return False
        return True

    async def refresh(self):
        await self.load()
        self.build()

    def build(self):
        self.clear_items()
        c = ui.Container(accent_color=self.accent())
        if self.notice:
            c.add_item(ui.TextDisplay(self.notice))
            c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(self.header()))
        if self.selected:
            c.add_item(ui.Separator())
            c.add_item(ui.TextDisplay(self.detail(self.selected)))
        self.add_item(c)

        # ① 分組選單
        gp = paginate(list(self.groups), self.group_page, PICKER_PAGE)
        self.group_page = gp.page
        gsel = ui.Select(placeholder=self.GROUP_PLACEHOLDER + (f" (第 {gp.page} / {gp.total} 頁)" if gp.total > 1 else ""),
                         options=[discord.SelectOption(label=self.group_name(k)[:100], value=k, default=k == self.group,
                                                       description=self.group_status(k)[:100] or None) for k in gp.items])
        gsel.callback = self.on_group
        self.add_item(ui.ActionRow(gsel))
        if gp.total > 1:
            self.add_item(ui.ActionRow(*nav_buttons(gp.page, gp.total, self.set_group_page, "compact")))

        # ② 那組的選項選單
        ip = paginate(self.groups[self.group], self.item_page, PICKER_PAGE)
        self.item_page = ip.page
        isel = ui.Select(placeholder=f"{self.ITEM_PLACEHOLDER}：{self.group_name(self.group)}"[:140]
                         + (f" (第 {ip.page} / {ip.total} 頁)" if ip.total > 1 else ""),
                         options=[discord.SelectOption(label=self.item_label(i)[:100], value=i, default=i == self.selected,
                                                       description=self.item_status(i)[:100] or None) for i in ip.items])
        isel.callback = self.on_item
        self.add_item(ui.ActionRow(isel))
        if ip.total > 1:
            self.add_item(ui.ActionRow(*nav_buttons(ip.page, ip.total, self.set_item_page)))

        # ③ 操作按鈕
        row = []
        for label, style, cb, disabled in self.actions():
            b = ui.Button(label=label, style=style, disabled=disabled)
            b.callback = cb
            row.append(b)
        if row:
            self.add_item(ui.ActionRow(*row))

    def group_status(self, key: str) -> str:
        return ""

    async def done(self, interaction: discord.Interaction, notice: str | None = None):
        self.notice = notice
        await self.refresh()
        await interaction.response.edit_message(view=self)

    async def on_group(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        if value in self.groups:
            self.group, self.item_page, self.selected = value, 1, None
        await self.done(interaction)

    async def set_group_page(self, interaction: discord.Interaction, page: int):
        self.group_page = page
        await self.done(interaction)

    async def set_item_page(self, interaction: discord.Interaction, page: int):
        self.item_page = page
        await self.done(interaction)

    async def on_item(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        self.selected = value if any(value in items for items in self.groups.values()) else None
        await self.done(interaction)


# =========================================================
# 🏷️ /admin-user title 控制台 (0.35.035)
# =========================================================
class AdminTitleView(AdminPickerView):
    """🗂️ 稱號分組 ➔ 🏷️ 稱號 (一頁 25 個) ➔ 🏷️ 戴上 (順便給) / 🎁 給 / 🗑️ 收回 / ✖️ 卸下"""
    GROUP_PLACEHOLDER = "🗂️ 稱號分組"
    ITEM_PLACEHOLDER = "🏷️ 選稱號"

    def __init__(self, admin_id: int, user):
        order = sorted(title_data.TITLES, key=lambda t: -title_data.RARITY_ORDER[title_data.TITLES[t]["rarity"]])
        super().__init__(admin_id, user, title_data.group_titles(order))   # {分組: [稱號 id (等級高的在前)]}
        self.state = {"equipped": None, "unlocked": [], "stats": {}}
        self.granted = []

    async def load(self):
        self.state = await get_title_state(self.user.id)
        self.granted = [t for t in await get_granted_titles(self.user.id) if t in title_data.TITLES]

    def group_name(self, key):
        return title_data.TITLE_GROUPS.get(key, {}).get("name", "📌 其他")

    def group_status(self, key):
        return f"{sum(t in self.state['unlocked'] for t in self.groups[key])} / {len(self.groups[key])} 個已解鎖"

    def item_label(self, tid):
        return title_data.title_label(tid)

    def item_status(self, tid):
        tags = []
        if tid == self.state["equipped"]:
            tags.append("🏷️ 戴著")
        if tid in self.granted:
            tags.append("🎁 管理員給的")
        elif tid in self.state["unlocked"]:
            tags.append("✅ 自己達成")
        return "、".join(tags) or "🔒 沒有"

    def accent(self):
        return discord.Color(title_data.title_color(self.selected or self.state["equipped"]))

    def header(self):
        equipped = self.state["equipped"]
        return (f"## 🏷️ 稱號控制台：{self.user.display_name}\n"
                f"戴著：`{title_data.title_label(equipped) if equipped else '沒戴'}`　"
                f"已解鎖 `{len(self.state['unlocked'])}` / `{len(title_data.TITLES)}` 個 (管理員給的 `{len(self.granted)}` 個)\n"
                "-# 選分組 ➔ 選稱號 ➔ 按下面的按鈕；管理員給的稱號不用符合解鎖條件")

    def detail(self, tid):
        return (f"**{title_data.title_label(tid)}**　{self.group_name(title_data.title_group(tid) or 'other')}\n"
                f"-# {title_data.title_desc(tid, self.state.get('stats'))}\n狀態：{self.item_status(tid)}")

    def actions(self):
        sel, equipped = self.selected, self.state["equipped"]
        return [
            ("🏷️ 戴上 (順便給)", discord.ButtonStyle.success, self.on_equip, sel is None or sel == equipped),
            ("🎁 給", discord.ButtonStyle.primary, self.on_grant, sel is None or sel in self.granted),
            ("🗑️ 收回", discord.ButtonStyle.danger, self.on_revoke, sel is None or sel not in self.granted),
            ("✖️ 卸下稱號", discord.ButtonStyle.secondary, self.on_unequip, equipped is None),
        ]

    async def on_equip(self, interaction: discord.Interaction):
        await set_granted_title(self.user.id, self.selected, True)
        await set_equipped_title(self.user.id, self.selected)
        await self.done(interaction, f"🏷️ **{self.user.display_name}** 戴上了 **{title_data.title_label(self.selected)}**")

    async def on_grant(self, interaction: discord.Interaction):
        await set_granted_title(self.user.id, self.selected, True)
        await self.done(interaction, f"🎁 已給 **{self.user.display_name}** 稱號 **{title_data.title_label(self.selected)}** (到 /profile 可以戴上)")

    async def on_revoke(self, interaction: discord.Interaction):
        await set_granted_title(self.user.id, self.selected, False)
        still = self.selected in (await get_title_state(self.user.id))["unlocked"]
        await self.done(interaction, f"🗑️ 已收回 **{self.user.display_name}** 的 **{title_data.title_label(self.selected)}**"
                        + ("\n-# 他自己有達成條件，所以還是有這個稱號" if still else ""))

    async def on_unequip(self, interaction: discord.Interaction):
        await set_equipped_title(self.user.id, None)
        await self.done(interaction, f"✖️ **{self.user.display_name}** 已卸下稱號")


# =========================================================
# 🖼️ /admin-user namecard 控制台 (0.35.036)
# =========================================================
class AdminNamecardView(AdminPickerView):
    """🎰 卡池 ➔ 角色 (一頁 25 位) ➔ 🖼️ 戴上 (順便給) / 🎁 給 / 🗑️ 收回 / ✖️ 不放名片 / 📥 原檔 (私訊給我)"""
    GROUP_PLACEHOLDER = "🎰 卡池"
    ITEM_PLACEHOLDER = "🖼️ 選角色"

    def __init__(self, bot, admin_id: int, user):
        self.bot = bot
        self.pool = load_gacha_pool()
        groups = {key: [] for key in GACHA_POOLS}
        for cid, info in self.pool.items():
            groups.setdefault(info.get("pool") or "other", []).append(cid)
        super().__init__(admin_id, user, groups)
        self.state = {"equipped": None, "owned": []}

    async def load(self):
        self.state = await get_namecard_state(self.user.id)

    def name(self, cid):
        info = self.pool.get(cid, {})
        return f"{info.get('emoji', '🖼️')} {info.get('name', cid)}"

    def group_name(self, key):
        return GACHA_POOLS.get(key, {}).get("name", "📌 其他")

    def group_status(self, key):
        return f"{sum(c in self.state['owned'] for c in self.groups[key])} / {len(self.groups[key])} 張已擁有"

    def item_label(self, cid):
        return self.name(cid)

    def item_status(self, cid):
        tags = []
        if cid == self.state["equipped"]:
            tags.append("🖼️ 戴著")
        tags.append("✅ 擁有" if cid in self.state["owned"] else "🔒 沒有")
        if namecard_url(cid) is None:
            tags.append("名片圖還沒做")
        return "、".join(tags)

    def accent(self):
        return discord.Color.from_rgb(88, 101, 242)

    def header(self):
        equipped = self.state["equipped"]
        return (f"## 🖼️ 名片控制台：{self.user.display_name}\n"
                f"戴著：`{self.name(equipped) if equipped else '沒放'}`　擁有 `{len(self.state['owned'])}` / `{len(self.pool)}` 張\n"
                "-# 選卡池 ➔ 選角色 ➔ 按下面的按鈕；管理員給的名片不用推角稱號")

    def detail(self, cid):
        card = namecard_data.namecard_info(cid)
        lines = [f"**{self.name(cid)} 的名片**" + (f"　「{card['name']}」" if card else "")]
        if card:
            lines.append(f"-# {card['desc']}")
        lines.append(f"狀態：{self.item_status(cid)}")
        return "\n".join(lines)

    def actions(self):
        sel, equipped, owned = self.selected, self.state["equipped"], self.state["owned"]
        return [
            ("🖼️ 戴上 (順便給)", discord.ButtonStyle.success, self.on_equip, sel is None or sel == equipped),
            ("🎁 給", discord.ButtonStyle.primary, self.on_grant, sel is None or sel in owned),
            ("🗑️ 收回", discord.ButtonStyle.danger, self.on_revoke, sel is None or sel not in owned),
            ("✖️ 不放名片", discord.ButtonStyle.secondary, self.on_unequip, equipped is None),
            ("📥 原檔", discord.ButtonStyle.secondary, self.on_full, sel is None),
        ]

    async def on_equip(self, interaction: discord.Interaction):
        await grant_namecard(self.user.id, self.selected, "admin")
        await set_equipped_namecard(self.user.id, self.selected)
        msg = f"🖼️ **{self.user.display_name}** 換上了 {self.name(self.selected)} 的名片"
        if namecard_url(self.selected) is None:
            msg += "\n-# 這位角色的名片圖還沒做，資料卡暫時不會顯示圖片"
        await self.done(interaction, msg)

    async def on_grant(self, interaction: discord.Interaction):
        await grant_namecard(self.user.id, self.selected, "admin")
        await self.done(interaction, f"🎁 已給 **{self.user.display_name}** {self.name(self.selected)} 的名片 (到 /profile 可以換上)")

    async def on_revoke(self, interaction: discord.Interaction):
        await revoke_namecard(self.user.id, self.selected)
        msg = f"🗑️ 已收回 **{self.user.display_name}** 的 {self.name(self.selected)} 名片"
        if f"oshi_{self.selected}" in (await get_title_state(self.user.id))["unlocked"]:   # 這裡會順便把名片補回來
            msg += "\n-# 他現在還有這位角色的推角稱號，名片已經自動補回來了"
        await self.done(interaction, msg)

    async def on_unequip(self, interaction: discord.Interaction):
        await set_equipped_namecard(self.user.id, None)
        await self.done(interaction, f"✖️ **{self.user.display_name}** 已經不放名片了")

    async def on_full(self, interaction: discord.Interaction):
        """📥 名片原檔 (PNG / 無損 WebP) 私訊給下指令的管理員本人；控制台不變，結果另外私下提示"""
        cid = self.selected
        await interaction.response.defer(ephemeral=True, thinking=True)
        file = await fetch_original_file(self.bot, cid, "full")
        if file is None:
            await send_notice(interaction, f"⚠️ {self.name(cid)} 的名片原圖還沒上傳 (tools/card_art/upload_namecard.py)，或私人頻道抓不到。")
            return
        try:
            await interaction.user.send(view=build_namecard_dm_view(self.pool[cid]["name"], file, full=True), file=file)
        except discord.Forbidden:
            await send_notice(interaction, "❌ 沒辦法私訊你：請打開伺服器的「私人訊息」設定。")
            return
        await send_notice(interaction, f"📥 已把 {self.name(cid)} 的名片原檔 `{file.filename}` 私訊給你")


async def setup(bot: commands.Bot):
    await bot.add_cog(UserAdmin(bot))
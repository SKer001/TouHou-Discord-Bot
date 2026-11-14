import importlib
import random
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Database.User_DB_Manager import (
    get_or_create_user, update_visibility, add_money, add_exp,
    get_daily_status as db_get_daily_status, claim_daily, calc_stamina,
    add_item, use_stamina_item, get_title_state, set_equipped_title,
    get_namecard_state, set_equipped_namecard,
)
from Database import title_data, namecard_data
from Utils.gacha_pools import load_gacha_pool
from Utils.namecards import namecard_url, namecard_original, fetch_original_file
from Database.Item_DB_Manager import get_all_items, get_item, DAILY_REWARD_ITEM
from .Components.general_components import (
    build_profile_container,
    build_daily_repeat_container,
    build_power_up_container,
    build_notice_container,
    build_stamina_item_container,
    build_namecard_dm_view,
)
from Utils.components import send_notice

# ---------------------------------------------------------
# ⚙️ 常數設定
# ---------------------------------------------------------
TAIWAN_TZ = timezone(timedelta(hours=8))

# 運勢等級 (0~5) 對應的賽錢範圍
MONEY_RANGES = {
    5: (1500, 2000),
    4: (800, 1200),
    3: (500, 790),
    2: (300, 490),
    1: (150, 290),
    0: (50, 140),
}


def today_str() -> str:
    return datetime.now(TAIWAN_TZ).strftime("%Y-%m-%d")


def make_view(container: ui.Container) -> ui.LayoutView:
    """把一張 Container 包成可送出的 V2 訊息 (提示卡、升級卡用)"""
    view = ui.LayoutView()
    view.add_item(container)
    return view


# ---------------------------------------------------------
# 📅 每日簽到：簽到日期與當日運勢存在 Users.db 的 users 資料表
#    (資料庫操作請見 Database/User_DB_Manager.py；這裡只負責決定「今天」是哪一天)
# ---------------------------------------------------------
async def get_daily_status(user_id: int) -> dict:
    """唯讀查詢今天的簽到狀態：{"signed_today": bool, "fortune_level": int | None}"""
    return await db_get_daily_status(user_id, today_str())


async def perform_daily(user_id: int) -> dict | None:
    """
    執行每日簽到。已簽到過則回傳 None (呼叫端負責顯示「重複簽到」提示)；
    成功則回傳 {"fortune_level", "money_gained", "exp_gained", "new_money", "exp_result"}。
    """
    fortune_level = random.randint(0, 5)
    if not await claim_daily(user_id, today_str(), fortune_level):
        return None

    rules = await econ.get_rules()   # 活動預留位：daily_money / daily_exp 倍率、daily_items 額外道具
    min_m, max_m = MONEY_RANGES.get(fortune_level, (300, 500))
    money_gained = int(round(random.randint(min_m, max_m) * econ.modifier(rules, "daily_money")))
    exp_gained = int(round(random.randint(100, 200) * econ.modifier(rules, "daily_exp")))

    # 呼叫主資料庫統一寫入，確保全域資料同步
    new_money = await add_money(user_id, money_gained)
    exp_result = await add_exp(user_id, exp_gained)

    # 🍙 簽到固定贈送的道具 (道具不存在於 Item.db 時就不送)
    items = []
    for item_id, amount in [list(DAILY_REWARD_ITEM)] + rules.get("daily_items", []):
        item_info = await get_item(item_id)
        if item_info and amount > 0:
            await add_item(user_id, item_id, amount)
            items.append({"item_id": item_id, "name": item_info["name"], "emoji": item_info["emoji"], "amount": amount})
    item_reward = items[0] if items else None

    return {
        "fortune_level": fortune_level,
        "money_gained": money_gained,
        "exp_gained": exp_gained,
        "new_money": new_money,
        "exp_result": exp_result,
        "item": item_reward,
        "items": items,
    }


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


# ---------------------------------------------------------
# ⚡ 恢復體力 View (Components V2)：選道具 ➔ 確認使用 ➔ 可繼續使用或返回資料卡
# ---------------------------------------------------------
class StaminaItemView(ui.LayoutView):
    def __init__(self, profile_view, user, owned: list, stamina: dict):
        super().__init__(timeout=180)
        self.profile_view = profile_view
        self.user = user
        self.owned = owned
        self.stamina = stamina
        self.selected = None
        self.notice = None
        self.busy = False   # 使用按鈕連點保護
        self.build()

    def build(self):
        self.clear_items()
        container = build_stamina_item_container(self.user, self.stamina, self.owned, self.selected, self.notice)
        container.add_item(ui.Separator())

        if self.owned:
            select = ui.Select(placeholder="🎒 選擇要使用的體力道具...", options=[
                discord.SelectOption(
                    label=f"{info['name']} ×{count}"[:100],
                    description=f"回復 {info['effect']['stamina']} 體力"[:100],
                    value=iid,
                    emoji=info["emoji"],
                    default=(iid == self.selected),
                )
                for iid, info, count in self.owned[:25]
            ])
            select.callback = self.on_select
            container.add_item(ui.ActionRow(select))

        buttons = []
        if self.selected:
            use_btn = ui.Button(label="🍽️ 使用 1 個", style=discord.ButtonStyle.success)
            use_btn.callback = self.on_use
            buttons.append(use_btn)
        back_btn = ui.Button(label="🔙 返回資料卡", style=discord.ButtonStyle.secondary)
        back_btn.callback = self.on_back
        buttons.append(back_btn)
        container.add_item(ui.ActionRow(*buttons))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await send_notice(interaction, "❌ 這不是你的神社倉庫！")
            return False
        return True

    async def refresh_data(self):
        user_data = await get_or_create_user(self.user.id)
        self.stamina = calc_stamina(user_data.get("stamina"), user_data.get("stamina_updated_at"))
        self.owned = await get_owned_stamina_items(self.user.id, user_data["inventory"])
        if self.selected not in {iid for iid, _, _ in self.owned}:
            self.selected = None

    async def on_select(self, interaction: discord.Interaction):
        self.selected = interaction.data["values"][0]
        self.notice = None
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_use(self, interaction: discord.Interaction):
        if self.busy:
            await interaction.response.defer()
            return
        self.busy = True
        try:
            info = next((i for iid, i, _ in self.owned if iid == self.selected), None)
            if info is None:
                self.notice = "❌ 找不到這個道具，請重新選擇。"
            else:
                result = await use_stamina_item(self.user.id, self.selected, info["effect"]["stamina"])
                if result["ok"]:
                    self.notice = (
                        f"✅ 使用了 {info['emoji']} **{info['name']}**！"
                        f"體力 `{result['before']}` ➔ `{result['stamina']}`（剩下 `{result['left']}` 個）"
                    )
                else:
                    self.notice = "❌ 倉庫裡已經沒有這個道具了。"
            await self.refresh_data()
            self.build()
            await interaction.response.edit_message(view=self)
        finally:
            self.busy = False

    async def on_back(self, interaction: discord.Interaction):
        user_data = await get_or_create_user(self.user.id)
        daily_status = await get_daily_status(self.user.id)
        self.profile_view.build(user_data, daily_status)
        self.stop()
        await interaction.response.edit_message(view=self.profile_view)


# ---------------------------------------------------------
# 🎛️ 資料卡 View (Components V2)：卡片內含「投賽錢簽到」按鈕
# ---------------------------------------------------------
NAMECARD_OPTIONS = 24   # 名片選單最多列幾張 (再加「不放名片」= Discord 上限 25)


class ProfileView(ui.LayoutView):
    def __init__(self, target_user, is_self: bool, title_state: dict,
                 user_data: dict, daily_status: dict, reward: dict | None = None,
                 namecard_state: dict | None = None):
        super().__init__(timeout=180)
        self.target_user = target_user
        self.is_self = is_self
        self.title_state = title_state   # get_title_state()：{"equipped", "unlocked"}
        self.namecard_state = namecard_state or {"equipped": None, "owned": []}   # get_namecard_state()
        self.title_group = None          # 稱號選單目前選的分組 (None = 戴著的稱號那組，沒戴就是最高等級那組)
        self.data = None                 # 最近一次 build 的 (user_data, daily_status)，切換分組時重畫用
        self.reward = reward          # 剛簽到完的獎勵 (只顯示在這張卡片上)
        self.message = None           # 送出後由指令填入，供逾時時停用按鈕
        self.daily_button = None
        self.build(user_data, daily_status)

    def build(self, user_data: dict, daily_status: dict):
        """依最新資料重新組出整張卡片；只有本人的卡片才有簽到按鈕"""
        self.data = (user_data, daily_status)
        button = None
        if self.is_self:
            if daily_status["signed_today"]:
                button = ui.Button(label="✅ 今日已簽到", style=discord.ButtonStyle.secondary, disabled=True)
            else:
                button = ui.Button(label="⛩️ 投賽錢簽到", style=discord.ButtonStyle.success)
                button.callback = self.on_daily
        self.daily_button = button

        stamina = calc_stamina(user_data.get("stamina"), user_data.get("stamina_updated_at"))
        container = build_profile_container(
            self.target_user, user_data, daily_status, self.title_state["equipped"],
            is_self=self.is_self, reward=self.reward, daily_button=button, stamina=stamina,
            namecard_url=namecard_url(self.namecard_state["equipped"]),
            namecard_caption=namecard_data.namecard_caption(self.namecard_state["equipped"]),
        )
        # 🏷️ 更換稱號、🖼️ 更換名片、⚡ 恢復體力：只有本人的卡片才有
        if self.is_self:
            container.add_item(ui.Separator())
            for select in self._title_selects():
                container.add_item(ui.ActionRow(select))
            container.add_item(ui.ActionRow(self._namecard_select()))
            stamina_btn = ui.Button(label="⚡ 恢復體力", style=discord.ButtonStyle.primary)
            stamina_btn.callback = self.on_stamina
            shrine_btn = ui.Button(label="⛩️ 前往神社", style=discord.ButtonStyle.secondary)
            shrine_btn.callback = self.on_shrine
            row = [stamina_btn, shrine_btn]
            if namecard_original(self.namecard_state["equipped"]):   # 📥 戴著的名片有原圖 ➔ 可以下載
                download_btn = ui.Button(label="📥 下載名片原圖", style=discord.ButtonStyle.secondary)
                download_btn.callback = self.on_download_namecard
                row.append(download_btn)
            container.add_item(ui.Separator())
            container.add_item(ui.ActionRow(*row))
        self.clear_items()
        self.add_item(container)

    def _title_selects(self) -> list[ui.Select]:
        """
        🏷️ 更換稱號：先選分組，再選那組已解鎖的稱號 (Discord 選單最多 25 個選項，稱號全放一起會放不下)
        一個都沒解鎖 ➔ 只有一個反灰的選單
        """
        unlocked, equipped = self.title_state["unlocked"], self.title_state["equipped"]
        if not unlocked:
            select = ui.Select(placeholder="🏷️ 還沒有解鎖任何稱號 (祈願 10 抽就有第一個)", disabled=True,
                               options=[discord.SelectOption(label="不戴稱號", value="__none__")])
            return [select]
        groups = title_data.group_titles(unlocked)
        current = self.title_group
        if current not in groups:
            current = title_data.title_group(equipped) if equipped in unlocked else None
            if current not in groups:
                current = title_data.title_group(unlocked[0]) or next(iter(groups))
        self.title_group = current

        group_select = ui.Select(placeholder="🗂️ 稱號分組…", options=[
            discord.SelectOption(
                label=title_data.TITLE_GROUPS.get(key, {}).get("name", "🏷️ 其他"), value=key, default=(key == current),
                description=f"已解鎖 {len(tids)} 個" + ("・戴著的稱號在這組" if equipped in tids else ""))
            for key, tids in list(groups.items())[:25]
        ])
        group_select.callback = self.on_title_group

        options = [
            discord.SelectOption(label=title_data.title_label(tid), value=tid, default=(tid == equipped),
                                 description=title_data.TITLES[tid]["desc"][:100])
            for tid in groups[current][:24]
        ]
        options.append(discord.SelectOption(label="不戴稱號", value="__none__", default=(equipped is None),
                                            description="名字下面不顯示稱號"))
        title_select = ui.Select(placeholder="🏷️ 更換稱號…", options=options)
        title_select.callback = self.on_title
        return [group_select, title_select]

    def _namecard_select(self) -> ui.Select:
        """
        🖼️ 更換名片：擁有的名片 (角色 emoji + 名字，最多 24 張) + 「不放名片」
        一張都沒有 ➔ 反灰，placeholder 寫怎麼拿
        """
        owned, equipped = self.namecard_state["owned"], self.namecard_state["equipped"]
        if not owned:
            return ui.Select(placeholder="🖼️ 還沒有角色名片 (收藏冊集齊某位角色每個階級的完美卡就有)", disabled=True,
                             options=[discord.SelectOption(label="不放名片", value="__none__")])
        shown = owned[:NAMECARD_OPTIONS]
        if equipped and equipped not in shown:   # 戴著的那張一定要列出來
            shown = shown[:NAMECARD_OPTIONS - 1] + [equipped]
        pool = load_gacha_pool()
        options = []
        for cid in shown:
            info = pool.get(cid, {})
            has_art = namecard_url(cid) is not None
            card = namecard_data.namecard_info(cid)
            options.append(discord.SelectOption(
                label=f"{info.get('name', cid)}的名片"[:100], value=cid, emoji=info.get("emoji") or "🖼️",
                default=(cid == equipped),
                description=((f"「{card['name']}」{card['desc']}"[:100] if card else None) if has_art
                             else "名片圖還在製作中，戴上暫時不會顯示圖片")))
        options.append(discord.SelectOption(label="不放名片", value="__none__", default=(equipped is None),
                                            description="資料卡最上面不放圖"))
        select = ui.Select(placeholder="🖼️ 更換名片…", options=options)
        select.callback = self.on_namecard
        return select

    async def on_namecard(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        cid = None if value == "__none__" else value
        if not await set_equipped_namecard(interaction.user.id, cid):
            await send_notice(interaction, "❌ 你還沒有這張名片。")
            return
        self.namecard_state = await get_namecard_state(interaction.user.id)
        self.build(await get_or_create_user(interaction.user.id), await get_daily_status(interaction.user.id))
        await interaction.response.edit_message(view=self)

    async def on_download_namecard(self, interaction: discord.Interaction):
        """📥 把戴著的名片原圖 (高畫質 JPG) 私訊給本人 (原圖在私人頻道，見 Utils/namecards.py)"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        state = await get_namecard_state(interaction.user.id)   # 重新讀：可能已經換掉 / 被收回
        cid = state["equipped"]
        if cid is None or cid not in state["owned"]:
            await send_notice(interaction, "❌ 你現在沒有戴名片，先用「🖼️ 更換名片」換上要下載的那張。")
            return
        file = await fetch_original_file(interaction.client, cid, "jpg")
        if file is None:
            await send_notice(interaction, "⚠️ 這張名片的原圖還沒準備好，請稍後再試或通知管理員。")
            return
        name = load_gacha_pool().get(cid, {}).get("name", cid)
        try:
            await interaction.user.send(view=build_namecard_dm_view(name, file), file=file)
        except discord.Forbidden:
            await send_notice(interaction, "❌ 沒辦法私訊你：請在伺服器的隱私設定打開「私人訊息」再試一次。")
            return
        await send_notice(interaction, f"📥 已經把 **{name}** 的名片原圖私訊給你了！")

    async def on_title_group(self, interaction: discord.Interaction):
        """切換稱號分組：只換第二個選單的內容，不動資料"""
        self.title_group = interaction.data["values"][0]
        self.build(*self.data)
        await interaction.response.edit_message(view=self)

    async def on_title(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        tid = None if value == "__none__" else value
        if not await set_equipped_title(interaction.user.id, tid):
            await send_notice(interaction, "❌ 這個稱號還沒有解鎖。")
            return
        self.title_state = await get_title_state(interaction.user.id)
        self.namecard_state = await get_namecard_state(interaction.user.id)   # get_title_state 可能剛補了名片
        self.build(await get_or_create_user(interaction.user.id), await get_daily_status(interaction.user.id))
        await interaction.response.edit_message(view=self)

    async def on_stamina(self, interaction: discord.Interaction):
        user_data = await get_or_create_user(interaction.user.id)
        stamina = calc_stamina(user_data.get("stamina"), user_data.get("stamina_updated_at"))
        owned = await get_owned_stamina_items(interaction.user.id, user_data["inventory"])
        view = StaminaItemView(self, self.target_user, owned, stamina)
        await interaction.response.edit_message(view=view)

    async def on_shrine(self, interaction: discord.Interaction):
        """⛩️ 前往神社：另外開一則只有自己看得到的神社畫面 (同 /shrine manage)，資料卡留在原地"""
        await interaction.response.defer(ephemeral=True)
        shrine_view = importlib.import_module("Cogs.load-general.shrine").ShrineView   # 呼叫時才取，重載後拿到新版
        view = await shrine_view.create(interaction.user, await econ.get_shrine(interaction.user.id))
        await interaction.followup.send(view=view, ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_user.id:
            await send_notice(interaction, "❌ 這不是你的資料卡，只有本人可以簽到！")
            return False
        return True

    async def on_daily(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        result = await perform_daily(user_id)

        user_data = await get_or_create_user(user_id)
        daily_status = await get_daily_status(user_id)

        if result is None:
            # 🔁 重複簽到：卡片同步成「已簽到」，並另外私下提示 (保留原本的重複簽到提醒)
            self.build(user_data, daily_status)
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                view=make_view(build_daily_repeat_container(interaction.user, daily_status["fortune_level"])),
                ephemeral=True,
            )
            return

        self.reward = result
        self.build(user_data, daily_status)
        await interaction.response.edit_message(view=self)

        # 💥 若觸發升級，追投 POWER UP 卡片
        if result["exp_result"].get("leveled_up"):
            await interaction.followup.send(view=make_view(build_power_up_container(interaction.user, result["exp_result"])))

    async def on_timeout(self):
        """逾時後把簽到按鈕反灰"""
        if self.daily_button is not None:
            self.daily_button.disabled = True
            if self.message:
                try:
                    await self.message.edit(view=self)
                except discord.HTTPException:
                    pass


# ---------------------------------------------------------
# 🤖 Profile Cog
# ---------------------------------------------------------
class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # 1. 🌸 /profile 個人資料卡 (含今日簽到狀態、運勢與簽到按鈕)
    @app_commands.command(name="profile", description="查看個人或指定成員的幻想鄉個人資料卡")
    @app_commands.describe(
        user="【可選】選擇要查看的伺服器成員 (留空則查看自己)",
        visibility="【可選】設定您的資料卡公開狀態 (True: 公開 / False: 私人)"
    )
    async def profile_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.User | discord.Member = None,
        visibility: bool = None
    ):
        # 1. 優先處理隱私變更 (始終只修改指令觸發者自身)
        if visibility is not None:
            await update_visibility(interaction.user.id, visibility)
            user = interaction.user

        # 2. 決定查詢目標（未指定時預設為指令觸發者自身）
        target_user = user or interaction.user
        is_self = (target_user.id == interaction.user.id)

        # 3. 從 SQLite 撈取/自動建立玩家資料
        target_data = await get_or_create_user(target_user.id)

        # 4. 隱私權限檢查
        target_is_public = bool(target_data.get("is_public", 1))

        if not is_self and not target_is_public:
            container = build_notice_container(
                "🔒 無法存取個人資料",
                f"**{target_user.display_name}** 已將其資料卡設為私人，無法公開檢視。",
                discord.Color.red(),
            )
            await interaction.response.send_message(view=make_view(container), ephemeral=True)
            return

        # 5. 組出資料卡 (含今日簽到狀態、運勢、稱號)
        daily_status = await get_daily_status(target_user.id)
        title_state = await get_title_state(target_user.id)   # 先算稱號 (會順便補推角名片)，再讀名片
        view = ProfileView(target_user, is_self, title_state, target_data, daily_status,
                           namecard_state=await get_namecard_state(target_user.id))

        is_ephemeral = (visibility is not None) or (is_self and not target_is_public)
        await interaction.response.send_message(view=view, ephemeral=is_ephemeral)
        view.message = await interaction.original_response()

    # 2. ⛩️ /daily 快捷簽到：直接簽到並顯示自己的資料卡 (已簽到過則顯示重複簽到提示)
    @app_commands.command(name="daily", description="每日向博麗神社投賽錢，抽取今日運勢並獲得賽錢與經驗值！")
    async def daily_cmd(self, interaction: discord.Interaction):
        user = interaction.user

        # 已簽到過：只回覆私人的重複簽到提示
        status = await get_daily_status(user.id)
        if status["signed_today"]:
            await interaction.response.send_message(
                view=make_view(build_daily_repeat_container(user, status["fortune_level"])), ephemeral=True
            )
            return

        await interaction.response.defer()
        result = await perform_daily(user.id)
        if result is None:  # 極少數情況：幾乎同時從別處簽到完了
            status = await get_daily_status(user.id)
            await interaction.followup.send(
                view=make_view(build_daily_repeat_container(user, status["fortune_level"])), ephemeral=True
            )
            return

        user_data = await get_or_create_user(user.id)
        status = await get_daily_status(user.id)
        title_state = await get_title_state(user.id)
        view = ProfileView(user, True, title_state, user_data, status, reward=result,
                           namecard_state=await get_namecard_state(user.id))
        view.message = await interaction.followup.send(view=view)

        if result["exp_result"].get("leveled_up"):
            await interaction.followup.send(view=make_view(build_power_up_container(user, result["exp_result"])))


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
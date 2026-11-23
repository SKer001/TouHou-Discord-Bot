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
    add_item, get_title_state, set_equipped_title,
    get_namecard_state, set_equipped_namecard,
)
from Database import title_data, namecard_data
from Utils.gacha_pools import GACHA_POOLS, load_gacha_pool
from Utils.namecards import namecard_url, namecard_original, fetch_original_file
from Database.Item_DB_Manager import get_all_items, get_item, DAILY_REWARD_ITEM
from .Components.general_components import (
    build_profile_container,
    build_daily_repeat_container,
    build_power_up_container,
    build_notice_container,
    build_namecard_dm_view,
)
from Utils.components import send_notice
from Utils.picker import GroupPickerView   # 🗂️ 修改稱號 / 名片控制台 (跟管理員控制台共用)
from Utils.stamina_modal import open_stamina_modal

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


def is_public(user_data: dict) -> bool:
    """資料卡是不是公開的 (users.is_public，預設公開)"""
    return bool(user_data.get("is_public", 1))


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


# ⚡ 恢復體力：0.35.000 起改成彈窗 (Utils/stamina_modal.py)，神社採集畫面也共用同一個


# ---------------------------------------------------------
# 🎛️ 資料卡 View (Components V2)：卡片內含「投賽錢簽到」按鈕
# ---------------------------------------------------------


class ProfileView(ui.LayoutView):
    def __init__(self, target_user, is_self: bool, title_state: dict,
                 user_data: dict, daily_status: dict, reward: dict | None = None,
                 namecard_state: dict | None = None):
        super().__init__(timeout=180)
        self.target_user = target_user
        self.is_self = is_self
        self.title_state = title_state   # get_title_state()：{"equipped", "unlocked"}
        self.namecard_state = namecard_state or {"equipped": None, "owned": []}   # get_namecard_state()
        self.data = None                 # 最近一次 build 的 (user_data, daily_status)
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
            title_stats=self.title_state.get("stats"),
        )
        # 只有本人的卡片才有：一排按鈕 ⚡ 恢復體力 / ⛩️ 前往神社 / 🏷️ 修改稱號 / 🖼️ 修改名片 / (📥 下載名片原圖)
        # 0.35.038 三個常駐選單改成按鈕；0.35.039 按鈕改成另外跳出控制台 (TitlePickerView / NamecardPickerView，預覽 + 確認)
        if self.is_self:
            stamina_btn = ui.Button(label="⚡ 恢復體力", style=discord.ButtonStyle.primary)
            stamina_btn.callback = self.on_stamina
            shrine_btn = ui.Button(label="⛩️ 前往神社", style=discord.ButtonStyle.secondary)
            shrine_btn.callback = self.on_shrine
            title_btn = ui.Button(label="🏷️ 修改稱號", style=discord.ButtonStyle.secondary)
            title_btn.callback = self.on_open_title
            card_btn = ui.Button(label="🖼️ 修改名片", style=discord.ButtonStyle.secondary)
            card_btn.callback = self.on_open_namecard
            row = [stamina_btn, shrine_btn, title_btn, card_btn]
            if namecard_original(self.namecard_state["equipped"]):   # 📥 戴著的名片有原圖 ➔ 可以下載
                download_btn = ui.Button(label="📥 下載名片原圖", style=discord.ButtonStyle.secondary)
                download_btn.callback = self.on_download_namecard
                row.append(download_btn)
            container.add_item(ui.Separator())
            container.add_item(ui.ActionRow(*row))
        self.clear_items()
        self.add_item(container)

    async def on_open_title(self, interaction: discord.Interaction):
        """🏷️ 修改稱號：另外跳出一則只有自己看得到的控制台，確認換上後這張資料卡跟著更新"""
        view = await TitlePickerView.create(interaction.user, self)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def on_open_namecard(self, interaction: discord.Interaction):
        """🖼️ 修改名片：同上"""
        view = await NamecardPickerView.create(interaction.user, self)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def on_download_namecard(self, interaction: discord.Interaction):
        """📥 把戴著的名片原圖 (高畫質 JPG) 私訊給本人 (原圖在私人頻道，見 Utils/namecards.py)"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        state = await get_namecard_state(interaction.user.id)   # 重新讀：可能已經換掉 / 被收回
        cid = state["equipped"]
        if cid is None or cid not in state["owned"]:
            await send_notice(interaction, "❌ 你現在沒有戴名片，先用「🖼️ 修改名片」換上要下載的那張。")
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

    async def on_stamina(self, interaction: discord.Interaction):
        """⚡ 恢復體力：打開彈窗 (Utils/stamina_modal.py)；吃完後資料卡更新體力，結果私下提示"""
        async def done(inter: discord.Interaction, notice: str):
            self.build(await get_or_create_user(inter.user.id), await get_daily_status(inter.user.id))
            await inter.response.edit_message(view=self)
            await send_notice(inter, notice)
        await open_stamina_modal(interaction, done)

    async def on_shrine(self, interaction: discord.Interaction):
        """⛩️ 前往神社：另外開一則只有自己看得到的神社畫面 (同 /shrine manage)，資料卡留在原地"""
        await interaction.response.defer(ephemeral=True)
        shrine_view = importlib.import_module("Cogs.load-general.shrine").ShrineView   # 呼叫時才取，重載後拿到新版
        view = await shrine_view.create(interaction.user, await econ.get_shrine(interaction.user.id))
        view.message = await interaction.followup.send(view=view, ephemeral=True)   # 逾時時把按鈕反灰用

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

        # 💥 若觸發升級，追投 POWER UP 卡片 (私人資料卡只有自己看得到，0.36.002)
        if result["exp_result"].get("leveled_up"):
            await interaction.followup.send(view=make_view(build_power_up_container(interaction.user, result["exp_result"])),
                                            ephemeral=not is_public(user_data))

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
# 🏷️ / 🖼️ 修改稱號、修改名片控制台 (0.35.039，使用者 grill 定案)
#   資料卡的按鈕另外跳出一則只有自己看得到的控制台 (跟管理員控制台一樣：分組 ➔ 選項 (翻頁) ➔ 按鈕)
#   全部列出，還沒拿到的標 🔒 並說明怎麼拿；選好先在上面預覽，按「✅ 確認」才換上，原本的資料卡跟著更新
# ---------------------------------------------------------
async def sync_profile_card(profile_view, user_id: int) -> str:
    """確認換上之後更新原本那張資料卡；過期 / 改不了就回傳說明 (不假裝成功)"""
    if profile_view is None or profile_view.is_finished() or profile_view.message is None:
        return "\n-# 原本的資料卡已經過期，重新打開 `/profile` 就會看到"
    try:
        profile_view.title_state = await get_title_state(user_id)
        profile_view.namecard_state = await get_namecard_state(user_id)
        profile_view.build(await get_or_create_user(user_id), await get_daily_status(user_id))
        await profile_view.message.edit(view=profile_view)
    except discord.HTTPException:
        return "\n-# 原本的資料卡沒辦法更新，重新打開 `/profile` 就會看到"
    return "\n-# 原本的資料卡也換好了"


class TitlePickerView(GroupPickerView):
    """🗂️ 稱號分組 ➔ 🏷️ 稱號 (全部列出，🔒 = 還沒解鎖) ➔ 預覽 ➔ ✅ 確認換上 / ↩️ 取消 / ✖️ 卸下稱號"""
    GROUP_PLACEHOLDER = "🗂️ 稱號分組"
    ITEM_PLACEHOLDER = "🏷️ 選稱號"

    def __init__(self, user, profile_view=None):
        order = sorted(title_data.TITLES, key=lambda t: -title_data.RARITY_ORDER[title_data.TITLES[t]["rarity"]])
        super().__init__(user.id, user, title_data.group_titles(order), timeout=600)
        self.profile_view = profile_view
        self.state = {"equipped": None, "unlocked": [], "stats": {}}
        self.pending = None   # ("equip", 稱號 id) / ("unequip", None)：預覽中、還沒確認

    @classmethod
    async def create(cls, user, profile_view=None):
        view = cls(user, profile_view)
        await view.load()
        st = view.state   # 打開戴著的稱號在的那組、那一頁；沒戴就打開等級最高的已解鎖稱號那組
        view.open_at(st["equipped"] or (st["unlocked"][0] if st["unlocked"] else None))
        view.build()
        return view

    async def load(self):
        self.state = await get_title_state(self.user.id)

    def group_name(self, key):
        return title_data.TITLE_GROUPS.get(key, {}).get("name", "📌 其他")

    def group_status(self, key):
        return f"已解鎖 {sum(t in self.state['unlocked'] for t in self.groups[key])} / {len(self.groups[key])} 個"

    def item_label(self, tid):
        return title_data.title_label(tid)

    def item_status(self, tid):
        if tid == self.state["equipped"]:
            return "🏷️ 戴著"
        if tid in self.state["unlocked"]:
            return "✅ 已解鎖"
        return f"🔒 {title_data.condition_text(tid)}"

    def accent(self):
        return discord.Color(title_data.title_color(self.state["equipped"]))

    def header(self):
        equipped = self.state["equipped"]
        return (f"## 🏷️ 修改稱號\n戴著：`{title_data.title_label(equipped) if equipped else '沒戴'}`　"
                f"已解鎖 `{len(self.state['unlocked'])}` / `{len(title_data.TITLES)}` 個\n"
                "-# 選分組 ➔ 選稱號 ➔ 看上面的預覽 ➔ 按「✅ 確認換上」")

    def detail(self, tid):
        text = f"**{title_data.title_label(tid)}**\n-# {title_data.title_desc(tid, self.state.get('stats'))}"
        if tid not in self.state["unlocked"]:
            return text + f"\n🔒 **還沒解鎖**：{title_data.condition_text(tid)}"
        if tid == self.state["equipped"]:
            return text + "\n🏷️ 你現在就戴著這個稱號"
        return text

    def select_item(self, item):
        self.selected = item
        ok = item and item in self.state["unlocked"] and item != self.state["equipped"]
        self.pending = ("equip", item) if ok else None

    def preview_container(self):
        if not self.pending:
            return None
        kind, tid = self.pending
        title_text = (f"**{title_data.title_label(tid)}**\n-# *{title_data.title_desc(tid, self.state.get('stats'))}*\n"
                      if kind == "equip" else "-# *(不戴稱號)*\n")
        c = ui.Container(accent_color=discord.Color(title_data.title_color(tid if kind == "equip" else None)))
        c.add_item(ui.Section(
            ui.TextDisplay(f"-# 👀 預覽：資料卡上會變成這樣\n## 🌸 {self.user.display_name} 的幻想鄉通行證\n{title_text}"),
            accessory=ui.Thumbnail(self.user.display_avatar.with_size(128).url)))
        return c

    def actions(self):
        unequip = self.pending and self.pending[0] == "unequip"
        return [
            ("✅ 確認卸下" if unequip else "✅ 確認換上", discord.ButtonStyle.success, self.on_confirm, self.pending is None),
            ("↩️ 取消", discord.ButtonStyle.secondary, self.on_cancel, self.pending is None and self.selected is None),
            ("✖️ 卸下稱號", discord.ButtonStyle.danger, self.on_unequip, self.state["equipped"] is None or bool(unequip)),
        ]

    async def on_confirm(self, interaction: discord.Interaction):
        if not self.pending:
            await self.done(interaction)
            return
        kind, tid = self.pending
        self.pending = None
        if not await set_equipped_title(self.user.id, tid if kind == "equip" else None):   # 預覽到確認之間狀態變了
            await self.done(interaction, "❌ 這個稱號還沒有解鎖，沒辦法戴上。")
            return
        notice = f"✅ 已換上 **{title_data.title_label(tid)}**" if kind == "equip" else "✅ 已卸下稱號"
        await self.done(interaction, notice + await sync_profile_card(self.profile_view, self.user.id))

    async def on_cancel(self, interaction: discord.Interaction):
        self.select_item(None)
        await self.done(interaction)

    async def on_unequip(self, interaction: discord.Interaction):
        self.selected, self.pending = None, ("unequip", None)
        await self.done(interaction)


class NamecardPickerView(GroupPickerView):
    """🎰 卡池 ➔ 🖼️ 角色的名片 (全部列出，🔒 = 還沒拿到) ➔ 預覽 ➔ ✅ 確認換上 / ↩️ 取消 / ✖️ 不放名片"""
    GROUP_PLACEHOLDER = "🎰 卡池"
    ITEM_PLACEHOLDER = "🖼️ 選名片"

    def __init__(self, user, profile_view=None, owned: list[str] | None = None):
        self.pool = load_gacha_pool()
        groups = {key: [] for key in GACHA_POOLS}
        for cid, info in self.pool.items():
            groups.setdefault(info.get("pool") or "other", []).append(cid)
        groups["other"] = groups.get("other", []) + [c for c in owned or [] if c not in self.pool]   # 角色已經不在卡池的名片也要換得到
        super().__init__(user.id, user, groups, timeout=600)
        self.profile_view = profile_view
        self.state = {"equipped": None, "owned": list(owned or [])}
        self.pending = None   # ("equip", 角色 id) / ("unequip", None)

    @classmethod
    async def create(cls, user, profile_view=None):
        state = await get_namecard_state(user.id)
        view = cls(user, profile_view, state["owned"])
        view.state = state
        view.open_at(state["equipped"] or (state["owned"][0] if state["owned"] else None))   # 沒戴就打開第一張擁有的那組
        view.build()
        return view

    async def load(self):
        self.state = await get_namecard_state(self.user.id)

    def name(self, cid):
        info = self.pool.get(cid, {})
        return f"{info.get('emoji', '🖼️')} {info.get('name', cid)}"

    def group_name(self, key):
        return GACHA_POOLS.get(key, {}).get("name", "📌 其他")

    def group_status(self, key):
        return f"擁有 {sum(c in self.state['owned'] for c in self.groups[key])} / {len(self.groups[key])} 張"

    def item_label(self, cid):
        return f"{self.name(cid)} 的名片"

    def item_status(self, cid):
        if cid == self.state["equipped"]:
            tag = "🖼️ 戴著"
        elif cid in self.state["owned"]:
            tag = "✅ 擁有"
        else:
            tag = "🔒 還沒拿到"
        if namecard_url(cid) is None:
            tag += "・名片圖製作中"
        else:
            card = namecard_data.namecard_info(cid)
            if card:
                tag += f"・「{card['name']}」"
        return tag

    def accent(self):
        return discord.Color.from_rgb(88, 101, 242)

    def header(self):
        equipped = self.state["equipped"]
        owned = [c for c in self.state["owned"]]
        return (f"## 🖼️ 修改名片\n戴著：`{self.name(equipped) if equipped else '沒放'}`　"
                f"擁有 `{len(owned)}` / `{sum(len(v) for v in self.groups.values())}` 張\n"
                "-# 選卡池 ➔ 選名片 ➔ 看上面的預覽 ➔ 按「✅ 確認換上」")

    def detail(self, cid):
        card = namecard_data.namecard_info(cid)
        lines = [f"**{self.name(cid)} 的名片**" + (f"　「{card['name']}」" if card else "")]
        if card:
            lines.append(f"-# {card['desc']}")
        if cid not in self.state["owned"]:
            lines.append(f"🔒 **還沒拿到**：把 {self.name(cid)} 每個階級的完美卡 (完整度 1.0000) 都放進 🔒 收藏冊 (`/card album`)，就會拿到這張名片")
        elif cid == self.state["equipped"]:
            lines.append("🖼️ 你現在就戴著這張名片")
        return "\n".join(lines)

    def select_item(self, item):
        self.selected = item
        ok = item and item in self.state["owned"] and item != self.state["equipped"]
        self.pending = ("equip", item) if ok else None

    def preview_container(self):
        if not self.pending:
            return None
        kind, cid = self.pending
        c = ui.Container(accent_color=self.accent())
        c.add_item(ui.TextDisplay("-# 👀 預覽：資料卡上的名片會變成這樣"))
        if kind == "unequip":
            c.add_item(ui.TextDisplay("*(資料卡上不放名片圖)*"))
            return c
        url = namecard_url(cid)
        if url:
            c.add_item(ui.MediaGallery(discord.MediaGalleryItem(url)))
            caption = namecard_data.namecard_caption(cid)
            if caption:
                c.add_item(ui.TextDisplay(caption))
        else:
            c.add_item(ui.TextDisplay(f"**{self.name(cid)} 的名片**\n-# 這張名片的圖還在製作中，戴上之後資料卡暫時不會顯示圖片"))
        return c

    def actions(self):
        unequip = self.pending and self.pending[0] == "unequip"
        return [
            ("✅ 確認卸下" if unequip else "✅ 確認換上", discord.ButtonStyle.success, self.on_confirm, self.pending is None),
            ("↩️ 取消", discord.ButtonStyle.secondary, self.on_cancel, self.pending is None and self.selected is None),
            ("✖️ 不放名片", discord.ButtonStyle.danger, self.on_unequip, self.state["equipped"] is None or bool(unequip)),
        ]

    async def on_confirm(self, interaction: discord.Interaction):
        if not self.pending:
            await self.done(interaction)
            return
        kind, cid = self.pending
        self.pending = None
        if not await set_equipped_namecard(self.user.id, cid if kind == "equip" else None):
            await self.done(interaction, "❌ 你還沒有這張名片，沒辦法換上。")
            return
        notice = f"✅ 已換上 {self.name(cid)} 的名片" if kind == "equip" else "✅ 資料卡已經不放名片了"
        await self.done(interaction, notice + await sync_profile_card(self.profile_view, self.user.id))

    async def on_cancel(self, interaction: discord.Interaction):
        self.select_item(None)
        await self.done(interaction)

    async def on_unequip(self, interaction: discord.Interaction):
        self.selected, self.pending = None, ("unequip", None)
        await self.done(interaction)


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
        target_is_public = is_public(target_data)

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

        # 🔒 私人資料卡：簽到結果和 POWER UP 都只有自己看得到 (0.36.002，使用者定；原本一律公開)
        private = not is_public(await get_or_create_user(user.id))
        await interaction.response.defer(ephemeral=private)
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
        view.message = await interaction.followup.send(view=view, ephemeral=private)

        if result["exp_result"].get("leveled_up"):
            await interaction.followup.send(view=make_view(build_power_up_container(user, result["exp_result"])),
                                            ephemeral=private)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
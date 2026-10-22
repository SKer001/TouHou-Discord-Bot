import random
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands, ui
from discord.ext import commands

from Database.User_DB_Manager import (
    get_or_create_user, update_visibility, add_money, add_exp,
    get_daily_status as db_get_daily_status, claim_daily,
)
from .Components.general_components import (
    get_avatar_dominant_color,
    build_profile_container,
    build_daily_repeat_container,
    build_power_up_container,
    build_notice_container,
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

    min_m, max_m = MONEY_RANGES.get(fortune_level, (300, 500))
    money_gained = random.randint(min_m, max_m)
    exp_gained = random.randint(100, 200)

    # 呼叫主資料庫統一寫入，確保全域資料同步
    new_money = await add_money(user_id, money_gained)
    exp_result = await add_exp(user_id, exp_gained)

    return {
        "fortune_level": fortune_level,
        "money_gained": money_gained,
        "exp_gained": exp_gained,
        "new_money": new_money,
        "exp_result": exp_result,
    }


# ---------------------------------------------------------
# 🎛️ 資料卡 View (Components V2)：卡片內含「投賽錢簽到」按鈕
# ---------------------------------------------------------
class ProfileView(ui.LayoutView):
    def __init__(self, target_user, is_self: bool, dominant_color: discord.Color,
                 user_data: dict, daily_status: dict, reward: dict | None = None):
        super().__init__(timeout=180)
        self.target_user = target_user
        self.is_self = is_self
        self.dominant_color = dominant_color
        self.reward = reward          # 剛簽到完的獎勵 (只顯示在這張卡片上)
        self.message = None           # 送出後由指令填入，供逾時時停用按鈕
        self.daily_button = None
        self.build(user_data, daily_status)

    def build(self, user_data: dict, daily_status: dict):
        """依最新資料重新組出整張卡片；只有本人的卡片才有簽到按鈕"""
        button = None
        if self.is_self:
            if daily_status["signed_today"]:
                button = ui.Button(label="✅ 今日已簽到", style=discord.ButtonStyle.secondary, disabled=True)
            else:
                button = ui.Button(label="⛩️ 投賽錢簽到", style=discord.ButtonStyle.success)
                button.callback = self.on_daily
        self.daily_button = button

        container = build_profile_container(
            self.target_user, user_data, daily_status, self.dominant_color,
            is_self=self.is_self, reward=self.reward, daily_button=button,
        )
        self.clear_items()
        self.add_item(container)

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

        # 5. 組出資料卡 (含今日簽到狀態與運勢)
        dominant_color = await get_avatar_dominant_color(target_user)
        daily_status = await get_daily_status(target_user.id)
        view = ProfileView(target_user, is_self, dominant_color, target_data, daily_status)

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
        dominant_color = await get_avatar_dominant_color(user)

        view = ProfileView(user, True, dominant_color, user_data, status, reward=result)
        view.message = await interaction.followup.send(view=view)

        if result["exp_result"].get("leveled_up"):
            await interaction.followup.send(view=make_view(build_power_up_container(user, result["exp_result"])))


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
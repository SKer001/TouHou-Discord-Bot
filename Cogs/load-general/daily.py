import os
import random
from datetime import datetime, timezone, timedelta
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from Utils.embed_builder import (
    build_daily_embed,
    build_daily_repeat_embed,
    build_fortune_embed,
    build_power_up_embed
)

# 常數設定
ADMIN_ID = 403895664666214400
TAIWAN_TZ = timezone(timedelta(hours=8))
DB_PATH = os.path.join(os.path.dirname(__file__), "daily.db")


# ---------------------------------------------------------
# 💾 獨立資料庫邏輯
# ---------------------------------------------------------
async def init_daily_db():
    """初始化同級目錄下的 daily.db"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users_daily (
                user_id INTEGER PRIMARY KEY,
                money INTEGER DEFAULT 1000,
                level INTEGER DEFAULT 0,
                exp INTEGER DEFAULT 0,
                last_daily TEXT DEFAULT NULL,
                fortune_level INTEGER DEFAULT 3
            )
        """)
        await db.commit()


async def get_or_create_daily_user(user_id: int) -> dict:
    """取得或建立玩家 daily 資料"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users_daily WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

        await db.execute(
            "INSERT INTO users_daily (user_id, money, level, exp) VALUES (?, 1000, 0, 0)",
            (user_id,)
        )
        await db.commit()
        return {"user_id": user_id, "money": 1000, "level": 0, "exp": 0, "last_daily": None, "fortune_level": 3}


async def add_exp_internal(user_id: int, exp_amount: int) -> dict:
    """計算經驗值與 0.0 P ~ 100.0 P 升級"""
    user_data = await get_or_create_daily_user(user_id)
    current_level = user_data.get("level", 0)
    current_exp = user_data.get("exp", 0)

    if current_level >= 1000:
        return {"leveled_up": False, "old_p": 100.0, "new_p": 100.0, "is_max": True}

    old_p = current_level / 10.0
    current_exp += exp_amount
    leveled_up = False

    while current_level < 1000:
        req_exp = 50 + (current_level * 15)
        if current_exp >= req_exp:
            current_exp -= req_exp
            current_level += 1
            leveled_up = True
        else:
            break

    if current_level >= 1000:
        current_level = 1000
        current_exp = 0

    new_p = current_level / 10.0

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users_daily SET level = ?, exp = ? WHERE user_id = ?",
            (current_level, current_exp, user_id)
        )
        await db.commit()

    return {"leveled_up": leveled_up, "old_p": old_p, "new_p": new_p, "is_max": (current_level >= 1000)}


# ---------------------------------------------------------
# 🤖 Daily Cog
# ---------------------------------------------------------
class Daily(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await init_daily_db()

    # 1. ⛩️ /daily 每日簽到
    @app_commands.command(name="daily", description="每日向博麗神社投賽錢，抽取今日運勢並獲得賽錢與經驗值！")
    async def daily_cmd(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        today_str = datetime.now(TAIWAN_TZ).strftime("%Y-%m-%d")
        user_data = await get_or_create_daily_user(user_id)

        # 判斷是否今天已簽到
        if user_data.get("last_daily") == today_str:
            embed = build_daily_repeat_embed(interaction.user, user_data.get("fortune_level", 3))
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 隨機抽取運勢等級 0~5
        fortune_level = random.randint(0, 5)

        # 根據運勢等級給予賽錢數額
        money_ranges = {
            5: (1500, 2000),
            4: (800, 1200),
            3: (500, 790),
            2: (300, 490),
            1: (150, 290),
            0: (50, 140)
        }
        min_m, max_m = money_ranges.get(fortune_level, (300, 500))
        money_gained = random.randint(min_m, max_m)
        exp_gained = random.randint(100, 200)

        # 計算新賽錢與寫入資料庫
        new_money = user_data.get("money", 1000) + money_gained

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                UPDATE users_daily 
                SET money = ?, last_daily = ?, fortune_level = ? 
                WHERE user_id = ?
            """, (new_money, today_str, fortune_level, user_id))
            await db.commit()

        # 經驗值與升級計算
        exp_result = await add_exp_internal(user_id, exp_gained)

        # 發送簽到卡片
        daily_embed = build_daily_embed(interaction.user, money_gained, exp_gained, fortune_level, new_money)
        await interaction.response.send_message(embed=daily_embed)

        # 💥 若升級，追投 POWER UP 卡片
        if exp_result.get("leveled_up"):
            power_up_embed = build_power_up_embed(interaction.user, exp_result)
            await interaction.followup.send(embed=power_up_embed)

    # 2. 🔮 /fortune 查看今日運勢
    @app_commands.command(name="fortune", description="查看今天的運勢與籤詩")
    async def fortune_cmd(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        today_str = datetime.now(TAIWAN_TZ).strftime("%Y-%m-%d")
        user_data = await get_or_create_daily_user(user_id)

        has_daily = (user_data.get("last_daily") == today_str)
        fortune_level = user_data.get("fortune_level", 3)

        embed = build_fortune_embed(interaction.user, fortune_level, has_daily)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Daily(bot))
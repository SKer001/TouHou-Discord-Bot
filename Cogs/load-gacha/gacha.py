import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random
import uuid
from datetime import datetime

# 🟢 引入你 db_manager.py 中的 get_or_create_user 與 add_money
from Database.db_manager import get_or_create_user, add_money
from Utils.embed_builder import build_gacha_single_embed, build_gacha_ten_embed

BASE_DIR = "Cogs/load-gacha"
USERS_DIR = f"{BASE_DIR}/users"
CHAR_FILE = f"{BASE_DIR}/character.json"

os.makedirs(USERS_DIR, exist_ok=True)
with open(CHAR_FILE, "r", encoding="utf-8") as f:
    ALL_CHARACTERS = json.load(f)

class GachaCardSys(commands.GroupCog, group_name="card", group_description="東方角色卡牌收集與合成系統"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_user_data(self, user_id: int) -> dict:
        path = f"{USERS_DIR}/{user_id}.json"
        if not os.path.exists(path):
            return {"user_id": user_id, "stats": {"total_draws": 0, "total_fusions": 0}, "cards": []}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_user_data(self, user_id: int, data: dict):
        path = f"{USERS_DIR}/{user_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def generate_completeness(self) -> float:
        """產生高斯平方分佈的 Float 完整度"""
        val = (random.gauss(0, 0.35)) ** 2
        return round(max(0.001, min(1.000, val)), 4)

    @app_commands.command(name="draw", description="⛩️ 博麗神社祈願：消耗賽錢抽取角色卡牌")
    @app_commands.choices(pull_type=[
        app_commands.Choice(name="單次祈願 (2,000 賽錢)", value=1),
        app_commands.Choice(name="十連祈願 (20,000 賽錢)", value=10)
    ])
    async def draw_card(self, interaction: discord.Interaction, pull_type: app_commands.Choice[int]):
        user_id = interaction.user.id
        draw_count = pull_type.value
        total_cost = draw_count * 2000

        # ==========================================
        # 🪙 1. 賽錢判定與扣款邏輯 
        # ==========================================
        # 取得主資料庫中的玩家資料
        user_db = await get_or_create_user(user_id)
        current_money = user_db.get("money", 0)

        # 檢查餘額是否足夠
        if current_money < total_cost:
            await interaction.response.send_message(
                f"❌ **賽錢不足！**\n祈願需要 `{total_cost}` 賽錢，但你的口袋裡只有 `{current_money}` 賽錢...\n*靈夢看了看空蕩蕩的賽錢箱，無奈地把你請出了神社。*", 
                ephemeral=True
            )
            return

        # 使用 add_money 傳入負值進行扣款
        await add_money(user_id, -total_cost)

        # ==========================================
        # 🎴 2. 進行抽卡與卡庫寫入邏輯
        # ==========================================
        user_data = self.get_user_data(user_id)
        results = []
        char_keys = list(ALL_CHARACTERS.keys())

        for _ in range(draw_count):
            char_key = random.choice(char_keys)
            char_data = ALL_CHARACTERS[char_key]
            
            # 決定稀有度與稱號 (權重: N=75%, R=22%, SR=3%)
            rarity = random.choices(char_data["rarities"], weights=[75, 22, 3], k=1)[0]
            title = char_data["titles"][rarity]
            
            # 建立實體卡牌
            new_card = {
                "instance_id": f"c_{char_data['uuid'][:4]}_{uuid.uuid4().hex[:8]}",
                "character_key": char_key,
                "name": char_data["name"],
                "emoji": char_data["emoji"],
                "rarity": rarity,
                "title": title,
                "completeness": self.generate_completeness(),
                "obtained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            results.append(new_card)
            user_data["cards"].append(new_card)

        # 儲存個人卡庫並更新統計
        user_data["stats"]["total_draws"] += draw_count
        self.save_user_data(user_id, user_data)

        # ==========================================
        # 🎨 3. 繪製並發送 Embed
        # ==========================================
        if draw_count == 1:
            embed = build_gacha_single_embed(results[0], interaction.user.display_name, total_cost)
        else:
            embed = build_gacha_ten_embed(results, interaction.user.display_name, total_cost)

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCardSys(bot))
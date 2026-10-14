import io
import discord
from PIL import Image


# ---------------------------------------------------------
# 🎨 輔助函式：從 Discord 頭像 URL 提取主色調 (Dominant Color)
# ---------------------------------------------------------
async def get_avatar_dominant_color(user: discord.User | discord.Member) -> discord.Color:
    """下載使用者頭像並擷取出現頻率最高的代表色彩，回傳 discord.Color 物件"""
    try:
        avatar_bytes = await user.display_avatar.with_size(64).read()
        image = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
        quantized = image.quantize(colors=1, method=2)
        palette = quantized.getpalette()[:3]
        return discord.Color.from_rgb(palette[0], palette[1], palette[2])
    except Exception:
        return discord.Color.red()


# ---------------------------------------------------------
# 🌸 1. 個人資料卡 Embed (Profile Card)
# ---------------------------------------------------------
# Utils/embed_builder.py

# Utils/embed_builder.py

def get_required_exp_for_level(level: int) -> int:
    """計算當前階級 (level) 升到下一階級 (level + 1) 所需的經驗值"""
    return 50 + (level * 15)


def build_profile_embed(
    user: discord.User | discord.Member,
    user_data: dict,
    dominant_color: discord.Color
) -> discord.Embed:
    """根據玩家資料與頭像主色繪製 Embed 個人資料卡"""
    money = user_data.get("money", 1000)
    current_level = user_data.get("level", 0)  # level 0~1000 (對應 0.0 P ~ 100.0 P)
    exp = user_data.get("exp", 0)
    inventory = user_data.get("inventory", {})
    is_public = bool(user_data.get("is_public", 1))

    p_power = current_level / 10.0
    total_items = sum(inventory.values()) if isinstance(inventory, dict) else 0
    embed_color = dominant_color if is_public else discord.Color.dark_gray()

    # ---------------------------------------------------------
    # 📊 1. 動態經驗值進度條計算
    # ---------------------------------------------------------
    if current_level >= 1000:
        bar = "🟥" * 10
        exp_text = f"`{exp:,}` / `MAX` EXP (🌟 **FULL POWER**)"
        exp_bar = f"`[{bar}]`"
    else:
        req_exp = get_required_exp_for_level(current_level)
        needed_exp = req_exp - exp
        
        # 計算 10 段進度條比例 (0 ~ 10)
        percentage = min(max(exp / req_exp, 0.0), 1.0)
        filled_length = int(round(percentage * 10))
        empty_length = 10 - filled_length
        
        # 組合進度條字串 (綠色填滿 🟥 + 灰色未填滿 ⬜)
        bar = "🟥" * filled_length + "⬜" * empty_length
        exp_text = f"`{exp:,}` / `{req_exp:,}` EXP *(還差 `{needed_exp:,}` EXP)*"
        exp_bar = f"`[{bar}]`"

    # ---------------------------------------------------------
    # 🎨 2. 建立與組裝 Embed 卡片
    # ---------------------------------------------------------
    embed = discord.Embed(
        title=f"🌸 {user.display_name} 的幻想鄉通行證",
        color=embed_color,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)

    # 第一排：基礎資訊 (inline=True) -> 賽錢、P點、背包物品
    embed.add_field(name="💰 賽錢 (Money)", value=f"`{money:,}` 兩", inline=True)
    embed.add_field(name="🔴 P點 (Power)", value=f"`{p_power:.1f}` P", inline=True)
    embed.add_field(name="🎒 背包物品數", value=f"`{total_items}` 件道具", inline=True)

    # 第二排：經驗值與進度條 (inline=False) -> 獨佔整行寬度，絕對不折行！
    embed.add_field(
        name="✨ 經驗值 (EXP)",
        value=f"{exp_text}\n{exp_bar}",
        inline=False
    )

    # 第三排：卡片隱私狀態 (inline=False)
    embed.add_field(
        name="🔒 卡片狀態",
        value="`🌐 公開`" if is_public else "`🔒 私人`",
        inline=False
    )

    embed.set_footer(text="TouHouBot Profile System • 幻想鄉居民登記")
    return embed

# ---------------------------------------------------------
# 💥 2. POWER UP 升級特效 Embed
# ---------------------------------------------------------
def build_power_up_embed(user: discord.User | discord.Member, result: dict) -> discord.Embed:
    """繪製 POWER UP! 特效 Embed 訊息"""
    old_p = result["old_p"]
    new_p = result["new_p"]

    embed = discord.Embed(
        title="💥 POWER UP! 火力提升！",
        description=f"🎉 恭喜 **{user.mention}** 彈幕火力獲得突破！",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="🔴 彈幕火力 (Power)",
        value=f"`{old_p:.1f} P` ➔ **`{new_p:.1f} P`**",
        inline=False
    )

    if result.get("is_max"):
        embed.set_footer(text="🌟 警告：火力已達最大上限 (FULL POWER!)")
    else:
        embed.set_footer(text="TouHouBot Power System • 繼續集滿 P 點以提升火力！")

    embed.set_thumbnail(url=user.display_avatar.url)
    return embed


# Utils/embed_builder.py (請加入以下內容)

FORTUNE_MAP = {
    5: {"name": "🌟 大吉 (大顯神威)", "desc": "博麗大神顯靈！靈力極致充沛，萬事亨通！"},
    4: {"name": "🎉 吉 (靈力充沛)", "desc": "守矢神社加護，符卡發動順暢無阻！"},
    3: {"name": "🍡 中吉 (人里平穩)", "desc": "命蓮寺鐘聲祈福，平安無事、順風順水的一天。"},
    2: {"name": "🍵 小吉 (茶柱立起)", "desc": "紅魔館的小憩時刻，平淡中帶有些許小幸運。"},
    1: {"name": "🍃 末吉 (微風拂過)", "desc": "迷途竹林偶爾迷路，但終能找到出口。"},
    0: {"name": "🍵 凶 (厄神降臨)", "desc": "雛大人幫你承受了厄運，今天適合低調行事。"}
}

def build_daily_embed(
    user: discord.User | discord.Member,
    money_gained: int,
    exp_gained: int,
    fortune_level: int,
    current_money: int
) -> discord.Embed:
    """繪製 /daily 簽到成功 Embed"""
    fortune_info = FORTUNE_MAP.get(fortune_level, FORTUNE_MAP[3])
    
    embed = discord.Embed(
        title="⛩️ 博麗神社賽錢箱 • 簽到成功！",
        description=f"**{user.mention}** 向賽錢箱投下了賽錢，並求得了一支運勢籤！",
        color=discord.Color.gold() if fortune_level >= 4 else discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(name="🔮 今日運勢", value=f"**{fortune_info['name']}**\n*{fortune_info['desc']}*", inline=False)
    embed.add_field(name="💰 獲得賽錢", value=f"`+{money_gained:,}` 兩", inline=True)
    embed.add_field(name="✨ 獲得經驗", value=f"`+{exp_gained:,}` EXP", inline=True)
    embed.add_field(name="🏦 目前賽錢總額", value=f"`{current_money:,}` 兩", inline=False)
    
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="TouHouBot Daily System • 明天 00:00 後可再次投賽錢")
    return embed


def build_daily_repeat_embed(
    user: discord.User | discord.Member,
    fortune_level: int
) -> discord.Embed:
    """繪製重複簽到 (提醒與今日運勢) Embed"""
    fortune_info = FORTUNE_MAP.get(fortune_level, FORTUNE_MAP[3])
    
    embed = discord.Embed(
        title="⌛ 今天已經投過賽錢囉！",
        description=f"**{user.display_name}**，你今天已經向博麗神社投過賽錢了。\n請等待明日 **00:00** 刷新後再來吧！",
        color=discord.Color.dark_orange()
    )
    embed.add_field(
        name="🔮 你今天的運勢是",
        value=f"**{fortune_info['name']}**\n*{fortune_info['desc']}*",
        inline=False
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="TouHouBot Daily System • 每日簽到限制 1 次")
    return embed


def build_fortune_embed(
    user: discord.User | discord.Member,
    fortune_level: int,
    has_daily: bool
) -> discord.Embed:
    """繪製 /fortune 運勢查詢 Embed"""
    if not has_daily:
        embed = discord.Embed(
            title="🔮 今日運勢未解鎖",
            description=f"**{user.display_name}**，你今天還沒向博麗神社投賽錢喔！\n請先輸入 `/daily` 簽到並抽取的你今日運勢吧！",
            color=discord.Color.blue()
        )
        embed.set_footer(text="TouHouBot Fortune System • 輸入 /daily 解鎖運勢")
        return embed

    fortune_info = FORTUNE_MAP.get(fortune_level, FORTUNE_MAP[3])
    embed = discord.Embed(
        title=f"🔮 {user.display_name} 的今日運勢",
        description=f"**運勢階級**：{fortune_info['name']}\n\n📝 **籤詩解讀**：\n{fortune_info['desc']}",
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="TouHouBot Fortune System • 每日 00:00 重置運勢")
    return embed
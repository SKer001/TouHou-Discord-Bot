import discord
import os

def get_completeness_eval(completeness: float) -> tuple[str, discord.Color]:
    """根據完整度回傳東方風格評價名稱與顏色"""
    comp_str = f"{completeness:.4f}"
    
    if completeness >= 0.990:
        return f"💠 **{comp_str}** [神代之遺]", discord.Color.teal()
    elif completeness >= 0.900:
        return f"🌟 **{comp_str}** [蓬萊仙姿]", discord.Color.gold()
    elif completeness >= 0.700:
        return f"🌸 **{comp_str}** [西行櫻華]", discord.Color.purple()
    elif completeness >= 0.400:
        return f"🍃 **{comp_str}** [妖怪山珍]", discord.Color.green()
    elif completeness >= 0.150:
        return f"🍂 **{comp_str}** [人間凡品]", discord.Color.light_grey()
    elif completeness >= 0.050:
        return f"🪵 **{comp_str}** [迷途遺物]", discord.Color.dark_grey()
    else:
        return f"🏚️ **{comp_str}** [彈幕戰痕]", discord.Color.dark_red()


def _apply_thumbnail(embed: discord.Embed, char_key: str, thumbnails_dir: str, files_list: list, used_keys: set):
    """
    🖼️ 圖片載入機制：
    1. 優先尋找 `{char_key}.png` 角色專屬圖片。
    2. 若找不到，自動降級使用預設的 `fill.png` 預設圖。
    """
    if not thumbnails_dir:
        return

    char_img_path = os.path.join(thumbnails_dir, f"{char_key}.png") if char_key else None
    fill_img_path = os.path.join(thumbnails_dir, "fill.png")

    try:
        # 🟢 1. 角色專屬圖片存在
        if char_img_path and os.path.exists(char_img_path):
            filename = f"{char_key}.png"
            embed.set_thumbnail(url=f"attachment://{filename}")
            if char_key not in used_keys:
                files_list.append(discord.File(char_img_path, filename=filename))
                used_keys.add(char_key)
        
        # 🟡 2. 角色圖片不存在 ➔ 自動退回使用 fill.png
        elif os.path.exists(fill_img_path):
            filename = "fill.png"
            embed.set_thumbnail(url=f"attachment://{filename}")
            if "fill" not in used_keys:
                files_list.append(discord.File(fill_img_path, filename="fill.png"))
                used_keys.add("fill")
                
    except Exception as e:
        print(f"⚠️ [Thumbnail Check] 載入 {char_key} / fill.png 失敗: {e}")


def build_gacha_single_embed(card_data: dict, user_name: str, cost: int, thumbnails_dir: str = None) -> tuple[discord.Embed, list[discord.File]]:
    """繪製單抽詳細 Embed"""
    eval_str, color = get_completeness_eval(card_data['completeness'])
    
    embed = discord.Embed(
        title="⛩️ 博麗神社祈願成功！",
        description=f"投入了 `{cost:,}` 賽錢，塞錢箱發出了清脆的聲響...",
        color=color
    )
    embed.add_field(name="角色", value=f"{card_data['emoji']} **{card_data['name']}**", inline=True)
    embed.add_field(name="階級與稱號", value=f"`[{card_data['rarity']}]` {card_data['title']}", inline=True)
    embed.add_field(name="完整度品相", value=eval_str, inline=False)
    embed.set_footer(text=f"卡牌編號: {card_data['instance_id']} | 擁有者: {user_name}")

    files = []
    used_keys = set()
    _apply_thumbnail(embed, card_data.get("character_key"), thumbnails_dir, files, used_keys)

    return embed, files


def build_gacha_ten_embeds(results: list[dict], user_name: str, total_cost: int, thumbnails_dir: str = None) -> tuple[list[discord.Embed], list[discord.File]]:
    """十連抽 Multi-Embed 模式 (10 個獨立項，各項獨立 Thumbnail，貫穿無縫連貫邊條)"""
    files = []
    used_keys = set()
    embeds = []

    # 👑 1. 統一邊框顏色：取最高品質卡牌顏色 (10 個 Embed 顏色相同才會無縫黏合)
    best_card = max(results, key=lambda c: c['completeness'])
    _, main_color = get_completeness_eval(best_card['completeness'])

    total_count = len(results)

    for idx, card in enumerate(results, start=1):
        eval_str, _ = get_completeness_eval(card['completeness'])
        
        if idx == 1:
            header_desc = f"共抽到 **10** 張卡片 · 消耗賽錢：`{total_cost:,}` 🪙\n\n"
            title_str = f"⛩️ {user_name} 的抽卡結果（十連模式）"
        else:
            header_desc = ""
            title_str = f"{idx}. {card.get('emoji', '🎴')} [{card['rarity']}] {card['name']}"

        card_desc = (
            f"{header_desc}"
            f"├ *{card['title']}*\n"
            f"└ ID: `{card['instance_id']}` · {eval_str}"
        )

        # 🔑 絕對不要設定 url 參數！讓它作為一般純 Embed 發送
        embed = discord.Embed(
            title=title_str,
            description=card_desc,
            color=main_color
        )

        if idx == total_count:
            embed.set_footer(text=f"祈願者: {user_name} | 卡牌已全數寫入個人卡庫")

        _apply_thumbnail(embed, card.get("character_key"), thumbnails_dir, files, used_keys)
        embeds.append(embed)

    return embeds, files


def build_card_inventory_embeds(
    cards_page: list, 
    current_page: int, 
    total_pages: int, 
    total_cards_count: int, 
    all_cards: list, 
    user_name: str,
    thumbnails_dir: str = None
) -> tuple[list[discord.Embed], list[discord.File]]:
    """個人卡冊 Multi-Embed 模式 (10 個獨立 Embed，右側專屬/fill.png 縮圖，貫穿無縫連貫邊條)"""
    files = []
    used_keys = set()
    embeds = []

    if not cards_page:
        embed = discord.Embed(
            title=f"🎒 {user_name} 的博麗神社卡冊",
            description="*（當前分類下沒有任何卡牌）*",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"頁數: {current_page} / {total_pages} | 使用選單可進行篩選與詳細檢視")
        return [embed], files

    # 👑 1. 統一邊框顏色：計算當頁最高品質卡牌顏色，作為全頁 10 個 Embed 的統一顏色
    best_page_card = max(cards_page, key=lambda c: c['completeness'])
    _, main_color = get_completeness_eval(best_page_card['completeness'])

    # 2. 統計全體稀有度數量
    rarity_counts = {"N": 0, "R": 0, "SR": 0, "SSR": 0, "UR": 0, "LR": 0}
    for card in all_cards:
        r = card.get("rarity", "N")
        if r in rarity_counts:
            rarity_counts[r] += 1
            
    stats_str = (
        f"`N`: {rarity_counts['N']} | `R`: {rarity_counts['R']} | `SR`: {rarity_counts['SR']} | "
        f"`SSR`: {rarity_counts['SSR']} | `UR`: {rarity_counts['UR']} | `LR`: {rarity_counts['LR']}"
    )

    start_idx = (current_page - 1) * 10 + 1
    total_in_page = len(cards_page)

    for page_idx, card in enumerate(cards_page):
        global_idx = start_idx + page_idx
        eval_str, _ = get_completeness_eval(card['completeness'])

        # 👑 第一張卡片顯示總持有量與階級統計 Header
        if page_idx == 0:
            header_desc = f"📊 **持有總量**：`{total_cards_count}` 張\n🏷️ **階級統計**：{stats_str}\n\n"
        else:
            header_desc = ""

        card_desc = (
            f"{header_desc}"
            f"├ *{card['title']}*\n"
            f"└ {eval_str} | ID: `{card['instance_id']}`"
        )

        # 🔑 絕對不要設定 url 參數！所有 Embed 統一使用 main_color，觸發邊條無縫黏合！
        embed = discord.Embed(
            title=f"{global_idx}. {card.get('emoji', '🎴')} [{card['rarity']}] {card['name']}",
            description=card_desc,
            color=main_color
        )

        if page_idx == total_in_page - 1:
            embed.set_footer(text=f"頁數: {current_page} / {total_pages} | 使用選單可進行篩選與詳細檢視")

        # 🖼️ 為該張卡片掛載獨立縮圖
        _apply_thumbnail(embed, card.get("character_key"), thumbnails_dir, files, used_keys)
        embeds.append(embed)

    return embeds, files


def build_card_detail_embed(card_data: dict, user_name: str, thumbnails_dir: str = None) -> tuple[discord.Embed, list[discord.File]]:
    """繪製單張卡牌詳細鑑定頁面"""
    eval_str, color = get_completeness_eval(card_data['completeness'])

    embed = discord.Embed(
        title=f"🎴 卡牌鑑定詳情：{card_data['name']}",
        color=color
    )
    embed.add_field(name="角色名稱", value=f"{card_data.get('emoji', '🎴')} **{card_data['name']}**", inline=True)
    embed.add_field(name="稀有度階級", value=f"`[{card_data['rarity']}]`", inline=True)
    embed.add_field(name="專屬稱號", value=card_data['title'], inline=False)
    embed.add_field(name="完整度 (Float) 品相", value=eval_str, inline=False)
    embed.add_field(name="卡牌識別號 (Instance ID)", value=f"`{card_data['instance_id']}`", inline=True)
    embed.add_field(name="獲得時間", value=f"`{card_data.get('obtained_at', '未知')}`", inline=True)

    embed.set_footer(text=f"擁有者: {user_name}")

    files = []
    used_keys = set()
    _apply_thumbnail(embed, card_data.get("character_key"), thumbnails_dir, files, used_keys)

    return embed, files
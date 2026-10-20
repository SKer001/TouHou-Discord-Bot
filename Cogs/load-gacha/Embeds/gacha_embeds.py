import discord

def get_completeness_eval(completeness: float) -> tuple[str, discord.Color]:
    """根據完整度回傳東方風格的評價名稱與對應顏色"""
    comp_str = f"{completeness:.4f}"
    
    if completeness >= 0.990:
        return f"💠 **{comp_str}** [神代之遺]", discord.Color.teal()       # 神明御賜，完美無缺
    elif completeness >= 0.900:
        return f"🌟 **{comp_str}** [蓬萊仙姿]", discord.Color.gold()       # 猶如蓬萊之藥般歷久彌新
    elif completeness >= 0.700:
        return f"🌸 **{comp_str}** [西行櫻華]", discord.Color.purple()     # 品相極佳，帶有櫻花美感
    elif completeness >= 0.400:
        return f"🍃 **{comp_str}** [妖怪山珍]", discord.Color.green()      # 常規良品，妖怪山特產水準
    elif completeness >= 0.150:
        return f"🍂 **{comp_str}** [人間凡品]", discord.Color.light_grey() # 人里流通品質，有使用痕跡
    elif completeness >= 0.050:
        return f"🪵 **{comp_str}** [迷途遺物]", discord.Color.dark_grey()  # 陳舊斑駁，彷彿遺棄在竹林
    else:
        return f"🏚️ **{comp_str}** [彈幕戰痕]", discord.Color.dark_red()   # 飽經彈幕洗禮，近乎碎裂

def build_gacha_single_embed(card_data: dict, user_name: str, cost: int) -> discord.Embed:
    """繪製祈願單抽的詳細結果"""
    eval_str, color = get_completeness_eval(card_data['completeness'])
    
    embed = discord.Embed(
        title="⛩️ 博麗神社祈願成功！",
        description=f"投入了 `{cost}` 賽錢，塞錢箱發出了清脆的聲響...",
        color=color
    )
    embed.add_field(name="角色", value=f"{card_data['emoji']} **{card_data['name']}", inline=True)
    embed.add_field(name="階級與稱號", value=f"`[{card_data['rarity']}]` {card_data['title']}", inline=True)
    embed.add_field(name="完整度品相", value=eval_str, inline=False)
    embed.set_footer(text=f"卡牌編號: {card_data['instance_id']} | 擁有者: {user_name}")
    
    return embed

def build_gacha_ten_embed(results: list, user_name: str, total_cost: int) -> discord.Embed:
    """繪製祈願十連抽的簡略清單結果"""
    # 找出十連中完整度最高的一張來決定卡片顏色
    best_card = max(results, key=lambda x: x['completeness'])
    _, best_color = get_completeness_eval(best_card['completeness'])

    embed = discord.Embed(
        title="⛩️ 博麗神社 十連祈願結果",
        description=f"大方地投入了 `{total_cost}` 賽錢！靈夢非常高興，神明賜予了以下卡牌：\n\n",
        color=best_color
    )
    
    lines = []
    for card in results:
        eval_str, _ = get_completeness_eval(card['completeness'])
        # 組合簡略資訊格式
        line = f"• `[{card['rarity']}]` {card['emoji']} ** - *{card['title']}* | {eval_str}"
        lines.append(line)
        
    embed.description += "\n".join(lines)
    embed.set_footer(text=f"祈願者: {user_name} | 卡牌已全數收入個人卡庫")
    
    return embed

def build_card_inventory_embed(
    cards_page: list, 
    current_page: int, 
    total_pages: int, 
    total_cards_count: int, 
    all_cards: list, 
    user_name: str
) -> discord.Embed:
    """繪製個人卡冊列表 Embed"""
    # 統計各稀有度數量
    rarity_counts = {"N": 0, "R": 0, "SR": 0, "SSR": 0, "UR": 0, "LR": 0}
    for card in all_cards:
        r = card.get("rarity", "N")
        if r in rarity_counts:
            rarity_counts[r] += 1
            
    stats_str = (
        f"`N`: {rarity_counts['N']} | `R`: {rarity_counts['R']} | `SR`: {rarity_counts['SR']} | "
        f"`SSR`: {rarity_counts['SSR']} | `UR`: {rarity_counts['UR']} | `LR`: {rarity_counts['LR']}"
    )

    embed = discord.Embed(
        title=f"🎒 {user_name} 的博麗神社卡冊",
        description=f"📊 **持有總量**：`{total_cards_count}` 張\n🏷️ **階級統計**：{stats_str}\n\n",
        color=discord.Color.blue()
    )

    if not cards_page:
        embed.description += "正文內容：*（當前分類下沒有任何卡牌）*"
    else:
        lines = []
        for card in cards_page:
            eval_str, _ = get_completeness_eval(card['completeness'])
            line = (
                f"• `[{card['rarity']}]` {card.get('emoji', '🎴')} **{card['name']}** - *{card['title']}*\n"
                f"  └ {eval_str} | `ID: {card['instance_id']}`"
            )
            lines.append(line)
        embed.description += "\n".join(lines)

    embed.set_footer(text=f"頁數: {current_page} / {total_pages} | 使用下拉選單可進行篩選或詳細檢視")
    return embed


def build_card_detail_embed(card_data: dict, user_name: str) -> discord.Embed:
    """繪製單張卡牌的詳細鑑定頁面 Embed"""
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

    embed.set_footer(text=f"擁有者: {user_name} | 點擊下方按鈕可返回卡冊列表")
    return embed
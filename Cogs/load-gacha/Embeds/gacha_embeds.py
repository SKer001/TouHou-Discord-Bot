"""
卡牌畫面產生器 (Discord Components V2)

需要 discord.py >= 2.6   ➔  pip install -U discord.py

這裡的每個 build_*_container() 都回傳一個 ui.Container：
  - 左側色條 = Container 的 accent_color
  - 每張卡 = 一個 Section (左邊文字 + 右邊 Thumbnail)
呼叫端 (gacha.py) 再把按鈕 / 選單加進 Container，最後放進 LayoutView 送出。

⚠️ Components V2 訊息不能同時帶 content / embeds，且「每則訊息最多 40 個元件」，
   (Section 本身 + 文字 + Thumbnail = 3 個)，所以卡冊每頁預設 8 張。
"""
import discord
from discord import ui

# 卡冊每頁張數：8 張 Section(24) + 標題/分隔(3~4) + 兩個選單列(4) + 翻頁列(4) = 36 < 40
INVENTORY_PER_PAGE = 8


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


# ================= 🖼️ Thumbnail 機制 =================
def get_thumbnail_url(char_key: str | None, thumbnails: dict | None) -> str | None:
    """
    依角色 ID (例如 "marisa") 到 Thumbnails.json 查 URL：
    1. 有該 ID 且 URL 不為空 ➔ 使用角色專屬圖片
    2. 沒有該 ID ➔ 退回使用 "fill" 的 URL
    3. 連 "fill" 都沒有 ➔ 回傳 None (該項目只顯示文字)
    """
    if not thumbnails:
        return None
    return thumbnails.get(char_key) or thumbnails.get("fill")


def _card_block(text: str, char_key: str | None, thumbnails: dict | None):
    """文字 + 右側縮圖的 Section；沒有任何圖片 URL 時退化成純文字"""
    url = get_thumbnail_url(char_key, thumbnails)
    if url:
        return ui.Section(ui.TextDisplay(text), accessory=ui.Thumbnail(url))
    return ui.TextDisplay(text)


def _card_text(index: int, card: dict, id_first: bool = True) -> str:
    eval_str, _ = get_completeness_eval(card["completeness"])
    head = f"**{index}.** {card.get('emoji', '🎴')} `[{card['rarity']}]` **{card['name']}**"
    if id_first:
        return f"{head}\n├ *{card['title']}*\n└ ID: `{card['instance_id']}` · {eval_str}"
    return f"{head}\n├ *{card['title']}*\n└ {eval_str} | ID: `{card['instance_id']}`"


# ================= 🎴 Container 建構 =================
def build_gacha_single_container(card_data: dict, user_name: str, cost: int, thumbnails: dict = None) -> ui.Container:
    """單抽結果"""
    eval_str, color = get_completeness_eval(card_data["completeness"])

    text = (
        f"## ⛩️ 博麗神社祈願成功！\n"
        f"投入了 `{cost:,}` 賽錢，塞錢箱發出了清脆的聲響...\n\n"
        f"**角色**：{card_data.get('emoji', '🎴')} **{card_data['name']}**\n"
        f"**階級與稱號**：`[{card_data['rarity']}]` {card_data['title']}\n"
        f"**完整度品相**：{eval_str}\n\n"
        f"-# 卡牌編號: {card_data['instance_id']} | 擁有者: {user_name}"
    )

    container = ui.Container(accent_color=color)
    container.add_item(_card_block(text, card_data.get("character_key"), thumbnails))
    return container


def build_gacha_ten_container(results: list[dict], user_name: str, total_cost: int, thumbnails: dict = None) -> ui.Container:
    """十連結果：標題 + 分隔線 + 10 個『文字＋右側縮圖』的 Section"""
    best_card = max(results, key=lambda c: c["completeness"])
    _, color = get_completeness_eval(best_card["completeness"])

    container = ui.Container(accent_color=color)
    container.add_item(ui.TextDisplay(
        f"## ⛩️ {user_name} 的抽卡結果（十連模式）\n"
        f"共抽到 **{len(results)}** 張卡片 · 消耗賽錢：`{total_cost:,}` 🪙\n"
        f"-# 卡牌已全數寫入個人卡庫"
    ))
    container.add_item(ui.Separator())

    for idx, card in enumerate(results, start=1):
        container.add_item(_card_block(_card_text(idx, card, id_first=True), card.get("character_key"), thumbnails))

    return container


def build_card_inventory_container(
    cards_page: list,
    current_page: int,
    total_pages: int,
    total_cards_count: int,
    all_cards: list,
    user_name: str,
    thumbnails: dict = None,
    per_page: int = INVENTORY_PER_PAGE,
) -> ui.Container:
    """個人卡冊：當頁卡牌，每張一個『文字＋右側縮圖』的 Section"""
    if not cards_page:
        container = ui.Container(accent_color=discord.Color.blue())
        container.add_item(ui.TextDisplay(
            f"## 🎒 {user_name} 的博麗神社卡冊\n"
            f"*（當前分類下沒有任何卡牌）*\n"
            f"-# 頁數: {current_page} / {total_pages}"
        ))
        return container

    best_page_card = max(cards_page, key=lambda c: c["completeness"])
    _, color = get_completeness_eval(best_page_card["completeness"])

    rarity_counts = {"N": 0, "R": 0, "SR": 0, "SSR": 0, "UR": 0, "LR": 0}
    for card in all_cards:
        r = card.get("rarity", "N")
        if r in rarity_counts:
            rarity_counts[r] += 1

    stats_str = (
        f"`N`: {rarity_counts['N']} | `R`: {rarity_counts['R']} | `SR`: {rarity_counts['SR']} | "
        f"`SSR`: {rarity_counts['SSR']} | `UR`: {rarity_counts['UR']} | `LR`: {rarity_counts['LR']}"
    )

    container = ui.Container(accent_color=color)
    container.add_item(ui.TextDisplay(
        f"## 🎒 {user_name} 的博麗神社卡冊\n"
        f"📊 **持有總量**：`{total_cards_count}` 張\n"
        f"🏷️ **階級統計**：{stats_str}"
    ))
    container.add_item(ui.Separator())

    start_idx = (current_page - 1) * per_page + 1
    for page_idx, card in enumerate(cards_page):
        container.add_item(_card_block(
            _card_text(start_idx + page_idx, card, id_first=False),
            card.get("character_key"),
            thumbnails,
        ))

    return container


def build_card_detail_container(card_data: dict, user_name: str, thumbnails: dict = None) -> ui.Container:
    """單張卡牌詳細鑑定頁面"""
    eval_str, color = get_completeness_eval(card_data["completeness"])

    text = (
        f"## 🎴 卡牌鑑定詳情：{card_data['name']}\n"
        f"**角色名稱**：{card_data.get('emoji', '🎴')} **{card_data['name']}**\n"
        f"**稀有度階級**：`[{card_data['rarity']}]`\n"
        f"**專屬稱號**：{card_data['title']}\n"
        f"**完整度 (Float) 品相**：{eval_str}\n"
        f"**卡牌識別號 (Instance ID)**：`{card_data['instance_id']}`\n"
        f"**獲得時間**：`{card_data.get('obtained_at', '未知')}`\n\n"
        f"-# 擁有者: {user_name}"
    )

    container = ui.Container(accent_color=color)
    container.add_item(_card_block(text, card_data.get("character_key"), thumbnails))
    return container
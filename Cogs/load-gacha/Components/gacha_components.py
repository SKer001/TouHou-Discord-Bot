"""
卡牌畫面產生器 (Discord Components V2)

需要 discord.py >= 2.6   ➔  pip install -U discord.py

這裡的每個 build_*_container() 都回傳一個 ui.Container：
  - 左側色條 = Container 的 accent_color
  - 每張卡 = 一個 Section (左邊文字 + 右邊 Thumbnail)
呼叫端 (gacha.py) 再把按鈕 / 選單加進 Container，最後放進 LayoutView 送出。

⚠️ Components V2 訊息不能同時帶 content / embeds，且「每則訊息最多 40 個元件」，
   (Section 本身 + 文字 + Thumbnail = 3 個)，所以每頁的列數要算過。
"""
import discord
from discord import ui

# 卡冊 (疊卡列表) 每頁疊數：
#   Container + 標題 + 分隔(3) + 7 疊 Section(21) + 分隔(1)
#   + 卡池篩選 / 階級篩選 / 疊選單 三列(6) + 翻頁與排序列(5) = 36 < 40
STACKS_PER_PAGE = 7
# 單一疊內每頁張數：
#   Container + 標題 + 分隔(3) + 8 張 Section(24) + 分隔(1) + 卡牌選單列(2) + 返回與翻頁列(5) = 35 < 40
STACK_CARDS_PER_PAGE = 8


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
def build_gacha_single_container(card_data: dict, user_name: str, cost: int, thumbnails: dict = None, pool_name: str = "") -> ui.Container:
    """單抽結果"""
    eval_str, color = get_completeness_eval(card_data["completeness"])

    text = (
        f"## ⛩️ 博麗神社祈願成功！\n"
        f"-# 卡池：{pool_name}\n"
        f"投入了 `{cost:,}` 賽錢，塞錢箱發出了清脆的聲響...\n\n"
        f"**角色**：{card_data.get('emoji', '🎴')} **{card_data['name']}**\n"
        f"**階級與稱號**：`[{card_data['rarity']}]` {card_data['title']}\n"
        f"**完整度品相**：{eval_str}\n\n"
        f"-# 卡牌編號: {card_data['instance_id']} | 擁有者: {user_name}"
    )

    container = ui.Container(accent_color=color)
    container.add_item(_card_block(text, card_data.get("character_key"), thumbnails))
    return container


def build_gacha_ten_container(results: list[dict], user_name: str, total_cost: int, thumbnails: dict = None, pool_name: str = "") -> ui.Container:
    """十連結果：標題 + 分隔線 + 10 個『文字＋右側縮圖』的 Section"""
    best_card = max(results, key=lambda c: c["completeness"])
    _, color = get_completeness_eval(best_card["completeness"])

    container = ui.Container(accent_color=color)
    container.add_item(ui.TextDisplay(
        f"## ⛩️ {user_name} 的抽卡結果（十連模式）\n"
        f"🎰 卡池：{pool_name}\n"
        f"共抽到 **{len(results)}** 張卡片 · 消耗賽錢：`{total_cost:,}` 🪙\n"
        f"-# 卡牌已全數寫入個人卡庫"
    ))
    container.add_item(ui.Separator())

    for idx, card in enumerate(results, start=1):
        container.add_item(_card_block(_card_text(idx, card, id_first=True), card.get("character_key"), thumbnails))

    return container


def _rarity_stats(all_cards: list) -> str:
    rarity_counts = {"N": 0, "R": 0, "SR": 0, "SSR": 0, "UR": 0, "LR": 0}
    for card in all_cards:
        r = card.get("rarity", "N")
        if r in rarity_counts:
            rarity_counts[r] += 1
    return " | ".join(f"`{r}`: {n}" for r, n in rarity_counts.items())


def build_stack_list_container(
    stacks_page: list[dict],
    current_page: int,
    total_pages: int,
    total_stacks: int,
    all_cards: list,
    user_name: str,
    thumbnails: dict = None,
    filter_desc: str = "",
    start_index: int = 1,
) -> ui.Container:
    """
    個人卡冊 (疊卡模式)：同角色、同階級的卡疊成一列
    stack = {"character_key", "rarity", "name", "emoji", "title", "cards": [...], "best": float}
    """
    header = (
        f"## 🎒 {user_name} 的博麗神社卡冊\n"
        f"📊 **持有總量**：`{len(all_cards)}` 張 · `{total_stacks}` 疊 (目前篩選)\n"
        f"🏷️ **階級統計**：{_rarity_stats(all_cards)}\n"
        f"-# {filter_desc}"
    )

    if not stacks_page:
        container = ui.Container(accent_color=discord.Color.blue())
        container.add_item(ui.TextDisplay(header))
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(f"*（當前篩選下沒有任何卡牌）*\n-# 頁數: {current_page} / {total_pages}"))
        return container

    best_stack = max(stacks_page, key=lambda s: s["best"])
    _, color = get_completeness_eval(best_stack["best"])

    container = ui.Container(accent_color=color)
    container.add_item(ui.TextDisplay(header))
    container.add_item(ui.Separator())

    for idx, stack in enumerate(stacks_page, start=start_index):
        best_eval, _ = get_completeness_eval(stack["best"])
        text = (
            f"**{idx}.** {stack.get('emoji', '🎴')} `[{stack['rarity']}]` **{stack['name']}**　×**{len(stack['cards'])}**\n"
            f"├ *{stack['title']}*\n"
            f"└ 最高完整度 {best_eval}"
        )
        container.add_item(_card_block(text, stack["character_key"], thumbnails))

    return container


def build_stack_cards_container(
    stack: dict,
    cards_page: list,
    current_page: int,
    total_pages: int,
    user_name: str,
    thumbnails: dict = None,
    start_index: int = 1,
) -> ui.Container:
    """單一疊的內容：列出這一疊裡的每一張卡 (依完整度由高到低)"""
    _, color = get_completeness_eval(stack["best"])
    container = ui.Container(accent_color=color)
    container.add_item(ui.TextDisplay(
        f"## {stack.get('emoji', '🎴')} `[{stack['rarity']}]` {stack['name']}　×{len(stack['cards'])}\n"
        f"*{stack['title']}*\n"
        f"-# {user_name} 的卡冊 · 依完整度由高到低排列"
    ))
    container.add_item(ui.Separator())

    for idx, card in enumerate(cards_page, start=start_index):
        eval_str, _ = get_completeness_eval(card["completeness"])
        text = f"**{idx}.** {eval_str}\n└ ID: `{card['instance_id']}` · 取得於 `{card.get('obtained_at', '未知')}`"
        container.add_item(_card_block(text, card.get("character_key"), thumbnails))

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


# ================= ⚗️ 合成 / 🔮 融合 =================
def _material_lines(cards: list[dict]) -> str:
    lines = []
    for idx, card in enumerate(cards, start=1):
        eval_str, _ = get_completeness_eval(card["completeness"])
        lines.append(f"**{idx}.** `{card['instance_id']}` · {eval_str}")
    return "\n".join(lines)


def build_synthesis_preview_container(card_a: dict, card_b: dict, preview: dict, user_name: str, thumbnails: dict = None) -> ui.Container:
    """合成確認畫面：兩張素材 + 預計結果 (一般 / 加倍兩種可能，按下確認才擲加倍)"""
    normal_eval, color = get_completeness_eval(preview["normal_completeness"])
    doubled_eval, _ = get_completeness_eval(preview["doubled_completeness"])
    chance = preview["double_chance"] * 100

    text = (
        f"## ⚗️ 卡牌合成確認\n"
        f"{card_a.get('emoji', '🎴')} `[{card_a['rarity']}]` **{card_a['name']}** - *{card_a['title']}*\n\n"
        f"**消耗素材**\n{_material_lines([card_a, card_b])}\n\n"
        f"**一般結果**：{normal_eval}（`+{preview['normal_increase']:.4f}`）\n"
        f"**✨ 加倍結果**：{doubled_eval}（`+{preview['doubled_increase']:.4f}`）\n"
        f"**🎲 加倍機率**：`{chance:.2f}%`\n"
        f"-# 兩張完整度越接近，增幅與加倍機率越高\n\n"
        f"-# ⚠️ 確認後兩張素材卡會消失，並產生一張新卡 | 擁有者: {user_name}"
    )
    container = ui.Container(accent_color=color)
    container.add_item(_card_block(text, card_a.get("character_key"), thumbnails))
    return container


def build_synthesis_result_container(new_card: dict, increase: float, doubled: bool, user_name: str, thumbnails: dict = None) -> ui.Container:
    """合成完成"""
    eval_str, color = get_completeness_eval(new_card["completeness"])
    bonus_str = f"`+{increase:.4f}`" + (" ✨ 加倍！" if doubled else "")

    text = (
        f"## ⚗️ 合成成功！\n"
        f"兩張卡牌的靈力交融在一起，化為了新的形態...\n\n"
        f"**角色**：{new_card.get('emoji', '🎴')} **{new_card['name']}**\n"
        f"**階級與稱號**：`[{new_card['rarity']}]` {new_card['title']}\n"
        f"**完整度品相**：{eval_str}（{bonus_str}）\n\n"
        f"-# 卡牌編號: {new_card['instance_id']} | 擁有者: {user_name}"
    )
    container = ui.Container(accent_color=color)
    container.add_item(_card_block(text, new_card.get("character_key"), thumbnails))
    return container


def build_fusion_preview_container(cards: list[dict], next_rarity: str, next_title: str, user_name: str, thumbnails: dict = None) -> ui.Container:
    """融合確認畫面：三張滿完整度素材 ➔ 高一階 (新卡完整度隨機)"""
    base = cards[0]
    text = (
        f"## 🔮 卡牌融合確認\n"
        f"{base.get('emoji', '🎴')} **{base['name']}**　`[{base['rarity']}]` ➔ `[{next_rarity}]`\n"
        f"**新稱號**：*{next_title}*\n\n"
        f"**消耗素材**\n{_material_lines(cards)}\n\n"
        f"**新卡完整度**：🎲 隨機（與祈願相同）\n\n"
        f"-# ⚠️ 確認後三張素材卡會消失，並產生一張高一階的新卡 | 擁有者: {user_name}"
    )
    container = ui.Container(accent_color=discord.Color.purple())
    container.add_item(_card_block(text, base.get("character_key"), thumbnails))
    return container


def build_fusion_result_container(new_card: dict, old_rarity: str, user_name: str, thumbnails: dict = None) -> ui.Container:
    """融合完成"""
    eval_str, color = get_completeness_eval(new_card["completeness"])
    text = (
        f"## 🔮 融合成功！\n"
        f"三張卡牌的力量產生共鳴，昇華為更高的階級！\n\n"
        f"**角色**：{new_card.get('emoji', '🎴')} **{new_card['name']}**\n"
        f"**階級與稱號**：`[{old_rarity}]` ➔ `[{new_card['rarity']}]` {new_card['title']}\n"
        f"**完整度品相**：{eval_str}\n\n"
        f"-# 卡牌編號: {new_card['instance_id']} | 擁有者: {user_name}"
    )
    container = ui.Container(accent_color=color)
    container.add_item(_card_block(text, new_card.get("character_key"), thumbnails))
    return container
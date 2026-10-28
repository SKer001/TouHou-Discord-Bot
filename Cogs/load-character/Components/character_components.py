"""
東方角色圖鑑畫面產生器 (Discord Components V2)

需要 discord.py >= 2.6   ➔  pip install -U discord.py

每個 build_*_container() 回傳一個 ui.Container，
下拉選單由呼叫端 (character.py) 加進 Container 後再送出。
角色資料來自 Characters/<分類>/<角色id>.json (由 Utils/character_data.py 載入)。
"""
import discord
from discord import ui

# 角色檔案頁的色條：依該角色「最高階級」上色
RARITY_COLORS = {
    "N": discord.Color.light_grey(),
    "R": discord.Color.green(),
    "SR": discord.Color.blue(),
    "SSR": discord.Color.purple(),
    "UR": discord.Color.gold(),
    "LR": discord.Color.red(),
}

SP_TYPE_NAMES = {
    "damage": "⚔️ 傷害",
    "heal": "💚 治療",
    "buff": "⬆️ 增益",
    "debuff": "⬇️ 減益",
    "shield": "🛡️ 護盾",
}


# ---------------------------------------------------------
# 🖼️ Thumbnail：依角色 ID 查 images/Thumbnails.json，沒有就用 "fill"
# ---------------------------------------------------------
def get_thumbnail_url(char_id: str | None, thumbnails: dict | None) -> str | None:
    if not thumbnails:
        return None
    return thumbnails.get(char_id) or thumbnails.get("fill")


def _rarity_range(char: dict) -> str:
    rarities = char["gacha"].get("rarities", [])
    return f"{rarities[0]} ~ {rarities[-1]}" if rarities else "—"


# ---------------------------------------------------------
# 🏠 1. 首頁：選擇分類
# ---------------------------------------------------------
def build_home_container(categories: dict, owned: dict | None = None) -> ui.Container:
    """owned = {"角色id": {"階級": 張數}}：檢視者自己的收藏"""
    total_chars = sum(len(c["characters"]) for c in categories.values())
    owned = owned or {}
    owned_chars = sum(1 for c in categories.values() for ch in c["characters"] if ch["id"] in owned)

    container = ui.Container(accent_color=discord.Color.purple())
    container.add_item(ui.TextDisplay(
        "## 🌸 東方 Project 角色圖鑑資料庫\n"
        "請先從下方下拉式選單選擇 **角色分類 / 作品章節**：\n"
        f"📚 你已收集 `{owned_chars} / {total_chars}` 位角色\n"
        f"-# 共 {len(categories)} 個分類 · {total_chars} 位角色"
    ))
    return container


# ---------------------------------------------------------
# 📂 2. 分類頁：列出該分類的角色
# ---------------------------------------------------------
def build_category_container(category_data: dict, owned: dict | None = None) -> ui.Container:
    characters = category_data["characters"]
    owned = owned or {}
    owned_count = sum(1 for ch in characters if ch["id"] in owned)

    container = ui.Container(accent_color=discord.Color.blue())
    container.add_item(ui.TextDisplay(
        f"## 📂 {category_data['category_name']}\n"
        f"{category_data.get('description', '')}\n"
        f"📚 已收集 `{owned_count} / {len(characters)}` 位 · ✅ = 已擁有\n"
        f"-# 共 {len(characters)} 位角色 · 請從下方選單選擇要檢視的角色"
    ))

    if characters:
        container.add_item(ui.Separator())
        lines = [
            f"{'✅' if ch['id'] in owned else '▫️'} {ch.get('emoji', '👤')} **{ch['name']}**　`[{_rarity_range(ch)}]`\n"
            f"-# {ch['profile'].get('title', '')}"
            for ch in characters
        ]
        container.add_item(ui.TextDisplay("\n".join(lines)))
    return container


# ---------------------------------------------------------
# 👤 3. 角色檔案頁：文字 + 右側縮圖
# ---------------------------------------------------------
def build_character_container(char: dict, category_name: str, thumbnails: dict | None = None,
                              owned: dict | None = None) -> ui.Container:
    """owned = {"角色id": {"階級": 張數}}：檢視者自己的收藏"""
    my_cards = (owned or {}).get(char.get("id"), {})
    profile = char["profile"]
    gacha = char["gacha"]
    stats = char["base_stats"]
    sp = char["special_powers"]
    rarities = gacha.get("rarities", [])

    top_rarity = rarities[-1] if rarities else None
    container = ui.Container(accent_color=RARITY_COLORS.get(top_rarity, discord.Color.blurple()))

    # 標題區：稱號 + 名字 + 簡介 (右側放角色縮圖)
    header_text = (
        f"## 【{profile.get('title', '')}】{char.get('emoji', '')} {char['name']}\n"
        f"-# {category_name}\n"
        f"{profile.get('description', '')}"
    )
    url = get_thumbnail_url(char.get("id"), thumbnails)
    if url:
        container.add_item(ui.Section(ui.TextDisplay(header_text), accessory=ui.Thumbnail(url)))
    else:
        container.add_item(ui.TextDisplay(header_text))

    container.add_item(ui.Separator())

    # 基本資料 + 基礎數值
    container.add_item(ui.TextDisplay(
        f"**種族**：{profile.get('species', '未知')}\n"
        f"**能力**：`{profile.get('ability', '無')}`\n"
        f"**基礎數值**：❤️ HP `{stats.get('hp', 0):,}` · ⚔️ ATK `{stats.get('atk', 0):,}` · 🛡️ DEF `{stats.get('def', 0):,}`\n"
        f"-# 基礎數值尚未計入階級與完整度"
    ))

    # 卡池階級與稱號
    if rarities:
        pool_state = "🎴 可在 `/card gacha` 祈願中獲得" if gacha.get("enabled") else "🚫 目前不在卡池中"
        title_lines = "\n".join(
            f"`[{r}]` {gacha.get('titles', {}).get(r, '')}　" + (f"✅ ×{my_cards[r]}" if my_cards.get(r) else "▫️ 未擁有")
            for r in rarities
        )
        container.add_item(ui.TextDisplay(f"### 🏷️ 卡牌階級\n{title_lines}\n-# {pool_state}"))

    # 個人能力 (SP)：依階級分 I / II / III
    levels = sp.get("levels", {})
    if levels:
        lines = []
        for rarity, lv in levels.items():
            numeral = lv.get("id", "").rsplit("_", 1)[-1]
            detail = f"{SP_TYPE_NAMES.get(lv.get('type'), lv.get('type', '—'))} · 消耗 B 點 `{lv.get('spent', 0)}` · 冷卻 `{lv.get('cooldown', 0)}`"
            desc = f"\n-# {lv['desc']}" if lv.get("desc") else ""
            lines.append(f"**{numeral}** `[{rarity}]` {lv.get('name', '')}\n└ {detail}{desc}")
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(f"### ✨ 特殊能力 (SP)：{sp.get('name', '')}\n" + "\n".join(lines)))

    container.add_item(ui.TextDisplay("-# TouHou Project Character Profile • 東方角色圖鑑"))
    return container

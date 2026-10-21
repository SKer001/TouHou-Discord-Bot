"""
東方角色圖鑑畫面產生器 (Discord Components V2)

需要 discord.py >= 2.6   ➔  pip install -U discord.py

每個 build_*_container() 回傳一個 ui.Container，
下拉選單由呼叫端 (character.py) 加進 Container 後再送出。
"""
import discord
from discord import ui


# ---------------------------------------------------------
# 🖼️ Thumbnail：依角色 ID 查 images/Thumbnails.json，沒有就用 "fill"
# ---------------------------------------------------------
def get_thumbnail_url(char_id: str | None, thumbnails: dict | None) -> str | None:
    if not thumbnails:
        return None
    return thumbnails.get(char_id) or thumbnails.get("fill")


def parse_color(hex_str, default: str = "#FF0000") -> discord.Color:
    """支援 16 進位顏色碼 (#RRGGBB)；格式錯誤時退回預設色"""
    for value in (hex_str, default):
        try:
            return discord.Color(int(str(value).lstrip("#"), 16))
        except (ValueError, TypeError):
            continue
    return discord.Color.red()


# ---------------------------------------------------------
# 🏠 1. 首頁：選擇分類
# ---------------------------------------------------------
def build_home_container(db_data: dict) -> ui.Container:
    total_chars = sum(len(c.get("characters", [])) for c in db_data.values())

    container = ui.Container(accent_color=discord.Color.purple())
    container.add_item(ui.TextDisplay(
        "## 🌸 東方 Project 角色圖鑑資料庫\n"
        "請先從下方下拉式選單選擇 **角色分類 / 作品章節**：\n"
        f"-# 共 {len(db_data)} 個分類 · {total_chars} 位角色"
    ))
    return container


# ---------------------------------------------------------
# 📂 2. 分類頁：列出該分類的角色
# ---------------------------------------------------------
def build_category_container(category_data: dict) -> ui.Container:
    characters = category_data.get("characters", [])

    container = ui.Container(accent_color=discord.Color.blue())
    container.add_item(ui.TextDisplay(
        f"## 📂 {category_data.get('category_name', '未命名分類')}\n"
        f"{category_data.get('description', '')}\n"
        f"-# 共 {len(characters)} 位角色 · 請從下方選單選擇要檢視的角色"
    ))

    if characters:
        container.add_item(ui.Separator())
        lines = [
            f"👤 **{ch['name']}**　*{ch.get('en_name', '')}*\n-# {ch.get('title', '')}"
            for ch in characters
        ]
        container.add_item(ui.TextDisplay("\n".join(lines)))
    return container


# ---------------------------------------------------------
# 👤 3. 角色檔案頁：文字 + 右側縮圖
# ---------------------------------------------------------
def build_character_container(char: dict, thumbnails: dict | None = None) -> ui.Container:
    container = ui.Container(accent_color=parse_color(char.get("color")))

    # 標題區：稱號 + 名字 + 簡介 (右側放角色縮圖)
    header_text = (
        f"## 【{char['title']}】{char['name']}\n"
        f"-# {char.get('en_name', '')}\n"
        f"{char['description']}"
    )
    url = get_thumbnail_url(char.get("id"), thumbnails)
    if url:
        container.add_item(ui.Section(ui.TextDisplay(header_text), accessory=ui.Thumbnail(url)))
    else:
        container.add_item(ui.TextDisplay(header_text))

    container.add_item(ui.Separator())

    # 基本資料
    container.add_item(ui.TextDisplay(
        f"**種族**：{char.get('species', '未知')}　　**主要居所**：{char.get('location', '未知')}\n"
        f"**主要能力**：`{char.get('ability', '無')}`\n"
        f"**代表主題曲**：🎵 {char.get('theme_song', '無')}\n"
        f"**初次登場作品**：`{char['debut']}`"
    ))

    # 代表符卡 (沒有符卡的角色不顯示)
    spells = char.get("spell_cards", [])
    if spells:
        spells_text = "\n".join(f"• {s}" for s in spells)
        container.add_item(ui.TextDisplay(f"### 🃏 代表符卡\n```text\n{spells_text}\n```"))

    container.add_item(ui.TextDisplay("-# TouHou Project Character Profile • 東方角色圖鑑"))
    return container
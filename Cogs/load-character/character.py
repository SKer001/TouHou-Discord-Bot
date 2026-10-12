import os
import json
import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------
# 💡 載入同目錄下的 characters.json 資料庫
# ---------------------------------------------------------
JSON_PATH = os.path.join(os.path.dirname(__file__), "characters.json")

def load_character_data() -> dict:
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------
# 🎛️ 選單 1：選擇「當前分類下的其他角色」
# ---------------------------------------------------------
class SameCategoryCharacterSelect(discord.ui.Select):
    def __init__(self, category_key: str, current_char_id: str, db_data: dict):
        self.category_key = category_key
        self.db_data = db_data

        category = db_data.get(category_key, {})
        characters = category.get("characters", [])

        options = []
        for char in characters[:25]:  # 防止超過 25 個
            is_current = (char["id"] == current_char_id)
            options.append(
                discord.SelectOption(
                    label=char["name"],
                    value=char["id"],
                    description=f"{char['en_name']} - {char['title']}",
                    default=is_current,
                    emoji="👤"
                )
            )

        super().__init__(
            placeholder="選擇「當前分類」的其他角色...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        selected_char_id = self.values[0]
        category = self.db_data.get(self.category_key, {})
        target_char = next((c for c in category.get("characters", []) if c["id"] == selected_char_id), None)

        if target_char:
            embed = build_character_embed(target_char)
            view = CharacterProfileView(self.category_key, target_char["id"], self.db_data)
            await interaction.response.edit_message(embed=embed, view=view)


# ---------------------------------------------------------
# 🎛️ 選單 2：選擇「切換到其他作品/傳記分類」
# ---------------------------------------------------------
class CategorySwitchSelect(discord.ui.Select):
    def __init__(self, current_category_key: str, db_data: dict):
        self.db_data = db_data

        options = []
        for cat_key, cat_data in db_data.items():
            options.append(
                discord.SelectOption(
                    label=cat_data["category_name"],
                    value=cat_key,
                    description=cat_data.get("description", "")[:50],
                    default=(cat_key == current_category_key),
                    emoji="📚"
                )
            )

        super().__init__(
            placeholder="切換到其他作品/分類...",
            min_values=1,
            max_values=1,
            options=options[:25],
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        selected_cat_key = self.values[0]
        view = CharacterSelectionView(selected_cat_key, self.db_data)
        cat_name = self.db_data[selected_cat_key]["category_name"]

        embed = discord.Embed(
            title=f"📂 已選擇分類：{cat_name}",
            description="請從下方選單選擇您要檢視的角色：",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)


# ---------------------------------------------------------
# 🎛️ 容器 1：角色圖鑑檢視頁面 (包含雙下拉選單)
# ---------------------------------------------------------
class CharacterProfileView(discord.ui.View):
    def __init__(self, category_key: str, current_char_id: str, db_data: dict):
        super().__init__(timeout=180)
        # 加入「當前分類角色」選單
        self.add_item(SameCategoryCharacterSelect(category_key, current_char_id, db_data))
        # 加入「作品分類切換」選單
        self.add_item(CategorySwitchSelect(category_key, db_data))


# ---------------------------------------------------------
# 🎛️ 選單 3：第一階段（選擇分類後，選擇該分類的角色）
# ---------------------------------------------------------
class InitialCharacterSelect(discord.ui.Select):
    def __init__(self, category_key: str, db_data: dict):
        self.category_key = category_key
        self.db_data = db_data

        category = db_data.get(category_key, {})
        characters = category.get("characters", [])

        options = []
        for char in characters[:25]:
            options.append(
                discord.SelectOption(
                    label=char["name"],
                    value=char["id"],
                    description=f"{char['en_name']} - {char['title']}",
                    emoji="👤"
                )
            )

        super().__init__(
            placeholder="請選擇角色...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_char_id = self.values[0]
        category = self.db_data.get(self.category_key, {})
        target_char = next((c for c in category.get("characters", []) if c["id"] == selected_char_id), None)

        if target_char:
            embed = build_character_embed(target_char)
            view = CharacterProfileView(self.category_key, target_char["id"], self.db_data)
            await interaction.response.edit_message(embed=embed, view=view)


class CharacterSelectionView(discord.ui.View):
    def __init__(self, category_key: str, db_data: dict):
        super().__init__(timeout=120)
        self.add_item(InitialCharacterSelect(category_key, db_data))


# ---------------------------------------------------------
# 🎛️ 選單 0：指令觸發第一步 (選擇分類/作品)
# ---------------------------------------------------------
class InitialCategorySelect(discord.ui.Select):
    def __init__(self, db_data: dict):
        self.db_data = db_data

        options = []
        for cat_key, cat_data in db_data.items():
            options.append(
                discord.SelectOption(
                    label=cat_data["category_name"],
                    value=cat_key,
                    description=cat_data.get("description", "")[:50],
                    emoji="📂"
                )
            )

        super().__init__(
            placeholder="請選擇作品/角色分類...",
            min_values=1,
            max_values=1,
            options=options[:25]
        )

    async def callback(self, interaction: discord.Interaction):
        selected_cat_key = self.values[0]
        cat_name = self.db_data[selected_cat_key]["category_name"]

        embed = discord.Embed(
            title=f"📂 已選擇：{cat_name}",
            description="請從下方選單選擇該分類中的角色：",
            color=discord.Color.blue()
        )
        view = CharacterSelectionView(selected_cat_key, self.db_data)
        await interaction.response.edit_message(embed=embed, view=view)


class InitialCategoryView(discord.ui.View):
    def __init__(self, db_data: dict):
        super().__init__(timeout=120)
        self.add_item(InitialCategorySelect(db_data))


# ---------------------------------------------------------
# 🛠️ 核心 Embed 渲染輔助函式
# ---------------------------------------------------------
def build_character_embed(char_data: dict) -> discord.Embed:
    # 支援 16 進位顏色碼
    color_hex = char_data.get("color", "#FF0000").lstrip("#")
    color = discord.Color(int(color_hex, 16))

    embed = discord.Embed(
        title=f"【{char_data['title']}】{char_data['name']}",
        description=f"**初次登場作品：** `{char_data['debut']}`\n\n{char_data['description']}",
        color=color
    )
    embed.set_author(name=f"{char_data['name']} ({char_data['en_name']})")
    
    embed.add_field(name="種族", value=char_data.get("species", "未知"), inline=True)
    embed.add_field(name="主要居所", value=char_data.get("location", "未知"), inline=True)
    embed.add_field(name="主要能力", value=f"`{char_data.get('ability', '無')}`", inline=False)
    embed.add_field(name="代表主題曲", value=f"🎵 {char_data.get('theme_song', '無')}", inline=False)

    spells = char_data.get("spell_cards", [])
    if spells:
        spells_text = "\n".join([f"• {s}" for s in spells])
        embed.add_field(name="🃏 代表符卡", value=f"```text\n{spells_text}\n```", inline=False)

    embed.set_footer(text="TouHou Project Character Profile • 東方角色圖鑑")
    return embed


# ---------------------------------------------------------
# 🤖 Cog 核心類別
# ---------------------------------------------------------
class CharacterProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="character", description="瀏覽東方 Project 角色檔案與資料庫")
    async def character_cmd(self, interaction: discord.Interaction):
        # 每次發送時讀取最新的 JSON 資料
        db_data = load_character_data()

        if not db_data:
            await interaction.response.send_message("❌ 無法載入 `characters.json` 資料庫，請檢查檔案是否存在。", ephemeral=True)
            return

        embed = discord.Embed(
            title="🌸 東方 Project 角色圖鑑資料庫",
            description="請先從下方下拉式選單選擇 **角色分類 / 作品章節**：",
            color=discord.Color.purple()
        )
        view = InitialCategoryView(db_data)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterProfileCog(bot))
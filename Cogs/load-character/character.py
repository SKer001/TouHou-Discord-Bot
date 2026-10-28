import os
import json
import discord
from discord import app_commands, ui
from discord.ext import commands
from .Components.character_components import (
    build_home_container,
    build_category_container,
    build_character_container,
)
from Utils.components import send_notice
from Utils.character_data import load_categories
from Database.User_DB_Manager import get_user_cards

# ---------------------------------------------------------
# 💡 路徑設定
#   - 角色資料：專案根目錄的 Characters/<分類>/<角色id>.json (由 Utils/character_data.py 載入)
#   - images/Thumbnails.json：在專案根目錄 (與 Main.py 同級)，
#     本檔位於 Cogs/load-character/，往上兩層就是根目錄
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
THUMBNAILS_FILE = os.path.join(PROJECT_ROOT, "images", "Thumbnails.json")


def load_thumbnails() -> dict:
    """格式：{"角色ID": "圖片URL", ..., "fill": "預設圖URL"}；讀取失敗時回傳空字典 (只顯示文字)"""
    try:
        with open(THUMBNAILS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ [Character Error] 讀取 {THUMBNAILS_FILE} 失敗：{e}")
        return {}


# ---------------------------------------------------------
# 🎛️ 圖鑑瀏覽 View (Components V2)
#   同一個 View 依狀態切換三種畫面：
#   首頁 (只有分類選單) ➔ 分類頁 (角色選單 + 分類選單) ➔ 角色檔案頁 (同上)
# ---------------------------------------------------------
class CharacterBrowserView(ui.LayoutView):
    def __init__(self, categories: dict, thumbnails: dict, owned: dict | None = None):
        super().__init__(timeout=180)
        self.categories = categories
        self.thumbnails = thumbnails
        self.owned = owned or {}   # 下指令的人自己的收藏 {"角色id": {"階級": 張數}}
        self.category_key = None
        self.char_id = None
        self.message = None  # 送出後由指令填入，供逾時時停用選單
        self.char_select = None
        self.category_select = None

        self.build()

    def build(self):
        """依目前狀態重新組出整個畫面"""
        self.char_select = None

        if self.category_key is None:
            container = build_home_container(self.categories, self.owned)
        elif self.char_id is None:
            container = build_category_container(self.categories[self.category_key], self.owned)
        else:
            char = self._get_char(self.category_key, self.char_id)
            container = build_character_container(
                char, self.categories[self.category_key]["category_name"], self.thumbnails, self.owned
            )

        container.add_item(ui.Separator())

        # 選單 1：當前分類的角色 (進入分類後才出現)
        if self.category_key is not None:
            characters = self.categories[self.category_key]["characters"]
            self.char_select = ui.Select(
                placeholder="選擇「當前分類」的其他角色..." if self.char_id else "請選擇角色...",
                options=[
                    discord.SelectOption(
                        label=ch["name"],
                        value=ch["id"],
                        description=ch["profile"].get("title", "")[:100] or None,
                        default=(ch["id"] == self.char_id),
                        emoji=ch.get("emoji") or "👤",
                    )
                    for ch in characters[:25]
                ],
            )
            self.char_select.callback = self.on_character
            container.add_item(ui.ActionRow(self.char_select))

        # 選單 2：作品 / 分類
        self.category_select = ui.Select(
            placeholder="請選擇作品/角色分類..." if self.category_key is None else "切換到其他作品/分類...",
            options=[
                discord.SelectOption(
                    label=cat["category_name"],
                    value=key,
                    description=cat.get("description", "")[:100] or None,
                    default=(key == self.category_key),
                    emoji="📂" if self.category_key is None else "📚",
                )
                for key, cat in list(self.categories.items())[:25]
            ],
        )
        self.category_select.callback = self.on_category
        container.add_item(ui.ActionRow(self.category_select))

        self.clear_items()
        self.add_item(container)

    def _get_char(self, category_key: str, char_id: str):
        characters = self.categories.get(category_key, {}).get("characters", [])
        return next((c for c in characters if c["id"] == char_id), None)

    async def refresh(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_category(self, interaction: discord.Interaction):
        selected = interaction.data["values"][0]
        if selected not in self.categories:
            await send_notice(interaction, "❌ 找不到該分類，請重新使用 `/character`。")
            return
        self.category_key = selected
        self.char_id = None
        await self.refresh(interaction)

    async def on_character(self, interaction: discord.Interaction):
        selected = interaction.data["values"][0]
        if self._get_char(self.category_key, selected) is None:
            await send_notice(interaction, "❌ 找不到該角色，請重新使用 `/character`。")
            return
        self.char_id = selected
        await self.refresh(interaction)

    async def on_timeout(self):
        """逾時後把選單反灰，避免點到沒反應的控制項"""
        for select in (self.char_select, self.category_select):
            if select is not None:
                select.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ---------------------------------------------------------
# 🤖 Cog 核心類別
# ---------------------------------------------------------
class CharacterProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="character", description="瀏覽東方 Project 角色檔案與資料庫")
    async def character_cmd(self, interaction: discord.Interaction):
        # 每次發送時讀取最新的角色資料 (改了 Characters/ 底下的檔案不必重開機器人)
        categories = load_categories()

        if not categories:
            await send_notice(interaction, "❌ 無法載入 `Characters/` 角色資料，請檢查資料夾與檔案格式。")
            return

        owned = {}
        for card in await get_user_cards(interaction.user.id):
            per_char = owned.setdefault(card["character_key"], {})
            per_char[card["rarity"]] = per_char.get(card["rarity"], 0) + 1

        view = CharacterBrowserView(categories, load_thumbnails(), owned)
        await interaction.response.send_message(view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterProfileCog(bot))

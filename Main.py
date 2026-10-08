import os
import sys
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# 讀取 .env 檔案
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")


# ---------------------------------------------------------
# 💡 控制台彩色進度條函式 (ANSI Color)
# ---------------------------------------------------------
def show_progress(current, total, prefix="載入進度", bar_length=30):
    """
    顯示 Console 彩色進度條
    :param current: 目前數值
    :param total: 總數值
    :param prefix: 進度條前綴文字
    :param bar_length: 進度條總格數（預設 30 格）
    """
    if total <= 0:
        return

    # 計算進度比例 (限制在 0.0 ~ 1.0)
    progress = min(max(current / total, 0.0), 1.0)
    percent = int(progress * 100)
    filled_length = int(bar_length * progress)

    # ANSI 色塊設定 (綠色 filled: \033[32m█ | 紅色 remaining: \033[31m-)
    GREEN_BLOCK = "\033[32m█\033[0m"
    RED_BLOCK = "\033[31m-\033[0m"

    bar = GREEN_BLOCK * filled_length + RED_BLOCK * (bar_length - filled_length)

    # \033[K 為清除至行尾指令，避免舊字元殘留
    print(f"\r{prefix}: |{bar}| {percent:3d}% [{current}/{total}]\033[K", end="", flush=True)

    # 達到 100% 時自動補換行
    if current >= total:
        print()


# ---------------------------------------------------------
# 🤖 機器人主類別
# ---------------------------------------------------------
class TouHouBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="TB! ",
            intents=discord.Intents.all(),  # 記得去 Developer Portal 開啟三大 特權 Intents
            description="幻想鄉的日常維護機器人 (TouHou Bot Core)"
        )

    async def setup_hook(self):
        """機器人初始化：優先單獨載入 Logger/Logger.py，再載入 Cogs/load-*"""
        print("🔧 開始初始化系統...")

        # ---------------------------------------------------------
        # 📌 步驟 1：單獨、優先載入 Logger/Logger.py
        # ---------------------------------------------------------
        try:
            await self.load_extension("Logger.Logger")
            print("✅ [獨立載入成功] Logger.Logger")
        except Exception as e:
            print(f"❌ [獨立載入失敗] Logger.Logger: {e}")
            
        """機器人啟動時的初始化 hook (自動掃描 Cogs/load-* 並顯示進度)"""
        print("🔧 開始初始化 Cogs 模組...")

        base_dir = os.path.dirname(os.path.abspath(__file__))
        cogs_dir = os.path.join(base_dir, "Cogs")

        # 1. 收集所有符合條件的 Cog 檔案路徑
        cogs_to_load = []
        if os.path.exists(cogs_dir):
            for folder_name in os.listdir(cogs_dir):
                folder_path = os.path.join(cogs_dir, folder_name)

                # 篩選：必須是「資料夾」且名稱為「load-」開頭
                if os.path.isdir(folder_path) and folder_name.startswith("load-"):
                    for filename in os.listdir(folder_path):
                        if filename.endswith(".py") and not filename.startswith("__"):
                            cog_import_path = f"Cogs.{folder_name}.{filename[:-3]}"
                            cogs_to_load.append(cog_import_path)

        total_cogs = len(cogs_to_load)

        # 2. 逐一載入 Cog 並更新進度條
        if total_cogs > 0:
            print(f"📦 找到 {total_cogs} 個模組，準備載入：")
            for index, cog_path in enumerate(cogs_to_load, start=1):
                try:
                    await self.load_extension(cog_path)
                    # 更新控制台彩色進度條
                    show_progress(index, total_cogs, prefix="🚀 Cogs 載入進度")
                except Exception as e:
                    print(f"\n❌ 載入失敗 ({cog_path}): {e}")
        else:
            print("⚠️ 未找到任何 Cogs/load-* 模組。")

        # 3. 同步 Slash Commands
        try:
            print("\n🔄 正在同步 Slash Commands 到 Discord...")
            synced = await self.tree.sync()
            print(f"✨ 成功同步 {len(synced)} 個斜線指令！")
        except Exception as e:
            print(f"\n❌ 同步斜線指令失敗: {e}")

    async def on_ready(self):
        print(f"🤖 {self.user} 已成功登入並上線！")
        activity = discord.CustomActivity(name="🌸 符卡規則生效中 | 前綴: TB!")
        
        # 方案 B：動態顯示「正在玩某款東方遊戲」 (若要用方案 B，請把上一行註解並取消註解下一行)
        # activity = discord.Game(name="東方紅魔鄉 ~ the Embodiment of Scarlet Devil")

        # 方案 C：動態顯示「正在觀看某個內容」
        # activity = discord.Activity(type=discord.ActivityType.watching, name="博麗神社賽錢箱")

        await self.change_presence(
            status=discord.Status.online,  # 可選: online(在線), idle(閒置), dnd(請勿打擾)
            activity=activity
        )


# =========================================================
# 主程式進入點
# =========================================================
async def main():
    if not TOKEN:
        print("❌ 錯誤：找不到 DISCORD_TOKEN，請檢查 .env 檔案內容！")
        return

    bot = TouHouBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
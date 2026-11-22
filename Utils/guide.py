"""
📚 教學書的入口 (0.36.000)：各指令群組的 `help` 子指令 (/card help、/ura help…) 都呼叫這裡
書的畫面在 Cogs/load-general/help.py (GuideView)；Cog 之間不互相 import，所以在呼叫時才取 (reload 後拿得到新版)
新增一本書：在 Cogs/load-general/Components/guide/ 加 <分類 key>.py、BOOK_KEYS 加一筆，
那個分類如果是指令群組，就在群組裡加:

    @app_commands.command(name="help", description="📖 教學書：〇〇的玩法與指令")
    async def help_book(self, interaction: discord.Interaction):
        await open_guide(interaction, "<分類 key>")
"""
import importlib

import discord


async def open_guide(interaction: discord.Interaction, key: str):
    await importlib.import_module("Cogs.load-general.help").open_guide(interaction, key)

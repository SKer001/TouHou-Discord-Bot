import os
import sys
import traceback
import discord
from discord import app_commands
from discord.ext import commands
import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
import datetime
import json
from Utils.components import send_notice

load_dotenv()

# =========================================================
# ⚙️ 設定區塊
# =========================================================
# 請填入你想接收「重大事件」特報的 Discord 頻道 ID
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

# ---------------------------------------------------------
# 1. 動態計算路徑與建立 logs 資料夾
# ---------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(CURRENT_DIR, "Logs")

if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# ---------------------------------------------------------
# 2. 設定 Python Logging
# ---------------------------------------------------------
logger = logging.getLogger('interaction_logger')
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter(
        fmt='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler (每日自動續寫與切割)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file_path = os.path.join(LOGS_DIR, f"interaction_{today_str}.log")
    file_handler = TimedRotatingFileHandler(
        filename=log_file_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    # 指定切換時附加的日期字串格式
    file_handler.suffix = "%Y-%m-%d.log"

    # 自訂檔名重新命名邏輯：確保午夜切換後，舊檔名也是標準的 YYYY-MM-DD.log 格式
    file_handler.namer = lambda name: name.replace(".log.", ".").replace(f"{today_str}.log.", "")

    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


# ---------------------------------------------------------
# 3. 輔助函式：遞迴解析 Options
# ---------------------------------------------------------
def parse_options(options_list: list) -> dict:
    result = {}
    for opt in options_list:
        if 'options' in opt:
            result[opt['name']] = parse_options(opt['options'])
        else:
            result[opt['name']] = opt.get('value')
    return result


# ---------------------------------------------------------
# 4. 核心 Cog 模組
# ---------------------------------------------------------
class Logger(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 註冊 Slash Command 的全域錯誤處理器
        bot.tree.error(self.on_app_command_error)

    # -----------------------------------------------------
    # 💡 通用輔助函式：傳送 Components V2 通知到指定頻道 (重大事件專用)
    # -----------------------------------------------------
    async def send_alert_log(self, title: str, description: str, color: discord.Color, fields: dict = None):
        """非同步發送重大事件至指定 DiscordLog 頻道"""
        try:
            channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if not channel:
                # 若抓不到頻道物件（例如快取尚未建立），嘗試從 API 拉取
                channel = await self.bot.fetch_channel(LOG_CHANNEL_ID)

            container = discord.ui.Container(accent_color=color)
            container.add_item(discord.ui.TextDisplay(f"## {title}\n{description}"))

            if fields:
                container.add_item(discord.ui.Separator())
                container.add_item(discord.ui.TextDisplay(
                    "\n".join(f"**{name}**\n{value}" for name, value in fields.items())
                ))

            # Discord 時間戳記：每位讀者會看到自己時區的時間
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(
                f"-# System Alert Log • <t:{int(discord.utils.utcnow().timestamp())}:F>"
            ))

            view = discord.ui.LayoutView(timeout=None)
            view.add_item(container)
            await channel.send(view=view)
        except Exception as e:
            logger.error(f"[SYSTEM ERROR] 無法發送 Log 至頻道 {LOG_CHANNEL_ID}: {e}")

    # =====================================================
    # A. Bot 生命週期與連線狀態監聽 (重大事件：開機/斷線/重連)
    # =====================================================
    @commands.Cog.listener()
    async def on_ready(self):
        msg = f"========== BOT STARTED: {self.bot.user} (ID: {self.bot.user.id}) =========="
        logger.info(msg)
        
        # 📢 發送至 Discord 頻道
        await self.send_alert_log(
            title="🟢 機器人已順利啟動",
            description=f"**Bot 名稱:** {self.bot.user}\n**Bot ID:** `{self.bot.user.id}`",
            color=discord.Color.green()
        )

    @commands.Cog.listener()
    async def on_disconnect(self):
        logger.warning("[SYSTEM] Bot disconnected from Discord WebSocket!")
        
        # 📢 發送至 Discord 頻道
        await self.send_alert_log(
            title="🔴 機器人已中斷連線",
            description="Bot 與 Discord 連線（WebSocket）已斷開，正嘗試重新連線中...",
            color=discord.Color.red()
        )

    @commands.Cog.listener()
    async def on_resumed(self):
        logger.info("[SYSTEM] Bot session successfully resumed.")
        
        # 📢 發送至 Discord 頻道
        await self.send_alert_log(
            title="🟡 連線已恢復 (Session Resumed)",
            description="與 Discord 的 WebSocket 連線已重新建立。",
            color=discord.Color.gold()
        )

    # =====================================================
    # B. Slash Command 全域錯誤監聽 (重大事件：指令崩潰報錯)
    # =====================================================
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        user = f"{interaction.user} ({interaction.user.id})"
        guild = f"{interaction.guild.name} ({interaction.guild.id})" if interaction.guild else "DM"
        command_name = interaction.command.name if interaction.command else "Unknown"

        # 解包原始 Exception
        original_error = getattr(error, 'original', error)

        # 1. 寫入本地 log 檔案
        log_msg = (
            f"[CMD ERROR] User: {user} | Guild: {guild} | Command: /{command_name} | "
            f"ErrorType: {type(original_error).__name__} | Details: {original_error}"
        )
        logger.error(log_msg)

        tb_lines = "".join(traceback.format_exception(type(original_error), original_error, original_error.__traceback__))
        logger.error(f"Traceback:\n{tb_lines}")

        # 2. 📢 發送至 Discord 紀錄頻道 (精簡並截斷，避免字數超過 Discord 限額)
        tb_snippet = tb_lines[-1000:] if len(tb_lines) > 1000 else tb_lines  # 節錄最後 1000 字元的核心報錯
        
        fields = {
            "👤 觸發者": f"{interaction.user.mention} (`{interaction.user.id}`)",
            "🏠 伺服器 / 頻道": f"{guild} / {interaction.channel.mention if interaction.channel else 'DM'}",
            "🤖 觸發指令": f"`/{command_name}`",
            "❌ 錯誤類型": f"`{type(original_error).__name__}`",
            "📝 錯誤訊息": f"```python\n{original_error}\n```",
            "🔍 Traceback 簡報": f"```python\n{tb_snippet}\n```"
        }

        await self.send_alert_log(
            title="🚨 斜線指令執行異常 (Command Error)",
            description="在執行 Slash Command 時捕捉到未處理的 Exception。",
            color=discord.Color.dark_red(),
            fields=fields
        )

        # 3. 回覆給使用者友善提示
        if not interaction.response.is_done():
            await send_notice(interaction, "❌ 執行指令時發生內部錯誤，已自動通報開發團隊處理。")

    # =====================================================
    # C. 全局 Interaction 監聽 (一般日常操作：僅寫入 Log 檔)
    # =====================================================
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        create_time = interaction.created_at.astimezone().strftime('%Y-%m-%d %H:%M:%S')
        user = f"{interaction.user} ({interaction.user.id})"
        guild = f"{interaction.guild.name} ({interaction.guild.id})" if interaction.guild else "Direct Message"
        channel = f"{interaction.channel.name} ({interaction.channel.id})" if interaction.channel else "Unknown"

        header = f"TriggeredAt: {create_time} | User: {user} | Guild: {guild} | Channel: {channel}"

        # 1. Slash Commands
        if interaction.type == discord.InteractionType.application_command:
            command_name = interaction.command.name if interaction.command else interaction.data.get('name', 'Unknown')
            raw_options = interaction.data.get('options', [])
            parsed_options = parse_options(raw_options) if raw_options else "No Options"

            log_msg = f"[SLASH CMD] {header} | Command: /{command_name} | Args: {parsed_options}"
            logger.info(log_msg)

        # 2. UI Components
        elif interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get('custom_id', 'Unknown')
            component_type = interaction.data.get('component_type', 'Unknown')
            values = interaction.data.get('values', [])
            values_str = f" | Selected: {values}" if values else ""

            log_msg = f"[COMPONENT] {header} | CustomID: {custom_id} | Type: {component_type}{values_str}"
            logger.info(log_msg)

        # 3. Modals
        elif interaction.type == discord.InteractionType.modal_submit:
            custom_id = interaction.data.get('custom_id', 'Unknown')
            components = interaction.data.get('components', [])
            modal_data = {}
            for row in components:
                for comp in row.get('components', []):
                    modal_data[comp['custom_id']] = comp['value']

            log_msg = f"[MODAL] {header} | CustomID: {custom_id} | Data: {json.dumps(modal_data, ensure_ascii=False)}"
            logger.info(log_msg)


async def setup(bot):
    await bot.add_cog(Logger(bot))
"""
🎪 /event 指令群組
- /event info ：查看活動內容 (限定地點、限定料理與配方、限定客人、剩餘時間)
- /event quest：活動任務 (進度、領取賽錢與經驗值、活動稱號)
活動資料在 Events/<id>.json，狀態在 Database/Economy_DB_Manager.py，任務在 Database/Quest_DB_Manager.py
"""
import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Database import Quest_DB_Manager as qdm
from Database import title_data
from Database.Item_DB_Manager import get_all_items
from Database.events import game_rules, load_events
from Utils.components import send_notice
from .Components.shrine_components import build_event_container
from .Components.quest_components import (
    QUESTS_PER_PAGE, build_quest_container, build_no_quest_container, quest_button,
)

CLAIM_FAIL_TEXT = {
    "not_active": "❌ 這個活動已經結束了，沒領的任務獎勵已經消失。",
    "not_found": "❌ 找不到這個任務 (活動內容可能更新了)。",
    "not_done": "❌ 這個任務還沒完成。",
    "claimed": "⚠️ 這個任務已經領過了。",
}


def claim_result_text(res: dict) -> str:
    """領取結果 ➔ 畫面上方的訊息"""
    if not res.get("ok"):
        return CLAIM_FAIL_TEXT.get(res.get("reason"), "❌ 領取失敗。")
    parts = []
    if res["money"]:
        parts.append(f"`{res['money']:,}` 賽錢")
    if res["exp"]:
        parts.append(f"`{res['exp']:,}` EXP")
    text = f"🎁 領到 {'、'.join(parts) or '獎勵'}！（{res['quest']['name']}）"
    er = res.get("exp_result") or {}
    if er.get("leveled_up"):
        text += f"\n🔴 P 點提升了！`{er['old_p']:.1f}` ➔ `{er['new_p']:.1f}` P" + ("　**FULL POWER!**" if er.get("is_max") else "")
    for tid in res.get("new_titles", []):
        if tid in title_data.TITLES:   # 改了活動檔還沒全部重載時 TITLES 裡可能還沒有 (earned_titles 已經記下來了)
            text += f"\n🏷️ 獲得活動稱號 **{title_data.title_label(tid)}**！可以到 `/profile` 戴上。"
    return text


def quest_pages(board: list[dict]) -> list[tuple[int, int]]:
    """分頁：一頁 = 一個活動的一段任務 [(活動 index, 從第幾個任務開始)]"""
    pages = []
    for i, b in enumerate(board):
        for start in range(0, max(1, len(b["quests"])), QUESTS_PER_PAGE):
            pages.append((i, start))
    return pages


class QuestView(ui.LayoutView):
    """/event quest：每個任務一列 + 右側領取按鈕；只有本人能按"""

    def __init__(self, user_id: int, board: list[dict], items: dict, page: int = 0):
        super().__init__(timeout=600)
        self.user_id, self.board, self.items = user_id, board, items
        self.page, self.result = page, None
        self.build()

    def build(self):
        self.clear_items()
        pages = quest_pages(self.board)
        if not pages:
            self.add_item(build_no_quest_container(self.result))
            return
        self.page = max(0, min(self.page, len(pages) - 1))
        i, start = pages[self.page]
        b = self.board[i]
        quests = b["quests"][start:start + QUESTS_PER_PAGE]
        buttons = {}
        for q in quests:
            btn = quest_button(q)
            if q["done"] and not q["claimed"]:
                btn.callback = self._make_claim(b["event"]["id"], q["id"])
            buttons[q["id"]] = btn
        container = build_quest_container(b, quests, buttons, self.items, self.result, self.page, len(pages))
        if len(pages) > 1:
            prev = ui.Button(label="◀ 上一頁", style=discord.ButtonStyle.secondary, disabled=self.page == 0)
            prev.callback = self.on_prev
            nxt = ui.Button(label="下一頁 ▶", style=discord.ButtonStyle.secondary, disabled=self.page >= len(pages) - 1)
            nxt.callback = self.on_next
            container.add_item(ui.ActionRow(prev, nxt))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的畫面，請自己用 `/event quest` 打開。")
            return False
        return True

    def _make_claim(self, event_id: str, quest_id: str):
        async def callback(interaction: discord.Interaction):
            res = await qdm.claim_quest(self.user_id, event_id, quest_id)   # 資料層會再檢查一次 (完成、沒領過、活動進行中)
            self.board = await qdm.get_quest_board(self.user_id)
            self.result = claim_result_text(res)
            self.build()
            await interaction.response.edit_message(view=self)
        return callback

    async def on_prev(self, interaction: discord.Interaction):
        self.page -= 1
        self.result = None
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_next(self, interaction: discord.Interaction):
        self.page += 1
        self.result = None
        self.build()
        await interaction.response.edit_message(view=self)


class EventCog(commands.GroupCog, group_name="event", group_description="🎪 活動：活動內容、活動任務"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="info", description="🎪 查看目前的活動：限定地點、限定料理、限定客人")
    async def info(self, interaction: discord.Interaction):
        overview = await econ.get_events_overview()
        overview.sort(key=lambda o: {"active": 0, "upcoming": 1, "ended": 2}[o["status"]])
        recipes = game_rules(list(load_events().values()))["recipes"]
        view = ui.LayoutView()
        view.add_item(build_event_container(overview, await get_all_items(), recipes))
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="quest", description="📜 活動任務：看任務進度、領取賽錢與經驗值、拿活動稱號")
    async def quest(self, interaction: discord.Interaction):
        board = await qdm.get_quest_board(interaction.user.id)
        view = QuestView(interaction.user.id, board, await get_all_items())
        await interaction.response.send_message(view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventCog(bot))

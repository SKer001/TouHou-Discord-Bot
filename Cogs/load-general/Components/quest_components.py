"""
📜 /event quest 的畫面 (Components V2)：只負責畫面，不碰資料庫
資料來自 Database/Quest_DB_Manager.get_quest_board；按鈕由 Cog 的 QuestView 建好、綁好 callback 再傳進來
"""
from datetime import datetime

import discord
from discord import ui

from Database.events import quest_goal

QUESTS_PER_PAGE = 9   # 一頁最多幾個任務 (每個任務 = Section + 文字 + 按鈕 3 個元件；9 個 + 標題 / 頁尾 / 換頁 ≈ 35，不超過 40)
QUEST_COLOR = discord.Color.red()


def _ts(value: str, style: str = "R") -> str:
    return f"<t:{int(datetime.fromisoformat(value).timestamp())}:{style}>"


def quest_button(quest: dict) -> ui.Button:
    """依狀態產生右側按鈕：完成沒領 ➔ 🎁 領取 (綠、可按)；已領 ➔ ✅ 已領取 (反灰)；未完成 ➔ 未完成 (反灰)"""
    if quest["claimed"]:
        return ui.Button(label="✅ 已領取", style=discord.ButtonStyle.secondary, disabled=True)
    if quest["done"]:
        return ui.Button(label="🎁 領取", style=discord.ButtonStyle.success)
    return ui.Button(label="未完成", style=discord.ButtonStyle.secondary, disabled=True)


def reward_text(reward: dict) -> str:
    """🎁 `50,000` 賽錢 + `300` EXP (獎勵要看清楚確切數字，不縮寫)"""
    parts = []
    if reward.get("money"):
        parts.append(f"`{reward['money']:,}` 賽錢")
    if reward.get("exp"):
        parts.append(f"`{reward['exp']:,}` EXP")
    return "🎁 " + " + ".join(parts) if parts else ""


def quest_line(quest: dict, event: dict, items: dict) -> str:
    """一個任務的文字：**1. 名稱**\\n-# 說明\\n目標 `3 / 10` · 🎁 獎勵"""
    goal = quest_goal(quest, event, items).replace("{p}", f"`{quest['cur']} / {quest['need']}`")
    reward = reward_text(quest.get("reward", {}))
    first, *rest = goal.split("\n", 1)
    line = f"**{quest['index']}. {quest['name']}**\n-# {quest['desc']}\n{first}" + (f" · {reward}" if reward else "")
    return line + (f"\n{rest[0]}" if rest else "")


def build_quest_container(board: dict, quests: list[dict], buttons: dict, items: dict,
                          result: str | None = None, page: int = 0, pages: int = 1) -> ui.Container:
    """
    一個活動的任務頁：board = get_quest_board 的一筆；quests = 這一頁要顯示的任務 (分頁由 View 決定)
    buttons = {任務 id: ui.Button}；result = 上方的結果訊息 (例如「🎁 領到…」)
    """
    ev = board["event"]
    container = ui.Container(accent_color=QUEST_COLOR)
    head = f"## {ev.get('emoji', '🎪')} {ev.get('name', ev['id'])}任務"
    if pages > 1:
        head += f"　`{page + 1} / {pages}`"
    head += "\n-# 活動期間做的事才會計數；完成後按右邊的「🎁 領取」拿獎勵"
    container.add_item(ui.TextDisplay((f"{result}\n" if result else "") + head))
    container.add_item(ui.Separator())
    for q in quests:
        container.add_item(ui.Section(ui.TextDisplay(quest_line(q, ev, items)), accessory=buttons[q["id"]]))
    container.add_item(ui.Separator())
    lines = [f"✅ 已完成 `{board['done']} / {board['total']}` 項 · 🎁 已領取 `{board['claimed']} / {board['total']}` 項"]
    for t in board.get("titles", []):
        state = "🏅 已獲得" if t["earned"] else f"`{min(board['claimed_all_runs'], t['min'])} / {t['min']}`"
        lines.append(f"🏷️ **[{t['rarity']}] {t['name']}**　領取 {t['min']} 項任務　{state}")
    if board.get("ends_at"):
        lines.append(f"⏳ 活動 {_ts(board['ends_at'])} 結束，沒領的獎勵會一起消失")
    else:
        lines.append("⏳ 活動測試中，沒有結束時間")
    if board.get("titles"):
        lines.append("-# 活動稱號是永久的，活動結束也會保留；可以到 `/profile` 的「🏷️ 更換稱號」戴上")
    container.add_item(ui.TextDisplay("\n".join(lines)))
    return container


def build_no_quest_container(result: str | None = None) -> ui.Container:
    """沒有進行中的活動任務"""
    container = ui.Container(accent_color=QUEST_COLOR)
    container.add_item(ui.TextDisplay((f"{result}\n" if result else "")
                                      + "## 📜 活動任務\n🎪 目前沒有進行中的活動，下次活動開始時再來看看吧！"))
    return container

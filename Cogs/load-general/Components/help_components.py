"""
❓ /help 的畫面：總覽 (各分類簡介) + 分類頁 (玩法說明 + 指令列表)
指令列表從 bot.tree 即時讀 (說明、參數)，新增指令不用改這裡；沒分到類的會出現在「其他」。
管理員指令 (名稱開頭 admin-) 不列出。
"""
import discord
from discord import app_commands, ui

HELP_COLOR = discord.Color.from_rgb(220, 70, 90)

# 分類：key ➔ (標題, 一句話簡介, 玩法說明, 包含的頂層指令)
CATEGORIES = {
    "card": (
        "🎴 抽卡與卡牌", "祈願抽角色卡、整理卡冊、合成與融合",
        "用賽錢向博麗神社祈願 (單抽 5,000、十連 50,000)，每個卡池連續 100 抽沒有 UR 必定給一張 UR。\n"
        "同角色同階級的卡可以**合成**提高完整度；三張完整度 1.0000 的卡可以**融合**成高一階。",
        ["card", "character"],
    ),
    "profile": (
        "👤 個人與簽到", "資料卡、每日簽到與運勢、排行榜",
        "每天 (台灣時間 00:00 重置) 簽到一次，抽今日運勢拿賽錢、經驗和一顆 🍙 飯糰。\n"
        "累積簽到 7 天開通市場與轉帳。資料卡可以設成私人，也能在上面用道具恢復體力。",
        ["profile", "daily", "leaderboard"],
    ),
    "shrine": (
        "⛩️ 神社經營", "賽錢箱、清掃、治退妖怪、採集、料理、招待參拜客",
        "神社每小時會進帳賽錢 (最多存 200,000，要回收)；神社變髒、妖怪出現都會降低效率，記得清掃和治退妖怪。\n"
        "用體力到各地**採集**素材 ➔ **料理** ➔ **招待**參拜客賺賽錢，客人心情越好給越多。",
        ["shrine"],
    ),
    "event": (
        "🎪 活動", "限定地點、限定料理、限定客人",
        "活動期間有限定的採集地點、料理和客人，端上活動料理報酬更高。\n活動結束時，活動道具會被清除。",
        ["event"],
    ),
    "market": (
        "💹 市場與交易", "卡牌市值、分解、玩家市場、轉帳",
        "每張卡都有每天浮動的市值，可以直接**分解**換賽錢，或上架到市場賣給其他玩家 (買家多付 5%)。\n"
        "也可以把賽錢**轉帳**給其他玩家 (手續費 5%)。市場與轉帳要累積簽到 7 天才能用，分解不限。",
        ["market", "trade"],
    ),
}
OTHER = ("📌 其他", "其他指令", "", [])


def is_admin_command(cmd) -> bool:
    return cmd.name.startswith("admin-")


def walk_commands(tree: app_commands.CommandTree) -> dict[str, list[app_commands.Command]]:
    """頂層指令名稱 ➔ 底下所有可執行的指令 (群組會攤開)，排除管理員指令"""
    out = {}
    for top in tree.get_commands(type=discord.AppCommandType.chat_input):
        if is_admin_command(top):
            continue
        if isinstance(top, app_commands.Group):
            out[top.name] = [c for c in top.walk_commands() if isinstance(c, app_commands.Command)]
        else:
            out[top.name] = [top]
    return out


def categorize(tree: app_commands.CommandTree) -> dict[str, list[app_commands.Command]]:
    """分類 key ➔ 指令；沒有分到類的放 other (不列 /help 自己)"""
    cmds = walk_commands(tree)
    result = {key: [c for top in tops for c in cmds.get(top, [])] for key, (_, _, _, tops) in CATEGORIES.items()}
    known = {top for *_, tops in CATEGORIES.values() for top in tops} | {"help"}
    other = [c for top, cs in cmds.items() if top not in known for c in cs]
    if other:
        result["other"] = other
    return {k: v for k, v in result.items() if v}


def category_info(key: str) -> tuple:
    return CATEGORIES.get(key, OTHER)


def command_line(cmd: app_commands.Command) -> str:
    line = f"**`/{cmd.qualified_name}`**　{cmd.description}"
    params = []
    for p in cmd.parameters:
        desc = p.description if p.description and p.description != "…" else ""
        name = p.display_name if p.required else f"[{p.display_name}]"
        params.append(f"`{name}`" + (f" {desc}" if desc else ""))
    if params:
        line += "\n-# 　" + "、".join(params)
    return line


def build_overview_container(categories: dict) -> ui.Container:
    c = ui.Container(accent_color=HELP_COLOR)
    c.add_item(ui.TextDisplay("## ❓ 指令說明\n幻想鄉的博麗神社歡迎你！從下面選單選一個分類，看詳細玩法和指令。"))
    c.add_item(ui.Separator())
    lines = []
    for key, cmds in categories.items():
        title, short, *_ = category_info(key)
        lines.append(f"**{title}**　`{len(cmds)}` 個指令\n-# {short}")
    c.add_item(ui.TextDisplay("\n".join(lines)))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay("-# 💡 新手建議：先 `/daily` 簽到 ➔ `/card gacha` 祈願 ➔ `/shrine manage` 打理神社"))
    return c


def build_category_container(key: str, cmds: list) -> ui.Container:
    title, _, guide, _ = category_info(key)
    c = ui.Container(accent_color=HELP_COLOR)
    c.add_item(ui.TextDisplay(f"## {title}" + (f"\n{guide}" if guide else "")))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay("\n".join(command_line(cmd) for cmd in cmds)))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay("-# `[ ]` 是可以不填的參數"))
    return c

"""
❓ /help 的畫面 (0.35.034 重做)
- 總覽：每個分類一行 + 「查看 ▶」按鈕、新手三步驟；管理員多一行「🛠️ 管理員指令表」
- 分類頁：玩法說明 (📖 怎麼玩) 和指令 (📋 指令) 放在同一頁，右上角放一張代表角色的卡面
- 🛠️ 管理員指令表：只有管理員打 /help 才看得到；依指令群組 (admin-user、admin-item…) 分段，
  一頁放不下 (Discord 一則訊息文字上限 4000 字) 就自動分成好幾頁 (admin1、admin2…)
指令列表都從 bot.tree 即時讀 (說明、參數)，新增指令不用改這裡；沒分到類的會出現在「📌 其他」，
沒寫在 ADMIN_GROUPS 的管理員群組會出現在「🛠️ 其他管理指令」。
"""
import discord
from discord import app_commands, ui

from Utils.thumbnails import load_thumbnails, thumbnail_url

HELP_COLOR = discord.Color.from_rgb(220, 70, 90)
ADMIN_COLOR = discord.Color.from_rgb(120, 125, 135)

# 分類：key ➔ 標題、一句話簡介、色條、代表卡面 (Thumbnails.json 的 角色, 階級)、怎麼玩 (一行一點)、包含的頂層指令
# 玩法裡的數字要跟程式一致 (見 TODO.md 0.1 / 0.2)；改數值時這裡也要改
CATEGORIES = {
    "card": {
        "title": "🎴 抽卡與卡牌", "short": "祈願抽角色卡、整理卡冊、合成與融合",
        "color": discord.Color.from_rgb(232, 170, 60), "thumb": ("marisa", "UR"),
        "guide": [
            "🙏 **祈願**：用賽錢抽角色卡，單抽 5,000、十連 50,000；有 📜 舊作、🔴 紅魔鄉兩個卡池",
            "🎯 **保底**：每個卡池連續 100 抽沒出 UR，第 100 抽一定是 UR",
            "⚗️ **合成**：兩張同角色、同階級的卡 ➔ 一張完整度更高的卡 (有機會加倍)",
            "🔮 **融合**：三張完整度 1.0000 的同一種卡 ➔ 升一個階級",
            "🔒 **收藏冊**：收進去的卡不會被拿去合成、融合、分解或上架",
            "📖 **圖鑑**：看每位角色的介紹和各階級的卡面",
        ],
        "tops": ["card", "character"],
    },
    "profile": {
        "title": "🪪 資料卡與簽到", "short": "每日簽到、運勢、稱號、名片、排行榜、通知",
        "color": discord.Color.from_rgb(88, 101, 242), "thumb": ("reimu", "SR"),
        "guide": [
            "📅 **每天簽到** (台灣時間 00:00 重置)：抽今日運勢，拿 50～2,000 賽錢、100～200 經驗和一顆 🍙 飯糰",
            "✨ **經驗值**會讓 P 點 (火力) 上升，最高 100.0 P",
            "🏷️ **稱號**：完成各種目標就會解鎖，在資料卡上選一個戴起來",
            "🖼️ **角色名片**：收藏冊集齊某位角色每個階級的完美卡，就能拿到那位角色的名片",
            "⚡ **恢復體力**：在資料卡上吃體力道具 (每天最多 3 個，含簽到的 🍙)",
            "🔓 累積簽到 **7 天**開通市場與轉帳",
        ],
        "tops": ["profile", "daily", "leaderboard", "notify"],
    },
    "shrine": {
        "title": "⛩️ 神社經營", "short": "賽錢箱、清掃、治退妖怪、採集、料理、招待參拜客",
        "color": discord.Color.from_rgb(214, 48, 49), "thumb": ("reimu", "UR"),
        "guide": [
            "💰 **賽錢箱**：神社每小時進帳 5,000 × 效率，最多存 20 萬，要記得回收",
            "🧹 **清掃・治退妖怪**：神社變髒、妖怪出現都會降低效率；治退一隻妖怪拿 800～1,500 賽錢",
            "🧺 **採集**：每趟花 20 體力，到 9 個地點採素材 (體力每 6 分鐘回 1，最多 240)",
            "🍳 **料理**：招待料理一鍋 2 份；⚡ 體力料理一鍋 1 份",
            "🍵 **招待參拜客**：端上客人點的菜賺賽錢 (每份 2,000 × 心情²)，再多端一份牠最愛的料理整筆 ×1.5",
            "💡 缺菜可以一鍵跳去料理，缺素材就按「🧺 快速採集」",
        ],
        "tops": ["shrine"],
    },
    "event": {
        "title": "🎪 活動", "short": "限定地點、料理、客人與活動任務",
        "color": discord.Color.from_rgb(180, 30, 60), "thumb": ("remilia", "UR"),
        "guide": [
            "🎪 活動期間有限定的採集地點、料理和客人，用 `/event info` 看現在有哪些活動",
            "🍽️ 端上活動料理，每份的報酬再 ×1.2",
            "📜 **活動任務**：活動期間做的事才算，完成後領賽錢和經驗值；領到一定數量還能**永久**拿到活動稱號",
            "⚠️ 活動結束時，活動道具和沒領的任務獎勵都會消失",
        ],
        "tops": ["event"],
    },
    "market": {
        "title": "💹 市場與交易", "short": "卡牌市值、分解、玩家市場、轉帳",
        "color": discord.Color.from_rgb(46, 160, 110), "thumb": ("sakuya", "UR"),
        "guide": [
            "📈 **市值**：每張卡都有每天浮動的市值，完整度越高越值錢",
            "♻️ **分解**：把卡直接換成賽錢 (不用開通)",
            "🛒 **市場**：上架賣給其他玩家，買家多付 5%；7 天沒賣出會退回",
            "💸 **轉帳**：把賽錢轉給其他玩家，手續費 5%，每天最多轉出 50 萬",
            "🔓 市場與轉帳要累積簽到 **7 天**才能用",
        ],
        "tops": ["market", "trade"],
    },
}
OTHER = {"title": "📌 其他", "short": "其他指令", "color": HELP_COLOR, "thumb": None, "guide": [], "tops": []}

# 🛠️ 管理員指令群組 ➔ 段落標題 (排列順序 = 這裡的順序；沒寫到的放最後)
ADMIN_GROUPS = {
    "admin-user": "👤 玩家資料 (賽錢、經驗、體力、簽到、稱號、名片)",
    "admin-item": "🎒 道具",
    "admin-gacha": "🎴 卡牌",
    "admin-shrine": "⛩️ 神社",
    "admin-market": "💹 市場",
    "admin-trade": "💸 轉帳",
    "admin-event": "🎪 活動",
    "admin-sys": "⚙️ 系統 (重載、同步、關機)",
}
ADMIN_OTHER = "🛠️ 其他管理指令"
ADMIN_PAGE_BUDGET = 3300   # 管理員表一頁的指令文字上限 (留空間給標題、頁尾；整則訊息上限 4000 字)

STEPS = ("1️⃣ `/daily` 簽到拿賽錢 ➔ 2️⃣ `/card gacha` 祈願抽卡 ➔ 3️⃣ `/shrine manage` 打理神社、招待客人賺更多賽錢")


def is_admin_command(cmd) -> bool:
    return cmd.name.startswith("admin-")


def _flatten(top) -> list[app_commands.Command]:
    if isinstance(top, app_commands.Group):
        return [c for c in top.walk_commands() if isinstance(c, app_commands.Command)]
    return [top]


def walk_commands(tree: app_commands.CommandTree, admin: bool = False) -> dict[str, list[app_commands.Command]]:
    """頂層指令名稱 ➔ 底下所有可執行的指令 (群組會攤開)；admin=False 只給一般指令、True 只給管理員指令"""
    return {top.name: _flatten(top) for top in tree.get_commands(type=discord.AppCommandType.chat_input)
            if is_admin_command(top) == admin}


def categorize(tree: app_commands.CommandTree) -> dict[str, list[app_commands.Command]]:
    """分類 key ➔ 一般指令；沒有分到類的放 other (不列 /help 自己，也不列管理員指令)"""
    cmds = walk_commands(tree)
    result = {key: [c for top in info["tops"] for c in cmds.get(top, [])] for key, info in CATEGORIES.items()}
    known = {top for info in CATEGORIES.values() for top in info["tops"]} | {"help"}
    other = [c for top, cs in cmds.items() if top not in known for c in cs]
    if other:
        result["other"] = other
    return {k: v for k, v in result.items() if v}


def category_info(key: str) -> dict:
    return CATEGORIES.get(key, OTHER)


def _clean_desc(text: str) -> str:
    return (text or "").replace("【開發者專用】", "").strip()


def command_line(cmd: app_commands.Command) -> str:
    """**`/指令`**　說明 (+ 下一行灰字參數；`[ ]` = 可以不填)"""
    line = f"**`/{cmd.qualified_name}`**　{_clean_desc(cmd.description)}"
    params = []
    for p in cmd.parameters:
        desc = p.description if p.description and p.description != "…" else ""
        name = p.display_name if p.required else f"[{p.display_name}]"
        params.append(f"`{name}`" + (f" {desc}" if desc else ""))
    if params:
        line += "\n-# 　" + "、".join(params)
    return line


# ---------------- 🛠️ 管理員指令表 ----------------
def admin_sections(tree: app_commands.CommandTree) -> list[tuple[str, list[app_commands.Command]]]:
    """[(段落標題, 指令), ...]，照 ADMIN_GROUPS 的順序；沒寫到的群組併成「其他管理指令」放最後"""
    cmds = walk_commands(tree, admin=True)
    sections = [(title, cmds[name]) for name, title in ADMIN_GROUPS.items() if cmds.get(name)]
    other = [c for name, cs in cmds.items() if name not in ADMIN_GROUPS for c in cs]
    if other:
        sections.append((ADMIN_OTHER, other))
    return sections


def _section_text(title: str, cmds: list) -> str:
    return f"### {title}\n" + "\n".join(command_line(c) for c in cmds)


def admin_pages(tree: app_commands.CommandTree) -> list[list[tuple[str, list]]]:
    """
    把管理員段落依序裝進好幾頁，一頁文字不超過 ADMIN_PAGE_BUDGET；
    一個段落自己就超過一頁時，拆成好幾段 (後面的標題加「(續)」)
    """
    blocks = []   # (標題, 指令)，每塊都保證放得進一頁
    for title, cmds in admin_sections(tree):
        chunk = []
        for cmd in cmds:
            if chunk and len(_section_text(title, chunk + [cmd])) > ADMIN_PAGE_BUDGET:
                blocks.append((title, chunk))
                chunk, title = [], title.split(" (")[0] + " (續)"
            chunk.append(cmd)
        blocks.append((title, chunk))
    pages, page, used = [], [], 0
    for title, chunk in blocks:
        size = len(_section_text(title, chunk)) + 1
        if page and used + size > ADMIN_PAGE_BUDGET:
            pages.append(page)
            page, used = [], 0
        page.append((title, chunk))
        used += size
    if page:
        pages.append(page)
    return pages


def page_keys(tree: app_commands.CommandTree, admin: bool) -> dict[str, str]:
    """選單用：頁面 key ➔ 選項標題 (一般分類；管理員再加 admin1、admin2…)"""
    keys = {key: category_info(key)["title"] for key in categorize(tree)}
    if admin:
        n = len(admin_pages(tree))
        for i in range(1, n + 1):
            keys[f"admin{i}"] = "🛠️ 管理員指令表" + (f" ({i} / {n})" if n > 1 else "")
    return keys


# ---------------- 畫面 ----------------
def build_overview_container(categories: dict, admin: bool = False, admin_count: int = 0, on_open=None) -> ui.Container:
    """總覽：每個分類一個 Section (說明 + 右側「查看 ▶」按鈕)；on_open(key) ➔ 按鈕的 callback"""
    c = ui.Container(accent_color=HELP_COLOR)
    c.add_item(ui.TextDisplay("## ⛩️ 幻想鄉指南\n歡迎來到博麗神社！每個分類都有**玩法說明**和**指令**，按「查看 ▶」打開。"))
    c.add_item(ui.Separator())

    def row(key: str, text: str, style=discord.ButtonStyle.secondary):
        btn = ui.Button(label="查看 ▶", style=style)
        if on_open:
            btn.callback = on_open(key)
        c.add_item(ui.Section(ui.TextDisplay(text), accessory=btn))

    for key, cmds in categories.items():
        info = category_info(key)
        row(key, f"**{info['title']}**　`{len(cmds)}` 個指令\n-# {info['short']}")
    if admin:
        c.add_item(ui.Separator())
        row("admin1", f"**🛠️ 管理員指令表**　`{admin_count}` 個指令\n-# 只有管理員打 `/help` 才看得到", discord.ButtonStyle.primary)
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay(f"### 🔰 新手三步驟\n{STEPS}"))
    return c


def build_category_container(key: str, cmds: list, thumbnails: dict | None = None) -> ui.Container:
    """分類頁：標題 (+ 代表卡面) ➔ 📖 怎麼玩 ➔ 📋 指令"""
    info = category_info(key)
    c = ui.Container(accent_color=info["color"])
    head = f"## {info['title']}\n{info['short']}"
    url = thumbnail_url(info["thumb"][0], thumbnails, info["thumb"][1]) if info["thumb"] else None
    c.add_item(ui.Section(ui.TextDisplay(head), accessory=ui.Thumbnail(url)) if url else ui.TextDisplay(head))
    if info["guide"]:
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay("### 📖 怎麼玩\n" + "\n".join(f"- {g}" for g in info["guide"])))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay("### 📋 指令\n" + "\n".join(command_line(cmd) for cmd in cmds)))
    c.add_item(ui.TextDisplay("-# `[ ]` 是可以不填的參數"))
    return c


def build_admin_container(page: list[tuple[str, list]], index: int, total: int) -> ui.Container:
    """🛠️ 管理員指令表的一頁：每個群組一段 (### 標題 + 指令與參數)"""
    c = ui.Container(accent_color=ADMIN_COLOR)
    c.add_item(ui.TextDisplay("## 🛠️ 管理員指令表" + (f"　({index} / {total})" if total > 1 else "")
                              + "\n-# 只有管理員打 `/help` 才看得到這頁；這些指令一般玩家用了會被擋下"))
    for title, cmds in page:
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(_section_text(title, cmds)))
    c.add_item(ui.TextDisplay("-# `[ ]` 是可以不填的參數"))
    return c

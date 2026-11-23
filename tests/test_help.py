"""/help 幻想鄉指南 (不連 Discord)：分類、一般玩家看不到管理員指令、管理員指令表 (分頁)、沒分到類的進「其他」
教學書本身 (格式、每章、翻頁、/xxx help) 在 test_guide.py"""
import asyncio, glob, os, sys, tempfile, importlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord import app_commands
from discord.ext import commands
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)


async def main():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    for path in sorted(glob.glob("Cogs/load-*/*.py")):
        folder, name = os.path.basename(os.path.dirname(path)), os.path.splitext(os.path.basename(path))[0]
        await bot.load_extension(f"Cogs.{folder}.{name}")
    hc = importlib.import_module("Cogs.load-general.Components.help_components")
    help_mod = importlib.import_module("Cogs.load-general.help")

    cats = hc.categorize(bot.tree)
    names = {c.qualified_name for cs in cats.values() for c in cs}
    check("no admin", not any(n.startswith("admin-") for n in names))
    check("no help itself", "help" not in names)
    check("all player commands listed", {"card gacha", "card fusion", "character", "profile", "daily", "leaderboard",
                                         "shrine manage", "shrine storage", "event info", "event quest", "market sell", "trade", "notify"} <= names)
    check("notify in profile", "notify" in {c.name for c in cats["profile"]})
    check("no other yet", "other" not in cats)
    check("shrine has 7", len(cats["shrine"]) == 7)   # 2026-11-23 多了 /shrine job
    check("ura has 7", {c.qualified_name for c in cats.get("ura", [])} == {"ura explore", "ura resume", "ura abandon", "ura shop", "ura inventory", "ura status", "ura bestiary"})

    # 新指令沒分類時出現在「其他」
    @app_commands.command(name="newthing", description="新功能")
    async def newthing(interaction): ...
    bot.tree.add_command(newthing)
    cats = hc.categorize(bot.tree)
    check("unknown goes other", [c.name for c in cats.get("other", [])] == ["newthing"])
    v = help_mod.HelpView(bot, "other")
    check("other page: command list", v.page == "other" and any(
        "`/newthing`" in it.content for it in v.walk_children() if isinstance(it, discord.ui.TextDisplay)))
    check("other row says 查看", any(isinstance(b, discord.ui.Button) and b.label == "查看 ▶"
                                    for b in help_mod.HelpView(bot).walk_children()))
    bot.tree.remove_command("newthing")
    cats = hc.categorize(bot.tree)
    check("group help subcommands not listed", not any(c.name == "help" for cs in cats.values() for c in cs))

    # 畫面：總覽 / 分類頁，元件數不超過 40、文字不超過 4000
    def count(item):
        return 1 + sum(count(ch) for ch in getattr(item, "children", []))
    def text_len(view):
        total = 0
        def walk(it):
            nonlocal total
            if isinstance(it, discord.ui.TextDisplay): total += len(it.content)
            for ch in getattr(it, "children", []): walk(ch)
        for it in view.children: walk(it)
        return total
    def texts(view):
        out = []
        def walk(it):
            if isinstance(it, discord.ui.TextDisplay): out.append(it.content)
            for ch in getattr(it, "children", []): walk(ch)
            if getattr(it, "accessory", None) is not None: walk(it.accessory)
        for it in view.children: walk(it)
        return "\n".join(out)
    def selects(view):
        return [it for it in view.walk_children() if isinstance(it, discord.ui.Select)]

    admin_keys = [k for k in hc.page_keys(bot.tree, True) if k.startswith("admin")]
    check(f"admin pages exist {admin_keys}", admin_keys and admin_keys[0] == "admin1")
    books = help_mod.book_chapter_counts()
    for admin in (False, True):
        for page in ["overview", *[k for k in cats if k not in books], *(admin_keys if admin else [])]:
            v = help_mod.HelpView(bot, page, admin=admin)
            n = sum(count(i) for i in v.children)
            check(f"{page}/{admin} components {n}", n <= 40)
            check(f"{page}/{admin} text {text_len(v)}", text_len(v) <= 4000)
            check(f"{page}/{admin} page kept", v.page == page)
            for sel in selects(v):
                check(f"{page}/{admin} select ≤25", len(sel.options) <= 25)
    v = help_mod.HelpView(bot, "nope")
    check("bad page -> overview", v.page == "overview")

    # 一般玩家：總覽、選單、任何頁面都沒有管理員指令；硬傳 admin 頁回到總覽
    v = help_mod.HelpView(bot)
    check("player overview no admin", "管理員" not in texts(v) and "admin-" not in texts(v))
    for key in cats:
        v = help_mod.GuideView(bot, key) if key in books else help_mod.HelpView(bot, key)
        check(f"player {key} no admin", "admin-" not in texts(v)
              and not any(o.value.startswith("admin") for s in selects(v) for o in s.options))
        if key in books:
            check(f"book key {key} -> overview in HelpView", help_mod.HelpView(bot, key).page == "overview")
    v = help_mod.HelpView(bot, "admin1")
    check("player admin page blocked", v.page == "overview" and "admin-" not in texts(v))
    check("player page_keys no admin", not any(k.startswith("admin") for k in hc.page_keys(bot.tree, False)))

    # 管理員：總覽有管理員指令表、每個 admin- 指令都出現在某一頁
    v = help_mod.HelpView(bot, admin=True)
    check("admin overview has table", "管理員指令表" in texts(v))
    admin_names = {c.qualified_name for cs in hc.walk_commands(bot.tree, admin=True).values() for c in cs}
    check(f"admin commands {len(admin_names)}", len(admin_names) >= 20 and all(n.startswith("admin-") for n in admin_names))
    shown = "\n".join(texts(help_mod.HelpView(bot, k, admin=True)) for k in admin_keys)
    check("every admin command listed", all(f"`/{n}`" in shown for n in admin_names))
    check("dev prefix stripped", "【開發者專用】" not in shown)

    # 總覽的「📖 教學書」按鈕在同一則訊息翻開那本書；管理員那顆「查看 ▶」切到管理員表
    class Resp:
        async def edit_message(self, **kw): self.view = kw.get("view")
    class Inter:
        def __init__(self): self.response = Resp()
    v = help_mod.HelpView(bot, admin=True)
    book_btns = [b for b in v.walk_children() if isinstance(b, discord.ui.Button) and b.label == "📖 教學書"]
    btns = [b for b in v.walk_children() if isinstance(b, discord.ui.Button) and b.label == "查看 ▶"]
    check(f"overview buttons {len(book_btns)} + {len(btns)}", len(book_btns) == len(books) and len(btns) == len(cats) - len(books) + 1)
    it = Inter(); await book_btns[0].callback(it)
    check("book button opens guide", isinstance(it.response.view, help_mod.GuideView) and it.response.view.key == next(iter(books)))
    v = help_mod.HelpView(bot, admin=True)
    btns = [b for b in v.walk_children() if isinstance(b, discord.ui.Button) and b.label == "查看 ▶"]
    await btns[-1].callback(Inter())
    check("last button opens admin table", v.page == "admin1")
    back = next(b for b in v.walk_children() if isinstance(b, discord.ui.Button) and "總覽" in b.label)
    await back.callback(Inter())
    check("back to overview", v.page == "overview")

    # 管理員指令變多 ➔ 自動分頁，每頁 ≤ 4000 字，指令一個都不少
    async def cb(interaction, target: str, amount: int): ...
    for g in ("admin-yyy", "admin-zzz"):   # Discord 一個群組最多 25 個子指令
        big = app_commands.Group(name=g, description="測試用")
        for i in range(20):
            big.add_command(app_commands.Command(name=f"cmd{i:02d}", description="很長的說明" * 6, callback=cb))
        bot.tree.add_command(big)
    pages = hc.admin_pages(bot.tree)
    keys = [k for k in hc.page_keys(bot.tree, True) if k.startswith("admin")]
    check(f"auto paging {len(pages)}", len(pages) >= 2 and len(keys) == len(pages))
    shown = ""
    for k in keys:
        v = help_mod.HelpView(bot, k, admin=True)
        check(f"{k} text {text_len(v)} ≤ 4000", text_len(v) <= 4000 and sum(count(i) for i in v.children) <= 40)
        shown += texts(v)
    check("paged: all listed", all(f"`/{g} cmd{i:02d}`" in shown for g in ("admin-yyy", "admin-zzz") for i in range(20)))
    check("unknown admin group -> other", "其他管理指令" in shown)
    bot.tree.remove_command("admin-yyy")
    bot.tree.remove_command("admin-zzz")


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

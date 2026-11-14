"""/help 指令說明 (不連 Discord)：分類、排除管理員指令、沒分到類的進「其他」"""
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
    check("shrine has 6", len(cats["shrine"]) == 6)

    # 新指令沒分類時出現在「其他」
    @app_commands.command(name="newthing", description="新功能")
    async def newthing(interaction): ...
    bot.tree.add_command(newthing)
    cats = hc.categorize(bot.tree)
    check("unknown goes other", [c.name for c in cats.get("other", [])] == ["newthing"])
    bot.tree.remove_command("newthing")
    cats = hc.categorize(bot.tree)

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
    for page in ["overview", *cats]:
        v = help_mod.HelpView(bot, page)
        n = sum(count(i) for i in v.children)
        check(f"{page} components {n}", n <= 40)
        check(f"{page} text {text_len(v)}", text_len(v) <= 4000)
        check(f"{page} page kept", v.page == page)
    v = help_mod.HelpView(bot, "nope")
    check("bad page -> overview", v.page == "overview")


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

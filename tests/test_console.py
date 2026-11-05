"""主控台指令與模組重載 (不連 Discord)"""
import asyncio, io, os, sys, shutil, tempfile, contextlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
from Utils import console, reloader

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)


async def run(bot, line):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await console.handle_line(bot, line)
    return buf.getvalue()


async def main():
    await udm.init_db()
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.shrine")
    await bot.load_extension("Cogs.load-gacha.gacha")

    out = await run(bot, "help")
    check("help", "reload" in out and "shutdown" in out)
    check("unknown", "沒有「nope」" in await run(bot, "nope"))
    check("version", "v" in await run(bot, "version"))
    out = await run(bot, "modules")
    check("modules lists new files", "Cogs.load-general.shrine" in out and "Cogs.load-market.market" in out)
    check("reload ambiguous", "找不到唯一" in await run(bot, "reload load-"))

    # 重載單一模組：只重載自己資料夾的 Components，不動資料層 (其他 Cog 的例外類別才不會對不上)
    old_exc = udm.InsufficientFunds
    out = await run(bot, "reload shrine")
    check(f"reload one {out!r}", "已重載 Cogs.load-general.shrine" in out)
    check("db untouched on single reload", udm.InsufficientFunds is old_exc)
    gacha = sys.modules["Cogs.load-gacha.gacha"]
    check("other cog consistent", gacha.InsufficientFunds is udm.InsufficientFunds)

    # 全部重載：資料層一起換新，DB_PATH 留在沙盒，新檔案會被載入
    out = await run(bot, "reload all")
    check("reload all loads new", "Cogs.load-market.market" in bot.extensions and "新載入" in out)
    check("db path kept", udm.DB_PATH == os.path.join(tmp, "Users.db"))
    gacha = sys.modules["Cogs.load-gacha.gacha"]
    check("all consistent after reload all", gacha.InsufficientFunds is sys.modules["Database.User_DB_Manager"].InsufficientFunds)

    out = await run(bot, "money 5 2500")
    check("money", "3,500" in out)
    check("money usage", "用法" in await run(bot, "money x"))
    out = await run(bot, "stamina 5 -40")
    check("stamina", "200 / 240" in out)
    await bot.close()

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

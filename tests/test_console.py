"""主控台指令與模組重載 (不連 Discord)"""
import asyncio, io, os, sys, shutil, tempfile, contextlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
os.environ.setdefault("SHOW_UNRELEASED", "1")   # 🙈 測試預設看得到未公開卡池 (Utils/config.py)
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
    old_get_shrine = sys.modules["Database.economy.shrine"].get_shrine
    old_get_user = sys.modules["Database.users.core"].get_or_create_user
    out = await run(bot, "reload all")
    check("reload all loads new", "Cogs.load-market.market" in bot.extensions and "新載入" in out)
    check("db path kept", udm.DB_PATH == os.path.join(tmp, "Users.db"))
    gacha = sys.modules["Cogs.load-gacha.gacha"]
    check("all consistent after reload all", gacha.InsufficientFunds is sys.modules["Database.User_DB_Manager"].InsufficientFunds)

    # 經濟系統拆成 Database/economy/ 套件：子模組照依賴順序先重載，入口 (Economy_DB_Manager) 最後
    econ_names = ["Database.Economy_DB_Manager", "Database.economy.shrine", "Database.economy.market", "Database.economy.gather",
                  "Database.economy.common", "Database.economy", "Database.economy.market_value", "Database.economy.event_state",
                  "Database.User_DB_Manager", "Database.Item_DB_Manager", "Database.Notify_DB_Manager", "Database.events", "Utils.config"]
    ordered = sorted(econ_names, key=reloader._order)
    pos = {n: i for i, n in enumerate(ordered)}
    check("reload order: udm first", ordered[0] == "Database.User_DB_Manager")
    check("reload order: economy parts by dependency",
          pos["Database.economy"] < pos["Database.economy.common"] < pos["Database.economy.event_state"] < pos["Database.economy.shrine"]
          < pos["Database.economy.gather"] < pos["Database.economy.market_value"] < pos["Database.economy.market"] < pos["Database.Economy_DB_Manager"])
    check("reload order: entry before its importers", pos["Database.Economy_DB_Manager"] < pos["Database.Item_DB_Manager"] < pos["Database.Notify_DB_Manager"])
    check("reload order: utils last", ordered[-1] == "Utils.config")
    import pkgutil, Database.economy as econ_pkg
    on_disk = {"Database.economy." + m.name for m in pkgutil.iter_modules(econ_pkg.__path__)}
    check("reload order: every economy part listed", on_disk <= set(reloader.PACKAGE_ORDER["Database.Economy_DB_Manager"]))
    econ = sys.modules["Database.Economy_DB_Manager"]
    check("economy entry lists every part", {m.__name__ for m in econ._PARTS} == on_disk)
    check("reload all reloaded economy parts", econ.get_shrine is not old_get_shrine and all(
        getattr(econ, n) is getattr(sys.modules[f"Database.economy.{p}"], n)
        for p, n in (("shrine", "get_shrine"), ("gather", "explore"), ("market", "buy_listing"), ("event_state", "get_rules"), ("market_value", "settle_prices"))))
    gather, shrine_mod = sys.modules["Database.economy.gather"], sys.modules["Database.economy.shrine"]
    check("parts consistent after reload all", gather._shrine_tx is shrine_mod._shrine_tx and gather.get_rules is econ.get_rules
          and sys.modules["Database.economy.market"]._FEE_MODS is sys.modules["Database.economy.event_state"]._FEE_MODS)
    check("part identity untouched by entry reload", all(m.__name__.startswith("Database.economy.") and m.__spec__.name == m.__name__
                                                         and sys.modules[m.__name__] is m for m in econ._PARTS))
    check("importers see new entry", sys.modules["Database.Notify_DB_Manager"].econ.get_shrine is shrine_mod.get_shrine)

    # 玩家資料庫拆成 Database/users/ 套件：整組排最前面 (其他資料層會從入口匯入)，子模組照依賴順序、入口 (User_DB_Manager) 最後
    user_names = ["Database.User_DB_Manager", "Database.users.cards", "Database.users.titles", "Database.users", "Database.users.core",
                  "Database.users.schema", "Database.Economy_DB_Manager", "Database.economy.common", "Database.Item_DB_Manager", "Utils.config"]
    ordered = sorted(user_names, key=reloader._order)
    pos = {n: i for i, n in enumerate(ordered)}
    check("reload order: users parts by dependency, entry last",
          ordered[:6] == ["Database.users", "Database.users.schema", "Database.users.core", "Database.users.titles",
                          "Database.users.cards", "Database.User_DB_Manager"])
    check("reload order: users before the other data layers",
          pos["Database.User_DB_Manager"] < pos["Database.economy.common"] < pos["Database.Economy_DB_Manager"] < pos["Database.Item_DB_Manager"])
    import Database.users as users_pkg
    on_disk = {"Database.users." + m.name for m in pkgutil.iter_modules(users_pkg.__path__)}
    check("reload order: every users part listed", on_disk <= set(reloader.PACKAGE_ORDER["Database.User_DB_Manager"]))
    check("users entry is the same module object", sys.modules["Database.User_DB_Manager"] is udm)
    check("users entry lists every part", {m.__name__ for m in udm._PARTS} == on_disk)
    check("reload all reloaded users parts", udm.get_or_create_user is not old_get_user and all(
        getattr(udm, n) is getattr(sys.modules[f"Database.users.{p}"], n)
        for p, n in (("schema", "connect"), ("core", "get_or_create_user"), ("core", "tw_day"), ("titles", "get_title_state"),
                     ("cards", "draw_gacha"), ("cards", "InsufficientFunds"))))
    u_schema, u_core, u_titles, u_cards = (sys.modules[f"Database.users.{p}"] for p in ("schema", "core", "titles", "cards"))
    check("users parts consistent after reload all", u_core.connect is u_schema.connect and u_titles.connect is u_schema.connect
          and u_cards.connect is u_schema.connect and u_cards.add_player_stat is u_core.add_player_stat
          and u_cards.get_title_state is u_titles.get_title_state and u_titles.get_or_create_user is u_core.get_or_create_user)
    check("users part identity untouched by entry reload", all(m.__name__.startswith("Database.users.") and m.__spec__.name == m.__name__
                                                              and sys.modules[m.__name__] is m for m in udm._PARTS))
    check("db path kept in schema too", u_schema.DB_PATH == udm.DB_PATH == os.path.join(tmp, "Users.db"))
    check("other data layers see new connect", sys.modules["Database.economy.shrine"].connect is u_schema.connect)
    check("db still usable after reload all", (await udm.get_or_create_user(987654))["money"] == udm.STARTING_MONEY)

    out = await run(bot, "money 5 2500")
    check("money", f"{udm.STARTING_MONEY + 2500:,}" in out)
    check("money usage", "用法" in await run(bot, "money x"))
    out = await run(bot, "stamina 5 -40")
    check("stamina", "200 / 240" in out)
    await bot.close()

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

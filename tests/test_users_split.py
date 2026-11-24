"""📦 User_DB_Manager (入口) 與 Database/users/ 子模組：路徑沒跑掉、改入口的屬性子模組會一起變 (測試 / botcli 都是改入口)"""
import asyncio, os, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
os.environ.setdefault("SHOW_UNRELEASED", "1")   # 🙈 測試預設看得到未公開卡池 (Utils/config.py)
from Database import User_DB_Manager as udm
from Database.users import schema, core, titles, cards

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)


PARTS = (schema, core, titles, cards)
same = lambda a, b: os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))

# 預設路徑：schema.py 搬到 Database/users/ 底下，資料庫還是要在 Database/Users.db (正式環境不會改 DB_PATH，路徑錯了會悄悄開一個空的)
check("default DB_DIR is Database/", same(udm.DB_DIR, os.path.join(ROOT, "Database")) and schema.DB_DIR == udm.DB_DIR)
check("default DB_PATH is Database/Users.db", same(udm.DB_PATH, os.path.join(ROOT, "Database", "Users.db")) and schema.DB_PATH == udm.DB_PATH)
check("legacy path is <root>/database.db", same(udm.LEGACY_DB_PATH, os.path.join(ROOT, "database.db")))

check("entry lists every part", tuple(udm._PARTS) == PARTS)
check("entry re-exports everything", all(getattr(udm, k) is v for p in PARTS for k, v in vars(p).items() if not k.startswith("__")))
check("private / imported names on entry", all(hasattr(udm, n) for n in (
    "_ensure_user", "_load_inventory", "_insert_cards", "_add_draws", "_event_runs", "_sync_oshi_namecards", "_change_stamina",
    "os", "json", "aiosqlite", "datetime", "timedelta", "timezone", "asynccontextmanager", "card_cache", "apply_current_names",
    "collection_stats", "oshi_stats", "TW", "SCHEMA_STATEMENTS", "PLAYER_STATS", "STAMINA_MAX", "InsufficientFunds")))

tmp = tempfile.mkdtemp()


async def main():
    # DB_PATH：改入口 ➔ schema.connect 真的開那個檔 (絕不碰真實 Users.db)
    real = udm.DB_PATH
    udm.DB_PATH = os.path.join(tmp, "Users.db")
    check("DB_PATH forwarded", schema.DB_PATH == udm.DB_PATH and not any(hasattr(p, "DB_PATH") for p in (core, titles, cards)))
    await udm.init_db()
    check("connect opens the patched path", os.path.exists(os.path.join(tmp, "Users.db")))
    user = await udm.get_or_create_user(1)
    check("new player money", user["money"] == udm.STARTING_MONEY == 50_000)

    # 常數：STARTING_MONEY 定義在 schema、_ensure_user 在用
    udm.STARTING_MONEY = 1000
    check("const forwarded", schema.STARTING_MONEY == 1000)
    check("patched const really used", (await udm.get_or_create_user(2))["money"] == 1000)
    udm.STARTING_MONEY = 50_000
    check("const restored", (await udm.get_or_create_user(3))["money"] == 50_000)

    # 另一個檔：其他資料層 from Database.User_DB_Manager import connect 拿到的也是 schema.connect ➔ 一樣跟著 DB_PATH
    udm.DB_PATH = os.path.join(tmp, "Other.db")
    await udm.init_db()
    from Database.economy import shrine
    check("importers share connect", shrine.connect is schema.connect is udm.connect)
    async with shrine.connect() as db:
        async with db.execute("SELECT COUNT(*) AS n FROM users") as cursor:
            check("second db starts empty", (await cursor.fetchone())["n"] == 0 and os.path.exists(os.path.join(tmp, "Other.db")))
    udm.DB_PATH = os.path.join(tmp, "Users.db")
    async with udm.connect() as db:
        async with db.execute("SELECT COUNT(*) AS n FROM users") as cursor:
            check("back on first db", (await cursor.fetchone())["n"] == 3)

    # 函式：get_user_cards 定義在 cards；get_or_create_user 定義在 core、titles 也拿著一份
    orig = udm.get_user_cards
    async def fake(user_id, include_locked=False): return "FAKE"
    udm.get_user_cards = fake
    check("func forwarded", cards.get_user_cards is fake and await udm.get_user_cards(1) == "FAKE")
    udm.get_user_cards = orig
    check("func restored", cards.get_user_cards is orig and udm.get_user_cards is orig)
    orig = udm.get_or_create_user
    udm.get_or_create_user = fake
    check("imported copy forwarded", core.get_or_create_user is fake and titles.get_or_create_user is fake)
    udm.get_or_create_user = orig
    check("imported copy restored", core.get_or_create_user is orig and titles.get_or_create_user is orig)

    # 跨子模組的呼叫照舊：抽卡 (cards) 用 core 的統計 / tw_day、titles 的稱號
    check("tw_day shared", cards.tw_day is core.tw_day is udm.tw_day)
    check("stats shared", cards.add_player_stat is core.add_player_stat and titles.get_player_stats is core.get_player_stats)
    check("exception class shared", udm.InsufficientFunds is cards.InsufficientFunds)
    check("title state works", isinstance(await udm.get_title_state(1), dict))
    check("stamina works", (await udm.get_stamina(1))["stamina"] == udm.STAMINA_MAX)

    # 新名字只留在入口，不會塞進子模組
    udm._test_only = 1
    check("new name stays on entry", not any(hasattr(p, "_test_only") for p in PARTS))
    del udm._test_only
    check("real path untouched", same(real, os.path.join(ROOT, "Database", "Users.db")))

asyncio.run(main())
shutil.rmtree(tmp, ignore_errors=True)
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

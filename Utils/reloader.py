"""
🔄 模組重載 (/admin-sys reload 與主控台的 reload 指令共用)

reload_extension 只會重載 Cog 檔案本身；Components (畫面)、Database、Utils 不重載的話改了看不到。
但 importlib.reload 是「原地」重新執行模組：沒被重載的 Cog 還拿著舊的類別 (例如 InsufficientFunds)，
資料層卻開始丟新的類別 ➔ except 接不到。所以：
- 重載單一模組：只重載它自己資料夾的 Components
- 全部重載：Database、Utils、全部 Components 先重載，再重載全部 Cog (大家一起換新)
"""
import importlib
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {__name__}   # 自己不重載 (正在執行中)


def scan_extensions() -> list[str]:
    """跟 Main.py 一樣：Cogs/load-*/ 第一層的每個 .py 都是一個模組"""
    cogs_dir = os.path.join(PROJECT_ROOT, "Cogs")
    found = []
    for folder in sorted(os.listdir(cogs_dir)):
        path = os.path.join(cogs_dir, folder)
        if os.path.isdir(path) and folder.startswith("load-"):
            for filename in sorted(os.listdir(path)):
                if filename.endswith(".py") and not filename.startswith("__"):
                    found.append(f"Cogs.{folder}.{filename[:-3]}")
    return found


# 拆成套件的資料層：{入口 (舊檔名): [子模組，照依賴順序]}。子模組要先重載、入口最後，
# 不然入口轉出來的還是舊函式；排序時整組排在入口原本的位置
PACKAGE_ORDER = {
    "Database.User_DB_Manager": [
        "Database.users", "Database.users.schema", "Database.users.core", "Database.users.titles", "Database.users.cards",
    ],
    "Database.Economy_DB_Manager": [
        "Database.economy", "Database.economy.common", "Database.economy.event_state", "Database.economy.shrine",
        "Database.economy.gather", "Database.economy.market_value", "Database.economy.market",
    ],
}
_PART_OF = {part: (entry, i) for entry, parts in PACKAGE_ORDER.items() for i, part in enumerate(parts)}
_FIRST = {"Database.User_DB_Manager": 0}     # 其他資料層會從它匯入，要最先 (它的子模組也跟著排最前面)


def _order(name: str):
    if name in _PART_OF:                       # 套件的子模組：排在入口的位置，照依賴順序
        entry, i = _PART_OF[name]
        return (_FIRST.get(entry, 1), entry, i)
    if name in PACKAGE_ORDER:                  # 入口排在自己的子模組後面
        return (_FIRST.get(name, 1), name, len(PACKAGE_ORDER[name]))
    if name.startswith("Database."):
        return (1, name)
    if name.startswith("Utils."):
        return (2, name)
    return (3, name)


def reload_support_modules(extension: str | None = None) -> tuple[list[str], list[str]]:
    """
    extension=None：重載 Database、Utils、全部 Components
    extension="Cogs.load-general.shrine"：只重載 Cogs.load-general.Components.*
    重載時保留 DB_PATH (botcli / 測試會把資料庫指到沙盒)。回傳 (成功, 失敗訊息)
    """
    if extension:
        prefix = extension.rsplit(".", 1)[0] + ".Components."
        names = [m for m in list(sys.modules) if m.startswith(prefix)]
    else:
        names = [m for m in list(sys.modules)
                 if m.startswith(("Database.", "Utils.")) or (m.startswith("Cogs.") and ".Components." in m)]
    ok, failed = [], []
    for name in sorted(names, key=_order):
        module = sys.modules.get(name)
        if name in SKIP or module is None or not getattr(module, "__file__", None):
            continue
        keep = getattr(module, "DB_PATH", None)
        try:
            importlib.reload(module)
            if keep is not None:
                module.DB_PATH = keep
            ok.append(name)
        except Exception as e:
            failed.append(f"{name}: {e}")
    return ok, failed


async def reload_one(bot, extension: str) -> dict:
    """重載單一模組 (含它資料夾的 Components)"""
    support, failed = reload_support_modules(extension)
    try:
        await bot.reload_extension(extension)
    except Exception as e:
        failed.append(f"{extension}: {e}")
    return {"support": support, "reloaded": [extension] if not failed else [], "loaded": [], "unloaded": [], "failed": failed}


async def reload_all(bot, skip: set[str] = frozenset()) -> dict:
    """全部重載：資料層 / 畫面 ➔ 全部 Cog；載入新檔案、卸載檔案已不存在的模組"""
    support, failed = reload_support_modules()
    on_disk = scan_extensions()
    reloaded, loaded, unloaded = [], [], []
    for ext in sorted(bot.extensions.keys()):
        if ext in skip:
            continue
        try:
            if ext.startswith("Cogs.") and ext not in on_disk:
                await bot.unload_extension(ext)
                unloaded.append(ext)
            else:
                await bot.reload_extension(ext)
                reloaded.append(ext)
        except Exception as e:
            failed.append(f"{ext}: {e}")
    for ext in on_disk:
        if ext not in bot.extensions and ext not in skip:
            try:
                await bot.load_extension(ext)
                loaded.append(ext)
            except Exception as e:
                failed.append(f"{ext}: {e}")
    return {"support": support, "reloaded": reloaded, "loaded": loaded, "unloaded": unloaded, "failed": failed}

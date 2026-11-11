"""
💻 主控台指令：機器人跑起來後，可以直接在終端機輸入指令 (不用進 Discord)

讀鍵盤用 daemon 執行緒 (不會卡住關機)，指令丟回機器人的 event loop 執行。
新增指令：在 COMMANDS 加一筆 (名稱: (說明, async 函式(bot, args)))。
"""
import asyncio
import sys
import threading
import time

from Utils import reloader
from Utils.version import VERSION

STARTED_AT = time.time()


def _find_extension(bot, name: str) -> list[str]:
    """模組名稱可以只打一部分，例如 shrine ➔ Cogs.load-general.shrine"""
    exts = sorted(bot.extensions.keys())
    if name in exts:
        return [name]
    return [e for e in exts if name.lower() in e.lower()]


async def cmd_help(bot, args):
    print("💻 主控台指令：")
    for name, (desc, _) in COMMANDS.items():
        print(f"   {name:<10} {desc}")


async def cmd_status(bot, args):
    up = int(time.time() - STARTED_AT)
    latency = f"{bot.latency * 1000:.0f} ms" if bot.latency == bot.latency else "連線中"
    print(f"🤖 {bot.user} · v{VERSION} · 延遲 {latency} · 伺服器 {len(bot.guilds)} 個 · "
          f"模組 {len(bot.extensions)} 個 · 已執行 {up // 3600} 小時 {up % 3600 // 60} 分")


async def cmd_version(bot, args):
    print(f"🏷️ v{VERSION}")


async def cmd_modules(bot, args):
    for ext in sorted(bot.extensions.keys()):
        print(f"   • {ext}")
    new = [e for e in reloader.scan_extensions() if e not in bot.extensions]
    if new:
        print("🆕 還沒載入的新檔案：" + "、".join(new) + "（輸入 reload all 載入）")


async def cmd_reload(bot, args):
    if not args:
        print("用法：reload all ｜ reload <模組名稱，可以只打一部分，例如 shrine>")
        return
    if args[0] == "all":
        r = await reloader.reload_all(bot)
        print(f"🔁 全部重載：畫面 / 資料層 {len(r['support'])} 個、指令模組 {len(r['reloaded'])} 個")
        if r["loaded"]:
            print("🆕 新載入：" + "、".join(r["loaded"]))
        if r["unloaded"]:
            print("📤 已卸載 (檔案不在了)：" + "、".join(r["unloaded"]))
    else:
        found = _find_extension(bot, args[0])
        if len(found) != 1:
            print(f"❌ 找不到唯一的模組「{args[0]}」" + (f"，符合的有：{'、'.join(found)}" if found else ""))
            return
        r = await reloader.reload_one(bot, found[0])
        print(f"🔄 已重載 {found[0]}（畫面 {len(r['support'])} 個）" if r["reloaded"] else f"❌ 重載 {found[0]} 失敗")
    for f in r["failed"]:
        print(f"   ❌ {f}")
    await cmd_sync(bot, [])


async def cmd_sync(bot, args):
    try:
        synced = await bot.tree.sync()
        print(f"⚡ 已同步 {len(synced)} 個斜線指令")
    except Exception as e:
        print(f"❌ 同步失敗：{e}")


async def cmd_money(bot, args):
    from Database.User_DB_Manager import add_money
    if len(args) != 2 or not args[0].isdigit() or not args[1].lstrip("-").isdigit():
        print("用法：money <玩家ID> <數量 (負數 = 扣除)>")
        return
    print(f"💰 玩家 {args[0]} 目前 {await add_money(int(args[0]), int(args[1])):,} 賽錢")


async def cmd_stamina(bot, args):
    from Database.User_DB_Manager import add_stamina
    if len(args) != 2 or not args[0].isdigit() or not args[1].lstrip("-").isdigit():
        print("用法：stamina <玩家ID> <數量 (負數 = 扣除)>")
        return
    r = await add_stamina(int(args[0]), int(args[1]))
    print(f"⚡ 玩家 {args[0]} 目前體力 {r['stamina']} / {r['max']}")


async def cmd_notify(bot, args):
    cog = bot.get_cog("NotifyCog")
    if cog is None:
        print("❌ 通知模組 (notify) 沒有載入")
        return
    r = await cog.run_once()
    print(f"🔔 手動檢查通知：找到 {r['notices']} 則 ➔ 私訊 {r['users']} 位玩家（成功 {r['sent']}、失敗 {r['failed']}）")


async def cmd_shutdown(bot, args):
    print("⚙️ 機器人正在安全關閉中...")
    await bot.close()


COMMANDS = {
    "help": ("顯示這份說明", cmd_help),
    "status": ("連線狀態、延遲、伺服器數、執行時間", cmd_status),
    "version": ("目前版本", cmd_version),
    "modules": ("列出已載入的模組與還沒載入的新檔案", cmd_modules),
    "reload": ("reload all 全部重載 ｜ reload <名稱> 重載單一模組", cmd_reload),
    "sync": ("同步斜線指令到 Discord", cmd_sync),
    "money": ("money <玩家ID> <數量> 調整賽錢", cmd_money),
    "stamina": ("stamina <玩家ID> <數量> 調整體力", cmd_stamina),
    "notify": ("手動檢查一次主動通知並私訊 (平常每 10 分鐘自動跑)", cmd_notify),
    "shutdown": ("安全關閉機器人 (也可以打 exit)", cmd_shutdown),
}
ALIASES = {"exit": "shutdown", "quit": "shutdown", "stop": "shutdown", "?": "help", "ls": "modules"}


async def handle_line(bot, line: str):
    parts = line.strip().split()
    if not parts:
        return
    name = ALIASES.get(parts[0].lower(), parts[0].lower())
    if name not in COMMANDS:
        print(f"❓ 沒有「{parts[0]}」這個指令，輸入 help 看說明")
        return
    try:
        await COMMANDS[name][1](bot, parts[1:])
    except Exception as e:
        print(f"❌ 執行 {name} 時發生錯誤：{e}")


def start_console(bot):
    """在背景開一個讀鍵盤的執行緒；沒有互動式終端機 (例如背景執行) 時不啟動"""
    if not sys.stdin or not sys.stdin.isatty():
        return
    loop = asyncio.get_running_loop()

    def read_loop():
        while True:
            line = sys.stdin.readline()
            if not line:   # EOF
                return
            asyncio.run_coroutine_threadsafe(handle_line(bot, line), loop)

    threading.Thread(target=read_loop, name="console", daemon=True).start()
    print("💻 主控台可以輸入指令了 (輸入 help 看說明)")

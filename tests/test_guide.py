"""📚 教學書 (不連 Discord)：每本書的格式、每個指令都有章節講到、畫面不超過 40 個元件 / 4000 字、翻頁與入口
只檢查某幾本：python tests/test_guide.py ura card"""
import asyncio, glob, os, sys, tempfile, importlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
os.environ.setdefault("SHOW_UNRELEASED", "1")   # 🙈 測試預設看得到未公開卡池 (Utils/config.py)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)


def count(item):
    return 1 + sum(count(ch) for ch in getattr(item, "children", [])) + (1 if getattr(item, "accessory", None) is not None else 0)

def walk_items(view):
    out = []
    def walk(it):
        out.append(it)
        for ch in getattr(it, "children", []): walk(ch)
        if getattr(it, "accessory", None) is not None: walk(it.accessory)
    for it in view.children: walk(it)
    return out

def texts(view):
    return "\n".join(it.content for it in walk_items(view) if isinstance(it, discord.ui.TextDisplay))

def buttons(view):
    return [it for it in walk_items(view) if isinstance(it, discord.ui.Button)]

def selects(view):
    return [it for it in walk_items(view) if isinstance(it, discord.ui.Select)]

def components(view):
    return sum(count(i) for i in view.children)


class Resp:
    def __init__(self): self.view = None; self.ephemeral = None
    async def edit_message(self, **kw): self.view = kw.get("view")
    async def send_message(self, **kw): self.view = kw.get("view"); self.ephemeral = kw.get("ephemeral")

class Inter:
    def __init__(self, bot, values=None, uid=1):
        self.response = Resp(); self.client = bot
        self.user = type("U", (), {"id": uid, "display_name": "測試"})()
        self.data = {"values": values or []}


async def main():
    only = set(sys.argv[1:])
    await udm.init_db()
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    for path in sorted(glob.glob("Cogs/load-*/*.py")):
        folder, name = os.path.basename(os.path.dirname(path)), os.path.splitext(os.path.basename(path))[0]
        await bot.load_extension(f"Cogs.{folder}.{name}")
    hc = importlib.import_module("Cogs.load-general.Components.help_components")
    gc = importlib.import_module("Cogs.load-general.Components.guide_components")
    help_mod = importlib.import_module("Cogs.load-general.help")
    cats = hc.categorize(bot.tree)

    check("every category has a book key", set(hc.CATEGORIES) == set(gc.BOOK_KEYS))
    for key in gc.BOOK_KEYS:
        if only and key not in only:
            continue
        book = gc.load_book(key)
        check(f"{key}: book exists", isinstance(book, dict))
        if not isinstance(book, dict):
            continue
        check(f"{key}: intro", isinstance(book.get("intro"), str) and 0 < len(book["intro"]) <= 300)
        chs = book.get("chapters", [])
        check(f"{key}: chapters {len(chs)}", 1 <= len(chs) <= 15)
        cmd_names = {c.qualified_name for c in cats.get(key, [])}
        covered = set()
        for i, ch in enumerate(chs, 1):
            tag = f"{key} ch{i} {ch.get('title')}"
            check(f"{tag}: keys", set(ch) <= {"title", "short", "body", "commands"} and {"title", "short", "body", "commands"} <= set(ch))
            check(f"{tag}: title", isinstance(ch.get("title"), str) and 2 <= len(ch["title"]) <= 30 and not ch["title"][0].isascii())
            check(f"{tag}: short", isinstance(ch.get("short"), str) and 0 < len(ch["short"]) <= 90)
            try:
                body = gc.body_text(ch)
            except Exception as e:   # 從程式讀數字的函式壞掉
                check(f"{tag}: body renders ({e!r})", False)
                continue
            check(f"{tag}: body length {len(body)}", 50 <= len(body) <= 3200)
            check(f"{tag}: no admin", "admin-" not in body)
            check(f"{tag}: no leftover braces", "{" not in body and "}" not in body and "None" not in body)
            for n in ch.get("commands", []):
                check(f"{tag}: command /{n} exists in {key}", n in cmd_names)
                covered.add(n)
        check(f"{key}: every command has a chapter {sorted(cmd_names - covered)}", cmd_names <= covered)

        # 畫面：目錄 + 每一章，元件 ≤ 40、文字 ≤ 4000、選單 ≤ 25
        total = len(gc.chapters(book))
        for page in range(0, total + 1):
            for from_help in (True, False):
                v = help_mod.GuideView(bot, key, page, from_help=from_help)
                n, t = components(v), len(texts(v))
                check(f"{key} page {page}: components {n}", n <= 40)
                check(f"{key} page {page}: text {t}", t <= 4000)
                check(f"{key} page {page}: kept", v.chapter == page)
                for s in selects(v):
                    check(f"{key} page {page}: select ≤25", len(s.options) <= 25)
                home = [b for b in buttons(v) if b.label in ("🏠 回到總覽", "⛩️ 其他模式")]
                check(f"{key} page {page}: home button", len(home) == 1 and home[0].label == ("🏠 回到總覽" if from_help else "⛩️ 其他模式"))
        v = help_mod.GuideView(bot, key, total)
        check(f"{key}: quickref lists all", all(f"`/{n}`" in texts(v) for n in cmd_names))
        cover = help_mod.GuideView(bot, key, 0)
        chapter_btns = [b for b in buttons(cover) if b.label in [c["title"] for c in gc.chapters(book)]]
        check(f"{key}: cover has a button per chapter", len(chapter_btns) == total)

    # 🎪 開書時讀進行中的活動 (0.37.005)：不寫死某個活動；沒有活動 / 紅霧異變 / 換成別的活動，三種都要對
    events_mod = importlib.import_module("Database.events")
    scarlet = events_mod.load_events()["th06_scarlet_mist"]
    other = {"id": "test_spring", "name": "測試春雪", "emoji": "🌸", "event_dish_bonus": 1.5,
             "location": {"id": "test_loc", "name": "測試花園", "emoji": "🌷", "drops": []}}
    ctxs = {"none": {"active": [], "rules": events_mod.game_rules([])},
            "scarlet": {"active": [scarlet], "rules": events_mod.game_rules([scarlet])},
            "other": {"active": [other], "rules": events_mod.game_rules([])}}
    for name, ctx in ctxs.items():
        for key in gc.BOOK_KEYS:
            book = gc.load_book(key)
            if not book or (only and key not in only):
                continue
            for i, ch in enumerate(book["chapters"], 1):
                body = gc.body_text(ch, ctx)
                check(f"ctx {name} {key} ch{i}: renders", 50 <= len(body) <= 3200 and "{" not in body and "None" not in body)
                v = help_mod.GuideView(bot, key, i, ctx=ctx)
                check(f"ctx {name} {key} ch{i}: page ok", len(texts(v)) <= 4000 and components(v) <= 40)
    if not only or "event" in only:
        ev_text = lambda ctx: "\n".join(gc.body_text(ch, ctx) for ch in gc.load_book("event")["chapters"])
        check("event book: no fixed example when nothing active", "紅霧異變" not in ev_text(ctxs["none"]) and "現在沒有進行中的活動" in ev_text(ctxs["none"]))
        check("event book: lists the active event", "紅霧異變" in ev_text(ctxs["scarlet"]) and "紅霧異變的解決者" in ev_text(ctxs["scarlet"]))
        check("event book: other event, not scarlet", "測試春雪" in ev_text(ctxs["other"]) and "紅霧異變" not in ev_text(ctxs["other"]))
    if not only or "card" in only:
        pull = gc.load_book("card")["chapters"][0]
        check("card: event pool now (scarlet)", "現在的活動限定卡池" in gc.body_text(pull, ctxs["scarlet"]) and "現在開放中" in gc.body_text(pull, ctxs["scarlet"]))
        check("card: no event pool", "現在沒有開放活動限定卡池" in gc.body_text(pull, ctxs["none"]) and "現在開放中" not in gc.body_text(pull, ctxs["none"]))
        check("card: no fixed 紅霧 example in the 🎪 line", "例如紅霧異變" not in gc.body_text(pull, ctxs["none"]))
    if not only or "ura" in only:
        fest = next(ch for ch in gc.load_book("ura")["chapters"] if ch["title"] == "🎪 活動關卡")
        check("ura fest: none", "紅霧" not in gc.body_text(fest, ctxs["none"]) and "現在沒有裏世界內容的活動" in gc.body_text(fest, ctxs["none"]))
        check("ura fest: scarlet", "🟢 現在 🔴 紅霧異變" in gc.body_text(fest, ctxs["scarlet"]))
    live = await gc.current_context()
    check(f"current_context reads the DB ({live and [e['id'] for e in live['active']]})",
          live is not None and "th06_scarlet_mist" in [e["id"] for e in live["active"]])   # 紅霧異變 auto_start、沒有紀錄 = 進行中

    # 翻頁：目錄 ➔ 第 1 章 ➔ 下一章 ➔ 上一章 ➔ 跳章 ➔ 目錄 ➔ 回總覽
    key = next(k for k in gc.BOOK_KEYS if gc.load_book(k) and (not only or k in only))
    book = gc.load_book(key)
    v = help_mod.GuideView(bot, key, from_help=True)
    first = next(b for b in buttons(v) if b.label == book["chapters"][0]["title"])
    it = Inter(bot); await first.callback(it)
    check("cover button opens ch1", it.response.view is v and v.chapter == 1)
    prev = next(b for b in buttons(v) if b.label == "◀ 上一章")
    check("ch1 prev disabled", prev.disabled)
    nxt = next(b for b in buttons(v) if b.label == "下一章 ▶")
    await nxt.callback(Inter(bot)); check("next", v.chapter == 2)
    prev = next(b for b in buttons(v) if b.label == "◀ 上一章")
    await prev.callback(Inter(bot)); check("prev", v.chapter == 1)
    last = len(gc.chapters(book))
    await v.on_jump(Inter(bot, [str(last)])); check("jump to last", v.chapter == last)
    check("last next disabled", next(b for b in buttons(v) if b.label == "下一章 ▶").disabled)
    toc = next(b for b in buttons(v) if b.label == "📚 目錄")
    await toc.callback(Inter(bot)); check("toc", v.chapter == 0)
    home = next(b for b in buttons(v) if b.label == "🏠 回到總覽")
    it = Inter(bot); await home.callback(it)
    check("home -> help overview", isinstance(it.response.view, help_mod.HelpView) and it.response.view.page == "overview")

    # /help 總覽的「📖 教學書」在同一則訊息翻開那本書
    hv = help_mod.HelpView(bot)
    book_btns = [b for b in buttons(hv) if b.label == "📖 教學書"]
    check(f"overview book buttons {len(book_btns)}", len(book_btns) == len(help_mod.book_chapter_counts()))
    it = Inter(bot); await book_btns[0].callback(it)
    check("overview opens book", isinstance(it.response.view, help_mod.GuideView) and it.response.view.from_help
          and it.response.view.chapter == 0 and it.response.view.ctx is not None)

    # /card help、/ura help…：另開一則只有自己看得到的目錄頁；🪪 資料卡沒有 /profile help
    groups = {"card": "card", "shrine": "shrine", "ura": "ura", "market": "market", "event": "event"}
    for group, key in groups.items():
        cmd = bot.tree.get_command(group).get_command("help")
        check(f"/{group} help exists", cmd is not None)
        if cmd is None or (only and key not in only) or not gc.load_book(key):
            continue
        it = Inter(bot)
        await cmd.callback(cmd.binding, it)
        gv = it.response.view
        check(f"/{group} help opens book", isinstance(gv, help_mod.GuideView) and gv.key == key and not gv.from_help
              and it.response.ephemeral)
        check(f"/{group} help read the live events", gv.ctx is not None and "active" in gv.ctx)
        check(f"/{group} help not listed as chapter command", f"{group} help" not in {c.qualified_name for c in cats[key]})
    check("no /profile help", not hasattr(bot.tree.get_command("profile"), "get_command"))


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

import asyncio, os, sys, json, shutil, tempfile, importlib, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from Utils import character_data as cd
from Database import User_DB_Manager as udm
TMPDB = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(TMPDB, 'Users.db')

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

class Resp:
    def __init__(s, it): s.it = it; s.done = False
    def is_done(s): return s.done
    async def send_message(s, content=None, **kw):
        assert content is None and "embed" not in kw; s.done = True; s.it.view = kw.get("view"); s.it.kw = kw
    async def edit_message(s, content=None, **kw):
        assert content is None; s.done = True; s.it.view = kw.get("view")
class Interaction:
    def __init__(s, data=None):
        s.user = types.SimpleNamespace(id=1, display_name="t"); s.response = Resp(s); s.data = data or {}; s.view = None
    async def original_response(s): return None

def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def count(v): return sum(1 for _ in v.walk_children())
def thumbs(v): return [i.media.url for i in v.walk_children() if isinstance(i, discord.ui.Thumbnail)]

async def main():
    await udm.init_db()
    p = {'name': '博麗靈夢', 'emoji': '☯️'}
    await udm.add_gacha_cards(1, [dict(instance_id=f'c_x_{i}', character_key='reimu', name='博麗靈夢', emoji='☯️', rarity='SR', title='t', completeness=0.5, obtained_at='x') for i in range(3)])
    cats = cd.load_categories()
    check(f"categories order {list(cats)}", list(cats) == ["Main", "TH01", "TH02", "TH03", "TH04", "TH05", "TH06"])
    check("24 chars", sum(len(c["characters"]) for c in cats.values()) == 24)

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-character.character")
    cog = bot.get_cog("CharacterProfileCog")
    cmd = next(c for c in cog.walk_app_commands() if c.name == "character")
    mod = sys.modules["Cogs.load-character.character"]

    it = Interaction(); await cmd.callback(cog, it)
    view = it.view
    check("home", "角色圖鑑資料庫" in texts(view) and "24 位角色" in texts(view) and "`1 / 24`" in texts(view))
    fill = json.load(open("images/Thumbnails.json", encoding="utf-8"))["fill"]
    max_count = 0
    for key, cat in cats.items():
        i2 = Interaction(data={"values": [key]}); await view.on_category(i2)
        check(f"category {key}", cat["category_name"] in texts(i2.view))
        max_count = max(max_count, count(i2.view))
        for ch in cat["characters"]:
            i3 = Interaction(data={"values": [ch["id"]]}); await view.on_character(i3)
            t = texts(i3.view)
            ok_page = (ch["name"] in t and ch["special_powers"]["name"] in t
                       and all(lv["name"] in t for lv in ch["special_powers"]["levels"].values())
                       and "HP `0`" in t and "B 點 `0`" in t and "威力" not in t and thumbs(i3.view) == [fill]
                       and ch["special_powers"]["name"] != ch["profile"]["ability"]
                       and all(set(lv) == {"id", "name", "type", "spent", "cooldown", "desc"}
                               and lv["name"].endswith("・" + ch["special_powers"]["name"])
                               for lv in ch["special_powers"]["levels"].values()))
            check(f"page {ch['id']}", ok_page)
            max_count = max(max_count, count(i3.view))
    check(f"component count {max_count}", max_count <= 40)
    await view.on_category(Interaction(data={"values": ["Main"]}))
    check("category owned", "`1 / 2`" in texts(view) and "✅ ☯️" in texts(view))
    await view.on_character(Interaction(data={"values": ["reimu"]}))
    check("char owned", "✅ ×3" in texts(view) and "▫️ 未擁有" in texts(view))
    i4 = Interaction(data={"values": ["nope"]}); await view.on_character(i4)
    check("bad char notice", "找不到該角色" in texts(i4.view))

    # 縮圖：有專屬圖用專屬圖、沒有 Thumbnails.json 只顯示文字
    v2 = mod.CharacterBrowserView(cats, {"reimu": "https://x/reimu.png", "fill": fill})
    v2.category_key, v2.char_id = "Main", "reimu"; v2.build()
    check("own thumbnail", thumbs(v2) == ["https://x/reimu.png"])
    v3 = mod.CharacterBrowserView(cats, {}); v3.category_key, v3.char_id = "Main", "reimu"; v3.build()
    check("no thumbnail", thumbs(v3) == [] and "博麗靈夢" in texts(v3))

    # 壞檔略過
    tmp = tempfile.mkdtemp()
    shutil.copytree("Characters", os.path.join(tmp, "Characters"))
    open(os.path.join(tmp, "Characters", "TH06", "broken.json"), "w", encoding="utf-8").write("{")
    d = json.load(open("Characters/TH06/cirno.json", encoding="utf-8")); d["id"] = "other"
    json.dump(d, open(os.path.join(tmp, "Characters", "TH06", "cirno.json"), "w", encoding="utf-8"), ensure_ascii=False)
    os.makedirs(os.path.join(tmp, "Characters", "TH99"))
    old = cd.CHARACTERS_DIR; cd.CHARACTERS_DIR = os.path.join(tmp, "Characters")
    c2 = cd.load_categories(); cd.CHARACTERS_DIR = old
    check("bad files skipped", len(c2["TH06"]["characters"]) == 8 and "TH99" not in c2)
    shutil.rmtree(tmp, ignore_errors=True)

asyncio.run(main())
print(f"passed {ok}, failed {fail}")

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
    real_thumbs = json.load(open("images/Thumbnails.json", encoding="utf-8"))
    fill = real_thumbs["fill"]
    # 測試玩家只有 3 張靈夢 SR：每頁的卡面 = 該角色擁有的最高階級，沒有就最低階級，沒有圖就 fill
    def expect_thumb(ch):
        rarity = "SR" if ch["id"] == "reimu" else ch["gacha"]["rarities"][0]
        return real_thumbs.get(f"{ch['id']}_{rarity}") or real_thumbs.get(ch["id"]) or fill
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
                       and "HP `0`" in t and "B 點 `0`" in t and "威力" not in t and thumbs(i3.view) == [expect_thumb(ch)]
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

    # 依階級的卡面：有收藏用擁有的最高階級、沒有收藏用最低階級、該階級沒圖退回角色圖 / fill
    by_rarity = {"reimu_SR": "https://x/reimu_SR.png", "reimu_UR": "https://x/reimu_UR.png", "fill": fill}
    v4 = mod.CharacterBrowserView(cats, by_rarity, {"reimu": {"SR": 2, "UR": 1}}); v4.category_key, v4.char_id = "Main", "reimu"; v4.build()
    check("thumbnail top owned rarity", thumbs(v4) == ["https://x/reimu_UR.png"])
    v5 = mod.CharacterBrowserView(cats, by_rarity, {}); v5.category_key, v5.char_id = "Main", "reimu"; v5.build()
    check("thumbnail lowest rarity", thumbs(v5) == ["https://x/reimu_SR.png"])
    v6 = mod.CharacterBrowserView(cats, by_rarity, {"reimu": {"SSR": 1}}); v6.category_key, v6.char_id = "Main", "reimu"; v6.build()
    check("thumbnail rarity fallback", thumbs(v6) == [fill])

    gc = importlib.import_module("Cogs.load-gacha.Components.gacha_components")
    check("card thumbnail by rarity", gc.get_thumbnail_url("reimu", by_rarity, "UR") == "https://x/reimu_UR.png")
    check("card thumbnail fallback", gc.get_thumbnail_url("reimu", by_rarity, "SSR") == fill
          and gc.get_thumbnail_url("reimu", {"reimu": "https://x/r.png", "fill": fill}, "UR") == "https://x/r.png"
          and gc.get_thumbnail_url("reimu", None, "UR") is None)
    card = dict(instance_id="c_x_9", character_key="reimu", name="博麗靈夢", emoji="☯️", rarity="UR", title="t", completeness=0.5, obtained_at="x")
    check("card detail uses rarity art", [i.media.url for i in gc.build_card_detail_container(card, "t", by_rarity).walk_children()
                                          if isinstance(i, discord.ui.Thumbnail)] == ["https://x/reimu_UR.png"])

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

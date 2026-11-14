"""📥 名片原圖下載：原圖在私人頻道 (NamecardOriginals.json 記訊息 id)，/profile「📥 下載名片原圖」私訊本人、/admin-user namecard「📥 原檔」私訊管理員"""
import asyncio, os, sys, tempfile, types, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from discord import app_commands
from Database import User_DB_Manager as udm
from Database import Item_DB_Manager as idm
from Utils import namecards as nc
from Utils import config

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")   # 絕不碰真實 Users.db
idm.DB_PATH = os.path.join(tmp, "Item.db")
nc.NAMECARDS_FILE = os.path.join(tmp, "Namecards.json")
nc.ORIGINALS_FILE = os.path.join(tmp, "NamecardOriginals.json")
os.environ["NAMECARD_CHANNEL_ID"] = "555"
config.ADMIN_IDS = config.ADMIN_IDS | {900}

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

# --- 假的私人頻道 / 訊息 / 附件 ---
class Attachment:
    def __init__(s, filename): s.filename = filename
    async def to_file(s): return discord.File(fp=__import__("io").BytesIO(b"img"), filename=s.filename)
class Channel:
    def __init__(s): s.fetched = []
    async def fetch_message(s, mid):
        s.fetched.append(mid)
        if mid != 42: raise discord.NotFound(types.SimpleNamespace(status=404, reason="x"), "gone")
        return types.SimpleNamespace(attachments=[Attachment("reimu_full.jpg"), Attachment("reimu.png")])
CHANNEL = Channel()
class Client:
    def get_channel(s, cid): return CHANNEL if cid == 555 else None
    async def fetch_channel(s, cid): raise discord.NotFound(types.SimpleNamespace(status=404, reason="x"), "no")

class Resp:
    def __init__(s, it): s.it = it; s.done = False
    def is_done(s): return s.done
    async def defer(s, **kw): s.done = True
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
    async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw):
        assert content is None; s.it.views.append(kw.get("view"))
        if s.it.view is None: s.it.view = kw.get("view")
avatar = types.SimpleNamespace(with_size=lambda n: types.SimpleNamespace(url="https://x/a.png"))
class User:
    def __init__(s, uid, dm_ok=True): s.id = uid; s.display_name = "t"; s.display_avatar = avatar; s.mention = "@t"; s.dms = []; s.dm_ok = dm_ok
    async def send(s, content=None, **kw):
        assert content is None
        if not s.dm_ok: raise discord.Forbidden(types.SimpleNamespace(status=403, reason="x"), "closed")
        s.dms.append(kw)
class Interaction:
    def __init__(s, user, data=None):
        s.user = user; s.client = Client()
        s.response = Resp(s); s.followup = Followup(s); s.view = None; s.views = []; s.data = data or {}
        s.type = discord.InteractionType.application_command
    async def original_response(s): return None
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def buttons(v): return {i.label: i for i in v.walk_children() if isinstance(i, discord.ui.Button)}
def files(v): return [i for i in v.walk_children() if isinstance(i, discord.ui.File)]


async def main():
    await udm.init_db()
    U = 1
    me = User(U)
    await udm.grant_namecard(U, "reimu", "admin")
    await udm.set_equipped_namecard(U, "reimu")

    # 沒有原圖紀錄 ➔ 沒有下載按鈕
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.profile")
    cog = bot.get_cog("Profile")
    cmds = {c.name: c for c in cog.walk_app_commands()}
    it = Interaction(me); await cmds["profile"].callback(cog, it, None, None)
    check("no download without original", "📥 下載名片原圖" not in buttons(it.view))
    check("namecard_original none", nc.namecard_original("reimu") is None)

    with open(nc.ORIGINALS_FILE, "w", encoding="utf-8") as f:
        json.dump({"reimu": {"message_id": 42, "jpg": "reimu_full.jpg", "full": "reimu.png"},
                   "cirno": {"message_id": 99, "jpg": "cirno_full.jpg", "full": None}}, f)

    # 有原圖 ➔ 本人卡有按鈕，按了私訊 JPG
    it = Interaction(me); await cmds["profile"].callback(cog, it, None, None)
    pv = it.view
    check("download button", "📥 下載名片原圖" in buttons(pv))
    i2 = Interaction(me); await pv.on_download_namecard(i2)
    check("dm sent", len(me.dms) == 1 and me.dms[0]["file"].filename == "reimu_full.jpg")
    dm_view = me.dms[0]["view"]
    check("dm v2 with file", files(dm_view) and files(dm_view)[0].media.url == "attachment://reimu_full.jpg"
          and "名片原圖" in texts(dm_view))
    check("dm notice", any("私訊給你" in texts(v) for v in i2.views))

    # 別人看我的卡 ➔ 沒有按鈕
    other = User(2)
    it = Interaction(other); await cmds["profile"].callback(cog, it, me, None)
    check("others no download", "📥 下載名片原圖" not in buttons(it.view))

    # 私訊關著
    closed = User(U, dm_ok=False)
    i3 = Interaction(closed); await pv.on_download_namecard(i3)
    check("dm closed notice", any("沒辦法私訊你" in texts(v) for v in i3.views))

    # 換成沒戴名片 ➔ 按鈕舊畫面還在也擋下
    await udm.set_equipped_namecard(U, None)
    i4 = Interaction(me); await pv.on_download_namecard(i4)
    check("not equipped blocked", any("沒有戴名片" in texts(v) for v in i4.views) and len(me.dms) == 1)

    # 訊息被刪 ➔ 原圖還沒準備好
    await udm.grant_namecard(U, "cirno", "admin"); await udm.set_equipped_namecard(U, "cirno")
    i5 = Interaction(me); await pv.on_download_namecard(i5)
    check("missing message", any("還沒準備好" in texts(v) for v in i5.views))

    # 頻道沒設定 ➔ None
    os.environ["NAMECARD_CHANNEL_ID"] = ""
    check("no channel", await nc.fetch_original_file(Client(), "reimu") is None)
    os.environ["NAMECARD_CHANNEL_ID"] = "555"

    # 🛠️ /admin-user namecard「📥 原檔」：私訊 PNG 給管理員本人
    await bot.load_extension("Cogs.load-general.Admin-user")
    acog = bot.get_cog("UserAdmin")
    acog.bot = Client()   # fetch_original_file 用 self.bot 抓頻道
    cmd = next(c for c in acog.walk_app_commands() if c.name == "namecard")
    act = lambda v: app_commands.Choice(name=v, value=v)
    admin = User(900)
    ia = Interaction(admin); await cmd.callback(acog, ia, act("full"), "reimu", None)
    check("admin full png", len(admin.dms) == 1 and admin.dms[0]["file"].filename == "reimu.png"
          and "原檔" in texts(admin.dms[0]["view"]))
    ia = Interaction(admin); await cmd.callback(acog, ia, act("full"), "亂打", None)
    check("admin bad character", "找不到這位角色" in texts(ia.view))
    ia = Interaction(User(5)); await cmd.callback(acog, ia, act("full"), "reimu", None)
    check("non-admin blocked", "無權限" in texts(ia.view))

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

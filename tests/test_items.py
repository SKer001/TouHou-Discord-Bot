import asyncio, os, sys, shutil, tempfile, types, json, sqlite3
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm
from Database import Item_DB_Manager as idm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
idm.DB_PATH = os.path.join(tmp, "Item.db")   # 空白道具庫 ➔ 會寫入 DEFAULT_ITEMS

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

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
        return None
avatar = types.SimpleNamespace(with_size=lambda n: types.SimpleNamespace(url="https://x/a.png", read=None))
class Interaction:
    def __init__(s, uid=1, data=None):
        s.user = types.SimpleNamespace(id=uid, display_name="t", display_avatar=avatar, mention="@t")
        s.response = Resp(s); s.followup = Followup(s); s.view = None; s.views = []; s.data = data or {}
        s.type = discord.InteractionType.application_command
    async def original_response(s): return None
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def buttons(v): return {i.label: i for i in v.walk_children() if isinstance(i, discord.ui.Button)}

async def main():
    await udm.init_db()
    # 預設道具 = 4 個體力道具
    items = await idm.get_all_items()
    check(f"default items {list(items)}", set(items) == {"yuyuko_dango", "sakuya_scone_tea", "marisa_mushroom_soup", "reimu_onigiri"})
    check("effects", [items[k]["effect"]["stamina"] for k in ("yuyuko_dango", "sakuya_scone_tea", "marisa_mushroom_soup", "reimu_onigiri")] == [120, 120, 67, 60])
    check("daily reward item exists", idm.DAILY_REWARD_ITEM[0] in items)

    # 舊版 Item.db (沒有 effect 欄位) 會自動補欄位
    old = os.path.join(tmp, "old_item.db")
    with sqlite3.connect(old) as c:
        c.execute("CREATE TABLE item_templates (item_id TEXT PRIMARY KEY, name TEXT, emoji TEXT, category TEXT, description TEXT)")
        c.execute("INSERT INTO item_templates VALUES ('apple', '蘋果', '🍎', 'consumable', 'x')")
    idm.DB_PATH = old
    it = await idm.get_item("apple")
    check("old db migrated", it and it["effect"] == {})
    await idm.replace_all_items(idm.DEFAULT_ITEMS)
    check("replace all", set(await idm.get_all_items()) == set(items))
    idm.DB_PATH = os.path.join(tmp, "Item.db")

    # 批次匯入帶 effect
    s, k = await idm.batch_import_db({"test_tea": {"name": "測試茶", "emoji": "🍵", "category": "consumable", "desc": "d", "effect": {"stamina": 5}}}, False)
    check("batch import effect", s == 1 and (await idm.get_item("test_tea"))["effect"] == {"stamina": 5})
    await idm.delete_item_db("test_tea")

    # add_item 併發不遺失
    await asyncio.gather(*[udm.add_item(1, "reimu_onigiri", 1) for _ in range(30)])
    check("add_item concurrent", (await udm.get_or_create_user(1))["inventory"]["reimu_onigiri"] == 30)
    await udm.add_item(1, "reimu_onigiri", -30)
    check("add_item remove key", "reimu_onigiri" not in (await udm.get_or_create_user(1))["inventory"])

    # use_stamina_item
    r = await udm.use_stamina_item(2, "yuyuko_dango", 120)
    check("use without item", not r["ok"] and r["stamina"] == 240)
    await udm.add_item(2, "yuyuko_dango", 1)
    await udm.spend_stamina(2, 200)
    r = await udm.use_stamina_item(2, "yuyuko_dango", 120)
    check(f"use ok {r}", r["ok"] and r["before"] == 40 and r["stamina"] == 160 and r["left"] == 0)
    check("item removed", "yuyuko_dango" not in (await udm.get_or_create_user(2))["inventory"])
    await udm.add_item(2, "sakuya_scone_tea", 1)
    rs = await asyncio.gather(*[udm.use_stamina_item(2, "sakuya_scone_tea", 120) for _ in range(5)])
    check("concurrent last item once", sum(x["ok"] for x in rs) == 1 and (await udm.get_stamina(2))["stamina"] == 280)

    # 清空所有背包
    await udm.add_item(3, "reimu_onigiri", 2)
    n = await udm.clear_all_inventories()
    check(f"clear all {n}", n >= 1 and (await udm.get_or_create_user(3))["inventory"] == {})

    # 簽到送飯糰 + 資料卡恢復體力流程
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.profile")
    cog = bot.get_cog("Profile")
    cmds = {c.name: c for c in cog.walk_app_commands()}
    it = Interaction(uid=10); await cmds["daily"].callback(cog, it)
    check("daily gives onigiri", (await udm.get_or_create_user(10))["inventory"].get("reimu_onigiri") == 1 and any("陰陽梅干飯糰" in texts(v) for v in it.views))
    await udm.add_stamina(10, -100)
    it = Interaction(uid=10); await cmds["profile"].callback(cog, it, None, None)
    pv = it.view
    check("profile stamina button", "⚡ 恢復體力" in buttons(pv))
    i2 = Interaction(uid=10); await buttons(pv)["⚡ 恢復體力"].callback(i2)
    sv = i2.view
    check("stamina view", "陰陽梅干飯糰" in texts(sv) and "`140 / 240`" in texts(sv))
    check("others blocked", await sv.interaction_check(Interaction(uid=99)) is False)
    await sv.on_select(Interaction(uid=10, data={"values": ["reimu_onigiri"]}))
    check("preview", "`140` ➔ `200`" in texts(sv))
    i3 = Interaction(uid=10); await sv.on_use(i3)
    check("used", "`140` ➔ `200`" in texts(sv) and "剩下 `0` 個" in texts(sv) and "沒有任何體力道具" in texts(sv))
    i4 = Interaction(uid=10); await sv.on_back(i4)
    check("back to profile", i4.view is pv and "`200 / 240`" in texts(pv))
    # 別人的資料卡沒有恢復體力按鈕
    it = Interaction(uid=11); await cmds["profile"].callback(cog, it, types.SimpleNamespace(id=10, display_name="t", display_avatar=avatar), None)
    check("no button on others", "⚡ 恢復體力" not in buttons(it.view))

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

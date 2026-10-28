import asyncio, os, sys, shutil, tempfile, importlib, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm
from Database import Item_DB_Manager as idm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
shutil.copy(idm.DB_PATH, os.path.join(tmp, "Item.db"))   # 道具資料庫用副本，絕不改動原檔
idm.DB_PATH = os.path.join(tmp, "Item.db")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else:
        fail += 1; print("FAIL:", name)

ADMIN = 403895664666214400

class Resp:
    def __init__(s, it): s.it = it; s.done = False; s.sent = []
    def is_done(s): return s.done
    async def send_message(s, content=None, **kw):
        assert not s.done; s.done = True
        assert content is None and "embed" not in kw and "embeds" not in kw, "非 V2 訊息"
        s.sent.append(kw); s.it.view = kw.get("view")
    async def defer(s, **kw): s.done = True
    async def edit_message(s, content=None, **kw):
        assert content is None and "embed" not in kw, "非 V2 編輯"
        s.done = True; s.it.view = kw.get("view")
    async def send_modal(s, modal): s.done = True; s.it.modal = modal

class Followup:
    def __init__(s, it): s.it = it; s.sent = []
    async def send(s, content=None, **kw):
        assert content is None and "embed" not in kw, "非 V2 followup"
        s.sent.append(kw); s.it.view = kw.get("view")

class Interaction:
    def __init__(s, uid=ADMIN, data=None):
        s.user = types.SimpleNamespace(id=uid, display_name="tester", mention="@t", color=discord.Color.default())
        s.response = Resp(s); s.followup = Followup(s); s.view = None; s.data = data or {}
        s.namespace = types.SimpleNamespace()
        s.type = discord.InteractionType.application_command
    async def edit_original_response(s, **kw): s.view = kw.get("view")

def texts(view):
    return "\n".join(i.content for i in view.walk_children() if isinstance(i, discord.ui.TextDisplay))
def is_v2(view): return isinstance(view, discord.ui.LayoutView)

async def main():
    await udm.init_db()
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    # 1. 所有 Cog 都能載入
    for folder in os.listdir("Cogs"):
        if folder.startswith("load-"):
            for f in os.listdir(os.path.join("Cogs", folder)):
                if f.endswith(".py") and not f.startswith("__"):
                    try:
                        await bot.load_extension(f"Cogs.{folder}.{f[:-3]}"); check(f, True)
                    except Exception as e:
                        check(f"load {f}: {e!r}", False)
    await bot.load_extension("Logger.Logger")

    from Utils.components import notice_view, pick_color
    check("color red", pick_color("❌ x") == discord.Color.red())
    check("color green", pick_color("✅ x") == discord.Color.green())

    # 2. admin-item edit_item
    item_cog = bot.get_cog("ItemAdmin")
    cmds = {c.name: c for c in item_cog.walk_app_commands()}
    items = await idm.get_all_items()
    iid = next(iter(items))
    it = Interaction(); await cmds["edit_item"].callback(item_cog, it, iid)
    v = it.view
    check("edit_item V2", is_v2(v) and "編輯道具" in texts(v))
    check("edit_item component count", sum(1 for _ in v.walk_children()) <= 40)
    # 換分類
    new_cat = next(c for c in ("consumable", "collectible", "special") if c != items[iid]["category"])
    it2 = Interaction(data={"values": [new_cat]}); await v.select_category_callback(it2)
    check("category changed", (await idm.get_item(iid))["category"] == new_cat and "分類已更改" in texts(it2.view))
    # Modal
    it3 = Interaction(); await v.edit_callback(it3)
    modal = it3.modal
    modal.name_input._value = "測試名稱"; modal.emoji_input._value = "🧪"; modal.desc_input._value = "測試描述"
    it4 = Interaction(); await modal.on_submit(it4)
    check("modal update", (await idm.get_item(iid))["name"] == "測試名稱" and "已成功更新" in texts(it4.view))
    # 刪除 → 取消 → 刪除 → 確定
    it5 = Interaction(); await v.delete_callback(it5); check("confirm screen", "刪除確認" in texts(it5.view))
    it6 = Interaction(); await v.cancel_delete_callback(it6); check("cancel", "已取消刪除" in texts(it6.view))
    await v.delete_callback(Interaction())
    it7 = Interaction(); await v.confirm_delete_callback(it7)
    check("deleted", await idm.get_item(iid) is None and "道具已刪除" in texts(it7.view))
    check("non-admin blocked", await v.interaction_check(Interaction(uid=1)) is False)
    # 其他 admin-item 指令
    it = Interaction(uid=1); await cmds["edit_item"].callback(item_cog, it, iid)
    check("no perm V2", is_v2(it.view) and "無權限" in texts(it.view))
    it = Interaction(); await cmds["give_items"].callback(item_cog, it, 5, None)
    check("give_items V2", is_v2(it.view) and "隨機道具發放完成" in texts(it.view))
    it = Interaction(); await cmds["manage"].callback(item_cog, it, None)
    check("manage V2", is_v2(it.view) and "道具管理" in texts(it.view) and it.response.sent[-1].get("ephemeral"))

    # 3. admin-sys reload
    sys_cog = bot.get_cog("SysAdmin")
    scmds = {c.name: c for c in sys_cog.walk_app_commands()}
    it = Interaction(); await scmds["reload"].callback(sys_cog, it)
    v = it.view
    check("reload panel V2", is_v2(v) and "模組重載控制台" in texts(v) and it.response.sent[0].get("ephemeral"))
    async def fake_sync(): return []
    bot.tree.sync = fake_sync
    it2 = Interaction(data={"values": ["Cogs.load-gacha.gacha"]}); await v.select_callback(it2)
    check("reload success", "重新載入成功" in texts(it2.view) and "模組重載控制台" in texts(it2.view))
    it3 = Interaction(data={"values": ["Cogs.nope"]}); await v.select_callback(it3)
    check("reload fail", "重新載入失敗" in texts(it3.view))
    check("reload non-admin", await v.interaction_check(Interaction(uid=1)) is False)
    it = Interaction(); await scmds["sync"].callback(sys_cog, it)
    check("sync V2", is_v2(it.view) and "成功同步" in texts(it.view))

    # 4. admin-user
    user_cog = bot.get_cog(next(n for n in bot.cogs if "User" in n and n != "SysAdmin"))
    ucmds = {c.name: c for c in user_cog.walk_app_commands()}
    target = types.SimpleNamespace(id=555, display_name="目標")
    it = Interaction(); await ucmds["add_money"].callback(user_cog, it, target, 100)
    check("add_money V2", is_v2(it.view) and "賽錢" in texts(it.view))
    it = Interaction(); await ucmds["clear_inventory"].callback(user_cog, it, target)
    check("clear_inventory V2", is_v2(it.view) and "清空" in texts(it.view))

    # 5. gacha 錯誤提示
    gcog = bot.get_cog("GachaCardSys")
    gcmds = {c.name: c for c in gcog.walk_app_commands()}
    it = Interaction(uid=777); await gcmds["gacha"].callback(gcog, it, types.SimpleNamespace(value="classic"), types.SimpleNamespace(value=10))
    check("gacha poor V2", is_v2(it.view) and "賽錢不足" in texts(it.view))
    it = Interaction(uid=777); await gcmds["fusion"].callback(gcog, it, "x", "y", "SR")
    check("fusion reject V2", is_v2(it.view) and "無法融合" in texts(it.view))

    # 6. Logger 重大事件
    log_cog = bot.get_cog(next(n for n in bot.cogs if "Log" in n))
    sent = []
    class Ch:
        async def send(self, content=None, **kw): sent.append((content, kw))
    bot.get_channel = lambda _id: Ch()
    await log_cog.send_alert_log("🟢 測試", "說明", discord.Color.green(), {"欄位": "值"})
    check("alert V2", sent and sent[0][0] is None and is_v2(sent[0][1]["view"]) and "欄位" in texts(sent[0][1]["view"]))

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

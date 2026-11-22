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
    async def defer(s, **kw): s.done = True; s.it.defer_ephemeral = kw.get("ephemeral", False)
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
    async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw):
        assert content is None; s.it.views.append(kw.get("view")); s.it.ephemerals.append(kw.get("ephemeral", False))
        if s.it.view is None: s.it.view = kw.get("view")
        return None
avatar = types.SimpleNamespace(with_size=lambda n: types.SimpleNamespace(url="https://x/a.png", read=None))
class Interaction:
    def __init__(s, uid=1, data=None):
        s.user = types.SimpleNamespace(id=uid, display_name="t", display_avatar=avatar, mention="@t")
        s.response = Resp(s); s.followup = Followup(s); s.view = None; s.views = []; s.data = data or {}
        s.ephemerals, s.defer_ephemeral = [], None
        s.type = discord.InteractionType.application_command
    async def original_response(s): return None
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def buttons(v): return {i.label: i for i in v.walk_children() if isinstance(i, discord.ui.Button)}

async def main():
    await udm.init_db()
    # 預設道具 = 4 + 2 個體力道具 + 28 道招待料理 + 27 種素材 + 紅霧異變活動 8 個 (素材 5 + 料理 3)
    items = await idm.get_all_items()
    check(f"default items {len(items)}", {"yuyuko_dango", "sakuya_scone_tea", "marisa_mushroom_soup", "reimu_onigiri",
                                          "onsen_zosui", "hell_nabe"} <= set(items) and len(items) == 69)
    serve = [v["effect"].get("serve") for v in items.values() if v["category"] == "cuisine"]
    check("cuisine food 10 / drink 11 / dessert 10 (含活動各 1)",
          (serve.count("food"), serve.count("drink"), serve.count("dessert")) == (10, 11, 10))
    check("new stamina dishes", [items[k]["effect"]["stamina"] for k in ("onsen_zosui", "hell_nabe")] == [60, 150]
          and all(items[k]["category"] == "consumable" for k in ("onsen_zosui", "hell_nabe")))
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
    # 🔒 私人資料卡：/daily 的簽到結果和 💥 POWER UP! 都只有自己看得到 (0.36.002，使用者定)；公開的照舊公開
    for uid, public in ((40, True), (41, False)):   # 40～43 號別的測試沒用
        await udm.get_or_create_user(uid); await udm.update_visibility(uid, public)
        await udm.add_exp(uid, udm.get_required_exp_for_level(0) - 1)   # 差 1 EXP 就升級
        it = Interaction(uid=uid); await cmds["daily"].callback(cog, it)
        power = [e for v, e in zip(it.views, it.ephemerals) if "POWER UP" in texts(v)]
        check(f"daily visibility public={public} {it.defer_ephemeral} {it.ephemerals}",
              it.defer_ephemeral is (not public) and len(it.views) == 2 and power == [not public]
              and all(e is (not public) for e in it.ephemerals))
    # 私人資料卡在 /profile 按「⛩️ 投賽錢簽到」升級：POWER UP 也只有自己看得到
    for uid, public in ((42, True), (43, False)):
        await udm.get_or_create_user(uid); await udm.update_visibility(uid, public)
        await udm.add_exp(uid, udm.get_required_exp_for_level(0) - 1)
        it = Interaction(uid=uid); await cmds["profile"].callback(cog, it, None, None)
        it2 = Interaction(uid=uid); await it.view.on_daily(it2)
        check(f"profile daily power up public={public} {it2.ephemerals}",
              [e for v, e in zip(it2.views, it2.ephemerals) if "POWER UP" in texts(v)] == [not public])
    await udm.add_stamina(10, -100)
    it = Interaction(uid=10); await cmds["profile"].callback(cog, it, None, None)
    pv = it.view
    check("profile stamina button", "⚡ 恢復體力" in buttons(pv))
    # ⚡ 恢復體力 = 彈窗 (Utils/stamina_modal.py)：選道具 + 選數量
    modal_holder = {}
    async def send_modal(m): modal_holder["m"] = m; i2.response.done = True
    i2 = Interaction(uid=10); i2.response.send_modal = send_modal
    await buttons(pv)["⚡ 恢復體力"].callback(i2)
    modal = modal_holder.get("m")
    labels = [c for c in modal.walk_children() if isinstance(c, discord.ui.Label)] if modal else []
    check("stamina modal", modal and len(labels) == 2 and "140 / 240" in labels[0].description
          and [o.value for o in modal.item_select.options] == ["reimu_onigiri"]
          and [o.value for o in modal.qty_select.options] == ["1", "2", "3"])
    modal.item_select._values, modal.qty_select._values = ["reimu_onigiri"], ["1"]
    i3 = Interaction(uid=10); i3.type = discord.InteractionType.modal_submit
    await modal.on_submit(i3)
    check(f"used {texts(i3.views[0]) if i3.views else ''}", i3.view is pv and "`200 / 240`" in texts(pv)
          and i3.views and "`140` ➔ `200`" in texts(i3.views[0]) and "今天還能吃 `2` 個" in texts(i3.views[0]))
    # 沒有體力道具 ➔ 直接提示，不開彈窗
    modal_holder.clear()
    i4 = Interaction(uid=10); i4.response.send_modal = send_modal
    await buttons(pv)["⚡ 恢復體力"].callback(i4)
    check("no item notice", not modal_holder and "沒有體力道具" in texts(i4.view))

    # 🍽️ 每天最多吃 3 個體力道具 (含飯糰)
    from datetime import datetime, timezone, timedelta
    t0 = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)   # 台灣 11:00
    await udm.add_item(12, "reimu_onigiri", 5)
    check("left 3", await udm.get_stamina_item_left(12, t0) == 3)
    r = await udm.use_stamina_item(12, "reimu_onigiri", 60, qty=2, now=t0)
    check(f"use 2 {r}", r["ok"] and r["used"] == 2 and r["daily_left"] == 1 and r["left"] == 3)
    r = await udm.use_stamina_item(12, "reimu_onigiri", 60, qty=2, now=t0)
    check("over limit rejected", not r["ok"] and r["reason"] == "daily_limit" and r["daily_left"] == 1)
    check("nothing changed", (await udm.get_or_create_user(12))["inventory"]["reimu_onigiri"] == 3)
    check("use last 1", (await udm.use_stamina_item(12, "reimu_onigiri", 60, now=t0))["daily_left"] == 0)
    check("limit 0", (await udm.use_stamina_item(12, "reimu_onigiri", 60, now=t0))["reason"] == "daily_limit")
    t1 = t0 + timedelta(hours=13)   # 台灣隔天 00:00
    check("reset next day", await udm.get_stamina_item_left(12, t1) == 3 and (await udm.use_stamina_item(12, "reimu_onigiri", 60, now=t1))["ok"])
    check("not owned", (await udm.use_stamina_item(12, "hell_nabe", 150, now=t1))["reason"] == "not_owned")
    check("bad qty", (await udm.use_stamina_item(12, "reimu_onigiri", 60, qty=0, now=t1))["reason"] == "bad_qty")
    await udm.add_item(12, "reimu_onigiri", 5)
    rs = await asyncio.gather(*[udm.use_stamina_item(12, "reimu_onigiri", 60, now=t1) for _ in range(4)])
    check("concurrent limit", sum(x["ok"] for x in rs) == 2)   # 隔天已經吃 1 個 ➔ 只能再 2 個
    # 額度用完 ➔ 按鈕直接提示
    sql_con = sqlite3.connect(udm.DB_PATH)
    sql_con.execute("UPDATE users SET stamina_item_day = ?, stamina_item_used = 3 WHERE user_id = 10", (udm.tw_day(),)); sql_con.commit(); sql_con.close()
    await udm.add_item(10, "reimu_onigiri", 1)
    i5 = Interaction(uid=10); i5.response.send_modal = send_modal
    await buttons(pv)["⚡ 恢復體力"].callback(i5)
    check("daily limit notice", not modal_holder and "今天已經吃了 3 個" in texts(i5.view))
    # 別人的資料卡沒有恢復體力按鈕
    it = Interaction(uid=11); await cmds["profile"].callback(cog, it, types.SimpleNamespace(id=10, display_name="t", display_avatar=avatar), None)
    check("no button on others", "⚡ 恢復體力" not in buttons(it.view))

    # adjust_item：正數給予、負數扣除、不能小於 0、剛好 0 移除
    r = await udm.adjust_item(20, "yuyuko_dango", 5); check("adjust +5", r == {"ok": True, "before": 0, "after": 5})
    r = await udm.adjust_item(20, "yuyuko_dango", -2); check("adjust -2", r["ok"] and r["after"] == 3)
    r = await udm.adjust_item(20, "yuyuko_dango", -10); check("adjust below 0 rejected", not r["ok"] and r["before"] == 3)
    check("unchanged after reject", (await udm.get_or_create_user(20))["inventory"]["yuyuko_dango"] == 3)
    r = await udm.adjust_item(20, "yuyuko_dango", -3); check("adjust to 0", r["ok"] and r["after"] == 0)
    check("removed at 0", "yuyuko_dango" not in (await udm.get_or_create_user(20))["inventory"])
    await udm.adjust_item(21, "reimu_onigiri", 3)
    rs = await asyncio.gather(*[udm.adjust_item(21, "reimu_onigiri", -1) for _ in range(5)])
    check("concurrent adjust", sum(x["ok"] for x in rs) == 3 and "reimu_onigiri" not in (await udm.get_or_create_user(21))["inventory"])

    # /admin-item manage：分類 + 分頁 + 堆疊列表 ➔ Modal 輸入數量
    await bot.load_extension("Cogs.load-general.Admin-item")
    acog = bot.get_cog("ItemAdmin")
    cmd_names = {c.name for c in acog.walk_app_commands()}
    check("give_item replaced", "manage" in cmd_names and "give_item" not in cmd_names)
    manage = next(c for c in acog.walk_app_commands() if c.name == "manage")
    from Utils.config import ADMIN_IDS
    if ADMIN_IDS:
        target = types.SimpleNamespace(id=30, display_name="目標")
        it = Interaction(uid=min(ADMIN_IDS)); await manage.callback(acog, it, target)
        mv = it.view
        check("manage view", "道具管理：目標" in texts(mv) and texts(mv).count("*未持有*") == 10)
        modal_holder = {}
        async def send_modal(m): modal_holder["m"] = m
        i2 = Interaction(uid=min(ADMIN_IDS), data={"values": ["sakuya_scone_tea"]}); i2.response.send_modal = send_modal
        await mv.item_callback(i2)
        modal = modal_holder["m"]
        check("modal opened", "目前持有 0" in str(modal.amount_input.label))
        for raw, expect in [("7", "已給予"), ("-2", "已扣除"), ("-99", "不能扣除"), ("0", "不能是 0"), ("x", "不是整數"), ("-5", "已從神社倉庫移除")]:
            modal.amount_input._value = raw
            i3 = Interaction(uid=min(ADMIN_IDS)); await modal.on_submit(i3)
            check(f"modal {raw}", expect in texts(mv))
        check("final count 0", "sakuya_scone_tea" not in (await udm.get_or_create_user(30))["inventory"])
        await udm.adjust_item(30, "reimu_onigiri", 2)
        await mv.category_callback(Interaction(uid=min(ADMIN_IDS), data={"values": ["owned"]}))
        check("owned filter", "陰陽梅干飯糰" in texts(mv) and "幽夢三色團子" not in texts(mv))
        await mv.category_callback(Interaction(uid=min(ADMIN_IDS), data={"values": ["special"]}))
        check("empty category", "沒有任何道具" in texts(mv))
        check("non-admin blocked", await mv.interaction_check(Interaction(uid=1)) is False)

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

"""🔍 單卡詳情改版 (2026-11-23)：角色資料、這張卡的實力 (跟裏世界一樣)、特殊能力、價值、狀態、📖 角色圖鑑按鈕"""
import asyncio, os, sys, shutil, sqlite3, tempfile, importlib, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
os.environ.setdefault("SHOW_UNRELEASED", "1")   # 🙈 測試預設看得到未公開卡池 (Utils/config.py)
import discord
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")   # 絕不碰真實 Users.db
gacha = importlib.import_module("Cogs.load-gacha.gacha")
gc = importlib.import_module("Cogs.load-gacha.Components.gacha_components")
from Database import Economy_DB_Manager as econ
from Database.ura import combat, data as ura_data, rules as ura_rules, describe

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

UID, OTHER = 616, 717
def card(iid, key="flandre", rarity="UR", comp=0.85):
    p = gacha.GACHA_POOL[key]
    return {"instance_id": iid, "character_key": key, "name": p["name"], "emoji": p["emoji"], "rarity": rarity,
            "title": p["titles"][rarity], "completeness": comp, "obtained_at": "2026-11-20 10:00:00"}

class Resp:
    def __init__(s, it): s.it = it; s.done = False; s.kw = {}
    def is_done(s): return s.done
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view"); s.kw = kw
    async def defer(s, **kw): s.done = True
    async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view")
class Interaction:
    def __init__(s, uid=UID, values=None):
        s.user = types.SimpleNamespace(id=uid, display_name="tester"); s.response = Resp(s); s.followup = Followup(s)
        s.view = None; s.data = {"values": values or []}; s.type = discord.InteractionType.component

def texts(item):
    return "\n".join(i.content for i in item.walk_children() if isinstance(i, discord.ui.TextDisplay))
def total(item):
    return sum(1 for _ in item.walk_children())
def labels(item):
    return [b.label for b in item.walk_children() if isinstance(b, discord.ui.Button)]
def button(item, label):
    return next(b for b in item.walk_children() if isinstance(b, discord.ui.Button) and b.label == label)


async def main():
    await udm.init_db()
    await udm.get_or_create_user(UID)

    # 1. 每位角色、每個階級、各種完整度都畫一次：元件、字數；數值跟裏世界出征算出來的一樣
    worst_c = worst_t = 0
    mismatch = []
    for cid, info_ in gacha.GACHA_POOL.items():
        for rarity in info_["rarities"]:
            for comp in (0.001, 0.2999, 0.3, 0.85, 1.0):
                c = card(f"c_all_{cid}_{rarity}_{comp}", cid, rarity, comp)
                info = await gacha.card_detail_info(c, UID)
                cont = gc.build_card_detail_container(c, "tester", gacha.THUMBNAILS, info)
                worst_c, worst_t = max(worst_c, total(cont) + 6), max(worst_t, len(texts(cont)))   # + 按鈕列 (1 + 5)
                u = combat.make_member(0, c, ura_data.characters()[cid])
                want = (combat.max_hp(u), describe.num(combat.eff_atk(u)), describe.num(combat.eff_def(u)))
                got = (info["ura"]["hp"], info["ura"]["atk"], info["ura"]["def"])
                if want != got or info["ura"]["ok"] != (comp >= ura_rules.MIN_COMPLETENESS):
                    mismatch.append((cid, rarity, comp, want, got))
                if info["spell"]["b"] != u["b_cost"] or info["spell"]["cd"] != u["cd_max"] \
                        or info["spell"]["effect"] != describe.spell_text(cid, u["tier"]):
                    mismatch.append((cid, rarity, comp, "spell"))
    check(f"all rendered within limits {worst_c} {worst_t}", worst_c <= 40 and worst_t <= 4000)
    check(f"stats same as ura {mismatch[:3]}", not mismatch)

    # 2. 內容：角色資料、實力、特殊能力 (只寫這個階級那一檔)、價值
    c = card("c_d_1", "flandre", "UR", 0.85)
    info = await gacha.card_detail_info(c, UID)
    t = texts(gc.build_card_detail_container(c, "tester", gacha.THUMBNAILS, info))
    from Utils.character_data import load_characters
    p = load_characters()["flandre"]["profile"]
    check("profile", f"【{p['title']}】" in t and p["species"] in t and p["ability"] in t and p["description"] in t)
    check("ura section", "### ⚔️ 這張卡的實力" in t and "✅ 可以派去裏世界" in t and ura_rules.CLASS_NAMES["atk"] in t)
    lv = load_characters()["flandre"]["special_powers"]["levels"]["UR"]
    others = [v["name"] for r, v in load_characters()["flandre"]["special_powers"]["levels"].items() if r != "UR"]
    check("spell this tier only", lv["name"] in t and not any(n in t for n in others) and "比平常的" in t)
    price = econ.price_of(await econ.get_market_prices(), "flandre", "UR")
    check("value", f"分解能拿 `{econ.card_value(price, 0.85):,}` 賽錢" in t)
    low = card("c_d_low", "flandre", "UR", 0.2)
    t = texts(gc.build_card_detail_container(low, "tester", gacha.THUMBNAILS, await gacha.card_detail_info(low, UID)))
    check("cannot expedition", "不能派去裏世界" in t and "比平常的" not in t)
    # 簡介太長就截斷
    long = dict(info, profile=dict(info["profile"], description="紅" * 500))
    t = texts(gc.build_card_detail_container(c, "tester", gacha.THUMBNAILS, long))
    check("description truncated", "紅" * gc.DETAIL_DESC_MAX + "…完整介紹看📖 角色圖鑑" in t and "紅" * (gc.DETAIL_DESC_MAX + 1) not in t)
    check("no info = basic", "卡牌資訊" in texts(gc.build_card_detail_container(c, "tester", gacha.THUMBNAILS)))

    # 3. 狀態：⚗️ 可以一起合成 / 🔮 可以融合 / 🔒 收藏中 / 🌀 出征中
    await udm.add_gacha_cards(UID, [card("c_s_1", "remilia", "SSR", 0.3), card("c_s_2", "remilia", "SSR", 0.4),
                                    card("c_s_3", "remilia", "SSR", 0.5),
                                    card("c_f_1", "cirno", "SR", 1.0), card("c_f_2", "cirno", "SR", 1.0),
                                    card("c_f_3", "cirno", "SR", 1.0), card("c_l_1", "cirno", "SR", 0.5),
                                    card("c_e_1", "remilia", "SSR", 0.6)], draw_count=0)
    await udm.set_cards_locked(UID, ["c_l_1"], True)
    con = sqlite3.connect(udm.DB_PATH)
    con.execute("UPDATE gacha_cards SET expedition = 1 WHERE instance_id = 'c_e_1'"); con.commit(); con.close()
    mine = {c["instance_id"]: c for c in await udm.get_user_cards(UID, include_locked=True)}
    async def state_text(cid):
        cc = mine[cid]
        return texts(gc.build_card_detail_container(cc, "tester", None, await gacha.card_detail_info(cc, UID)))
    check("synth state", "還有 `2` 張可以一起合成" in await state_text("c_s_1"))   # 出征中那張不算
    check("fuse state", "🔮 可以融合 ➔ `[SSR]`：完美卡 `3 / 3` 張" in await state_text("c_f_1"))
    check("locked state", "🔒 收藏中：" in await state_text("c_l_1"))
    check("expedition state", "🌀 出征中：" in await state_text("c_e_1"))

    # 4. 畫面：卡冊單卡 (本人 / 管理員看別人)、收藏冊單卡，都有 📖 角色圖鑑，開出 ephemeral 的角色頁
    cards = gacha.sort_cards(await udm.get_user_cards(UID))
    view = gacha.InventoryView(UID, cards, "tester", None)
    it = Interaction(values=["c_s_1"]); await view.card_select_callback(it)
    t = texts(it.view)
    check("inventory detail", "### 📜 角色資料" in t and "### 💹 價值" in t and total(it.view) <= 40 and len(t) <= 4000)
    check("inventory buttons", labels(it.view)[-4:] == ["🔙 返回這一疊", "🎒 返回卡冊", "🔒 放進收藏冊", "📖 角色圖鑑"])
    page = Interaction(); await button(it.view, "📖 角色圖鑑").callback(page)
    check("character page", page.view is not None and "蕾米莉亞" in texts(page.view) and "🏷️ 卡牌階級" in texts(page.view)
          and page.response.kw.get("ephemeral") is True
          and "紅霧異變期間開放" in texts(page.view))   # 卡池狀態那行也讀當下的活動 (2026-11-24)
    check("detail stays", "### 📜 角色資料" in texts(view))
    admin_cards = gacha.sort_cards(await udm.get_user_cards(UID, include_locked=True))
    av = gacha.InventoryView(OTHER, admin_cards, "目標", None, owner_id=UID)
    it = Interaction(uid=OTHER, values=["c_e_1"]); await av.card_select_callback(it)
    check("admin view detail", "🌀 出征中：" in texts(it.view) and "🔒 放進收藏冊" not in labels(it.view)
          and "📖 角色圖鑑" in labels(it.view))
    album = gacha.AlbumView(UID, "tester", await udm.get_album_cards(UID))
    it = Interaction(values=["c_l_1"]); await album.select_callback(it)
    check("album detail", "🔒 收藏中：" in texts(it.view) and "### ✨ 這張卡的特殊能力" in texts(it.view)
          and labels(it.view)[-3:] == ["🔙 返回收藏冊", "📤 取出 (回到卡冊)", "📖 角色圖鑑"] and total(it.view) <= 40)
    page = Interaction(); await button(it.view, "📖 角色圖鑑").callback(page)
    check("album character page", "琪露諾" in texts(page.view) and page.response.kw.get("ephemeral") is True)
    page = Interaction(); await gacha.send_character_page(page, "no_such_char")
    check("character missing", "找不到" in texts(page.view))


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

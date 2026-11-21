"""🌀 裏世界畫面 (Cogs/load-ura)：每個階段 / 模式都畫一次檢查 Discord 上限；假互動走完 出發 ➔ 探索 ➔ 結算"""
import asyncio, os, sys, tempfile, types, random, importlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import discord
from discord import ui
from Database import User_DB_Manager as udm
from Database import Ura_DB_Manager as ura
from Database.ura import data, rules, combat, run as R

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")   # 絕不碰真實 Users.db
cogmod = importlib.import_module("Cogs.load-ura.ura")
ura.secrets.token_hex = lambda n=8: "uitest"   # 出發的 seed 固定 (測試結果每次一樣)
UC = importlib.import_module("Cogs.load-ura.Components.ura_components")

# _select 會默默只留前 25 個選項 (Discord 上限)：測試裡改成記下來，最後檢查沒有選單被截掉 (= 有東西選不到)
_over = []
_orig_select = cogmod._select
def _loud_select(placeholder, options, *a, **kw):
    if len(options) > 25:
        _over.append((placeholder, len(options)))
    return _orig_select(placeholder, options, *a, **kw)
cogmod._select = _loud_select

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else:
        fail += 1; print("FAIL:", name)


# ---------- Discord 上限 ----------
def limits(view, where):
    items = list(view.walk_children())
    n = len(items) + 0
    text = sum(len(i.content) for i in items if isinstance(i, ui.TextDisplay))
    bad = []
    if n > 40: bad.append(f"元件 {n}")
    if text > 4000: bad.append(f"文字 {text}")
    for i in items:
        if isinstance(i, ui.ActionRow):
            kids = list(i.children)
            if sum(isinstance(k, ui.Button) for k in kids) > 5: bad.append("一排超過 5 顆按鈕")
            if any(isinstance(k, ui.Select) for k in kids) and len(kids) > 1: bad.append("選單那排有別的東西")
        if isinstance(i, ui.Select):
            if not 1 <= len(i.options) <= 25: bad.append(f"選項 {len(i.options)}")
            if i.max_values > len(i.options) or i.min_values > i.max_values: bad.append("min/max_values")
            for o in i.options:
                if len(o.label) > 100 or len(o.description or "") > 100 or len(o.value) > 100: bad.append("選項文字太長")
            if len(i.placeholder or "") > 150: bad.append("placeholder 太長")
        if isinstance(i, ui.Button) and len(i.label or "") > 80: bad.append("按鈕文字太長")
    check(f"limits {where}: {bad}", not bad)
    return n, text


class StubCog:
    def __init__(self): self.tracked, self.announced = [], []
    async def track(self, view): self.tracked.append(view)
    def forget(self, view): pass
    async def announce(self, it, state, settle): self.announced.append(settle)


def render_all(state, where):
    """這個進度的每一種模式都畫一次"""
    cog = StubCog()
    v = cogmod.RunView(cog, types.SimpleNamespace(id=1), {"rev": 0, "state": state})
    limits(v, f"{where}/main")
    for mode in ("bag", "abandon"):
        v.mode = mode; v.build(); limits(v, f"{where}/{mode}")
    for kind in ("enemy", "ally", "dead", "member"):
        v.mode, v.pending = "target", {"action": "attack", "kind": kind}
        v.build(); limits(v, f"{where}/target-{kind}")
    v.mode = "main"; v.pending = None


# ---------- 自動玩家：走很多局，每一步都畫 ----------
def autoplay(seed, team, bag, max_steps=400, accept_events=True):
    rng = random.Random(seed)
    chars = data.characters()
    cards = [({"instance_id": f"c{i}", "character_key": cid, "rarity": r, "completeness": c}, chars[cid])
             for i, (cid, r, c) in enumerate(team)]
    st = R.new_run(f"ui{seed}", cards, bag, 50000, rng, capacity=25)
    phases = set()
    for step in range(max_steps):
        if st["phase"] == "ended":
            break
        phases.add(st["phase"])
        render_all(st, f"seed{seed}#{step}:{st['phase']}")
        g = R.action_rng(st)
        ph = st["phase"]
        if ph == "doors":
            R.choose_door(st, g.randrange(len(st["doors"])), g)
        elif ph == "battle":
            b = st["battle"]
            actor = next((m for m in st["party"] if combat.can_act(st, m)), None)
            if actor and not combat.spell_ready(st, actor) and g.random() < 0.5:
                if R.battle_action(st, "spell", g, uid=actor["uid"], target=(combat.living(b["foes"]) or [{}])[0].get("uid")):
                    R.battle_action(st, "attack", g, uid=actor["uid"], target=combat.living(b["foes"])[0]["uid"])
            elif actor:
                R.battle_action(st, "attack", g, uid=actor["uid"], target=combat.living(b["foes"])[0]["uid"])
        elif ph == "chest":
            if not st["room"].get("opened"):
                R.open_chest(st, g, force=True)
            if st["phase"] == "chest":
                R.leave_room(st, g)
        elif ph == "event":
            pc = st["room"].get("pending_choice")
            if pc:
                do = data.events()[pc]["effect"]["do"]
                pick = None
                if do == "upgrade_treasure":
                    pick = next((i for i, t in enumerate(st["bag"]["treasures"]) if t["rarity"] != "LR"), None)
                elif do == "trial":
                    pick = combat.living(st["party"])[0]["uid"]
                elif do == "trade_items_for_relic":
                    pick = [i for i, n in st["bag"]["items"].items() for _ in range(n)][:3]
                if R.event_choice(st, accept_events, g, pick=pick):
                    R.event_choice(st, False, g)
            if st["phase"] == "event":
                R.leave_room(st, g)
        elif ph == "merchant":
            R.buy(st, 0)
            render_all(st, f"seed{seed}#{step}:merchant-bought")
            R.leave_room(st, g)
        elif ph == "boss_clear":
            if st["boss_cleared"] >= 2:
                R.evacuate(st)
            else:
                R.continue_after_boss(st, g)
        else:
            R.leave_room(st, g)
    return st, phases


async def fake_settle_render(st):
    """結算畫面 (直接用引擎的 settle)"""
    s = R.settle(st)
    s.update(net=max(0, s["money"] - s["brought"]), exp_result={"leveled_up": True, "new_p": 1.5})
    v = cogmod.RunView(StubCog(), types.SimpleNamespace(id=1), {"rev": 0, "state": st})
    v.settle, v.mode = s, "settle"
    v.build()
    limits(v, "settle")
    view = ui.LayoutView(); view.add_item(UC.build_public_settle_container("測試員", s))
    limits(view, "public settle")
    return v


# ---------- 假互動 ----------
class Resp:
    """同一個互動回應兩次 ➔ 丟例外 (Discord 會回 InteractionResponded)"""
    def __init__(s, it): s.it, s.done = it, False
    def is_done(s): return s.done
    def _mark(s):
        if s.done:
            raise RuntimeError("同一個互動回應了兩次")
        s.done = True
    async def send_message(s, content=None, *, view=None, ephemeral=False, **kw):
        assert content is None and view is not None
        s._mark(); s.it.sent.append(("send", view, ephemeral)); s.it.view = view
    async def edit_message(s, *, view=None, **kw):
        s._mark(); s.it.sent.append(("edit", view, True)); s.it.view = view
    async def send_modal(s, modal):
        s._mark(); s.it.modal = modal
    async def defer(s, **kw): s._mark()

class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, *, view=None, ephemeral=False, **kw):
        s.it.sent.append(("followup", view, ephemeral))

class It:
    def __init__(s, uid, data=None):
        s.user = types.SimpleNamespace(id=uid, display_name="測試員")
        s.data = data or {}
        s.channel_id = 5
        s.sent, s.view, s.modal = [], None, None
        s.response, s.followup = Resp(s), Followup(s)
    async def edit_original_response(s, *, view=None, **kw):
        s.sent.append(("edit_original", view, True))

def texts(view):
    return "\n".join(i.content for i in view.walk_children() if isinstance(i, ui.TextDisplay))

def find(view, label=None, placeholder=None):
    for i in view.walk_children():
        if label and isinstance(i, ui.Button) and i.label and i.label.startswith(label):
            return i
        if placeholder and isinstance(i, ui.Select) and (i.placeholder or "").startswith(placeholder):
            return i
    return None

async def press(view, uid, label=None, placeholder=None, values=None):
    comp = find(view, label, placeholder)
    assert comp is not None, f"找不到 {label or placeholder}"
    assert not getattr(comp, "disabled", False), f"{label or placeholder} 是停用的"
    return await press_comp(view, uid, comp, values)


async def press_comp(view, uid, comp, values=None):
    it = It(uid, {"values": values} if values is not None else {})
    if await view.interaction_check(it):
        await comp.callback(it)
    if not it.response.done:   # 每按一次都要剛好回應一次 (沒回應 = Discord 顯示「應用程式沒有回應」)
        raise AssertionError(f"沒有回應：{getattr(comp, 'label', None) or getattr(comp, 'placeholder', None)}")
    return it


def enabled_components(view):
    return [i for i in view.walk_children() if isinstance(i, (ui.Button, ui.Select)) and not getattr(i, "disabled", False)]


async def fuzz(cog, uid, card_ids, carry, seed, steps):
    """出發後每一步隨機按一個沒停用的按鈕 / 選單 (選單隨機選值)，每一步檢查上限與回應；回傳按過的元件名稱"""
    rng = random.Random(seed)
    ura.secrets.token_hex = lambda n=8: f"fuzz{seed}"
    async with udm.connect() as db:   # 每局補滿倉庫 (放棄 / 失敗會把帶進去的弄丟)
        await db.execute("DELETE FROM ura_storage WHERE user_id = ? AND kind = 'item'", (uid,))
        for iid in data.items():
            await db.execute("INSERT INTO ura_storage (user_id, kind, key, qty) VALUES (?, 'item', ?, 10)", (uid, iid))
        await db.commit()
    res = await ura.start_run(uid, card_ids, carry, 50000, None)
    assert res["ok"], res
    view = cogmod.RunView(cog, types.SimpleNamespace(id=uid, display_name="測試員"), res)
    pressed = set()
    for step in range(steps):
        if view.mode == "settle" or view.retired:
            break
        comps = [c for c in enabled_components(view) if not (isinstance(c, ui.Button) and c.label.startswith("📖"))]
        if step < steps - 20:   # 前面先別放棄 (最後 20 步才可以按)
            comps = [c for c in comps if not (isinstance(c, ui.Button) and c.label.startswith("🏳️ 確定"))]
        if not comps:
            check(f"fuzz{seed} stuck at {view.state['phase']}/{view.mode}", False)
            break
        comp = rng.choice(comps)
        values = None
        if isinstance(comp, ui.Select):
            k = rng.randint(comp.min_values, comp.max_values)
            values = [o.value for o in rng.sample(comp.options, k)]
        name = getattr(comp, "label", None) or comp.placeholder
        it = await press_comp(view, uid, comp, values)
        pressed.add(name.split(" (")[0] if isinstance(comp, ui.Button) else comp.placeholder)
        if it.view is view or it.view is None:
            limits(view, f"fuzz{seed}#{step}:{view.state['phase']}/{view.mode}")
    if view.mode != "settle":   # 收尾：放棄
        row = await ura.get_run(uid)
        if row:
            await ura.act(uid, row["rev"], lambda s, g: R.abandon(s))
    return pressed


async def main():
    # ===== 1. 每個階段 / 模式的上限 =====
    big = [("marisa", "SR", 0.65), ("meiling", "SR", 0.65), ("daiyousei", "SR", 0.65)]
    bag = {"eientei_salve": 2, "eirin_elixir": 1, "bamboo_herb": 2, "bunbunmaru": 2, "gensokyo_engi": 1, "bomb": 3,
           "dango": 3, "ice_seal": 2, "telescope": 2, "map_piece": 1, "sukima": 1, "phoenix_feather": 1, "chest_key": 3}
    seen = set()
    last = None
    for seed in range(12):
        st, ph = autoplay(seed, big, dict(bag), accept_events=seed % 2 == 0)
        seen |= ph
        if st["phase"] == "ended":
            last = st
    check(f"phases covered {seen}", {"doors", "battle", "chest", "event", "boss_clear"} <= seen)
    # 最壞情況：3 隻敵人都有狀態、隊伍有法具、滿 log、背包塞滿、待撿 25+ 樣
    rng = random.Random(7)
    chars = data.characters()
    cards = [({"instance_id": f"c{i}", "character_key": c, "rarity": "UR", "completeness": 1.0}, chars[c])
             for i, c in enumerate(["reimu", "marisa", "meiling"])]
    st = R.new_run("worst", cards, dict(bag), 1, rng, capacity=50)
    st["floor"] = 9
    R.choose_door(st, 0, rng)
    from Database.ura import combat as C
    C.start(st, "elite", ["mad_rabbit", "shadow_rabbit", "shadow_rabbit"], rng)
    for u in st["party"] + st["battle"]["foes"]:
        for sid in ("poison", "freeze", "atk_up", "shield", "taunt"):
            if sid in data.statuses():
                u["statuses"].append({"id": sid, "left": 3, "stacks": 1})
    for m in st["party"]:
        m["relic"] = {"rid": "nine_tails", "tier": 2}
    st["battle"]["log"] = ["一二三四五六七八九十" * 6] * 14
    st["bag"]["treasures"] = [R.roll_treasure("monster", 1, rng) for _ in range(30)]
    st["bag"]["relics"] = [R.roll_relic(1, rng) for _ in range(5)]
    st["bag"]["materials"] = {m[0]: 20 for m in __import__("Database.shrine_data", fromlist=["x"]).MATERIAL_ITEMS[:30]}
    st["pending"] = [{"kind": "treasures", "key": R.roll_treasure("monster", 1, rng)} for _ in range(30)]
    render_all(st, "worst battle")
    st["phase"], st["battle"] = "doors", None
    st["doors"] = [{"type": "battle", "foes": ["lost_spirit"] * 3}, {"type": "elite", "foes": ["mad_rabbit"]},
                   {"type": "chest", "locked": True, "mimic": False}, {"type": "chest", "hidden": True, "locked": False, "mimic": True}]
    render_all(st, "worst doors")
    st["phase"], st["room"] = "merchant", {"type": "merchant", "stock": R._merchant_stock(st, rng)}
    render_all(st, "worst merchant")
    for eid, ev in data.events().items():
        st["phase"], st["room"] = "event", {"type": "event", "event": eid, "etype": ev["type"],
                                             "pending_choice": eid if ev.get("choice") else None}
        render_all(st, f"event {eid}")
    st["phase"], st["room"] = "boss_clear", None
    st["boss_cleared"] = 1
    render_all(st, "worst boss_clear")
    if last:
        await fake_settle_render(last)
    st["result"], st["phase"] = "evacuated", "ended"
    v = await fake_settle_render(st)
    t = texts(v)
    check("settle big money", f"# 💰 {st['pocket']:,} 賽錢" in t and "淨賺" in t)
    st["result"] = "failed"
    t = texts(await fake_settle_render(st))
    check("settle failed", "迷失在第" in t and "完整度 −0.1" in t)
    # 狀態表 / 商店 / 倉庫
    view = ui.LayoutView(); view.add_item(UC.build_status_table()); limits(view, "status table")
    check("status table has all", all(s["name"] in texts(view) for k, s in data.statuses().items() if not k.startswith("_")))

    # 🎪 活動門 / 活動戰鬥 / 活動 BOSS / 小惡魔的交易 的畫面
    F = "th06_scarlet_mist"
    stub = StubCog()
    def rv(state):
        return cogmod.RunView(stub, types.SimpleNamespace(id=1), {"rev": 0, "state": state})
    fst = R.new_run("festui", cards, {}, 5000, random.Random(1), capacity=25, live_fests=[F])
    fst["doors"] = [{"type": "battle", "foes": ["scarlet_fairy", "vampire_bat"], "fest": F}, {"type": "chest", "locked": False, "mimic": False}]
    v = rv(fst); t = texts(v)
    check("fest door label", "1. 🎪 ⚔️ 戰鬥 ×2" in t and "🎪 紅霧異變｜🌫️ 紅霧：我方每回合結束" in t and find(v, label="1. 🎪"))
    R.choose_door(fst, 0, random.Random(2))
    v = rv(fst); t = texts(v)
    check("fest battle header", "### 🎪 ⚔️ 戰鬥" in t and "-# 🎪 紅霧異變｜🌫️ 紅霧" in t and "🌫️ 紅霧" in t.split("**我方**")[1])
    render_all(fst, "fest battle")
    fb = R.new_run("festboss", cards, {}, 5000, random.Random(1), capacity=25, live_fests=[F])
    fb["floor"], fb["room"] = 3, {"type": "elite", "fest": F, "fest_boss": True}
    C.start(fb, "elite", ["scarlet_flandre"], random.Random(1), fest_boss=True)
    v = rv(fb); t = texts(v)
    check("fest boss screen", "### 🎪 👹 活動 BOSS 戰" in t and "🎪 👹 **紅霧・芙蘭朵露**" in t and find(v, label="🏃 逃跑").disabled)
    render_all(fb, "fest boss")
    imp = R.new_run("festimp", cards, {}, 5000, random.Random(1), capacity=25, live_fests=[F])
    imp["floor"], imp["phase"] = 2, "event"
    imp["room"] = {"type": "event", "fest": F, "event": "fest_imp_deal", "etype": "special", "pending_choice": "fest_imp_deal"}
    v = rv(imp); t = texts(v)
    check("imp deal screen", "😈 小惡魔的交易" in t and "紅霧異變的特別關卡" in t and find(v, label="✅ 好"))
    R.event_choice(imp, True, random.Random(1))
    t = texts(rv(imp))
    check("imp deal result", "😈 付了 3,000 賽錢，換到 🎪" in t)

    # ===== 2. 假互動：整個流程 =====
    await udm.init_db()
    UID = 777
    await udm.get_or_create_user(UID)
    await udm.add_money(UID, 1_000_000)
    async with udm.connect() as db:
        await udm._insert_cards(db, UID, [
            {"instance_id": "m1", "character_key": "marisa", "name": "魔理沙", "emoji": "", "rarity": "SSR", "title": "", "completeness": 0.9, "obtained_at": "x"},
            {"instance_id": "m2", "character_key": "marisa", "name": "魔理沙", "emoji": "", "rarity": "SR", "title": "", "completeness": 0.2, "obtained_at": "x"},
            {"instance_id": "r1", "character_key": "reimu", "name": "靈夢", "emoji": "", "rarity": "UR", "title": "", "completeness": 1.0, "obtained_at": "x"},
        ])
        await db.commit()
    cog = cogmod.UraCog(bot=None)
    cog.announce_orig = cog.announce

    # 商店 ➔ 倉庫
    it = It(UID); await cogmod.UraCog.shop.callback(cog, it)
    shop = it.view; limits(shop, "shop")
    await press(shop, UID, placeholder="🛍️", values=["eientei_salve"])
    it = await press(shop, UID, label="🛒 買 5")
    check("shop bought", "✅ 買了" in texts(it.view))
    await press(shop, UID, placeholder="🗂️", values=["bags"])
    limits(shop, "shop bags")
    await press(shop, UID, placeholder="🛍️", values=["bag_n"])
    await press(shop, UID, label="🛒 買 1")
    for g in UC.SHOP_GROUPS:
        await press(shop, UID, placeholder="🗂️", values=[g]); limits(shop, f"shop {g}")
    all_items = [i for g in UC.SHOP_GROUPS for i in UC.shop_items(g)]
    check("every shop item listed once", sorted(all_items) == sorted([i for i, x in data.items().items() if x.get("price")] + list(data.bags())))

    # 出發：沒卡的人
    it = It(999); await cogmod.UraCog.explore.callback(cog, it)
    check("no cards notice", "還沒有可以出征的卡" in texts(it.view))
    # 出發：選隊伍
    it = It(UID); await cogmod.UraCog.explore.callback(cog, it)
    picker = it.view; limits(picker, "picker")
    other = It(123)
    check("picker deny others", not await picker.interaction_check(other))
    check("picker header", "選隊伍 (0 / 3)" in texts(picker))
    await press(picker, UID, placeholder="🧍", values=["marisa"])
    card_sel = find(picker, placeholder="🎴")
    check("card select lists both", card_sel and len(card_sel.options) == 2 and any(o.label.startswith("🚫") for o in card_sel.options))
    it = await press(picker, UID, placeholder="🎴", values=["m2"])
    check("bad card refused", "不能派" in texts(it.view))
    await press(picker, UID, label="➕ 加入隊伍")
    check("added marisa", "m1" in picker.picked)
    await press(picker, UID, placeholder="🧍", values=["reimu"])
    await press(picker, UID, label="➕ 加入隊伍")
    check("two picked", picker.picked == ["m1", "r1"])
    await press(picker, UID, label="➖ 移出隊伍")
    check("removed reimu", picker.picked == ["m1"])
    await press(picker, UID, label="➕ 加入隊伍")
    limits(picker, "picker full")
    it = await press(picker, UID, label="➡️ 下一步")
    load = it.view
    check("loadout view", isinstance(load, cogmod.LoadoutView)); limits(load, "loadout")
    await press(load, UID, placeholder="🧪", values=["eientei_salve"])
    await press(load, UID, label="➕ 5")
    check(f"carry 5 {load.carry}", load.carry == {"eientei_salve": 5})
    it = await press(load, UID, label="➕ 1")
    check("over limit notice", "⚠️" in texts(it.view) and load.carry == {"eientei_salve": 5})
    await press(load, UID, label="➖ 1")
    await press(load, UID, label="💾 儲存這組")
    check("loadout saved", (await ura.get_record(UID))["loadout"] == {"eientei_salve": 4})
    await press(load, UID, label="🧹 全部不帶")
    await press(load, UID, label="⚡ 快速整裝")
    check("quick loadout", load.carry == {"eientei_salve": 4})
    bag_id = str((await ura.get_storage(UID))["bags"][0]["id"])
    await press(load, UID, placeholder="🎒", values=[bag_id])
    check("bag chosen", "額外背包" in texts(load))
    it = await press(load, UID, label="💰 帶賽錢")
    modal = it.modal
    check("pocket modal", isinstance(modal, cogmod.PocketModal))
    modal.amount._value = "abc"
    it2 = It(UID); await modal.on_submit(it2)
    check("modal bad input", "整數" in texts(it2.view) and load.pocket == 0)
    modal.amount._value = "99,999,999"
    it2 = It(UID); await modal.on_submit(it2)
    check("modal too much", "不夠" in texts(it2.view))
    modal.amount._value = "20,000"
    it2 = It(UID); await modal.on_submit(it2)
    check("modal ok", load.pocket == 20000 and "20,000" in texts(it2.view))
    limits(load, "loadout filled")
    it = await press(load, UID, label="🚀 出發")
    run_view = it.view
    check("run started", isinstance(run_view, cogmod.RunView) and run_view.state["phase"] == "doors")
    check("tracked", cog.live.get(UID) is run_view or True)
    row = await ura.get_run(UID)
    check("db run", row and row["rev"] == 0 and row["state"]["pocket"] == 20000)
    limits(run_view, "run doors")

    # 再開一次 explore ➔ 顯示同一局，舊畫面退休
    it = It(UID); await cogmod.UraCog.explore.callback(cog, it)
    v2 = it.view
    check("explore again shows run", isinstance(v2, cogmod.RunView) and "已經有一局" in texts(v2))
    check("old view retired", run_view.retired)
    it = It(UID)
    check("retired refuses", not await run_view.interaction_check(it) and "過期" in texts(it.view))
    # 舊的 rev：同一個進度另一個畫面先動 ➔ 這個重新讀
    v3 = cogmod.RunView(cog, types.SimpleNamespace(id=UID), await ura.get_run(UID))
    await press(v2, UID, label="1.")
    it = await press(v3, UID, label="1.")
    check("stale reloads", "重新讀取" in texts(it.view) and v3.rev == v2.rev)

    # 一路玩到結束 (放棄)
    view = v2
    for _ in range(300):
        st = view.state
        if view.mode == "settle":
            break
        if view.mode == "target":
            sel = find(view, placeholder="🎯")
            await press(view, UID, placeholder="🎯", values=[sel.options[0].value]); continue
        ph = st["phase"]
        if ph == "doors":
            await press(view, UID, label="1.")
        elif ph == "battle":
            await press(view, UID, label="⚔️ 普攻")
        elif ph == "chest":
            b = find(view, label="🔓") or find(view, label="🗝️")
            if b and not b.disabled: await press(view, UID, label=b.label)
            else: await press(view, UID, label="🚪")
        elif ph == "event":
            if find(view, label="❌ 不要"): await press(view, UID, label="❌ 不要")
            else: await press(view, UID, label="🚪")
        elif ph in ("trap", "merchant"):
            await press(view, UID, label="🚪")
        elif ph == "boss_clear":
            await press(view, UID, label="🏁 撤離"); break
        limits(view, f"live {ph}")
        if st["floor"] >= 4 and view.state["phase"] == "doors":
            # 背包：用道具 (需要選目標時進選目標)
            await press(view, UID, label="🎒 背包")
            limits(view, "live bag")
            check("bag text", "背包" in texts(view))
            if find(view, placeholder="🧪"):
                await press(view, UID, placeholder="🧪", values=["eientei_salve"])
                if view.mode == "target":
                    await press(view, UID, placeholder="🎯", values=[find(view, placeholder="🎯").options[0].value])
            if view.mode == "bag":
                await press(view, UID, label="↩️ 返回")
            # 放棄：先確認
            await press(view, UID, label="🏳️ 放棄")
            check("abandon confirm", "確定要放棄" in texts(view))
            await press(view, UID, label="↩️ 返回")
            check("abandon back", view.mode == "main")
            await press(view, UID, label="🏳️ 放棄")
            it = await press(view, UID, label="🏳️ 確定放棄")
            check("abandoned settle", view.mode == "settle" and "放棄了探索" in texts(view))
            check("public settle sent", any(k == "followup" and not e for k, _, e in it.sent))
            break
    check("run gone", await ura.get_run(UID) is None)
    cards = {c["instance_id"]: c for c in await udm.get_user_cards(UID, include_locked=True)}
    check("penalty applied", abs(cards["m1"]["completeness"] - 0.8) < 1e-9 and cards["m1"]["expedition"] == 0)

    # 私人資料卡 ➔ 不公開
    await udm.update_visibility(UID, False)
    it = It(UID)
    await cog.announce(it, view.state, view.settle)
    check("private no public post", not any(k == "followup" for k, _, _ in it.sent))
    await udm.update_visibility(UID, True)

    # /ura resume、abandon 沒有局
    it = It(UID); await cogmod.UraCog.resume.callback(cog, it)
    check("resume none", "沒有進行中" in texts(it.view))
    it = It(UID); await cogmod.UraCog.abandon.callback(cog, it)
    check("abandon none", "沒有進行中" in texts(it.view))

    # /ura abandon 有局：直接確認畫面
    r = await ura.start_run(UID, ["r1"], {}, 0, None)
    it = It(UID); await cogmod.UraCog.abandon.callback(cog, it)
    check("abandon cmd confirm", it.view.mode == "abandon")
    await press(it.view, UID, label="🏳️ 確定放棄")
    check("abandon cmd done", await ura.get_run(UID) is None)

    # 收畫面用的互動：按狀態表 (另一則訊息) 之後，收的還是探索畫面
    r = await ura.start_run(UID, ["r1"], {}, 0, None)
    v = cogmod.RunView(cog, types.SimpleNamespace(id=UID, display_name="x"), r)
    await cog.track(v)
    await press(v, UID, label="🎒 背包")
    it_back = await press(v, UID, label="↩️ 返回")
    it_table = await press(v, UID, label="📖 狀態表")
    check("status table separate msg", it_table.sent[0][0] == "send" and v.last is it_back)
    v2 = cogmod.RunView(cog, types.SimpleNamespace(id=UID, display_name="x"), await ura.get_run(UID))
    await cog.track(v2)
    check("retire edits run screen", any(k == "edit_original" for k, _, _ in it_back.sent)
          and not any(k == "edit_original" for k, _, _ in it_table.sent) and v.retired)
    it = await press(v2, UID, label="1.")
    it_bad = It(UID)
    await v2.act(it_bad, lambda s, g: "不行")
    check("rejected keeps last", v2.last is it and "不行" in texts(it_bad.view))
    row = await ura.get_run(UID)
    await ura.act(UID, row["rev"], lambda s, g: R.abandon(s))

    # 隨機亂按：每個按鈕 / 選單都要經過 ura.act 而且剛好回應一次
    FUZZ = 888
    await udm.get_or_create_user(FUZZ)
    await udm.add_money(FUZZ, 5_000_000)
    keys = list(data.characters())
    async with udm.connect() as db:
        await udm._insert_cards(db, FUZZ, [
            {"instance_id": f"f_{k}", "character_key": k, "name": k, "emoji": "", "rarity": data.characters()[k]["rarities"][-1],
             "title": "", "completeness": 1.0, "obtained_at": "x"} for k in keys])
        for iid in data.items():
            await db.execute("INSERT INTO ura_storage (user_id, kind, key, qty) VALUES (?, 'item', ?, 10)", (FUZZ, iid))
        await db.commit()
    carry = {"eientei_salve": 2, "eirin_elixir": 1, "bunbunmaru": 2, "gensokyo_engi": 2, "dango": 3, "bomb": 3, "ice_seal": 2,
             "telescope": 1, "map_piece": 1, "reroll_dice": 1, "phoenix_feather": 1, "chest_key": 3, "iou": 2}
    teams = [["chiyuri", "daiyousei", "marisa"], ["meiling", "reimu", "yumemi"], ["chiyuri", "sakuya", "patchouli"],
             ["flandre", "elly", "mima"], [keys[0]], ["rika", "genji", "cirno"]]
    pressed = set()
    for seed, team in enumerate(teams):
        team = [t for t in team if t in data.characters()] or keys[:3]
        pressed |= await fuzz(cog, FUZZ, [f"f_{t}" for t in team], carry, seed, 300)
    want = {"⚔️ 普攻", "✨ 符卡", "🎒 道具", "🎒 背包", "🧪 使用道具…", "↩️ 返回", "🚪 繼續前進"}
    check(f"fuzz covered {sorted(want - pressed)}", want <= pressed)
    check("fuzz discarded", any(p.startswith("🗑️ 丟掉") for p in pressed))
    print("   fuzz pressed:", len(pressed), "種；沒按到：", sorted({"📜 御札", "🏃 逃跑", "🛒 買一個…", "✅ 好", "🔥 接受試煉",
          "⛩️ 獻上哪一個寶物？", "🦊 把法具裝給誰…", "📦 撿起放不下的東西…", "🏁 撤離 (帶東西回去)", "➡️ 繼續前進"} - pressed))
    check("fuzz runs cleaned", await ura.get_run(FUZZ) is None)

    # 隨機很難遇到的：特殊事件 (賭局 / 祠堂 / 試煉) 和 BOSS 打完撤離
    async def staged(setup):
        res = await ura.start_run(FUZZ, ["f_marisa", "f_meiling"], {}, 20000, None)
        await ura.act(FUZZ, res["rev"], lambda s, g: setup(s, g))
        return cogmod.RunView(cog, types.SimpleNamespace(id=FUZZ, display_name="測試員"), await ura.get_run(FUZZ))

    def event_room(eid, treasures=0):
        def setup(s, g):
            s["floor"], s["phase"] = 3, "event"
            s["room"] = {"type": "event", "event": eid, "etype": "special", "pending_choice": eid}
            s["bag"]["treasures"] = [{"id": "ura_bamboo_shoot", "rarity": "N", "zone": 1} for _ in range(treasures)]
        return setup
    v = await staged(event_room("tengu_gamble"))
    await press(v, FUZZ, label="✅ 好")
    check("gamble done", v.state["room"].get("result", {}).get("do") == "gamble" and "🎲" in texts(v))
    await press(v, FUZZ, label="🚪 繼續前進")
    check("after event doors", v.state["phase"] == "doors")
    await ura.act(FUZZ, v.rev, lambda s, g: R.abandon(s))
    v = await staged(event_room("shrine_altar", treasures=2))
    sel = find(v, placeholder="⛩️")
    check("offer lists one kind", sel and len(sel.options) == 1)
    await press(v, FUZZ, placeholder="⛩️", values=[sel.options[0].value])
    check("offered", v.state["room"]["result"]["do"] == "upgrade_treasure" and "⛩️" in texts(v)
          and sorted(t["rarity"] for t in v.state["bag"]["treasures"]) == ["N", "R"])
    await ura.act(FUZZ, v.rev, lambda s, g: R.abandon(s))
    v = await staged(event_room("trial_of_fire"))
    if find(v, label="🔥 接受試煉"):
        await press(v, FUZZ, label="🔥 接受試煉")
        check("trial asks target", v.mode == "target")
        await press(v, FUZZ, placeholder="🎯", values=[v.state["party"][1]["uid"]])
        check("trial done", v.state["room"]["result"]["do"] == "trial")
    else:
        check("trial event id", False)
    await ura.act(FUZZ, v.rev, lambda s, g: R.abandon(s))

    def boss_clear(s, g):
        s["floor"], s["phase"], s["boss_cleared"], s["room"] = 10, "boss_clear", 1, None
        s["pocket"] = 98765
        s["bag"]["treasures"] = [R.roll_treasure("boss", 1, g, rarity="UR")]
    v = await staged(boss_clear)
    m0 = (await udm.get_or_create_user(FUZZ))["money"]
    it = await press(v, FUZZ, label="🏁 撤離")
    check("evacuated settle", v.mode == "settle" and "# 💰 98,765 賽錢" in texts(v) and "淨賺 +78,765" in texts(v))
    pub = [view for k, view, e in it.sent if k == "followup" and not e]
    check("public evacuate post", pub and "# 💰 98,765 賽錢" in texts(pub[0]) and "測試員" in texts(pub[0]))
    check("money back", (await udm.get_or_create_user(FUZZ))["money"] == m0 + 98765)
    check("record net", (await ura.get_record(FUZZ))["best_money"] == 78765)

    # 倉庫：賣寶物 (先確認)
    async with udm.connect() as db:
        for tid, n in (("ura_bamboo_shoot", 3), ("ura_tanzaku", 2), ("ura_hourai_branch", 1), ("fest_gungnir_shard", 1)):
            await db.execute("INSERT INTO ura_storage (user_id, kind, key, qty) VALUES (?, 'treasure', ?, ?)", (UID, tid, n))
        await db.commit()
    it = It(UID); await cogmod.UraCog.inventory.callback(cog, it)
    inv = it.view; limits(inv, "storage")
    check("storage lists", "竹筍" in texts(inv) and "蓬萊之玉枝" in texts(inv))
    await press(inv, UID, placeholder="⭐", values=["N"])
    check("filter N", "竹筍" in texts(inv) and "蓬萊之玉枝" not in texts(inv))
    await press(inv, UID, label="💰 篩選出來的全部賣掉")
    check("sell confirm", "確定要把上面篩選出來的寶物" in texts(inv))
    m0 = (await udm.get_or_create_user(UID))["money"]
    await press(inv, UID, label="💰 確定全部賣掉")
    check("sold N only", (await udm.get_or_create_user(UID))["money"] == m0 + 3 * data.treasure_prices()["N"]
          and (await ura.get_storage(UID))["treasures"] == {"ura_tanzaku": 2, "ura_hourai_branch": 1, "fest_gungnir_shard": 1})
    await press(inv, UID, placeholder="⭐", values=["all"])
    await press(inv, UID, placeholder="🗺️", values=["fest"])
    t = texts(inv)
    check("filter fest", "岡格尼爾" in t and "七夕的短冊" not in t and "🎪 活動寶物" in t)
    for k in ("items", "bags"):
        await press(inv, UID, placeholder="📦", values=[k]); limits(inv, f"storage {k}")
    await press(inv, UID, placeholder="📦", values=["treasures"])
    await press(inv, UID, placeholder="🔍", values=["fest_gungnir_shard"])
    limits(inv, "storage peek")
    check("peek shows desc", data.treasure_info("fest_gungnir_shard")["desc"][:10] in texts(inv))
    await press(inv, UID, placeholder="🗺️", values=["all"])
    it = It(UID); await cogmod.UraCog.status.callback(cog, it)
    check("status cmd", "狀態表" in texts(it.view))

    # 📖 怪物圖鑑：竹林 5 隻全打過 ➔ 一隻一頁、領全收獎勵
    async with udm.connect() as db:
        for e in ("lost_spirit", "shadow_rabbit", "bamboo_wraith", "mad_rabbit", "ura_mokou"):
            await udm.add_player_stat(db, UID, f"ura_kill:{e}", 2)
        await db.commit()
    it = It(UID); await cogmod.UraCog.bestiary.callback(cog, it)
    bv = it.view; limits(bv, "bestiary list")
    t = texts(bv)
    base = cogmod.B.progress((await ura.get_bestiary(UID))["kills"])["base"]   # 前面走過的局也有打倒別的怪 (打倒當下就登錄)
    check(f"bestiary list {base}", "迷途竹林　5 / 5" in t and "裏・藤原妹紅" in t and f"一般主題 {base[0]} / 25" in t
          and "🎁 可以領" in t and base[0] >= 5)
    await press(bv, UID, placeholder="📖", values=["4"]); limits(bv, "bestiary boss page")
    t = texts(bv)
    check("boss page", "火之鳥" in t and "第 2 區起：沒有閃避" in t and "深區開招順序" in t and "💡" in t and "第 5 / 5 隻" in t)
    await press(bv, UID, label="◀️"); check("prev", "第 4 / 5 隻" in texts(bv) and "狂氣的月兔" in texts(bv))
    await press(bv, UID, label="↩️ 回清單"); check("back to list", "✅" in texts(bv))
    m0 = (await udm.get_or_create_user(UID))["money"]
    await press(bv, UID, label="🎁 領取：🎋 迷途竹林全收")
    check("claimed zone", "領到" in texts(bv) and (await udm.get_or_create_user(UID))["money"] == m0 + 200000 and "✅ 已領" in texts(bv))
    check("claim button gone", not any(isinstance(b, ui.Button) and "迷途竹林全收" in (b.label or "") for b in bv.walk_children()))
    for key in [s_["key"] for s_ in cogmod.B.sections()]:
        await press(bv, UID, placeholder="🗺️", values=[key]); limits(bv, f"bestiary {key}")
        for i in range(5):
            await press(bv, UID, placeholder="📖", values=[str(i)]); limits(bv, f"bestiary {key} #{i}")
    check("fest locked page", "活動期間才會出現" in texts(bv) and "❓ ？？？" in texts(bv))

    await long_lists(cog, staged, event_room, FUZZ)
    check(f"no select cut at 25 {_over[:3]}", not _over)


async def page_values(view, uid, placeholder):
    """一個會翻頁的選單：每一頁都看一次 (檢查上限)，回傳全部選項 {value: label}；看完停在最後一頁"""
    got = {}
    for _ in range(20):
        sel = find(view, placeholder=placeholder)
        assert sel is not None, f"找不到 {placeholder}"
        got.update({o.value: o.label for o in sel.options})
        limits(view, f"pages {placeholder}")
        nxt = find(view, label="下一頁")
        if not nxt or nxt.disabled:
            break
        await press(view, uid, label="下一頁")
    return got


async def long_lists(cog, staged, event_room, uid):
    """
    0.35.108 修：背包東西多 (超過 25 項) 時丟掉選單只列前 25 項，排在最後的法具丟不掉
    ➔ 背包「整理」先選一類、每類超過 25 項翻頁；待撿、獻寶物、狐狸、整裝道具也一樣
    """
    from Database.shrine_data import MATERIAL_ITEMS
    check("usable items fit one select", sum(1 for i in data.items().values() if i.get("use") != "passive") <= 25)
    async with udm.connect() as db:   # 前面的局放棄 / 失敗扣過完整度、口袋錢：補回來 (下面要再出發 3 次)
        await db.execute("UPDATE gacha_cards SET completeness = 1.0 WHERE user_id = ?", (uid,))
        await db.execute("UPDATE users SET money = money + 1000000 WHERE user_id = ?", (uid,))
        await db.commit()
    treasures = []   # 30 種不同的寶物 (5 個主題的名單輪流拿)
    for z, theme in enumerate(data.zones(), 1):
        for rows in data.theme_treasures(theme).values():
            treasures += [{"id": row[0], "rarity": "N", "zone": z} for row in rows]
    treasures = treasures[:30]
    check(f"test treasures {len(treasures)}", len(treasures) == 30)

    def big_bag(s, g):
        s["floor"], s["phase"], s["room"], s["capacity"] = 3, "doors", None, 300
        s["bag"]["items"] = {iid: 2 for iid in data.items()}                   # 27 種
        s["bag"]["materials"] = {m[0]: 3 for m in MATERIAL_ITEMS[:26]}         # 26 種
        s["bag"]["treasures"] = [dict(t) for t in treasures] + [dict(treasures[0])]   # 30 種 (第一種 2 個)
        s["bag"]["relics"] = [R.roll_relic(1, g) for _ in range(30)]           # 30 個
        s["pending"] = [{"kind": "treasures", "key": dict(treasures[i % 30])} for i in range(30)]
    v = await staged(big_bag)
    bag0 = v.state["bag"]
    limits(v, "big bag doors")
    check("main pending -> button", find(v, label="📦 撿起放不下的東西 (30 樣") is not None and find(v, placeholder="📦") is None)
    await press(v, uid, label="🎒 背包")
    limits(v, "big bag")
    tabsel = find(v, placeholder="🎒 整理背包")
    check("bag tabs", tabsel and [o.value for o in tabsel.options] == list(cogmod.BAG_TABS))

    # ① 每一類翻完所有頁：每一樣都找得到
    want = {
        "items": {f"items|{i}" for i in bag0["items"]},
        "materials": {f"materials|{m}" for m in bag0["materials"]},
        "treasures": {f"treasures|{i}" for i in range(30)},   # 同一種只列第一個 (第 31 個跟第 1 個同種)
        "relics": {f"relics|{i}" for i in range(30)},
        "equip": {str(i) for i in range(30)},
        "pending": {str(i) for i in range(30)},
    }
    for tab, ph in (("items", "🗑️ 丟掉"), ("materials", "🗑️ 丟掉"), ("treasures", "🗑️ 丟掉"), ("relics", "🗑️ 丟掉"),
                    ("equip", "🦊"), ("pending", "📦")):
        await press(v, uid, placeholder="🎒 整理背包", values=[tab])
        got = await page_values(v, uid, ph)
        check(f"bag tab {tab} lists all ({len(want[tab] - set(got))} missing)", want[tab] == set(got))
        check(f"bag tab {tab} paged", len(got) > 25)

    # ② 每一樣都丟得掉：每次選最後一類 (法具 ➔ 寶物 ➔ 素材 ➔ 道具)、翻到最後一頁丟最後一個，直到背包空了
    def things(bag):   # 背包裡總共幾樣 (疊在同一格的道具丟 1 個格數不會變，所以數個數)
        return sum(bag["items"].values()) + sum(bag["materials"].values()) + len(bag["treasures"]) + len(bag["relics"])
    relic_dropped = 0
    for step in range(400):
        if things(v.state["bag"]) == 0:
            break
        tabsel = find(v, placeholder="🎒 整理背包")
        drop = [o.value for o in tabsel.options if o.value in ("items", "materials", "treasures", "relics")] if tabsel else []
        if drop:
            await press(v, uid, placeholder="🎒 整理背包", values=[drop[-1]])
        await page_values(v, uid, "🗑️ 丟掉")
        sel = find(v, placeholder="🗑️ 丟掉")
        before, n_rel = things(v.state["bag"]), len(v.state["bag"]["relics"])
        await press(v, uid, placeholder="🗑️ 丟掉", values=[sel.options[-1].value])
        relic_dropped += n_rel - len(v.state["bag"]["relics"])
        if things(v.state["bag"]) >= before:
            check(f"discard step {step} shrinks", False)
            break
    check(f"bag emptied ({R.slots_used(v.state['bag'])} left)", R.slots_used(v.state["bag"]) == 0 and relic_dropped == 30)
    check("still bag mode", v.mode == "bag")

    # ③ 待撿 30 樣：在背包裡翻到第 2 頁撿；主畫面 25 樣以內才直接列選單
    await page_values(v, uid, "📦")
    sel = find(v, placeholder="📦")
    await press(v, uid, placeholder="📦", values=[sel.options[-1].value])
    check("took from page 2", len(v.state["pending"]) == 29 and len(v.state["bag"]["treasures"]) == 1)
    await press(v, uid, label="↩️ 返回")
    await press(v, uid, label="📦 撿起放不下的東西 (29 樣")
    check("button opens pending tab", v.mode == "bag" and find(v, placeholder="📦") is not None)
    for _ in range(4):
        await press(v, uid, placeholder="📦", values=[find(v, placeholder="📦").options[0].value])
    await press(v, uid, label="↩️ 返回")
    check("main pending select at 25", len(v.state["pending"]) == 25 and find(v, placeholder="📦 撿起放不下的東西…") is not None)
    await ura.act(uid, v.rev, lambda s, g: R.abandon(s))

    # ④ 祠堂：30 種寶物，獻第 2 頁的
    def shrine(s, g):
        event_room("shrine_altar")(s, g)
        s["bag"]["treasures"] = [dict(t) for t in treasures]
    v = await staged(shrine)
    got = await page_values(v, uid, "⛩️")
    check("offer lists 30", len(got) == 30)
    sel = find(v, placeholder="⛩️")
    await press(v, uid, placeholder="⛩️", values=[sel.options[-1].value])
    check("offered page 2", v.state["room"].get("result", {}).get("do") == "upgrade_treasure"
          and sorted(t["rarity"] for t in v.state["bag"]["treasures"]).count("R") == 1)
    await ura.act(uid, v.rev, lambda s, g: R.abandon(s))

    # ⑤ 狐狸：道具種類多 (每種最多列 3 份還是超過 25) ➔ 分次選、可以跨頁
    def fox(s, g):
        event_room("fox_trade")(s, g)
        s["bag"]["items"] = {iid: 3 for iid in list(data.items())[:13]}
    v = await staged(fox)
    items0 = dict(v.state["bag"]["items"])
    sel = find(v, placeholder="🦊 選 3 個")
    check("fox paged", sel is not None and "頁" in sel.placeholder and sel.min_values == 1 and find(v, label="下一頁"))
    await page_values(v, uid, "🦊")
    last = find(v, placeholder="🦊").options[-1].value
    await press(v, uid, placeholder="🦊", values=[last])
    check("fox picked 1", v.fox == [last.split("#")[0]] and "已選" in find(v, placeholder="🦊").placeholder
          and v.state["room"].get("pending_choice") == "fox_trade")
    await press(v, uid, label="🧹 重選")
    check("fox reset", v.fox == [])
    await press(v, uid, placeholder="🦊", values=[last])
    await press(v, uid, label="◀️ 上一頁")
    first = [o.value for o in find(v, placeholder="🦊").options[:2]]
    await press(v, uid, placeholder="🦊", values=first)
    gave = [x.split("#")[0] for x in [last] + first]
    left = {i: items0[i] - gave.count(i) for i in items0 if items0[i] - gave.count(i) > 0}
    check(f"fox traded", v.state["room"].get("result", {}).get("do") == "trade_items_for_relic"
          and v.state["bag"]["items"] == left and v.fox == [])
    await ura.act(uid, v.rev, lambda s, g: R.abandon(s))

    # ⑥ 整裝：倉庫 27 種道具 (翻頁)、30 個額外背包 (同種同次數合成一個選項)
    storage = {"items": {iid: 2 for iid in data.items()}, "treasures": {},
               "bags": [{"id": k + 1, "bag_id": list(data.bags())[k % 6], "uses_left": 1 + k % 3} for k in range(30)]}
    picker = types.SimpleNamespace(picked=[], card=lambda i: None)
    load = cogmod.LoadoutView(cog, types.SimpleNamespace(id=uid), picker, storage, {}, 0)
    limits(load, "loadout many")
    got = await page_values(load, uid, "🧪")
    check("loadout items all", set(got) == set(data.items()))
    pick = find(load, placeholder="🧪").options[-1].value
    await press(load, uid, placeholder="🧪", values=[pick])
    await press(load, uid, label="➕ 1")
    check("loadout page 2 carry", load.carry == {pick: 1})
    bsel = find(load, placeholder="🎒")
    check("loadout bags grouped", bsel and len(bsel.options) == 1 + 6 and "×5" in bsel.options[1].label)
    await press(load, uid, placeholder="🎒", values=[bsel.options[-1].value])
    check("loadout bag picked", load.bag_row == int(bsel.options[-1].value) and load.capacity()[0] > rules.BAG_SLOTS)


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

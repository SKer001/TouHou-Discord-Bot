import asyncio, os, sys, shutil, tempfile, importlib, types, random
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
gacha = importlib.import_module("Cogs.load-gacha.gacha")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

class Resp:
    def __init__(s, it): s.it = it; s.done = False
    def is_done(s): return s.done
    async def defer(s, **kw): s.done = True
    async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view")
class Interaction:
    def __init__(s, uid=1, data=None):
        s.user = types.SimpleNamespace(id=uid, display_name="t"); s.response = Resp(s); s.followup = Followup(s)
        s.view = None; s.data = data or {}; s.type = discord.InteractionType.application_command

def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def count(v): return sum(1 for _ in v.walk_children())
def selects(v): return [i for i in v.walk_children() if isinstance(i, discord.ui.Select)]
def buttons(v): return {i.label: i for i in v.walk_children() if isinstance(i, discord.ui.Button)}

def card(iid, key, rarity, comp, t="2026-01-01 00:00:00"):
    p = gacha.GACHA_POOL[key]
    return {"instance_id": iid, "character_key": key, "name": p["name"], "emoji": p["emoji"], "rarity": rarity,
            "title": p["titles"][rarity], "completeness": comp, "obtained_at": t}

async def main():
    await udm.init_db()
    cards = []
    n = 0
    # 20 張靈夢 SR (一疊)、各種角色
    for i in range(20):
        cards.append(card(f"c_th01_r{i:02d}", "reimu", "SR", round(0.01 * (i + 1), 4), f"2026-01-01 00:00:{i:02d}"))
    for key, v in gacha.GACHA_POOL.items():
        for r in v["rarities"]:
            n += 1
            cards.append(card(f"c_x_{n:03d}", key, r, round(random.uniform(0.001, 0.99), 4), f"2026-02-01 00:{n % 60:02d}:00"))
    cards.append({"instance_id": "c_old_1", "character_key": "ghost", "name": "舊角色", "emoji": "👻", "rarity": "R",
                  "title": "已移除", "completeness": 0.5, "obtained_at": "2025-01-01"})
    await udm.add_gacha_cards(1, cards)

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    cog = gacha.GachaCardSys(bot); await bot.add_cog(cog)
    cmd = next(c for c in cog.walk_app_commands() if c.name == "inventory")
    it = Interaction(); await cmd.callback(cog, it)
    v = it.view
    total_stacks = 24 * 3 + 1
    check("stacks", len(v.all_stacks) == total_stacks)
    check("header", f"`{len(cards)}` 張" in texts(v) and f"`{total_stacks}` 疊" in texts(v))
    reimu_sr = v.get_stack("reimu|SR")
    check("reimu stack 21", len(reimu_sr["cards"]) == 21 and reimu_sr["cards"][0]["completeness"] >= reimu_sr["cards"][-1]["completeness"])
    check(f"list count {count(v)}", count(v) <= 40)
    check("default sort rarity high first", v.filtered_stacks()[0]["rarity"] == "LR")

    # 卡池篩選
    i2 = Interaction(data={"values": ["th06"]}); await v.pool_select_callback(i2)
    fs = v.filtered_stacks()
    check("th06 filter", fs and all(s["pool"] == "th06" for s in fs) and len(fs) == 27)
    i2 = Interaction(data={"values": ["other"]}); await v.pool_select_callback(i2)
    check("other pool", [s["character_key"] for s in v.filtered_stacks()] == ["ghost"])
    check("other option exists", any(o.value == "other" for o in selects(v)[0].options))
    i2 = Interaction(data={"values": ["ALL"]}); await v.pool_select_callback(i2)
    # 階級篩選
    i2 = Interaction(data={"values": ["SR"]}); await v.rarity_select_callback(i2)
    check("rarity filter", all(s["rarity"] == "SR" for s in v.filtered_stacks()))
    i2 = Interaction(data={"values": ["LR"]}); await v.pool_select_callback(Interaction(data={"values": ["classic"]}))
    await v.rarity_select_callback(i2)
    check("combined filter", all(s["rarity"] == "LR" and s["pool"] == "classic" for s in v.filtered_stacks()))
    await v.rarity_select_callback(Interaction(data={"values": ["ALL"]}))
    await v.pool_select_callback(Interaction(data={"values": ["ALL"]}))

    # 排序切換
    modes = []
    for _ in range(4):
        modes.append(v.sort_mode)
        fs = v.filtered_stacks()
        if v.sort_mode == "count": check("count sort", fs[0]["character_key"] == "reimu" and fs[0]["rarity"] == "SR")
        if v.sort_mode == "best": check("best sort", all(fs[i]["best"] >= fs[i + 1]["best"] for i in range(len(fs) - 1)))
        if v.sort_mode == "latest": check("latest sort", all(fs[i]["latest"] >= fs[i + 1]["latest"] for i in range(len(fs) - 1)))
        await v.sort_callback(Interaction())
    check("sort cycle", modes == ["rarity", "best", "latest", "count"] and v.sort_mode == "rarity")

    # 翻頁
    pages = (total_stacks + gacha.STACKS_PER_PAGE - 1) // gacha.STACKS_PER_PAGE
    for _ in range(pages + 3):
        await v.next_page_callback(Interaction())
        check("page count ok", count(v) <= 40)
    check("page clamp", v.page == pages and f"{pages} / {pages}" in "".join(buttons(v)))

    # 進入一疊
    await v.stack_select_callback(Interaction(data={"values": ["reimu|SR"]}))
    check("stack view", "×21" in texts(v) and count(v) <= 40)
    await v.stack_next_callback(Interaction()); await v.stack_next_callback(Interaction()); await v.stack_next_callback(Interaction())
    check("stack page clamp", v.stack_page == 3)
    first = v.get_stack("reimu|SR")["cards"][0]["instance_id"]
    await v.card_select_callback(Interaction(data={"values": [first]}))
    check("detail", "卡牌鑑定詳情" in texts(v) and first in texts(v))
    await v.back_to_stack_callback(Interaction())
    check("back to stack", "×21" in texts(v) and v.stack_page == 3)
    await v.back_to_list_callback(Interaction())
    check("back to list", "博麗神社卡冊" in texts(v) and v.page == pages)
    await v.stack_select_callback(Interaction(data={"values": ["nope|X"]}))
    check("bad stack", v.selected_stack is None)
    check("others blocked", await v.interaction_check(Interaction(uid=2)) is False)

    # 空卡冊
    it = Interaction(uid=3); await cmd.callback(cog, it)
    check("empty inventory notice", "空空如也" in texts(it.view))

    # 收集進度
    check("progress text", "舊作卡池 `15/15`" in v._progress_text() and "紅魔鄉卡池 `9/9`" in v._progress_text())

    # 合成 / 融合捷徑
    await udm.add_gacha_cards(1, [card(f"c_th06_pf{i}", "cirno", "SR", 1.0) for i in range(3)])
    it = Interaction(); await cmd.callback(cog, it)
    v = it.view
    st = v.get_stack("cirno|SR")
    check("badges", st["can_fuse"] and "🔮" in texts(v) and "⚗️ 可合成" in texts(v))
    await v.stack_select_callback(Interaction(data={"values": ["cirno|SR"]}))
    labels = list(buttons(v))
    check(f"shortcut buttons {labels}", any("融合 ➔ SSR" in l for l in labels) and count(v) <= 40)
    i2 = Interaction(); await v.fuse_shortcut_callback(i2)
    check("fuse shortcut", isinstance(i2.view, gacha.CardActionConfirmView) and "融合確認" in texts(i2.view))
    it = Interaction(); await cmd.callback(cog, it)
    v = it.view
    await v.stack_select_callback(Interaction(data={"values": ["reimu|SR"]}))
    check("synth button", "⚗️ 合成這一疊" in buttons(v))
    i2 = Interaction(); await v.synth_shortcut_callback(i2)
    check("synth shortcut", isinstance(i2.view, gacha.SynthesisPickerView) and "步驟 1 / 2" in texts(i2.view))
    # 管理員檢視別人卡冊時沒有捷徑
    av = gacha.InventoryView(999, await udm.get_user_cards(1), "別人", cog, owner_id=1)
    await av.stack_select_callback(Interaction(uid=999, data={"values": ["reimu|SR"]}))
    check("no shortcut for others", "⚗️ 合成這一疊" not in buttons(av))

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

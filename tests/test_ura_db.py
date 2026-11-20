"""🌀 裏世界資料層 (Database/Ura_DB_Manager.py)：出發檢查、出征鎖、重複按、結算、倉庫 / 商店 / 賣寶物"""
import asyncio, os, sys, tempfile, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import aiosqlite
from Database import User_DB_Manager as udm
from Database import Economy_DB_Manager as edm
from Database import Ura_DB_Manager as ura
from Database.ura import data, rules, run as R

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")   # 絕不碰真實 Users.db

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else:
        fail += 1; print("FAIL:", name)

UID = 4242
chars = data.characters()
def card(iid, key, rarity="SR", comp=0.5):
    return {"instance_id": iid, "character_key": key, "name": key, "emoji": "", "rarity": rarity,
            "title": "", "completeness": comp, "obtained_at": "x"}

async def q(sql, *args):
    async with aiosqlite.connect(udm.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, args) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def comp(iid):
    return (await q("SELECT completeness FROM gacha_cards WHERE instance_id = ?", iid))[0]["completeness"]

async def exped(iid):
    return (await q("SELECT expedition FROM gacha_cards WHERE instance_id = ?", iid))[0]["expedition"]

def end_with(result, **extra):
    """測試用：直接把這一局改成結束 (撤離 / 失敗)"""
    def fn(state, rng):
        for k, v in extra.items():
            if k == "bag":
                state["bag"].update(v)
            elif k == "dead":
                state["party"][v]["alive"] = False
            else:
                state[k] = v
        state["result"] = result
        state["phase"] = "ended"
    return fn


async def main():
    # --- 舊資料庫遷移：gacha_cards 沒有 expedition 欄位 ➔ init_db 補上 ---
    async with aiosqlite.connect(udm.DB_PATH) as db:
        await db.execute("CREATE TABLE gacha_cards (instance_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, character_key TEXT NOT NULL, "
                         "name TEXT NOT NULL, emoji TEXT, rarity TEXT NOT NULL, title TEXT, completeness REAL NOT NULL, obtained_at TEXT)")
        await db.commit()
    await udm.init_db()
    cols = [r["name"] for r in await q("PRAGMA table_info(gacha_cards)")]
    check(f"migration adds expedition {cols}", "expedition" in cols and "locked" in cols)
    tables = {r["name"] for r in await q("SELECT name FROM sqlite_master WHERE type = 'table'")}
    check("ura tables", {"ura_runs", "ura_storage", "ura_bags", "ura_records"} <= tables)

    await udm.get_or_create_user(UID)
    keys = list(chars)
    A, B, D, E = keys[1], keys[0], keys[3], keys[4]
    async with udm.connect() as db:
        await udm._insert_cards(db, UID, [card("a", A), card("b", B), card("a2", A, "R"), card("low", D, comp=0.2),
                                          card("alb", E)])
        await db.commit()
    await udm.set_cards_locked(UID, ["alb"], True)
    await udm.add_money(UID, 2_000_000)

    # --- 可出征的卡 ---
    cand = {c["instance_id"]: c for c in await ura.candidate_cards(UID)}
    check("cand ok", cand["a"]["ok"] and cand["b"]["ok"])
    check(f"cand low comp {cand['low']}", not cand["low"]["ok"] and "完整度" in cand["low"]["why"])
    check("cand album", not cand["alb"]["ok"] and "收藏冊" in cand["alb"]["why"])

    # --- 商店 ---
    r = await ura.shop_buy(UID, "nope"); check("shop not_found", r["reason"] == "not_found")
    r = await ura.shop_buy(UID, "eientei_salve", 0); check("shop bad qty", r["reason"] == "bad_qty")
    price = data.items()["eientei_salve"]["price"]
    r = await ura.shop_buy(UID, "eientei_salve", 3); check(f"shop buy {r}", r["ok"] and r["cost"] == price * 3)
    r = await ura.shop_buy(UID, "bag_n"); check("shop bag", r["ok"])
    st = await ura.get_storage(UID)
    check(f"storage {st}", st["items"] == {"eientei_salve": 3} and len(st["bags"]) == 1 and st["bags"][0]["uses_left"] == ura.BAG_USES)
    bag_row = st["bags"][0]["id"]
    async with udm.connect() as db:
        await db.execute("UPDATE users SET money = 50 WHERE user_id = ?", (UID,)); await db.commit()
    r = await ura.shop_buy(UID, "eientei_salve"); check("shop not enough", r["reason"] == "not_enough")
    await udm.add_money(UID, 1_000_000 - 50)

    # --- 出發的檢查 ---
    async def start(ids, items=None, pocket=0, bag=None):
        return await ura.start_run(UID, ids, items or {}, pocket, bag, seed="t")
    r = await start([]); check("no cards", not r["ok"])
    r = await start(["a", "b", "a2", "low"]); check("too many cards", not r["ok"])
    r = await start(["a", "a"]); check("same card twice", not r["ok"])
    r = await start(["a", "a2"]); check(f"same character {r}", not r["ok"] and "同一位角色" in r["reason"])
    r = await start(["low"]); check("low completeness", not r["ok"] and "完整度" in r["reason"])
    r = await start(["alb"]); check("album card", not r["ok"] and "收藏冊" in r["reason"])
    r = await start(["zzz"]); check("not my card", not r["ok"])
    r = await start(["a"], {"eientei_salve": 4}); check("storage not enough", not r["ok"] and "不夠" in r["reason"])
    r = await start(["a"], {"nope": 1}); check("unknown item", not r["ok"])
    r = await start(["a"], pocket=10**9); check("pocket > money", not r["ok"] and "賽錢不夠" in r["reason"])
    r = await start(["a"], pocket=-1); check("negative pocket", not r["ok"])
    r = await start(["a"], bag=99999); check("no such bag", not r["ok"] and "背包" in r["reason"])
    check("nothing written", await ura.get_run(UID) is None and await exped("a") == 0)

    # --- 出發 ---
    money0 = (await udm.get_or_create_user(UID))["money"]
    r = await start(["a", "b"], {"eientei_salve": 2}, pocket=5000, bag=bag_row)
    check(f"start ok {r.get('reason')}", r["ok"] and r["rev"] == 0)
    st = r["state"]
    check("state party", [m["card_id"] for m in st["party"]] == ["a", "b"] and st["pocket"] == 5000)
    check("capacity with bag", st["capacity"] == rules.BAG_SLOTS + data.bags()["bag_n"]["slots"])
    check("bag items", st["bag"]["items"] == {"eientei_salve": 2})
    check("money taken", (await udm.get_or_create_user(UID))["money"] == money0 - 5000)
    s2 = await ura.get_storage(UID)
    check(f"storage taken {s2}", s2["items"] == {"eientei_salve": 1} and s2["bags"][0]["uses_left"] == ura.BAG_USES - 1)
    check("expedition set", await exped("a") == 1 and await exped("b") == 1 and await exped("a2") == 0)
    got = await ura.get_run(UID)
    check("get_run", got and got["rev"] == 0 and got["state"]["seed"] == "t")
    r = await start(["a2"]); check("one run at a time", not r["ok"] and "進行中" in r["reason"])

    # --- 出征鎖：其他功能都碰不到 ---
    ids = [c["instance_id"] for c in await udm.get_user_cards(UID)]
    check(f"inventory hides expedition {ids}", "a" not in ids and "b" not in ids and "a2" in ids)
    allc = await udm.get_user_cards(UID, include_locked=True)
    check("include_locked shows expedition flag", any(c["instance_id"] == "a" and c["expedition"] == 1 for c in allc))
    try:
        await edm.decompose_cards(UID, ["a"]); check("decompose blocked", False)
    except ValueError:
        check("decompose blocked", True)
    try:
        await udm.transform_cards(UID, ["a", "a2"], lambda c: card("new", A)); check("synth blocked", False)
    except ValueError:
        check("synth blocked", True)
    check("album blocked", await udm.set_cards_locked(UID, ["a"], True) == 0)
    check("admin delete blocked", await udm.delete_gacha_cards(UID, ["a"]) == 0)
    check("admin completeness blocked", await udm.update_cards_completeness(UID, ["a"], 1.0) == 0 and await comp("a") == 0.5)
    r = await edm.list_card(UID, "a", 100); check(f"list blocked {r}", not r["ok"])

    # --- 每一個動作 ---
    r = await ura.act(UID, 5, lambda s, g: None); check("stale rev", not r["ok"] and r["reason"] == "stale")
    r = await ura.act(UID, 0, lambda s, g: "不行"); check("fn reason not saved", not r["ok"] and r["reason"] == "不行")
    check("rev unchanged", (await ura.get_run(UID))["rev"] == 0)
    r = await ura.act(UID, 0, lambda s, g: R.choose_door(s, 0, g)); check(f"choose door {r.get('reason')}", r["ok"] and r["rev"] == 1)
    got = await ura.get_run(UID)
    check("saved", got["rev"] == 1 and got["state"]["floor"] == 1)
    # 同一個 rev 同時按兩下 ➔ 只成功一次
    rs = await asyncio.gather(ura.act(UID, 1, lambda s, g: s.update(mark=1)), ura.act(UID, 1, lambda s, g: s.update(mark=2)))
    check(f"double press once {[x['ok'] for x in rs]}", sorted(x["ok"] for x in rs) == [False, True])
    check("rev 2", (await ura.get_run(UID))["rev"] == 2)
    await ura.set_message(UID, 11, 22)
    got = await ura.get_run(UID); check("set_message", got["channel_id"] == 11 and got["message_id"] == 22)

    # --- 成功撤離 ---
    lvl0 = await q("SELECT level, exp, inventory, money FROM users WHERE user_id = ?", UID)
    tid = data.treasures(1)["SR"][0][0]
    fn = end_with("evacuated", pocket=12345, exp=100, kills={"lost_spirit": 2}, dead=1,
                  bag={"items": {"eientei_salve": 1}, "materials": {"mat_rice": 3}, "treasures": [{"id": tid, "rarity": "SR", "zone": 1}] * 2})
    r = await ura.act(UID, 2, fn)
    s = r.get("settle") or {}
    check(f"settle returned {r.get('reason')}", r["ok"] and s.get("result") == "evacuated")
    check(f"settle net {s.get('net')}", s.get("money") == 12345 and s.get("brought") == 5000 and s.get("net") == 7345)
    check("run deleted", await ura.get_run(UID) is None)
    u = (await q("SELECT level, exp, inventory, money FROM users WHERE user_id = ?", UID))[0]
    check("money back", u["money"] == lvl0[0]["money"] + 12345)
    inv = json.loads(u["inventory"])
    check(f"materials to inventory {inv}", inv.get("mat_rice", 0) == json.loads(lvl0[0]["inventory"] or "{}").get("mat_rice", 0) + 3)
    check("exp given", (u["level"], u["exp"]) != (lvl0[0]["level"], lvl0[0]["exp"]))
    st = await ura.get_storage(UID)
    check(f"storage back {st}", st["items"] == {"eientei_salve": 2} and st["treasures"] == {tid: 2})
    check("dead card penalty only", await comp("b") == 0.4 and await comp("a") == 0.5)
    check("expedition cleared", await exped("a") == 0 and await exped("b") == 0)
    rec = await ura.get_record(UID)
    check(f"record net {rec}", rec["best_money"] == 7345 and rec["deepest"] == 1 and json.loads(rec["best_money_party"])["brought"] == 5000)
    lb = await ura.get_leaderboard_records([UID, 31337])
    m, d = lb.get(UID, {}).get("money", {}), lb.get(UID, {}).get("depth", {})
    check(f"leaderboard records {lb}", m.get("value") == 7345 and m.get("floor") == 1 and m.get("at")
          and d.get("value") == 1 and d.get("net") == 7345 and len(m.get("party", [])) == 2 and 31337 not in lb)
    check("dead flag in record", [p["alive"] for p in m["party"]] == [True, False])
    stats = await udm.get_player_stats(UID)
    check(f"stats {stats}", stats.get("ura_runs") == 1 and stats.get("ura_evacuated") == 1 and stats.get("ura_kill:lost_spirit") == 2)
    r = await ura.act(UID, 3, lambda s, g: None); check("no run", r["reason"] == "none")

    # --- 失敗：全部掉光、每張卡都扣、紀錄不會變差 ---
    r = await start(["a"], {"eientei_salve": 2}, pocket=1000)
    check("start again", r["ok"])
    st = await ura.get_storage(UID)
    check(f"bag used up {st['bags']}", st["bags"] == [] or st["bags"][0]["uses_left"] == ura.BAG_USES - 1)
    m0 = (await udm.get_or_create_user(UID))["money"]
    r = await ura.act(UID, 0, end_with("failed", pocket=999, exp=100, bag={"materials": {"mat_rice": 5}}))
    check("fail settle", r["ok"] and r["settle"]["money"] == 0 and r["settle"]["exp"] == 50)
    check("fail no money", (await udm.get_or_create_user(UID))["money"] == m0)
    check("fail items lost", (await ura.get_storage(UID))["items"] == {})
    check("fail penalty", await comp("a") == 0.4 and await exped("a") == 0)
    rec = await ura.get_record(UID); check("record kept", rec["best_money"] == 7345)
    # 帶很多錢進去、撈得少 ➔ 淨賺比較低，紀錄不變
    r = await start(["b"], pocket=100000); check("start rich", r["ok"])
    r = await ura.act(UID, 0, end_with("evacuated", pocket=101000))
    check("rich net small", r["settle"]["net"] == 1000 and (await ura.get_record(UID))["best_money"] == 7345)

    # --- 放棄 (引擎的 abandon) ---
    r = await start(["a2"]); check("start a2", r["ok"])
    r = await ura.act(UID, 0, lambda s, g: R.abandon(s)); check(f"abandon {r.get('reason')}", r["ok"] and r["settle"]["result"] == "abandoned")
    check("abandon penalty", await comp("a2") == 0.4 and await exped("a2") == 0)

    # --- 額外背包：最後一次用掉就刪 ---
    async with udm.connect() as db:
        await db.execute("INSERT INTO ura_bags (user_id, bag_id, uses_left) VALUES (?, 'bag_r', 1)", (UID,)); await db.commit()
    last = [b for b in (await ura.get_storage(UID))["bags"] if b["bag_id"] == "bag_r"][0]["id"]
    r = await start(["b"], bag=last); check("start with last-use bag", r["ok"])
    check("bag broke", not any(b["id"] == last for b in (await ura.get_storage(UID))["bags"]))
    await ura.act(UID, 0, lambda s, g: R.abandon(s))

    # --- 賣寶物 ---
    m0 = (await udm.get_or_create_user(UID))["money"]
    r = await ura.sell_treasures(UID, {tid: 3}); check("sell too many", not r["ok"] and r["reason"] == "not_enough")
    check("nothing sold", (await ura.get_storage(UID))["treasures"] == {tid: 2})
    r = await ura.sell_treasures(UID, {"nope": 1}); check("sell unknown", not r["ok"])
    r = await ura.sell_treasures(UID, {}); check("sell empty", not r["ok"])
    r = await ura.sell_treasures(UID, {tid: 2})
    check(f"sell ok {r}", r["ok"] and r["money"] == data.treasure_prices()["SR"] * 2)
    check("sell money", (await udm.get_or_create_user(UID))["money"] == m0 + data.treasure_prices()["SR"] * 2)
    check("sold out", (await ura.get_storage(UID))["treasures"] == {})

    # --- 快速整裝 ---
    await ura.save_loadout(UID, {"eientei_salve": 2, "nope": 1, "bamboo_herb": 0})
    check("loadout saved", (await ura.get_record(UID))["loadout"] == {"eientei_salve": 2})
    check("record unchanged by loadout", (await ura.get_record(UID))["best_money"] == 7345)
    check("new user record", (await ura.get_record(999))["loadout"] == {})

    # 第一次撤離淨賺 0 (帶多少出來多少) 也算上榜；快速整裝存過的 (沒撤離) 不算
    U2 = 4343
    await udm.get_or_create_user(U2)
    async with udm.connect() as db:
        await udm._insert_cards(db, U2, [card("z1", A)])
        await db.commit()
    await ura.save_loadout(U2, {"eientei_salve": 1})
    check("loadout only not on board", U2 not in await ura.get_leaderboard_records([U2]))
    r = await ura.start_run(U2, ["z1"], {}, 500, None, seed="z")
    check(f"zero net start {r.get('reason')}", r["ok"])
    r = await ura.act(U2, 0, end_with("evacuated"))
    lb = (await ura.get_leaderboard_records([U2])).get(U2, {})
    check(f"zero net counts {lb}", lb.get("money", {}).get("value") == 0 and lb["money"]["at"] and lb.get("depth", {}).get("value") == 0)

    # 🎪 活動任務 (裏世界)：打倒當下就算 (含還在打的那一場、失敗也算)；撤離 / 帶出活動寶物要成功撤離才算
    F = "th06_scarlet_mist"
    async def qs():
        return {r["stat"]: r["value"] for r in await q("SELECT stat, value FROM event_quest_stats WHERE user_id = ?", U2)}
    base = await qs()
    def delta(now_):
        return {k: v - base.get(k, 0) for k, v in now_.items() if v != base.get(k, 0)}
    r = await ura.start_run(U2, ["z1"], {}, 0, None, seed="q1")
    fairy = {"eid": "scarlet_fairy", "kind": "normal", "how": "killed"}
    r = await ura.act(U2, 0, lambda s, g: s.update(battle={"killed": [fairy]}))   # 打到一半打倒了一隻
    check(f"kill counted mid-battle {delta(await qs())}", delta(await qs()) == {"ura_kill:scarlet_fairy": 1})
    r = await ura.act(U2, 1, lambda s, g: s.update(battle=None, kills={"scarlet_fairy": 1}))   # 打完那一場 (併進 kills)
    check("no double count", delta(await qs()) == {"ura_kill:scarlet_fairy": 1})
    r = await ura.act(U2, 2, lambda s, g: s.update(kills={"scarlet_fairy": 1, "scarlet_flandre": 1}))
    check(f"fest boss counted {delta(await qs())}", delta(await qs()) == {"ura_kill:scarlet_fairy": 1, "ura_kill:scarlet_flandre": 1,
                                                                         "ura_fest_boss": 1})
    lr = {"id": "fest_gungnir_shard", "rarity": "LR", "zone": 1, "fest": F}
    r = await ura.act(U2, 3, end_with("evacuated", bag={"treasures": [lr, {"id": "ura_pebble", "rarity": "N", "zone": 1}]}))
    d = delta(await qs())
    check(f"evacuate counted {d}", d.get("ura_evacuate") == 1 and d.get("ura_fest_treasure") == 1)
    check("fest treasure stored", (await ura.get_storage(U2))["treasures"].get("fest_gungnir_shard") == 1)
    r = await ura.start_run(U2, ["z1"], {}, 0, None, seed="q2")
    r = await ura.act(U2, 0, lambda s, g: s.update(battle={"killed": [fairy]}, result="failed", phase="ended",
                                                  bag={**s["bag"], "treasures": [lr]}))   # 全滅：那一場打倒的照算，其他不算
    d = delta(await qs())
    check(f"fail counts kills only {d}", d.get("ura_kill:scarlet_fairy") == 2 and d.get("ura_evacuate") == 1
          and d.get("ura_fest_treasure") == 1)

    # 🎪 每一步看「當下」有沒有活動 (紅霧異變 auto_start ➔ 沒有紀錄時就在進行)；活動結束後下一步就變成 []
    from Database import Economy_DB_Manager as econ
    r = await ura.start_run(U2, ["z1"], {}, 0, None, seed="fest")
    check(f"start live fests {r['state'].get('live_fests')}", r["ok"] and r["state"]["live_fests"] == [F])
    r = await ura.act(U2, 0, lambda s, g: None)
    check("act keeps live fests", r["ok"] and (await ura.get_run(U2))["state"]["live_fests"] == [F])
    await econ.admin_end_event(F)
    r = await ura.act(U2, 1, lambda s, g: None)
    check("event ended -> no fests", r["ok"] and (await ura.get_run(U2))["state"]["live_fests"] == [])
    await ura.act(U2, 2, lambda s, g: R.abandon(s))


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

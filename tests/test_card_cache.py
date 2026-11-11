"""🗂️ autocomplete 卡冊快取：命中、過期、各種寫入後失效、autocomplete 結果正確"""
import asyncio, os, sys, tempfile, importlib, types, sqlite3
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import discord
from discord.ext import commands
from Database import User_DB_Manager as udm
from Database import Economy_DB_Manager as econ
from Utils import card_cache

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")   # 絕不碰真實 Users.db
gacha = importlib.import_module("Cogs.load-gacha.gacha")
market = importlib.import_module("Cogs.load-market.market")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else:
        fail += 1; print("FAIL:", name)

A, B = 701, 702
def card(iid, key="reimu", rarity="SR", comp=0.5):
    p = gacha.GACHA_POOL[key]
    return {"instance_id": iid, "character_key": key, "name": p["name"], "emoji": p["emoji"],
            "rarity": rarity, "title": p["titles"][rarity], "completeness": comp, "obtained_at": "x"}

def sql(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); con.execute(q, args); con.commit(); con.close()

class Interaction:
    def __init__(s, uid=A, ns=None):
        s.user = types.SimpleNamespace(id=uid, display_name="tester")
        s.namespace = types.SimpleNamespace(**(ns or {}))

# 計算 get_user_cards 被呼叫幾次 (快取要模組內透過 udm 呼叫才算得到)
calls = {"n": 0}
_orig = udm.get_user_cards
async def counting(uid):
    calls["n"] += 1
    return await _orig(uid)
udm.get_user_cards = counting

async def ids(uid):
    return {c["instance_id"] for c in await card_cache.cached_user_cards(uid)}

async def main():
    await udm.init_db()

    # --- 命中 / 複本 ---
    await udm.add_gacha_cards(A, [card("k1"), card("k2")])
    calls["n"] = 0
    check("first read", await ids(A) == {"k1", "k2"} and calls["n"] == 1)
    check("hit no db", await ids(A) == {"k1", "k2"} and calls["n"] == 1)
    got = await card_cache.cached_user_cards(A)
    got[0]["rarity"] = "LR"; got.clear()
    check("copy not dirtied", len(await card_cache.cached_user_cards(A)) == 2
          and all(c["rarity"] == "SR" for c in await card_cache.cached_user_cards(A)))
    # 直接改資料庫 (不經資料層) ➔ TTL 內還是舊的
    sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, emoji, rarity, title, completeness, obtained_at) "
        "SELECT 'k3', user_id, character_key, name, emoji, rarity, title, completeness, obtained_at FROM gacha_cards WHERE instance_id = 'k1'")
    check("stale within ttl", await ids(A) == {"k1", "k2"})

    # --- 過期 ---
    real_now = card_cache._now
    base = real_now()
    card_cache._now = lambda: base + card_cache.CARD_CACHE_TTL + 1
    check("expired reload", await ids(A) == {"k1", "k2", "k3"})
    card_cache._now = real_now
    check("ttl ~30s", 10 <= card_cache.CARD_CACHE_TTL <= 60)

    # --- DB 路徑換了就不命中 ---
    calls["n"] = 0
    await ids(A); check("same path hit", calls["n"] == 0)
    real_path = udm.DB_PATH
    udm.DB_PATH = os.path.join(tmp, "Other.db")
    await udm.init_db()
    check("other path miss", await ids(A) == set() and calls["n"] == 1)
    udm.DB_PATH = real_path
    card_cache.invalidate_all()

    # --- 各種寫入後失效 ---
    await ids(B)
    await udm.add_gacha_cards(A, [card("k4")])
    check("add invalidates", "k4" in await ids(A))
    await udm.delete_gacha_cards(A, ["k4"])
    check("delete invalidates", "k4" not in await ids(A))
    await udm.update_cards_completeness(A, ["k1"], 1.0)
    check("update invalidates", next(c for c in await card_cache.cached_user_cards(A) if c["instance_id"] == "k1")["completeness"] == 1.0)
    consumed, new = await udm.transform_cards(A, ["k2", "k3"], lambda cs: card("k5", comp=0.9))
    check("transform invalidates", await ids(A) == {"k1", "k5"})

    def roll(since):
        return [card("k6")], since + 1, False
    await udm.add_money(A, 1000)
    await udm.draw_gacha(A, "classic", 1, 100, roll)
    check("draw invalidates", "k6" in await ids(A))

    # 失敗的寫入不影響 (也不會弄壞快取)
    try:
        await udm.transform_cards(A, ["nope"], lambda cs: card("zz"))
    except ValueError:
        pass
    check("failed transform keeps", await ids(A) == {"k1", "k5", "k6"})

    await econ.decompose_cards(A, ["k6"])
    check("decompose invalidates", "k6" not in await ids(A))

    # 市場：上架 / 下架 / 購買 / 到期 (B 要先有玩家資料才改得到簽到天數)
    await udm.add_money(B, 0)
    sql("UPDATE users SET daily_count = 7, money = 100000 WHERE user_id IN (?, ?)", (A, B))
    r = await econ.list_card(A, "k5", 100)
    check("list invalidates", r["ok"] and "k5" not in await ids(A))
    r = await econ.cancel_listing(A, r["listing"]["listing_id"])
    check("cancel invalidates", r["ok"] and "k5" in await ids(A))
    r = await econ.list_card(A, "k5", 100)
    await ids(A); await ids(B)
    r = await econ.buy_listing(B, r["listing"]["listing_id"])
    check("buy invalidates buyer", r["ok"] and "k5" in await ids(B))
    check("buy seller ok", "k5" not in await ids(A))
    r = await econ.list_card(B, "k5", 100)
    check("list B", r["ok"] and "k5" not in await ids(B))
    n = await econ.expire_listings(now=datetime.now(timezone.utc) + timedelta(days=8))
    check("expire invalidates seller", n == 1 and "k5" in await ids(B))

    await udm.clear_gacha_cards(B)
    check("clear invalidates", await ids(B) == set())

    # invalidate_all
    await ids(A)
    sql("DELETE FROM gacha_cards WHERE instance_id = 'k1'")
    card_cache.invalidate_all()
    check("invalidate_all", "k1" not in await ids(A))

    # 讀取途中卡冊變了 ➔ 不寫入快取 (不會把舊資料留 30 秒)
    card_cache.invalidate(A)
    async def racing(uid):
        rows = await _orig(uid)
        card_cache.invalidate(uid)      # 模擬讀到一半有人寫入
        return rows
    udm.get_user_cards = racing
    await card_cache.cached_user_cards(A)
    udm.get_user_cards = counting
    check("race not cached", A not in card_cache._cache)

    # --- autocomplete 結果正確 (合成 / 融合 / 市場) ---
    await udm.clear_gacha_cards(A)
    await udm.add_gacha_cards(A, [card("s1", comp=0.4), card("s2", comp=0.4),
                                  card("f1", rarity="SSR", comp=1.0), card("f2", rarity="SSR", comp=1.0),
                                  card("f3", rarity="SSR", comp=1.0)])
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    gcog = gacha.GachaCardSys(bot)
    mcog = market.MarketCog(bot)
    ch = await gcog.synthesis_pool_autocomplete(Interaction(), "")
    check(f"ac synth pool {ch}", [c.value for c in ch] == ["classic"])
    ch = await gcog.synthesis_character_autocomplete(Interaction(ns={"pool": "classic"}), "")
    check(f"ac synth char {ch}", [c.value for c in ch] == ["reimu"])
    ch = await gcog.fusion_rarity_autocomplete(Interaction(ns={"character": "reimu"}), "")
    check(f"ac fusion rarity {ch}", [c.value for c in ch] == ["SSR"])
    ch = await mcog.owned_pool_autocomplete(Interaction(), "")
    check(f"ac market pool {ch}", [c.value for c in ch] == ["classic"] and "5 張" in ch[0].name)

    calls["n"] = 0
    for _ in range(5):
        await gcog.synthesis_pool_autocomplete(Interaction(), "c")
        await mcog.owned_character_autocomplete(Interaction(ns={"pool": "classic"}), "")
    check("ac uses cache", calls["n"] == 0)

    # 融合掉之後 autocomplete 立刻更新
    await udm.transform_cards(A, ["f1", "f2", "f3"], lambda cs: card("u1", rarity="UR", comp=0.1))
    check("ac fusion after fuse", await gcog.fusion_pool_autocomplete(Interaction(), "") == [])
    ch = await mcog.owned_character_autocomplete(Interaction(ns={"pool": "classic"}), "")
    check(f"ac market count after fuse {ch}", "3 張" in ch[0].name)

    # 真正執行用的不是快取：卡被直接刪掉 ➔ 合成畫面要讀到最新
    await card_cache.cached_user_cards(A)
    sql("DELETE FROM gacha_cards WHERE instance_id = 's2'")
    r = await gcog.make_synthesis_view(A, "tester", "s1", "s2")
    check(f"execute reads db {r!r}"[:120], isinstance(r, str))

    # 快取模組不能 import Cogs
    import re
    src = open(os.path.join(ROOT, "Utils", "card_cache.py"), encoding="utf-8").read()
    check("no Cogs import", not re.search(r"^\s*(import|from)\s+Cogs", src, re.M))

asyncio.run(main())
print(f"passed {ok}, failed {fail}")

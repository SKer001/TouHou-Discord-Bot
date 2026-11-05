"""經濟系統：神社經營、浮動市值、分解、市場、轉帳、簽到天數"""
import asyncio, os, sys, shutil, tempfile, sqlite3, types
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
from Database import Economy_DB_Manager as econ

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

class Rng:
    """可控的亂數：random() 依序回傳 values (用完後回傳 last)"""
    def __init__(s, values=(), last=0.99): s.values = list(values); s.last = last
    def random(s): return s.values.pop(0) if s.values else s.last
    def choice(s, seq): return seq[0]

NEVER, ALWAYS = Rng(last=0.999), Rng(last=0.0)
T0 = datetime(2026, 11, 5, 4, 0, tzinfo=timezone.utc)   # 台灣時間 12:00
H = timedelta(hours=1)


def sql(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); con.execute(q, args); con.commit(); con.close()

def money(uid):
    con = sqlite3.connect(udm.DB_PATH); v = con.execute("SELECT money FROM users WHERE user_id=?", (uid,)).fetchone()[0]; con.close(); return v

def card(iid, key="cirno", rarity="SR", comp=0.5):
    return {"instance_id": iid, "character_key": key, "name": "琪露諾", "emoji": "🧊", "rarity": rarity, "title": "t",
            "completeness": comp, "obtained_at": "2026-11-05 12:00:00"}


async def main():
    # ---------------- 舊資料庫補欄位：現有玩家直接開通交易 ----------------
    con = sqlite3.connect(udm.DB_PATH)
    con.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, money INTEGER DEFAULT 1000, level INTEGER DEFAULT 0, exp INTEGER DEFAULT 0, last_daily TEXT, inventory TEXT DEFAULT '{}', created_at TIMESTAMP)")
    con.execute("INSERT INTO users (user_id) VALUES (500)"); con.commit(); con.close()
    await udm.init_db()
    check("backfill daily_count 7", (await econ.get_trade_status(500))["unlocked"])
    await udm.get_or_create_user(501)
    check("new user locked", (await econ.get_trade_status(501))["daily_count"] == 0)
    await udm.claim_daily(501, "2026-11-05", 3)
    await udm.claim_daily(501, "2026-11-05", 3)   # 同一天第二次不算
    await udm.claim_daily(501, "2026-11-06", 3)
    check("daily_count counts days", (await econ.get_trade_status(501))["daily_count"] == 2)

    # ---------------- 神社：純計算 ----------------
    st = econ._new_shrine(T0)
    s2 = econ.advance_shrine(st, T0 + 2 * H, NEVER)
    check(f"2h income {s2['box']}", abs(s2["box"] - 10000) < 1e-6 and s2["tick"] == 2 and s2["youkai"] == 0)
    s = econ.advance_shrine(st, T0 + 4 * H, NEVER)
    check("dirt after 4h", econ.shrine_dirt(s, T0 + 4 * H) == 1 and econ.shrine_dirt(s, T0 + 4 * H - timedelta(seconds=1)) == 0)
    s = econ.advance_shrine(st, T0 + 6 * H, NEVER)
    check(f"income drops when dirty {s['box']}", abs(s["box"] - (20000 + 2 * 4500)) < 1e-6)
    s = econ.advance_shrine(st, T0 + 100 * H, NEVER)
    check("box capped", s["box"] == econ.SHRINE_BOX_MAX and econ.shrine_dirt(s, T0 + 100 * H) == 4)
    # 妖怪：每小時一定生成 ➔ 5 小時後 5 隻、不會超過
    s = econ.advance_shrine(st, T0 + 7 * H, Rng(last=0.0))
    check(f"youkai max {s['youkai']}", s["youkai"] == 5)
    # 妖怪生成機率：0 隻時 80% (0.79 生成、0.81 不生成)
    check("youkai p 80%", econ.advance_shrine(st, T0 + H, Rng([0.79], 0.999))["youkai"] == 1)
    check("youkai p 80% miss", econ.advance_shrine(st, T0 + H, Rng([0.81], 0.999))["youkai"] == 0)
    # 參拜客：只在第 2、4…小時判定；心情每 4 小時 −10，40 小時後離開
    s = econ.advance_shrine(st, T0 + H, Rng([0.999, 0.0]))
    check("no guest at hour 1", s["guests"] == [])
    s = econ.advance_shrine(st, T0 + 2 * H, Rng([0.999, 0.999, 0.0], 0.999))
    check("guest at hour 2", len(s["guests"]) == 1 and s["guests"][0]["arrived_at"] == (T0 + 2 * H).isoformat())
    g = s["guests"][0]
    check("mood", econ.guest_mood(g, T0 + 2 * H) == 100 and econ.guest_mood(g, T0 + 6 * H) == 90 and econ.guest_mood(g, T0 + 42 * H) == 0)
    s = econ.advance_shrine(s, T0 + 50 * H, NEVER)
    check("guest leaves at 0", s["guests"] == [])
    check("serving reward", econ.serving_reward(100) == 1000 and econ.serving_reward(50) == 250 and econ.serving_reward(10, 2) == 20)
    check("efficiency floor", abs(econ.shrine_efficiency(4, 5) - 0.2) < 1e-9)
    # 很久沒來：只模擬最後 14 天，不會卡住
    s = econ.advance_shrine(st, T0 + timedelta(days=400), Rng(last=0.5))
    check("long catchup", s["box"] == econ.SHRINE_BOX_MAX)

    # ---------------- 神社：資料庫操作 ----------------
    await udm.get_or_create_user(1)
    r = await econ.get_shrine(1, now=T0, rng=NEVER)
    check("shrine created", r["summary"]["box"] == 0 and r["summary"]["efficiency"] == 1)
    r = await econ.shrine_collect(1, now=T0 + 3 * H + timedelta(minutes=30), rng=Rng([0.0], 0.999))   # 第 1 小時來一隻妖怪
    check(f"collect {r['collected']}", r["collected"] == 5000 + int(2.5 * 5000 * 0.92) and money(1) == 1000 + r["collected"])
    r = await econ.shrine_defeat(1, now=T0 + 4 * H, rng=NEVER)
    check("defeat", r["ok"] and r["summary"]["youkai"] == 0 and r["summary"]["dirt"] == 2 and money(1) == 1000 + 16500 + 1000)
    r = await econ.shrine_defeat(1, now=T0 + 4 * H, rng=NEVER)
    check("defeat none", not r["ok"])
    # 晦氣不會讓清潔度超過 4
    sql("UPDATE shrines SET youkai = 5, dirt_extra = 3")
    for _ in range(5):
        r = await econ.shrine_defeat(1, now=T0 + 4 * H, rng=NEVER)
    check(f"dirt no overflow {r['summary']['dirt']}", r["summary"]["dirt"] == 4 and r["summary"]["efficiency"] == 0.6)
    r = await econ.shrine_clean(1, now=T0 + 5 * H, rng=NEVER)
    check("clean", r["before"] == 4 and r["summary"]["dirt"] == 0 and r["summary"]["efficiency"] == 1)
    r = await econ.admin_set_shrine(1, box=12345, dirt=2, youkai=3, guests=2, guest_mood=50, now=T0 + 5 * H, rng=NEVER)
    s = r["summary"]
    check("admin shrine", s["box"] == 12345 and s["dirt"] == 2 and s["youkai"] == 3 and [g["mood"] for g in s["guests"]] == [50, 50])
    check("admin reset shrine", await econ.admin_reset_shrine(1) and (await econ.get_shrine(1, now=T0 + 5 * H, rng=NEVER))["summary"]["box"] == 0)

    # ---------------- 市值公式 ----------------
    m = econ.completeness_multiplier
    check("mult points", m(0.5) == 1 and abs(m(1) - 1.2) < 1e-9 and abs(m(0) - 0.2) < 1e-9)
    check("mult curve", m(0.75) - 1 < 0.1 and m(0.25) > 0.2 + 0.8 * 0.25 - 1)   # 越接近 1 加成越多；越接近 0 減少越少
    check("mult monotonic", all(m(i / 100) <= m((i + 1) / 100) for i in range(100)))
    pc = econ.price_change
    check("idle +2%", pc(0, 100) == 0.02)
    check("neutral 0%", abs(pc(50, 100)) < 1e-9)
    check("3x -> -10%", abs(pc(150, 100) + 0.10) < 1e-9 and abs(pc(999, 100) + 0.10) < 1e-9)
    check("under-sell between 0 and +2%", abs(pc(25, 100) - 0.01) < 1e-9)
    check("monotonic", all(pc(i, 100) >= pc(i + 1, 100) for i in range(200)))
    check("2x -> -5%", abs(pc(100, 100) + 0.05) < 1e-9)
    check("expected 0 counts as 1", abs(pc(1, 0) + 0.05) < 1e-9)

    # ---------------- 每日結算 ----------------
    probs = {("cirno", "SR"): ("th06", 0.1), ("cirno", "UR"): ("th06", 0.01)}
    check("first settle no backfill", await econ.settle_prices(probs, now=T0) == 0)
    # 11/05 (台灣) 抽了 100 抽 ➔ cirno SR 期望 10 張、持平 5 張；賣出 15 張 = 3 倍 ➔ −10%
    sql("INSERT INTO daily_draws VALUES ('2026-11-05', 'th06', 100)")
    sql("INSERT INTO daily_sales VALUES ('2026-11-05', 'cirno', 'SR', 15)")
    sql("INSERT INTO market_prices VALUES ('cirno', 'SR', 1000)")
    n = await econ.settle_prices(probs, now=T0 + timedelta(days=2))
    prices = await econ.get_market_prices()
    check(f"settle 2 days {n}", n == 2)
    check(f"sr price {prices[('cirno','SR')]}", abs(prices[("cirno", "SR")] - 1000 * 0.9 * 1.02) < 1e-6)
    await econ.admin_set_price("cirno", "SR", 777)
    check("admin set price", (await econ.get_market_prices())[("cirno", "SR")] == 777)
    await econ.admin_set_price("cirno", "SR", 1000 * 0.9 * 1.02)
    check(f"ur idle rise + floor {prices[('cirno','UR')]}", abs(prices[("cirno", "UR")] - 10000 * 1.02 * 1.02) < 1e-6)
    hist = await econ.get_price_history("cirno", "SR")
    check("history", [h["day"] for h in hist] == ["2026-11-05", "2026-11-06"] and abs(hist[0]["change"] + 0.1) < 1e-9)
    check("settle idempotent", await econ.settle_prices(probs, now=T0 + timedelta(days=2)) == 0)
    # 不會跌破官方價
    sql("INSERT INTO daily_sales VALUES ('2026-11-07', 'cirno', 'UR', 999)")
    await econ.settle_prices(probs, now=T0 + timedelta(days=3))
    check("floor official", (await econ.get_market_prices())[("cirno", "UR")] >= econ.OFFICIAL_PRICES["UR"])

    # ---------------- 分解 ----------------
    await udm.add_gacha_cards(1, [card("c_a", comp=1.0), card("c_b", comp=0.5)], draw_count=0)
    before = money(1)
    price = (await econ.get_market_prices())[("cirno", "SR")]
    r = await econ.decompose_cards(1, ["c_a", "c_b"], now=T0 + timedelta(days=3))
    check(f"decompose {r['total']}", r["total"] == round(price * 1.2) + round(price) and money(1) == before + r["total"])
    check("cards gone", await udm.get_user_cards(1) == [])
    check("sale logged", await econ.get_today_activity("cirno", "SR", now=T0 + timedelta(days=3)) == 2)
    try:
        await econ.decompose_cards(1, ["c_a"]); check("decompose twice", False)
    except ValueError:
        check("decompose twice", True)

    # ---------------- 市場 ----------------
    now = T0 + timedelta(days=3)
    await udm.get_or_create_user(2)
    await udm.add_gacha_cards(2, [card("c_s1"), card("c_s2")], draw_count=0)
    r = await econ.list_card(2, "c_s1", 1000, now=now)
    check("sell locked", not r["ok"] and r["reason"] == "locked")
    sql("UPDATE users SET daily_count = 7 WHERE user_id IN (1, 2)")
    r = await econ.list_card(2, "c_s1", 1000, now=now)
    check("listed", r["ok"] and [c["instance_id"] for c in await udm.get_user_cards(2)] == ["c_s2"])
    lid = r["listing"]["listing_id"]
    check("own buy", (await econ.buy_listing(2, lid, now=now))["reason"] == "own")
    sql("UPDATE users SET money = 1049 WHERE user_id = 1")
    check("not enough", (await econ.buy_listing(1, lid, now=now))["reason"] == "not_enough")
    sql("UPDATE users SET money = 1050 WHERE user_id = 1")
    seller_before = money(2)
    r1, r2 = await asyncio.gather(econ.buy_listing(1, lid, now=now), econ.buy_listing(1, lid, now=now))
    check("concurrent buy once", [r1["ok"], r2["ok"]].count(True) == 1)
    check("buyer paid 1.05", money(1) == 0 and money(2) == seller_before + 1000)
    check("card moved", [c["instance_id"] for c in await udm.get_user_cards(1)] == ["c_s1"])
    check("market sale logged", await econ.get_today_activity("cirno", "SR", now=now) == 3)
    check("buyer_total ceil", econ.buyer_total(1) == 2 and econ.buyer_total(100) == 105)
    # 7 天下架
    r = await econ.list_card(2, "c_s2", 5, now=now)
    check("expire not yet", await econ.expire_listings(now + timedelta(days=6)) == 0)
    sql("UPDATE users SET money = 100 WHERE user_id = 1")
    check("buy expired", (await econ.buy_listing(1, r["listing"]["listing_id"], now=now + timedelta(days=7)))["reason"] == "expired")
    check("expire", await econ.expire_listings(now + timedelta(days=7)) == 1 and len(await udm.get_user_cards(2)) == 1)
    # 自己下架
    r = await econ.list_card(2, "c_s2", 5, now=now)
    check("cancel other", not (await econ.cancel_listing(1, r["listing"]["listing_id"]))["ok"])
    check("cancel", (await econ.cancel_listing(2, r["listing"]["listing_id"]))["ok"] and len(await udm.get_user_cards(2)) == 1)
    check("listings empty", await econ.get_listings() == [])

    # ---------------- 轉帳 ----------------
    sql("UPDATE users SET money = 1000000 WHERE user_id = 1")
    await udm.get_or_create_user(3)
    check("target locked", (await econ.transfer_money(1, 3, 100, now=now))["reason"] == "target_locked")
    check("self", (await econ.transfer_money(1, 1, 100, now=now))["reason"] == "self")
    b2 = money(2)
    r = await econ.transfer_money(1, 2, 1000, now=now)
    check("transfer fee", r["ok"] and r["fee"] == 50 and money(2) == b2 + 950 and money(1) == 999000)
    check("fee ceil", econ.transfer_fee(19) == 1)
    r = await econ.transfer_money(1, 2, 499001, now=now)
    check("daily limit", not r["ok"] and r["reason"] == "limit" and r["left"] == 499000)
    check("limit exact", (await econ.transfer_money(1, 2, 499000, now=now))["ok"])
    check("next day resets", (await econ.transfer_money(1, 2, 1000, now=now + timedelta(days=1)))["ok"])
    sql("UPDATE users SET money = 10 WHERE user_id = 1")
    check("transfer not enough", (await econ.transfer_money(1, 2, 100, now=now + timedelta(days=1)))["reason"] == "not_enough")

    # ---------------- 祈願會記錄每日抽數 ----------------
    sql("UPDATE users SET money = 100000 WHERE user_id = 1")
    con = sqlite3.connect(udm.DB_PATH)
    row = con.execute("SELECT draws FROM daily_draws WHERE day = ? AND pool = 'th06'", (udm.tw_day(),)).fetchone(); con.close()
    before_draws = row[0] if row else 0
    await udm.draw_gacha(1, "th06", 10, 50000, lambda since: ([card(f"c_d{i}") for i in range(10)], since + 10, False))
    con = sqlite3.connect(udm.DB_PATH)
    n = con.execute("SELECT draws FROM daily_draws WHERE day = ? AND pool = 'th06'", (udm.tw_day(),)).fetchone()[0]; con.close()
    check("daily draws logged", n == before_draws + 10)

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

"""主動通知 (DM)：純判斷函式、開關、去重、collect_notices 整合、/notify 面板、背景 loop 不在測試裡啟動"""
import asyncio, json, os, sys, sqlite3, tempfile
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord import ui
from discord.ext import commands
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
from Database import Economy_DB_Manager as econ
from Database import Notify_DB_Manager as ndm
from Database import notify_data, shrine_data

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

H = timedelta(hours=1)
A, B, C = 111, 222, 333
EVENT = "th06_scarlet_mist"


def sql(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); con.execute(q, args); con.commit(); con.close()

def rows(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); r = con.execute(q, args).fetchall(); con.close(); return r

def summary(box=0, youkai=0, guests=()):
    return {"box": box, "box_max": econ.SHRINE_BOX_MAX, "youkai": youkai, "youkai_max": econ.YOUKAI_MAX,
            "youkai_penalty": 0.08 * youkai, "guests": list(guests)}

def kinds(notices, uid=None):
    return sorted(n["kind"] for n in notices if uid is None or n["user_id"] == uid)

def count(item):
    """元件數 (Section 的右側按鈕也算)"""
    n = 1 + sum(count(ch) for ch in getattr(item, "children", []))
    acc = getattr(item, "accessory", None)
    return n + (count(acc) if acc is not None else 0)

def walk(item):
    yield item
    for ch in getattr(item, "children", []):
        yield from walk(ch)
    if getattr(item, "accessory", None) is not None:
        yield from walk(item.accessory)

def texts(view):
    return "\n".join(i.content for top in view.children for i in walk(top) if isinstance(i, ui.TextDisplay))

def buttons(view):
    return [i for top in view.children for i in walk(top) if isinstance(i, ui.Button)]


class FakeResponse:
    def __init__(s): s.sent = []; s.done = False
    async def send_message(s, content=None, *, view=None, ephemeral=False, **kw):
        s.sent.append(("send", content, view, ephemeral, kw)); s.done = True
    async def edit_message(s, content=None, *, view=None, **kw):
        s.sent.append(("edit", content, view, None, kw)); s.done = True
    def is_done(s): return s.done

class FakeUser:
    def __init__(s, uid): s.id = uid; s.display_name = f"玩家{uid}"; s.name = s.display_name

class FakeInteraction:
    def __init__(s, uid): s.user = FakeUser(uid); s.response = FakeResponse(); s.followup = None; s.guild = None


def pure_checks(now):
    # 賽錢箱 / 妖怪：第一次看到就滿 ➔ 只記錄不通知；看過不滿再變滿 ➔ 通知；已經通知過 (watch=full) 不再通知
    n, up = ndm.check_shrine(A, summary(box=econ.SHRINE_BOX_MAX, youkai=5), now, {})
    check("box+youkai first seen full = silent", n == [])
    check("watch full", up == {"shrine_box_full": "full", "youkai_max": "full"})
    n, _ = ndm.check_shrine(A, summary(box=econ.SHRINE_BOX_MAX, youkai=5), now,
                            {"shrine_box_full": "not_full", "youkai_max": "not_full"})
    check("box+youkai become full", kinds(n) == ["shrine_box_full", "youkai_max"])
    n, _ = ndm.check_shrine(A, summary(box=econ.SHRINE_BOX_MAX, youkai=5), now, up)
    check("no repeat while full", n == [])
    n, up2 = ndm.check_shrine(A, summary(box=10, youkai=4), now, up)
    check("re-arm", n == [] and up2["shrine_box_full"] == "not_full" and up2["youkai_max"] == "not_full")
    # 參拜客：離開前 4 小時內才通知
    g = lambda gid, h: {"id": gid, "name": "人類", "emoji": "🧑", "mood": 10, "leave_at": now + h * H}
    n, _ = ndm.check_shrine(A, summary(guests=[g("a", 5), g("b", 3), g("c", 4), g("d", -1), {**g("e", 1), "id": None}]), now, {})
    check("guest window", [x["key"] for x in n] == ["b", "c"])
    check("window const", ndm.GUEST_LEAVING_WINDOW == timedelta(hours=4) and ndm.CHECK_INTERVAL_MINUTES == 10)

    # 體力：沒花過不通知；看到沒滿 ➔ spent；之後回滿通知一次
    full, part = {"stamina": 240, "max": 240}, {"stamina": 100, "max": 240}
    check("stamina never spent", ndm.check_stamina(A, full, now, {}) == ([], {}))
    n, up = ndm.check_stamina(A, part, now, {})
    check("stamina spent", n == [] and up == {"stamina_full": "spent"})
    check("stamina spent again no write", ndm.check_stamina(A, part, now, up) == ([], {}))
    n, up = ndm.check_stamina(A, full, now, {"stamina_full": "spent"})
    check("stamina full notice", kinds(n) == ["stamina_full"] and up == {"stamina_full": "full"})
    check("stamina full once", ndm.check_stamina(A, full, now, up) == ([], {}))
    check("stamina over max", kinds(ndm.check_stamina(A, {"stamina": 300, "max": 240}, now, {"stamina_full": "spent"})[0]) == ["stamina_full"])

    # 上架：不見了 + 過 7 天 = 到期；賣掉的、自己下架的不通知
    old = (now - timedelta(days=8)).isoformat()
    prev = {1: {"seller_id": A, "instance_id": "i1", "name": "琪露諾", "emoji": "🧊", "rarity": "SR", "price": 9, "listed_at": old},
            2: {"seller_id": A, "instance_id": "i2", "name": "x", "emoji": "", "rarity": "SR", "price": 9, "listed_at": old},
            3: {"seller_id": A, "instance_id": "i3", "name": "x", "emoji": "", "rarity": "SR", "price": 9,
                "listed_at": (now - timedelta(days=2)).isoformat()},
            4: {"seller_id": A, "instance_id": "i4", "name": "x", "emoji": "", "rarity": "SR", "price": 9, "listed_at": old}}
    n = ndm.check_expired(prev, {4}, {"i2"}, now)
    check("expired only 1", [x["key"] for x in n] == ["1"] and n[0]["data"]["name"] == "琪露諾")
    n = ndm.check_sales([{"trade_id": 7, "seller_id": A, "buyer_id": B, "character_key": "cirno", "rarity": "SR", "price": 100}])
    check("sale", n[0]["key"] == "7" and n[0]["user_id"] == A and n[0]["data"]["name"] == "cirno")

    # 活動：第一次看到只記錄；開始 / 結束才通知
    ev = {"id": "e", "name": "測試", "emoji": "🎪"}
    ch, st = ndm.check_events({}, [{"event": ev, "status": "active", "started_at": None}])
    check("event first seen", ch == [] and st == {"e": "active|auto"})
    ch, st = ndm.check_events(st, [{"event": ev, "status": "ended", "started_at": None}])
    check("event end", [c[0] for c in ch] == ["event_end"])
    ch, st = ndm.check_events(st, [{"event": ev, "status": "active", "started_at": "2026"}])
    check("event start", [c[0] for c in ch] == ["event_start"] and ch[0][2] == "e:2026")
    ch, _ = ndm.check_events(st, [{"event": ev, "status": "active", "started_at": "2026"}])
    check("event no change", ch == [])


async def main():
    econ.GUEST_SPAWN = [0.0] * 5   # 測試期間不會有新客人 (結果固定)
    await udm.init_db()
    await ndm.init_notify_db()
    await ndm.init_notify_db()   # 重複 init 沒問題
    now = datetime.now(timezone.utc).replace(microsecond=0)
    pure_checks(now)

    # ---------- 開關 ----------
    s = await ndm.get_settings(A)
    check("default all on", set(s) == set(notify_data.NOTIFY_TYPES) and all(s.values()))
    check("all dm now", all(i["dm"] for i in notify_data.NOTIFY_TYPES.values()))
    check("disable", await ndm.set_enabled(A, "youkai_max", False) and not (await ndm.get_settings(A))["youkai_max"])
    check("unknown kind", not await ndm.set_enabled(A, "nope", False))
    check("set_all", await ndm.set_all(C, False) == len(notify_data.NOTIFY_TYPES)
          and not any((await ndm.get_settings(C)).values()))
    await ndm.set_all(C, True)

    # ---------- 準備資料：A 有神社 (箱滿、妖怪滿、快離開的客人)、B 花了體力、C 有神社但私訊會失敗 ----------
    for uid in (A, B, C):
        await udm.add_money(uid, 0)
    kind = next(iter(shrine_data.GUESTS))
    guest = {"id": "g1", "kind": kind, "arrived_at": (now - 37 * H).isoformat(), "order": []}
    for uid, box in ((A, econ.SHRINE_BOX_MAX), (C, 0)):
        sql("INSERT INTO shrines (user_id, created_at, updated_at, tick, box, clean_at, dirt_extra, youkai, guests) "
            "VALUES (?, ?, ?, 0, ?, ?, 0, 5, ?)", (uid, now.isoformat(), now.isoformat(), box, now.isoformat(),
                                                   json.dumps([guest] if uid == A else [])))
    # 之前的檢查已經看過「沒滿」(第一次看到就滿只記錄、不通知)
    for uid in (A, C):
        for k in ("shrine_box_full", "youkai_max"):
            sql("INSERT INTO notify_watch (user_id, kind, value, updated_at) VALUES (?, ?, 'not_full', ?)",
                (uid, k, (now - H).isoformat()))
    check("spend stamina", (await udm.spend_stamina(B, 30))["ok"])
    # 上架：L1 6 天前 (之後到期)、L2 會賣出、L3 會自己下架
    def listing(lid, iid, days):
        sql("INSERT INTO market_listings (listing_id, seller_id, instance_id, character_key, name, emoji, rarity, title, "
            "completeness, obtained_at, price, listed_at) VALUES (?, ?, ?, 'cirno', '琪露諾', '🧊', 'SR', 't', 0.5, '', 1000, ?)",
            (lid, A, iid, (now - timedelta(days=days)).isoformat()))
    listing(1, "c1", 6); listing(2, "c2", 1); listing(3, "c3", 1)

    # ---------- 第 1 輪 ----------
    cog_mod = __import__("importlib").import_module("Cogs.load-general.notify")
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    calls = []
    async def sender(uid, items):
        calls.append((uid, kinds(items)))
        if uid == C:
            return False
        if uid == 999:
            raise RuntimeError("boom")
        return True

    r = await cog_mod.run_notify_once(bot, now, sender)
    got = dict(calls)
    check("A round1", got.get(A) == ["guest_leaving", "shrine_box_full"])   # 妖怪關掉了
    check("C round1 youkai", got.get(C) == ["youkai_max"])
    check("B nothing yet", B not in got)
    check("result", r == {"notices": 3, "users": 2, "sent": 1, "failed": 1})
    check("failed marked", rows("SELECT ok FROM notifications_sent WHERE user_id = ?", (C,)) == [(0,)])
    check("watch youkai A updated even if disabled",
          rows("SELECT value FROM notify_watch WHERE user_id = ? AND kind = 'youkai_max'", (A,)) == [("full",)])
    check("baseline set", rows("SELECT COUNT(*) FROM notify_watch WHERE user_id = 0 AND kind = 'baseline'") == [(1,)])
    check("event recorded", rows("SELECT value FROM notify_watch WHERE user_id = 0 AND kind = ?", (f"event:{EVENT}",)) == [("active|auto",)])
    check("snapshot 3", rows("SELECT COUNT(*) FROM notify_listings") == [(3,)])

    # 同一刻再跑：全部去重
    calls.clear()
    r = await cog_mod.run_notify_once(bot, now, sender)
    check("dedup", calls == [] and r["notices"] == 0)

    # 私訊失敗送到 log 頻道 (有 Logger 才送；沒有就略過)
    logged = []
    class FakeLogger:
        async def send_alert_log(s, title, desc, color, fields=None): logged.append((title, desc))
    class FakeBot:
        def get_cog(s, name): return FakeLogger() if name == "Logger" else None
    await cog_mod.report_failures(FakeBot(), [(C, [{"kind": "youkai_max"}])])
    check("failure logged", len(logged) == 1 and str(C) in logged[0][1] and "youkai_max" in logged[0][1])
    await cog_mod.report_failures(bot, [(C, [{"kind": "youkai_max"}])])   # 沒有 Logger 不會出錯
    check("no logger ok", len(logged) == 1)

    # ---------- 中間發生的事：L2 賣出、L3 下架、活動結束 ----------
    t2 = now + timedelta(days=2)
    sql("DELETE FROM market_listings WHERE listing_id IN (2, 3)")
    sql("INSERT INTO market_trades (kind, seller_id, buyer_id, instance_id, character_key, rarity, price, fee, day, created_at) "
        "VALUES ('market', ?, ?, 'c2', 'cirno', 'SR', 1000, 50, '2026-11-11', ?)", (A, B, (now + H).isoformat()))
    sql("INSERT INTO market_trades (kind, seller_id, buyer_id, instance_id, character_key, rarity, price, fee, day, created_at) "
        "VALUES ('market', ?, ?, 'old', 'cirno', 'SR', 1000, 50, '2026-11-01', ?)", (A, B, (now - 3 * H).isoformat()))
    check("end event", await econ.admin_end_event(EVENT, now + H) is not None)
    await ndm.set_enabled(C, "event_end", False)

    calls.clear()
    r = await cog_mod.run_notify_once(bot, t2, sender)
    got = dict(calls)
    check("A round2", got.get(A) == ["event_end", "market_expired", "market_sold"])
    check("B stamina full", got.get(B) == ["stamina_full"])
    check("C event_end disabled", C not in got)
    sold = rows("SELECT key FROM notifications_sent WHERE kind = 'market_sold'")
    check("old trade before baseline ignored", sold == [(str(rows("SELECT trade_id FROM market_trades WHERE instance_id='c2'")[0][0]),)])
    check("L1 returned to cards", rows("SELECT COUNT(*) FROM gacha_cards WHERE instance_id = 'c1'") == [(1,)])
    check("expired once", rows("SELECT key FROM notifications_sent WHERE kind = 'market_expired'") == [("1",)])

    # 活動再開始 ➔ event_start；B 沒有神社收不到
    await econ.admin_start_event(EVENT, 3, t2 + H)
    calls.clear()
    await cog_mod.run_notify_once(bot, t2 + 2 * H, sender)
    got = dict(calls)
    check("event start to shrine owners", got.get(A) == ["event_start"] and got.get(C) == ["event_start"] and B not in got)

    # 傳送時丟例外也不會掛掉
    await ndm.claim(999, "x", "y", now)
    async def bad_sender(uid, items): raise RuntimeError("boom")
    sql("UPDATE shrines SET box = ?, youkai = 0, updated_at = ? WHERE user_id = ?", (econ.SHRINE_BOX_MAX, (t2 + 2 * H).isoformat(), C))
    sql("UPDATE notify_watch SET value = 'not_full' WHERE user_id = ? AND kind = 'shrine_box_full'", (C,))
    r = await cog_mod.run_notify_once(bot, t2 + 2 * H, bad_sender)
    check("exception counted as failed", r["failed"] == 1 and r["sent"] == 0)

    # 舊紀錄 30 天後清掉
    check("prune", await ndm.prune_sent(now + timedelta(days=40)) > 0)

    # ---------- dm=False 的種類 (例如之後的特定關卡) ----------
    notify_data.NOTIFY_TYPES["stage_test"] = {"name": "測試關卡", "emoji": "🧪", "desc": "不能私訊", "dm": False}
    try:
        check("dm false off", (await ndm.get_settings(A))["stage_test"] is False)
        check("dm false cannot enable", not await ndm.set_enabled(A, "stage_test", True))
        fake = [{"user_id": A, "kind": "stage_test", "key": "1", "data": {}}]
        orig = ndm.collect_notices
        async def fake_collect(now=None): return [n for n in fake if notify_data.can_dm(n["kind"])]
        ndm.collect_notices = fake_collect
        calls.clear()
        await cog_mod.run_notify_once(bot, now, sender)
        ndm.collect_notices = orig
        check("dm false never sent", calls == [])
        v = cog_mod.NotifySettingsView(A, await ndm.get_settings(A))
        stage = [b for b in buttons(v) if b.label == "不支援私訊"]
        check("panel shows 不支援私訊", len(stage) == 1 and stage[0].disabled)
    finally:
        del notify_data.NOTIFY_TYPES["stage_test"]

    # ---------- 私訊畫面 ----------
    many = [{"user_id": A, "kind": k, "key": str(i), "data": d} for i, (k, d) in enumerate([
        ("shrine_box_full", {"box": 200000, "box_max": 200000}), ("guest_leaving", {"name": "人類", "emoji": "🧑", "mood": 10, "leave_at": now}),
        ("youkai_max", {"youkai": 5, "penalty": 0.4}), ("stamina_full", {"stamina": 240, "max": 240}),
        ("market_sold", {"name": "琪露諾", "emoji": "🧊", "rarity": "SR", "price": 1000, "buyer_id": B}),
        ("market_expired", {"name": "琪露諾", "emoji": "🧊", "rarity": "SR", "price": 1000}),
        ("event_start", {"name": "紅霧異變", "emoji": "🔴", "event_id": EVENT}), ("event_end", {"name": "紅霧異變", "emoji": "🔴", "event_id": EVENT}),
    ] * 3)]
    comps = __import__("importlib").import_module("Cogs.load-general.Components.notify_components")
    dm = ui.LayoutView(); dm.add_item(comps.build_notice_dm(many))
    check("dm components <= 40", sum(count(i) for i in dm.children) <= 40)
    check("dm footer", "/notify" in texts(dm) and "還有 12 則" in texts(dm))
    for k in notify_data.NOTIFY_TYPES:
        check(f"text {k}", notify_data.NOTIFY_TYPES[k]["name"] in comps.notice_text(next(n for n in many if n["kind"] == k)))

    # ---------- Cog：載入不啟動 loop、/notify 面板 ----------
    await bot.load_extension("Cogs.load-general.notify")
    cog = bot.get_cog("NotifyCog")
    check("loop not running in tests", not cog.notify_loop.is_running())
    check("interval", cog.notify_loop.minutes == 10)
    it = FakeInteraction(B)
    await cog.notify.callback(cog, it)
    kind_, content, view, eph, kw = it.response.sent[0]
    check("panel V2 ephemeral", isinstance(view, ui.LayoutView) and eph and content is None and "embed" not in kw)
    check("panel components <= 40", sum(count(i) for i in view.children) <= 40)
    check("panel text", "通知設定" in texts(view) and f"`{len(notify_data.NOTIFY_TYPES)} / {len(notify_data.NOTIFY_TYPES)}`" in texts(view))
    toggle = next(b for b in buttons(view) if b.custom_id == "notify:market_sold")
    it2 = FakeInteraction(B)
    check("owner ok", await view.interaction_check(it2))
    await toggle.callback(it2)
    check("toggled off", not (await ndm.get_settings(B))["market_sold"] and "已關閉" in texts(view))
    toggle = next(b for b in buttons(view) if b.custom_id == "notify:market_sold")
    check("button label off", toggle.label == "🔕 已關閉")
    off = next(b for b in buttons(view) if b.label == "全部關閉")
    await off.callback(FakeInteraction(B))
    check("all off", not any((await ndm.get_settings(B)).values()))
    on = next(b for b in buttons(view) if b.label == "全部開啟")
    await on.callback(FakeInteraction(B))
    check("all on", all((await ndm.get_settings(B)).values()))
    other = FakeInteraction(A)
    check("other user blocked", not await view.interaction_check(other) and other.response.sent)
    await bot.unload_extension("Cogs.load-general.notify")


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

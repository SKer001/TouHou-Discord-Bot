"""🏮 人里打工 (2026-11-23)：花體力換固定工錢、每天最多 2 次、台灣時間換日、活動倍率、連按不會超過次數、神社畫面"""
import asyncio, importlib, os, sys, shutil, tempfile, types
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
os.environ.setdefault("SHOW_UNRELEASED", "1")   # 🙈 測試預設看得到未公開卡池 (Utils/config.py)
from Database import User_DB_Manager as udm, Item_DB_Manager as idm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")
shutil.copy(idm.DB_PATH, os.path.join(tmp, "Item.db")); idm.DB_PATH = os.path.join(tmp, "Item.db")
from Database import Economy_DB_Manager as econ, events
import discord

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

T0 = datetime(2026, 11, 23, 3, 0, tzinfo=timezone.utc)   # 台灣時間 11:00


async def setup(uid, stamina, money=0, now=T0):
    await udm.get_or_create_user(uid)
    async with udm.connect() as db:
        await db.execute("UPDATE users SET stamina = ?, stamina_updated_at = ?, money = ?, job_day = NULL, job_used = 0 "
                         "WHERE user_id = ?", (stamina, now.isoformat(), money, uid))
        await db.commit()


async def row(uid):
    async with udm.connect() as db:
        async with db.execute("SELECT money, stamina, job_day, job_used FROM users WHERE user_id = ?", (uid,)) as cur:
            r = dict(await cur.fetchone())
        async with db.execute("SELECT value FROM player_stats WHERE user_id = ? AND stat = 'job'", (uid,)) as cur:
            s = await cur.fetchone()
    r["stat"] = s["value"] if s else 0
    return r


async def main():
    await udm.init_db()
    check("constants", (econ.JOB_STAMINA, econ.JOB_REWARD, econ.JOB_DAILY_LIMIT) == (100, 10_000, 2))
    check("modifier key", "job_reward" in events.MODIFIER_KEYS)
    sc = importlib.import_module("Cogs.load-general.Components.shrine_components")
    check("modifier names cover keys", set(sc.MODIFIER_NAMES) == set(events.MODIFIER_KEYS))

    # 體力剛好 100 ➔ 可以；99 ➔ 不行，什麼都不改
    await setup(1, 100)
    r = await econ.do_job(1, now=T0)
    st = await row(1)
    check(f"stamina exactly 100 {r}", r["ok"] and r["reward"] == 10_000 and r["jobs_left"] == 1
          and st["money"] == 10_000 and st["stamina"] == 0 and st["job_used"] == 1 and st["stat"] == 1)
    await setup(2, 99)
    r = await econ.do_job(2, now=T0)
    st = await row(2)
    check(f"stamina 99 refused {r['reason']}", not r["ok"] and r["reason"] == "stamina" and st["money"] == 0
          and st["stamina"] == 99 and st["job_used"] == 0 and st["stat"] == 0 and r["jobs_left"] == 2)

    # 一天 2 次，第 3 次被擋；台灣時間 00:00 (UTC 16:00) 換日重置
    await setup(3, 500)
    a = await econ.do_job(3, now=T0)
    b = await econ.do_job(3, now=T0 + timedelta(minutes=1))
    c = await econ.do_job(3, now=T0 + timedelta(minutes=2))
    st = await row(3)
    check("third job refused", a["ok"] and b["ok"] and b["jobs_left"] == 0 and not c["ok"] and c["reason"] == "daily_limit"
          and st["money"] == 20_000 and st["job_used"] == 2 and st["stat"] == 2)
    check("jobs left 0", await econ.get_jobs_left(3, now=T0) == 0)
    before_reset = datetime(2026, 11, 23, 15, 59, tzinfo=timezone.utc)   # 台灣時間 23:59
    after_reset = datetime(2026, 11, 23, 16, 0, tzinfo=timezone.utc)     # 台灣時間隔天 00:00
    check("same tw day still 0", await econ.get_jobs_left(3, now=before_reset) == 0
          and not (await econ.do_job(3, now=before_reset))["ok"])
    check("reset at tw midnight", await econ.get_jobs_left(3, now=after_reset) == 2)
    d = await econ.do_job(3, now=after_reset)
    check("new day job", d["ok"] and d["jobs_left"] == 1 and (await row(3))["money"] == 30_000)
    check("new player 2 left", await econ.get_jobs_left(999, now=T0) == 2)

    # 活動倍率 modifiers.job_reward
    orig = econ.get_rules
    async def boosted(now=None):
        rules = await orig(now=now)
        rules["modifiers"] = {**rules.get("modifiers", {}), "job_reward": 1.5}
        return rules
    econ.get_rules = boosted
    await setup(4, 240)
    r = await econ.do_job(4, now=T0)
    econ.get_rules = orig
    check(f"event modifier {r['reward']}", r["ok"] and r["reward"] == 15_000 and (await row(4))["money"] == 15_000
          and econ.job_reward({"modifiers": {"job_reward": 2}}) == 20_000 and econ.job_reward(None) == 10_000)

    # 連按：一起送出 3 次 (體力夠 3 次) ➔ 只有 2 次成功；體力只夠 1 次時一起送 2 次 ➔ 只成功 1 次
    await setup(5, 300)
    rs = await asyncio.gather(*[econ.do_job(5, now=T0) for _ in range(3)])
    st = await row(5)
    check(f"concurrent capped by daily limit {[x['ok'] for x in rs]}", sum(x["ok"] for x in rs) == 2
          and st["money"] == 20_000 and st["stamina"] == 100 and st["job_used"] == 2 and st["stat"] == 2)
    await setup(6, 150)
    rs = await asyncio.gather(*[econ.do_job(6, now=T0) for _ in range(2)])
    st = await row(6)
    check("concurrent capped by stamina", sum(x["ok"] for x in rs) == 1 and st["money"] == 10_000 and st["stamina"] == 50)
    # 從滿的掉下來：從現在開始計時 (跟採集一樣)
    await setup(7, udm.STAMINA_MAX)
    r = await econ.do_job(7, now=T0)
    check("stamina from full", r["ok"] and r["stamina"]["stamina"] == udm.STAMINA_MAX - 100 and r["stamina"]["next_in"] > 0)

    # ---------------- 神社畫面 ----------------
    shrine_mod = importlib.import_module("Cogs.load-general.shrine")

    class Resp:
        def __init__(s, it): s.it = it; s.done = False
        def is_done(s): return s.done
        async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
        async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
        async def defer(s, **kw): s.done = True
        async def send_modal(s, m): s.done = True; s.it.modal = m
    class Followup:
        def __init__(s, it): s.it = it
        async def send(s, content=None, **kw): assert content is None; s.it.view = kw.get("view"); return None
    class It:
        def __init__(s, uid, data=None):
            s.user = types.SimpleNamespace(id=uid, display_name="t"); s.data = data or {}
            s.response, s.followup, s.view, s.modal = Resp(s), Followup(s), None, None
    def btns(v): return {b.label: b for b in v.walk_children() if isinstance(b, discord.ui.Button)}
    def btn(v, prefix): return next((b for label, b in btns(v).items() if label.startswith(prefix)), None)
    def vtext(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))

    uid = 10
    await setup(uid, 120, now=datetime.now(timezone.utc))
    user = types.SimpleNamespace(id=uid, display_name="t")
    view = await shrine_mod.ShrineView.create(user, await econ.get_shrine(uid))
    check("main has job button", btn(view, "🏮 人里打工") is not None)
    await btn(view, "🏮 人里打工").callback(It(uid))
    b = btn(view, "🏮 花 100 體力")
    check(f"job screen {b and b.label}", view.mode == "job" and b and not b.disabled and "10,000 賽錢" in b.label
          and "今天還能 2 次" in b.label and btn(view, "⚡ 恢復體力") and btn(view, "🏠 返回神社") and "🏮 人里打工" in vtext(view)
          and sum(1 for _ in view.walk_children()) <= 40)
    await b.callback(It(uid))
    b = btn(view, "🏮 花 100 體力")
    check(f"job done + stamina short {vtext(view)[-120:]}", "跑完腿了" in vtext(view) and "`10,000`" in vtext(view)
          and b.disabled and "今天還能 1 次" in b.label and "體力不夠" in vtext(view))
    await btn(view, "⚡ 恢復體力").callback(It(uid))
    async with udm.connect() as db:   # 體力補回來，再打一次 ➔ 打完了
        await db.execute("UPDATE users SET stamina = 240, stamina_updated_at = ? WHERE user_id = ?",
                         (datetime.now(timezone.utc).isoformat(), uid))
        await db.commit()
    await view.on_job_open(It(uid))
    await btn(view, "🏮 花 100 體力").callback(It(uid))
    b = btn(view, "🏮 花 100 體力")
    check("job used up", b.disabled and "今天還能 0 次" in b.label and "已經打完了" in vtext(view))
    await b.callback(It(uid))   # 反灰還是被按到 (舊畫面) ➔ 資料層擋下
    check("refused when used up", "已經打完了" in vtext(view) and (await row(uid))["job_used"] == 2)
    # /shrine job 直接打開
    bot = __import__("discord.ext.commands", fromlist=["x"]).Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.shrine")
    cog = bot.get_cog("ShrineCog")
    cmd = next(c for c in cog.walk_app_commands() if c.name == "job")
    it = It(uid); await cmd.callback(cog, it)
    check(f"/shrine job {cmd.description}", it.view is not None and it.view.mode == "job" and len(cmd.description) <= 100)


asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

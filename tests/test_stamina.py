import asyncio, os, sys, shutil, tempfile
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
from Database import User_DB_Manager as udm

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
iso = lambda d: d.isoformat()

async def set_raw(uid, stamina, updated):
    async with udm.connect() as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
        await db.execute("UPDATE users SET stamina = ?, stamina_updated_at = ? WHERE user_id = ?", (stamina, updated, uid))
        await db.commit()

async def main():
    await udm.init_db()
    c = udm.calc_stamina
    # 純計算
    r = c(None, None, T0); check("new user full", r["stamina"] == 240 and r["next_in"] == 0)
    r = c(100, iso(T0), T0 + timedelta(minutes=5, seconds=59)); check("5:59 no tick", r["stamina"] == 100 and r["next_in"] == 1)
    r = c(100, iso(T0), T0 + timedelta(minutes=6)); check("6:00 +1", r["stamina"] == 101 and r["next_in"] == 360)
    r = c(100, iso(T0), T0 + timedelta(minutes=63)); check("63min +10 remainder kept", r["stamina"] == 110 and r["next_in"] == 180
                                                           and r["updated_at"] == iso(T0 + timedelta(minutes=60)))
    r = c(100, iso(T0), T0 + timedelta(minutes=63)); check(f"full_in {r['full_in']}", r["full_in"] == 180 + 129 * 360)
    r = c(230, iso(T0), T0 + timedelta(days=3)); check("cap 240", r["stamina"] == 240 and r["full_in"] == 0)
    r = c(300, iso(T0), T0 + timedelta(days=3)); check("over cap no regen", r["stamina"] == 300)
    r = c(100, iso(T0), T0 - timedelta(minutes=30)); check("clock skew safe", r["stamina"] == 100)

    # 使用 / 回復
    r = await udm.spend_stamina(1, 30); check("spend from full", r["ok"] and r["stamina"] == 210 and 359 <= r["next_in"] <= 360)
    r = await udm.spend_stamina(1, 500); check("not enough", not r["ok"] and r["stamina"] == 210)
    check("not enough unchanged", (await udm.get_stamina(1))["stamina"] == 210)
    r = await udm.add_stamina(1, 100); check("add over cap", r["stamina"] == 310 and r["next_in"] == 0)
    r = await udm.spend_stamina(1, 100); check("over cap spend", r["stamina"] == 210)
    r = await udm.add_stamina(1, -1000); check("floor 0", r["stamina"] == 0)

    # 經過時間後使用：先結算再扣，零頭保留
    await set_raw(2, 50, iso(datetime.now(timezone.utc) - timedelta(minutes=63)))
    r = await udm.spend_stamina(2, 5); check(f"settle then spend {r['stamina']}", r["stamina"] == 55 and 170 <= r["next_in"] <= 180)
    await set_raw(3, 238, iso(datetime.now(timezone.utc) - timedelta(minutes=30)))
    r = await udm.spend_stamina(3, 10); check(f"full then spend restarts clock {r}", r["stamina"] == 230 and r["next_in"] >= 359)

    # 併發扣：只能成功能扣的次數
    await set_raw(4, 25, iso(datetime.now(timezone.utc)))
    rs = await asyncio.gather(*[udm.spend_stamina(4, 10) for _ in range(5)])
    check("concurrent spend", sum(r["ok"] for r in rs) == 2 and (await udm.get_stamina(4))["stamina"] == 5)
    check("get_stamina no user", (await udm.get_stamina(999))["stamina"] == 240)

    # 資料卡顯示
    from importlib import import_module
    gc = import_module("Cogs.load-general.Components.general_components")
    check("text full", "已回滿" in gc._stamina_text(c(240, None)))
    t = gc._stamina_text(c(100, iso(T0), T0 + timedelta(minutes=63)))
    check(f"text partial {t}", "`110 / 240`" in t and "3 分 0 秒" in t and "小時" in t)

    # 資料卡實際組出來 (含體力)
    import types, discord
    avatar = types.SimpleNamespace(with_size=lambda n: types.SimpleNamespace(url="https://x/a.png"))
    user = types.SimpleNamespace(display_name="測試", display_avatar=avatar)
    data = await udm.get_or_create_user(2)
    stamina = c(data["stamina"], data["stamina_updated_at"])
    container = gc.build_profile_container(user, data, {"signed_today": False, "fortune_level": None},
                                           discord.Color.blue(), is_self=True, stamina=stamina)
    view = discord.ui.LayoutView(); view.add_item(container)
    t = "\n".join(i.content for i in view.walk_children() if isinstance(i, discord.ui.TextDisplay))
    check("profile shows stamina", "⚡ **體力**" in t and "`55 / 240`" in t)

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
shutil.rmtree(tmp, ignore_errors=True)

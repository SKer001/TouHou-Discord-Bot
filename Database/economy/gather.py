"""
🏮 人里打工、🗺️ 採集 / 🍳 料理 / 🏪 雜貨店 / 🍵 招待、🧺 快速採集

從 Database/Economy_DB_Manager.py 拆出來的；外面一律照舊從 Database.Economy_DB_Manager 匯入 (入口)，不要直接匯入這裡。
"""
import json
import math
import random
from datetime import datetime, timezone

from Database.User_DB_Manager import connect, _ensure_user, _load_inventory, tw_day, calc_stamina, STAMINA_MAX, add_player_stat, add_quest_stats
from Database import shrine_data
from Database.events import game_rules
from Database.economy.common import modifier
from Database.economy.event_state import _active_events, get_rules
from Database.economy.shrine import _shrine_tx, calc_serve_reward, explore_cost, guest_mood

# =========================================================
# 🏮 人里打工 (2026-11-23 使用者定)：花體力換固定工錢，每天最多 2 次 (台灣時間 00:00 重置)
#   限 2 次 = 2 萬 = 剛好一天自然回復的 240 體力；不設上限的話「做體力料理 ➔ 吃 ➔ 打工」會變成印鈔流程
#   不吃神社效率；活動倍率 modifiers.job_reward
# =========================================================
JOB_STAMINA = 100
JOB_REWARD = 10_000
JOB_DAILY_LIMIT = 2


def job_reward(rules: dict | None) -> int:
    """這一刻打工一次拿多少 (含活動倍率)"""
    return int(round(JOB_REWARD * modifier(rules, "job_reward")))


def jobs_left(day: str | None, used: int | None, now: datetime | None = None) -> int:
    """(純計算) 今天還能打工幾次；job_day 不是今天 = 今天還沒打過"""
    if day != tw_day(now):
        return JOB_DAILY_LIMIT
    return max(0, JOB_DAILY_LIMIT - (used or 0))


async def get_jobs_left(user_id: int, now: datetime | None = None) -> int:
    """今天還能打工幾次 (唯讀)"""
    async with connect() as db:
        async with db.execute("SELECT job_day, job_used FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
    return jobs_left(row["job_day"], row["job_used"], now) if row else JOB_DAILY_LIMIT


async def do_job(user_id: int, now: datetime | None = None) -> dict:
    """
    🏮 打工一次：扣 JOB_STAMINA 體力、加工錢、今天次數 +1、記 player_stats job，同一個交易 (連按兩下也不會超過次數 / 體力)
    失敗什麼都不改：reason = daily_limit (今天打完了) / stamina (體力不夠)
    回傳 {"ok", "reward", "money", "jobs_left", "stamina" (calc_stamina 的結果)}
    """
    now = now or datetime.now(timezone.utc)
    reward = job_reward(await get_rules(now=now))
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_user(db, user_id)
            async with db.execute("SELECT money, stamina, stamina_updated_at, job_day, job_used FROM users WHERE user_id = ?",
                                  (user_id,)) as cursor:
                row = await cursor.fetchone()
            info = calc_stamina(row["stamina"], row["stamina_updated_at"], now)
            left = jobs_left(row["job_day"], row["job_used"], now)
            fail = "daily_limit" if left <= 0 else "stamina" if info["stamina"] < JOB_STAMINA else None
            if fail:
                await db.rollback()
                return {"ok": False, "reason": fail, "jobs_left": left, "stamina": info, "money": row["money"], "reward": reward}
            new_value = info["stamina"] - JOB_STAMINA
            updated_at = now.isoformat() if info["stamina"] >= STAMINA_MAX else info["updated_at"]   # 從滿掉下來 ➔ 從現在開始計時
            used_today = JOB_DAILY_LIMIT - left + 1
            await db.execute("UPDATE users SET stamina = ?, stamina_updated_at = ?, money = money + ?, job_day = ?, job_used = ? "
                             "WHERE user_id = ?", (new_value, updated_at, reward, tw_day(now), used_today, user_id))
            await add_player_stat(db, user_id, "job")   # 之後可以做打工稱號
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "reward": reward, "money": row["money"] + reward, "jobs_left": left - 1,
            "stamina": calc_stamina(new_value, updated_at, now)}


# =========================================================
# 🗺️ 採集 / 🍳 料理 / 🏪 雜貨店 / 🍵 招待
# =========================================================
async def _read_user(db, user_id: int) -> dict:
    await _ensure_user(db, user_id)
    async with db.execute("SELECT money, inventory, stamina, stamina_updated_at FROM users WHERE user_id = ?", (user_id,)) as cursor:
        row = dict(await cursor.fetchone())
    row["inventory"] = _load_inventory(row["inventory"])
    return row


async def _write_inventory(db, user_id: int, inv: dict):
    inv = {k: v for k, v in inv.items() if v > 0}
    await db.execute("UPDATE users SET inventory = ? WHERE user_id = ?", (json.dumps(inv, ensure_ascii=False), user_id))


def roll_explore(location: dict, rng=random, special_chance: float | None = None) -> dict:
    """
    一趟採集 (純計算)：3~5 個素材，special_chance (預設 SPECIAL_CHANCE) 機率發生事件 (好壞各半)
    good / bad 可以是一個事件或事件池 (活動可以加進去，見 events.game_rules)
    """
    lo, hi = shrine_data.EXPLORE_DROPS
    n = lo + int(rng.random() * (hi - lo + 1))
    drops = {}
    for _ in range(n):
        m = rng.choice(location["drops"])
        drops[m] = drops.get(m, 0) + 1
    event = None
    if rng.random() < (shrine_data.SPECIAL_CHANCE if special_chance is None else special_chance):
        good = rng.random() < 0.5
        pool = location["good" if good else "bad"]
        pool = pool if isinstance(pool, list) else [pool]
        ev = pool[0] if len(pool) == 1 else rng.choice(pool)
        fx = ev["effect"]
        for m, k in fx.get("add", {}).items():
            drops[m] = drops.get(m, 0) + k
        if fx.get("empty"):
            drops = {}
        if fx.get("half"):
            drops = {m: k // 2 for m, k in drops.items() if k // 2 > 0}
        for _ in range(fx.get("lose", 0)):
            if drops:
                m = rng.choice(sorted(drops))
                drops[m] -= 1
                if drops[m] <= 0:
                    del drops[m]
        event = {"good": good, "text": ev["text"]}
    return {"drops": drops, "event": event}


async def _add_event_stats(db, user_id: int, runs: list[dict]):
    """(交易裡) 這幾趟遇到的好 / 壞事件次數 ➔ player_stats explore_good / explore_bad (0.35.005 起)"""
    good = sum(1 for r in runs if r.get("event") and r["event"]["good"])
    bad = sum(1 for r in runs if r.get("event") and not r["event"]["good"])
    await add_player_stat(db, user_id, "explore_good", good)
    await add_player_stat(db, user_id, "explore_bad", bad)


async def explore(user_id: int, location_id: str, times: int = 1, now: datetime | None = None, rng=random) -> dict:
    """
    採集 times 趟 (體力不夠時做到體力用完為止，至少要夠 1 趟)
    失敗 reason：not_found (地點不存在 / 活動地點已關閉)、no_stamina
    """
    now = now or datetime.now(timezone.utc)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            rules = game_rules(await _active_events(db, now))
            cost = explore_cost(rules)
            location = rules["locations"].get(location_id)
            if location is None:
                await db.rollback()
                return {"ok": False, "reason": "not_found"}
            user = await _read_user(db, user_id)
            info = calc_stamina(user["stamina"], user["stamina_updated_at"], now)
            runs = min(max(1, times), info["stamina"] // cost)
            if runs <= 0:
                await db.rollback()
                return {"ok": False, "reason": "no_stamina", "stamina": info["stamina"], "cost": cost}
            results, total = [], {}
            for _ in range(runs):
                r = roll_explore(location, rng, rules["special_chance"])
                results.append(r)
                for m, k in r["drops"].items():
                    total[m] = total.get(m, 0) + k
            inv = user["inventory"]
            for m, k in total.items():
                inv[m] = inv.get(m, 0) + k
            await _write_inventory(db, user_id, inv)
            updated_at = now.isoformat() if info["stamina"] >= STAMINA_MAX else info["updated_at"]
            new_stamina = info["stamina"] - runs * cost
            await db.execute("UPDATE users SET stamina = ?, stamina_updated_at = ? WHERE user_id = ?", (new_stamina, updated_at, user_id))
            await add_player_stat(db, user_id, "explore", runs)   # 📊 實際採集的趟數
            await add_player_stat(db, user_id, f"explore:{location_id}", runs)   # 🗺️ 每個地點的趟數 (足跡稱號；0.35.003 起)
            await _add_event_stats(db, user_id, results)   # 🍀 好 / 壞事件次數 (運氣稱號)
            await add_quest_stats(db, user_id, now, {f"explore:{location_id}": runs})   # 🎪 活動任務：在這個地點採集的趟數
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "location": location, "runs": results, "total": total,
            "stamina": calc_stamina(new_stamina, updated_at, now), "requested": times}


# ---------------------------------------------------------
# 🧺 快速採集 (料理畫面缺素材時，0.35.000)：總共 N 趟，每趟去「最缺」的地點，夠了換下一個、全部夠了提早停
# ---------------------------------------------------------
def expected_per_trip(location: dict, material: str) -> float:
    """一趟平均帶回幾個這種素材 (不算好壞事件)：平均掉落數 × 這種素材在掉落表的比例"""
    drops = location.get("drops") or []
    if material not in drops:
        return 0.0
    lo, hi = shrine_data.EXPLORE_DROPS
    return (lo + hi) / 2 * drops.count(material) / len(drops)


def best_location(material: str, rules: dict) -> str | None:
    """最容易採到這種素材的地點 (一趟平均拿最多)；一樣多時照地點的順序；沒有地點採得到 ➔ None"""
    best, best_e = None, 0.0
    for key, loc in rules["locations"].items():
        e = expected_per_trip(loc, material)
        if e > best_e:
            best, best_e = key, e
    return best


def missing_materials(recipe: dict, inventory: dict, pots: int = 1) -> dict:
    """做 pots 鍋還差的素材 {素材: 還差幾個}"""
    return {m: k * pots - inventory.get(m, 0) for m, k in recipe.items() if inventory.get(m, 0) < k * pots}


def plan_gather(missing: dict, rules: dict) -> dict:
    """
    (純計算) 缺的素材 ➔ 要去哪裡、大概要幾趟 (畫面上的「計算過程」)
    {"stops": [{"location", "materials" {素材: 還差}, "per_trip" {素材: 一趟平均幾個}, "trips" 預估趟數}, ...]  ← 最缺 (要跑最多趟) 的在前
     "unavailable": {素材: 還差} (現在沒有地點採得到，例如活動素材), "trips": 預估總趟數}
    """
    stops, unavailable = {}, {}
    for m, n in missing.items():
        loc = best_location(m, rules)
        if loc is None:
            unavailable[m] = n
            continue
        stop = stops.setdefault(loc, {"location": loc, "materials": {}, "per_trip": {}, "trips": 0})
        e = expected_per_trip(rules["locations"][loc], m)
        stop["materials"][m] = n
        stop["per_trip"][m] = e
        stop["trips"] = max(stop["trips"], math.ceil(n / e))
    ordered = sorted(stops.values(), key=lambda s: -s["trips"])
    return {"stops": ordered, "unavailable": unavailable, "trips": sum(s["trips"] for s in ordered)}


def shop_missing(missing: dict, rules: dict) -> tuple[dict, int]:
    """(純計算) 缺的素材裡雜貨店有賣的 ➔ ({素材: 數量}, 總價)"""
    buy = {m: n for m, n in missing.items() if m in rules["shop"]}
    return buy, sum(rules["shop"][m] * n for m, n in buy.items())


async def quick_explore(user_id: int, recipe: dict, times: int, pots: int = 1,
                        now: datetime | None = None, rng=random) -> dict:
    """
    快速採集：為了做 pots 鍋 recipe，總共最多採 times 趟
    每趟都重新算還差什麼，去最缺的地點；全部夠了就提早停，體力不夠一趟也會停 (stopped = done / times / no_stamina / unavailable)
    失敗 reason：nothing_missing (素材已經夠了) / unavailable (缺的素材現在都採不到) / no_stamina
    成功：runs [{location, drops, event}], total, missing (採完還差的), stopped, stamina, requested
    """
    now = now or datetime.now(timezone.utc)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            rules = game_rules(await _active_events(db, now))
            cost = explore_cost(rules)
            user = await _read_user(db, user_id)
            inv = user["inventory"]
            info = calc_stamina(user["stamina"], user["stamina_updated_at"], now)
            missing = missing_materials(recipe, inv, pots)
            if not missing:
                await db.rollback()
                return {"ok": False, "reason": "nothing_missing"}
            if not plan_gather(missing, rules)["stops"]:
                await db.rollback()
                return {"ok": False, "reason": "unavailable", "missing": missing}
            if info["stamina"] < cost:
                await db.rollback()
                return {"ok": False, "reason": "no_stamina", "stamina": info["stamina"], "cost": cost}
            stamina, runs, total, per_loc, stopped = info["stamina"], [], {}, {}, "times"
            for _ in range(max(1, times)):
                plan = plan_gather(missing_materials(recipe, inv, pots), rules)
                if not plan["stops"]:
                    stopped = "unavailable" if plan["unavailable"] else "done"
                    break
                if stamina < cost:
                    stopped = "no_stamina"
                    break
                loc_id = plan["stops"][0]["location"]
                r = roll_explore(rules["locations"][loc_id], rng, rules["special_chance"])
                runs.append({**r, "location": loc_id})
                for m, k in r["drops"].items():
                    total[m] = total.get(m, 0) + k
                    inv[m] = inv.get(m, 0) + k
                stamina -= cost
                per_loc[loc_id] = per_loc.get(loc_id, 0) + 1
            left = missing_materials(recipe, inv, pots)
            if not left:
                stopped = "done"
            await _write_inventory(db, user_id, inv)
            updated_at = now.isoformat() if info["stamina"] >= STAMINA_MAX else info["updated_at"]
            await db.execute("UPDATE users SET stamina = ?, stamina_updated_at = ? WHERE user_id = ?", (stamina, updated_at, user_id))
            await add_player_stat(db, user_id, "explore", len(runs))   # 📊 跟一般採集一樣算趟數
            for k, n in per_loc.items():
                await add_player_stat(db, user_id, f"explore:{k}", n)   # 🗺️ 每個地點的趟數 (足跡稱號)
            await _add_event_stats(db, user_id, runs)   # 🍀 好 / 壞事件次數 (運氣稱號)
            await add_quest_stats(db, user_id, now, {f"explore:{k}": n for k, n in per_loc.items()})   # 🎪 活動任務
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "runs": runs, "total": total, "missing": left, "stopped": stopped,
            "stamina": calc_stamina(stamina, updated_at, now), "requested": times}


async def shop_buy_missing(user_id: int, recipe: dict, pots: int = 1, now: datetime | None = None) -> dict:
    """
    🏪 用賽錢買齊：只買做 pots 鍋還缺、而且雜貨店有賣的素材 (同一個交易)
    失敗 reason：nothing_to_buy / not_enough (money, cost)
    """
    now = now or datetime.now(timezone.utc)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            rules = game_rules(await _active_events(db, now))
            user = await _read_user(db, user_id)
            inv = user["inventory"]
            buy, cost = shop_missing(missing_materials(recipe, inv, pots), rules)
            if not buy:
                await db.rollback()
                return {"ok": False, "reason": "nothing_to_buy"}
            if user["money"] < cost:
                await db.rollback()
                return {"ok": False, "reason": "not_enough", "money": user["money"], "cost": cost}
            for m, n in buy.items():
                inv[m] = inv.get(m, 0) + n
            await _write_inventory(db, user_id, inv)
            await db.execute("UPDATE users SET money = money - ? WHERE user_id = ?", (cost, user_id))
            await add_player_stat(db, user_id, "shop")   # 📊
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "bought": buy, "cost": cost, "money": user["money"] - cost,
            "missing": missing_materials(recipe, inv, pots)}


async def cook(user_id: int, dish_id: str, times: int = 1, now: datetime | None = None) -> dict:
    """料理 times 鍋 (每鍋 COOK_YIELD 份，體力料理 STAMINA_COOK_YIELD 份)；素材不夠 ➔ reason=not_enough + missing {素材: 還差幾個}"""
    now = now or datetime.now(timezone.utc)
    times = max(1, times)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            rules = game_rules(await _active_events(db, now))
            recipe = rules["recipes"].get(dish_id)
            if recipe is None:
                await db.rollback()
                return {"ok": False, "reason": "not_found"}
            user = await _read_user(db, user_id)
            inv = user["inventory"]
            missing = {m: k * times - inv.get(m, 0) for m, k in recipe.items() if inv.get(m, 0) < k * times}
            if missing:
                await db.rollback()
                return {"ok": False, "reason": "not_enough", "missing": missing}
            for m, k in recipe.items():
                inv[m] -= k * times
            made = shrine_data.cook_yield(dish_id, rules) * times
            inv[dish_id] = inv.get(dish_id, 0) + made
            await _write_inventory(db, user_id, inv)
            await add_player_stat(db, user_id, "cook", times)   # 📊 鍋數
            await add_player_stat(db, user_id, f"cook:{dish_id}", times)   # 🍳 每道料理的鍋數 (美食家稱號；0.35.007 起)
            await add_quest_stats(db, user_id, now, {f"cook:{dish_id}": times})   # 🎪 活動任務：做過哪些料理 (鍋數)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "made": made, "have": inv[dish_id]}


async def shop_buy(user_id: int, material_id: str, qty: int, now: datetime | None = None) -> dict:
    """雜貨店買素材 (商品 = 一般 + 活動商品 rules["shop"])；reason：not_found / bad_qty / not_enough"""
    now = now or datetime.now(timezone.utc)
    if qty < 1:
        return {"ok": False, "reason": "bad_qty"}
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            price = game_rules(await _active_events(db, now))["shop"].get(material_id)
            if price is None:
                await db.rollback()
                return {"ok": False, "reason": "not_found"}
            cost = price * qty
            user = await _read_user(db, user_id)
            if user["money"] < cost:
                await db.rollback()
                return {"ok": False, "reason": "not_enough", "money": user["money"], "cost": cost}
            inv = user["inventory"]
            inv[material_id] = inv.get(material_id, 0) + qty
            await _write_inventory(db, user_id, inv)
            await db.execute("UPDATE users SET money = money - ? WHERE user_id = ?", (cost, user_id))
            await add_player_stat(db, user_id, "shop")   # 📊
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "cost": cost, "money": user["money"] - cost, "have": inv[material_id]}


async def serve_guest(user_id: int, guest_id: str, extra: str | None = None, now: datetime | None = None, rng=random) -> dict:
    """
    招待一位客人：點的料理每道扣 1 份 (一定要齊)，額外招待可以再端 1 份任意料理；客人拿到後離開
    失敗 reason：not_found (客人已經離開) / missing (料理不夠，missing = {料理: 還差幾份}) / bad_extra
    """
    now = now or datetime.now(timezone.utc)

    async def action(state, db, rules):
        guest = next((g for g in state["guests"] if g.get("id") == guest_id), None)
        if guest is None:
            return {"ok": False, "reason": "not_found"}
        if extra and extra not in rules["dish_types"]:
            return {"ok": False, "reason": "bad_extra"}
        mood = guest_mood(guest, now)
        need = {}
        for d in guest["order"] + ([extra] if extra else []):
            need[d] = need.get(d, 0) + 1
        user = await _read_user(db, user_id)
        inv = user["inventory"]
        missing = {d: k - inv.get(d, 0) for d, k in need.items() if inv.get(d, 0) < k}
        if missing:
            return {"ok": False, "reason": "missing", "missing": missing}
        favorite = rules["guests"].get(guest["kind"], {}).get("favorite")
        reward = calc_serve_reward(mood, guest["order"], extra, rules, favorite)
        for d, k in need.items():
            inv[d] -= k
        await _write_inventory(db, user_id, inv)
        await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (reward["total"], user_id))
        await add_player_stat(db, user_id, "serve")   # 📊
        await add_player_stat(db, user_id, f"serve_guest:{guest['kind']}")   # 🙏 每種客人的招待次數 (客人稱號 SR；0.35.001 起)
        if reward["favorite_hit"]:   # 成功招待 = 額外端上客人最愛的料理
            await add_player_stat(db, user_id, "serve_favorite")
            await add_player_stat(db, user_id, f"serve_fav:{guest['kind']}")   # 🙏 客人稱號 UR
        # 🎪 活動任務：招待哪種客人、成功招待、端出「那個活動的」活動料理份數
        served = guest["order"] + ([extra] if extra else [])
        per_event = {}
        for d in served:
            eid = rules["event_dishes"].get(d)
            if eid:
                per_event.setdefault(eid, {"serve_event_dish": 0})["serve_event_dish"] += 1
        await add_quest_stats(db, user_id, now, {f"serve_guest:{guest['kind']}": 1,
                                                 "serve_favorite": 1 if reward["favorite_hit"] else 0}, per_event)
        state["guests"] = [g for g in state["guests"] if g.get("id") != guest_id]
        return {"ok": True, "reward": reward, "mood": mood, "guest": guest, "extra": extra,
                "money": user["money"] + reward["total"]}
    return await _shrine_tx(user_id, action, now, rng)


async def get_inventory(user_id: int) -> dict:
    async with connect() as db:
        async with db.execute("SELECT inventory FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
    return _load_inventory(row["inventory"]) if row else {}

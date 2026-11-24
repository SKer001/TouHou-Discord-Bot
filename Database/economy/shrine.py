"""
⛩️ 神社經營：賽錢箱、清潔度、妖怪、參拜客的結算與操作

從 Database/Economy_DB_Manager.py 拆出來的；外面一律照舊從 Database.Economy_DB_Manager 匯入 (入口)，不要直接匯入這裡。
"""
import json
import random
from datetime import datetime, timedelta, timezone

from Database.User_DB_Manager import connect, _ensure_user, add_player_stat
from Database import shrine_data
from Database.events import game_rules, all_guests, pick_line
from Database.economy.common import (
    DIRT_INTERVAL, DIRT_MAX, DIRT_PENALTY, FAVORITE_BONUS, GUEST_EVERY_HOURS, GUEST_MAX, GUEST_SPAWN, HOUR,
    MOOD_INTERVAL, MOOD_STEP, ORDER_SIZE, SERVE_TYPES_ORDER, SERVING_REWARD, SHRINE_BOX_MAX, SHRINE_INCOME_PER_HOUR, SHRINE_MAX_CATCHUP,
    YOUKAI_MAX, YOUKAI_PENALTY, YOUKAI_REWARD, YOUKAI_SPAWN, _dt, modifier,
)
from Database.economy.event_state import _active_events

# =========================================================
# ⛩️ 1. 神社經營
# =========================================================
def shrine_dirt(state: dict, t: datetime) -> int:
    """t 時的清潔度階段 (0 乾淨 ~ 4)：距離上次清掃每 4 小時 +1，再加上妖怪留下的晦氣"""
    base = int((t - _dt(state["clean_at"])) / DIRT_INTERVAL)
    return min(DIRT_MAX, max(0, base) + state["dirt_extra"])


def shrine_efficiency(dirt: int, youkai: int) -> float:
    return max(0.0, 1 - DIRT_PENALTY * dirt - YOUKAI_PENALTY * youkai)


def guest_mood(guest: dict, t: datetime) -> int:
    """參拜客心情 (%)：來的時候 100，每 4 小時 −10"""
    steps = int((t - _dt(guest["arrived_at"])) / MOOD_INTERVAL)
    return max(0, 100 - MOOD_STEP * steps)


def serving_reward(mood: int, portions: int = 1) -> int:
    """招待報酬 (不含加成)：每份 2000 × 心情²；跟實際入帳 (calc_serve_reward) 一樣四捨五入 (2026-11-23：原本截斷，心情 70% 寫 979 實拿 980)"""
    return int(round(SERVING_REWARD * (mood / 100) ** 2 * portions))


def calc_serve_reward(mood: int, order: list[str], extra: str | None, rules: dict, favorite: str | None) -> dict:
    """
    招待報酬 = 份數 × 2000 × 心情² × 1.2^(活動料理份數) × 1.5 (額外那份正中最愛)
    兩種加成都乘在過完心情之後的金額上 (使用者 2026-11-05 指定)
    """
    served = list(order) + ([extra] if extra else [])
    base = SERVING_REWARD * (mood / 100) ** 2 * len(served)
    event_count = sum(1 for d in served if d in rules["event_dishes"])
    favorite_hit = bool(extra) and extra == favorite
    mult = rules["event_dish_bonus"] ** event_count * (FAVORITE_BONUS if favorite_hit else 1) * modifier(rules, "serve_reward")
    return {"base": int(round(base)), "event_count": event_count, "favorite_hit": favorite_hit,
            "multiplier": mult, "total": int(round(base * mult))}


def explore_cost(rules: dict) -> int:
    """一趟採集的體力 (活動可以用 modifiers.explore_stamina 調整)"""
    return max(1, round(shrine_data.EXPLORE_STAMINA * modifier(rules, "explore_stamina")))


def make_order(rules: dict, rng=random) -> list[str]:
    """
    點餐：1~3 個不同種類，每類一道。點餐池 = 一般池 + 活動池 (rules["order_pool"])：
    活動池有東西時，每道有 order_event_chance 機率從活動池抽
    """
    n = ORDER_SIZE[0] + int(rng.random() * (ORDER_SIZE[1] - ORDER_SIZE[0] + 1))
    types = list(SERVE_TYPES_ORDER)
    picked = []
    for _ in range(min(n, len(types))):
        t = rng.choice(types)
        types.remove(t)
        pool = rules["order_pool"].get(t, {"base": [], "event": []})
        normal, special = pool["base"], pool["event"]
        if special and rng.random() < rules["order_event_chance"]:
            picked.append(rng.choice(special))
        else:
            picked.append(rng.choice(normal))
    order = sorted(picked, key=lambda d: SERVE_TYPES_ORDER.index(rules["dish_types"][d]))
    return order


def pick_guest_kind(rules: dict, rng=random) -> str:
    """
    客人池 = 一般池 + 活動池 (rules["guest_pool"])：活動有設 event_guest_chance 時，
    依機率決定抽哪一池；沒設 = 全部客人平均抽 (目前紅霧異變就是這樣)
    """
    pool = rules["guest_pool"]
    chance = rules.get("event_guest_chance")
    if chance is not None and pool["event"] and pool["base"]:
        return rng.choice(pool["event"] if rng.random() < chance else pool["base"])
    return rng.choice(sorted(rules["guests"]))


def new_guest(rules: dict, t: datetime, rng=random) -> dict:
    return {"id": f"{int(t.timestamp()):x}{int(rng.random() * 4096):03x}", "kind": pick_guest_kind(rules, rng),
            "arrived_at": t.isoformat(), "order": make_order(rules, rng)}


_GUEST_NAME_TO_KEY = {g["name"]: k for k, g in shrine_data.GUESTS.items()}


def sanitize_guests(state: dict, rules: dict, rng=random):
    """
    舊資料或活動結束後的修正 (原地修改)：舊版用中文名稱當 kind ➔ 換成 key；
    已結束活動的客人離開；點了不存在的料理 (活動結束) ➔ 重新點餐；補上 id
    """
    fixed = []
    for i, g in enumerate(state["guests"]):
        g = dict(g)
        g["kind"] = _GUEST_NAME_TO_KEY.get(g["kind"], g["kind"])
        if g["kind"] not in rules["guests"]:
            continue
        if not g.get("order") or any(d not in rules["dish_types"] for d in g["order"]):
            g["order"] = make_order(rules, rng)
        g.setdefault("id", f"g{i}{int(_dt(g['arrived_at']).timestamp()):x}")
        fixed.append(g)
    state["guests"] = fixed


def advance_shrine(state: dict, now: datetime, rng=random, rules: dict | None = None) -> dict:
    """
    純計算：把神社從 updated_at 推進到 now (不寫資料庫)
    - 賽錢箱依當下效率連續累積 (效率在整點事件、變髒的時間點改變)
    - 每個整點 (以建立時間為準)：妖怪依目前數量機率生成；每 2 小時：參拜客依目前人數機率來訪
    - 參拜客心情掉到 0 就離開；來的時候就決定好點什麼 (rules = events.game_rules，含活動)
    """
    rules = rules or game_rules([])
    income_mult = modifier(rules, "shrine_income")
    youkai_mult, guest_mult = modifier(rules, "youkai_spawn"), modifier(rules, "guest_spawn")
    st = dict(state)
    st["guests"] = list(state["guests"])
    anchor = _dt(st["created_at"])
    t = _dt(st["updated_at"])
    if now - t > SHRINE_MAX_CATCHUP:
        t = now - SHRINE_MAX_CATCHUP
        st["tick"] = max(st["tick"], int((t - anchor) / HOUR))

    while t < now:
        next_event = anchor + (st["tick"] + 1) * HOUR
        dirt = shrine_dirt(st, t)
        seg_end = min(now, next_event)
        if dirt < DIRT_MAX:
            clean_at = _dt(st["clean_at"])
            next_dirt = clean_at + (int((t - clean_at) / DIRT_INTERVAL) + 1) * DIRT_INTERVAL
            seg_end = min(seg_end, next_dirt)
        seg_end = max(t, seg_end)   # 保險：事件時間點已經過了就只處理事件、不算收入
        income = (seg_end - t) / HOUR * SHRINE_INCOME_PER_HOUR * shrine_efficiency(dirt, st["youkai"]) * income_mult
        st["box"] = min(SHRINE_BOX_MAX, st["box"] + income)
        t = seg_end

        if t >= next_event:
            st["tick"] += 1
            st["guests"] = [g for g in st["guests"] if guest_mood(g, t) > 0]
            if st["youkai"] < YOUKAI_MAX and rng.random() < min(1.0, YOUKAI_SPAWN[st["youkai"]] * youkai_mult):
                st["youkai"] += 1
            if st["tick"] % GUEST_EVERY_HOURS == 0 and len(st["guests"]) < GUEST_MAX \
                    and rng.random() < min(1.0, GUEST_SPAWN[len(st["guests"])] * guest_mult):
                st["guests"].append(new_guest(rules, t, rng))

    st["guests"] = [g for g in st["guests"] if guest_mood(g, now) > 0]
    st["updated_at"] = now.isoformat()
    return st


def shrine_summary(state: dict, now: datetime, rules: dict | None = None) -> dict:
    """畫面要顯示的資料 (已結算後的 state)；客人的台詞模板與提示也放進來 (料理名稱由畫面填)"""
    rules = rules or game_rules([])
    guest_info = {**all_guests(), **rules["guests"]}
    dirt = shrine_dirt(state, now)
    eff = shrine_efficiency(dirt, state["youkai"])
    next_dirt_at = None
    if dirt < DIRT_MAX:
        clean_at = _dt(state["clean_at"])
        next_dirt_at = clean_at + (int((now - clean_at) / DIRT_INTERVAL) + 1) * DIRT_INTERVAL
    guests = []
    for g in state["guests"]:
        arrived = _dt(g["arrived_at"])
        mood = guest_mood(g, now)
        steps = int((now - arrived) / MOOD_INTERVAL)
        info = guest_info.get(g["kind"], {"name": g["kind"], "emoji": "👤", "lines": {}, "hint": ""})
        guests.append({
            "id": g.get("id"), "kind": g["kind"], "name": info["name"], "emoji": info["emoji"],
            "event": info.get("event"), "order": list(g.get("order", [])), "hint": info.get("hint", ""),
            "line": pick_line(info, shrine_data.mood_tier(mood), g.get("id") or ""),
            "mood": mood, "arrived_at": arrived,
            "next_drop_at": arrived + (steps + 1) * MOOD_INTERVAL,
            "leave_at": arrived + (100 // MOOD_STEP) * MOOD_INTERVAL,
            "reward_per_portion": serving_reward(mood),
        })
    income = SHRINE_INCOME_PER_HOUR * eff * modifier(rules, "shrine_income")
    box = int(state["box"])
    full_in = None
    if box < SHRINE_BOX_MAX and income > 0:
        full_in = now + timedelta(hours=(SHRINE_BOX_MAX - state["box"]) / income)
    return {
        "box": box, "box_max": SHRINE_BOX_MAX, "income_per_hour": int(income), "box_full_at": full_in,
        "dirt": dirt, "dirt_max": DIRT_MAX, "dirt_penalty": DIRT_PENALTY * dirt, "next_dirt_at": next_dirt_at,
        "youkai": state["youkai"], "youkai_max": YOUKAI_MAX, "youkai_penalty": YOUKAI_PENALTY * state["youkai"],
        "youkai_reward": tuple(int(round(v * modifier(rules, "youkai_reward"))) for v in YOUKAI_REWARD),   # 打退一隻的賽錢範圍 (含活動倍率)
        "efficiency": eff, "guests": guests, "guest_max": GUEST_MAX, "guest_every_hours": GUEST_EVERY_HOURS,
        "next_event_at": _dt(state["created_at"]) + (state["tick"] + 1) * HOUR,
    }


def _new_shrine(now: datetime) -> dict:
    t = now.isoformat()
    return {"created_at": t, "updated_at": t, "tick": 0, "box": 0.0, "clean_at": t, "dirt_extra": 0, "youkai": 0, "guests": []}


async def _shrine_tx(user_id: int, action=None, now: datetime | None = None, rng=random) -> dict:
    """
    神社共用交易：讀取 (沒有就建立) ➔ 結算到現在 ➔ action(state, db, rules) 修改 ➔ 寫回
    rules = 這一刻的遊戲規則 (含進行中的活動)。回傳 {"summary": shrine_summary, **action 的回傳}
    """
    now = now or datetime.now(timezone.utc)
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_user(db, user_id)
            async with db.execute("SELECT * FROM shrines WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
            if row is None:
                state = _new_shrine(now)
            else:
                state = dict(row)
                state["guests"] = json.loads(state["guests"] or "[]")
            rules = game_rules(await _active_events(db, now))
            sanitize_guests(state, rules, rng)
            state = advance_shrine(state, now, rng, rules)
            extra = (await action(state, db, rules)) if action else {}
            await db.execute(
                """
                INSERT INTO shrines (user_id, created_at, updated_at, tick, box, clean_at, dirt_extra, youkai, guests)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    updated_at = excluded.updated_at, tick = excluded.tick, box = excluded.box,
                    clean_at = excluded.clean_at, dirt_extra = excluded.dirt_extra,
                    youkai = excluded.youkai, guests = excluded.guests
                """,
                (user_id, state["created_at"], state["updated_at"], state["tick"], state["box"],
                 state["clean_at"], state["dirt_extra"], state["youkai"], json.dumps(state["guests"], ensure_ascii=False)),
            )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"summary": shrine_summary(state, now, rules), **extra}


async def get_shrine(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """查看神社 (會結算並存檔)"""
    return await _shrine_tx(user_id, now=now, rng=rng)


async def shrine_collect(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """回收賽錢箱：整數部分轉進賽錢，零頭留在箱子裡"""
    async def action(state, db, rules):
        amount = int(state["box"])
        state["box"] -= amount
        await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (amount, user_id))
        await add_player_stat(db, user_id, "collect_money", amount)   # 📊 累計回收金額
        async with db.execute("SELECT money FROM users WHERE user_id = ?", (user_id,)) as cursor:
            money = (await cursor.fetchone())["money"]
        return {"collected": amount, "money": money}
    return await _shrine_tx(user_id, action, now, rng)


async def shrine_clean(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """清掃：清潔度回到乾淨 (晦氣一起清掉)，沒有獎勵、沒有冷卻"""
    now = now or datetime.now(timezone.utc)

    async def action(state, db, rules):
        before = shrine_dirt(state, now)
        state["clean_at"] = now.isoformat()
        state["dirt_extra"] = 0
        await add_player_stat(db, user_id, "clean")   # 📊
        return {"before": before}
    return await _shrine_tx(user_id, action, now, rng)


async def shrine_defeat(user_id: int, now: datetime | None = None, rng=random) -> dict:
    """治退一隻妖怪：+800～1500 賽錢 (隨機)，留下晦氣 (清潔度 +1 階，不會超過最髒)"""
    now = now or datetime.now(timezone.utc)

    async def action(state, db, rules):
        if state["youkai"] <= 0:
            return {"ok": False}
        state["youkai"] -= 1
        await add_player_stat(db, user_id, "youkai")   # 📊
        if shrine_dirt(state, now) < DIRT_MAX:
            state["dirt_extra"] += 1
        low, high = YOUKAI_REWARD
        reward = min(high, low + int(rng.random() * (high - low + 1)))
        reward = int(round(reward * modifier(rules, "youkai_reward")))
        await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (reward, user_id))
        return {"ok": True, "reward": reward}
    return await _shrine_tx(user_id, action, now, rng)


async def admin_set_shrine(user_id: int, box: int | None = None, dirt: int | None = None, youkai: int | None = None,
                           guests: int | None = None, guest_mood: int = 100, now: datetime | None = None, rng=random) -> dict:
    """
    【管理員】調整神社 (先結算到現在再改)：
    box 賽錢箱、dirt 清潔度階段 (從現在開始重新計時)、youkai 妖怪數、guests 參拜客數 (心情都設成 guest_mood)
    """
    now = now or datetime.now(timezone.utc)

    async def action(state, db, rules):
        if box is not None:
            state["box"] = float(max(0, min(SHRINE_BOX_MAX, box)))
        if dirt is not None:
            state["clean_at"] = now.isoformat()
            state["dirt_extra"] = max(0, min(DIRT_MAX, dirt))
        if youkai is not None:
            state["youkai"] = max(0, min(YOUKAI_MAX, youkai))
        if guests is not None:
            mood = max(MOOD_STEP, min(100, guest_mood))
            arrived = now - ((100 - mood) // MOOD_STEP) * MOOD_INTERVAL
            state["guests"] = [new_guest(rules, arrived, rng) for _ in range(max(0, min(GUEST_MAX, guests)))]
            for i, g in enumerate(state["guests"]):
                g["id"] = f"{g['id']}{i}"
        return {}
    return await _shrine_tx(user_id, action, now, rng)


async def admin_reset_shrine(user_id: int) -> bool:
    """【管理員】刪除神社資料 (下次打開時重新建立，賽錢箱歸零)"""
    async with connect() as db:
        cursor = await db.execute("DELETE FROM shrines WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0

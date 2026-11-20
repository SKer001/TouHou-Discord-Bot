"""
🌀 裏世界探索 (/ura) 的資料層 (Users.db；資料表定義在 User_DB_Manager.SCHEMA_STATEMENTS)

- ura_runs：進行中的一局，一人一列 (同時只能有一局)；state = 引擎的 run dict (JSON)
  每個動作 `UPDATE … SET rev = rev + 1 WHERE user_id = ? AND rev = ?`：重複按、重複接回都只會成功一次
- 出發 / 結算各自是一個交易：出發扣倉庫道具 + 賽錢 + 額外背包耐久、卡牌上出征鎖；
  結算發賽錢 + 經驗 + 道具 / 寶物 / 素材、扣完整度、解除出征鎖、更新排行榜紀錄、刪掉這一局
- ura_storage：裏世界倉庫 (kind = item / treasure)；ura_bags：額外背包 (用 3 次就壞)；ura_records：排行榜紀錄 + 快速整裝
規則全部在 Database/ura/ (引擎)，這裡只負責存取與交易。
"""
import json
import random
import secrets
from datetime import datetime, timezone

from Database.User_DB_Manager import connect, _ensure_user, _load_inventory, calc_exp_change, add_player_stat
from Database.Economy_DB_Manager import _active_events   # 🎪 進行中的活動 (過期的會在這裡結束)
from Database.ura import data, rules, run as R
from Utils import card_cache
from Utils.character_data import apply_current_names   # 錯誤訊息的卡名用目前的角色檔

BAG_USES = 3   # 額外背包用 3 次就壞


def _now(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


async def _live_fests(db, now: datetime | None) -> list[str]:
    """(交易裡) 現在進行中、有裏世界內容 (活動檔的 "ura") 的活動 id"""
    return [ev["id"] for ev in await _active_events(db, now or datetime.now(timezone.utc)) if isinstance(ev.get("ura"), dict)]


# =========================================================
# 📖 讀取
# =========================================================
async def get_run(user_id: int) -> dict | None:
    """{"rev", "state" (dict), "channel_id", "message_id"}；沒有進行中的一局 ➔ None"""
    async with connect() as db:
        async with db.execute("SELECT rev, state, channel_id, message_id FROM ura_runs WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return {"rev": row["rev"], "state": json.loads(row["state"]), "channel_id": row["channel_id"], "message_id": row["message_id"]}


async def candidate_cards(user_id: int) -> list[dict]:
    """
    可以出征的角色的卡 (含不能派的，畫面上要顯示原因)：
    [{instance_id, character_key, rarity, completeness, ok, why}]；why = 收藏冊 / 出征中 / 完整度不足
    (上架中的卡已經搬到市場託管，不在 gacha_cards 裡)
    """
    chars = data.characters()
    async with connect() as db:
        async with db.execute(
            "SELECT instance_id, character_key, rarity, completeness, locked, expedition "
            "FROM gacha_cards WHERE user_id = ? ORDER BY rowid", (user_id,)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    out = []
    for r in rows:
        if r["character_key"] not in chars:
            continue
        why = None
        if r["locked"]:
            why = "🔒 在收藏冊"
        elif r["expedition"]:
            why = "🌀 出征中"
        elif r["completeness"] < rules.MIN_COMPLETENESS:
            why = f"完整度不到 {rules.MIN_COMPLETENESS}"
        out.append({"instance_id": r["instance_id"], "character_key": r["character_key"], "rarity": r["rarity"],
                    "completeness": r["completeness"], "ok": why is None, "why": why})
    return out


async def get_storage(user_id: int) -> dict:
    """{"items": {道具: 數量}, "treasures": {寶物: 數量}, "bags": [{id, bag_id, uses_left}]}"""
    out = {"items": {}, "treasures": {}, "bags": []}
    async with connect() as db:
        async with db.execute("SELECT kind, key, qty FROM ura_storage WHERE user_id = ? AND qty > 0", (user_id,)) as cur:
            for r in await cur.fetchall():
                out["items" if r["kind"] == "item" else "treasures"][r["key"]] = r["qty"]
        async with db.execute("SELECT id, bag_id, uses_left FROM ura_bags WHERE user_id = ? ORDER BY id", (user_id,)) as cur:
            out["bags"] = [dict(r) for r in await cur.fetchall()]
    return out


async def get_record(user_id: int) -> dict:
    async with connect() as db:
        async with db.execute("SELECT * FROM ura_records WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return {"best_money": 0, "deepest": 0, "loadout": {}}
    d = dict(row)
    d["loadout"] = json.loads(d["loadout"]) if d.get("loadout") else {}
    return d


async def get_leaderboard_records(user_ids: list[int]) -> dict:
    """
    🏆 排行榜用：{玩家: {"money": 紀錄, "depth": 紀錄}} (只有成功撤離過的那一項才有)
    紀錄 = {"value", "at" (達成時間，同分時早的排前面), "party" [{cid, rarity, name, alive}], "relics", "net", "floor"}
    💰 money：value = 淨賺、floor = 那一局走到第幾關；🕳️ depth：value = 關數、net = 那一局的淨賺
    """
    out: dict = {}
    if not user_ids:
        return out
    marks = ", ".join("?" for _ in user_ids)
    async with connect() as db:
        async with db.execute(f"SELECT * FROM ura_records WHERE user_id IN ({marks})", tuple(user_ids)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        rec = {}
        if r.get("best_money_at"):
            p = json.loads(r["best_money_party"] or "{}")
            rec["money"] = {"value": r["best_money"], "at": r["best_money_at"], "party": p.get("party", []),
                            "relics": p.get("relics", []), "net": r["best_money"], "floor": p.get("floor")}
        if r.get("deepest_at"):
            p = json.loads(r["deepest_party"] or "{}")
            rec["depth"] = {"value": r["deepest"], "at": r["deepest_at"], "party": p.get("party", []),
                            "relics": p.get("relics", []), "net": max(0, p.get("money", 0) - p.get("brought", 0)),
                            "floor": r["deepest"]}
        if rec:
            out[r["user_id"]] = rec
    return out


async def save_loadout(user_id: int, items: dict) -> None:
    """💾 快速整裝：存下這次要帶的道具"""
    clean = {k: int(v) for k, v in items.items() if k in data.items() and int(v) > 0}
    async with connect() as db:
        await _ensure_user(db, user_id)
        await db.execute("INSERT INTO ura_records (user_id, loadout) VALUES (?, ?) "
                         "ON CONFLICT(user_id) DO UPDATE SET loadout = excluded.loadout", (user_id, json.dumps(clean)))
        await db.commit()


# =========================================================
# 🚀 出發
# =========================================================
async def start_run(user_id: int, card_ids: list[str], items: dict, pocket: int, bag_row: int | None = None,
                    channel_id: int | None = None, now: datetime | None = None, seed: str | None = None) -> dict:
    """
    出發 (單一交易)；失敗 {"ok": False, "reason": 原因}，成功 {"ok": True, "rev", "state"}
    檢查：沒有進行中的一局、1～3 張卡 (自己的、不在收藏冊 / 出征中、完整度 ≥ 0.3、角色不重複)、
         倉庫道具夠、一局最多帶幾個、背包格數、賽錢夠
    """
    items = {k: int(v) for k, v in (items or {}).items() if int(v) > 0}
    pocket = int(pocket or 0)
    if not 1 <= len(card_ids) <= rules.MAX_PARTY or len(set(card_ids)) != len(card_ids):
        return {"ok": False, "reason": f"要派 1～{rules.MAX_PARTY} 張不同的卡"}
    if pocket < 0:
        return {"ok": False, "reason": "帶進去的賽錢不能是負的"}
    chars = data.characters()
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_user(db, user_id)
            async with db.execute("SELECT 1 FROM ura_runs WHERE user_id = ?", (user_id,)) as cur:
                if await cur.fetchone():
                    await db.rollback()
                    return {"ok": False, "reason": "已經有一局在進行中了 (用 /ura resume 接回)"}
            marks = ", ".join("?" for _ in card_ids)
            async with db.execute(
                f"SELECT * FROM gacha_cards WHERE user_id = ? AND instance_id IN ({marks})", (user_id, *card_ids)) as cur:
                rows = {r["instance_id"]: apply_current_names(dict(r)) for r in await cur.fetchall()}
            why = None
            if len(rows) != len(card_ids):
                why = "有卡已經不在你的卡冊裡了"
            else:
                keys = [rows[i]["character_key"] for i in card_ids]
                if len(set(keys)) != len(keys):
                    why = "同一位角色不能派兩張"
                for i in card_ids:
                    r = rows[i]
                    if r["character_key"] not in chars:
                        why = f"{r['name']} 還不能出征"
                    elif r["locked"]:
                        why = f"{r['name']} 在收藏冊裡，不能出征"
                    elif r["expedition"]:
                        why = f"{r['name']} 已經在出征中"
                    elif r["completeness"] < rules.MIN_COMPLETENESS:
                        why = f"{r['name']} 的完整度不到 {rules.MIN_COMPLETENESS}"
            if why:
                await db.rollback()
                return {"ok": False, "reason": why}
            # 倉庫的道具
            async with db.execute("SELECT key, qty FROM ura_storage WHERE user_id = ? AND kind = 'item'", (user_id,)) as cur:
                have = {r["key"]: r["qty"] for r in await cur.fetchall()}
            carry = {}
            for iid, n in items.items():
                if iid not in data.items():
                    why = f"沒有 {iid} 這個道具"
                    break
                if have.get(iid, 0) < n:
                    why = f"倉庫的{data.items()[iid]['name']}不夠"
                    break
                why = R.item_limit_reason(carry, iid, n)
                if why:
                    break
                carry[iid] = n
            capacity = rules.BAG_SLOTS
            bag = None
            if not why and bag_row is not None:
                async with db.execute("SELECT * FROM ura_bags WHERE id = ? AND user_id = ? AND uses_left > 0", (bag_row, user_id)) as cur:
                    bag = await cur.fetchone()
                if not bag:
                    why = "沒有這個額外背包"
                else:
                    capacity += data.bags()[bag["bag_id"]]["slots"]
            if not why and R.slots_used({"items": carry, "materials": {}, "treasures": [], "relics": []}) > capacity:
                why = f"背包只有 {capacity} 格"
            async with db.execute("SELECT money FROM users WHERE user_id = ?", (user_id,)) as cur:
                money = (await cur.fetchone())["money"]
            if not why and money < pocket:
                why = f"賽錢不夠 (你只有 {money:,})"
            if why:
                await db.rollback()
                return {"ok": False, "reason": why}
            # 寫入
            for iid, n in carry.items():
                await db.execute("UPDATE ura_storage SET qty = qty - ? WHERE user_id = ? AND kind = 'item' AND key = ?", (n, user_id, iid))
            await db.execute("DELETE FROM ura_storage WHERE user_id = ? AND qty <= 0", (user_id,))
            if bag:
                if bag["uses_left"] <= 1:
                    await db.execute("DELETE FROM ura_bags WHERE id = ?", (bag_row,))
                else:
                    await db.execute("UPDATE ura_bags SET uses_left = uses_left - 1 WHERE id = ?", (bag_row,))
            if pocket:
                await db.execute("UPDATE users SET money = money - ? WHERE user_id = ?", (pocket, user_id))
            await db.execute(f"UPDATE gacha_cards SET expedition = 1 WHERE user_id = ? AND instance_id IN ({marks})", (user_id, *card_ids))
            seed = seed or secrets.token_hex(8)
            cards = [({"instance_id": i, "character_key": rows[i]["character_key"], "rarity": rows[i]["rarity"],
                       "completeness": rows[i]["completeness"]}, chars[rows[i]["character_key"]]) for i in card_ids]
            state = R.new_run(seed, cards, carry, pocket, random.Random(seed), capacity=capacity,
                              live_fests=await _live_fests(db, now))
            if bag:
                state["bag_name"] = data.bags()[bag["bag_id"]]["name"]
            ts = _now(now)
            await db.execute("INSERT INTO ura_runs (user_id, rev, state, channel_id, started_at, updated_at) VALUES (?, 0, ?, ?, ?, ?)",
                             (user_id, json.dumps(state, ensure_ascii=False), channel_id, ts, ts))
            await add_player_stat(db, user_id, "ura_runs")
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    card_cache.invalidate(user_id)
    return {"ok": True, "rev": 0, "state": state}


# =========================================================
# 👣 每一個動作
# =========================================================
async def act(user_id: int, rev: int, fn, now: datetime | None = None) -> dict:
    """
    對進行中的一局做一個動作：fn(state, rng) ➔ None (成功) / 原因字串 (失敗，不存)
    rev 不對 (別的畫面已經動過) ➔ {"ok": False, "reason": "stale"}
    這一局結束 (撤離 / 失敗 / 放棄) ➔ 在同一個交易裡結算，回傳多一個 "settle"
    """
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute("SELECT rev, state FROM ura_runs WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
            if not row:
                await db.rollback()
                return {"ok": False, "reason": "none"}
            if row["rev"] != rev:
                await db.rollback()
                return {"ok": False, "reason": "stale", "rev": row["rev"]}
            state = json.loads(row["state"])
            state["live_fests"] = await _live_fests(db, now)   # 🎪 每一步看「現在」有沒有活動 (結束了就不再出活動門)
            why = fn(state, R.action_rng(state))
            if why:
                await db.rollback()
                return {"ok": False, "reason": why, "rev": rev}
            if state["phase"] == "ended":
                summary = await _settle(db, user_id, state, now)
                await db.commit()
                card_cache.invalidate(user_id)
                return {"ok": True, "rev": rev + 1, "state": state, "settle": summary}
            cur = await db.execute("UPDATE ura_runs SET state = ?, rev = rev + 1, updated_at = ? WHERE user_id = ? AND rev = ?",
                                   (json.dumps(state, ensure_ascii=False), _now(now), user_id, rev))
            if cur.rowcount != 1:
                await db.rollback()
                return {"ok": False, "reason": "stale"}
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "rev": rev + 1, "state": state}


async def set_message(user_id: int, channel_id: int | None, message_id: int | None):
    """記下目前顯示這一局的訊息 (接回時刪掉舊的)"""
    async with connect() as db:
        await db.execute("UPDATE ura_runs SET channel_id = COALESCE(?, channel_id), message_id = ? WHERE user_id = ?",
                         (channel_id, message_id, user_id))
        await db.commit()


async def _settle(db, user_id: int, state: dict, now: datetime | None) -> dict:
    """(交易裡) 結算：發 / 扣全部在這裡，最後刪掉這一局"""
    s = R.settle(state)
    async with db.execute("SELECT money, level, exp, inventory FROM users WHERE user_id = ?", (user_id,)) as cur:
        u = await cur.fetchone()
    exp = calc_exp_change(u["level"], u["exp"], s["exp"])
    inv = _load_inventory(u["inventory"])
    for m, n in s["materials"].items():
        inv[m] = inv.get(m, 0) + n
    await db.execute("UPDATE users SET money = money + ?, level = ?, exp = ?, inventory = ? WHERE user_id = ?",
                     (s["money"], exp["new_level"], exp["current_exp"], json.dumps(inv, ensure_ascii=False), user_id))
    for iid, n in s["items"].items():
        await _storage_add(db, user_id, "item", iid, n)
    for t in s["treasures"]:
        await _storage_add(db, user_id, "treasure", t["id"], 1)
    cards = [m["card_id"] for m in state["party"]]
    if s["penalty"]:
        marks = ", ".join("?" for _ in s["penalty"])
        await db.execute(f"UPDATE gacha_cards SET completeness = MAX(0, ROUND(completeness - ?, 4)) "
                         f"WHERE user_id = ? AND instance_id IN ({marks})", (rules.COMP_PENALTY, user_id, *s["penalty"]))
    marks = ", ".join("?" for _ in cards)
    await db.execute(f"UPDATE gacha_cards SET expedition = 0 WHERE user_id = ? AND instance_id IN ({marks})", (user_id, *cards))
    net = max(0, s["money"] - s["brought"])   # 💰 排行榜用淨賺 (帶出 − 帶進，2026-11-20 使用者決定)；結算大標題寫帶回的總額
    if s["result"] == "evacuated":
        party = json.dumps({"party": s["party"], "relics": s["relics"], "money": s["money"], "brought": s["brought"],
                            "floor": s["floor"]}, ensure_ascii=False)
        ts = _now(now)
        await db.execute("INSERT INTO ura_records (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING", (user_id,))
        # 第一次撤離 (*_at 還是 NULL) 一定記；之後要「更好」才換 (一樣 = 留著先達成的那一筆，排行榜同分時它排前面)
        await db.execute("UPDATE ura_records SET best_money = ?, best_money_at = ?, best_money_party = ? "
                         "WHERE user_id = ? AND (best_money < ? OR best_money_at IS NULL)", (net, ts, party, user_id, net))
        await db.execute("UPDATE ura_records SET deepest = ?, deepest_at = ?, deepest_party = ? "
                         "WHERE user_id = ? AND (deepest < ? OR deepest_at IS NULL)", (s["floor"], ts, party, user_id, s["floor"]))
        await add_player_stat(db, user_id, "ura_evacuated")
    for eid, n in s["kills"].items():
        await add_player_stat(db, user_id, f"ura_kill:{eid}", n)
    await db.execute("DELETE FROM ura_runs WHERE user_id = ?", (user_id,))
    return {**s, "net": net if s["result"] == "evacuated" else 0, "exp_result": exp}


async def _storage_add(db, user_id: int, kind: str, key: str, n: int):
    await db.execute("INSERT INTO ura_storage (user_id, kind, key, qty) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(user_id, kind, key) DO UPDATE SET qty = qty + excluded.qty", (user_id, kind, key, n))


# =========================================================
# 🛒 商店 / 💎 賣寶物
# =========================================================
async def shop_buy(user_id: int, item_id: str, qty: int = 1) -> dict:
    """/ura shop：買道具或額外背包 (放進倉庫)；reason：not_found / bad_qty / not_enough"""
    if qty < 1:
        return {"ok": False, "reason": "bad_qty"}
    is_bag = item_id in data.bags()
    info = data.bags()[item_id] if is_bag else data.items().get(item_id)
    if not info or not info.get("price"):
        return {"ok": False, "reason": "not_found"}
    cost = info["price"] * qty
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_user(db, user_id)
            async with db.execute("SELECT money FROM users WHERE user_id = ?", (user_id,)) as cur:
                money = (await cur.fetchone())["money"]
            if money < cost:
                await db.rollback()
                return {"ok": False, "reason": "not_enough", "cost": cost, "money": money}
            await db.execute("UPDATE users SET money = money - ? WHERE user_id = ?", (cost, user_id))
            if is_bag:
                for _ in range(qty):
                    await db.execute("INSERT INTO ura_bags (user_id, bag_id, uses_left) VALUES (?, ?, ?)", (user_id, item_id, BAG_USES))
            else:
                await _storage_add(db, user_id, "item", item_id, qty)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "cost": cost, "money": money - cost}


async def sell_treasures(user_id: int, sell: dict) -> dict:
    """賣寶物 {寶物 id: 數量} (固定價格，賣給系統)；數量不夠就整筆不賣"""
    prices = data.treasure_prices()
    sell = {k: int(v) for k, v in sell.items() if int(v) > 0}
    if not sell:
        return {"ok": False, "reason": "empty"}
    total = 0
    for tid, n in sell.items():
        info = data.treasure_info(tid)
        if not info:
            return {"ok": False, "reason": "not_found"}
        total += prices[info["rarity"]] * n
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            for tid, n in sell.items():
                cur = await db.execute("UPDATE ura_storage SET qty = qty - ? WHERE user_id = ? AND kind = 'treasure' AND key = ? AND qty >= ?",
                                       (n, user_id, tid, n))
                if cur.rowcount != 1:
                    await db.rollback()
                    return {"ok": False, "reason": "not_enough"}
            await db.execute("DELETE FROM ura_storage WHERE user_id = ? AND qty <= 0", (user_id,))
            await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (total, user_id))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return {"ok": True, "money": total, "count": sum(sell.values())}

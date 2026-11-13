"""
🔔 主動通知 (DM) 的資料層：玩家開關、已發送紀錄 (去重)、上次看到的狀態，以及「要發哪些通知」的判斷

- 資料也在 Users.db，表由這裡自己建 (init_notify_db，在 notify Cog 的 cog_load 呼叫)
- 判斷都用時間差 / 狀態差，跟體力、神社一樣不用排程：
    check_* 純函式 = (現在時間 + 玩家資料 + 上次看到的狀態) ➔ 要發的通知清單
    collect_notices(now) = 讀資料庫 ➔ 跑 check_* ➔ 套用玩家開關與去重 ➔ 回傳還沒發過的通知
- 真的私訊在 Cogs/load-general/notify.py (這裡不 import discord)
"""
from datetime import datetime, timedelta, timezone

from Database import User_DB_Manager as udm
from Database import Economy_DB_Manager as econ
from Database.notify_data import NOTIFY_TYPES, can_dm
from Database import title_data
from Utils.gacha_pools import collection_stats, oshi_stats

# =========================================================
# ⏱️ 時間門檻 (要調整就改這裡)
# =========================================================
CHECK_INTERVAL_MINUTES = 10                  # 背景每 10 分鐘檢查一次
GUEST_LEAVING_WINDOW = timedelta(hours=4)    # 參拜客離開前 4 小時內通知 (每位只通知一次)
SALES_LOOKBACK = timedelta(days=7)           # 賣出紀錄最多往回看 7 天 (機器人關機太久時)
SENT_KEEP = timedelta(days=30)               # 已發送紀錄保留 30 天

GLOBAL_ID = 0                                # notify_watch 的全服狀態 (活動、起算時間) 用 user_id 0

SCHEMA_STATEMENTS = [
    # 玩家的通知開關：沒有紀錄 = 開啟 (預設全開)
    """
    CREATE TABLE IF NOT EXISTS notify_settings (
        user_id  INTEGER NOT NULL,
        kind     TEXT NOT NULL,
        enabled  INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (user_id, kind)
    )
    """,
    # 已發送的通知 (同一件事只發一次)；ok = 私訊有沒有送到 (0 = 對方關閉私訊等)
    """
    CREATE TABLE IF NOT EXISTS notifications_sent (
        user_id  INTEGER NOT NULL,
        kind     TEXT NOT NULL,
        key      TEXT NOT NULL,
        sent_at  TEXT NOT NULL,
        ok       INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (user_id, kind, key)
    )
    """,
    # 上次看到的狀態 (賽錢箱滿了沒、體力花過沒、活動狀態…)，用來判斷「從不滿變滿」
    """
    CREATE TABLE IF NOT EXISTS notify_watch (
        user_id    INTEGER NOT NULL,
        kind       TEXT NOT NULL,
        value      TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, kind)
    )
    """,
    # 上次看到的上架清單：下次不見了又沒賣出、而且過了 7 天 ➔ 到期退回
    """
    CREATE TABLE IF NOT EXISTS notify_listings (
        listing_id  INTEGER PRIMARY KEY,
        seller_id   INTEGER NOT NULL,
        instance_id TEXT NOT NULL,
        name        TEXT,
        emoji       TEXT,
        rarity      TEXT,
        price       INTEGER,
        listed_at   TEXT NOT NULL
    )
    """,
]


async def init_notify_db():
    async with udm.connect() as db:
        for stmt in SCHEMA_STATEMENTS:
            await db.execute(stmt)
        await db.commit()


# =========================================================
# ⚙️ 玩家開關
# =========================================================
async def get_settings(user_id: int) -> dict:
    """{種類: 開啟?}；不能私訊的種類一律 False"""
    async with udm.connect() as db:
        async with db.execute("SELECT kind, enabled FROM notify_settings WHERE user_id = ?", (user_id,)) as cursor:
            stored = {r["kind"]: bool(r["enabled"]) for r in await cursor.fetchall()}
    return {kind: can_dm(kind) and stored.get(kind, True) for kind in NOTIFY_TYPES}


async def set_enabled(user_id: int, kind: str, enabled: bool) -> bool:
    """設定開關；不認識或不能私訊的種類回傳 False"""
    if not can_dm(kind):
        return False
    async with udm.connect() as db:
        await db.execute(
            "INSERT INTO notify_settings (user_id, kind, enabled) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, kind) DO UPDATE SET enabled = excluded.enabled",
            (user_id, kind, int(enabled)),
        )
        await db.commit()
    return True


async def set_all(user_id: int, enabled: bool) -> int:
    """全部開啟 / 全部關閉 (只改能私訊的種類)，回傳改了幾種"""
    kinds = [k for k in NOTIFY_TYPES if can_dm(k)]
    async with udm.connect() as db:
        await db.executemany(
            "INSERT INTO notify_settings (user_id, kind, enabled) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, kind) DO UPDATE SET enabled = excluded.enabled",
            [(user_id, k, int(enabled)) for k in kinds],
        )
        await db.commit()
    return len(kinds)


async def _disabled_pairs(db) -> set[tuple[int, str]]:
    async with db.execute("SELECT user_id, kind FROM notify_settings WHERE enabled = 0") as cursor:
        return {(r["user_id"], r["kind"]) for r in await cursor.fetchall()}


# =========================================================
# 📨 已發送紀錄 (去重)
# =========================================================
async def claim(user_id: int, kind: str, key: str, now: datetime | None = None) -> bool:
    """先佔位再私訊：寫入成功 (之前沒發過) 回傳 True；已經發過回傳 False"""
    now = now or datetime.now(timezone.utc)
    async with udm.connect() as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO notifications_sent (user_id, kind, key, sent_at, ok) VALUES (?, ?, ?, ?, 1)",
            (user_id, kind, key, now.isoformat()),
        )
        await db.commit()
        return cursor.rowcount == 1


async def mark_failed(user_id: int, items: list[tuple[str, str]]):
    """私訊失敗 (對方關閉私訊等)：紀錄保留 (不會一直重試)，ok 設成 0"""
    async with udm.connect() as db:
        await db.executemany("UPDATE notifications_sent SET ok = 0 WHERE user_id = ? AND kind = ? AND key = ?",
                             [(user_id, k, key) for k, key in items])
        await db.commit()


async def was_sent(user_id: int, kind: str, key: str) -> bool:
    async with udm.connect() as db:
        async with db.execute("SELECT 1 FROM notifications_sent WHERE user_id = ? AND kind = ? AND key = ?",
                              (user_id, kind, key)) as cursor:
            return await cursor.fetchone() is not None


async def prune_sent(now: datetime | None = None) -> int:
    """刪掉 30 天以前的發送紀錄 (那些事件不會再出現)"""
    now = now or datetime.now(timezone.utc)
    async with udm.connect() as db:
        cursor = await db.execute("DELETE FROM notifications_sent WHERE sent_at < ?", ((now - SENT_KEEP).isoformat(),))
        await db.commit()
        return cursor.rowcount


# =========================================================
# 👀 上次看到的狀態
# =========================================================
async def _get_watch(db) -> dict:
    """{user_id: {kind: value}}"""
    out: dict[int, dict] = {}
    async with db.execute("SELECT user_id, kind, value FROM notify_watch") as cursor:
        for r in await cursor.fetchall():
            out.setdefault(r["user_id"], {})[r["kind"]] = r["value"]
    return out


async def _set_watch(db, user_id: int, kind: str, value: str | None, now: datetime):
    await db.execute(
        "INSERT INTO notify_watch (user_id, kind, value, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, kind) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (user_id, kind, value, now.isoformat()),
    )


# =========================================================
# 🧮 純計算：現在時間 + 玩家資料 + 上次看到的狀態 ➔ 要發的通知
#   通知 = {"user_id", "kind", "key" (去重用), "data" (畫面要顯示的內容)}
#   watch 更新 = {kind: value}，不管玩家有沒有開這種通知都會更新 (之後打開也不會收到舊事)
# =========================================================
def _notice(user_id: int, kind: str, key: str, **data) -> dict:
    return {"user_id": user_id, "kind": kind, "key": str(key), "data": data}


def _stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec="minutes")


def check_shrine(user_id: int, summary: dict, now: datetime, watch: dict) -> tuple[list[dict], dict]:
    """
    神社 (summary = econ.shrine_summary)：
    - 賽錢箱滿了 / 妖怪滿了：看過「不滿」之後變「滿」時通知一次；第一次看到 (沒有紀錄) 只記錄不通知 (使用者 2026-11-11)；回收、治退後重新計算
    - 參拜客離開前 GUEST_LEAVING_WINDOW 內通知，每位客人 (id) 只通知一次
    """
    notices, updates = [], {}
    full = summary["box"] >= summary["box_max"]
    if full and watch.get("shrine_box_full") == "not_full":
        notices.append(_notice(user_id, "shrine_box_full", _stamp(now), box=summary["box"], box_max=summary["box_max"]))
    updates["shrine_box_full"] = "full" if full else "not_full"

    maxed = summary["youkai"] >= summary["youkai_max"]
    if maxed and watch.get("youkai_max") == "not_full":
        notices.append(_notice(user_id, "youkai_max", _stamp(now), youkai=summary["youkai"],
                               penalty=summary["youkai_penalty"]))
    updates["youkai_max"] = "full" if maxed else "not_full"

    for g in summary["guests"]:
        if not g.get("id"):
            continue
        left = g["leave_at"] - now
        if timedelta(0) < left <= GUEST_LEAVING_WINDOW:
            notices.append(_notice(user_id, "guest_leaving", g["id"], name=g["name"], emoji=g["emoji"],
                                   mood=g["mood"], leave_at=g["leave_at"]))
    return notices, updates


def check_stamina(user_id: int, info: dict, now: datetime, watch: dict) -> tuple[list[dict], dict]:
    """體力 (info = udm.calc_stamina)：看過「沒滿」之後才會在回滿時通知一次；從來沒花過就不通知"""
    if info["stamina"] < info["max"]:
        return [], ({"stamina_full": "spent"} if watch.get("stamina_full") != "spent" else {})
    if watch.get("stamina_full") == "spent":
        return [_notice(user_id, "stamina_full", _stamp(now), stamina=info["stamina"], max=info["max"])], {"stamina_full": "full"}
    return [], {}


def check_sales(trades: list[dict]) -> list[dict]:
    """市場成交紀錄 (market_trades kind='market') ➔ 通知賣家；trade_id 去重"""
    return [_notice(t["seller_id"], "market_sold", t["trade_id"], name=t.get("name") or t["character_key"],
                    emoji=t.get("emoji") or "🎴", rarity=t["rarity"], price=t["price"], buyer_id=t["buyer_id"])
            for t in trades if t.get("seller_id")]


def check_expired(previous: dict, current_ids: set[int], sold_instances: set[str], now: datetime) -> list[dict]:
    """
    previous = 上次看到的上架 {listing_id: row}；現在不見了的：
    - 有賣出紀錄 ➔ 已經由 market_sold 通知，略過
    - 過了 7 天 ➔ 到期退回，通知賣家
    - 還沒 7 天 ➔ 賣家自己下架，不通知
    """
    out = []
    for lid, row in previous.items():
        if lid in current_ids or row["instance_id"] in sold_instances:
            continue
        if datetime.fromisoformat(row["listed_at"]) + econ.LISTING_DURATION <= now:
            out.append(_notice(row["seller_id"], "market_expired", lid, name=row.get("name") or "卡牌",
                               emoji=row.get("emoji") or "🎴", rarity=row.get("rarity"), price=row.get("price")))
    return out


def check_titles(user_id: int, unlocked: list[str], known: str | None) -> tuple[list[dict], str | None]:
    """
    稱號 (unlocked = title_data.unlocked_titles)：known = 上次看到的已解鎖稱號 (逗號分隔，存在 notify_watch，不會被清掉)
    - 新解鎖的每個稱號通知一次 (key = 稱號 id)
    - known 是 None = 系統剛上線時的第一輪 (由呼叫端決定)：只記錄、不通知，免得舊玩家一次收到一堆
    - known 只增不減：UR / LR 稱號賣卡會失去，之後再拿到不會重複私訊
    回傳 (通知, 新的 known 值；沒變回傳 None)
    """
    if known is None:
        return [], ",".join(sorted(unlocked))
    before = set(filter(None, known.split(",")))
    cur = ",".join(sorted(before | set(unlocked)))
    notices = [_notice(user_id, "title_unlocked", tid, title_id=tid, name=title_data.TITLES[tid]["name"],
                       rarity=title_data.TITLES[tid]["rarity"], desc=title_data.TITLES[tid]["desc"],
                       condition=title_data.condition_text(tid))
               for tid in unlocked if tid not in before]
    return notices, (cur if cur != known else None)


def check_events(previous: dict, overview: list[dict]) -> tuple[list[tuple[str, dict, str]], dict]:
    """
    活動狀態變化 (overview = econ.get_events_overview)：previous = {活動 id: "status|started_at"}
    - 第一次看到的活動只記錄、不通知 (系統剛上線時不會把進行中的活動當成新活動)
    - 不是進行中 ➔ 進行中：event_start；進行中 ➔ 已結束：event_end
    回傳 ([(kind, event, key)], 新狀態)
    """
    changes, state = [], {}
    for o in overview:
        ev = o["event"]
        cur = f"{o['status']}|{o.get('started_at') or 'auto'}"
        state[ev["id"]] = cur
        prev = previous.get(ev["id"])
        if prev is None:
            continue
        prev_status = prev.split("|", 1)[0]
        key = f"{ev['id']}:{o.get('started_at') or 'auto'}"
        if o["status"] == "active" and prev_status != "active":
            changes.append(("event_start", ev, key))
        elif o["status"] == "ended" and prev_status == "active":
            changes.append(("event_end", ev, key))
    return changes, state


# =========================================================
# 📋 讀資料庫 ➔ 要發的通知 (背景 loop 與主控台共用)
# =========================================================
async def collect_notices(now: datetime | None = None) -> list[dict]:
    """
    檢查所有玩家，回傳「開著、能私訊、還沒發過」的通知 (還沒佔位；發送前要 claim)
    會順便：結算每座神社 (econ.get_shrine，會寫回)、讓到期的上架退回 (econ.expire_listings)、更新 watch
    """
    now = now or datetime.now(timezone.utc)
    notices: list[dict] = []
    watch_updates: list[tuple[int, str, str]] = []

    async with udm.connect() as db:
        watch = await _get_watch(db)
        baseline_raw = watch.get(GLOBAL_ID, {}).get("baseline")
        if baseline_raw is None:
            # 系統第一次上線：從現在起算，之前的成交紀錄不通知
            await _set_watch(db, GLOBAL_ID, "baseline", now.isoformat(), now)
            await db.commit()
            baseline_raw = now.isoformat()
        async with db.execute("SELECT user_id FROM shrines") as cursor:
            shrine_ids = [r["user_id"] for r in await cursor.fetchall()]
        async with db.execute("SELECT user_id, stamina, stamina_updated_at FROM users") as cursor:
            stamina_rows = [dict(r) for r in await cursor.fetchall()]
        async with db.execute("SELECT * FROM notify_listings") as cursor:
            prev_listings = {r["listing_id"]: dict(r) for r in await cursor.fetchall()}
        async with db.execute(
            "SELECT u.user_id, COALESCE(g.total_draws, 0) AS total_draws, COALESCE(g.total_fusions, 0) AS total_fusions, "
            "COALESCE(g.total_synths, 0) AS total_synths, COALESCE(u.daily_count, 0) AS daily_count, "
            "COALESCE(u.best_streak, 0) AS best_streak, COALESCE(u.best_money, 0) AS best_money, COALESCE(k.ur_kinds, 0) AS ur_kinds, "
            "COALESCE(k.lr_kinds, 0) AS lr_kinds, COALESCE(k.perfect_kinds, 0) AS perfect_kinds FROM users u LEFT JOIN gacha_stats g ON g.user_id = u.user_id "
            f"LEFT JOIN ({udm.TITLE_CARD_KINDS_SQL.replace('SELECT ', 'SELECT user_id, ', 1)} "
            "GROUP BY user_id) k ON k.user_id = u.user_id"
        ) as cursor:
            title_rows = [dict(r) for r in await cursor.fetchall()]   # 欄位要跟 udm.get_title_stats 一致
        async with db.execute("SELECT user_id, character_key, rarity, MAX(completeness) AS best FROM gacha_cards "
                              "GROUP BY user_id, character_key, rarity") as cursor:
            owned_cards, char_counts = {}, {}
            for r in await cursor.fetchall():
                owned_cards.setdefault(r["user_id"], set()).add((r["character_key"], r["rarity"]))
                if r["best"] >= 0.99995:   # 推角：有完美卡的階級數
                    cc = char_counts.setdefault(r["user_id"], {})
                    cc[r["character_key"]] = cc.get(r["character_key"], 0) + 1
    for row in title_rows:   # 📚 卡池收集、💕 推角 (跟 udm.get_title_stats 一樣)
        row.update(collection_stats(owned_cards.get(row["user_id"], set())))
        row.update(oshi_stats(char_counts.get(row["user_id"], {})))

    # ⛩️ 神社 (每座都結算一次)
    for uid in shrine_ids:
        summary = (await econ.get_shrine(uid, now=now))["summary"]
        found, updates = check_shrine(uid, summary, now, watch.get(uid, {}))
        notices += found
        watch_updates += [(uid, k, v) for k, v in updates.items() if watch.get(uid, {}).get(k) != v]

    # ⚡ 體力
    for row in stamina_rows:
        if row["stamina_updated_at"] is None:   # 從沒用過體力
            continue
        info = udm.calc_stamina(row["stamina"], row["stamina_updated_at"], now)
        found, updates = check_stamina(row["user_id"], info, now, watch.get(row["user_id"], {}))
        notices += found
        watch_updates += [(row["user_id"], k, v) for k, v in updates.items()]

    # 💹 市場：先讓到期的退回，再比對上架清單與成交紀錄
    await econ.expire_listings(now)
    since = max(datetime.fromisoformat(baseline_raw), now - max(SALES_LOOKBACK, econ.LISTING_DURATION))
    async with udm.connect() as db:
        async with db.execute(
            "SELECT t.trade_id, t.seller_id, t.buyer_id, t.instance_id, t.character_key, t.rarity, t.price, t.created_at "
            "FROM market_trades t WHERE t.kind = 'market' AND t.created_at >= ?", (since.isoformat(),)
        ) as cursor:
            trades = [dict(r) for r in await cursor.fetchall()]
        async with db.execute("SELECT * FROM market_listings") as cursor:
            listings = econ.apply_current_names([dict(r) for r in await cursor.fetchall()])
    names = {r["instance_id"]: r for r in prev_listings.values()}
    for t in trades:   # 成交紀錄沒有卡名，從上次看到的上架清單補
        if t["instance_id"] in names:
            t["name"], t["emoji"] = names[t["instance_id"]]["name"], names[t["instance_id"]]["emoji"]
    notices += check_sales(trades)
    notices += check_expired(prev_listings, {r["listing_id"] for r in listings},
                             {t["instance_id"] for t in trades if t["instance_id"]}, now)

    # 🏷️ 稱號：第一次上線 (沒有 titles_baseline) 全部只記錄；之後新玩家沒有紀錄 = 之前一個都沒有
    titles_first_run = watch.get(GLOBAL_ID, {}).get("titles_baseline") is None
    for row in title_rows:
        uid = row["user_id"]
        known = None if titles_first_run else watch.get(uid, {}).get("titles", "")
        found, value = check_titles(uid, title_data.unlocked_titles(row), known)
        notices += found
        if value is not None:
            watch_updates.append((uid, "titles", value))
    if titles_first_run:
        watch_updates.append((GLOBAL_ID, "titles_baseline", now.isoformat()))

    # 🎪 活動 (只通知有神社的玩家)
    overview = await econ.get_events_overview(now)
    prev_events = {k.split(":", 1)[1]: v for k, v in watch.get(GLOBAL_ID, {}).items() if k.startswith("event:")}
    changes, event_state = check_events(prev_events, overview)
    for kind, ev, key in changes:
        notices += [_notice(uid, kind, key, name=ev.get("name", ev["id"]), emoji=ev.get("emoji", "🎪"),
                            event_id=ev["id"]) for uid in shrine_ids]
    watch_updates += [(GLOBAL_ID, f"event:{eid}", v) for eid, v in event_state.items() if prev_events.get(eid) != v]

    # 寫回 watch 與上架快照，再套用開關與去重
    async with udm.connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            for uid, kind, value in watch_updates:
                await _set_watch(db, uid, kind, value, now)
            await db.execute("DELETE FROM notify_listings")
            await db.executemany(
                "INSERT INTO notify_listings (listing_id, seller_id, instance_id, name, emoji, rarity, price, listed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(r["listing_id"], r["seller_id"], r["instance_id"], r["name"], r["emoji"], r["rarity"], r["price"],
                  r["listed_at"]) for r in listings],
            )
            disabled = await _disabled_pairs(db)
            async with db.execute("SELECT user_id, kind, key FROM notifications_sent") as cursor:
                sent = {(r["user_id"], r["kind"], r["key"]) for r in await cursor.fetchall()}
            await db.commit()
        except BaseException:
            await db.rollback()
            raise

    return [n for n in notices
            if can_dm(n["kind"]) and (n["user_id"], n["kind"]) not in disabled
            and (n["user_id"], n["kind"], n["key"]) not in sent]

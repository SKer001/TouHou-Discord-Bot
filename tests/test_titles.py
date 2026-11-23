"""🏷️ 稱號：解鎖條件、戴上 / 卸下、沒解鎖不能戴、/profile 顯示稱號與說明、色條顏色、更換選單"""
import asyncio, os, sys, tempfile, types, sqlite3
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
import discord
from discord.ext import commands
from discord import app_commands
from Database import User_DB_Manager as udm
from Database import Item_DB_Manager as idm
from Database import title_data as td

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")   # 絕不碰真實 Users.db
idm.DB_PATH = os.path.join(tmp, "Item.db")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

def sql(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); con.execute(q, args); con.commit(); con.close()

class Resp:
    def __init__(s, it): s.it = it; s.done = False
    def is_done(s): return s.done
    async def defer(s, **kw): s.done = True
    async def send_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
    async def edit_message(s, content=None, **kw): assert content is None; s.done = True; s.it.view = kw.get("view")
class Followup:
    def __init__(s, it): s.it = it
    async def send(s, content=None, **kw):
        assert content is None; s.it.views.append(kw.get("view"))
        if s.it.view is None: s.it.view = kw.get("view")
avatar = types.SimpleNamespace(with_size=lambda n: types.SimpleNamespace(url="https://x/a.png"))
class Interaction:
    def __init__(s, uid=1, data=None):
        s.user = types.SimpleNamespace(id=uid, display_name="t", display_avatar=avatar, mention="@t")
        s.response = Resp(s); s.followup = Followup(s); s.view = None; s.views = []; s.data = data or {}
        s.type = discord.InteractionType.application_command
    async def original_response(s): return None
def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
def selects(v): return [i for i in v.walk_children() if isinstance(i, discord.ui.Select)]
def accent(v): return next(i for i in v.walk_children() if isinstance(i, discord.ui.Container)).accent_color.value

# --- 純資料 ---
check("every title complete", all({"name", "rarity", "desc", "stat", "min"} <= set(t) and t["rarity"] in td.RARITY_COLORS
                                  for t in td.TITLES.values()))
check("draw titles", [td.TITLES[f"draw_{n}"]["rarity"] for n in (10, 100, 500, 1000, 2000, 5000)] == ["N", "R", "SR", "SSR", "UR", "LR"])
check("fusion titles", [td.TITLES[f"fusion_{n}"]["rarity"] for n in (1, 10, 50, 100, 500, 1000)] == ["N", "R", "SR", "SSR", "UR", "LR"])
check("fusion unlock", td.unlocked_titles({"total_fusions": 500}) == ["fusion_500", "fusion_100", "fusion_50", "fusion_10", "fusion_1"])
check("synth titles", [(td.TITLES[f"synth_{n}"]["rarity"], td.TITLES[f"synth_{n}"]["name"]) for n in (1, 10, 50, 100, 500, 1000)]
      == [("N", "初次合成"), ("R", "修卡匠"), ("SR", "精益求精"), ("SSR", "完美主義者"), ("UR", "匠心獨具"), ("LR", "千錘百鍊")])
check("synth condition", td.condition_text("synth_1") == "累計合成 1 次")
check("condition text", td.condition_text("fusion_500") == "累計融合 500 次")
check("unlock none", td.unlocked_titles({"total_draws": 9}) == [])
check("unlock order high first", td.unlocked_titles({"total_draws": 600}) == ["draw_500", "draw_100", "draw_10"])
check("ur/lr titles", [(td.TITLES[k]["rarity"], td.TITLES[k]["name"]) for k in ("ur_1", "ur_5", "ur_10", "lr_1", "lr_3")]
      == [("SR", "金色的奇蹟"), ("SSR", "傳說收藏家"), ("UR", "黃金卡冊"), ("UR", "觸及傳說之人"), ("LR", "幻想的頂點")])
check("lr needs 10 ur", td.unlocked_titles({"ur_kinds": 9, "lr_kinds": 3}) == ["ur_5", "ur_1"])
check("lr chain", td.unlocked_titles({"ur_kinds": 10, "lr_kinds": 3}) == ["lr_3", "ur_10", "lr_1", "ur_5", "ur_1"])
check("perfect titles", [(td.TITLES[f"perfect_{n}"]["rarity"], td.TITLES[f"perfect_{n}"]["name"]) for n in (1, 10, 30, 50)]
      == [("R", "一絲不苟"), ("SR", "收藏家的堅持"), ("SSR", "無瑕的卡冊"), ("UR", "完美的瀟灑")])
check("perfect condition", td.condition_text("perfect_10") == "卡冊有 10 種完美卡 (完整度 1.0000)")
check("requires text", td.condition_text("lr_1") == "卡冊有 1 種角色的 LR 卡，且已獲得「黃金卡冊」")
check("requires exist", all(t.get("requires", "ur_1") in td.TITLES for t in td.TITLES.values()))
check("every title grouped", all(td.title_group(t) for t in td.TITLES))
# 0.35.001 起稱號選單會分頁，一組可以超過 24 個 (神社 35 個)；分組本身超過 25 個也會分頁
check("groups listed", all(td.group_titles(list(td.TITLES)).values()) and len(td.group_titles(list(td.TITLES))["shrine"]) == 35)
check("group order", list(td.group_titles(["pool_all", "draw_10", "ur_1"])) == ["draw", "rare", "pool"])
check("label", td.title_label("draw_2000") == "[UR] 賽錢箱的守護神")
check("color", td.title_color("draw_5000") == 0xE74C3C and td.title_color(None) == td.NO_TITLE_COLOR == 0x5865F2)

async def main():
    # 舊版 gacha_stats 沒有 total_synths ➔ init_db 要自動補上
    con = sqlite3.connect(udm.DB_PATH)
    con.execute("CREATE TABLE gacha_stats (user_id INTEGER PRIMARY KEY, total_draws INTEGER NOT NULL DEFAULT 0, total_fusions INTEGER NOT NULL DEFAULT 0)")
    con.execute("INSERT INTO gacha_stats VALUES (99, 5, 2)"); con.commit(); con.close()
    await udm.init_db()
    con = sqlite3.connect(udm.DB_PATH)
    check("migrated total_synths", con.execute("SELECT total_synths FROM gacha_stats WHERE user_id = 99").fetchone() == (0,)); con.close()

    # 💰 財富：曾經持有過的最高賽錢 (觸發器維護，花掉不會變少)
    M = 64
    await udm.get_or_create_user(M)
    def best():
        con = sqlite3.connect(udm.DB_PATH); r = con.execute("SELECT money, best_money FROM users WHERE user_id = ?", (M,)).fetchone(); con.close(); return r
    S = udm.STARTING_MONEY
    check("best money on insert", best() == (S, S))
    await udm.add_money(M, 200_000)
    check("best money up", best() == (S + 200_000, S + 200_000))
    await udm.add_money(M, -150_000)
    check("best money kept", best() == (S + 50_000, S + 200_000))
    sql("UPDATE users SET money = money + 5 WHERE user_id = ?", (M,))   # 任何地方改 money 都會跟上 (觸發器)
    check("best money below best unchanged", best() == (S + 50_005, S + 200_000))
    unlocked = (await udm.get_title_state(M))["unlocked"]
    check("money title", "money_100k" in unlocked and "money_1m" not in unlocked)
    check("money titles", [(td.TITLES[k]["rarity"], td.TITLES[k]["name"]) for k in ("money_100k", "money_1m", "money_10m", "money_50m", "money_100m", "money_1b")]
          == [("N", "小有積蓄"), ("R", "人里的有錢人"), ("SR", "香霖堂的大主顧"), ("SSR", "守財奴"), ("UR", "幻想鄉的財神"), ("LR", "比賽錢箱還有錢")])
    check("money condition", td.condition_text("money_1m") == "曾經持有 1M 賽錢" and td.title_group("money_1b") == "money")

    # ⛩️ 神社動作計數 (player_stats) + 神社稱號 (SSR，說明帶目前的累計數字)
    from Database import Economy_DB_Manager as econ
    from datetime import datetime, timezone
    K = 67
    await udm.get_or_create_user(K)
    await udm.add_money(K, 10_000_000)
    t0 = datetime(2026, 11, 20, tzinfo=timezone.utc)
    check("shop counted", (await econ.shop_buy(K, "mat_rice", 4, now=t0))["ok"])
    await econ.shop_buy(K, "mat_seasoning", 2, now=t0)
    check("cook counted", (await econ.cook(K, "ran_inari", 2, now=t0))["ok"])
    await econ.shrine_clean(K, now=t0)
    await econ.admin_set_shrine(K, box=12_345_678, youkai=2, now=t0)
    await econ.shrine_defeat(K, now=t0)
    await econ.shrine_collect(K, now=t0)
    await econ.shrine_collect(K, now=t0)   # 箱子空了 ➔ 不加
    ps = await udm.get_player_stats(K)
    check("player stats", (ps["shop"], ps["cook"], ps["clean"], ps["youkai"], ps["collect_money"], ps["explore"])
          == (2, 2, 1, 1, 200_000, 0))   # 賽錢箱上限 20 萬
    async with udm.connect() as db:   # 直接補到 12,345,678 (一次回收最多 20 萬)
        await udm.add_player_stat(db, K, "collect_money", 12_145_678); await db.commit()
    unlocked = (await udm.get_title_state(K))["unlocked"]
    check("collect title", "shrine_collect" in unlocked and "shrine_shop" not in unlocked)
    st = await udm.get_title_state(K)
    check("desc short number", td.title_desc("shrine_collect", st["stats"]) == "已經從賽錢箱回收了 12.35M 賽錢，靈夢看你的眼神越來越複雜。")
    check("desc count", td.title_desc("shrine_cook", st["stats"]).startswith("已經做了 2 道料理"))
    check("shrine titles", all(td.TITLES[k]["rarity"] == "SSR" and td.title_group(k) == "shrine"
                               for k in ("shrine_serve", "shrine_explore", "shrine_youkai", "shrine_cook", "shrine_clean", "shrine_collect", "shrine_shop")))
    check("shrine condition", td.condition_text("shrine_collect") == "從賽錢箱累計回收 10M 賽錢"
          and td.condition_text("shrine_serve") == "成功招待 100 位客人 (額外端上最愛的料理)")
    from Utils.numbers import fmt_money
    check("fmt_money", [fmt_money(x) for x in (5000, 9999, 10_000, 200_000, 12_345_678)] == ["5,000", "9,999", "10K", "200K", "12.35M"])
    check("short numbers", [td.short_number(x) for x in (999, 1000, 1500, 1_234_567, 10_000_000, 2_555_000_000)]
          == ["999", "1K", "1.5K", "1.23M", "10M", "2.56B"])

    # 🔴 火力：現在的 P 點 (level / 10)
    W = 65
    await udm.get_or_create_user(W)
    await udm.add_exp(W, udm.get_total_exp_for_level(100))   # 剛好 10.0 P
    unlocked = (await udm.get_title_state(W))["unlocked"]
    check("power 10P", "power_10" in unlocked and "power_1" in unlocked and "power_30" not in unlocked)
    await udm.add_exp(W, -1)   # 掉回 9.9 P ➔ 失去 10P 稱號
    check("power drop", "power_10" not in (await udm.get_title_state(W))["unlocked"])
    check("power titles", [(td.TITLES[f"power_{p}"]["rarity"], td.TITLES[f"power_{p}"]["min"]) for p in (1, 10, 30, 50, 70, 99, 100)]
          == [("N", 10), ("R", 100), ("SR", 300), ("SSR", 500), ("UR", 700), ("LR", 990), ("LR", 1000)])
    check("power condition", td.condition_text("power_99") == "火力達到 99.0 P" and td.title_group("power_100") == "power")

    # 💹 市場賣出：market_trades kind = 'market' 的賣家筆數 (分解、轉帳不算)
    S = 66
    await udm.get_or_create_user(S)
    for i in range(10):
        sql("INSERT INTO market_trades (kind, seller_id, buyer_id, price, day, created_at) VALUES ('market', ?, 990, 100, 'd', 'c')", (S,))
    sql("INSERT INTO market_trades (kind, seller_id, price, day, created_at) VALUES ('decompose', ?, 100, 'd', 'c')", (S,))
    sql("INSERT INTO market_trades (kind, seller_id, buyer_id, price, day, created_at) VALUES ('market', 990, ?, 100, 'd', 'c')", (S,))
    check("market sold count", (await udm.get_title_stats(S))["market_sold"] == 10)
    unlocked = (await udm.get_title_state(S))["unlocked"]
    check("market titles", "sold_10" in unlocked and "sold_1" in unlocked and "sold_50" not in unlocked)
    check("market names", [td.TITLES[f"sold_{n}"]["name"] for n in (1, 10, 50, 100, 300, 500)]
          == ["第一筆生意", "跳蚤市場的攤主", "河童的生意夥伴", "霧雨道具店的競爭對手", "幻想鄉的大商人", "卡牌市場的支配者"])
    for _ in range(3):   # 💸 轉帳：kind = 'transfer' 的 price 加總 (賣出、分解不算)
        sql("INSERT INTO market_trades (kind, seller_id, buyer_id, price, fee, day, created_at) VALUES ('transfer', ?, 990, 400000, 20000, 'd', 'c')", (S,))
    check("transfer sent", (await udm.get_title_stats(S))["transfer_sent"] == 1_200_000)
    unlocked = (await udm.get_title_state(S))["unlocked"]
    check("transfer titles", "transfer_1m" in unlocked and "transfer_100k" in unlocked and "transfer_10m" not in unlocked)
    check("transfer condition", td.condition_text("transfer_10m") == "累計轉出 10M 賽錢" and td.title_group("transfer_50m") == "transfer"
          and [td.TITLES[k]["rarity"] for k in ("transfer_100k", "transfer_1m", "transfer_10m", "transfer_50m")] == ["R", "SR", "SSR", "UR"])
    check("market condition", td.condition_text("sold_300") == "在市場賣出 300 張卡" and td.title_group("sold_1") == "market")

    # 🌟 UR / LR：卡冊裡現在有幾種角色 (同角色多張只算一種，賣掉就沒了)
    U = 60
    await udm.get_or_create_user(U)
    for i, (ck, r) in enumerate([("reimu", "UR"), ("reimu", "UR"), ("marisa", "UR"), ("remilia", "LR"), ("cirno", "SSR")]):
        sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, completeness) VALUES (?, ?, ?, 'x', ?, 0.5)", (f"u{i}", U, ck, r))
    s = await udm.get_title_stats(U)
    check("ur/lr kinds", (s["ur_kinds"], s["lr_kinds"]) == (2, 1))
    check("lr locked without 10 ur", (await udm.get_title_state(U))["unlocked"] == ["ur_1"])
    sql("DELETE FROM gacha_cards WHERE user_id = ? AND character_key IN ('reimu', 'marisa')", (U,))
    check("sold ur lost", (await udm.get_title_stats(U))["ur_kinds"] == 0 and (await udm.get_title_state(U))["unlocked"] == [])

    # 💎 完美卡：完整度 1.0000 (四捨五入 4 位)，角色 + 階級一樣只算一種
    P = 61
    await udm.get_or_create_user(P)
    for i, (ck, r, c) in enumerate([("reimu", "SR", 1.0), ("reimu", "SR", 1.0), ("reimu", "SSR", 0.99996),
                                    ("cirno", "SR", 0.9999), ("rumia", "R", 0.5)]):
        sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, completeness) VALUES (?, ?, ?, 'x', ?, ?)", (f"p{i}", P, ck, r, c))
    check("perfect kinds", (await udm.get_title_stats(P))["perfect_kinds"] == 2)
    check("perfect title", (await udm.get_title_state(P))["unlocked"] == ["perfect_1"])

    # 📚 卡池收集：紅魔鄉角色到齊 (階級不限) ➔ 全卡 ➔ 再加舊作全卡 = LR
    from Utils import gacha_pools as gp
    members = gp.pool_members()
    check("pool sizes", (len(members["classic"]), len(members["th06"])) == (15, 9)
          and sum(len(r) for r in members["classic"].values()) == 45 and sum(len(r) for r in members["th06"].values()) == 27)
    C = 62
    await udm.get_or_create_user(C)
    def add(pool, every_rarity, prefix):
        for cid, rs in members[pool].items():
            for r in (rs if every_rarity else rs[:1]):
                sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, completeness) VALUES (?, ?, ?, 'x', ?, 0.5)",
                    (f"{prefix}{cid}{r}", C, cid, r))
    add("th06", False, "a")
    st = await udm.get_title_stats(C)
    check("th06 chars", st["pool_chars:th06"] == 1 and st["pool_cards:th06"] == 0 and st["all_cards"] == 0)
    check("th06 chars title", "pool_th06_chars" in (await udm.get_title_state(C))["unlocked"])
    add("th06", True, "b")
    add("classic", True, "c")
    unlocked = (await udm.get_title_state(C))["unlocked"]
    check("all_cards needs th07 too", "pool_all" not in unlocked and "pool_th07_chars" not in unlocked)   # 🌸 2026-11-24 加妖妖夢
    add("th07", True, "d")
    unlocked = (await udm.get_title_state(C))["unlocked"]
    check("all pools LR", {"pool_th06_cards", "pool_classic_chars", "pool_classic_cards", "pool_th07_chars", "pool_th07_cards",
                           "pool_all"} <= set(unlocked))
    sql("DELETE FROM gacha_cards WHERE user_id = ? AND character_key = 'remilia' AND rarity = 'LR'", (C,))
    unlocked = (await udm.get_title_state(C))["unlocked"]
    check("sold one ➔ lose cards titles", "pool_all" not in unlocked and "pool_th06_cards" not in unlocked
          and "pool_th06_chars" in unlocked and "pool_classic_cards" in unlocked)
    check("th07 pool titles", td.TITLES["pool_th07_chars"]["name"] == "幽明結界的越境者" and td.TITLES["pool_th07_cards"]["rarity"] == "UR"
          and td.TITLES["luck_th07_lr"]["name"] == "機率境界的操縱者" and "八雲紫" in td.TITLES["luck_th07_lr"]["desc"]
          and td.condition_text("pool_th07_cards") == "妖妖夢卡池的卡全部收集 (每個階級)")
    check("pool condition text", td.condition_text("pool_th06_chars") == "紅魔鄉卡池的角色全部到齊"
          and td.condition_text("pool_classic_cards") == "舊作卡池的卡全部收集 (每個階級)")
    # 💕 推角：收藏冊裡有那位角色每個階級各一張完美卡 (完整度 1.0000)，名稱「我是XXX的狗!!!」，每位角色自動一個
    #    (2026-11-14 起只算收藏冊 locked = 1；卡冊裡的完美卡不算)
    O = 63
    await udm.get_or_create_user(O)
    cards = [("cirno", "SR", 1.0, 1), ("cirno", "SR", 0.3, 1), ("cirno", "SSR", 1.0, 1), ("cirno", "UR", 0.99996, 1),
             ("reimu", "SR", 1.0, 1), ("reimu", "SSR", 1.0, 1), ("reimu", "UR", 0.9999, 1),   # 靈夢 UR 不完美
             ("rumia", "R", 1.0, 0), ("rumia", "SR", 1.0, 0), ("rumia", "SSR", 1.0, 0)]       # 露米婭全在卡冊 ➔ 不算
    for i, (ck, r, c, lk) in enumerate(cards):
        sql("INSERT INTO gacha_cards (instance_id, user_id, character_key, name, rarity, completeness, locked) VALUES (?, ?, ?, 'x', ?, ?, ?)",
            (f"o{i}", O, ck, r, c, lk))
    st = await udm.get_title_stats(O)
    check("oshi counts", st["oshi:th06:cirno"] == 3 and st["oshi:classic:reimu"] == 2 and st["oshi:th06:rumia"] == 0)
    check("oshi ignores card book", st["perfect_kinds"] == 8)   # 完美卡稱號還是卡冊 + 收藏冊都算
    unlocked = (await udm.get_title_state(O))["unlocked"]
    check("oshi unlocked", "oshi_cirno" in unlocked and "oshi_reimu" not in unlocked)
    check("oshi name", td.TITLES["oshi_cirno"]["name"] == "我是琪露諾的狗!!!" and td.TITLES["oshi_cirno"]["rarity"] == "SR")
    check("oshi every character", all(f"oshi_{cid}" in td.TITLES and td.TITLES[f"oshi_{cid}"]["min"] == len(rs)
                                      for m in members.values() for cid, rs in m.items()))
    check("oshi condition", td.condition_text("oshi_cirno") == "收藏冊裡有琪露諾每個階級 (SR / SSR / UR) 各一張完美卡 (完整度 1.0000)")
    check("oshi groups", td.title_group("oshi_reimu") == "oshi_classic" and td.title_group("oshi_cirno") == "oshi_th06"
          and td.TITLE_GROUPS["oshi_th06"]["name"] == "💕 推角・紅魔鄉")
    sql("DELETE FROM gacha_cards WHERE instance_id = 'o2'")   # 賣掉琪露諾 SSR 完美卡
    check("oshi sold lost", "oshi_cirno" not in (await udm.get_title_state(O))["unlocked"])
    check("every pool has titles", all(any(t["stat"] == f"pool_{k}:{p}" for t in td.TITLES.values())
                                       for p in gp.GACHA_POOLS for k in ("chars", "cards")))

    # 📅 簽到稱號 (累積天數) 與連續簽到 (daily_streak / best_streak)
    D = 50
    check("daily titles", [td.TITLES[f"daily_{n}"]["name"] for n in (7, 30, 60, 100, 200, 365)]
          == ["三日坊主不再", "每日參拜", "風雨無阻", "百日參拜", "神社的一份子", "四季的參拜者"])
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        await udm.claim_daily(D, day, 3)
    def streak():
        con = sqlite3.connect(udm.DB_PATH); r = con.execute("SELECT daily_streak, best_streak, daily_count FROM users WHERE user_id = ?", (D,)).fetchone(); con.close(); return r
    check("streak 3", streak() == (3, 3, 3))
    check("same day twice", await udm.claim_daily(D, "2026-11-03", 3) is False and streak() == (3, 3, 3))
    await udm.claim_daily(D, "2026-11-05", 3)   # 11/04 沒簽 ➔ 斷掉
    check("streak broken, best kept", streak() == (1, 3, 4))
    await udm.claim_daily(D, "2026-11-06", 3)
    check("streak again", streak() == (2, 3, 5))
    await udm.claim_daily(D, "2026-12-01", 3)   # 跨月也照日期算
    sql("UPDATE users SET daily_count = 30, best_streak = 0 WHERE user_id = ?", (D,))
    check("daily titles unlocked", (await udm.get_title_state(D))["unlocked"] == ["daily_30", "daily_7"])
    check("daily stats", (await udm.get_title_stats(D))["daily_count"] == 30)
    check("daily condition", td.condition_text("daily_365") == "累積簽到 365 天")
    check("streak titles", [(td.TITLES[t]["rarity"], td.TITLES[t]["min"]) for t in ("streak_30", "streak_100", "streak_365")]
          == [("SSR", 30), ("UR", 100), ("LR", 365)])
    sql("UPDATE users SET best_streak = 100, daily_streak = 1 WHERE user_id = ?", (D,))
    check("streak uses best", (await udm.get_title_state(D))["unlocked"][:2] == ["streak_100", "streak_30"])
    check("streak condition", td.condition_text("streak_30") == "連續簽到 30 天")
    A = 1
    st = await udm.get_title_state(A)
    check("new player no titles", st["equipped"] is None and st["unlocked"] == [])
    check("cannot equip locked", await udm.set_equipped_title(A, "draw_10") is False)
    check("cannot equip unknown", await udm.set_equipped_title(A, "nope") is False)

    sql("INSERT INTO gacha_stats (user_id, total_draws) VALUES (?, 120)", (A,))
    st = await udm.get_title_state(A)
    check("unlocked after draws", st["unlocked"] == ["draw_100", "draw_10"])
    check("equip", await udm.set_equipped_title(A, "draw_100") and (await udm.get_title_state(A))["equipped"] == "draw_100")
    check("equip higher locked", await udm.set_equipped_title(A, "draw_500") is False
          and (await udm.get_title_state(A))["equipped"] == "draw_100")
    # 資料庫裡的稱號已不符條件 (例如之後改了門檻) ➔ 當成沒戴
    sql("UPDATE users SET equipped_title = 'draw_5000' WHERE user_id = ?", (A,))
    check("invalid equipped hidden", (await udm.get_title_state(A))["equipped"] is None)
    sql("UPDATE gacha_stats SET total_fusions = 12 WHERE user_id = ?", (A,))
    check("fusion stat read", (await udm.get_title_state(A))["unlocked"] == ["draw_100", "fusion_10", "draw_10", "fusion_1"])
    sql("UPDATE gacha_stats SET total_fusions = 0 WHERE user_id = ?", (A,))
    # 合成次數 (2026-11-13 起記錄)：合成才加，融合不加
    card = {"instance_id": "s1", "character_key": "reimu", "name": "x", "emoji": "x", "rarity": "SR",
            "title": "x", "completeness": 0.5, "obtained_at": "x"}
    await udm.add_gacha_cards(A, [card, dict(card, instance_id="s2")], draw_count=0)
    await udm.transform_cards(A, ["s1", "s2"], lambda cs: dict(cs[0], instance_id="s3"), count_synthesis=True)
    check("synthesis counted", (await udm.get_title_stats(A))["total_synths"] == 1
          and "synth_1" in (await udm.get_title_state(A))["unlocked"])
    await udm.add_gacha_cards(A, [dict(card, instance_id="s4")], draw_count=0)
    await udm.transform_cards(A, ["s3", "s4"], lambda cs: dict(cs[0], instance_id="s5"))
    check("plain transform not counted", (await udm.get_title_stats(A))["total_synths"] == 1)
    check("unequip", await udm.set_equipped_title(A, None) and (await udm.get_title_state(A))["equipped"] is None)

    # --- /profile 畫面 ---
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await bot.load_extension("Cogs.load-general.profile")
    cog = bot.get_cog("Profile")
    cmds = {c.name: c for c in cog.walk_app_commands()}

    it = Interaction(uid=A); await cmds["profile"].callback(cog, it, None, None)
    pv = it.view
    check("no title fixed color", accent(pv) == td.NO_TITLE_COLOR)
    # 0.35.039：資料卡沒有選單，一排按鈕；「🏷️ 修改稱號」另外跳出控制台 (分組 ➔ 稱號 ➔ 預覽 ➔ 確認)
    blabels = [b.label for b in pv.walk_children() if isinstance(b, discord.ui.Button)]
    check("buttons instead of selects", not selects(pv) and blabels[-4:] == ["⚡ 恢復體力", "⛩️ 前往神社", "🏷️ 修改稱號", "🖼️ 修改名片"])
    class Msg:   # 資料卡訊息 (確認換上後會被編輯)
        def __init__(s): s.view = None
        async def edit(s, **kw): s.view = kw.get("view")
    pv.message = Msg()
    def containers(v): return [c for c in v.children if isinstance(c, discord.ui.Container)]
    def pbtn(v, label): return next(b for b in v.walk_children() if isinstance(b, discord.ui.Button) and b.label.startswith(label))
    async def ppick(v, idx, value, uid=A): await selects(v)[idx].callback(Interaction(uid=uid, data={"values": [value]}))
    async def ppress(v, label, uid=A): await pbtn(v, label).callback(Interaction(uid=uid))

    io = Interaction(uid=A); await pv.on_open_title(io)
    tv = io.view
    check("panel is separate", tv is not pv and type(tv).__name__ == "TitlePickerView" and len(selects(tv)) == 2)
    sel = selects(tv)
    all_groups = list(td.group_titles(list(td.TITLES)))   # 2026-11-24 加 TH07 後 27 組 ➔ 分組選單翻頁 (一頁 25)
    check("all groups listed (page 1)", [o.value for o in sel[0].options] == all_groups[:25] and len(all_groups) > 25)
    check("opens on highest unlocked group", next(o for o in sel[0].options if o.default).value == "draw")
    st = {o.value: o.description for o in sel[1].options}
    check("status unlocked / locked", st["draw_100"] == "✅ 已解鎖" and st["draw_5000"].startswith("🔒 ")
          and td.condition_text("draw_5000") in st["draw_5000"])
    check("nothing to confirm", pbtn(tv, "✅").disabled and pbtn(tv, "✖️ 卸下稱號").disabled and len(containers(tv)) == 1)

    # 🔒 沒解鎖的：說明怎麼拿，不能確認
    await ppick(tv, 1, "draw_5000")
    check("locked explains", "還沒解鎖" in texts(tv) and td.condition_text("draw_5000") in texts(tv)
          and pbtn(tv, "✅").disabled and len(containers(tv)) == 1)
    # ✅ 已解鎖：上面出現預覽 (稱號色條)，確認才換上
    await ppick(tv, 1, "draw_100")
    pc = containers(tv)[0]
    check("preview shown", len(containers(tv)) == 2 and "👀 預覽" in texts(tv) and "**[R] 虔誠的參拜者**" in texts(tv)
          and pc.accent_color.value == td.RARITY_COLORS["R"] and not pbtn(tv, "✅ 確認換上").disabled)
    check("not saved before confirm", (await udm.get_title_state(A))["equipped"] is None)
    await ppress(tv, "✅ 確認換上")
    check("saved", (await udm.get_title_state(A))["equipped"] == "draw_100" and "已換上" in texts(tv) and len(containers(tv)) == 1)
    t = texts(pv.message.view)
    check("profile card updated", "**[R] 虔誠的參拜者**" in t and f"-# *{td.TITLES['draw_100']['desc']}*" in t
          and "原本的資料卡也換好了" in texts(tv))
    check("title under name", t.index("的幻想鄉通行證") < t.index("[R] 虔誠的參拜者") < t.index("資料卡 • TouHouBot"))
    check("title color", accent(pv) == td.RARITY_COLORS["R"])

    # 預覽到確認之間條件變了 ➔ 擋下
    tv.pending = ("equip", "draw_5000")
    await ppress(tv, "✅ 確認換上")
    check("locked rejected", "還沒有解鎖" in texts(tv) and (await udm.get_title_state(A))["equipped"] == "draw_100")
    # ↩️ 取消
    await ppick(tv, 1, "draw_10"); await ppress(tv, "↩️ 取消")
    check("cancel", tv.selected is None and tv.pending is None and len(containers(tv)) == 1)

    # 私人資料卡一樣用稱號顏色 (2026-11-13 使用者)
    await udm.update_visibility(A, False)
    it = Interaction(uid=A); await cmds["profile"].callback(cog, it, None, None)
    check("private same color", accent(it.view) == td.RARITY_COLORS["R"] and "[R] 虔誠的參拜者" in texts(it.view))
    await udm.update_visibility(A, True)

    # 別人看得到稱號，但沒有按鈕；別人也按不了我的控制台
    it = Interaction(uid=2); await cmds["profile"].callback(cog, it, types.SimpleNamespace(id=A, display_name="t", display_avatar=avatar), None)
    check("others see title", "[R] 虔誠的參拜者" in texts(it.view) and not selects(it.view)
          and "🏷️ 修改稱號" not in [b.label for b in it.view.walk_children() if isinstance(b, discord.ui.Button)])
    check("others blocked on panel", not await tv.interaction_check(Interaction(uid=2)))

    # ✖️ 卸下：一樣先預覽再確認
    await ppress(tv, "✖️ 卸下稱號")
    check("unequip preview", "(不戴稱號)" in texts(tv) and containers(tv)[0].accent_color.value == td.NO_TITLE_COLOR
          and pbtn(tv, "✅ 確認卸下") is not None)
    await ppress(tv, "✅ 確認卸下")
    check("unequip saved", (await udm.get_title_state(A))["equipped"] is None and "已卸下" in texts(tv)
          and "虔誠的參拜者" not in texts(pv.message.view))
    # 資料卡過期 ➔ 不假裝更新
    pv.stop()
    await ppick(tv, 1, "draw_100"); await ppress(tv, "✅ 確認換上")
    check("expired card notice", "已經過期" in texts(tv) and (await udm.get_title_state(A))["equipped"] == "draw_100")

    # 沒有任何稱號 ➔ 控制台照樣打開，全部 🔒
    it = Interaction(uid=3); await cmds["profile"].callback(cog, it, None, None)
    io = Interaction(uid=3); await it.view.on_open_title(io)
    nv = io.view
    check("none all locked", "已解鎖 `0`" in texts(nv) and all(o.description.startswith("🔒") for o in selects(nv)[1].options)
          and pbtn(nv, "✅").disabled)

    # 🛠️ /admin-user title：管理員直接給 / 戴上 / 收回稱號，不用符合條件
    from Utils import config
    config.ADMIN_IDS = config.ADMIN_IDS | {900}
    await bot.load_extension("Cogs.load-general.Admin-user")
    acog = bot.get_cog("UserAdmin")
    title_cmd = next(c for c in acog.walk_app_commands() if c.name == "title")
    G = 70
    gtarget = types.SimpleNamespace(id=G, display_name="g")

    # 0.35.035：控制台 (分組選單 ➔ 稱號選單 + 翻頁 ➔ 按鈕)，不再用 autocomplete (稱號快 200 個)
    check("title cmd only target param", [p.name for p in title_cmd.parameters] == ["target"])
    def btn(v, label): return next(b for b in v.walk_children() if isinstance(b, discord.ui.Button) and label in b.label)
    async def pick(view, select_index, value, uid=900):
        it = Interaction(uid=uid, data={"values": [value]})
        await selects(view)[select_index].callback(it)
        return it
    async def press(view, label, uid=900):
        it = Interaction(uid=uid)
        await btn(view, label).callback(it)
        return it

    it = Interaction(uid=900)
    await title_cmd.callback(acog, it, gtarget)
    tv = it.view
    check("panel opens", "稱號控制台：g" in texts(tv) and len(selects(tv)) == 2)
    gsel = selects(tv)[0]
    groups_all = list(td.group_titles(list(td.TITLES)))
    check("group select ≤ 25, first page", len(gsel.options) <= 25 and [o.value for o in gsel.options] == groups_all[:25])
    check("buttons disabled before pick", btn(tv, "戴上").disabled and btn(tv, "🎁 給").disabled and btn(tv, "收回").disabled)

    # 選 🎰 祈願 ➔ LR 幻想鄉第一信仰 ➔ 戴上 (順便給)
    await pick(tv, 0, "draw")
    await pick(tv, 1, "draw_5000")
    check("picked shows status", "[LR] 幻想鄉第一信仰" in texts(tv) and "🔒 沒有" in texts(tv) and not btn(tv, "戴上").disabled)
    await press(tv, "戴上")
    st = await udm.get_title_state(G)
    check("admin equip any title", st["equipped"] == "draw_5000" and st["unlocked"] == ["draw_5000"] and "戴上了" in texts(tv))
    check("equipped status", "🏷️ 戴著" in texts(tv) and btn(tv, "戴上").disabled and not btn(tv, "收回").disabled)

    # 給 🔥 連續簽到 365
    await pick(tv, 0, "streak")
    await pick(tv, 1, "streak_365")
    await press(tv, "🎁 給")
    check("admin grant", (await udm.get_title_state(G))["unlocked"] == ["draw_5000", "streak_365"] and "已給" in texts(tv))
    check("grant button off after", btn(tv, "🎁 給").disabled)

    # 收回戴著的 ➔ 也卸下
    await pick(tv, 0, "draw")
    await pick(tv, 1, "draw_5000")
    await press(tv, "收回")
    st = await udm.get_title_state(G)
    check("admin revoke drops equipped", st["unlocked"] == ["streak_365"] and st["equipped"] is None and "已收回" in texts(tv))

    # ⛩️ 神社 35 個 ➔ 稱號選單翻頁，第 2 頁的也選得到
    await pick(tv, 0, "shrine")
    n_shrine = len(td.group_titles(list(td.TITLES))["shrine"])
    check(f"shrine page 1 ({n_shrine})", n_shrine > 25 and len(selects(tv)[1].options) == 25 and "第 1 / 2 頁" in selects(tv)[1].placeholder)
    await press(tv, "下一頁")
    page2 = [o.value for o in selects(tv)[1].options]
    check("shrine page 2", len(page2) == n_shrine - 25 and "第 2 / 2 頁" in selects(tv)[1].placeholder)
    await pick(tv, 1, page2[-1])
    await press(tv, "🎁 給")
    check("grant from page 2", page2[-1] in await udm.get_granted_titles(G))
    await press(tv, "卸下")
    check("unequip", (await udm.get_title_state(G))["equipped"] is None)

    # 元件數、選單選項數
    def count(item): return 1 + sum(count(ch) for ch in getattr(item, "children", []))
    check(f"panel components {sum(count(i) for i in tv.children)} ≤ 40", sum(count(i) for i in tv.children) <= 40
          and all(len(s_.options) <= 25 for s_ in selects(tv)))

    # 亂傳的值不會壞掉；別人不能按
    await pick(tv, 1, "亂打")
    check("bad title value ignored", btn(tv, "戴上").disabled)
    it = Interaction(uid=G)
    check("other user blocked", not await tv.interaction_check(it) and "不是你的控制台" in texts(it.view))
    it = Interaction(uid=G); await title_cmd.callback(acog, it, None)
    check("non-admin blocked", "無權限" in texts(it.view))

    # 自己達成條件的稱號收回也不會不見
    it = Interaction(uid=900)
    await title_cmd.callback(acog, it, types.SimpleNamespace(id=A, display_name="a"))
    av = it.view
    await pick(av, 0, "draw")
    await pick(av, 1, "draw_100")
    check("earned not granted ➔ revoke off", btn(av, "收回").disabled and "✅ 自己達成" in texts(av))
    await press(av, "🎁 給")
    await press(av, "收回")
    check("revoke earned keeps", "draw_100" in (await udm.get_title_state(A))["unlocked"] and "自己有達成條件" in texts(av))

    # --- 🙏 客人稱號 (0.35.001)：每種客人 SR 招待 50 次 / UR 成功招待 50 次；活動客人每個活動一組 ---
    from Database import shrine_data as sd
    from Database.events import load_events
    ev_guests = {k for ev in load_events().values() for k in ev.get("guests", {})}
    kinds = set(sd.GUESTS) | ev_guests
    check(f"guest titles {len(kinds)}", all(td.guest_title_id(k, t) in td.TITLES for k in kinds for t in ("sr", "ur"))
          and len([t for t in td.TITLES if t.startswith("guest_")]) == 2 * len(kinds) == 24)
    check("guest rarity / min", all(td.TITLES[td.guest_title_id(k, "sr")]["rarity"] == "SR" and td.TITLES[td.guest_title_id(k, "ur")]["rarity"] == "UR"
                                    and td.TITLES[td.guest_title_id(k, "sr")]["min"] == 50 for k in kinds))
    check("guest names unique", len({td.TITLES[t]["name"] for t in td.TITLES}) == len(td.TITLES))
    check("guest groups", td.title_group("guest_kappa_sr") == "guest" and td.title_group("guest_fairy_maid_ur") == "guest_th06_scarlet_mist"
          and td.TITLE_GROUPS["guest_th06_scarlet_mist"]["name"] == "🙏 客人・紅霧異變"
          and list(td.TITLE_GROUPS).index("guest_th06_scarlet_mist") == list(td.TITLE_GROUPS).index("guest") + 1)
    check("shrine group unchanged", td.title_group("shrine_serve") == "shrine")
    check("guest names from data", td.TITLES["guest_kappa_ur"]["name"] == "小黃瓜外交官" and td.TITLES["guest_familiar_bat_sr"]["name"] == "蝙蝠的落腳處")
    check("guest condition", td.condition_text("guest_oni_sr") == "招待小鬼 50 次"
          and td.condition_text("guest_oni_ur") == "成功招待小鬼 50 次 (額外端上牠最愛的料理)")
    check("guest desc n", td.title_desc("guest_fox_sr", {"ps:serve_guest:fox": 12}).startswith("招待了 12 次狐妖"))
    check("guest unlock", td.unlocked_titles({"ps:serve_guest:fox": 50, "ps:serve_fav:fox": 49}) == ["guest_fox_sr"])
    # 活動檔沒寫 titles 的客人 ➔ 預設名稱
    saved = dict(td.TITLES)
    td._guest_titles("test_ghost", {"name": "幽靈"}, "guest_x", None, "x")
    check("guest default names", td.TITLES["guest_test_ghost_sr"]["name"] == "幽靈的常客" and td.TITLES["guest_test_ghost_ur"]["name"] == "幽靈的知己")
    td.TITLES.clear(); td.TITLES.update(saved)
    # player_stats 記的次數 ➔ get_title_stats 讀得到
    con = sqlite3.connect(udm.DB_PATH)
    con.execute("INSERT INTO player_stats (user_id, stat, value) VALUES (?, 'serve_guest:kappa', 50), (?, 'serve_fav:kappa', 50)", (C, C))
    con.commit(); con.close()
    st = await udm.get_title_state(C)
    check("guest unlocked from stats", {"guest_kappa_sr", "guest_kappa_ur"} <= set(st["unlocked"]))

    # --- 🗺️ 足跡稱號 (0.35.002)：每個地點 SR 200 趟 / UR 1000 趟；幻想鄉踏破 SR、活動踏破 SSR (永久保留) ---
    ev_locs = {eid: [l["id"] for l in ([ev["location"]] if ev.get("location") else []) + list(ev.get("locations", []))]
               for eid, ev in load_events().items()}
    all_locs = set(sd.LOCATIONS) | {l for ls in ev_locs.values() for l in ls}
    check(f"trek titles {len(all_locs)}", all(td.trek_title_id(l, t) in td.TITLES for l in all_locs for t in ("sr", "ur"))
          and td.TITLES[td.trek_title_id("village", "sr")]["min"] == 200 and td.TITLES[td.trek_title_id("village", "ur")]["min"] == 1000)
    check("trek groups", td.title_group("trek_village_sr") == "trek" and td.title_group("trek_scarlet_kitchen_sr") == "trek_th06_scarlet_mist"
          and td.title_group("trek_all") == "trek" and td.title_group("trek_th06_scarlet_mist_all") == "trek_th06_scarlet_mist"
          and td.TITLE_GROUPS["trek_th06_scarlet_mist"]["name"] == "🗺️ 足跡・紅霧異變")
    check("trek names", td.TITLES["trek_kourindou_ur"]["name"] == "外界道具鑑定士" and td.TITLES["trek_scarlet_kitchen_sr"]["name"] == "紅魔館廚房的小偷"
          and td.TITLES["trek_all"]["rarity"] == "SR" and td.TITLES["trek_th06_scarlet_mist_all"]["name"] == "紅霧異變 • 踏破"
          and td.TITLES["trek_th06_scarlet_mist_all"]["rarity"] == "SSR")
    check("event trek desc from file", td.TITLES["trek_th06_scarlet_mist_all"]["desc"].startswith("趁著紅霧溜進紅魔館的廚房"))
    check("trek condition", td.condition_text("trek_misty_lake_sr") == "在霧之湖採集 200 趟"
          and td.condition_text("trek_all") == "9 個一般採集地點都至少採集過 1 趟 (活動地點不算)")
    base_visits = {f"ps:explore:{l}": 1 for l in sd.LOCATIONS}
    check("trek base needs all", td.trek_stats({**base_visits, "ps:explore:village": 0})["trek_base"] == 8
          and td.trek_stats(base_visits)["trek_base"] == 9)
    check("event loc not in base", td.trek_stats({"ps:explore:scarlet_kitchen": 5}) == {"trek_base": 0, "trek_ev:th06_scarlet_mist": 1})
    check("names still unique", len({td.TITLES[t]["name"] for t in td.TITLES}) == len(td.TITLES))
    # 踏破第一次達成 ➔ earned_titles 永久保留 (之後統計變了 / 新增地點也不會失去)
    D = 4040
    await udm.get_or_create_user(D)
    con = sqlite3.connect(udm.DB_PATH)
    con.executemany("INSERT INTO player_stats (user_id, stat, value) VALUES (?, ?, 1)",
                    [(D, f"explore:{l}") for l in list(sd.LOCATIONS) + ["scarlet_kitchen"]])
    con.commit(); con.close()
    st = await udm.get_title_state(D)
    check("trek unlocked", {"trek_all", "trek_th06_scarlet_mist_all"} <= set(st["unlocked"])
          and {"trek_all", "trek_th06_scarlet_mist_all"} <= set(await udm.get_earned_titles(D)))
    sql("DELETE FROM player_stats WHERE user_id = ?", (D,))
    check("trek kept", {"trek_all", "trek_th06_scarlet_mist_all"} <= set((await udm.get_title_state(D))["unlocked"]))

    # --- 🍀 運氣稱號 (0.35.005)：採集事件、運勢、保底、90 抽內出 UR (每個卡池分開；2026-11-22 前是十連雙 UR) ---
    luck = [t for t in td.TITLES if t.startswith("luck_")]
    check(f"luck titles {len(luck)}", len(luck) == 11 + 3 * len(__import__("Utils.gacha_pools", fromlist=["x"]).GACHA_POOLS))
    check("luck tiers", [(td.TITLES[f"luck_pity_{t}"]["rarity"], td.TITLES[f"luck_pity_{t}"]["min"]) for t in ("ssr", "ur", "lr")]
          == [("SSR", 10), ("UR", 50), ("LR", 100)]
          and (td.TITLES["luck_good_sr"]["min"], td.TITLES["luck_good_ur"]["min"]) == (20, 100)
          and (td.TITLES["luck_kyo_sr"]["min"], td.TITLES["luck_kyo_ssr"]["rarity"]) == (10, "SSR"))
    check("luck pool groups", td.title_group("luck_classic_lr") == "luck" and td.title_group("luck_th06_lr") == "luck_th06"
          and td.TITLE_GROUPS["luck_th06"]["name"] == "🍀 運氣・紅魔鄉"
          and [td.TITLES[luck_t]["min"] for luck_t in ("luck_th06_ssr", "luck_th06_ur", "luck_th06_lr")] == [1, 5, 10])
    check("luck names", td.TITLES["luck_classic_lr"]["name"] == "魔界神也嫉妒的手氣" and td.TITLES["luck_th06_lr"]["name"] == "命運的操縱者"
          and td.TITLES["luck_bad_sr"]["name"] == "倒楣巫女")
    check("luck condition", td.condition_text("luck_th06_ur") == "在紅魔鄉卡池距離上次 UR 90 抽內就出 UR 5 次"
          and td.condition_text("luck_pity_ssr") == "祈願觸發 10 次保底 (所有卡池合計)")
    check("names unique with luck", len({td.TITLES[t]["name"] for t in td.TITLES}) == len(td.TITLES))
    # 計數：90 抽內出的 UR (卡上的 lucky，一抽一次；LR、保底送的不算)、保底張數、簽到大吉 / 凶
    E = 5050
    def lc(i, r, pity=False, lucky=False):
        return {"instance_id": f"c_luck_{E}_{i}", "character_key": "cirno", "name": "琪露諾", "emoji": "🧊", "rarity": r,
                "title": "t", "completeness": 0.5, "obtained_at": "2026-11-16 12:00:00", "pity": pity, "lucky": lucky}
    await udm.get_or_create_user(E)
    await udm.draw_gacha(E, "th06", 10, 0, lambda s: ([lc(0, "UR", True), lc(1, "LR")] + [lc(i, "N") for i in range(2, 10)], 0, True))
    await udm.draw_gacha(E, "th06", 10, 0, lambda s: ([lc(10, "UR", lucky=True)] + [lc(i, "N") for i in range(11, 20)], 0, True))
    await udm.draw_gacha(E, "classic", 1, 0, lambda s: ([lc(20, "UR", True)], 0, True))
    ps = await udm.get_player_stats(E)
    check(f"luck gacha stats {ps}", ps.get("tenpull_2ur:th06") == 1 and not ps.get("tenpull_2ur:classic") and ps.get("gacha_pity") == 2)
    await udm.claim_daily(E, "2026-11-16", 5); await udm.claim_daily(E, "2026-11-16", 5)   # 同一天第二次不算
    await udm.claim_daily(E, "2026-11-17", 0); await udm.claim_daily(E, "2026-11-18", 3)
    ps = await udm.get_player_stats(E)
    check(f"fortune stats", ps.get("fortune_5") == 1 and ps.get("fortune_0") == 1 and not ps.get("fortune_3"))
    st = await udm.get_title_state(E)
    check("luck_th06_ssr unlocked", "luck_th06_ssr" in st["unlocked"] and "luck_classic_ssr" not in st["unlocked"])

    # --- 🍳 美食家稱號 (0.35.006)：料理圖鑑、吃體力料理、分類全收 (keep)、活動食譜 (keep) ---
    gm = [t for t in td.TITLES if t.startswith("gourmet_")]
    check(f"gourmet titles {len(gm)}", len(gm) == 6 + 4 + len(td.GOURMET_EVENT_DISHES))
    check("gourmet tiers", [(td.TITLES[f"gourmet_dex_{x}"]["rarity"], td.TITLES[f"gourmet_dex_{x}"]["min"]) for x in ("sr", "ssr", "ur")]
          == [("SR", 10), ("SSR", 20), ("UR", 30)]
          and [(td.TITLES[f"gourmet_eat_{x}"]["rarity"], td.TITLES[f"gourmet_eat_{x}"]["min"]) for x in ("sr", "ur", "lr")]
          == [("SR", 100), ("UR", 500), ("LR", 1000)])
    check("gourmet cat mins", [td.TITLES[f"gourmet_cat_{c}"]["min"] for c in ("food", "drink", "dessert", "stamina")] == [9, 10, 9, 5]
          and all(td.TITLES[f"gourmet_cat_{c}"]["keep"] and td.TITLES[f"gourmet_cat_{c}"]["rarity"] == "SR" for c in ("food", "drink", "dessert", "stamina")))
    ev_t = td.TITLES["gourmet_th06_scarlet_mist_all"]
    check("gourmet event", ev_t["name"] == "紅霧異變 • 食譜全收" and ev_t["rarity"] == "SSR" and ev_t["keep"] and ev_t["min"] == 3
          and ev_t["desc"].startswith("女僕長筆記上") and td.title_group("gourmet_th06_scarlet_mist_all") == "gourmet_th06_scarlet_mist"
          and td.TITLE_GROUPS["gourmet_th06_scarlet_mist"]["name"] == "🍳 美食家・紅霧異變")
    check("gourmet condition", td.condition_text("gourmet_cat_stamina") == "體力類的料理全部做過 (5 道)"
          and td.condition_text("gourmet_eat_sr") == "累計吃 100 個體力道具 (含簽到的飯糰)")
    gs = td.gourmet_stats({"ps:cook:ran_inari": 1, "ps:cook:hell_nabe": 2, "ps:cook:evt_napolitan": 1})
    check(f"gourmet stats {gs}", gs["dex"] == 2 and gs["dex_cat:food"] == 1 and gs["dex_cat:stamina"] == 1 and gs["dex_ev:th06_scarlet_mist"] == 1)
    check("names unique with gourmet", len({td.TITLES[t]["name"] for t in td.TITLES}) == len(td.TITLES))
    # 吃體力道具 ➔ eat_stamina；做完一類 ➔ 分類全收永久保留
    F = 6060
    await udm.add_item(F, "reimu_onigiri", 3)
    await udm.use_stamina_item(F, "reimu_onigiri", 60, qty=2)
    check("eat stat", (await udm.get_player_stats(F)).get("eat_stamina") == 2)
    from Database import shrine_data as sd2
    con = sqlite3.connect(udm.DB_PATH)
    con.executemany("INSERT INTO player_stats (user_id, stat, value) VALUES (?, ?, 1)", [(F, f"cook:{d}") for d in sd2.STAMINA_RECIPES])
    con.commit(); con.close()
    st = await udm.get_title_state(F)
    check("cat full unlocked", "gourmet_cat_stamina" in st["unlocked"] and "gourmet_cat_stamina" in await udm.get_earned_titles(F))
    sql("DELETE FROM player_stats WHERE user_id = ? AND stat LIKE 'cook:%'", (F,))
    check("cat full kept", "gourmet_cat_stamina" in (await udm.get_title_state(F))["unlocked"])

    # --- ⛩️ 神社分級 (0.35.009)：每項 N / R / SR / SSR (原本的) / UR ---
    tiers = {"serve": (1, 10, 50, 100, 500), "explore": (10, 50, 100, 500, 1000), "youkai": (5, 20, 100, 300, 500),
             "cook": (5, 20, 100, 300, 500), "clean": (1, 10, 50, 100, 500),
             "collect": (10_000, 100_000, 1_000_000, 10_000_000, 100_000_000), "shop": (1, 10, 50, 100, 500)}
    ok_tiers = all([td.TITLES[f"shrine_{k}{s}"]["min"] for s in ("_n", "_r", "_sr", "", "_ur")] == list(v)
                   and [td.TITLES[f"shrine_{k}{s}"]["rarity"] for s in ("_n", "_r", "_sr", "", "_ur")] == ["N", "R", "SR", "SSR", "UR"]
                   for k, v in tiers.items())
    check("shrine tiers", ok_tiers and td.TITLES["shrine_explore"]["name"] == "採集達人")
    check("shrine unlock", td.unlocked_titles({"ps:explore": 499})[:1] == ["shrine_explore_sr"]
          and "shrine_explore" in td.unlocked_titles({"ps:explore": 500}))
    check("shrine collect short", td.title_desc("shrine_collect_n", {"ps:collect_money": 15000}).startswith("從賽錢箱回收了 15K"))

    # --- 稱號控制台分頁：⛩️ 神社 35 個 ➔ 兩頁；戴著的稱號在第 2 頁 ➔ 一打開就在第 2 頁 ---
    shrine = td.group_titles(sorted(td.TITLES, key=lambda t: -td.RARITY_ORDER[td.TITLES[t]["rarity"]]))["shrine"]
    late = shrine[-1]
    await udm.set_granted_title(C, late, True)
    await udm.set_equipped_title(C, late)
    it = Interaction(uid=C); await cmds["profile"].callback(cog, it, None, None)
    io = Interaction(uid=C); await it.view.on_open_title(io)
    gv = io.view
    sel = selects(gv)
    check("open equipped group + page", next(o for o in sel[0].options if o.default).value == "shrine"
          and "第 2 / 2 頁" in sel[1].placeholder and any(o.value == late and o.description == "🏷️ 戴著" for o in sel[1].options))
    await next(b for b in gv.walk_children() if isinstance(b, discord.ui.Button) and b.label == "◀️ 上一頁").callback(Interaction(uid=C))
    check("title page 1", "第 1 / 2 頁" in selects(gv)[1].placeholder and len(selects(gv)[1].options) == 25)
    def count(item): return 1 + sum(count(ch) for ch in getattr(item, "children", []))
    await selects(gv)[1].callback(Interaction(uid=C, data={"values": [selects(gv)[1].options[0].value]}))
    check(f"panel components {sum(count(i) for i in gv.children)} ≤ 40", sum(count(i) for i in gv.children) <= 40
          and all(len(x.options) <= 25 for x in selects(gv)))

asyncio.run(main())
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

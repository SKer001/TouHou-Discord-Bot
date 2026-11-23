"""
📚 🎴 抽卡與卡牌・教學書 (0.36.000；0.37.003 改成新機率；0.37.005 活動卡池不寫死，照開書時進行中的活動)
格式見 Components/guide_components.py；數字從抽卡 Cog (Cogs/load-gacha/gacha.py) 的常數讀，開畫面時才算
(Cog 模組用 importlib 在函式裡取，/admin-sys reload 之後拿得到新版)
"""
import importlib
from statistics import NormalDist

# 抽到的完整度 = gauss(0, 0.35)² 夾在 0.001 ~ 1.000 (沒有常數可讀)
# 來源：Cogs/load-gacha/gacha.py GachaCardSys.generate_completeness
COMP_SIGMA = 0.35
COMP_MIN, COMP_MAX = 0.001, 1.0


def _gacha():
    return importlib.import_module("Cogs.load-gacha.gacha")


def _gacha_components():
    return importlib.import_module("Cogs.load-gacha.Components.gacha_components")


def _pct(x: float) -> str:
    """0.123 ➔ 12%、0.0456 ➔ 4.6%、0.0043 ➔ 0.43%"""
    p = x * 100
    if p >= 10:
        return f"{p:.0f}%"
    if p >= 1:
        return f"{p:.1f}%"
    return f"{p:.2f}%"


def _comp_at_least(c: float) -> float:
    """抽到的完整度 ≥ c 的機率 (照 generate_completeness 的分布)"""
    return 2 * (1 - NormalDist(0, COMP_SIGMA).cdf(c ** 0.5))


def _grades() -> list[tuple[str, str, float]]:
    """完整度品相 [(emoji, 名稱, 下限), ...] 由高到低；直接掃 get_completeness_eval，門檻改了這裡跟著變"""
    gcomp = _gacha_components()
    out, prev = [], None
    for i in range(10001):
        c = i / 10000
        s = gcomp.get_completeness_eval(c)[0]
        key = (s.split(" ", 1)[0], s[s.rfind("[") + 1:s.rfind("]")])
        if key != prev:
            out.append((key[0], key[1], c))
            prev = key
    return out[::-1]


def _rarity_names(g) -> list[str]:
    return sorted(g.RARITY_ORDER, key=g.RARITY_ORDER.get)


def _pull(ctx: dict | None = None) -> str:
    """ctx = 開書時讀的進行中活動 (guide_components.current_context)；不要把某個活動寫死成例子"""
    g = _gacha()
    event_pool = ((ctx or {}).get("rules") or {}).get("gacha_event_pool")
    ur, rar = g.PITY_RARITY, g.RARITIES
    rates = g.base_rates()
    rate_line = "、".join(f"{r} {g.rate_text(rates[r] / 100)}" for r in rar)
    combos = sorted({tuple(v["rarities"]) for v in g.GACHA_POOL.values()}, key=lambda t: g.RARITY_ORDER.get(t[0], 0))
    (n0, p0), (n1, p1), (n2, p2) = g.UR_CURVE[:3]
    others = [r for r in rar if r != ur]
    top = others[-1]   # 最高階 (LR)：固定機率，不影響保底

    pool_lines, no_pity, stats = [], [], None
    for key, p in g.GACHA_POOLS.items():
        chars = g.pool_characters(key)
        st = g.ur_cycle_stats(key)
        stats = stats or (st if st["avg"] else None)
        avg = f" · 平均約 **{st['avg']:.0f}** 抽一張 {ur}" if st["avg"] else ""
        if p.get("event_only"):
            note = g.open_note(key).replace("🎪 ", "")
            now = "　🟢 **現在開放中**" if event_pool and event_pool.get("key") == key else ""
            pool_lines.append(f"- **{p['name']}**：{p['desc']}，共 **{len(chars)}** 位角色{avg}；"
                              f"🎪 平常不能抽，只有**{note}**從「🎪 活動限定卡池」抽得到{now}")
        else:
            pool_lines.append(f"- **{p['name']}**：{p['desc']}，共 **{len(chars)}** 位角色{avg}")
        if not st["avg"]:
            no_pity.append(p["name"])

    one, ten = g.draw_cost(1), g.draw_cost(10)
    ura_min = importlib.import_module("Database.ura.rules").MIN_COMPLETENESS
    lines = [
        "向博麗神社的賽錢箱投賽錢**祈願**，就能抽到東方角色的卡牌。打 `/card gacha`，選**卡池**和**單抽 / 十連**就開抽。",
        "",
        "### 🎰 卡池",
        *pool_lines,
        "- **🎪 活動限定卡池**：只在活動期間開放，抽哪個卡池由那個活動決定 (可能是上面標 🎪 的卡池，"
        "也可能是活動自己的限定卡池)，結果畫面的卡池名稱會標「・〇〇限定」；沒有的時候選它會提示「🎪 目前沒有進行中的活動卡池。」",
        *([f"-# 🟢 現在的活動限定卡池：{event_pool['name']}" if event_pool else "-# 現在沒有開放活動限定卡池"]
          if ctx is not None else []),
        "",
        "### 💰 價格",
        f"- 單抽 **{one:,}** 賽錢、十連 **{ten:,}** 賽錢" + (" (十連就是 10 抽的錢，沒有折扣)" if ten == one * 10 else ""),
        "- 賽錢不夠時不會扣錢，也不會抽",
        "-# 賽錢可以靠 `/daily` 簽到和⛩️ 神社經營賺 (詳見各自的教學書)；活動期間價格可能變動，以結果畫面上寫的為準",
        "",
        "### 🎲 機率",
        "- 每一抽**先抽階級，再從卡池裡有這個階級的角色平均抽一位**",
        f"- 起始機率：{rate_line}",
        f"- 每位角色只有**連續的 3 個階級** ({'、'.join(' / '.join(c) for c in combos)})，"
        f"所以只有階級裡有 {ur} 的角色抽得到 {ur}；每位角色的階級可以在 `/character` 看到",
        f"- {top} 固定 {g.rate_text(rates[top] / 100)}，跟保底無關",
        "-# 活動期間機率可能調整 (用 `/event info` 看)，按「📊 機率表」看到的就是現在的機率",
        "",
        f"### 🎯 {ur} 越抽越容易出 (保底)",
        f"- **每個卡池各自計算**「距離上次 {ur} 第幾抽」",
        f"- 第 1～{n0} 抽 {ur} 是 {p0:g}%，第 {n0 + 1} 抽起慢慢升高 (第 {n1} 抽 {p1:g}%、第 {n2} 抽 {p2:g}%)，"
        f"**第 {g.PITY_THRESHOLD} 抽必定出 {ur}**；多出來的 {ur} 機率是從 {' / '.join(g.CURVE_SOURCES)} 扣的",
        f"- 抽到 {ur} 就從 0 重新算；抽到 {top} **不會**重置；十連也是一抽一抽算",
    ]
    if stats:
        cum = stats["cum"]
        lines.append(f"-# 算起來：{n0} 抽內出 {ur} 約 {_pct(cum[n0])}、{n1} 抽內約 {_pct(cum[n1])}、"
                     f"吃到保底約 {_pct(stats['pity'])}，平均約 {stats['avg']:.0f} 抽一張")
    if no_pity:
        lines.append(f"-# ⚠️ {'、'.join(no_pity)}目前沒有階級裡有 {ur} 的角色，沒有保底")
    lines += [
        "",
        "### 📏 完整度",
        f"- 每張卡都有一個 **{COMP_MIN:.4f} ~ {COMP_MAX:.4f}** 的完整度，抽到時隨機決定，跟階級無關",
        f"- 大部分的卡都很低：約 {_pct(1 - _comp_at_least(0.1))} 不到 0.1，"
        f"直接抽到 **{COMP_MAX:.4f} (完美)** 只有約 {_pct(_comp_at_least(COMP_MAX - 0.00005))}",
        "- 完整度會顯示成品相：" + "、".join(
            f"{e} {n}" + (f" ({low:g} 以上)" if low > 0 else " (更低)") for e, n, low in _grades()),
        "- 完整度會影響合成、融合 (第 3 章)、分解能換多少賽錢 (💹 市場與交易教學書)，"
        f"以及能不能派去裏世界 (至少 {ura_min:g})、派去有多強 (🌀 裏世界探索教學書)",
        "",
        "### 🖼️ 結果畫面",
        "- 單抽顯示角色、階級與稱號、完整度品相；十連一次列出 10 張，觸發保底的那張標「🎯 保底」",
        f"- 畫面上寫著保底進度 (`幾抽 / {g.PITY_THRESHOLD}`)、**下一抽 {ur} 的機率**和本池累計抽數；"
        f"這次有觸發保底會多一行「🎯 觸發保底！必定獲得 {ur}！」",
        f"- 「🌸 繼續單抽 ({one:,})」「⛩️ 繼續十連 ({ten:,})」用同一個卡池再抽，「🎒 查看卡庫」打開卡冊",
        "- 「📊 機率表」：這個卡池每個階級的機率、有哪些角色、" + ur + " 怎麼升高，還有**你自己的保底進度**"
        " (只有按的人看得到，誰都可以按)",
        "",
        "### 📜 祈願紀錄",
        f"`/card history` 看總祈願次數、融合次數，還有每個卡池的累計抽數、保底進度條、下一抽 {ur} 的機率"
        f"和上次抽到 {ur} 的時間；下面的「📊 選一個卡池查看機率表」可以直接看機率表 (只列現在抽得到的卡池)。",
    ]
    return "\n".join(lines)


def _album() -> str:
    g = _gacha()
    gcomp = _gacha_components()
    ura = importlib.import_module("Database.ura.rules")
    sorts = " ➔ ".join(name for _, name in g.INVENTORY_SORTS)
    first_sort = g.INVENTORY_SORTS[0][1]
    lines = [
        "抽到的卡都收在**卡冊**裡，打 `/card inventory` 打開。",
        "",
        "### 🗂️ 疊卡列表",
        f"- 同一位角色、同一個階級的卡會**疊成一疊**，顯示張數和這疊最高的完整度，一頁 {gcomp.STACKS_PER_PAGE} 疊",
        "- 最上面有持有總量、各階級張數，以及每個卡池收集了幾位角色",
        "- 疊的名字旁邊有 ⚗️ = 這疊可以合成、🔮 = 這疊可以融合",
        "- 「🎰 選擇卡池篩選...」「🔍 選擇稀有度篩選...」只看某個卡池、某個階級",
        f"- 「🔃 排序：{first_sort}」每按一次換一種：{sorts}",
        "- 「🎴 選擇一疊卡牌查看內容...」點進一疊",
        "-# 角色後來不在任何卡池時，卡池篩選會多一個「📦 其他 (已不在卡池)」",
        "",
        "### 🎴 一疊裡的卡",
        f"- 依完整度由高到低列出這疊的每一張，寫著品相、卡牌 ID 和取得時間，一頁 {gcomp.STACK_CARDS_PER_PAGE} 張",
        "- 「🎴 選擇卡牌檢視詳細鑑定...」看某一張的詳情，「🔙 返回卡冊」回列表",
        "- 這疊能合成或融合時，下面多一排捷徑「⚗️ 合成這一疊」「🔮 融合 ➔ SR」(箭頭後面是升上去的階級)，直接跳到合成 / 融合畫面",
        "",
        "### 🔍 單卡詳情",
        "- 最上面是角色、階級、這張卡的稱號和完整度品相，下面分成幾段：",
        "  - 📜 **角色資料**：角色稱號、種族、能力和一段簡介",
        f"  - ⚔️ **這張卡的實力**：照這張卡的階級和完整度算出的 HP / ATK / DEF 和職業 (跟派去🌀 裏世界時一樣)，"
        f"以及能不能出征 (完整度至少 {ura.MIN_COMPLETENESS:g})",
        "  - ✨ **這張卡的特殊能力**：只寫這張卡階級的那一檔 (I / II / III)：效果、消耗 B 點、冷卻",
        "  - 💹 **價值**：現在分解能拿多少賽錢 (市值 × 完整度倍率)",
        "  - 🗂️ **卡牌資訊**：卡牌 ID、取得時間、狀態 (🔒 收藏中 / 🌀 出征中 / ⚗️ 還有幾張能一起合成 / 🔮 能不能融合)",
        "- 按鈕：「🔙 返回這一疊」「🎒 返回卡冊」「🔒 放進收藏冊」「📖 角色圖鑑」(另開一則只有你看得到的角色頁)",
        "-# 收藏冊裡的卡點進去也是同一個畫面",
        "",
        "### 🔒 收藏冊",
        "- 在單卡詳情按「🔒 放進收藏冊」，這張卡就搬進收藏冊；放進、取出都不用錢，也沒有張數上限",
        "- 收藏冊裡的卡**不會被拿去合成、融合、分解或上架市場**，那些畫面的選單裡根本不會出現，不怕手滑",
        "- 也**不能派去裏世界出征**：挑隊伍時會標 🚫 和「🔒 在收藏冊」，要派就先取出來",
        "- 收進去的卡不會出現在卡冊，卡冊上的張數和階級統計不算它；但卡冊上的**收集進度**會連收藏冊一起算"
        " (跟 `/character` 圖鑑的「已擁有」、稱號一樣)，放進收藏冊不會讓進度變少",
        f"- 打 `/card album` 看收藏冊 (一頁 {gcomp.ALBUM_PER_PAGE} 張)，從「🎴 選擇一張卡查看或取出...」點一張，"
        "按「📤 取出 (回到卡冊)」就回到卡冊，「🔙 返回收藏冊」回列表",
        "-# 正在裏世界出征的卡暫時不會出現在卡冊，也不能放進收藏冊，回來之後就恢復；"
        f"不過成功撤離時倒下的卡，或那一局失敗 / 放棄時派出的每一張卡，完整度都會被扣 {ura.COMP_PENALTY:g} (詳見🌀 裏世界探索教學書)",
        "",
        "### 💕 收藏冊與稱號、名片",
        "收藏冊裡放齊一位角色**每個階級各一張完美卡 (1.0000)**，就會解鎖她的推角稱號，第一次解鎖還會永久拿到她的名片。"
        "稱號要那些卡**一直放在收藏冊**才有，取出來稱號就會消失 (名片會留著)；詳細看🪪 資料卡與簽到教學書。",
    ]
    return "\n".join(lines)


def _craft() -> str:
    g = _gacha()
    caps = []
    prev_floor = None
    for floor, cap in g.SYNTHESIS_CAPS:
        if prev_floor is not None and prev_floor <= COMP_MIN:   # 完整度最低就是 COMP_MIN，比它低的那一行用不到
            break
        cond = f"{floor:g} 以上" if floor > 0 else f"不到 {prev_floor:g}"
        caps.append(f"{cond} ➔ 最多 +{cap:g}")
        prev_floor = floor
    chances = "、".join(f"{r} {p * 100:g}%" for r, p in g.SYNTHESIS_DOUBLE_CHANCE.items())
    ex_r = "R" if "R" in g.SYNTHESIS_DOUBLE_CHANCE else next(iter(g.SYNTHESIS_DOUBLE_CHANCE))
    ex1 = g.calc_synthesis(0.3, 0.25, ex_r)
    ex2 = g.calc_synthesis(0.5, 0.05, ex_r)
    n = g.FUSION_COUNT
    lines = [
        "想讓卡更好，就靠**合成**把完整度拉高，再用**融合**升到更高的階級。",
        "",
        "### ⚗️ 合成：兩張變一張",
        "- 條件：**同一位角色、同一個階級**的兩張卡，而且兩張都還不到 1.0000",
        "- 打 `/card synthesis`，先選代數 (卡池) 再選角色，都只列出有卡可以合成的；"
        "接著選第一張、再選第二張 (只列出能配對的)，選錯可以按「🔙 重選第一張」",
        "- 也可以在卡冊點進一疊，按「⚗️ 合成這一疊」",
        "- 合完的結果畫面有「⚗️ 繼續合成」，直接回到同一位角色的選卡畫面接著合 (這位角色已經沒得合時會反灰)",
        "",
        "### ⚡ 自動合成全部",
        "- 選卡畫面最下面的「⚡ 自動合成全部」：把**這位角色**的卡一次合完，每個階級各自合",
        "- 每次拿**完整度最低的兩張**合 (一樣低先拿比較早取得的)，新卡放回去繼續比，合到只剩一張未滿 1.0000 為止；"
        "合到 1.0000 的卡就不再參加",
        "- 每一次都照樣有機會加倍，也都算進合成次數 (合成稱號)",
        "- 會先出確認畫面列出每個階級「幾張 ➔ 最多合成幾次」，按「⚡ 確認自動合成」才做；結果畫面每個階級一行，"
        "寫合成幾次、加倍幾次、剩下那張的完整度",
        "- ⚠️ 用掉的卡會消失、合完不能還原；想留的卡先放進收藏冊 (收藏冊、出征中的卡不會被合)",
        "",
        "### 📈 完整度加多少",
        "- 新卡 = **較高那張的完整度 + 增幅**，一定比兩張都高，最多到 1.0000",
        "- **兩張越接近越划算**：一模一樣時拿滿額增幅，差越多增幅越少",
        "- 增幅上限看**較低那張**是幾位數：" + "、".join(caps),
        "- 有機會**加倍** (增幅 ×2)。兩張一樣時的加倍機率看階級：" + chances + "；差越多機率也越低",
        f"-# 例如兩張 {ex_r} 卡 0.3000 + 0.2500 ➔ {ex1['normal_completeness']:.4f}，"
        f"加倍的話 {ex1['doubled_completeness']:.4f} (機率 {ex1['double_chance'] * 100:.2f}%)；"
        f"0.5000 + 0.0500 只會變成 {ex2['normal_completeness']:.4f}",
        "",
        "### ✅ 先看結果再決定",
        "- 確認畫面會先列出要用掉的兩張卡、**一般結果**、**✨ 加倍結果**和**🎲 加倍機率**",
        "- 按「⚗️ 確認合成」才真的合成 (這時才決定有沒有加倍)，按「✖️ 取消」卡牌不會有任何變動",
        "",
        "### 🔮 融合：完美卡升一階",
        f"- 條件：**同一位角色、同一個階級**、完整度都是 **1.0000** 的卡 **{n} 張**",
        "- 融合後變成這位角色的**下一個階級**，稱號也換成新階級的；已經是她**最高的階級**就不能再融合",
        "- 新卡的完整度**重新隨機** (跟祈願一樣)，通常又會變低，要再合成上去",
        f"- 打 `/card fusion` 依序選代數、角色、階級 (只列出湊得到 {n} 張的)，或在卡冊點進那一疊按「🔮 融合 ➔ SR」這類按鈕；"
        f"要用哪 {n} 張系統會自動挑",
        "- 確認畫面列出要用掉的卡、新階級和新稱號，按「🔮 確認融合」才融合，「✖️ 取消」不會有變動",
        "",
        "### ⚠️ 注意",
        "- 合成、融合用掉的卡會**消失**，換成一張新卡 (卡牌 ID 也是新的)",
        "- 收藏冊裡的卡、正在裏世界出征的卡都不能拿來合成或融合",
        f"-# 💡 小技巧：同角色同階級的卡先兩兩合成、把完整度拉到 1.0000，湊滿 {n} 張再融合",
    ]
    return "\n".join(lines)


def _dex() -> str:
    g = _gacha()
    cats = importlib.import_module("Utils.character_data").load_categories()
    total = sum(len(c["characters"]) for c in cats.values())
    cat_names = "、".join(c["category_name"] for c in cats.values())
    pools = "；".join(f"{p['name']} = {p['desc']}" for p in g.GACHA_POOLS.values())
    lines = [
        "`/character` 是東方角色的圖鑑，看得到每位角色的資料、卡牌階級和卡面，還有你收集了哪些。",
        "",
        "### 🔎 怎麼找角色",
        f"- 先從「請選擇作品/角色分類...」選一個分類，目前有 {len(cats)} 個：{cat_names}，共 {total} 位角色",
        "- 分類頁列出這個分類的每位角色、階級範圍和稱號，✅ = 你已經有她的卡",
        "- 再從「請選擇角色...」點一位角色；看完可以用同一個選單換角色，或用「切換到其他作品/分類...」換分類",
        "- 首頁和分類頁會寫你已經收集了幾位角色",
        "",
        "### 👤 角色頁上有什麼",
        "- 角色的稱號、名字、所屬分類和簡介",
        "- 種族、能力，以及 ❤️ HP、⚔️ ATK、🛡️ DEF **基礎數值**：派去裏世界出征時，角色的數值就從這裡算起，"
        "再乘上那張卡的階級和完整度",
        "- **🏷️ 卡牌階級**：這位角色的每個階級、各階級的專屬稱號，以及你**有幾張** (✅ ×張數 / ▫️ 未擁有)；"
        "有做卡面的角色，每個階級旁邊會放那個階級的卡面",
        "- **✨ 特殊能力 (SP)**：依階級分成 I / II / III，寫著類型、消耗 B 點、冷卻和說明",
        "",
        "### 🎰 跟卡池的關係",
        f"- {pools}",
        "- 角色頁的卡牌階級下面寫「🎴 可在 `/card gacha` 祈願中獲得」就抽得到，寫「🚫 目前不在卡池中」就是現在抽不到",
        "- 想抽某位角色，先在這裡看她在哪個分類，就知道要選哪個卡池",
        "-# 圖鑑的「已擁有」連收藏冊、出征中的卡一起算；上架到市場還沒賣掉的卡不算",
    ]
    return "\n".join(lines)


BOOK = {
    "intro": "向博麗神社祈願抽東方角色卡，整理卡冊、收藏喜歡的卡，再用合成與融合把卡練到完美、升上更高的階級。",
    "chapters": [
        {"title": "🙏 祈願、機率與保底", "short": "卡池、價格、階級機率、完整度與每個卡池各自的保底",
         "body": _pull, "commands": ["card gacha", "card history"]},
        {"title": "📒 卡冊與收藏冊", "short": "疊卡、篩選排序、單卡詳情；把重要的卡收進收藏冊保護起來",
         "body": _album, "commands": ["card inventory", "card album"]},
        {"title": "⚗️ 合成與融合", "short": "兩張合成拉高完整度，湊滿完美卡再融合升一階",
         "body": _craft, "commands": ["card synthesis", "card fusion"]},
        {"title": "📖 角色圖鑑", "short": "找角色、看階級與卡面、自己收集了哪些、角色在哪個卡池",
         "body": _dex, "commands": ["character"]},
    ],
}

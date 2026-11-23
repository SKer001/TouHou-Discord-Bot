"""
📚 🌀 裏世界探索・教學書 (0.36.000)
格式見 Components/guide_components.py；數字從裏世界的引擎與資料檔讀 (Database/ura/rules.py、data/*.json、
Database/Ura_DB_Manager.py、活動檔 Events/*.json 的 "ura" 區塊)，開畫面時才算
"""
import importlib


# =========================================================
# 🔢 小工具 (模組在函式裡才取，reload 後拿得到新版)
# =========================================================
def _rules():
    return importlib.import_module("Database.ura.rules")


def _data():
    return importlib.import_module("Database.ura.data")


def _uc():
    return importlib.import_module("Cogs.load-ura.Components.ura_components")


def _pct(v: float) -> str:
    return f"{round(float(v) * 100, 1):g}%"


def _num(v: float) -> str:
    return f"{round(float(v), 2):g}"


def _rng(pair) -> str:
    lo, hi = pair
    return f"{lo:,}" if lo == hi else f"{lo:,}～{hi:,}"


def _zone_len() -> int:
    """一區幾關 (第 1～10 關 = 第 1 區)；來源：rules.zone_of"""
    r = _rules()
    return next(f for f in range(1, 1000) if r.zone_of(f + 1) > r.zone_of(1))


def _theme_names() -> str:
    return "、".join(f"{z['emoji']} {z['name']}" for z in _data().zones() if not z.get("borrowed"))


def _item(iid: str) -> str:
    it = _data().items().get(iid, {})
    return f"{it.get('emoji', '')} {it.get('name', iid)}".strip()


# =========================================================
# 1. 🌀 一局怎麼玩
# =========================================================
def _flow() -> str:
    r = _rules()
    n = _zone_len()
    idle = importlib.import_module("Cogs.load-ura.ura").VIEW_TIMEOUT // 60
    kill = r.EXP_KILL
    lines = [
        f"裏世界是**搜打撤**的冒險：派 1～{r.MAX_PARTY} 位角色深入裏世界，一關一關往下走、打怪撿寶物，最後**平安撤離**才算數。",
        "",
        "### 🗺️ 一局的流程",
        "- 打 `/ura explore` 選隊伍、整裝，按「🚀 出發！」",
        "- 每一關有幾扇門，選一扇走進去：戰鬥、寶箱、事件…… (第 3 章)",
        f"- 每 {n} 關是一區，第 {n} 關是 👹 **BOSS**",
        "- 打倒 BOSS 後二選一：「🏁 撤離 (帶東西回去)」，或「➡️ 繼續前進」到下一區 (敵人更強、寶物更好)",
        "- 每進一關都會扣 🧭 **常識度**，扣到 0 就失敗 (第 3 章)",
        "- 同一時間只能有一局；進度會一直存著，隨時回來接著打",
        "-# 💡 第一次玩：先以打倒第 1 區的 BOSS、平安撤離為目標",
        "",
        "### 🏁 成功撤離",
        "- 撤離的方法：打倒區域 BOSS 後按「🏁 撤離 (帶東西回去)」，或在**選門時**用 🔙 歸還符"
        " (會先跳一次確認，寫清楚會帶回什麼，按「🔙 確定撤離」才用掉)",
        "- 帶回：口袋的賽錢、背包裡的道具 / 素材 / 寶物 (法具帶不回來，見第 6 章)",
        f"- 經驗值全拿；只有**倒下**的隊友完整度 −{_num(r.COMP_PENALTY)}",
        "",
        "### 💀 失敗 / 🏳️ 放棄",
        "- 全隊倒下、常識度歸零 = 失敗；也可以自己放棄",
        "- 口袋的賽錢 (連帶進去的) 和背包裡的東西 (連帶進去的道具) **全部沒了**",
        f"- 經驗值只拿 {_pct(r.FAIL_EXP_RATIO)}",
        f"- 派出的**每一張卡完整度 −{_num(r.COMP_PENALTY)}** (一局每張最多扣一次)",
        "-# 💡 撤離前用 🔥 不死鳥的羽毛把倒下的隊友救回來，結算時就不算倒下",
        "",
        "### 📈 經驗值",
        "-# 加在你自己的經驗值上 (累積起來讓資料卡的 P 點上升)，一局結束時一起結算",
        f"- 每走一關 +{r.EXP_FLOOR}；打倒一隻一般怪 +{kill['normal']}、精英 +{kill['elite']}、寶箱怪 +{kill['mimic']}、"
        f"BOSS +{kill['boss']} (活動 BOSS +{kill['fest_boss']})",
        f"- 越深越多：第 N 區 × (1 + (N − 1) / 10)，例如第 5 區 ×{_num(r.exp_mult(5))}",   # 來源：rules.exp_mult
        "- 結算會公開發在頻道 (資料卡設成私人就不發)；成功撤離的紀錄會上 `/leaderboard` 的"
        "「💰 裏世界・帶出最多錢」(算淨賺 = 帶出 − 帶進) 和「🕳️ 裏世界・最深入」",
        "",
        "### 🔄 接回與放棄",
        f"- 探索畫面只有自己看得到；閒置 {idle} 分鐘會先收起來，機器人重開後舊畫面也會失效 —— **進度都還在**，打 `/ura resume` 就能接回",
        "- 已經有一局在跑時打 `/ura explore`，也會直接接回那一局",
        "- 開了新畫面，舊的那則會變成「↪️ 這個畫面已經移到新的訊息了」",
        "- 不想玩了：`/ura abandon` 或畫面上的「🏳️ 放棄」，會先問一次，按「🏳️ 確定放棄」才算",
    ]
    return "\n".join(lines)


# =========================================================
# 2. 🧍 組隊與整裝
# =========================================================
def _party() -> str:
    r, d = _rules(), _data()
    bag_uses = importlib.import_module("Database.Ura_DB_Manager").BAG_USES
    cat = d.category_max()
    slots = [b["slots"] for b in d.bags().values()]
    lines = [
        "### 🧍 選隊伍",
        "- 打 `/ura explore`，在「🎰 卡池」選代數 ➔「🧍 選角色：…」挑角色 ➔「🎴 派哪一張卡？」選要派哪一張",
        f"- 按「➕ 加入隊伍」放進隊伍、「➖ 移出隊伍」拿掉；至少 1 位、最多 {r.MAX_PARTY} 位",
        "- 選好按「➡️ 下一步：整裝」",
        "- 選角色時畫面會寫那位的**職業**和**符卡** (B 點、冷卻)，見第 5 章",
        "",
        "### 🚫 哪些卡不能派",
        "- **同一位角色只能派一張**",
        f"- 完整度不到 **{_num(r.MIN_COMPLETENESS)}** 的卡",
        "- 放在**收藏冊**裡的卡、已經在出征中的卡",
        f"-# 不能派的卡在選單裡會標 🚫 和原因；目前有 {len(d.characters())} 位角色能出征",
        "",
        "### 🌀 出征中的卡",
        "- 出發後，派出的卡暫時不會出現在卡冊裡，**不能合成、融合、分解、上架市場，也不能放進收藏冊**",
        "- 這一局結束 (撤離、失敗或放棄) 就回到卡冊",
        "",
        "### 🎒 整裝：帶道具",
        "- 道具要先用 `/ura shop` 買進**裏世界倉庫** (成功撤離帶回來的也在那裡)，出發時才挑要帶哪些",
        "- 在「🧪 選一個道具…」選好，按「➕ 1」「➕ 5」多帶、「➖ 1」少帶、「🧹 全部不帶」清空",
        f"- 背包基本 {r.BAG_SLOTS} 格；有些道具一局最多帶幾個，回血類、回常識度類各自合計最多 "
        f"{max(cat.values())} 個 (第 7 章)",
        "- **帶進去的道具也算在背包裡**：失敗或放棄就跟著沒了",
        "- 「💾 儲存這組」把現在這組存起來，下次按「⚡ 快速整裝」一鍵帶齊",
        "- 倉庫不夠的話，會列出還缺什麼、照 `/ura shop` 原價共多少賽錢，按「🛒 補買缺的」才扣錢，買的放進倉庫並直接帶上；"
        "賽錢不夠時按鈕反灰、寫還差多少",
        "-# 只買這次的背包放得下、沒超過上限的量 (例如存那組時有帶額外背包、這次沒帶，多的就不買，會寫出有幾個沒買)；只補道具，額外背包和賽錢不補",
        "",
        "### 🎒 額外背包",
        f"- 在「🎒 額外背包」選一個帶上，這一局的背包多 +{min(slots)}～+{max(slots)} 格 (看種類)",
        f"- 每個額外背包能用 {bag_uses} 次，每出發一次就用掉 1 次 (不管成功失敗)，用完就壞掉",
        "",
        "### 💰 帶賽錢 (口袋)",
        "- 按「💰 帶賽錢」輸入金額，從你的賽錢移進這一局的**口袋**",
        "- 口袋的錢用來跟局內的流浪商人買東西，有些事件也要用 (例如天狗的賭局)",
        "- 局內撿到的賽錢也會放進口袋；**成功撤離才帶得回來**，失敗連帶進去的都沒了",
        "-# 不帶錢也可以出發，撿到的錢一樣會進口袋",
        "",
        "都準備好就按「🚀 出發！」；想換隊伍按「↩️ 上一步」。",
    ]
    return "\n".join(lines)


# =========================================================
# 3. 🚪 選門與常識度
# =========================================================
def _doors() -> str:
    r, d = _rules(), _data()
    n = _zone_len()
    elite_cap = r.ROOM_CAPS["elite"]
    battle_floors = "、".join(str(f) for f in r.BATTLE_FLOORS)
    lo, hi = r.DOOR_COUNT
    per = [r.sanity_per_floor(z, False) for z in (1, 2, 3)]
    sanity_items = "、".join(f"{_item(i)} +{it['effect']['value']:,}" for i, it in d.items().items()
                             if it.get("cat") == "sanity" and it["effect"].get("do") == "sanity")
    lines = [
        "每一關都要**選一扇門**走進去，門上看得到是哪一種房間 (🕳️ 陷阱除外，見下面)。",
        "",
        "### 🚪 門的種類",
        "- ⚔️ **戰鬥**：1～3 隻一般怪 (門上寫 ×幾隻)",   # 來源：run._battle_door (weighted_count(1, 3))
        f"- 💀 **精英**：強敵 + 0～2 隻小弟，掉的東西比較好；每區最多出現 {elite_cap} 次 (📯 挑戰號角不受這個限制)",   # 來源：run._elite_door (weighted_count(0, 2))
        f"- 💰 **寶箱**：選「🔓 打開寶箱」或「🚪 不開了，往前走」；{_pct(r.LOCKED_CHANCE)} 上了鎖 "
        f"(要 🗝️ 寶箱鑰匙，按「🗝️ 用鑰匙打開」)，{_pct(r.MIMIC_CHANCE)} 是**寶箱怪** (一打開就開打，強度跟精英一樣)",
        "- ❓ **事件**：🟢 好事件、🔴 壞事件一進門就生效；✨ 特殊事件自己決定要不要做，不想就按「❌ 不要」",
        f"- 🕳️ **陷阱**：一半機率弄丟一個道具，不然全隊 −{_pct(r.TRAP_HP_PCT)} HP (最低留 1；背包沒道具就一定扣血)。"   # 來源：run._trap (rng.random() < 0.5)
        f"隊上有斥候、或用了 {_item('ward_amulet')} 就沒事",
        "- ⚠️ **陷阱門會偽裝成 💰 寶箱**：看不穿的時候門上寫「💰 寶箱」，走進去才發現是假寶箱 (斥候、提燈、望遠鏡看得穿，見下面)",   # 來源：run.door_view
        f"-# 同一關可以有兩扇以上的真寶箱 (每區最多 {r.ROOM_CAPS['chest']} 個)，陷阱一關最多一扇：看到兩扇 💰 可能都是真的，也可能一真一假",   # 來源：rules.REPEAT_ROOMS
        "- 🛒 **流浪商人**：用口袋的錢買道具，偶爾賣法具 (第 8 章)",
        "- 👹 **BOSS**：這一區的頭目，**不能逃**",
        f"- 🔍 **隱藏寶箱**：隊上有斥候 (或 🏮 提燈效果中) 時，第 1～{n - 2} 關有 {_pct(r.HIDDEN_CHEST_CHANCE)} 機率多出一扇寶箱門",   # 來源：run.gen_doors (fz < 9)
        "",
        f"### 🗺️ 一區 {n} 關",
        f"- 第 {battle_floors} 關是戰鬥關：固定兩扇門，一扇 ⚔️ 戰鬥、一扇 💀 精英 (這一區的精英門出現滿 {elite_cap} 次後改成戰鬥)",
        f"- 第 {n - 1} 關固定是流浪商人、第 {n} 關固定是 BOSS；其他關 {lo}～{hi} 扇門隨機",   # 來源：run.gen_doors (fz == 9 / 10)
        f"- 每一區會隨機抽一個主題 ({_theme_names()})，不會跟前 3 區重複，決定會遇到的敵人、BOSS、素材和寶物",   # 來源：run.zone_theme (themes[-3:])
        "- **難度只看是第幾區**：越深敵人越強、寶物越好",
        f"-# 第 2 區起的區域 BOSS 數值更高，但招式重新照固定順序開放 (第 2～{r.DEEP_BOSS_UNLOCK_ZONES} 區只有 1 招，"
        f"之後每深 {r.DEEP_BOSS_UNLOCK_ZONES} 區多 1 招)、招式數值 × {_num(r.DEEP_BOSS_SKILL_SCALE)}、"
        f"每 {r.DEEP_BOSS_SKILL_EVERY} 回合才放一次、本身沒有閃避；詳見 `/ura bestiary` 的 BOSS 頁",
        "",
        "### 🔍 看清楚門後面",
        "- 平常只看得到房間種類 (陷阱看起來是寶箱)；隊上有活著的 🔍 **斥候** (或用了 🏮 提燈) 就看得到敵人名字、"
        "寶箱有沒有上鎖 / 是不是寶箱怪、事件是好是壞、哪一扇其實是 🕳️ 陷阱，還能躲過陷阱",
        "-# 💡 看得到是寶箱怪時，不想打就按「🚪 不開了，往前走」",
        f"- {_item('telescope')}：看穿這一關的門 (陷阱也現形)；{_item('map_piece')}：多看下下一關 (沒有斥候時陷阱一樣寫成寶箱)；"
        f"{_item('reroll_dice')}：重抽這一關的門",
        "",
        "### 🧭 常識度",
        f"- 出發時 {r.SANITY_START:,}，這也是上限 (補超過的浪費掉)",
        f"- 每進一關扣：第 1 區 {per[0]}、第 2 區 {per[1]}、第 3 區 {per[2]}…… (每深一區多扣 {per[1] - per[0]})",
        f"- 隊上有活著的 🧭 **嚮導**：每關少扣 {_pct(r.GUIDE_DISCOUNT)}，逃跑也少扣",
        "- 逃跑會多扣 (第 4 章)，壞事件、有些敵人的招式也會扣",
        "- **歸 0 = 全隊迷失在裏世界，這局失敗**",
        f"- 補回來：{sanity_items}，有些符卡也能回",
        "-# 畫面上的常識度條：剩 30% 以下變橘色、10% 以下變紅色",   # 來源：ura_components.sanity_bar
    ]
    return "\n".join(lines)


# =========================================================
# 4. ⚔️ 戰鬥
# =========================================================
def _battle() -> str:
    r = _rules()
    fm = r.FLEE_MULT
    pc = lambda kind: _pct(r.persuade_chance(10, kind))
    stackable = "、".join(f"{s.get('emoji', '')} {s.get('name', sid)}" for sid, s in _data().statuses().items()
                          if s.get("max_stacks", 1) > 1)
    lines = [
        "### 🔁 一回合怎麼進行",
        "- **每回合我方只有一位隊友能行動**：先在「🙋 誰行動？」選人，再按「⚔️ 普攻」或「✨ 符卡」",
        "- 接著是敵方回合，每隻敵人各動一次 (普攻或招式)，然後進下一回合",
        "- 要選目標時 (敵人 2 隻以上、回血要選隊友…)，會再出一個「🎯 …：選目標」的選單讓你挑",
        "-# 時間停止的符卡、某些御札可以讓這回合多動幾次，我方欄下面會寫「這回合還能行動 N 次」",
        "",
        "### ⚔️ 普攻與 ✨ 符卡",
        "- 普攻：ATK × 1，不花 B 點",
        "- 符卡：花 ✨ **B 點**、放完要冷卻；B 點不夠或冷卻中，按鈕會反灰 (第 5 章)",
        f"- B 點：出發時 {r.B_START}、最多 {r.B_MAX}；每回合 +2 (我方、敵方回合各 +1)、"   # 來源：combat.enemy_phase (add_b 1 + 1)
        f"每進一關 +{r.B_STEP}、打倒一隻敵人 +{r.B_KILL}",
        "- 冷卻每回合 −1，進下一關也 −1",
        "",
        "### 🎒 道具與 📜 御札 (不算行動)",
        "- 「🎒 道具」：戰鬥中用回血、糰子、炸彈、冰封符…，**不會用掉這回合的行動**",
        f"- 🍡 糰子：讓一般怪 / 精英心滿意足地離開 (戰利品照拿)；對 BOSS 則是讓牠露出 💢 破綻 (這場受到的傷害變多)。"
        f"越深成功率越低 (第 10 關：一般怪 {pc('normal')}、精英 {pc('elite')}、BOSS {pc('boss')})，每隻每場只能試一次，沒成功也會用掉",
        "- 「📜 御札」：裝了御札類法具的隊友才能用，**一回合限一次**，也不算行動 (第 6 章)",
        "-# 💡 道具和御札要在**普攻 / 符卡之前**用 (行動一用完就輪到敵人)；御札要先在「🙋 誰行動？」選裝著它的那位，按鈕才會亮",
        "",
        "### 🏃 逃跑",
        f"- 「🏃 逃跑」一定成功，但要扣常識度：一般戰鬥 = 這區每關扣量 × {_num(fm['normal'])}、"
        f"精英 × {_num(fm['elite'])}、寶箱怪 × {_num(fm['mimic'])} (按鈕上會寫扣多少)",
        "- 背包有 💨 煙霧彈就自動用掉，不扣常識度",
        "- **BOSS 戰不能逃**",
        "-# 逃跑前已經打倒的敵人，戰利品照拿",
        "",
        "### 👹 敵人怎麼打你",
        f"- 敵人比較常打血多的隊友，🛡️ 守護者被選中的比重 × {r.GUARD_WEIGHT}；有人 📣 嘲諷時，單體攻擊全部打那一位",
        f"- BOSS 戰以外，拖過 {r.ENRAGE_AFTER} 回合敵人會 😡 狂暴 (每回合 ATK +{_pct(r.ENRAGE_STEP)})",
        f"- BOSS 照固定順序放招式，其他回合普攻：區域 BOSS 第 1 區每 2 回合一招、第 2 區起每 {r.DEEP_BOSS_SKILL_EVERY} 回合一招；"
        "🎪 活動 BOSS 不管第幾區都是每 2 回合",   # 來源：combat._pick_skill (skill_every 預設 2)、combat.start (只有區域 BOSS 設 skill_every)
        f"- BOSS 血剩一半進入 🔥 第二階段 (ATK +{_pct(r.BOSS_PHASE2_ATK)})，有些招式要第二階段才會用",   # 來源：combat.deal (max_hp / 2)
        "- 全隊倒下 = 這局失敗；**HP 不會自己回**，打完記得補",
        f"-# 背包有 {_item('substitute_doll')} 時，隊友 HP 歸 0 會自動留 1 (用掉一個)",
        "",
        "### ✨ 狀態效果",
        "- 名字旁邊的 emoji 是狀態，括號 = 剩幾回合 / 幾關 / 幾次；同一個狀態大多不會疊，再中一次只會刷新回合數"
        + (f" ({stackable}這類會疊層，寫成 ×層數)" if stackable else ""),
        "- 只在戰鬥中有效的狀態，打完就消失",
        "- 燒傷、死蝶這類持續扣血，最多扣到剩 1 HP，不會直接打死",
        "- 對 BOSS：封印無效；凍住 / 睡著的回合減半 (無條件捨去，所以 1 回合的對 BOSS 沒用)，而且越控越難成功",   # 來源：status.apply (boss_half)
        "- 每個狀態的效果看「📖 狀態表」或 `/ura status`",
        "",
        "### 🔍 查看詳情",
        "- 用「🔍 查看角色 / 敵人的詳情…」選一位，會另外跳出一則只有你看得到的訊息：數值、符卡、法具、狀態",
        "- 敵人的**招式和攻略提示**要打倒過一次 (登錄進怪物圖鑑) 才看得到",
    ]
    return "\n".join(lines)


# =========================================================
# 5. 🃏 職業與符卡
# =========================================================
def _classes() -> str:
    r, d = _rules(), _data()
    chars = d.characters()
    count = {}
    for c in chars.values():
        count[c["class"]] = count.get(c["class"], 0) + 1

    def cls(key: str) -> str:
        return f"{r.CLASS_NAMES[key]} ({count.get(key, 0)} 位)"

    mult = "、".join(f"{k} ×{_num(v)}" for k, v in r.RARITY_MULT.items())
    lo, hi = r.DAMAGE_VARIANCE
    example = next(iter(chars.values()), None)
    outside = "、".join(chars[cid]["name"] for cid, sp in d.spells().items()
                        if not cid.startswith("_") and sp.get("outside") and cid in chars)
    lines = [
        "### 📊 數值",
        "- 每位角色有 ❤️ HP、⚔️ ATK、🛡️ DEF 三項基礎數值",
        "- 實際數值 = 基礎 × **階級倍率** × **完整度倍率**",
        f"  - 階級：{mult}",
        f"  - 完整度：{_num(r.MIN_COMPLETENESS)} = ×{_num(r.comp_mult(r.MIN_COMPLETENESS))}、"
        f"1.0 = ×{_num(r.comp_mult(1.0))}，中間照比例",
        f"- DEF 越高受到的傷害越少，最多減 {_pct(r.dmg_reduction(10 ** 6))}；每一下傷害有 ±{_pct(hi - 1)} 的浮動",
        "",
        "### 🎭 五種職業",
        f"- {cls('atk')}：ATK 高，普攻或單體招打得破敵人的 ⚖️ 審判",
        f"- {cls('guard')}：血厚，敵人選目標時比重 × {r.GUARD_WEIGHT}，大多打守護者；身上有 📣 嘲諷時，單體攻擊全部打這位",
        f"- {cls('sup')}：放任何符卡都會順便**淨化**全隊能清掉的壞狀態",
        f"- {cls('scout')}：看穿門後面、躲過陷阱、{_pct(r.HIDDEN_CHEST_CHANCE)} 找到隱藏寶箱，在場時所有敵人的閃避減半",   # 來源：combat.deal (dodge /= 2)
        f"- {cls('guide')}：每關少扣 {_pct(r.GUIDE_DISCOUNT)} 常識度，逃跑和敵人扣常識度的招式也少扣",
        "-# 職業效果都要那位隊友**還活著**才有",
        "",
        "### ✨ 符卡",
        "- 每位角色一招符卡，花 B 點、放完進入冷卻 (第 4 章)",
        "- **符卡分三檔**：看這張卡是那位角色的第幾個階級，**檔次越高數字越大**",
    ]
    if example and len(example["rarities"]) >= 3:
        rs = example["rarities"]
        lines.append(f"  - 例如{example['name']}的卡有 {' / '.join(rs)}，{rs[0]} 是第 1 檔、{rs[-1]} 是第 3 檔")
    lines += [
        "- 完整度超過 0.8：冷卻 × 0.9 (無條件捨去，最少 1 回合)",   # 來源：rules.spell_cooldown
        "- 符卡有打單體、打全體、回血、上狀態、時間停止……每位都不一樣",
    ]
    if outside:
        lines.append(f"- {outside}的符卡在選門時也能放 (按鈕「✨ {outside}的符卡」)")
    lines += [
        "",
        "### 🔍 去哪裡看每位角色",
        "- 出發選角色時：職業、符卡說明、B 點和冷卻",
        "- 探索中「🔍 查看角色 / 敵人的詳情…」：這張卡的實際數值、職業特性、這一檔的符卡數字",
        "- `/character` 角色頁：基礎數值和每個階級的「✨ 特殊能力 (SP)」(B 點、冷卻)",
    ]
    return "\n".join(lines)


# =========================================================
# 6. 🔮 法具
# =========================================================
TYPE_NAMES = {"shiki": "式神", "ofuda": "御札", "blessing": "加護"}   # 來源：data/relics.json 的 type
TYPE_TEXT = {
    "shiki": "裝上後每回合自動幫忙 (攻擊、回血、回 B 點)",
    "ofuda": "戰鬥中按「📜 御札」主動用，有次數 (剩幾次寫在名字後面)，一回合限一次、不算行動",
    "blessing": "裝上就一直有效 (ATK、減傷、最大 HP、B 點…)",
}


def _relics() -> str:
    r, d = _rules(), _data()
    by_type = {}
    for rel in d.base_relics().values():
        by_type.setdefault(rel["type"], []).append(f"{rel['emoji']} {rel['name']}")
    fox = d.events().get("fox_trade", {}).get("effect", {}).get("items")
    (t1, p1, c1), (t2, p2, c2) = r.MERCHANT_RELIC[:2]
    lines = [
        "法具是**只在這一局有效**的裝備，每位隊友可以裝 1 個；撤離後**不會帶回來**，下一局要重新找。",
        "",
        "### 🦊 三種法具",
    ]
    for t, names in by_type.items():
        lines.append(f"- **{TYPE_NAMES.get(t, t)}** ({'、'.join(names)})：{TYPE_TEXT.get(t, '')}")
    lines += [
        "- 等級只有 **SSR / UR / LR**，效果照等級分三檔，越高越強",
        "- 每種法具都有對應的職業：**職業對上**的隊友裝，效果再加強 (數字變大或次數變多)",
        "",
        "### 📦 怎麼拿到",
        f"- 💀 精英：{_pct(r.REWARDS['elite']['relic_chance'])} 掉一個",
        "- 👹 區域 BOSS：一定掉一個，而且挑隊上活著的隊友職業對得上的",
        f"- 💰 寶箱：{_pct(r.CHESTS['normal']['relic_chance'])}；上鎖寶箱 {_pct(r.CHESTS['locked']['relic_chance'])}；"
        f"寶箱怪 {_rng(r.MIMIC_RELICS)} 個",
    ]
    if fox:
        lines.append(f"- ✨ 狐狸的交易 (事件)：交 {fox} 個道具換一個")
    lines += [
        f"- 🛒 流浪商人：{_pct(r.MERCHANT_RELIC_CHANCE)} 會擺一個 ({t1} {c1:,} / {t2} {c2:,} 賽錢)",
        "-# 流浪商人不賣 LR；掉落的法具越深的區越容易是高等級",
        "",
        "### 🎒 裝備、換掉、卸下",
        "- 撿到的法具先放進背包 (一個佔 1 格)",
        "- 打開「🎒 背包」➔ 在「🎒 看哪一類…」切到「🦊 法具」➔ 在「🦊 把法具裝給誰…」選要裝的法具 ➔ "
        "再從「🎯 🦊 裝備法具：選目標」選隊友 (只派一位時直接裝上)",
        "- 那位已經裝了法具的話，舊的會換下來放回背包",
        "- 「🔓 卸下法具 (放回背包)…」：把裝著的拿下來 (背包要有空位)",
        "- **裝在身上的不佔背包格子**；不要的可以用「🗑️ 丟掉法具…」",
        "- 戰鬥中不能裝、不能卸，要在選門或房間裡整理",
        "-# 每件法具的詳細數字：「🔍 查看」裝著它的隊友；背包選單裡也有一句說明",
    ]
    return "\n".join(lines)


# =========================================================
# 7. 🎒 背包與戰利品
# =========================================================
def _bag() -> str:
    r, d = _rules(), _data()
    slots = [b["slots"] for b in d.bags().values()]
    items = d.items()
    max_stack = max(it.get("stack", 1) for it in items.values())
    stacked = "、".join([_item(i) for i, it in items.items() if it.get("stack", 1) == max_stack][:2])
    cat = d.category_max()
    rw, ch = r.REWARDS, r.CHESTS
    floor_of = {"monster": "一般怪 / 精英", "chest": "寶箱", "locked": "上鎖寶箱", "boss": "BOSS / 寶箱怪"}
    rarity_floor = "、".join(f"{floor_of[t]} {next(iter(b))} 起跳" for t, b in r.TREASURE_BASE.items() if t in floor_of)
    battle_only = "、".join(_item(i) for i, it in items.items() if it.get("use") == "battle")
    guaranteed = "、".join(f"{n} 個 {k}" for k, n in r.GUARANTEED_PER_100.items())
    lines = [
        "### 🔲 背包格數",
        f"- 基本 {r.BAG_SLOTS} 格，帶額外背包再加 +{min(slots)}～+{max(slots)} 格 (出發時選)",
        "- 畫面最上面隨時寫著「🎒 背包 已用 / 總共」",
        "",
        "### 📦 一格放多少",
        f"- 🧪 道具：看種類，一格 1～{max_stack} 個 (例如 {stacked} 一格 {max_stack} 個)",
        f"- 🧺 素材：一格 {r.MATERIAL_STACK} 個",
        "- 💎 寶物：一個 1 格 (不會疊)",
        "- 🦊 法具：在背包裡一個 1 格，裝在隊友身上不佔格",
        f"- 有些道具一局最多拿幾個，回血類、回常識度類各合計最多 {max(cat.values())} 個 —— **撿東西也算**，到上限就撿不起來",
        "",
        "### 📥 放不下的東西",
        "- 背包滿了，撿到的東西會先放到「📦 待撿」",
        "- 丟掉一些東西騰出空位，再用「📦 撿起放不下的東西…」撿回來",
        "- 待撿清單和選單都會寫每樣東西的功用 (道具的效果、法具這一檔的數字、寶物賣多少錢)，先看再決定要不要騰位置",
        "- **離開這一關，待撿的就沒了**",
        "",
        "### 🗑️ 整理背包",
        "- 「🎒 背包」打開後，用「🎒 看哪一類…」切換 🧪 道具 / 🧺 素材 / 💎 寶物 / 🦊 法具",
        "- 「🧪 使用道具…」：選門時、房間裡也能用回血、回常識度的道具；選門類的道具只有選門時能用"
        + (f"，{battle_only}只有戰鬥中能用" if battle_only else ""),
        "- 丟東西：道具、寶物一次丟 1 個；**素材是那一種全部丟掉**",
        "- 戰鬥中打開背包只能用道具，不能丟",
        "",
        "### 💰 戰利品",
        "每打倒 (或用糰子勸走) 一隻敵人都有獎勵：",
        f"- 一般怪：賽錢 {_rng(rw['normal']['money'])}、素材 {_rng(rw['normal']['materials'])}、"
        f"{_pct(rw['normal']['treasure_chance'])} 寶物",
        f"- 精英：賽錢 {_rng(rw['elite']['money'])}、道具 {_rng(rw['elite']['items'])}、"
        f"{_pct(rw['elite']['relic_chance'])} 法具、{_pct(rw['elite']['treasure_chance'])} 寶物",
        f"- BOSS：賽錢 {_rng(rw['boss']['money'])}、素材 {_rng(rw['boss']['materials'])}、道具 {_rng(rw['boss']['items'])}、"
        f"法具 {_rng(rw['boss']['relics'])}、寶物 {_rng(rw['boss']['treasures'])}",
        f"- 寶箱：賽錢 {_rng(ch['normal']['money'])} × 第幾區 (上鎖 {_rng(ch['locked']['money'])} × 區)、"
        f"素材、道具、寶物 {_rng(ch['normal']['treasures'])} (上鎖 {_rng(ch['locked']['treasures'])})",
        f"- 寶箱怪：賽錢 {r.mimic_money(1):,} 起、道具 {_rng(r.MIMIC_ITEMS)}、法具 {_rng(r.MIMIC_RELICS)}、寶物 {_rng(r.MIMIC_TREASURES)}",
        "-# 範圍裡數量越多越難出；賽錢直接進口袋",
        f"- 寶物越深越容易出高階：{rarity_floor}",
        f"-# 每 100 關固定藏著 {guaranteed} 寶物，放在某幾關的寶箱裡 (那一關一定有一扇寶箱門)",   # 來源：run._guaranteed ((floor - 1) // 100)
        "- 素材是這一區主題的料理素材，帶回去可以在神社做料理",
        "",
        "### 🏁 哪些要成功撤離才算",
        "- 口袋的賽錢、道具、素材、寶物：**撤離才帶得回來**，失敗全部沒了",
        "- 法具：不管怎樣都帶不回來",
        "- 怪物圖鑑的登錄：打倒當下就算，失敗也照算",
        "-# 帶回來的道具、寶物放進 `/ura inventory`；素材放進神社倉庫",
    ]
    return "\n".join(lines)


# =========================================================
# 8. 🛒 裏世界商店
# =========================================================
def _shop() -> str:
    r, d, uc = _rules(), _data(), _uc()
    items = d.items()
    bags = d.bags()
    bag_uses = importlib.import_module("Database.Ura_DB_Manager").BAG_USES
    lines = [
        "打 `/ura shop` 打開商店，用你的賽錢買東西。",
        "",
        "### 🛍️ 怎麼買",
        "- 「🗂️ 分類」切換種類 ➔「🛍️ 選要買的東西…」選一樣 ➔ 按「🛒 買 1 個」「🛒 買 5 個」「🛒 買 10 個」",
        "- 額外背包一次只能「🛒 買 1 個」",
        "- 買的東西放進**裏世界倉庫** (`/ura inventory`)，出發整裝時再挑要帶哪些",
        "-# 商品清單上有每樣的說明和「一局最多 N」(沒有上限的寫「不限」)",
        "",
        "### 📋 賣什麼",
    ]
    for group, name in uc.SHOP_GROUPS.items():
        if group == "bags":
            continue
        goods = [f"{items[i]['emoji']} {items[i]['name']} {items[i]['price']:,}" for i in uc.shop_items(group)]
        if goods:
            lines.append(f"- **{name}**：" + "、".join(goods))
    if bags:
        bl = sorted(bags.values(), key=lambda b: b["slots"])
        lines.append(f"- **{uc.SHOP_GROUPS.get('bags', '🎒 額外背包')}**：+{bl[0]['slots']} 格 {bl[0]['price']:,} ～ "
                     f"+{bl[-1]['slots']} 格 {bl[-1]['price']:,}，每個用 {bag_uses} 次")
    no_sell = "、".join(_item(i) for i, it in items.items() if it.get("price") and it.get("merchant") is False)
    lines += [
        "",
        "### 💡 新手小技巧",
        "- 回血、回常識度的各帶幾個，避免半路撐不住",
        f"- {_item('chest_key')}：上鎖的寶箱東西比較好",
        f"- {_item('dango')}：打不過的敵人可以試著勸走，獎勵照拿",
        f"- {_item('smoke_bomb')}：逃跑不扣常識度",
        f"- {_item('return_talisman')}：選門時直接成功撤離，保住整局的收穫 (一局最多帶 {items['return_talisman'].get('max', 1)} 個；"
        "用之前會先問一次)",
        "",
        f"### 🛒 局內的流浪商人",
        f"- 每區第 {_zone_len() - 1} 關固定出現，用**口袋的錢**買，價格 = 商店 × {_num(r.MERCHANT_MARKUP)}，"   # 來源：run.gen_doors (fz == 9)
        f"每樣只有 {_rng(r.MERCHANT_QTY)} 個",
        f"- 每次隨機擺 {r.MERCHANT_KINDS} 種道具，{_pct(r.MERCHANT_RELIC_CHANCE)} 多擺一個法具",
        f"- 不賣：{no_sell}、額外背包",
        "- 商人畫面每樣東西下面都寫著功用 (跟 `/ura shop` 的說明一樣，法具寫這一檔的數字)",
        "- 從「🛒 買一個…」選，買的東西直接放進這一局的背包",
    ]
    return "\n".join(lines)


# =========================================================
# 9. 📦 倉庫與寶物
# =========================================================
def _storage() -> str:
    r, d = _rules(), _data()
    prices = d.treasure_prices()
    per_page = importlib.import_module("Cogs.load-ura.ura").STORAGE_PER_PAGE
    price_text = "、".join(f"{k} {prices[k]:,}" for k in r.RARITIES if k in prices)
    lines = [
        "打 `/ura inventory` 打開裏世界倉庫，用「📦 看哪一頁」切換三頁。",
        "",
        "### 💎 寶物",
        f"- 成功撤離帶回來的寶物都在這裡，照階級高到低排，一頁 {per_page} 種",
        f"- 寶物分 {' / '.join(r.RARITIES)} 六個階級，賣價固定 (一個)：{price_text} 賽錢",
        "- 「⭐ 篩選階級」「🗺️ 篩選區域」：只看某個階級、某個主題 (或 🎪 活動寶物)",
        "- 「🔍 看說明 (這一頁的寶物)」：選一個看它的說明",
        "- 「💰 篩選出來的全部賣掉」：把**目前篩選出來的寶物全部**賣掉，會先問一次，按「💰 確定全部賣掉」才賣，按「↩️ 取消」就不賣",
        "- ⚠️ 沒有篩選就是**所有寶物**一起賣；賣掉就拿不回來，想留一些的話先篩選出要賣的那一批",
        "-# 頁首會寫目前篩選出來共幾個、全部賣掉可以拿多少",
        "- 寶物的用處：賣給系統換賽錢；🎪 活動寶物成功撤離帶出來時，還會算進活動任務 (第 11 章)",
        "-# 💡 高階寶物大多從深區、上鎖寶箱和 BOSS 來 (第 7 章)",
        "",
        "### 🧪 道具",
        "- 在 `/ura shop` 買的、成功撤離帶回來的道具都在這裡",
        "- 出發整裝時從這裡挑要帶哪些 (第 2 章)",
        "",
        "### 🎒 額外背包",
        "- 買的額外背包，和每個**還能用幾次**；用完就壞掉消失",
    ]
    return "\n".join(lines)


# =========================================================
# 10. 📖 怪物圖鑑
# =========================================================
def _active_ids(ctx: dict | None) -> set:
    """開書時進行中的活動 id (guide_components.current_context)；0.37.005 起不拿某個活動當固定例子"""
    return {ev.get("id") for ev in (ctx or {}).get("active") or []}


def _bestiary(ctx: dict | None = None) -> str:
    r = _rules()
    bestiary = importlib.import_module("Database.ura.bestiary")
    td = importlib.import_module("Database.title_data")
    titles = td.TITLES
    group = td.TITLE_GROUPS.get("ura", {}).get("name", "🌀 裏世界")
    secs = bestiary.sections()
    zones = [s for s in secs if s["kind"] == "zone"]
    prog = bestiary.progress({})
    base_total = prog["base"][1]
    rw = r.BESTIARY_REWARDS
    zone_list = "、".join(f"{s['emoji']} {s['name']} {len(s['enemies'])} 隻" for s in zones)

    def title(tid: str) -> str:
        t = titles.get(tid)
        return f"[{t['rarity']}]「{t['name']}」" if t else ""

    zone_title = ""
    if zones:
        zt = title(f"ura_dex_{zones[0]['id']}")
        zone_title = f" (例：{zones[0]['name']} {zt})" if zt else ""
    fests = [s for s in secs if s["kind"] == "fest" and s["id"] in _active_ids(ctx)]   # 只拿進行中的活動舉例
    fest_title = title(f"ura_dex_{fests[0]['id']}") if fests else ""
    fest_title = f"再拿那個活動的稱號 (現在的{fests[0]['name']}是 {fest_title})" if fest_title else "再拿那個活動的稱號"
    lines = [
        "打 `/ura bestiary` 打開怪物圖鑑，記錄你在裏世界遇過的敵人。",
        "",
        "### 📖 怎麼登錄",
        "- **打倒或用糰子勸走一次**就登錄，打倒當下就算 —— 那一局後來失敗或放棄也照算",
        "- 寶箱怪算在那一區的精英裡",
        "- 還沒登錄的只會顯示「❓ ？？？」",
        "",
        "### 🗺️ 分區",
        f"- 每個主題一區：{zone_list} (一般怪、精英、BOSS)",
        "- 有裏世界內容的活動另外一區 (🎪)：活動怪只在活動期間出現，登錄過的活動結束後照樣保留",
        "- 「🗺️ 看哪一區」切換區域、「📖 看哪一隻」看一隻的圖鑑頁；「◀️」「▶️」翻上一隻 / 下一隻，「↩️ 回清單」回到清單",
        "",
        "### 🔍 圖鑑頁看得到什麼",
        "- 介紹、第 1 區時的 HP / ATK / DEF (越深的區越強)、閃避",
        "- **招式**：每一招的效果和使用條件 (冷卻、血量低於多少才用…)",
        "- BOSS 第 2 區起的規則和開招順序",
        "- 💡 攻略提示、打倒過幾次",
        "-# 探索中「🔍 查看」敵人時，也要登錄過才看得到招式和攻略",
        "",
        "### 🎁 全收獎勵與稱號",
        f"- 每區全收：{rw['zone'][0]:,} 賽錢 + {rw['zone'][1]:,} 經驗，再拿那一區的稱號{zone_title}",
        f"- 一般主題 {base_total} 隻全收：{rw['all'][0]:,} 賽錢 + {rw['all'][1]:,} 經驗，稱號 {title('ura_dex_all')}",
        f"- 活動怪全收：{rw['fest'][0]:,} 賽錢 + {rw['fest'][1]:,} 經驗，{fest_title}",
        "- 賽錢和經驗要在那一區的清單按「🎁 領取：…」才會發，每個只能領一次",
        f"- 稱號全收就解鎖、永久保留：在 `/profile` 按「🏷️ 修改稱號」，到分組「{group}」換上",
    ]
    return "\n".join(lines)


# =========================================================
# 11. 🎪 活動關卡
# =========================================================
def _fest(ctx: dict | None = None) -> str:
    r, d = _rules(), _data()
    live = _active_ids(ctx)
    fl = {k: v for k, v in d.fests().items() if k in live}   # 只列進行中的活動 (不拿某個活動當固定例子)
    boss_hp, fest_hp = r.BOSS_MULT[0], r.FEST_BOSS_MULT[0]
    slot = "、".join(f"{n} 個 {_pct(w / 100)}" for n, w in r.FEST_TREASURE_SLOT)
    boss_slot = "～".join(str(n) for n, _ in r.FEST_BOSS_TREASURE_SLOT)
    lines = [
        "有裏世界內容的活動進行中，選門時偶爾會看到標 🎪 的**活動門**。",
        "",
        "### 🚪 活動門",
        f"- 每一關有 {_pct(r.FEST_STAGE_CHANCE)} 機率，其中一扇門變成 🎪 活動門 (每區最多 {r.FEST_ZONE_CAP} 扇)",
        f"- 房間種類不變 (戰鬥、精英、寶箱、事件)；陷阱、第 {_zone_len() - 1} 關的商人、第 {_zone_len()} 關的 BOSS 不會變",
        "- 門上一定看得到是哪個活動、有什麼環境效果",
        "- 🎪 戰鬥 / 精英：敵人換成活動敵人；🎪 寶箱裡的寶箱怪也是活動精英",
        "- 🎪 事件：活動專屬的事件",
        "- 活動一結束就不會再出現活動門 (進行中的那一局照樣打得完)",
        "",
        "### 🌫️ 環境",
        "- 🎪 房間裡的戰鬥會套用活動的環境效果 (例如每回合扣血、錢變多)，只在那一場有效",
        "",
        "### 👹 活動 BOSS",
        f"- 🎪 精英門有 {_pct(r.FEST_BOSS_CHANCE)} 換成**活動 BOSS** (一局最多打到一次)",
        f"- 當成 BOSS 戰：不能逃、血剩一半進第二階段；HP 是同區一般怪的 {_num(fest_hp)} 倍 (區域 BOSS 是 {_num(boss_hp)} 倍)",
        "- 打倒後**不會**跳出撤離 / 繼續，直接往下一關",
        f"- 一定掉 1 個活動法具 + {boss_slot} 個活動寶物 (另外有賽錢、素材、道具)",
        "",
        "### 💎 活動寶物、🦊 活動法具",
        f"- 🎪 房間裡本來就會掉寶物時，再多擲一格**活動寶物** ({slot})，只有 SSR / UR / LR",
        f"- 🎪 房間掉的法具有 {_pct(r.FEST_RELIC_CHANCE)} 換成活動法具",
        "- **活動寶物在活動結束後也會保留**，可以賣；要成功撤離帶出來，「帶出活動寶物」這類活動任務才算",
        "- 活動法具跟一般法具一樣，只在那一局有效",
    ]
    if fl:
        ens = d.enemies()
        lines.append("")
        for f in fl.values():
            env = f.get("environment") or {}
            parts = []
            if env:
                parts.append(f"環境 {env.get('emoji', '')} {env.get('name', '')}（{env.get('desc', '')}）")
            normals = "、".join(ens[e]["name"] for e in f.get("normals", []) if e in ens)
            if normals:
                parts.append(f"活動敵人 {normals}")
            if f.get("elite") in ens:
                parts.append(f"精英 {ens[f['elite']]['name']}")
            if f.get("boss") in ens:
                parts.append(f"活動 BOSS {ens[f['boss']]['name']}")
            rels = "、".join(v.get("name", k) for k, v in (f.get("relics") or {}).items())
            if rels:
                parts.append(f"活動法具 {rels}")
            n_t = sum(len(v) for v in (f.get("treasures") or {}).values())
            if n_t:
                parts.append(f"活動寶物 {n_t} 種")
            lines.append(f"-# 🟢 現在 {f.get('emoji', '')} {f.get('name', '')}：" + "；".join(parts))
    elif ctx is not None:
        lines += ["", "-# 現在沒有裏世界內容的活動在進行，活動門暫時不會出現"]
    lines.append("-# 現在有什麼活動看 `/event info`，活動任務看 `/event quest`，詳細看 🎪 活動的教學書")
    return "\n".join(lines)


BOOK = {
    "intro": "派角色深入裏世界，一關一關選門、戰鬥、撿寶物；打倒 BOSS 後平安撤離，東西才帶得回來。",
    "chapters": [
        {"title": "🌀 一局怎麼玩", "short": "出發 ➔ 一關選一扇門 ➔ 打倒 BOSS 後撤離或繼續；成功撤離才帶得回東西，失敗會扣完整度",
         "body": _flow, "commands": ["ura resume", "ura abandon"]},
        {"title": "🧍 組隊與整裝", "short": "派 1～3 位角色、哪些卡不能派、出征中的卡、帶道具和賽錢、額外背包",
         "body": _party, "commands": ["ura explore"]},
        {"title": "🚪 選門與常識度", "short": "門的種類、每區 10 關與 BOSS、隨機主題，以及每進一關都會扣的常識度",
         "body": _doors, "commands": []},
        {"title": "⚔️ 戰鬥", "short": "每回合選一位隊友行動：普攻、符卡、道具、御札、逃跑，還有狀態效果和查看詳情",
         "body": _battle, "commands": ["ura status"]},
        {"title": "🃏 職業與符卡", "short": "數值怎麼算、五種職業的特性、符卡的 B 點、冷卻和三個檔次",
         "body": _classes, "commands": []},
        {"title": "🔮 法具", "short": "式神、御札、加護：怎麼拿到、裝給誰、換掉或卸下；只在這一局有效",
         "body": _relics, "commands": []},
        {"title": "🎒 背包與戰利品", "short": "背包格數、一格疊幾個、放不下的待撿、丟東西，戰利品哪些要撤離才算",
         "body": _bag, "commands": []},
        {"title": "🛒 裏世界商店", "short": "用賽錢買探索道具和額外背包，放進倉庫、出發時再挑；局內還有流浪商人",
         "body": _shop, "commands": ["ura shop"]},
        {"title": "📦 倉庫與寶物", "short": "寶物、道具、額外背包三頁；寶物分階級、篩選後一鍵賣掉換賽錢",
         "body": _storage, "commands": ["ura inventory"]},
        {"title": "📖 怪物圖鑑", "short": "打倒或勸走過的敵人會登錄：看數值、招式和攻略，全收領賽錢、經驗和稱號",
         "body": _bestiary, "commands": ["ura bestiary"]},
        {"title": "🎪 活動關卡", "short": "活動期間的 🎪 門：環境效果、活動敵人與 BOSS、活動寶物和法具",
         "body": _fest, "commands": []},
    ],
}

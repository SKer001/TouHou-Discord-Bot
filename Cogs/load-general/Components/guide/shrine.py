"""
📚 ⛩️ 神社經營・教學書 (0.36.000)
格式見 Components/guide_components.py；數字從程式常數讀，開畫面時才算：
- 神社 / 招待：Database/Economy_DB_Manager.py 開頭的常數
- 採集 / 料理 / 雜貨店 / 客人：Database/shrine_data.py + Database/events.game_rules([]) (沒有活動時的基本規則)
- 體力：Database/User_DB_Manager.py (STAMINA_*)；倉庫：Cogs/load-general/shrine.py、Components/general_components.py
活動會改數值 (modifiers、活動商品、活動料理…)，書裡寫的是基本值，並註明活動期間可能不同
"""
import importlib


def _m(name: str):
    return importlib.import_module(name)


def _econ():
    return _m("Database.Economy_DB_Manager")


def _data():
    return _m("Database.shrine_data")


def _rules() -> dict:
    """沒有活動時的基本規則 (教學書不連資料庫，看不到現在有沒有活動)"""
    return _m("Database.events").game_rules([])


def _items() -> dict:
    """道具 id ➔ {name, emoji, effect} (預設道具 + 遊戲資料定義的素材 / 料理)"""
    idb = _m("Database.Item_DB_Manager")
    out = {}
    for iid, name, emoji, _cat, _desc, effect in [*idb.DEFAULT_ITEMS, *idb.managed_items()]:
        out[iid] = {"name": name, "emoji": emoji, "effect": effect or {}}
    return out


def _label(items: dict, iid: str) -> str:
    info = items.get(iid) or {}
    return f"{info.get('emoji', '')} {info.get('name', iid)}".strip()


def _hours(td) -> str:
    return f"{td.total_seconds() / 3600:g}"


def _pct_list(chances: list, unit: str) -> str:
    return "、".join(f"{i} {unit}時 {p:.0%}" for i, p in enumerate(chances))


# =========================================================
# 第 1 章 ⛩️ 賽錢箱、清掃與妖怪
# =========================================================
def _shrine() -> str:
    e = _econ()
    comp = _m("Cogs.load-general.Components.shrine_components")
    income, box_max = e.SHRINE_INCOME_PER_HOUR, e.SHRINE_BOX_MAX
    full_hours = box_max / income
    min_eff = max(0.0, 1 - e.DIRT_PENALTY * e.DIRT_MAX - e.YOUKAI_PENALTY * e.YOUKAI_MAX)
    lo, hi = e.YOUKAI_REWARD
    view_minutes = 10   # 來源：Cogs/load-general/shrine.py ShrineView timeout=600
    lines = [
        "每位玩家都有一間自己的神社，打 `/shrine manage` 打開（只有自己看得到）。"
        "神社不用一直開著：每次打開或按按鈕時，才把這段時間發生的事一次算完。",
        "",
        "### 💰 賽錢箱",
        f"- 神社每小時自動進帳 **{income:,} 賽錢 × 神社效率**，存在賽錢箱裡",
        f"- 賽錢箱最多裝 **{box_max:,}**，**滿了就不會再累積**，要記得回收",
        "- 按「💰 回收」（括號裡是箱子裡現在的錢），或直接打 `/shrine collect`，錢就會進到你身上",
        "- 畫面上會顯示每小時進帳多少、什麼時候裝滿",
        f"-# 效率 100% 時從空到滿大約 {full_hours:g} 小時，一天回收一次就不太會浪費",
        "",
        "### ⚙️ 神社效率",
        f"- 效率 = 100% − 髒亂 − 妖怪，**最低 {min_eff:.0%}**",
        f"- 清潔度每髒一階 **−{e.DIRT_PENALTY:.0%}**，每隻妖怪 **−{e.YOUKAI_PENALTY:.0%}**",
        "- 效率只影響賽錢箱的進帳，不影響招待客人的報酬",
        "",
        "### 🧹 清潔度",
        f"- 共 {len(comp.DIRT_NAMES)} 個階段：" + " ➔ ".join(comp.DIRT_NAMES),
        f"- 從上次清掃開始，**每 {_hours(e.DIRT_INTERVAL)} 小時髒一階**，最多髒到第 {e.DIRT_MAX} 階",
        "- 按「🧹 清掃」馬上回到一塵不染；清掃**沒有獎勵、也沒有冷卻**，想掃就掃（已經一塵不染時按鈕會反灰）",
        "",
        "### 👹 妖怪",
        f"- 每小時判定一次會不會多一隻妖怪來作亂，已經在的越多越不容易再來：{_pct_list(e.YOUKAI_SPAWN, '隻')}",
        f"- 最多 **{e.YOUKAI_MAX} 隻**",
        f"- 按「⚔️ 治退妖怪」（括號裡是現在有幾隻）一次打退一隻，拿 **{lo:,}～{hi:,} 賽錢**（隨機）",
        "- 但妖怪會留下**晦氣**：每打退一隻，清潔度就掉一階（已經最髒就不再加）",
        "-# 💡 小技巧：先把妖怪全部治退，最後再清掃，晦氣會一起掃掉",
        "",
        "### 🙏 參拜客",
        "神社畫面下半部會列出來參拜的妖怪：心情、點了什麼菜、每份能拿多少賽錢。"
        "按「🍵 招待」（括號裡是客人數）端菜給牠們，詳見「🍵 招待參拜客」那章。",
        "",
        "### ⏳ 其他",
        "- 畫面最下面寫著「下一次妖怪 / 參拜客判定」的時間，按「🔄」重新整理",
        f"- 太久沒來的話，只會補算**最近 {e.SHRINE_MAX_CATCHUP.days} 天**（那時賽錢箱早就滿了）",
        "- 下排的「🗺️ 採集」「🍳 料理」「🏪 雜貨店」通往其他玩法，後面幾章會講",
        f"- 神社畫面放著超過 {view_minutes} 分鐘，按鈕就會失效，再打一次指令就好",
        f"-# 🔔 賽錢箱滿了、妖怪滿 {e.YOUKAI_MAX} 隻時，機器人可以私訊提醒你（在 `/notify` 開關）",
        # 來源：Economy_DB_Manager.modifier (shrine_income / youkai_spawn / youkai_reward)；神社畫面只有每小時進帳會跟著變
        "-# 活動期間神社收入、妖怪出現機率、治退的賽錢可能會調整：每小時進帳以神社畫面為準，其他看 `/event info`",
    ]
    return "\n".join(lines)


# =========================================================
# 第 2 章 🧺 採集與體力
# =========================================================
def _explore() -> str:
    e, data, rules = _econ(), _data(), _rules()
    udm = _m("Database.User_DB_Manager")
    idb = _m("Database.Item_DB_Manager")
    gather_times = _m("Cogs.load-general.shrine").GATHER_TIMES
    items = _items()
    cost = e.explore_cost(rules)
    lo, hi = data.EXPLORE_DROPS
    locs = rules["locations"]
    mats = {m for loc in locs.values() for m in loc["drops"]}
    per_hour = 3600 // udm.STAMINA_INTERVAL_SECONDS
    full_hours = udm.STAMINA_MAX * udm.STAMINA_INTERVAL_SECONDS / 3600
    onigiri, onigiri_n = idb.DAILY_REWARD_ITEM
    onigiri_hp = items.get(onigiri, {}).get("effect", {}).get("stamina", 0)
    dishes = sorted(rules["stamina_dishes"], key=lambda d: (-items.get(d, {}).get("effect", {}).get("stamina", 0), d))
    dish_text = "、".join(f"{_label(items, d)} +{items.get(d, {}).get('effect', {}).get('stamina', 0)}" for d in dishes)
    buttons = "、".join(f"「🧺 {n} 趟 (-{cost * n})」" for n in gather_times)
    lines = [
        "用 `/shrine explore`，或神社畫面的「🗺️ 採集」，到幻想鄉各地採集做料理用的**素材**。",
        "",
        "### ⚡ 體力",
        f"- 體力上限 **{udm.STAMINA_MAX}**，**每 {udm.STAMINA_INTERVAL_SECONDS // 60} 分鐘自然回復 1 點**"
        f"（一小時 {per_hour} 點，從 0 回滿要 {full_hours:g} 小時）",
        f"- 自然回復只會回到 {udm.STAMINA_MAX}；吃體力道具可以超過，但超過時就不會再自然回復",
        "- 採集畫面上會顯示現在的體力，和下一點什麼時候回來",
        "",
        "### 🗺️ 怎麼採集",
        "1. 在「選擇採集地點…」選一個地點",
        # 來源：Cogs/load-general/shrine.py _build_explore (1 次 / 連續 5 次)、Economy_DB_Manager.explore (至少 1 趟)
        f"2. 按「🗺️ 採集 1 次 (-{cost})」或「🗺️ 連續 5 次 (-{cost * 5})」",
        f"- 每趟花 **{cost} 體力**，帶回 **{lo}～{hi} 個**素材，從那個地點的素材裡隨機抽",
        "- 連續 5 次但體力不夠時，能跑幾趟就跑幾趟（至少要夠 1 趟）",
        f"- 平常有 **{len(locs)} 個地點、{len(mats)} 種素材**（不含活動）：" + "、".join(f"{v['emoji']} {v['name']}" for v in locs.values()),
        # 來源：shrine_components.build_explore_container (活動地點後面標「🎪 活動限定」)
        "- 活動期間還會多開標著「🎪 活動限定」的地點，採得到活動素材",
        "- 畫面下方會列出每個地點採得到哪些素材；人間之里的素材在雜貨店也買得到",
        "",
        "### 🍀 隨機事件",
        f"每趟有 **{data.SPECIAL_CHANCE:.0%}** 機率遇到事件，好事壞事各一半：",   # 來源：Economy_DB_Manager.roll_explore (good = random < 0.5)
        "- 🍀 好事：額外多拿幾個素材",
        "- 💥 壞事：被摸走幾個、只剩一半，運氣差的時候甚至空手而回",
        "",
        "### 🧺 快速採集",
        "在料理畫面選了一道素材不夠的菜，可以按「🧺 快速採集」自動去採缺的素材（入口見「🍳 料理」那章）：",
        "- 畫面會先算好**還差哪些素材、去哪裡最好採、大概要幾趟**",
        f"- 按{buttons}就總共採幾趟：每趟都先去最缺的地方，那邊夠了就換下一個",
        # 來源：Economy_DB_Manager.quick_explore (pots 預設 1，shrine.py 沒有另外傳)
        "- 目標是做 **1 鍋**：素材採齊就提早收工，不會多花體力；體力不夠就先停下來",
        "- 採集是隨機的，運氣不好可能要多跑幾趟",
        "",
        "### ⚡ 恢復體力",
        "採集畫面、快速採集畫面和 `/profile` 都有「⚡ 恢復體力」：",
        "- 跳出彈窗，選「要吃哪一個？」和「吃幾個？」",
        # 來源：User_DB_Manager.stamina_items_left (用 tw_day 換日 = 台灣時間 00:00)
        f"- **每天最多吃 {udm.STAMINA_ITEM_DAILY_LIMIT} 個體力道具，包含簽到送的 🍙**（台灣時間 00:00 重置）",
        f"- {_label(items, onigiri)}（+{onigiri_hp}）：每天簽到（`/daily`）送 {onigiri_n} 個",
        f"- 其他要在「🍳 料理」的「⚡ 體力料理」自己做：{dish_text}",
        # 來源：explore_cost (modifiers.explore_stamina)、events.game_rules special_chance (活動取最大)
        "-# 活動期間每趟的體力消耗可能不一樣（以採集畫面按鈕上寫的為準），遇到事件的機率也可能變高",
    ]
    return "\n".join(lines)


# =========================================================
# 第 3 章 🍳 料理
# =========================================================
def _cook() -> str:
    data, rules = _data(), _rules()
    comp = _m("Cogs.load-general.Components.shrine_components")
    cats = comp.COOK_CATEGORIES
    serve_dishes = [d for d in rules["recipes"] if d not in rules["stamina_dishes"]]
    per_type = {t: sum(1 for d in serve_dishes if rules["dish_types"].get(d) == t) for t in ("food", "drink", "dessert")}
    type_text = "、".join(f"{cats[t]} {n}" for t, n in per_type.items())
    lines = [
        "用 `/shrine cook`，或神社畫面的「🍳 料理」，把素材做成料理。",
        "",
        "### 🗂️ 選料理",
        "1. 在「🗂️ 選擇分類…」選分類：" + "、".join(cats.values()),
        "2. 在「選擇料理…」選要做的菜，選單上會寫「✅ 可做 N 鍋」或 ❌，還有需要哪些素材",
        "3. 畫面會列出配方：每樣素材夠不夠（✅ / ❌）、倉庫裡有幾份、素材夠做幾鍋",
        # 來源：Cogs/load-general/shrine.py _build_cook 的按鈕 (做 1 鍋 / 做 5 鍋 / 全部)
        "4. 按「🍳 做 1 鍋」「🍳 做 5 鍋」或「🍳 全部 (N)」（N = 現在的素材夠做幾鍋）",
        "",
        "### 🍱 兩種料理",
        f"- **招待料理**（平常有 {type_text}，共 {len(serve_dishes)} 道）：一鍋做 **{data.COOK_YIELD} 份**，用來招待參拜客",
        f"- **⚡ 體力料理**（平常有 {len(rules['stamina_dishes'])} 道）：一鍋只做 **{data.STAMINA_COOK_YIELD} 份**，"
        "**不能拿來招待**，只能在「⚡ 恢復體力」吃掉回體力",
        "- 活動期間還會多出 🎪 活動料理（詳見🎪 活動教學書）",
        "-# 客人點餐會在食物、茶水、點心裡各點最多一道，多備幾種不同的菜比較不會缺",
        "",
        "### 🧺 素材不夠時",
        "選的菜一鍋都做不出來時，按鈕下面會多一顆「🧺 快速採集」：",
        "- 自動去採還缺的素材，目標是做 1 鍋（怎麼採見「🧺 採集與體力」那章）",   # 來源：Economy_DB_Manager.quick_explore pots=1
        "- 缺的是人間之里的素材時，快速採集畫面上也能按「🏪 買齊人里素材」直接用賽錢買",
        "- 採齊之後按「🍳 回去料理」把菜做出來",
        "",
        "### 🍵 從招待畫面過來",
        "招待客人時發現缺菜，按招待畫面的「🍳 去做…」：",
        "- 料理畫面會**自動選好第一道缺的菜**，上面寫著「🍵 客人還在等：…」",
        "- 每做好一次，就會**自動換成下一道還缺的菜**（「➡️ 接著做 …」）",
        "- 客人點的菜都齊了，按「🍵 回去招待」端上桌",
        "-# 自動換菜只有從招待畫面跳過來時才有；自己打開料理畫面時，做完會停在原本選的那道",
    ]
    return "\n".join(lines)


# =========================================================
# 第 4 章 🍵 招待參拜客
# =========================================================
def _serve() -> str:
    e, data = _econ(), _data()
    title_min = _m("Database.title_data").GUEST_TITLE_MIN
    leaving = _m("Database.Notify_DB_Manager").GUEST_LEAVING_WINDOW
    every = e.GUEST_EVERY_HOURS
    stay_hours = (100 // e.MOOD_STEP) * e.MOOD_INTERVAL.total_seconds() / 3600
    lo, hi = e.ORDER_SIZE
    per = e.serving_reward(100)
    example_n = hi + 1   # 點最多道 + 額外招待 1 份
    example = e.serving_reward(100, example_n)
    example_fav = int(round(example * e.FAVORITE_BONUS))
    # 挑算出來是整數的心情 (70% 這種會因為小數變成 979，畫面跟實拿差 1)
    moods = "、".join(f"{m}% 一份 {e.serving_reward(m):,}" for m in (100, 80, 50))
    guests = "、".join(f"{g['emoji']} {g['name']}" for g in data.GUESTS.values())
    lines = [
        "參拜客是來神社的妖怪，端上牠點的料理就能拿到賽錢。客人會出現在 `/shrine manage` 的神社畫面上，按「🍵 招待」開始。",
        "",
        "### 🚶 客人怎麼來",
        f"- 每 **{every} 小時**判定一次，神社裡的客人越多越不容易再來：{_pct_list(e.GUEST_SPAWN, '位')}",
        f"- 最多同時 **{e.GUEST_MAX} 位**；一般客人有 {len(data.GUESTS)} 種：{guests}，活動期間還有限定客人",
        "- 只有一位客人時按「🍵 招待」直接進招待畫面；好幾位的話先在「選擇要招待的客人…」挑一位",
        "",
        "### 😊 心情",
        # 來源：Economy_DB_Manager.guest_mood (從 100 開始扣)
        f"- 客人來的時候心情 **100%**，之後**每 {_hours(e.MOOD_INTERVAL)} 小時 −{e.MOOD_STEP}%**",
        f"- 心情掉到 0% 就會生氣離開，所以一位客人最多待 **{stay_hours:g} 小時**",
        "- 神社畫面會顯示每位客人的心情、每份報酬、什麼時候心情變差；招待畫面會顯示什麼時候生氣離開",
        "- 心情不同，客人點餐時說的話也不一樣",
        "",
        "### 🧾 點餐",
        f"- 客人一來就決定好要點什麼：**{lo}～{hi} 道**，食物、茶水、點心每種最多一道",
        "- 活動期間客人也可能點 🎪 活動料理（詳見🎪 活動教學書）",   # 來源：Economy_DB_Manager.make_order (order_event_chance)
        # 來源：Economy_DB_Manager.serve_guest (點的每道扣 1 份、額外招待 1 份)
        "- 點的每道要 1 份，**一定要全部給齊**才能按「🍵 端上桌」；倉庫夠的打 ✅、不夠的打 ❌",
        "",
        "### 💰 報酬",
        f"- **每份報酬 = {per:,} × 心情²**：{moods}",
        "- 總報酬 = 端上桌的份數 × 每份報酬，招待畫面下方有預估報酬",
        f"- 例如心情 100% 時點了 {hi} 道、再額外招待 1 份 = {example_n} × {per:,} = **{example:,} 賽錢**",
        "- 端上活動料理時，每一份都會讓報酬再乘上活動加成（詳見🎪 活動教學書）",
        "-# 心情是平方算的，掉一點報酬就少很多：客人來了早點招待最划算",
        "",
        "### 🎁 額外招待",
        "- 用「🎁 要不要額外招待？（可以不選）」先選分類（食物 / 茶水 / 點心），再從下面的選單挑 **1 份**招待料理，多一份就多一份報酬",
        "- 只會列出端完點的菜之後，倉庫還有剩的料理；改選「➖ 不額外招待」就取消",
        f"- 額外招待的那份如果剛好是客人的**最愛**，整筆報酬再 **×{e.FAVORITE_BONUS:g}**（上面的例子就變成 {example_fav:,}）",
        "- 只有**額外招待**端上最愛才算；客人自己點到最愛的菜不會加成",
        "- 最愛不會直接告訴你：看招待畫面灰字的 💡 提示猜猜看",
        "-# 預估報酬不會先算最愛的加成，端上桌後的訊息寫「✨ 正中最愛」就是猜中了",
        "",
        "### 🍳 缺菜怎麼辦",
        "- 按「🍳 去做…」一鍵跳到料理畫面，自動選好缺的菜；做齊後按「🍵 回去招待」",
        "- 想先招待別位，按「👥 換客人」（有兩位以上客人時才有）",   # 來源：shrine.py _build_serve (len(guests) > 1)
        "",
        "### 👋 招待完",
        "- 客人吃飽就會心滿意足地離開，空出位子給下一位",
        # 來源：Database/title_data.py _guest_titles (sr = SR、ur = UR)
        f"- 🏷️ 每種客人各有兩個稱號：招待同一種客人 {title_min} 次（SR）、額外招待正中牠的最愛 {title_min} 次（UR）",
        f"-# 🔔 客人離開前 {_hours(leaving)} 小時內，機器人可以私訊提醒你（每位一次，在 `/notify` 開關）",
        # 來源：Economy_DB_Manager.modifier (guest_spawn / serve_reward)
        "-# 活動期間客人來訪的機率、招待報酬可能會調整，看 `/event info`",
    ]
    return "\n".join(lines)


# =========================================================
# 第 5 章 🏪 雜貨店
# =========================================================
def _shop() -> str:
    e, data, rules = _econ(), _data(), _rules()
    items = _items()
    prices = rules["shop"]
    # 只用雜貨店素材就做得出來的招待料理：一份的成本
    costs = [sum(prices[m] * k for m, k in r.items()) / data.COOK_YIELD
             for d, r in data.RECIPES.items() if all(m in prices for m in r)]
    per = e.serving_reward(100)
    lines = [
        "用 `/shrine shop`，或神社畫面的「🏪 雜貨店」，到人間之里的雜貨店用賽錢買素材。",
        "",
        "### 🛒 賣什麼",
        "只賣人間之里的基本食材：",
        *[f"- {_label(items, m)}　`{p:,}` 賽錢 / 個" for m, p in prices.items()],
        "其他素材（八目鰻、冰晶、茶葉…）雜貨店沒有，要自己去採集。",
        "",
        "### 🧾 怎麼買",
        "1. 在「選擇要買的素材…」選一樣",
        "2. 按「買 1 個」「買 5 個」或「買 10 個」，選好素材後按鈕上會顯示總價",   # 來源：Cogs/load-general/shrine.py _build_shop (1, 5, 10)
        "- 賽錢不夠的按鈕會反灰；買到的素材直接放進神社倉庫",
        "",
        "### 🤔 為什麼不能拿來賺錢？",
        "- 雜貨店**只賣不收**：素材和料理都不能賣回去換賽錢",
        f"- 料理變成賽錢的方法只有**招待客人**，而客人每 {e.GUEST_EVERY_HOURS} 小時才有機會來一位、最多 {e.GUEST_MAX} 位，"
        "買再多素材也只能招待這麼多人",
    ]
    if costs:
        lines.append(f"- 只用雜貨店素材就做得出來的料理，一份成本大約 {min(costs):,.0f}～{max(costs):,.0f} 賽錢；"
                     f"心情 100% 的客人一份報酬 {per:,}，心情越低賺得越少")
    lines += [
        "- 所以雜貨店是**缺一兩樣時救急用**的，平常的素材靠採集（只花體力）比較划算",
        "",
        "### 🏪 買齊人里素材",
        "在料理畫面按「🧺 快速採集」後，如果缺的素材裡有雜貨店賣的，會出現「🏪 買齊人里素材」（括號裡是總價）：",
        "- 一鍵把**做 1 鍋還缺的**人里素材照雜貨店的價格買齊，只買缺的數量",   # 來源：Economy_DB_Manager.shop_buy_missing pots=1
        "- 賽錢不夠的話按鈕會反灰",
        "-# 活動期間雜貨店可能會多賣活動商品，以店裡顯示的為準",
    ]
    return "\n".join(lines)


# =========================================================
# 第 6 章 🎒 神社倉庫
# =========================================================
def _storage() -> str:
    shrine_cog = _m("Cogs.load-general.shrine")
    gen = _m("Cogs.load-general.Components.general_components")
    serve_types = " / ".join(gen.SERVE_LABELS.values())
    first_serve = next(iter(gen.SERVE_LABELS.values()))
    names = {value: f"{emoji} {label}" for value, label, emoji, _desc in shrine_cog.CATEGORY_OPTIONS}
    consumable_label = names.get("consumable", "消耗品")
    cuisine_label = names.get("cuisine", "招待料理")
    # 遊戲資料裡還沒有道具的分類 (管理員另外加進 Item.db 的道具看不到，所以只寫「目前」)
    idb = _m("Database.Item_DB_Manager")
    used = {cat for _i, _n, _e, cat, _d, _fx in [*idb.DEFAULT_ITEMS, *idb.managed_items()]}
    empty = [names[v] for v, *_ in shrine_cog.CATEGORY_OPTIONS if v != "all" and v not in used]
    timeout_minutes = 2   # 來源：Cogs/load-general/shrine.py InventoryView timeout=120
    lines = [
        "用 `/shrine storage` 打開**神社倉庫**，也就是你的道具背包：採集來的素材、做好的料理、體力道具都放在這裡。"
        "料理、招待、吃體力道具都直接從倉庫扣。",
        # 來源：Database/ura/run.py settle (只有成功撤離才帶回 materials) ➔ Ura_DB_Manager._settle 加進同一個倉庫
        "-# 🌀 裏世界成功撤離時帶回來的料理素材也會放進這裡；裏世界的寶物和道具另外放在 `/ura inventory`（詳見🌀 裏世界探索教學書）",
        "",
        "### 🗂️ 分類",
        "用「🌸 選擇道具分類...」切換，選單上會寫每個分類有幾種道具：",
        *[f"- {emoji} {label}：{desc}" for _value, label, emoji, desc in shrine_cog.CATEGORY_OPTIONS],
        f"-# 🍙 飯糰和⚡ 體力料理在「{consumable_label}」，招待料理在「{cuisine_label}」"
        + ("；" + "、".join(f"「{n}」" for n in empty) + "目前還沒有道具" if empty else ""),
        "",
        "### 🏷️ 道具旁邊的標籤",
        "- 「⚡ 體力 +N」：吃了能回復多少體力",
        f"- 「🍽️ 招待用 · {first_serve}」：能招待客人的料理，後面是種類（{serve_types}）",
        "- 每樣道具下面還有一行小字說明",
        "-# 倉庫只能看；要吃體力道具，請按採集畫面或 `/profile` 的「⚡ 恢復體力」",
        "",
        "### 📄 翻頁",
        f"- 一頁 {gen.ITEMS_PER_PAGE} 種道具，標題下面會寫共幾種、合計幾件",
        "- 「◀️ 上一頁」「下一頁 ▶️」翻頁，頭尾相接（第一頁按上一頁會跳到最後一頁）",
        "- 按中間的頁碼會跳出「跳轉倉庫頁面」，輸入頁數直接跳過去",
        f"- 畫面 {timeout_minutes} 分鐘沒動作，選單和按鈕就會停用，再打一次指令就好",
        "",
        "### 👀 看別人的倉庫",
        "在 `target` 選一位成員就能看他的倉庫；對方把個人卡片設成私密的話就看不到。只有打指令的人能操作選單。",
        "",
        "### ⚠️ 活動道具",
        "活動素材和活動料理在**活動結束時會從所有人的倉庫清空**，記得在結束前做成料理、端給客人。",
    ]
    return "\n".join(lines)


BOOK = {
    "intro": "經營自己的神社：回收賽錢箱、清掃、治退妖怪，再採集素材做料理，招待來參拜的妖怪賺賽錢。",
    "chapters": [
        {"title": "⛩️ 賽錢箱、清掃與妖怪", "short": "賽錢箱每小時自動進帳；清掃、治退妖怪讓神社效率保持在高檔",
         "body": _shrine, "commands": ["shrine manage", "shrine collect"]},
        {"title": "🧺 採集與體力", "short": "花體力到幻想鄉各地採素材，快速採集自動補齊缺的素材，體力道具每天限吃幾個",
         "body": _explore, "commands": ["shrine explore"]},
        {"title": "🍳 料理", "short": "先選分類再選料理；招待料理和體力料理的差別，缺素材時一鍵去採",
         "body": _cook, "commands": ["shrine cook"]},
        {"title": "🍵 招待參拜客", "short": "客人怎麼來、心情怎麼掉、報酬怎麼算；額外招待猜中最愛有加成",
         "body": _serve, "commands": []},
        {"title": "🏪 雜貨店", "short": "人里基本食材的價格、為什麼不能拿來賺錢、一鍵買齊缺的素材",
         "body": _shop, "commands": ["shrine shop"]},
        {"title": "🎒 神社倉庫", "short": "所有道具都放在這裡：分類、效果標籤、翻頁；活動道具活動結束會清空",
         "body": _storage, "commands": ["shrine storage"]},
    ],
}

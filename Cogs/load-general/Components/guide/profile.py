"""
📚 🪪 資料卡與簽到・教學書 (0.36.000)
格式見 Components/guide_components.py；數字從程式常數讀 (profile.py、User_DB_Manager、Economy_DB_Manager、
title_data、general_components、notify_data…)，開畫面時才算。沒有 /profile help，只能從 /help 打開
"""
import importlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

DAILY_EXP = (100, 200)   # 來源：Cogs/load-general/profile.py perform_daily 的 random.randint(100, 200) (沒有常數)
MAX_LEVEL = 1000         # 來源：Database/User_DB_Manager.py calc_exp_change (level 0～1000 = 0.0～100.0 P，沒有常數)
PROFILE_TIMEOUT_MIN = 3  # 來源：Cogs/load-general/profile.py ProfileView 的 timeout=180 秒 (沒有常數)


def _mod(name: str):
    return importlib.import_module(name)


def _daily_item() -> tuple[str, int, int]:
    """簽到固定送的道具 ➔ (「emoji 名稱」, 數量, 回復體力；沒有就 0)。道具資料在 Item.db，讀不到就用預設清單"""
    im = _mod("Database.Item_DB_Manager")
    iid, amount = im.DAILY_REWARD_ITEM
    name, emoji, effect = iid, "🎁", {}
    for row in im.DEFAULT_ITEMS:
        if row[0] == iid:
            name, emoji, effect = row[1], row[2], row[5] or {}
    try:   # 唯讀開 Item.db (不存在就不會建檔)
        with closing(sqlite3.connect(Path(im.DB_PATH).as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT name, emoji, effect FROM item_templates WHERE item_id = ?", (iid,)).fetchone()
        if row:
            name, emoji = row[0] or name, row[1] or emoji
            effect = json.loads(row[2]) if row[2] else {}
    except Exception:
        pass
    return f"{emoji} {name}", amount, int((effect or {}).get("stamina") or 0)


def _title_mins(stat: str) -> list[int]:
    td = _mod("Database.title_data")
    return sorted(t["min"] for t in td.TITLES.values() if t.get("stat") == stat)


def _group(*keys: str) -> str:
    groups = _mod("Database.title_data").TITLE_GROUPS
    return "、".join(f"「{groups[k]['name']}」" for k in keys if k in groups)


def _daily() -> str:
    p = _mod("Cogs.load-general.profile")
    gc = _mod("Cogs.load-general.Components.general_components")
    econ = _mod("Database.Economy_DB_Manager")
    item, amount, stamina = _daily_item()
    levels = sorted(p.MONEY_RANGES, reverse=True)
    streak = " / ".join(str(n) for n in _title_mins("best_streak"))
    lines = [
        "每天向博麗神社**投一次賽錢**，抽今天的運勢，拿賽錢、經驗值和道具。",
        "",
        "### ⛩️ 怎麼簽到",
        "- 打 `/daily` 直接簽到，簽完會跳出你的資料卡，上面寫著這次拿到什麼",
        "- 也可以打 `/profile`，按「今日運勢」右邊的「⛩️ 投賽錢簽到」；簽過之後按鈕會變成「✅ 今日已簽到」",
        "- **一天一次**，每天**台灣時間 00:00** 重置；今天簽過再打 `/daily`，只會提醒你今天抽到的運勢",
        "",
        "### 🔮 運勢與賽錢",
        f"運勢有 {len(levels)} 種，**每一種機率都一樣**，運勢越好賽錢越多：",
    ]
    for lv in levels:
        lo, hi = p.MONEY_RANGES[lv]
        lines.append(f"- {gc.get_fortune_info(lv)['name']}：💰 {lo:,} ～ {hi:,}")
    lines += [
        "",
        "### ✨ 其他獎勵",
        f"- 經驗值 **{DAILY_EXP[0]}～{DAILY_EXP[1]} EXP** (跟運勢無關)，累積起來會讓 P 點上升 (見下一章)",
        f"- 每次固定送 {item} ×{amount}" + (f"，吃了回復 {stamina} 體力" if stamina else ""),
        "- 活動期間簽到可能有加成，或是多送活動道具",
        "",
        "### 📅 累積簽到與連續簽到",
        f"- **累積簽到**滿 **{econ.TRADE_UNLOCK_DAILY} 天** (不用連續) 就開通 💹 玩家市場與 💸 轉帳，資料卡上看得到還差幾天",
        f"- 累積天數也會解鎖{_group('daily')}稱號",
        f"- **連續簽到沒有額外獎勵**，只算稱號：最長連續紀錄達到 {streak} 天會解鎖{_group('streak')}稱號",
        "- 中斷一天就從 1 重新算，但**最長紀錄不會變少**",
        "",
        f"-# 小技巧：抽到大吉、凶的次數也有對應的{_group('luck')}稱號；凶的那天賽錢最少，但也算一次累積簽到",
    ]
    return "\n".join(lines)


def _card() -> str:
    udm = _mod("Database.User_DB_Manager")
    econ = _mod("Database.Economy_DB_Manager")
    shrine = _mod("Database.shrine_data")
    num = _mod("Utils.numbers")
    first = udm.get_required_exp_for_level(0)
    step = udm.get_required_exp_for_level(1) - first
    total = udm.get_total_exp_for_level(MAX_LEVEL)
    smax, interval = udm.STAMINA_MAX, udm.STAMINA_INTERVAL_SECONDS // 60
    full_hours = smax * udm.STAMINA_INTERVAL_SECONDS / 3600
    lines = [
        "打 `/profile` 看自己的資料卡「幻想鄉通行證」；`user` 選一位成員，就能看別人的。",
        "",
        "### 📋 資料卡上有什麼",
        "- 名字下面是戴著的**稱號**，資料卡左邊的色條會跟著稱號等級變色",
        f"- 💰 **賽錢**：{num.SHORT_FROM:,} 以上會縮寫，例如 `{num.fmt_money(1_500_000)}` = {1_500_000:,}",
        "- 🔴 **P點**、⚡ **體力**、⛩️ **神社倉庫** (道具總件數)",
        f"- 📅 **累積簽到**：滿 {econ.TRADE_UNLOCK_DAILY} 天會顯示「🔓 已開通市場與轉帳」",
        "- ✨ **經驗值進度條**：還差多少 EXP 升下一個 0.1 P",
        "- 🔮 **今日運勢**：今天簽到了沒、抽到什麼",
        "- 🖼️ **角色名片**：有戴才會出現，放在今日運勢下面 (見下一章)",
        "",
        "### 🌐 公開與私人",
        "- 預設是**公開**：你打 `/profile` 時大家都看得到，別人也可以查你",
        "- `/profile` 的 `visibility` 選 False 改成**私人**、選 True 改回公開 (設定的那一次，資料卡只有你看得到)",
        "- 私人資料卡：別人查你只會看到「🔒 無法存取個人資料」；你自己打 `/profile` 時只有你看得到",
        "- ⚠️ 打 `/daily` 簽到時，跳出來的資料卡**一律大家都看得到**；不想公開就在私人的 `/profile` 按「⛩️ 投賽錢簽到」"
        " (資料卡只有你看得到，但升級時的「💥 POWER UP!」通知還是會公開)",
        "- 排行榜上私人玩家照樣算名次，只是不顯示名字 (自己打開的排行榜例外，見排行榜那章)",
        "",
        "### 🔴 P點 (火力)",
        f"- 經驗值累積到門檻就升 **0.1 P**，會跳出「💥 POWER UP!」；最高 **{MAX_LEVEL / 10:.1f} P** (FULL POWER)",
        f"- 第一個 0.1 P 要 {first:,} EXP，之後每一級多要 {step:,} EXP；從 0 升到滿總共 {total:,} EXP",
        "- 經驗值來源：每日簽到、🎪 活動任務、🌀 裏世界探索",
        f"- P點**本身沒有額外效果**，用來解鎖{_group('power')}稱號、上排行榜",
        "",
        "### ⚡ 體力",
        f"- 上限 **{smax}**，每 **{interval} 分鐘**自然回 1 點，從 0 回滿要 {full_hours:g} 小時",
        f"- 用在神社採集 (`/shrine explore`)，一趟 {shrine.EXPLORE_STAMINA} 體力 (活動期間可能調整)",
        "- 吃體力道具可以**超過上限**；超過時不會自然回復，要用到上限以下才重新開始回",
        f"- 體力道具**一天最多吃 {udm.STAMINA_ITEM_DAILY_LIMIT} 個** (含簽到送的那個)，台灣時間 00:00 重置",
        "",
        "### 🔘 最底下那排按鈕 (只有自己的資料卡才有)",
        "- 「⚡ 恢復體力」：跳出小視窗，選要吃哪一個體力道具、吃幾個 (倉庫沒有體力道具、今天額度用完時會直接提醒你)",
        "- 「⛩️ 前往神社」：另外打開只有你看得到的神社畫面 (跟 `/shrine manage` 一樣)",
        "- 「🏷️ 修改稱號」、「🖼️ 修改名片」：換稱號和名片，見下一章",
        "- 「📥 下載名片原圖」：戴著有原圖的名片時才會出現，把高畫質原圖私訊給你 (私訊要開著)",
        f"-# 資料卡大約 {PROFILE_TIMEOUT_MIN} 分鐘沒操作，按鈕就會失效，重新打 `/profile` 就好",
    ]
    return "\n".join(lines)


def _titles() -> str:
    td = _mod("Database.title_data")
    groups = td.TITLE_GROUPS
    oshi = next((tid for tid in td.TITLES if tid.startswith("oshi_")), None)
    oshi_groups = "、".join(f"「{g['name']}」" for k, g in groups.items() if k.startswith("oshi_"))
    rarities = " → ".join(td.RARITY_ORDER)
    cats = [
        (("draw", "fusion", "synth"), "祈願、融合、合成的累計次數"),
        (("daily", "streak"), "累積簽到天數、最長連續簽到天數"),
        (("rare", "perfect"), "手上**現在**有幾種角色的 UR / LR、幾種完整度 1.0000 的完美卡 (收藏冊裡的也算)"),
        (("money",), "曾經持有過的最高賽錢 (花掉也不會掉)"),
        (("power",), "現在的 P 點"),
        (("market", "transfer"), "在市場被別人買走幾張卡、累計轉出多少賽錢"),
        (("shrine",), "神社的成功招待、採集、治退妖怪、料理、清掃、雜貨店次數，和從賽錢箱累計回收的賽錢"),
        (("guest",), "招待每一種參拜客的次數、端上牠最愛料理的次數"),
        (("trek",), "在每個採集地點採集的趟數，以及每個地點都去過"),
        (("luck",), "採集遇到好 / 壞事件、簽到抽到大吉 / 凶、祈願觸發保底、一次十連出 2 張以上 UR"),
        (("gourmet",), "做過幾種料理、吃了幾個體力道具、某一類料理全部做過"),
        (("ura",), "裏世界的📖 怪物圖鑑：某一區、或全部的怪物都登錄進圖鑑"),
        (("pool",), "某個卡池的角色到齊、全卡收集"),
        (("event",), "活動期間領取的活動任務數"),
    ]
    lines = [
        f"稱號會顯示在資料卡的名字下面，等級跟卡牌一樣分 {rarities}。目前一共 **{len(td.TITLES)}** 個，"
        "做到條件就**自動解鎖**，不用另外領。",
        "",
        "### 🗂️ 稱號有哪些大類",
    ]
    lines += [f"- {_group(*keys)}：{text}" for keys, text in cats if any(k in groups for k in keys)]
    if oshi_groups:
        lines.append(f"- {oshi_groups}：每位角色一個，跟角色名片有關 (下面講)")
    described = {k for keys, _ in cats for k in keys}
    extra = "、".join(f"「{g['name']}」" for k, g in groups.items() if k not in described and not k.startswith("oshi_"))
    if extra:   # 活動 / 卡池專屬的子分組 (客人・活動名、運氣・卡池名…)
        lines.append(f"-# 另外還有活動、卡池專屬的分組：{extra}")
    lines += [
        "",
        "### ⏳ 稱號會不會失去",
        "- **累積的** (次數、天數、最高紀錄)：拿到就不會失去",
        "- **永久保留的**：🗺️ 踏破、🍳 料理全收、🌀 怪物圖鑑全收、🎪 活動任務稱號，第一次達成就一直留著",
        "- **看「現在」的**：🌟 UR / LR 收藏、💎 完美卡、📚 卡池收集。卡被分解、上架 (上架中的卡不算在手上)、"
        "拿去合成 / 融合用掉，或完整度被扣 (🌀 裏世界)，就可能不符合條件而失去；條件再次達成就會自動回來",
        "- 💕 推角只看收藏冊：把卡拿出收藏冊就會失去 (名片不會，見下面)",
        "- 戴著的稱號失去時，資料卡會變成沒戴稱號；條件再次達成就會自動戴回去",
        "",
        "### 🏷️ 換稱號",
        "1. 在自己的資料卡按「🏷️ 修改稱號」，跳出一個只有你看得到的控制台",
        "2. 第一個選單「🗂️ 稱號分組」選一組，下面寫著這組解鎖了幾個",
        "3. 第二個選單「🏷️ 選稱號」選一個，每個都標著 🏷️ 戴著 / ✅ 已解鎖 / 🔒 解鎖條件",
        "4. 選了已解鎖的稱號，最上面會出現「👀 預覽」，確定就按「✅ 確認換上」，反悔按「↩️ 取消」",
        "5. 想拿掉稱號：按「✖️ 卸下稱號」再按「✅ 確認卸下」",
        "- 🔒 **還沒解鎖的稱號也全部列出來**，選了會寫出解鎖條件，可以當成目標清單",
        "- 換好後原本那張資料卡會跟著更新 (資料卡已經過期的話，重新打 `/profile` 就看得到)；"
        "解鎖新稱號時也可以收到私訊 (`/notify`)",
        "",
        "### 🖼️ 角色名片",
        "- 名片是放在資料卡「今日運勢」下面的一張角色橫幅圖",
        "- **怎麼拿**：把某位角色**每個階級**各一張**完美卡** (完整度 1.0000) 放進 🔒 收藏冊 (`/card album`) "
        "➔ 解鎖那位角色的推角稱號 ➔ **第一次**拿到推角稱號就**永久**獲得那位角色的名片",
    ]
    if oshi:
        lines.append(f"-# 例如「{td.title_label(oshi)}」：{td.condition_text(oshi)}")
    lines += [
        "- 之後把卡拿出收藏冊或賣掉，推角稱號會失去，但**名片會一直留著**",
        "- 「🖼️ 修改名片」：「🎰 卡池」選單 ➔「🖼️ 選名片」選單 ➔ 看預覽 ➔「✅ 確認換上」；"
        "不想放圖就按「✖️ 不放名片」再按「✅ 確認卸下」",
        "- 標「名片圖製作中」的名片可以先戴上，圖做好之後就會出現",
    ]
    return "\n".join(lines)


def _ranks() -> str:
    gc = _mod("Cogs.load-general.Components.general_components")
    nd = _mod("Database.notify_data")
    ndm = _mod("Database.Notify_DB_Manager")
    names = "、".join(name for name, _, _ in gc.LEADERBOARD_TYPES.values())
    card_names = "、".join(gc.LEADERBOARD_TYPES[k][0] for k in ("chars", "kinds", "cards") if k in gc.LEADERBOARD_TYPES)
    lines = [
        "### 🏆 排行榜",
        "- 打 `/leaderboard` 打開**本伺服器**的排行榜，訊息大家都看得到；`category` 可以直接選項目，不填就是賽錢",
        f"- 共 {len(gc.LEADERBOARD_TYPES)} 個項目：{names}",
        "- 打開後用「🏆 換一個排行項目」選單切換",
        "- **只比同一個伺服器**、有遊玩紀錄的成員 (機器人不算)",
        "- 💎 資產總值 = 賽錢 + 手上所有卡的價值 (現在市值 × 完整度倍率，收藏冊、上架中的卡也算)",
        f"- {card_names}：卡冊、收藏冊、裏世界出征中的卡都算，上架中的不算",
        "- 🌀 裏世界兩項只列**成功撤離過**的人：帶出最多錢算**單局淨賺** (帶出 − 帶進)，最深入只算成功撤離的局；"
        "同分的話先達成的排前面",
        "- 名字後面會顯示那位玩家戴著的稱號",
        "",
        "### 👀 翻頁與找自己",
        f"- 一頁 {gc.PER_PAGE} 名 (裏世界兩項一頁 {gc.URA_PER_PAGE} 名)，用「◀️ 上一頁」「下一頁 ▶️」翻",
        "- 「📍 跳到我的名次」直接翻到你那一頁 (還沒上榜時不能按)；你不在這一頁時，最下面會寫你目前第幾名",
        "- 你自己那一格會標「⬅️ 你」；只有打指令的人能操作這個排行榜",
        "",
        "### 🔒 私人資料卡",
        "- 私人玩家**照樣算名次**，但顯示成「🔒 私人玩家」，不顯示名字和稱號 (裏世界的角色、法具也不顯示)",
        "- ⚠️ 例外是**自己打開的排行榜**：上面會照常顯示你的名字、稱號 (和裏世界的角色、法具)，"
        "而排行榜訊息大家都看得到；別人打開的排行榜上，你才會是「🔒 私人玩家」",
        "",
        "### 🔔 私訊通知",
        "打 `/notify` 打開通知設定 (只有你看得到)，選哪些事情要機器人**私訊**你：",
    ]
    for info in nd.NOTIFY_TYPES.values():
        lines.append(f"- {info['emoji']} **{info['name']}**：{info['desc']}" + ("" if info.get("dm") else " (不支援私訊)"))
    lines += [
        "",
        "- **預設全部開啟**；每一種右邊有開關，按一下在「🔔 開啟中」和「🔕 已關閉」之間切換",
        "- 底下的「🔔 全部開啟」「🔕 全部關閉」一次切換全部",
        f"- 機器人每 {ndm.CHECK_INTERVAL_MINUTES} 分鐘檢查一次，同一件事只通知一次，同一輪的通知會合成一則私訊",
        "-# 要收得到私訊，伺服器的「私人訊息」設定要開著；私訊失敗的那幾則不會重送",
    ]
    return "\n".join(lines)


BOOK = {
    "intro": "每天簽到抽運勢、領賽錢；看自己的資料卡、P點和體力，換稱號和角色名片，再到排行榜比一比。",
    "chapters": [
        {"title": "📅 每日簽到與運勢", "short": "每天一次投賽錢簽到：運勢與賽錢、經驗值、送的道具，累積簽到開通市場與轉帳",
         "body": _daily, "commands": ["daily"]},
        {"title": "🪪 資料卡與體力", "short": "資料卡上有什麼、公開與私人、P點和體力怎麼算、最底下那排按鈕",
         "body": _card, "commands": ["profile"]},
        {"title": "🏷️ 稱號與名片", "short": "稱號怎麼解鎖、會不會失去、怎麼換；角色名片怎麼拿、怎麼戴",
         "body": _titles, "commands": []},
        {"title": "🏆 排行榜與通知", "short": "本伺服器的排行榜項目、翻頁與找自己的名次；/notify 開關私訊通知",
         "body": _ranks, "commands": ["leaderboard", "notify"]},
    ],
}

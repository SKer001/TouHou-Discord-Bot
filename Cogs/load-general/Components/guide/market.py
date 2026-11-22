"""
📚 💹 市場與交易・教學書 (0.36.000)
格式見 Components/guide_components.py；數字從 Database/Economy_DB_Manager.py 與 Cogs/load-market/market.py 的常數讀，開畫面時才算
手續費用基本費率 (活動可以用 modifiers.market_fee / transfer_fee 調整，書裡只提「活動期間可能調整」)
"""
import importlib
import inspect

COMPLETENESS_SAMPLES = (1.0, 0.9, 0.75, 0.5, 0.25, 0.1, 0.0)   # 完整度倍率表要列的點 (只是舉例)


def _econ():
    return importlib.import_module("Database.Economy_DB_Manager")


def _market():
    return importlib.import_module("Cogs.load-market.market")


def _pct(x: float) -> str:
    return f"{x * 100:g}%"


def _value() -> str:
    econ, mk = _econ(), _market()
    prices = "・".join(f"{r} {p:,}" for r, p in econ.OFFICIAL_PRICES.items())
    mults = "・".join(f"`{c:.2f}` ×{econ.completeness_multiplier(c):.2f}" for c in COMPLETENESS_SAMPLES)
    rise, fall = econ.PRICE_IDLE_RISE, econ.PRICE_DAILY_LIMIT
    rare1, rare2 = -econ.price_change(1, 0), -econ.price_change(2, 0)   # 預計一天新抽到不到 1 張的卡
    samples = " / ".join(f"{c:.4f}" for c in mk.VALUE_SAMPLES)
    history = inspect.signature(econ.get_price_history).parameters["days"].default   # /market price 列幾天的漲跌
    lines = [
        "每一種卡 (角色 × 階級) 都有一個**市值**，每天跟著全服的買賣浮動。分解拿到的錢、市場的參考價、"
        "排行榜的💎 資產總值都用它來算。",
        "",
        "### 💰 市值與官方價",
        "- 市值一開始等於**官方價**，之後怎麼跌都**不會低於官方價**：",
        f"-# {prices}",
        # 來源：Database/Economy_DB_Manager.py completeness_multiplier (0.5 = ×1，公式裡寫死，沒有常數)
        "- 市值是**完整度 0.5** 那張卡的價格；一張卡實際值多少 = 市值 × **完整度倍率**",
        "",
        "### 📐 完整度倍率",
        mults,
        f"- 完整度越接近 1 越值錢，滿分 ×{econ.completeness_multiplier(1.0):.1f}；"
        f"低於 0.5 掉得很快，最低 ×{econ.completeness_multiplier(0.0):.1f}",
        "",
        "### 📈 每天怎麼漲跌",
        "每天**台灣時間 00:00** 結算一次：看前一天這種卡**被賣掉幾張** (分解 + 市場成交都算)，"
        "跟全服那天的抽卡量換算出的「**預計新抽到幾張**」比。",
        f"- 沒人賣 ➔ 漲 **+{_pct(rise)}** (就算沒人抽也會漲；這也是一天最多漲的幅度)",
        f"- 賣掉的比預計新抽到的 {_pct(econ.NEUTRAL_RATIO)} 少 ➔ 小漲；剛好 {_pct(econ.NEUTRAL_RATIO)} ➔ 持平",
        f"- 賣得更多 ➔ 跌，賣到持平點的 {econ.SATURATE_RATIO:g} 倍就跌 **−{_pct(fall)}** (一天最多跌這麼多)",
        f"- 簡單說：**抽的人多、賣的人少就慢慢漲；大家一起賣就會跌**。一天最多漲 {_pct(rise)}、最多跌 {_pct(fall)}",
        f"-# 預計一天新抽到不到 1 張的卡 (照 1 張算)：同一天只要有人賣 1 張就跌 {_pct(rare1)}、賣 2 張就跌 {_pct(rare2)}",
        "",
        "### 🔍 查市值",
        f"打 `/market price`，選卡池 ➔ 選角色，就能看那位角色每個階級的市值 (和官方價)、今天已經賣掉幾張、"
        f"完整度 {samples} 各值多少，還有近 {history} 天每天的漲跌。",
        "",
        "### ♻️ 分解：直接換成賽錢",
        "- **不用開通**，第一天就能用；拿到的錢 = 市值 × 完整度倍率",
        f"- 打 `/market decompose`，選卡池 ➔ 選角色，列出你那位角色的卡 (一頁 {mk.PICK_PER_PAGE} 張，可以跨頁多選)",
        "- 選好按「♻️ 分解選取的 N 張」，確認畫面再按「♻️ 確認分解」；不要了就按「↩️ 返回」",
        "- ⚠️ **分解後卡就消失，不能復原**；實際金額以按下確認那一刻的市值為準",
        "- 🔒 **收藏冊 (`/card album`) 的卡不能分解**，也不會出現在清單裡；🌀 裏世界出征中的卡也一樣",
        "- 分解也算「賣出」：會讓這種卡隔天的漲幅變小，賣得夠多就會跌；活動期間分解有時會有加成",
    ]
    return "\n".join(lines)


def _shop() -> str:
    econ, mk = _econ(), _market()
    fee = econ.MARKET_BUYER_FEE
    example = 1000
    days = econ.LISTING_DURATION.days
    lines = [
        "把卡**自己訂價**賣給其他玩家，或買別人上架的卡。市場的操作畫面都只有你看得到 (上架公告除外)。",
        "",
        "### 🔓 開通條件",
        f"- **累積簽到 {econ.TRADE_UNLOCK_DAILY} 天** (不用連續) 才能上架和購買；資料卡上看得到還差幾天",
        "- 還沒開通也能先用 `/market browse` 逛逛、看價格",
        "",
        "### 🏷️ 上架",
        "- 打 `/market sell`，選卡池 ➔ 選角色，`price` 填售價 (**價格自訂**，至少 1)",
        "- 從清單選一張要賣的卡 (旁邊有參考市值)，確認畫面再按「🏷️ 確認上架」；不要了就按「↩️ 返回」",
        "- 上架後卡會交給市場**託管**：離開你的卡冊，不能合成、融合、分解，"
        "也不算進看「手上現在有」的稱號 (🌟 UR / LR 收藏、💎 完美卡、📚 卡池收集)",
        "- 確認後會在頻道發一則大家都看得到的「🏷️ 市場新上架」公告 (有你的名字、稱號和買家要付的價格)",
        "- 🔒 收藏冊、🌀 裏世界出征中的卡不能上架",
        "",
        "### 💰 價格與手續費",
        f"- 賣出時你拿到**全部售價**；手續費 **{_pct(fee)}** 由**買家**另外付",
        f"- 例如售價 {example:,} ➔ 買家付 {econ.buyer_total(example, 1.0):,} (有小數就進位)",
        "- 活動期間手續費可能調整，以確認畫面寫的為準",
        "",
        "### ⌛ 沒賣出會怎樣",
        f"- 上架 **{days} 天**沒賣出就自動下架，卡退回你的卡冊，也會收到「📦 上架到期退回」私訊 (可以在 `/notify` 關掉)",
        "- 想提早收回：打 `/market mine`，從「選擇要下架的卡…」選一張，再按「📤 確認下架」",
        "",
        "### 🛒 瀏覽與購買",
        f"- 打 `/market browse`，選卡池 (`character` 可以不填 = 整個卡池)，**最便宜的排最前面**，一頁 {mk.LISTINGS_PER_PAGE} 張",
        "- 清單上的價格是**買家要付的錢** (含手續費)，也寫著還剩多久下架；自己上架的會標「（你的）」，不能買",
        "- 從「選擇要購買的卡…」選一張，再按「🛒 確認購買」，卡馬上進你的卡冊",
        "- 賣家的錢會立刻入帳，也會收到「💹 上架的卡賣出了」私訊 (可以在 `/notify` 關掉)",
        "",
        "-# 小技巧：上架前先用 `/market price` 看看市值；市場成交也算「賣出」，同一種卡大家一起賣，隔天市值就會跌",
    ]
    return "\n".join(lines)


def _trade() -> str:
    econ = _econ()
    fee = econ.TRANSFER_FEE
    example = 1000
    cut = econ.transfer_fee(example, 1.0)   # 1.0 = 基本費率 (不帶活動倍率)
    lines = [
        "直接把賽錢轉給其他玩家。打 `/trade`，`target` 選收款的玩家、`amount` 填金額。",
        "",
        "### 🔓 開通條件",
        f"- **你和對方都要累積簽到 {econ.TRADE_UNLOCK_DAILY} 天**才能轉；對方還沒開通的話，"
        "按下確認時會顯示「🔒 對方還沒開通交易」，錢不會轉出去",
        "- 不能轉給自己，也不能轉給機器人",
        "",
        "### 💸 手續費",
        f"- 手續費 **{_pct(fee)}**，從你轉出的金額裡扣 (有小數就進位)",
        f"- 例如轉 {example:,} ➔ 手續費 {cut:,}，對方實收 **{example - cut:,}**；你這邊就是扣 {example:,}",
        "- 活動期間手續費可能調整，以確認畫面寫的為準",
        "",
        "### 📅 每天上限",
        f"- 每人每天**最多轉出 {econ.TRANSFER_DAILY_LIMIT:,}** (算轉出的金額，含手續費)，台灣時間 00:00 重置",
        "- 確認畫面會寫今天已經轉出多少；超過時會告訴你今天還能轉多少",
        "",
        "### ✅ 轉帳流程",
        "- 打完指令會先跳出只有你看得到的確認畫面：轉給誰、手續費、對方實收",
        "- 按「💸 確認轉帳」才會真的轉；不要了就按「✖️ 取消」",
        "- ⚠️ 轉出去就**不能取消**，按確認前看清楚對象和金額",
        "",
        "### 📨 收款人會收到私訊",
        "- 對方會收到「💸 你收到一筆轉帳」的私訊，寫著誰轉的、從哪個伺服器、扣掉手續費實收多少",
        "- 對方關閉私訊也**照樣轉帳成功**，只是你會看到「對方關閉了私訊，沒有收到通知」",
        "- 這則私訊是轉帳當下直接送的，不受 `/notify` 的開關影響",
        "",
        "-# 累計轉出的金額 (手續費前) 會解鎖「💸 轉帳」稱號",
        "-# 沒有直接送卡的功能：想把卡給朋友，可以上架到市場再請對方用 `/market browse` 買 (不過其他人也買得到)",
    ]
    return "\n".join(lines)


BOOK = {
    "intro": "每張卡都有每天浮動的市值：可以直接分解換賽錢，也可以上架賣給其他玩家，或把賽錢轉給朋友。",
    "chapters": [
        {"title": "📈 市值與分解", "short": "卡的市值每天怎麼漲跌、完整度倍率、把卡直接分解成賽錢",
         "body": _value, "commands": ["market price", "market decompose"]},
        {"title": "🛒 玩家市場", "short": "開通條件、自訂價格上架、買家手續費、沒賣出自動退回、瀏覽購買與下架",
         "body": _shop, "commands": ["market sell", "market browse", "market mine"]},
        {"title": "💸 轉帳", "short": "雙方都要開通、手續費、每天上限，收款人會收到私訊",
         "body": _trade, "commands": ["trade"]},
    ],
}

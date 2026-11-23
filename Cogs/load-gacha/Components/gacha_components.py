"""
卡牌畫面產生器 (Discord Components V2)

需要 discord.py >= 2.6   ➔  pip install -U discord.py

這裡的每個 build_*_container() 都回傳一個 ui.Container：
  - 左側色條 = Container 的 accent_color
  - 每張卡 = 一個 Section (左邊文字 + 右邊 Thumbnail)
呼叫端 (gacha.py) 再把按鈕 / 選單加進 Container，最後放進 LayoutView 送出。

⚠️ Components V2 訊息不能同時帶 content / embeds，且「每則訊息最多 40 個元件」，
   (Section 本身 + 文字 + Thumbnail = 3 個)，所以每頁的列數要算過。
"""
import discord
from discord import ui

# 卡冊 (疊卡列表) 每頁疊數：
#   Container + 標題 + 分隔(3) + 7 疊 Section(21) + 分隔(1)
#   + 卡池篩選 / 階級篩選 / 疊選單 三列(6) + 翻頁與排序列(5) = 36 < 40
STACKS_PER_PAGE = 7
# 單一疊內每頁張數：
#   Container + 標題 + 分隔(3) + 8 張 Section(24) + 分隔(1) + 卡牌選單列(2) + 返回與翻頁列(5) = 35 < 40
STACK_CARDS_PER_PAGE = 8


def get_completeness_eval(completeness: float) -> tuple[str, discord.Color]:
    """根據完整度回傳東方風格評價名稱與顏色"""
    comp_str = f"{completeness:.4f}"

    if completeness >= 0.990:
        return f"💠 **{comp_str}** [神代之遺]", discord.Color.teal()
    elif completeness >= 0.900:
        return f"🌟 **{comp_str}** [蓬萊仙姿]", discord.Color.gold()
    elif completeness >= 0.700:
        return f"🌸 **{comp_str}** [西行櫻華]", discord.Color.purple()
    elif completeness >= 0.400:
        return f"🍃 **{comp_str}** [妖怪山珍]", discord.Color.green()
    elif completeness >= 0.150:
        return f"🍂 **{comp_str}** [人間凡品]", discord.Color.light_grey()
    elif completeness >= 0.050:
        return f"🪵 **{comp_str}** [迷途遺物]", discord.Color.dark_grey()
    else:
        return f"🏚️ **{comp_str}** [彈幕戰痕]", discord.Color.dark_red()


# ================= 🖼️ Thumbnail 機制 =================
def get_thumbnail_url(char_key: str | None, thumbnails: dict | None, rarity: str | None = None) -> str | None:
    """
    依角色 ID 與階級 (例如 "marisa" + "UR") 到 Thumbnails.json 查 URL：
    1. 有 "角色_階級" (例如 "marisa_UR") ➔ 使用該階級的卡面
    2. 有角色 ID ➔ 使用角色專屬圖片
    3. 都沒有 ➔ 退回使用 "fill" 的 URL；連 "fill" 都沒有 ➔ 回傳 None (該項目只顯示文字)
    """
    if not thumbnails:
        return None
    return (thumbnails.get(f"{char_key}_{rarity}") if rarity else None) or thumbnails.get(char_key) or thumbnails.get("fill")


def _card_block(text: str, char_key: str | None, thumbnails: dict | None, rarity: str | None = None):
    """文字 + 右側縮圖的 Section；沒有任何圖片 URL 時退化成純文字"""
    url = get_thumbnail_url(char_key, thumbnails, rarity)
    if url:
        return ui.Section(ui.TextDisplay(text), accessory=ui.Thumbnail(url))
    return ui.TextDisplay(text)


def _card_text(index: int, card: dict, id_first: bool = True) -> str:
    eval_str, _ = get_completeness_eval(card["completeness"])
    head = f"**{index}.** {card.get('emoji', '🎴')} `[{card['rarity']}]` **{card['name']}**"
    if card.get("pity"):
        head += "　🎯 保底"
    if id_first:
        return f"{head}\n├ *{card['title']}*\n└ ID: `{card['instance_id']}` · {eval_str}"
    return f"{head}\n├ *{card['title']}*\n└ {eval_str} | ID: `{card['instance_id']}`"


# ================= 🎴 Container 建構 =================
def build_gacha_single_container(card_data: dict, user_name: str, cost: int, thumbnails: dict = None,
                                 pool_name: str = "", pity_text: str = "") -> ui.Container:
    """單抽結果"""
    eval_str, color = get_completeness_eval(card_data["completeness"])

    text = (
        f"## ⛩️ 博麗神社祈願成功！\n"
        f"-# 卡池：{pool_name}\n"
        f"投入了 `{cost:,}` 賽錢，塞錢箱發出了清脆的聲響...\n\n"
        f"**角色**：{card_data.get('emoji', '🎴')} **{card_data['name']}**\n"
        f"**階級與稱號**：`[{card_data['rarity']}]` {card_data['title']}\n"
        f"**完整度品相**：{eval_str}\n\n"
        f"{pity_text}\n"
        f"-# 卡牌編號: {card_data['instance_id']} | 擁有者: {user_name}"
    )

    container = ui.Container(accent_color=color)
    container.add_item(_card_block(text, card_data.get("character_key"), thumbnails, card_data.get("rarity")))
    return container


def build_gacha_ten_container(results: list[dict], user_name: str, total_cost: int, thumbnails: dict = None,
                              pool_name: str = "", pity_text: str = "") -> ui.Container:
    """十連結果：標題 + 分隔線 + 10 個『文字＋右側縮圖』的 Section"""
    best_card = max(results, key=lambda c: c["completeness"])
    _, color = get_completeness_eval(best_card["completeness"])

    container = ui.Container(accent_color=color)
    container.add_item(ui.TextDisplay(
        f"## ⛩️ {user_name} 的抽卡結果（十連模式）\n"
        f"🎰 卡池：{pool_name}\n"
        f"共抽到 **{len(results)}** 張卡片 · 消耗賽錢：`{total_cost:,}` 🪙\n"
        f"{pity_text}\n"
        f"-# 卡牌已全數寫入個人卡庫"
    ))
    container.add_item(ui.Separator())

    for idx, card in enumerate(results, start=1):
        container.add_item(_card_block(_card_text(idx, card, id_first=True), card.get("character_key"), thumbnails, card.get("rarity")))

    return container


def build_gacha_history_container(user_name: str, pools: dict, pity: dict, stats: dict,
                                  threshold: int, pity_rarity: str, next_rates: dict | None = None,
                                  notes: dict | None = None) -> ui.Container:
    """
    祈願紀錄：各卡池的累計抽數與保底進度
    pools = GACHA_POOLS；pity = {"卡池": {"total_draws", "since_ur", "last_ur_at"}}；stats = get_gacha_stats()
    next_rates = {"卡池": 下一抽 UR 的機率文字 (例 "1.54%")}；值是 None = 這個卡池沒有 UR (沒有保底)
    notes = {"卡池": 加在卡池名稱後面的說明 (例 紅魔鄉「🎪 紅霧異變期間開放」)}
    """
    next_rates, notes = next_rates or {}, notes or {}
    container = ui.Container(accent_color=discord.Color.gold())
    container.add_item(ui.TextDisplay(
        f"## 📜 {user_name} 的祈願紀錄\n"
        f"🎰 **總祈願次數**：`{stats.get('total_draws', 0):,}` 抽 · 🔮 **融合次數**：`{stats.get('total_fusions', 0):,}` 次\n"
        f"-# 每個卡池分開算：{pity_rarity} 前 80 抽 0.1%，第 81 抽起慢慢升高，第 {threshold} 抽必定獲得 {pity_rarity}；LR 不影響保底"
    ))
    container.add_item(ui.Separator())

    lines = []
    for key, p in pools.items():
        row = pity.get(key, {"total_draws": 0, "since_ur": 0, "last_ur_at": None})
        since = row["since_ur"]
        last = row["last_ur_at"] or "尚未獲得"
        title = f"### {p['name']}" + (f"\n-# {notes[key]}" if notes.get(key) else "")
        if key in next_rates and next_rates[key] is None:
            lines.append(f"{title}\n累計 `{row['total_draws']:,}` 抽 · 這個卡池沒有 {pity_rarity}，沒有保底")
            continue
        filled = min(10, since * 10 // threshold)
        bar = "🟨" * filled + "⬛" * (10 - filled)
        rate = f" · 下一抽 {pity_rarity} `{next_rates[key]}`" if next_rates.get(key) else ""
        lines.append(
            f"{title}\n"
            f"累計 `{row['total_draws']:,}` 抽 · 保底 `{since} / {threshold}`{rate}（最晚再 `{threshold - since}` 抽必出 {pity_rarity}）\n"
            f"{bar}\n"
            f"-# 上次獲得 {pity_rarity}：{last}"
        )
    container.add_item(ui.TextDisplay("\n".join(lines)))
    return container


def _pct(p: float, digits: int = 2) -> str:
    """0.43452 ➔ 43.45%；尾數的 0 去掉 (0.001 ➔ 0.1%)"""
    return f"{p * 100:.{digits}f}".rstrip("0").rstrip(".") + "%"


def build_rate_sheet_container(data: dict, threshold: int, pity_rarity: str) -> ui.Container:
    """
    📊 機率表 (gacha.rate_sheet_data 算好的數字)：起始機率與各階級角色、UR 曲線與累積機率、長期平均、自己的保底進度
    """
    order = ["N", "R", "SR", "SSR", "UR", "LR"]
    start, holders = data["start"], data["holders"]
    head = [f"## 📊 機率表：{data['pool_name']}",
            "-# 每一抽先抽階級，再從這個卡池裡有這個階級的角色平均抽一位"]
    if data["event_pool"]:
        head.append("-# 🎪 活動限定卡池：保底跟一般卡池分開算")
    if data.get("open_note"):
        head.append(f"-# {data['open_note']}；保底照樣記在這個卡池，活動下次再開也接著算")
    if data["event_rates"]:
        head.append("🎪 **活動期間調整了起始機率**（下面的數字已經是活動中的機率）")
    if data["rate_up"]:
        ups = "、".join(f"{name} ×{m:g}" for name, m in data["rate_up"].items())
        head.append(f"🎪 **活動機率提升**：{ups}（抽到那個階級時，比同階級的其他角色容易出現）")

    rows = []
    for r in order:
        names = holders.get(r)
        if not names:
            rows.append(f"`{r}` —（這個卡池沒有）")
            continue
        rate = _pct(start[r])
        if r == pity_rarity:
            rate += " 起，依保底進度往上升"
        each = "" if r == pity_rarity else f"，每位 {_pct(start[r] / len(names))}"
        rows.append(f"`{r}` **{rate}** · {len(names)} 位{each}\n-# {'、'.join(names)}")
    rarity_text = "### 🎴 起始機率與角色\n" + "\n".join(rows)

    if data["has_ur"]:
        (n1, p1), (n2, p2), (n3, p3) = data["curve"].items()
        c1, c2, c3 = (data["cum"][n] for n in (n1, n2, n3))
        ur_text = (
            f"### 🎯 {pity_rarity} 機率與保底（距離上次 {pity_rarity} 的第幾抽）\n"
            f"- 第 1～{n1} 抽：每抽 {_pct(p1)}\n"
            f"- 第 {n1 + 1}～{n2} 抽：慢慢升到 {_pct(p2)}\n"
            f"- 第 {n2 + 1}～{n3} 抽：慢慢升到 {_pct(p3)}\n"
            f"- 第 {threshold} 抽：**必出 {pity_rarity}**（保底，從有 {pity_rarity} 的角色平均抽一位）\n"
            f"-# {pity_rarity} 多出來的機率從 N / R / SR 照比例扣；抽到 {pity_rarity} 才重新計算\n"
            f"📈 {n1} 抽內出 {pity_rarity}：**{_pct(c1, 1)}** · {n2} 抽內：**{_pct(c2, 1)}** · "
            f"{n3} 抽內：**{_pct(c3, 1)}** · 吃到保底：**{_pct(data['pity'], 1)}**\n"
            f"📈 長期平均每抽 {pity_rarity} {_pct(data['long_run'][pity_rarity])}，平均 **{data['avg']:.1f}** 抽一張"
        )
        since = data["since_ur"]
        nxt = "必出" if data["next"] >= 1 else _pct(data["next"])
        mine = f"### 🧾 你的保底進度\n保底 `{since} / {threshold}` · 下一抽 {pity_rarity} `{nxt}`"
    else:
        ur_text = f"### 🎯 保底\n這個卡池沒有 {pity_rarity} 角色，所以抽不到 {pity_rarity}，也沒有保底。"
        mine = ""
    lr_text = (f"💎 **LR 固定 {_pct(start['LR'])}**，跟保底無關：抽到 LR 不會重置 {pity_rarity} 的保底進度"
               if holders.get("LR") else "")

    container = ui.Container(accent_color=discord.Color.blurple())
    container.add_item(ui.TextDisplay("\n".join(head)))
    container.add_item(ui.Separator())
    container.add_item(ui.TextDisplay(rarity_text))
    container.add_item(ui.Separator())
    container.add_item(ui.TextDisplay("\n".join(t for t in (ur_text, lr_text) if t)))
    if mine:
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(mine))
    return container


def _rarity_stats(all_cards: list) -> str:
    rarity_counts = {"N": 0, "R": 0, "SR": 0, "SSR": 0, "UR": 0, "LR": 0}
    for card in all_cards:
        r = card.get("rarity", "N")
        if r in rarity_counts:
            rarity_counts[r] += 1
    return " | ".join(f"`{r}`: {n}" for r, n in rarity_counts.items())


def build_stack_list_container(
    stacks_page: list[dict],
    current_page: int,
    total_pages: int,
    total_stacks: int,
    all_cards: list,
    user_name: str,
    thumbnails: dict = None,
    filter_desc: str = "",
    start_index: int = 1,
    progress_text: str = "",
) -> ui.Container:
    """
    個人卡冊 (疊卡模式)：同角色、同階級的卡疊成一列
    stack = {"character_key", "rarity", "name", "emoji", "title", "cards": [...], "best": float, "can_synth", "can_fuse"}
    progress_text：各卡池的收集進度 (一行)
    """
    header = (
        f"## 🎒 {user_name} 的博麗神社卡冊\n"
        f"📊 **持有總量**：`{len(all_cards)}` 張 · `{total_stacks}` 疊 (目前篩選)\n"
        f"🏷️ **階級統計**：{_rarity_stats(all_cards)}\n"
        f"📚 **收集進度**：{progress_text}\n"
        f"-# {filter_desc} · ⚗️ 可合成 · 🔮 可融合"
    )

    if not stacks_page:
        container = ui.Container(accent_color=discord.Color.blue())
        container.add_item(ui.TextDisplay(header))
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(f"*（當前篩選下沒有任何卡牌）*\n-# 頁數: {current_page} / {total_pages}"))
        return container

    best_stack = max(stacks_page, key=lambda s: s["best"])
    _, color = get_completeness_eval(best_stack["best"])

    container = ui.Container(accent_color=color)
    container.add_item(ui.TextDisplay(header))
    container.add_item(ui.Separator())

    for idx, stack in enumerate(stacks_page, start=start_index):
        best_eval, _ = get_completeness_eval(stack["best"])
        text = (
            f"**{idx}.** {stack.get('emoji', '🎴')} `[{stack['rarity']}]` **{stack['name']}**　×**{len(stack['cards'])}**"
            f"{'　⚗️' if stack.get('can_synth') else ''}{'　🔮' if stack.get('can_fuse') else ''}\n"
            f"├ *{stack['title']}*\n"
            f"└ 最高完整度 {best_eval}"
        )
        container.add_item(_card_block(text, stack["character_key"], thumbnails, stack["rarity"]))

    return container


def build_stack_cards_container(
    stack: dict,
    cards_page: list,
    current_page: int,
    total_pages: int,
    user_name: str,
    thumbnails: dict = None,
    start_index: int = 1,
) -> ui.Container:
    """單一疊的內容：列出這一疊裡的每一張卡 (依完整度由高到低)"""
    _, color = get_completeness_eval(stack["best"])
    container = ui.Container(accent_color=color)
    container.add_item(ui.TextDisplay(
        f"## {stack.get('emoji', '🎴')} `[{stack['rarity']}]` {stack['name']}　×{len(stack['cards'])}\n"
        f"*{stack['title']}*\n"
        f"-# {user_name} 的卡冊 · 依完整度由高到低排列"
    ))
    container.add_item(ui.Separator())

    for idx, card in enumerate(cards_page, start=start_index):
        eval_str, _ = get_completeness_eval(card["completeness"])
        text = f"**{idx}.** {eval_str}\n└ ID: `{card['instance_id']}` · 取得於 `{card.get('obtained_at', '未知')}`"
        container.add_item(_card_block(text, card.get("character_key"), thumbnails, card.get("rarity")))

    return container


DETAIL_DESC_MAX = 300   # 單卡詳情的角色簡介最多幾個字 (超過截斷，完整的看 📖 角色圖鑑)


def build_card_detail_container(card_data: dict, user_name: str, thumbnails: dict = None, info: dict | None = None) -> ui.Container:
    """
    單張卡牌詳細鑑定頁面 (卡冊 / 收藏冊 / 管理員看別人卡冊共用；2026-11-23 改版)
    info = gacha.card_detail_info() 算好的：profile / ura / spell / value / synth / fuse (沒有的段落就不顯示)
    段落：卡片 ➔ 📜 角色資料 ➔ ⚔️ 這張卡的實力 ➔ ✨ 這張卡的特殊能力 ➔ 💹 價值 ➔ 🗂️ 卡牌資訊
    """
    info = info or {}
    eval_str, color = get_completeness_eval(card_data["completeness"])
    rarity = card_data["rarity"]
    container = ui.Container(accent_color=color)
    container.add_item(_card_block(
        f"## 🎴 卡牌鑑定詳情：{card_data.get('emoji', '🎴')} {card_data['name']}　`[{rarity}]`\n"
        f"*{card_data['title']}*\n"
        f"**完整度品相**：{eval_str}",
        card_data.get("character_key"), thumbnails, rarity))

    p = info.get("profile")
    if p:
        desc = p.get("description", "")
        if len(desc) > DETAIL_DESC_MAX:
            desc = desc[:DETAIL_DESC_MAX].rstrip() + "…完整介紹看📖 角色圖鑑"
        lines = ["### 📜 角色資料"]
        head = (f"**【{p['title']}】**" if p.get("title") else "") + (f" · 種族：{p['species']}" if p.get("species") else "")
        if head:
            lines.append(head.lstrip(" ·"))
        if p.get("ability"):
            lines.append(f"**能力**：`{p['ability']}`")
        if desc:
            lines.append(desc)
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay("\n".join(lines)))

    u = info.get("ura")
    if u:
        go = (f"✅ 可以派去裏世界 (完整度 ≥ {u['min']:g})" if u["ok"]
              else f"⚠️ 完整度不到 {u['min']:g}，不能派去裏世界")
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(
            f"### ⚔️ 這張卡的實力\n"
            f"❤️ HP `{u['hp']:,}` · ⚔️ ATK `{u['atk']}` · 🛡️ DEF `{u['def']}`　{u['cls']}\n"
            f"{go}\n"
            f"-# 跟裏世界出征時一樣：角色基礎數值 × 階級 `[{rarity}]` ×{u['rarity_mult']:g} × 完整度倍率 ×{u['comp_mult']:.2f}"))

    s = info.get("spell")
    if s:
        cd = f"`{s['cd']}` 回合" + (f" (完整度超過 0.8，比平常的 {s['cd_base']} 回合短)" if s["cd"] < s["cd_base"] else "")
        detail = " · ".join(x for x in (s.get("type_name"), f"消耗 B 點 `{s['b']}`", f"冷卻 {cd}") if x)
        numeral = f"**{s['numeral']}** " if s.get("numeral") else ""
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(
            f"### ✨ 這張卡的特殊能力：{s['sp_name']}\n"
            f"{numeral}`[{rarity}]` {s['name']}\n└ {detail}"
            + (f"\n-# {s['effect']}" if s.get("effect") else "")))

    v = info.get("value")
    if v:
        mult = f" × 活動分解倍率 ×{v['mult']:g}" if v["mult"] != 1 else ""
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(
            f"### 💹 價值\n分解能拿 `{v['value']:,}` 賽錢\n"
            f"-# 這張卡的市值 `{round(v['price']):,}` × 完整度倍率{mult} (跟 `/market decompose` 一樣)"))

    if card_data.get("locked"):
        state = "🔒 收藏中：放在收藏冊，不能合成、融合、分解、上架"
    elif card_data.get("expedition"):
        state = "🌀 出征中：正在裏世界，那一局結束前不能合成、融合、分解、上架"
    elif info.get("fuse"):
        f = info["fuse"]
        state = (f"🔮 可以融合 ➔ `[{f['next']}]`：完美卡 `{f['have']} / {f['need']}` 張" if f["have"] >= f["need"]
                 else f"💠 完美卡：同角色同階級 `{f['have']} / {f['need']}` 張，湊滿就能融合 ➔ `[{f['next']}]`")
    elif info.get("synth"):
        state = f"⚗️ 同角色同階級還有 `{info['synth']}` 張可以一起合成"
    elif "synth" in info:
        state = "🎴 在卡冊裡 (同角色同階級沒有其他可以一起合成的卡)"
    else:
        state = "🎴 在卡冊裡"
    container.add_item(ui.Separator())
    container.add_item(ui.TextDisplay(
        f"### 🗂️ 卡牌資訊\n"
        f"**卡牌 ID**：`{card_data['instance_id']}`\n"
        f"**取得時間**：`{card_data.get('obtained_at') or '未知'}`\n"
        f"**狀態**：{state}\n"
        f"-# 擁有者: {user_name}"))
    return container


ALBUM_PER_PAGE = 10   # 收藏冊每頁幾張 (選單一頁列完)


def build_album_container(page_cards: list[dict], page: int, total_pages: int, total: int,
                          user_name: str, start: int = 1, result: str | None = None) -> ui.Container:
    """🔒 收藏冊：鎖住的卡 (卡冊、合成、融合、分解、上架都看不到)，點卡可以取出"""
    head = f"{result}\n" if result else ""
    head += f"## 🔒 {user_name} 的收藏冊\n收藏中 `{total}` 張。放在這裡的卡不會被合成、融合、分解或上架。"
    container = ui.Container(accent_color=discord.Color.from_rgb(233, 30, 99))
    container.add_item(ui.TextDisplay(head))
    container.add_item(ui.Separator())
    if page_cards:
        lines = [f"**{start + i}.** {c.get('emoji') or '🎴'} `[{c['rarity']}]` **{c['name']}** · `{c['completeness']:.4f}`"
                 for i, c in enumerate(page_cards)]
        container.add_item(ui.TextDisplay("\n".join(lines)))
    else:
        container.add_item(ui.TextDisplay("收藏冊是空的。\n在 `/card inventory` 點開一張卡，按「🔒 放進收藏冊」就能收進來。"))
    container.add_item(ui.TextDisplay(f"-# 第 {page} / {total_pages} 頁"))
    return container


# ================= ⚗️ 合成 / 🔮 融合 =================
def _material_lines(cards: list[dict]) -> str:
    lines = []
    for idx, card in enumerate(cards, start=1):
        eval_str, _ = get_completeness_eval(card["completeness"])
        lines.append(f"**{idx}.** `{card['instance_id']}` · {eval_str}")
    return "\n".join(lines)


def build_synthesis_preview_container(card_a: dict, card_b: dict, preview: dict, user_name: str, thumbnails: dict = None) -> ui.Container:
    """合成確認畫面：兩張素材 + 預計結果 (一般 / 加倍兩種可能，按下確認才擲加倍)"""
    normal_eval, color = get_completeness_eval(preview["normal_completeness"])
    doubled_eval, _ = get_completeness_eval(preview["doubled_completeness"])
    chance = preview["double_chance"] * 100

    text = (
        f"## ⚗️ 卡牌合成確認\n"
        f"{card_a.get('emoji', '🎴')} `[{card_a['rarity']}]` **{card_a['name']}** - *{card_a['title']}*\n\n"
        f"**消耗素材**\n{_material_lines([card_a, card_b])}\n\n"
        f"**一般結果**：{normal_eval}（`+{preview['normal_increase']:.4f}`）\n"
        f"**✨ 加倍結果**：{doubled_eval}（`+{preview['doubled_increase']:.4f}`）\n"
        f"**🎲 加倍機率**：`{chance:.2f}%`\n"
        f"-# 兩張完整度越接近，增幅與加倍機率越高\n\n"
        f"-# ⚠️ 確認後兩張素材卡會消失，並產生一張新卡 | 擁有者: {user_name}"
    )
    container = ui.Container(accent_color=color)
    container.add_item(_card_block(text, card_a.get("character_key"), thumbnails, card_a.get("rarity")))
    return container


def build_synthesis_result_container(new_card: dict, increase: float, doubled: bool, user_name: str, thumbnails: dict = None) -> ui.Container:
    """合成完成"""
    eval_str, color = get_completeness_eval(new_card["completeness"])
    bonus_str = f"`+{increase:.4f}`" + (" ✨ 加倍！" if doubled else "")

    text = (
        f"## ⚗️ 合成成功！\n"
        f"兩張卡牌的靈力交融在一起，化為了新的形態...\n\n"
        f"**角色**：{new_card.get('emoji', '🎴')} **{new_card['name']}**\n"
        f"**階級與稱號**：`[{new_card['rarity']}]` {new_card['title']}\n"
        f"**完整度品相**：{eval_str}（{bonus_str}）\n\n"
        f"-# 卡牌編號: {new_card['instance_id']} | 擁有者: {user_name}"
    )
    container = ui.Container(accent_color=color)
    container.add_item(_card_block(text, new_card.get("character_key"), thumbnails, new_card.get("rarity")))
    return container


def build_auto_synthesis_preview_container(sample: dict, preview: dict, user_name: str, thumbnails: dict = None) -> ui.Container:
    """
    ⚡ 自動合成全部的確認畫面：preview = {階級: 未滿 1.0000 的張數} (gacha.auto_synthesis_preview)
    合到 1.0000 的卡會提早退出，所以次數寫「最多」
    """
    rows = "\n".join(f"`{r}`：`{n}` 張 ➔ 最多合成 `{n - 1}` 次" for r, n in preview.items())
    top = list(preview)[-1]
    text = (
        f"## ⚡ 自動合成全部：{sample.get('emoji', '🎴')} {sample['name']}\n"
        f"每個階級各自合：每次拿**完整度最低的兩張**合成，新卡放回去繼續比，合到只剩一張未滿 `1.0000` 為止"
        f"（合到 `1.0000` 的卡不再參加）\n\n"
        f"{rows}\n\n"
        f"-# ⚠️ 用掉的卡會消失，每一次會不會加倍都是隨機的，合完**不能還原**\n"
        f"-# 🔒 收藏冊、正在裏世界出征的卡不會被合；想留的卡先放進收藏冊 (`/card album`) | 擁有者: {user_name}"
    )
    container = ui.Container(accent_color=discord.Color.orange())
    container.add_item(_card_block(text, sample.get("character_key"), thumbnails, top))
    return container


def build_auto_synthesis_result_container(sample: dict, result: dict, user_name: str, thumbnails: dict = None) -> ui.Container:
    """⚡ 自動合成完成：每個階級一行 (合成幾次、加倍幾次、剩下那張的完整度、合到 1.0000 的張數)，不逐次列"""
    rows = []
    for r, info in result["rarities"].items():
        line = f"`{r}`：合成 `{info['count']}` 次" + (f"（✨ 加倍 `{info['doubled']}` 次）" if info["doubled"] else "")
        if info["last"] is not None:
            line += f" ➔ 剩下 {get_completeness_eval(info['last'])[0]}"
        if info["perfect"]:
            line += f" · 合到 `1.0000`：`{info['perfect']}` 張"
        rows.append(line)
    top = list(result["rarities"])[-1] if result["rarities"] else sample.get("rarity")
    text = (
        f"## ⚡ 自動合成完成：{sample.get('emoji', '🎴')} {sample['name']}\n"
        f"卡牌的靈力一張接一張交融在一起...\n\n"
        + "\n".join(rows) +
        f"\n\n-# 共合成 {result['count']} 次 (都算進合成次數) | 擁有者: {user_name}"
    )
    container = ui.Container(accent_color=discord.Color.teal())
    container.add_item(_card_block(text, sample.get("character_key"), thumbnails, top))
    return container


def build_fusion_preview_container(cards: list[dict], next_rarity: str, next_title: str, user_name: str, thumbnails: dict = None) -> ui.Container:
    """融合確認畫面：三張滿完整度素材 ➔ 高一階 (新卡完整度隨機)"""
    base = cards[0]
    text = (
        f"## 🔮 卡牌融合確認\n"
        f"{base.get('emoji', '🎴')} **{base['name']}**　`[{base['rarity']}]` ➔ `[{next_rarity}]`\n"
        f"**新稱號**：*{next_title}*\n\n"
        f"**消耗素材**\n{_material_lines(cards)}\n\n"
        f"**新卡完整度**：🎲 隨機（與祈願相同）\n\n"
        f"-# ⚠️ 確認後三張素材卡會消失，並產生一張高一階的新卡 | 擁有者: {user_name}"
    )
    container = ui.Container(accent_color=discord.Color.purple())
    container.add_item(_card_block(text, base.get("character_key"), thumbnails, next_rarity))
    return container


def build_fusion_result_container(new_card: dict, old_rarity: str, user_name: str, thumbnails: dict = None) -> ui.Container:
    """融合完成"""
    eval_str, color = get_completeness_eval(new_card["completeness"])
    text = (
        f"## 🔮 融合成功！\n"
        f"三張卡牌的力量產生共鳴，昇華為更高的階級！\n\n"
        f"**角色**：{new_card.get('emoji', '🎴')} **{new_card['name']}**\n"
        f"**階級與稱號**：`[{old_rarity}]` ➔ `[{new_card['rarity']}]` {new_card['title']}\n"
        f"**完整度品相**：{eval_str}\n\n"
        f"-# 卡牌編號: {new_card['instance_id']} | 擁有者: {user_name}"
    )
    container = ui.Container(accent_color=color)
    container.add_item(_card_block(text, new_card.get("character_key"), thumbnails, new_card.get("rarity")))
    return container
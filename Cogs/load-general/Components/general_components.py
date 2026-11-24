import io
import discord
from discord import ui
from PIL import Image
from Database.User_DB_Manager import get_required_exp_for_level
from Database.Item_DB_Manager import CATEGORY_NAMES
from Database.Economy_DB_Manager import TRADE_UNLOCK_DAILY
from Database import title_data
from Database.ura import data as ura_data   # 🌀 排行榜的法具名稱
from Utils.numbers import fmt_money   # 持有金額一萬以上縮寫 (1.5M)


# ---------------------------------------------------------
# 🎨 輔助函式：從 Discord 頭像 URL 提取主色調 (Dominant Color)
# ---------------------------------------------------------
async def get_avatar_dominant_color(user: discord.User | discord.Member) -> discord.Color:
    """下載使用者頭像並擷取出現頻率最高的代表色彩，回傳 discord.Color 物件"""
    try:
        avatar_bytes = await user.display_avatar.with_size(64).read()
        image = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
        quantized = image.quantize(colors=1, method=2)
        palette = quantized.getpalette()[:3]
        return discord.Color.from_rgb(palette[0], palette[1], palette[2])
    except Exception:
        return discord.Color.red()


# ---------------------------------------------------------
# 🔮 運勢對照表
# ---------------------------------------------------------
FORTUNE_MAP = {
    5: {"name": "🌟 大吉 (大顯神威)", "desc": "博麗大神顯靈！靈力極致充沛，萬事亨通！"},
    4: {"name": "🎉 吉 (靈力充沛)", "desc": "守矢神社加護，符卡發動順暢無阻！"},
    3: {"name": "🍡 中吉 (人里平穩)", "desc": "命蓮寺鐘聲祈福，平安無事、順風順水的一天。"},
    2: {"name": "🍵 小吉 (茶柱立起)", "desc": "紅魔館的小憩時刻，平淡中帶有些許小幸運。"},
    1: {"name": "🍃 末吉 (微風拂過)", "desc": "迷途竹林偶爾迷路，但終能找到出口。"},
    0: {"name": "🎎 凶 (厄神降臨)", "desc": "雛大人幫你承受了厄運，今天適合低調行事。"},
}


def get_fortune_info(fortune_level) -> dict:
    """查無對應等級 (含 None) 時，退回中吉"""
    return FORTUNE_MAP.get(fortune_level, FORTUNE_MAP[3])


def _make_notice_text_container(color: discord.Color, text: str, avatar_url: str | None = None) -> ui.Container:
    """標題 + 內文 (可選：右側頭像) 的簡單提示卡"""
    container = ui.Container(accent_color=color)
    if avatar_url:
        container.add_item(ui.Section(ui.TextDisplay(text), accessory=ui.Thumbnail(avatar_url)))
    else:
        container.add_item(ui.TextDisplay(text))
    return container


def build_notice_container(title: str, text: str, color: discord.Color) -> ui.Container:
    """通用提示卡 (例如：私人資料卡無法檢視)"""
    return _make_notice_text_container(color, f"## {title}\n{text}")


# ---------------------------------------------------------
# 🌸 1. 個人資料卡 + 今日簽到 / 運勢 (Components V2)
# ---------------------------------------------------------
def _exp_text_and_bar(level: int, exp: int) -> tuple[str, str]:
    """經驗值文字與 10 段進度條"""
    if level >= 1000:
        return f"`{exp:,}` / `MAX` EXP (🌟 **FULL POWER**)", f"`[{'🟥' * 10}]`"

    req_exp = get_required_exp_for_level(level)
    percentage = min(max(exp / req_exp, 0.0), 1.0)
    filled = int(round(percentage * 10))
    bar = "🟥" * filled + "⬜" * (10 - filled)
    return f"`{exp:,}` / `{req_exp:,}` EXP *(還差 `{req_exp - exp:,}` EXP)*", f"`[{bar}]`"


def _daily_section_text(daily_status: dict, is_self: bool, reward: dict | None) -> str:
    """今日簽到狀態 + 運勢；reward 只在剛簽到完的那張卡片上顯示"""
    if daily_status.get("signed_today"):
        fortune = get_fortune_info(daily_status.get("fortune_level"))
        text = (
            f"### 🔮 今日運勢　✅ 今日已簽到\n"
            f"**{fortune['name']}**\n"
            f"*{fortune['desc']}*"
        )
        if reward:
            text += f"\n\n🎉 **簽到成功！**　💰 `+{reward['money_gained']:,}` 兩　✨ `+{reward['exp_gained']:,}` EXP"
            for item in reward.get("items") or ([reward["item"]] if reward.get("item") else []):
                text += f"　{item['emoji']} {item['name']} `×{item['amount']}`"
    else:
        hint = ("向博麗神社投賽錢，抽取今日運勢並獲得賽錢與經驗值吧！" if is_self
                else "這位居民今天還沒有向博麗神社投賽錢。")
        text = f"### 🔮 今日運勢　⌛ 尚未簽到\n{hint}"

    return text + "\n-# 每日 00:00 重置簽到與運勢"


def _format_duration(seconds: int) -> str:
    hours, rest = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} 小時 {minutes} 分"
    return f"{minutes} 分 {secs} 秒"


def _stamina_text(stamina: dict | None) -> str:
    """資料卡上的體力那一行 (含換行)；stamina 為 None 時不顯示"""
    if stamina is None:
        return ""
    head = f"⚡ **體力**　`{stamina['stamina']} / {stamina['max']}`"
    if stamina["stamina"] > stamina["max"]:
        return f"{head}　✨ 超過上限（用掉到 {stamina['max']} 以下才會開始自然回復）\n"
    if stamina["stamina"] >= stamina["max"]:
        return f"{head}　✅ 已回滿\n"
    return f"{head}　-# 下次 +1：{_format_duration(stamina['next_in'])} · 回滿：{_format_duration(stamina['full_in'])}\n"


def _daily_count_text(count: int) -> str:
    """累積簽到天數；滿 TRADE_UNLOCK_DAILY 天開通市場與轉帳"""
    need = TRADE_UNLOCK_DAILY
    if count >= need:
        return f"📅 **累積簽到**　`{count}` 天　🔓 已開通市場與轉帳"
    return f"📅 **累積簽到**　`{count} / {need}` 天\n-# 再簽到 {need - count} 天就能使用市場與轉帳"


def build_profile_container(
    user: discord.User | discord.Member,
    user_data: dict,
    daily_status: dict,
    title_id: str | None = None,
    is_self: bool = False,
    reward: dict | None = None,
    daily_button: ui.Button | None = None,
    stamina: dict | None = None,
    namecard_url: str | None = None,
    namecard_caption: str | None = None,
    title_stats: dict | None = None,
) -> ui.Container:
    """
    個人資料卡：頭像標題 (+ 稱號與說明) / 賽錢・P點・體力・背包 / 經驗值進度條 / 今日簽到與運勢 / (角色名片)。
    title_id = 戴著的稱號 (title_data.TITLES)；色條 = 稱號等級色，沒戴 = 固定色 (公開、私人一樣，2026-11-13 使用者)。
    daily_button 不為 None 時，會放在「今日運勢」區塊的右側 (只有本人的卡片才會有)。
    stamina = calc_stamina() 的結果；None 時不顯示體力。
    namecard_url = 戴著的角色名片圖片網址 (Utils.namecards.namecard_url)；有的話放在今日運勢下面 (0.35.038 從最上面移下來)，None = 不放圖。
    namecard_caption = 名片圖下面那行字 (Database.namecard_data.namecard_caption)，有圖才顯示。
    title_stats = 玩家統計 (稱號說明裡有 {n} 的換成目前的累計數字，例如神社稱號)。
    """
    money = user_data.get("money", 1000)
    current_level = user_data.get("level", 0)  # level 0~1000 (對應 0.0 P ~ 100.0 P)
    exp = user_data.get("exp", 0)
    inventory = user_data.get("inventory", {})
    is_public = bool(user_data.get("is_public", 1))

    p_power = current_level / 10.0
    total_items = sum(inventory.values()) if isinstance(inventory, dict) else 0
    exp_text, exp_bar = _exp_text_and_bar(current_level, exp)
    title = title_data.TITLES.get(title_id)
    container = ui.Container(accent_color=discord.Color(title_data.title_color(title_id)))

    title_text = f"**{title_data.title_label(title_id)}**\n-# *{title_data.title_desc(title_id, title_stats)}*\n" if title else ""
    container.add_item(ui.Section(
        ui.TextDisplay(
            f"## 🌸 {user.display_name} 的幻想鄉通行證\n"
            f"{title_text}"
            f"-# {'🌐 公開' if is_public else '🔒 私人'}資料卡 • TouHouBot Profile System • 幻想鄉居民登記"
        ),
        accessory=ui.Thumbnail(user.display_avatar.with_size(128).url),
    ))
    container.add_item(ui.Separator())

    container.add_item(ui.TextDisplay(
        f"💰 **賽錢**　`{fmt_money(money)}` 兩\n"
        f"🔴 **P點**　`{p_power:.1f}` P\n"
        f"{_stamina_text(stamina)}"
        f"⛩️ **神社倉庫**　`{total_items}` 件道具\n"
        f"{_daily_count_text(user_data.get('daily_count') or 0)}\n\n"
        f"✨ **經驗值 (EXP)**\n{exp_text}\n{exp_bar}"
    ))
    container.add_item(ui.Separator())

    daily_text = _daily_section_text(daily_status, is_self, reward)
    if daily_button is not None:
        container.add_item(ui.Section(ui.TextDisplay(daily_text), accessory=daily_button))
    else:
        container.add_item(ui.TextDisplay(daily_text))

    if namecard_url:   # 🖼️ 角色名片 (19:9 橫幅)：0.35.038 使用者要求從最上面移到下面 (本人的按鈕還在它下面)
        container.add_item(ui.Separator())
        container.add_item(ui.MediaGallery(discord.MediaGalleryItem(namecard_url)))
        if namecard_caption:   # 名片名稱｜說明 (2026-11-14 使用者要求)
            container.add_item(ui.TextDisplay(namecard_caption))
    return container


# ---------------------------------------------------------
# ⌛ 2. 重複簽到提示 (Components V2)
# ---------------------------------------------------------
def build_daily_repeat_container(user: discord.User | discord.Member, fortune_level) -> ui.Container:
    fortune = get_fortune_info(fortune_level)
    return _make_notice_text_container(
        discord.Color.dark_orange(),
        f"## ⌛ 今天已經投過賽錢囉！\n"
        f"**{user.display_name}**，你今天已經向博麗神社投過賽錢了。\n"
        f"請等待明日 **00:00** 刷新後再來吧！\n\n"
        f"### 🔮 你今天的運勢是\n"
        f"**{fortune['name']}**\n"
        f"*{fortune['desc']}*\n"
        f"-# TouHouBot Daily System • 每日簽到限制 1 次",
        user.display_avatar.with_size(128).url,
    )


# ---------------------------------------------------------
# 💥 3. POWER UP 升級特效 (Components V2)
# ---------------------------------------------------------
def build_power_up_container(user: discord.User | discord.Member, result: dict) -> ui.Container:
    footer = ("🌟 警告：火力已達最大上限 (FULL POWER!)" if result.get("is_max")
              else "TouHouBot Power System • 繼續集滿 P 點以提升火力！")
    return _make_notice_text_container(
        discord.Color.gold(),
        f"## 💥 POWER UP! 火力提升！\n"
        f"🎉 恭喜 **{user.display_name}** 彈幕火力獲得突破！\n\n"
        f"🔴 **彈幕火力 (Power)**\n"
        f"`{result['old_p']:.1f} P` ➔ **`{result['new_p']:.1f} P`**\n"
        f"-# {footer}",
        user.display_avatar.with_size(128).url,
    )


# ---------------------------------------------------------
# 🎒 4. 背包 (Components V2：Container + Section + 分頁)
# ---------------------------------------------------------
# 需要 discord.py >= 2.6。每頁道具數；V2 每則訊息最多 40 個元件，
# 目前整個背包畫面只用到約 13 個，所以這個數字可以放心調大。
ITEMS_PER_PAGE = 10

# 「全部道具」時的排序：依分類分組，同分類內再依道具 ID A-Z
CATEGORY_ORDER = {"consumable": 0, "cuisine": 1, "collectible": 2, "special": 3, "material": 4}
SERVE_LABELS = {"food": "🍚 食物", "drink": "🍵 茶水", "dessert": "🍮 點心"}


def item_effect_tag(info: dict) -> str:
    """道具效果的小標籤：體力道具「⚡ 體力 +120」、招待料理「🍽️ 招待用 · 🍚 食物」"""
    effect = info.get("effect") or {}
    if effect.get("stamina"):
        return f"⚡ 體力 +{effect['stamina']}"
    if effect.get("serve"):
        return f"🍽️ 招待用 · {SERVE_LABELS.get(effect['serve'], effect['serve'])}"
    return ""
UNKNOWN_ITEM = {"name": "未知道具", "emoji": "❓", "category": "special", "desc": "未知的物品。"}


def get_inventory_view_data(inventory: dict, item_templates: dict, category: str, page: int) -> dict:
    """
    一次算好背包畫面需要的所有資料 (篩選、排序、分頁、各分類數量)，
    避免 View 為了取得總頁數而重複計算兩次。
    """
    entries = []                                   # [(item_id, amount, info), ...]
    category_counts = {"all": 0, "consumable": 0, "cuisine": 0, "collectible": 0, "special": 0, "material": 0}

    for item_id, amount in inventory.items():
        if not isinstance(amount, int) or amount <= 0:
            continue
        info = item_templates.get(item_id, UNKNOWN_ITEM)
        cat = info.get("category", "special")
        category_counts["all"] += 1
        if cat in category_counts:
            category_counts[cat] += 1
        if category == "all" or cat == category:
            entries.append((item_id, amount, info))

    entries.sort(key=lambda e: (CATEGORY_ORDER.get(e[2].get("category"), 99), e[0]))

    total_pages = max(1, (len(entries) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * ITEMS_PER_PAGE

    return {
        "items": entries[start:start + ITEMS_PER_PAGE],
        "page": page,
        "total_pages": total_pages,
        "kinds": len(entries),                      # 目前分類的道具種類數
        "total_amount": sum(e[1] for e in entries), # 目前分類的道具總件數
        "category_counts": category_counts,         # 各分類種類數 (給選單顯示)
    }


def build_inventory_container(
    user: discord.User | discord.Member,
    data: dict,
    category: str,
    accent_color: discord.Color,
) -> ui.Container:
    """繪製背包：標題區(右側頭像) + 分隔線 + 當頁道具清單 (含道具說明)"""
    cat_name = CATEGORY_NAMES.get(category, "🎒 道具")

    header = ui.Section(
        ui.TextDisplay(
            f"## {cat_name} - {user.display_name} 的神社倉庫\n"
            f"共 `{data['kinds']}` 種道具 · 合計 `{data['total_amount']:,}` 件\n"
            f"-# 第 {data['page']} / {data['total_pages']} 頁 • 幻想鄉居民登記"
        ),
        accessory=ui.Thumbnail(user.display_avatar.with_size(128).url),
    )

    container = ui.Container(accent_color=accent_color)
    container.add_item(header)
    container.add_item(ui.Separator())

    if not data["items"]:
        container.add_item(ui.TextDisplay("🍵 目前該分類空空如也...\n快去參與活動或投賽錢獲得道具吧！"))
        return container

    lines = []
    for _item_id, amount, info in data["items"]:
        line = f"{info.get('emoji', '❓')} **{info.get('name', '未知道具')}** ×`{amount:,}`"
        tag = item_effect_tag(info)
        if tag:
            line += f"　{tag}"
        desc = info.get("desc")
        if desc:
            line += f"\n-# {desc}"
        lines.append(line)

    container.add_item(ui.TextDisplay("\n\n".join(lines)))
    return container


# ---------------------------------------------------------
# 🏆 排行榜 (Components V2)
# ---------------------------------------------------------
# 排行項目：key ➔ (顯示名稱, 統計欄位, 數值格式)
# 🌀 裏世界兩項 (0.35.086) 的欄位由 leaderboard.py 從 ura_records 補上 (只有成功撤離過的玩家上榜)
LEADERBOARD_TYPES = {
    "money":     ("💰 賽錢",       "money",         lambda v: f"{fmt_money(v)} 兩"),
    "assets":    ("💎 資產總值",   "assets",        lambda v: f"{v:,} 兩"),
    "level":     ("🔴 P點",        "level",         lambda v: f"{v / 10:.1f} P"),
    "chars":     ("📚 收集角色",   "char_count",    lambda v: f"{v} 位"),
    "kinds":     ("🃏 收集卡種",   "kind_count",    lambda v: f"{v} 種"),
    "cards":     ("🎴 卡牌總數",   "card_count",    lambda v: f"{v:,} 張"),
    "draws":     ("🎰 祈願次數",   "total_draws",   lambda v: f"{v:,} 抽"),
    "fusions":   ("🔮 融合次數",   "total_fusions", lambda v: f"{v:,} 次"),
    "ura_money": ("💰 裏世界・帶出最多錢", "ura_money", lambda v: f"{fmt_money(v)} 兩"),
    "ura_depth": ("🕳️ 裏世界・最深入", "ura_depth",  lambda v: f"第 {v} 關"),
}
URA_TYPES = {"ura_money", "ura_depth"}
PER_PAGE = 10       # 一頁幾名 (使用者 2026-11-20：裏世界兩項 5 名，其他 10 名)
URA_PER_PAGE = 5
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def leaderboard_per_page(type_key: str) -> int:
    return URA_PER_PAGE if type_key in URA_TYPES else PER_PAGE


def _ura_relic_name(rel: dict) -> str:
    rd = ura_data.relics().get(rel.get("rid"), {})
    return f"{rd.get('emoji', '🦊')} {rd.get('name', rel.get('rid', '?'))}"


def leaderboard_entry(type_key: str, rank: int, row: dict, viewer_id: int) -> str:
    """
    一位玩家一塊 (條列式，docs/gameplay/ura.md「排行榜」)：
      🥇 名字 · [SR] 稱號
      (裏世界兩項) 角色：[SR] 琪露諾 💀 / [N] 大妖精　法具：🦊 九尾式神
      項目：數字
    私人資料卡的玩家計入名次，但名字、稱號、角色、法具都不顯示；
    本人也一樣 (0.36.002，使用者定：排行榜是公開訊息)，不標「⬅️ 你」，名次寫在最下面那行
    """
    title, field, fmt = LEADERBOARD_TYPES[type_key]
    shown = bool(row["is_public"])
    head = f"{MEDALS.get(rank, f'`#{rank}`')} **{row['member'].display_name if shown else '🔒 私人玩家'}**"
    if shown and row.get("title") in title_data.TITLES:
        head += f" · {title_data.title_label(row['title'])}"
    if shown and row["user_id"] == viewer_id:
        head += "　⬅️ 你"
    lines = [head]
    if type_key in URA_TYPES:
        rec = row["ura"]
        if shown:
            party = " / ".join(f"[{p.get('rarity', '?')}] {p.get('name', '?')}" + ("" if p.get("alive", True) else " 💀")
                               for p in rec.get("party", []))
            lines.append(f"角色：{party or '—'}")
            if rec.get("relics"):
                lines.append("法具：" + " / ".join(_ura_relic_name(r) for r in rec["relics"]))
        money = f"賽錢：{fmt_money(rec.get('net', 0))} 兩"
        depth = f"探索深度：第 {rec['floor']} 關" if rec.get("floor") is not None else "探索深度：—"
        lines += [money, depth] if type_key == "ura_money" else [depth, money]
    else:
        lines.append(f"{title.split(' ', 1)[1]}：{fmt(row[field])}")
    return "\n".join(lines)


def build_leaderboard_container(guild: discord.Guild, type_key: str, rows: list[dict], page, viewer_id: int) -> ui.Container:
    """
    rows 已依該項目由高到低排序 (同分：裏世界兩項先達成的在前)，每筆含 "member"，這一頁的再含 "title" (戴著的稱號 id)
    page = Utils.pagination.paginate() 切好的這一頁
    """
    title, field, fmt = LEADERBOARD_TYPES[type_key]
    ura = type_key in URA_TYPES
    container = ui.Container(accent_color=discord.Color.dark_purple() if ura else discord.Color.gold())
    who = f"成功撤離過的 {len(rows)} 位" if ura else f"有遊玩紀錄的 {len(rows)} 位居民"
    container.add_item(ui.TextDisplay(
        f"## 🏆 {guild.name} 排行榜：{title}\n"
        f"-# 只比較本伺服器中{who} · 私人資料卡的玩家不顯示名字"
        + ("\n-# 💰 算的是淨賺 (帶出 − 帶進)；🕳️ 只算成功撤離的局" if ura else "")
    ))
    container.add_item(ui.Separator())
    if page.items:
        blocks = [leaderboard_entry(type_key, page.start + i + 1, row, viewer_id) for i, row in enumerate(page.items)]
        container.add_item(ui.TextDisplay("\n\n".join(blocks)))
    elif ura:
        container.add_item(ui.TextDisplay("*（這個伺服器還沒有人從裏世界成功撤離）*"))
    else:
        container.add_item(ui.TextDisplay("*（這個伺服器還沒有人留下遊玩紀錄）*"))

    my_rank = next((i for i, row in enumerate(rows, start=1) if row["user_id"] == viewer_id), None)
    container.add_item(ui.Separator())
    if my_rank is None:
        container.add_item(ui.TextDisplay("-# 你還沒有成功撤離過，用 `/ura explore` 出發吧！" if ura
                                          else "-# 你還沒有遊玩紀錄，快去 `/daily` 或 `/card gacha` 吧！"))
    elif not rows[my_rank - 1]["is_public"]:   # 私人資料卡：榜上看不出是你，一律寫在這裡
        container.add_item(ui.TextDisplay(f"-# 📍 你目前是第 {my_rank} 名 ({fmt(rows[my_rank - 1][field])})"
                                          "・你的資料卡是私人的，榜上顯示成「🔒 私人玩家」"))
    elif not page.start < my_rank <= page.start + len(page.items):
        container.add_item(ui.TextDisplay(f"-# 📍 你目前是第 {my_rank} 名 ({fmt(rows[my_rank - 1][field])})"))
    return container


def build_namecard_dm_view(character_name: str, file: discord.File, full: bool = False) -> ui.LayoutView:
    """📥 名片原圖的私訊：說明文字 + 附件 (V2 的附件要用 ui.File 放進畫面才會顯示)"""
    container = ui.Container(accent_color=discord.Color.from_rgb(233, 30, 99))
    kind = "原檔" if full else "原圖 (高畫質 JPG)"
    container.add_item(ui.TextDisplay(f"## 🖼️ {character_name}的角色名片\n這是你的名片{kind}，可以下載保存。"))
    container.add_item(ui.File(media=f"attachment://{file.filename}"))
    container.add_item(ui.TextDisplay("-# 僅供個人收藏，請勿轉載"))
    view = ui.LayoutView()
    view.add_item(container)
    return view

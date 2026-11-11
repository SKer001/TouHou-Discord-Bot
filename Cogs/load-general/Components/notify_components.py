"""
🔔 主動通知的畫面 (Components V2)：/notify 設定面板、私訊內容；只負責畫面，不碰資料庫
"""
import discord
from discord import ui

from Database.notify_data import NOTIFY_TYPES

DM_MAX_NOTICES = 12      # 一則私訊最多列幾則 (其餘併成「還有 N 則」，避免超過 40 個元件)


def _ts(dt, style: str = "R") -> str:
    return f"<t:{int(dt.timestamp())}:{style}>"


def notice_text(notice: dict) -> str:
    """一則通知的文字 (依種類)"""
    kind, d = notice["kind"], notice["data"]
    info = NOTIFY_TYPES.get(kind, {"name": kind, "emoji": "🔔"})
    head = f"### {info['emoji']} {info['name']}\n"
    if kind == "shrine_box_full":
        body = f"賽錢箱存滿了 `{d['box']:,} / {d['box_max']:,}`，不回收就不會再累積。\n用 `/shrine collect` 回收。"
    elif kind == "guest_leaving":
        body = (f"{d['emoji']} **{d['name']}** 心情剩 `{d['mood']}%`，{_ts(d['leave_at'])} 就要離開了。\n"
                f"用 `/shrine manage` 招待客人。")
    elif kind == "youkai_max":
        body = f"神社的妖怪滿 `{d['youkai']}` 隻了，效率 −{d['penalty']:.0%}。\n用 `/shrine manage` 治退妖怪。"
    elif kind == "stamina_full":
        body = f"體力回滿了 `{d['stamina']} / {d['max']}`，再放著就浪費了。\n可以用 `/shrine explore` 去採集。"
    elif kind == "market_sold":
        body = (f"{d['emoji']} **{d['name']}** [{d['rarity']}] 以 `{d['price']:,}` 賽錢賣出了，"
                f"賽錢已經入帳。")
    elif kind == "market_expired":
        body = (f"{d['emoji']} **{d['name']}** [{d['rarity']}] 上架 7 天沒有賣出，已經退回你的卡冊。\n"
                f"可以用 `/market sell` 重新上架。")
    elif kind == "event_start":
        body = f"{d['emoji']} **{d['name']}** 開始了！限定地點、料理與客人登場。\n用 `/event` 看活動內容。"
    elif kind == "event_end":
        body = f"{d['emoji']} **{d['name']}** 結束了，活動道具已經清除。\n感謝參與！"
    else:
        body = info.get("desc", "")
    return head + body


def build_notice_dm(notices: list[dict]) -> ui.Container:
    """背景通知的私訊 (同一位玩家這一輪的通知併成一則)"""
    container = ui.Container(accent_color=discord.Color.gold())
    container.add_item(ui.TextDisplay("## 🔔 博麗神社的通知"))
    shown = notices[:DM_MAX_NOTICES]
    for n in shown:
        container.add_item(ui.TextDisplay(notice_text(n)))
    if len(notices) > len(shown):
        container.add_item(ui.TextDisplay(f"-# …還有 {len(notices) - len(shown)} 則通知"))
    container.add_item(ui.Separator())
    container.add_item(ui.TextDisplay("-# 可以用 `/notify` 關掉這類通知"))
    return container


def build_notify_settings(settings: dict, buttons: dict, result: str | None = None) -> ui.Container:
    """
    /notify 設定面板：每種通知一行 (Section + 右側開關按鈕)
    settings = {種類: 開啟?}；buttons = {種類: ui.Button} (由 View 建好、綁好 callback)
    """
    container = ui.Container(accent_color=discord.Color.gold())
    on = sum(settings.values())
    dm_kinds = sum(1 for i in NOTIFY_TYPES.values() if i["dm"])
    text = f"## 🔔 通知設定\n機器人會在這些事情發生時私訊你。目前開啟 `{on} / {dm_kinds}` 種。"
    if result:
        text = f"{result}\n" + text
    container.add_item(ui.TextDisplay(text))
    container.add_item(ui.Separator())
    for kind, info in NOTIFY_TYPES.items():
        line = f"**{info['emoji']} {info['name']}**\n-# {info['desc']}"
        container.add_item(ui.Section(ui.TextDisplay(line), accessory=buttons[kind]))
    container.add_item(ui.Separator())
    container.add_item(ui.TextDisplay("-# 私訊要能收到，伺服器的「私人訊息」設定要開著。"))
    return container

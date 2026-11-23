"""
📚 教學書的畫面 (0.36.000，使用者 2026-11-22 定案)：每個 /help 分類一本，玩法和指令合在一起、分章節
- 內容：`Components/guide/<分類 key>.py` 的 `BOOK` (一本書一個檔案)，格式：
    BOOK = {
        "intro": "目錄頁的一兩句簡介",
        "chapters": [
            {"title": "⚗️ 合成與融合", "short": "目錄與跳章選單的一句話 (≤ 90 字)",
             "body": "玩法說明 (Markdown) 或回傳字串的函式 (數字從程式常數讀，開畫面時才算)；
                      函式可以收一個參數 ctx = current_context() 的結果 (現在進行中的活動)，見下面",
             "commands": ["card synthesis", "card fusion"]},   # 這章用到的指令 (qualified name)；沒有就 []
            ...
        ],
    }
- 每本書最後自動多一章「📋 指令速查」= 這個分類的全部指令 (不用寫在 BOOK 裡)
- 標題、色條、代表卡面沿用 help_components.CATEGORIES；指令說明與參數從 bot.tree 即時讀
- 目錄頁：簡介 + 章節列表 + 每章一顆按鈕 (一排 3 顆)；章節頁：玩法 ➔ 這章用到的指令 ➔ 翻頁按鈕 + 跳章選單
  (按鈕和選單由 help.py 的 GuideView 做好傳進來，放在框裡)
- 🎪 不要把某個活動寫死成例子 (0.37.005，使用者：「萬一今天活動不是紅魔鄉呢」)：開書時讀一次 current_context()
  = {"active": [進行中的活動檔], "rules": 當下規則 (game_rules)}，body(ctx) 用它寫「現在」的內容；
  ctx 是 None (測試、讀不到資料庫) 時只寫通用說明
"""
import importlib
import inspect

import discord
from discord import ui

BOOK_KEYS = ["card", "profile", "shrine", "ura", "event", "market"]   # 有教學書的分類 (順序 = /help 總覽的順序)
QUICKREF = {"title": "📋 指令速查", "short": "這個模式的全部指令和參數一次列出來，給老玩家查", "commands": None}
CHAPTER_BUTTONS_PER_ROW = 3


def help_components():
    return importlib.import_module("Cogs.load-general.Components.help_components")


def load_book(key: str) -> dict | None:
    """BOOK 字典；這個分類沒有教學書 (或檔案還沒寫、寫壞了) 回傳 None，壞檔印警告 (測試會抓出來)"""
    if key not in BOOK_KEYS:
        return None
    name = f"Cogs.load-general.Components.guide.{key}"
    try:
        return importlib.import_module(name).BOOK
    except ModuleNotFoundError as e:
        if e.name != name:
            print(f"⚠️ [Guide] 讀取教學書 {key} 失敗：{e!r}")
        return None
    except Exception as e:   # 書寫壞了不要讓 /help 整個打不開
        print(f"⚠️ [Guide] 讀取教學書 {key} 失敗：{e!r}")
        return None


def chapters(book: dict) -> list[dict]:
    """書裡的章 + 最後的「📋 指令速查」"""
    return [*book["chapters"], QUICKREF]


async def current_context() -> dict | None:
    """開書時讀一次：進行中的活動 + 當下規則；讀不到就 None (書照樣能看，只是不寫現在的活動)"""
    try:
        econ = importlib.import_module("Database.Economy_DB_Manager")
        events = importlib.import_module("Database.events")
        active = [o["event"] for o in await econ.get_events_overview() if o["status"] == "active"]
        return {"active": active, "rules": events.game_rules(active)}
    except Exception as e:
        print(f"⚠️ [Guide] 讀取進行中的活動失敗：{e!r}")
        return None


def _takes_ctx(fn) -> bool:
    try:
        return len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        return False


def body_text(chapter: dict, ctx: dict | None = None) -> str:
    body = chapter.get("body", "")
    if callable(body):
        body = body(ctx) if _takes_ctx(body) else body()
    return body.strip()


def safe_body_text(chapter: dict, ctx: dict | None = None) -> str:
    """畫面用：從程式讀數字的函式壞掉時，這章顯示一句提示就好，不要整頁打不開 (測試用 body_text 會抓出來)"""
    try:
        return body_text(chapter, ctx)
    except Exception as e:
        print(f"⚠️ [Guide] 教學書「{chapter.get('title')}」這章產生失敗：{e!r}")
        return "⚠️ 這章暫時打不開，請通知管理員。下面的指令說明還是可以看。"


def chapter_commands(chapter: dict, cmds: list) -> list:
    """這章要列的指令物件 (照 BOOK 寫的順序)；指令速查 = 分類的全部指令"""
    if chapter.get("commands") is None:
        return list(cmds)
    by_name = {c.qualified_name: c for c in cmds}
    return [by_name[n] for n in chapter["commands"] if n in by_name]


def _head(key: str, thumbnails: dict | None, text: str) -> ui.Item:
    hc = help_components()
    info = hc.category_info(key)
    url = hc.thumbnail_url(info["thumb"][0], thumbnails, info["thumb"][1]) if info["thumb"] else None
    return ui.Section(ui.TextDisplay(text), accessory=ui.Thumbnail(url)) if url else ui.TextDisplay(text)


def build_cover_container(key: str, book: dict, thumbnails: dict | None, chapter_rows: list, bottom_row) -> ui.Container:
    """📚 目錄頁：書名 (+ 代表卡面) ➔ 簡介 ➔ 章節列表 ➔ 每章一顆按鈕 ➔ 回總覽"""
    info = help_components().category_info(key)
    c = ui.Container(accent_color=info["color"])
    c.add_item(_head(key, thumbnails, f"## 📚 {info['title']}・教學書\n{book['intro']}"))
    c.add_item(ui.Separator())
    lines = [f"**第 {i} 章　{ch['title']}**\n-# {ch['short']}" for i, ch in enumerate(chapters(book), 1)]
    c.add_item(ui.TextDisplay("### 📖 目錄\n" + "\n".join(lines)))
    for row in chapter_rows:
        c.add_item(row)
    c.add_item(ui.Separator())
    c.add_item(bottom_row)
    return c


def build_chapter_container(key: str, book: dict, index: int, cmds: list, rows: list, ctx: dict | None = None) -> ui.Container:
    """📖 章節頁 (index 從 1 開始)：第幾章 ➔ 玩法 ➔ 這章用到的指令 ➔ 翻頁按鈕 + 跳章選單"""
    hc = help_components()
    info = hc.category_info(key)
    chs = chapters(book)
    ch = chs[index - 1]
    c = ui.Container(accent_color=info["color"])
    c.add_item(ui.TextDisplay(f"-# 📚 {info['title']}・教學書 · 第 {index} / {len(chs)} 章\n## {ch['title']}"))
    body = safe_body_text(ch, ctx) if ch is not QUICKREF else "這個模式的全部指令。想知道怎麼玩，按「📚 目錄」翻到對應的章節。"
    if body:
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(body))
    shown = chapter_commands(ch, cmds)
    if shown:
        c.add_item(ui.Separator())
        title = "### 📋 全部指令" if ch is QUICKREF else "### 📋 這章用到的指令"
        c.add_item(ui.TextDisplay(title + "\n" + "\n".join(hc.command_line(cmd) for cmd in shown)))
        c.add_item(ui.TextDisplay("-# `[ ]` 是可以不填的參數"))
    c.add_item(ui.Separator())
    for row in rows:
        c.add_item(row)
    return c

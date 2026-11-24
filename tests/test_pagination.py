"""📄 共用分頁 Utils/pagination.py (不連 Discord)：切頁、翻頁 (停在頭尾 / 頭尾相接)、各樣式的按鈕、跳頁彈窗"""
import asyncio, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
os.environ.setdefault("SHOW_UNRELEASED", "1")   # 🙈 測試預設看得到未公開卡池 (Utils/config.py)
from Utils.pagination import PageJumpModal, nav_buttons, page_count, paginate, step

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)


class FakeResponse:
    def __init__(self): self.modal = None
    async def send_modal(self, modal): self.modal = modal
    def is_done(self): return False
    async def send_message(self, *a, **k): self.sent = (a, k)


class FakeInteraction:
    def __init__(self): self.response = FakeResponse()


async def main():
    # --- 切頁 ---
    check("count", page_count(0, 10) == 1 and page_count(10, 10) == 1 and page_count(11, 10) == 2)
    pg = paginate(list(range(25)), 9, 10)
    check("clamp high", pg.page == 3 and pg.total == 3 and pg.start == 20 and pg.items == [20, 21, 22, 23, 24])
    pg = paginate([], 0, 10)
    check("empty", pg.page == 1 and pg.total == 1 and pg.items == [] and pg.start == 0)

    # --- 翻頁 ---
    check("clamp step", step(1, -1, 3) == 1 and step(3, 1, 3) == 3 and step(2, 1, 3) == 3)
    check("wrap step", step(1, -1, 3, wrap=True) == 3 and step(3, 1, 3, wrap=True) == 1 and step(1, 1, 1, wrap=True) == 1)

    changed = []
    async def on_change(interaction, page): changed.append(page)

    # default：到頭到尾反灰
    prev, label, nxt = nav_buttons(1, 3, on_change)
    check("default labels", (prev.label, label.label, nxt.label) == ("◀️ 上一頁", "📄 1 / 3 頁", "下一頁 ▶️"))
    check("default disabled", prev.disabled and label.disabled and not nxt.disabled)
    await nxt.callback(FakeInteraction()); await prev.callback(FakeInteraction())
    check("default callbacks", changed == [2, 1])

    # compact：頭尾相接、只有一頁時反灰
    changed.clear()
    prev, label, nxt = nav_buttons(1, 3, on_change, "compact")
    check("compact labels", (prev.label, label.label, nxt.label) == ("◀️", "1 / 3", "▶️") and not prev.disabled)
    await prev.callback(FakeInteraction())
    check("compact wrap", changed == [3])
    check("compact single", all(b.disabled for b in nav_buttons(1, 1, on_change, "compact")))

    # simple：沒有頁碼
    btns = nav_buttons(2, 2, on_change, "simple")
    check("simple", [b.label for b in btns] == ["◀ 上一頁", "下一頁 ▶"] and btns[1].disabled and not btns[0].disabled)

    # jump：頁碼可以按 ➔ 跳頁彈窗
    changed.clear()
    prev, label, nxt = nav_buttons(3, 3, on_change, "jump", jump_title="跳轉倉庫頁面")
    check("jump labels", label.label == " 3 / 3 " and not label.disabled and not nxt.disabled)
    await nxt.callback(FakeInteraction())
    check("jump wrap", changed == [1])
    it = FakeInteraction()
    await label.callback(it)
    modal = it.response.modal
    check("jump modal", isinstance(modal, PageJumpModal) and modal.title == "跳轉倉庫頁面")
    modal.page_input._value = "2"
    await modal.on_submit(FakeInteraction())
    check("jump submit", changed == [1, 2])
    modal.page_input._value = "abc"
    bad = FakeInteraction()
    await modal.on_submit(bad)
    check("jump bad input", changed == [1, 2] and hasattr(bad.response, "sent"))

    print(f"passed {ok}, failed {fail}")
    return fail


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)

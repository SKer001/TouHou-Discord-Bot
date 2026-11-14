"""
🖼️ 角色名片的名稱與說明 (純資料，不碰資料庫)

- 名片畫的是「角色平常看不到的另一面」的反差日常 (2026-11-14 使用者決定)
- 每張名片：name 名片名稱、desc 說明 (2026-11-14 使用者要求「每個名片都要有 desc」)
- 顯示：/profile 名片圖下面一行灰色小字「🖼️ 名稱｜說明」；更換名片選單的選項說明
- 新增：名片定案時在 NAMECARDS 加一筆，鍵 = 角色 id (跟 images/Namecards.json 一樣)
"""

NAMECARDS = {
    "reimu": {"name": "夏日午睡",
              "desc": "總說要好好守護神社的巫女，在蟬聲和西瓜的香味裡不知不覺睡著了。今天的賽錢箱，大概也是空的吧。"},
    "marisa": {"name": "深夜的魔法研究",
               "desc": "嘴上說天才不用努力，其實每晚都在魔法店裡讀書讀到天亮。這件事，可別跟靈夢說喔。"},
    "mima": {"name": "月夜屋頂的惡靈",
             "desc": "傳說中的大惡靈，夜裡常飄到神社屋頂看星星，然後就這樣睡著了。新月杖還在旁邊發著光，替她守夜。"},
    "genji": {"name": "池邊的日光浴",
              "desc": "活了上千年的老烏龜，最大的興趣是曬太陽打盹。麻雀把他的殼當成午睡的老位子，他也懶得趕。"},
}


def namecard_info(character_key: str | None) -> dict | None:
    """那張名片的 {"name", "desc"}；還沒寫就回傳 None"""
    return NAMECARDS.get(character_key) if character_key else None


def namecard_caption(character_key: str | None) -> str | None:
    """資料卡名片圖下面那行字；沒資料回傳 None"""
    info = namecard_info(character_key)
    return f"-# 🖼️ **{info['name']}**｜{info['desc']}" if info else None

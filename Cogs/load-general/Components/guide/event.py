"""
📚 🎪 活動・教學書 (0.36.000)
格式見 Components/guide_components.py；數字從活動檔 (Events/*.json，Database/events.load_events) 讀，開畫面時才算
"""
import importlib


def _events() -> list[dict]:
    return list(importlib.import_module("Database.events").load_events().values())


def _example() -> dict | None:
    evs = _events()
    return evs[0] if evs else None


def _about() -> str:
    ev = _example()
    lines = [
        "幻想鄉發生**異變**的時候就會開活動。活動期間，平常的玩法裡會多出限定內容，活動結束就恢復原狀。",
        "",
        "### 🎁 活動期間會多出什麼",
        "- 🗺️ **限定採集地點**：在 `/shrine explore` 的地點清單裡，標「活動限定」，採得到活動素材",
        "- 🍳 **活動料理**：用活動素材做的限定料理，客人點餐時有機會點到",
        "- 🙏 **限定客人**：只在活動期間來神社參拜的客人",
        "- 🌀 **裏世界的活動關卡**：選門時會出現標 🎪 的門，有活動限定的敵人、BOSS 和寶物 (詳見🌀 裏世界教學書)",
        "",
        "### ✨ 活動料理加成",
        "招待客人時端上活動料理，**每一份**都會讓這次的報酬再乘上活動加成；端越多份乘越多次。",
    ]
    if ev:
        loc = ev.get("location") or {}
        parts = []
        if loc:
            parts.append(f"限定地點 {loc.get('emoji', '')} {loc.get('name', '')}")
        if ev.get("recipes"):
            parts.append(f"{len(ev['recipes'])} 道活動料理")
        if ev.get("guests"):
            parts.append(f"{len(ev['guests'])} 種限定客人")
        parts.append(f"活動料理每份 ×{ev.get('event_dish_bonus', 1.0):g}")
        lines += ["", f"-# 例如 {ev.get('emoji', '')} {ev['name']}：" + "、".join(parts)]
    lines += [
        "",
        "### ⚠️ 活動結束時",
        "- 活動素材、活動料理會從所有人的神社倉庫**清空**，記得在結束前用掉",
        "- 還沒領的活動任務獎勵也會跟著消失",
        "- 已經拿到的**活動稱號**、裏世界帶回來的**活動寶物**都會留著",
        "",
        "用 `/event info` 看現在有哪些活動、各自的限定內容和結束時間。",
    ]
    return "\n".join(lines)


def _quests() -> str:
    lines = [
        "活動期間做的事會累積成**活動任務**的進度，完成之後到 `/event quest` 領賽錢和經驗值。",
        "",
        "### 📜 任務怎麼算",
        "- **只算活動進行中做的事**：活動開始前、結束後做的都不算",
        "- 任務內容五花八門：到限定地點採集、做活動料理、招待限定客人、端活動料理、祈願、簽到，"
        "還有裏世界的打倒活動敵人、成功撤離等等",
        "- 裏世界的「打倒敵人」任務在**打倒當下就算**，那一局後來失敗也照算；"
        "「帶出活動寶物」「成功撤離」則要真的平安回來才算",
        "",
        "### 🎁 領取",
        "- 每個任務右邊有一顆按鈕：「🎁 領取」= 完成了可以領、「✅ 已領取」、「未完成」",
        "- 只有活動進行中才能領，**活動結束後沒領的就沒了**",
        "- 活動快結束還有完成沒領的任務時，機器人會私訊提醒你一次 (可以在 `/notify` 關掉)",
        "",
        "### 🏷️ 活動稱號",
        "領取的任務數量達到門檻，就會**永久**拿到那個活動的稱號，活動結束也不會消失，在 `/profile` 的稱號分組「🎪 活動」裡換上。",
    ]
    for ev in _events():
        titles = sorted(ev.get("quest_titles", []), key=lambda t: t.get("min_quests", 0))
        if titles:
            text = "、".join(f"{t['min_quests']} 項 [{t['rarity']}]「{t['name']}」" for t in titles)
            lines.append(f"-# {ev.get('emoji', '')} {ev['name']}：領 {text}")
    lines += [
        "",
        "-# 同一個活動之後再開一次時，任務進度和領取紀錄會重新算；稱號門檻算的是所有次加起來領過幾種不同的任務。",
    ]
    return "\n".join(lines)


BOOK = {
    "intro": "活動期間會有限定的採集地點、料理、客人和裏世界關卡，還有活動任務可以領獎勵、拿永久稱號。",
    "chapters": [
        {"title": "🎪 活動是什麼", "short": "限定地點、活動料理、限定客人與裏世界活動關卡；活動結束時會發生什麼",
         "body": _about, "commands": ["event info"]},
        {"title": "📜 活動任務與稱號", "short": "活動期間累積任務進度，領賽錢、經驗值和永久的活動稱號",
         "body": _quests, "commands": ["event quest"]},
    ],
}

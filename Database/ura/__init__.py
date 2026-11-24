"""
🌀 裏世界探索 (/ura) 的遊戲引擎 (純邏輯，不 import discord、不碰資料庫；亂數一律由呼叫端注入)

規格：docs/gameplay/ura.md
- data.py    讀 Database/ura/data/*.json (狀態、符卡、敵人、道具、法具、寶物、事件、區域)
- rules.py   數值公式 (區域倍率、減傷、完整度倍率、寶物機率曲線、常識度…)
- status.py  統一的「狀態效果」系統 (資料驅動)
- combat.py  回合制戰鬥
- run.py     一局的流程 (選門、房間、背包、商人、結算)
狀態全部是 dict / list，可以直接 json.dumps 存進資料庫，接回時原樣讀出來。
"""

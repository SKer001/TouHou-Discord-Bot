"""TH07 妖妖夢數值模擬・第三輪 (2026-11-23，歷史紀錄)：紫的全體倍率 1.3 ➔ 1.6 ➔ 1.8 有沒有差、莉莉卡 B 點 / 冷卻

用法 (在專案根目錄)：python tools/ura_sim/th07/th07_sim3.py [每格局數，預設 300]
結果印在畫面上，另存 tools/ura_sim/th07/out/th07_sim3_out.json (不要 commit)。
⚠️ 跟 th07_sim2.py 一樣沒有「每組一個新行程」，數字只能當參考；要準的用 th07_sim4.py。
"""
import copy
import importlib.util
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))   # 專案根目錄
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
sys.path.insert(0, ROOT)
os.chdir(ROOT)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
ZONES = (3, 4, 5, 6, 7)


def job(args):
    name, team, theme, over, seed = args
    spec = importlib.util.spec_from_file_location("ura_sim_spells", os.path.join(ROOT, "tools", "ura_sim", "spells.py"))
    s = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s)
    from Database.ura import data, run as R
    sp = data.spells()
    for cid, patch in (over or {}).items():
        new = copy.deepcopy(sp[cid])
        if "tiers" in patch:
            new["tiers"] = patch["tiers"]
        for k in ("b", "cd"):
            if k in patch:
                new[k] = patch[k]
        if "turns" in patch:
            for e in new["effects"]:
                if e.get("status") in patch["turns"][0]:
                    e["turns"] = patch["turns"][1]
        sp[cid] = new
    if theme:
        R.zone_theme = lambda run, zone: data.zone_by_id(theme)
    rng = random.Random(seed)
    cleared, pocket = [], []
    for _ in range(N):
        r = s.play(team, dict(s.BAGS["重裝"]), rng, 7)
        cleared.append(r["boss_cleared"])
        pocket.append(r["pocket"])
    return {"name": name, "theme": theme or "隨機", "p": {z: sum(c >= z for c in cleared) / N for z in ZONES},
            "pocket_med": sorted(pocket)[N // 2]}


M, S = 0.65, 0.9
A = lambda x: [("marisa", "SR", M), ("meiling", "SR", M), x]
G = lambda x: [("marisa", "SR", M), x, ("daiyousei", "SR", M)]
JOBS = [
    ("B·紫SSR 換琪露諾 現案 1.3/1.6/1.9", [("yukari", "SSR", M), ("meiling", "SR", M), ("yuki_mai", "SR", M)], None),
    ("B·紫SSR 換琪露諾 1.6/1.9/2.2", [("yukari", "SSR", M), ("meiling", "SR", M), ("yuki_mai", "SR", M)],
     {"yukari": {"tiers": [{"m": 1.6, "s": 40}, {"m": 1.9, "s": 60}, {"m": 2.2, "s": 80}]}}),
    ("B·紫SSR 換琪露諾 1.8/2.1/2.4", [("yukari", "SSR", M), ("meiling", "SR", M), ("yuki_mai", "SR", M)],
     {"yukari": {"tiers": [{"m": 1.8, "s": 40}, {"m": 2.1, "s": 60}, {"m": 2.4, "s": 80}]}}),
    ("R·紫UR 換靈夢 現案", [("yukari", "UR", S), ("meiling", "SSR", S), ("daiyousei", "SR", S)], None),
    ("R·紫UR 換靈夢 1.6/1.9/2.2", [("yukari", "UR", S), ("meiling", "SSR", S), ("daiyousei", "SR", S)],
     {"yukari": {"tiers": [{"m": 1.6, "s": 40}, {"m": 1.9, "s": 60}, {"m": 2.2, "s": 80}]}}),
    ("R 靈夢隊 (對照)", [("reimu", "UR", S), ("meiling", "SSR", S), ("daiyousei", "SR", S)], None),
    ("A·莉莉卡SR 現案 B10/冷卻6", A(("lyrica", "SR", M)), None),
    ("A·莉莉卡SR B8/冷卻5", A(("lyrica", "SR", M)), {"lyrica": {"b": 8, "cd": 5}}),
    ("A·莉莉卡SSR 現案", A(("lyrica", "SSR", M)), None),
]

if __name__ == "__main__":
    jobs = [(n, t, "", o, 5000 + i) for i, (n, t, o) in enumerate(JOBS)]
    with ProcessPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(job, jobs))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "th07_sim3_out.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for r in res:
        print(f"{r['name']:<34} " + " ".join(f"{z}:{r['p'][z]:.0%}" for z in ZONES) + f"  錢中位 {r['pocket_med'] // 1000}K")

"""TH07 妖妖夢數值模擬・第二輪 (2026-11-23，歷史紀錄)：莉莉回血幾 %、愛麗絲人偶替身幾 % / 幾回合、梅露蘭 / 莉莉卡跟同職業對照、全體攻擊隊換主攻

用法 (在專案根目錄)：python tools/ura_sim/th07/th07_sim2.py [每格局數，預設 300]
結果印在畫面上，另存 tools/ura_sim/th07/out/th07_sim2_out.json (不要 commit)。
⚠️ 這支沒有「每組一個新行程」：同一個工作行程會沿用上一組改過的符卡數值，數字只能當參考；要準的用 th07_sim4.py。
   「現案」指的是當時的草案，定案後的數字在 docs/dev/new-characters.md 第 5 節。
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
    ("A 一般隊 (大妖精SR)", A(("daiyousei", "SR", M)), None),
    ("A·雪與舞SR", A(("yuki_mai", "SR", M)), None),
    ("A·莉莉SR 現案 10/13/16%", A(("lily_white", "SR", M)), None),
    ("A·莉莉SR 12/16/20%", A(("lily_white", "SR", M)), {"lily_white": {"tiers": [{"h": 0.12}, {"h": 0.16}, {"h": 0.2}]}}),
    ("A·莉莉SR 15/20/25% (= 雪與舞)", A(("lily_white", "SR", M)), {"lily_white": {"tiers": [{"h": 0.15}, {"h": 0.2}, {"h": 0.25}]}}),
    ("A·梅露蘭SR", A(("merlin", "SR", M)), None),
    ("A·愛麗絲(TH05)SR", A(("alice", "SR", M)), None),
    ("A·帕秋莉SR", A(("patchouli", "SR", M)), None),
    ("A·美鈴SR (守護基準)", G(("meiling", "SR", M)), None),
    ("A·美鈴SSR", G(("meiling", "SSR", M)), None),
    ("A·愛麗絲SR 現案 30/40/50% 2回合", G(("alice_th07", "SR", M)), None),
    ("A·愛麗絲SSR 現案", G(("alice_th07", "SSR", M)), None),
    ("A·愛麗絲SR 40/50/60%", G(("alice_th07", "SR", M)), {"alice_th07": {"tiers": [{"v": 0.4}, {"v": 0.5}, {"v": 0.6}]}}),
    ("A·愛麗絲SR 30/40/50% 3回合", G(("alice_th07", "SR", M)), {"alice_th07": {"turns": [["doll_guard"], 3]}}),
    ("A·愛麗絲SR 嘲諷+替身都 3回合", G(("alice_th07", "SR", M)), {"alice_th07": {"turns": [["doll_guard", "taunt"], 3]}}),
    ("A·蕾蒂SR", G(("letty", "SR", M)), None),
    ("A·夢子SR", G(("yumeko", "SR", M)), None),
    ("A·艾莉SR", G(("elly", "SR", M)), None),
    ("B 全體隊 琪露諾SR/美鈴SR/雪與舞SR", [("cirno", "SR", M), ("meiling", "SR", M), ("yuki_mai", "SR", M)], None),
    ("B·幽幽子SSR 換琪露諾", [("yuyuko", "SSR", M), ("meiling", "SR", M), ("yuki_mai", "SR", M)], None),
    ("B·紫SSR 換琪露諾", [("yukari", "SSR", M), ("meiling", "SR", M), ("yuki_mai", "SR", M)], None),
    ("B·藍SSR 換琪露諾", [("ran", "SSR", M), ("meiling", "SR", M), ("yuki_mai", "SR", M)], None),
    ("B·神綺SSR 換琪露諾", [("shinki", "SSR", M), ("meiling", "SR", M), ("yuki_mai", "SR", M)], None),
    ("A·莉莉卡SR 換大妖精", A(("lyrica", "SR", M)), None),
    ("A·露易絲SR 換大妖精", A(("luize", "SR", M)), None),
    ("A·小惡魔SR 換大妖精 (賺錢對照)", A(("koakuma", "SR", M)), None),
]

if __name__ == "__main__":
    jobs = [(n, t, "", o, 5000 + i) for i, (n, t, o) in enumerate(JOBS)]
    with ProcessPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(job, jobs))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "th07_sim2_out.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for r in res:
        print(f"{r['name']:<34} " + " ".join(f"{z}:{r['p'][z]:.0%}" for z in ZONES) + f"  錢中位 {r['pocket_med'] // 1000}K")

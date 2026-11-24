"""TH07 妖妖夢數值模擬・定案用 (2026-11-23)：每組一個新行程 (max_tasks_per_child=1，主題 / 數值的修改不會帶到下一組)，記每位角色每局放幾次符卡

用法 (在專案根目錄)：python tools/ura_sim/th07/th07_sim4.py [每格局數，預設 200] [輸出前綴]
結果印在畫面上，另存 tools/ura_sim/th07/out/<前綴>_out.json / .txt (不要 commit)。需要 Python 3.11 以上。
說明與怎麼改成下一代角色用：docs/handbook/sessions.md「筆記的去向」。VARIANTS 是定案前比過的方案 (莉莉 15 / 20 / 25%、3 回合)，現在已經是正式數值。
"""
import copy
import importlib.util
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))   # 專案根目錄
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")   # 輸出資料夾
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "th07_sim4"
ZONES = (3, 4, 5, 6, 7, 8)


def job(args):
    name, team, theme, aoe, over, seed = args
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    spec = importlib.util.spec_from_file_location("ura_sim_spells", os.path.join(ROOT, "tools", "ura_sim", "spells.py"))
    s = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s)
    from Database.ura import data, run as R
    s.AOE_SOLO = aoe
    sp = data.spells()
    for cid, patch in (over or {}).items():
        new = copy.deepcopy(sp[cid])
        for k in ("tiers", "b", "cd"):
            if k in patch:
                new[k] = patch[k]
        if "turns" in patch:
            for e in new["effects"]:
                if e.get("status") in patch["turns"][0]:
                    e["turns"] = patch["turns"][1]
        sp[cid] = new
    if theme:
        R.zone_theme = lambda run, zone: data.zone_by_id(theme)
    casts = {}
    orig = R.battle_action

    def counting(run, act, rng, **kw):
        if act == "spell":
            u = next((m for m in run["party"] if m["uid"] == kw.get("uid")), None)
            res = orig(run, act, rng, **kw)
            if u is not None and res is None:
                casts[u["cid"]] = casts.get(u["cid"], 0) + 1
            return res
        return orig(run, act, rng, **kw)
    R.battle_action = counting
    rng = random.Random(seed)
    cleared, pocket = [], []
    for _ in range(N):
        r = s.play(team, dict(s.BAGS["重裝"]), rng, 8)
        cleared.append(r["boss_cleared"])
        pocket.append(r["pocket"])
    return {"name": name, "theme": theme or "隨機", "aoe": aoe, "p": {z: sum(c >= z for c in cleared) / N for z in ZONES},
            "pocket_med": sorted(pocket)[N // 2], "casts": {k: round(v / N, 1) for k, v in casts.items()}}


M, S, U = 0.65, 0.9, 1.0
A = lambda x: [("marisa", "SR", M), ("meiling", "SR", M), x]     # 換輔助 / 嚮導位
G = lambda x: [("marisa", "SR", M), x, ("daiyousei", "SR", M)]   # 換守護位
C = lambda x: [("marisa", "SR", M), ("meiling", "SR", M), x]     # 換斥候位 (沒補師)
D = lambda x: [x, ("yumeko", "SSR", S), ("daiyousei", "SR", S)]  # 強隊換攻擊手
E = lambda x: [x, ("remilia", "LR", U), ("daiyousei", "SR", U)]  # 頂尖換神綺
B = lambda x: [x, ("meiling", "SR", M), ("yuki_mai", "SR", M)]   # 全體隊換琪露諾
RT = lambda x: [x, ("meiling", "SSR", S), ("daiyousei", "SR", S)]  # 靈夢隊換靈夢
TEAMS = {
    # 攻擊手
    "A 一般隊 魔理沙SR": [("marisa", "SR", M), ("meiling", "SR", M), ("daiyousei", "SR", M)],
    "A·妖夢SR": [("youmu", "SR", M), ("meiling", "SR", M), ("daiyousei", "SR", M)],
    "D 強隊 芙蘭UR": D(("flandre", "UR", S)),
    "D·魔理沙UR": D(("marisa", "UR", S)),
    "D·琪露諾UR": D(("cirno", "UR", S)),
    "D·神綺UR": D(("shinki", "UR", S)),
    "D·妖夢UR": D(("youmu", "UR", S)),
    "D·幽幽子UR": D(("yuyuko", "UR", S)),
    "D·藍UR": D(("ran", "UR", S)),
    "E 頂尖 神綺LR": E(("shinki", "LR", U)),
    "E·幽幽子LR": E(("yuyuko", "LR", U)),
    "E·藍LR": E(("ran", "LR", U)),
    # 守護者 (同一檔：美鈴 / 夢子 / 蕾蒂 SR = 第 2 檔；愛麗絲 SSR = 第 2 檔)
    "G·美鈴SR": G(("meiling", "SR", M)),
    "G·夢子SR": G(("yumeko", "SR", M)),
    "G·蕾蒂SR": G(("letty", "SR", M)),
    "G·愛麗絲SR (她的最低檔)": G(("alice_th07", "SR", M)),
    "G·愛麗絲SSR": G(("alice_th07", "SSR", M)),
    # 輔助 (大妖精 / 雪與舞 / 莉莉 SR = 第 3 檔；梅露蘭 SR = 第 2 檔；愛麗絲(TH05) / 帕秋莉 SR = 第 1 檔)
    "A·雪與舞SR": A(("yuki_mai", "SR", M)),
    "A·莉莉SR": A(("lily_white", "SR", M)),
    "A·梅露蘭SR": A(("merlin", "SR", M)),
    "A·愛麗絲(TH05)SR": A(("alice", "SR", M)),
    "A·帕秋莉SR": A(("patchouli", "SR", M)),
    # 斥候 (露米婭 / 橙 / 露娜薩 SR = 第 2 檔)
    "C 沒補師 露米婭SR": C(("rumia", "SR", M)),
    "C·橙SR": C(("chen", "SR", M)),
    "C·露娜薩SR": C(("lunasa", "SR", M)),
    # 嚮導
    "R 靈夢隊 靈夢UR": RT(("reimu", "UR", S)),
    "R·紫UR": RT(("yukari", "UR", S)),
    "A·露易絲SR": A(("luize", "SR", M)),
    "A·莉莉卡SR": A(("lyrica", "SR", M)),
    "A·小惡魔SR (賺錢對照)": A(("koakuma", "SR", M)),
    # 全體攻擊隊
    "B 全體隊 琪露諾SR": B(("cirno", "SR", M)),
    "B·幽幽子SSR": B(("yuyuko", "SSR", M)),
    "B·藍SSR": B(("ran", "SSR", M)),
    "B·紫SSR": B(("yukari", "SSR", M)),
    "B·神綺SSR": B(("shinki", "SSR", M)),
    # 妖妖夢隊
    "F 幽幽子SSR/紫SSR/莉莉SR": [("yuyuko", "SSR", M), ("yukari", "SSR", M), ("lily_white", "SR", M)],
    "H 騷靈樂團 三姊妹SR": [("lunasa", "SR", M), ("merlin", "SR", M), ("lyrica", "SR", M)],
    "H2 騷靈樂團 三姊妹SSR 0.9": [("lunasa", "SSR", S), ("merlin", "SSR", S), ("lyrica", "SSR", S)],
    "I 妖夢SR/愛麗絲SR/莉莉SR": [("youmu", "SR", M), ("alice_th07", "SR", M), ("lily_white", "SR", M)],
    "J 藍UR/紫UR/大妖精SR": [("ran", "UR", S), ("yukari", "UR", S), ("daiyousei", "SR", S)],
}
NETHER = ["A 一般隊 魔理沙SR", "A·妖夢SR", "C 沒補師 露米婭SR", "C·橙SR", "C·露娜薩SR", "D 強隊 芙蘭UR", "D·妖夢UR", "D·幽幽子UR",
          "D·藍UR", "E 頂尖 神綺LR", "E·幽幽子LR", "B 全體隊 琪露諾SR", "B·幽幽子SSR", "B·藍SSR", "R 靈夢隊 靈夢UR", "R·紫UR",
          "I 妖夢SR/愛麗絲SR/莉莉SR", "J 藍UR/紫UR/大妖精SR"]
AOE = ["B 全體隊 琪露諾SR", "B·幽幽子SSR", "B·藍SSR", "B·紫SSR", "D·幽幽子UR", "D·藍UR", "D·神綺UR", "E 頂尖 神綺LR",
       "E·幽幽子LR", "J 藍UR/紫UR/大妖精SR"]
VARIANTS = [   # (名稱, 隊伍, 修改)
    ("A·莉莉SR 回血 15/20/25", A(("lily_white", "SR", M)), {"lily_white": {"tiers": [{"h": 0.15}, {"h": 0.2}, {"h": 0.25}]}}),
    ("A·莉莉SR 春之祝福 3 回合", A(("lily_white", "SR", M)), {"lily_white": {"turns": [["spring_blessing"], 3]}}),
    ("A·莉莉SR 回血 15/20/25 + 3 回合", A(("lily_white", "SR", M)),
     {"lily_white": {"tiers": [{"h": 0.15}, {"h": 0.2}, {"h": 0.25}], "turns": [["spring_blessing"], 3]}}),
    ("C·露娜薩SR 弱化 3 回合", C(("lunasa", "SR", M)), {"lunasa": {"turns": [["debuff_atk", "debuff_def"], 3]}}),
    ("H 騷靈樂團 三姊妹SR 露娜薩 3 回合", [("lunasa", "SR", M), ("merlin", "SR", M), ("lyrica", "SR", M)],
     {"lunasa": {"turns": [["debuff_atk", "debuff_def"], 3]}}),
]

if __name__ == "__main__":
    jobs = [(n, t, "", False, None, 1000 + i) for i, (n, t) in enumerate(TEAMS.items())]
    jobs += [(n, TEAMS[n], "netherworld", False, None, 2000 + i) for i, n in enumerate(NETHER)]
    jobs += [(n, TEAMS[n], "", True, None, 3000 + i) for i, n in enumerate(AOE)]
    jobs += [(n, t, "", False, o, 4000 + i) for i, (n, t, o) in enumerate(VARIANTS)]
    os.makedirs(HERE, exist_ok=True)
    with ProcessPoolExecutor(max_workers=10, max_tasks_per_child=1) as ex:
        res = list(ex.map(job, jobs))
    with open(os.path.join(HERE, f"{PREFIX}_out.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    lines = []
    for r in res:
        tag = ("冥界" if r["theme"] == "netherworld" else "隨機") + (" 單BOSS也放全體" if r["aoe"] else "")
        lines.append(f"{tag:<14}{r['name']:<30} " + " ".join(f"{z}區 {r['p'][z]:.0%}" for z in ZONES)
                     + f"  錢中位 {r['pocket_med'] // 1000}K  符卡/局 " + "、".join(f"{k} {v}" for k, v in r["casts"].items()))
    open(os.path.join(HERE, f"{PREFIX}_out.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))

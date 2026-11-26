"""📜 CHANGELOG.md：版本紀錄由新到舊排、不重複，最上面那筆跟 Utils/version.py 一樣
(1.00.008～010 曾經被插到 1.00.000 下面：編版本號的工具找 "## 0." 當插入點，1.00 之後就插錯位置)"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT); os.chdir(ROOT)
from Utils.version import VERSION

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)

text = open("CHANGELOG.md", encoding="utf-8").read()
heads = re.findall(r"(?m)^## (\d+\.\d{2}\.\d{3}) — ", text)
vers = [tuple(map(int, v.split("."))) for v in heads]
check("有版本紀錄", len(vers) > 0)
check(f"最上面那筆是 {VERSION} (現在是 {heads[0] if heads else '沒有'})", bool(heads) and heads[0] == VERSION)
for (a, va), (b, vb) in zip(zip(heads, vers), zip(heads[1:], vers[1:])):
    check(f"{a} 要排在 {b} 上面 (由新到舊)", va > vb)
print(f"passed {ok}, failed {fail}")
sys.exit(1 if fail else 0)

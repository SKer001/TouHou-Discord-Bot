"""
🧪 執行全部測試：python tests/run_all.py

- 每個 test_*.py 都在獨立的子行程中執行，資料庫一律使用暫存資料夾 (絕不碰真實的 Users.db / Item.db)
- 測試用真實的 discord.py 物件 + 假的 Interaction，不會連上 Discord
- 執行前後會比對 Database/*.db 的 sha256，確認真實資料庫沒有被改動
"""
import glob
import hashlib
import os
import re
import subprocess
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)


def db_hashes() -> dict:
    return {
        path: hashlib.sha256(open(path, "rb").read()).hexdigest()
        for path in glob.glob(os.path.join(ROOT, "Database", "*.db"))
    }


def main() -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    before = db_hashes()
    total_pass = total_fail = 0
    broken = []

    for path in sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py"))):
        name = os.path.basename(path)
        proc = subprocess.run([sys.executable, path], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
        output = proc.stdout + proc.stderr
        match = re.search(r"passed (\d+), failed (\d+)", output)
        if proc.returncode != 0 or not match:
            broken.append(name)
            print(f"💥 {name} 執行失敗\n{output[-2000:]}")
            continue
        passed, failed = int(match.group(1)), int(match.group(2))
        total_pass += passed
        total_fail += failed
        mark = "✅" if failed == 0 else "❌"
        print(f"{mark} {name}: passed {passed}, failed {failed}")
        for line in output.splitlines():
            if line.startswith("FAIL:"):
                print(f"    {line}")

    if db_hashes() != before:
        print("🚨 真實資料庫在測試期間被改動了！請檢查測試是否有把 DB_PATH 指到暫存資料夾。")
        broken.append("database-guard")

    print(f"\n總計 passed {total_pass}, failed {total_fail}" + (f"，執行失敗：{broken}" if broken else ""))
    return 0 if total_fail == 0 and not broken else 1


if __name__ == "__main__":
    sys.exit(main())

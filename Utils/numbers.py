"""
🔢 數字顯示 (使用者 2026-11-14)：
- short_number：縮寫，最多兩位小數 (999 / 1.5K / 12.35M / 2.56B)
- fmt_money：「持有 / 餘額 / 累計」這類大數字用；一萬以上縮寫，以下照常加逗號 (5,000)
  價格、花費、獎勵、轉帳金額、手續費這些要看清楚確切數字的地方不要用，照舊 f"{n:,}"
"""

SHORT_FROM = 10_000   # fmt_money 從多少開始縮寫


def short_number(n) -> str:
    n = int(n)
    for unit, size in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if abs(n) >= size:
            return f"{n / size:.2f}".rstrip("0").rstrip(".") + unit
    return str(n)


def fmt_money(n) -> str:
    n = int(n)
    return short_number(n) if abs(n) >= SHORT_FROM else f"{n:,}"

"""
💹 經濟系統 (Database/Users.db)：神社經營、浮動市值、分解、市場、轉帳

資料表結構定義在 User_DB_Manager.SCHEMA_STATEMENTS (同一個 Users.db，init_db 一起建立)。
跟體力一樣「不用背景排程」：神社在每次查看 / 操作時才依經過時間結算，市值在第一次有人用到時補結算前幾天。

所有數值都是使用者 2026-11-05 指定的 (見 TODO.md / CHANGELOG.md 0.23.000)，要改數值改常數就好。

📦 這個檔案是入口：實作拆在 Database/economy/ 底下，這裡把每個子模組的名字全部轉出來，
   外面照舊寫 `from Database import Economy_DB_Manager as econ`、`from Database.Economy_DB_Manager import X`。
   - common.py        神社經營的數值常數、_dt / modifier / economy_meta 小工具
   - event_state.py   🎪 活動狀態、get_rules、手續費倍率快取
   - shrine.py        ⛩️ 神社經營
   - gather.py        🏮 打工、🗺️ 採集 / 🍳 料理 / 🏪 雜貨店 / 🍵 招待、🧺 快速採集
   - market_value.py  💹 浮動市值
   - market.py        ♻️ 分解、🏪 市場、💸 轉帳

⚠️ 對入口的屬性賦值 (測試會寫 econ.get_rules = fake、econ.GUEST_SPAWN = […]、econ.load_events = fake) 會一起改到
   「本來就有這個名字」的子模組，所以跟拆開前一樣會生效；新增子模組要加進下面的 _PARTS (照依賴順序)，
   也要加進 Utils/reloader.py 的 PACKAGE_ORDER。
"""
import sys
import types

from Database.economy import common, event_state, shrine, gather, market_value, market

_PARTS = (common, event_state, shrine, gather, market_value, market)   # 依賴順序

for _part in _PARTS:
    globals().update({_k: _v for _k, _v in vars(_part).items() if not _k.startswith("__")})
del _part


class _EntryModule(types.ModuleType):
    """econ.X = 值 ➔ 入口自己改，子模組裡同名的也一起改 (函式是在子模組的命名空間裡找名字的)"""

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name.startswith("__"):   # __name__ / __spec__ / __file__…：importlib.reload 會重設入口的這些屬性，不能傳給子模組
            return
        for part in self.__dict__.get("_PARTS", ()):
            if name in vars(part):
                setattr(part, name, value)


sys.modules[__name__].__class__ = _EntryModule

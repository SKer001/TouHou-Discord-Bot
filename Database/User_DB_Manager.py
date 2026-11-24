"""
👤 玩家資料庫管理 (Database/Users.db)

所有「跟玩家有關」的資料都在同一個資料庫裡：
  - users        ：賽錢 / 等級 / 經驗 / 背包 / 隱私 / 每日簽到日期與運勢
  - gacha_stats  ：每位玩家的抽卡統計
  - gacha_cards  ：每位玩家持有的卡牌 (每張卡一列)
  - namecards    ：每位玩家擁有的角色名片 (推角稱號解鎖 / 管理員給)

道具範本 (item_templates) 在另一個資料庫：請見 Item_DB_Manager.py

📦 這個檔案是入口：實作拆在 Database/users/ 底下，這裡把每個子模組的名字全部轉出來，
   外面照舊寫 `from Database import User_DB_Manager as udm`、`from Database.User_DB_Manager import X`。
   - schema.py   🧱 資料表結構與初始化 (DB_PATH、SCHEMA_STATEMENTS、connect、_ensure_user、init_db)
   - core.py     👤 玩家資料、💰 貨幣經驗、📅 每日簽到、🎒 背包道具、🏆 排行榜與隱私、tw_day、📊 玩家統計、🎪 活動任務計數、⚡ 體力
   - titles.py   🏷️ 稱號、🖼️ 角色名片
   - cards.py    🎴 抽卡：卡牌與統計、🛠️ 管理員卡冊操作

⚠️ 對入口的屬性賦值 (測試 / botcli / 重載會寫 udm.DB_PATH = 沙盒、udm.STARTING_MONEY = 1000、udm.get_user_cards = fake) 會一起改到
   「本來就有這個名字」的子模組，所以跟拆開前一樣會生效 (connect 讀的是 schema.DB_PATH)；新增子模組要加進下面的 _PARTS (照依賴順序)，
   也要加進 Utils/reloader.py 的 PACKAGE_ORDER。跟 Economy_DB_Manager.py 同一套做法。
"""
import sys
import types

from Database.users import schema, core, titles, cards

_PARTS = (schema, core, titles, cards)   # 依賴順序

for _part in _PARTS:
    globals().update({_k: _v for _k, _v in vars(_part).items() if not _k.startswith("__")})
del _part


class _EntryModule(types.ModuleType):
    """udm.X = 值 ➔ 入口自己改，子模組裡同名的也一起改 (函式是在子模組的命名空間裡找名字的)"""

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name.startswith("__"):   # __name__ / __spec__ / __file__…：importlib.reload 會重設入口的這些屬性，不能傳給子模組
            return
        for part in self.__dict__.get("_PARTS", ()):
            if name in vars(part):
                setattr(part, name, value)


sys.modules[__name__].__class__ = _EntryModule

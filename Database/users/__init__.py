"""
👤 玩家資料庫的實作 (從 Database/User_DB_Manager.py 拆出來的)

依賴順序 (上面的不匯入下面的)：schema ➔ core ➔ titles ➔ cards
外面一律從入口 Database.User_DB_Manager 匯入；這裡故意不匯入任何子模組 (避免循環 import)。
"""

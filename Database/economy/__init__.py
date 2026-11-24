"""
💹 經濟系統的實作 (從 Database/Economy_DB_Manager.py 拆出來的)

依賴順序 (上面的不匯入下面的)：common ➔ event_state ➔ shrine ➔ gather；common ➔ event_state ➔ market_value ➔ market
外面一律從入口 Database.Economy_DB_Manager 匯入；這裡故意不匯入任何子模組 (避免循環 import)。
"""

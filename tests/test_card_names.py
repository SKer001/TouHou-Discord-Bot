"""🎴 卡牌名稱 / 稱號：資料庫存的是副本，讀卡時要換成目前角色檔的內容 (角色改名、改稱號後舊卡跟著變)"""
import asyncio, os, sys, tempfile, sqlite3
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from Database import User_DB_Manager as udm
from Database import Economy_DB_Manager as econ
from Utils import character_data

tmp = tempfile.mkdtemp()
udm.DB_PATH = os.path.join(tmp, "Users.db")   # 絕不碰真實 Users.db

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else:
        fail += 1; print("FAIL:", name)

def sql(q, args=()):
    con = sqlite3.connect(udm.DB_PATH); con.execute(q, args); con.commit(); con.close()

A = 801
chars = character_data.load_characters()
reimu = chars["reimu"]

def stale(iid, key="reimu", rarity="SR"):
    """寫入當下的舊副本 (名字、表情、稱號都過時)"""
    return {"instance_id": iid, "character_key": key, "name": "舊名字", "emoji": "❓",
            "rarity": rarity, "title": "舊稱號", "completeness": 0.5, "obtained_at": "x"}

async def main():
    await udm.init_db()
    await udm.add_gacha_cards(A, [stale("n1"), stale("n2", key="no_such_char")])

    cards = {c["instance_id"]: c for c in await udm.get_user_cards(A)}
    check("name from character file", cards["n1"]["name"] == reimu["name"])
    check("emoji from character file", cards["n1"]["emoji"] == reimu["emoji"])
    check("title from character file", cards["n1"]["title"] == reimu["gacha"]["titles"]["SR"])
    check("missing character keeps copy", cards["n2"]["name"] == "舊名字" and cards["n2"]["title"] == "舊稱號")

    # 稱號表裡沒有的階級 ➔ 保留副本的稱號
    sql("UPDATE gacha_cards SET rarity = 'XX' WHERE instance_id = 'n1'")
    cards = {c["instance_id"]: c for c in await udm.get_user_cards(A)}
    check("unknown rarity keeps title", cards["n1"]["title"] == "舊稱號" and cards["n1"]["name"] == reimu["name"])
    sql("UPDATE gacha_cards SET rarity = 'SR' WHERE instance_id = 'n1'")

    # 角色檔改名 ➔ 快取清掉後立刻生效
    orig = character_data.load_characters
    def renamed():
        d = orig()
        d["reimu"] = dict(d["reimu"], name="新名字", gacha=dict(d["reimu"]["gacha"], titles={"SR": "新稱號"}))
        return d
    character_data.load_characters = renamed
    character_data.clear_card_info_cache()
    cards = {c["instance_id"]: c for c in await udm.get_user_cards(A)}
    check("rename applies", cards["n1"]["name"] == "新名字" and cards["n1"]["title"] == "新稱號")
    character_data.load_characters = orig
    character_data.clear_card_info_cache()

    # 合成 / 融合讀到的卡也是新名字
    consumed, new = await udm.transform_cards(A, ["n1"], lambda cs: dict(cs[0], instance_id="n3"))
    check("transform reads current names", consumed[0]["name"] == reimu["name"] and new["title"] == reimu["gacha"]["titles"]["SR"])

    # 市場上架清單
    sql("INSERT INTO market_listings (seller_id, instance_id, character_key, name, emoji, rarity, title, completeness, obtained_at, price, listed_at) "
        "VALUES (?, 'm1', 'reimu', '舊名字', '❓', 'SR', '舊稱號', 0.5, 'x', 100, '2026-11-13T00:00:00')", (A,))
    listing = (await econ.get_listings(seller_id=A))[0]
    check("listing current names", listing["name"] == reimu["name"] and listing["title"] == reimu["gacha"]["titles"]["SR"])

asyncio.run(main())
print(f"passed {ok}, failed {fail}")

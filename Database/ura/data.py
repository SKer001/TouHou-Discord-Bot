"""🌀 裏世界的資料檔 (Database/ura/data/*.json)；讀一次快取，reload() 重讀

🎪 活動的裏世界內容寫在各活動檔 (Events/<id>.json) 的 "ura" 區塊 (格式見 Events/README.md)：
狀態 / 敵人 / 法具 / 事件 / 寶物**不管活動有沒有在進行都會併進來** (活動寶物活動結束也要賣得掉、
進行中的那一局要能打完)；活動有沒有在進行只決定會不會出 🎪 門 (run["live_fests"]，資料層每一步更新)。
併進來的法具 / 事件帶 "fest": 活動 id，一般的掉落池、事件池都會排除它們。
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_cache: dict = {}


def _load(name: str) -> dict:
    if name not in _cache:
        with open(os.path.join(DATA_DIR, f"{name}.json"), encoding="utf-8") as f:
            _cache[name] = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    return _cache[name]


def reload():
    _cache.clear()


# =========================================================
# 🎪 活動 (Events/*.json 的 "ura")
# =========================================================
def fests() -> dict:
    """{活動 id: ura 區塊 + id / name / emoji}"""
    if "fests" not in _cache:
        from Database.events import load_events
        out = {}
        for eid, ev in load_events().items():
            u = ev.get("ura")
            if isinstance(u, dict):
                out[eid] = {**u, "id": eid, "name": ev.get("name", eid), "emoji": ev.get("emoji", "🎪")}
        _cache["fests"] = out
    return _cache["fests"]


def _merged(key: str, base: dict) -> dict:
    """一般資料 + 每個活動的同名區塊 (帶 "fest" 標記)"""
    ck = f"merged:{key}"
    if ck not in _cache:
        out = dict(base)
        for eid, f in fests().items():
            for k, v in (f.get(key) or {}).items():
                out[k] = {**v, "fest": eid}
        _cache[ck] = out
    return _cache[ck]


def statuses() -> dict:
    return _merged("statuses", _load("statuses"))


def spells() -> dict:
    return _load("spells")


def enemies() -> dict:
    return _merged("enemies", _load("enemies"))


def items() -> dict:
    return _load("items")["items"]


def category_max() -> dict:
    return _load("items")["category_max"]


def bags() -> dict:
    return {k: v for k, v in _load("items")["bags"].items() if not k.startswith("_")}


def relics() -> dict:
    """全部法具 (含活動法具，帶 "fest")；一般掉落用 base_relics()"""
    return _merged("relics", _load("relics")["relics"])


def base_relics() -> dict:
    return {k: v for k, v in relics().items() if not v.get("fest")}


def events() -> dict:
    """全部事件 (含活動事件，帶 "fest")；一般的 ❓ 事件門只抽沒有 "fest" 的"""
    return _merged("events", _load("events")["events"])


def event_weights() -> dict:
    return _load("events")["weights"]


def treasure_prices() -> dict:
    return _load("treasures")["sell_price"]


def zones() -> list[dict]:
    """5 個區域；copy_of 的區域 (名單還沒定) 借那一區的敵人 / 素材 / 寶物"""
    raw = _load("zones")["zones"]
    by_id = {z["id"]: z for z in raw}
    out = []
    for z in raw:
        src = by_id.get(z.get("copy_of"), z)
        out.append({**src, **{k: z[k] for k in ("id", "name", "emoji")}, "treasure_zone": src["id"],
                    "borrowed": bool(z.get("copy_of"))})
    return out


def zone_info(zone: int) -> dict:
    """第 zone 區 (1 起算) 的資料；第 6 區以後主題從頭輪"""
    zs = zones()
    return zs[(zone - 1) % len(zs)]


def treasures(zone: int) -> dict:
    """{階級: [(id, 名稱, emoji), ...]}"""
    t = _load("treasures")
    return {r: [tuple(x) for x in lst] for r, lst in t[zone_info(zone)["treasure_zone"]].items()}


def fest_treasures(fid: str) -> dict:
    """活動寶物 {階級: [(id, 名稱, emoji), ...]} (只有 SSR / UR / LR)"""
    return {r: [tuple(x) for x in lst] for r, lst in (fests().get(fid, {}).get("treasures") or {}).items()}


def treasure_info(tid: str) -> dict | None:
    """寶物 id ➔ {id, name, emoji, rarity, zone_key}；活動寶物的 zone_key = "fest:<活動 id>" """
    for zkey, by_r in _load("treasures").items():
        if zkey == "sell_price":
            continue
        for r, lst in by_r.items():
            for x in lst:
                if x[0] == tid:
                    return {"id": x[0], "name": x[1], "emoji": x[2], "rarity": r, "zone_key": zkey}
    for fid in fests():
        for r, lst in fest_treasures(fid).items():
            for x in lst:
                if x[0] == tid:
                    return {"id": x[0], "name": x[1], "emoji": x[2], "rarity": r, "zone_key": f"fest:{fid}"}
    return None


def characters() -> dict:
    """角色檔 (Characters/) ➔ {id: {name, emoji, rarities, class, base}}；沒有 ura_class 的角色不能出征"""
    from Utils.character_data import load_characters
    out = {}
    for cid, c in load_characters().items():
        if not c.get("ura_class"):
            continue
        out[cid] = {"name": c["name"], "emoji": c.get("emoji", "🎴"), "rarities": list(c["gacha"]["rarities"]),
                    "class": c["ura_class"], "base": dict(c["base_stats"]), "spell_name": c["special_powers"]["name"]}
    return out

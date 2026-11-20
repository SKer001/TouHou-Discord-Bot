"""🌀 裏世界的資料檔 (Database/ura/data/*.json)；讀一次快取，reload() 重讀"""
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


def statuses() -> dict:
    return _load("statuses")


def spells() -> dict:
    return _load("spells")


def enemies() -> dict:
    return _load("enemies")


def items() -> dict:
    return _load("items")["items"]


def category_max() -> dict:
    return _load("items")["category_max"]


def bags() -> dict:
    return {k: v for k, v in _load("items")["bags"].items() if not k.startswith("_")}


def relics() -> dict:
    return _load("relics")["relics"]


def events() -> dict:
    return _load("events")["events"]


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
        out.append({**src, **{k: z[k] for k in ("id", "name", "emoji")}, "treasure_zone": src["id"]})
    return out


def zone_info(zone: int) -> dict:
    """第 zone 區 (1 起算) 的資料；第 6 區以後主題從頭輪"""
    zs = zones()
    return zs[(zone - 1) % len(zs)]


def treasures(zone: int) -> dict:
    """{階級: [(id, 名稱, emoji), ...]}"""
    t = _load("treasures")
    return {r: [tuple(x) for x in lst] for r, lst in t[zone_info(zone)["treasure_zone"]].items()}


def treasure_info(tid: str) -> dict | None:
    """寶物 id ➔ {id, name, emoji, rarity, zone_key}"""
    for zkey, by_r in _load("treasures").items():
        if zkey == "sell_price":
            continue
        for r, lst in by_r.items():
            for x in lst:
                if x[0] == tid:
                    return {"id": x[0], "name": x[1], "emoji": x[2], "rarity": r, "zone_key": zkey}
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

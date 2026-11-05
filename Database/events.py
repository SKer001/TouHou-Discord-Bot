"""
🎪 活動資料 (Events/<id>.json) 的讀取與合併 (純資料，不碰資料庫)

活動的狀態 (進行中 / 已結束、開始與結束時間) 存在 Users.db 的 economy_meta (Economy_DB_Manager)。
這裡只負責：讀活動檔、把「進行中的活動」跟基本資料 (shrine_data) 合併成這一刻的遊戲規則。
新增活動：放一個 Events/<id>.json (格式照 th06_scarlet_mist.json)，不用改程式。
"""
import json
import os

from Database import shrine_data as base

EVENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Events")


def load_events() -> dict:
    """{活動 ID: 活動資料}；壞掉的檔案印警告後略過"""
    events = {}
    if not os.path.isdir(EVENTS_DIR):
        return events
    for filename in sorted(os.listdir(EVENTS_DIR)):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(EVENTS_DIR, filename), encoding="utf-8") as f:
                data = json.load(f)
            events[data["id"]] = data
        except (OSError, ValueError, KeyError) as e:
            print(f"⚠️ [Events] 讀取 {filename} 失敗：{e}")
    return events


def event_item_ids(event: dict) -> set[str]:
    return {item["id"] for item in event.get("items", [])}


def game_rules(active: list[dict]) -> dict:
    """
    基本資料 + 進行中的活動 ➔ 這一刻的規則：
    {"recipes", "dish_types", "locations", "guests", "event_dishes" (活動料理 ID ➔ 活動),
     "event_guests", "order_event_chance", "event_dish_bonus"}
    """
    recipes = dict(base.RECIPES)
    dish_types = dict(base.DISH_TYPES)
    locations = {k: {**v, "event": None} for k, v in base.LOCATIONS.items()}
    guests = {k: {**v, "event": None} for k, v in base.GUESTS.items()}
    event_dishes, event_guests = {}, set()
    chance, bonus = 0.0, 1.0
    for ev in active:
        recipes.update(ev.get("recipes", {}))
        for item in ev.get("items", []):
            serve = (item.get("effect") or {}).get("serve")
            if serve:
                dish_types[item["id"]] = serve
                event_dishes[item["id"]] = ev["id"]
        loc = ev.get("location")
        if loc:
            locations[loc["id"]] = {**loc, "event": ev["id"]}
        for key, g in ev.get("guests", {}).items():
            guests[key] = {**g, "event": ev["id"]}
            event_guests.add(key)
        chance = max(chance, ev.get("order_event_chance", 0.0))
        bonus = max(bonus, ev.get("event_dish_bonus", 1.0))
    return {
        "recipes": recipes, "dish_types": dish_types, "locations": locations, "guests": guests,
        "event_dishes": event_dishes, "event_guests": event_guests,
        "order_event_chance": chance, "event_dish_bonus": bonus,
    }


def all_guests() -> dict:
    """包含所有活動 (不管有沒有進行中) 的客人資料：顯示已在神社裡的活動客人時用"""
    guests = {k: {**v, "event": None} for k, v in base.GUESTS.items()}
    for ev in load_events().values():
        for key, g in ev.get("guests", {}).items():
            guests[key] = {**g, "event": ev["id"]}
    return guests

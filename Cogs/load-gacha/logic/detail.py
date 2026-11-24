"""
🔍 單卡詳情的資料 card_detail_info (卡冊 / 收藏冊 / 管理員看別人卡冊共用)
(從 Cogs/load-gacha/gacha.py 拆出來；gacha.py 會把這裡的名字全部轉出去)
"""
import importlib

from Database import Economy_DB_Manager as econ
from Database.User_DB_Manager import get_user_cards
from .rules import FUSION_COUNT, get_next_rarity, is_perfect


# ================= 🔍 單卡詳情的資料 (2026-11-23 使用者定案) =================
async def card_detail_info(card: dict, owner_id: int) -> dict:
    """
    單卡詳情 (卡冊 / 收藏冊 / 管理員看別人卡冊) 要多顯示的東西，build_card_detail_container 用：
    - "profile"：角色稱號、種族、能力、簡介 (Characters/ 的 profile)
    - "ura"：這張卡的 HP / ATK / DEF、職業、能不能出征 (跟裏世界出征一樣用 combat.make_member 算)
    - "spell"：這張卡階級那一檔的特殊能力 (效果 = ura describe.spell_text；B 點 / 冷卻 = 出征時的值)
    - "value"：分解能拿多少 (市值 × 完整度倍率 × 活動的分解倍率，跟 /market decompose 一樣)
    - "synth" / "fuse"：卡冊裡同角色同階級還有幾張能一起合成 / 湊滿幾張完美卡能融合 (收藏中、出征中的卡不算)
    """
    from Utils.character_data import load_characters
    from Database.ura import combat as ura_combat, data as ura_data, describe as ura_describe, rules as ura_rules
    cid, rarity, comp = card["character_key"], card["rarity"], float(card["completeness"])
    info = {}
    char = load_characters().get(cid) or {}
    profile = char.get("profile") or {}
    if profile:
        info["profile"] = {k: profile.get(k, "") for k in ("title", "species", "ability", "description")}
    sp = char.get("special_powers") or {}
    level = (sp.get("levels") or {}).get(rarity) or {}
    uchar = ura_data.characters().get(cid)
    if uchar and cid in ura_data.spells() and rarity in ura_rules.RARITY_MULT:
        u = ura_combat.make_member(0, card, uchar)
        info["ura"] = {"hp": ura_combat.max_hp(u), "atk": ura_describe.num(ura_combat.eff_atk(u)),
                       "def": ura_describe.num(ura_combat.eff_def(u)), "cls": ura_rules.CLASS_NAMES.get(u["cls"], u["cls"]),
                       "rarity_mult": ura_rules.RARITY_MULT[rarity], "comp_mult": ura_rules.comp_mult(comp),
                       "min": ura_rules.MIN_COMPLETENESS, "ok": comp >= ura_rules.MIN_COMPLETENESS}
        info["spell"] = {"sp_name": sp.get("name") or uchar.get("spell_name", ""), "name": level.get("name", ""),
                         "numeral": (level.get("id") or "").rsplit("_", 1)[-1], "type": level.get("type"),
                         "effect": ura_describe.spell_text(cid, u["tier"]), "b": u["b_cost"], "cd": u["cd_max"],
                         "cd_base": ura_data.spells()[cid]["cd"]}
    elif level:   # 不在裏世界資料裡的角色：照角色檔寫
        info["spell"] = {"sp_name": sp.get("name", ""), "name": level.get("name", ""),
                         "numeral": (level.get("id") or "").rsplit("_", 1)[-1], "type": level.get("type"),
                         "effect": level.get("desc", ""), "b": level.get("spent", 0), "cd": level.get("cooldown", 0),
                         "cd_base": level.get("cooldown", 0)}
    if info.get("spell"):   # ⚔️ 傷害 / 💚 治療…：跟 /character 角色頁同一份名稱 (呼叫時才取，Cog 之間不互相 import)
        names = getattr(importlib.import_module("Cogs.load-character.Components.character_components"), "SP_TYPE_NAMES", {})
        t = info["spell"]["type"]
        info["spell"]["type_name"] = names.get(t, t or "")
    rules = await econ.get_rules()
    price = econ.price_of(await econ.get_market_prices(), cid, rarity)
    mult = econ.modifier(rules, "decompose")
    info["value"] = {"price": price, "value": econ.card_value(price, comp, mult), "mult": mult}
    if not card.get("locked") and not card.get("expedition"):
        same = [c for c in await get_user_cards(owner_id)
                if c["character_key"] == cid and c["rarity"] == rarity and c["instance_id"] != card["instance_id"]]
        if is_perfect(card):
            nxt = get_next_rarity(card)
            if nxt:
                info["fuse"] = {"have": 1 + sum(1 for c in same if is_perfect(c)), "need": FUSION_COUNT, "next": nxt}
        else:
            info["synth"] = sum(1 for c in same if not is_perfect(c))
    return info

import discord
from discord import ui
from discord.ext import commands
from discord import app_commands
import importlib
import json
import os
import random
import uuid
from datetime import datetime

from Database import Economy_DB_Manager as econ
from Utils import card_cache   # autocomplete 專用的卡冊快取
from Database.User_DB_Manager import (
    get_user_cards, transform_cards, draw_gacha, get_gacha_pity, get_gacha_stats, InsufficientFunds,
    get_album_cards, set_cards_locked, auto_synthesize_cards,
)
from .Components.gacha_components import (
    STACKS_PER_PAGE,
    STACK_CARDS_PER_PAGE,
    build_gacha_single_container,
    build_gacha_ten_container,
    build_gacha_history_container,
    build_rate_sheet_container,
    build_stack_list_container,
    build_stack_cards_container,
    build_card_detail_container,
    build_album_container,
    ALBUM_PER_PAGE,
    build_synthesis_preview_container,
    build_synthesis_result_container,
    build_auto_synthesis_preview_container,
    build_auto_synthesis_result_container,
    build_fusion_preview_container,
    build_fusion_result_container,
)
from Utils.components import send_notice, notice_view, notice_container
from Utils.pagination import nav_buttons, paginate   # 📄 共用分頁
from Utils.gacha_pools import GACHA_POOLS, load_gacha_pool
from Database.events import pool_open_events   # 🎪 event_only 卡池 (紅魔鄉) 是哪個活動開放的
from Utils.numbers import fmt_money   # 持有金額一萬以上縮寫 (1.5M)
from Utils.guide import open_guide

# 📦 這個檔案只留 GachaCardSys 指令與 setup；規則拆在 logic/、畫面拆在 views/，這裡把它們的名字全部轉出來
#    (Admin-gacha.py、市場、稱號、教學書、tools、測試照舊從這個模組拿 GACHA_POOL、DRAW_COST、InventoryView、roll_pool_cards…)：
#    - logic/rules.py      卡池資料 (GACHA_POOL、THUMBNAILS)、⛩️ 祈願規則、⚗️ 合成 / 🔮 融合規則、📊 機率表的資料計算
#    - logic/detail.py     🔍 單卡詳情的資料 card_detail_info
#    - views/synthesis.py  CardActionConfirmView、SynthesisPickerView
#    - views/inventory.py  InventoryView、AlbumView、角色圖鑑頁 send_character_page
#    - views/result.py     GachaResultView、EventPoolPickerView、GachaHistoryView、機率表的送出 send_rate_sheet
#
# ⚠️ 對這個模組的屬性賦值 (例如測試寫 gacha.DRAW_COST = 1) 會一起改到「本來就有這個名字」的子模組，所以跟拆開前一樣會生效
#    (跟 Cogs/load-ura/ura.py、Database/User_DB_Manager.py 同一套做法)。新增子模組要加進下面的 _PARTS (照依賴順序)，
#    也要加進 Utils/reloader.py 的 VIEW_ORDER。子模組不要定義 setup、GachaCardSys 這兩個名字 (會被最下面的蓋掉 / 蓋掉最下面的)。
import sys
import types

from .logic import rules as _l_rules, detail as _l_detail
from .views import synthesis as _v_synthesis, inventory as _v_inventory, result as _v_result

_PARTS = (_l_rules, _l_detail, _v_synthesis, _v_inventory, _v_result)   # 依賴順序

for _part in _PARTS:
    globals().update({_k: _v for _k, _v in vars(_part).items() if not _k.startswith("__")})
del _part


class _EntryModule(types.ModuleType):
    """gacha.X = 值 ➔ 入口自己改，子模組裡同名的也一起改 (函式是在子模組的命名空間裡找名字的)"""

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name.startswith("__"):
            return
        for part in self.__dict__.get("_PARTS", ()):
            if name in vars(part):
                setattr(part, name, value)


sys.modules[__name__].__class__ = _EntryModule


# ================= 🎴 Cog 類別 =================
class GachaCardSys(commands.GroupCog, group_name="card", group_description="東方角色卡牌收集與合成系統"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def generate_completeness(self) -> float:
        val = (random.gauss(0, 0.35)) ** 2
        return round(max(0.001, min(1.000, val)), 4)

    async def execute_gacha(self, interaction: discord.Interaction, draw_count: int, pool_key: str) -> bool:
        """祈願；畫面換成抽卡結果 ➔ True (選卡池的畫面用來判斷要不要停掉)，沒抽 (沒開放、賽錢不足、跳選單) ➔ False"""
        await interaction.response.defer()

        # 活動的機率提升、祈願價格倍率、活動限定卡池都在 rules
        rules = await econ.get_rules()
        user_id = interaction.user.id
        cost_mult = rules["modifiers"].get("gacha_cost", 1.0)
        total_cost = draw_cost(draw_count, cost_mult)
        pools = event_pools(rules)
        if pool_key == EVENT_POOL and len(pools) > 1:   # 🎪 同時有好幾個活動卡池 ➔ 先選要抽哪個
            picker = EventPoolPickerView(user_id, self, draw_count, pools, total_cost, interaction)
            if interaction.type == discord.InteractionType.component:
                await interaction.edit_original_response(view=picker)
            else:
                await interaction.followup.send(view=picker)
            return False
        resolved = resolve_pool(pool_key, rules)   # event_only 的卡池 (th06) 也只有活動期間抽得到
        if not resolved:
            await send_notice(interaction, "🎪 目前沒有進行中的活動卡池。")
            return False
        pool_key, pool_name = resolved

        # 卡池沒有角色時直接中止
        if not pool_characters(pool_key, rules):
            await send_notice(interaction, "❌ 這個卡池目前沒有任何角色，暫時無法祈願，請聯絡管理員。")
            return False

        # 扣款、擲卡 (含保底)、寫入卡牌與統計全部在同一個交易 (活動卡池的保底跟一般卡池分開算)
        try:
            result = await draw_gacha(
                user_id, pool_key, draw_count, total_cost,
                lambda since_ur: roll_pool_cards(pool_key, draw_count, since_ur, self.generate_completeness, rules),
                # 活動卡池：每張卡的預期抽數另外記，浮動市值才算得到 (一般卡池照舊用卡池抽數 × 機率)
                #  (活動開放的一般卡池 th06 不用：它本來就有卡池抽數 × 機率)
                expected=expected_cards(pool_key, draw_count, rules) if pool_key.startswith(f"{EVENT_POOL}_") else None,
                # 🎪 活動任務 gacha_event_pool 只算開這個卡池的活動 (別的活動的卡池不算)
                quest_events=list(pools[pool_key]["events"]) if pool_key in pools else None,
            )
        except InsufficientFunds as e:
            msg = f"❌ **賽錢不足！**\n祈願需要 `{total_cost:,}` 賽錢，但你的口袋裡只有 `{fmt_money(e.money)}` 賽錢...\n*靈夢看了看空蕩蕩的賽錢箱，無奈地把你請出了神社。*"
            await send_notice(interaction, msg)
            return False

        results = result["cards"]
        if PITY_RARITY in pool_holders(pool_key, rules):   # 卡池沒有 UR 就沒有保底
            next_ur = rate_text(next_ur_rate(pool_key, result["since_ur"], rules))
            pity_text = (f"🎯 保底：`{result['since_ur']} / {PITY_THRESHOLD}` · 下一抽 {PITY_RARITY} `{next_ur}`"
                         f" · 本池累計 `{result['pool_draws']:,}` 抽")
        else:
            pity_text = f"🎯 這個卡池沒有 {PITY_RARITY}，沒有保底 · 本池累計 `{result['pool_draws']:,}` 抽"
        if any(c.get("pity") for c in results):
            pity_text = f"🎯 **觸發保底！必定獲得 {PITY_RARITY}！**\n" + pity_text

        if draw_count == 1:
            container = build_gacha_single_container(
                results[0], interaction.user.display_name, total_cost, THUMBNAILS, pool_name, pity_text
            )
        else:
            container = build_gacha_ten_container(
                results, interaction.user.display_name, total_cost, THUMBNAILS, pool_name, pity_text
            )

        view = GachaResultView(user_id, interaction.user.display_name, self, container, pool_key, cost_mult)

        if interaction.type == discord.InteractionType.component:
            await interaction.edit_original_response(view=view)
        else:
            await interaction.followup.send(view=view)
        return True

    @app_commands.command(name="gacha", description="⛩️ 博麗神社祈願：消耗賽錢抽取角色卡牌")
    @app_commands.describe(pool="要祈願的卡池 (依作品代數劃分)", pull_type="單抽或十連")
    @app_commands.choices(
        pool=[app_commands.Choice(name=f"{p['name']} ({p['desc']})", value=key) for key, p in GACHA_POOLS.items()
              if not p.get("event_only")]   # 紅魔鄉 (event_only) 只在活動期間從「🎪 活動限定卡池」抽
             + [app_commands.Choice(name="🎪 活動限定卡池 (活動期間才開放)", value=EVENT_POOL)],
        pull_type=[
            app_commands.Choice(name=f"單次祈願 ({DRAW_COST:,} 賽錢)", value=1),
            app_commands.Choice(name=f"十連祈願 ({DRAW_COST * 10:,} 賽錢)", value=10),
        ],
    )
    async def gacha_card(self, interaction: discord.Interaction, pool: app_commands.Choice[str], pull_type: app_commands.Choice[int]):
        await self.execute_gacha(interaction, pull_type.value, pool.value)

    @app_commands.command(name="history", description="📜 查看各卡池的祈願次數與保底進度")
    async def history(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        pity = await get_gacha_pity(user_id)
        stats = await get_gacha_stats(user_id)
        pools = dict(GACHA_POOLS)
        rules = await econ.get_rules()
        for key, ep in event_pools(rules).items():   # 進行中的活動卡池全部列出來 (保底跟一般卡池分開算)
            if key not in pools:
                pools[key] = {"name": ep["name"]}
        notes = {key: open_note(key) for key in pools if open_note(key)}   # 紅魔鄉：🎪 紅霧異變期間開放
        drawable = {key: p for key, p in pools.items() if resolve_pool(key, rules)}   # 📊 機率表選單只列現在抽得到的
        next_rates = {   # 下一抽 UR 的機率；卡池沒有 UR ➔ None
            key: rate_text(next_ur_rate(key, pity.get(key, {}).get("since_ur", 0), rules))
                 if PITY_RARITY in pool_holders(key, rules) else None
            for key in pools
        }
        container = build_gacha_history_container(
            interaction.user.display_name, pools, pity, stats, PITY_THRESHOLD, PITY_RARITY, next_rates, notes
        )
        await interaction.response.send_message(view=GachaHistoryView(container, drawable))

    @app_commands.command(name="inventory", description="🎒 查看個人的博麗神社卡冊與持有卡牌")
    async def view_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        cards = await get_user_cards(user_id)

        if not cards:
            await send_notice(interaction, "🎒 你的卡冊空空如也，快去使用 `/card gacha` 進行第一次祈願吧！")
            return

        view = InventoryView(user_id, sort_cards(cards), interaction.user.display_name, self,
                             owned_keys=await owned_character_keys(user_id))
        await interaction.followup.send(view=view)

    @app_commands.command(name="album", description="🔒 收藏冊：收進來的卡不會被合成、融合、分解或上架")
    async def view_album(self, interaction: discord.Interaction):
        cards = await get_album_cards(interaction.user.id)
        view = AlbumView(interaction.user.id, interaction.user.display_name, cards)
        await interaction.response.send_message(view=view)

    # ---------------- 共用：代數 / 角色 autocomplete ----------------
    def _pool_label(self, pool_key: str) -> str:
        return GACHA_POOLS[pool_key]["name"] if pool_key in GACHA_POOLS else "📦 其他 (已不在卡池)"

    def _pool_choices(self, groups: dict, current: str) -> list[app_commands.Choice[str]]:
        """groups = {(角色, 階級): [卡...]}；依代數彙整成選項"""
        counts = {}
        for cards in groups.values():
            pool_key = card_pool_key(cards[0])
            counts[pool_key] = counts.get(pool_key, 0) + 1
        choices = []
        for pool_key, count in counts.items():
            label = self._pool_label(pool_key)
            if current.lower() in f"{pool_key} {label}".lower():
                choices.append(app_commands.Choice(name=f"{label} · {count} 組可用", value=pool_key))
        return choices[:AUTOCOMPLETE_LIMIT]

    def _character_choices(self, groups: dict, pool_key: str | None, current: str) -> list[app_commands.Choice[str]]:
        """依已選的代數列出有可用組合的角色"""
        owned = {}
        for (char_key, _), cards in groups.items():
            if card_pool_key(cards[0]) != pool_key:
                continue
            entry = owned.setdefault(char_key, {"name": cards[0]["name"], "emoji": cards[0].get("emoji", "🎴"), "count": 0})
            entry["count"] += len(cards)
        current = current.strip().lower()
        return [
            app_commands.Choice(name=f"{e['emoji']} {e['name']} ({key}) · {e['count']} 張可用"[:100], value=key)
            for key, e in owned.items()
            if not current or current in key.lower() or current in e["name"].lower()
        ][:AUTOCOMPLETE_LIMIT]

    # ---------------- ⚗️ 合成 ----------------
    async def synthesis_pool_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._pool_choices(find_synthesis_groups(await card_cache.cached_user_cards(interaction.user.id)), current)

    async def synthesis_character_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        groups = find_synthesis_groups(await card_cache.cached_user_cards(interaction.user.id))
        return self._character_choices(groups, getattr(interaction.namespace, "pool", None), current)

    async def make_synthesis_view(self, user_id: int, user_name: str, card1: str, card2: str):
        """建立合成確認畫面；卡牌不存在或條件不符時回傳錯誤訊息 (str)"""
        cards = {c["instance_id"]: c for c in await get_user_cards(user_id)}
        card_a, card_b = cards.get(card1), cards.get(card2)
        if card_a is None or card_b is None:
            return "❌ 找不到指定的卡牌，可能已經被合成或融合掉了。"
        if not can_synthesize(card_a, card_b):
            return "❌ **無法合成！**\n合成需要兩張「不同的」、「同角色」、「同階級」的卡牌，且完整度都未達 `1.0000`。"

        preview = calc_synthesis(card_a["completeness"], card_b["completeness"], card_a["rarity"])
        container = build_synthesis_preview_container(card_a, card_b, preview, user_name, THUMBNAILS)

        def build_new_card(consumed: list) -> dict:
            a, b = consumed
            if not can_synthesize(a, b):
                raise ValueError("卡牌狀態已改變，無法合成")
            result = roll_synthesis(a["completeness"], b["completeness"], a["rarity"])
            return {**synthesized_card(a, result["new_completeness"]), "_result": result}

        async def on_confirm(_interaction: discord.Interaction):
            try:
                _, new_card = await transform_cards(user_id, [card1, card2], build_new_card, count_synthesis=True)
            except ValueError as e:
                return f"❌ **合成失敗**：{e}\n-# 卡牌沒有任何變動。"
            result = new_card.pop("_result")
            return build_synthesis_result_container(new_card, result["increase"], result["doubled"], user_name, THUMBNAILS)

        return CardActionConfirmView(user_id, user_name, self, container, on_confirm, "⚗️ 確認合成",
                                     continue_character=card_a["character_key"])

    async def make_auto_synthesis_view(self, user_id: int, user_name: str, character_key: str):
        """⚡ 自動合成全部的確認畫面 (這位角色每個階級各自合)；沒有可以合的卡 ➔ 錯誤訊息 (str)"""
        cards = [c for c in await get_user_cards(user_id) if c["character_key"] == character_key]
        preview = auto_synthesis_preview(cards)
        if not preview:
            return "❌ 這位角色已經沒有可以合成的卡了 (同一個階級至少要兩張未滿 `1.0000` 的卡)。"
        sample = cards[0]
        container = build_auto_synthesis_preview_container(sample, preview, user_name, THUMBNAILS)

        def run(current: list) -> dict:   # 在交易裡，用當下的卡重算；跟確認畫面不一樣就整筆不做
            if auto_synthesis_preview(current) != preview:
                raise ValueError("卡牌跟確認畫面不一樣了 (有卡被用掉、收進收藏冊或新抽到)，請回到選卡畫面重新按「⚡ 自動合成全部」")
            return run_auto_synthesis(current)

        async def on_confirm(_interaction: discord.Interaction):
            try:
                result = await auto_synthesize_cards(user_id, character_key, run)
            except ValueError as e:
                return f"❌ **自動合成沒有執行**：{e}\n-# 卡牌沒有任何變動。"
            return build_auto_synthesis_result_container(sample, result, user_name, THUMBNAILS)

        # 自動合成完只留「🎒 查看卡庫」(失敗時才有「⚗️ 繼續合成」回選卡畫面)
        return CardActionConfirmView(user_id, user_name, self, container, on_confirm, "⚡ 確認自動合成",
                                     continue_character=character_key, continue_on_success=False)

    @app_commands.command(name="synthesis", description="⚗️ 合成卡牌：兩張同角色、同階級的卡合成一張完整度更高的卡")
    @app_commands.describe(pool="代數 (只列出有可合成卡牌的)", character="角色 (只列出該代數中有可合成卡牌的)")
    @app_commands.autocomplete(pool=synthesis_pool_autocomplete, character=synthesis_character_autocomplete)
    async def synthesis(self, interaction: discord.Interaction, pool: str, character: str):
        user_id = interaction.user.id
        # 使用者也可能不透過 autocomplete 直接輸入，所以這裡一樣要檢查
        cards = [
            c for group in find_synthesis_groups(await get_user_cards(user_id)).values() for c in group
            if c["character_key"] == character and card_pool_key(c) == pool
        ]
        if not cards:
            await send_notice(interaction, "❌ **無法合成！**\n這個角色沒有可以合成的卡牌：合成需要兩張「同角色」、「同階級」且完整度都未達 `1.0000` 的卡牌。")
            return
        view = SynthesisPickerView(user_id, interaction.user.display_name, self, character, cards)
        await interaction.response.send_message(view=view)

    # ---------------- 🔮 融合 ----------------
    async def fusion_pool_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._pool_choices(find_fusion_groups(await card_cache.cached_user_cards(interaction.user.id)), current)

    async def fusion_character_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        groups = find_fusion_groups(await card_cache.cached_user_cards(interaction.user.id))
        return self._character_choices(groups, getattr(interaction.namespace, "pool", None), current)

    async def fusion_rarity_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """依已選的角色列出可以融合的階級 (每個角色最多 2 個)"""
        char_key = getattr(interaction.namespace, "character", None)
        groups = find_fusion_groups(await card_cache.cached_user_cards(interaction.user.id))
        choices = []
        for (key, rarity), group in sorted(groups.items(), key=lambda kv: RARITY_ORDER.get(kv[0][1], 0)):
            if key != char_key or current.upper() not in rarity:
                continue
            name = f"[{rarity} → {get_next_rarity(group[0])}] · 持有 {len(group)} 張 1.0000"
            choices.append(app_commands.Choice(name=name, value=rarity))
        return choices

    @app_commands.command(name="fusion", description="🔮 融合卡牌：三張同角色、同階級且完整度 1.0000 的卡融合成高一階的卡")
    @app_commands.describe(
        pool="代數 (只列出有可融合卡牌的)",
        character="角色 (只列出該代數中有可融合卡牌的)",
        rarity="要融合的階級 (只列出符合條件的)",
    )
    @app_commands.autocomplete(pool=fusion_pool_autocomplete, character=fusion_character_autocomplete, rarity=fusion_rarity_autocomplete)
    async def fusion(self, interaction: discord.Interaction, pool: str, character: str, rarity: str):
        result = await self.make_fusion_view(interaction.user.id, interaction.user.display_name, character, rarity, pool)
        if isinstance(result, str):
            await send_notice(interaction, result)
            return
        await interaction.response.send_message(view=result)

    async def make_fusion_view(self, user_id: int, user_name: str, char_key: str, rarity: str, pool: str | None = None):
        """建立融合確認畫面；條件不符時回傳錯誤訊息 (str)。pool 有給時會一併檢查卡池"""
        group = find_fusion_groups(await get_user_cards(user_id)).get((char_key, rarity))
        if not group or (pool is not None and card_pool_key(group[0]) != pool):
            return (f"❌ **無法融合！**\n融合需要 **{FUSION_COUNT}** 張「同角色」、「同階級」且完整度 `1.0000` 的卡牌，"
                    f"而且該角色必須還有更高的階級。")

        materials = group[:FUSION_COUNT]   # 滿完整度的卡都一樣，取最早獲得的三張
        material_ids = [c["instance_id"] for c in materials]
        next_rarity = get_next_rarity(materials[0])
        next_title = GACHA_POOL[char_key]["titles"][next_rarity]
        container = build_fusion_preview_container(materials, next_rarity, next_title, user_name, THUMBNAILS)

        def build_new_card(consumed: list) -> dict:
            base = consumed[0]
            if not all(
                is_perfect(c) and c["character_key"] == base["character_key"] and c["rarity"] == base["rarity"]
                for c in consumed
            ):
                raise ValueError("卡牌狀態已改變，無法融合")
            new_rarity = get_next_rarity(base)
            if new_rarity is None:
                raise ValueError("這張卡已經是最高階級")
            char_data = GACHA_POOL[base["character_key"]]
            return {
                "instance_id": f"c_{char_data['uuid'][:4]}_{uuid.uuid4().hex[:12]}",
                "character_key": base["character_key"],
                "name": char_data["name"],
                "emoji": char_data["emoji"],
                "rarity": new_rarity,
                "title": char_data["titles"][new_rarity],
                "completeness": self.generate_completeness(),
                "obtained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        async def on_confirm(_interaction: discord.Interaction):
            try:
                _, new_card = await transform_cards(user_id, material_ids, build_new_card, count_fusion=True)
            except ValueError as e:
                return f"❌ **融合失敗**：{e}\n-# 卡牌沒有任何變動。"
            return build_fusion_result_container(new_card, rarity, user_name, THUMBNAILS)

        return CardActionConfirmView(user_id, user_name, self, container, on_confirm, "🔮 確認融合")

    @app_commands.command(name="help", description="📖 教學書：抽卡、卡冊、合成與融合的玩法與指令 (只有自己看得到)")
    async def help_book(self, interaction: discord.Interaction):
        await open_guide(interaction, "card")


async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCardSys(bot))

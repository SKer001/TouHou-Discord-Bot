"""
💹 /market (市值、分解、上架、購買、我的上架)；轉帳 /trade 在 Cogs/load-general/trade.py
規則與數值在 Database/Economy_DB_Manager.py；卡池資料用 importlib 從抽卡模組取 (reload 後拿到新版)
"""
import importlib
import re
from datetime import datetime, timezone

import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Database.User_DB_Manager import get_user_cards
from Utils import card_cache   # autocomplete 專用的卡冊快取
from Utils.components import send_notice
from .Components.market_components import (
    build_price_container, build_listing_lines, card_label, short_id, simple_container,
    build_listing_announce,
)

AUTOCOMPLETE_LIMIT = 25
PICK_PER_PAGE = 20        # 選單一次最多 25 個選項，留一點餘裕
LISTINGS_PER_PAGE = 10
VALUE_SAMPLES = (1.0, 0.5, 0.1)   # /market price 顯示這幾個完整度的價值


def gacha_mod():
    return importlib.import_module("Cogs.load-gacha.gacha")


def card_probabilities() -> dict:
    """{(角色, 階級): (卡池, 單抽抽中機率)}：卡池內角色平均抽，階級照 RARITY_WEIGHTS"""
    g = gacha_mod()
    pools = {}
    for key, data in g.GACHA_POOL.items():
        pools.setdefault(data["pool"], []).append(key)
    total = sum(g.RARITY_WEIGHTS)
    probs = {}
    for pool, keys in pools.items():
        for key in keys:
            for i, rarity in enumerate(g.GACHA_POOL[key]["rarities"]):
                probs[(key, rarity)] = (pool, g.RARITY_WEIGHTS[i] / total / len(keys))
    return probs


def resolve_pool(value: str | None) -> str | None:
    """卡池參數：正常是 key；Discord 偶爾會把 autocomplete 的顯示名稱整串送進來，這時從名稱反查"""
    g = gacha_mod()
    if not value or value in g.GACHA_POOLS:
        return value
    for key, p in g.GACHA_POOLS.items():
        if value.startswith(p["name"]) or f"({key})" in value:
            return key
    return value


def resolve_character(value: str | None) -> str | None:
    """角色參數：正常是 key；收到顯示名稱 (例如「🧸 愛麗絲 (alice) · 5 張」) 時取括號裡的 key"""
    g = gacha_mod()
    if not value or value in g.GACHA_POOL:
        return value
    for m in re.findall(r"\(([A-Za-z0-9_]+)\)", value):
        if m in g.GACHA_POOL:
            return m
    return value


def pick_label(card: dict) -> str:
    """選單上的卡：同角色同完整度的卡會長得一樣，所以加上 ID 區分"""
    return f"{card_label(card)} #{short_id(card['instance_id'])}"[:100]


async def prepare_market():
    """每個市場指令開頭：補結算市值、下架過期的卡"""
    await econ.settle_prices(card_probabilities())
    await econ.expire_listings()
    await econ.get_rules()   # 更新活動的手續費倍率 (畫面上的買家價格)


def reason_text(r: dict, status: dict | None = None) -> str:
    reason = r.get("reason")
    if reason == "locked":
        n = status["daily_count"] if status else 0
        return f"🔒 累積簽到 `{econ.TRADE_UNLOCK_DAILY}` 天才能使用市場與轉帳（目前 `{n}` 天）。\n-# 分解卡牌不受限制。"
    return {
        "target_locked": f"🔒 對方還沒開通交易（要累積簽到 `{econ.TRADE_UNLOCK_DAILY}` 天）。",
        "not_found": "❌ 這張卡已經賣出或下架了。",
        "own": "❌ 不能買自己上架的卡。",
        "expired": "❌ 這張卡已經超過 7 天，下架了。",
        "not_enough": f"❌ 賽錢不足！需要 `{r.get('total', r.get('amount', 0)):,}`，你只有 `{r.get('money', 0):,}`。",
        "limit": f"❌ 超過今天的轉帳額度！今天還能轉 `{r.get('left', 0):,}` 賽錢。",
        "self": "❌ 不能轉給自己。",
        "bad_amount": "❌ 金額要大於 0。",
        "bad_price": "❌ 價格要大於 0。",
    }.get(reason, f"❌ 操作失敗（{reason}）")


def _expires_ts(listing: dict) -> int:
    return int((datetime.fromisoformat(listing["listed_at"]) + econ.LISTING_DURATION).timestamp())


# =========================================================
# 共用：只有本人能操作的 View
# =========================================================
class OwnerView(ui.LayoutView):
    def __init__(self, user_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_notice(interaction, "❌ 這不是你的畫面！")
            return False
        return True

    def _nav(self, page: int, pages: int):
        prev = ui.Button(label="◀️", style=discord.ButtonStyle.secondary, disabled=pages <= 1)
        prev.callback = self.on_prev
        label = ui.Button(label=f"{page} / {pages}", style=discord.ButtonStyle.secondary, disabled=True)
        nxt = ui.Button(label="▶️", style=discord.ButtonStyle.secondary, disabled=pages <= 1)
        nxt.callback = self.on_next
        return prev, label, nxt

    async def on_prev(self, interaction):
        self.page = self.page - 1 if self.page > 1 else self.pages
        await self.refresh(interaction)

    async def on_next(self, interaction):
        self.page = self.page + 1 if self.page < self.pages else 1
        await self.refresh(interaction)

    async def refresh(self, interaction):
        self.build()
        await interaction.response.edit_message(view=self)


# =========================================================
# ♻️ 分解：分頁多選 ➔ 確認 ➔ 結果
# =========================================================
class DecomposeView(OwnerView):
    def __init__(self, user_id: int, cards: list[dict], prices: dict, mult: float = 1.0):
        super().__init__(user_id)
        self.cards = sorted(cards, key=lambda c: (c["rarity"], -c["completeness"]))
        self.values = {c["instance_id"]: econ.card_value(econ.price_of(prices, c["character_key"], c["rarity"]), c["completeness"], mult)
                       for c in cards}
        self.selected: set[str] = set()
        self.page, self.mode, self.result = 1, "pick", None
        self.build()

    @property
    def pages(self):
        return max(1, -(-len(self.cards) // PICK_PER_PAGE))

    def _page_cards(self):
        start = (self.page - 1) * PICK_PER_PAGE
        return self.cards[start:start + PICK_PER_PAGE]

    def build(self):
        self.clear_items()
        total = sum(self.values[i] for i in self.selected)
        if self.mode == "done":
            r = self.result
            lines = [f"- {card_label(c)} ➔ `{c['value']:,}`" for c in r["cards"][:15]]
            if len(r["cards"]) > 15:
                lines.append(f"…另外 `{len(r['cards']) - 15}` 張")
            self.add_item(simple_container(
                f"## ♻️ 分解完成\n" + "\n".join(lines) +
                f"\n\n💰 獲得 `{r['total']:,}` 賽錢，目前持有 `{r['money']:,}` 賽錢", discord.Color.green()))
            return
        if self.mode == "confirm":
            chosen = [c for c in self.cards if c["instance_id"] in self.selected]
            lines = [f"- {card_label(c)} ➔ `{self.values[c['instance_id']]:,}`" for c in chosen[:15]]
            if len(chosen) > 15:
                lines.append(f"…另外 `{len(chosen) - 15}` 張")
            container = simple_container(
                f"## ♻️ 確認分解 `{len(chosen)}` 張卡\n" + "\n".join(lines) +
                f"\n\n💰 共可獲得 `{total:,}` 賽錢\n-# ⚠️ 分解後卡牌會消失，無法復原；實際金額以確認當下的市值為準", discord.Color.orange())
            ok = ui.Button(label="♻️ 確認分解", style=discord.ButtonStyle.danger)
            ok.callback = self.on_confirm
            back = ui.Button(label="↩️ 返回", style=discord.ButtonStyle.secondary)
            back.callback = self.on_back
            container.add_item(ui.ActionRow(ok, back))
            self.add_item(container)
            return

        page_cards = self._page_cards()
        container = simple_container(
            f"## ♻️ 分解卡牌\n依「市值 × 完整度倍率」換成賽錢（可以跨頁多選）\n"
            f"已選 `{len(self.selected)}` 張，共 `{total:,}` 賽錢", discord.Color.teal())
        select = ui.Select(
            placeholder="選擇要分解的卡（本頁）…", min_values=0, max_values=len(page_cards),
            options=[
                discord.SelectOption(
                    label=pick_label(c), value=c["instance_id"], default=c["instance_id"] in self.selected,
                    description=f"價值 {self.values[c['instance_id']]:,} 賽錢 · 取得 {c.get('obtained_at') or '?'}"[:100],
                ) for c in page_cards
            ],
        )
        select.callback = self.on_select
        container.add_item(ui.ActionRow(select))
        go = ui.Button(label=f"♻️ 分解選取的 {len(self.selected)} 張", style=discord.ButtonStyle.danger, disabled=not self.selected)
        go.callback = self.on_go
        container.add_item(ui.ActionRow(*self._nav(self.page, self.pages), go))
        self.add_item(container)

    async def on_select(self, interaction):
        page_ids = {c["instance_id"] for c in self._page_cards()}
        self.selected = (self.selected - page_ids) | set(interaction.data.get("values", []))
        await self.refresh(interaction)

    async def on_go(self, interaction):
        self.mode = "confirm"
        await self.refresh(interaction)

    async def on_back(self, interaction):
        self.mode = "pick"
        await self.refresh(interaction)

    async def on_confirm(self, interaction):
        try:
            self.result = await econ.decompose_cards(self.user_id, list(self.selected))
        except ValueError as e:
            await send_notice(interaction, f"❌ {e}，請重新打開分解畫面。")
            return
        self.mode = "done"
        await self.refresh(interaction)


# =========================================================
# 🏷️ 上架：分頁單選 ➔ 確認 ➔ 結果
# =========================================================
class SellView(OwnerView):
    def __init__(self, user_id: int, cards: list[dict], prices: dict, price: int, user_name: str = "", thumbnails: dict | None = None):
        super().__init__(user_id)
        self.user_name, self.thumbnails = user_name, thumbnails
        self.cards = sorted(cards, key=lambda c: (c["rarity"], -c["completeness"]))
        self.prices, self.price = prices, price
        self.chosen, self.page, self.mode, self.result = None, 1, "pick", None
        self.build()

    @property
    def pages(self):
        return max(1, -(-len(self.cards) // PICK_PER_PAGE))

    def _value(self, c):
        return econ.card_value(econ.price_of(self.prices, c["character_key"], c["rarity"]), c["completeness"])

    def build(self):
        self.clear_items()
        if self.mode == "done":
            l = self.result["listing"]
            self.add_item(simple_container(
                f"## 🏷️ 上架成功\n{card_label(l)}\n售價 `{self.price:,}`（買家付 `{econ.buyer_total(self.price):,}`）\n"
                f"-# ⌛ <t:{_expires_ts(l)}:R>沒賣出會自動下架，退回卡冊；用 `/market mine` 可以自己下架", discord.Color.green()))
            return
        if self.mode == "confirm":
            c = self.chosen
            container = simple_container(
                f"## 🏷️ 確認上架\n{pick_label(c)}\n"
                f"你的售價 `{self.price:,}` 賽錢（賣出後全額入帳）\n"
                f"買家要付 `{econ.buyer_total(self.price):,}`（售價 × {1 + econ.market_fee_rate():g}）\n"
                f"參考市值 `{self._value(c):,}`\n-# 確認後會在頻道公開上架公告；上架中的卡不能合成、融合、分解；7 天沒賣出自動下架", discord.Color.orange())
            ok = ui.Button(label="🏷️ 確認上架", style=discord.ButtonStyle.success)
            ok.callback = self.on_confirm
            back = ui.Button(label="↩️ 返回", style=discord.ButtonStyle.secondary)
            back.callback = self.on_back
            container.add_item(ui.ActionRow(ok, back))
            self.add_item(container)
            return
        start = (self.page - 1) * PICK_PER_PAGE
        page_cards = self.cards[start:start + PICK_PER_PAGE]
        container = simple_container(f"## 🏷️ 上架到市場\n售價 `{self.price:,}` 賽錢，選一張要賣的卡：", discord.Color.teal())
        select = ui.Select(placeholder="選擇要上架的卡…", options=[
            discord.SelectOption(label=pick_label(c), value=c["instance_id"],
                                 description=f"參考市值 {self._value(c):,} · 取得 {c.get('obtained_at') or '?'}"[:100])
            for c in page_cards
        ])
        select.callback = self.on_select
        container.add_item(ui.ActionRow(select))
        container.add_item(ui.ActionRow(*self._nav(self.page, self.pages)))
        self.add_item(container)

    async def on_select(self, interaction):
        iid = interaction.data["values"][0]
        self.chosen = next(c for c in self.cards if c["instance_id"] == iid)
        self.mode = "confirm"
        await self.refresh(interaction)

    async def on_back(self, interaction):
        self.mode = "pick"
        await self.refresh(interaction)

    async def on_confirm(self, interaction):
        r = await econ.list_card(self.user_id, self.chosen["instance_id"], self.price)
        if not r["ok"]:
            await send_notice(interaction, reason_text(r, await econ.get_trade_status(self.user_id)))
            return
        self.result, self.mode = r, "done"
        await self.refresh(interaction)
        l = r["listing"]
        announce = ui.LayoutView()
        announce.add_item(build_listing_announce(self.user_name, l, econ.buyer_total(l["price"]), _expires_ts(l), self.thumbnails))
        try:   # 上架要公開：在頻道發一則所有人看得到的公告
            await interaction.followup.send(view=announce)
        except discord.HTTPException:
            pass


# =========================================================
# 🛒 瀏覽 / 購買、📋 我的上架 (下架)
# =========================================================
class ListingsView(OwnerView):
    """mode="buy"：瀏覽市場買卡；mode="mine"：自己的上架，可以下架"""

    def __init__(self, user_id: int, listings: list[dict], kind: str, title: str):
        super().__init__(user_id)
        self.kind, self.title = kind, title
        self.listings = listings
        for l in self.listings:
            l["expires_ts"] = _expires_ts(l)
        self.chosen, self.page, self.mode, self.notice = None, 1, "list", None
        self.build()

    @property
    def pages(self):
        return max(1, -(-len(self.listings) // LISTINGS_PER_PAGE))

    def build(self):
        self.clear_items()
        if self.mode == "confirm":
            l = self.chosen
            if self.kind == "buy":
                text = (f"## 🛒 確認購買\n{card_label(l)}\n*{l.get('title') or ''}*\n"
                        f"要付 `{econ.buyer_total(l['price']):,}` 賽錢（售價 `{l['price']:,}` × {1 + econ.market_fee_rate():g}）")
                label, style = "🛒 確認購買", discord.ButtonStyle.success
            else:
                text = f"## 📋 確認下架\n{card_label(l)}\n售價 `{l['price']:,}`\n-# 下架後卡會回到你的卡冊"
                label, style = "📤 確認下架", discord.ButtonStyle.danger
            container = simple_container(text, discord.Color.orange())
            ok = ui.Button(label=label, style=style)
            ok.callback = self.on_confirm
            back = ui.Button(label="↩️ 返回", style=discord.ButtonStyle.secondary)
            back.callback = self.on_back
            container.add_item(ui.ActionRow(ok, back))
            self.add_item(container)
            return

        start = (self.page - 1) * LISTINGS_PER_PAGE
        page_items = self.listings[start:start + LISTINGS_PER_PAGE]
        head = f"{self.notice}\n\n" if self.notice else ""
        body = build_listing_lines(page_items, econ.buyer_total, self.user_id if self.kind == "buy" else None) or "目前沒有上架中的卡。"
        container = simple_container(f"{head}## {self.title}\n{body}", discord.Color.teal())
        if page_items:
            select = ui.Select(
                placeholder="選擇要購買的卡…" if self.kind == "buy" else "選擇要下架的卡…",
                options=[discord.SelectOption(label=f"{start + i}. {card_label(l)}"[:100], value=str(l["listing_id"]),
                                              description=f"售價 {econ.buyer_total(l['price']) if self.kind == 'buy' else l['price']:,} 賽錢")
                         for i, l in enumerate(page_items, 1)])
            select.callback = self.on_select
            container.add_item(ui.ActionRow(select))
        container.add_item(ui.ActionRow(*self._nav(self.page, self.pages)))
        self.add_item(container)

    async def on_select(self, interaction):
        lid = int(interaction.data["values"][0])
        self.chosen = next(l for l in self.listings if l["listing_id"] == lid)
        self.mode = "confirm"
        await self.refresh(interaction)

    async def on_back(self, interaction):
        self.mode, self.notice = "list", None
        await self.refresh(interaction)

    async def on_confirm(self, interaction):
        l = self.chosen
        if self.kind == "buy":
            r = await econ.buy_listing(self.user_id, l["listing_id"])
            if not r["ok"]:
                await send_notice(interaction, reason_text(r, await econ.get_trade_status(self.user_id)))
                return
            self.notice = f"✅ 買到了 {card_label(l)}！付了 `{r['total']:,}` 賽錢，剩下 `{r['money']:,}`。"
        else:
            r = await econ.cancel_listing(self.user_id, l["listing_id"])
            if not r["ok"]:
                await send_notice(interaction, reason_text(r))
                return
            self.notice = f"📤 已下架 {card_label(l)}，卡回到卡冊了。"
        self.listings = [x for x in self.listings if x["listing_id"] != l["listing_id"]]
        self.mode = "list"
        self.page = min(self.page, self.pages)
        await self.refresh(interaction)


# =========================================================
# 💹 Cog
# =========================================================
class MarketCog(commands.GroupCog, group_name="market", group_description="💹 市值、分解卡牌、玩家市場"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- autocomplete ----------------
    async def pool_autocomplete(self, interaction, current: str):
        g = gacha_mod()
        return [app_commands.Choice(name=f"{p['name']} ({p['desc']})"[:100], value=key)
                for key, p in g.GACHA_POOLS.items() if current.lower() in f"{key} {p['name']} {p['desc']}".lower()][:AUTOCOMPLETE_LIMIT]

    async def character_autocomplete(self, interaction, current: str):
        g = gacha_mod()
        pool_key = getattr(interaction.namespace, "pool", None)
        current = current.strip().lower()
        return [app_commands.Choice(name=f"{d['emoji']} {d['name']} ({k})"[:100], value=k)
                for k, d in g.GACHA_POOL.items()
                if d["pool"] == pool_key and (not current or current in k.lower() or current in d["name"].lower())][:AUTOCOMPLETE_LIMIT]

    async def owned_pool_autocomplete(self, interaction, current: str):
        g = gacha_mod()
        counts = {}
        for card in await card_cache.cached_user_cards(interaction.user.id):
            key = g.card_pool_key(card)
            counts[key] = counts.get(key, 0) + 1
        out = []
        for key, n in counts.items():
            label = g.GACHA_POOLS[key]["name"] if key in g.GACHA_POOLS else "📦 其他 (已不在卡池)"
            if current.lower() in f"{key} {label}".lower():
                out.append(app_commands.Choice(name=f"{label} · {n} 張", value=key))
        return out[:AUTOCOMPLETE_LIMIT]

    async def owned_character_autocomplete(self, interaction, current: str):
        g = gacha_mod()
        pool_key = getattr(interaction.namespace, "pool", None)
        owned = {}
        for card in await card_cache.cached_user_cards(interaction.user.id):
            if g.card_pool_key(card) != pool_key:
                continue
            e = owned.setdefault(card["character_key"], {"name": card["name"], "emoji": card.get("emoji") or "🎴", "n": 0})
            e["n"] += 1
        current = current.strip().lower()
        return [app_commands.Choice(name=f"{e['emoji']} {e['name']} ({k}) · {e['n']} 張"[:100], value=k)
                for k, e in owned.items() if not current or current in k.lower() or current in e["name"].lower()][:AUTOCOMPLETE_LIMIT]

    async def _owned_cards(self, interaction, pool: str, character: str) -> list[dict] | None:
        g = gacha_mod()
        pool, character = resolve_pool(pool), resolve_character(character)
        cards = [c for c in await get_user_cards(interaction.user.id)
                 if c["character_key"] == character and g.card_pool_key(c) == pool]
        if not cards:
            await send_notice(interaction, "❌ 你在這個卡池沒有這個角色的卡。")
            return None
        return cards

    # ---------------- 指令 ----------------
    @app_commands.command(name="price", description="💹 查詢角色各階級的市值與近 7 天漲跌")
    @app_commands.describe(pool="卡池 (代數)", character="角色")
    @app_commands.autocomplete(pool=pool_autocomplete, character=character_autocomplete)
    async def price(self, interaction: discord.Interaction, pool: str, character: str):
        g = gacha_mod()
        pool, character = resolve_pool(pool), resolve_character(character)
        data = g.GACHA_POOL.get(character)
        if data is None or data["pool"] != pool:
            await send_notice(interaction, "❌ 找不到這個角色，請從選單中選擇。")
            return
        await prepare_market()
        prices = await econ.get_market_prices()
        rows = []
        for rarity in data["rarities"]:
            p = econ.price_of(prices, character, rarity)
            rows.append({
                "rarity": rarity, "title": data["titles"][rarity], "price": p,
                "official": econ.OFFICIAL_PRICES.get(rarity, 1),
                "sold_today": await econ.get_today_activity(character, rarity),
                "values": {c: econ.card_value(p, c) for c in VALUE_SAMPLES},
                "history": await econ.get_price_history(character, rarity),
            })
        view = ui.LayoutView()
        view.add_item(build_price_container({**data, "key": character}, rows, g.THUMBNAILS))
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="decompose", description="♻️ 分解卡牌：依市值 × 完整度換成賽錢")
    @app_commands.describe(pool="卡池 (代數)", character="角色")
    @app_commands.autocomplete(pool=owned_pool_autocomplete, character=owned_character_autocomplete)
    async def decompose(self, interaction: discord.Interaction, pool: str, character: str):
        cards = await self._owned_cards(interaction, pool, character)
        if cards is None:
            return
        await prepare_market()
        await interaction.response.send_message(view=DecomposeView(interaction.user.id, cards, await econ.get_market_prices(),
                                                                  econ.modifier(await econ.get_rules(), "decompose")), ephemeral=True)

    @app_commands.command(name="sell", description="🏷️ 把卡上架到市場 (不限價格，7 天沒賣出自動下架)")
    @app_commands.describe(pool="卡池 (代數)", character="角色", price="售價 (賣出後全額入帳；買家另付 5%)")
    @app_commands.autocomplete(pool=owned_pool_autocomplete, character=owned_character_autocomplete)
    async def sell(self, interaction: discord.Interaction, pool: str, character: str, price: app_commands.Range[int, 1]):
        status = await econ.get_trade_status(interaction.user.id)
        if not status["unlocked"]:
            await send_notice(interaction, reason_text({"reason": "locked"}, status))
            return
        cards = await self._owned_cards(interaction, pool, character)
        if cards is None:
            return
        await prepare_market()
        view = SellView(interaction.user.id, cards, await econ.get_market_prices(), price,
                        interaction.user.display_name, gacha_mod().THUMBNAILS)
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="browse", description="🛒 瀏覽市場上架中的卡 (依價格排序)")
    @app_commands.describe(pool="卡池 (代數)", character="角色 (留空 = 整個卡池)")
    @app_commands.autocomplete(pool=pool_autocomplete, character=character_autocomplete)
    async def browse(self, interaction: discord.Interaction, pool: str, character: str | None = None):
        g = gacha_mod()
        pool, character = resolve_pool(pool), resolve_character(character)
        if pool not in g.GACHA_POOLS:
            await send_notice(interaction, "❌ 找不到這個卡池，請從選單中選擇。")
            return
        keys = [k for k, d in g.GACHA_POOL.items() if d["pool"] == pool]
        if character:
            if character not in keys:
                await send_notice(interaction, "❌ 這個卡池沒有這個角色。")
                return
            keys = [character]
        await prepare_market()
        listings = await econ.get_listings(keys)
        title = f"🛒 市場 · {g.GACHA_POOLS[pool]['name']}" + (f" · {g.GACHA_POOL[character]['name']}" if character else "")
        await interaction.response.send_message(view=ListingsView(interaction.user.id, listings, "buy", title), ephemeral=True)

    @app_commands.command(name="mine", description="📋 查看自己上架中的卡，可以下架")
    async def mine(self, interaction: discord.Interaction):
        await prepare_market()
        listings = await econ.get_listings(seller_id=interaction.user.id)
        await interaction.response.send_message(view=ListingsView(interaction.user.id, listings, "mine", "📋 我上架中的卡"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MarketCog(bot))

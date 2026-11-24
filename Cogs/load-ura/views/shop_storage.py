"""
🌀 裏世界畫面：🛒 商店 ShopView、📦 倉庫 StorageView
(從 Cogs/load-ura/ura.py 拆出來)
"""
from discord import ui

from Database import Ura_DB_Manager as ura
from Database.ura import data, rules
from Utils.components import send_notice
from Utils.pagination import nav_buttons, paginate
from ..Components import ura_components as UC
from .common import DENY, STORAGE_PER_PAGE, SECONDARY, SUCCESS, DANGER, _btn, _select, box_rows, _opt


# =========================================================
# 🛒 商店
# =========================================================
class ShopView(ui.LayoutView):
    def __init__(self, user, money: int, storage: dict):
        super().__init__(timeout=600)
        self.user, self.money, self.storage = user, money, storage
        self.group, self.sel, self.notice = "heal", None, None
        self.build()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await send_notice(interaction, DENY)
            return False
        return True

    def build(self):
        self.clear_items()
        self._build()
        box_rows(self)

    def _build(self):
        self.add_item(UC.build_shop_container(self.group, self.money, self.storage, self.sel, self.notice))
        gopts = [_opt(name, key, default=key == self.group) for key, name in UC.SHOP_GROUPS.items()]
        self.add_item(_select("🗂️ 分類", gopts, self.on_group))
        items = UC.shop_items(self.group)
        opts = []
        for i in items:
            info = data.bags()[i] if self.group == "bags" else data.items()[i]
            label = f"🎒 {info['name']}" if self.group == "bags" else f"{info['emoji']} {info['name']}"
            opts.append(_opt(label, i, f"{info['price']:,} 賽錢", default=i == self.sel))
        if opts:
            self.add_item(_select("🛍️ 選要買的東西…", opts, self.on_sel))
        qtys = (1,) if self.group == "bags" else (1, 5, 10)
        self.add_item(ui.ActionRow(*[_btn(f"🛒 買 {q} 個", SUCCESS, self._buy_cb(q), disabled=not self.sel) for q in qtys]))

    async def redraw(self, interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_group(self, interaction):
        self.group, self.sel, self.notice = interaction.data["values"][0], None, None
        await self.redraw(interaction)

    async def on_sel(self, interaction):
        self.sel, self.notice = interaction.data["values"][0], None
        await self.redraw(interaction)

    def _buy_cb(self, qty: int):
        async def cb(interaction):
            res = await ura.shop_buy(self.user.id, self.sel, qty)
            if res["ok"]:
                self.notice = f"✅ 買了 {UC.item_name(self.sel)} ×{qty}，花了 {res['cost']:,} 賽錢 (放進 `/ura inventory`)"
                self.money = res["money"]
            elif res["reason"] == "not_enough":
                self.notice = f"❌ 賽錢不夠 (要 {res['cost']:,}，你有 {res['money']:,})"
            else:
                self.notice = "❌ 沒有這個東西"
            self.storage = await ura.get_storage(self.user.id)
            await self.redraw(interaction)
        return cb


# =========================================================
# 📦 倉庫 (寶物 / 道具 / 額外背包；寶物可以篩選後一鍵賣掉)
# =========================================================
class StorageView(ui.LayoutView):
    def __init__(self, user, storage: dict):
        super().__init__(timeout=600)
        self.user, self.storage = user, storage
        self.page_kind, self.page = "treasures", 1
        self.rarity, self.zone = None, None
        self.confirm, self.notice = False, None
        self.peek = None   # 🔍 看說明：選到的寶物 id
        self.build()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await send_notice(interaction, DENY)
            return False
        return True

    def rows(self):
        return UC.treasure_rows(self.storage, self.rarity, self.zone)

    def build(self):
        self.clear_items()
        self._build()
        box_rows(self)

    def _build(self):
        if self.page_kind == "treasures":
            rows = self.rows()
            pg = paginate(rows, self.page, STORAGE_PER_PAGE)
            zone_name = "🎪 活動寶物" if self.zone == "fest" else next((z["name"] for z in data.zones() if z["id"] == self.zone), None)
            filters = f"篩選：{self.rarity or '全部階級'}、{zone_name or '全部區域'}"
            total = sum(data.treasure_prices()[info["rarity"]] * n for _, info, n in rows)
            if self.peek not in [tid for tid, *_ in pg.items]:
                self.peek = None
            self.add_item(UC.build_storage_container("treasures", self.storage, rows, pg.items, filters, self.notice,
                                                     confirm_total=total if self.confirm else None, peek=self.peek))
        elif self.page_kind == "items":
            items = [(i, n) for i, n in self.storage["items"].items() if n > 0]
            pg = paginate(items, self.page, STORAGE_PER_PAGE)
            self.add_item(UC.build_storage_container("items", self.storage, items, pg.items, "", self.notice))
        else:
            pg = paginate(self.storage["bags"], self.page, STORAGE_PER_PAGE)
            self.add_item(UC.build_storage_container("bags", self.storage, self.storage["bags"], pg.items, "", self.notice))
        self.page = pg.page
        kinds = [("treasures", "💎 寶物"), ("items", "🧪 道具"), ("bags", "🎒 額外背包")]
        self.add_item(_select("📦 看哪一頁", [_opt(n, k, default=k == self.page_kind) for k, n in kinds], self.on_kind))
        if self.confirm:
            self.add_item(ui.ActionRow(_btn("💰 確定全部賣掉", DANGER, self.on_sell_yes), _btn("↩️ 取消", SECONDARY, self.on_cancel)))
            return
        if self.page_kind == "treasures":
            ropts = [_opt("全部階級", "all", default=self.rarity is None)] + [_opt(r, r, default=r == self.rarity) for r in rules.RARITIES]
            self.add_item(_select("⭐ 篩選階級", ropts, self.on_rarity))
            zones, seen = [], set()
            for z in data.zones():
                if z["id"] not in seen and not z.get("borrowed"):
                    seen.add(z["id"])
                    zones.append(z)
            zopts = [_opt("全部區域", "all", default=self.zone is None)] + [
                _opt(f"{z['emoji']} {z['name']}", z["id"], default=z["id"] == self.zone) for z in zones] + [
                _opt("🎪 活動寶物", "fest", "活動結束也保留，可以賣", default=self.zone == "fest")]
            self.add_item(_select("🗺️ 篩選區域", zopts, self.on_zone))
            if pg.items:
                popts = [_opt(f"{info['name']}〔{info['rarity']}〕", tid, default=tid == self.peek) for tid, info, _ in pg.items]
                self.add_item(_select("🔍 看說明 (這一頁的寶物)", popts, self.on_peek))
        row = nav_buttons(pg.page, pg.total, self.set_page) if pg.total > 1 else []
        if self.page_kind == "treasures":
            row.append(_btn("💰 篩選出來的全部賣掉", SUCCESS, self.on_sell, disabled=not self.rows()))
        if row:
            self.add_item(ui.ActionRow(*row))

    async def redraw(self, interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def set_page(self, interaction, page):
        self.page = page
        await self.redraw(interaction)

    async def on_kind(self, interaction):
        self.page_kind, self.page, self.confirm, self.notice = interaction.data["values"][0], 1, False, None
        await self.redraw(interaction)

    async def on_rarity(self, interaction):
        v = interaction.data["values"][0]
        self.rarity, self.page, self.notice = (None if v == "all" else v), 1, None
        await self.redraw(interaction)

    async def on_zone(self, interaction):
        v = interaction.data["values"][0]
        self.zone, self.page, self.notice = (None if v == "all" else v), 1, None
        await self.redraw(interaction)

    async def on_peek(self, interaction):
        self.peek = interaction.data["values"][0]
        await self.redraw(interaction)

    async def on_sell(self, interaction):
        self.confirm, self.notice = True, None
        await self.redraw(interaction)

    async def on_cancel(self, interaction):
        self.confirm = False
        await self.redraw(interaction)

    async def on_sell_yes(self, interaction):
        sell = {tid: n for tid, _, n in self.rows()}
        res = await ura.sell_treasures(self.user.id, sell)
        self.confirm = False
        self.storage = await ura.get_storage(self.user.id)
        self.notice = (f"✅ 賣掉 {res['count']} 個寶物，拿到 {res['money']:,} 賽錢" if res["ok"]
                       else "❌ 倉庫的寶物有變動，請重新確認")
        await self.redraw(interaction)

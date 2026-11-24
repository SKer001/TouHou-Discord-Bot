"""
🌀 裏世界畫面：出發 ① 選隊伍 PartyPickerView ➔ ② 整裝 LoadoutView (帶賽錢彈窗 PocketModal) ➔ 出發 (開 RunView)
(從 Cogs/load-ura/ura.py 拆出來；這個檔在 views/ 子資料夾，不會被當成 Cog 載入，檔名 setup 跟 Cog 的 setup() 無關)
"""
import discord
from discord import ui

from Database import Ura_DB_Manager as ura
from Database.User_DB_Manager import get_or_create_user
from Database.ura import data, describe, rules, run as R
from Utils.components import send_notice
from Utils.gacha_pools import GACHA_POOLS, load_gacha_pool
from Utils.pagination import nav_buttons, paginate
from Utils.picker import GroupPickerView
from ..Components import ura_components as UC
from .common import VIEW_TIMEOUT, DENY, LIST_PER_PAGE, PRIMARY, SECONDARY, SUCCESS, _btn, _select, box_rows, _opt
from .run import RunView


# =========================================================
# 🚀 出發 ①：選隊伍 (卡池 ➔ 角色 ➔ 那位角色的哪張卡)
# =========================================================
class PartyPickerView(GroupPickerView):
    GROUP_PLACEHOLDER = "🎰 卡池"
    ITEM_PLACEHOLDER = "🧍 選角色"
    DENY_TEXT = DENY

    def __init__(self, cog, user, cards: list[dict], groups: dict):
        super().__init__(user.id, user, groups, timeout=VIEW_TIMEOUT)
        self.cog = cog
        self.cards = cards
        self.picked: list[str] = []    # instance_id (照選的順序)
        self.card_choice = None
        self.card_page = 1             # 「🎴 派哪一張卡？」第幾頁 (同一位角色超過 LIST_PER_PAGE 張時翻頁)

    @classmethod
    async def create(cls, cog, user):
        cards = await ura.candidate_cards(user.id)
        if not any(c["ok"] for c in cards):
            return None
        pool = load_gacha_pool()
        owned = []
        for c in cards:
            if c["character_key"] not in owned:
                owned.append(c["character_key"])
        groups = {k: [] for k in GACHA_POOLS}
        for cid in data.characters():
            if cid in owned:
                groups.setdefault(pool.get(cid, {}).get("pool") or "other", []).append(cid)
        view = cls(cog, user, cards, groups)
        view.open_at(next(c["character_key"] for c in cards if c["ok"]))
        view.build()
        return view

    async def load(self):
        self.cards = await ura.candidate_cards(self.user.id)
        ids = {c["instance_id"]: c for c in self.cards}
        self.picked = [i for i in self.picked if i in ids and ids[i]["ok"]]

    def card(self, iid: str) -> dict | None:
        return next((c for c in self.cards if c["instance_id"] == iid), None)

    def char(self, cid: str) -> dict:
        return data.characters().get(cid, {})

    def picked_char(self, cid: str) -> str | None:
        return next((i for i in self.picked if (self.card(i) or {}).get("character_key") == cid), None)

    def group_name(self, key):
        return GACHA_POOLS.get(key, {}).get("name", "📌 其他")

    def group_status(self, key):
        return f"{len(self.groups[key])} 位角色有卡"

    def item_label(self, cid):
        ch = self.char(cid)
        return f"{'✅ ' if self.picked_char(cid) else ''}{ch.get('emoji', '')} {ch.get('name', cid)}"

    def item_status(self, cid):
        mine = [c for c in self.cards if c["character_key"] == cid]
        return f"{UC.CLASS_NAMES.get(self.char(cid).get('class'), '')}｜{len(mine)} 張，可以派 {sum(c['ok'] for c in mine)} 張"

    def header(self):
        lines = [f"## 🚀 出發：選隊伍 ({len(self.picked)} / {rules.MAX_PARTY})"]
        for i in self.picked:
            c, ch = self.card(i), self.char(self.card(i)["character_key"])
            lines.append(f"{ch.get('emoji', '')} **{ch.get('name', '')}**〔{c['rarity']}〕 完整度 {c['completeness']:.4f}（{UC.CLASS_NAMES.get(ch.get('class'), '')}）")
        if not self.picked:
            lines.append("-# 還沒有人。選角色 ➔ 選卡 ➔ ➕ 加入隊伍")
        lines.append("-# 同一位角色只能派一張；收藏冊的卡、完整度不到 0.3 的不能派。失敗 / 放棄時派出的卡完整度 −0.1")
        return "\n".join(lines)

    def detail(self, cid):
        ch = self.char(cid)
        sp = data.spells().get(cid, {})
        note = describe.spell_note(cid)
        return (f"{ch.get('emoji', '')} **{ch.get('name', cid)}**　{UC.CLASS_NAMES.get(ch.get('class'), '')}\n"
                f"✨ {ch.get('spell_name', '符卡')}　B 點 {sp.get('b', '?')}・冷卻 {sp.get('cd', '?')} 回合\n"
                f"效果：{describe.spell_text(cid)}" + (f"\n-# {note}" if note else "") + f"\n-# {describe.COOLDOWN_NOTE}")

    def accent(self):
        return UC.COLOR_RUN

    def select_item(self, item):
        self.selected = item
        mine = sorted([c for c in self.cards if c["character_key"] == item and c["ok"]],
                      key=lambda c: (-UC.RARITY_SORT.get(c["rarity"], 0), -c["completeness"]))
        self.card_choice = mine[0]["instance_id"] if mine else None
        self.card_page = 1   # 預設選的是能派的最好那張，排在第一頁

    def actions(self):
        cid = self.selected
        has = cid and self.picked_char(cid)
        return [("➕ 加入隊伍", SUCCESS, self.on_add, not (cid and self.card_choice and not has and len(self.picked) < rules.MAX_PARTY)),
                ("➖ 移出隊伍", SECONDARY, self.on_remove, not has),
                ("➡️ 下一步：整裝", PRIMARY, self.on_next, not self.picked)]

    def build(self):
        super().build()
        if self.selected:
            last = self.children[-1]
            self.remove_item(last)
            # 能派的、階級高、完整度高的在前；超過一頁就翻頁 (2026-11-23：原本只列前 25 張，後面的選不到)
            mine = sorted([c for c in self.cards if c["character_key"] == self.selected],
                          key=lambda c: (not c["ok"], -UC.RARITY_SORT.get(c["rarity"], 0), -c["completeness"]))
            pg = paginate(mine, self.card_page, LIST_PER_PAGE)
            self.card_page = pg.page
            opts = [_opt(f"{'' if c['ok'] else '🚫 '}〔{c['rarity']}〕完整度 {c['completeness']:.4f}", c["instance_id"],
                         c["why"] or "可以出征", default=c["instance_id"] == self.card_choice) for c in pg.items]
            if opts:
                self.add_item(_select("🎴 派哪一張卡？" + (f" (第 {pg.page} / {pg.total} 頁)" if pg.total > 1 else ""),
                                      opts, self.on_card))
            if pg.total > 1:
                self.add_item(ui.ActionRow(*nav_buttons(pg.page, pg.total, self.set_card_page, "compact")))
            self.add_item(last)
        box_rows(self)

    async def on_card(self, interaction):
        c = self.card(interaction.data["values"][0])
        if not c or not c["ok"]:
            await self.done(interaction, f"❌ 這張不能派：{(c or {}).get('why') or '找不到這張卡'}")
            return
        self.card_choice = c["instance_id"]
        await self.done(interaction)

    async def set_card_page(self, interaction, page: int):
        self.card_page = page
        await self.done(interaction)

    async def on_add(self, interaction):
        if self.card_choice and self.card_choice not in self.picked and len(self.picked) < rules.MAX_PARTY \
                and not self.picked_char(self.selected):
            self.picked.append(self.card_choice)
        await self.done(interaction)

    async def on_remove(self, interaction):
        i = self.picked_char(self.selected)
        if i:
            self.picked.remove(i)
        await self.done(interaction)

    async def on_next(self, interaction):
        await self.load()
        if not self.picked:
            await self.done(interaction, "❌ 隊伍裡的卡已經不能派了，請重新選")
            return
        view = await LoadoutView.create(self.cog, self.user, self)
        await interaction.response.edit_message(view=view)


# =========================================================
# 🚀 出發 ②：整裝 (道具、額外背包、帶多少賽錢) ➔ 出發
# =========================================================
class PocketModal(ui.Modal, title="💰 帶多少賽錢進去？"):
    amount = ui.TextInput(label="賽錢 (流浪商人用；只有成功撤離才帶得回來)", placeholder="例如 30000", max_length=12)

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.amount.default = str(owner.pocket)

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.amount.value).replace(",", "").strip()
        if not raw.isdigit():
            await send_notice(interaction, "❌ 請輸入 0 以上的整數")
            return
        n = int(raw)
        money = (await get_or_create_user(self.owner.user.id))["money"]
        if n > money:
            await send_notice(interaction, f"❌ 賽錢不夠 (你只有 {money:,})")
            return
        self.owner.pocket, self.owner.money, self.owner.notice = n, money, None
        self.owner.buy_plan = None   # 帶的錢變了 ➔ 補買夠不夠錢要重算 (再按一次 ⚡ 快速整裝)
        await self.owner.redraw(interaction)


class LoadoutView(ui.LayoutView):
    def __init__(self, cog, user, picker: PartyPickerView, storage: dict, record: dict, money: int):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.cog, self.user, self.picker = cog, user, picker
        self.storage, self.record, self.money = storage, record, money
        self.carry: dict[str, int] = {}
        self.bag_row = None
        self.pocket = 0
        self.sel = None
        self.page = 1   # 🧪 選道具的頁數
        self.notice = None
        self.buy_plan = None   # ⚡ 快速整裝算好的補買 {"buy": {道具: 數量}, "cost": 總價}；帶的東西 / 背包一改就清掉
        self.build()

    @classmethod
    async def create(cls, cog, user, picker):
        storage = await ura.get_storage(user.id)
        record = await ura.get_record(user.id)
        money = (await get_or_create_user(user.id))["money"]
        return cls(cog, user, picker, storage, record, money)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await send_notice(interaction, DENY)
            return False
        return True

    def capacity(self) -> tuple[int, str | None]:
        bag = next((b for b in self.storage["bags"] if b["id"] == self.bag_row), None)
        if not bag or bag["bag_id"] not in data.bags():
            return rules.BAG_SLOTS, None
        info = data.bags()[bag["bag_id"]]
        return rules.BAG_SLOTS + info["slots"], f"{info['name']} (+{info['slots']} 格)"

    def add(self, iid: str, n: int) -> str | None:
        """多帶 n 個；回傳停下來的原因"""
        cap, _ = self.capacity()
        for _ in range(n):
            if self.storage["items"].get(iid, 0) - self.carry.get(iid, 0) <= 0:
                return f"倉庫的{UC.item_name(iid)}不夠"
            why = R.item_limit_reason(self.carry, iid, 1)
            if why:
                return why
            trial = dict(self.carry)
            trial[iid] = trial.get(iid, 0) + 1
            if R.slots_used({"items": trial, "materials": {}, "treasures": [], "relics": []}) > cap:
                return f"背包只有 {cap} 格"
            self.carry = trial
        return None

    def party(self) -> list[dict]:
        out = []
        for i in self.picker.picked:
            c = self.picker.card(i)
            ch = data.characters().get(c["character_key"], {})
            out.append({"emoji": ch.get("emoji", ""), "name": ch.get("name", ""), "rarity": c["rarity"],
                        "completeness": c["completeness"], "cls": ch.get("class")})
        return out

    def build(self):
        self.clear_items()
        self._build()
        box_rows(self)

    def _build(self):
        cap, bag_name = self.capacity()
        self.add_item(UC.build_loadout_container(self.party(), self.carry, self.storage, cap, bag_name, self.pocket,
                                                 self.money, self.notice))
        have = [(i, n) for i, n in self.storage["items"].items() if n > 0 and i in data.items()]
        if have:
            pg = paginate(have, self.page, LIST_PER_PAGE)   # 道具種類超過 25 種就翻頁
            self.page = pg.page
            opts = [_opt(UC.item_name(i), i, f"倉庫 {n}｜帶 {self.carry.get(i, 0)}｜{data.items()[i].get('desc', '')}",
                         default=i == self.sel) for i, n in pg.items]
            ph = "🧪 選一個道具…" if pg.total == 1 else f"🧪 選一個道具 (第 {pg.page} / {pg.total} 頁)…"
            self.add_item(_select(ph, opts, self.on_sel))
            if pg.total > 1:
                self.add_item(ui.ActionRow(*nav_buttons(pg.page, pg.total, self.set_page)))
            self.add_item(ui.ActionRow(
                _btn("➕ 1", SUCCESS, self._add_cb(1), disabled=not self.sel),
                _btn("➕ 5", SUCCESS, self._add_cb(5), disabled=not self.sel),
                _btn("➖ 1", SECONDARY, self.on_minus, disabled=not (self.sel and self.carry.get(self.sel))),
                _btn("🧹 全部不帶", SECONDARY, self.on_clear, disabled=not self.carry),
                _btn("💾 儲存這組", SECONDARY, self.on_save, disabled=not self.carry),
            ))
        # 額外背包一個一列會超過 25 個：同一種、剩一樣次數的合成一個選項 (選了就用那組的第一個)
        groups = {}
        for b in self.storage["bags"]:
            if b["bag_id"] in data.bags():
                groups.setdefault((b["bag_id"], b["uses_left"]), []).append(b["id"])
        if groups:
            opts = [_opt("不帶額外背包", "none", default=self.bag_row is None)]
            for (bid, uses), ids in groups.items():
                info = data.bags()[bid]
                opts.append(_opt(f"🎒 {info['name']} (+{info['slots']} 格)" + (f" ×{len(ids)}" if len(ids) > 1 else ""), str(ids[0]),
                                 f"還能用 {uses} 次 (這次出發用掉 1 次)", default=self.bag_row in ids))
            self.add_item(_select("🎒 額外背包", opts, self.on_bag))
        if self.buy_plan:
            cost = self.buy_plan["cost"]
            short = cost - (self.money - self.pocket)   # 帶進去的賽錢要留著 (不然買完出發不了)
            label = f"🛒 補買缺的 ({cost:,} 賽錢)" if short <= 0 else f"🛒 補買 (賽錢還差 {short:,})"
            self.add_item(ui.ActionRow(_btn(label, SUCCESS, self.on_buy_missing, disabled=short > 0)))
        self.add_item(ui.ActionRow(
            _btn("⚡ 快速整裝", PRIMARY, self.on_quick, disabled=not self.record.get("loadout")),
            _btn("💰 帶賽錢", SECONDARY, self.on_pocket),
            _btn("🚀 出發！", SUCCESS, self.on_go),
            _btn("↩️ 上一步", SECONDARY, self.on_back),
        ))

    async def redraw(self, interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def set_page(self, interaction, page):
        self.page = page
        await self.redraw(interaction)

    def _add_cb(self, n: int):
        async def cb(interaction):
            why = self.add(self.sel, n) if self.sel else "先選一個道具"
            self.notice, self.buy_plan = (f"⚠️ {why}" if why else None), None
            await self.redraw(interaction)
        return cb

    async def on_sel(self, interaction):
        self.sel = interaction.data["values"][0]
        await self.redraw(interaction)

    async def on_minus(self, interaction):
        if self.carry.get(self.sel):
            self.carry[self.sel] -= 1
            if not self.carry[self.sel]:
                del self.carry[self.sel]
        self.notice, self.buy_plan = None, None
        await self.redraw(interaction)

    async def on_clear(self, interaction):
        self.carry, self.notice, self.buy_plan = {}, None, None
        await self.redraw(interaction)

    async def on_save(self, interaction):
        await ura.save_loadout(self.user.id, self.carry)
        self.record = await ura.get_record(self.user.id)
        self.notice, self.buy_plan = "💾 存好了，下次出發可以按 ⚡ 快速整裝一鍵帶齊", None   # 補買清單被換掉 ➔ 按鈕也收起來
        await self.redraw(interaction)

    def quick_fill(self) -> list[str]:
        """照存好的那組，先從倉庫帶 (帶不齊的原因寫在回傳的清單)"""
        self.carry = {}
        short = []
        for iid, n in self.record.get("loadout", {}).items():
            if iid not in data.items():
                continue
            why = self.add(iid, n)
            if why:
                short.append(f"{UC.item_name(iid)}：{why}")
        return short

    def quick_plan(self) -> tuple[dict, dict]:
        """
        倉庫不夠的部分照 /ura shop 原價補買 (2026-11-23 使用者定)：
        只買「這次的背包放得下、沒超過道具上限」的量 (存那組時有裝額外背包、這次沒裝的話就少買，不會白花錢)
        回傳 (要買的 {道具: 數量}, 沒買的 {道具: (數量, 原因)})；倉庫還有剩卻沒帶上的 (卡在上限 / 格數) 不算缺
        """
        cap, _ = self.capacity()
        trial, buy, skipped = dict(self.carry), {}, {}
        for iid, n in self.record.get("loadout", {}).items():
            have = trial.get(iid, 0)
            if iid not in data.items() or n <= have:
                continue
            in_storage = self.storage["items"].get(iid, 0) > have   # 倉庫還有卻沒帶上 = 卡在上限 / 格數，不是缺貨
            for _ in range(n - have):
                why = R.item_limit_reason(trial, iid, 1)
                test = dict(trial)
                test[iid] = test.get(iid, 0) + 1
                if not why and R.slots_used({"items": test, "materials": {}, "treasures": [], "relics": []}) > cap:
                    why = f"背包只有 {cap} 格"
                if why:
                    k, _r = skipped.get(iid, (0, why))
                    skipped[iid] = (k + 1, why)
                    continue
                if in_storage:   # 照理不會發生 (第一輪就帶上了)；不買
                    continue
                trial = test
                buy[iid] = buy.get(iid, 0) + 1
        return buy, skipped

    def _quick_notice(self, short: list[str]) -> str:
        """快速整裝的結果；倉庫不夠的話算好補買 (self.buy_plan) 並列出要買什麼、共多少錢"""
        buy, skipped = self.quick_plan()
        self.buy_plan = None
        if not short:
            return "⚡ 帶齊了！"
        lines = []
        if buy:
            items = data.items()
            cost = sum(items[i]["price"] * k for i, k in buy.items())
            self.buy_plan = {"buy": buy, "cost": cost}
            lines.append("⚡ 倉庫有的都帶上了，還缺的可以照 `/ura shop` 原價補買：")
            lines += [f"- {UC.item_name(i)} ×{k}　`{items[i]['price']:,}` × {k} = `{items[i]['price'] * k:,}`" for i, k in buy.items()]
            lines.append(f"共 **{cost:,} 賽錢** (你有 {self.money:,})；按「🛒 補買缺的」才扣錢，買的放進倉庫並直接帶上")
            avail = self.money - self.pocket   # 帶進去的賽錢要留著
            if cost > avail:
                lines.append(f"-# 💸 賽錢不夠，還差 {cost - avail:,}"
                             + (f" (要帶進去的 {self.pocket:,} 賽錢也算在內)" if self.pocket else ""))
        else:
            lines.append("⚠️ 有些沒帶齊")
            lines += [f"-# {x}" for x in short]
        if skipped and buy:   # 沒東西要買時，上面「有些沒帶齊」已經寫了原因
            n = sum(k for k, _ in skipped.values())
            lines.append(f"-# ⚠️ 有 {n} 個放不下，沒有買：" + "、".join(f"{UC.item_name(i)} ×{k} ({why})" for i, (k, why) in skipped.items()))
        return "\n".join(lines)

    async def on_quick(self, interaction):
        self.money = (await get_or_create_user(self.user.id))["money"]
        self.notice = self._quick_notice(self.quick_fill())
        await self.redraw(interaction)

    async def on_buy_missing(self, interaction):
        """🛒 補買：重新讀倉庫和賽錢再算一次，跟畫面上寫的一樣才買 (避免中間在別的地方買過 / 花過錢)"""
        shown, self.buy_plan = self.buy_plan, None   # 先收起來：連按兩下的第二下會走「重算了」，不會買兩次
        self.storage = await ura.get_storage(self.user.id)
        self.money = (await get_or_create_user(self.user.id))["money"]
        notice = self._quick_notice(self.quick_fill())
        if not shown or self.buy_plan != shown:
            self.notice = "⚠️ 倉庫或背包變了，補買的東西重算了，確認後再按一次\n" + notice
            await self.redraw(interaction)
            return
        if shown["cost"] > self.money - self.pocket:   # 帶進去的賽錢要留著
            self.notice = notice
            await self.redraw(interaction)
            return
        res = await ura.shop_buy_many(self.user.id, shown["buy"])
        if not res["ok"]:
            why = {"not_enough": f"賽錢不夠 (要 {res.get('cost', 0):,}，你有 {res.get('money', 0):,})"}.get(res["reason"], "買不了")
            self.notice = f"❌ {why}\n" + notice
            await self.redraw(interaction)
            return
        self.storage = await ura.get_storage(self.user.id)
        self.money = res["money"]
        bought = "、".join(f"{UC.item_name(i)} ×{k}" for i, k in shown["buy"].items())
        self.notice = f"🛒 買了 {bought}，花了 {res['cost']:,} 賽錢\n" + self._quick_notice(self.quick_fill())
        await self.redraw(interaction)

    async def on_bag(self, interaction):
        v = interaction.data["values"][0]
        old = self.bag_row
        self.bag_row = None if v == "none" else int(v)
        cap, _ = self.capacity()
        if R.slots_used({"items": self.carry, "materials": {}, "treasures": [], "relics": []}) > cap:
            self.bag_row, self.notice = old, f"⚠️ 現在帶的道具超過 {cap} 格，先少帶一點"
        else:
            self.notice = None
        if self.bag_row != old:
            self.buy_plan = None   # 背包大小變了，補買要重算 (再按一次 ⚡ 快速整裝)
        await self.redraw(interaction)

    async def on_pocket(self, interaction):
        await interaction.response.send_modal(PocketModal(self))

    async def on_back(self, interaction):
        await self.picker.refresh()
        await interaction.response.edit_message(view=self.picker)

    async def on_go(self, interaction):
        res = await ura.start_run(self.user.id, list(self.picker.picked), self.carry, self.pocket, self.bag_row,
                                  channel_id=interaction.channel_id)
        if not res["ok"]:
            self.storage = await ura.get_storage(self.user.id)
            self.money = (await get_or_create_user(self.user.id))["money"]
            self.notice = f"❌ {res['reason']}"
            await self.redraw(interaction)
            return
        view = RunView(self.cog, self.user, res, notice="🌀 出發了！穿過裂縫，眼前是一片陌生的竹林……")
        view.last = interaction
        await interaction.response.edit_message(view=view)
        self.stop()
        self.picker.stop()
        await self.cog.track(view)

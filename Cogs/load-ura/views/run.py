"""
🌀 裏世界畫面：進行中的一局 RunView (選門、戰鬥、房間、背包、選目標、放棄確認、結算)
(從 Cogs/load-ura/ura.py 拆出來；Cog 由建構子傳進來 (self.cog)，這裡不 import ura.py)
"""
import discord
from discord import ui

from Database import Ura_DB_Manager as ura
from Database.ura import combat, data, rules, run as R
from Utils.components import send_notice, notice_view
from Utils.pagination import nav_buttons, paginate
from Utils.thumbnails import load_thumbnails, thumbnail_url
from ..Components import ura_components as UC
from .common import (
    VIEW_TIMEOUT, DENY, STALE, LIST_PER_PAGE, PRIMARY, SECONDARY, SUCCESS, DANGER, _btn, _select, box_rows, _opt,
)


# =========================================================
# 🌀 進行中的一局
# =========================================================
class RunView(ui.LayoutView):
    """
    mode：main (依 phase 顯示) / bag (背包) / target (選目標) / abandon (確認放棄) / settle (結算)
    多步的選擇 (誰行動 ➔ 動作 ➔ 目標、放棄確認) 都在這裡，最後一按才呼叫 ura.act()
    """

    def __init__(self, cog, user, row: dict, mode: str = "main", notice: str | None = None):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.cog, self.user = cog, user
        self.rev, self.state = row["rev"], row["state"]
        self.mode, self.notice = mode, notice
        self.actor = None      # 戰鬥：誰行動
        self.pending = None    # 等選目標的動作 {"action", "item", "kind", "idx"}
        self.settle = None
        self.last = None       # 最後一次互動 (逾時 / 被新畫面取代時拿來改畫面)
        self.retired = False
        # 下面三個只存在畫面上 (不寫進進度 state，重開機器人 / resume 後從頭)
        self.bag_tab = None    # 背包看哪一類 (UC.BAG_KINDS 的 key，或 pending = 待撿)
        self.pages = {}        # 各個會翻頁的選單現在在第幾頁 {清單: 頁數}
        self.fox = []          # 狐狸：已經選好、還沒交出去的道具
        self.build()

    # ---------- 共用 ----------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await send_notice(interaction, DENY)
            return False
        if self.retired:
            await send_notice(interaction, STALE)
            return False
        return True

    async def on_timeout(self):
        self.cog.forget(self)
        if self.last and not self.retired and self.mode != "settle":
            try:
                await self.last.edit_original_response(view=notice_view("⏳ 畫面閒置太久先收起來了；進度都還在，用 `/ura resume` 接回"))
            except discord.HTTPException:
                pass

    async def redraw(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)
        self.last = interaction   # 只記「改到這個畫面」的互動 (狀態表、錯誤提示是另一則訊息，不能拿來收畫面)

    async def act(self, interaction: discord.Interaction, fn, keep: bool = False):
        """所有會改進度的按鈕都走這裡；keep = 成功後留在同一個 mode (例如背包裡連續操作)"""
        before = self.state["phase"]
        res = await ura.act(self.user.id, self.rev, fn)
        if res["ok"]:
            self.rev, self.state, self.notice, self.fox = res["rev"], res["state"], None, []
            if not (keep and self.state["phase"] == before):
                self.mode, self.pending = "main", None
            if res.get("settle"):
                await self.finish(interaction, res["settle"])
                return
            await self.redraw(interaction)
            return
        reason = res["reason"]
        if reason == "stale":   # 別的畫面已經動過：重新讀進度 (不是錯誤)
            row = await ura.get_run(self.user.id)
            if row:
                self.rev, self.state, self.fox = row["rev"], row["state"], []
                self.mode, self.pending = "main", None
                self.notice = "🔄 進度在別的畫面動過了，已經重新讀取"
                await self.redraw(interaction)
                return
            reason = "none"
        if reason == "none":
            self.retired = True
            self.stop()
            self.cog.forget(self)
            await interaction.response.edit_message(view=notice_view("🏁 這局已經結束了，用 `/ura explore` 再出發"))
            return
        await send_notice(interaction, f"❌ {reason}")

    async def finish(self, interaction: discord.Interaction, settle: dict):
        self.settle, self.mode = settle, "settle"
        await self.redraw(interaction)
        self.retired = True
        self.stop()
        self.cog.forget(self)
        await self.cog.announce(interaction, self.state, settle)

    # ---------- 畫面 ----------
    def build(self):
        self.clear_items()
        self._build()
        box_rows(self)

    def _build(self):
        st = self.state
        if self.mode == "settle":
            self.add_item(UC.build_settle_container(st, self.settle))
            return
        if self.mode == "abandon":
            body = ("### 🏳️ 確定要放棄這次探索嗎？\n派出的卡**每張完整度 −0.1**，口袋的賽錢和背包裡的東西**全部沒了**，經驗只拿一半。")
            self.add_item(UC.build_run_container(st, self.notice, body))
            self.add_item(ui.ActionRow(_btn("🏳️ 確定放棄", DANGER, self.on_abandon_yes), _btn("↩️ 返回", SECONDARY, self.on_back)))
            return
        if self.mode == "evac_confirm":
            self.add_item(UC.build_run_container(st, self.notice, UC.talisman_confirm_text(st, self.pending["item"])))
            self.add_item(ui.ActionRow(_btn("🔙 確定撤離", SUCCESS, self.on_talisman_yes), _btn("↩️ 返回", SECONDARY, self.on_back)))
            return
        if self.mode == "target":
            self._build_target()
            return
        if self.mode == "bag":
            self._build_bag()
            return
        phase = st["phase"]
        if phase == "battle":
            self._build_battle()
        elif phase == "doors":
            self._build_doors()
        else:
            self._build_room()

    def _paged(self, key: str, placeholder: str, opts: list, callback, **kw) -> list[ui.Button]:
        """
        選項超過 25 個就分頁：放上這一頁的選單，回傳翻頁按鈕 (一頁就放得下 ➔ 空 list)，讓呼叫端跟別的按鈕放同一排
        頁數記在 self.pages[key]；清單變短 (丟掉、撿起) 時 paginate 會把頁數拉回範圍內
        """
        pg = paginate(opts, self.pages.get(key, 1), LIST_PER_PAGE)
        self.pages[key] = pg.page
        if pg.total > 1:
            dots = "…" if placeholder.endswith("…") else ""
            placeholder = f"{placeholder.rstrip('…')} (第 {pg.page} / {pg.total} 頁){dots}"
        self.add_item(_select(placeholder, pg.items, callback, **kw))
        return nav_buttons(pg.page, pg.total, self._pager(key)) if pg.total > 1 else []

    def _pager(self, key: str):
        async def cb(interaction, page):
            self.pages[key] = page
            await self.redraw(interaction)
        return cb

    def _pending_opts(self) -> list:
        return [_opt(UC.pending_label(p), str(i), UC.thing_desc(p["kind"], p["key"]))
                for i, p in enumerate(self.state.get("pending") or [])]

    def _pending_row(self):
        """主畫面的「撿起放不下的東西」：25 樣以內直接選；更多的話到背包裡翻頁挑"""
        opts = self._pending_opts()
        if len(opts) > LIST_PER_PAGE:
            self.add_item(ui.ActionRow(_btn(f"📦 撿起放不下的東西 ({len(opts)} 樣，到背包裡挑)", SECONDARY, self.on_pending_bag)))
        elif opts:
            self.add_item(_select("📦 撿起放不下的東西…", opts, self.on_take))

    def _build_battle(self):
        st, b = self.state, self.state["battle"]
        self.add_item(UC.build_run_container(st, self.notice))
        ready = [m for m in st["party"] if combat.can_act(st, m)]
        if self.actor not in [m["uid"] for m in ready]:
            self.actor = ready[0]["uid"] if ready else None
        if ready:
            opts = []
            for m in ready:
                why = combat.spell_ready(st, m)
                spell = m.get("spell_name") or "符卡"
                opts.append(_opt(f"{m['emoji']} {m['name']}", m["uid"], f"✨ {spell}：" + ("可以放" if not why else why),
                                 default=m["uid"] == self.actor))
            self.add_item(_select("🙋 誰行動？", opts, self.on_actor))
        actor = combat.find_unit(st, self.actor) if self.actor else None
        why = combat.spell_ready(st, actor) if actor else "沒有人能行動"
        rel = actor.get("relic") if actor else None
        ofuda = bool(rel and data.relics()[rel["rid"]]["type"] == "ofuda" and rel.get("left", 0) > 0 and not b["ofuda_used"])
        smoke = st["bag"]["items"].get("smoke_bomb", 0) > 0
        cost = 0 if smoke else rules.flee_cost(rules.zone_of(st["floor"]), combat.has_guide(st), b["kind"])
        flee = "🏃 逃跑" + ("" if b["kind"] == "boss" else (" (💨 煙霧彈)" if smoke else f" (🧭 −{cost})"))
        self.add_item(ui.ActionRow(
            _btn("⚔️ 普攻", PRIMARY, self.on_attack, disabled=actor is None),
            _btn("✨ 符卡", SUCCESS, self.on_spell, disabled=bool(why)),
            _btn("🎒 道具", SECONDARY, self.on_bag, disabled=not R.usable_items(st)),
            _btn("📜 御札", SECONDARY, self.on_ofuda, disabled=not ofuda),
            _btn(flee, SECONDARY, self.on_flee, disabled=b["kind"] == "boss"),
        ))
        self._peek_row()
        self.add_item(ui.ActionRow(_btn("📖 狀態表", SECONDARY, self.on_status_table), _btn("🏳️ 放棄", DANGER, self.on_abandon)))

    def _peek_row(self):
        """🔍 查看：我方 (+ 戰鬥中的敵人) ➔ 另外一則私人訊息顯示詳情"""
        st = self.state
        units = list(st["party"]) + (list(st["battle"]["foes"]) if st["phase"] == "battle" and st.get("battle") else [])
        opts = [_opt(f"{u['emoji']} {u['name']}", u["uid"], ("我方" if u["side"] == "ally" else "敵人") + "｜" +
                     (f"❤️ {u['hp']} / {combat.max_hp(u)}" if u["alive"] else "💀 倒下")) for u in units]
        if opts:
            self.add_item(_select("🔍 查看角色 / 敵人的詳情…", opts, self.on_peek_unit))

    def _build_doors(self):
        st = self.state
        self.add_item(UC.build_run_container(st, self.notice))
        revealed = R.doors_revealed(st)
        doors = [_btn(UC.door_label(st, i, d, revealed), DANGER if d["type"] == "boss" else PRIMARY, self._door_cb(i))
                 for i, d in enumerate(st["doors"][:5])]
        if doors:
            self.add_item(ui.ActionRow(*doors))
        self._pending_row()
        self._peek_row()
        row = [_btn("🎒 背包", SECONDARY, self.on_bag)]
        caster = next((m for m in combat.living(st["party"]) if data.spells()[m["cid"]].get("outside")), None)
        if caster:
            row.append(_btn(f"✨ {caster['name']}的符卡", SUCCESS, self._outside_cb(caster["uid"]),
                            disabled=bool(combat.spell_ready(st, caster, in_battle=False))))
        row += [_btn("📖 狀態表", SECONDARY, self.on_status_table), _btn("🏳️ 放棄", DANGER, self.on_abandon)]
        self.add_item(ui.ActionRow(*row))

    def _build_room(self):
        st, phase = self.state, self.state["phase"]
        room = st.get("room") or {}
        self.add_item(UC.build_run_container(st, self.notice))
        row = []
        if phase == "chest":
            if not room.get("opened"):
                locked = room.get("locked")
                no_key = locked and st["bag"]["items"].get("chest_key", 0) <= 0
                row.append(_btn("🗝️ 用鑰匙打開" if locked else "🔓 打開寶箱", SUCCESS, self.on_open, disabled=bool(no_key)))
                row.append(_btn("🚪 不開了，往前走", PRIMARY, self.on_leave))
            else:
                row.append(_btn("🚪 繼續前進", PRIMARY, self.on_leave))
        elif phase == "event":
            pc = room.get("pending_choice")
            if pc:
                do = data.events()[pc]["effect"]["do"]
                if do == "upgrade_treasure":
                    first = {}
                    for i, t in enumerate(st["bag"]["treasures"]):
                        if t["rarity"] != "LR":
                            first.setdefault((t["id"], t["rarity"]), i)   # 同一種只列一次
                    ts = sorted(first.items(), key=lambda kv: UC.RARITY_SORT.get(kv[0][1], 0))
                    if ts:
                        opts = [_opt(f"{UC.treasure_name(tid)}〔{r}〕", str(i), "獻上這個，換高一階的寶物") for (tid, r), i in ts]
                        nav = self._paged("offer", "⛩️ 獻上哪一個寶物？", opts, self.on_offer)
                        if nav:
                            self.add_item(ui.ActionRow(*nav))
                elif do == "trade_items_for_relic":
                    self._build_fox(data.events()[pc]["effect"]["items"])
                elif do == "trial":
                    row.append(_btn("🔥 接受試煉", SUCCESS, self.on_trial))
                else:
                    row.append(_btn("✅ 好", SUCCESS, self.on_accept))
                row.append(_btn("❌ 不要", SECONDARY, self.on_decline))
            else:
                row.append(_btn("🚪 繼續前進", PRIMARY, self.on_leave))
        elif phase == "trap":
            row.append(_btn("🚪 繼續前進", PRIMARY, self.on_leave))
        elif phase == "merchant":
            stock = [(i, s) for i, s in enumerate(room.get("stock", [])) if s["qty"] > 0]
            if stock:
                opts = [_opt(UC.item_name(s["id"]) if s["kind"] == "item" else UC.relic_name(s["relic"]), str(i),
                             f"{s['price']:,} 賽錢｜剩 {s['qty']}｜"
                             + UC.thing_desc(s["kind"], s["id"] if s["kind"] == "item" else s["relic"])) for i, s in stock]
                self.add_item(_select("🛒 買一個…", opts, self.on_buy))
            row.append(_btn("🚪 離開", PRIMARY, self.on_leave))
        elif phase == "boss_clear":
            row += [_btn("🏁 撤離 (帶東西回去)", SUCCESS, self.on_evacuate), _btn("➡️ 繼續前進", PRIMARY, self.on_continue)]
        self._pending_row()
        row += [_btn("🎒 背包", SECONDARY, self.on_bag), _btn("🏳️ 放棄", DANGER, self.on_abandon)]
        self.add_item(ui.ActionRow(*row[:5]))

    def _build_bag(self):
        """
        背包 (使用者 2026-11-21 grill 定)：選單切一類 (道具 / 素材 / 寶物 / 法具 + 有待撿時「📦 待撿」)，一次只看一類、一樣一行
        使用 / 丟掉 / 裝備 / 卸下 / 撿起的選單只列這一類 (這一頁)；一類超過 25 樣就翻頁
        戰鬥中只能用道具 (🧪 使用道具 列全部用得到的，不是被動的道具 ≤ 25 種)
        """
        st = self.state
        battle = st["phase"] == "battle"
        tabs = dict(UC.BAG_KINDS)
        if not battle and st.get("pending"):
            tabs["pending"] = "📦 待撿"
        if self.bag_tab not in tabs:
            self.bag_tab = "items"
        tab = self.bag_tab
        pg = paginate(UC.bag_entries(st, tab), self.pages.get(f"bag:{tab}", 1), LIST_PER_PAGE)
        self.pages[f"bag:{tab}"] = pg.page
        self.add_item(UC.build_run_container(st, self.notice, UC.bag_body(st, tab, pg.items, pg.page, pg.total)))
        self.add_item(_select("🎒 看哪一類…", [_opt(name, k, UC.bag_tab_desc(st, k), default=k == tab) for k, name in tabs.items()],
                              self.on_bag_tab))
        sfx = f" (第 {pg.page} / {pg.total} 頁)" if pg.total > 1 else ""
        page = pg.items
        if tab == "items":
            usable = R.usable_items(st)
            if usable:
                opts = [_opt(UC.item_name(i), i, UC.item_option_desc(i, st["bag"]["items"][i])) for i in usable]
                self.add_item(_select("🧪 使用道具…", opts, self.on_use))
            if not battle and page:
                self.add_item(_select(f"🗑️ 丟掉道具 (一次丟 1 個){sfx}…",
                                      [_opt(f"{e['label']} (丟 1 個)", f"items|{e['key']}", e["desc"]) for e in page], self.on_discard))
        elif not battle and tab == "materials" and page:
            self.add_item(_select(f"🗑️ 丟掉素材 (那一種全部丟掉){sfx}…",
                                  [_opt(f"{e['label']} (全部丟掉)", f"materials|{e['key']}", e["desc"]) for e in page], self.on_discard))
        elif not battle and tab == "treasures" and page:
            self.add_item(_select(f"🗑️ 丟掉寶物 (一次丟 1 個){sfx}…",
                                  [_opt(f"{e['label']} (丟 1 個)", f"treasures|{e['key']}", e["desc"]) for e in page], self.on_discard))
        elif not battle and tab == "relics":
            if page:
                self.add_item(_select(f"🦊 把法具裝給誰{sfx}…", [_opt(e["label"], e["key"], e["desc"]) for e in page], self.on_relic))
                self.add_item(_select(f"🗑️ 丟掉法具{sfx}…",
                                      [_opt(f"{e['label']} (丟掉)", f"relics|{e['key']}", e["desc"]) for e in page], self.on_discard))
            worn = [m for m in st["party"] if m.get("relic")]
            if worn:
                self.add_item(_select("🔓 卸下法具 (放回背包)…",
                                      [_opt(f"{m['emoji']} {m['name']}：{UC.relic_name(m['relic'])}", m["uid"],
                                            data.relics().get(m["relic"]["rid"], {}).get("desc", "")) for m in worn],
                                      self.on_unequip))
        elif not battle and tab == "pending" and page:
            self.add_item(_select(f"📦 撿起放不下的東西{sfx}…", [_opt(e["label"], e["key"], e["desc"]) for e in page], self.on_take))
        nav = nav_buttons(pg.page, pg.total, self._pager(f"bag:{tab}")) if pg.total > 1 else []
        self.add_item(ui.ActionRow(*nav, _btn("↩️ 返回", SECONDARY, self.on_back)))

    def _build_fox(self, need: int):
        """狐狸要 need 個道具：可以分幾次選 (道具多的時候選單會翻頁)，選滿 need 個就交出去"""
        have = dict(self.state["bag"]["items"])
        for iid in self.fox:
            have[iid] = have.get(iid, 0) - 1
        if len(self.fox) >= need or any(n < 0 for n in have.values()):   # 背包變了 ➔ 重選
            self.fox, have = [], dict(self.state["bag"]["items"])
        left = need - len(self.fox)
        if sum(n for n in have.values() if n > 0) < left:
            return
        # 同一種最多列「還要幾個」份，不然一種道具很多個就把選單塞滿
        opts = [_opt(UC.item_name(iid), f"{iid}#{k}") for iid, n in have.items() for k in range(max(0, min(n, left)))]
        if self.fox:
            ph = f"🦊 再選 {left} 個交給狐狸 (已選：{'、'.join(UC.item_name(i) for i in self.fox)})…"
        else:
            ph = f"🦊 選 {need} 個道具交給狐狸…"
        paged = len(opts) > LIST_PER_PAGE
        row = self._paged("fox", ph, opts, self.on_trade, max_values=left, min_values=1 if paged else left)
        if self.fox:
            row.append(_btn("🧹 重選", SECONDARY, self.on_fox_reset))
        if row:
            self.add_item(ui.ActionRow(*row))

    def _build_target(self):
        st, p = self.state, self.pending
        self.add_item(UC.build_run_container(st, self.notice))
        kind = p["kind"]
        if kind == "enemy":
            pool = combat.living((st.get("battle") or {}).get("foes", []))
        elif kind == "dead":
            pool = [m for m in st["party"] if not m["alive"]]
        elif kind == "member":
            pool = list(st["party"])
        else:
            pool = combat.living(st["party"])
        opts = [_opt(f"{u['emoji']} {u['name']}", u["uid"],
                     f"❤️ {u['hp']} / {combat.max_hp(u)}" if u["alive"] else "💀 倒下") for u in pool]
        what = {"attack": "⚔️ 普攻", "spell": "✨ 符卡", "ofuda": "📜 御札", "relic": "🦊 裝備法具", "trial": "🔥 試煉"}.get(
            p["action"], UC.item_name(p.get("item") or ""))
        if opts:
            self.add_item(_select(f"🎯 {what}：選目標", opts, self.on_target))
        self.add_item(ui.ActionRow(_btn("↩️ 取消", SECONDARY, self.on_back)))

    # ---------- 按鈕 ----------
    def _door_cb(self, idx: int):
        async def cb(interaction: discord.Interaction):
            await self.act(interaction, lambda s, g: R.choose_door(s, idx, g))
        return cb

    def _outside_cb(self, uid: str):
        async def cb(interaction: discord.Interaction):
            await self.act(interaction, lambda s, g: R.cast_outside(s, uid, g))
        return cb

    async def on_back(self, interaction):
        self.mode, self.pending, self.notice = "main", None, None
        await self.redraw(interaction)

    async def on_bag(self, interaction):
        """打開背包：停在道具頁、各類從第 1 頁看"""
        self.mode, self.notice, self.bag_tab = "bag", None, "items"
        self.pages = {k: v for k, v in self.pages.items() if not k.startswith("bag:")}
        await self.redraw(interaction)

    async def on_abandon(self, interaction):
        self.mode, self.notice = "abandon", None
        await self.redraw(interaction)

    async def on_abandon_yes(self, interaction):
        await self.act(interaction, lambda s, g: R.abandon(s))

    async def on_status_table(self, interaction):
        view = ui.LayoutView(timeout=None)
        view.add_item(UC.build_status_table())
        await interaction.response.send_message(view=view, ephemeral=True)

    async def on_actor(self, interaction):
        self.actor = interaction.data["values"][0]
        await self.redraw(interaction)

    async def battle(self, interaction, action: str, item: str | None = None, target: str | None = None):
        uid = self.actor
        if target is None:
            kind = R.target_kind(self.state, action, uid, item)
            if kind:
                self.pending, self.mode = {"action": action, "item": item, "kind": kind}, "target"
                await self.redraw(interaction)
                return
        await self.act(interaction, lambda s, g: R.battle_action(s, action, g, uid=uid, target=target, item=item))

    async def on_attack(self, interaction):
        await self.battle(interaction, "attack")

    async def on_spell(self, interaction):
        await self.battle(interaction, "spell")

    async def on_ofuda(self, interaction):
        await self.battle(interaction, "ofuda")

    async def on_flee(self, interaction):
        await self.battle(interaction, "flee")

    async def on_use(self, interaction):
        iid = interaction.data["values"][0]
        if self.state["phase"] == "battle":
            await self.battle(interaction, "item", item=iid)
            return
        kind = R.target_kind(self.state, "item", item=iid)
        if kind:
            self.pending, self.mode = {"action": "item_out", "item": iid, "kind": kind}, "target"
            await self.redraw(interaction)
            return
        if data.items().get(iid, {}).get("effect", {}).get("do") == "evacuate" and self.state["phase"] == "doors":
            # 🔙 歸還符：一用這局就結束，先確認 (2026-11-23 使用者：「歸還符要多一道確認」)
            self.pending, self.mode, self.notice = {"action": "talisman", "item": iid}, "evac_confirm", None
            await self.redraw(interaction)
            return
        await self.act(interaction, lambda s, g: R.use_item(s, iid, None, g), keep=True)

    async def on_talisman_yes(self, interaction):
        iid = (self.pending or {}).get("item")
        if not iid:
            await self.on_back(interaction)
            return
        await self.act(interaction, lambda s, g: R.use_item(s, iid, None, g))

    async def on_target(self, interaction):
        t, p = interaction.data["values"][0], self.pending or {}
        a = p.get("action")
        if a in ("attack", "spell", "ofuda", "item"):
            await self.battle(interaction, a, item=p.get("item"), target=t)
        elif a == "item_out":
            await self.act(interaction, lambda s, g: R.use_item(s, p["item"], t, g))
        elif a == "relic":
            await self.act(interaction, lambda s, g: R.equip_relic(s, p["idx"], t))
        elif a == "trial":
            await self.act(interaction, lambda s, g: R.event_choice(s, True, g, pick=t))
        else:
            await self.on_back(interaction)

    async def on_take(self, interaction):
        idx = int(interaction.data["values"][0])
        await self.act(interaction, lambda s, g: R.take_pending(s, idx), keep=True)

    async def on_discard(self, interaction):
        kind, key = interaction.data["values"][0].split("|", 1)
        if kind in ("treasures", "relics"):
            key = int(key)
        n = self.state["bag"]["materials"].get(key, 1) if kind == "materials" else 1
        await self.act(interaction, lambda s, g: R.discard(s, kind, key, n), keep=True)

    async def on_unequip(self, interaction):
        uid = interaction.data["values"][0]
        await self.act(interaction, lambda s, g: R.unequip_relic(s, uid), keep=True)

    async def on_peek_unit(self, interaction):
        """🔍 查看：畫面重畫 (選單回到沒選的樣子) + 另外一則私人訊息放詳情 (不蓋掉戰鬥畫面)"""
        u = combat.find_unit(self.state, interaction.data["values"][0])
        if not u:
            await send_notice(interaction, "❌ 找不到這位")
            return
        kills = {} if u["side"] == "ally" else (await ura.get_bestiary(self.user.id))["kills"]
        thumb = thumbnail_url(u["cid"], load_thumbnails(), u["rarity"]) if u["side"] == "ally" else None
        view = ui.LayoutView(timeout=None)
        view.add_item(UC.build_unit_detail(self.state, u, kills, thumb))
        await self.redraw(interaction)
        await interaction.followup.send(view=view, ephemeral=True)

    async def on_relic(self, interaction):
        idx = int(interaction.data["values"][0])
        if len(self.state["party"]) == 1:
            uid = self.state["party"][0]["uid"]
            await self.act(interaction, lambda s, g: R.equip_relic(s, idx, uid), keep=True)
            return
        self.pending, self.mode = {"action": "relic", "idx": idx, "kind": "member"}, "target"
        await self.redraw(interaction)

    async def on_open(self, interaction):
        await self.act(interaction, lambda s, g: R.open_chest(s, g), keep=True)

    async def on_leave(self, interaction):
        await self.act(interaction, lambda s, g: R.leave_room(s, g))

    async def on_accept(self, interaction):
        await self.act(interaction, lambda s, g: R.event_choice(s, True, g), keep=True)

    async def on_decline(self, interaction):
        await self.act(interaction, lambda s, g: R.event_choice(s, False, g), keep=True)

    async def on_offer(self, interaction):
        idx = int(interaction.data["values"][0])
        await self.act(interaction, lambda s, g: R.event_choice(s, True, g, pick=idx), keep=True)

    async def on_trade(self, interaction):
        pc = (self.state.get("room") or {}).get("pending_choice")
        need = data.events().get(pc, {}).get("effect", {}).get("items", 0)
        picks = self.fox + [v.split("#")[0] for v in interaction.data["values"]]
        if len(picks) < need:   # 還沒選滿：先記在畫面上
            self.fox, self.notice = picks, None
            await self.redraw(interaction)
            return
        await self.act(interaction, lambda s, g: R.event_choice(s, True, g, pick=picks[:need]), keep=True)

    async def on_fox_reset(self, interaction):
        self.fox, self.notice = [], None
        await self.redraw(interaction)

    async def on_bag_tab(self, interaction):
        self.bag_tab, self.notice = interaction.data["values"][0], None
        await self.redraw(interaction)

    async def on_pending_bag(self, interaction):
        self.mode, self.bag_tab, self.notice = "bag", "pending", None
        await self.redraw(interaction)

    async def on_trial(self, interaction):
        alive = combat.living(self.state["party"])
        if len(alive) == 1:
            uid = alive[0]["uid"]
            await self.act(interaction, lambda s, g: R.event_choice(s, True, g, pick=uid), keep=True)
            return
        self.pending, self.mode = {"action": "trial", "kind": "ally"}, "target"
        await self.redraw(interaction)

    async def on_buy(self, interaction):
        idx = int(interaction.data["values"][0])
        await self.act(interaction, lambda s, g: R.buy(s, idx), keep=True)

    async def on_evacuate(self, interaction):
        await self.act(interaction, lambda s, g: R.evacuate(s))

    async def on_continue(self, interaction):
        await self.act(interaction, lambda s, g: R.continue_after_boss(s, g))

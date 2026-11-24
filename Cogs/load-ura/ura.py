"""
🌀 裏世界探索 /ura：出發 (選卡 ➔ 整裝 ➔ 出發)、探索 (選門、戰鬥、房間、背包)、接回、放棄、商店、倉庫、狀態表
規則在 Database/ura/ (引擎)、存取在 Database/Ura_DB_Manager.py、畫面文字在 Components/ura_components.py
(docs/gameplay/ura.md「第二階段第一輪：畫面」)

- 畫面全部私人 (ephemeral)；只有結算在頻道另外發一則公開的 (資料卡設成私人就不發)
- 每個動作都帶進度版本號 rev 呼叫 ura.act()：連點、舊畫面只會成功一次，舊畫面按了會重新讀進度
- 私人訊息拿 id 刪不掉，舊畫面靠 rev 失效；新畫面打開時，15 分鐘內的舊畫面盡量改成「已移到新畫面」
"""
import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Ura_DB_Manager as ura
from Database.User_DB_Manager import get_or_create_user
from Database.ura import bestiary as B, combat, data, describe, rules, run as R
from Utils.components import send_notice, notice_view
from Utils.gacha_pools import GACHA_POOLS, load_gacha_pool
from Utils.pagination import nav_buttons, paginate
from Utils.picker import GroupPickerView
from Utils.thumbnails import load_thumbnails, thumbnail_url
from Utils.guide import open_guide
from .Components import ura_components as UC

VIEW_TIMEOUT = 840   # 14 分鐘：互動 token 只有 15 分鐘，逾時時還來得及把畫面改成「已收起來」
DENY = "❌ 這不是你的畫面"
STALE = "⌛ 這個畫面已經過期了，請用 `/ura resume` 接回"
STORAGE_PER_PAGE = 10
LIST_PER_PAGE = 25   # 會變長的選單 (背包、待撿、獻寶物、狐狸、整裝道具)：超過就翻頁

PRIMARY, SECONDARY = discord.ButtonStyle.primary, discord.ButtonStyle.secondary
SUCCESS, DANGER = discord.ButtonStyle.success, discord.ButtonStyle.danger


def _btn(label: str, style, callback, disabled: bool = False) -> ui.Button:
    b = ui.Button(label=label[:80], style=style, disabled=disabled)
    b.callback = callback
    return b


def _select(placeholder: str, options: list[discord.SelectOption], callback, max_values: int = 1,
            min_values: int = 1) -> ui.ActionRow:
    n = len(options[:25])
    s = ui.Select(placeholder=placeholder[:150], options=options[:25], max_values=min(max_values, n),
                  min_values=min(min_values, n))
    s.callback = callback
    return ui.ActionRow(s)


def box_rows(view: ui.LayoutView):
    """
    畫好之後把直接放在畫面上的按鈕排 / 選單移進最後一個框 (Container) 最下面，中間用 Separator 隔開
    (按鈕包在框裡；使用者 2026-11-21 grill 定，/ura 每個畫面 build() 最後都呼叫)
    """
    kids = list(view.children)
    boxes = [c for c in kids if isinstance(c, ui.Container)]
    rows = [c for c in kids if isinstance(c, ui.ActionRow)]
    if not boxes or not rows:
        return
    for r in rows:
        view.remove_item(r)
    boxes[-1].add_item(ui.Separator())
    for r in rows:
        boxes[-1].add_item(r)


def _opt(label: str, value: str, description: str | None = None, default: bool = False) -> discord.SelectOption:
    return discord.SelectOption(label=label[:100], value=value[:100], description=(description or None) and description[:100],
                                default=default)


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


# =========================================================
# 📖 怪物圖鑑 (分區 ➔ 那一區的清單 ➔ 一隻一頁；全收獎勵按「🎁 領取」)
# =========================================================
class BestiaryView(ui.LayoutView):
    def __init__(self, user, book: dict):
        super().__init__(timeout=600)
        self.user, self.kills, self.claimed = user, book["kills"], set(book["claimed"])
        self.key, self.idx, self.notice = B.sections()[0]["key"], None, None
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
        sec = B.section(self.key) or B.sections()[0]
        self.key = sec["key"]
        self.add_item(UC.build_bestiary_container(self.key, self.idx, self.kills, self.claimed, self.notice))
        prog = B.progress(self.kills)["sections"]
        sopts = [_opt(f"{s['emoji']} {s['name']}", s["key"], f"已登錄 {prog[s['key']][0]} / {prog[s['key']][1]}" +
                      ("・🎪 活動" if s["kind"] == "fest" else ""), default=s["key"] == self.key) for s in B.sections()]
        self.add_item(_select("🗺️ 看哪一區", sopts, self.on_section))
        mopts = []
        for i, (eid, role) in enumerate(sec["enemies"]):
            e = B.entry(eid, role, self.kills)
            label = f"{e['emoji']} {e['name']}" if e["unlocked"] else "❓ ？？？"
            mopts.append(_opt(label, str(i), e["role_name"], default=i == self.idx))
        self.add_item(_select("📖 看哪一隻", mopts, self.on_monster))
        row = []
        if self.idx is not None:
            row += [_btn("◀️", SECONDARY, self.on_prev, disabled=self.idx <= 0),
                    _btn("▶️", SECONDARY, self.on_next, disabled=self.idx >= len(sec["enemies"]) - 1),
                    _btn("↩️ 回清單", SECONDARY, self.on_back)]
        for rid in [sec["key"]] + ([B.ALL_REWARD] if sec["kind"] == "zone" else []):
            if rid not in self.claimed and B.reward_ready(self.kills, rid):
                row.append(_btn(f"🎁 領取：{B.reward_info(rid)['label']}", SUCCESS, self._claimer(rid)))
        if row:
            self.add_item(ui.ActionRow(*row[:5]))

    async def redraw(self, interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_section(self, interaction):
        self.key, self.idx, self.notice = interaction.data["values"][0], None, None
        await self.redraw(interaction)

    async def on_monster(self, interaction):
        self.idx, self.notice = int(interaction.data["values"][0]), None
        await self.redraw(interaction)

    async def on_prev(self, interaction):
        self.idx, self.notice = max(0, (self.idx or 0) - 1), None
        await self.redraw(interaction)

    async def on_next(self, interaction):
        self.idx, self.notice = (self.idx or 0) + 1, None
        await self.redraw(interaction)

    async def on_back(self, interaction):
        self.idx, self.notice = None, None
        await self.redraw(interaction)

    def _claimer(self, rid: str):
        async def cb(interaction):
            res = await ura.claim_bestiary(self.user.id, rid)
            book = await ura.get_bestiary(self.user.id)
            self.kills, self.claimed = book["kills"], set(book["claimed"])
            if res["ok"]:
                lv = res["exp_result"]
                self.notice = (f"🎁 領到「{res['label']}」的獎勵：{res['money']:,} 賽錢 + {res['exp']:,} 經驗" +
                               (f"　🎉 升到 {lv['new_p']:.1f} P" if lv.get("leveled_up") else ""))
            else:
                self.notice = {"claimed": "↩️ 這個獎勵已經領過了", "not_ready": "⚠️ 還沒全部登錄，不能領"}.get(res["reason"], "❌ 找不到這個獎勵")
            await self.redraw(interaction)
        return cb


# =========================================================
# 🌀 /ura 指令
# =========================================================
class UraCog(commands.GroupCog, group_name="ura", group_description="🌀 裏世界探索：派角色深入裏世界，帶寶物回來"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.live: dict[int, RunView] = {}   # 每人目前的探索畫面 (新畫面打開時把舊的收起來)

    async def track(self, view: RunView):
        old = self.live.get(view.user.id)
        self.live[view.user.id] = view
        if old is not None and old is not view and not old.retired:
            old.retired = True
            old.stop()
            if old.last is not None:
                try:
                    await old.last.edit_original_response(view=notice_view("↪️ 這個畫面已經移到新的訊息了"))
                except discord.HTTPException:
                    pass

    def forget(self, view: RunView):
        if self.live.get(view.user.id) is view:
            del self.live[view.user.id]

    async def announce(self, interaction: discord.Interaction, state: dict, settle: dict):
        """結算公開到頻道 (資料卡設成私人就不發)"""
        user = await get_or_create_user(interaction.user.id)
        if not user.get("is_public", 1):
            return
        view = ui.LayoutView(timeout=None)
        view.add_item(UC.build_public_settle_container(interaction.user.display_name, settle))
        try:
            await interaction.followup.send(view=view, ephemeral=False)
        except discord.HTTPException:
            pass

    async def show_run(self, interaction: discord.Interaction, row: dict, mode: str = "main", notice: str | None = None):
        view = RunView(self, interaction.user, row, mode=mode, notice=notice)
        view.last = interaction
        await interaction.response.send_message(view=view, ephemeral=True)
        await self.track(view)

    @app_commands.command(name="explore", description="🌀 出發探索裏世界 (派 1～3 位角色；已經有一局就接著打)")
    async def explore(self, interaction: discord.Interaction):
        row = await ura.get_run(interaction.user.id)
        if row:
            await self.show_run(interaction, row, notice="⚠️ 你已經有一局在進行中了，接著打吧")
            return
        view = await PartyPickerView.create(self, interaction.user)
        if view is None:
            await send_notice(interaction, "❌ 你還沒有可以出征的卡",
                              footer="完整度要 0.3 以上、不能放在收藏冊；用 /card gacha 抽卡")
            return
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="resume", description="🔄 接回進行中的裏世界探索 (畫面過期、機器人重開時用)")
    async def resume(self, interaction: discord.Interaction):
        row = await ura.get_run(interaction.user.id)
        if not row:
            await send_notice(interaction, "❌ 現在沒有進行中的探索", footer="用 /ura explore 出發")
            return
        await self.show_run(interaction, row)

    @app_commands.command(name="abandon", description="🏳️ 放棄進行中的裏世界探索 (會先確認)")
    async def abandon(self, interaction: discord.Interaction):
        row = await ura.get_run(interaction.user.id)
        if not row:
            await send_notice(interaction, "❌ 現在沒有進行中的探索")
            return
        await self.show_run(interaction, row, mode="abandon")

    @app_commands.command(name="shop", description="🛒 裏世界商店：買探索用的道具和額外背包")
    async def shop(self, interaction: discord.Interaction):
        money = (await get_or_create_user(interaction.user.id))["money"]
        view = ShopView(interaction.user, money, await ura.get_storage(interaction.user.id))
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="inventory", description="📦 裏世界倉庫：寶物 (可以賣)、道具、額外背包")
    async def inventory(self, interaction: discord.Interaction):
        view = StorageView(interaction.user, await ura.get_storage(interaction.user.id))
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="status", description="📖 裏世界的狀態表 (所有狀態的效果)")
    async def status(self, interaction: discord.Interaction):
        view = ui.LayoutView(timeout=None)
        view.add_item(UC.build_status_table())
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="bestiary", description="👹 裏世界怪物圖鑑：打倒過的敵人、收集進度、全收獎勵")
    async def bestiary(self, interaction: discord.Interaction):
        book = await ura.get_bestiary(interaction.user.id)
        await interaction.response.send_message(view=BestiaryView(interaction.user, book), ephemeral=True)

    @app_commands.command(name="help", description="📖 教學書：裏世界探索的玩法與指令 (只有自己看得到)")
    async def help_book(self, interaction: discord.Interaction):
        await open_guide(interaction, "ura")


async def setup(bot: commands.Bot):
    await bot.add_cog(UraCog(bot))

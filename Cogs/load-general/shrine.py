"""
⛩️ 神社經營 /shrine：賽錢箱定時進帳、清掃、治退妖怪、參拜客；/shrine storage 神社倉庫 (道具)
數值與結算規則在 Database/Economy_DB_Manager.py
"""
import json
import os

import discord
from discord import app_commands, ui
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Database.User_DB_Manager import get_or_create_user, get_stamina
from Database import shrine_data
from Database.Item_DB_Manager import get_all_items
from Utils.components import send_notice
from Utils.pagination import nav_buttons   # 📄 共用分頁
from .Components.shrine_components import (
    build_shrine_container, build_serve_container, build_explore_container, build_cook_container, build_shop_container,
    build_gather_container, COOK_CATEGORIES, dish_category,
)
from Utils.stamina_modal import open_stamina_modal   # ⚡ 恢復體力彈窗 (跟 /profile 共用)

GATHER_TIMES = (1, 3, 5, 10)   # 快速採集的按鈕：總共採幾趟 (使用者 2026-11-16 指定)
from .Components.general_components import get_inventory_view_data, build_inventory_container
from Utils.numbers import fmt_money   # 持有金額一萬以上縮寫 (1.5M)
from Utils.guide import open_guide


THUMBNAILS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "images", "Thumbnails.json")


def guest_image_url(kind: str) -> str | None:
    """客人頭像：images/Thumbnails.json 的 "guest_<種類>" (沒有就不放圖)"""
    try:
        with open(THUMBNAILS_FILE, encoding="utf-8") as f:
            return json.load(f).get(f"guest_{kind}")
    except (OSError, ValueError):
        return None


# =========================================================
# 📦 神社倉庫 (原本的 /inventory，v0.26.000 搬到 /shrine storage)
# =========================================================
# 分類選單：(value, 名稱, emoji, 說明)
CATEGORY_OPTIONS = [
    ("all", "全部道具", "🌸", "顯示倉庫內所有道具"),
    ("consumable", "消耗品 / 食物", "🍵", "可以使用的日常消耗品"),
    ("collectible", "符卡 / 收藏品", "🎴", "具有特殊意義的收藏"),
    ("special", "特殊 / 裝備", "🛠️", "關鍵道具或強化裝備"),
    ("cuisine", "招待料理", "🍱", "招待參拜客用的食物 / 茶水 / 點心"),
]


# ---------------------------------------------------------
# 🕹️ 背包互動 UI 控制器 (Components V2 LayoutView)
# ---------------------------------------------------------
class InventoryView(ui.LayoutView):
    def __init__(self, invoker_id: int, user: discord.User, inventory: dict, item_templates: dict, color: discord.Color):
        super().__init__(timeout=120)
        self.invoker_id = invoker_id
        self.user = user
        self.inventory = inventory
        self.item_templates = item_templates
        self.color = color
        self.category = "all"
        self.current_page = 1
        self.total_pages = 1
        self.message = None  # 送出後由指令填入，供逾時時停用按鈕

        self.build()

    def build(self):
        """依目前的分類與頁數，重新組出整個畫面 (資料只算一次)"""
        data = get_inventory_view_data(self.inventory, self.item_templates, self.category, self.current_page)
        self.current_page = data["page"]
        self.total_pages = data["total_pages"]

        container = build_inventory_container(self.user, data, self.category, self.color)
        container.add_item(ui.Separator())

        # 分類選單 (顯示各分類的道具種類數)
        counts = data["category_counts"]
        self.select_category = ui.Select(
            placeholder="🌸 選擇道具分類...",
            options=[
                discord.SelectOption(
                    label=label, value=value, emoji=emoji,
                    description=f"{desc} · {counts.get(value, 0)} 種",
                    default=(value == self.category),
                )
                for value, label, emoji, desc in CATEGORY_OPTIONS
            ],
        )
        self.select_category.callback = self.on_select_category

        # 翻頁按鈕 (頭尾相接；中間的頁碼按鈕可點擊跳頁)
        self.btn_prev, self.btn_page, self.btn_next = nav_buttons(
            self.current_page, self.total_pages, self.set_page, "jump", jump_title="跳轉倉庫頁面")

        container.add_item(ui.ActionRow(self.select_category))
        container.add_item(ui.ActionRow(self.btn_prev, self.btn_page, self.btn_next))

        self.clear_items()
        self.add_item(container)

    async def update_message(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await send_notice(interaction, "❌ 只有該指令的使用者才能操作此選單！")
            return False
        return True

    async def on_timeout(self):
        """逾時後把選單與按鈕反灰，避免使用者點到沒反應的控制項"""
        for item in (self.select_category, self.btn_prev, self.btn_page, self.btn_next):
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_select_category(self, interaction: discord.Interaction):
        self.category = interaction.data["values"][0]
        self.current_page = 1
        await self.update_message(interaction)

    async def set_page(self, interaction: discord.Interaction, page: int):
        self.current_page = page   # 跳頁輸入超出範圍時 get_inventory_view_data 會限制
        await self.update_message(interaction)




class ShrineView(ui.LayoutView):
    """
    神社主畫面 (同一則訊息切換 mode)：
    main 神社 ➔ serve_pick 選客人 ➔ serve 招待；explore 採集；cook 料理；shop 雜貨店
    連動 (0.35.000)：招待缺菜 ➔「🍳 去做」到 cook (serve_queue = 客人還缺的菜，做完自動換下一道)
                    ➔ 料理缺素材 ➔「🧺 快速採集」到 gather ➔ 採齊後「🍳 回去料理」➔ 都做完「🍵 回去招待」
    """

    def __init__(self, user: discord.abc.User, result: dict, notice: str | None = None):
        super().__init__(timeout=600)
        self.user = user
        self.summary = result["summary"]
        self.notice = notice
        self.mode = "main"
        self.items, self.inventory, self.rules = {}, {}, None
        self.guest_id, self.extra = None, None
        self.explore_loc, self.explore_result, self.stamina = None, None, None
        self.cook_sel, self.shop_sel, self.money = None, None, 0
        self.cook_cat = None          # 料理畫面選的分類 (food / drink / dessert / stamina)
        self.serve_return = None      # 從招待跳到料理時記住的客人 id (「🍵 回去招待」用)
        self.serve_queue = []         # 那位客人還缺、要做的菜
        self.gather_result = None     # 快速採集剛剛的結果

    @classmethod
    async def create(cls, user, result: dict, notice: str | None = None, mode: str = "main") -> "ShrineView":
        view = cls(user, result, notice)
        view.mode = mode
        await view.reload()
        view.build()
        return view

    async def reload(self, result: dict | None = None):
        """重新讀取畫面需要的資料 (道具名稱、倉庫、規則、體力、賽錢)"""
        if result:
            self.summary = result["summary"]
        self.items = await get_all_items()
        self.inventory = await econ.get_inventory(self.user.id)
        self.rules = await econ.get_rules()
        self.stamina = await get_stamina(self.user.id)
        self.money = (await get_or_create_user(self.user.id))["money"]

    # ---------------- 畫面 ----------------
    def build(self):
        self.clear_items()
        getattr(self, f"_build_{self.mode}")()

    def _btn(self, label, style, callback, disabled=False):
        b = ui.Button(label=label, style=style, disabled=disabled)
        b.callback = callback
        return b

    def _home(self):
        return self._btn("🏠 返回神社", discord.ButtonStyle.secondary, self.on_home)

    def _build_main(self):
        s = self.summary
        container = build_shrine_container(self.user.display_name, s, self.notice, self.items)
        container.add_item(ui.Separator())
        container.add_item(ui.ActionRow(
            self._btn(f"💰 回收 ({s['box']:,})", discord.ButtonStyle.success, self.on_collect, s["box"] < 1),
            self._btn("🧹 清掃", discord.ButtonStyle.primary, self.on_clean, s["dirt"] == 0),
            self._btn(f"⚔️ 治退妖怪 ({s['youkai']})", discord.ButtonStyle.danger, self.on_defeat, s["youkai"] == 0),
            self._btn(f"🍵 招待 ({len(s['guests'])})", discord.ButtonStyle.success, self.on_serve_open, not s["guests"]),
            self._btn("🔄", discord.ButtonStyle.secondary, self.on_refresh),
        ))
        container.add_item(ui.ActionRow(
            self._btn("🗺️ 採集", discord.ButtonStyle.secondary, self.on_explore_open),
            self._btn("🍳 料理", discord.ButtonStyle.secondary, self.on_cook_open),
            self._btn("🏪 雜貨店", discord.ButtonStyle.secondary, self.on_shop_open),
        ))
        self.add_item(container)

    def _guest(self):
        return next((g for g in self.summary["guests"] if g["id"] == self.guest_id), None)

    def _build_serve_pick(self):
        container = ui.Container(accent_color=discord.Color.from_rgb(232, 120, 150))
        text = "## 🍵 招待參拜客\n選一位客人："
        if self.notice:
            text = f"{self.notice}\n\n{text}"
        container.add_item(ui.TextDisplay(text))
        select = ui.Select(placeholder="選擇要招待的客人…", options=[
            discord.SelectOption(
                label=f"{g['name']}　心情 {g['mood']}%"[:100], value=g["id"], emoji=g["emoji"],
                description=("點了：" + "、".join(self.items.get(d, {}).get("name", d) for d in g["order"]))[:100])
            for g in self.summary["guests"]
        ])
        select.callback = self.on_pick_guest
        container.add_item(ui.ActionRow(select))
        container.add_item(ui.ActionRow(self._home()))
        self.add_item(container)

    def _build_serve(self):
        g = self._guest()
        if g is None:
            self.mode, self.notice = "main", "⚠️ 這位客人已經離開了。"
            return self._build_main()
        preview = econ.calc_serve_reward(g["mood"], g["order"], self.extra, self.rules, None)
        container = build_serve_container(g, self.items, self.inventory, self.extra, preview,
                                          guest_image_url(g["kind"]), self.rules["event_dish_bonus"])
        if self.notice:
            container.add_item(ui.TextDisplay(self.notice))
        # 額外招待只列「端完點的菜之後還有剩」的料理，避免選了才發現不夠
        type_label = {"food": "食物", "drink": "茶水", "dessert": "點心"}
        left = {d: n - g["order"].count(d) for d, n in self.inventory.items() if d in self.rules["dish_types"]}
        dishes = sorted((d for d, n in left.items() if n > 0),
                        key=lambda d: (("food", "drink", "dessert").index(self.rules["dish_types"][d]), d))
        options = [discord.SelectOption(label="不額外招待", value="__none__", emoji="➖", default=self.extra is None,
                                        description="只端客人點的菜")]
        options += [discord.SelectOption(
            label=f"額外招待：{self.items.get(d, {}).get('name', d)}"[:100], value=d,
            emoji=self.items.get(d, {}).get("emoji"), default=d == self.extra,
            description=(f"{type_label[self.rules['dish_types'][d]]} · 倉庫 {self.inventory[d]} 份，端完點餐後剩 {left[d]} 份"
                         + (" · 🎪 活動料理" if d in self.rules["event_dishes"] else ""))[:100])
            for d in dishes[:24]]
        select = ui.Select(placeholder="🎁 要不要額外招待？（可以不選）", options=options)
        select.callback = self.on_pick_extra
        container.add_item(ui.ActionRow(select))
        missing = self._serve_missing(g)
        buttons = [self._btn("🍵 端上桌", discord.ButtonStyle.success, self.on_serve, bool(missing))]
        cookable = [d for d in missing if d in self.rules["recipes"]]
        if cookable:   # 🍳 缺菜 ➔ 跳到料理畫面，選好第一道缺的
            name = self.items.get(cookable[0], {}).get("name", cookable[0])
            label = f"🍳 去做{name}" + (f" 等 {len(cookable)} 道" if len(cookable) > 1 else "")
            buttons.append(self._btn(label[:80], discord.ButtonStyle.primary, self.on_serve_to_cook))
        if len(self.summary["guests"]) > 1:
            buttons.append(self._btn("👥 換客人", discord.ButtonStyle.secondary, self.on_serve_open))
        buttons.append(self._home())
        container.add_item(ui.ActionRow(*buttons))
        self.add_item(container)

    def _build_explore(self):
        container = build_explore_container(self.rules["locations"], self.stamina, econ.explore_cost(self.rules),
                                            self.explore_result, self.items)
        if self.notice:
            container.add_item(ui.TextDisplay(self.notice))
        select = ui.Select(placeholder="選擇採集地點…", options=[
            discord.SelectOption(label=loc["name"], value=key, emoji=loc["emoji"], default=key == self.explore_loc,
                                 description=loc["desc"][:100])
            for key, loc in self.rules["locations"].items()
        ][:25])
        select.callback = self.on_pick_location
        container.add_item(ui.ActionRow(select))
        cost = econ.explore_cost(self.rules)
        container.add_item(ui.ActionRow(
            self._btn(f"🗺️ 採集 1 次 (-{cost})", discord.ButtonStyle.primary, self.on_explore_1,
                      not self.explore_loc or self.stamina["stamina"] < cost),
            self._btn(f"🗺️ 連續 5 次 (-{cost * 5})", discord.ButtonStyle.primary, self.on_explore_5,
                      not self.explore_loc or self.stamina["stamina"] < cost),
            self._btn("⚡ 恢復體力", discord.ButtonStyle.secondary, self.on_stamina),
            self._home(),
        ))
        self.add_item(container)

    def _can_cook(self, dish_id: str | None) -> int:
        if not dish_id or dish_id not in self.rules["recipes"]:
            return 0
        return min(self.inventory.get(m, 0) // k for m, k in self.rules["recipes"][dish_id].items())

    def _build_cook(self):
        if self.cook_sel not in self.rules["recipes"]:
            self.cook_sel = None   # 活動料理：活動結束就做不了
        if self.cook_sel:
            self.cook_cat = dish_category(self.cook_sel, self.rules)
        container = build_cook_container(self.rules, self.items, self.inventory, self.cook_sel, self.notice,
                                         self.serve_queue if self.serve_return else None)
        # 先選分類 (Discord 選單最多 25 個，料理全放一起會放不下)
        by_cat = {}
        for d in self.rules["recipes"]:
            by_cat.setdefault(dish_category(d, self.rules), []).append(d)
        cat_select = ui.Select(placeholder="🗂️ 選擇分類…", options=[
            discord.SelectOption(label=label, value=cat, default=cat == self.cook_cat,
                                 description=f"{len(by_cat.get(cat, []))} 道 · 現在能做 "
                                             f"{sum(1 for d in by_cat.get(cat, []) if self._can_cook(d))} 道")
            for cat, label in COOK_CATEGORIES.items() if by_cat.get(cat)
        ])
        cat_select.callback = self.on_pick_cook_cat
        container.add_item(ui.ActionRow(cat_select))
        if self.cook_cat in by_cat:
            options = []
            for d in sorted(by_cat[self.cook_cat])[:25]:
                r, can = self.rules["recipes"][d], self._can_cook(d)
                need = " + ".join(f"{self.items.get(m, {}).get('name', m)}×{k}" for m, k in r.items())
                options.append(discord.SelectOption(
                    label=self.items.get(d, {}).get("name", d)[:100], value=d,
                    emoji=self.items.get(d, {}).get("emoji"), default=d == self.cook_sel,
                    description=f"{'✅ 可做 ' + str(can) + ' 鍋' if can else '❌'} · {need}"[:100]))
            select = ui.Select(placeholder="選擇料理…", options=options)
            select.callback = self.on_pick_dish
            container.add_item(ui.ActionRow(select))
        can = self._can_cook(self.cook_sel)
        container.add_item(ui.ActionRow(
            self._btn("🍳 做 1 鍋", discord.ButtonStyle.success, self.on_cook_1, can < 1),
            self._btn("🍳 做 5 鍋", discord.ButtonStyle.success, self.on_cook_5, can < 5),
            self._btn(f"🍳 全部 ({can})", discord.ButtonStyle.primary, self.on_cook_all, can < 1),
            self._home(),
        ))
        extra = []
        if self.cook_sel and can < 1:
            extra.append(self._btn("🧺 快速採集", discord.ButtonStyle.primary, self.on_gather_open))
        if self.serve_return:
            ready = not self.serve_queue
            extra.append(self._btn("🍵 回去招待", discord.ButtonStyle.success if ready else discord.ButtonStyle.secondary,
                                   self.on_back_to_serve))
        if extra:
            container.add_item(ui.ActionRow(*extra))
        self.add_item(container)

    def _gather_state(self) -> tuple[dict, dict, dict, int]:
        """快速採集要的資料：(還差的素材, 預估路線, 雜貨店能買的, 買的總價)；以做 1 鍋為目標"""
        recipe = self.rules["recipes"].get(self.cook_sel, {})
        missing = econ.missing_materials(recipe, self.inventory)
        buy, buy_cost = econ.shop_missing(missing, self.rules)
        return missing, econ.plan_gather(missing, self.rules), buy, buy_cost

    def _build_gather(self):
        if self.cook_sel not in self.rules["recipes"]:
            self.mode, self.notice = "cook", "⚠️ 這道料理現在做不了（活動可能結束了）。"
            return self._build_cook()
        missing, plan, buy, buy_cost = self._gather_state()
        cost = econ.explore_cost(self.rules)
        container = build_gather_container(self.cook_sel, missing, plan, self.rules, self.items, self.stamina,
                                           cost, buy, buy_cost, self.gather_result, self.notice)
        can_go = bool(missing) and bool(plan["stops"]) and self.stamina["stamina"] >= cost
        container.add_item(ui.ActionRow(*[
            self._btn(f"🧺 {n} 趟 (-{cost * n})", discord.ButtonStyle.primary, getattr(self, f"on_gather_{n}"), not can_go)
            for n in GATHER_TIMES
        ]))
        row = []
        if buy:
            row.append(self._btn(f"🏪 買齊人里素材 ({buy_cost:,})", discord.ButtonStyle.secondary, self.on_gather_buy,
                                 self.money < buy_cost))
        row.append(self._btn("⚡ 恢復體力", discord.ButtonStyle.secondary, self.on_stamina))
        row.append(self._btn("🍳 回去料理", discord.ButtonStyle.success if not missing else discord.ButtonStyle.secondary,
                             self.on_cook_back))
        row.append(self._home())
        container.add_item(ui.ActionRow(*row))
        self.add_item(container)

    def _build_shop(self):
        prices = self.rules["shop"]
        container = build_shop_container(prices, self.items, self.inventory, self.money, self.shop_sel, self.notice)
        select = ui.Select(placeholder="選擇要買的素材…", options=[
            discord.SelectOption(label=f"{self.items.get(m, {}).get('name', m)}　{p:,} 賽錢", value=m,
                                 emoji=self.items.get(m, {}).get("emoji"), default=m == self.shop_sel)
            for m, p in prices.items()
        ])
        select.callback = self.on_pick_shop
        container.add_item(ui.ActionRow(select))
        price = prices.get(self.shop_sel, 0)
        container.add_item(ui.ActionRow(*[
            self._btn(f"買 {n} 個 ({price * n:,})" if self.shop_sel else f"買 {n} 個", discord.ButtonStyle.primary,
                      getattr(self, f"on_buy_{n}"), not self.shop_sel or self.money < price * n)
            for n in (1, 5, 10)
        ], self._home()))
        self.add_item(container)

    # ---------------- 共用 ----------------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await send_notice(interaction, "❌ 這不是你的神社！用 `/shrine manage` 打開自己的神社吧。")
            return False
        return True

    async def _show(self, interaction: discord.Interaction, mode: str | None = None, notice: str | None = None,
                    result: dict | None = None):
        if mode:
            self.mode = mode
        self.notice = notice
        await self.reload(result)
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_home(self, interaction):
        self.serve_return, self.serve_queue, self.gather_result = None, [], None
        await self._show(interaction, "main", result=await econ.get_shrine(self.user.id))

    async def on_stamina(self, interaction):
        """⚡ 恢復體力彈窗 (Utils/stamina_modal.py)；吃完回到原本的畫面"""
        mode = self.mode

        async def done(inter, notice):
            await self._show(inter, mode, notice)
        await open_stamina_modal(interaction, done)

    async def on_refresh(self, interaction):
        await self._show(interaction, "main", result=await econ.get_shrine(self.user.id))

    # ---------------- 神社 ----------------
    async def on_collect(self, interaction):
        r = await econ.shrine_collect(self.user.id)
        notice = f"💰 回收了 `{r['collected']:,}` 賽錢！目前持有 `{fmt_money(r['money'])}` 賽錢。" if r["collected"] else "⚠️ 賽錢箱裡還沒有錢。"
        await self._show(interaction, "main", notice, r)

    async def on_clean(self, interaction):
        r = await econ.shrine_clean(self.user.id)
        await self._show(interaction, "main", "✨ 神社打掃得一塵不染！" if r["before"] else "✨ 神社本來就很乾淨。", r)

    async def on_defeat(self, interaction):
        r = await econ.shrine_defeat(self.user.id)
        notice = (f"⚔️ 打退了一隻妖怪！獲得 `{r['reward']:,}` 賽錢。\n-# 妖怪留下了晦氣，清潔度掉了一階…"
                  if r["ok"] else "⚠️ 現在沒有妖怪在作亂。")
        await self._show(interaction, "main", notice, r)

    # ---------------- 招待 ----------------
    async def on_serve_open(self, interaction):
        r = await econ.get_shrine(self.user.id)
        self.extra = None
        guests = r["summary"]["guests"]
        if len(guests) == 1:
            self.guest_id = guests[0]["id"]
            await self._show(interaction, "serve", result=r)
        elif guests:
            await self._show(interaction, "serve_pick", result=r)
        else:
            await self._show(interaction, "main", "⚠️ 現在沒有客人。", r)

    async def on_pick_guest(self, interaction):
        self.guest_id, self.extra = interaction.data["values"][0], None
        await self._show(interaction, "serve", result=await econ.get_shrine(self.user.id))

    async def on_pick_extra(self, interaction):
        value = interaction.data["values"][0]
        self.extra = None if value == "__none__" else value
        await self._show(interaction, "serve")

    async def on_serve(self, interaction):
        r = await econ.serve_guest(self.user.id, self.guest_id, self.extra)
        if not r["ok"]:
            msg = {"not_found": "⚠️ 這位客人已經離開了。",
                   "missing": "❌ 料理不夠：" + "、".join(f"{self.items.get(d, {}).get('name', d)} 還差 {k} 份" for d, k in r.get("missing", {}).items())
                   }.get(r["reason"], f"❌ 招待失敗（{r['reason']}）")
            await self._show(interaction, "serve" if r["reason"] == "missing" else "main", msg, r if "summary" in r else None)
            return
        rw, g = r["reward"], r["guest"]
        name = shrine_data.GUESTS.get(g["kind"], {}).get("name") or self.rules["guests"].get(g["kind"], {}).get("name", "客人")
        extras = []
        if rw["favorite_hit"]:
            extras.append("✨ 正中最愛 ×1.5")
        if rw["event_count"]:
            extras.append(f"🎪 活動料理 ×{self.rules['event_dish_bonus']:g}^{rw['event_count']}")
        notice = (f"🍵 **{name}** 吃得心滿意足地離開了！獲得 `{rw['total']:,}` 賽錢"
                  + (f"（{'、'.join(extras)}）" if extras else "") + f"\n-# 目前持有 `{fmt_money(r['money'])}` 賽錢")
        self.guest_id, self.extra = None, None
        self.serve_return, self.serve_queue = None, []
        await self._show(interaction, "main", notice, r)

    def _serve_missing(self, g: dict | None = None) -> dict:
        """這位客人 (點的菜 + 額外招待) 還差的料理 {料理: 份數}，照點餐順序"""
        g = g or self._guest()
        if g is None:
            return {}
        need = {}
        for d in g["order"] + ([self.extra] if self.extra else []):
            need[d] = need.get(d, 0) + 1
        return {d: k - self.inventory.get(d, 0) for d, k in need.items() if self.inventory.get(d, 0) < k}

    async def on_serve_to_cook(self, interaction):
        """🍳 招待畫面缺菜 ➔ 料理畫面，先選好第一道缺的；做完會自動換下一道"""
        await self.reload()
        queue = [d for d in self._serve_missing() if d in self.rules["recipes"]]
        if not queue:
            await self._show(interaction, "serve", "✅ 客人點的菜已經都有了！")
            return
        self.serve_return, self.serve_queue, self.cook_sel = self.guest_id, queue, queue[0]
        name = self.items.get(queue[0], {}).get("name", queue[0])
        more = f"（還有 {len(queue) - 1} 道要做）" if len(queue) > 1 else ""
        await self._show(interaction, "cook", f"🍳 客人點的 **{name}** 還沒有，先來做吧！{more}")

    async def on_back_to_serve(self, interaction):
        self.guest_id = self.serve_return
        await self._show(interaction, "serve", result=await econ.get_shrine(self.user.id))

    # ---------------- 採集 ----------------
    async def on_explore_open(self, interaction):
        self.explore_result = None
        await self._show(interaction, "explore")

    async def on_pick_location(self, interaction):
        self.explore_loc = interaction.data["values"][0]
        await self._show(interaction, "explore")

    async def _explore(self, interaction, times):
        r = await econ.explore(self.user.id, self.explore_loc, times)
        if not r["ok"]:
            msg = {"no_stamina": "❌ 體力不夠了！按「⚡ 恢復體力」吃點東西吧。", "not_found": "❌ 這個地點現在去不了（活動可能結束了）。"}
            self.explore_result = None
            await self._show(interaction, "explore", msg.get(r["reason"], "❌ 採集失敗"))
            return
        self.explore_result = r
        await self._show(interaction, "explore")

    async def on_explore_1(self, interaction):
        await self._explore(interaction, 1)

    async def on_explore_5(self, interaction):
        await self._explore(interaction, 5)

    # ---------------- 料理 ----------------
    async def on_cook_open(self, interaction):
        await self._show(interaction, "cook")

    async def on_pick_cook_cat(self, interaction):
        cat = interaction.data["values"][0]
        if cat != self.cook_cat:
            self.cook_cat, self.cook_sel = cat, None
        await self._show(interaction, "cook")

    async def on_pick_dish(self, interaction):
        self.cook_sel = interaction.data["values"][0]
        await self._show(interaction, "cook")

    async def _cook(self, interaction, times):
        r = await econ.cook(self.user.id, self.cook_sel, times)
        name = self.items.get(self.cook_sel, {}).get("name", self.cook_sel)
        if r["ok"]:
            notice = f"🍳 做好了 **{name}** ×{r['made']} 份！倉庫裡現在有 `{r['have']}` 份。"
        else:
            notice = "❌ 素材不夠：" + "、".join(f"{self.items.get(m, {}).get('name', m)} 還差 {k}" for m, k in r.get("missing", {}).items())
        await self.reload()
        if r["ok"] and self.serve_return:   # 🍵 從招待跳過來的：換下一道客人還缺的菜
            g = next((x for x in self.summary["guests"] if x["id"] == self.serve_return), None)
            missing = self._serve_missing(g) if g else {}
            self.serve_queue = [d for d in self.serve_queue if d in missing]
            if self.serve_queue:
                self.cook_sel = self.serve_queue[0]
                notice += f"\n➡️ 接著做 **{self.items.get(self.cook_sel, {}).get('name', self.cook_sel)}**"
            elif g:
                notice += "\n✅ 客人點的菜都齊了！按「🍵 回去招待」端上桌。"
        self.mode, self.notice = "cook", notice
        self.build()
        await interaction.response.edit_message(view=self)

    # ---------------- 快速採集 ----------------
    async def on_gather_open(self, interaction):
        self.gather_result = None
        await self._show(interaction, "gather")

    async def on_cook_back(self, interaction):
        self.gather_result = None
        await self._show(interaction, "cook")

    async def _gather(self, interaction, times):
        recipe = self.rules["recipes"].get(self.cook_sel)
        if recipe is None:
            await self._show(interaction, "cook", "⚠️ 這道料理現在做不了（活動可能結束了）。")
            return
        r = await econ.quick_explore(self.user.id, recipe, times)
        if not r["ok"]:
            self.gather_result = None
            msg = {"nothing_missing": "✅ 素材已經夠了！按「🍳 回去料理」做菜吧。",
                   "unavailable": "🚫 缺的素材現在沒有地方採得到（可能是活動素材）。",
                   "no_stamina": "❌ 體力不夠了！按「⚡ 恢復體力」吃點東西吧。"}.get(r["reason"], "❌ 採集失敗")
            await self._show(interaction, "gather", msg)
            return
        self.gather_result = r
        await self._show(interaction, "gather")

    async def on_gather_1(self, interaction):
        await self._gather(interaction, 1)

    async def on_gather_3(self, interaction):
        await self._gather(interaction, 3)

    async def on_gather_5(self, interaction):
        await self._gather(interaction, 5)

    async def on_gather_10(self, interaction):
        await self._gather(interaction, 10)

    async def on_gather_buy(self, interaction):
        recipe = self.rules["recipes"].get(self.cook_sel, {})
        r = await econ.shop_buy_missing(self.user.id, recipe)
        if r["ok"]:
            got = "、".join(f"{self.items.get(m, {}).get('name', m)}×{n}" for m, n in r["bought"].items())
            notice = f"🛒 在雜貨店買了 {got}，花了 `{r['cost']:,}` 賽錢。"
        elif r["reason"] == "not_enough":
            notice = f"❌ 賽錢不足！需要 `{r['cost']:,}`，你只有 `{fmt_money(r['money'])}`。"
        else:
            notice = "⚠️ 沒有需要在雜貨店買的素材。"
        await self._show(interaction, "gather", notice)

    async def on_cook_1(self, interaction):
        await self._cook(interaction, 1)

    async def on_cook_5(self, interaction):
        await self._cook(interaction, 5)

    async def on_cook_all(self, interaction):
        r = self.rules["recipes"][self.cook_sel]
        await self._cook(interaction, max(1, min(self.inventory.get(m, 0) // k for m, k in r.items())))

    # ---------------- 雜貨店 ----------------
    async def on_shop_open(self, interaction):
        await self._show(interaction, "shop")

    async def on_pick_shop(self, interaction):
        self.shop_sel = interaction.data["values"][0]
        await self._show(interaction, "shop")

    async def _buy(self, interaction, n):
        r = await econ.shop_buy(self.user.id, self.shop_sel, n)
        name = self.items.get(self.shop_sel, {}).get("name", self.shop_sel)
        notice = (f"🛒 買了 **{name}** ×{n}，花了 `{r['cost']:,}` 賽錢。" if r["ok"]
                  else f"❌ 賽錢不足！需要 `{r.get('cost', 0):,}`，你只有 `{fmt_money(r.get('money', 0))}`。")
        await self._show(interaction, "shop", notice)

    async def on_buy_1(self, interaction):
        await self._buy(interaction, 1)

    async def on_buy_5(self, interaction):
        await self._buy(interaction, 5)

    async def on_buy_10(self, interaction):
        await self._buy(interaction, 10)


class ShrineCog(commands.GroupCog, group_name="shrine", group_description="⛩️ 神社經營與神社倉庫"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="manage", description="⛩️ 打開自己的神社：賽錢箱、清掃、治退妖怪、參拜客")
    async def manage(self, interaction: discord.Interaction):
        await self._open(interaction, "main")

    async def _open(self, interaction: discord.Interaction, mode: str, notice: str | None = None, result: dict | None = None):
        await interaction.response.defer(ephemeral=True)
        result = result or await econ.get_shrine(interaction.user.id)
        view = await ShrineView.create(interaction.user, result, notice, mode)
        await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(name="explore", description="🗺️ 到幻想鄉各地採集料理素材 (消耗體力)")
    async def explore(self, interaction: discord.Interaction):
        await self._open(interaction, "explore")

    @app_commands.command(name="cook", description="🍳 用素材做招待料理 (一鍋 2 份)")
    async def cook(self, interaction: discord.Interaction):
        await self._open(interaction, "cook")

    @app_commands.command(name="shop", description="🏪 人間之里雜貨店：買基本食材")
    async def shop(self, interaction: discord.Interaction):
        await self._open(interaction, "shop")

    @app_commands.command(name="collect", description="💰 回收神社賽錢箱裡的賽錢")
    async def collect(self, interaction: discord.Interaction):
        r = await econ.shrine_collect(interaction.user.id)
        notice = f"💰 回收了 `{r['collected']:,}` 賽錢！目前持有 `{fmt_money(r['money'])}` 賽錢。" if r["collected"] else "⚠️ 賽錢箱裡還沒有錢。"
        await self._open(interaction, "main", notice, r)


    @app_commands.command(name="storage", description="📦 檢視自己或他人的神社倉庫 (道具)")
    @app_commands.describe(target="要檢視的成員 (留空則檢視自己)")
    async def storage(self, interaction: discord.Interaction, target: discord.User = None):
        await interaction.response.defer(ephemeral=True)
        target_user = target or interaction.user
        user_data = await get_or_create_user(target_user.id)
        if target and not bool(user_data.get("is_public", 1)) and target.id != interaction.user.id:
            await send_notice(interaction, f"🔒 **{target_user.display_name}** 已設定個人卡片為私密，無法檢視其神社倉庫！")
            return

        raw_inv = user_data.get("inventory", "{}")
        if isinstance(raw_inv, str):
            try:
                inventory = json.loads(raw_inv)
            except json.JSONDecodeError:
                inventory = {}
        else:
            inventory = raw_inv or {}
        item_templates = await get_all_items()
        color = getattr(target_user, "color", discord.Color.default())
        accent_color = color if color != discord.Color.default() else discord.Color.dark_theme()
        view = InventoryView(interaction.user.id, target_user, inventory, item_templates, accent_color)
        view.message = await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(name="help", description="📖 教學書：神社經營的玩法與指令 (只有自己看得到)")
    async def help_book(self, interaction: discord.Interaction):
        await open_guide(interaction, "shrine")


async def setup(bot: commands.Bot):
    await bot.add_cog(ShrineCog(bot))

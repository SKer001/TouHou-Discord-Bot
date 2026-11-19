"""
🗂️ 共用控制台：分組選單 ➔ 選項選單 (翻頁) ➔ 按鈕 (0.35.035 管理員稱號 / 名片控制台；0.35.039 搬來 Utils，玩家的修改稱號 / 名片也用)

子類別要給：
- groups：{分組 key: [選項 id, ...]} (照顯示順序；空的分組不列)
- load()：重新讀資料 (每次操作後呼叫)
- group_name(key)、group_status(key) (分組選項說明)、item_label(id)、item_status(id) (選項說明)
- header() (控制台最上面的標題文字)、detail(id) (選好之後顯示的說明)、accent()
- actions() ➔ [(按鈕文字, 樣式, callback, 停用?), ...]
- preview_container() ➔ 預覽用的另一個 Container (放在控制台上面)，不需要就回傳 None
- allowed(interaction) ➔ 誰可以按 (預設 = 打開控制台的人；管理員控制台再加 is_admin)

每次操作後重新讀資料，結果顯示在最上面 (self.notice)。翻頁用 Utils/pagination.py。
"""
import discord
from discord import ui

from Utils.components import send_notice
from Utils.pagination import nav_buttons, paginate

PICKER_PAGE = 25   # 分組 / 選項選單一頁幾個 (Discord 上限 25)；超過才多一排翻頁按鈕


class GroupPickerView(ui.LayoutView):
    GROUP_PLACEHOLDER = "🗂️ 分組"
    ITEM_PLACEHOLDER = "選一個…"
    DENY_TEXT = "❌ 這不是你的控制台"

    def __init__(self, owner_id: int, user, groups: dict[str, list[str]], timeout: float = 900):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.user = user
        self.groups = {k: v for k, v in groups.items() if v}
        self.group = next(iter(self.groups))
        self.group_page = 1
        self.item_page = 1
        self.selected = None   # 選好的選項 id
        self.notice = None     # 上一次操作的結果

    # ---------- 子類別要實作 ----------
    async def load(self): ...
    def group_name(self, key: str) -> str: return key
    def group_status(self, key: str) -> str: return ""
    def item_label(self, item: str) -> str: return item
    def item_status(self, item: str) -> str: return ""
    def header(self) -> str: return ""
    def detail(self, item: str) -> str: return ""
    def accent(self) -> discord.Color | None: return None
    def actions(self) -> list: return []
    def preview_container(self) -> ui.Container | None: return None

    def allowed(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    # ---------- 共用 ----------
    def open_at(self, item: str | None):
        """一打開就翻到 item 所在的分組與那一頁 (例如戴著的稱號)；找不到就維持第一組"""
        for key, items in self.groups.items():
            if item in items:
                self.group = key
                self.group_page = list(self.groups).index(key) // PICKER_PAGE + 1
                self.item_page = items.index(item) // PICKER_PAGE + 1
                return

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.allowed(interaction):
            await send_notice(interaction, self.DENY_TEXT)
            return False
        return True

    async def refresh(self):
        await self.load()
        self.build()

    def build(self):
        self.clear_items()
        preview = self.preview_container()
        if preview is not None:
            self.add_item(preview)
        c = ui.Container(accent_color=self.accent())
        if self.notice:
            c.add_item(ui.TextDisplay(self.notice))
            c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(self.header()))
        if self.selected:
            c.add_item(ui.Separator())
            c.add_item(ui.TextDisplay(self.detail(self.selected)))
        self.add_item(c)

        # ① 分組選單
        gp = paginate(list(self.groups), self.group_page, PICKER_PAGE)
        self.group_page = gp.page
        gsel = ui.Select(placeholder=self.GROUP_PLACEHOLDER + (f" (第 {gp.page} / {gp.total} 頁)" if gp.total > 1 else ""),
                         options=[discord.SelectOption(label=self.group_name(k)[:100], value=k, default=k == self.group,
                                                       description=self.group_status(k)[:100] or None) for k in gp.items])
        gsel.callback = self.on_group
        self.add_item(ui.ActionRow(gsel))
        if gp.total > 1:
            self.add_item(ui.ActionRow(*nav_buttons(gp.page, gp.total, self.set_group_page, "compact")))

        # ② 那組的選項選單
        ip = paginate(self.groups[self.group], self.item_page, PICKER_PAGE)
        self.item_page = ip.page
        isel = ui.Select(placeholder=f"{self.ITEM_PLACEHOLDER}：{self.group_name(self.group)}"[:120]
                         + (f" (第 {ip.page} / {ip.total} 頁)" if ip.total > 1 else ""),
                         options=[discord.SelectOption(label=self.item_label(i)[:100], value=i, default=i == self.selected,
                                                       description=self.item_status(i)[:100] or None) for i in ip.items])
        isel.callback = self.on_item
        self.add_item(ui.ActionRow(isel))
        if ip.total > 1:
            self.add_item(ui.ActionRow(*nav_buttons(ip.page, ip.total, self.set_item_page)))

        # ③ 操作按鈕
        row = []
        for label, style, cb, disabled in self.actions():
            b = ui.Button(label=label, style=style, disabled=disabled)
            b.callback = cb
            row.append(b)
        if row:
            self.add_item(ui.ActionRow(*row))

    async def done(self, interaction: discord.Interaction, notice: str | None = None):
        self.notice = notice
        await self.refresh()
        await interaction.response.edit_message(view=self)

    def select_item(self, item: str | None):
        """選了一個選項 (子類別可以覆寫，例如順便決定預覽)"""
        self.selected = item

    async def on_group(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        if value in self.groups:
            self.group, self.item_page = value, 1
            self.select_item(None)
        await self.done(interaction)

    async def set_group_page(self, interaction: discord.Interaction, page: int):
        self.group_page = page
        await self.done(interaction)

    async def set_item_page(self, interaction: discord.Interaction, page: int):
        self.item_page = page
        await self.done(interaction)

    async def on_item(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        self.select_item(value if any(value in items for items in self.groups.values()) else None)
        await self.done(interaction)

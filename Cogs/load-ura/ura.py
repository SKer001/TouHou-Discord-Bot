"""
🌀 裏世界探索 /ura：出發 (選卡 ➔ 整裝 ➔ 出發)、探索 (選門、戰鬥、房間、背包)、接回、放棄、商店、倉庫、狀態表
規則在 Database/ura/ (引擎)、存取在 Database/Ura_DB_Manager.py、畫面文字在 Components/ura_components.py
(docs/gameplay/ura.md「第二階段第一輪：畫面」)

- 畫面全部私人 (ephemeral)；只有結算在頻道另外發一則公開的 (資料卡設成私人就不發)
- 每個動作都帶進度版本號 rev 呼叫 ura.act()：連點、舊畫面只會成功一次，舊畫面按了會重新讀進度
- 私人訊息拿 id 刪不掉，舊畫面靠 rev 失效；新畫面打開時，15 分鐘內的舊畫面盡量改成「已移到新畫面」

📦 這個檔案只留 UraCog 指令與 setup；畫面拆在 views/ 底下，這裡把它們的名字全部轉出來
   (測試、教學書照舊從這個模組拿 RunView、VIEW_TIMEOUT、STORAGE_PER_PAGE、_select…)：
   - views/common.py        共用小工具 (VIEW_TIMEOUT、DENY、_btn、_select、box_rows、_opt…)
   - views/run.py           RunView 進行中的一局
   - views/setup.py         PartyPickerView、PocketModal、LoadoutView (出發：選隊伍 ➔ 整裝)
   - views/shop_storage.py  ShopView、StorageView
   - views/bestiary.py      BestiaryView

⚠️ 對這個模組的屬性賦值 (測試會寫 cogmod._select = 會記錄的版本) 會一起改到「本來就有這個名字」的 views 子模組，
   所以跟拆開前一樣會生效 (跟 Database/User_DB_Manager.py 同一套做法)。新增子模組要加進下面的 _PARTS (照依賴順序)，
   也要加進 Utils/reloader.py 的 VIEW_ORDER。子模組不要用 setup 這個名字匯入 (會蓋掉最下面的 setup())。
"""
import sys
import types

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
from .views import common as _v_common, run as _v_run, setup as _v_setup, shop_storage as _v_shop_storage, bestiary as _v_bestiary

_PARTS = (_v_common, _v_run, _v_setup, _v_shop_storage, _v_bestiary)   # 依賴順序

for _part in _PARTS:
    globals().update({_k: _v for _k, _v in vars(_part).items() if not _k.startswith("__")})
del _part


class _EntryModule(types.ModuleType):
    """cogmod.X = 值 ➔ 入口自己改，views 子模組裡同名的也一起改 (函式是在子模組的命名空間裡找名字的)"""

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name.startswith("__"):
            return
        for part in self.__dict__.get("_PARTS", ()):
            if name in vars(part):
                setattr(part, name, value)


sys.modules[__name__].__class__ = _EntryModule


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

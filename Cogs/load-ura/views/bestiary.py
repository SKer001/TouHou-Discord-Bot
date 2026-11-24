"""
🌀 裏世界畫面：📖 怪物圖鑑 BestiaryView
(從 Cogs/load-ura/ura.py 拆出來)
"""
from discord import ui

from Database import Ura_DB_Manager as ura
from Database.ura import bestiary as B
from Utils.components import send_notice
from ..Components import ura_components as UC
from .common import DENY, SECONDARY, SUCCESS, _btn, _select, box_rows, _opt


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

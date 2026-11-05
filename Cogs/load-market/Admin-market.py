"""
🛠️ /admin-market：直接設定特定角色、特定階級的市值 (測試 / 調整用)
"""
import importlib

import discord
from discord import app_commands
from discord.ext import commands

from Database import Economy_DB_Manager as econ
from Utils.config import is_admin
from Utils.components import send_notice

AUTOCOMPLETE_LIMIT = 25


def market_mod():
    return importlib.import_module("Cogs.load-market.market")


class MarketAdmin(commands.GroupCog, group_name="admin-market", group_description="【開發者專用】市值管理"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _deny(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user):
            await send_notice(interaction, "❌ 無權限")
            return True
        return False

    async def pool_autocomplete(self, interaction, current: str):
        g = market_mod().gacha_mod()
        return [app_commands.Choice(name=f"{p['name']} ({p['desc']})"[:100], value=key)
                for key, p in g.GACHA_POOLS.items() if current.lower() in f"{key} {p['name']}".lower()][:AUTOCOMPLETE_LIMIT]

    async def character_autocomplete(self, interaction, current: str):
        g = market_mod().gacha_mod()
        pool_key = market_mod().resolve_pool(getattr(interaction.namespace, "pool", None))
        current = current.strip().lower()
        return [app_commands.Choice(name=f"{d['emoji']} {d['name']} ({k})"[:100], value=k)
                for k, d in g.GACHA_POOL.items()
                if d["pool"] == pool_key and (not current or current in k.lower() or current in d["name"].lower())][:AUTOCOMPLETE_LIMIT]

    async def rarity_autocomplete(self, interaction, current: str):
        m = market_mod()
        data = m.gacha_mod().GACHA_POOL.get(m.resolve_character(getattr(interaction.namespace, "character", None)))
        if not data:
            return []
        prices = await econ.get_market_prices()
        key = m.resolve_character(interaction.namespace.character)
        return [app_commands.Choice(name=f"{r} · 目前 {econ.price_of(prices, key, r):,.0f}", value=r) for r in data["rarities"]]

    async def _resolve(self, interaction, pool, character, rarity):
        m = market_mod()
        pool, character = m.resolve_pool(pool), m.resolve_character(character)
        data = m.gacha_mod().GACHA_POOL.get(character)
        if data is None or data["pool"] != pool or rarity not in data["rarities"]:
            await send_notice(interaction, "❌ 找不到這個角色或階級，請從選單中選擇。")
            return None
        return character, data

    @app_commands.command(name="set_price", description="【開發者專用】設定特定角色特定階級的市值 (完整度 0.5 的價格)")
    @app_commands.describe(pool="卡池", character="角色", rarity="階級", price="新的市值 (每日結算時仍不會低於官方價)")
    @app_commands.autocomplete(pool=pool_autocomplete, character=character_autocomplete, rarity=rarity_autocomplete)
    async def set_price(self, interaction: discord.Interaction, pool: str, character: str, rarity: str, price: app_commands.Range[int, 1]):
        if await self._deny(interaction):
            return
        found = await self._resolve(interaction, pool, character, rarity)
        if not found:
            return
        key, data = found
        old = econ.price_of(await econ.get_market_prices(), key, rarity)
        await econ.admin_set_price(key, rarity, price)
        note = "" if price >= econ.OFFICIAL_PRICES.get(rarity, 1) else f"\n-# ⚠️ 低於官方價 `{econ.OFFICIAL_PRICES[rarity]:,}`，下次每日結算會被拉回官方價"
        await send_notice(interaction, f"🛠️ [Dev] {data['emoji']} **{data['name']}** `[{rarity}]` 市值 `{old:,.0f}` ➔ `{price:,}`{note}")

    @app_commands.command(name="reset_price", description="【開發者專用】把特定角色特定階級的市值改回官方價")
    @app_commands.describe(pool="卡池", character="角色", rarity="階級")
    @app_commands.autocomplete(pool=pool_autocomplete, character=character_autocomplete, rarity=rarity_autocomplete)
    async def reset_price(self, interaction: discord.Interaction, pool: str, character: str, rarity: str):
        if await self._deny(interaction):
            return
        found = await self._resolve(interaction, pool, character, rarity)
        if not found:
            return
        key, data = found
        await econ.admin_set_price(key, rarity, None)
        await send_notice(interaction, f"🛠️ [Dev] {data['emoji']} **{data['name']}** `[{rarity}]` 市值已改回官方價 `{econ.OFFICIAL_PRICES.get(rarity, 1):,}`")


async def setup(bot: commands.Bot):
    await bot.add_cog(MarketAdmin(bot))

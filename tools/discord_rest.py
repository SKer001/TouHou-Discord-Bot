"""
🌐 Discord REST 小工具 (給 tools/ 底下的腳本共用)

- 只用機器人自己的 Token 呼叫 Discord REST API，不連 Gateway，所以機器人正在執行時也能同時使用
- 測試頻道：.env 的 TEST_CHANNEL_ID，沒有設定時用 LOG_CHANNEL_ID
- render_components()：把訊息的 V2 元件 JSON 印成文字 (跟 botcli 的畫面格式一致)
"""
import asyncio
import os

import aiohttp
from dotenv import load_dotenv

load_dotenv()

API = "https://discord.com/api/v10"
COMPONENTS_V2_FLAG = 1 << 15

BUTTON_STYLES = {1: "藍", 2: "灰", 3: "綠", 4: "紅", 5: "連結", 6: "購買"}
SELECT_TYPES = {3: "選單", 5: "成員選單", 6: "身分組選單", 7: "提及選單", 8: "頻道選單"}


def test_channel_id() -> int:
    raw = os.getenv("TEST_CHANNEL_ID") or os.getenv("LOG_CHANNEL_ID")
    if not raw or not raw.strip().isdigit():
        raise SystemExit("❌ .env 沒有設定 TEST_CHANNEL_ID 或 LOG_CHANNEL_ID")
    return int(raw)


class DiscordREST:
    """async with DiscordREST() as api: await api.get(...)"""

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("DISCORD_TOKEN")
        if not self.token:
            raise SystemExit("❌ .env 沒有設定 DISCORD_TOKEN")
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers={
            "Authorization": f"Bot {self.token}",
            "User-Agent": "DiscordBot (TouHou-Discord-Bot tools, 1.0)",
        })
        return self

    async def __aexit__(self, *exc):
        await self.session.close()

    async def request(self, method: str, path: str, **kwargs):
        """回傳 (狀態碼, JSON 或文字)；遇到 429 會依 retry_after 自動重試"""
        for _ in range(5):
            async with self.session.request(method, API + path, **kwargs) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = await resp.text()
                if resp.status == 429 and isinstance(data, dict):
                    await asyncio.sleep(float(data.get("retry_after", 1)) + 0.1)
                    continue
                return resp.status, data
        return 429, {"message": "rate limited"}

    async def get(self, path: str, **params):
        return await self.request("GET", path, params=params or None)

    async def post(self, path: str, payload: dict):
        return await self.request("POST", path, json=payload)

    async def patch(self, path: str, payload: dict):
        return await self.request("PATCH", path, json=payload)


def describe_error(data) -> str:
    """把 Discord 的 400 錯誤 (含巢狀 errors) 整理成可讀的文字"""
    if not isinstance(data, dict):
        return str(data)
    lines = [f"{data.get('message', '錯誤')} (code {data.get('code')})"]

    def walk(node, path):
        if isinstance(node, dict):
            if "_errors" in node:
                for err in node["_errors"]:
                    lines.append(f"  · {'.'.join(path) or '(root)'}：{err.get('message')} [{err.get('code')}]")
            for key, value in node.items():
                if key != "_errors":
                    walk(value, path + [key])

    walk(data.get("errors", {}), [])
    return "\n".join(lines)


def render_components(components: list, prefix: str = "") -> list[str]:
    """把 V2 元件 JSON 轉成文字行"""
    lines = []
    for comp in components or []:
        t = comp.get("type")
        if t == 17:     # Container
            color = comp.get("accent_color")
            lines.append(f"{prefix}┌─ Container  色條 {'#%06x' % color if color is not None else '無'}")
            lines += render_components(comp.get("components"), prefix + "│ ")
            lines.append(f"{prefix}└─")
        elif t == 9:    # Section
            lines += render_components(comp.get("components"), prefix)
            acc = comp.get("accessory") or {}
            if acc.get("type") == 11:
                lines.append(f"{prefix}  🖼️ 縮圖：{acc.get('media', {}).get('url', '').rsplit('/', 1)[-1]}")
            elif acc:
                lines += render_components([acc], prefix + "  ")
        elif t == 10:   # TextDisplay
            for line in comp.get("content", "").split("\n"):
                lines.append(f"{prefix}{line}")
        elif t == 14:   # Separator
            lines.append(f"{prefix}────────────")
        elif t == 11:
            lines.append(f"{prefix}🖼️ 縮圖：{comp.get('media', {}).get('url', '').rsplit('/', 1)[-1]}")
        elif t == 12:   # MediaGallery
            lines.append(f"{prefix}🖼️ 圖庫 ({len(comp.get('items', []))} 張)")
        elif t == 1:    # ActionRow
            buttons = [c for c in comp.get("components", []) if c.get("type") == 2]
            if buttons:
                parts = []
                for b in buttons:
                    emoji = (b.get("emoji") or {}).get("name", "")
                    state = "✖" if b.get("disabled") else ""
                    parts.append(f"[{BUTTON_STYLES.get(b.get('style'), '?')}{state}] {emoji + ' ' if emoji else ''}{b.get('label', '')}")
                lines.append(prefix + "  ".join(parts))
            others = [c for c in comp.get("components", []) if c.get("type") != 2]
            lines += render_components(others, prefix)
        elif t in SELECT_TYPES:
            state = "（停用）" if comp.get("disabled") else ""
            lines.append(f"{prefix}▼ {SELECT_TYPES[t]}：{comp.get('placeholder', '')}{state}")
            for opt in comp.get("options", []):
                emoji = (opt.get("emoji") or {}).get("name", "")
                mark = " ✓" if opt.get("default") else ""
                lines.append(f"{prefix}    · {opt.get('value')} = {emoji + ' ' if emoji else ''}{opt.get('label')}{mark}")
        else:
            lines.append(f"{prefix}[元件 type {t}]")
    return lines


def count_components(components: list) -> int:
    total = 0
    for comp in components or []:
        total += 1
        total += count_components(comp.get("components"))
        if comp.get("accessory"):
            total += 1
    return total

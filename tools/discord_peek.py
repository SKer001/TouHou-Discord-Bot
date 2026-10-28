"""
👀 discord_peek：讀取測試頻道最新的訊息，把機器人實際送出的 V2 畫面印成文字

    python tools/discord_peek.py                 # 最新 5 則
    python tools/discord_peek.py -n 10           # 最新 10 則
    python tools/discord_peek.py --bot-only      # 只看機器人送出的
    python tools/discord_peek.py --raw           # 印出原始 JSON
    python tools/discord_peek.py --channel 123   # 指定其他頻道

- 頻道預設為 .env 的 TEST_CHANNEL_ID，沒有就用 LOG_CHANNEL_ID
- 只用 REST API，機器人正在執行時也能使用；ephemeral (僅自己可見) 的訊息 API 讀不到
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from discord_rest import (
    COMPONENTS_V2_FLAG, DiscordREST, count_components, describe_error, render_components, test_channel_id,
)


def format_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return iso or "?"


async def main(args) -> int:
    channel_id = args.channel or test_channel_id()
    async with DiscordREST() as api:
        status, me = await api.get("/users/@me")
        if status != 200:
            print(f"❌ Token 無效：{describe_error(me)}")
            return 1
        status, messages = await api.get(f"/channels/{channel_id}/messages", limit=min(100, args.n * (4 if args.bot_only else 1)))
        if status != 200:
            print(f"❌ 讀取頻道 {channel_id} 失敗：{describe_error(messages)}")
            return 1

    if args.bot_only:
        messages = [m for m in messages if m["author"]["id"] == me["id"]]
    messages = list(reversed(messages[: args.n]))   # 舊 ➔ 新
    print(f"👀 頻道 {channel_id} · 最新 {len(messages)} 則（由舊到新）· 機器人：{me['username']}")

    for msg in messages:
        author = msg["author"]
        tag = "🤖" if author.get("bot") else "👤"
        v2 = "V2" if msg.get("flags", 0) & COMPONENTS_V2_FLAG else "舊版"
        edited = " · 已編輯" if msg.get("edited_timestamp") else ""
        via = ""
        meta = msg.get("interaction_metadata") or msg.get("interaction")
        if meta:
            via = f" · 回應 {meta.get('user', {}).get('username', '?')} 的互動"
        print(f"\n━━━ {tag} {author.get('global_name') or author['username']} · {format_time(msg['timestamp'])}{edited} · {v2}{via} · id {msg['id']} ━━━")
        if args.raw:
            print(json.dumps({k: msg.get(k) for k in ("content", "embeds", "components", "flags")}, ensure_ascii=False, indent=2))
            continue
        if msg.get("content"):
            for line in msg["content"].split("\n"):
                print(f"  {line}")
        for embed in msg.get("embeds", []):
            print(f"  [Embed] {embed.get('title', '')}  {embed.get('description', '')[:200]}")
        if msg.get("components"):
            for line in render_components(msg["components"]):
                print("  " + line)
            if msg.get("flags", 0) & COMPONENTS_V2_FLAG:
                print(f"  -- 元件數 {count_components(msg['components'])}/40")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="讀取 Discord 測試頻道的最新訊息")
    parser.add_argument("-n", type=int, default=5, help="顯示幾則 (預設 5)")
    parser.add_argument("--channel", type=int, help="頻道 ID (預設 TEST_CHANNEL_ID / LOG_CHANNEL_ID)")
    parser.add_argument("--bot-only", action="store_true", help="只顯示機器人送出的訊息")
    parser.add_argument("--raw", action="store_true", help="印出原始 JSON")
    sys.exit(asyncio.run(main(parser.parse_args())))

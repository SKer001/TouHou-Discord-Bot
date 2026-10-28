"""
🖥️ botcli：不連 Discord，用指令列「假裝打指令」測試機器人

    python tools/botcli.py "/card gacha pool:classic pull_type:10" "click 繼續十連" "/card inventory"
    python tools/botcli.py --file steps.txt
    python tools/botcli.py                 # 互動模式 (一行一個步驟，輸入 help 看說明)

- 載入 Cogs/load-*/ 底下的所有模組 (跟 Main.py 一樣)，但不登入 Discord、不載入 Logger
- 資料庫一律使用沙盒 .botcli/ (第一次執行時從 Database/ 複製一份)，絕不寫入真實的 Users.db / Item.db
- 沙盒會保留到下次執行 (卡牌、賽錢會累積)；--reset 重新從 Database/ 複製，--fresh 從空資料庫開始
- 畫面 (View) 只存在於同一次執行中：要點按鈕就把指令與點擊寫在同一次執行的步驟裡

步驟語法 (輸入 help 會印出同樣內容)：
  /群組 指令 參數:值 ...      執行斜線指令，例如 /card gacha pool:classic pull_type:10
                              含空白的值用引號："name:博麗 靈夢"；成員參數用 me、@名稱 或使用者 ID
  ? /群組 指令 參數 [已填參數:值 ...] [current:輸入中的文字]
                              查看 autocomplete 選項，例如 ? /card fusion character pool:classic
  click <按鈕>                點按鈕：b2，或按鈕文字的一部分 (例如 click 繼續十連)
  select <選單> <值...>        選選單：s1 th06，或 select 卡池 th06；多選用空白分隔；值可用 value 或選項文字
  modal 欄位:值 ...           送出目前開著的 Modal，欄位可用標籤文字的一部分
  as <me|@名稱|ID>            切換下指令的人 (預設是 .env 的第一個管理員)
  msg <編號>                  之後的 click / select 對準第幾則訊息 (預設是最新被更新的那則)
  show [編號]                 重新印出某則訊息
  users                       列出沙盒中的玩家
  sql <SELECT ...>            在沙盒 Users.db 上執行唯讀查詢
  commands                    列出所有斜線指令與參數
"""
import argparse
import asyncio
import os
import shlex
import shutil
import sqlite3
import sys
import traceback
import warnings
import zlib
from datetime import datetime, timezone

warnings.filterwarnings("ignore", category=DeprecationWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

SANDBOX_DIR = os.path.join(ROOT, ".botcli")
GUILD_ID = 900000000000000001
CHANNEL_ID = 900000000000000002


# =========================================================
# 🗄️ 沙盒資料庫
# =========================================================
def prepare_sandbox(reset: bool, fresh: bool):
    global SANDBOX_DIR
    """把 Database/*.db 用 sqlite backup API 複製到 .botcli/ (機器人在跑時也能安全複製)"""
    os.makedirs(SANDBOX_DIR, exist_ok=True)
    for name in ("Users.db", "Item.db"):
        dst = os.path.join(SANDBOX_DIR, name)
        if fresh and name == "Users.db":
            if os.path.exists(dst):
                os.remove(dst)
            continue
        if os.path.exists(dst) and not reset:
            continue
        src = os.path.join(ROOT, "Database", name)
        if not os.path.exists(src):
            continue
        if os.path.exists(dst):
            os.remove(dst)
        src_uri = "file:" + src.replace("\\", "/") + "?mode=ro"   # 唯讀開啟，保證不會動到真實資料庫
        with sqlite3.connect(src_uri, uri=True) as s, sqlite3.connect(dst) as d:
            s.backup(d)


def point_databases_to_sandbox():
    from Database import User_DB_Manager as udm
    from Database import Item_DB_Manager as idm
    udm.DB_PATH = os.path.join(SANDBOX_DIR, "Users.db")
    idm.DB_PATH = os.path.join(SANDBOX_DIR, "Item.db")
    return udm, idm


# =========================================================
# 🎭 假的 Discord 物件
# =========================================================
class FakeAsset:
    def __init__(self, user_id: int):
        self.url = f"https://cdn.discordapp.com/embed/avatars/{user_id % 6}.png"

    def with_size(self, _size):
        return self

    async def read(self):
        raise RuntimeError("botcli 不下載頭像")   # get_avatar_dominant_color 會退回預設色


class FakeUser:
    def __init__(self, user_id: int, name: str):
        self.id = user_id
        self.name = name
        self.display_name = name
        self.global_name = name
        self.mention = f"<@{user_id}>"
        self.bot = False
        self.color = self.colour = __import__("discord").Color.default()
        self.display_avatar = self.avatar = FakeAsset(user_id)

    def __str__(self):
        return self.name


class FakeGuild:
    def __init__(self, members: dict):
        self.id = GUILD_ID
        self.name = "botcli 測試伺服器"
        self._members = members

    @property
    def members(self):
        return list(self._members.values())

    def get_member(self, user_id):
        return self._members.get(user_id)


class FakeChannel:
    id = CHANNEL_ID
    name = "botcli"
    mention = f"<#{CHANNEL_ID}>"


class FakeAttachment:
    """add_items_batch 之類的檔案參數：值填本機檔案路徑"""
    def __init__(self, path: str):
        self.path = path
        self.filename = os.path.basename(path)

    async def read(self):
        with open(self.path, "rb") as f:
            return f.read()


class Message:
    """一則機器人送出的訊息 (只保存目前的 View)"""
    def __init__(self, cli, view, ephemeral: bool, author_id: int):
        self.cli = cli
        self.id = len(cli.messages) + 1
        self.view = view
        self.ephemeral = ephemeral
        self.author_id = author_id
        cli.messages.append(self)

    async def edit(self, view=None, **kwargs):
        _reject_legacy(kwargs)
        if view is not None:
            self.view = view
        self.cli.touched(self, "edit")


def _reject_legacy(kwargs: dict):
    """專案規定一律用 Components V2：帶 content / embed 的回覆直接標成錯誤"""
    legacy = [k for k in ("content", "embed", "embeds") if kwargs.get(k)]
    if legacy:
        raise AssertionError(f"回覆帶了 {legacy}，專案規定一律使用 Components V2")


class FakeResponse:
    def __init__(self, interaction):
        self._i = interaction
        self._done = False

    def is_done(self):
        return self._done

    def _mark(self):
        if self._done:
            raise RuntimeError("這個互動已經回應過了 (Discord 會回 InteractionResponded)")
        self._done = True

    async def send_message(self, content=None, *, view=None, ephemeral=False, **kwargs):
        _reject_legacy({"content": content, **kwargs})
        self._mark()
        msg = Message(self._i.cli, view, ephemeral, self._i.user.id)
        self._i.original = msg
        self._i.cli.touched(msg, "send")

    async def edit_message(self, content=None, *, view=None, **kwargs):
        _reject_legacy({"content": content, **kwargs})
        self._mark()
        target = self._i.message
        if target is None:
            raise RuntimeError("edit_message 只能用在按鈕 / 選單 / Modal 的互動上")
        if view is not None:
            target.view = view
        self._i.cli.touched(target, "edit")

    async def defer(self, *, ephemeral=False, thinking=False, **kwargs):
        self._mark()
        self._i.deferred_ephemeral = ephemeral

    async def send_modal(self, modal):
        self._mark()
        self._i.cli.pending_modal = (modal, self._i.message)
        self._i.cli.print_modal(modal)


class FakeFollowup:
    def __init__(self, interaction):
        self._i = interaction

    async def send(self, content=None, *, view=None, ephemeral=False, wait=True, **kwargs):
        _reject_legacy({"content": content, **kwargs})
        msg = Message(self._i.cli, view, ephemeral or self._i.deferred_ephemeral, self._i.user.id)
        self._i.cli.touched(msg, "send")
        return msg


class FakeInteraction:
    def __init__(self, cli, user, *, message=None, data=None, namespace=None, command=None, component=False):
        import discord
        self.cli = cli
        self.user = user
        self.guild = cli.guild
        self.guild_id = cli.guild.id
        self.channel = FakeChannel()
        self.channel_id = CHANNEL_ID
        self.message = message           # 元件互動：被點的那則訊息
        self.original = message          # edit_original_response 的對象
        self.data = data or {}
        self.namespace = namespace or __import__("types").SimpleNamespace()
        self.command = command
        self.created_at = datetime.now(timezone.utc)
        self.deferred_ephemeral = False
        self.type = discord.InteractionType.component if component else discord.InteractionType.application_command
        self.response = FakeResponse(self)
        self.followup = FakeFollowup(self)
        self.client = cli.bot

    async def edit_original_response(self, *, view=None, **kwargs):
        _reject_legacy(kwargs)
        if self.original is None:   # 斜線指令 defer 後第一次編輯 = 建立回覆
            self.original = Message(self.cli, view, self.deferred_ephemeral, self.user.id)
            self.cli.touched(self.original, "send")
            return self.original
        if view is not None:
            self.original.view = view
        self.cli.touched(self.original, "edit")
        return self.original

    async def original_response(self):
        return self.original


# =========================================================
# 🖼️ 把 V2 畫面轉成文字
# =========================================================
def render_view(view, refs: dict) -> list[str]:
    """回傳文字行；refs 會填入 b1/s1… ➔ 元件 的對照"""
    from discord import ui
    lines = []

    def color_of(container):
        c = getattr(container, "accent_colour", None) or getattr(container, "accent_color", None)
        return f"#{c.value:06x}" if hasattr(c, "value") else "無"

    def text_lines(content: str, prefix: str):
        for line in content.split("\n"):
            lines.append(f"{prefix}{line}")

    def walk(item, prefix: str):
        if isinstance(item, ui.Container):
            lines.append(f"{prefix}┌─ Container  色條 {color_of(item)}")
            for child in item.children:
                walk(child, prefix + "│ ")
            lines.append(f"{prefix}└─")
        elif isinstance(item, ui.Section):
            for child in item.children:
                walk(child, prefix)
            acc = item.accessory
            if isinstance(acc, ui.Thumbnail):
                url = acc.media.url if hasattr(acc.media, "url") else str(acc.media)
                lines.append(f"{prefix}  🖼️ 縮圖：{url.rsplit('/', 1)[-1]}")
            elif isinstance(acc, ui.Button):
                walk_button(acc, prefix + "  ")
        elif isinstance(item, ui.TextDisplay):
            text_lines(item.content, prefix)
        elif isinstance(item, ui.Separator):
            lines.append(f"{prefix}────────────")
        elif isinstance(item, ui.ActionRow):
            parts = []
            for child in item.children:
                if isinstance(child, ui.Button):
                    parts.append(button_label(child))
                else:
                    walk(child, prefix)
            if parts:
                lines.append(f"{prefix}" + "  ".join(parts))
        elif isinstance(item, ui.Select):
            ref = f"s{sum(1 for k in refs if k.startswith('s')) + 1}"
            refs[ref] = item
            state = "（停用）" if item.disabled else ""
            span = f"選 {item.min_values}~{item.max_values} 個" if item.max_values > 1 else "單選"
            lines.append(f"{prefix}▼ [{ref}] {item.placeholder or '選單'}　{span}{state}")
            for opt in item.options:
                mark = " ✓" if opt.default else ""
                desc = f" — {opt.description}" if opt.description else ""
                emoji = f"{opt.emoji} " if opt.emoji else ""
                lines.append(f"{prefix}    · {opt.value} = {emoji}{opt.label}{desc}{mark}")
        elif isinstance(item, ui.Thumbnail):
            lines.append(f"{prefix}🖼️ 縮圖")
        else:
            lines.append(f"{prefix}[{type(item).__name__}]")

    def button_label(btn):
        ref = f"b{sum(1 for k in refs if k.startswith('b')) + 1}"
        refs[ref] = btn
        emoji = f"{btn.emoji} " if btn.emoji else ""
        state = "✖" if btn.disabled else ""
        return f"[{ref}{state}] {emoji}{btn.label or ''}"

    def walk_button(btn, prefix):
        lines.append(prefix + button_label(btn))

    if view is None:
        return ["(沒有畫面)"]
    for child in view.children:
        walk(child, "")
    count = sum(1 for _ in view.walk_children())
    lines.append(f"-- 元件數 {count}/40" + ("　⚠️ 超過上限！" if count > 40 else ""))
    return lines


# =========================================================
# 🤖 CLI 主體
# =========================================================
class BotCLI:
    def __init__(self, udm):
        import discord
        from discord.ext import commands
        from Utils.config import ADMIN_IDS

        self.udm = udm
        self.bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        self.messages: list[Message] = []
        self.last_touched: Message | None = None
        self.focus: Message | None = None
        self.refs: dict[int, dict] = {}       # 訊息編號 ➔ {b1: Button, s1: Select}
        self.pending_modal = None
        self.users: dict[int, FakeUser] = {}
        self.guild = FakeGuild(self.users)
        admin = min(ADMIN_IDS) if ADMIN_IDS else 100000000000000001
        self.me = self.get_user(admin, "管理員(me)" if ADMIN_IDS else "me")   # 「me」永遠指這個身分
        self.current = self.me
        self.errors = 0

    # ---------------- 使用者 ----------------
    def get_user(self, user_id: int, name: str | None = None) -> FakeUser:
        if user_id not in self.users:
            self.users[user_id] = FakeUser(user_id, name or f"玩家{str(user_id)[-4:]}")
        return self.users[user_id]

    def resolve_user(self, raw: str) -> FakeUser:
        raw = raw.strip()
        if raw.lower() == "me":
            return self.me
        if raw.startswith("<@") and raw.endswith(">"):
            raw = raw[2:-1].lstrip("!")
        if raw.isdigit():
            return self.get_user(int(raw))
        name = raw.lstrip("@")
        for user in self.users.values():
            if user.display_name == name:
                return user
        # 新名字 ➔ 用名字產生固定的假 ID (每次執行都一樣，沙盒裡的資料才接得上)
        fake_id = 200000000000000000 + zlib.crc32(name.encode("utf-8"))
        return self.get_user(fake_id, name)

    async def load(self):
        async def fake_sync(*_args, **_kwargs):
            print("    （botcli：略過 tree.sync，不會真的同步到 Discord）")
            return list(self.bot.tree.get_commands())
        self.bot.tree.sync = fake_sync

        await self.udm.init_db()
        from Database import Item_DB_Manager as idm
        if hasattr(idm, "init_item_db"):
            await idm.init_item_db()
        # 沙盒裡已有的玩家都當成伺服器成員 (排行榜會用到)
        async with self.udm.connect() as db:
            async with db.execute("SELECT user_id FROM users") as cursor:
                for row in await cursor.fetchall():
                    self.get_user(row["user_id"])
        loaded = []
        for folder in sorted(os.listdir("Cogs")):
            path = os.path.join("Cogs", folder)
            if not (os.path.isdir(path) and folder.startswith("load-")):
                continue
            for filename in sorted(os.listdir(path)):
                if filename.endswith(".py") and not filename.startswith("__"):
                    ext = f"Cogs.{folder}.{filename[:-3]}"
                    try:
                        await self.bot.load_extension(ext)
                        loaded.append(ext)
                    except Exception as e:
                        self.errors += 1
                        print(f"❌ 載入失敗 {ext}: {e}")
        print(f"🤖 botcli 已載入 {len(loaded)} 個模組 · 沙盒資料庫 {os.path.relpath(SANDBOX_DIR, ROOT)} · 目前身分：{self.current.display_name} ({self.current.id})")

    # ---------------- 訊息顯示 ----------------
    def touched(self, msg: Message, action: str):
        self.last_touched = msg
        self.focus = msg
        self.print_message(msg, action)

    def print_message(self, msg: Message, action: str = "show"):
        refs = {}
        lines = render_view(msg.view, refs)
        self.refs[msg.id] = refs
        tag = {"send": "新訊息", "edit": "訊息已更新", "show": "訊息"}.get(action, action)
        vis = "　🔒 僅自己可見" if msg.ephemeral else ""
        print(f"\n━━━ [{tag} #{msg.id}]{vis} ━━━")
        for line in lines:
            print("  " + line)

    def print_modal(self, modal):
        from discord import ui
        print(f"\n━━━ [Modal] {modal.title} ━━━")
        for item in modal.children:
            if isinstance(item, ui.TextInput):
                default = f"（預設：{item.default}）" if item.default else ""
                print(f"  ✏️ {item.label}{default}")
        print("  -- 用 modal 標籤:值 ... 送出")

    # ---------------- 指令 ----------------
    def all_commands(self):
        from discord import app_commands
        result = {}
        for cmd in self.bot.tree.walk_commands():
            if isinstance(cmd, app_commands.Command):
                result[cmd.qualified_name] = cmd
        return result

    def find_command(self, tokens: list[str]):
        """/card gacha a:b ➔ (Command, 剩下的 token)"""
        cmds = self.all_commands()
        words = [tokens[0].lstrip("/")] + tokens[1:]
        for n in range(min(3, len(words)), 0, -1):
            name = " ".join(words[:n])
            if name in cmds:
                return cmds[name], words[n:]
        raise ValueError(f"找不到指令 /{' '.join(words[:2])}（輸入 commands 查看全部）")

    def convert(self, param, raw: str):
        import discord
        from discord import app_commands
        t = param.type
        if param.choices:
            for choice in param.choices:
                if str(choice.value) == raw or choice.name == raw:
                    return choice
            raise ValueError(f"參數 {param.name} 只能是：{', '.join(f'{c.value}({c.name})' for c in param.choices)}")
        if t == discord.AppCommandOptionType.integer:
            value = int(raw)
        elif t == discord.AppCommandOptionType.number:
            value = float(raw)
        elif t == discord.AppCommandOptionType.boolean:
            value = raw.lower() in ("1", "true", "yes", "y", "是")
        elif t in (discord.AppCommandOptionType.user, discord.AppCommandOptionType.mentionable):
            return self.resolve_user(raw)
        elif t == discord.AppCommandOptionType.attachment:
            if not os.path.exists(raw):
                raise ValueError(f"找不到檔案 {raw}")
            return FakeAttachment(raw)
        else:
            value = raw
        if param.min_value is not None and value < param.min_value:
            raise ValueError(f"參數 {param.name} 不能小於 {param.min_value}（Discord 會擋下）")
        if param.max_value is not None and value > param.max_value:
            raise ValueError(f"參數 {param.name} 不能大於 {param.max_value}（Discord 會擋下）")
        return value

    def parse_args(self, cmd, tokens: list[str], allow_missing: bool = False) -> tuple[dict, dict]:
        """回傳 (轉換後的參數, 原始字串)；原始字串給 autocomplete 的 namespace 用"""
        params = dict(cmd._params)   # CommandParameter：autocomplete 是可呼叫的函式
        raw = {}
        for tok in tokens:
            if ":" not in tok:
                raise ValueError(f"參數格式應為 名稱:值，收到 `{tok}`")
            key, value = tok.split(":", 1)
            if key not in params and key != "current":
                raise ValueError(f"/{cmd.qualified_name} 沒有參數 {key}（可用：{', '.join(params)}）")
            raw[key] = value
        kwargs = {}
        for name, param in params.items():
            if name in raw:
                kwargs[name] = self.convert(param, raw[name])
            elif param.required and not allow_missing:
                raise ValueError(f"缺少必填參數 {name}")
        return kwargs, raw

    async def run_command(self, tokens: list[str]):
        cmd, rest = self.find_command(tokens)
        kwargs, _ = self.parse_args(cmd, rest)
        inter = FakeInteraction(self, self.current, command=cmd)
        await self._invoke(cmd, inter, kwargs)

    async def _invoke(self, cmd, inter, kwargs):
        from discord.utils import maybe_coroutine
        cog = cmd.binding
        if cog is not None and hasattr(cog, "interaction_check"):
            ok = await maybe_coroutine(cog.interaction_check, inter)
            if ok is False:
                print("⛔ Cog 的 interaction_check 擋下了這個指令")
                return
        await (cmd.callback(cog, inter, **kwargs) if cog is not None else cmd.callback(inter, **kwargs))
        if not inter.response.is_done() and inter.original is None:
            self.errors += 1
            print("⚠️ 指令沒有回應任何東西 (Discord 上會顯示「應用程式沒有回應」)")

    async def autocomplete(self, tokens: list[str]):
        cmd, rest = self.find_command(tokens)
        if not rest:
            raise ValueError("用法：? /指令 參數名稱 [已填參數:值 ...] [current:文字]")
        target, filled = rest[0], rest[1:]
        param = cmd._params.get(target)
        if param is None:
            raise ValueError(f"/{cmd.qualified_name} 沒有參數 {target}")
        if param.autocomplete is None:
            if param.choices:
                print(f"📋 {target} 是固定選項：")
                for c in param.choices:
                    print(f"    · {c.value} = {c.name}")
                return
            raise ValueError(f"參數 {target} 沒有 autocomplete")
        kwargs, raw = self.parse_args(cmd, filled, allow_missing=True)
        ns = __import__("types").SimpleNamespace(**kwargs)
        inter = FakeInteraction(self, self.current, namespace=ns, command=cmd)
        choices = await param.autocomplete(cmd.binding, inter, raw.get("current", ""))
        print(f"\n📋 /{cmd.qualified_name} {target} 的 autocomplete（{len(choices)} 個，上限 25）：")
        for c in choices:
            warn = "　⚠️ 超過 100 字" if len(c.name) > 100 else ""
            print(f"    · {c.value} = {c.name}{warn}")
        if len(choices) > 25:
            self.errors += 1
            print("    ⚠️ 超過 25 個選項，Discord 會拒絕！")

    # ---------------- 元件 ----------------
    def target_message(self) -> Message:
        msg = self.focus or self.last_touched
        if msg is None:
            raise ValueError("還沒有任何訊息")
        if msg.id not in self.refs:
            self.print_message(msg)
        return msg

    def find_component(self, msg: Message, key: str, kind: str):
        refs = self.refs.get(msg.id, {})
        if key in refs:
            return refs[key]
        prefix = "b" if kind == "button" else "s"
        matches = [
            item for ref, item in refs.items() if ref.startswith(prefix)
            and key in ((item.label or "") if kind == "button" else (item.placeholder or ""))
        ]
        if not matches:
            raise ValueError(f"訊息 #{msg.id} 上找不到 {'按鈕' if kind == 'button' else '選單'}「{key}」")
        if len(matches) > 1:
            raise ValueError(f"「{key}」對應到多個元件，請改用編號 ({prefix}1、{prefix}2…)")
        return matches[0]

    async def _dispatch(self, msg: Message, item, data: dict):
        if item.disabled:
            raise ValueError("這個元件是停用狀態，Discord 上點不了")
        inter = FakeInteraction(self, self.current, message=msg, data=data, component=True)
        view = msg.view
        if hasattr(view, "interaction_check") and await view.interaction_check(inter) is False:
            return
        if not getattr(item, "callback", None):
            raise ValueError("這個元件沒有任何作用 (沒有 callback)")
        await item.callback(inter)
        if not inter.response.is_done():
            self.errors += 1
            print("⚠️ 元件回呼沒有回應 (Discord 上會顯示「此互動失敗」)")

    async def click(self, key: str):
        from discord import ui
        msg = self.target_message()
        btn = self.find_component(msg, key, "button")
        if not isinstance(btn, ui.Button):
            raise ValueError(f"{key} 不是按鈕")
        await self._dispatch(msg, btn, {"custom_id": btn.custom_id, "component_type": 2})

    async def select(self, key: str, values: list[str]):
        msg = self.target_message()
        sel = self.find_component(msg, key, "select")
        chosen = []
        for raw in values:
            opt = next((o for o in sel.options if o.value == raw), None) \
                or next((o for o in sel.options if raw in o.label), None)
            if opt is None:
                raise ValueError(f"選單沒有「{raw}」這個選項")
            chosen.append(opt.value)
        if not (sel.min_values <= len(chosen) <= sel.max_values):
            raise ValueError(f"這個選單要選 {sel.min_values}~{sel.max_values} 個")
        sel._values = chosen
        await self._dispatch(msg, sel, {"custom_id": sel.custom_id, "component_type": 3, "values": chosen})

    async def submit_modal(self, tokens: list[str]):
        from discord import ui
        if not self.pending_modal:
            raise ValueError("目前沒有開著的 Modal")
        modal, origin = self.pending_modal
        inputs = [i for i in modal.children if isinstance(i, ui.TextInput)]
        for item in inputs:
            item._value = item.default
        for tok in tokens:
            if ":" not in tok:
                raise ValueError("用法：modal 標籤:值 ...")
            key, value = tok.split(":", 1)
            item = next((i for i in inputs if key in str(i.label)), None)
            if item is None:
                raise ValueError(f"Modal 沒有「{key}」欄位")
            item._value = value
        for item in inputs:
            if item.required and not item._value:
                raise ValueError(f"必填欄位「{item.label}」沒有值")
        self.pending_modal = None
        inter = FakeInteraction(self, self.current, message=origin, component=True)
        await modal.on_submit(inter)

    # ---------------- 其他 ----------------
    async def list_users(self):
        async with self.udm.connect() as db:
            async with db.execute(
                """
                SELECT u.user_id, u.money, u.level, u.stamina,
                       (SELECT COUNT(*) FROM gacha_cards c WHERE c.user_id = u.user_id) AS cards
                FROM users u ORDER BY u.user_id
                """
            ) as cursor:
                rows = await cursor.fetchall()
        print(f"\n👥 沙盒玩家 {len(rows)} 位：")
        for r in rows:
            name = self.get_user(r["user_id"]).display_name
            mark = "　⬅️ 目前身分" if r["user_id"] == self.current.id else ""
            print(f"    · {r['user_id']} {name}　賽錢 {r['money']:,} · 等級 {r['level']} · 體力 {r['stamina']} · 卡牌 {r['cards']}{mark}")

    async def sql(self, query: str):
        if not query.strip().lower().startswith(("select", "pragma", "with")):
            raise ValueError("sql 只允許唯讀查詢 (SELECT / WITH / PRAGMA)")
        async with self.udm.connect() as db:
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                cols = [d[0] for d in cursor.description] if cursor.description else []
        print("    " + " | ".join(cols))
        for row in rows[:50]:
            print("    " + " | ".join(str(row[c]) for c in cols))
        if len(rows) > 50:
            print(f"    … 共 {len(rows)} 列，只顯示前 50 列")

    def list_commands(self):
        print("\n📜 斜線指令：")
        for name, cmd in sorted(self.all_commands().items()):
            params = " ".join(
                (f"{p.name}:" if p.required else f"[{p.name}:]") + ("ac" if p.autocomplete else "")
                for p in cmd._params.values()
            )
            print(f"    /{name} {params}")
        print("    （ac = 有 autocomplete，可用 ? /指令 參數 查看）")

    def _root_command_names(self) -> set:
        return {name.split(" ")[0] for name in self.all_commands()}

    @staticmethod
    def _fix_msys_path(token: str) -> str:
        """Git Bash 會把 "/card" 改寫成 "C:/Program Files/Git/card"，這裡還原回來"""
        normalized = token.replace("\\", "/")
        lowered = normalized.lower()
        marker = "/git/"
        if ":" in lowered[:3] and marker in lowered[:40]:
            return "/" + normalized[lowered.index(marker) + len(marker):]
        return token

    # ---------------- 步驟執行 ----------------
    async def step(self, line: str):
        line = line.strip()
        if not line or line.startswith("#"):
            return
        line = self._fix_msys_path(line)
        print(f"\n▶ {line}")
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError as e:
            print(f"❌ 無法解析：{e}")
            self.errors += 1
            return
        head = tokens[0]
        if not head.startswith("/") and head.split(" ")[0] in self._root_command_names():
            tokens[0] = head = "/" + head   # 允許省略開頭的 /，例如 card gacha …
        try:
            if head.startswith("/"):
                await self.run_command(tokens)
            elif head == "?":
                await self.autocomplete(tokens[1:])
            elif head == "click":
                await self.click(" ".join(tokens[1:]))
            elif head == "select":
                await self.select(tokens[1], tokens[2:])
            elif head == "modal":
                await self.submit_modal(tokens[1:])
            elif head == "as":
                self.current = self.resolve_user(tokens[1])
                print(f"👤 目前身分：{self.current.display_name} ({self.current.id})")
            elif head == "msg":
                self.focus = self.messages[int(tokens[1].lstrip("#")) - 1]
                print(f"🎯 之後的操作對準訊息 #{self.focus.id}")
            elif head == "show":
                msg = self.messages[int(tokens[1].lstrip("#")) - 1] if len(tokens) > 1 else self.target_message()
                self.print_message(msg)
            elif head == "users":
                await self.list_users()
            elif head == "sql":
                await self.sql(line.split(None, 1)[1])
            elif head == "commands":
                self.list_commands()
            elif head in ("help", "h"):
                print(__doc__)
            else:
                raise ValueError(f"看不懂的步驟「{head}」（輸入 help 看說明）")
        except (ValueError, IndexError) as e:
            self.errors += 1
            print(f"❌ {e}")
        except Exception:
            self.errors += 1
            print("💥 機器人程式拋出例外（Discord 上會變成指令錯誤通報）：")
            traceback.print_exc(file=sys.stdout)
        # 讓 view 裡排程的小任務有機會跑完
        await asyncio.sleep(0)


async def amain(args):
    global SANDBOX_DIR
    if args.sandbox:
        SANDBOX_DIR = os.path.abspath(args.sandbox)
    prepare_sandbox(args.reset, args.fresh)
    udm, _ = point_databases_to_sandbox()
    cli = BotCLI(udm)
    await cli.load()
    if args.as_user:
        cli.current = cli.resolve_user(args.as_user)

    steps = list(args.steps)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            steps += f.read().splitlines()

    if steps:
        for line in steps:
            await cli.step(line)
    else:
        print("輸入 help 查看語法，exit 離開")
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, lambda: input("botcli> "))
            if line.strip() in ("exit", "quit", "q"):
                break
            await cli.step(line)

    print(f"\n🏁 結束 · 錯誤 {cli.errors} 個")
    return 1 if cli.errors else 0


def main():
    parser = argparse.ArgumentParser(description="不連 Discord 的機器人指令測試工具")
    parser.add_argument("steps", nargs="*", help="依序執行的步驟 (每個步驟用引號包起來)")
    parser.add_argument("--file", "-f", help="從檔案讀取步驟 (一行一個，# 開頭為註解)")
    parser.add_argument("--as", dest="as_user", help="一開始的身分 (使用者 ID 或 @名稱)")
    parser.add_argument("--reset", action="store_true", help="重新從 Database/ 複製沙盒資料庫")
    parser.add_argument("--fresh", action="store_true", help="沙盒 Users.db 從空白開始")
    parser.add_argument("--sandbox", help="沙盒資料夾 (預設 .botcli/；測試用暫存資料夾)")
    args = parser.parse_args()
    sys.exit(asyncio.run(amain(args)))


if __name__ == "__main__":
    main()

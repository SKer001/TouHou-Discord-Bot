"""🙈 未公開卡池開關 (Utils/config.py 的 SHOW_UNRELEASED + Utils/gacha_pools.py 的 "released": False)

開關在 import 時就決定，所以用子行程各跑一次：
  - 沒開 (SHOW_UNRELEASED=0，正式機器人的樣子)：未公開卡池與它的角色整個當作不存在，而且所有 Cog 都載得起來
  - 開了 (SHOW_UNRELEASED=1，開發的樣子)：全部看得到
之後卡池全部公開了 (沒有 "released": False)，兩輪檢查的內容就會一樣，不用改這個檔案。
"""
import asyncio, glob, json, os, subprocess, sys, tempfile, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 專案根目錄
MODE = os.environ.get("_UNRELEASED_TEST_MODE")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL:", name)


def parent():
    """兩種環境各開一個子行程；明確傳 0 / 1，.env 裡寫了什麼都不影響 (load_dotenv 不會蓋掉已經有的環境變數)"""
    global ok
    for mode, flag in (("off", "0"), ("on", "1")):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "SHOW_UNRELEASED": flag, "_UNRELEASED_TEST_MODE": mode}
        proc = subprocess.run([sys.executable, os.path.abspath(__file__)], cwd=ROOT, env=env,
                              capture_output=True, text=True, encoding="utf-8")
        out = proc.stdout + proc.stderr
        done = f"child {mode} done" in out
        check(f"{mode}: child finished", proc.returncode == 0 and done)
        if proc.returncode != 0 or not done:
            print(out[-3000:])
        for line in out.splitlines():
            if line.startswith("FAIL:"):
                check(f"{mode}: {line[5:].strip()}", False)
            elif line.startswith("CHILD_OK "):
                ok += int(line.split()[1])
            elif line.startswith("["):
                print(line)
    # 只認 1 / true / yes / on；空字串、0、false 都是沒開
    sys.path.insert(0, ROOT)
    from Utils import config
    check("flag parse", all(config._parse_flag(v) for v in ("1", "true", "YES", " on "))
          and not any(config._parse_flag(v) for v in (None, "", "0", "false", "off", "no")))


def _ids(folders) -> set:
    return {os.path.splitext(os.path.basename(p))[0] for f in folders
            for p in glob.glob(os.path.join(ROOT, "Characters", f, "*.json"))}


async def child():
    sys.path.insert(0, ROOT); os.chdir(ROOT)
    import importlib
    import discord
    from discord.ext import commands
    from Utils import config, gacha_pools as gp, character_data as cd
    from Database import User_DB_Manager as udm, title_data as td
    from Database.ura import data as ura_data
    udm.DB_PATH = os.path.join(tempfile.mkdtemp(), "Users.db")
    await udm.init_db()

    show = MODE == "on"
    check("flag", config.SHOW_UNRELEASED is show)
    unreleased = {k for k, p in gp.ALL_GACHA_POOLS.items() if not p.get("released", True)}
    hidden_pools = set() if show else unreleased
    public = [k for k in gp.ALL_GACHA_POOLS if k not in hidden_pools]
    hidden_dirs = {f for k in hidden_pools for f in gp.ALL_GACHA_POOLS[k]["folders"]}
    hidden_ids = _ids(hidden_dirs)
    all_ids = _ids(["*"])
    print(f"[{MODE}] 未公開卡池 {sorted(unreleased)}；這一輪藏起來 {sorted(hidden_pools)} ({len(hidden_ids)} 位角色)")
    if unreleased:   # 有未公開的卡池時 (2026-11-24：th07 妖妖夢)：沒開一定要真的藏到角色，不然下面都是空檢查
        check("off hides characters / on hides nothing", bool(hidden_ids) is (not show))

    # 🎰 卡池清單
    check("GACHA_POOLS", list(gp.GACHA_POOLS) == public and all(gp.GACHA_POOLS[k] is gp.ALL_GACHA_POOLS[k] for k in public))
    check("hidden_folders", gp.hidden_folders() == frozenset(hidden_dirs))

    # 📚 角色檔
    cats = cd.load_categories()
    chars = cd.load_characters()
    check("load_categories", not (set(cats) & hidden_dirs) and all(f in cats for p in public for f in gp.ALL_GACHA_POOLS[p]["folders"]))
    check("load_characters", set(chars) == all_ids - hidden_ids)
    pool = gp.load_gacha_pool()
    check("load_gacha_pool", not (set(pool) & hidden_ids) and {c["pool"] for c in pool.values()} <= set(public))
    check("pool_members", list(gp.pool_members()) == public and all(gp.pool_members()[k] for k in public))
    check("card names", not (set(cd._card_info_map()) & hidden_ids))

    # 🏅 稱號：卡池收集、推角、歐氣
    for k in hidden_pools:
        check(f"no titles for {k}", not any(t.startswith((f"pool_{k}_", f"luck_{k}_")) for t in td.TITLES)
              and f"oshi_{k}" not in td.TITLE_GROUPS and f"luck_{k}" not in td.TITLE_GROUPS
              and not any(t["stat"].endswith(f":{k}") or f":{k}:" in t["stat"] for t in td.TITLES.values()))
    for k in public:
        check(f"titles for {k}", {f"pool_{k}_chars", f"pool_{k}_cards", f"luck_{k}_ssr", f"luck_{k}_ur", f"luck_{k}_lr"} <= set(td.TITLES)
              and f"oshi_{k}" in td.TITLE_GROUPS)
    check("oshi titles", {t[5:] for t in td.TITLES if t.startswith("oshi_")} == set(pool))
    check("every title grouped", all(td.title_group(t) for t in td.TITLES) and all(td.group_titles(list(td.TITLES)).values()))
    check("condition text", all(td.condition_text(t) for t in td.TITLES))
    # 「幻想鄉緣起」只看公開的卡池
    owned = {(cid, r) for cid, c in pool.items() for r in c["rarities"]}
    stats = gp.collection_stats(owned)
    check("all_cards = public pools only", stats["all_cards"] == 1
          and set(stats) == {"all_cards"} | {f"{a}:{k}" for k in public for a in ("pool_chars", "pool_cards")})
    check("pool_all unlocked", "pool_all" in td.TITLES and "pool_all" in td.unlocked_titles(stats))
    oshi = gp.oshi_stats({})
    check("oshi_stats", {s.split(":")[1] for s in oshi} <= set(public) and not ({s.split(":")[2] for s in oshi} & hidden_ids))

    # 🌀 裏世界可選角色
    uc = ura_data.characters()
    check("ura characters", not (set(uc) & hidden_ids) and set(uc) == {c for c, v in chars.items() if v.get("ura_class")})
    check("ura spells for shown characters", all(c in ura_data.spells() for c in uc))

    # 🤖 所有 Cog 都載得起來 (跟 Main.py 一樣掃 Cogs/load-*/ 第一層)
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    loaded, total = [], 0
    for folder in sorted(glob.glob(os.path.join(ROOT, "Cogs", "load-*"))):
        for path in sorted(glob.glob(os.path.join(folder, "*.py"))):
            name = f"Cogs.{os.path.basename(folder)}.{os.path.basename(path)[:-3]}"
            total += 1
            try:
                await bot.load_extension(name); loaded.append(name)
            except Exception as e:   # noqa: BLE001
                check(f"load {name}: {type(e).__name__}: {e}", False)
    check(f"cogs loaded {len(loaded)} / {total}", total >= 10 and len(loaded) == total)

    def texts(v): return "\n".join(i.content for i in v.walk_children() if isinstance(i, discord.ui.TextDisplay))
    def options(v): return [o for i in v.walk_children() if isinstance(i, discord.ui.Select) for o in i.options]

    class Resp:
        def __init__(s, it): s.it = it; s.done = False
        def is_done(s): return s.done
        async def defer(s, **kw): s.done = True
        async def send_message(s, content=None, **kw): s.done = True; s.it.view = kw.get("view")
    class Followup:
        def __init__(s, it): s.it = it
        async def send(s, content=None, **kw): s.it.view = kw.get("view")
    class Interaction:
        def __init__(s):
            s.user = types.SimpleNamespace(id=1, display_name="t")
            s.response = Resp(s); s.followup = Followup(s); s.view = None; s.data = {}
            s.type = discord.InteractionType.application_command
        async def original_response(s): return None
        async def edit_original_response(s, **kw): s.view = kw.get("view")

    hidden_cat_names = {cd.CATEGORY_INFO[f][0] for f in hidden_dirs if f in cd.CATEGORY_INFO}
    hidden_pool_names = {gp.ALL_GACHA_POOLS[k]["name"] for k in hidden_pools}

    # 📖 圖鑑首頁 + 分類選單
    cog = bot.get_cog("CharacterProfileCog")
    cmd = next(c for c in cog.walk_app_commands() if c.name == "character")
    it = Interaction(); await cmd.callback(cog, it)
    labels = " ".join(f"{o.label} {o.value}" for o in options(it.view))
    check("/character home", f"{len(chars)} 位角色" in texts(it.view) and not any(n in texts(it.view) for n in hidden_cat_names))
    check("/character category select", bool(labels) and not any(n in labels for n in hidden_cat_names)
          and not any(f in labels.split() for f in hidden_dirs))

    # 🖼️ 名片選單 (玩家 / 管理員)
    user = types.SimpleNamespace(id=1, display_name="t")
    v = sys.modules["Cogs.load-general.profile"].NamecardPickerView(user, None, [])
    check("namecard picker groups", [k for k in v.groups if k != "other"] == public and not v.groups.get("other")
          and not ({c for g in v.groups.values() for c in g} & hidden_ids))
    v = sys.modules["Cogs.load-general.Admin-user"].AdminNamecardView(bot, 1, user)
    check("admin namecard picker groups", list(v.groups) == public and not ({c for g in v.groups.values() for c in g} & hidden_ids))

    # 🎰 抽卡：模組的卡池、/card history 的選單、指令的卡池選項
    gacha = sys.modules["Cogs.load-gacha.gacha"]
    check("gacha module pool", gacha.GACHA_POOLS is gp.GACHA_POOLS and not (set(gacha.GACHA_POOL) & hidden_ids))
    gcog = next(c for c in bot.cogs.values() if type(c).__module__ == "Cogs.load-gacha.gacha")
    cmds = {c.name: c for c in gcog.walk_app_commands()}
    it = Interaction(); await cmds["history"].callback(gcog, it)
    check("/card history", "祈願紀錄" in texts(it.view) and not any(n in texts(it.view) for n in hidden_pool_names)
          and not ({o.value for o in options(it.view)} & hidden_pools))
    choices = [c.value for c_ in bot.cogs.values() for cmd_ in c_.walk_app_commands()
               for p in getattr(cmd_, "parameters", []) for c in p.choices]
    check("command choices", bool(choices) and not (set(choices) & hidden_pools))

    print(f"CHILD_OK {ok}")
    print(f"child {MODE} done")


if MODE:
    asyncio.run(child())
    sys.exit(1 if fail else 0)
parent()
print(f"passed {ok}, failed {fail}")

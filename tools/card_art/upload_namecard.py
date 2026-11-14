"""📥 角色名片：原圖上傳到私人頻道 + 產生 Discord 顯示用的壓縮版 (一次做完)
python tools/card_art/upload_namecard.py <原圖路徑> <角色id>

1. 顯示用：呼叫 build_namecards.py ➔ images/Namecards/<角色id>.jpg + images/Namecards.json (要 push 才看得到)
2. 原圖 (repo 是公開的，原圖不進 repo)：上傳到 .env 的 NAMECARD_CHANNEL_ID (只有機器人看得到的私人頻道)
   - <角色id>_full.jpg：原尺寸、quality 95 (玩家「📥 下載名片原圖」拿到的)
   - <角色id>.png：原檔 (超過上傳上限就改無損 WebP，還是太大就不傳)，管理員用 /admin-user namecard「📥 原檔」私訊自己
   訊息 id 記到 images/NamecardOriginals.json (要 commit，機器人靠它找原圖)
   同一位角色重新上傳 ➔ 新訊息、JSON 換成新的 id (舊訊息留著，要的話自己去頻道刪)
只用 Discord REST (機器人 Token)，不連 Gateway，機器人執行中也可以跑。
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv   # noqa: E402
import build_namecards   # noqa: E402

ORIGINALS_FILE = os.path.join(PROJECT_ROOT, "images", "NamecardOriginals.json")
UPLOAD_LIMIT = int(9.5 * 1024 * 1024)   # Discord 一般伺服器上傳上限 10MB，留一點餘裕
FULL_JPEG_QUALITY = 95
API = "https://discord.com/api/v10"


def encode_files(img: Image.Image, cid: str) -> list[tuple[str, bytes, str]]:
    """原圖 ➔ [(檔名, 內容, MIME)]：高畫質 JPG + 原檔 (PNG / 無損 WebP，太大就略過)"""
    rgb = img.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=FULL_JPEG_QUALITY, optimize=True, progressive=True)
    files = [(f"{cid}_full.jpg", buf.getvalue(), "image/jpeg")]
    if len(files[0][1]) > UPLOAD_LIMIT:
        raise SystemExit(f"❌ 高畫質 JPG 就有 {len(files[0][1]) / 1048576:.1f}MB，超過上傳上限")
    for fmt, ext, mime, kwargs in (("PNG", "png", "image/png", {"optimize": True}),
                                   ("WEBP", "webp", "image/webp", {"lossless": True, "method": 6})):
        buf = io.BytesIO()
        img.save(buf, fmt, **kwargs)
        size = len(buf.getvalue())
        if size <= UPLOAD_LIMIT:
            files.append((f"{cid}.{ext}", buf.getvalue(), mime))
            break
        print(f"⚠️ {fmt} 有 {size / 1048576:.1f}MB，超過上傳上限，改試下一種")
    else:
        print("⚠️ 原檔太大傳不上去，只傳高畫質 JPG (管理員「📥 原檔」會拿到 JPG)")
    return files


def post_files(token: str, channel_id: int, text: str, files: list[tuple[str, bytes, str]]) -> int:
    """multipart 上傳附件，回傳訊息 id"""
    boundary = uuid.uuid4().hex
    payload = {"content": text, "attachments": [{"id": i, "filename": name} for i, (name, _, _) in enumerate(files)]}
    body = io.BytesIO()
    def part(headers: str, data: bytes):
        body.write(f"--{boundary}\r\n{headers}\r\n\r\n".encode())
        body.write(data)
        body.write(b"\r\n")
    part('Content-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json',
         json.dumps(payload, ensure_ascii=False).encode())
    for i, (name, data, mime) in enumerate(files):
        part(f'Content-Disposition: form-data; name="files[{i}]"; filename="{name}"\r\nContent-Type: {mime}', data)
    body.write(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"{API}/channels/{channel_id}/messages", data=body.getvalue(), method="POST",
        headers={"Authorization": f"Bot {token}", "Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "DiscordBot (TouHouBot namecard uploader, 1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return int(json.load(resp)["id"])
    except urllib.error.HTTPError as e:
        raise SystemExit(f"❌ 上傳失敗 HTTP {e.code}：{e.read().decode(errors='replace')[:300]}")


def save_record(cid: str, message_id: int, files: list[tuple[str, bytes, str]]):
    data = {}
    if os.path.exists(ORIGINALS_FILE):
        with open(ORIGINALS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    data[cid] = {"message_id": message_id, "jpg": files[0][0], "full": files[1][0] if len(files) > 1 else None}
    with open(ORIGINALS_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(sorted(data.items())), f, ensure_ascii=False, indent=4)
        f.write("\n")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    src, cid = argv
    if not os.path.isfile(src):
        print(f"❌ 找不到原圖：{src}")
        return 1
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    token = os.getenv("DISCORD_TOKEN")
    channel = (os.getenv("NAMECARD_CHANNEL_ID") or "").strip()
    if not token or not channel.isdigit():
        print("❌ .env 要有 DISCORD_TOKEN 和 NAMECARD_CHANNEL_ID")
        return 1

    # 1. 顯示用壓縮版
    out = build_namecards.build_namecard(src, cid)
    url = build_namecards.update_json(cid, out)
    print(f"✅ 顯示用：{out}\n   {url}")

    # 2. 原圖上傳
    img = Image.open(src)
    img.load()
    files = encode_files(img, cid)
    sizes = "、".join(f"{n} {len(d) / 1048576:.1f}MB" for n, d, _ in files)
    message_id = post_files(token, int(channel), f"🖼️ 名片原圖：`{cid}` ({img.width}×{img.height})", files)
    save_record(cid, message_id, files)
    print(f"✅ 原圖已上傳 (訊息 {message_id})：{sizes}\n   記在 {ORIGINALS_FILE}")
    print("➡️ 記得 commit + push：images/Namecards/、images/Namecards.json、images/NamecardOriginals.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

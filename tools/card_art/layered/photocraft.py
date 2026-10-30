"""直接跟 photocraft-cli mcp (stdio JSON-RPC) 對話的小工具
對話開始後才加的 MCP 伺服器不會載入成工具，用這個一樣能操作 PhotoCraft：
    pc = PC(); pc.call("doc_open", path="TH05/shinki/LR/10b_char_lit.png"); pc.call("command_run", id="...", params={...})
設定讀專案根目錄的 .mcp.json (只能讀 images/Original、只能寫 Documents/photocraft_out)"""
import json
import os
import subprocess

MCP_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".mcp.json")
CFG = json.load(open(MCP_JSON, encoding="utf-8"))["mcpServers"]["photocraft"]


class PC:
    def __init__(self):
        self.p = subprocess.Popen([CFG["command"]] + CFG["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        self.n = 0
        self._req("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "claude", "version": "0"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, m):
        self.p.stdin.write(json.dumps(m) + "\n")
        self.p.stdin.flush()

    def _req(self, method, params):
        self.n += 1
        self._send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        while True:
            r = json.loads(self.p.stdout.readline())
            if r.get("id") == self.n:
                return r

    def tools(self):
        return self._req("tools/list", {})["result"]["tools"]

    def call(self, name, **args):
        r = self._req("tools/call", {"name": name, "arguments": args})
        if "error" in r:
            raise RuntimeError(r["error"])
        res = r["result"]
        texts = [c.get("text") for c in res.get("content", []) if c.get("type") == "text"]
        if res.get("isError"):
            raise RuntimeError("\n".join(t for t in texts if t))
        return res, "\n".join(t for t in texts if t)

    def close(self):
        self.p.stdin.close()
        self.p.terminate()

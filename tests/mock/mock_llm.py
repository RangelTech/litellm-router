"""Mock OpenAI-compativel (stdlib). Responde com o id do mock e a chave recebida; /stats conta chamadas."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MOCK_ID = os.environ.get("MOCK_ID", "mock")
STATS = {"total": 0, "by_key": {}, "by_model": {}}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/stats":
            return self._send({"mock": MOCK_ID, **STATS})
        self._send({"object": "list", "data": [{"id": "m1", "object": "model"}]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/reset":
            STATS.update(total=0, by_key={}, by_model={})
            return self._send({"ok": True})
        a = self.headers.get("Authorization", "")
        key = a[7:] if a.startswith("Bearer ") else ""
        STATS["total"] += 1
        STATS["by_key"][key] = STATS["by_key"].get(key, 0) + 1
        m = body.get("model", "")
        STATS["by_model"][m] = STATS["by_model"].get(m, 0) + 1
        text = f"mock={MOCK_ID} key={key}"
        self._send({"id": "c1", "object": "chat.completion", "created": 1, "model": m,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


ThreadingHTTPServer(("0.0.0.0", 9000), H).serve_forever()

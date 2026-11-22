"""The Morph Timeline editor on a stand-in ComfyUI, to work on the editor without restarting ComfyUI.

    python comfy_pack/tools/editor_harness.py [port]      (default 47366; open http://127.0.0.1:47366/)

Serves the real ``web/morph_timeline.js`` with a stub ``/scripts/app.js`` (an ``app`` that records the extension and
answers ``queuePrompt`` by running the Timeline node here), the pack's own ``/xenoform_nodes/still`` and ``/song``
routes, and a page with one Timeline node on the bundled demo song (Dense, Auto: nine shots). ``POST /run`` takes the
hidden widget's value and returns what the node would send the editor. Standard library and the pack only.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK.parent))

from comfy_pack import routes  # noqa: E402
from comfy_pack.nodes import NODE_CLASS_MAPPINGS as NODES  # noqa: E402

STUB_APP = """
export const app = {
  extensions: [],
  registerExtension(ext) { this.extensions.push(ext); },
  graph: { setDirtyCanvas() {}, change() { window.__changed = (window.__changed || 0) + 1; } },
  async queuePrompt(number, batch, ids) {
    window.__queued = ids;
    const node = window.__node;
    const w = node.widgets.find((x) => x.name === "timeline");
    const res = await fetch("/run", { method: "POST", body: w.value || "" });
    const got = await res.json();
    node.onExecuted({ text: [got.text], xenoform_board: [JSON.stringify(got.view)] });
    return true;
  },
};
"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Morph Timeline harness</title>
<style>body{margin:0;background:#0b0b0f;color:#ececf1;font:13px system-ui;padding:16px}
canvas{background:#1b1b22;border-radius:8px;display:block;margin:12px 0}button{height:30px;padding:0 12px}</style></head>
<body><h3>Xenoform Morph Timeline: a stand-in node</h3>
<p id="sum"></p><canvas id="node" width="360" height="140"></canvas>
<button id="open">Open the Morph Timeline</button> <span id="val"></span>
<script type="module">
import { app } from "/scripts/app.js";
await import("/extensions/xenoform/morph_timeline.js");
const ext = app.extensions.find((e) => e.name === "xenoform.morphTimeline");
function TimelineNode() {}
await ext.beforeRegisterNodeDef(TimelineNode, { name: "XenoformMorphTimeline" });
const node = new TimelineNode();
Object.assign(node, { id: 3, size: [360, 140], flags: {}, widgets: [{ name: "timeline", value: "", type: "text", options: {} }] });
node.addWidget = (type, name, value, callback, options) => { const w = { type, name, value, callback, options: options || {} }; node.widgets.push(w); return w; };
node.setDirtyCanvas = () => draw();
node.setSize = (s) => { node.size = s; };
node.onNodeCreated();
window.__node = node;
function draw() {
  const c = document.getElementById("node"), g = c.getContext("2d");
  g.clearRect(0, 0, c.width, c.height);
  node.onDrawForeground(g);
  document.getElementById("sum").textContent = node._xfText || "";
  const w = node.widgets.find((x) => x.name === "timeline");
  document.getElementById("val").textContent = w.value ? `saved edits: ${w.value.length} chars` : "no edits saved";
  window.__hidden = { type: w.type, hidden: w.hidden, size: w.computeSize && w.computeSize() };
}
const got = await (await fetch("/view.json")).json();
node.onExecuted({ text: [got.text], xenoform_board: [JSON.stringify(got.view)] });
draw();
document.getElementById("open").onclick = () => node.widgets.find((x) => x.type === "button").callback();
window.__ready = true;
</script></body></html>"""


class Harness:
    def __init__(self):
        self.song = NODES["XenoformSongAnalysis"]().analyse("demo.wav", 12, "numpy")["result"][0]
        self.board = NODES["XenoformStoryboard"]().plan(self.song, "chrome-mercury", "", "dense", 0, 0.5, 0.3, 0.5, "auto",
                                                        "smooth", "viscous", "16:9", 2727)["result"][0]
        self.runs: list[str] = []

    def run(self, timeline: str) -> dict:
        self.runs.append(timeline)
        out = NODES["XenoformMorphTimeline"]().edit(self.board, timeline)
        return {"text": out["ui"]["text"][0], "view": json.loads(out["ui"]["xenoform_board"][0])}


HARNESS: Harness | None = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if url.path == "/scripts/app.js":
            return self._send(200, STUB_APP.encode("utf-8"), "text/javascript")
        if url.path.startswith("/extensions/xenoform/"):
            f = (PACK / "web" / url.path.rsplit("/", 1)[-1]).resolve()
            if f.is_file() and f.parent == (PACK / "web").resolve():
                return self._send(200, f.read_bytes(), "text/javascript")
            return self._send(404, b"no", "text/plain")
        if url.path == "/view.json":
            return self._send(200, json.dumps(HARNESS.run("")).encode("utf-8"), "application/json")
        if url.path == "/runs.json":
            return self._send(200, json.dumps(HARNESS.runs).encode("utf-8"), "application/json")
        if url.path == "/xenoform_nodes/still":
            data = routes.thumbnail(q.get("file", ""), int(q.get("w", "176") or 176))
            return self._send(200, data, "image/jpeg") if data else self._send(404, b"no", "text/plain")
        if url.path == "/xenoform_nodes/song":
            path = routes.allowed_song(q.get("path", ""))
            if path is None:
                return self._send(404, b"no", "text/plain")
            data = path.read_bytes()
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                start = int(a or 0)
                end = int(b) if b else len(data) - 1
                chunk = data[start:end + 1]
                return self._send(206, chunk, "audio/wav", {"Content-Range": f"bytes {start}-{start + len(chunk) - 1}/{len(data)}",
                                                            "Accept-Ranges": "bytes"})
            return self._send(200, data, "audio/wav", {"Accept-Ranges": "bytes"})
        return self._send(404, b"no", "text/plain")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/run":
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n).decode("utf-8") if n else ""
            return self._send(200, json.dumps(HARNESS.run(body)).encode("utf-8"), "application/json")
        return self._send(404, b"no", "text/plain")


def main() -> int:
    global HARNESS
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 47366
    HARNESS = Harness()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Morph Timeline harness on http://127.0.0.1:{port}/", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

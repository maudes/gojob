"""Re-export the Mermaid diagrams in this folder (*.mmd) to ../img/*.svg.

    python3 docs/diagrams/export.py

Then open http://127.0.0.1:8765 in a browser. The page renders every .mmd and saves the SVG next to the
others; it needs an internet connection to load the Mermaid library. Stop the script with Ctrl+C when the
page says "done". Nothing is sent anywhere except the library download.
"""
import http.server
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "img"
PORT = 8765


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str = "text/plain; charset=utf-8", code: int = 200) -> None:
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send((HERE / "export.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/list":
            self._send(json.dumps(sorted(p.name for p in HERE.glob("*.mmd"))).encode(), "application/json")
        elif self.path.startswith("/src/") and self.path[5:] in {p.name for p in HERE.glob("*.mmd")}:
            self._send((HERE / self.path[5:]).read_bytes())
        else:
            self._send(b"not found", code=404)

    def do_POST(self) -> None:  # noqa: N802
        name = self.path.removeprefix("/save/")
        if not self.path.startswith("/save/") or "/" in name or not name.endswith(".svg"):
            return self._send(b"bad name", code=400)
        body = self.rfile.read(int(self.headers["content-length"]))
        (OUT / name).write_bytes(body)
        self._send(b"ok")

    def log_message(self, *args: object) -> None:
        pass


if __name__ == "__main__":
    print(f"Open http://127.0.0.1:{PORT} in a browser, wait for 'done', then press Ctrl+C.")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

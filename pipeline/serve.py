#!/usr/bin/env python3
"""Local dev server for site/ with HTTP Range support (PMTiles needs it; python -m http.server lacks it).
Usage: python pipeline/serve.py [port]   →  http://localhost:8000"""
import os, re, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

class RangeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(SITE), **k)
    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes"); super().end_headers()
    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)", rng); size = os.path.getsize(path)
        start = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2)))
        end = int(m.group(2)) if m.group(1) and m.group(2) else size - 1
        end = min(end, size - 1)
        f = open(path, "rb"); f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._range_len = end - start + 1
        return f
    def copyfile(self, src, dst):
        n = getattr(self, "_range_len", None)
        if n is None: return super().copyfile(src, dst)
        dst.write(src.read(n))
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"serving {SITE} at http://localhost:{port}")
    ThreadingHTTPServer(("", port), RangeHandler).serve_forever()

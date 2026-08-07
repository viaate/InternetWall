#!/usr/bin/env python3
"""
Screenshot helper. Renders pages and artifacts through the pre-installed Chromium so
what gets checked is what a browser actually draws.

cairosvg was used for this at first and quietly ignored textLength, which made correct
artwork look broken and nearly sent a good file to the bin. Anything checked here goes
through a real layout engine.

Chromium is not Safari, so this catches layout and art bugs but not WebKit-specific ones.
Those still need the iPad.

    python3 src/shoot.py art                      every art/*.svg to one contact sheet
    python3 src/shoot.py page index.html out.png  a page at iPad Air 4 landscape
    python3 src/shoot.py page index.html out.png --w 820 --h 1180
"""

import argparse
import glob
import http.server
import os
import pathlib
import socketserver
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# iPad Air 4, landscape, in CSS points. The Pro 11 is 1210x834, within 1%.
AIR_W, AIR_H = 1180, 820


def serve(directory):
    """A file:// origin blocks some things a real host does not, so serve properly."""
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(
        *a, directory=str(directory), **kw)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def browser(p):
    return p.chromium.launch(executable_path=CHROME, args=["--no-sandbox",
                                                           "--force-device-scale-factor=2"])


def shoot_art(out):
    files = sorted(glob.glob(str(ROOT / "art" / "*.svg")))
    if not files:
        sys.exit("no art/*.svg")
    httpd, port = serve(ROOT)
    # The sheet is written into src/, so art/ is one level up from it.
    cells = "".join(
        f'<figure><img src="../art/{os.path.basename(f)}">'
        f'<figcaption>{os.path.basename(f)}</figcaption></figure>' for f in files)
    page_html = f"""<!doctype html><meta charset=utf-8>
    <style>
      body{{margin:0;background:#e9e9e6;font:12px Helvetica,Arial,sans-serif;
            display:flex;flex-wrap:wrap;gap:16px;padding:16px;align-items:flex-start}}
      figure{{margin:0;background:#fff;padding:8px;box-shadow:0 2px 8px rgba(0,0,0,.18)}}
      img{{display:block;height:340px;width:auto}}
      figcaption{{padding-top:6px;color:#444}}
    </style>{cells}"""
    (ROOT / "src" / "_sheet.html").write_text(page_html, encoding="utf-8")
    with sync_playwright() as p:
        b = browser(p)
        pg = b.new_page(viewport={"width": 1500, "height": 900})
        pg.goto(f"http://127.0.0.1:{port}/src/_sheet.html")
        pg.wait_for_timeout(700)
        pg.screenshot(path=out, full_page=True)
        b.close()
    httpd.shutdown()
    (ROOT / "src" / "_sheet.html").unlink(missing_ok=True)
    print(f"wrote {out} ({len(files)} artifacts)")


def shoot_page(target, out, w, h, wait, clicks):
    httpd, port = serve(ROOT)
    with sync_playwright() as p:
        b = browser(p)
        pg = b.new_page(viewport={"width": w, "height": h})
        errors = []
        pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
              if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        failed = []
        pg.on("requestfailed", lambda r: failed.append(r.url))
        pg.goto(f"http://127.0.0.1:{port}/{target}")
        pg.wait_for_timeout(wait)
        for sel in clicks:
            try:
                pg.click(sel, timeout=3000)
                pg.wait_for_timeout(900)
            except Exception as exc:
                print(f"  click {sel!r} failed: {str(exc)[:90]}")
        pg.screenshot(path=out)
        b.close()
    httpd.shutdown()
    print(f"wrote {out} at {w}x{h}")
    for e in errors[:20]:
        print("  !", e[:160])
    for f in failed[:20]:
        print("  ! request failed:", f[:160])
    if not errors and not failed:
        print("  no console errors, no failed requests")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["art", "page"])
    ap.add_argument("target", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--w", type=int, default=AIR_W)
    ap.add_argument("--h", type=int, default=AIR_H)
    ap.add_argument("--wait", type=int, default=1100)
    ap.add_argument("--click", action="append", default=[])
    a = ap.parse_args()
    if a.mode == "art":
        shoot_art(a.target or "/tmp/artifacts.png")
    else:
        shoot_page(a.target, a.out, a.w, a.h, a.wait, a.click)


if __name__ == "__main__":
    main()

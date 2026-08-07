#!/usr/bin/env python3
"""
Drives the app through the states a screenshot of the front page never reaches:
the long-press settings panel, the idle wall, the saga scrolled down to its video
plates and scoreboard, and the offline case.

Chromium, not Safari, so this proves layout and logic and not WebKit behaviour.
The iPad is still the last word on video, audio, and memory.

    python3 src/verify.py            writes shots to /tmp and prints a report
"""

import http.server
import pathlib
import socketserver
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/verify")
W, H = 1180, 820


def serve():
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(
        *a, directory=str(ROOT), **kw)
    # Threading matters: a single-threaded server blocks on a video byte-range
    # request and starves every other asset, which looks exactly like the app
    # failing to load media.
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    httpd, port = serve()
    base = f"http://127.0.0.1:{port}/"
    fails, notes = [], []

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME,
                              args=["--no-sandbox", "--force-device-scale-factor=2",
                                    "--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": W, "height": H})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error"
              and "404" not in m.text and "favicon" not in m.text else None)
        pg.goto(base, wait_until="networkidle")

        # --- the wall must never be able to navigate away -------------------
        anchors = pg.evaluate("() => document.querySelectorAll('a[href]').length")
        if anchors:
            fails.append(f"{anchors} <a href> present — a tap could leave the kiosk")
        notes.append(f"anchors with href: {anchors}")

        # --- settings via long press on bare wall ---------------------------
        pg.mouse.move(600, 780)
        pg.mouse.down()
        pg.wait_for_timeout(1700)
        pg.mouse.up()
        pg.wait_for_timeout(400)
        if not pg.is_visible("#settings.on"):
            fails.append("long-press on bare wall did not open settings")
        else:
            pg.screenshot(path=OUT / "settings.png")
            notes.append("settings panel opens on long press")

        # a swatch must actually repaint the wall
        before = pg.evaluate("() => getComputedStyle(document.documentElement)"
                             ".getPropertyValue('--wall').trim()")
        pg.click(".sw:nth-child(7)")
        pg.wait_for_timeout(200)
        after = pg.evaluate("() => getComputedStyle(document.documentElement)"
                            ".getPropertyValue('--wall').trim()")
        if before == after:
            fails.append("wall colour swatch did not change --wall")
        notes.append(f"swatch changes wall: {before} -> {after}")
        pg.click("#setDone")
        pg.wait_for_timeout(300)

        # settings must survive a reload, or calibration is pointless
        pg.reload(wait_until="networkidle")
        persisted = pg.evaluate("() => getComputedStyle(document.documentElement)"
                                ".getPropertyValue('--wall').trim()")
        if persisted != after:
            fails.append(f"settings did not persist: {persisted!r} != {after!r}")
        notes.append(f"persisted across reload: {persisted}")

        # put it back so the committed default is not whatever was clicked here
        pg.evaluate("() => { localStorage.removeItem('wall.cfg'); }")

        # --- idle ------------------------------------------------------------
        pg.evaluate("() => { cfg.idleMin = 1/60; resetIdle(); }")
        pg.wait_for_timeout(1800)
        if not pg.evaluate("() => document.body.classList.contains('idle')"):
            fails.append("idle never engaged")
        else:
            pg.wait_for_timeout(1800)   # let the fade finish
            pg.screenshot(path=OUT / "idle.png")
            notes.append("idle engages and fades to bare wall")

        # a wake tap must not also open a story
        pg.mouse.click(183, 205)        # dead centre of the CarterPCs frame
        pg.wait_for_timeout(400)
        if pg.evaluate("() => document.body.classList.contains('story-open')"):
            fails.append("the tap that wakes the wall also opened a story")
        else:
            notes.append("wake tap is swallowed, no story opened")
        if pg.evaluate("() => document.body.classList.contains('idle')"):
            fails.append("tap did not wake the wall")

        # --- the saga ---------------------------------------------------------
        pg.evaluate("() => { cfg.idleMin = 15; resetIdle(); }")
        pg.click("[data-key=booksR]")
        pg.wait_for_timeout(600)
        plates = pg.evaluate("() => document.querySelectorAll('.plate').length")
        notes.append(f"saga chapters with a play plate: {plates}")
        if plates < 8:
            fails.append(f"expected 8 video plates, found {plates}")

        pg.evaluate("() => { const b=document.querySelector('#storyBody');"
                    " b.scrollTop = b.scrollHeight * 0.30; }")
        pg.wait_for_timeout(500)
        pg.screenshot(path=OUT / "saga-mid.png")

        # One <video> at a time is the whole point of the plate design.
        #
        # Playback itself cannot be checked here: this Chromium ships without H.264 or
        # AAC (canPlayType returns "" for both) and the clips are avc1, so every element
        # errors on load. Safari on the iPad decodes H.264 in hardware, so this is a
        # limitation of the test browser, not of the app. What is still worth asserting
        # is the lifecycle — that opening a second clip disposes of the first.
        codec = pg.evaluate('''() => document.createElement('video')
            .canPlayType('video/mp4; codecs="avc1.42E01E"') || 'unsupported' ''')
        notes.append(f"test browser H.264 support: {codec}")

        pg.evaluate("() => document.querySelectorAll('.plate')[0].click()")
        pg.wait_for_timeout(900)
        pg.evaluate("() => { const p=document.querySelectorAll('.plate');"
                    " if (p.length) p[0].click(); }")
        pg.wait_for_timeout(900)
        live = pg.evaluate("() => document.querySelectorAll('video').length")
        notes.append(f"live <video> elements after opening two clips: {live}")
        if live > 1:
            fails.append(f"{live} video elements alive at once — A14 memory risk")

        # Our own teardown fires `error` on the element it is disposing of. If that is
        # mistaken for a broken file, a working clip gets covered with a failure notice.
        spurious = pg.evaluate('''() => [...document.querySelectorAll('.missing')]
            .filter(n => /this clip/.test(n.textContent)).length''')
        notes.append(f"clips wrongly marked missing by teardown: {spurious}")
        if spurious and codec != 'unsupported':
            fails.append("teardown marked a working clip as missing")

        # scoreboard
        pg.evaluate("""() => {
            const b = document.querySelector('#storyBody');
            const s = document.querySelector('.scores');
            if (s) b.scrollTop = s.offsetTop - 40;
        }""")
        pg.wait_for_timeout(400)
        pg.evaluate("() => { const b=document.querySelector('.guess button');"
                    " if (b) b.click(); }")
        pg.wait_for_timeout(1200)
        widths = pg.evaluate("() => [...document.querySelectorAll('.fill')]"
                             ".map(f => f.getBoundingClientRect().width)")
        if widths and max(widths) < 5:
            fails.append("scoreboard bars stayed at zero after guessing")
        notes.append(f"scoreboard bar widths after a guess: "
                     f"{[round(w) for w in widths[:4]]}...")
        pg.screenshot(path=OUT / "saga-scores.png")

        # --- offline ----------------------------------------------------------
        # Not tested by toggling Chromium's offline flag: that blocks loopback too, so
        # the page cannot even be re-served and the run dies on ERR_INTERNET_DISCONNECTED
        # without having proven anything. What actually matters is that no request ever
        # leaves the device, which is a property of the source and of the request log.
        pg.evaluate("() => document.querySelector('#storyClose').click()")

        external = pg.evaluate("""() => {
            const out = [];
            for (const r of performance.getEntriesByType('resource')) {
                const u = new URL(r.name, location.href);
                if (u.origin !== location.origin) out.push(r.name);
            }
            return out;
        }""")
        if external:
            fails.append(f"requests left the device: {external[:3]}")
        notes.append(f"cross-origin requests made during the whole run: {len(external)}")

        src = (ROOT / "index.html").read_text()
        import re
        remote = [m for m in re.findall(r'https?://[^\s"\'<>)]+', src)
                  if not m.startswith("http://www.w3.org/")]   # the SVG namespace is not a fetch
        if remote:
            fails.append(f"index.html contains remote URLs: {remote[:3]}")
        notes.append(f"remote URLs in index.html: {len(remote)}")

        pg.screenshot(path=OUT / "offline.png")

        if errs:
            fails.append(f"javascript errors: {errs[:3]}")

        b.close()
    httpd.shutdown()

    print("\n".join("  · " + n for n in notes))
    print()
    if fails:
        print("FAIL")
        for f in fails:
            print("  ✗ " + f)
        sys.exit(1)
    print("PASS — all checks green")


if __name__ == "__main__":
    main()

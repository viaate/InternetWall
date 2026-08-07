#!/usr/bin/env python3
"""Drives the calibration page in a real browser.

Every check here is about a mistake that produces no error and looks fine. A corner that
lands a few pixels from where it was tapped still draws a quadrilateral. Corners wound
anticlockwise still solve, and render a mirror image with backwards text and no warning
anywhere. Neither shows up by reading the code or by looking at a screenshot, so both get
clicked at.

    python3 src/calibrate.test.py
"""
import asyncio, sys
from playwright.async_api import async_playwright
import http.server, socketserver, threading, functools, os, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
_s = importlib.util.spec_from_file_location("sh", os.path.join(HERE, "shoot.py"))
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
CHROME = _m.CHROME
H = functools.partial(http.server.SimpleHTTPRequestHandler)
class T(socketserver.ThreadingTCPServer): allow_reuse_address=True
srv = T(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

async def main():
    fails=[]
    def ck(n, ok, d=""):
        print(("ok    " if ok else "FAIL  ")+n.ljust(44)+d)
        if not ok: fails.append(n)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width":1400,"height":900})
        errs=[]
        # favicon is the harness asking, not the page failing
        pg.on("console", lambda m: errs.append(m.text) if (m.type=="error" and "favicon" not in m.location.get("url","")) else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(f"http://127.0.0.1:{port}/src/calibrate.html")
        await pg.evaluate("""(url)=>new Promise(r=>{
            const im=document.querySelector('#img');
            im.onload=()=>{ nat={w:im.naturalWidth,h:im.naturalHeight};
                            drawList(); paint(); r(); };
            im.src=url; })""", f"http://127.0.0.1:{port}/ForOliviaToApprove/plate-temp.jpg")
        ck("page loads with no errors", not errs, "; ".join(errs[:2]))

        # the TV corners, clockwise from top left, as fractions
        frac = [(0.2797,0.3712),(0.6944,0.3676),(0.6912,0.6966),(0.2780,0.7040)]
        box = await pg.evaluate("()=>{const r=imgRect();return {x:r.x,y:r.y,w:r.w,h:r.h};}")
        sw = await pg.evaluate("()=>{const s=document.querySelector('#stageWrap').getBoundingClientRect();return {x:s.left,y:s.top};}")
        for fx,fy in frac:
            await pg.mouse.click(sw['x']+box['x']+fx*box['w'], sw['y']+box['y']+fy*box['h'])
        out = await pg.evaluate("()=>document.querySelector('#out').value")
        ck("four clicks produce JSON", "tv" in out, out[:44].replace("\n"," "))
        got = await pg.evaluate("()=>pts.tv.map(p=>[+(p[0]/nat.w).toFixed(3),+(p[1]/nat.h).toFixed(3)])")
        errmax = max(max(abs(g[0]-f[0]),abs(g[1]-f[1])) for g,f in zip(got,frac))
        ck("corners land where clicked", errmax < 0.004, f"max frac error {errmax:.4f}")
        hint = await pg.evaluate("()=>document.querySelector('#hint').textContent")
        ck("reports done for a valid quad", "done" in hint, hint[:40])

        # wound backwards: must be refused, not silently mirrored
        await pg.evaluate("()=>{pts.tv=[];drawList();paint();}")
        for fx,fy in reversed(frac):
            await pg.mouse.click(sw['x']+box['x']+fx*box['w'], sw['y']+box['y']+fy*box['h'])
        hint = await pg.evaluate("()=>document.querySelector('#hint').textContent")
        out2 = await pg.evaluate("()=>document.querySelector('#out').value")
        ck("reversed winding is refused", "wrong way" in hint and "tv" not in out2, hint[:46])

        # undo
        await pg.evaluate("()=>{pts.tv=[[10,10],[20,10],[20,20]];drawList();paint();}")
        await pg.keyboard.press("Escape")
        n = await pg.evaluate("()=>pts.tv.length")
        ck("escape removes the last point", n==2, f"{n} left")

        await pg.screenshot(path="/tmp/claude-0/-home-user/f4e6fbbb-6c81-50a2-aeee-05d93bbeb71a/scratchpad/calib.png")
        await b.close()
    print()
    print("all passed" if not fails else f"{len(fails)} FAILED")
    sys.exit(1 if fails else 0)
asyncio.run(main())

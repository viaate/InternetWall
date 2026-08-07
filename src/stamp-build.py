#!/usr/bin/env python3
"""
Stamps sw.js with the current commit, so every deploy busts the cache.

A service worker is only re-evaluated by the browser when its own bytes change. With a
hardcoded version string, sw.js is byte-identical between deploys, the browser keeps the
old worker, and nothing ships. This changes one line per commit, which is enough.

Run before pushing:

    python3 src/stamp-build.py
"""

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
sw = ROOT / "sw.js"

build = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                       cwd=ROOT, capture_output=True, text=True).stdout.strip() or "dev"
text = sw.read_text()
new = re.sub(r"const BUILD = '[^']*';", f"const BUILD = '{build}';", text)
if new == text and f"'{build}'" not in text:
    raise SystemExit("could not find the BUILD line in sw.js")
sw.write_text(new)
print(f"sw.js stamped with build {build}")

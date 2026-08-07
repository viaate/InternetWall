#!/usr/bin/env python3
"""Tests for the light-layer builder.

Built on a synthetic shoot rather than on real frames, because a synthetic one has a
ground truth: the exact light that was added is known, so the question "did we recover
it" has an answer rather than an opinion. The real shoot cannot answer that about itself.

    python3 src/make-layers.test.py
"""

import importlib.util
import pathlib
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ml", HERE / "make-layers.py")
ml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ml)

fails = []


def check(name, ok, detail=""):
    print(("ok    " if ok else "FAIL  ") + name.ljust(46) + detail)
    if not ok:
        fails.append(name)


def add(b, l):
    """How a light source combines with the room, matching what the app does.

    Addition, not screen. The layers are linear differences and CSS composites them with
    plus-lighter, so the test has to model addition or it is measuring the gap between two
    different pipelines rather than testing one.
    """
    return np.clip(b + np.clip(l, 0, 255), 0, 255)


def synth(w=520, h=390, seed=7):
    """A room with structure in it. Structure matters: alignment is matched on edges, so
    a smooth gradient would have nothing to align against and every shift would score
    the same."""
    rng = np.random.default_rng(seed)
    a = rng.normal(96, 12, (h, w, 3))
    for i in range(14):                      # objects, giving the frame real edges
        y, x = rng.integers(0, h - 40), rng.integers(0, w - 40)
        hh, ww = rng.integers(18, 40), rng.integers(18, 40)
        a[y:y + hh, x:x + ww] += rng.normal(0, 46, 3)
    return np.clip(a, 4, 250)


def blob(w, h, cx, cy, rx, ry, rgb, amp):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    g = np.exp(-(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2))
    return np.dstack([g * rgb[i] * amp for i in range(3)])


def nudge(a, dy, dx):
    h, w = a.shape[:2]
    out = np.zeros_like(a)
    out[max(0, dy):min(h, h + dy), max(0, dx):min(w, w + dx)] = \
        a[max(0, -dy):min(h, h - dy), max(0, -dx):min(w, w - dx)]
    return out


# --------------------------------------------------------------------- alignment

base = synth()
h, w = base.shape[:2]
lit = add(base, blob(w, h, w * .3, h * .35, w * .22, h * .22, (1, .8, .5), 140))
truth, _ = ml.difference(base, lit)

# The bug this exists to catch: best_shift returns the offset to APPLY, not the offset it
# measured. Returning the measurement made every correction run backwards, landing the
# frame twice as far out as it started while reporting a plausible number, so the sign is
# asserted directly rather than inferred from the error going down.
worst = 0.0
for dy, dx in [(0, 0), (1, 2), (3, 4), (-2, 5), (5, -3), (-4, -4), (6, 0), (0, -6)]:
    got, _ = ml.best_shift(base, nudge(lit, dy, dx))
    check(f"shift ({dy:>2},{dx:>2}) is undone by ({dy:>2},{dx:>2})", got == (dy, dx),
          f"got {got}")

    C = 14      # a border band wider than any shift here; nothing real is measured there
    fixed, _ = ml.difference(base, ml.shift(nudge(lit, dy, dx), *got))
    err = float(np.abs(fixed[C:-C, C:-C, 3] - truth[C:-C, C:-C, 3]).mean())
    worst = max(worst, err)
check("recovered layer matches ground truth", worst < 1e-6, f"worst {worst:.2e}")

# --------------------------------------------------------------------- difference

d, peak = ml.difference(base, base)
check("an unchanged frame yields no layer", d is None, "no light added")

darker, _ = ml.difference(base, base * 0.7)
check("a darker frame cannot subtract light", darker is None,
      "clipped at zero, no dark holes")

# --------------------------------------------------------------------- additivity

l1 = blob(w, h, w * .3, h * .3, w * .2, h * .2, (1, .75, .45), 130)
l2 = blob(w, h, w * .7, h * .6, w * .18, h * .16, (.4, .7, 1), 120)
both = add(add(base, l1), l2)
a1, _ = ml.difference(base, add(base, l1))
a2, _ = ml.difference(base, add(base, l2))
comp = base.copy()
for lay in (a1, a2):
    al = lay[..., 3:4] / 255.0
    comp = comp + lay[..., :3] * al
comp = np.clip(comp, 0, 255)
err = float(np.abs(comp - both).mean())
check("two layers composite to the real combination", err < 1.0, f"mean {err:.2f}/255")

# --------------------------------------------------------------------- end to end

with tempfile.TemporaryDirectory() as td:
    ind, outd = pathlib.Path(td) / "shoot", pathlib.Path(td) / "out"
    ind.mkdir()
    save = lambda arr, n: Image.fromarray(
        np.clip(arr, 0, 255).astype(np.uint8)).save(ind / n, quality=96)
    save(base, "base.jpg")
    save(add(base, l1), "light-warm.jpg")
    save(add(base, l2), "strip-white.jpg")
    save(nudge(add(base, blob(w, h, w * .5, h * .5, w * .14, h * .1, (.9, .9, 1), 150)),
               2, -3), "tv.jpg")

    sys.argv = ["make-layers.py", str(ind), str(outd), "--width", str(w)]
    ml.main()

    import json
    man = json.loads((outd / "layers.json").read_text())
    keys = {l["key"] for l in man["layers"]}
    check("end to end writes every layer", keys == {"light-warm", "strip", "tv"}, str(sorted(keys)))
    check("the strip is the one tintable layer",
          [l["key"] for l in man["layers"] if l["tint"]] == ["strip"])
    check("base and layer files all exist",
          all((outd / l["src"]).exists() for l in man["layers"]) and (outd / "base.jpg").exists())

    tv = np.asarray(Image.open(outd / "tv.png").convert("RGBA")).astype(np.float32)
    b = 4
    edge = max(tv[:b, :, 3].max(), tv[-b:, :, 3].max(), tv[:, :b, 3].max(), tv[:, -b:, 3].max())
    check("an aligned frame leaves no bright border", edge == 0, f"max edge alpha {edge:.0f}")

print()
print("all passed" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)

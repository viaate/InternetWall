#!/usr/bin/env python3
"""Turn the six-frame shoot into light layers the app can add together.

The room page is a photograph. Turning the ceiling light on does not simulate light, it
shows a second photograph of the same room with the light actually on. That is exact and
it cannot look drawn, because it is not drawn.

The problem is combinations. Six frames give six states, but the room has far more than
six: light warm with the strip cyan and the TV on is a state nobody photographed and
nobody is going to. Cross-fading whole frames cannot produce it.

Light adds. Two sources on together put out, to a very good approximation, the sum of
what each puts out alone. So subtract the base frame from each state frame and what is
left is precisely that one source's contribution to every pixel. Store those differences,
add them back onto the base, and any combination composites by adding the layers you
want. Six photographs, every state.

Added, specifically, not screened. A difference is a linear measurement and screen is not
a linear operator, so differencing one way and compositing the other does not round-trip:
it comes back a few counts off on every pixel where two sources overlap, which is exactly
where the eye is looking. The layers are composited in CSS with mix-blend-mode
plus-lighter, which is addition, and this file's own check uses addition to match.

The honest caveat is gamma. Radiance adds in linear light, and a JPEG is gamma-encoded,
so adding encoded values slightly overstates the result in the shadows. Doing it properly
would mean linearising, adding, and re-encoding, which CSS blend modes cannot do at
composite time, so the whole pipeline stays in sRGB and is consistent with itself rather
than being correct in one half and not the other.

    python3 src/make-layers.py shoot/ room/

Expects, in the input directory:

    base.jpg          everything off
    light-warm.jpg    ceiling light warm
    light-white.jpg   ceiling light cool          (optional)
    strip-white.jpg   strip on, set to white
    tv.jpg            TV on, showing something bright
    check.jpg         strip and TV on together    (optional, see --check)

Writes base.jpg plus one PNG per layer, and layers.json describing them.

Two things this does that matter more than they sound:

Alignment. The instruction is that the camera must not move, and the camera always moves
a little. A two pixel shift is invisible in any single frame and very visible the moment
two frames are subtracted, as a bright outline around every edge in the room. So each
frame is registered against the base by brute-force integer shift search before anything
is subtracted.

The strip layer is stored white and tinted at runtime. The strip can be any colour and
nobody is photographing all of them, but the *shape* of the light it throws, which
surfaces catch it and how it falls off, is the same whatever colour it is. Photograph it
white, keep the shape, multiply by the hue at runtime.
"""

import argparse
import json
import pathlib
import sys

import numpy as np
from PIL import Image

# Which frames make which layer. `tint` marks a layer whose colour is set at runtime
# rather than baked, which is true of exactly one thing: the strip.
FRAMES = [
    # filename          layer key       device   state      tint
    ("light-warm.jpg",  "light-warm",   "light", "warm",    False),
    ("light-white.jpg", "light-white",  "light", "white",   False),
    ("strip-white.jpg", "strip",        "strip", "on",      True),
    ("tv.jpg",          "tv",           "tv",    "on",      False),
]

MAX_SHIFT = 6          # px. Beyond this the phone was knocked, and no shift will save it.


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)


def _edges(a, step=1):
    """Gradient magnitude, optionally decimated.

    Matched on gradients rather than on pixels because the whole point is that the two
    frames differ in brightness. Matching on brightness would rate the darkest alignment
    as the best one, which is not the question being asked; edges sit where the room's
    geometry is and the geometry is what has to line up.
    """
    g = a.mean(2)[::step, ::step]
    gy, gx = np.gradient(g)
    return np.hypot(gy, gx)


def _score(b, f, dy, dx, m):
    bb = b[m + dy:b.shape[0] - m + dy, m + dx:b.shape[1] - m + dx]
    ff = f[m:f.shape[0] - m, m:f.shape[1] - m]
    return float(np.abs(bb - ff).mean())


def best_shift(base, frame, max_shift=MAX_SHIFT):
    """Find the integer (dy, dx) that best lines `frame` up with `base`.

    Coarse to fine, and the fine pass is the whole reason this function exists. Searching
    only on a quarter-scale image can express shifts in multiples of four pixels, so a
    three pixel nudge gets "corrected" to four and comes out one pixel worse than doing
    nothing. That is the exact failure this is meant to prevent, so the coarse pass only
    narrows the range and a full-resolution pass settles the last few pixels.

    The fine pass runs on a centre crop. Forty-nine full-frame comparisons at twelve
    megapixels is minutes of work for an answer a central megapixel already contains,
    and the centre of the frame is where the room is.
    """
    COARSE = 4
    cb, cf = _edges(base, COARSE), _edges(frame, COARSE)
    m = max(1, max_shift // COARSE)
    coarse, _ = min(
        (((dy * COARSE, dx * COARSE), _score(cb, cf, dy, dx, m))
         for dy in range(-m, m + 1) for dx in range(-m, m + 1)),
        key=lambda t: t[1],
    )

    h, w = base.shape[:2]
    ch, cw = min(h, 900), min(w, 900)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    fb = _edges(base[y0:y0 + ch, x0:x0 + cw])
    ff = _edges(frame[y0:y0 + ch, x0:x0 + cw])
    r = COARSE - 1
    pad = COARSE + r
    best, err = min(
        (((coarse[0] + dy, coarse[1] + dx),
          _score(fb, ff, coarse[0] + dy, coarse[1] + dx, pad))
         for dy in range(-r, r + 1) for dx in range(-r, r + 1)),
        key=lambda t: t[1],
    )
    # Negated on the way out. The search measures the offset between the two frames;
    # the caller wants the offset to apply to undo it, and those are opposites. Handing
    # back the measurement made every correction run the wrong way and land the frame
    # twice as far out as it started, while still reporting a plausible-looking number.
    return (-best[0], -best[1]), err


def shift(a, dy, dx):
    out = np.zeros_like(a)
    h, w = a.shape[:2]
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    yd0, yd1 = max(0, -dy), min(h, h - dy)
    xd0, xd1 = max(0, -dx), min(w, w - dx)
    out[yd0:yd1, xd0:xd1] = a[ys0:ys1, xs0:xs1]
    return out


def difference(base, frame):
    """The light one source adds, as an RGB image plus the alpha to composite it with.

    Clipped at zero. A source can only add light, so a negative difference is noise or a
    misalignment, never a real measurement, and letting it through would punch dark holes
    into the room wherever the sensor happened to wobble.
    """
    d = np.clip(frame - base, 0, 255)
    # Alpha is how much light arrived at all; colour is the direction it arrived in.
    # Splitting them means the layer can be screened at any strength, and a tintable
    # layer can have its colour replaced while keeping its falloff.
    a = d.max(2)
    peak = float(a.max())
    if peak < 1.0:
        return None, 0.0
    rgb = np.zeros_like(d)
    nz = a > 0
    for c in range(3):
        rgb[..., c][nz] = d[..., c][nz] / a[nz] * 255.0
    return np.dstack([rgb, a]), peak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("indir")
    ap.add_argument("outdir")
    ap.add_argument("--width", type=int, default=2360,
                    help="output width; the iPad is 1180pt at 2x")
    ap.add_argument("--check", action="store_true",
                    help="if check.jpg exists, composite strip+tv and report the error "
                         "against it, which is the only real test that adding works")
    a = ap.parse_args()

    ind, outd = pathlib.Path(a.indir), pathlib.Path(a.outdir)
    outd.mkdir(parents=True, exist_ok=True)

    basep = ind / "base.jpg"
    if not basep.exists():
        sys.exit(f"no {basep}. That frame is the one everything else is measured against.")

    base_full = load(basep)
    H, W = base_full.shape[:2]
    scale = a.width / W
    size = (a.width, int(round(H * scale)))

    def down(arr):
        return np.asarray(
            Image.fromarray(arr.astype(np.uint8)).resize(size, Image.LANCZOS)
        ).astype(np.float32)

    Image.fromarray(base_full.astype(np.uint8)).resize(size, Image.LANCZOS)\
         .save(outd / "base.jpg", quality=88, optimize=True)
    base = down(base_full)

    layers, made = [], {}
    for fname, key, device, state, tint in FRAMES:
        p = ind / fname
        if not p.exists():
            print(f"  {fname:18} absent, skipping")
            continue
        frame_full = load(p)
        if frame_full.shape != base_full.shape:
            sys.exit(f"{fname} is a different size to base.jpg. Same camera, same lens, "
                     f"same orientation, or none of this works.")

        (dy, dx), err = best_shift(base_full, frame_full)
        if abs(dy) >= MAX_SHIFT or abs(dx) >= MAX_SHIFT:
            print(f"  {fname:18} WARNING: needed a {dy},{dx}px shift. The phone moved "
                  f"more than it should have; check for haloes around edges.")
        if dy or dx:
            frame_full = shift(frame_full, dy, dx)

        frame = down(frame_full)
        rgba, peak = difference(base, frame)
        if (dy or dx) and rgba is not None:
            # Aligning vacates a band at one or two edges, which is filled with zeros and
            # would subtract as a bright border all the way round the layer. Nothing real
            # is measured there, so nothing is claimed there.
            b = int(np.ceil(max(abs(dy), abs(dx)) * scale)) + 1
            rgba[:b, :, 3] = 0; rgba[-b:, :, 3] = 0
            rgba[:, :b, 3] = 0; rgba[:, -b:, 3] = 0
        if rgba is None:
            print(f"  {fname:18} adds no light at all. Was the source actually on, and "
                  f"was exposure locked?")
            continue

        out = f"{key}.png"
        Image.fromarray(rgba.astype(np.uint8), "RGBA").save(outd / out, optimize=True)
        made[key] = rgba
        layers.append({"key": key, "src": out, "device": device, "state": state,
                       "tint": tint, "peak": round(peak, 1)})
        print(f"  {fname:18} -> {out}  shift {dy},{dx}  peak +{peak:.0f}")

    (outd / "layers.json").write_text(json.dumps(
        {"base": "base.jpg", "size": list(size), "layers": layers}, indent=2) + "\n")

    if a.check and (ind / "check.jpg").exists() and "strip" in made and "tv" in made:
        # The whole design rests on light adding. This is the one measurement that says
        # whether it does, in this room, on this camera, rather than in principle.
        real_full = load(ind / "check.jpg")
        (dy, dx), _ = best_shift(base_full, real_full)
        real = down(shift(real_full, dy, dx) if (dy or dx) else real_full)
        comp = base.copy()
        for k in ("strip", "tv"):
            rgba = made[k]
            al = rgba[..., 3:4] / 255.0
            comp = comp + rgba[..., :3] * al          # plus-lighter, what CSS will do
        comp = np.clip(comp, 0, 255)
        err = float(np.abs(comp - real).mean())
        print(f"\n  additive check: mean error {err:.1f}/255 against the real photograph")
        print("  under 4 is indistinguishable, 4-10 is fine, above that something moved.")

    print(f"\nwrote {len(layers)} layers to {outd}")


if __name__ == "__main__":
    main()

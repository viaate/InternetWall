#!/usr/bin/env python3
"""
Bakes the drywall texture used behind the whole app.

Why bake it instead of doing it live: the obvious way to get this look on the web is an
SVG <feTurbulence> filter, but a filter is re-evaluated on every repaint of the layer it
sits on. On the A14 in the iPad Air that is a measurable cost for something that never
changes. A pre-rendered tile costs exactly one decode at load and nothing afterwards.

Seamlessness comes from building the noise in the frequency domain. An inverse FFT is
periodic by construction, so the tile wraps on both axes with no matching or mirroring,
and no visible seam grid when it repeats across a 1180pt wall.

Output is RGBA: white where the wall bulges toward the light, black where it dips, alpha
carrying the amplitude. That way it composites over any --wall-color without tinting it,
so changing the Sherwin-Williams value stays a one-line edit.

    python3 src/make-wall-texture.py

Writes art/wall-texture.png and prints the base64 data URI length.
"""

import base64
import io
import pathlib

import numpy as np
from PIL import Image

# The tile is sized against the real panel, not picked for roundness. Both iPads are 2x,
# so a 512px tile shown at background-size:256px lands 1:1 on device pixels and never gets
# resampled. At the Air's 264ppi that tile covers ~49mm of wall, which fixes the scale of
# everything below: one tile px is one device px is ~0.096mm.
SIZE = 512
SEED = 20260806

# Orange peel spatter is roughly 2-5mm across. At ~10.4 device px/mm that is 21-52px, so
# the peel band sits at 512/31 ≈ 16 cycles per tile. The first version of this file used
# 34 cycles on a 256 tile, which worked out at 0.7mm and read as fabric grain, not wall.
# A wide band is what makes this look like swirled plaster rather than sprayed peel:
# the Gaussian's lower shoulder leaks energy down to ~9 cycles, i.e. 5-6mm blobs, and the
# eye reads those as clouds. Keeping the band narrow keeps the texture at one scale.
BANDS = [
    # (centre frequency in cycles per tile, bandwidth, weight)
    (18.0, 4.5, 1.00),    # the peel itself, ~2.7mm, tightly banded
    (44.0, 12.0, 0.22),   # a little tooth on top so the blobs are not glassy
]

# The broad undulation left by the taping knife is 20-30mm, which is most of a tile. Putting
# it in here would show up as obvious repetition, so it is a CSS radial gradient instead.

# Painted drywall under diffuse room light varies by only a few percent in luminance.
# 26 looked right in isolation and far too coarse once frames were on top of it, because
# there was suddenly something genuinely flat in shot to compare against.
PEAK_ALPHA = 14     # 0-255


def banded_noise(size, seed, bands):
    """White noise shaped in the frequency domain, so the result tiles seamlessly."""
    rng = np.random.default_rng(seed)
    spec = np.fft.fft2(rng.normal(size=(size, size)))

    fy = np.fft.fftfreq(size) * size
    fx = np.fft.fftfreq(size) * size
    radius = np.hypot(*np.meshgrid(fy, fx, indexing="ij"))

    shaped = np.zeros_like(spec)
    for centre, width, weight in bands:
        # Gaussian band-pass. Smooth shoulders matter: a hard cutoff rings and the
        # ringing shows up as faint concentric halos once the tile repeats.
        shaped += spec * weight * np.exp(-(((radius - centre) / width) ** 2))

    out = np.real(np.fft.ifft2(shaped))
    return out / np.abs(out).max()


def main():
    n = banded_noise(SIZE, SEED, BANDS)

    # Drywall is lit from the room, so bumps catch light more sharply than dips shade.
    # Skewing the positive side slightly keeps it from looking like symmetric TV static.
    # Done via sign/abs rather than np.where(n>0, n**0.85, ...): np.where evaluates both
    # branches for every element, so the discarded branch raises a fractional power of a
    # negative and fills half the array with NaN before the selection throws it away.
    exponent = np.where(n > 0, 0.85, 1.15)
    lit = np.sign(n) * np.abs(n) ** exponent

    alpha = np.clip(np.abs(lit) * PEAK_ALPHA, 0, 255)

    # Ordered dither on alpha. The channel only spans ~20 levels here, and without this
    # the smooth gradients inside each blob quantise into visible contour rings.
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0
    alpha = np.floor(alpha + np.tile(bayer, (SIZE // 4, SIZE // 4)) - 0.5)
    alpha = np.clip(alpha, 0, 255).astype(np.uint8)

    rgb = np.where(lit > 0, 255, 0).astype(np.uint8)
    tile = np.dstack([rgb, rgb, rgb, alpha])

    img = Image.fromarray(tile, "RGBA")
    out = pathlib.Path(__file__).resolve().parent.parent / "art" / "wall-texture.png"
    img.save(out, optimize=True)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"data URI length: {len(b64):,} chars")
    print(f"alpha: mean {alpha.mean():.2f}  max {alpha.max()}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Turns the photographs and scans in src/ into the files the app loads from art/,
and generates the QR codes.

Run it after dropping a new photo into src/:

    python3 src/build-assets.py

Nothing here is clever. It exists so that redoing an asset is one command rather than
a sequence of remembered crops, and so the crop maths is written down instead of living
in somebody's head.
"""

import pathlib
import re

import numpy as np
import segno
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
ART = ROOT / "art"


def save(im, name, width, quality=88):
    """Downscale to a sane width and write. 1600px covers a full-bleed hero on a 2x
    panel; anything larger is bytes the iPad decodes and then throws away."""
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    out = ART / name
    out.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(out, quality=quality, optimize=True, progressive=True)
    print(f"  {name:34s} {im.width}x{im.height}  {out.stat().st_size//1024:>4d} KB")


def trim_to_frame(path, thresh=118, pad=0, inset=0):
    """Crop a photographed frame off its dark background.

    The frames are white and were shot on a dark surface, so the object is simply the
    bright region. Row/column means rather than per-pixel tests, because a stray
    highlight on the background would otherwise drag the bounding box out to the edge.
    """
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(float).mean(axis=2)
    rows = a.mean(axis=1) > thresh
    cols = a.mean(axis=0) > thresh
    ys = np.where(rows)[0]
    xs = np.where(cols)[0]
    if not len(ys) or not len(xs):
        return im
    box = (max(0, xs[0] - pad + inset), max(0, ys[0] - pad + inset),
           min(im.width, xs[-1] + 1 + pad - inset),
           min(im.height, ys[-1] + 1 + pad - inset))
    print(f"    trimmed {im.size} -> {(box[2]-box[0], box[3]-box[1])}")
    return im.crop(box)


# --------------------------------------------------------------------------- photos

BOOKS = [
    ("books/01-hole-new-world.jpg",  "08afcf43-IMG_0151.jpeg"),
    ("books/02-enter-the-mine.jpg",  "a570a50f-IMG_0150.jpeg"),
    ("books/03-zombies-day-off.jpg", "1e259ab3-IMG_0149.jpeg"),
    ("books/04-into-the-overworld.jpg", "3133c2ee-IMG_0147.webp"),
    ("books/05-end-of-all-things.jpg",  "8792ab97-IMG_0148.webp"),
    ("books/06-activity-book.jpg",      "b9964736-IMG_0155.webp"),
]

# The activity book is a smaller trim than the graphic novels: 5.4 x 7.4in against
# 6.7 x 8.7in. On a shelf that is the difference between a matched set and one book
# that is obviously the wrong size, so index.html scales it by height ratio.
ACTIVITY_SCALE = round(7.4 / 8.7, 3)


def match_white(im, target=245):
    """Lift a photograph so its white furniture matches the other frames on the wall.

    The card frame was shot in dimmer light than the Luton one: its moulding sits at
    200,200,201 against 239,247,254, which on a light wall reads as grey plastic next to
    white. Scaling to put the moulding's 90th percentile on `target` fixes the whole
    exposure rather than just the border, with a soft shoulder so the bright parts of
    the cards do not clip to flat white.
    """
    a = np.asarray(im).astype(float)
    h, w, _ = a.shape
    band = np.concatenate([a[:int(h * .05)].reshape(-1, 3), a[-int(h * .05):].reshape(-1, 3),
                           a[:, :int(w * .04)].reshape(-1, 3), a[:, -int(w * .04):].reshape(-1, 3)])
    current = float(np.percentile(band, 90))
    gain = target / current
    print(f"    moulding p90 {current:.0f} -> {target}, gain {gain:.3f}")
    lifted = a * gain
    # Soft shoulder above 235 so specular highlights roll off instead of clipping flat.
    knee = 235.0
    over = lifted > knee
    lifted[over] = knee + (255 - knee) * np.tanh((lifted[over] - knee) / (255 - knee))
    return Image.fromarray(np.clip(lifted, 0, 255).astype(np.uint8))


def photos():
    print("books")
    for name, f in BOOKS:
        save(Image.open(SRC / f), name, 900)

    print("shelf and framed pieces")
    save(Image.open(SRC / "05e52816-IMG_0146.jpeg"), "shelf.jpg", 1400, quality=92)
    # These two are photographs of the real frames, so they are used whole rather than
    # dropped inside a CSS frame, because a drawn moulding around a photographed one reads as
    # two frames.
    save(match_white(trim_to_frame(SRC / "81859b66-IMG_0142.jpeg", inset=10)),
         "cards.jpg", 1600)
    save(trim_to_frame(SRC / "3d0e020c-IMG_0152.jpeg", thresh=100, inset=6), "luton.jpg", 1600)


# --------------------------------------------------------------------------- QR

# Every outbound reference in the app. The iPad cannot follow a link, so each of these
# becomes a QR code somebody points their own phone at.
#
# Share URLs carry a tracking parameter (?si= / ?is=) that identifies the account the
# link was copied from. Handing those out on a wall would tag every scanner as having
# come from Jack's link. They are stripped here, and STRIP_PARAMS is the guard that
# keeps one from creeping back in later.
STRIP_PARAMS = ("si", "is", "feature", "pp", "utm_source", "utm_medium", "utm_campaign")

LINKS = {
    # key                     video id       start seconds
    "carter-meeting":       ("CsOaHKlU3rU", None),
    "carter-freepcs":       ("7sIHuqe6-gY", None),
    "shrek-awkward":        ("RIsr05EOaQs", 486),
    "spoon-buying":         ("RIsr05EOaQs", 373),
    "jack-grandma":         ("CAvKpRMkXSk", 1037),
    "jack-dad":             ("DDvyeek9qLc", 1247),
    "jack-mum":             ("uezUNLa8pJc", 129),
    "jack-sister":          ("e7Y9BsxmgkU", 21),
    "jack-dog":             ("RbsCG0Fh2EE", 174),
    "jack-uncle":           ("m1ngSHEso-4", 119),
    "jack-finale":          ("eZid7JDPbmM", 722),
    "jack-update":          ("luSZf-umwPo", 1033),
    "jack-spoon":           ("MmrI9m67_MY", 213),
    "jack-playbutton":      ("W9Nnu55WXhs", 196),
    "jack-label":           ("KVlYmWmvAlg", 1242),
}


def url_for(vid, t):
    """youtu.be short form: fewer characters means a lower QR version, which means
    chunkier modules, which is what actually matters for a phone reading a 3cm code
    off a screen at arm's length."""
    return f"https://youtu.be/{vid}" + (f"?t={t}" if t else "")


def qr():
    print("qr codes")
    (ART / "qr").mkdir(parents=True, exist_ok=True)
    bad = []
    for key, (vid, t) in LINKS.items():
        u = url_for(vid, t)
        for p in STRIP_PARAMS:
            if re.search(rf"[?&]{p}=", u):
                bad.append((key, u, p))
        code = segno.make(u, error="m")
        path = ART / "qr" / f"{key}.svg"
        # Quiet zone of 2 rather than the standard 4: the code sits inside its own
        # white card in the layout, which supplies the rest of the margin, and 4 here
        # wastes a third of the width on nothing.
        code.save(str(path), scale=1, border=2, dark="#111111", light="#ffffff")
        print(f"  {key:20s} v{code.version:<2d} {u}")
    if bad:
        raise SystemExit(f"tracking parameters present: {bad}")


if __name__ == "__main__":
    photos()
    qr()
    print("\ndone")

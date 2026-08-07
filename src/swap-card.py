#!/usr/bin/env python3
"""
Drops a different card into one of the three openings of the card frame, without
re-photographing the frame.

Why this exists: the frame was photographed with The Wee Wee Bush in the middle. That
card has since gone into the slab, so it currently appears twice on the wall, which is
the one visible inconsistency left. Re-shooting the whole frame to change one card is a
lot of setup for a small edit, and the new photograph would have different light.

This keeps the real frame, the real mat and the real lighting, and replaces only what is
inside one opening. The card is perspective-fitted to that opening's own corners, so it
sits at the same slight angle as its neighbours, and its exposure is matched to what it
replaced so it does not read as pasted on.

    python3 src/swap-card.py 2 path/to/new-card.jpg

Openings are numbered 1, 2, 3 from the left. Writes art/cards.jpg and keeps the previous
version alongside as art/cards.before-swap.jpg the first time it is run.
"""

import pathlib
import shutil
import sys

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARDS = ROOT / "art" / "cards.jpg"
BACKUP = ROOT / "art" / "cards.before-swap.jpg"


def openings(bgr):
    """The three mat openings, left to right, as corner quads.

    Found as the non-white regions inside the mat. Contours are filtered by area so the
    nested one that turns up inside a busy card does not count as a fourth opening.
    """
    h, w = bgr.shape[:2]
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    m = (grey < 200).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((21, 21), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Take the three largest rather than everything over a size floor. The white name bar
    # across the bottom of a card is bright enough to split that card's region in two, so
    # a threshold alone reports four openings on a frame that plainly has three.
    keep = sorted(cnts, key=cv2.contourArea, reverse=True)[:3]
    if len(keep) < 3 or cv2.contourArea(keep[-1]) < w * h * 0.02:
        sys.exit(f"could not find three card openings (found {len(cnts)} regions)")
    keep.sort(key=lambda c: cv2.boundingRect(c)[0])

    out = []
    for c in keep:
        box = cv2.boxPoints(cv2.minAreaRect(c))
        s, d = box.sum(axis=1), np.diff(box, axis=1).ravel()
        out.append(np.array([box[np.argmin(s)], box[np.argmin(d)],
                             box[np.argmax(s)], box[np.argmax(d)]], dtype="float32"))
    return out


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__.strip())
    which = int(sys.argv[1])
    card_path = pathlib.Path(sys.argv[2])
    if which not in (1, 2, 3):
        sys.exit("opening must be 1, 2 or 3")
    if not card_path.exists():
        sys.exit(f"no such file: {card_path}")

    frame = cv2.imread(str(CARDS))
    quad = openings(frame)[which - 1]
    card = cv2.imread(str(card_path))
    if card is None:
        sys.exit(f"could not read {card_path}")

    ch, cw = card.shape[:2]
    src = np.array([[0, 0], [cw, 0], [cw, ch], [0, ch]], dtype="float32")
    warped = cv2.warpPerspective(card, cv2.getPerspectiveTransform(src, quad),
                                 (frame.shape[1], frame.shape[0]), flags=cv2.INTER_CUBIC)

    mask = np.zeros(frame.shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, quad.astype(np.int32), 255)

    # Match exposure to what was there. The frame photo is not evenly lit across its
    # width, so a card pasted in at its own brightness reads as a sticker.
    old_mean = cv2.mean(frame, mask=mask)[:3]
    new_mean = cv2.mean(warped, mask=mask)[:3]
    gain = np.array([o / n if n > 1 else 1.0 for o, n in zip(old_mean, new_mean)])
    warped = np.clip(warped.astype(float) * gain, 0, 255).astype(np.uint8)
    print(f"  exposure matched: {tuple(round(v) for v in new_mean)} "
          f"-> {tuple(round(v) for v in old_mean)}")

    # Feather by a pixel or two so the join is not a hard cut against the mat bevel.
    soft = cv2.GaussianBlur(mask, (5, 5), 0).astype(float)[..., None] / 255.0
    out = (warped * soft + frame * (1 - soft)).astype(np.uint8)

    if not BACKUP.exists():
        shutil.copy(CARDS, BACKUP)
        print(f"  kept the original as {BACKUP.name}")
    cv2.imwrite(str(CARDS), out, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"  wrote {CARDS.name}, opening {which} replaced with {card_path.name}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Builds art/slab.png, the slab standing in front of the books on the right shelf.

This is a composite, not a photograph, and it is worth being precise about what that
means. Every graphic element in it is the real object:

  slab/photos/slab-label.png   the actual printed label, with Jack's orange JMW and the
                               smiley he drew on the winning design
  slab/photos/card-front.jpg   the actual card, with JMW and the inscription

Nothing is drawn from imagination. What is synthesised is only the plastic: the case
outline, its corner radius, and two glare highlights. That is the part nobody can
recover from the files, and the part that matters least, being clear plastic.

Replace this the moment there is a straight-on photograph of the real slab. Until then
it is a great deal closer to the truth than a dashed box, and at shelf scale (about
50pt tall on the wall) it is indistinguishable from one.

    python3 src/make-slab.py
"""

import pathlib

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Inches, and everything else is derived from them, so the proportions are real rather
# than whatever looked right on screen.
#
# The shell is deliberately close-fitting. A first pass used PSA's own 3.25 x 5.25 outline,
# which left a wide plastic skirt all round and read as much chunkier than the real thing.
CARD_W, CARD_H = 2.5, 3.5
SIDE = 0.16          # plastic either side of the card
TOP = 0.13
GAP = 0.10           # between label and card
BOTTOM = 0.16
DPI = 320


def load_label(path):
    """The printed label, whole.

    Earlier versions of this cropped the red away, on the assumption it was a bleed mark
    left over from printing. It is not. The red band is part of the design and belongs on
    the slab, so the file is used exactly as it is.
    """
    im = Image.open(path).convert("RGB")
    print(f"  label {im.size}, used whole")
    return im


def _order(pts):
    """Order four points tl, tr, br, bl."""
    sm, df = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(sm)], pts[np.argmin(df)],
                     pts[np.argmax(sm)], pts[np.argmax(df)]], dtype="float32")


def _edge_corners(contour, rough):
    """Recover the true corners by fitting the four straight sides and intersecting them.

    A corner vertex cannot be read off the outline directly. The card has rounded corners,
    so the outline never actually reaches the point where two sides would meet, and
    approxPolyDP puts its vertex somewhere on the curve instead, about 27px inside the
    real corner here, which dragged a wedge of concrete into the top-left of the warp.

    The straight middle of each side is unambiguous, though. Fit a line to each, intersect
    consecutive pairs, and the intersections land on the extrapolated corners whether or
    not the card is rounded, and without any dependence on where the shadow falls.
    """
    pts = contour.reshape(-1, 2).astype(float)
    lines = []
    for i in range(4):
        a, b = rough[i], rough[(i + 1) % 4]
        d = b - a
        length = np.hypot(*d)
        n = np.array([-d[1], d[0]]) / length          # unit normal to this side

        # Points near this side, taking only the middle 70% so the rounded corners and
        # the neighbouring sides are excluded from the fit.
        rel = pts - a
        along = rel @ (d / length)
        off = np.abs(rel @ n)
        keep = (off < length * 0.05) & (along > length * 0.15) & (along < length * 0.85)
        side = pts[keep]
        if len(side) < 20:
            return None
        # fitLine returns a 4x1 column, so it needs flattening before unpacking.
        vx, vy, x0, y0 = cv2.fitLine(side.astype(np.float32),
                                     cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        lines.append((float(vx), float(vy), float(x0), float(y0)))

    out = []
    for i in range(4):
        vx1, vy1, x1, y1 = lines[i - 1]
        vx2, vy2, x2, y2 = lines[i]
        den = vx1 * vy2 - vy1 * vx2
        if abs(den) < 1e-6:
            return None
        t = ((x2 - x1) * vy2 - (y2 - y1) * vx2) / den
        out.append([x1 + vx1 * t, y1 + vy1 * t])
    return _order(np.array(out, dtype="float32"))


def cut_card(path):
    """Lift the card off the concrete it was photographed on and square it up.

    The card was shot handheld, so it is both rotated and keystoned. A perspective warp
    onto a true 2.5x3.5 rectangle fixes both at once, which is why the corners have to be
    right: cropping alone cannot remove a wedge of table, only a straightened warp can.
    """
    bgr = cv2.imread(str(path))

    # Learn the concrete from the four corners of the frame, which are certainly floor,
    # then keep what is far from it in colour. Thresholding on saturation or brightness
    # instead pulled in most of the floor as well: the contour came out at 91% of the
    # frame and the warp carried a wide margin of concrete into the slab.
    k = 60
    corners = np.concatenate([bgr[:k, :k].reshape(-1, 3), bgr[:k, -k:].reshape(-1, 3),
                              bgr[-k:, :k].reshape(-1, 3), bgr[-k:, -k:].reshape(-1, 3)])
    floor = np.median(corners, axis=0)
    # 110 rather than 70: the card throws a soft shadow to its left, and at 70 that
    # shadow is "not floor" too, so the outline bulged past the real edge on that side.
    mask = (np.linalg.norm(bgr.astype(float) - floor, axis=2) > 110).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((31, 31), np.uint8))

    c = max(cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0],
            key=cv2.contourArea)
    approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
    rough = (_order(approx.reshape(-1, 2).astype("float32")) if len(approx) == 4
             else _order(cv2.boxPoints(cv2.minAreaRect(c))))

    src = _edge_corners(c, rough)
    if src is None:
        src = rough
        print("    (edge fitting failed, using the rough outline)")

    # A hair inside the fitted edge, so no single row of the card's own dark rim survives.
    centre = src.mean(axis=0)
    src = (centre + (src - centre) * 0.995).astype("float32")

    cw, ch = 769, 1077          # a real 2.5 x 3.5in card at this slab's scale
    dst = np.array([[0, 0], [cw, 0], [cw, ch], [0, ch]], dtype="float32")
    warped = cv2.warpPerspective(bgr, cv2.getPerspectiveTransform(src, dst), (cw, ch),
                                 flags=cv2.INTER_CUBIC)
    print(f"  card {bgr.shape[1]}x{bgr.shape[0]} -> {cw}x{ch}, corners "
          f"{[[int(x), int(y)] for x, y in src]}")
    return Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))


def build():
    label = load_label(ROOT / "slab" / "photos" / "slab-label.png")
    card = cut_card(ROOT / "slab" / "photos" / "card-front.jpg")

    content_w = CARD_W + 2 * SIDE
    label_h = (content_w - 2 * SIDE) * label.height / label.width
    slab_w = round(content_w * DPI)
    slab_h = round((TOP + label_h + GAP + CARD_H + BOTTOM) * DPI)

    slab = Image.new("RGBA", (slab_w, slab_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(slab)

    # The shell is clear, not white. Earlier passes filled it with near-opaque off-white,
    # which is why it read as a solid plastic brick with pictures on it, since the wall behind
    # never showed through. A low alpha plus a defined edge is what actually says acrylic:
    # the plastic is nearly invisible and you see it by its rim and its glare.
    r = round(0.06 * DPI)
    d.rounded_rectangle([0, 0, slab_w, slab_h], radius=r, fill=(246, 250, 253, 46))
    # Two rims, a lighter one just inside a darker one, which is how a moulded acrylic
    # edge catches room light along its bevel.
    d.rounded_rectangle([0, 0, slab_w, slab_h], radius=r, outline=(176, 190, 200, 210),
                        width=3)
    d.rounded_rectangle([4, 4, slab_w - 4, slab_h - 4], radius=r - 3,
                        outline=(255, 255, 255, 170), width=3)

    lw = round((content_w - 2 * SIDE) * DPI)
    lh = round(label.height * lw / label.width)
    lx, ly = (slab_w - lw) // 2, round(TOP * DPI)

    # Take the digital edge off the label so it sits with the card instead of on top of it.
    #
    # The label is a vector render and the card is a photograph, and side by side that
    # showed: high-frequency energy measured 25 on the label against 9 on the card, i.e.
    # razor-sharp type against optically soft photography. A real slab photographed once
    # would have both at the same acuity. A little blur and a little sensor grain is what
    # closes that gap; the amounts are small because the label still has to be readable.
    lab = label.resize((lw, lh), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.7))
    arr = np.asarray(lab).astype(float)
    rng = np.random.default_rng(4)
    arr += rng.normal(0, 2.4, arr.shape)
    lab = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    slab.paste(lab, (lx, ly))

    cw, ch = round(CARD_W * DPI), round(CARD_H * DPI)
    cx, cy = (slab_w - cw) // 2, ly + lh + round(GAP * DPI)
    slab.paste(card.resize((cw, ch), Image.LANCZOS), (cx, cy))
    d.rectangle([cx, cy, cx + cw, cy + ch], outline=(158, 166, 173, 255), width=2)

    SLAB_W, SLAB_H = slab_w, slab_h

    # The front sheet of acrylic, over everything that is sealed behind it.
    #
    # Without this the card was fully opaque, which read as a card lying on top of the slab
    # rather than one sealed inside it. A real slab has 3mm of plastic between your eye and
    # the card: it lifts the blacks slightly and takes a little saturation out, and that
    # tiny veil is most of what says "behind glass".
    veil = Image.new("RGBA", (slab_w, slab_h), (243, 247, 250, 16))
    face = Image.new("L", (slab_w, slab_h), 0)
    ImageDraw.Draw(face).rounded_rectangle([0, 0, slab_w, slab_h], radius=r, fill=255)
    slab = Image.alpha_composite(slab, Image.composite(
        veil, Image.new("RGBA", slab.size, (0, 0, 0, 0)), face))

    # The card is recessed in the well, so the case wall throws a hairline shadow around
    # it. Drawn as four thin edges rather than a blur, which would creep over the artwork.
    sh = ImageDraw.Draw(slab, "RGBA")
    for i, alpha in enumerate((34, 22, 12)):
        sh.rectangle([cx - i - 1, cy - i - 1, cx + cw + i, cy + ch + i],
                     outline=(70, 80, 90, alpha), width=1)

    # Glare. Two soft diagonal wedges on a separate layer so the blur does not smear the
    # card underneath. This is the only invented part of the image and it stays subtle.
    glare = Image.new("RGBA", (SLAB_W, SLAB_H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glare)
    W, H = SLAB_W, SLAB_H
    g.polygon([(W*.05, H*.16), (W*.42, H*.03), (W*.60, H*.03), (W*.05, H*.36)],
              fill=(255, 255, 255, 54))
    g.polygon([(W*.86, H*.60), (W*.95, H*.52), (W*.95, H*.88), (W*.86, H*.93)],
              fill=(255, 255, 255, 32))
    glare = glare.filter(ImageFilter.GaussianBlur(12))
    # Masked to the case outline, or the blur bleeds past the rounded corners and the
    # slab gets a soft white halo that reads as a bad cut-out.
    shape = Image.new("L", (SLAB_W, SLAB_H), 0)
    ImageDraw.Draw(shape).rounded_rectangle([0, 0, SLAB_W, SLAB_H], radius=r, fill=255)
    slab = Image.alpha_composite(slab, Image.composite(
        glare, Image.new("RGBA", slab.size, (0, 0, 0, 0)), shape))

    out = ROOT / "art" / "slab.png"
    slab.save(out)
    print(f"  wrote {out.name} {slab.size} ({out.stat().st_size//1024} KB)")


if __name__ == "__main__":
    build()

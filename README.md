# InternetWall

The single app for the iPad mounted next to the gallery wall. It draws the wall, you
tap a piece, you get its story. Leave it alone for fifteen minutes and it stops looking
like a screen.

Built for an **iPad Air 4** (A14, 1180×820pt landscape), developed on an **iPad Pro 11
M5** (1210×834pt). Those are 0.8% apart, so there is one fluid layout and no device
branching anywhere.

---

## Two rules the code never breaks

**Nothing navigates.** No `<a href>`, no `location` writes, no hash routing. Every view
is a class on `<body>`. A navigation inside Guided Access is unrecoverable without
unlocking the iPad, so references to outside things are QR codes people scan with their
own phone, never links this iPad could follow.

**Nothing is fetched.** No CDN, no web font, no analytics, no YouTube embed. The whole
app is `index.html` plus `art/` and `slab/`.

`src/verify.py` asserts both on every run.

---

## Looking at it right now

On the machine with this repo:

```
python3 serve.py
```

It prints two addresses. Open the second one on the iPad, on the same wifi. That is the
whole thing.

That is plain `http://`, so iOS will not register the service worker and it will not work
with the serving machine switched off. Fine for trying it. For the real install, read on.

---

## Getting it onto the iPad

The app being self-contained is not the same as it working with the wifi off. Without
a service worker it would still need whatever machine is serving it to be switched on,
which rather defeats a thing bolted to a wall. `sw.js` closes that gap.

**iOS only runs service workers over HTTPS or on localhost.** That drives the choice:

| How you serve it | Works offline? |
|---|---|
| GitHub Pages (HTTPS) | **yes**, and this is the one to use |
| Any HTTPS host | yes |
| A PC on the LAN over plain `http://` | no; the app runs, but the PC must stay on |

Then, on the iPad:

1. Open the page in Safari, **Share → Add to Home Screen**. This is what gets you real
   fullscreen with no Safari chrome.
2. Open it from the home screen icon, long-press bare wall, and press
   **Save all 8 clips to this iPad**. That is ~86MB and takes a few minutes. The wall,
   the stories and every photo are already saved by then; this is just the video.
3. **Settings → Display & Brightness → Auto-Lock → Never.**
4. **Settings → Accessibility → Guided Access → on.** Triple-click the side button to
   lock it to the app.
5. Turn **auto-brightness off**, then calibrate the idle level (below).

Video is not precached at install on purpose. `cache.addAll` is all-or-nothing, so one
86MB failure would throw away the entire install and the app would silently never go
offline.

---

## The one thing that cannot be built as asked

The brief for idle was *"after 15 mins it just chooses the brightness that looks most
like it's not there and turns into the wall"*.

**Safari has no screen-brightness API. No web page can dim an iPad's backlight.** That
half is not possible from inside a web app, and no amount of work here changes it.

What it does instead: at fifteen minutes it drops every piece, leaves the bare drywall,
and lays a scrim over it whose level you set once by eye. Long-press while idle, drag
until the panel stops reading as a lit screen from your chair, done. Saved to
`localStorage`, survives restarts.

Pair it with iOS auto-brightness **off**. Left on, the panel will drift away from
whatever you calibrated, by itself, at dusk.

---

## Moving things around

`PIECES` at the top of the script in `index.html` is the only thing to edit, and
**everything in it is in inches.**

```js
{ key:'carter', type:'frame', xIn:1.5, yIn:6, wIn:15.5,
  art:'art/carter.jpg', ratio:1.25, mould:'5.2%', matV:'10.4%', matH:'14%', … }
```

That matters more than it sounds. When these were percentages, a 14in picture and a 22in
shelf were both just "some fraction of the panel", so there was nothing to check either
against, and the frames ended up about a third too large next to the books. Give a piece
its real width and it lands correctly against every other piece for free.

`WALL_IN` is how much real wall the panel pretends to be, currently **64in**. Raise it
and everything shrinks together without distorting. It cannot go much below 64: row two
is two 21.65in ledges plus a 17in sign, which is 60.3in of furniture before any gaps.

Positions are inches too, converted to `vw` for both axes rather than percentages,
because a percentage is of the panel's width horizontally and its height vertically, so
a 9in book and a 9in gap would not come out the same size.

**Height is never given.** It falls out of `ratio` (the artwork's own aspect) plus the
mat and moulding widths, so a frame cannot be set to the wrong shape by hand. Mat borders
are set separately for the long and short sides (`matV` / `matH`), because they really
are different: 2in against 1.5in on an 11x14, and uniform padding made the frames an inch
too tall.

Real sizes currently encoded: 11x14 frames with an 8x10 opening at 15.5 x 12.5in outer,
IKEA MOSSLANDA ledges at 21.65in, the graphic novels at 6.7 x 8.7in, the activity book at
the smaller 5.4 x 7.4in trim, and the slab at 4.62in tall. Correct any of these and
everything else stays in proportion around it.

---

## Leaning

Drag the wall and the camera leans, up to 7 degrees, then springs back square on release.
The pieces sit proud of the wall on the z axis so they slide against it rather than with
it, which is what makes a flat panel read as having depth.

Depth is exaggerated about four times. A frame really stands an inch off a wall, which at
this scale is under two points of travel at these angles, i.e. invisible.

A drag is not a tap. Past 10px of movement the gesture becomes a look and the click that
follows it is swallowed, so a deliberate drag never opens a story. The flag that does the
swallowing is cleared when a *new* gesture starts rather than when the click arrives: a
drag ending off-screen emits no click at all, and the flag would otherwise stay armed and
eat whichever real tap came next.

Frames are placed by their **top** edge (`y`). Ledges are placed by their **bottom**
edge (`b`), so the shelf line stays where it was drilled no matter how tall whatever is
standing on it turns out to be. Swapping a placeholder for a real photo of a loaded
shelf cannot shift the shelf.

Wall colour is `--wall` at the top of the CSS, currently `#c6d1cf`. That is sampled
from the room photo and white-balanced against the ceiling and the door trim; three
separate patches of wall agreed to within one step. It is still a measurement off a
warm-lit phone photo, so treat it as a starting point. The settings panel has the
Sherwin-Williams greens-greys loaded as swatches and whatever you pick there wins.

---

## Artwork

Everything on the wall is a photograph or a publisher's cover scan. `src/build-assets.py`
crops, resizes and writes them into `art/`:

```
python3 src/build-assets.py
```

It trims the two photographed frames off the dark surface they were shot on by finding
the bright region, so `cards.jpg` and `luton.jpg` need no manual cropping. Drop a new
photo in `src/`, point the script at it, run it.

Those two are used **whole**, not dropped inside a drawn frame: a CSS moulding around a
photographed moulding reads as two frames. Everything else sits in a frame drawn in CSS,
which stays sharp at any size and matches the real frames rather than stock.

Every artifact on the wall is now a real photograph or a real cover scan. Nothing is a
placeholder and nothing is drawn from imagination.

The one composite is **`art/slab.png`**, built by `src/make-slab.py`, and it is worth
being precise about what that means. The real slab does not exist yet, so it is assembled
from two files that *are* real: `slab/photos/slab-label.png`, the actual printed label
with Jack's orange initials on it, and `slab/photos/card-front.jpg`, the actual card. Only
the plastic is synthetic, and the plastic is the part no file could have supplied. Replace
it with a straight-on photograph the moment there is a real one to photograph.

Two things will want updating when the physical wall changes, and neither needs the
frame photographed again:

**The middle card.** `art/cards.jpg` shows The Wee Wee Bush in the middle slot. That card
has gone into the slab, so it currently appears twice on the wall. Once you know what
replaced it, one command fixes it:

```
python3 src/swap-card.py 2 path/to/the-new-card.jpg
```

Openings are numbered 1, 2, 3 from the left. It keeps the real frame, the real mat and
the real lighting, fits the new card to that opening's own corners so it sits at the same
slight angle as its neighbours, and matches its exposure to what it replaced. Round-tripped
against the existing card it comes back within JPEG re-encode noise. The original is kept
as `art/cards.before-swap.jpg`.

**The slab.** `art/slab.png` once the real one exists, at which point it is a photograph
and `src/make-slab.py` is no longer needed.

Note this machine has no outbound network. The egress proxy refuses every host,
including `example.com`, so nothing can be fetched here. A square-on photo of the real
object beats a scrape anyway.

---

## QR codes

The iPad cannot follow a link, and nobody is going to retype a timestamped YouTube URL
off a wall. Every outbound reference is a QR code instead, generated into `art/qr/` by
the same script from the `LINKS` table in it, so a code can never drift out of step
with the caption printed beside it.

Two details that matter:

- Share URLs carry a tracking parameter (`?si=` / `?is=`) identifying the account the
  link was copied from. Those are stripped, and `STRIP_PARAMS` fails the build if one
  creeps back in.
- They use the `youtu.be` short form. Fewer characters means a lower QR version, which
  means chunkier modules, which is what actually decides whether a phone reads a 3cm
  code off a screen at arm's length. All fifteen come out at version 3.

---

## Scripts

| | |
|---|---|
| `python3 serve.py` | serve it to the iPad over wifi |
| `python3 src/build-assets.py` | rebuild every image in `art/` and every QR code |
| `python3 src/make-slab.py` | rebuild the slab composite |
| `python3 src/swap-card.py N card.jpg` | put a different card in opening N of the card frame |
| `python3 src/verify.py [outdir]` | drives settings, idle, the saga, the no-navigation and no-fetch rules |
| `python3 src/shoot.py page index.html out.png` | screenshot at iPad Air 4 landscape |
| `python3 src/make-wall-texture.py` | rebuild the drywall tile |

Two things the local browser cannot check, both of which need the actual iPad:

- **Video.** The bundled Chromium ships without H.264 or AAC, and the clips are `avc1`,
  so every clip errors on load here. Safari decodes H.264 in hardware.
- **Memory.** Only one `<video>` is ever alive: built on tap, torn down on close.
  Eight at once is fine on the M5 and a problem on the A14, which is exactly the class
  of bug the development iPad hides.

---

## Where the saga came from

The eleven chapters, their dates, scores, comment counts, body copy and pull quotes are
reused **verbatim** from `viaate/slab`. That copy was already written and already good.
The clips and photos are copied into `slab/`.

Two changes for this context. The play-button chapter's YouTube facade is gone, because
there is no network to load it from. And every "watch Jack react" link is a QR code
instead, because of the no-navigation rule.

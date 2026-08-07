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
unlocking the iPad, so references to outside things are *printed as text you type in*
rather than linked.

**Nothing is fetched.** No CDN, no web font, no analytics, no YouTube embed. The whole
app is `index.html` plus `art/` and `slab/`.

`src/verify.py` asserts both on every run.

---

## Getting it onto the iPad

The app being self-contained is not the same as it working with the wifi off — without
a service worker it would still need whatever machine is serving it to be switched on,
which rather defeats a thing bolted to a wall. `sw.js` closes that gap.

**iOS only runs service workers over HTTPS or on localhost.** That drives the choice:

| How you serve it | Works offline? |
|---|---|
| GitHub Pages (HTTPS) | **yes** — this is the one to use |
| Any HTTPS host | yes |
| A PC on the LAN over plain `http://` | no — app runs, but the PC must stay on |

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

`PIECES` at the top of the script in `index.html` is the only thing to edit.

```js
{ key:'carter', type:'frame', x:'3.5%', y:'10.2%', w:'24%',
  art:'art/carter.jpg', ratio:1.25, mould:'5.2%', mat:'11%', … }
```

`x` / `y` / `w` are percentages of the panel. **Height is never given** — it falls out
of `ratio` (the artwork's own aspect) plus the mat and moulding widths, so a frame
cannot be set to the wrong shape by hand.

Frames are placed by their **top** edge (`y`). Ledges are placed by their **bottom**
edge (`b`), so the shelf line stays where it was drilled no matter how tall whatever is
standing on it turns out to be — swapping a placeholder for a real photo of a loaded
shelf cannot shift the shelf.

Wall colour is `--wall` at the top of the CSS, currently `#c6d1cf`. That is sampled
from the room photo and white-balanced against the ceiling and the door trim; three
separate patches of wall agreed to within one step. It is still a measurement off a
warm-lit phone photo, so treat it as a starting point — the settings panel has the
Sherwin-Williams greens-greys loaded as swatches and whatever you pick there wins.

---

## Artwork still needed

Three photographs are irreplaceable and already in: `carter.jpg`, `jen.jpg`,
`shrek.jpg`.

Four artifacts are still placeholders. **This machine has no outbound network** — the
egress proxy refuses every host, including `example.com` — so nothing can be downloaded
here, and a straight-on photo of the real object beats a scrape anyway.

| File | What to shoot |
|---|---|
| `art/luton.jpg` | the framed tarp, square on |
| `art/cards.jpg` | the three-card frame, square on |
| `art/books-left.jpg` | the left ledge, loaded, from the front |
| `art/books-right.jpg` | the right ledge with the slab in front of the books |

Shoot square-on, not at an angle, in daylight or under a white bulb, filling the frame,
long edge 1600px or more. Drop each in at that path — no code change, no rebuild.

Until then each shows a plainly provisional placeholder. That is deliberate: a bad fake
is worse than an honest gap, and nothing on this wall pretends to be something it is not.

---

## Scripts

| | |
|---|---|
| `python3 src/verify.py [outdir]` | drives settings, idle, the saga, the no-navigation and no-fetch rules |
| `python3 src/shoot.py page index.html out.png` | screenshot at iPad Air 4 landscape |
| `python3 src/make-wall-texture.py` | rebuild the drywall tile |

Two things the local browser cannot check, both of which need the actual iPad:

- **Video.** The bundled Chromium ships without H.264 or AAC, and the clips are `avc1`,
  so every clip errors on load here. Safari decodes H.264 in hardware.
- **Memory.** Only one `<video>` is ever alive — built on tap, torn down on close.
  Eight at once is fine on the M5 and a problem on the A14, which is exactly the class
  of bug the development iPad hides.

---

## Where the saga came from

The eleven chapters, their dates, scores, comment counts, body copy and pull quotes are
reused **verbatim** from `viaate/slab`. That copy was already written and already good.
The clips and photos are copied into `slab/`.

Two changes for this context. The play-button chapter's YouTube facade is gone, because
there is no network to load it from. And every "watch Jack react" link is printed as
text instead of linked, because of the no-navigation rule.

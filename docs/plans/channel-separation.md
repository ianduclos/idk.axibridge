# Colour separation — design notes

Shipped 2026-08-17. This document is the *why*, kept because most of what
follows is a judgment call that could reasonably have gone the other way, and
the point of writing it down is that changing your mind later should cost an
afternoon rather than an archaeology session.

## The problem

axibridge could already *plot* in several colours — pen passes, nib-offset
registration, the guided swap queue — but nothing in it could produce work that
wanted several colours. Every image-driven generator saw exactly one thing:
luminance. So every colour decision was manual: duplicate the layer, hand-edit
until it looks like the cyan bits, repeat, hope.

The feature is one button that turns an image into *plates*.

## The one rule everything else rests on

**Every plate is returned in `grayscale`'s polarity: rows in [0, 1] where
0 means draw hardest.**

`asset_store.grayscale` has always returned 0 = black, and every consumer is
built on "low value, press harder" — `_tone_lut`, brightness/contrast/gamma/
levels, `ImageSampler`, `image_threshold`'s marching squares, `linedraw`'s own
tone pass. Keeping colour plates in that same convention is what made this a
four-line change at each decode site instead of a fork through sixteen
generators.

So an *ink* plate comes back as `1 - ink`: lots of cyan reads as dark, which
reads as draw-hard. Invert that anywhere and every image generator inverts with
it, and nothing else in the suite would notice.

## Where the pieces live

| | |
|---|---|
| The channel model, the maths, `sample_rows()` | `axibridge/channels.py` |
| The decode + its cache | `asset_store.channel()` in `axibridge/assets.py` |
| `channel` / `black_generation` params | `sources/_pixelgen.py` (`ImageBaseParams`) and `sources/image_threshold.py` |
| `tone_from` / `tone_to` / `tone_rescale` | `sources/_pixelgen.py` (`PixelGenParams`, inside `_tone_lut`) |
| The stack op | `Session.add_separation_stack` |
| The endpoint | `POST /api/layers/separate` |
| The UI | `#separate-row` in `static/js/compose.js` |
| Tests | `tests/test_separation.py`, plus three in `tests/test_acceptance_ui.py` |

## Decisions, and how to reverse each one

### 1. GCR in the subtract form, not the divide form

**Chosen:** `k = black_generation × (1 − max(r,g,b))`, then `c = (1 − r) − k`.

**The textbook alternative** is the divide form, `(1 − r − k) / (1 − k)`, which
is what a prepress RIP does. It re-saturates each plate after pulling K out, so
plates stay dense.

Subtract was chosen because a plotter is not a press. The divide form assumes
transparent process inks laid in perfect register on a press that does not care
how much ink it uses; here every extra unit of density is another minute of a
felt tip dragging across paper. Measured on a saturated dark blue (0, 0, 0.5) at
full black generation: subtract gives C=M=0.5, divide gives C=M=1.0 — twice the
ink for the same picture. Subtract also needs no guard as `k` approaches 1.

Both forms hit the endpoints identically, which is what the tests actually pin.

**To flip:** one expression in `channels.cmyk_plate`. Add a `1 - k < 1e-6`
guard. `test_full_black_generation_hands_the_darks_to_k` and its zero-BG twin
still hold; the mid-range values move, so nothing else needs rewriting.

### 2. RGB plates are the raw plane, not its complement

**Chosen:** the `r` plate returns `r` — bright red areas come back light, so
they draw little. This is the Photoshop reading of "the red channel": that plane
shown as its own greyscale image.

**The alternative** is `1 - r`, treating it like a red-filtered black-and-white
photograph, where *little* red reads dark.

There is no physically correct answer, because RGB is additive light and ink is
subtractive — which is exactly why CMY exists and why RGB plates are an analysis
view rather than an ink plate. Raw won because it makes the plates match what
any image editor shows for the same channel, and because it buys a free
correctness check: at `black_generation = 0` the CMY plates come out *exactly*
equal to the R/G/B planes (`1 − (1 − r) = r`), which `test_cmy_at_zero_black_
generation_equals_rgb` pins. Flipping RGB breaks that identity, so if you do it,
delete that test deliberately rather than discovering it.

**To flip:** the `PLANE_CHANNELS` branch in `asset_store.channel`.

### 3. Tone bands pass through by default — but it is a checkbox, not a decision

`tone_from` / `tone_to` clip the darkness range; `tone_rescale` decides what
happens to what survives.

- **Off (default):** the window passes through. Abutting windows partition the
  range *exactly*, so a set of tonal plates lays back the ink of the unwindowed
  drawing and no more. This is what makes them stackable.
- **On:** the window is stretched to full contrast, the graphic-arts
  convention, so a narrow band reads strongly on its own. Costs additivity —
  three stretched bands lay roughly three times the ink.

This one is a param rather than a code decision **because Ian named it as the
thing he would want to change**, and the cheapest possible way to make something
changeable is to not make it a decision at all.

The windows are **half-open**, `[lo, hi)`, with the top of the range closed. Two
abutting plates both claiming the shared boundary means a double strike of ink
on the paper, which is a real defect and not a rounding detail; closing the top
keeps the very darkest tones from falling out of every band.

**Where it does not reach:** `tone_*` lives on `PixelGenParams`, so it covers
the ten sources whose tone runs through `_pixelgen._tone_lut` (dots, halftone,
linescan, longwave, margins, misremembered, polyspiral, squiggle_lr, subline,
waves). The five with their own tone paths — lineart_hatch, lineart_edges,
linedraw, fast_marching_topo, fast_marching_contours — and image_threshold do
not get it, and the field correctly never appears on their forms.
`test_tone_window_absent_where_it_would_not_work` pins that, so the asymmetry
is stated rather than latent. lineart_hatch already has richer banding of its
own (`band_from`/`band_to`, which also drives streamline spacing) plus
`add_lineart_stack`, which is why the generic pair had to take a different
name.

### 4. Three overlapping tone windows — flagged, not resolved

`PixelGenParams` now carries three mechanisms that all sound like "window my
tones":

| | domain | outside the window | inside |
|---|---|---|---|
| `black_point` / `white_point` | input luma, pre-gamma | clipped | rescaled |
| `min_brightness` / `max_brightness` | output byte, post-gamma | clamped | untouched |
| `tone_from` / `tone_to` | final darkness | **zeroed** | passed or rescaled |

They differ in domain and in what they do to what falls outside, so they are not
redundant *in effect* — only `tone_*` actually removes ink rather than
compressing it, which is the whole point of a plate. But they are close in
*purpose*, and the Image-processing group is now eight knobs deep. Worth a
consolidation pass at some point; deliberately not done as a side effect of
this round.

### 5. Plates are independent layers, with no grouping field

A plate is an ordinary `CanvasLayer` with real generator provenance. Its own
effect stack, pen, transform, occluder flags, tween behaviour, regenerate. That
is not a limitation of the design, it *is* the design: you can hatch the cyan
plate and leave the others alone, or nudge one plate off register by hand, or
animate one, because nothing about a plate is special.

Ian wants separations to group by default once first-class layer grouping
exists (parked as timeline-v2 Q1c). The preparation that needed is **zero model
change**: `add_separation_stack` is the single place a separation is born and it
already knows the whole set, so the day grouping lands, it is one wrapper call
in that method. Adding a `separation_id` now would be a save-format change that
pre-empts an architecture question, which CLAUDE.md says not to resolve
implicitly.

### 6. A plate carries a params override, not a channel

This is the choice that paid off most. Because a plate is
`{name, generator?, params, pen_id}` rather than `{channel, pen_id}`:

- colour separation (`{"channel": "c"}`) and tonal separation
  (`{"tone_from": 0, "tone_to": 0.34}`) are the *same operation*, not two;
- a plate can name its **own generator** — cyan as halftone dots, magenta as
  squiggles, black as traced edges. Ian's idea, and it is the Oehlen regime
  collision along the colour axis instead of the spatial one.

Params carry across a generator switch by intersection with the target's
declared fields, so the merge can never build an invalid params dict; the rest
fall to that generator's defaults.

### 7. Misregistration is a transform nudge, nothing more

`misregistration_mm` composes a small seeded offset into each plate's affine —
uniform over a disc of that radius, seeded per `(seed, plate index)`. It is
undoable, hand-editable afterwards, and zero is exact identity. Offset
printing's charm is that the plates never land quite on top of one another, and
this buys that without inventing a concept.

**Not done, wants a bench test first:** per-plate **screen angles**. Real CMYK
printing rotates each screen (C 15°, M 75°, Y 0°, K 45°) to kill moiré, and
separating with `halftone` at one angle almost certainly *will* moiré. It is
conditional magic — only generators with an angle param can honour it — so it
waits until Ian has seen the first prints and can say whether the moiré is a
problem or a feature.

## Performance

`luma` delegates to `grayscale()`, so the default path is not merely equivalent
to what it was, it is the same call on the same cache. RGB planes and CMY at
`black_generation = 0` take an `Image.split()` fast path at C speed. Only real
GCR walks the pixels in Python — the same order of work `grayscale` already
does, and `gencache` memoises `generate()` above it, so a plate is decoded once
per param change rather than per resolve.

Cached in `AssetStore._channel`, a dict parallel to `_gray` rather than an
extended key on it, so the hot unmodified luma path's key shape is untouched.
`black_generation` is normalised out of the key for RGB plates, which cannot be
moved by it.

## The extension seam

Ian roadmapped three follow-ons, and the shape of `channels.py` is what should
keep each of them from being a rewrite. Each is a new plate definition plus an
enum entry, with **no generator, no session and no UI change**:

- **Spot-colour plates** — pick a hex, the plate is per-pixel proximity to it.
  What actually separates for a drawer of three arbitrary felt tips rather than
  four theoretical inks. The real design work is the metric: RGB euclidean
  distance lies about perceived colour, Lab does not.
- **HSV / Lab opponent plates** — a hue plate is a strange picture nobody
  prints. Nearly free now that RGB decode exists.
- **N-pen least-squares separation** — pick 3–5 real pens from the library and
  solve the subtractive mix per pixel for the closest match to the photograph.
  The end of Cohen's colour logic: a palette chosen by what you own rather than
  by what a printer assumes. Ambitious enough to be its own project; it needs
  the plate list to become dynamic (the enum stops being a fixed `Literal`),
  which is the one part of the current shape it would genuinely strain.

## Known gaps

- The `show_map` canvas ghost draws the full-colour image, not the plate's own
  channel — it is rendered client-side from the asset (`main.js mapGhosts()`).
  Acceptable: the ghost exists to place the layer, and all plates share one
  placement.
- Nothing is hardware-verified. The overprint colour of real transparent felt
  tips is the actual deliverable here and no test can judge it.

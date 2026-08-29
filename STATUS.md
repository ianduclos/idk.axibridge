---
project: idk.axibridge
state: active
updated: 2026-08-22
machine: mac+pi
summary: Pass 4's A1 (time as a param) is built and green on the branch feat/time-as-a-param — a declared time axis, ProcessModule, a trajectory cache, the venation growth generator, a watch/scrub popup and Rehearse — reviewed clean but NOT merged and never once on paper.
next:
  - "Decide what happens to feat/time-as-a-param (12 commits, 21f4ddc..9727323, suite 1080 -> 1118, final review clean). Nothing is pushed or merged — that call is yours"
  - "Then the bench work in HANDOFF.md's top entry, which is the point of the whole round: watch a venation layer play, scrub it, Rehearse it, and PLOT one. Continuous growth lines should plot unusually cleanly and nothing here has touched paper"
  - "The A1.5 question the round exists to make answerable: now that there is something to watch, does poking a running process want to be direct manipulation or a recorded score? It cannot be answered from a desk"
  - "A2 (the homeostat) is now unblocked and is the natural next build; docs/plans/time-as-a-param.md sketches what it needs from A1 and what it deliberately leaves open"
  - "Still open from before: the cymatic fill has no ink on paper either, colour separation's CHECKME.md 2026-08-17 section, bench/hardware eye-checks back to 2026-07-13, and the multi-pen swap queue has never touched a real AxiDraw"
handoff_for: ian
---

# idk.axibridge — status

**Session 2026-08-21/22 (Opus 5): pass 4's A1 — time as a param — built by a
subagent fleet on a branch, reviewed clean, unmerged.**

Twelve commits on `feat/time-as-a-param`, suite 1080 -> 1118. Design first
(`docs/plans/time-as-a-param.md`), then a phased plan
(`…-IMPLEMENTATION.md`), then seven tasks each with its own implementer and
reviewer. The full account, including what the design got wrong, is
`docs/plans/time-as-a-param-RESULTS.md`.

**What shipped.** A generator can declare which param is its **time axis**;
the master timeline scrubs it. `ProcessModule` is a base for generators that
unfold — `run()` yields the marks added at each step — and `generate()` stays
a pure function of params, so the memo, tweening, undo, estimates and the
plotter all keep working. A **trajectory cache** runs the whole process once
and slices it, so scrubbing costs a prefix concatenation rather than a re-run.
`venation` (space-colonisation growth) is the first real process. A **popup**
plays and scrubs any layer with a time axis, driving the existing
`/api/generators/preview` — no new endpoint. **Rehearse** stamps several
moments of a process onto one sheet in a single undo step.

**Two things the design did not anticipate, both worth knowing.** The
master-timeline binding largely already existed: `_effective_gen_params` was
already folding `master_t` into a `frame` axis, so A1 was mostly a
generalisation of one method rather than new plumbing. And because the
trajectory cache key deliberately **excludes** the time axis, Rehearse's N
moments all hit ONE cached run — which is why Rehearse ended up as N ordinary
generator layers rather than the tween-sweep-explode route the design doc
specified. That route could not have delivered the single undo step the doc
itself demanded, since each of those methods checkpoints independently.

**The plan's own test code was the main source of defects.** Seven were found
because every implementer was told to check whether a test would genuinely
fail for the reason its step predicted — two broken test imports, a clamp that
ran after an int cast, a vacuous cache test, a selector that never matched the
element the code created, popup CSS classes that never existed, dead telemetry
markup. Prose saying "run it and watch it fail" is not the same as having
watched it fail.

**Two performance defects were mine, not the implementers'.** The venation
loop was ~918M distance computations (~3 minutes) and lands on the *first*
`generate()`, because a trajectory always runs to its declared bound.
Vectorising fixed the constant factor but not the growth: at `kill`'s declared
minimum the node count ran away to 92k and ~7 GB. Final: the pathological case
is 6.18 s / 465 MB, the default 0.108 s. Separately the trajectory cache could
evict the entry it had just inserted, recomputing forever at a zero hit rate —
found by a reviewer comparing against `gencache`, which has guarded that for
years.

**Nothing has touched paper, and the popup has never been driven by hand** —
only headless. HANDOFF.md's top entry is the bench work.

---

# idk.axibridge — status

**Session 2026-08-21 (Opus 5): the cymatic fill — pass 4's B2, shipped.**

Five commits, suite 1049 → 1075. The first item of idea pass 4 to be built,
taken out of Round 1 order because it was the one Ian wanted.

**Eigenfunction fill** (`e3cca09`) fills a closed shape with the **nodal
lines of its own vibration** — the lines where sand collects on a vibrating
surface. The point of it, and the reason it is an effect rather than a
generator: the pattern is not laid over the shape, it is *produced by* the
boundary, so every silhouette gives a different figure and a hole is a real
boundary that the pattern reorganises around. One control (Mode) changes
density **and** character together, which hatch spacing cannot do.

- **What it is, precisely:** a clamped membrane — a drumhead, second-order
  Dirichlet Laplacian. NOT a free Chladni plate, which is fourth-order and
  biharmonic and a genuinely harder problem. The module docstring says so
  rather than claiming a physics it does not solve.
- **Mix is signed on purpose.** A symmetric shape has *repeated* frequencies,
  and any combination of the modes sharing one is also a mode — physically why
  a square gives stars, crosses and flowers rather than one figure. −1 and +1
  are `u1 − u2` and `u1 + u2`; a square shows the straight line at 0 and the
  two diagonals at the ends.
- **Two things the idea doc did not anticipate.** A degenerate group needs a
  *canonical* basis or ARPACK's arbitrary choice makes Mix = 0 an accidental
  superposition and shifts the knob's meaning whenever the boundary is nudged;
  it is settled by **least nodal length** (quartimax, the textbook answer, was
  tried first — it maximises concentration, which is not the same question as
  which picture a pen would rather draw). And the field has to be **held two
  cells past the boundary** before contouring: zeroing the outside instead
  puts a contour crossing wherever a negative nodal domain meets the edge,
  i.e. a traced line running along the outline itself.
- **It shipped sparse, and that was wrong.** The first version drew only the
  nodal set — which Courant's theorem caps at n curves for the n-th mode, so
  it could only ever be a dozen stubby strokes with a great deal of white
  between them. Ian looked at it and said it felt boring; on his shape it was
  2 strokes and 185 mm of ink, and it read as a diagram. Every *other* level
  set of the same mode is equally a product of the boundary and they nest into
  long continuous closed curves, so `levels` + `level_bias` turn a partition
  into a fill (same shape, new defaults: 20 strokes, 1815 mm) and hand density
  its own control, which gives Mode back to character. `field = sand` contours
  |u| instead — ink where the surface is *still*, which is what sand on a real
  plate does — and `spread` rings the shape across a band of modes rather than
  holding one. Two artefacts fell out of that round: non-zero levels
  staircasing along the outline (fixed by a sub-cell blur), and then the blur
  making contours touch the lattice edge, where a contour that fails to close
  is **dropped in silence** — `levels=1` drew nothing at all until the padding
  ring was forced back to zero.
- **Image density** is the one addition beyond the idea doc: an image weighs
  the membrane, dark is heavy is slow, so lines bunch and low modes localise
  where the picture is dense.
- **The solve is cached whole**, with the mode count bucketed, so the first
  drag of the Mode slider pays for it (~80 ms on a 120 mm pentagon, ~7 s for a
  bed-sized shape at mode 200) and every step after is ~10 ms. That also
  answers ROADMAP's open question about eigensolve cost, which is now removed
  from the file.
- Two supporting changes: `axibridge/marching.py` (`bd48239`) now owns the
  marching-squares tracer that `image_threshold` used to keep private — an
  image contour and a nodal line are the same problem once the field is on a
  lattice — and `scipy` is finally a **declared** dependency rather than a
  transitive one through vpype, the same fix `fonttools` got on 2026-08-13.

Tests are analytic rather than golden: the closed-form rectangle spectrum
(0.01–0.1 % error), Courant's nodal-domain bound, and a square's degenerate
pairs equal to 1e-6 — that last one is what caught a rasteriser bug where a
horizontal boundary edge lying exactly on a scanline read as interior.

**No ink on paper, and it has never been driven in the browser** — verified
through the same API the UI calls (effect preview, PATCH, resolve, stats,
undo) and rendered to PNG contact sheets. HANDOFF.md's top entry is the
eye-check.

---

# idk.axibridge — status

**Session 2026-08-17/18 (Opus 5): colour separation, seeds everywhere, HSL,
then idea pass 4.**

Seven commits, suite 990 → 1048. The last two are documentation only — no code
changed after the HSL round. ROADMAP.md was also pruned to open work only
at the top of the session — shipped items now leave the file rather than
accumulating as struck-through history (`git log` and STATUS keep that), which
took it from 1214 lines to ~330.

**Colour separation** (`a8c4751`, `81e3280`) closes the roadmap's long-standing
"CMYK / greyscale separation" item. axibridge could already *plot* in several
colours — pen passes, nib-offset registration, the guided swap queue — but
nothing in it could produce work that wanted several colours, because every
image generator saw exactly one thing: luminance.

- **The polarity contract is what made it small.** Every plate returns in
  `asset_store.grayscale`'s convention (rows in [0,1], 0 = draw hardest), so
  `_tone_lut`, the brightness/contrast/gamma stack, `ImageSampler` and
  `image_threshold`'s marching squares need not know a channel exists. 16
  generators gained channel selection from four one-line edits.
- **`luma` delegates to `grayscale()`** rather than being reimplemented, so the
  default path is byte-identical by identity, not by agreement — the existing
  990-test suite passing unchanged is the evidence.
- `black_generation` 0..1 moves the achromatic component between CMY and K.
  At 0 the CMY plates are *exactly* the RGB planes and the K plate is empty:
  both correct, both pinned as tests, and the UI says the second one out loud.
- **A plate carries a params override, not a channel.** That one choice makes
  colour and tonal separation the same operation, and lets a plate name its
  own generator — cyan as halftone dots, magenta as squiggles. Ian's idea, and
  the best structural call of the round.
- **Plates are plain `CanvasLayer`s** with real generator provenance: own
  effect stack, pen, transform, occluder flags, tween behaviour. Nothing links
  them, which is the point — the button only creates four normal layers
  atomically. Grouping-by-default is prepared for (one wrapper call in
  `add_separation_stack`) without pre-empting the parked grouping question.
- Two real bugs the tests caught: a tuple seed for `random.Random` (invalid in
  3.13), and abutting tone windows both claiming the shared boundary — windows
  are half-open now, so tonal plates partition the range exactly.
- `docs/plans/channel-separation.md` carries a **decision table**: every
  judgment call, its alternative, and the one-line change that reverses it.
  Ian asked for this specifically so changing his mind later costs an
  afternoon rather than an excavation.

**Seeds** (`77ef845`), from Ian noticing that many modules still started at 0.
The July round had put the roll in exactly one place — `renderGenForm` — so it
only covered the Compose generator picker. Effects never rolled at all (two
`freehand` layers wobbled identically), and neither did `add_lineart_stack`,
the new separation stack, or any scripted `/api/layers/generate`. Now one rule
each side (`rollSeed` in JS, `Session._rolled_seed` in Python): an **integer**
field named exactly `seed`. `fast_marching_topo`'s `seed_x`/`seed_y` are
wavefront *positions* — floats — and rolling them would move the picture
rather than vary its texture, which is why the rule is that narrow.

**HSL plates** (`004ca71`), asked for as "just for fun", and the first real
exercise of the extension seam — three plate definitions plus a UI mode, no
generator, session or endpoint change. It also caught a small dishonesty: the
docs named a `CHANNEL_DECODERS` dispatch that was actually inline branching,
so that got built properly rather than gaining a third special case. What the
three are worth: **saturation** is genuinely useful (ink only where the image
is colourful), **lightness** is a different greyscale from luma (even-handed
about colour, where luma knows blue is dark and yellow bright), and **hue** is
the strange one, with an unavoidable seam through every red because a circle
does not flatten onto a line. The trap designed around: hue is undefined
without saturation and conventionally reported as 0 — red — so a greyscale
photo would have separated into a solid black rectangle. Achromatic pixels
return blank.

**One non-event worth recording**: Ian asked for one-click CMYK/RGB layer
generation, which was already what the ⌗ Separate row did — his browser tab
predated the rebuild. Diagnosed rather than rebuilt (the running server
answered the new endpoint with 400, not 404, so it was current); no second
path to the same thing was added.

**Idea pass 4** (`9eaf476`, `40cf3ea`) — `docs/IDEAS-pass4.md` plus a ROADMAP
section, from a long brainstorm. Passes 1–3 all asked *what should the marks
look like?*; this one starts from a diagnosis instead — computational art gives
itself away through seven properties (uniform rules, no history, no cost, one
global state…) and underneath all seven is that **it has nothing at stake**.
Two halves: give the process something to lose (cybernetic loops, where Ashby's
homeostat supplies the *reason* Oehlen's regime collision always lacked), and
let the field carry the structure (geodesics, eigenfunction fill, hachures,
stripe patterns). Plus an adjacent blending axis — optimal transport, where the
property that matters is that **a linear blend crossfades while OT makes mass
travel**, and with no opacity available travel is the only interpolation a pen
can draw.

The build order turns on one dependency: only the homeostat and the seam need
the time-as-a-param substrate, so everything field-derived and the whole
blending axis can land first without blocking anything. A first draft of the
roadmap dropped three items (Pask's habituation, the descent/pentimento idea,
Beer's algedonic marks) — Ian caught it and they were restored. The second was
the costly one: diffusion's trajectory and pass 1's long-open rehearsal idea
are the same thing, and A1 ships it for every time-based generator at once,
which is a second argument for the substrate nearly as strong as the first.

Nothing is started. `docs/IDEAS-pass4.md` carries a "Where to start" section
with the recommendation and the two A1 design risks worth settling first.

**Conceptual material was harvested to the vault** the same day — 13 atomic
notes staged in `llm/proposed/` (the seven-properties diagnosis, optimal
transport and barycenters, prediction error, four cybernetics notes, hachures,
eigenfunction nodal lines, three field-derived line notes) plus CLIPasso and
diffvg bookmarks. Committed there separately; awaiting promotion in a vault
session.

**Nothing here has touched paper.** The acceptance tests drive the real UI end
to end (upload → separate → four named plates → one undo removes all four),
but what two transparent felt tips do when they overprint is the actual
deliverable and no test can judge it.

---

**Session 2026-08-13 (Sonnet 5): filled-outline text generator, then two orientation bugs found and fixed.**

Five commits, suite 947 → 990. Two pieces of work, the second triggered by
Ian testing the first.

**`text_fill` — real font outlines as closed, fillable shapes**, alongside
the existing stroke-only `text`. Shipped in three phases:
1. **Geometry core** (`b1559e1`): `axibridge/sources/_fontglyph.py` — shared
   glyph-outline machinery (font loading, variable-axis instancing, TrueType/
   CFF contour flattening, composite-glyph decomposition) used by both `text`
   (relocated onto it, no behavior change) and the new module. Overlap
   resolution runs through skia-pathops when installed (optional, same
   scikit-fmm-style accelerator pattern) — Recursive's own glyphs turned out
   to need it (a rings-count mismatch with/without confirmed this empirically,
   not hypothetically). One bundled font: Recursive (OFL variable, weight/
   slant/mono/casual sliders, each a no-op on a font lacking that axis).
2. **System-font discovery** (`fcec806`): `axibridge/system_fonts.py` scans
   macOS/Linux font directories (never raises; empty on the Pi, which is
   correct, not broken) so real Helvetica/Arial/Times New Roman render where
   actually installed — they're proprietary and can't be bundled. 1113 faces
   found on this Mac in ~0.3s. New `GET /api/fonts`, folded into `/api/state`
   too (mirrors how image assets already hydrate).
3. **Drag-in upload** (`a86c826`): fonts share the existing image asset
   store rather than a parallel one (its persistence/versioning were already
   blob-agnostic) — `AssetStore` gained no "kind" tag at all, just a second
   decode-as-validation accessor (`font_label`, fontTools instead of PIL).
   Found and fixed a latent bug this surfaced: `info()` assumed a bad decode
   always returns `None`, but it actually raises — harmless before because
   upload always rolled back synchronously, not harmless once fonts
   legitimately share the store. Also caught a real cache-correctness bug
   while wiring resolution: re-uploading a different font under the same
   filename would have silently kept serving stale glyph instances.

**Then Ian reported it "renders sideways in portrait"** — reproduced
identically against the *original* `text` module, so not a text_fill
regression. Two related but distinct bugs, both closed same session:

- **`c13abb4`** — `Session._placement_transform` only ever corrected a
  `orientation="geometry"` layer's rotation *at creation*. Toggle the view
  afterwards and the layer just sat there un-rotated. New
  `Session.set_view()` retroactively re-applies the same quarter-turn (or its
  inverse) to every live layer's existing transform — exact round-trip, no
  drift, manual Placement edits preserved. The backend fix alone wasn't
  enough: the frontend was discarding the corrected response and never
  refetching resolved geometry, so the canvas kept drawing the old transform
  even after the API returned the right one.
- **`e6671f3`** — same root cause, different code path: baking a grid sheet
  (e.g. 3×3) in portrait put frames in landscape reading order.
  `_grid_place`'s frame-index → cell mapping was pure machine-frame divmod
  with no idea the portrait display map exists. Fixed so cols/rows mean
  "as you see them" in either view.

Both fixes are hand-derived, numerically verified (a git-stash spot check
confirmed the new regression tests fail on the old code and pass on the
new), and the layer-orientation fix was checked live in the browser end to
end. `tests/test_orientation.py` had a real coverage gap the investigation
found along the way — `text_fill` and `flowfield` were both silently absent
from the only test that exercises actual rotation behavior — now closed.

---

**Session 2026-08-11 continued (Fable 5 orchestrating Sonnet/Opus): the E-batch, timeline v2, and the staging/plot rework.**

~15 commits, suite 843 → 947 passed. Continues straight from the previous
wrapup's "new batch starting" entry — that batch is now COMPLETE.

- **E-batch** (all bench-checked asks from Ian): schematic line width setting;
  Settings menu owns Restart server; motion params moved under the paper
  guide; live generator param editing with coalesced undo; keyframe sublayers
  share collapse/scroll state across an A/B switch; render popup gained
  palindrome, higher-res zoomable renders, and GIF/MP4 export.
- **`docs/plans/timeline-v2.md`** (Opus design doc, Ian ruled on Q1-Q7 plus
  second rulings §2b/§2c plus a plot-flow ruling) is the round's contract and
  reads as its own record — start there for the reasoning behind any of the
  below.
- **Chains**: A>B>C>D collapses into ONE tween layer (keys capped at 24),
  each segment carries its own easing (pingpong stays a layer-global),
  endpoints snap for seed fidelity, and endpoints can be added/removed/
  reordered with a full cascade. Chain UI: a keyframe list plus right-click
  Copy/Paste state; per-param copy/paste was scoped out and parked in
  ROADMAP.
- **Bottom timeline bar**: auto-hides, frame steppers, checkpoint jumps, a
  popup button; the slider snaps to the frame grid (⇧ escapes the snap),
  ticks mark cached frames, and the active range shades.
- **Popup fixes**, including the ffmpeg PATH bug: a Finder-launched app
  bundle never sees the shell's brew PATH, so `_find_ffmpeg` now checks
  well-known install locations directly, and the launch script installs
  ffmpeg when it's missing entirely.
- **Trays**: an always-visible view label (live · sheet n/N vs. a tray's own
  "×" mark), a sticky live-sheet view so param edits re-render the sheet in
  place, a ↻ re-bake-from-live action (one undo entry), click-to-select
  trays.
- **Sheets**: crop (`timeline` | `full`) replaces framing entirely — the old
  per-frame center mode is DELETED, and motion now survives baking instead
  of being frozen out by it. Sheets are rows×cols only now; a general
  rotation heuristic replaced the old framing-specific one. Legacy `framing`
  keys still load, they just no longer drive new bakes.
- **Plot flow**: ▶ Plot now obeys the current view label rather than always
  plotting the live canvas — a **semantic change** worth knowing if anything
  external assumed the old behavior. Multi-pen sheets run as a guided pass
  queue (hold + "swap to pen, then ▶ continue"); Stop clears the queue; the
  target picker greys out on sheet/tray views. **Not hardware-verified** —
  simulator and headless only.
- **Final sweep**: a chain fence on interpolation (video pairs still blend
  fine, chains don't try to); A→blends→B now groups sheet interpolation
  correctly; a narrow-tween warning; per-sheet and total plot-time surfaced
  in the layout summary; closing the popup re-syncs the timeline; a
  paste-skip notice when a paste can't apply.

**Boundary changes** (recorded in the cross-project feed): new API endpoints
for chain keyframe add/remove/reorder, staging rebake, and
`animation export.gif` / `export.mp4`; crop replaces framing in sheet/capture
formats (legacy `framing` keys still load); `plot.js`'s ▶ Plot semantic
change above; ffmpeg is now a launch-installed dependency, not an assumed one.

**Not done / explicitly deferred**: hardware verification of the pen-swap
queue; Ian's bench eye-check of the whole round (CHECKME.md's new
2026-08-11 section); per-param copy/paste, dynamic trays,
project-starts-in-a-tray, a +keyframe jump-to-new-key affordance, and
whether held-queue-survives-view-change is the right call — all parked, not
scheduled. An Opus docs-upkeep pass runs immediately after this wrapup.

---

**Session 2026-08-10→11 (Fable 5 orchestrating Sonnet/Opus): fast-marching contours, then a scrub/animation performance pass.**

Two rounds, both verified by Ian.

**Round 1 — `fast_marching_contours` source** (`4c99f2b`). Edge-seeded
Eikonal isochrones with an original boundary-threading stage, reverse-engineered
from reference SVGs (padcrafting/ContourTool establishes the speed mapping
only — it has no threading and seeds points). Turns 200 loose contours into a
handful of serpentine pen-down trails joined along the frame perimeter. 24
tests. Ian: **"this is golden"** — taste-verified, not just numerically.

**Round 2 — animation/multi-layer performance** (`9649d8d`, `fb959d5`,
`966debf`). Diagnosed a sentinel project scrubbing at >10s/frame: param-route
tweens re-ran generators on every frame, every per-layer cache held one slot
keyed on `master_t` (so scrubbing never hit), an occluder sitting on top
re-clipped everything below it, `plan_job` estimates ran per frame, and a
stray `/api/plan` fired per slider tick. Four fixes:
1. `stats=false` opt-out on `GET /api/compose/resolved`; the slider now
   passes `plan:false, stats:false` while dragging and does a full refresh on
   release.
2. `axibridge/gencache.py` — a content-keyed memo on `generate()` itself
   (key: generator id + canonicalized params + `asset_store.version()`),
   random eviction (LRU is the wrong policy for cyclic scrub/loop access —
   see the module docstring), point-budget-bounded, sized by the new
   `AXIBRIDGE_CACHE_BUDGET` env multiplier.
3. All four per-layer caches (tween, clip-follow, shaped, occlusion) went
   from one slot to a budget-bounded multi-entry map, each entry holding
   strong references to pin the `id()`-keyed objects it names
   (`tests/test_scrub_caches.py`).
4. Optional `skfmm` Eikonal solver behind the `[fast]` extra
   (`scikit-fmm>=2024`, installed on the Mac venv) — the pure-Python solver
   stays the tested reference and is what the Pi runs, unaffected.

Measured on the real sentinel project: cold frame >10s → ~2.5s, a revisited
frame → sub-millisecond. Suite: 843 passed, 1 skipped. Ian confirmed the run
a success in-app.

**New batch starting, not yet built** — see `HANDOFF.md` for the full spec.
Six small UI fixes (schematic line width, a Settings menu-bar tab, motion
params reordered, live generator preview, keyframe sublayer polish, render
popup upgrades) plus two design docs Opus is drafting first
(`docs/plans/timeline-v2.md` for a windowed-tween timeline rethink, and a
staging/batching UX doc), plus a meta/harness review and a general
low-key improvements pass.

---

**Session 2026-08-10 (Codex): Fast Marching Topo, native adaptation.**

Ian pointed at Roland Blok's `FastMarchingTopoPlot` and chose a native
axibridge adaptation over a literal browser-control port. The algorithm is
intact: brightness becomes wave speed, a heap-based Fast Marching solve
computes seeded Eikonal travel time, and evenly spaced iso-times become
topographic stroke contours. Dark pixels slow the front and compress the
lines; bright pixels spread them. `_fast_marching.py` owns the numerical
engine; `fast_marching_topo.py` is the registered image source.

Native means the shared 800px working canvas rather than percent-of-original,
`resolution` 0.25×..2×, blur in paper mm, the common brightness/contrast/
gamma/levels pipeline, rotation/frame/show-map behavior, normalized seed X/Y,
and alpha clipping on by default. `asset_store.alpha(..., size=)` now resamples
the crop mask to the exact working grid, and `_pixelgen.luma_grid` now admits
sub-1× resolution for expensive generators. Contour extraction is compiled
marching squares through an explicit `contourpy` dependency; the upstream
Unlicense provenance is in both new module docstrings.

Eleven focused tests pin the Eikonal field, slow-region density, unreachable
pixels, deterministic contours, seed/invert changes, exact closure, resized
alpha clipping, bounds/schema/orientation and monotone progress. Full suite:
**800 passed**, typecheck clean. A default 800px 1200×800 gradient source took
**1.3s**, producing 232 paths / 127,695 points. Not yet judged in the app or on
paper; the concrete check is in `CHECKME.md` and `HANDOFF.md`.

**Session 2026-08-09 (Opus 5): offset fill v2 — one spiral instead of sixty rings.**

Prompted by reading [cavalier-contours-js](https://github.com/msurguy/cavalier-contours-js),
a TypeScript port of the Rust `cavalier_contours` crate, and comparing it
against our `offset_fill`. The library itself is unusable here — JavaScript,
against server-side geometry behind the single-resolve invariant, on a Pi with
no Node — so nothing was vendored. Four of its ideas were.

Measurement first, and it reframed the job. Ours was already fast (3–10 ms for
a full-bed fill) and already correct about topology. What it was bad at was
**pen lifts**: a 120 mm square at 1 mm spacing plots as *61 separate strokes*,
sixty of which are travel between rings a millimetre apart. And `smooth` was
scale-blind — 8 segments per quarter is 0.005 mm of chord error at a 1 mm
radius and 0.53 mm at 110 mm.

`effects/offset_fill_v2.py` is a **sibling**, not a replacement. v1 and its
275-line test file are untouched, and `spiral=False` reproduces it path for
path — a test asserts it, and the rest of the file leans on that control arm.

- **The spiral** (ROADMAP's named open item, now struck). A level *forest*
  links each component to what it erodes into; a spiral runs down every
  maximal hole-free single-child chain, and rings take over wherever one
  splits or carries a hole — built *on top of* the rings, as that entry asked.
  A dying limb's medial tail becomes the spiral's last turn instead of a lift.
  61 strokes → 1.
- **`tolerance` (mm) replaced `smooth`.** The segment count is derived per
  call from the radius actually being offset, so it means one thing at every
  scale.
- **eps triple** (`pos_eq_eps`, `offset_dist_eps`, `slice_join_eps`), in the
  collapsed Fine-tuning group, each saying which engine it serves.
- **`effects/_arcpoly.py`** — a bulge-polyline offsetter behind
  `engine="arc"`, **off by default**.

**The subtlety worth carrying forward**, because it cost a rebuild and is
written up in `_spiral`: laps hold their spacing by drifting in LOCKSTEP, and
the innermost lap has nothing to drift toward, so a full-drift blend slides the
lap above right onto it. Capping the drift at `blend` bounds parallel
separation at `(1 − blend) × spacing`. It is invisible on a square or a star,
whose inner laps are short; it is 31% of the stroke as doubled ink on a C at
blend 1.0, because a long thin shape's contours barely shorten as they erode.
Default 0.5. (An earlier draft of that docstring claimed the bound held
*everywhere* — it does not: at the seam a lap necessarily returns near its own
start before hopping, which is what a seam is.)

**The arc engine**, and why it is not the default. It decouples output vertex
density from input density — at a matched 0.05 mm tolerance a traced circle
fills in ~380 vertices whether the import was a 96-gon or a 1440-gon, against
776 → 7569 for shapely, which inherits whatever the source polyline had. It
also holds 10 µm over ten repeated 1 mm offsets, and declines to emit the
area-0.0 ring shapely hands back for a shape that has just vanished. But it is
2–4× slower on the preview path, and a wrong prune is permanent wrong ink
rather than a crash. `tests/test_arcpoly.py` gates it: a differential test
against shapely across seven shapes, plus a test asserting the default, so
flipping it is a deliberate act that wants a wider corpus and a hardware check.

Five silent bugs on the way there, each now a named test — a reflex arc's
centre on the wrong side of its chord; a fitter that turned squares into
circles (four corners are concyclic, so a vertex-only deviation test finds them
a perfect fit); an uncapped greedy fit eating a circle in one 356° bite; mitre
joins laying down a backwards spike because a mitre trims *both* sides; and a
prune comparing flattened geometry against an exact distance, which rejected
every valid offset and kept the slivers.

One pinned weak spot: in the last millimetre before a shape collapses the raw
offset crosses itself repeatedly and the noding invents faces whose total area
*grows* with depth. The symmetric distance test does not catch them (a mitre
spike legitimately sits further than |d| away), so the invariant is enforced a
level up in `_forest`, where the previous level is in hand — verified monotone
across six shapes at four spacings.

Verified: 789 tests green. **Not** verified: nothing was run in the app or put
on paper. See `CHECKME.md`.

Also inherited, unrecorded until now: three UI commits landed on 2026-08-08
after the last wrapup — the playback transport joining the status line
(`4ffecda`), zoom moving to the toolbar's right end with 100% meaning life size
(`608341b`), and Plot/Settings sub-sections folding via `data-fold` markup
(`4bb2ec9`). None has had an eye-check.

---

## Earlier sessions
**Session 2026-08-08 (Opus 5): three small things — space, precision, a spline.**

Unrelated asks, batched. 743 tests green, typecheck and build clean.

- **~20px of dead height above the canvas, reclaimed.** The tool row sat 93px
  down: a 44/42px header band that in the app shell is *empty on the left*
  (the in-page menubar stands down for the system one, so only the traffic
  lights and a right-aligned readout cluster occupy it), then 12px, the row,
  then 10px. Now 40/38 + 4 + row + 5, and the segment buttons a pixel shorter.
  `#canvas-wrap`'s top went 93 → 75, measured in headless chromium in both
  shell modes. Nothing moved and no markup changed — the wrapper is `flex: 1`
  with the SVG absolutely positioned inside it, so the drawn page grew on its
  own, and the sheet is height-constrained in portrait so every pixel counts.
  Ian's call was to tighten paddings rather than restructure; the alternative
  (hoisting the tool row bodily into the header band, which the CSS comment at
  `:root[data-shell="native"] header` already hints at) is still available and
  worth about 50px. **The band stays at 38px deliberately:** `<header>` is the
  only `pywebview-drag-region`, and double-click-to-zoom needs
  `e.target === header`, so it needs real empty area to grab.
- **Shift fine-tune was never the drag.** `main.js` already produced twelve
  significant digits; `forms.js` crushed them straight back on both live
  preview and commit. The cause was one value doing two jobs — `step` was the
  coarse default *and* the finest a value could be — so on any field with a
  span over 20 (most millimetre params) the committed resolution was whole
  millimetres, and shift+arrow moved *exactly as far as a plain arrow*. That
  is the "shift does nothing" Ian kept reporting. `step` now stays the coarse
  default and a derived `fine` (`step / 10`, or 1 for integers — Pydantic
  rejects a 0.1 on an int field) is what actually quantizes and what gets
  stamped on `data-fine-step`. `main.js` needed no change; it reads the stamp.
  The literal-comparison quantizer went too: decimals come from `log10(fine)`,
  because an equality ladder mis-rounds silently the moment a rung is added.
  Result — span ≤ 2 → 0.001, span ≤ 20 → 0.01, span > 20 → 0.1, int → 1;
  verified live, a 10..400mm field shift-arrows 200 → 200.1.
  Placement's four boxes are hand-written rather than schema-driven, so they
  got the same treatment by hand, and their `toFixed()` calls were never
  cosmetic: `commitPlacement` re-reads the boxes, so `toFixed(0)` meant a
  rotation could only ever *be* a whole degree.
- **`effects/smoothen.py` — Catmull-Rom, and the choice is the design.**
  Visible faceting is flattened geometry, not the machine (settled 2026-07-31):
  the vertices are honest samples and what is missing is the arc between them.
  An interpolating spline puts that arc back without moving a point Ian
  placed, so a flattened circle comes back *round* instead of shrinking toward
  its centroid — the opposite of what the `[1,2,1]/4` kernels in `sources/`
  do. That kernel is still there as `relax`, for input that is genuinely noisy
  rather than merely sparse. Centripetal by default (no cusps), `resolution`
  in paper mm per the resolve-order invariant, closed rings wrap so the seam
  curves like anything else, open endpoints come back bit-identical, and
  consecutive duplicates are dropped before parameterisation — a zero chord is
  a division by zero and shapely emits them routinely. On a flattened octagon
  it cuts radial error by 9×.
- **The playback transport joined the status line** (Ian, same session). It
  had its own strip under the sheet, spending a whole row on two controls, and
  it reports on the drawing exactly as the status line does. Now bottom-right
  of the canvas pane at `#machine-state`'s button scale, so Animate and Stop
  read as the same class of control. Placement is `#global-error`'s existing
  `margin-left: auto` doing the work — it pushes itself and everything after
  it right, so no second auto margin competes for the gap. Net: the sheet no
  longer jumps down when a plan appears, and the status line grew 2px.

**Debt noted, not paid:** the arc-length `_resample` walker now exists
byte-identically in five effects (`coherent_jitter`, `freehand`, `eyelets`,
`parasite_line`, `continue_strokes`) and again with a pressure channel in
`sources/drawing.py`. `smoothen.py` stays self-contained rather than starting
a sixth copy *or* a half-finished hoist — but the next effect that needs it
should hoist the lot into one place first.

**Ian has not eye-checked any of this** — `CHECKME.md` has a 2026-08-08
section. All three are taste calls a passing suite says nothing about.

---


**Session 2026-08-07 (part 3, Opus 5): Slice 4 finished — 4c through 4g.**

The redesign's own slice, done. 727 tests green, 26 acceptance tests.

- **The canvas toolbar is one fixed row of tools.** It wrapped to three at
  1500px and every row it wrapped to pushed the sheet down while you resized.
  The overlays and render mode went to the View menu, the A/B ⇄ cluster to
  Plot › Staging, Animate + speed to a playback strip under the sheet that is
  absent when there is nothing to play. Measured 1600 → 900px: toolbar 39.8px
  and canvas top 95.8px, both constant. Below 900 the HEADER wraps — a
  separate control, recorded rather than hidden.
- **Machine state lives in the status line** (4d), visible from any tab:
  position, pen, progress, time left, and Pause/Resume/Stop moved there
  bodily. Fixes the bug the plan named — `remaining …` used to be written
  OVER the est/ink/lifts readout and never restored.
- **The Plot tab is five panels, not ten.** Motion parameters, pen & origin, raw
  EBB, soft limits and holder calibration went to Settings (which already
  owned calibration's reset button, so that control is reunited); only the
  pure actions became a **Machine menu**. Ian delegated the per-panel calls;
  the reasoning is in `plot.js`'s `MACHINE_PANELS` comment.
- **Plot by pen** (4e): `target` takes `pen:<id>`, one filter in
  `compose.flatten_to_document` so every consumer sees it through the single
  resolve path. No done-ledger, on purpose — a stale one authorises
  replotting over wet ink.
- **The layer list** (4f): drag to reorder with a drop line, ⌥-drag to
  duplicate, rename in place, and the per-row ↑ ↓ retired — moving a layer
  across fifteen was fourteen reorders and fourteen resolves. Occlusion
  channels are two segmented groups instead of eight tickboxes (4g).
- **The menu greys what it cannot do.** The probe reports `{on, enabled}` per
  item; an NSMenu autoenables its items by default and would have overruled
  every `setEnabled_` on open, so `setAutoenablesItems_(False)` is what makes
  it stick.

Two of my own mistakes worth carrying forward. Double-click-to-rename never
fired and I blamed `draggable`, changed the code on that theory, and the probe
came back `draggable: false` with the event still missing — the real cause is
that selecting a row rebuilds it between the two clicks, so `e.detail` is used
instead. And two acceptance assertions depended on which tests ran first (the
server fixture is session-scoped): both now establish their own precondition.

**Ian has not eye-checked this round.** The Machine menu's greying in
particular is verified only against real AppKit objects and a faked bridge.

---

**Session 2026-08-07 later (Opus 5): the two menu bars became one definition.**

Slice 4 of `docs/plans/ui-redesign.md`. 15 commits, suite 689 → 712. Four of
those commits are reverts, and the reverts are the story.

- **4a shipped, 4b was built and reverted.** The engraved-voice consolidation
  (`50dab95`) stands: one selector list states the uppercase/tracked treatment
  once through `--engraved-*` custom properties, where eight rules used to
  restate it. Zero visual change, measured over 2904 elements across all four
  tabs. **4b (IBM Plex Sans) was built, shown, and reverted the same day** —
  Ian: *"got used to the mono"*. Mono-only is now a decision, not an omission;
  the plan's 4b section is annotated BUILT-THEN-REVERTED with the three
  findings that outlive it, chief among them that
  `input, select, textarea { font-family: inherit }` is load-bearing only
  while `body` is mono.
- **No emoji in this UI** (`e3adad3`) — the layer-visibility `👁` is now inline
  Lucide `eye`/`eye-off` via the existing `.tool-icon` class, and the layer
  row's controls got a shallow well so they stop reading as decoration. Ian
  has said this before; it is now in auto-memory.
- **The menu unification, which took most of the session and four failures.**
  The app shell hides the in-page menu bar and showed a SECOND hand-written
  list, where Undo sat under "History" and orientation under "Canvas" — so the
  previous session's Edit-menu work had never been visible to Ian at all, and
  moving controls into the in-page menu made them *unreachable* in his app.
  `axibridge/menu_spec.py` now parses `#menubar` out of `index.html` into
  (label, selector, kind, shortcut); `build_menu` walks it; `merge_native_menus`
  folds our Edit/View items into pywebview's own menus of those names. **The
  markup is the contract now** — add a menu item to the page and it appears in
  both bars, with a checkmark.
- **Four bugs, all in the one path no test here can reach**, each fixed by
  removing its class rather than its instance:
  `item.title()` on a bar menu (pywebview titles the SUBMENU) → prefer the
  submenu; `NSMenuItem.alloc().init()` leaves the title as the literal string
  **"NSMenuItem"**, not empty, so an emptiness fallback never fired; the state
  sync pulled via `evaluate_js` from inside the `js_api` handler the page was
  awaiting (a bridge deadlock) → the page pushes instead; and a main-queue
  block that **returns a value** makes PyObjC raise an uncaught ObjC exception
  that terminates the app → `on_main()` is now the only way this file schedules
  main-thread work, and it always returns None.
- **The shell leaves evidence now.** Every AppKit poke swallows its exception
  so a cosmetic failure cannot stop the app opening, and Finder gives the
  bundle no stderr — so "best-effort" meant "invisible", and each bug cost a
  round trip through Ian relaunching. `~/Library/Logs/axibridge-shell.log`
  records the merge, the resulting bar, every state sync and every swallowed
  exception. It found the crash in one step after three days' worth of guessing
  in one afternoon.
- **4c's first step landed** (`6d0f047`): the View menu took the travel /
  draw-order / paper-guide checkboxes and Schematic·Ink. Toolbar three rows →
  two. It shook out a parser bug worth remembering — `<input>` is a VOID
  element, so `handle_endtag` never fires and a naive tag stack never unwinds;
  the whole View menu silently vanished from the spec until void tags were
  balanced on the way in.

Ian confirmed the menu bar, the checkmarks and the moved controls in the real
app. **Testing lesson banked:** two of the four fixes passed a unit test whose
fake encoded what I believed about NSMenu rather than what it does. There is
now a real-AppKit test (`test_merge_against_real_appkit_menus`) and a
subprocess test for the crash class, because a recurrence kills the
interpreter rather than failing an assertion.

---

**Session 2026-08-07 (Opus 5): the redesign plan's first three slices, plus redo.**

Worked `docs/plans/ui-redesign.md` from Slice 1 to Slice 3, checkpointing
after each. Seven commits, suite 639 → 689.

- **Occlusion is memoised** (`compose.OcclusionCache`). It used to run in full
  on every resolve; a repeat resolve on a 5-layer scene with a stroke occluder
  over a dense hatch fill went 430 ms → ~0. The cache is **content-keyed and
  never invalidated**: geometry is identified by object identity (legal only
  because modules are pure and lists are replaced wholesale), plus pen
  diameter, margin, groups, the receives flag, and layer order via the
  accumulated channel signature. `id()` reuse can't bite because every entry
  holds a strong reference to each list its key names. `tests/test_occlusion_cache.py`
  never inspects the cache — it asserts the cached resolve is byte-identical
  to an uncached one after every mutation that can move a mask. Known gap,
  documented: a visible region layer rewrites the shaped geometry below it
  each resolve, so those layers miss every time. Slow, never wrong.
- **Undo 8 → 50, with a geometry budget, and redo.** Measured first: an
  ordinary edit retains ~29 KB (the deep-copied Project), while an edit that
  REPLACES geometry pins its own copy at ~130 bytes/point — 50 bakes of a
  1200-path import is ~110 MB. Hence two caps, not one number. Redo makes
  history a pair of stacks; any real edit clears the redo branch, and a
  coalesced slider run is one entry in both directions.
- **Orientation is a declared layer property** (ROADMAP option B).
  `SourceModule.orientation` is mandatory — `"none" | "param" | "geometry"` —
  and for `"geometry"` sources in portrait the layer's affine carries the
  display map's inverse, so a layer lands where it would have in landscape,
  on screen. All 27 sources classified. The recurrence-stopper is
  `tests/test_orientation.py`: it fails on a source that declares nothing.
- **Acceptance harness** (`tests/test_acceptance_ui.py`): ten Playwright tests
  driving the real UI against a real server on a temp port, asserting what the
  user sees. They skip cleanly with no browser, which is how the Pi stays
  backend-only.
- **Vite + TypeScript**, with the source unmoved. `app.frontend_dir()` is the
  whole switch: built output when it exists, source when it doesn't — the
  fallback is what keeps a machine with no npm working. TypeScript is a lint
  pass (`allowJs`, `noEmit`), nothing renamed. ROADMAP's "Far / undecided — UI
  revamp" is marked RESOLVED with what was adopted and what it cost.
- **Edit menu** (Ian's ask, mid-session): Undo/Redo with ⌘Z / ⇧⌘Z; the
  portrait/landscape control **moved** into the View menu rather than being
  proxied there, so it cannot drift from `main.js`.


**Session 2026-07-27 (Opus 5): two new modules, and the workflow changed.**

Ian asked that work be **incorporated automatically** from here on — commit
straight to `main`, only branch when he says so. (Pushing still requires
asking; that rule is unchanged.) The trigger: nine feature branches had piled
up committed-but-unmerged, so finished work read to him as missing entirely.
`feat/ui-round-0726` was the last one and is now merged.

- **`effects/offset_fill.py`** — the second fill primitive beside `hatch_fill`:
  repeats the outline *inward* as concentric rings (contour-map look) instead
  of laying scanlines across it. The whole effect is erosion by a disk, and
  **topology needs no special-casing** — components split, components vanish,
  holes grow and merge, and shapely returning a `MultiPolygon` or an empty
  geometry *is* the event. The levels form a monotone forest because erosion
  can never invent a hole nor merge components. Load-bearing details, each
  pinned by a test: rings are eroded from the ORIGINAL at `k*spacing` (never
  iteratively, or corners re-round each pass); the even-odd hole assembly runs
  BEFORE eroding, which is why this is layer-wide and can't be a mode on
  `contract_expand`; inner rings are `filled=False` or occlusion reads the
  stack as stripes. `medial_tail` draws a centreline down limbs too narrow for
  another ring, suppressed when it would double an existing one.
- **`round_center`** (Ian's follow-up, same day) — relaxes each ring's corners
  in proportion to its depth, so the family morphs from the shape toward
  circles on the way in. A morphological opening, which is what buys the three
  properties that matter: it leaves straight runs untouched (ring spacing
  survives), it stays contained in the shape (rings can't escape or enter a
  hole), and it rounds only CONVEX corners — so concave structure survives and
  a star's centre becomes a flower, not a disc. That is the honest result, not
  a shortfall. The radius backs off by halves rather than ever costing a ring:
  verified that without the guard a 40mm square drops from 10 rings to 5.
- **`sources/brush.py` + `static/js/brush.js`** — ROADMAP 0c, the sibling of
  the shipped pen tool, now a 4th toolbar segment button. Circle brush, `[`/`]`
  resize, `E` toggles erase. The correctness story is the **sequential fold**:
  erases apply per stroke in chronological order, never
  union-all-then-subtract-all, or a repaint over an erased spot is swallowed.
  `test_repaint_over_an_erase_survives` builds the batched answer explicitly
  and asserts the real one differs — confirmed it is the only test of the 17
  that fails under a batched implementation. Output is every ring as a closed
  `filled=True` path, holes by nesting. Playwright-verified end-to-end against
  the real UI (4 strokes, no console errors, the erase bite and repaint bulge
  both visible in the resolved output).
- **`docs/plans/liquify-effect.md`** — a *loose* plan (hatch-connect-v2 style,
  not a frozen brief) for a soft-brush warp effect Ian raised hypothetically.
  Three findings worth keeping: it would be the first captured-input *Effect*
  (draw/pen/brush are all Sources); "depth as parameter" reads as a global
  `amount` 0..1 that must be exactly identity at 0, which makes timeline
  animation free; and **interpolating two liquifications is easier than the
  captured-geometry morph already shipped**, because a warp is a field rather
  than a structure. The trap there is that the tempting fix (A/B inside the
  effect) re-forks interpolation — extend the core instead. Filed as ROADMAP 0d.

Also merged this session: **`feat/ui-round-0726`** (Lucide tool icons, pen
Commit button, hatch-to-its-own-pen split), which had been sitting unmerged
since 07-26.

**Not done:** nothing has touched paper. Both new modules are screen-verified
only (rendered PNGs + Playwright), and ring-spacing-vs-pen-width is exactly
the kind of thing only real ink settles.

**Late in the session** (Ian's ask, all pushed):

- **`main` is on origin** — first push ever, and **idkpi pulled** to the same
  commit with 560 green there. Standing rule changed: push without asking on
  this project.
- **`fix(server)`: the app's slow quit was a one-line uvicorn default.**
  `timeout_graceful_shutdown` defaults to *wait forever* for open connections,
  and `/api/events` is an SSE stream that never finishes by design — so every
  quit hung until `launch/axibridge_app.py`'s 5s grace expired and SIGKILLed
  it. Measured with a stream held open: before, SIGTERM hung past 10s; after,
  clean exit in 2.17s. The plot-running close guard is untouched.
- **"Unknown source: brush" is a stale server, not a bug.**
  `load_builtin_modules()` runs once at startup, so a process started before a
  new module file exists never imports it — the browser picks up new JS
  instantly (no build step) and the mismatch looks like a broken tool. Restart
  the app after any new source/effect lands. Worth knowing generally.
- **"Graduate to a real app?"** — the shell question and the frontend-build
  question are separate and must stay that way (ROADMAP keeps the latter
  deliberately open). A Tauri/Electron shell would still point at
  `localhost:2942`, so the dev loop would be unchanged; a bundler is what
  would actually add tedium. Most of the "cheap" feeling was the shutdown bug
  above. Recommendation on record: use it a week, then fix the specific
  irritations rather than buying an architecture.

---

**Prior session 2026-07-25 (Sonnet 5): merged the four pending branches to main**
(nested-tween-morph, pen-tool, geometry-morph-tween, hatch-connect-strokes),
in dependency order with tests run after each step (suite 511 green).
`feat/geometry-morph-tween` needed a rebase onto the advanced `feat/pen-tool`
tip as flagged, which surfaced a real conflict/regression: nested-tween-morph
had rewired the live tween resolve path (`_source_paths_at`) to reduce
endpoints via `effective_generator` + `lerp_params` directly, bypassing
`blend_generator_params` — where the captured-geometry deep-lerp (pen/drawing
shape morph) lived. Fixed by applying the same deep-lerp inside
`_source_paths_at` on the post-reduction param dicts; one failing test
(`test_pen_tween_morphs_shape_continuously_not_stepped`) caught it before it
reached main.

---

**Session 2026-07-20 → 21 (Sonnet 5 / Opus 4.8): pen tool built, tween shapes now morph, hatch strokes join.**

The ⚓ pen tool (`sources/pen.py` + `static/js/pen.js`) with Photoshop grammar
and a 3-way toolbar mode segment driven by a shared `setToolMode` broker;
captured-geometry tween morph (`tween._blend_geometry` — pen/drawing shapes
morph A→B structurally instead of stepping at 0.5) plus a `cosine` ease;
`hatch_fill.connect_strokes` to cut pen lifts. Full record:
`docs/plans/pen-brush-tools-RESULTS.md`.

## Prior arc — 2026-07-19 (Fable + Sonnet 5): interpolation core unified, canon audit

One interpolation blend core in `tween.py` (`structures_match` / `lerp_paths` /
`blend_generator_params` / `blend_effect_stacks`), cheap-checkpoint invariant
restored, capture snapshots externalized to `staging/snapshot-<group>.json`,
registry-wide contract tests (`test_effect_contract.py`). **This is the
unification that ROADMAP 0d's liquify note warns against re-forking.**

## Prior arc — 2026-07-16 → 19 (generator v2, bench latch, draw/response tools)

`misremembered`/`glyphgram` v2 (scribble masses + tone, coherent-field +
continuity); generate-bench latch with coalesced undo; draw tool
(`sources/drawing.py` + `static/js/draw.js`) and response brushes
(`parasite_line`, `eyelets`, `velocity_tube`). Aesthetic rule (auto-memory):
structure-following marks, coherent fields, chaining — never uniform scatter.
Agent-ops: no worktrees (PEP 660 editable install imports main checkout);
agents work in the main checkout.

## Older history

URGENT round 11/11 (2026-07-13, orientation coherence via viewmap tags),
lineart v2, animation previews, Pi rounds, sheets v2, A/B capture — see
ROADMAP shipped sections and git history. Architecture invariants:
`ARCHITECTURE.md`, `docs/MODULES.md` (single resolve path; scrubbing never
mutates stored state). Two AxiDraw modes contend for the serial port —
Mac-driven pi_ssh (default) vs the disabled Pi-served service.

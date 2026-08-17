# Check when you're home — 2026-08-07, added to 08-08, 08-09 and 08-10

Everything below passed its tests. None of it has passed *your eyes*, and the
first group is the part no test here can reach. Delete this file once you've
been through it.

## Only verified against fakes — most likely to be wrong

**Relaunch AxiBridge (quit fully, not a reload) for anything in this group.**

- **Machine menu greying.** With nothing connected the whole Machine menu
  should be grey. Connect the simulator: pen up/down and the origin items
  should come alive (the simulator advertises them). Verified only
  against real AppKit objects and a faked bridge — never a real menu.
- **Menu checkmarks.** View should tick your current orientation, render mode
  and whichever overlays are on, and the ticks should follow when you change
  them from anywhere.
- **Edit / View merged into the system menus.** Undo/Redo above Cut/Copy/Paste;
  Portrait/Landscape above Enter Full Screen. No duplicate Edit or View.
- If any of this misbehaves: `cat ~/Library/Logs/axibridge-shell.log` — it
  records the merge, the resulting bar, every state sync and every swallowed
  exception. That is the file that turned four silent failures into one.

## Verified against the simulator only — real machine untested

- **The status line during a plot.** Progress, time left, X/Y, pen up/down,
  and Pause/Resume/Stop, under the sheet, on every tab.
- **est / ink / lifts must survive the job** — it used to be overwritten by
  "remaining …" mid-plot and never restored.
- **Plot by pen.** The target picker now offers `pen: <name> (N layers)`.
  Worth one real multi-pen sheet: pick a pen, plot, swap, pick the next.

## New since you last looked — all taste, mined from the August review

- **Sliders are faders now**: 12px groove, machined cap, and the fill is
  graphite instead of `--live`. That last bit was a real bug — three sliders
  on screen all claimed the selection colour, i.e. "you are here", at once.
- **The canvas well has a lamp**: brightness falls off from the sheet to the
  frame. The old page-wide gradient is gone.
- **Sentence case below panel level** (`Fine tuning`, `Placement`, `Pen &
  occlusion`), body ink one step quieter, panel headings unchanged.
- **The window title says `axibridge — <project>`.**

## Verified in a browser — just taste, not correctness

- **The toolbar** is one row of tools and zoom-fit. Does losing the overlays
  to the View menu cost you anything in practice?
- **Layer list:** drag to reorder (drop line shows where it lands), ⌥-drag to
  duplicate, double-click a name to rename in place. The ↑ ↓ buttons are gone.
- **Occlusion channels** are two A/B/C/D segmented groups instead of eight
  tickboxes.
- **Plot tab** is five panels; the machine ones are in Settings now.

## Added 2026-08-08 — the bed, the sliders, Smoothen

- **The sheet is 20px taller.** The tool row sits right under the header band
  now. Is the header still comfortable to grab and drag the window by? Does
  double-clicking it still zoom? Those are the only two things the tighter
  band could have cost.
- **Shift fine-tune actually resolves now.** Grab any millimetre slider with a
  wide range (page size, a radius, a length) and shift-drag it: the number
  should move in tenths, not whole millimetres. Shift+arrow should move
  visibly *less* than a plain arrow — that was the part that did nothing at
  all before. The number boxes step ten times finer too, which is the one
  trade: their own up/down arrows are slower now. Say if that irritates.
- **Placement keeps decimals.** x/y to 0.01mm, scale to 0.001, rotation to
  0.1°. Rotation could only ever be a whole degree before, and any finer angle
  was thrown away by the panel merely re-rendering.
- **Animate plot moved into the status line**, bottom-right corner of the
  canvas pane, at the same button scale as Pause/Resume/Stop. It had its own
  strip under the sheet spending a whole row on two controls; that row is gone,
  so the sheet no longer jumps when a plan appears. Check the speed box is
  still comfortable to hit at the smaller size.
- **New effect: Smoothen.** Stack it on anything visibly faceted — an imported
  SVG curve, a boolean result, a generator that walks in straight steps. It
  passes *through* your points and only invents the arc between them, so a
  flattened circle should come back round rather than shrink. `Relax` above 0
  is the opposite behaviour (it moves the points) — only reach for it if the
  input is genuinely noisy. Two things worth watching: whether `resolution`
  0.5mm is the right default for plot time, and whether a filled shape with
  Smoothen on it still occludes cleanly.

## Added 2026-08-08 (later) — zoom, folds, one fewer emoji

- **Zoom moved to the right end of the tool row**, with a percentage box beside
  fit-to-page. Type a number, or read what the wheel/pinch did.
- **100% is life size — but only after you calibrate it.** A browser cannot
  measure a monitor; it assumes 96 pixels to the inch, which is out by a fifth
  or more on Retina. **Settings › Display** has a bar the app believes is
  100&nbsp;mm: hold a ruler across it, type what it really reads, Apply. Until
  you do, 100% is approximate and the panel says so. This is the one thing here
  that genuinely needs you — I cannot do it from this end.
- **Plot and Settings sub-sections fold now**, like the layer panel's. Pen
  height test, Plot-pass optimisation and Plot stepper default closed (they are
  secondary procedures); Quick A ⇄ B and From the tray default open (they are
  the Staging panel's actual content). Machine settings went from six flat
  fields to two groups — Estimator calibration, Server & paths. All remember.
  Say if any of those defaults are backwards for how you work.
- **The camera emoji is gone** from the generator dropdown — the group is just
  "Image-driven" now.

## Added 2026-08-10 — Fast marching topo

- Add **Fast marching topo** with a real tonal portrait. Dark areas should
  compress the topographic rings into detail; bright areas should let them
  breathe. Do the defaults (200 contours, speed offset 0.1) give a useful
  first result, or just an impressive thicket?
- Move Center X/Y away from the middle. Does the expanding-wave origin feel
  like a compositional control, or is it too hidden/technical to predict?
- Try a transparent PNG with **Clip transparent areas** on. The contours must
  stop at the silhouette; watch specifically for tiny clipped fragments that
  would cost a pen lift without contributing a mark.
- Default 800px generation measured 1.3s and about 128k points on a gradient.
  Try Resolution 0.5× and 2× on the same image: does the quality/time tradeoff
  feel honest, and does plot-pass Simplify tame 1× without visibly changing it?

## Known and deliberate

- Below ~900px window width the canvas top edge shifts 10px. That is the
  HEADER wrapping, not the toolbar, at a width where the canvas is ~260px.
- Jog is out of the UI (your call, 2026-08-08): no arrow pad, no step select,
  no Machine-menu items. `POST /api/machine/jog` and the backend methods stay,
  so it is one markup block to put back. Check that Go to origin, Set origin
  and Origin = guide corner still do what you need without it.

## 2026-08-09 — offset fill v2 (the spiral)

Screen and tests only; nothing plotted. You waved it through as "good enough
for my use", so none of this blocks anything — it is here because ink settles
questions a render cannot.

- **Stack "Offset fill (v2)" on a filled shape** and check the Plot tab
  reports **one stroke** where plain Offset fill reports ~60. That is the whole
  point of the module; if it says otherwise something is wrong.
- **Scrub `Seam blend` 0 → 1.** At 0 you get plain rings joined by one radial
  step (a visible seam — the square's diagonal). At 0.5, the default, a real
  spiral. Past 0.5 consecutive turns run closer than half the spacing, and at
  1.0 the innermost two touch — on a long thin shape (a C, a bar) that is a
  lot of doubled ink. **The question for you: is 0.5 the right default, or do
  you want the smoother spiral and the darker centre?**
- **On paper**: does one unbroken stroke actually read better than concentric
  rings, or does the continuous inward drift show as a spiral where you wanted
  contours? This is aesthetic and only you can call it.
- **Engine → `arc`** (Fine tuning). It should look identical to `shapely` on
  everything; it is off by default because a wrong prune is permanent ink, not
  a crash, and it is 2–4× slower on preview. If you ever see it disagree
  visibly with the shapely engine, that is a bug worth reporting — the
  differential test says they agree across seven shapes.
- **Known and NOT new**: an annulus whose wall pinches at exactly a ring depth
  shatters into a dotted circle. Plain `offset_fill` does the same — it is a
  knife-edge coincidence of geometry and spacing, not a v2 regression. Nudge
  the spacing.

## Added 2026-08-11 — E-batch, timeline v2, staging/plot rework

Full record in `docs/plans/timeline-v2.md` and STATUS.md's top entry.
Simulator/headless-verified only — nothing below has had your eyes on it.

- **Chains**: build an A>B>C>D as one tween layer. Confirm it reads and edits
  as a single layer, not four; give each segment its own easing and check the
  keyframe list plus right-click Copy/Paste state feel natural. Try
  add/remove/reorder on an endpoint and watch the cascade.
- **Bottom timeline bar**: auto-hides — does it get in the way or vanish when
  you want it? Frame steppers, checkpoint jumps, the popup button. Drag the
  slider: it should snap to the frame grid, ⇧ should escape the snap, and
  ticks should mark frames already cached.
- **Render popup**: palindrome option, higher-res zoomable renders, GIF/MP4
  export. The ffmpeg PATH bug is fixed (Finder launches never saw brew's
  PATH) — confirm export actually works from the built app, not just `npm run
  dev`.
- **Trays**: the always-visible view label (live · sheet n/N vs. a tray's
  "×"), a sticky live-sheet view (param edits should re-render the sheet in
  place, not fall back to live), ↻ re-bake-from-live, click-to-select trays.
- **Sheets**: crop (`timeline` | `full`) replaces the old per-frame
  center-recompute framing entirely — motion should now survive baking where
  it used to freeze. Rows×cols only; a general rotation heuristic replaced
  the framing-specific one. If an old project used `framing`, confirm it
  still loads sanely even though new bakes won't produce that key.
- **▶ Plot obeys the view label now** — this is a semantic change from
  before (it used to always plot the live canvas). Plot from a sheet view and
  confirm it plots what's on screen, not the underlying live layers.
- **Multi-pen sheets run as a guided pass queue**: hold + "swap to pen, then
  ▶ continue". **Not hardware-verified** — this needs a real multi-pen sheet
  on the actual AxiDraw, not just the simulator. Also confirm Stop clears the
  queue rather than leaving it primed for a phantom continue.
- **E1-E6 small fixes**: schematic line width (0.2mm default, changeable in
  Settings); Settings menu owning Restart server; motion params sitting right
  after the paper guide; generator param edits updating the canvas live the
  way effect edits do; keyframe sublayers keeping collapse/scroll state
  across an A/B switch; the render popup upgrades above.
- **Final-sweep items to sanity check**: a chain fence on interpolation
  (video pairs should still blend — only chains are fenced); A→blends→B
  sheet groups should interpolate as one group; a narrow-tween warning should
  appear where expected; per-sheet and total plot-time should show in the
  layout summary; closing the popup should re-sync the timeline; pasting
  somewhere it can't apply should show a skip notice rather than silently
  doing nothing.

---

## 2026-08-17 — colour separation, and seeds everywhere

Backend, UI and acceptance tests all pass, but the actual deliverable here is
what two transparent felt tips do when they overprint, and no test can judge
that. Nothing in this section has touched paper.

**On screen, first**

- **Separate a real photo.** Compose → an image generator (halftone is the
  most legible) → pick an image → the **⌗ Separate** row appears under the
  form. CMYK by default. Press it; you should get four plates named
  `Halftone · cyan` and so on, landing pixel-exactly on top of one another.
- **Black generation** (in the collapsed Image-processing group) is the knob
  worth playing with before you commit ink. At 1.0 the K plate carries the
  darks and CMY stay lean; at 0.0 the K plate is **empty** and the darks come
  from overprinting CMY. The row tells you about the empty K plate, but
  confirm that reads as informative rather than alarming.
- **Effects on one plate.** Put `hatch_fill` or `freehand` on the cyan layer
  alone. This is the thing the whole design is for — confirm it feels as
  ordinary as it should, because a plate is just a layer.
- **Per-plate generators.** Each plate row has a generator picker defaulting
  to "same as above". Try cyan as halftone and magenta as subline — that is
  the regime collision along the colour axis, and whether it's a good picture
  or a mess is entirely your call.
- **Tone bands** mode separates by darkness instead of colour (lights/mids/
  darks). The `tone_rescale` checkbox in Image processing is the decision you
  said you'd want to change: off, the bands add back up to the original ink;
  on, each band reads at full contrast on its own. Off is the default.

**Then on paper — the part that actually matters**

- **Does the overprint colour work?** Cyan over magenta should give something
  like blue. If the plates read as three separate drawings rather than one
  image, the black-generation default is the first thing to move.
- **Moiré.** Separating with `halftone` puts four dot grids at the same angle
  on top of each other, which in real printing is exactly what screen angles
  exist to prevent. If it moirés badly, that's the roadmapped per-plate screen
  angles becoming worth building — I deliberately didn't guess.
- **Misregistration.** The `slop` box (mm) nudges each plate off register on
  purpose. 0 is exact. Whether a bit of drift reads as charm or as a mistake
  is a paper question.

**Seeds — a behaviour change worth noticing**

- Adding the same effect to two layers now gives two different seeds, so
  stacking `freehand` twice no longer produces the identical wobble. Same for
  layers created by the lineart stack, the separation stack, or the API.
  If anything you expected to match now differs, that's this — and an explicit
  seed still always wins.

**HSL mode (added same day, for fun)**

- A fourth mode in the separation dropdown: hue / saturation / lightness.
  Not an ink model — nobody prints these — so judge it as pictures, not as a
  reproduction.
- **Saturation** is the one that turned out useful: ink only where the image
  is colourful, blank where it's grey. It's a "where is there colour" mask.
- **Lightness** is a different greyscale from luma — even-handed about colour,
  where luma knows blue is dark and yellow is bright. Worth comparing the two
  on the same photo.
- **Hue** has a hard seam through every red, because hue is an angle and a
  circle doesn't flatten onto a line. That's inherent, not a bug to report.
  Greys come out blank on both hue and saturation, deliberately — otherwise a
  greyscale photo would have separated into a solid black rectangle.

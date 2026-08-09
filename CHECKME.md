# Check when you're home — 2026-08-07, added to 08-08 and 08-09

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

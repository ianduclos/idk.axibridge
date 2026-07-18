# Results: response brushes (docs/plans/response-brushes.md)

Run: Sonnet 5 agent 2026-07-18, terminated by session limit during final
composition tuning; completed by the supervising Fable session same day.
Branch `feat/response-brushes`.

## Shipped

- `effects/parasite_line.py` — wandering dotted companion (offset + smooth
  seeded wander, crossings, occasional loops, dash/gap emission, per-path
  variety). Defaults settled by eye: offset 3, wavelength 35, wander 4,
  loopiness 0.25, dash 1.2 / gap 1.0, side alternate.
- `sources/drawing.py` `render="velocity_tube"` — speed-derived width from
  the stored per-point `t_s`; slow swells, flicks taper to hairline.
  Defaults: width_min 1.0, width_max 6.0, speed_smooth_mm 8,
  keep_centerline true. `"centerline"` output unchanged (tested).
- `effects/eyelets.py` — rings at curvature extrema + open ends, seam-aware
  on closed paths, ±30% radius jitter. Defaults: radius 1.4,
  sensitivity 0.5, spacing 12, at_ends true, nudge 0.6.
- `on_closed` param on BOTH effects (default true = brief's contract
  behavior; false skips closed inputs) — added by the supervisor, see below.
- `response` brush preset in `static/js/draw.js`.

## The two composition bugs (why the first acceptance failed)

The modules eye-checked well in isolation but the naive stack
`[parasite, eyelets]` on a velocity-tube layer produced ring-swarms
(1447 pen lifts / 6m for one stroke):

1. **Both effects decorated the closed tube outline as well as the
   centerline** — doubling companions, and the outline's width wiggles
   read as curvature extrema, chaining rings along the whole tube.
   Fix: `on_closed: false` in the preset (both effects).
2. **Effect order**: with eyelets AFTER parasite, `at_ends` ringed both
   ends of every ~1.2 mm parasite dash — hundreds of beads. Fix: eyelets
   runs FIRST in the preset; parasite then skips the eyelet circles
   because they're closed. This ordering constraint is commented in the
   preset table.

Preset also runs eyelets calmer than module defaults (sensitivity 0.7,
spacing 18) — hand strokes stay jittery after smoothing; the defaults
were tuned on clean synthetic paths.

## Acceptance

Slow-arc + fast-flick stroke with the `response` brush:
`scratchpad/agent-brushes/response_brush_acceptance.png` (session scratch)
— swollen-to-hairline outline + centerline, dotted wanderer crossing the
stroke, sparse rings at bends/ends. 174 lifts / est 44.5 s for the stroke:
plotter-honest for a dotted-companion look.

## Would tune next

- Parasite dash count dominates lift count; a `dash_mm` ≈ 2.5 variant
  ("response·sparse") would halve lifts for big drawings.
- Eyelet clustering on slow jittery sections — could gate sites on local
  speed once effects can see it (they can't; source-side option if wanted).
- The tube's `geometry bounds exceed soft envelope` warning fires when
  decorations overhang the bed edge — harmless (clipped at plot), but a
  bed-margin clamp on parasite excursions would quiet it.

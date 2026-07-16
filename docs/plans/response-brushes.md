# Plan: response brushes — parasite line, eyelets, velocity tube (Sonnet 5)

You are Claude (Sonnet 5) running as a coding agent on Ian's Mac, in a git
worktree of axibridge. Written by a Fable session on 2026-07-17.
PREREQUISITE: the `feat/draw-mode` plan (docs/plans/draw-mode.md) must
already be merged — `sources/drawing.py` and `static/js/draw.js` with its
`BRUSHES` table must exist. If they don't, stop and write
`docs/plans/response-brushes-BLOCKED.md` instead of building around it.

The goal is a specific look Ian showed from a demo: a plain mouse stroke
becomes a *skeleton the machine responds to* — a swollen outline whose
width breathes with drawing speed, a dotted companion line that wanders
around the stroke and occasionally crosses it, and small circular eyelets
sprouting at corners and ends. Coherent, continuous, hand-like — never
uniform scatter. If an output reads as a fixed recipe stamped along the
path, it fails; per-mark variety is the house rule (see how
`sources/misremembered.py::_scrub` randomizes wobble per chord).

## Read first (in order, all in-repo)

1. `CLAUDE.md` — module purity, bounded params, occlusion metadata rules.
2. `docs/MODULES.md` — effect authoring contract.
3. `axibridge/effects/freehand.py` + `tests/test_freehand.py` — the house
   style for characterful effects: seed mixing `(params.seed * 31 +
   ctx.seed)` plus a per-path term, docstring explaining mechanics.
4. `axibridge/effects/fat_tube.py` — the uniform-width tube; your velocity
   tube is its speed-aware sibling but lives in the SOURCE (see Part 3 for
   why), so read this for outline/cap geometry, not as the edit target.
5. `sources/drawing.py` — the stroke format `[[x_mm, y_mm, t_s], ...]` and
   the `render` enum you will extend.
6. `docs/IDEAS-generators.md` §framing — the aesthetic rationale.

## Protocol

- `.venv/bin/python -m pytest -q` green before EVERY commit.
- Branch `feat/response-brushes` from main. One conventional commit per
  module, plus one for the preset wiring. NEVER main. Do not push.
- **Eye-check is the core loop, not an afterthought.** For each module,
  write a throwaway script in your scratch dir: synthesize input strokes
  (for velocity work, synthesize `t` too — a stroke with a dwell, a slow
  arc, a fast flick), run the module, render to PNG with PIL (skeleton
  grey, response black, ~3px/mm), and LOOK at it with the Read tool.
  Iterate until the aesthetic target reads on the image. Budget most of
  your time here. Ship fewer modules finished-and-looked-at rather than
  all three untuned; priority order: parasite → velocity tube → eyelets.

## Module 1 — `effects/parasite_line.py`

A companion line that walks with each stroke the way a dog circles a
walker: offset to one side, drifting laterally at low frequency, crossing
the skeleton now and then, occasionally looping. Usually rendered dotted.

- Pure effect (`@register_effect` — copy freehand's registration shape).
  Input paths ALWAYS pass through unchanged; the parasite paths are ADDED.
- Mechanics: resample the input at a fixed internal step (~0.5 mm); walk
  it with a lateral offset `offset + wander(s)` along the local normal,
  where `wander` is smooth seeded 1-D noise (sum of 2–3 incommensurate
  sines is fine). When `|wander| > offset` the parasite crosses the
  skeleton — that's desired, don't prevent it. A `loopiness` param adds
  occasional small loops: when a seeded trigger fires, wrap a ~1.5–3 mm
  circle blended into the parasite's direction of travel (the demo's
  scallops). Vary wander frequency/amplitude PER PATH from the seed.
- Params (bounded, titled, described; fine-grained ones grouped under
  `json_schema_extra={"group": "Fine tuning"}`):
  `offset` mm 0.5–15 default 3; `wavelength` mm 5–120 default 35;
  `wander` mm 0–12 default 4; `loopiness` 0–1 default 0.25;
  `dash_mm` 0–10 default 1.2 and `gap_mm` 0–10 default 1.0 (0 dash =
  solid line; dotted = emit many ≥2-point segments); `side`
  left|right|alternate default alternate; `min_length` mm (skip paths
  shorter than this, default 8); `seed`.
- Closed inputs (first==last): parasite orbits them too — keep `filled`
  and closure of the ORIGINAL untouched; parasite segments themselves are
  open and unfilled always.
- Tests: purity (input list and Path objects unmutated — compare
  deep-copied points), originals present verbatim in output, determinism
  under seed, two overlapping layers differ via ctx.seed, dash_mm=0 emits
  one polyline per parasite, bounds respected.
- Aesthetic target: at defaults on a hand-drawn squiggle, the parasite
  should read as a second, distractible hand annotating the first —
  attached but not obedient. If it reads as a constant-offset contour or
  as noise, wander/loopiness aren't doing their job.

## Module 2 — `sources/drawing.py` render mode `"velocity_tube"`

The demo's swollen outline: tube width driven by DRAWING SPEED. This must
live in the drawing source, not an effect: effects are pure
`list[Path] -> list[Path]` and paths carry only (x, y) — the timestamps
exist only in the source's `strokes` params. Do not try to smuggle time
through the effect pipeline; that path leads to editing `model.py`, which
is forbidden.

- Extend `render: Literal["centerline", "velocity_tube"]`. New params
  (bounded): `width_min` mm 0.3–10 default 1.0, `width_max` mm 1–25
  default 6.0, `speed_smooth_mm` 1–30 default 8 (window for smoothing the
  speed signal along arc length).
- Per resampled point derive speed from the stored `t_s` (guard zero/equal
  timestamps and 1–2 point strokes); smooth it; map slow→`width_max`,
  fast→`width_min` (normalize per stroke: each stroke's own min/max speed
  spans the range — a uniformly-drawn stroke sits mid-width, dwells
  swell). Emit the OUTLINE as one closed path per stroke: left offsets,
  end cap, reversed right offsets, start cap, `first == last`,
  `filled=False`. Also emit the centerline when a new bool param
  `keep_centerline` (default True) says so — the demo shows both.
- Degenerate cases: strokes with all-equal timestamps render at the
  midpoint width; self-intersecting outlines are acceptable (plotter
  draws them fine) — do NOT pull in shapely to clean them.
- Tests (extend `tests/test_drawing_source.py`): closed outline
  (first==last), dwell section measurably wider than flick section
  (synthesize t accordingly and compare local outline widths), centerline
  toggle, determinism, params bounded.
- Aesthetic target: draw slow around a corner, flick the exits — the
  corner swells like ink pooling, the exits taper to hairlines. If the
  width flutters point-to-point, `speed_smooth_mm` isn't being applied
  along arc length.

## Module 3 — `effects/eyelets.py`

Small circles sprouted where the line has structure: curvature extrema
and stroke ends — the demo's little rings at corners and junctions.
Structure-following, never random scatter.

- Pure effect; originals pass through unchanged, circles are added.
- Mechanics: resample (~0.5 mm), estimate curvature, pick local maxima
  above a threshold with a minimum arc-length spacing between picks;
  optionally the two ends. Each eyelet: a closed circle (first==last,
  `filled=False`), radius jittered ±30% from the seed, centered ON the
  line or nudged just off it (`nudge` param, mm) so rings sit like beads.
- Params: `radius` mm 0.4–6 default 1.4; `sensitivity` 0–1 default 0.5
  (curvature threshold, 1 = only the sharpest corners); `spacing` mm
  2–60 default 12; `at_ends` bool default True; `nudge` mm 0–4 default
  0.6; `seed`.
- Closed/filled inputs: eyelets on their corners too; never alter the
  original's `filled`/closure.
- Tests: purity, originals verbatim, circles closed, determinism, a
  square path gets ≥1 eyelet near each corner but a straight line gets
  only end eyelets (sensitivity respected), spacing enforced.
- Aesthetic target: on an angular gesture the rings should feel like
  rivets/grommets marking the joints — deliberate, sparse. If a smooth
  arc grows a chain of rings, sensitivity/spacing defaults are wrong.

## Part 4 — the "response" brush preset

Append to `BRUSHES` in `static/js/draw.js` (shape already contracted):

```js
{ id: "response", label: "response", 
  source: { render: "velocity_tube" },
  effects: [
    { effect: "parasite_line", enabled: true, params: {} },
    { effect: "eyelets", enabled: true, params: {} },
  ] },
```

Then verify in a browser exactly like draw-mode.md's protocol (throwaway
server on a temp port, NEVER 2942; Playwright; domcontentloaded): enter
draw mode, pick "response", draw one stroke with a deliberate slow-fast
rhythm, screenshot, and LOOK: swollen-and-tapering outline + dotted
wanderer + rings at the corner. That screenshot is the acceptance test
for the whole plan — iterate defaults until it matches the demo's spirit.

## Boundaries

- Do not touch: `model.py`, `compose.py`, `session.py`, `estimate.py`,
  backends, `fat_tube.py`, `freehand.py`, any existing module's params or
  ids. `sources/drawing.py` may only GROW (new render mode + params);
  the `"centerline"` behavior must stay byte-identical (test it).
- Every numeric param bounded; every effect pure; every module
  deterministic under (params, ctx.seed); occlusion metadata (`filled`,
  first==last closure) preserved everywhere.
- When done: `docs/plans/response-brushes-RESULTS.md` with the acceptance
  screenshot's path, per-module notes, and default values you settled on.

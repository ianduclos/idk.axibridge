# Plan: AARON core-figure generator (Sonnet 5)

You are Claude (Sonnet 5) running as a coding agent on Ian's Mac, in a git
worktree of axibridge. Written 2026-07-19 (Sonnet 5, no Fable in the loop).
No hard prerequisite beyond current main — this generator only depends on
`effects/freehand.py`, which has been on main since June.

## The goal, and the design calls this brief freezes

ROADMAP's AARON pass item 1 / `docs/IDEAS-aaron-pass.md` §A describe this at
the concept level ("grow a skeleton — plant morphology variables OR a figure
armature with a balance constraint — then embody: a closed outline walked
around it, carefulness varying along the body") without picking between
plant and figure, or specifying the embodiment mechanics. Those are real
design decisions, made here so you're not improvising architecture mid-build:

1. **Skeleton = plant morphology, not a bipedal figure armature.** A branching
   structure has a much simpler, more robust balance rule (weighted centroid
   near the root x) than a legged figure (foot contact, joint limits,
   standing-up physics) — Cohen's own knowledge-level list (§1.5 of the idea
   doc) treats "an entire flora from a few morphological variables" as
   already sufficient richness. If plants read too samey once you're
   eye-checking, a figure armature is the natural v2 — don't build it now.
2. **Embodiment = per-branch tapering outlines, shapely-unioned, then
   redrawn zone-by-zone through `effects/freehand.py`.** Not a single
   hand-walked contour around the whole tree (self-intersections at branch
   joints are a real mess to get right). Full mechanics in Phase 2 below —
   this reuses two things already in the codebase (the tapering-outline
   technique from `sources/drawing.py`'s velocity tube, and calling
   `FreehandModule.apply()` directly as a library function, not just as a
   user-facing effect) rather than inventing new geometry machinery.
3. **Never-overlap = per-figure placement retry against an accumulated
   shapely mask, all inside one `generate()` call.** No session/compose.py
   change — see Boundaries. This is smaller in scope than true AARON
   (which reasons against the WHOLE drawing's history including other
   layers) but delivers the "thing-ness" and foreground-first read the idea
   doc is after, with zero architecture change.

## Read first (in order, all in-repo)

1. `CLAUDE.md` — module purity, bounded params (this generator has many;
   don't let any float unbounded).
2. `docs/IDEAS-aaron-pass.md` §"AARON's mechanisms" and §A — the paper
   quotes, so you understand WHY carefulness-varies-along-the-body and
   never-overlap matter, not just what to build.
3. `axibridge/sources/two_hands.py` — precedent for a generator that runs
   substantial internal simulation/state (agents, turns) inside one
   `generate()` call and stays deterministic from `(seed, params)` alone.
   Copy its shape, not its mechanics.
4. `axibridge/sources/drawing.py`'s `_velocity_outline`/`_tangents`/
   `_velocity_widths` (the whole block, ~lines 186–269) — the exact
   hand-built offset-outline-with-varying-width technique you'll reuse per
   branch, swapping "speed" for "taper along the branch."
5. `axibridge/effects/freehand.py` — read the whole file. You will import
   `FreehandModule` and `FreehandParams` directly and call `.apply()` on
   your own candidate outline pieces — effects are pure, stateless classes,
   so this is safe, and it's the ONLY way to get Cohen's actual
   "carefulness parameter" behavior (confidence/tremor/correction/fatigue)
   without reimplementing a spring-damper hand controller from scratch.
   This is a new *kind* of cross-import (a source importing a specific
   effect class) — deliberate and fine, contrast with Boundaries below.
6. `axibridge/registry.py`'s `EffectContext` — trivially constructible from
   a source (`EffectContext(seed=derived_seed)`, `translation=(0,0)` since
   you're building in absolute mm already).
7. `axibridge/compose.py`'s `build_mask` (~lines 293–334) — not imported,
   but the even-odd depth-parity idea (nested filled loops) is worth having
   fresh; you will NOT need it here since a single tree-union rarely
   produces holes, but read Boundaries for why you don't import it anyway.

## Protocol

- `.venv/bin/python -m pytest -q` green before EVERY commit.
- Branch `feat/aaron-core-figure` from main. One commit per phase (skeleton,
  embodiment, placement, params/polish) is a reasonable split. NEVER main.
  Do not push.
- **Eye-check is the core loop, budget most of your time here.** Throwaway
  script in your scratch dir: generate at defaults, render to PNG with PIL,
  LOOK. Iterate skeleton shape and carefulness contrast until it reads
  "quasi-figurative, not a stick-and-blob diagram" BEFORE moving to
  placement. Then generate `count=4+` and confirm by eye that nothing
  overlaps and the arrangement reads foreground-first, not scattered.

## Phase 1 — skeleton (internal, not emitted directly)

A branching structure grown from a root point, bounded and deterministic
under `(seed, params)`:

- Root at `(0, size)` in the generator's own local frame (placement in
  Phase 3 translates the whole figure into bed coordinates — grow in local
  space, place in world space, don't conflate the two).
- Recursive growth: each node has a position, a direction, a "level"
  (0 = trunk), and spawns 1..`branch_count` children at the next level, each
  child's direction offset from the parent's by an angle drawn from
  `branch_spread` (0 = children continue nearly straight, 1 = wide fanning),
  length scaled by `taper` per level (`length_l = base_length * taper**l`),
  down to `branch_levels` deep. Use a **local** `random.Random(seed *
  1000003 + fig_index)` per figure, never the global `random` module — this
  is what makes multi-figure placement (Phase 3) reproducible.
- **Node cap, independent of the levels×branch_count combinatorics**: stop
  spawning new children once total node count crosses a fixed budget (a few
  hundred is a rich enough tree; `branch_levels=5, branch_count=4` would
  otherwise combinatorially explode past a thousand nodes, and Phase 3
  retries multiply that cost). Truncating growth at the cap rather than
  rejecting the params keeps `generate()` always-succeeds, matching the
  house rule (`drawing.py`, `sources/brush.py` in the sibling pen/brush
  brief) that a regenerate must never die on a parameter combination.
- **Balance constraint**: after growing, compute the mass-weighted centroid
  (weight each segment by `length * width` as a crude proxy for AARON's
  "behavioral level") and check its horizontal offset from the root x is
  within `balance_tolerance`. If not, regrow with a derived seed
  (`seed_attempt = base_seed * 31 + attempt`) up to `balance_attempts`
  times; if none pass, use the LAST attempt anyway (never fail
  `generate()` on an unlucky seed — bounded-attempts-then-accept is the same
  pattern as Phase 3's placement retries).

## Phase 2 — embodiment (candidate outline → freehand walk → closed path)

1. **Per-branch tapering outline**: for each skeleton branch (a poly-line of
   node positions), build a closed outline exactly like `drawing.py`'s
   `_velocity_outline` — left offsets, end cap, right offsets, start cap,
   closed — except the per-point width comes from `base_width * taper**level`
   (with a floor so tips don't vanish to zero-width) instead of a speed
   signal. Union ALL branch outlines into one shapely geometry
   (`unary_union`); this is the candidate silhouette. If the union comes out
   as a `MultiPolygon` (branches too thin/spread to overlap into one piece),
   keep only the largest-area piece and note the dropped fragments in
   RESULTS as a known edge case — don't try to force-connect them, that's a
   `base_width`/`branch_spread` tuning problem, not a correctness one.
2. **Carefulness zones**: for each point on the candidate polygon's exterior
   ring, find the nearest skeleton node and read off its level and its
   distance-from-nearest-tip. Quantize into 3 bands — **core** (level 0–1,
   far from any tip), **limb** (mid-level), **tip** (leaf nodes / near a
   branch end) — and split the ring into contiguous arcs per band (walk the
   ring in order, cut a new arc whenever the band changes). `tip` gets HIGH
   carefulness (high `confidence`, low `tremor` — a sure hand); `core` gets
   LOW carefulness (low `confidence`, high `tremor` — loose, searching).
   `carefulness_contrast` (0–1) scales how far apart the tip/core
   `FreehandParams` are from a shared midpoint — 0 = uniform hand everywhere
   (defeats the whole point, but useful for debugging), 1 = maximum spread.
3. **Redraw each arc** through `FreehandModule().apply([Path(points=arc,
   filled=False)], FreehandParams(confidence=.., tremor=.., correction=..,
   fatigue=.., seed=derived_seed, step=..), EffectContext(seed=derived_seed))`
   — pass OPEN arcs (not closed), so freehand's own closure-seeking never
   triggers per-arc; you want the WHOLE ring closed once, not each fragment.
4. **Concatenate the redrawn arcs in ring order and close.** Do not try to
   smooth the seam between two independently-hand-drawn arcs — the jump
   from one arc's last (freehand-distorted) point to the next arc's first
   point is itself an ordinary drawn segment once both are in the same
   point list, exactly like `ARCHITECTURE.md`'s region "continuous" stitch
   ("the seam a drawn connection wherever the effect moved the ends"). If
   arcs are reasonably long relative to how far freehand drifts (tune
   `confidence`/`tremor` if not), the seam reads as part of the gesture, not
   a glitch. Snap `points[0] == points[-1]` exactly at the end (same
   reasoning as `freehand.py`'s own closed-path snap) and set `filled=True`.

## Phase 3 — foreground-first placement (never-overlap)

```
mask = None  # accumulated shapely union of already-placed figures
paths = []
for i in range(params.count):
    for attempt in range(params.placement_attempts):
        fig_poly, fig_path = grow_and_embody(seed_for(i, attempt), params)  # Phases 1-2
        placed = shapely.affinity.translate(fig_poly, dx, dy)  # random position within bed margin
        if mask is None or not placed.buffer(0).intersects(mask.buffer(params.spacing)):
            mask = placed if mask is None else mask.union(placed)
            paths.append(translate_path(fig_path, dx, dy))
            break
    else:
        # exhausted attempts: place the LAST tried figure anyway — never fail
        mask = placed if mask is None else mask.union(placed)
        paths.append(translate_path(fig_path, dx, dy))
```

Candidate positions: uniform-random within the bed minus `params.margin` on
each side, sized so the figure's own bounding box fits (reject/retry
positions that would hang off the placement area before even doing the
overlap check — cheaper than a doomed shapely test). Figures are placed in
**generation order = draw order = z-order** (list order, per the IPR
contract) — this alone gives the foreground-first read: figure 0 claims
space first, figure 3 has to find what's left, exactly like AARON "putting
it where you can find space for it" against decision history. Each figure
should ALSO vary in `size` a little (e.g. ± a seeded fraction) so a
foreground/background size hierarchy emerges rather than a uniform grid of
same-size blobs — cheap and worth doing, it's most of what sells
"foreground-first" to the eye.

## Params

```python
class CoreFigureParams(BaseModel):
    count: int = Field(default=4, ge=1, le=12, title="Figures")
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")
    size: float = Field(default=80.0, ge=20.0, le=180.0, title="Size (mm)",
                        description="Approx. root-to-tallest-tip height")
    branch_levels: int = Field(default=3, ge=1, le=5, title="Branch levels")
    branch_count: int = Field(default=2, ge=1, le=4, title="Branches per node")
    branch_spread: float = Field(default=0.5, ge=0.0, le=1.0, title="Branch spread")
    taper: float = Field(default=0.6, ge=0.1, le=0.9, title="Taper")
    base_width: float = Field(default=10.0, ge=2.0, le=40.0, title="Base width (mm)")
    carefulness_contrast: float = Field(default=0.6, ge=0.0, le=1.0, title="Carefulness contrast")
    balance_tolerance: float = Field(default=15.0, ge=2.0, le=60.0, title="Balance tolerance (mm)",
                                     json_schema_extra={"group": "Fine tuning"})
    balance_attempts: int = Field(default=12, ge=1, le=60, title="Balance regrow attempts",
                                  json_schema_extra={"group": "Fine tuning"})
    spacing: float = Field(default=8.0, ge=0.0, le=40.0, title="Spacing (mm)")
    placement_attempts: int = Field(default=20, ge=1, le=100, title="Placement attempts",
                                    json_schema_extra={"group": "Fine tuning"})
    margin: float = Field(default=15.0, ge=0.0, le=80.0, title="Bed margin (mm)")
```

Every numeric bounded per house rule. `size`/`base_width` variance-per-figure
(the "foreground-first size hierarchy" note in Phase 3) is an internal
seeded jitter, not a new param — don't expose a dial for something the seed
already controls well.

## Tests (`tests/test_core_figure.py`)

- Determinism: same `(params, seed)` → byte-identical output across two
  calls.
- Every emitted path is closed (`points[0] == points[-1]`) and
  `filled=True`.
- `count=N` produces exactly N figures (paths, or path-groups if a figure
  ever needs >1 path — shouldn't with this design, one figure = one closed
  ring after Phase 2's concatenation).
- **Never-overlap**: with a generous `spacing` and modest `count`
  (e.g. count=3, spacing=10, on the default bed), reconstruct each figure's
  shapely polygon from its path and assert pairwise intersection area is
  ~0 — this is the test that actually proves Phase 3's retry loop works,
  not just that it runs.
- Balance: for a params set with `balance_tolerance` very tight (e.g. 2mm)
  and few `balance_attempts`, confirm `generate()` still terminates and
  returns a valid figure (the "accept the last attempt" fallback path).
- Node cap: `branch_levels=5, branch_count=4` (near-max combinatorics)
  still returns in reasonable test time (assert on wall clock loosely, e.g.
  under a few seconds) — this is the test that catches a missing/broken
  node cap.
- Carefulness actually varies: sample local wobble/deviation-from-smooth
  near a `tip`-zone arc vs a `core`-zone arc on the SAME figure and confirm
  they differ in the expected direction at `carefulness_contrast=1` (tip
  tighter, core looser) — at `carefulness_contrast=0` they should be close
  to equal. This is the test that would catch a zone-assignment bug that
  silently makes every arc use the same hand.
- Bounded params (spot-check a couple of `ge`/`le` violations 422 via the
  normal Pydantic path).

## Aesthetic target

At defaults, `count=4`: four plant-like closed silhouettes, each reading as
one continuous, coherent form (not a bag of overlapping blobs) — tapering
confidently toward their tips, loose and searching near the trunk/core, none
touching or overlapping another, roughly foreground-first in apparent size.
If every figure looks identical, the per-figure seed isn't reaching deep
enough into the skeleton growth (check you're deriving a real per-figure
seed, not reusing `params.seed` raw for every figure). If the whole
silhouette looks uniformly wobbly with no confident/loose contrast, the
carefulness zoning isn't reaching `FreehandParams` — check zone arcs are
actually getting DIFFERENT confidence/tremor values, not all defaulting to
the same midpoint. If figures visibly overlap, check the `spacing` buffer is
applied to the INTERSECTION test, not just to the stored mask.

## Boundaries

- Do not touch: `model.py`, `compose.py`, `session.py`, `estimate.py`,
  backends, any existing source/effect's params or ids, `effects/freehand.py`
  itself (import and call it, don't edit it).
- Do NOT import `compose.py` from this source — everything Phase 3 needs
  (shapely union/intersects/buffer) is plain shapely, no need for
  `build_mask`'s layer/pen-aware machinery. Importing `FreehandModule`
  directly (Read First #5) IS fine and deliberate — contrast: that's
  reusing a pure, stateless effect class as a library function; `compose.py`
  carries session/layer state a source has no business touching.
- No session-level "check against OTHER layers on the canvas" — never-overlap
  here is scoped to the figures THIS generator call places, per the idea
  doc's own B/A pull order (context-awareness across layers, via the
  sheet-snapshot asset, is a separate future roadmap item, not this one).
- Every numeric param bounded; deterministic under `(params, seed)`;
  `generate()` must always terminate and never raise on any in-bounds
  param combination (the node cap and the bounded-retries-then-accept
  patterns in Phases 1 and 3 are both there specifically for this).
- When done: `docs/plans/aaron-core-figure-RESULTS.md` with the acceptance
  screenshot's path, the default values you settled on after eye-checking,
  and a note on the MultiPolygon-fragment edge case if you hit it.

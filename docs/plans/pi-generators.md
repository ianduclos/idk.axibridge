# Plan: four generators/effects — scheduled unattended run on idkpi

You are Claude (Fable 5) running headless on the Raspberry Pi `idkpi`, in a
clone of axibridge at `~/idk.axibridge`. This plan was written by a Mac
session on 2026-07-10; treat it as the mission brief. The user is not
watching — finish the work, verify it, push the branch.

## Read first (in this order, all in-repo)

1. `CLAUDE.md` — operating rules. The resolve invariant, module purity,
   bounded params, undo discipline. Non-negotiable.
2. `docs/MODULES.md` — the module authoring contract you'll follow four times.
3. `docs/IDEAS-generators.md` §"framing" + §2/§3 and
   `docs/IDEAS-oehlen-pass.md` §3 — the aesthetic rationale behind each
   module below. The *why* lives there; don't skip it, the point is the
   uncanny/liminal quality, not feature completeness.
4. `axibridge/effects/freehand.py` + `tests/test_freehand.py` — the house
   style for exactly this kind of module (controller, seeding, tests).

## Protocol

- Environment: `.venv/` at the repo root is ready (deps installed, suite
  verified green on this machine). `.venv/bin/python -m pytest -q` before
  every commit. No hardware is needed; the suite is simulator-only.
- Git: `git fetch origin && git checkout -B feat/pi-generators origin/main`
  FIRST (the Mac may have pushed newer commits than this checkout has).
  One conventional commit per module. Push the branch to origin when each
  module lands (`git push -u origin feat/pi-generators`). **Never commit to
  main.** Never push to main.
- Verify visually, not just with pytest: for each module write a throwaway
  PIL render script under `/tmp/` (pattern: draw intention grey / output
  black, a small param sweep grid), render PNG, and actually look at it with
  the Read tool. Iterate until the aesthetic target below reads on the
  image. This step is where the value is; budget real time for it.
- If you run short on time or context, ship fewer modules *completely*
  rather than all four partially, in this priority order:
  continue_strokes → misremembered → grammar → two_hands.
- When done: update the shipped-markers in the two IDEAS docs and ROADMAP
  (same style as freehand's), and write `docs/plans/pi-generators-RESULTS.md`
  — what shipped, what you'd tune next, anything surprising. Commit that too.

## Module 1 — `effects/continue_strokes.py` (autocomplete as intrusion)

The machine finishes your sentence. For each open path in the layer, learn
the layer's own local stroke statistics and extend the path past its
endpoint with a sampled continuation — fluent but hollow, with a visible
seam where the machine takes over.

- Statistics, v1 (no neural anything): resample each path at a fixed step;
  build turning-angle sequences; fit an order-N Markov chain / n-gram over
  quantized turning angles plus a step-length distribution, pooled from the
  whole layer. Sample a continuation from the endpoint's trailing context.
- Params (all bounded, titled, described): `extension` (mm, ~1–150),
  `temperature` (0–1: sampling spread), `order` (1–4: context length),
  `both_ends` (bool), `seed`. Group anything fine-grained under
  `json_schema_extra={"group": "Fine tuning"}`.
- Closed paths (first==last) pass through UNCHANGED — you don't continue a
  closed thought. Preserve `filled`. Purity: new Path objects only.
- Seed mixing: `(params.seed * 31 + ctx.seed)` plus a per-path term, like
  freehand does — overlapping layers must differ, re-resolves must not.
- Aesthetic target: the continuation should be *plausible for a few mm,
  then noticeably wrong* — statistically fluent drift, not noise. On a
  layer of characterful strokes (test with freehand output as input), a
  viewer should be able to point near where each stroke stops being real.

## Module 2 — `sources/misremembered.py` (lossy recall of an image)

Not thresholding (exists), not halftone (exists): *recall*. Sample the
image sparsely, fit a small budget of primitives, draw the reconstruction —
big masses right, details confabulated.

- Read pixels via `assets.asset_store.grayscale(name, blur_px)` with the
  standard `image` asset param (`json_schema_extra={"format": "asset"}`),
  and apply the shared Image processing group (see how existing image
  sources use `image_processing.py`). Look at `sources/_pixelgen.py` /
  `sources/linescan.py` for the placement conventions (`width` mm, `rotate`,
  `show_map`); reuse `PixelGenParams` if it fits, don't force it.
- Core: extract structure (cheap edge/gradient field from the grayscale),
  then greedily fit `budget` primitives (long strokes following strong
  coherent edges; a few closed blobs for dark masses). Each primitive gets a
  confidence from the structure it explains.
- Confidence controls the mark: high → one long firm polyline; low → short,
  broken, searching marks (2–4 short segments with lateral scatter). Do the
  character in-module (don't depend on the freehand effect — the user can
  stack it on top for more).
- Params: `image`, `budget` (int, ~10–800 — THE dial: 40 = dream,
  400 = portrait), `width` (mm), `detail` (edge sensitivity), `seed`, plus
  the standard placement/processing params. `budget` must be tween-friendly
  (numeric) so an animation can "remember harder" over master_t.
- Deterministic per (params, image). Coordinates mm, ≥ 0. Call
  `registry.report_progress(frac)` in the fitting loop — budgets near 800
  will be slow on this Pi.
- Aesthetic target on a portrait/face asset: recognizable at arm's length,
  wrong in the details the way memory is wrong. If it looks like edge
  detection, the confidence→mark mapping isn't doing enough work.

## Module 3 — `sources/grammar.py` (shape grammar with a transgression budget)

A Stiny-style shape grammar that obeys itself almost everywhere — and
spends a small budget of deliberate, rule-aware violations at salient
locations. Near-order: a wrongness you feel before you can point at it.

- **Author in cubic bézier space** (user requirement). Internal geometry is
  cubic segments; motifs and rewrite rules operate on control points;
  flatten to polylines only at output (adaptive subdivision to a bounded
  `flatten_tol` mm param, default ~0.2). The IPR stays polylines —
  do NOT touch `model.py`.
- Ship 2–4 built-in grammars behind an enum (no rule editor — explicitly
  out of scope, see IDEAS-oehlen-pass UI notes). Suggestions: a
  branching/recursive motif, a tiling/band grammar, a radial one. Each rule
  rewrites a placed motif into transformed copies (affine on control
  points) with curvature — the bézier requirement is there so the output
  reads as *drawn curves*, not polyline scaffolds.
- Transgressions: after generating the obedient structure, rank rewrite
  sites by salience (proximity to symmetry axes, to the bounding-box
  center, to pattern-completing positions) and re-apply `budget` of them
  *violated*: rotated a few degrees, scaled off-module, rule swapped —
  parameterized by `violation` (magnitude 0–1) and `salience_bias` (0 =
  spend randomly, 1 = spend at the most salient sites).
- Params: `grammar` (enum), `iterations` (bounded so path count stays sane
  on a Pi — cap total emitted segments), `size` (mm), `budget` (int 0–16),
  `violation`, `salience_bias`, `flatten_tol`, `seed`.
- Aesthetic target: at budget 0 the output is cleanly formal; at budget 2–3
  with violation ~0.2 it should feel *haunted* — visibly regular, almost
  right. If violations read as glitch/noise, they're not rule-aware enough.

## Module 4 — `sources/two_hands.py` (negotiating agents)

Two line-agents with different characters take turns marking the sheet,
each responding to what's already there — completing, echoing,
contradicting, avoiding. Composition emerges from the conversation.

- Each agent: a small bounded genome (curvature preference, stroke length,
  lift frequency, jitter) — grouped params `Agent A` / `Agent B` via
  `json_schema_extra={"group": ...}` so the form stays scannable.
- Interaction params: `rounds` (bounded), `agreeableness` (imitate ↔
  oppose), `attention` (respond to the last stroke ↔ the whole sheet).
  A turn = perceive (sample existing stroke endpoints/directions near the
  chosen focus) → respond (start near/away, echo or contradict the local
  direction per agreeableness) → mark (stroke in the agent's character).
- **Pen split without new machinery**: a `draw` enum param
  `both | hand_a | hand_b`. Same seed + params ⇒ the identical
  conversation; the filter only selects whose strokes are emitted. Two
  layers with the same recipe and different `draw` values give the user a
  physical two-pen negotiation. Document this trick in the module docstring
  and keep generation order-deterministic so it actually works.
- Deterministic under seed. Coordinates mm ≥ 0 inside a `size` (mm) square.
- Aesthetic target: with agreeableness high the sheet should read as one
  fluent drawing by two moods; low, as an argument — marks blocking and
  crossing each other. If it reads as two independent scribbles, the
  perceive step isn't feeding the response.

## Boundaries

- Modules + their tests + the docs updates listed above. Nothing else: no
  UI work, no compose.py changes, no new endpoints, no model.py changes,
  no backend/serial code (the AxiDraw may be attached — do not open its
  port; nothing in this plan needs hardware).
- Every numeric param bounded. Every module deterministic under seed.
  Every effect pure. Occlusion metadata (`filled`, closure) preserved.

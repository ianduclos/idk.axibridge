# Changes

---

### 2026-09-09 — Stable animation random identity (Codex)
- affects: saved animation layers, effect/generator authors and cached renders.
- detail: optional `CanvasLayer.effect_seed` persists shared randomness for
  Animate/append keyframes; old layers fall back to their original ID-derived
  seed. Both context and cache consumers honor it. Equal seed zero remains
  deterministic across animation; numeric interpolation uses module types.
  Update other consumers before regenerating new animations; older code ignores
  this field and can reintroduce midpoint jumps. See docs/MODULES.md.

### 2026-09-09 — Magnetic corner recipes (Codex)
- affects: saved magnetic source recipes and bench consumers.
- detail: optional corner captures, XY editor state, canonical sizes, scatter
  strength bounds and locks accompany explicit magnets; only the magnets and
  drawing controls drive geometry. Older recipes gain defaults. New recipes
  require this source version to regenerate; update consumers before resuming
  them. Pole spacing thins whole routes after boundary filtering, before styling.

### 2026-09-08 — Assigned pen width in effect contexts (Codex)
- affects: effect authors, normal/region/tween resolve and cache consumers.
- detail: `EffectContext.line_diameter_mm` supplies the assigned output pen's
  mark width, with the existing 0.5 mm unassigned fallback. Enabled effect stacks
  include width in shape/tween cache keys. Ribbon consumes it for automatic
  strand density; no store reads or Node runtime are required by the effect.

### 2026-09-06 — Second Reading replay and placement contracts (Codex)
- affects: saved Second Reading recipes, bench consumers and source-module authors.
- detail: reading/control events now select retained response policies; Responsive
  defaults to single-pass responses without thick reinforcement. Historical study
  replay requires `historical_stacks=True`. Fit recipes retain stable overshoot
  coordinates and expose an inverse display transform; `placement_frame(params)`
  keeps generated source frames within the bed under orientation changes. See
  `docs/plans/second-reading.md` and `docs/MODULES.md` for the contracts.

### 2026-09-06 — Agent protocol documented (Codex)
- affects: agents working in this repository.
- detail: primary ownership, bounded Sol/Terra support and calibrated aesthetic
  review are recorded in AGENTS.md. Operational context remains in CLAUDE.md.

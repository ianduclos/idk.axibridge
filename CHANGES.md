# Changes

---

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

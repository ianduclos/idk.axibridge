---
project: idk.axibridge
state: active
updated: 2026-07-27
machine: mac+pi
summary: Two new modules on main — offset_fill (concentric-ring fill, topology-aware, with round_center) and the brush tool (paint/erase masses) — plus the pending UI round merged; suite 559 green, nothing plotted on paper yet.
next:
  - "Push main to origin — 48 commits ahead, never yet pushed (needs Ian's OK)"
  - "Pull the idkpi clone: the effect/source ROSTER changed (new offset_fill effect, new brush source) and tests/test_app.py pins it, so the shared suite fails there until it pulls"
  - "Bench: plot offset_fill (ring spacing vs pen width is the thing only ink settles) and a brush mass with a fill stacked on it"
  - "Tapered brush (radius from drawing speed) — the queued brush follow-up; per-point timestamps are already captured so it is a pure addition"
  - "Delete the now-merged local feature branches (ui-round-0726, offset-fill, and the six older merged ones)"
handoff_for: ian
---

# idk.axibridge — status

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

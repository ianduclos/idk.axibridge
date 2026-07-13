---
project: idk.axibridge
state: active
updated: 2026-07-13
machine: mac+pi
summary: Two green unmerged branches await Ian's merge call — animation-preview fixes (canvas preview mode, tray A⇄B sharpened, contact-sheet bake removed) and lineart v2 (flow-hatch/XDoG family + one-click stack + detail round); an 11-item URGENT fix list from first real use leads the ROADMAP.
next:
  - "Merge feat/animation-previews and feat/lineart-v2 into main (Ian decides order/push); on push, announce the removed /api/animation/contact_sheet in the CHANGES feed and pull the Pi clone"
  - Work the ROADMAP "URGENT fixes" list top-down (tray PNG popup preview, orientation coherence, image centering, effects-boxes collapse, …)
  - Install apple/ml-depth-pro + checkpoint into .venv (diagnosed missing, not a bug — ROADMAP urgent item 6)
  - Real-photo print test of a maxed lineart_edges layer (mass + ink_fill) — eye checks were on a synthetic subject
  - AARON pass items still queued — core-figure generator, sheet-snapshot asset, felt-tip color kit (linedraw v2 itself shipped)
handoff_for: ian
---

# idk.axibridge — status

**Session 2026-07-12 → 13, two branches, suite green on both (main baseline
301 → 308 with animation work → 351 with lineart).** Neither branch is
pushed or merged — never push without asking.

**`feat/animation-previews`** (4 commits) — the "previews do nothing" fix:
- `/api/preview/sheet` + canvas preview mode: the centre canvas swaps to a
  grid page or tray sheet's REAL geometry with a banner + exit (before:
  only the invisible travel overlay changed).
- Tray A⇄B sharpened: same-kind/same-shape compat with named-field errors,
  auto-preview after capture/interpolate, legible A/B pickers, ⇄ disabled
  with a reason, `POST /staging/groups/{gid}/relayout` re-paginates a
  capture (or re-runs a batch from sources) at a new grid.
- Windows + time-curve demoted to an "advanced timing" fold; the
  **contact-sheet bake endpoint is REMOVED** (capture-sheet → insert-as-
  layers replaces it) — announce as a boundary change when this merges.

**`feat/lineart-v2`** (3 commits) — AARON §D shipped:
- Engine `sources/_lineart.py` (numpy/scipy first): ETF flow field, XDoG,
  Zhang–Suen thinning, angle-aware tracing, Jobard–Lefer streamlines with
  band windows/cross-hatch/dash, carefulness wobble via distance transform.
- `lineart_edges` + `lineart_hatch` generators (bands stack as layers, one
  pen each), `session.add_lineart_stack` one-click faithful/artistic
  presets (tuned on renders), ★ Create stack button.
- Detail round from Ian's first prints: skeletonized tracing, `resolution`
  ×1..2, `mass` + `ink_fill` (maxed edges layer holds as a full drawing);
  clip-backed generator layers now default `frame_follow=True`.

**URGENT list**: 11 items at the top of `ROADMAP.md`, dictated by Ian from
real use 2026-07-13 — includes a confirmed diagnosis for the Depth Pro
complaint (package genuinely absent from `.venv`, install task).

## Prior arc

Pi round 2 (bitmap-lines, contract_expand, region continuity, workbench
drawing), sheets v2, glyphgram, A/B capture series — see ROADMAP shipped
sections. Architecture invariants: `ARCHITECTURE.md`, `docs/MODULES.md`
(single resolve path; scrubbing never mutates stored state). Two AxiDraw
modes contend for the serial port — Mac-driven pi_ssh (default) vs the
disabled Pi-served service.

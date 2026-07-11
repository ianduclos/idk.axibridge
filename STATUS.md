---
project: idk.axibridge
state: active
updated: 2026-07-11
machine: mac+pi
summary: Pi round 2 merged (bitmap-lines, contract/expand, region continuity, workbench mouse drawing) on top of sheets v2, glyphgram, and A/B capture series; suite 301 green both machines; AARON pass 3 documented and queued.
next:
  - "Restart the live server AFTER saving the open untitled project (4 unsaved layers) — it predates glyphgram/contract_expand/bitmap-lines/draw-mode; hard-reload the browser tab too"
  - Try the new vocabulary on paper — bitmap-lines regions (continuous boundary), A/B interpolated series, glyphgram over freehand, drawn strokes through effect stacks
  - AARON pass item 1, the core-figure generator (docs/IDEAS-aaron-pass.md — the mechanisms are quoted from Cohen's 1988 paper)
  - Round-2 tuning notes in docs/plans/pi-round2-RESULTS.md; roadmap audit items (seed reroll, unsaved-work guard, perception pass)
handoff_for: null
---

# idk.axibridge — status

**Session 2026-07-10 → 11 (12 commits on `main`, suite 301 green Mac /
302 Pi).** The second unattended Pi run shipped all four round-2 tasks,
reviewed and merged `66ca43f`:

- **bitmap redesigned** — default `style="lines"`: paths keep their
  identity, vertices snap to the layer-anchored grid, segments become hard
  90° staircases; the old merged-raster lives on as `style="blocks"`.
- **contract_expand** — signed mm offset (buffer for filled, offset_curve
  for strokes); stacking gives onion rings.
- **region_boundary: cut | continuous** — continuous stitches each path
  below back into ONE pen-down line through the region (travel order via
  midpoint projection; cut pinned byte-identical).
- **workbench mouse drawing** — ✏ mode with raw/smooth/steps/zigzag/stitch
  modes; drawings ride the whole pipeline via `WorkbenchBody.paths`
  (scraps as `module="drawing"`, import live).

Also this arc: **sheets v2** (fixed framing so motion survives flipbooks,
crosshair registration marks, per-frame caches killing the
O(frames×pages×passes) resolve blow-up, one-layout UI), **glyphgram**
(asemic Hershey destruction, abstraction dial), **A/B capture series**
(canvas-toolbar A · B · ⇄ → n-step interpolated staged batch), slider
thumb/number desync fixed (range step="any" + our quantization), **Stop ⌂**
(stop returns carriage home, user-stop only), workbench stage polish.
Idea **pass 3 (AARON)** is in `docs/IDEAS-aaron-pass.md` with Cohen's 1988
mechanisms quoted and a ROADMAP section (core figures → sheet-snapshot
context asset → felt-tip color kit → linedraw v2).

Housekeeping: merged mission branches deleted local/remote/Pi; both Pi
mission logs + RESULTS docs in `docs/plans/`; `.claude/skills/pi` is the
scheduled-run runbook. **The live server on :2942 still runs pre-glyphgram
code and holds an unsaved 4-layer untitled project — save before
restarting** (see the unsaved-work-guard roadmap item, born of a real loss
on 2026-07-10).

## Prior arc

2026-07-10 uncanny push: freehand/bitmap/fat_tube effects, region layers
(resolve order `occlusion(regions(effects(transform(source))))`), ⚗
workbench + global scrap library, repo to private GitHub with idkpi dev
clone, Pi round 1 (continue_strokes, misremembered, grammar, two_hands).
Grid sheets + animation arcs: see ROADMAP's shipped sections and
`tests/test_sheets.py` / `tests/test_sheet_framing.py`.

Architecture and module contracts: `ARCHITECTURE.md`, `docs/MODULES.md` —
non-negotiable invariants (single resolve path; scrubbing never mutates
stored state). Deployment note: two AxiDraw modes contend for the serial
port — Mac-driven pi_ssh (default) vs Pi-served `axibridge.service` at
`idkpi:2942` (disabled by default).

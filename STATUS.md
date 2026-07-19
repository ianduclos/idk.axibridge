---
project: idk.axibridge
state: active
updated: 2026-07-19
machine: mac+pi
summary: Generator v2 rework (misremembered/glyphgram), the Generate-bench latch with coalesced undo, and the draw tool + response brushes (two supervised Sonnet agent runs) are all merged on main with the suite at 430; pen and brush tools are specced on the roadmap.
next:
  - "Bench eye-check on paper: misremembered v2 (tone/mass_style on real photos), glyphgram v2 continuity dial, draw mode + response brush plots"
  - Pull the idkpi clone to current main (lockstep after the merges)
  - Pen tool (ROADMAP 0b) then brush tool (0c) — agent briefs in the proven docs/plans format on request
  - Older URGENT-round eye-checks still open (see HANDOFF)
handoff_for: ian
---

# idk.axibridge — status

**Session 2026-07-16 → 19 (Fable, with two supervised Sonnet agent runs).**

- **Generator v2 pass** (from Ian's "blob machine / font airbrush" critique):
  `misremembered` masses now scrub the actual silhouette (field-clipped
  serpentine, `mass_style` keeps the v1 amoeba), a `tone` dial hatches
  mid-dark isophotes, per-seed anchor bias varies layouts; `glyphgram`
  distorts through one smooth field (strokes densified to ~mm vertices so
  they can bend) and a `continuity` dial chains ends into continuous
  almost-writing. Aesthetic rule recorded in auto-memory: structure-
  following marks, coherent fields, chaining — never uniform scatter.
- **Generate bench latch**: creating a layer latches the form — sliders
  live-edit it (auto-apply on release), `＋ New layer` unlatches keeping
  params; server merges consecutive regenerates of one layer into ONE undo
  entry (`RegenerateBody.coalesce`). Import/assets folded into a collapsed
  panel; sticky image/rotate/width/frame across generator switches;
  drag-drop an image/video onto the canvas imports + selects it.
- **Draw tool** (agent run 1, clean): `sources/drawing.py` — strokes as
  `[[x,y,t]]` params, first-class layer; `static/js/draw.js` canvas mode;
  brush presets. **Response brushes** (agent run 2, cut off at session
  limit, completed by supervisor): `parasite_line` + `eyelets` effects,
  `velocity_tube` render (speed-driven width), `response` preset. Two
  composition bugs found post-agent: decorations must skip closed paths
  (`on_closed`) and eyelets must run BEFORE parasite (else every dash end
  grows a ring) — 1447 lifts → 174 for the acceptance stroke. See
  `docs/plans/*-RESULTS.md`. `keep_centerline` now defaults off.
- Smaller: custom scrollbars; Settings no longer renders dicts as
  editable `[object Object]` (would have corrupted settings.json);
  `.row[hidden]` CSS fix (Create-stack row showed for every generator).
- **Roadmap**: pen tool (⚓ béziers, 0b) and brush tool (● circle brush,
  0c) specced under "make what exists comfortable"; eraser/hole question
  settled as hatch-based ink (no even-odd occlusion change).
- Agent-ops lesson recorded: worktree isolation is unusable here (PEP 660
  editable install always imports the main checkout) — agents work in the
  main checkout on feature branches; a stale agent test server holding the
  verification port produced one false verification round.

## Prior arc

URGENT round 11/11 (2026-07-13, orientation coherence via viewmap tags),
lineart v2, animation previews, Pi rounds, sheets v2, A/B capture — see
ROADMAP shipped sections and git history. Architecture invariants:
`ARCHITECTURE.md`, `docs/MODULES.md` (single resolve path; scrubbing never
mutates stored state). Two AxiDraw modes contend for the serial port —
Mac-driven pi_ssh (default) vs the disabled Pi-served service.

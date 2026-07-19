---
project: idk.axibridge
state: active
updated: 2026-07-19
machine: mac+pi
summary: Canon docs (CLAUDE.md/ARCHITECTURE.md/ROADMAP.md) audited and corrected against real drift; three build briefs written (pen+brush combined, AARON core-figure, perception-pass); Path.is_closed unifies a closed-path definition that had drifted three ways; suite at 432, all committed on main.
next:
  - "Bench eye-check on paper: misremembered v2 (tone/mass_style on real photos), glyphgram v2 continuity dial, draw mode + response brush plots"
  - Pull the idkpi clone to current main (lockstep after the merges — includes the compose.py/model.py/effects Path.is_closed refactor, behavior-neutral but touches shared files)
  - Run one of the three ready briefs when you want the work done: docs/plans/pen-brush-tools.md, aaron-core-figure.md, perception-pass.md
  - Decide the tween/geometry-as-params gap (forbid / arc-length-resample / leave documented) — flagged in docs/MODULES.md, deliberately not decided this session
  - Older URGENT-round eye-checks still open (see HANDOFF)
handoff_for: ian
---

# idk.axibridge — status

**Session 2026-07-19 continued (Sonnet 5, no Fable in the loop).**

Fable's own parting advice (previous session) was to spend remaining Fable
time converting judgment into durable artifacts before losing access — this
continuation picked up two items from that list with Sonnet 5 instead:

- **Canon-doc audit** (CLAUDE.md/ARCHITECTURE.md/docs/MODULES.md against
  actual code): fixed CLAUDE.md's resolve-order invariant, which had been
  silently missing `regions(...)` since region layers shipped (inconsistent
  with its own handoff bullet and with ARCHITECTURE.md, which was correct);
  documented `coalesce` in both files (shipped mid-July, was undocumented).
  **Bigger find**: ROADMAP's "occlusion doesn't reassemble even-odd holes"
  note — and TODAY's own brush-tool (0c) spec, built on the same claim —
  were both stale. `compose.build_mask` has reassembled nested holes
  correctly for occlusion, not just `hatch_fill`, since 2026-07-10
  (`test_filled_occlusion_mask_respects_nested_holes` proves it). Both
  corrected; the brush brief below reflects the real, better constraint.
  `docs/MODULES.md` gained a named "geometry-as-params sources" pattern.
- **Three build briefs** in `docs/plans/` (frozen-contract format, same as
  `response-brushes.md`): `pen-brush-tools.md` (combined per Ian's call —
  one philosophy doc for the tool-mode family, toolbar becomes a 4-way
  select/draw/pen/brush segment), `aaron-core-figure.md` (settles
  plant-morphology-over-figure-armature + reuses `effects/freehand.py`
  directly for Cohen's carefulness parameter + a self-contained
  never-overlap placement loop), `perception-pass.md` (agreement-as-
  vote-count line weight; a depth detector stays optional since Depth Pro
  isn't on the Pi venv).
- **Architecture critique** (Ian asked specifically about tween/frame-
  interpolation compatibility, closed-vs-open effect handling, and
  color/3D "curveballs"): found tween's same-generator lerp only blends
  scalar params, so geometry-as-params sources (drawing today, pen/brush
  soon) hard-snap their actual shape at t=0.5 instead of morphing — flagged
  as a real, deliberately-undecided design question, not fixed (Ian wants
  it left alone for now — his own idiosyncratic workflow depends on the
  current shape). Confirmed color/3D are both already correctly modeled
  (pen-per-layer; depth stays an asset-space signal, never a geometry axis)
  — validated as settled decisions, not gaps.
- **Two small fixes made from the critique**: `Path.is_closed` (model.py)
  replaces three drifted inline "is this closed" definitions
  (`compose.py` used `>2` points, `hatch_fill.py` used `>3`,
  `compose.build_mask` used the actually-correct `>=4`) — now one
  definition, swept into `compose.py` and 8 effects. Two new tests in
  `test_tween.py` actually exercise ARCHITECTURE.md's claim that "regions...
  tween... for free" (nothing tested this combination before) — confirmed
  true in both directions. Suite: 432 passed, 0 skipped when the port's
  free. Both changes committed on main (`86eb7fd`, `f850dd9`).

## Prior arc — 2026-07-16 → 19 (Fable, two supervised Sonnet agent runs)

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
  0c) specced under "make what exists comfortable." *Correction, 2026-07-19*:
  the eraser/hole caveat noted here at spec time ("occlusion mask
  over-covers a donut's hole") was already stale when written — occlusion
  has reassembled nested holes correctly since 2026-07-10; see the
  continuation session above and the 0c entry in ROADMAP.md.
- Agent-ops lesson recorded: worktree isolation is unusable here (PEP 660
  editable install always imports the main checkout) — agents work in the
  main checkout on feature branches; a stale agent test server holding the
  verification port produced one false verification round.

## Older history

URGENT round 11/11 (2026-07-13, orientation coherence via viewmap tags),
lineart v2, animation previews, Pi rounds, sheets v2, A/B capture — see
ROADMAP shipped sections and git history. Architecture invariants:
`ARCHITECTURE.md`, `docs/MODULES.md` (single resolve path; scrubbing never
mutates stored state). Two AxiDraw modes contend for the serial port —
Mac-driven pi_ssh (default) vs the disabled Pi-served service.

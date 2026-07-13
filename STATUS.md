---
project: idk.axibridge
state: active
updated: 2026-07-13
machine: mac+pi
summary: Both feature branches and the full 11-item URGENT round are merged and pushed (main 16fc350, suite 382, 12/12 live checks); what remains is Ian's bench eye-check of the behavior changes.
next:
  - "Bench eye-check the urgent round: centering feel, threshold band on a real photo, portrait width remap, viewAxis fader direction (one fader deliberately flipped)"
  - Real-photo print test of a maxed lineart_edges layer (mass + ink_fill) — eye checks were on a synthetic subject
  - AARON pass items still queued — core-figure generator, sheet-snapshot asset, felt-tip color kit
handoff_for: ian
---

# idk.axibridge — status

**Session 2026-07-13 (evening): URGENT round shipped 11/11.** Sonnet agent
waves orchestrated from a Fable session; plan in
`~/.claude/plans/generic-squishing-flask.md` (session-local), outcomes in
the ROADMAP's struck-through URGENT list and the `fix/urgent-round1` merge
(`16fc350`). Suite 359 → 382; a live Playwright/API pass verified all 12
checks including "portrait rotate reads 0, stores 270" and
resolve-bit-identical across view toggles.

Highlights:
- **Orientation coherence** (the big one): params stay machine-frame mm
  forever; the display layer maps once via schema tags
  (viewRotate/viewAngle/viewSize/viewOrient) in `static/js/viewmap.js` +
  `forms.js`. The portrait rotate=270 band-aids are gone. Includes a
  deliberate behavior fix: only the original-y viewAxis fader negates in
  portrait now (the x fader's drag direction changed).
- **image_threshold** is now a band select (`threshold_min`/`threshold_max`;
  legacy `threshold` loads byte-identical).
- **DELETE /api/assets** (+ "Clear unused assets" button) — unreferenced
  by default, `?force=true` for all, clips kept whole.
- Image generator output centers on the bed at add time (stacks stay
  band-aligned; clip-backed layers keep identity).
- Anim preview popup keeps the last frame during re-renders; menu bar
  (File/View) in the header; workbench picker split; linedraw
  `resolution` ×1..2; forms `<details>` groups persist open-state.
- **Depth Pro installed** on the Mac venv (checkpoint gitignored at
  `checkpoints/depth_pro.pt`, 1.8 GB; numpy moved to 1.26.4, suite green).
  The Pi venv does NOT have it.

Earlier the same day: `feat/animation-previews` + `feat/lineart-v2` merged
and pushed (see previous entry's contents in git history); the removed
`POST /api/animation/contact_sheet` and the threshold param rename are both
announced in the CHANGES feed. Pi clone pulled to `16fc350` — Mac and Pi in
lockstep.

## Prior arc

Lineart v2 (flow-hatch/XDoG family, one-click stack), animation previews,
Pi round 2, sheets v2, glyphgram, A/B capture series — see ROADMAP shipped
sections. Architecture invariants: `ARCHITECTURE.md`, `docs/MODULES.md`
(single resolve path; scrubbing never mutates stored state). Two AxiDraw
modes contend for the serial port — Mac-driven pi_ssh (default) vs the
disabled Pi-served service.

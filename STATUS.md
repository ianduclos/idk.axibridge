---
project: idk.axibridge
state: active
updated: 2026-07-07
machine: mac+pi
summary: Animation v1.0–v1.4 shipped and e2e-verified; save diagnosed and fixed (stale-file pruning + zombie-asset resurrection, saved-feedback UX, ⌘S); user favicon wired in.
next:
  - Restart the live server/app — it ran OLD code against NEW static files all session (version skew explains most reported weirdness); confirm save behaves after restart
  - Canvas zoom & pan (wheel zoom + drag pan in canvas.js, display-only)
  - Easing / >2 keyframes if linear A→B starts to feel limiting (ROADMAP)
handoff_for: null
---

# idk.axibridge — status

July 2026 animation arc, five use-driven rounds in one long session (18
commits `5367bcc..d02f93e`, suite 177 passing): frame-sequence assets with
video import + progress SSE; master timeline scrubbing through the single
resolve path; one-click animate; timeline windows; per-layer frame offset
(frame units) and **clip-follow** ("clip follows timeline"); exclusive tween
in-betweens; cascade delete with un-animate; plot-time crop (guide/bed/
custom); pywebview app shell (`launch/AxiBridge.app`) with in-app server log.
The canonical **frame-ladder recipe** is documented in `ROADMAP.md` (v1.4
section); design rationale in the animation sections there and in auto-memory.

Save investigation (2026-07-07): the user's real project (`~/AxidrawProjects/
untitled`) loads/resolves/re-saves cleanly on current code — the hard failure
was almost certainly **version skew** (the live server process predated the
session's commits but served the repo's current JS, so new frontend calls hit
old endpoints). Two genuine defects found and fixed with regression tests:
save never pruned stale files, so `load_project` (which reads every file in
`assets/`) resurrected deleted assets — e.g. a re-imported shorter sequence's
old tail frames — and dead `gen-*.svg` snapshots piled up; and saving gave no
visible feedback outside the Plot-tab log (now "saved ✓" on the button + ⌘S).

Architecture and module contracts: `ARCHITECTURE.md`, `docs/MODULES.md` —
non-negotiable invariants (single resolve path; scrubbing never mutates
stored state). Deployment note: two AxiDraw modes contend for the serial
port — Mac-driven pi_ssh (default, live-verified) vs Pi-served
`axibridge.service` at `idkpi:2942` (disabled by default). See
`../../02_Areas/__claude/SYSTEM.md` arms table.

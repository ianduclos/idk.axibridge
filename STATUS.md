---
project: idk.axibridge
state: active
updated: 2026-07-07
machine: mac+pi
summary: Animation v1.0–v1.4 shipped and e2e-verified (frame sequences, master timeline, clip-follow frame ladders, cascade/un-animate delete, plot crop, pywebview app shell); project save is reportedly broken and un-diagnosed.
next:
  - Fix project save (user-reported, un-diagnosed — see HANDOFF.md)
  - Restart the user's live server/app so it picks up v1.4 (was on old code)
  - Canvas zoom & pan (wheel zoom + drag pan in canvas.js, display-only)
  - Easing / >2 keyframes if linear A→B starts to feel limiting (ROADMAP)
handoff_for: claude-axibridge
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

Architecture and module contracts: `ARCHITECTURE.md`, `docs/MODULES.md` —
non-negotiable invariants (single resolve path; scrubbing never mutates
stored state). Deployment note: two AxiDraw modes contend for the serial
port — Mac-driven pi_ssh (default, live-verified) vs Pi-served
`axibridge.service` at `idkpi:2942` (disabled by default). See
`../../02_Areas/__claude/SYSTEM.md` arms table.

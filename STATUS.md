---
project: idk.axibridge
state: stable
updated: 2026-06-13
machine: mac+pi
summary: Deployed and hardware-verified — pi_ssh backend runs detached remote jobs (plots survive Mac sleep), 10 plotterfun generators with live param preview.
next:
  - Canvas zoom & pan (wheel zoom + drag pan in canvas.js, display-only)
  - Collapsible panels / collapsed-by-default effect steps
  - Drag-to-reorder layers; keyboard nudge/duplicate/tab shortcuts
handoff_for: null
---

# idk.axibridge — status

Seeded 2026-06-13 by the hub from repo docs and git history; refine on next
real session. `next` mirrors the top of `ROADMAP.md` (near-term UI comfort);
the full ordered list with rationale lives there. Architecture and module
contracts: `ARCHITECTURE.md`, `docs/MODULES.md` — non-negotiable invariants.

Deployment note: two AxiDraw modes contend for the serial port — Mac-driven
pi_ssh (default, live-verified) vs Pi-served `axibridge.service` at
`idkpi:2942` (disabled by default; start it for plots that must survive the
Mac sleeping). See `../../02_Areas/__claude/SYSTEM.md` arms table.

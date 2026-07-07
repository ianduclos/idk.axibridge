---
project: idk.axibridge
updated: 2026-07-07
entries: 1
---

### Fix project save — opened 2026-07-07, owner: claude-axibridge
- done: nothing — user reported "we need to fix save" at session end, no
  diagnosis yet (symptom unknown: could be an error, silent no-op, or bad
  round-trip)
- next: reproduce — save a project containing the new animation state (a
  frame sequence, a clip-follow layer, a tween) via `POST /api/project/save`
  and reload it; check `axibridge/project_io.py` against fields added this
  session (`frame_offset`, `frame_follow`, sequence assets `clip#NNNN.jpg`,
  removed TweenParams `sweep_from/to`) and generator SVG snapshots
- blockers: none (needs a repro first)
- context: `axibridge/project_io.py`, `axibridge/session.py` (save path),
  `tests/` has no save round-trip test covering v1.0–v1.4 fields — write one
  as the repro. Session work: commits `5367bcc..d02f93e`, ROADMAP.md v1.4
  section has the frame-ladder recipe.

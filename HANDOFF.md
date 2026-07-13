---
project: idk.axibridge
updated: 2026-07-13
entries: 1
---

### Merge the two feature branches — opened 2026-07-13, owner: ian
- done: `feat/animation-previews` (4 commits, suite 308) and
  `feat/lineart-v2` (3 commits, suite 351) both complete, reviewed,
  committed, green; neither pushed nor merged.
- next: Ian picks merge order (they're independent; lineart branched from
  main, not from the animation branch) and says push. After push: append a
  CHANGES.md feed entry for the removed `POST /api/animation/contact_sheet`
  (Pi clone + any script calling it must switch to capture→insert), and
  `git pull` the idkpi clone to keep Mac/Pi in lockstep.
- blockers: none — waiting on Ian's call (house rule: never push unasked).
- context: STATUS.md body lists both branches' contents; ROADMAP.md top has
  the URGENT fix list that should drive the next working session.

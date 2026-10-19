"""The synthesis bench's package (S4, 2026-10-19).

Design: docs/synthesis-bench/design-2026-10-19.md; build plan:
docs/superpowers/plans/2026-10-19-synthesis-bench-build.md (S4).

- `kit/` — the research gesture kit, frozen for THIS bench (a separate copy
  from Gesture Studies', so refreezing it never moves a study or a kept
  study layer); written by `tools/synthesis/freeze.py`, never edited by hand.
- the hand library is Gesture Studies' (`_gesture_studies/library/`,
  append-only, content-addressed), read through `frozen_library`.
- `frozen_library` and `devices` are Gesture Studies' own modules loaded a
  second time as modules of this package (`_shared.load`), so their `.kit`
  imports bind to this kit: one source, two kits.
- `engine` plays a score (the executor `kit/_synth.py`) into app paths per
  score layer, with the measuring devices laid on.
- `gallery` — the bench's starting points (the writers, every Gesture Study as
  one sealed layer).

Importing this package is light: the kit loads on first use.
"""

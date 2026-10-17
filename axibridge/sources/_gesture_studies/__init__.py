"""Gesture Studies — saved pieces with their own controls, one bench.

Spec: docs/superpowers/specs/2026-10-17-gesture-studies.md. A study is a
frozen gesture-kit recipe (or, for the first study, Hand Drift params) plus
the few controls that matter for it; everything else in the recipe is fixed.

- `kit/` — the research gesture kit, frozen (header + `kit/FROZEN.json` name
  the research commit; written by `tools/gesture_studies/freeze.py`, never
  edited by hand). numpy / scipy / shapely only. The app never reads
  `tools/` or `.local/`.
- `library/` — every generative hand / tempo / dance trail of the research
  library (policy gate applied at freeze time), content-addressed and
  append-only; read through `frozen_library`.
- `studies/` — the built-in studies (`<id>/study.json`, order in
  `index.json`). Saved studies live in the machine-level store
  (`axibridge/gesture_studies_store.py`).
- `studies.py` — the study format, control validation, recipe resolution.
- `engine.py` — runs a resolved study (kit, or the Hand Drift engine for the
  Hand Drift study) to app paths.

Importing this package is light: the kit and library load on first use.
"""

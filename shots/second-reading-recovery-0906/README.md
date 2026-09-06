# Recovered baseline and pre-review experiment

A/B/C are First / Shape / Relation. Rows: seeds 1, 4, 12, 23, 42, 91.
Columns: turns 5, 6, 8, 12, with exact shared prefix/input through turn 5.
`recipes.json` records parameters and decisions; `exchanges.png` isolates input
and the first answer. SVGs retain precise per-cell geometry.

K unchanged B3-4; L grid-snapped vertices; M alternating ±12 mm path translations;
N removes only turn 6. Sol read these without the key, then read sequences.
The lead/reviewer reports are in `docs/reviews/second-reading-0906-{lead,sol}.md`.
This is a calibration probe, not an aesthetic benchmark or automatic score.

`recovery-checks.json` verifies all 30 original historical SVG/decision cells.
`experiment-before.py` preserves pre-review geometry. Reproduce with:

```
.venv/bin/python tools/second_reading_recovery_study.py --before --output /tmp/second-reading-before
```

The final experiment and alternating captures live in the sibling
`second-reading-recovery-final-0906` directory. Never overwrite the original
`second-reading-0905` study.

# Second Reading: mixed construction study, 5 September 2026

Ian found the first slice too geometric and predictable. The subsequent
organic experiment overcorrected toward the homeostat's coiling signature.
This revision keeps broad curves and restores hard turns, adding two actions:
fold (an open, unequal return through an existing interval) and graft (unequal
offshoots attached at different positions on a new trunk rooted in a passage).
Concentration is less frequent and its winding is reduced. Passage construction
is inherited during echo and extension. This is an experiment, not an aesthetic
success established by the new action names.

Open overview.png for all six seeds, or seed-12.png / seed-23.png for individual
rows. Each row shows the shared prefix at turn 4, three continuations to turn
12, and a fixed synthetic human intervention with continuation A. JSON bundles
retain the full recipes and metadata; SVGs retain the actual rendered geometry.
Regenerate using `tools/second_reading_study.py --output shots/second-reading-mixed-0905`.
The original and rejected organic studies remain in their separate directories.
Earlier study images document earlier engine versions; their recipes are not
version-pinned executables of those historical engines.

## Visual judgement

Seed 12 A is among the stronger cases: the tight vertical passage acquires a
broad, loose connection to the right-hand offshoots. The difference in extent
and construction matters more than the small knot alone. Seed 91 B also gives
the small opening a different context through a much larger curved enclosure,
although that enclosure risks becoming an obvious framing device.

Seed 23 A/B/C is a weak case: successive additions keep decorating the same
left-hand branch while the isolated right stroke remains largely inert.
Seed 42 C similarly thickens a bundle without much change in its role.
Folds and grafts are distinguishable, but can still become recognizable motifs.
The next iteration should examine when to leave a target and how an echo can
retain only a consequential part of a relationship. Do not add a seventh action
to cover up repetitive scheduling. No global harmony score is proposed.

Human capture now removes fine chatter and rounds soft bends, preserving
endpoints and supported hard corners. New strokes record smoothing 0.6; old
recipes default to 0 and retain their original input geometry. This particular
study's synthetic polyline intentionally remains a cornered, legacy stroke.

## Verification

1,232 tests pass, including real browser acceptance; frontend build and
TypeScript checks pass. Mechanism checks cover fold reversal and bounded width,
graft attachments and unequal reach, capture smoothing/corner retention,
whole-curve target dependence, replay, future-only events and saved geometry.

54 cold generations at the full 64-turn bound (six seeds, three reach and
persistence values) took at most 104 ms; warm generation at most 0.066 ms.
Maximum output in this sample was 6,424 points. These are local Python generation
measurements, not new HTTP latency measurements. Raw data is in
full-bound-performance.json. Paper judgement remains outstanding.

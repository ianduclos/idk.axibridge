# Second Reading — response before style, 5 September 2026

Ian's correction: the first version answered human input with perceptible
novelty. The later mixed grammars produced similar, increasingly entropic
results. A successful response can concern human input, earlier machine ink,
or both; the latest mark need not always receive the answer.

## What changed

Attention lasts several turns, but the operation can change while attention
stays on a passage. Recent repetitions of the same target/action reduce its
selection weight. Older, less-answered passages remain eligible. Recurrence
still controls the preference for older material; it is not an input-following
on/off switch. No global harmony score or compulsory alternating cycle.

Five operations now use actual target geometry: extension carries its changes
of direction forward; echo transfers the whole passage under unequal scale and
rotation; traversal uses two contours' anchors and interiors; surround borrows
a contour and returns around a substantial space; concentration makes a short
physical darkening at pen-scale spacing. Fold/graft templates and noisy guide
following are retired from responses. The opening still mixes a loose curve
with an articulated passage. Human corner-aware smoothing remains.

The darkening uses six actual paths within approximately 0.9 mm, not a preview
stroke-width effect. This is a small first step toward differences in visual
authority, not an equivalent of the paintings' colour, opacity or material range.

## Inspect the controlled intervention study first

`interventions.png` holds seed 12 and its turn-4 prefix constant. Each row inserts
a different synthetic mark at turn 5: a crossing, an open hook, a short angular
interruption. Columns show the shared prefix, input, one answer, four answers,
and an alternative continuation of exactly that input. All use the same base
stream; only the explicitly labelled alternative branches at turn 6, seed 29.
These are controlled marks, not recordings of Ian drawing.

`interventions.json` stores all 15 recipes and action/target histories. Each
cell also has its own SVG. Reproduce with:

```
.venv/bin/python tools/second_reading_interventions.py
```

The crossing's first answer links its left end into older material; subsequent
work travels toward its far end. The hook produces a larger enclosing response.
The small interruption receives a much wider return. These are distinguishable
consequences of the input, rather than the same motif translated nearby.
The alternative column sometimes makes a useful different answer and sometimes
mostly a quieter one; branching does not guarantee an equally strong drawing.

The full six-seed study (`overview.png`, per-seed panels, JSON and SVGs) is also
retained. Seed 1 A has a more convincing difference of extent than the previous
small bundles. Seed 23 A still gets congested around an established cluster.
Seed 91's human case also converges on a knot despite a long input. Many curves
remain too similarly fluent; not all of their crossings earn their place.
These weaknesses are part of the evidence, not excluded seeds.

Next evaluation should happen through Ian's own alternating turns. The useful
question is whether an answer offers a next move he would not otherwise have
made. Do not translate these visual findings into an automatic beauty score.
Paper remains untested.

## Reproducibility and verification

Recorded events, exact prefix preservation, branch switching, saving and the
single resolve path are unchanged. Synthetic tests independently check response
to interior shape with identical endpoints, both-target traversal, selective
nonresponse to ignored ink, reduced preference for repeated answers, and the
physical extent of enclosures and darkening. Historical study images document
older engines; recipes are not pinned to historical engine code.

`full-bound-performance.json` records 54 full 64-turn generations across six
seeds and three values each of persistence and reach. These are Python cold/warm
generation timings, not browser or HTTP latency measurements.


Final verification: **1,234 tests passed, 1 skipped**. The skipped app-shell
spawn/terminate test detects Ian's running server on port 2942 and deliberately
leaves it alone; confirmed by a focused rerun with skip reasons. All bench
acceptance tests ran. Frontend build and typecheck pass. Maximum measured cold
generation: 73.7 ms; warm generation: 0.053 ms; maximum 7,520 output points in
this sample. No plotting or hardware commands were sent.

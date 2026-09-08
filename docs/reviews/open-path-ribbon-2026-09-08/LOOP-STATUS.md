# Loop sample refinement and stress tests

Ian accepted the corner direction and asked about unevenness near the loop's
tight return, explicitly allowing it to remain if a fix would be disruptive.

The loop fixture itself had misaligned Bezier handles. Its lower sampled joint
turned abruptly by 4.47 degrees. A three-way probe compared the committed sample,
denser sampling alone, and aligned tangent handles with finer return sampling.
Denser sampling retained the crease. The aligned sample removed that contribution
without introducing a new width treatment.

Only the middle cubic's control points and sample count changed: its handles now
align geometrically with both adjoining curves, and the tight return is sampled
at 260 intervals instead of 65. The first and last cubics stay unchanged. The
offset, width profile, corner union and masking algorithms are unchanged. This
corrects the supplied example; it is not a smoothing pass applied to user paths.

`loop-sample-check.cjs` failed on the old sampled joint and passes now.
`loop-bend-evidence.py` compares against baseline 6617aed and writes
`loop-bend-probes.png`. At width 24 the corrected return is cleaner. At width 60
the inner boundary still has a cusp: excessive width relative to a tight bend
remains a separate geometric limit. No claim of universally even spacing.

The final bounded stress sweep is in STRESS.md: 156 configurations including
short/duplicate-point paths, multiple corners, reversed paths, near-reversals,
high strand counts, and both mask orders. It found no crash, invalid coordinate,
unmasked endpoint drift, mutation or nondeterminism. Heavy zigzags took around
1.7 seconds, and one masked near-reversal produced 254 fragments. Those are
performance/complexity limits, not a guarantee of visual quality.

Existing geometry and overlap checks and the six-fixture browser checks pass.
The inline comparison opens on Loop. Ready for Ian's visual check; no paper or
hardware test and no production application change.

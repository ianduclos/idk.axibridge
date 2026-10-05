# Pace experiment — round 1

Hypothesis: redistributing inherited turning along a curve can make one passage
nearly hold its direction while another spends that turning quickly. Change the
fundamental course before migration, without another decorative oscillation.

## Source

Only `t_meander.js` changes the generator. Added `paceCurve(P, rng, F, amount)`
immediately before `crossings`; `seedChannels` calls it in its local `mk`.
The function unwraps segment headings, re-times them with one broad low-rate
interval and a separate faster interval, integrates a new curve, and distributes
endpoint error along its length. Displacement is bounded to 30mm and the available
frame margin. It resamples at 1.5mm before the existing seed smoothing/wiggle.
Independent stream `(seed,6210,channel index)` leaves existing RNG consumption
unchanged. Prototype `pace:0` skips the experiment. No UI, density, or migration
code was changed. `original/t_meander.js` preserves the original; `round1/`
contains the complete source fragments and local build script before round 2.

## Visible evidence

Actual rendered populations inspected at `round1-sparse.png`, `round1-full.png`,
and `round1-close.png`; seeds 5,13,18,24 in prescribed order. Baseline sparse
population is `baseline-sparse.png`. Observations are provisional for Ian.

1. Seed 18: the left passage becomes a long nearly flat entry that tips into a
   narrower vertical run. The change of authority is useful; its tiny internal
   hooked corner is still rather mannered. The detached bottom oval is weaker.
2. Seed 5: concentrated folded ink near the middle reads more clearly against
   broad simple arcs. But the large trunk loses its original almost-step shape,
   becoming a simpler bow: a loss of distinct character as well as a cleanup.
3. Seed 13: the long right-hand arc now has a notably flatter lower passage;
   the floating central half-circle with terminal hooks remains generic and
   less consequential. Several short marks don't establish a relation.
4. Seed 24: lower curve becomes a narrow teardrop. It changes shape substantially
   but is more uniform, and repeated lower rails are bland. Preserve as a dud
   rather than claim every seed improved.
5. Full recipe: fundamental changes survive, but dense curved stripes still
   dominate the page. Seed 18 gives more oppositional flat/sharp passages;
   seeds 13/24 still risk decorative fans and contour-like repetition. This
   experiment does not address that density behavior.

Close views use explicitly recorded 100x70mm windows, one per seed, and include
weak/ambiguous results. They are not a selection of winners.

## Mechanical checks

`sh build.sh`; prescribed sparse/full `sheet.js` generation; original pinned
Python `shoot.py` for screenshots; `node checks.js` all passed. The checks cover
helper purity and determinism, start/end anchoring within resampling tolerance,
and repeated full outputs for all eight seed/recipe combinations. Every final
coordinate was finite and within the 300x218mm bed; all outputs were below 100m.
Measured sparse ink 0.869–1.443m; full ink 14.029–24.928m, saved exactly in
`round1-checks.json`. No aesthetic thresholds, hardware, or production tests.

## Risks / next critique

Endpoint correction can partly undo desired pacing, especially when available
margin reduces the whole displacement. Re-timing can move a second trunk's
crossing away from the original crossing test, although it stays within bed.
Migration then amplifies small differences, so the hypothesis isn't isolated
from event topology. Uniform teardrops and generic curled terminals are real
weaknesses. Round 2 should remain an independent pacing investigation, guided
by neutral review, with no convergence or integration into other experiments.

## Round 2 — one hinge, independent continuation

The neutral review valued the large enclosure/satellite in 18 and the stacked
lobes in 47, but found 24 emblematic and full82 too equally busy. I inspected
the lead's current 0.1mm R sparse/full populations, including 47/82, and close
views before changing the source. Thin lines make tributaries and gaps legible;
I reject my earlier impulse to treat all full density as saturation. Density
settings and source are unchanged.

Exact additional source changes: `t_meander.js` adds `hingeCurve` after
`crossings`, then calls it on channel0's selected present after migration and
window/trim/uncoil, before bundles. It identifies opposed turning on two 24mm
neighbourhoods, partially straightens a 28mm approach toward its chord, caps
movement at 6mm, and leaves all other points and channels alone. Curves without
an appreciable transition stay themselves. The tiny-turn cutoff is a geometric
noise tolerance, not an aesthetic score. `hinge:0` disables this round only;
round1 `paceCurve` remains unchanged. No RNG is consumed by round2. An initial
audit found one new centreline crossing in 82; the final call backs displacement
off by halves, or retains the original, if its interchannel crossing counts
change. This protects those counts, not a mathematical guarantee of all topology.
Round1 simulation events and other channel centrelines remain exactly equal.

`close.js` now uses 0.1mm preview strokes. Local `round2-sparse.json` and
`round2-full.json` extend the common recipes with now-disclosed 47/82, preserving
settings and seed order. Source snapshot is `round2-source/`; `round1/` is frozen.

Visible gains and limits, from actual `round2-sparse.png`, `round2-full.png`,
`round2-close.png` (all six seeds, plus close windows for18,24,47,82):

1. Sparse18 keeps its hanging enclosure and little satellite. Its passage into
   the diagonal junction becomes slightly more planar, leaving the opposing
   rounded passage. This is restrained; the unresolved junction carries more
   interest than the size of my intervention.
2. Sparse47 keeps the stacked-lobe construction and irregular lower junction.
   A straighter shoulder makes its lobe-to-lobe transition more abrupt. Full47
   changes far more than the small centreline edit implies, with a new central
   ring-like tributary pattern; that is a mixed result, not reliably better.
3. Sparse24 remains a compact teardrop/emblem. The small shoulder change doesn't
   cure the weakness. I preserved this failure rather than introduce new surface
   motifs or change every lobe merely to distinguish the round.
4. Sparse5 has practically no visible change;13 slightly changes its long
   passage;82 retains its loose lobes and unresolved crossings. Full82 still has
   too many similar patches of authority. A local hinge alone is insufficient
   for that criticism, and I left the density behavior for a separate decision.
5. Full13/18/24 have substantially different tributary populations because
   density grows from changed geometry. Some patches get more particular
   direction, but this downstream amplification makes causal aesthetic claims
   provisional. Thin strokes show continuity and interruption more usefully
   than the first local thick previews did.

Mechanical evidence: `check-round2.js` checks helper purity, endpoints, point
count and 6mm displacement; repeats all 12 outputs; checks finite coordinates,
bed bounds,100m and250k point budgets; compares simulation events and untouched
channel centrelines to `hinge:0`; records before/after centreline crossing counts
in `round2-checks.json`. These checks deliberately say nothing about beauty.
No physical plotting or user acceptance has been verified.

## Round 3 — explicit, strongly unequal cubic controls

Ian approved a bolder third round after finding the first two conservative.
This round intentionally drops the 6mm movement ceiling and crossing-count
guard. It replaces the round2 hinge in the current engine; `round2-source/`
and `round1/` stay frozen. No convergence with the other makers.

Exact source mechanism: `t_meander.js` replaces unused/current `hingeCurve`
with `bezierPace(P,speed,rng)`. Around a substantial inherited turn, selected
by accumulated signed curvature over neighbouring arclength, a roughly
75–95mm passage becomes one explicit cubic. The approach occupies 1.2 times
the selection radius; the escape .85 times. Its incoming handle is
0.9–1.55 times the original passage's arclength, its outgoing handle only
0.055–0.15 times. Incoming direction turns sideways by 0.15–0.85 radians;
outgoing direction rotates against the turn by 0.45–1.9 radians. This permits
overshoot and tight foldback, rather than retaining original endpoint tangents.
Control points clamp to the bed's 5mm inner margin: the cubic's convex hull
provides the geometry bound. Cubic sampling depends on control-polygon length;
selected speeds interpolate to match the new point population. Untouched
prefix/tail points remain exact.

The post-migration call rewrites channel0 plus, with a fixed independent
stream, sometimes the longest eligible minor. In these six seeds, only18
also rewrites a minor. Existing simulation RNG consumption is unchanged;
new streams are `(seed,6212,channel id)` and `(seed,6213)`. `bezier:0` gives
the pre-hinge round1 geometry. `paceCurve` from round1 remains. Debug channel
metadata records actual four cubic controls and measured handle ratio.
All helpers remain inside existing `t_meander.js`; build concatenation unchanged.

Observed actual incoming/outgoing handle ratios, after bed clamping, range
7.5:1–15.5:1. These are strongly unequal controls, not a renamed smoothing pass.
Endpoint positions of the replaced passage still connect to its old course;
tangents, local crossings, silhouette, and displacement magnitude are intentionally
free. Simulation events remain old events: they describe the unedited migration,
not newly-created drawing intersections. This is a relevant limitation.

Actual six-seed whole sparse/full populations and recorded close views inspected:
`round3-sparse.png`, `round3-full.png`, `round3-close.png`,
`round3-full-close.png`, all at0.1mm strokes. Gains/losses remain provisional:

1. Seed5 replaces a smoothly folded middle with a long almost-horizontal brim
   and abrupt reversal. The close shows one curve spending much more time on
   its approach than its escape. Broad quiet upper/lower passages remain. The
   narrow brim also risks an overly clean mechanical gesture.
2. Seed18's inner rounded lobe becomes a long diagonal passage and very short
   turn back. Its large hanging enclosure now has a pointed lower approach,
   while the small satellite survives. This is visibly more consequential
   than round2. The narrow doubled diagonal may read as a bar; that possibility
   is a cost, not evidence of intended figuration.
3. Seed24 gains a hanging upper passage with a tight upward recovery into the
   junction, competing with its lower teardrop. It is less uniformly emblematic,
   though the old teardrop remains. Full24 amplifies into a large concentric
   tributary mass: a useful authority imbalance but a risk of decorative rings.
4. Seed47 loses some useful lower irregularity and two sampled crossings.
   A broad left approach replaces the earlier compressed cluster. The reduced
   busy junction may be less interesting; preserve this disagreement/dud.
5. Seed82 gains a larger bulging return on the right, a short escape meeting
   other channels, and a more particular central quiet area in full view.
   Remaining fans still have similar authority; this isn't a complete solution.
6. Seed13 spends its turning in a more angular central tongue. Its isolated
   floating half-circle remains generic, showing that rewriting one main
   passage doesn't make every disconnected mark consequential.

Meaningful geometry checks (`node check-round3.js`) all passed for12 outputs:
source/helper purity and deterministic controls, exact untouched prefix/tail and
endpoints, matched speed/point arrays, all final points finite and within bed,
deterministic repeated output,100m/250k limits. Full ink20.833–34.325m except24
at16.504m; maximum69,525 points. Cubic controls and before/after crossing counts
are in `round3-checks.json`; crossings changed in5,13,18,47,82 and stayed at24.
No topology-invariance claim. No production, app, hardware or shared files edited.
Current sources are frozen in `round3-source/` for lead reproduction/review.

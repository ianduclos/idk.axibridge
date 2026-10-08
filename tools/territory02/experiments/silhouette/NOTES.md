# Silhouette — round 1

## Hypothesis

A curve can resist a familiar circular/S outline when a long passage changes its direction unevenly: an outgoing shoulder travels flatter than the inherited bend and a shorter return folds back. One broad route change can alter a curve's character without adding marks. The first trial did this before migration, but migration made several almost-circles more prominent. That trial remains as `trial-seeded-*` evidence; the submitted version applies the route decision to the migrated snapshot population instead.

## Exact source change

Only `t_meander.js` is changed from the supplied source.

- New `silhouetteRoute(P, seed, id, trunk, F)` resamples one channel and reroutes one broad internal span using an asymmetric displacement envelope and partial straightening toward its span's chord. Endpoints stay fixed. Short curves and some minors stay unchanged. A private deterministic RNG stream (`6201`) keeps the old simulation random choices unchanged. Available bed room limits amplitude; original proximity to the bed suppresses displacement.
- `Territory.prototype.meander`: immediately after `migrate`, applies that same channel-seeded route decision to every snapshot and remaps its existing migration speeds by fractional arc index. All normal rendering, trace selection, bundles and density proceed from these changed snapshots. No new decoration pass, dials, or shared recipe changes.
- `seedChannels` is unchanged in the submitted version; the abandoned seeded trial is saved separately.

The submitted round-1 source is frozen in `round1-source/t_meander.js` and `round1-source/territory-engine.js`. `baseline-t_meander.js` is the original reference. `build.sh` remains local-only.

## Actual inspection

Inspected both complete matched sheets for seeds **5,13,18,24**, sparse and full, plus all four automatic close views in each recipe. Evidence: `baseline-{sparse,full}.png`, `round1-{sparse,full}.png`, and `round1-close-{sparse,full}.png`; matching HTML is alongside. No seed selection or beauty scoring.

Visible gains are uneven. Sparse 13 loses the broad round balloon on the right: its return is now narrow and oddly shouldered, with an upright passage that doubles toward the left. Sparse 18's small left form turns from a broad loop into a compact abrupt fold and long release; its upper branch has a shallow sag with a compressed rise. In 5 the long rising sweep changes into two unequal stages with a straighter diagonal approach. 24 retains much of its U-shaped construction but develops a small rising fold at the junction. Simple wide passages remain.

Failures/ambiguities: the fold in sparse 18 can look like a kink inserted for effect; 13 is stranger but may lose the original's breathing room at the centre. 5's large lower-left familiar U persists. 24 changes least at the whole-sheet level. Full populations retain repeated crescent/contour fields: changing the centrelines changes their edges and some entrances but does not solve that stronger visual repetition. Full 5 becomes busier than the original, with a compressed nest at the top right. Some route departures get swallowed by density.

## Checks and risks

`node check.js` verifies all eight seed/recipe combinations twice: exact deterministic line output, input cores preserved, every coordinate finite and inside 300×218 mm, nonempty strokes, and total ink below 100,000 mm. `checks.json` records counts and physical totals: sparse 1.006–1.217 m; full 16.407–30.626 m. Largest emitted segment is 1.782 mm. `sh build.sh` succeeds. These are geometry checks only.

The simulation's cutoff-event locations/loops remain in its original geometry: only channel snapshots are rerouted. That may make a historical cutoff less literally consistent with its transformed channel. No hardware tested. The effect is post-simulation shaping rather than a physical migration model, and a close-to-identical fractional span can fall at different physical places across snapshots as a channel length changes. Independent approach preserved; no production, shared harness, app, hardware or Git changes.

Close views confirm the differing turns in sparse 13/18 and the rising fold in 24. They also expose a full-13 failure: short repeated rectangular/comb-like pieces near the shaped upper route. Full 5's strongest close passage compresses into a heavy tangle; full 24's wide repeated U is still dominated by concentric spacing. Those are retained for critique, not edited out of the evidence.

# Silhouette — round 2

## Critique and decision

Inspected the lead's thin K sparse/full populations, including the newly available 47/82, and K's sparse-18 void and full-13 bar close views before editing. Accepted the question of a sustained change along a distant sweep and the need to preserve quiet/fracture. I did not fill empty areas, add linking marks, or remove detached material to force coherence. I retained the independent silhouette approach. The thin line request is honored in the local recipes (`w:0.1`) and `close.js` now uses 0.1 mm instead of 0.4 mm.

## Exact changes from round 1

`t_meander.js`: `silhouetteRoute` gives trunks a longer rerouted span, slower outward shoulder and more compressed return; minor route parameters remain as before. New `silhouetteWarp` derives one spatial displacement field from the latest migrated routes. Compact weighted kernels blend displaced and stationary anchors; unchanged passages supply zero displacement and the field fades into untouched ground. The field then maps **every snapshot, final channel, cutoff loop and event point** in `Territory.prototype.meander`. It preserves point counts and shared coordinates. Round 1's independent per-snapshot deformation/remapped speed block is removed. `close.js` changes only the physical display width/comment. Build and shared recipes remain unchanged.

An initial smoother field trial is retained as `round2-field-trial-*`; it softened distant transitions too much. The submitted longer-held shoulder has a tighter late release. Submitted sources are frozen in `round2-source/{t_meander.js,close.js,territory-engine.js}`; round1-source is preserved.

## Visible evidence and tradeoffs

Both complete six-seed thin sheets and all six sparse/full automatic close views were inspected. Evidence: `round2-{sparse,full}.png`, `round2-close-{sparse,full}.png`, their HTML and local six-cell recipes. No cherry-picking.

Sparse 5 preserves the rising sweep and large emptiness, but its former S turn becomes a longer oblique passage with two unequal releases: quieter and less emphatic. Sparse 18 keeps its huge void and little fold; the long remote route changes from a round return to a descending drift with a compressed lower transition. This offers another character, but doesn't prove the fragments deepen the void. Sparse 82 now has a descending kinked route through the gap between its episodes; their relation is stronger to my eye while remaining unresolved. Sparse 13 stretches its central returns into a narrower diagonal relation. Sparse 24 remains mostly a familiar broad U with remote small folds. Sparse 47 is a loss: some of the previous stacked cavity intricacy simplifies into quieter loops and hooks.

Full 13's obvious repeated small bars are substantially reduced by the changed geometry and resulting clipping, rather than removed by a decoration cleanup; some peripheral traffic remains. Full 5/24/47 still present broad repeated fields and some redistributed bands fill quiet vacancies. Full 82's wide lower echo becomes a direction-changing wave but can still read as ornamental repetition. Thin rendering makes the fields less coalesced without resolving placement. The round is mixed, not an across-population improvement.

## Checks and remaining limits

`check-consistency.js` proves that coincident source points map identically across historical snapshots, final channels, cutoff loops and event points, and checks a 2 mm grid for deterministic finite bounded mapping. The round-1 coordinate mismatch is resolved. Existing migration-speed scalars remain simulation activity transported with the points, not recomputed physical speeds after deformation. The spatial map is continuous with bounded support but no injectivity/topology proof is claimed.

`node check-round2.js` checks all 12 seed/recipe cases twice: deterministic line geometry, core input preserved, finite coordinates within 300×218 mm, nonempty strokes, <100 m ink and ≤250,000 points. `round2-checks.json`: sparse 1.061–1.418 m; full 15.016–33.014 m; maximum 66,829 points and 1.198 mm emitted segment. `node check-consistency.js` and local build succeeded. No hardware, shared harness, production, app or Git changes. Ready for independent review, with no convergence/integration performed.

# Silhouette — round 3: unequal cubics

## Starting comparison and exact geometry

Read the matching round-1 K population and our round-2 sparse population before editing, especially 47. Its former arch→neck→folded basin→hook range had indeed been flattened. This round restores the round-1 `silhouetteRoute` proportions and removes the shared averaged `silhouetteWarp` helper/call. New `silhouetteBezier` in the existing `t_meander.js` surgically replaces a selected internal passage with **explicit cubic control points**, before the existing bundle and hand rendering.

There are two geometries, chosen deterministically with independent stream 6227. One cubic uses an outgoing handle 1.25–2× the endpoint distance (minimum25 mm), rotated0.2–0.7 rad from the inherited tangent, versus a4–11 mm arrival handle rotated1.0–2.1 rad sideways from the incoming tangent. This can overhang/cross its continuation. The other uses two cubics through an off-axis pivot22–54 mm away: first outgoing handle35–85 mm, pivot arrival3–6 mm, pivot departure7–15 mm, final arrival12–37 mm at another sideways direction. The pivot's tangent turns1.9–2.4 rad from the entry tangent. Control points are bounded5 mm inside the simulation bed; the convex hull bounds each cubic. Cubics are evaluated at ≤0.5 mm control-polygon sampling, resampled0.5 mm and inserted into the route. No new concat part or hand changes.

Routes <95 mm and most minors remain unchanged. Broadly diverse routes (≥3 curvature sign changes and >5.3 rad accumulated broad turning after5 mm resampling/two smoothing passes) receive a short late intervention instead of replacing their middle sequence. These are geometry gates to protect existing range, not aesthetic scores. The first trial protected too many gently turning routes; it remains `round3-short-trial-*`. Source snapshots and final channels use the new surgery; original migration-speed magnitudes are remapped by fractional index.

## Visible results, including weak cases

Inspected all six sparse/full0.1 mm populations and all twelve automatic close views. Additional selected tight sparse views cover all six seeds. Evidence: `round3-{sparse,full}.png`, `round3-close-{sparse,full}.png`, `round3-tight-sparse.png`, with matching HTML. Whole-population weak cases are retained.

Sparse18 is the largest departure: the broad U is replaced by a long diagonal that turns close to the right edge; the void now has a much less rounded boundary. It is sharper but may be too simple and frame-dependent. Sparse13 gains a sideways folded passage with a tight return and skewed release; its former round return no longer defines the middle. Sparse47 regains a lower folded basin/neck with a narrow loop crossing it, while the top arch also gets a small tight loop that risks reading as a decorative knot. Sparse82's lower passage doubles back into a displaced loop while retaining its broad asymmetric overhang. Sparse24 remains relatively conventional: an elongated U and a more awkward central crossing. Sparse5 largely retains its long quiet rise but its central small enclosure is triangular rather than circular. Thus the population contains several characters rather than one prescribed hairpin.

Tight returns/crossings are still visible in the actual emitted hand paths after2 mm resampling/Catmull smoothing; no raw-control overlay stands in for that check. Full13 loses some of round2's stream coherence and regains little bars. Full18 now has more diagonal traffic. Full47 remains sparse near the restored central range while echoes occupy the periphery. Full5/82 retain broad contour-like repetition. These are departures and mixed gains/losses, not an overall improvement claim.

## Deliberately relaxed constraints and verification

Released round2's single spatial map/coincident-point consistency and smooth-route/topology preferences. Cubic joins may be misaligned, channels may fold back or cross, and shaping need not preserve the old silhouette. Outer route endpoints remain inherited in this implementation, but internal tangent continuity is not required. **Cutoff event positions and stored cutoff loops remain in the original simulation geometry**, so they need not coincide with path-specific shaped snapshots/channels. This is a known experimental consistency limitation, not resolved production geometry. Speed values are inherited simulation activity rather than recomputed shaped physical velocity. Round2's consistency check is specific to its frozen source and is not a round3 assertion.

`node check-round3.js`: all twelve cases deterministic, pure with core inputs preserved, finite and within300×218 mm, nonempty, below100 m and250k points. `round3-checks.json`: sparse0.880–1.247 m, full12.659–33.629 m; maximum68,053 points/3.226 mm emitted segment. `node check-bezier.js`: six independent synthetic cubic departures preserve inputs, repeat exactly and remain finite/within bed after the actual2 mm hand controls. Local build succeeds. Frozen source: `round3-source/{t_meander.js,close.js,territory-engine.js}`. Rounds1/2 are preserved. No production, shared harness, integration/convergence, Git, app or hardware changes.

Selected-close qualification:18's diagonal turn is rounded after the hand pass, rather than a literal cusp.47's tight upper turn survives as overlapping small loops and may look like a scribble/knot;24's large U remains smooth. These close views limit the claim that tighter control handles alone make every selected passage visibly tight.

# Void — round 1

Hypothesis: an inherited broad bend can shelter an empty pocket more specifically
than an arbitrary quiet circle. An unequal, incomplete return edge may almost
divide the space without closing it. This is independent of the other makers.

## Source

- `t_void.js`: new `bendPocket(geo, chans, seed)`. Selects a 70–140 mm arc
  with substantial signed chord sag, penalises other centrelines inside its
  reservoir, forms a bend-derived polygon, and supplies an incomplete return
  lip plus a cached 1 mm occupancy mask. Geometry/occupancy select the pocket;
  there is no beauty score.
- `t_meander.js`: after the inherited drawing, draw the lip with the existing
  firm hand and pass the optional pocket to density. Existing base curves remain
  intact. The lip also becomes density input, so its effect is more than clipping.
- `t_density.js`: initialise the existing void mask with the pocket mask.
  Existing arbitrary shard voids are still added. Slashes/ribbons may cross the
  space; this is a resistance to fill, not a clean knockout of all marks.
- `build.sh`: append local helper before local density. Builds only this copy.
- `round1-source/`: source snapshot for critique/round 2. `round0-*` preserve
  changed original source files. `check-round1.js` / `round1-checks.json` provide
  mechanical verification, not aesthetic acceptance.

## Evidence and visible reading

Matched common populations, no seed culling:
`baseline-sparse.png`, `baseline-full.png`, `round1-sparse.png`, `round1-full.png`.
Close views: `round1-close-sparse.png`, `round1-close-full.png` (13 and 18).
All were rendered and inspected locally.

1. Sparse: seed18 acquires a shelf above its large lower basin. The simple
   inherited bend remains more important than the addition. Seed5's long angled
   lip slightly pinches its spacious upper passage. Seed24 gains a shallow open
   notch. These may offer material for composition but are small advances.
2. Weak sparse seed13: return crosses the older loop at the knot, then abruptly
   rises. Close inspection reads it as a stiff bracket, mechanically repeatable
   across the population. It does not yet change character persuasively along
   its course. Keep this case.
3. Full: reservoir resists fill while the surrounding growth changes. Seed13
   keeps a broad empty crescent against its large loop, but grows a dense mass
   on the opposite side. Seed18's lower basin survives while short echoes pile
   above the lip and long slashes traverse it. Seed24 becomes a large lower
   swirl; this may still read as combing rather than a strong peculiar void.
4. The inherited full recipe remains busy and often combed. A single pocket
   does not resolve its overall visual uniformity. Some difference between full
   sheets comes from the extra lip becoming a new growth source, not the mask
   alone; attribute cautiously.

## Risks / next critique

The current lip is piecewise straight with merely local corner rounding: the
same angled-bracket grammar repeats. The reservoir's unseen return is polygonal,
so density can inadvertently reveal a cutout edge. Selection favours a broad
existing bend and may overlook small powerful gaps. Masking acts late; it does
not alter the fundamental base curves. Round 2 should pursue the independent
critique, especially a return that changes character without becoming a polite
outline. No convergence or integration was performed.

## Checks and limits

`node check-round1.js`: identical lines on repeated runs for seeds 5,13,18,24
under both shared recipes; every emitted point finite and within 300×218 mm;
ink 1.11–29.53 m, all below 100 m. Local build and both populations render.
Screen-only; plotter, app, production, shared configuration, and Git untouched.
Visual judgement remains provisional for Ian to check.

# Round 2 — inherited departure / second boundary

Focused critique: keep blunt incompatibility; test one passage that begins as
an actual curve continuation, changes character sharply, and alters another
boundary/void. Do not turn all curves into clean connectors. No convergence.
Reviewed the lead's thin P sparse/full six-seed populations; local thin close
views retain 47/82 and include weak 24 alongside 18. Round1 source is untouched.

## Exact changes

1. `t_void.js`: pocket selection/mask geometry is unchanged. The new passage
   finds an actual plotted `strand` within 7 mm of the selected bend's start,
   reuses approximately 12 mm of its precise coordinates in reverse, departs
   with its inherited tangent, changes abruptly into a shelf, and crosses a
   nearby second channel (within 30 mm of the old lip's endpoint). When none is
   nearby, it crosses the selected bend's far boundary instead. A short turn
   continues beyond that boundary. If no usable plotted prefix exists, the
   whole pocket is declined. Points are clipped to a 3 mm bed inset.
2. `t_meander.js`: emit that continuous passage directly, preserving inherited
   prefix coordinates instead of applying another hand pass over the joint.
   Optional `pocketLip:false` supports attribution; base drawing remains intact.
3. `t_density.js`: the passage is physical occupancy but, by default, cannot
   seed an echo train. `pocketGrowth:true` restores its seedability;
   `pocketMask:false` suppresses the reservoir. These are experiment controls,
   not changes to the shared recipe or production interface.
4. `close.js`: render actual config width (0.1 mm) for current close views.
   Local `population-*.json` reproduce the shared recipes and add 47/82.
   `round2-source/` snapshots all changed source/tool files.

## Addressed / retained disagreement

1. Addressed floating starts and dropped endpoints: the passage follows real
   ink and then reaches through a second boundary. Seed24 becomes a canopy
   attached at both sides; seed47's previously floating incision acquires a
   relation to the upper arch and lower knot. The sharp incompatibility remains.
2. Did not smooth the blunt angle into a pleasing arc or make every base curve
   agree. Only this passage changes; all original marks remain.
3. The critique is only partly answered artistically. A shared prefix is a
   mechanically real continuation, yet the viewer may still perceive a branch.
   Several passages still read as schematic links. Exact attachment is not
   evidence of a stronger drawing.

## Visible gains / losses (all six retained)

1. Sparse5: the open upper space becomes a long tapering wedge. Its simplicity
   has authority, but closure may be too tidy and the turn too slight.
2. Sparse13: the bracket remains awkward; attachment turns it into a narrow
   hinge against the large loop. It changes a gap but does not resolve the knot.
3. Sparse18: explicit loss—the strong horizontal shelf from round1 is replaced
   by a diagonal across the basin. The tiny departure curl and exit across the
   lower boundary are more connected, while the space is less peculiar and may
   read as a diagrammatic link. Round1 remains a meaningful alternative.
4. Sparse24: gain—the floating annotation becomes a canopy whose unequal angles
   divide the lower void. The tiny departure fold is arguably needless.
5. Sparse47: the incision now passes from the inherited upper curve into the
   lower boundary. It has more consequence and remains stern. It also resembles
   a wire joining two lobes; retain this ambiguity.
6. Sparse82: the passage makes a slender angular inner void, then crosses the
   lower boundary with a little fold. More specific space, but a danger of a
   closed schematic outline. Full recipes often lose these subtle differences
   beneath echo trains and slashes; uniform combing remains a broader limitation.

## Attribution evidence

`round2-ablation.png` has rows 18 and 47, columns baseline / mask only /
passage + mask / passage + mask + growth. Seed18's mask-only and default
passage sheets have very similar surrounding density. Re-enabling passage
growth substantially redistributes trains elsewhere; that gain/loss cannot be
credited only to a shaped empty pocket. Seed47 changes visibly even from mask
alone, since blocked echo trains alter the later available ground. Default
passage changes occupancy and source indices as well as geometry, so it is
not perfectly independent of density mechanics despite no direct seeding.

## Evidence and checks

- `round2-sparse.png`, `round2-full.png`: six-seed whole populations, inspected.
- `round2-close-sparse.png`, `round2-close-full.png`: thin views of 18,24,47,82,
  inspected; `round1-close-held.png` preserves thin round1 geometry for 47/82.
- `round2-ablation.png`: eight attribution variants, inspected.
- `check-round2.js` / `round2-checks.json`: twelve outputs repeated identically;
  all emitted points finite and within 300×218 mm; every passage begins with
  at least three exact consecutive (reversed) coordinates from its inherited
  strand. Maximum 29.97 m ink, 60,737 points, below 100 m / 250k limits.
- Build only in this copy. No production, shared files, Git, app or hardware
  actions. Visual judgement remains provisional for Ian to check.

The eight ablation variants also passed finite/within-bed, <100 m and <250k
point safety checks; largest ablation ink was 28.24 m. Sources frozen for the
fresh neutral review; no further aesthetic retuning.

# Round 3 — explicit unequal cubic courses

Ian authorized a bolder round: tighten curves with unbalanced Bézier handles,
relax earlier preservation preferences, and let the curve's own course pressure
empty space. Round1/round2 snapshots remain untouched. No convergence occurred.

## Exact geometry and source changes

1. New helper `voidBezierCourses(chans,seed)` is inside existing `t_meander.js`.
   After migration/present-time selection, before bundle construction, it selects
   one existing broad bend (roughly 60–124 mm along a resampled course). Selection
   uses chord length × signed sag, with deterministic seeded variation. Other
   courses remain unmodified; there is no extra connection line.
2. Replace that source subarc with two explicit cubic Béziers sharing shoulder S:
   `B(a, a+ta*hA, S-tm*hS1, S)` then
   `B(S, S+tm*hS2, b-tb*hB, b)`.
   Hinge: shoulder normal offset 2.1×signed sag, chord skew +0.12×chord;
   middle tangent rotated 0.95 rad×sag sign; handles 0.92×chord / 3.5 mm,
   then 5 mm / 0.6×chord. Recoil: offset 2.5×sag, skew −0.14×chord,
   middle tangent −1.9 rad×sign; handles 0.7×chord / 6 mm, then
   2.5 mm / 0.6×chord. Recoil additionally rotates the long start handle
   −0.8 rad×sign and long end handle +0.65 rad×sign away from inherited
   tangent directions. This can reverse a course into a large crosswise return;
   endpoint positions stay shared, but tangent agreement is deliberately relaxed.
3. Sample cubics by their control-polygon length at <=0.35 mm parameter sampling
   scale, then resample the complete centreline at the channel's existing ds.
   Controls are bounded to an 8 mm bed inset: the cubic convex hull keeps samples
   in bed. The real rendered hand still samples at 2 mm, so source tightness
   alone is not evidence; actual populations and closes were inspected.
4. Around S, preserve source geometry through the second bundle pass: weight
   ramps from normal smoothing at 24 mm distance to full geometry at 7 mm.
   There is no global removal of smoothing. Existing hand/band routines remain.
5. New present speeds map the original speed array by normalized course position.
   These are inherited migration weights, not a simulation of the new cubics.
   Old history remains as independent material; it can now contradict the course.
6. Round2 `pocket-lip` emission and pocket mask are removed from the active path.
   `t_density.js` restored from the original local `round0-t_density.js`.
   `build.sh` restored the original concat list: no extra helper file. The old
   `t_void.js` remains as prior-round evidence but is not built. `voidCourse`
   diagnostics expose selected channel, variant, controls and shoulder in results.
   `round3-source/` freezes changed/current source and thin close tool.

## Visible gains/losses against round2

1. Sparse5: lower-left void changes from rounded cup to unequal compressed wedge;
   most upper course remains plain. The bed inset limits its outward push.
   Tiny hand curls persist on a different nearby line; do not credit those as
   the main cubic change. Full5 becomes busy again and may have lost open authority.
2. Sparse13: the separate bracket disappears; the knot contains an elongated
   recurving tongue and longer departures. This is a change through the actual
   course, but subtle and arguably less clear than the previous slight relation.
   Full13 turns it into a substantial curved mass; combing remains evident.
3. Sparse18: the final recoil visibly swells inward, turns across itself and
   releases into a broad low return. It changes the basin through its course
   rather than adding a diagonal overlay. First draft's tiny turn was rejected;
   rotated long-handle directions produced the stronger final change. Actual
   thin close shows the crossing and unequal return surviving the 2 mm hand.
   The former round1 horizontal shelf is still a meaningful alternative, not
   something superseded by attachment. Full18 gains a long authoritative return
   but also decorative-looking echo fans below it.
4. Sparse24: sharply compressed notch near the knot, while lower lobes stay quiet.
   Removing the canopy loses round2's explicit division. It may be too small a
   departure for Ian's bolder request; keep this weak case. Full24 masks the notch
   with nearby density and does not prove an improvement.
5. Sparse47: the useful round2 looped fastening is lost. The upper arch becomes
   asymmetric, flatter at one end, then releases into a long diagonal return.
   It is quieter but less consequential. Full47 gains a bulky arch of growth
   rather than the previous fastening's clearer authority; retain the loss.
6. Sparse82: the broad outer course acquires two unequal lobes and a tight waist,
   preserving more of the layered interior than the round2 angular inner overlay.
   Thin close makes the gentle approach / compressed waist / broad release legible.
   Full82 converts that waist into a denser bend; possible renewed hair/combing.
   This is a useful geometric possibility, not a settled aesthetic win.

## Relaxed constraints and risks

Source subarcs can be replaced, inherited tangent continuity can break, and old
history can disagree with the altered course. The experiment no longer protects
all old curves intact or requires endpoint attachment to another boundary.
Only one course is altered per sheet; plain passages remain and only seed18 takes
recoil in this common population. Unequal source handles do not automatically
make strong images: several hinge results remain mild. Controls may shorten
near the bed inset. Retained speed/history come from before the edit. Density
changes respond to new curve occupancy/source geometry, with no reserved mask;
full-sheet gains cannot be ascribed to empty space alone.

## Frozen evidence and verification

`round3-sparse.png`, `round3-full.png`: complete six-seed 0.1 mm populations;
`round3-close-sparse.png`, `round3-close-full.png`: all six actual rendered courses,
including weak24 and the lost47 fastening. Final populations/closes inspected.
`check-round3.js` / `round3-checks.json`: twelve repeated deterministic outputs,
input core objects unchanged, every emitted point finite within 300×218 mm,
actual control-pair handle ratios >=3, maximum 33.48 m ink / 67,896 points,
below 100 m / 250k limits. Full cubic controls saved in the check report.
Sources frozen. No shared files, production, Git, app, hardware or delegation.
Visual verdict remains provisional for Ian to check.

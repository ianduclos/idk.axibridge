# Meander research 1: migration and line-family techniques

Scope: five technique areas for a one-pen, abstract "meander" drawing on a 300x218 mm sheet, deterministic by seed, ~0.2 s per thumbnail, 24 in <=5 s in node. Budget for this document: the goal is a searching, restated, unpredictable line family, NOT a river render and NOT Hodgin's *Meander* map. Sources actually fetched: the meanderpy README and source (github.com/zsylvester/meanderpy, fetched 2026-09-29). Everything else is from memory and marked **(unverified)**. I did not run any code; costs are estimates from point counts. One web search (Howard-Knutson / Ikeda) timed out, so the equations below for those papers are from memory and marked as such; meanderpy's discretisation is the verified anchor.

Units below: work in "channel widths" W (a free scale, e.g. W = 3 to 6 mm on the sheet), nodes spaced ds ~ W/2 to W. The sheet then holds 50 to 100 W, so ~ 5 to 8 bends across the long axis at wavelength ~ 10 to 14 W (**unverified** typical fluvial ratio).

## 1. Curvature-driven centreline migration

### Summary
A centreline is a polyline x_i(t). Each step, compute curvature C_i, convert it to a "nominal migration rate" R0_i = k_l * C_i (sign chosen so outer bank erodes, i.e. bends grow outward), then smooth it with an exponentially decaying upstream kernel to get R1_i, and move each node along its normal by R1_i * dt. The lag between where curvature is and where the movement happens is what makes bends skew downstream and translate downstream. Curvature alone (omega only) is unstable and grows noisy kinks; the upstream weighting is a low-pass filter that also produces the physical asymmetry.

### Verified discretisation (meanderpy, Sylvester et al., after Howard & Knutson 1984)
From the fetched source:

```
R1[i] = omega * R0[i] + gamma * sum_{j<=i}( R0[j] * G(s_i - s_j) ) / sum_j( G(s_i - s_j) )
G(s)  = exp(-alpha * s)             # s = arc distance upstream of i
alpha = k * 2 * Cf / D              # k: constant (~1), Cf: Chezy friction factor, D: depth
defaults: omega = -1.0, gamma = 2.5
```

Displacement per step (normal to the local tangent, dx_ds, dy_ds are unit tangent components):

```
disp_x =  R1[i] * dy_ds * dt
disp_y = -R1[i] * dx_ds * dt
# clamp |disp| <= cfl_factor * deltas   (meanderpy: cfl_factor = 0.5)
```

meanderpy also notes it deliberately uses a *linear* rate-vs-curvature relation, unlike Howard-Knutson's original nonlinear form, citing satellite evidence. Cutoff distance `crdist` is typically 2 W; resampling is a spline re-sample to spacing `deltas` every step; the ends (`pad` nodes) are held fixed.

### Howard-Knutson form (from memory, unverified)
Nominal rate ζ_i = Ω·C_i·W... Their model: migration rate = ω·(local curvature) + Γ·(weighted sum of upstream curvature), weights decaying with distance along the channel over a few channel widths, with Ω ≈ -1 and Γ ≈ 2.5 (the same numbers meanderpy carries, so this is consistent). Ikeda-Parker-Sawai (1981) linear bend theory (from memory, unverified) gives excess near-bank velocity u_b' obeying, in Sylvester's shorthand,

```
du'/ds + (2 Cf / D) * u' = -(2 Cf / D) * F * (W / 2) * ... * d(theta)/ds    # lagging response to curvature
```

i.e. first-order lag: bank velocity relaxes to a curvature-proportional target with e-folding length D/(2Cf) ≈ 1/alpha. The convolution kernel above is the closed form of that ODE. The point that matters for drawing: **one length, 1/alpha, controls the lag, and lag creates the asymmetry.**

### Practical single-pass update (cheaper than the convolution)
Because G is exponential, replace the O(N^2) sum by a running recurrence, O(N):

```
a = exp(-alpha*ds)                      # constant if resampled to fixed ds
S_0 = R0_0 ; Z_0 = 1
for i in 1..N-1:
  S_i = a*S_{i-1} + R0_i               # weighted sum
  Z_i = a*Z_{i-1} + 1                  # weight sum
  R1_i = omega*R0_i + gamma * S_i/Z_i
```

(Same result as meanderpy up to the meanderpy sum being over all upstream nodes; the recurrence is exact for exponential G.) This makes the whole migration step ~ N * 20 flops.

### Curvature
On a resampled polyline with spacing ds: C_i = (theta_{i+1} - theta_i)/ds, theta = atan2 of segment direction, wrapped. Smooth C with 2 to 3 passes of [1 2 1]/4 before use (else 2ds noise dominates, see section 4). Sign convention: with y down (machine frame) test once and flip so bends grow.

### Typical parameters (nondimensional, for our sheet)
- N nodes: 300 to 500 at ds ~ 1 to 2 mm (a channel of 600 to 1000 mm length folded into the sheet).
- dt * k_l * C_max ~ 0.05 ds per step (stability, below). Steps to build 3 to 6 mature bends from a low-amplitude noisy line: 300 to 1500 (**estimate**, tune by test).
- 1/alpha ~ 5 to 15 W. Larger = stronger skew and longer wavelength; smaller = symmetric, blobby, closer to pure curvature flow.
- omega = -1, gamma = 2.5 give net "positive feedback" (|gamma| > |omega| means upstream influence dominates); these are meanderpy's defaults, keep them as the starting point.

### What controls wavelength and asymmetry
1. **Initial perturbation spectrum.** The model amplifies a band of wavelengths; the fastest-growing band is set by the kernel length 1/alpha and W, roughly a few tens of 1/alpha (**unverified**). If you seed the centreline with band-limited noise (or a Kinoshita curve, below) the outcome wavelength follows the seed. Wavelength irregularity comes from irregular seeds, not from the migration law.
2. **1/alpha.** Longer kernel -> more downstream skew, bends lean and are more "saw-toothed". Also less symmetric loop necks.
3. **gamma/omega.** Higher gamma raises the lag contribution and growth rate.
4. **Spatially varying k_l(s)** (stiff/soft banks): the easiest way to get *unpredictable* weight distribution. A slowly varying noise multiplier on k_l along the arc index (or along position, as a 2D noise field, "geology") gives bends that grow at different rates, some frozen, some wild. This is the recommended abstraction lever, not in the classical models.

### Kinoshita curve (idealised seed; from memory, unverified)
Direction angle along arc length s': theta(s') = theta0 sin(2 pi s'/L) + theta0^3 (J_s cos(3*2 pi s'/L) - J_f sin(3*2 pi s'/L)), with J_s, J_f order 1/32 to 1/192 depending on the source; theta0 up to ~110 deg gives strongly looped, skewed bends. Integrate x' = cos theta, y' = sin theta. Use: as a seed with jittered L and theta0 per bend (piecewise), or simply as a source of distinctive skewed lobes when a *slight* migration run is wanted. Risk: it looks like a textbook meander ("ribbon of stereotypical loops").

### JS cost
Per step: curvature (N), smoothing (N), recurrence (N), displacement (N). ~ 6N flops ~ 3000 flops for N=500, i.e. ~ 10 microseconds. 1000 steps = ~10 to 20 ms, plus per-step resampling (section 4) and cutoff checks (section 2) which dominate: maybe 100 microseconds per step, so 0.1 s for 1000 steps. This fits 0.2 s if the loop stays under ~1500 steps and N under ~600.

### Pitfalls
- Time-step instability: displacement per step must stay < 0.5 ds (meanderpy's `cfl_factor`); clamp it. Without it nodes cross and the polyline kinks. Halve dt when max |R1| dt exceeds the clamp rather than clipping silently (clipping distorts shape).
- Curvature at fixed ends: pin the first and last ~10 nodes (meanderpy's `pad`); the upstream boundary has no history, so start the recurrence with S_0 = R0_0 * something, or extend the line beyond the sheet and crop.
- The classic long-run result is a *saturated* meander belt: loops close, cut off, regrow. That saturation is what makes it look like a river map. Stop early or drive it with non-uniform k_l.

### What it gives / how it can fail aesthetically
Gives: smooth, asymmetric, leaning loops with a natural phase relation between the bends, and a history of positions (section 3). Fails: (a) even amplitude and wavelength (a sine train of bends, exactly Hodgin's look); (b) "river" reading as soon as there are oxbow scars and a width-consistent pair of banks. Mitigations: non-uniform k_l, band-limited irregular seed, early stopping mid-growth, several lines with different parameters sharing the sheet, treat the lines as unnamed strands rather than banks.

## 2. Cutoff detection

### Summary
When two non-adjacent parts of the centreline approach within a threshold (neck cutoff, crdist ~ 2 W in meanderpy), the loop between them is cut: the line is reconnected across the neck, and the enclosed loop is dropped (oxbow). A chute cutoff (short-circuit across a point bar without the neck being narrow) is the same test with a smaller threshold and a topological condition on arc-length separation; in a 2D geometric model the two are indistinguishable, and meanderpy only implements neck cutoffs. **(unverified)** that chute cutoffs are treated separately in the literature as a distinct process needing a flow-partition criterion.

### Verified meanderpy method
```
dist = cdist(points, points); dist[dist > crdist] = nan    # O(N^2) full matrix
blank a diagonal band (arc-adjacent nodes)
for each non-nan pair (i1, i2): x = hstack(x[:i1+1], x[i2:])   # loop removed, iteratively
```
The band width is `2*crdist/ds` nodes, so genuinely local proximity is ignored.

### Efficient JS version
```
grid hash, cell size = crdist
for i in 0..N-1:
  insert node i in cell (floor(x/c), floor(y/c))   # Map<key, int[]> or typed CSR
for each cell, for each pair in (cell, 8 neighbours) with j - i > jmin:
  if dist(i,j) < crdist: candidate (i, j)
pick the candidate with smallest j - i first  (innermost loop), cut, restart the scan locally
```
where jmin = ceil(3*crdist/ds) (arc length of the smallest loop worth cutting, about pi*crdist). Cost O(N) per pass with a fixed-size hash (use a Int32Array of head pointers over a (300/c)x(218/c) grid, next[] chain). Do the test every 5 to 10 steps rather than every step (bends approach slowly); ~N=500 nodes ~ 20 microseconds. Cutoffs are rare (a handful per run), so no restart cost issue.

### What to do with the removed loop (oxbow)
The removed segment x[i1+1..i2-1] is a closed-ish arc (both ends are within crdist of each other). Options:
1. Discard (meanderpy).
2. Store as an "abandoned channel" polyline; join the two ends across the neck with a short chord so it is a closed-ish lake. Also drop it from later migration (it no longer moves). Drawn: it is the strongest river cue (crescent lake), so ink it only partially, as a fragment with a gap at one end, or restate 1 to 3 times as drifting arcs. It naturally provides "long open lines between things" and "hooks at line ends" when the neck end is left open.
3. Keep migrating it with a lower k_l (frozen ghost).
Recommendation for this drawing: keep the oxbow as a polyline candidate for later sections but never close it and never fill it; treat as a stroke source (with its lineage/age) not a shape.

### Reconnection
Concatenate x[:i1+1] with x[i2:]; the join is a kink of angle up to ~180 deg. Fix: after the cut, apply local smoothing over ±5 nodes and resample; migration then rounds it. The kink acts as a new high-curvature point, and the model spontaneously produces the classic sharp cutoff corner, which is visually characterful (a beak). Keep it.

### Pitfalls
- Self-crossing rather than approach: nodes may pass through each other in one step if displacement > crdist. The 0.5 ds clamp avoids this; a segment-segment intersection test is a backstop (segments are short so hash the segments' cells).
- Endpoint: don't let the fixed padding be cut.
- Cutoff creates a discontinuity in history (section 3): scroll-bar snapshots made before a cutoff contain the removed loop; keep them (that's the scars).

### Aesthetics
Gives sudden topology change, the "what is going on" moment, and a saving of the excess loops (density variation: dense scroll bars near old belts, thin straight reaches after cutoffs). Fails: each cutoff leaves a symmetric, moon-shaped oxbow, which is the most clichéd river mark; and a run with many cutoffs produces a uniform lace.

## 3. Scroll bars and point bars from migration history

### Summary
Real scroll bars are the surface ridges of a point bar, each recording an earlier position of the inner bank; spacing is irregular because each ridge records a flood-driven accretion event, not regular time. In the model, a scroll-bar family is the set of earlier centrelines (or bank lines offset by ±W/2) at a sampled set of times.

### Sampling past centrelines
Store the polyline snapshot every K steps (meanderpy: `saved_ts`, plus `cl_x, cl_y` per snapshot). Memory: 1500 steps / 10 = 150 snapshots x 500 nodes x 2 = 150k floats, trivial. Do NOT draw them all.

Selection rules (avoid tree rings, per PACK risks):
1. **Drop the even index.** Choose times by an event process: t_k+1 = t_k + Gamma-distributed gap (shape ~ 0.7 to 1.5, giving clumped events), or a power-law gap. Gaps vary by ~ 5x within a family. Real bars also cluster (**unverified**: fluvial literature describes scroll bar spacing as irregular but with mean spacing related to bar width / flood periodicity).
2. **Select by displacement, not time.** Keep a snapshot only where its displacement from the previously kept snapshot exceeds a random threshold (0.3 to 2 W) *somewhere* along an arc; draw only the sub-polyline where the displacement is above threshold. This yields ridges that exist where the bend actually moved, and pinch to nothing elsewhere (fan and pinch).
3. **Locality.** Draw each kept snapshot only on the inner side of a bend (arc range where R1 >0 and the bank moved into the bar, or where migration monotonic across snapshots), and cut where the snapshot line crosses a later snapshot (later erosion truncates earlier bars). This truncation is the visual signature that distinguishes real scroll bars from concentric arcs: earlier ridges end against later ones at oblique angles. Implementation: process newest to oldest; for each older snapshot, split it at intersections with the newest kept line and drop the outside part (a crude 2D "eroded by" rule) using a coarse occupancy grid of already-inked cells (the prototype `Sheet` with lineage fits).
4. **Restate, don't ring.** Draw each selected ridge with `handLine` sway and overshoot so its edges drift and do not agree (Ian's sketch: contours restated 2 to 6 times that drift and don't agree).
5. **Amount varies by region**: multiply the keep probability by a slow noise field so some bends have 8 ridges, some 1, some none (open ground).

### Pseudocode
```
snap = list of centreline polylines with time
kept = []
for s in reverse(snap) with stochastic gap:
   segs = arcs of s where displacement(s, kept[-1]) > thr(random 0.3..2 W)
   for seg: cut against ink occupancy; if length > 8 mm: kept.push(seg)
```
displacement(s, prev): nearest-point distance via the shared spatial hash or the prototype `distField` of the newer line (one field per kept line, or one field for the union of kept lines: dilate + BFS). With grids of 300x218 and a union distance field recomputed once per kept ridge (~ 10 to 40 per sheet, 65k cells) ~ 1 ms each, so 40 ms worst case. Use a 2 mm grid (16k cells) to keep it ~ 0.3 ms.

### Pitfalls
- Snapshots earlier than the cutoff have loop parts that no longer exist. Fine, but their proximity to newer lines can be sub-pixel along long stretches: coincident line problem (double-inking). The occupancy cut above handles it.
- Snapshots at nearly constant spacing when the migration rate is uniform: enforce the irregular gaps by displacement-threshold randomisation.
- Draw only on the "point bar" side: because we have no banks, choose the side by the sign of curvature (inside of the bend = concave side).

### Aesthetics
Gives: nested, drifting, truncated partial arcs with irregular weight, which is exactly "density piled at junctions" and "lines shared between lobes" when two migrating strands' families meet. Fails: even concentric arcs (tree rings/fingerprint, both rejected); layered parallel stripes. Kill test: if any 3 adjacent ridges have spacing within 20% of each other over > 30 mm, the sampling is too regular.

## 4. Resampling and stability

### Requirements
Nodes drift along the line during migration (normals only displace perpendicular, but curvature-driven convergence bunches nodes on the inside of bends and spreads them on the outside). Curvature needs roughly uniform ds. So resample each step or every few steps.

### Arc-length resampling (cheap, linear)
```
cum = cumulative chord length
for k in 0..M-1: target = k*ds; advance j while cum[j+1] < target; lerp between j and j+1
```
Linear interpolation shrinks curves slightly at each resample (chord cutting, a curvature-loss effect that acts as diffusion). Fine at ds <= W/2. Catmull-Rom interpolation (as in `t_hand.js`) is more faithful but ~ 4x cost. meanderpy resamples with parametric cubic splines (`splprep`, s=0) every step **(verified)**; in JS use linear resample plus one smoothing pass, or resample every 3 to 5 steps. `resample(P, step)` in `t_head.js` already exists; check that it does arc length lerp (I only listed its signature).

### Smoothing
The migration law is an anti-diffusion of shape at short scale (gamma>0 amplifies curvature), so 2ds noise grows. Countermeasures, in order of cost:
1. [1 2 1]/4 on curvature before conversion (cheap).
2. Laplacian smoothing on positions with lambda ~ 0.1 every step or every few steps (`smoothPts`); the amount is a stability/character dial: more smoothing = softer, less "scribbly".
3. Low-pass the displacement field instead of positions (keeps the shape from shrinking).
4. **Taubin** alternating positive/negative lambda/mu smoothing avoids shrinkage **(unverified specifics)**; use only if shrinkage shows.

### Preventing bunching and kinks
- Resample to fixed ds at every step (or when max/min segment ratio exceeds 1.6).
- Clamp displacement (0.5 ds).
- Cap curvature at |C| <= 1/(0.7 W) (minimum radius of curvature ~ W physical; tighter loops cut off anyway) to prevent runaway inside tight loops.
- Cutoff test at the same cadence.

### Self-intersection
Between cutoff checks, tight necks can cross. Detect segment-segment intersection using the same grid hash on segments (cell size crdist), only for non-adjacent segments; on a hit, treat as a cutoff at the intersection point (loop removed, splice at the intersection). This is more robust than the distance threshold alone.

### JS cost
Resample + smooth each step: ~ 3N array ops ~ 20 microseconds at N=500. All-in per-step cost with cutoff checks ~ 100 to 150 microseconds (unmeasured), so 1000 steps ~ 0.1 to 0.15 s. Use Float64Array pairs x[], y[] rather than arrays of [x,y] for the hot loop; convert to [x,y] polylines only for drawing.

### Aesthetic note
Smoothing strength determines the *character* of the line: lots of smoothing = the "shmoother" Ian asked for; too much and it reads as a machine-perfect sine. Add controlled irregularity after the run (hand sway, small low-frequency wobble, restated overdraw with drift), not during migration.

## 5. Variable-width strokes from a line family

The constraint is one pen, one line width. "Width" must be an illusion made by pairs, bundles, or varying separation of thin lines. Ian asked for exactly this on v5: "the illusion of line width and narrowness through the lines, to create the illusion of volume".

### Options
1. **Bank pairs by offset curves.** Left = C + (w(s)/2) n, right = C - (w(s)/2) n, w(s) varying by noise or by curvature (wider at inflections in real rivers; **unverified** and immaterial here). Cheap: O(N). Failure: cusps/self-intersection on the concave side where radius of curvature < w/2; visible as loops/spurs.
2. **Strand bundles.** Offsets at fractional positions u_k in [-1,1]: line_k = C + u_k * (w(s)/2) n, with u_k drifting (converge/diverge): u_k(s) = base_k * env(s) + small independent noise per strand. Pinch where env -> 0 (strands converge to one thin line), swell where env large. This gives the "restated searching bundles beside thin single lines" (v5 keepers) and the volume illusion from varying spacing. Strand count 2 to 7. Use different low-frequency phases per strand so they cross occasionally (nuanced tangle, not parallel ruling).
3. **Curvature-limited offset**: w_eff(s) = min(w(s), 1.6 / max(|C|, eps)) local clamp (radius of curvature limit) **(my heuristic)** -> avoids cusps by narrowing the ribbon on tight bends, which itself is a nice effect (bundle squeezes on bends, opens on straights).
4. **Cheap cusp trimming**: compute offset polyline, then remove loops by checking the offset segment direction against the source: drop offset points where dot(segment_offset, segment_centre) <= 0 (backward-running segments), and re-splice. O(N), no intersection tests; leaves small corners rather than loops. Good enough for pen work.
5. **Geometry via distance field**: draw isolines of the signed distance to the centreline family, at d = ±w/2 (prototype `distField` + `isolines`). No cusps by construction (isolines of a distance field cusp only at the medial axis, where they simply terminate), can restate bands with multiple iso-levels and vary w with a field multiplier. Cost: BFS distance on 65k cells ~ 1 to 3 ms (per family) + isolines ~ 3 ms. The isolines start/stop at the medial axis, which yields natural hooks/terminations. Isoline output is grid-smooth only after 1 or 2 smoothing passes; prototype `isolines(val, valid, level, minLen)` takes a value array so it fits. Recommended as the robust fallback where the offset test finds cusps.
6. **Line density instead of pairs**: hatch-free approach: draw many thin restatements of the same centreline with position jitter drawn from a distribution with s-dependent variance (narrow -> tight cluster, wide -> spread). The bank pair emerges as the cluster envelope. Overdraw density reads as weight. Cheapest and the least rigid; no cusps because every strand is a small displacement of the same smooth curve (use low-frequency perturbation, |dn| < 0.5/|C|).

### Variable width control
w(s) = w0 * (0.15 + 0.85 * noise_lowfreq(s * f)) * (1 + 0.5 * migration_speed(s)) (fast-moving arcs wide: the point-bar/cut-bank asymmetry, borrowed from physics; makes width correlate with process rather than random). To avoid a river reading, decorrelate w from the bends (e.g. use a phase-shifted noise) so width does not follow the bend pattern.

### Convergence/divergence between strands
Two strands from different migration runs (or a family and its own later ghost) can be blended: line(s, u) = (1-u) * A(s) + u * B(s) with A, B aligned by arc-length fraction or by nearest-point projection. Interpolated strands sweep between two shapes, producing "sling bands" (Ian's sketch: a sling band between bulbs) and shared lines. Cost O(N) per strand; alignment by projection needs the hash (one nearest-point query per node ~ 1 microsecond each with the grid).

### Pitfalls
- Offset cusps on tight bends (mitigations 3 to 5).
- Parallel offset strands read as ruled tree rings / engraving (both rejected). Break with per-strand phase noise, dropouts (pen lifts where a strand fades), variable lengths (ends staggered), differing overshoot, and different strand start points.
- Uniform strand count along a family: vary count along s (some strands terminate with inward hooks, some begin mid-stream).
- Coincident strands where u_k cross: fine visually (tangle), but merge duplicates in post using the occupancy `Sheet`.

### Cost
Offsets: ~ N*K points, K<=7: ~ 3500 points, microseconds-ish (< 1 ms). Distance-field approach: 5 to 10 ms. Both far inside budget; the pen-path stage (`handLine`, `walkLine` with the occupancy grid) will dominate, as in v5.

### Aesthetics
Gives: volume illusion through bundles that swell, pinch, cross; economy of ink; a way to read weight differently across a single continuous form. Fails: bank pairs read instantly as a river or road or ribbon (strongest risk); bundles with constant separation read as multi-lane track marks; too-clean offsets are the "tight ruled parallels" already rejected.

## 6. Existing implementations and what is borrowable

- **meanderpy** (Sylvester, Python + numba; github.com/zsylvester/meanderpy; verified by fetch). Borrow: the kernel/recurrence form, defaults (omega -1, gamma 2.5, CFL factor 0.5, crdist 2 W, resample each step, padded ends), `ChannelBelt` with saved timesteps, cutoff loop removal via slicing. Not borrowable directly: the O(N^2) cdist cutoff test and spline resample per step are too slow for the JS budget; replace with hash + linear resample. It also produces a stereotypical river look; use only the mechanism.
- **Hodgin, *Meander* (2011?)** **(unverified from memory)**: reportedly a curve-flow/migration piece rendered as a map of bends with fine contour-like bands. I did not fetch write-ups. Treat it as the look to avoid rather than something to borrow.
- **Howard & Knutson 1984**, **Ikeda, Parker & Sawai 1981** **(unverified; from memory)** as above.
- **Schwenk, Foufoula-Georgiou, and others** on curvature-driven models and cutoff statistics **(unverified, name recall only)**; Not needed.
- **Kinoshita 1961/ Langbein-Leopold sine-generated curve** **(unverified)** for seeds.
- Prototype internals I read the signatures of but did not read the code of: `resample`, `smoothPts`, `polyLen`, `distField`, `isolines`, `Sheet`, `walkLine`, Catmull-Rom hand in `t_hand.js`. The recommendations above assume these behave as their names suggest; verify before relying on them.

## 7. Suggested composition of the techniques (for the meander-round planner)

1. Seed: 1 to 3 band-limited noise centrelines (not Kinoshita) crossing or nearly crossing the sheet at odd angles; spatially varying k_l (noise) so bends differ in ripeness.
2. Run 600 to 1500 steps of the recurrence model; snapshots every ~8 steps; cutoffs by hash.
3. From the history choose ridge subsets by displacement threshold and truncation (section 3). Do not draw every snapshot; do not draw the "current" centreline as a bank pair.
4. Convert only some of the families into strand bundles (section 5, option 2 or 6), leaving others as single thin lines.
5. Hand pass: `handLine` with restatement and drift; hooks at strand ends; sling bands via interpolated strands between neighbouring families.
6. Registers: bundles/scroll-bar density near active bends; sparse single lines along reaches; oxbow fragments as open hooks. Negative space: leave large areas of the sheet ungenerated by lowering k_l to zero and dropping ink there.

Total estimated cost per thumbnail: migration 0.1 to 0.15 s (upper end), family selection ~ 20 ms, bundle offsets ~ 5 ms, hand pass and occupancy ~ 50 ms (from v5 experience, unmeasured). This is at the edge of the 0.2 s target; the levers are N (300 rather than 500), step count (600 rather than 1500 with larger dt), and snapshot cadence. Measure first.

## 8. Open questions for the round
1. Does the drawing want the migration *history* (ridges, family) at all, or just the final shapes as a source of skewed, leaning open strokes? The second is much cheaper and more abstract.
2. How is the line kept from reading as a river: is a distinct convention wanted (no closed oxbows, no banks)? I recommend yes.
3. Should the migration law be steered (k_l noise) or the seed be authored (a hand-drawn schedule of bends per seed)? Steering is more seed-variable; authoring gives composition.

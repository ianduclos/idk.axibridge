# Meander 5 brainstorm: mutations within echo trains (Opus, 29 September 2026)

This builds on the core mechanism the lead already chose, the echo train. Echo k+1 is derived from echo k, never from the source, so any mutation applied to echo k is inherited automatically. Each mutation below is therefore a change to one echo, or to the train's state, that the next offsets carry forward. Notation: `P` is the echo polyline, `n(s)` is its unit normal toward the train side, `κ(s)` is its signed curvature (smoothed over 6 mm), `g` is the train's current gap, and `m` is the Mutate dial.

## 0. The base rule that every mutation rides on: curvature-driven migration

Offset each point by `d(s) = g·(1 + β·κ̂(s))` instead of a flat `g`. Here `κ̂` is curvature normalised to the train's mean, and `β = 0.25 + 0.6m`. The outside of a bend moves faster, as a migrating bank does, so bends grow and lobes elongate. The train drifts away from concentric by itself, which is the most important protection against the tree-ring look. Clamp `d` to 0.4–3 mm and resample at 0.5 mm after every echo.

## 1. Mutations

| # | Mutation | Geometry | Trigger | Heredity | Cliché risk | Kill |
|---|---|---|---|---|---|---|
| 1 | **Swale (spacing jump)** | Set `g ← g·j`, with j drawn from {0.45, 1.8–3.2}, for one echo | Per echo, `p = 0.06m`, never in the first 2 echoes | The new `g` becomes the baseline, and later echoes random-walk from it (±8 %) | Rhythmic barcode if the jumps are periodic | Per-train gap CV < 0.25 on more than half the trains → raise j's spread |
| 2 | **Buckle** | Add `a·w(s)·sin(2π(s−s0)/λ)·n(s)` over a 15–45 mm window, where w is a Hann window, a = 1–3 g and λ = 8–20 mm | Per echo, `p = 0.05m`, centred where \|κ\| is lowest (on a straight reach) | Migration (§0) amplifies the bump echo by echo. The train grows its own meander, the river's instability | Uniform squiggle, the "sine-wave border" | The same λ repeated on more than 3 trains in a sheet → widen λ |
| 3 | **Cutoff → oxbow** | Look for a neck where two points more than 3 λ apart in arc length lie within 1.5 g in space. Splice the chord across the neck, and emit the cut loop as a closed stroke | Automatic whenever a neck forms (buckles and migration produce necks) | Later echoes derive from the shortcut, so the train straightens past a scar. The oxbow is orphaned but may carry 1–3 inward echoes of its own, with a shrinking gap | Beads or blobs if several fire | More than 2 oxbows per train, or any oxbow under 6 mm across → drop it |
| 4 | **Chute (inherited break)** | Delete a 3–8 mm window from echo k. Every later echo keeps a break at the nearest-point projection, widened by ×1.15–1.4 | `p = 0.04m` per echo | The break widens outward, cutting a channel through the set that fans open | Dotted and dashed rows, the Morse look | Break width over 40 % of echo length → stop widening |
| 5 | **Shear / fan hinge** | Vary the gap along the arc, `g(s) = g·(1 + φ·(s−s̄)/L)` with φ = ±0.3–0.9, and slide the ends by δ = 1–4 mm along the tangent | Once per train at birth, `p = 0.3 + 0.4m` | φ compounds, so the echoes diverge from a pivot: one end packed, the other open. This is the "fanned repeat" | Radial sunburst | The pivot's echoes cross, or lie closer than 0.35 mm → clamp φ |
| 6 | **Split** | Cut echo k at s\*, where \|κ\| is at a local maximum. The two halves become daughter trains with independent `g`, `β` and mutation rolls | `p = 0.03m` per echo, at most one per train | Each daughter inherits the parent's state, then mutates on its own. Divergence reads as a braid | Symmetric Y-forks, the tree look | Both daughters end up with the same g (within 10 %) → re-roll |
| 7 | **Scar (cross-cutting reset)** | Stop the train, then seed a new train from its last echo, offset on the far side, at 25–70° to the old set. Cut the new train's sub-arc as a chord through the old set, with a small κ | `p = 0.02m` per echo, or when the train hits a mask edge obliquely | The new set truncates the old one where they meet. This makes the Mamoré's criss-crossing scroll-bar generations | Tartan, or a regular grid | More than 1 scar per train, or scars on more than half the trains → halve p |

Accumulating smoothing (Laplacian, 1 pass per echo, weight 0.15–0.3) sits under all of these. It gradually erases the source's hand-tremor, and it also softens the mutations, so each one appears, peaks and fades over about 5–15 echoes. That is heredity with decay, not a stamp.

## 2. Placement and seeding

1. **Bend-inside first, alternating.** Seed sub-arcs centred on curvature peaks of the drawn lines, on the concave (point-bar) side, with length about 1.2× the bend's arc. Rank bends by `|κ|·open area on that side`, and consecutive bends along one line take alternate sides, as point bars do. At most about 40 % of any line's length carries a train, so the drawing never looks outlined.
2. **Young first, old in the gaps.** Trains are placed in rank order, and each later train is truncated by the earlier ones. Give the first (dominant) trains the longest runs and the highest mutation rolls, then fill the remaining open ground with short, low-mutation trains seeded from the edges of existing trains, not from the base. Second-generation trains are what make the field feel grown and not outlined.
3. **Continuations and stray planes.** Band ends that exit into open space seed straight-ish trains (κ small, φ large), and those become the fans. A leftover void over 800 mm² that no train can reach is the only place a standalone plane may appear when Source is 0, and each such void gets one plane or none.

Stop an echo when it reaches the mask, another train, the sheet margin, T < 0.1, or a length under 8 mm. Stagger the trimmed ends by stopping each echo end at its own `dist` threshold with ±30 % jitter, never at a common line.

## 3. Dials

- **Source s.** The ground budget splits into `train = (1 − s)^1.3` and `plane = 1 − train`. At s < 0.5, planes may appear only where they cross a base line, or in isolated voids (rule 3), with at most `1 + round(4s)` planes. At s = 1, the Version 8 ground code runs unchanged. At intermediate values, planes are laid after the trains, into what the trains leave empty, so the two never interleave into mush.
- **Mutate m** (0–1.5, marked "over" above 1) sets:
  - β (§0);
  - every per-echo p (linear in m);
  - the per-train mutation cap, `1 + round(3m)`;
  - φ's range.

  At m = 0 the trains are plain offsets. That setting is the tree-ring reference, useful for diagnosis and not a default. Default m = 0.6.

## 4. Round kill signals

1. **Ringness.** The share of train ink with gap CV < 0.2, no mutation fired and at least 6 echoes. If it is over 30 %, the look is tree rings.
2. **Topo.** Adjacent trains running parallel (within 15°) for more than 60 mm across more than 50 % of the sheet.
3. **Hair.** More than 8 echoes lie within 5 mm.

If ringness or topo still fails after β is raised, the mechanism is contour lines at heart. Fall back to Source around 0.3 and report.

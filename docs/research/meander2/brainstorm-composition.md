# Meander round 2 brainstorm: composition (Opus)

Lens: composition. This covers blending the sources, cropping from a larger field, a protagonist for the thin cells, one mass versus all-over, and scale jumps. Before writing I read the round-2 plan, the README, both blind reviews, brainstorm 3 and `t_meander.js`, and looked at sheets A–C, `recipes.json` and Ian's 03:12 sketch.

## What the code says the compositions are made of

Four facts drive everything below.

1. **Every cell is an inset.** Several mechanisms keep lines off the edges:
   - migration is damped by `smooth(6, 20, edgeDist)` and clamped to 6 mm;
   - `trimToSheet` cuts the present to 10–12 mm inside;
   - `noiseWalk` steers home once it is within 25 mm of the margin.

   So nothing on sheets A–C leaves the frame. M02, M04 and M11 have shaped negative space because the mass sits off-centre, but the mass is always a whole figure with a margin around it. That margin is the "placed object" feeling, and it is a composition bug rather than a taste call.
2. **The two sources differ in topology, not in line quality.**
   - Territory: the trunk is the longest contour chain, and the minors are *other, independent* contour chains. The result is scattered bodies that each come with hooks. The families are M06/M07/M14 and M12/M15/M17, and the thin mazes come from here.
   - Nothing: every minor *sprouts off the trunk* (`seedChannels`, the top-up loop), so the drawing is one connected sprawl. That is why "nothing" won 4 of 6 pairs, and it is also why its cells look more like Ian's sketch, which is one connected mass with lobes sharing lines.
3. **Weight is spent without regard to the drawing.** `activityField` is random blobs plus a ridge, placed independently of where the channels are. A band's width is `S0·(0.2+0.8A)·speed`. So when the trunk happens to run through low `A` (M01, M06), no channel earns a band and the cell has no protagonist. The thin cells are an alignment failure between the field and the geometry, not a lack of mechanism.
4. **Budget.** I measured the 6 review seeds in node: about 250 ms per sheet (territory) and 220 ms (nothing). `migrate` accounts for about 110 ms of that, and `seedChannels` for 11 ms (territory) or 1 ms (nothing). The rest is the territory build and render. We are already at the 0.25 s line, so every idea has to be cost-neutral. Migration cost scales with **channel points**, which `maxLen` caps, and not with sheet area. A larger virtual field with the same channels therefore costs about the same.

---

## 1. Sprout graft: an inherited trunk, a sprouted family

**Mechanism.** In `seedChannels`, keep the territory's trunk, which is the longest chain. Then draw only `round(g·(nCh−1))` minors from the other territory chains, and fill the remainder with the existing top-up loop, which sprouts noise-walk minors off the trunk. `g` is an inheritance share in [0, 1]: 0 is the current "nothing" topology on a territory trunk, and 1 is today's territory.

Two refinements matter:

- The sprouts should favour the **trunk's most curved reaches**. Weight the sprout index `i` by `|κ|` from `curvatureOf` instead of choosing it uniformly. That way the sprawl grows where the inherited form bends, and the family resemblance lives in the bends as well as the path.
- Inherited minors are kept only if they touch the trunk's 25 mm neighbourhood. Isolated contour chains are the source of the scattered-beans cells, so they go.

**Cost:** zero. It is a seeding change, and the channel count is unchanged.

**Decision it makes.** Which lines inherit. The seed's big gesture comes from its territory, and everything else is grown from that gesture.

**Cliché.** A trunk with branches: tree, coral or antler. The top-up uses `h ± (0.6…1.4)` rad off the trunk tangent, so if all sprouts leave at similar angles, it reads as a twig.

**Kill.** In an A/B at g = 0.3 against pure nothing on the same 6 seeds, kill it if the reviewer still cannot group the g = 0.3 cells with their territory siblings at better than 3 of 6. If so, the inheritance is still invisible and not worth its code. Also kill it if 2 or more cells read "branch/tree" unprompted.

**Effect on round-2 failures.**

- Territory against nothing: this is the blend the reviewer asked for, and it is the cheapest honest test of it.
- Thin cells: it removes the isolated minors that made M06/M07/M14 mazes.
- One family per seed: kept through the trunk.

## 2. Contour-steered walk: territory as a current, not a skeleton

**Mechanism.** Every centreline is a `noiseWalk`, including the trunk. Its heading update gains one term:

`h += nz·0.12 + w(x,y)·wrap(θ_T(x,y) − h)·0.15`

- `θ_T` is the territory's contour tangent field. Rasterise the chains' tangents on the 5 mm grid that `activityField` uses, and take the nearest direction within 15 mm, sign-agnostic, so it acts as an axis rather than an arrow.
- `w(x,y) = β·(1 − A(x,y))`. In calm ground the walk follows the seed's contours. In active ground it ignores them and wanders.
- Walk length and the home-steer stay as they are, apart from idea 3's edge changes.

**Cost:** one grid build of about 3 ms, plus a lookup per walk step.

**Decision it makes.** Where the drawing obeys the seed and where it departs from it. That is a register boundary drawn by the field. This is Ian's "different registers mixing into each other", with territory as one of the registers.

**Cliché.** A walk that follows a field is a flow-field drawing: streamlines, hair, wind maps. At high β with low noise it is topographic, which Ian rejected.

**Kill.** Kill it if any cell shows two or more near-parallel walks in the calm zone within 8 mm for more than 40 mm; the field is then combing them. Also kill it if the contact sheet reads "flow field / hair" on 2 or more cells. Keep β ≤ 0.6 and make the tangent field sign-agnostic, so walks can cross it.

**Effect.** It gives a family resemblance through *orientation* rather than position. That is more robust to migration, which scrambles positions: the reason inheritance was 0/6. It needs its own review; don't stack it with idea 1 in the same batch.

## 3. Found window: simulate on 1.6× and crop by a work-weighted score

**Mechanism.**

- **Field.** Parameterise `seedChannels`, `noiseWalk`, `activityField` and `migrate` on a field rect `F = {w, h}` instead of the `W`/`H` globals. All of their edge terms already read `W`/`H`. Set `F = 1.6 × sheet`.
- **Source.** For territory, place the sheet's territory chains at a scaled offset inside F. Use the scale factor `1/s` for the chosen zoom, so the family survives the crop. For "nothing", only the start point changes.
- **Channels.** Keep the channel count and `maxLen`. The sim therefore costs about the same, and the field is just emptier around the drawing.
- **Edges.** Remove the edge damping and trimming *inside* F. Keep them only at F's own boundary.
- **Score.** After `migrate`, rasterise every snapshot's `speed` onto a 5 mm grid over F. This is the *work map* `Wk`: where the river actually moved. Build a summed-area table. Evaluate about 150 windows of sheet aspect at zooms s ∈ {1.0, 0.8, 0.62}, where s is the window width over the sheet width. Score each window on four terms:
  - **(a) Mass offset.** The work-weighted centroid is 0.15–0.35 of the window diagonal from the centre.
  - **(b) Shaped void.** The largest empty 5 mm component covers 25–55% of the window and touches at most 2 window edges.
  - **(c) Controlled exit.** The top-decile work cells cut 1 or 2 window edges, never 3 or 4. The number of centreline crossings of the frame is at most 5 in total.
  - **(d) Protagonist.** The best 40 mm sub-window holds at least 3.5× the median work.
- **Render.** Transform the channels, snapshots and events into sheet mm (translate, then scale by 1/s). Clip them to the sheet, then run M2/M3 unchanged in sheet space. Band spacing is computed after scaling, so strands stay at plotted width at any zoom.

**Cost:** about +5 ms for the grid and scoring. The sim is unchanged if points are held constant.

**Decision it makes.** Where the frame is, and at what scale. The composition is found after the process instead of being imposed on it. Something leaves the page, the void has an edge on one side, and there is a weight centre.

**Cliché.** The inset-map or "detail crop" look. It appears when the frame cuts many lines evenly on all four sides: an excerpt of a texture. Term (c) exists to prevent exactly that. At s = 0.62 a single bend can also look like a logo.

**Kill.** In 24 crops:

- more than 60% of winning windows put the mass in one quadrant (the score is composing, not the process);
- the reviewer names "map / detail / excerpt" on 3 or more;
- fewer than half show any line leaving the frame (then the crop added nothing over today's inset).

**Effect.** It fixes the inset margin (fact 1), and it is the only idea that makes negative space *open* rather than surround. It gives scale jumps for free through s. Term (d) gives thin cells a protagonist by choosing a window that has one.

## 4. Work map as the activity field: weight where the river worked

**Mechanism.** Keep `A` for the *simulation*, where it seeds the variety. For M2/M3 (band width, history keep-rate, `cross` permission, search placement), read instead:

`A_r = mix(A, norm(Wk)^γ, μ)`

- `Wk` is the work map from idea 3, blurred at σ = 10 mm. On its own sheet-size field it costs about 2 ms.
- `γ` is the concentration exponent. γ = 1 spreads weight in proportion to work. γ = 3 hands nearly all weight to the single reach that migrated most.
- The ranking of minors for `S0 = 4` in the M2 block then uses `A_r`, so the two banded minors are the two that did the most. Today they are the two that happen to sit in random blobs.
- Search spots use `A_r > 0.55` as now, so the tangle joins the protagonist instead of landing on a stray straight.

**Decision it makes.** Who the protagonist is. The answer is the reach with the most history, which is also where the traces are. Weight, history and tangle agree on one place, and that agreement is the "coherent" half of Ian's "stranger yet coherent".

**Cliché.** Everything happens at one U-turn in every cell. It is a formula: M04's U-turn, repeated.

**Kill.** Kill it if 4 or more of 6 protagonists are the same shape: a U-turn at the largest bend. If that happens, randomise between the first and second work peak. Also kill it if the thin-cell seeds 7 and 3 still show a "no protagonist" verdict at γ = 2.

**Effect.** It targets M01, M06, M07 and M14 directly, with no new process: weight that was already spent is simply spent where the geometry is. It is also a sensible fix for the reviewer's "bands applied after the fact": width now comes from the migration speed at two scales, local (as today) and regional.

## 5. Gather/scatter as a per-seed decision

**Mechanism.** Draw one scalar per seed, `m ∈ [0, 1]`, from a bimodal distribution: 40% in [0, 0.2], 40% in [0.8, 1], and 20% in the middle. That gives "bit of either" plus a few in-betweens. `m` sets four existing constants together:

- **Home-steer target.** `noiseWalk` steers toward an off-centre attractor, `(0.3…0.7)W, (0.35…0.65)H`, over a radius `lerp(0.45, 0.2, m)·W`, instead of steering toward the sheet centre at 25 mm from the edge. A high `m` pulls the walks into one mass; a low `m` lets them roam.
- **Sprout spread.** Choose the index along the trunk from the middle `lerp(100%, 35%, m)` of its length.
- **Blob count and field shape.** One broad blob when `m > 0.6`, and three plus the ridge otherwise. This goes through idea 4's γ = `lerp(1, 3, m)`.
- **`maxLen`.** Multiply by `lerp(1.3, 0.8, m)`. Scattered drawings get longer channels; massed drawings get shorter, more bent ones.

It is one decision, visible as a page knob ("Gather", with Auto = drawn from the seed). The recipe records `m`.

**Decision it makes.** One mass or all-over, made explicitly and early, instead of emerging by accident as it does today (M02 massed, M06 scattered, and nobody chose either).

**Cliché.**

- High `m` makes a clot: a ball of string with a margin, which is the "placed object" again.
- Low `m` makes wallpaper.

**Kill.** Kill it if a reviewer can't sort 12 blind cells into mass and all-over at 10 of 12 or better; the knob is then not legible. Also kill it if the high-`m` cells read as "a ball / knot / clot" on 2 or more. In that case pair high `m` with idea 3's exit term, so the mass is cut by an edge.

**Effect.** It makes Ian's axis a controlled variable for review, rather than something that falls out of the source. It also stops the source choice from carrying the composition, which is what confounded the round-2 A/B.

## 6. Lag by activity: scale jumps from one rule

**Mechanism.** In `seedChannels`' `mk()`, set each channel's `lag` (the Howard–Knutson damping length, which sets the bend wavelength) from the activity at its seed point:

`lag = lerp(45, 4, A(p0))·(0.8 + 0.4·rng)`

Scale `ds`, `neckW` and the sprout walk's noise wavelength (`s/45` → `s/lerp(60, 12, A)`) by the same ratio. The minimum `ds` is 0.8 mm, which keeps the point count bounded. One or two channels in hot ground become tight, restless, small-λ meanders, while the trunk in calm ground stays long-wavelength. That puts wavelengths about 6–10× apart on one sheet from one rule, and it is brainstorm 3's two-scale rule without running two sims.

As a side effect, the terminal curl size varies with λ, so the identical spirals of M12/M15/M17/M18 stop being identical.

**Decision it makes.** Scale, and so where the drawing becomes textural (small λ, many snapshots in a small area) and where it stays organic line.

**Cliché.** Small λ with occupancy respected is brain coral or fingerprint. That is why hot ground must also carry `cross` (which it does already, at A > 0.72).

**Kill.** Kill it if any small-λ channel reads as evenly spaced wiggles: the CV of its bend spacing is below 0.3, or a reviewer says "coral / fingerprint / intestine". Also watch cost: kill it if the small-λ channels push `migrate` beyond +30 ms.

**Effect.** The scale jump and the missing texture-by-density register both follow from this, and it is the natural partner for the tangle work in item 1 of the plan.

---

## Ranking

1. **Found window (3), with the work map (4) as its score and its render field.** The two share one grid. Together they attack the three largest composition failures at once:
   - the inset margin, which no parameter today can remove;
   - the thin cells, because the window and the weight both go to where the work is;
   - scale, through the zoom.

   The engineering cost is the `F` parameterisation, which is mechanical but touches four functions. Build 4 first; it is testable alone on the current sheet.
2. **Sprout graft (1).** It is zero-cost and answers the round's open source question directly. It fixes the topology that made the territory cells scatter, and it keeps the one-family-per-seed virtue. Review it at g ∈ {0, 0.3, 0.6} on the six seeds before touching anything else, so the source question is settled on clean evidence.

Ideas 5 and 6 are round-3 material. 5 is a knob that needs 3 and 4 to be meaningful, and 6 belongs with the tangle work. Idea 2 is the riskiest, because of the flow-field look, but it is the only one that makes inheritance survive migration.

## Wild card: the off-frame protagonist

Use idea 3's field and score, but **invert term (d)**: the window must *exclude* the top work peak, the trunk's hottest reach, while keeping at least 60% of that reach's history traces, oxbows and abandoned minors. The strongest force in the drawing lies just outside the paper, 10–40 mm beyond one edge. The sheet shows only its consequences:

- scroll fragments that stop against a line nobody drew;
- a band entering from the edge at its widest;
- minors bent toward something unseen.

It is brainstorm 3's "headless channel", made by framing rather than by withholding, so it costs nothing. It is the most direct route to "make you ask what's really going on". Kill it on sight if the in-frame part reads as debris without a pull, meaning the reviewer can't say which edge the "thing" is behind. Run it on at most 4 cells of a sheet, never as a default.

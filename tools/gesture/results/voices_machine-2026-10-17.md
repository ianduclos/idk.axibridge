# Round 9 — machine voices and diagram voices — 2026-10-17

Thread `voices_machine`. Two kinds of voice that no human hand taught: **machine
grammars**, generalised from the round-8 chain-joins "failure", and **diagram
voices**, where the system's own measurements are drawn as plotter line. Both
are kit modules: auto-discovered files, recipes beside every image.

```
.local/gesture/.venv/bin/python -m experiments.voices_machine [alone handover annotated shadow charts limb numbers]
```

## What was built

`gesture/kit/voices_machine.py`. Six machine grammars. Each is one pure
rewrite `rewrite(points, rng, unit) -> points`, so the same rule can speak a
whole line or a stretch of one:

| # | grammar | rule (obeyed everywhere) |
|---|---|---|
| 1 | compass | only k headings exist; the turtle follows the source and turns only when its error exceeds unit/2 (odd k gives no way straight back) |
| 2 | ruler | least-squares straight runs, corners at the runs' intersections, each corner overshot by a draftsman's tick |
| 3 | stair | rook moves on a rotated grid |
| 4 | koch | the source is decimated to a polygon; every edge is replaced recursively by ONE motif, drawn once per line |
| 5 | lsys | the source's turns are tokenised as L/S/R, rewritten by `rules`, then drawn by a turtle at a fixed angle and step |
| 6 | codebook | the source is cut into unit tokens and k-means'd into k prototypes; every token is redrawn as its prototype (the k-NN attractor exploited on purpose) |

- voice **`machine`** re-speaks a learned hand's line in one grammar.
  `source_part` makes several machines speak the SAME line.
- modulator **`handover`** gives stretches of an existing Mark to machine a/b
  (alternating), choosing them `at` = seams (where the drift changes hand) /
  even / random / straight (where the hand is straightest, the attractor's
  own taste). Each stretch lands back on the hand's line: a small end error
  is sheared out (runs stay straight), a large one goes through a similarity
  on the chord. It writes the `machine` channel (nearest). It appends
  `machine:<id>` to `meta["voices"]` and the `voice` channel, so every voice
  diagram shows the machine speaking. Every other channel is carried by
  `remap`; this is tested with `timing`'s `dance_t` and `tremor`.

`gesture/kit/voices_machine_diagram.py`:

- charts **kappa** (seismograph rows; seams ticked and named; machine
  stretches bracketed), **route** (one lane per voice, its local share),
  **tempo** (the 2/3-power-law speed v ∝ κ^-1/3, plus t(s) and r(s) after
  `timing`), **phase** (the (κ, dκ/ds) trajectory, tanh-compressed), **atlas**
  (inflection tokens, chord-levelled, sorted by turning, numbered) and
  **ledger** (a stat table drawn with rules, one row per decile).
- labels use a 3×5-grid stroke font (uppercase, digits, signs). It is machine
  lettering and never Arabic.
- voice **`diagram`** is a chart as a piece in itself. `of_part` measures a
  neighbour part's line, `machine_a/b` hand the measured line over first, and
  `aspect` fits grid cells.
- modulator **`annotate`** draws the chart of the marks it receives, after
  every earlier modulator: `below` / `right` (the drawing is refit into the
  rest of the box) or `shadow` (a second line follows the drawing at
  distance gap + gain·m̂).
- **the limb, `drawn_by`**: every chart polyline is redrawn through a hand
  (`grammar.restyle` in a shared 1000 px frame). `keep` sets how much chart
  shape the hand must keep; `amount` sets how much fine turning it owns.

## Numbers (`numbers`, seed 9100, k = 5)

| # | voice | vertices | distinct headings (1°) | corners/R | median abs κ·R |
|---|---|---|---|---|---|
| 1 | hand (matisse) | 5534 | — | 5.4 | 8.5 |
| 2 | compass | 90 | **5** | 18.0 | 0 |
| 3 | stair | 177 | **4** | 37.6 | 0.4 |
| 4 | lsys | 478 | **6** (5 + chord fit) | 47.6 | 17.8 |
| 5 | ruler | 212 | 127 | 25.3 | 0 |
| 6 | koch | 814 | 290 | 63.3 | 55 |
| 7 | codebook | 616 | 269 | 9.1 | 7.5 |

Rule adherence is exact where the rule is a heading set: compass uses 5
headings and stair uses 4. Handover at seams, share 0.4: 36 stretches, 43.7 %
of the length machine-spoken. Run times: a sheet takes 0.2–1.5 s, a `drawn_by`
kappa sheet ~5 s, and atlas + ledger drawn by a hand ~60 s (restyle per label
stroke).

## Images (results/, recipe JSON beside each)

1. `voices_machine-alone.jpg`: one Matisse line re-spoken by every grammar.
   Compass k3 (a line made only of triangles) and stair are the strongest:
   coherent, strange and still carrying the hand's route.
2. `voices_machine-handover.jpg`: four drift lines hand the pen to two
   machines each. The hand comes back after every stretch, and each machine
   is recognisable on sight. Stair+koch @even (top right) reads most like a
   conversation.
3. **`voices_machine-annotated.jpg`**: a drift + handover (ruler, stair)
   beside its κ(s). Stair stretches show as dense regular combs and ruler
   stretches as isolated spikes on flat ground. The seam labels (MATI / SHIK /
   LICH / M.RULE / M.STAI) read like a score.
4. `voices_machine-shadow.jpg`: the same drawing doubled by its curvature. It
   reads as a ribbon, and the distance variation is subtle.
5. **`voices_machine-charts.jpg`**: one line measured six ways. Phase reads as a
   drawn cushion, route as soft dunes, tempo as a barcode.
6. **`voices_machine-limb.jpg`**: the κ(s) of ONE shikasta line, drawn by the
   machine, Matisse and Lichtenberg. The trace stays readable (same spikes
   and plateaus) but becomes cusped peaks, sagging baselines and hooked
   ticks. Each hand stays distinct.
7. `voices_machine-limb-atlas-ledger.jpg`: the atlas and the ledger drawn by
   Matisse.

## Surprises

- **Hand-drawn labels become asemic script.** Restyled segment-font labels
  turn into pseudo-writing that sits exactly at "threshold legibility"
  (review C): a table that behaves like language without content. The
  ledger drawn by Matisse is the most unexpected image of the round.
- The shikasta line's κ(s) is already a machine trace: piecewise-constant
  arcs with δ corners, a clothoid-token signature. Its own diagram is the
  most "machine" thing in the bench.
- The fidelity sweep (`.local/gesture/out/voices_machine/try6.jpg`) shows one
  dial. keep 0.006 keeps the measurement, keep 0.015 turns it into a drawn
  landscape, and keep 0.04 collapses: the restyle coarse fit fails into a
  single sweeping arc.

## Failures and duds

- **codebook is a dud.** At 3× unit, six prototypes chained with heading
  continuity read as a loose resmoothed hand, so the limited vocabulary is
  invisible. It probably needs either token boundaries made visible (a
  corner at every join) or far fewer, longer prototypes.
- The tempo chart is dominated by machine corners (κ → 0 on straight runs
  saturates v). As a chart it is honest, as a piece it is a barcode.
- `shadow` is under-differentiated at gain 4 mm. Try a larger gain, or route
  as the measure.
- The `grid` arranger squashes full-box charts into wide cells. I worked
  around it with `aspect`.

## Proposed kit-core changes (not made)

1. **Recipe-level "same line" sharing.** `source_part` / `of_part` re-grow a
   neighbour's line at its seed, but they cannot see that part's modulator
   output. A core hook for passing a part's marks to a later part (e.g. an
   arranger-level `annotate_part`), or an arranger that gives every part the
   previous parts' marks, would let a diagram part describe a modulated line
   without the modulator workaround.
2. **`summary()` labels.** These name `hand`/`hands` only, so machine and
   diagram parts show as `machine(matisse)`. Use `part.label` when it is set.
3. **Text in the kit.** The stroke font belongs in a shared helper (other
   threads will want labels).

## Next limb

The diagram as a voice in the drift route: give the hand-drawn κ(s) to
`handover` as a source, so a drawing hands the pen to its own measurement,
then to a machine, then back. Also a codebook that shows its joins.

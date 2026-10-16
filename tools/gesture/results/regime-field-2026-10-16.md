# Regime fields and composition (2026-10-16)

The direction is set out in `docs/IDEAS-gesture-bank.md`, "three regimes that
become one another in space". The regime r is 0 for a line, 1 for a nib and 2
for a shape. It is a property of **where** a line is on the sheet.

Code:
- `gesture/regime_field.py`: fields, hand fields, `compose`, the hatching
  detector, and a stand-in engine.
- `experiments/regime_compose.py`: subcommands `hand`, `sheets`, `one` and `plot`.
- `tests/test_regime_field.py`: 8 tests, about 4 s.

The pipeline uses the real `gesture/regime.py` (`from_field`, `render`) and
`gesture/signs.py` (`place_signs`, `sign_paths`). The stand-in is kept only
for `engine_name="standin"`.

Raw outputs are in `.local/gesture/out/regime_field/` (`sheets.jsonl`,
`grammar_shikasta.json`). The plot candidates are in
`.local/gesture/out/plot_candidates_regimes/`. Nothing was plotted.

Figures:

| # | file | shows |
|---|---|---|
| F1 | `regime-field-fields-raster.jpg` | every preset field over a tree (blue = nib, red = shape) |
| F2 | `regime-field-fields.jpg` | 8 fields × one tree × the Hokusai hand |
| F3 | `regime-field-structures.jpg` | 4 structures × 4 fields, hands keyed to regime |
| F4 | `regime-field-hands.jpg` | 4 hand fields × 3 structures on the `sense` field |
| F5 | `regime-field-coherence.jpg` | bleed, single line, signs/echo/drips on and off, axis on and off |
| F6 | `regime-field-candidates.jpg` | the two A4 candidates |

## 1. Field families

A field is evaluated on unit sheet coordinates. It always returns r ∈ [0, 2],
is deterministic in its seed, and is clamped off the sheet.

| # | family | constructors | notes |
|---|---|---|---|
| 1 | authored | `axis` (tilt, wobble, taper), `bands`, `margins`, `radial` (lobes) | fronts are smoothsteps of width `bleed`, made wobbly by 1-D noise |
| 2 | structure | `structure_field(d, mode)`, with modes `strahler`, `order`, `density`, `trunk` | per-stroke values are splatted with a Gaussian. `strahler()` uses the topology tree's `host` meta |
| 3 | procedural | `noise_fronts` | smooth noise through soft thresholds. The bleed itself varies over the sheet between `bleed_lo` and `bleed_hi` |
| 4 | mixed | `mix`, `maximum`, `minimum`, `offset`, `scale`, `warp` (domain warp), `levels` | presets: `trunk` (trunk + noise islands); `sense` (an axis alternating nib and mass, a right-margin script zone, a top centre column, noise islands, warped) |

**Hand fields** give each position a set of weights over the hands:
- `hand_zones`: soft Voronoi over noise;
- `hand_bands`;
- `hand_by_field`: hand keyed to regime, with Matisse for lines, shikasta for
  nibs and Hokusai for masses.

A line is cut into runs per hand by `hand_runs`, which uses hysteresis and
switches hand at random inside the bleed (code-switching). Each run is
restyled in its own hand, extended into its neighbours and cross-faded there
(`restyle_line`), so the line stays one line. Junctions are re-welded
afterwards.

The shikasta hand is grammar v6 learned on wc-12, wc-13 and wc-15 only. It goes
through `calligraphy.require_generative`, so album pages are excluded.

## 2. Pipeline

`compose(seed, size, structure, field, hands, signs, tremor, echo, drip, script)` runs:

1. **Structure**, one of:
   - `tree`: one-trunk Oehlen tree, denser than the default (fill .92);
   - `forest`;
   - `grammar`: v6 contiguous lines, already in a hand; with several hands, one
     drawing per hand, keeping the lines whose centroid lies in that hand's zone;
   - `single`: composite single line, chain fix;
   - `line`: one wandering line;
   - or any `Drawing`.
2. **Hands**: runs restyled per line and cross-faded.
3. **Optional script zones**: small v6 drawings in the shikasta hand placed
   where r is about 1.
4. **Tremor**: per-hand default model, applied to centrelines before width, so
   ribbons tremble with their line.
5. **Regime render**: `regime.from_field` then `regime.render`. The nib is 1.3 %
   of H at φ 60°, mass 3 % of H, pen 0.4 mm on A4.
6. **Marks**: `signs.place_signs`, then echoes and drips.
7. **Output**: polylines in px, exported with `composite.to_svg`.

**Hatching detector** (`hatching_families`):
- A mark is short and straight. Open paths are cut at reversals; closed rings
  are taken whole.
- A family is 4 or more marks that are close, parallel and side by side.
- `solid_gap` separates pen-spaced fill, which inks solid, from gapped
  hatching.

## 3. What makes zones one sheet (honest reading)

1. **Fields tied to structure cohere. Authored fields read as overlays.**
   - `strahler` and `trunk` (F2) give a trunk that thickens into a mass and
     branches that thin back to nib and wire, without a seam. This is the only
     place where regimes truly *become* one another along the drawing's own
     logic.
   - `axis` placed at a fixed x crosses the tree, so lines touching it turn into
     beads: a bead chain, not a trunk.
   - `bands` produces a bottom zone of massive pseudo-glyphs ("JAHLB"). It is
     striking, but its border is a straight front, so it reads as collage.
2. **Shared lines are what binds zones.** `single/noise` (F3, F6 right): one
   line runs wire, then swells into a mass, then thins and goes on. That is
   the "a single line that is wire in one zone and nib in the next" case, and
   it looks like one gesture.
   - Its counterpart dud is `single/trunk` (F5): the single line *is* the trunk,
     so everything turns to mass.
   - `single/strahler` is also a dud: a single line has no tree, so it gets no
     regime at all.
3. **Bleed width is nearly invisible.** The abrupt, mixed and gradual noise
   sheets (F5, top row) look identical, even though the fields differ (see the
   histograms in the log). Two things erase the difference:
   - the regime renderer's smoothstep on r, with fill only above r ≈ 1.3, plus
     along-stroke smoothing at σ = W;
   - so the *position* of a front matters and its width does not.

   Subtle transitions will have to come from the stroke (taper and ramp
   operators), not from field softness.
4. **Echoes, drips and signs add relation, not unity.** Drips under masses read
   right: shapes shed lines. Echo shapes are too small to be recognised as
   answers.
   - Signs from `signs.py` (eyes, lozenges, rings, commas) are what carry the
     "something being said" quality.
   - The strongest sign-like moments are **accidental**: in `grammar/sense` a
     big loop holding a dot (an eye) and rings, where signs land inside the
     grammar's own loops.
5. **Hand fields are invisible at sheet scale** (F4). Rows that differ only in
   hand field look alike: the regime dominates perception and the restyle
   texture is small. Code-switching works mechanically (it is tested) but
   doesn't show.
6. **Script zones are mostly a dud.**
   - Short shikasta lines become nib confetti that the hatching detector
     flagged. They are now limited to lines ≥ 8 % of H and 5 per tile.
   - Long ones read as outlined ribbons, not script.
   - The nib regime in general renders as a hollow double line. Next to masses
     it looks like a "pipe", not a broad nib.

**Closest to the reference's sense: `regimes-strahler-tree`** (F6 left):
- an off-centre black axis that becomes a club-like mass at the top;
- a branch thinning through nib into wire;
- a tangle of wire lines;
- small signs.

The reference's script columns and washes are missing. **Bold but far from the
reference: the `noise` sheets**: blobs everywhere, Oehlen-like but uniform.
**Worst:** `margins` (nothing visible), `single/strahler`, `single/trunk`, and
the hand-field rows (identical-looking).

## 4. Plot candidates (A4 portrait, pen 0.4 mm, 25 mm/s nominal)

| # | file | paths | pen-down | pen-up | est. | shares line/nib/shape | hatching families |
|---|---|---|---|---|---|---|---|
| P1 | `regimes-strahler-tree.svg` | 337 | 17.4 m | 13.9 m | 23.6 min | .54 / .34 / .12 | 1 (3 marks) |
| P2 | `regimes-single-noise.svg` | 489 | 21.6 m | 31.8 m | 39.7 min | .41 / .33 / .26 | 1 (2 marks) + 1 solid |

Most of the pen-down length goes to concentric mass fill. The single-dash
families in P1 and P2 are 2–3 parallel marks (sign ticks or near-parallel tree
twigs), not fills. They should be checked by eye before plotting. Pen-up travel
is unordered: run path ordering before plotting.

## 5. Open problems

1. **Nib legibility**: the outline ribbon reads as a pipe. Options:
   - a stronger nib contrast;
   - a concentric fill for r ∈ [0.8, 1.2] on thick parts only;
   - a wider nib only in script zones.
2. **Transitions need stroke operators.** Field bleed is lost in the renderer.
   Drive the operators (`thicken`, `swell`, `terminal_drop`, `shed`) from field
   gradients, instead of sampling r alone.
3. **The `regime.render` fill emits open, clipped concentric arcs** at the fill
   boundary of elongated masses: parallel strokes at pen spacing. They ink
   solid, which is why `solid_gap` exists, but the regime agent may want to
   close them.
4. **Hand differences need regime-aware evidence.** Either make the hands differ
   in what *becomes* a mass, or accept that hand texture is a close-range
   quality.
5. **Script zones need their own structure** (baselines and rows), not tiles of
   grammar lines.
6. **Pen-path ordering and travel** for the candidates.

# contagion: a line that catches a regime's grammar (round 13, thread I-c, 2026-10-18)

**Outcome.** One bold line crosses found ground's found layer: the measurement plate and the far river.
Where it touches a regime, it catches that regime's grammar and carries it along its own path, away
from the source. Then it sheds the grammar and goes its own way. The clearest moment is on the left.
The line touches the river and climbs into the plate as a river: about 80 mm of tight meanders where
no river belongs. On the right it rides a plate rule. It then drops down the sheet as a dead-straight,
ticked axis and crosses the river. There it catches the river while it still carries the ruling. The
river surfaces only once the ruling wears off, as a few whole bends in the blank. Then the line is its
own again. Images only, nothing plotted, nothing downloaded.

## What "catch" means here (and how it differs from ride)

- **Contact = found ground's ride.** The line is listening, and a found contour is near and aligned.
  The line rides it 0.9 mm beside, for 10–15 mm. This is the visible onset.
- **Catch.** Where the line leaves, its own path is redrawn in the regime's grammar. The grammar is
  generated fresh from statistics measured on the found layer as pasted, so it is at the sheet's
  scale. No piece of the source is pasted.
  - **River.** Langbein & Leopold's sine-generated curve, with every parameter measured on the far
    river:
    - per half-bend, the heading's swing (median 78.7°) and length (median 4.6 mm), from 92 bends,
      fit as a bivariate log-normal;
    - the mean swing profile. It is nearer a straight ramp than a cosine, which gives the river's
      rounder arcs;
    - calibrated so that a generated river, measured the same way, reads like the found one.
  - **Plate.** Its ruling: dead-straight runs at the plate's −2.5°, or at right angles to it with an
    elbow back. Ticks are the plate's 1.7 mm leader length, 6.3 mm apart (my choice: a quarter of the
    column pitch).
- **The way out.** The grammar is shed in whole elements, never faded. River bends get rarer, and each
  one is still a whole bend. A plate infection loses its ruling first and keeps its ticks longest.
- **Double infection.** While two regimes are carried, their elements alternate. A ruled run is capped
  at 9 mm, so a river bend can get in.

## The piece and the frame

- Frame: 205 × 297 portrait. This is found ground's frame on purpose, so that ride and catch can be
  compared 1:1.
- The found layer is lifted into the top three fifths. The plate sits at the top and the river band
  at 55 %. The lower two fifths are blank: the "another place" that only the line enters.
- The line is `dance_thrusting` at length 4, 0.7 mm, 1495 mm long. Seed **5302**.
- I chose it from 168 seed renders (5100–5447: 144 portrait, 24 landscape) by reading the maps, not by score.

| # | regime | contact | carried | what happens |
|---|---|---|---|---|
| 1 | river | left bank, (58, 150) | 84 mm of own path | meanders climb into the plate; bends rarer from y ≈ 100; last bend at (98, 93), under the C row |
| 2 | plate | rule C5, (183, 96) | 248 mm (the ticks linger) | ticked axis straight down across the river; ruling gone by y ≈ 135, ticks into the blank |
| 3 | river, while carrying 2 | right bank, (172, 146) | 141 mm | ruled runs and ticks first; then whole bends; the last ones sparse at y ≈ 224 in the blank |

- Of the carried river, 176 of 202 mm lies farther than 15 mm from any found river: it was carried
  away, not ridden.
- Of the carried plate, 51 of 95 mm lies farther than 15 mm from any found rule.

## Images (recipe JSON beside each)

1. `contagion-1-piece.jpg`: **the piece** (seed 5302).
2. `contagion-2-map.jpg`: the infections made legible. Colours show what the line is doing at each
   point. Rings and numbered labels mark the contact, the onset, where wearing off starts, and the
   last caught element.
3. `contagion-3-ride-vs-catch.jpg`: the same gesture three ways:
   - nothing caught;
   - **ride only**: the control, `catch = ride`, with the same contacts and nothing carried. This is
     found ground's behaviour;
   - catch.
   Panels 2 → 3 isolate exactly what contagion adds.
4. `contagion-4-grammar-and-duds.jpg`: what "whole" means:
   - the found river;
   - a fresh carried river;
   - the way out, run by the kit's own walk;
   - three duds, in grey (below);
   - the plate's way out: ruling first, ticks last.

## Duds (what taught me)

- **AR(6) heading model** (my first generator, row 6 of image 4). It had the same swing rms (68°) and
  half-wavelength (4.4 mm) as the river, and it still read as jitter with knots: a wobble. Matching
  the statistics was not enough. The grammar is the *bend*: a swing between extrema and its profile.
- **Fade and blend** (rows 4–5): the risk the brief names, drawn out. A shrinking or averaged river is
  a texture, neither river nor line. That is why the way out sheds whole bends.
- **Plate as orthogonal elbows** (first sweeps, `.local/gesture/out/contagion/sweep_*`). Every ruled
  run snapped to the plate's axes, with elbows back. The result read as circuit traces and staircases
  (systematic structure as the headline). The fix: elbows only when the leader is 2 mm to 30 % of the
  run, otherwise a straight chord.
- **One ruled run swallowing a second infection.** A plate run is up to 107 mm, the plate's own rule
  length. While two regimes were active, the river never got in. The fix: `rule_shared`.

## Honest read

- **Axis I test.** Can someone point at where the line took the other regime, and where it went its
  own way? Yes on the left: at the river bank, then up through the plate, then stopping under the C
  row. Yes for the ruling: it starts at rule C5, goes down the right, and ends in the blank. The big
  loops below are the line by itself, in another place. The **double infection is the weak part**.
  In the plain piece it reads as "ruled, then a few bends", not as two grammars alternating. You
  need the map to see that the river was caught at the bank.
- **The risk.** The carried river is whole: real bends with overturned loops, at the river's scale.
  It is not a wobble, and the duds image shows the difference. It is more regular than the found one,
  because its bends are drawn independently. I measured the bend-to-bend correlation on the found
  river (lag 1: −0.05 for the swing, 0.22 for the length). With 92 bends that is not evidence of
  structure, so I did not add any. At 0.7 mm black against the found river's 0.3 mm blue, its loops
  read as a little denser than the source.
- **The plate's grammar is partly mine.** The plate has straight rules and short leaders. "Ticked
  axis" is my reading of "the above graph". It reads as a graph, but the ticks are an interpretation,
  not something the plate itself does.
- **Would Ian keep it?** I think he keeps the procedure, and maybe the piece for its left half. The
  river climbing into the plate is exactly the "line in front becomes the river … then does some
  other thing by itself in another place". The right half is busier and less legible.

## Files

- `tools/gesture/gesture/kit/arrangers_contagion.py`:
  - arranger `contagion`;
  - `river_grammar`, `plate_grammar`, `gen_meander`, `contagion_walk`;
  - channel `catch`, with codes 0 own, 1/2 riding, 3 carried river, 4 rule, 5 tick.
  - It reuses found ground's `Ground`, `_ride`, `_bridge`, `resample` and `tangents` read-only, and
    inks with `oehlen_found_ink`.
- `tools/gesture/experiments/contagion.py`: layouts, `sweep`, `debug`, and `final`, which rebuilds
  all four images. Run `.local/gesture/.venv/bin/python tools/gesture/experiments/contagion.py final`.
- `tools/gesture/tests/test_kit_contagion.py`: 9 tests, about 40 s. They cover determinism across
  `PYTHONHASHSEED`, the ride control carrying nothing, grammar recovery, fresh-not-pasted, and the
  way out shedding whole bends.

## Proposed core changes (not made)

- `arrangers_oehlen_found.py`: make `Ground`, `_ride`, `_bridge` and `_clip_rect` public (or move them
  to a shared `_found.py`). Contagion imports them, and renaming them would break it silently.
- Put the found-layer pasting step (both arrangers repeat it) into one helper.

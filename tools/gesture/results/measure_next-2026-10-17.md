# Round 11 — measure_next: measurement, next versions — 2026-10-17

The numbered atlas pairing (round 10, `measure_pairs-pair_atlas`) is frozen as a
study. This exploration makes new versions beside it, on the specimen side, on
the drawing side, and as new pairings. It takes one risk: a drawing redrawn
from its own atlas.

Outcome: the specimen side gave the strongest new pieces (a taxonomy plate,
specimens with their own κ, new cuts). The risk held better than expected: the
re-chained drawing reads as one line, and the mantis dance re-chained from its
atlas is the best image of the set.

Code: `tools/gesture/gesture/kit/measure_next.py` (one new kit file; it imports
`measure_pairs` and `voices_machine_diagram`, edits neither). Driver:
`experiments/measure_next.py`. Tests: `tests/test_measure_next.py`, 37 passed
in 7 s. Outputs: `.local/gesture/out/measure_next/` (every image, recipe
beside each, `numbers.json`). 14 copies here as `measure_next-*.jpg` +
`.recipe.json`, each under 400 KB. Every image is one `kit.run` +
`kit.preview`; contact sheets carry their cells' recipes. Each new version is
labelled as a version of its parent ("numbered atlas v2: …", "dance + atlas
v2: …").

## Modules

| # | kind | id | what |
|---|---|---|---|
| 1 | modulator | `measure_next` | the pairing, v2. `cut`: turning (round 10 exactly), inflection, pause, hand, crossing, loops, approach. `norm`: chord, axis, size, axis+size. `trace`: each specimen's own κ under it. `plate`: grid, frieze (packed by width), exploded (with a length `cap`), taxonomy (families in rows; `group` by shape or by hand). `hist`: length or turning, as `steps` or `tally`. `page`: diptych, margin, triptych (drawing, atlas, the atlas re-chained). `shadow`: the drawing in merged-shadow beads. `drawn_by` + `straight`: which lines stay machine-straight. `avoid`: index numbers avoid each other and the line |
| 2 | modulator | `measure_next_rechain` | the drawing redrawn from its atlas. Specimens are re-chained in a new order (time, sign, turning, length, match, family, reverse, shuffle) into one line. `rotate: false` is the collage baseline. Writes a join report into the mark's meta |
| 3 | modulator | `measure_next_rehand` | the drawing re-spoken specimen by specimen; the hand changes at every specimen boundary; ends pinned, joins blended |
| 4 | voice | `measure_next_duet` | a drawing of two voices: two hands, two whole lines on one surface, `voice` 0/1 |

With defaults and `avoid: false`, `measure_next` draws exactly the frozen
pair_atlas (a test compares every point). With defaults, the only change is
that the numbers avoid collisions.

## Images worth Ian's eyes

1. **`measure_next-triptych_dance.jpg`** (dance + atlas v2). The mantis dance,
   cut at the dancer's own pauses, then its atlas, then its gestures re-chained
   into ONE line. The dance is 33 separate trails; the third drawing is one
   continuous line, numbered with the same specimen numbers. My read: the risk
   paying off. It reads as a single gesture, not a collage.
2. **`measure_next-taxonomy.jpg`** and **`measure_next-plate_big.jpg`**. The
   specimens sorted into five families by shape (letters A–E, a count, a fine
   rule between families). Labels like "C3" sit on the drawing. In plate_big
   the plate is the main element and the drawing its accessory, with κ under
   each specimen. My read: the most natural-history of the set; the family
   letters on the line make the drawing legible as a mix of kinds.
3. **`measure_next-norm_trace.jpg`**. Every specimen at a common size on its
   principal axis, with its own κ trace under it. Shapes compare at once; the
   traces show which ones are one smooth turn and which ones stutter.
4. **`measure_next-cuts.jpg`**. Six new cuts of the same drift: pause,
   hand change, self-crossing, the loops, closest approach, inflection. The
   loops cut makes a short plate of enclosed shapes (triangles, a teardrop).
   The approach cut is the least obvious: its specimens join places that
   nearly touch.
5. **`measure_next-rehand.jpg`**. The hand changes at every specimen boundary
   (matisse, lichtenberg, shikasta in turn); the plate is cut by hand, so each
   specimen is exactly one hand's stretch. It reads as one line whose texture
   changes, not three lines.
6. **`measure_next-duet.jpg`**. Two voices on one surface. The plate is
   grouped by hand (A = matisse, B = lichtenberg), and the A/B labels on the
   drawing tell the two lines apart where they cross.

Also made: `frieze` (true frieze, packed by width), `exploded` (with a cap),
`shadow` (merged-shadow beads with the atlas from the centreline),
`drawn_traces` (only the κ traces drawn by matisse; Ian's "keep some lines
straight"), `dance_pause`, `river_taxonomy` (river_oxbow, a round-11 hand),
`rechain` (the risk contact sheet). In out only: `hands`, `new_hands`
(dancer_anna, trail_slime, trail_borer, dancer_zachary; uncommitted when
made), `drawn_straight`, `drawn_all`, `triptych`, `triptych_turning`,
`rechain_cuts`, `taxonomy_tally`, `taxonomy_trace`, `loops_size`, every single
cut page.

## The risk: re-chaining the atlas into a second drawing

**It held.** Each specimen carries its entry and exit tangent, taken from the
original over ±1 mm. Each next specimen is turned so it continues the chain's
tangent. Time order reproduces the original exactly (a test checks this to
1e-9 mm). Any other order is G1 at every join.

Join continuity on the seed-7003 drift. A "kink" is a join whose tangent
change over ±1 mm is larger than 95 % of the original line's own (42.8°):

| # | cut / order | joins | median tangent jump | kinks (original at same cuts) | κ jumps |
|---|---|---|---|---|---|
| 1 | inflection / time (check) | 31 | 3.7° | 2 (2) | 0 |
| 2 | inflection / sign, tangent continued | 31 | 3.0° | 2 (2) | 3 |
| 3 | inflection / sign, translated only (collage) | 31 | 39.2° | 13 (2) | 20 |
| 4 | inflection / calm to coiled | 31 | 2.5° | 2 (2) | 4 |
| 5 | inflection / match curvature | 31 | 4.2° | 2 (2) | 3 |
| 6 | pause / sign | 40 | 26.2° | 13 (19) | 26 |
| 7 | pause / match | 40 | 32.1° | 18 (19) | 13 |
| 8 | crossing / match | 35 | 4.2° | 3 (2) | 2 |

The mantis dance (pause cut, 47 joins): match order 3.8° median, 1 kink
(original 2); the collage 73°, 40 kinks.

- **Inflection cuts re-chain almost seamlessly.** Both ends of each specimen
  have κ ≈ 0, so any order is close to G2 as well as G1 (0–4 κ jumps out of 31).
- **Pause cuts sit on turn apexes**, so their joins carry real turning. They
  stay G1, but κ jumps where two apexes of different strength meet. The
  `match` order (each next specimen's starting κ closest to the chain's
  ending κ) halves those jumps (26 → 13).
- **The collage is worse than it looks.** Translated-only chains kink at 13 of
  31 joins, yet at thumbnail size they still pass for a line, because the
  drift is already kinky. The numbers catch what the eye forgives.
- **What it loses.** A re-chained drift no longer has the original's big
  enclosing shapes. It becomes a walk: calm to coiled ends in a knot, match
  becomes a long frieze line. The dance gains from it (scattered trails become
  one line). The drift mostly loses (a strong composition becomes a wander).

## Specimen and label numbers (drift seed 7003, 1555 mm)

| # | cut | specimens | share of the line covered |
|---|---|---|---|
| 1 | turning (round 10) | 28 | 0.84 (short bits dropped) |
| 2 | inflection | 32 | 0.99 |
| 3 | pause | 41 | 0.99 |
| 4 | hand | 21 | 1.00 |
| 5 | crossing | 36 | 0.99 |
| 6 | loops | 7 | 0.31 (the loops only) |
| 7 | approach | 18 | 1.00 |

Index collisions (number boxes the line runs through, and touching pairs),
round 10 placement → `avoid`: pair_atlas 1 → 0; mantis 3 → 0; drift with 32
numbers 3 → 0; aaron 2 → 0. The fix: candidates further out, on both sides,
slid along the line, and joined by a leader. Dense knots still crowd (the
re-chained drift's knot): the placement falls back to the least-bad spot.

Time: every sheet under 1 s, except `drawn_by` (10–31 s with rules kept
straight, 49–118 s when everything is redrawn).

## What failed or is weak

- **Exploded with a cap** works (no arc dominates any more), but it reads as a
  scatter. Two labels still touch (05/02).
- **The tally histogram** (bars made of specimen numbers) is legible only up
  to about 8 per bar. Above that it falls back to steps.
- **The loops cut** finds only 7 loops on this drift. It needs a loopy hand
  (river_oxbow, trail_borer) to make a full plate.
- **`drawn_all`** (everything through matisse, specimens too) distorts the
  specimens, which are the drawing's own lines. `drawn_traces` keeps them
  true; I'd keep that as the drawn_by default for atlases.
- **Shadow + numbers**: the merged-shadow beads crowd the index numbers in
  the dense middle.
- The drift's re-chained second drawing (`triptych`) is weaker than the
  dance's: see the risk section.

## Proposed core changes (not made)

1. `measure_next` relies on private helpers in `measure_pairs`
   (`_new_marks`, `_template`, `_at`, `_chord_frame`, `_rule`) and
   `voices_machine_diagram` (`text`, `measure`, `hand_drawn`). A small
   `kit/_measure_common.py` would make them a contract. Until then, a freeze of
   either file must take `measure_next.py` along (same rule as round 10's
   `_lettering` proposal).
2. `kit.contact(..., recipes=...)`, as round 10 proposed; this driver writes
   the list by hand.
3. Ward clustering for families uses scipy; it is deterministic, but a
   frozen app copy needs scipy.cluster available (the app venv has scipy).

## Next

- Make the dance triptych and the taxonomy plate studies (controls: cut,
  plate, group, families, trace, rechain order, split).
- Re-chain with a cap on the turning run, so calm to coiled does not end in a
  knot (insert a calm specimen after every k coiled ones).
- The taxonomy across hands: one plate of families drawn from several hands'
  specimens, each specimen tagged with its hand.

## Test status

`tests/test_measure_next.py`: 37 passed in 7 s (defaults redraw the frozen
pair_atlas point for point, cuts cover and stay in order,
loops close, crossings and near misses, norms, time-order re-chain is exact,
G1 beats the collage, labels avoid, families are deterministic and ranked,
every plate and page runs and is deterministic, rules stay straight under
drawn_by, shadow, rehand ends pinned, duet voices, histograms, pens). No
processes left running.

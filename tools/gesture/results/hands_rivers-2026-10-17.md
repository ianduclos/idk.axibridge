# New hands from rivers (round 11, exploration 1a, 2026-10-17)

Outcome first:

- Rivers learned as hands are distinct from every existing hand. They are not
  near `meander69` or `matisse`, which was the feared outcome. Their nearest
  hand is `dance_levitation`, a slow, smooth trail.
- The human-band zoom, `river_bend`, is the most distinct and the most
  self-consistent. Its nearest existing hand sits at distance 1.62, with
  AUC 0.99 and leave-one-out self-recognition 1.00.
- Through the kit as a single line, two river hands collapse onto existing
  hands: `river_belt` onto Ingres and `river_threads` onto shikasta. As
  lone lines, they are not new hands.
- A clothoid grammar cannot close a loop. The oxbow outlines are 100 % closed
  in training, but only 1.3 % of the generated strokes close. The fix is a
  voice that builds the loop: `river_loops`.
- Braided channels needed a voice too: `river_braid`. Its threads split
  around island lenses learned from real islands and rejoin. Every thread is
  one contiguous line.
- After Ian's mid-round note, the oxbow work stopped where it was. It is
  kept as evidence and not developed further.

Nothing was downloaded or plotted. No existing file was edited.

## Files

- `tools/gesture/experiments/hands_rivers.py`: stages `extract`, `learn`,
  `measure` and `sheets`. Run with `.local/gesture/.venv/bin/python
  tools/gesture/experiments/hands_rivers.py all`; it takes about 3 minutes.
- `tools/gesture/gesture/kit/voices_rivers.py`: the voices `river_loops`
  and `river_braid`, plus loaders for the library kinds `river_loops` and
  `river_braid`.
- `tools/gesture/tests/test_hands_rivers.py`: 14 tests, about 4 s.
  `test_kit.py` still passes.
- New library entries, 92 KB in total:
  - five hands: `hand/river_bend`, `river_meander`, `river_belt`,
    `river_oxbow` and `river_threads`;
  - `river_loops/river_cutoffs`: 582 oxbow profiles and 885 cut-off-bend
    profiles;
  - `river_braid/river_anavilhanas`: 14 island lenses.
- Raw outputs are in `.local/gesture/out/hands_rivers/`: training drawings,
  grammars, panel caches, `measure.json` / `measure.md`, every tile with its
  recipe, and the contact sheets.

## How the hands were made

- **Line width.** A river's channel width is not ink width. Every river
  drawing gets a nominal width of 0.0025 × R, the dance convention.
  - The standard projector already leaves out the `w_` and `end_` features
    (`hybrid._matrix`), so the placements below are geometry only.
  - The nominal width therefore does not explain why the rivers sit near the
    dance hands.
- **Zoom.** Zoom is measured in channel widths along the channel. Main
  stems come from GRWL tiles SB18, SB19, SB20, SC18 and SC20: single-channel
  segments with a median width of 150–700 m, smoothed at 1.5 w.
  - Each training drawing is one stretch, cut into 5 pieces with 1.5 w pen
    lifts. There are 14 drawings per zoom.
  - The three zooms:
    - 60 w (`river_bend`): κ·R median about 4, inside the human band (2–7.5);
    - 150 w (`river_meander`): about 9;
    - 400 w (`river_belt`): about 21, near round 8's dense river.
  - Round 8 got 33 → 3.8 by shrinking geographic windows. Here the same
    reasoning is applied in channel widths, so zoom is set by the river's
    own scale (wavelength ≈ 11 w).
- **Oxbows.** `river_oxbow` is learned from the OSM `water=oxbow` closed
  outlines.
  - Each drawing holds the oxbows of one 0.12° cell, where there are at
    least 4.
  - The outlines are smoothed at 1/50 of the perimeter, because OSM
    digitising corners are not the lake's.
  - Each outline starts at its sharpest horn.
- **Threads.** `river_threads` comes from the Anavilhanas Sentinel-2 tile
  (Rio Negro):
  - NIR < 700 is water;
  - the narrow channels are the water minus an opening with a 20 px disk;
  - `extract_hybrid` then traces them, and the result is tiled 2×2.
- **Grammars.** All are learned with `grammar.learn(min_len_w=12)`, as in
  round 9. They are saved with `kit.library.save` and carry provenance:
  corpus ids, zoom, extraction method and rights. Policy is generative.

## Distinctness and self-consistency

The standard protocol:

- 74 features, σ ≥ 7 w, medium projection.
- 6 generated sheets per hand at seeds 9000 + i. The library hands reuse
  round 9's cached sheets, which use the same protocol.
- dist = centroid distance / mean RMS radius.
- Self-consistency: each new hand also has 12 sheets. The distance between
  halves A (sheets 0–5) and B (sheets 6–11) is compared with each half's
  distance to the nearest other hand.

| # | hand | nearest existing hand (dist) | 2nd | AUC vs nearest (any) | self-recog | halves A↔B | nearest other to a half | consistent |
|---|---|---|---|---|---|---|---|---|
| 1 | river_bend (60 w) | dance_levitation 1.62 | marden 2.07 | 0.99 | 1.00 | 0.50 | river_meander 1.19 | yes |
| 2 | river_meander (150 w) | dance_levitation 1.31 | marden 1.81 | 1.00 | 0.67 | 1.09 | river_belt 1.04 | no (barely) |
| 3 | river_belt (400 w) | dance_levitation 1.04 | mime_mantis 1.12 | 0.67 (vs oxbow) | 0.33 | 0.62 | river_oxbow 0.77 | yes |
| 4 | river_oxbow | dance_levitation 1.25 | dance_fluidity 1.46 | 0.67 (vs belt) | 0.67 | 0.83 | river_belt 0.75 | no |
| 5 | river_threads | ingres 0.74 | molnar_letters 0.79 | 0.72 | 0.33 | 0.58 | ingres 0.76 | yes |

- **Distance to Matisse / meander69.** Matisse is 3.46 / 2.59 / 1.86 for bend
  / meander / belt; meander69 is 2.96 / 2.34 / 1.28.
- **Earlier hands, for scale.** In round 9 most new hands sat 0.5–1.1 from
  their nearest hand.
- **The zooms against each other.** bend~meander is 1.34, meander~belt
  1.26 and bend~belt 1.54. The three zooms are three hands, not one.
- **Through the kit.** This is what Ian sees: one line per part, 3 parts per
  sheet, every library hand drawn the same way. The picture changes:
  - `river_belt` lands on Ingres, at 0.42 with AUC 0.38;
  - `river_threads` lands on shikasta, at 0.31;
  - `river_oxbow` lands on mime_penguin, at 0.50;
  - `river_bend` stays apart: bubble at 0.99, AUC 0.98;
  - `river_meander` stays apart: bubble at 0.96, AUC 0.94.
  - Read: the dense river's character (repetition of bends) lives in
    sheet-level statistics, not in what one chained line shows.
- **The voices, at kit level:**
  - `river_loops` alone and beside: 1.37 and 1.31 from their nearest
    (bubble), AUC 1.00, self-recognition 1.00. These are the most distinct
    objects made here.
  - `river_loops` knot: dance_staccato at 0.90.
  - `river_braid`: bubble at 1.11, AUC 0.98.
- **Closure.** Strokes whose end comes back within 5 % of the stroke's
  length: 100 % of the oxbow training strokes, 1.3 % of the generated ones.
  The grammar learns the crescent's arcs and horns but not the return.
  `river_loops` closes by construction: the turning function is integrated,
  and the gap is removed as a ramp on the tangent vectors, so no corner
  appears.

## The two voices

- **`river_loops`.** Loop shapes are turning functions θ(u) at 128 steps:
  - 582 OSM oxbow outlines, closed;
  - 885 cut-off bends from Li et al. (589 neck, the rest chute), open, with
    a median neck gap of 0.1 of length.
  - A new loop is one profile, nudged toward a near neighbour, then
    jittered.
  - Modes:
    - `knot`: the host line runs round a closing loop at its sharpest bends
      and goes on, as one line;
    - `beside`: abandoned loops sit on the outer side of the bends;
    - `alone`: loops only.
  - `loop_r` writes a regime value onto the loop points.
- **`river_braid`.**
  - A backbone from any hand, and K threads.
  - Each adjacent pair of threads opens and closes a run of island lenses.
  - Lens length = aspect × width, with the aspect drawn from the 14
    Anavilhanas islands (median 5.0). The half-width profile is a real
    island's.
  - Threads touch at the nodes. `emphasis` marks each split on one thread
    of the pair, so `dev_beads` puts one bead per split.

## Images worth Ian's eyes

1. **`hands_rivers-spec-river_bend.jpg`.** The human-band river (Ian's pick 1).
   - Slow, broad lobes; one line that wanders back on itself; small nicks
     where chunks join.
   - My read: calm and spacious, a hand of few events. The source tile shows
     what it was learned from.
2. **`hands_rivers-spec-braid.jpg`** (Ian's pick 3).
   - Best cells: "4 threads on river_bend" and "beads at the splits". They
     read as a channel that splits around islands and closes again.
   - Island edges are lumpy. That is mostly the threads' own wander plus
     real island outlines; `smooth` = 3 barely changes it.
   - Duds:
     - "6 threads, wide": offset threads cross where the backbone bends
       tighter than the bundle is wide.
     - "on matisse": Matisse's corners shred the bundle.
3. **`hands_rivers-combos.jpg`.**
   - Braid with beads at the splits: my favourite.
   - Drift `river_bend > river_belt > river_bend`: scale jumps inside one
     line; the belt's curls arrive mid-line.
   - Drift `matisse > river_meander > lichtenberg`: works but is not
     surprising.
   - Dud: "oxbow loops as hokusai's stresses". At `loop_r` 1.6 the loops
     become black elongated capsules, the thing Ian dislikes.
   - "Shikasta with abandoned oxbows (nib)" gives odd crescent ribbons.
     Interesting, but this is oxbow work and has stopped.
4. **`hands_rivers-neighbours.jpg`.** Each river hand beside three existing
   hands, at the same seed:
   - its nearest on sheets;
   - its nearest through the kit;
   - its farthest.
5. **`hands_rivers-spec-loops.jpg`.** Evidence only, since oxbows are
   dropped. The loops alone make the most distinct marks of the round:
   crescents, beans and open necks.
6. **`hands_rivers-spec-river_belt.jpg`.** The dense river. Its curls and
   little loops look river-like. It has occasional long straight chords:
   line tokens from piece ends, an artefact of the 5-piece cutting.

## What failed

- **Single-line river hands at kit level.** `river_belt`, `river_threads` and
  `river_oxbow` are not distinct as lone lines; see above.
- **`river_meander` and `river_oxbow` self-consistency.** Their halves are as
  far apart as their nearest other hand. Each has 14 drawings and 42 / 93
  long strokes, which is thin.
- **Few islands.** Only 14 of 32 Anavilhanas islands survive (not touching
  the tile edge, aspect ≥ 1.5, solidity ≥ 0.6). The braid's lens statistics
  rest on few samples.
- **Dente centrelines, JRC transitions, GRWL masks.** These rasters are LZW
  TIFFs, and the research venv has no `imagecodecs`. They were not read.
- **The threads extraction** is fragmentary: T-branches and stair corners at
  20 m px.
- **Width as a hand** (the brief's third idea): not tried.

## Proposed core changes (not made)

1. Add `imagecodecs` to the research venv: a pip package, not a corpus. It
   opens Dente 1984–2020 year-coded centrelines (37 redrawings of the same
   river, as nested migrating arcs), the GRWL masks and JRC transitions.
   These are already on disk.
2. `grammar.learn`/`generate`: a `closed` stroke flag that the chain honours,
   for example a closure-aware final chunk. It would let closed-form corpora
   (oxbows, islands, cells) be hands, not only voices.

## Candidate downloads (not downloaded; for the lead to ask Ian)

Sizes marked "unverified" were not checked against the live listing.

**Seismographs and GPS tracks** (Ian's request):

1. **IRIS SeismoArchives**: scanned analog paper and film seismograms (WWSSN
   and historical), by earthquake and by station.
   - <https://ds.iris.edu/seismo/>; high-res TIFFs (gzip) at 400 dpi, per
     earthquake.
   - Size: several MB per record (unverified); one earthquake's set is
     probably tens of MB.
   - What it gives: a machine drawing a line under the earth's hand. Long
     contiguous traces with bursts (the coda), drawn by a pen, so a hand
     with real ink and real tempo.
2. **Icelandic analog seismogram archive**: about 175,000 drum records
   scanned at 300 dpi, free.
   - <https://seismis.hi.is/>.
   - Size: a 20–50 record sample might be 100–300 MB (unverified).
   - What it gives: the spiral/raster drum record. Quiet lines with sudden
     scribbles; a hand whose events are not the draughtsman's.
3. **GeoLife GPS Trajectories 1.3** (Microsoft Research): 17,621 human
   trajectories, Beijing, 2007–2012.
   - <https://www.microsoft.com/download/details.aspx?id=52367>.
   - Size: 298.7 MB zip. Non-commercial research only.
   - What it gives: walking / cycling / driving lines with stops. Corners
     from streets, loops from wandering; the tempo of a body moving through
     a city.
4. **Movebank Data Repository**: seabird GPS foraging trips, for example
   white-tailed tropicbird (doi:10.5441/001/1.649s6f21) and northern gannet
   (doi:10.5441/001/1.5km7v2s3).
   - <https://www.datarepository.movebank.org>.
   - Size: typically 1–50 MB per dataset (unverified). Check each licence;
     public is not necessarily CC0.
   - What it gives: closed foraging loops (out to sea and back) at the
     human band after rescaling. These are loops that close by behaviour,
     the river_loops idea from an animal.

**Rivers, for better hands:**

5. **Sentinel-2 Pastaza megafan crop** (S2B_18MUC_20240731, AWS Earth
   Search COG, B03/B08/B11 30 km windows).
   - About 25 MB.
   - What it gives: the braided end-member. It would replace the 14 lens
     samples with hundreds of real braid bars.
6. **Frasson et al. 2019 GRWL meander attributes** (Zenodo 2582500).
   - South America sections are 5–36 MB each (manifest).
   - What it gives: per-bend wavelength and sinuosity, to sample bends by
     type rather than by stretch.

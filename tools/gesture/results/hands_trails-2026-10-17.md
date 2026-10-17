# New hands from trails, flies and dancers — round 11, exploration 1b (2026-10-17)

Fifteen new hands are in the library: seven trail hands, two fly hands and six dancer hands.
The fly hands are the strongest result. They sit 4.6–6.4 cloud radii from every existing hand,
and every one of their sheets is recognised as its own. The dancer question has a clear answer:
in these six dancers, identity barely shows in the line. Movement quality shows far more.
Most trail photographs failed as scans, and the trail hands that survived are learned from
very little data. Diwani was learned and measured, then dropped on Ian's call; it is not in
the library.

Code:

- `experiments/hands_trails.py`: stages `extract learn save measure dancers sheets`.
- `gesture/kit/voices_trails.py`: voices `trail_sheet` and `trail_brood`, renderer
  `trail_gallery`, arranger `trail_specimen`.
- `tests/test_hands_trails.py`: 22 tests, about 1 s. `test_kit.py` passes alongside.

Raw outputs are in `.local/gesture/out/hands_trails/`: extraction overlays, grammars,
`measure.{md,json}`, `dancers.json`, and every tile with its recipe in `sheets/`.
Nothing was plotted or downloaded.

## Look at these first

1. `hands_trails-specimens-trails.jpg`. Each new trail and fly hand gets six single lines
   and two whole sheets, at one scale, with a 10 mm bar. The bottom row is the two fly hands.
   Their lines circle into coils and drift between them. `fly_fru` (courtship neurons driven)
   pulls its coils tighter, into knots that read as beads, with bigger lobes between them.
   No other hand in the bank draws like this.
2. `hands_trails-brood.jpg`. This is a bark-beetle brood gallery as a voice. One hand draws
   the mother line and another draws the larvae. Each larva widens and ends in a round pupal
   chamber. Tiles 1 and 6 read most like real galleries. The branching that extraction could
   not keep as a grammar survives here as structure.
3. `hands_trails-miner.jpg`. The leaf-miner hand is inked as a mine. The gallery widens as the
   larva grows and swells smoothly into a round chamber. This is a line becoming a bead with
   no snap. Tile 3 (`fill: late`) turns into a solid bar, the capsule Ian dislikes, so it is a
   dud kept as evidence. Tile 5 drifts through `trail_grazer` and balloons into a wide sail,
   which is strange but worth a look.
4. `hands_trails-answer.jpg`. A trail hand answers a dancer hand or a fly hand on one surface.
   Tiles 3 (`fly_fru` + miner) and 5 (`fly_open` + tracks) work best: the coils against one
   long mine ending in a bead.
5. `hands_trails-atlas-trails.jpg`. Each new hand sits beside its two nearest library hands.

Also:

- `hands_trails-specimens-dancers.jpg`: the six dancers. They look alike, which is the honest
  result.
- `hands_trails-atlas-dancers.jpg`: each dancer beside its nearest library hands.

## Hands saved (library `hand`, own folders, provenance + policy)

Distinctness and self-consistency use the standard 74-feature panel and the standard
preprocessing (σ ≥ 7 line widths + medium projection, `hybrid.projector` on the round-8 real
panel). There are 6 `generate_drawing` sheets per hand, seeds 9000–9005.

The comparison covers every library hand, including the `river_*` hands the other agent saved
during this round.

The columns:

- **dist**: centroid distance in units of the two hands' mean RMS radius. About 1 means the
  clouds touch.
- **tightness**: the hand's own radius ÷ the median radius. Below 1 means coherent.
- **self-recog**: leave-one-out nearest centroid over all hands.

| # | hand | source | nearest library hand (dist) | tightness | self-recog |
|---|---|---|---|---|---|
| 1 | **fly_open** | mosca-draw connectome walks, open field, 5 seeds | dance_staccato (**6.43**) | 5.97 | **1.00** |
| 2 | **fly_fru** | the same, fru courtship neurons driven | dance_staccato (**4.63**) | 3.24 | **1.00** |
| 3 | trail_grazer | Helminthoida + Nereites + Paleodictyon, relief rescue | river_belt (1.49) | 0.27 | 1.00 |
| 4 | trail_oaknet | skeletonised oak leaf (vein net), coarse | dance_levitation (1.44) | 0.57 | 0.83 |
| 5 | trail_slime | slug/snail slime on concrete | marden (1.02) | 0.34 | 0.83 |
| 6 | trail_beetle | didactic bark-beetle gallery relief (insect-03) | river_meander (1.01) | 0.44 | 0.83 |
| 7 | trail_borer | wood-borer galleries, coarse | marden (0.87) | 0.34 | 0.83 |
| 8 | trail_tracks | positron 1932 + three bubble-chamber tracings | molnar_letters (1.04) | 1.39 | 0.33 |
| 9 | trail_miner | aspen leaf-miner galleries, coarse centre-line | river_belt (0.59) | 2.70 | 0.20 |
| 10 | dancer_anna | E2MB "Unusual Poses" | mime_dragon (1.12) | 2.82 | 0.33 |
| 11 | dancer_cristel | ″ | dance_particles (1.02) | 1.44 | 0.50 |
| 12 | dancer_zachary | ″ | mime_dragon (0.60) | 1.56 | 0.17 |
| 13 | dancer_marija | ″ | mime_mantis (0.55) | 1.91 | 0.17 |
| 14 | dancer_madeline | ″ | dance_particles (0.41) | 2.34 | 0.00 |
| 15 | dancer_amber | ″ | dance_particles (0.39) | 2.54 | 0.00 |

How to read these numbers:

- **The fly hands are genuinely new.** They are the farthest from every hand by a wide
  margin. They are loose (big tightness) but always recognise themselves.
  - `fly_fru` vs `fly_open`: distance 3.66, classifier AUC 0.93. Driving the courtship neurons
    changes the hand.
  - Caveat: the walks are simulated. A spiking model of the male CNS connectome drives a
    differential-drive body (Ian's mosca-draw). These are not recorded flies. The paths are
    read in place from `~/_SecondBrain/01_Projects/mosca-draw/out/k4_circulation/`; nothing
    was copied.
- **The tight trail hands are tight because they are tiny.** They are learned from 36–76
  token records (7–20 strokes); the dancers have 3,500–6,000. A grammar with a handful of
  tokens repeats itself, so it looks coherent. Read their tightness and self-recognition as an
  upper bound.
  - `trail_grazer` scores highest of all (5.5). But it learned the edges of fossil grooves,
    not the meander: no hairpins, just hooked arcs. It is distinct, but it is not the
    grazing trace's grammar.
- **trail_miner is the opposite case.** It has the most character of the trail hands: long
  runs, rounded hairpins, lobes. It has only 6 long strokes, though, so its sheets vary a lot
  (tightness 2.7). It lands near the new river hands, which makes sense: a mine meanders like
  a river.
- **Orientation is lost.** Slime trails run vertically down the wall, but the hand learns
  curvature only, so `trail_slime` draws loops in any direction. The panel measures it as
  distinct, but it has lost the gravity of the wall.

## The dancer question: can dancers be told apart?

The data separates dancers cleanly. E2-Create Motion Bank "Unusual Poses" has six dancers,
the same task, and 5–10 min each. The hands use 12 windows of 15 s each, spread through each take.

The test:

- Real trail windows, 8 per class, balanced. Panel space with standard preprocessing.
- The control is the E2 Stocos *movement-quality* set: 8 qualities, the same procedure.

| question | classes | chance | LOO nearest centroid | logistic CV5 | shuffled labels | pair AUC median |
|---|---|---|---|---|---|---|
| **who** (6 dancers, one task) | 6 | 0.17 | 0.29 | **0.17** | 0.16 | 0.75 |
| **how** (8 qualities) | 8 | 0.13 | 0.54 | **0.63** | 0.11 | **0.97** |

**Answer: hardly.** In these line features the instruction outweighs the dancer.

- A classifier names the dancer at chance level.
- The pairwise AUCs split the dancers into two families rather than six:
  - {Amber, Madeline, Zachary} vs {Anna, Cristel, Marija}.
  - Within a family the pairs are 0.40–0.60. Across families they are 0.87–0.99.
- The learned hands agree: dancer-to-dancer distances are 0.46–1.0, except Anna, who stands
  apart at 1.3–2.0.
- Caveats: the comparison crosses two datasets, and two Stocos qualities have only 4 windows.
- I kept all six hands. Anna is the most distinct. The other five behave like dialects of the
  existing dance family.

## What failed (kept as evidence)

1. **Plain extraction on textured photographs: 0 strokes.** Bark (insect-04/05/08), the oak
   leaf and all three trace fossils gave nothing. Hysteresis cannot separate the trail from
   the texture.
2. **Rescue 1, the centre-line at a coarser scale** (downscale to the gallery width, then Otsu):
   - It saved the leaf miners (clean serpentines with hairpins), the oak net and, partly, the
     borer.
   - It did not save the elm beetle: the result is wood grain. `trail_elm` was measured and
     kept out.
3. **Rescue 2, relief photographs read as gradient-energy bands** (the groove is an edge pair,
   not ink):
   - At fine scales it traced rock grain.
   - At σ ≈ 10 px (1200 px image) it found groove edges in fragments, which became
     `trail_grazer`.
   - Helminthoida's U-turns are always lost, and Paleodictyon's hexagon net never came out.
4. **The positron alone is one track**: 7 strokes, 14 records. It was kept out as
   `trail_positron`.
   - Ian wanted particle tracks, so I folded the positron into `trail_tracks` with the
     physicists' tracings of three bubble-chamber events.
   - The eleven other bc photographs extract as bubble outlines, or are not chambers at all:
     bc-15 is an aerial photo of the lab.
   - `trail_tracks` is loose. It sits near molnar_letters because the tracings carry
     handwritten particle labels.
5. **The manifest's "leaf-eaten white oak" is not a leaf miner.** It is a skeletonised leaf, a
   vein net. The real miners are insect-01/02.
6. **insect-03 is second-hand.** It is a didactic wall relief made by people after a beetle
   gallery, not the gallery itself. It is recorded so in provenance.
7. **Diwani** (dropped this round): the policy gate passes only wc-05.
   - wc-39 is an album page. wc-05 is the 1711 Ahmed III letter, which opens with the tughra
     and the sultan's titles, with no devotional invocation; I checked it by eye, and the lead
     should confirm.
   - I learned and measured it as evidence: nearest river_threads at 0.78, loose. It draws
     small curls.
   - It is **not** in the library, and a test asserts that.
8. `trail_gallery` with `fill: late` gives a capsule. Use `chamber`.

## Proposed core changes (not made)

- `grammar.learn` is orientation-free. A trail's dominant direction (slime down the wall,
  galleries across the grain) is lost. An optional heading prior in the hand would help: the
  start heading sampled from training, κ biased back toward it.
- The panel's tightness and self-recognition should report the token-pool size beside them.
  Hands with fewer than about 100 records look coherent for the wrong reason.

## Candidate downloads (Ian's list; nothing downloaded; rights as information only)

| # | corpus | source | size (approx.) | rights | what it would give |
|---|---|---|---|---|---|
| 1 | Late Willem de Kooning drawings | [MoMA collection](https://www.moma.org/collection/works/160641) (85 works online, incl. the 1966 charcoal set 635.2012.x); AIC *Willem de Kooning Drawing* (2026; [coverage](https://galeriemagazine.com/willem-de-kooning-drawing-on-view-art-institute-of-chicago/)) has 1980s linear works; [1980s paintings show](https://www.moma.org/docs/press_archives/7488/releases/MOMA_1997_0001_1.pdf) | 20–40 sheets ≈ 50 MB | © de Kooning Foundation / ARS | loose ribbon loops, long overlapping sweeps: a fast, wide-armed hand |
| 2 | Picasso line drawings | [Museu Picasso Barcelona collection](https://museupicassobcn.cat/en/collection/artwork/lines) (e.g. *Lines*, 1970 graphite); Menil *Picasso: The Line* ([70–100 sheets](https://houmuse.org/?p=9678)) | 30 sheets ≈ 50 MB | © Succession Picasso / ARS | single continuous contour, few corners, very long strokes: a one-line hand to set against Matisse |
| 3 | Sigmar Polke works on paper | [MoMA collection](https://www.moma.org/collection/works/34147) (ballpoint/gouache 1963–66); [MoMA 1999 catalogue PDF](https://www.moma.org/documents/moma_catalogue_187_300100396.pdf) | 20 sheets ≈ 30 MB | © Estate of Sigmar Polke / ARS (reproduction via Art Resource / Scala) | ballpoint doodle, raster dots, deliberately clumsy lines: "useful awkwardness" |
| 4 | Seismograms (paper) | [Iceland analog archive](https://iris.landsbokasafn.is/en/publications/the-analog-seismogram-archives-of-iceland-scanning-and-preservati/) (175k scans, 300 dpi, 4–8 MB each); [IRIS Caltech scans](https://ds.iris.edu/seismo-archives/projects/Caltech_Seismograms.htm); [USGS WWSSN film chips](https://www.usgs.gov/index.php/data/world-wide-standardized-seismographic-network-film-chip-scans) (TIFF ≥ 400 ppi) | 30 records ≈ 200 MB | public / research archives | long drifting baselines with bursts: a time hand (a line that waits and then shudders). Digital waveforms are already on disk (`earth/fdsn-particle-motion`) |
| 5 | Animal GPS tracks | [Movebank Data Repository](https://www.movebank.org/node/15294) (396 datasets, 466 M fixes; e.g. [LifeTrack White Stork Sicily](https://datarepository.movebank.org/handle/10255/move.1343)) | 2–3 studies, 10–200 MB each | per-dataset licence (some need terms accepted) | migration arcs, foraging loops, roost returns at landscape scale |
| 6 | Human GPS tracks | [Microsoft GeoLife 1.3](https://www.microsoft.com/en-us/download/details.aspx?id=52367) (182 users, 17,621 trajectories) | 298.7 MB zip | non-commercial research | street-grid corners plus loitering scribble: a city hand |
| 7 | Liquid stains on fabric | [Fabric Stain Dataset](https://datasetninja.com/fabric-stain-dataset) (Univ. Moratuwa: 466 images, ink/dirt/oil on polyester and cotton) | 416 MB | CC0 1.0 | **not a line hand.** A mass-edge corpus: wicking fronts (ragged, fibre-aligned rims, coffee-ring edges, satellite drops) and the gradient from saturated core to dry edge. That is the grammar of a line becoming a pool, the "smoother transitions into thicker shapes". No time-series wicking set exists that I could find; photographing ink on cloth at intervals ourselves would give the front's motion |
| 8 | Fly flight (recorded) | Dryad [*Wind history shapes olfactory search…*](https://datadryad.org/dataset/doi:10.5061/dryad.gb5mkkx4x) (free-flight Drosophila, 3D, braid-tracked, 10 ms rows); Zenodo [*Long-range search in Diptera*](https://zenodo.org/records/5017751) (tethered flight in VR; per-species HDF5: mosquito 29 MB, hover fly 66 MB, crane fly 67 MB, apple fly 0.3–1.4 GB) | 2.0 GB / 2.9 GB (small files usable alone) | Dryad reuse terms / CC0 | real flies, against the simulated walks: casting zig-zags and plume surges; several species, so a species-per-hand test like the dancers |

The on-disk fly data is simulated walking, not recorded flight. Row 8 is the recorded
counterpart. The smallest useful start is `mos_vision.h5` + `hover_vision.h5` (95 MB, CC0).

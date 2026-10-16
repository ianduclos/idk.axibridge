# Artists' line: Marden, early computer art, continuous-line drawers, rule-based (research, 2026-10-16)

Ian's picks as hands for the gesture bank. Candidate list:
`artists-line-candidates.csv` (169 rows, Marden-heavy). Method: museum API and
open-data metadata only (AIC API, V&A API, MoMA and Tate open-data CSVs, Met API),
plus web search. **Nothing was downloaded** (HEAD requests only). Each download
still needs Ian's go. Rights are recorded as information, not as a filter.
**†** = general knowledge, not source-checked.

## Short answer

1. **Marden is well covered but not in one place.** No museum holds a big run
   of the 1988-91 Cold Mountain stick drawings online. What exists: the Art
   Institute of Chicago (AIC) has the late stick/brush ink drawings at huge
   size (*Sepia Drawing II* 6439x9442, *2 Red Rocks 3* 6037x4515, *Aphrodite
   (Negril) with Green* stick drawing) plus *Zen Studies* 1-6 (3000 px). MoMA has
   about 22 Marden ink drawings online (St. Barts 10, Hydra, Rain, Aphrodite
   Study, Muses Drawing 5, Phuket, 4 Howell Paper Drawings x5, Suicide Notes,
   Greece Summer x12) but only at 1024 px. The Matthew Marks 1991 show
   ("Recent Drawings and Etchings") checklist lists 18 ink drawings, 11 of
   them from the St. Barts and Hydra groups, with images on the gallery site.
   The complete series is in Brenda Richardson, *Brice Marden: Cold Mountain*
   (Houston Fine Art Press 1992, 151 pp, ISBN 0939594307); no digital copy found.
2. **Early computer art is the best-served group.** The V&A API has
   high-quality IIIF images (2500 px long edge, reachable by curl, no gate): Cohen
   about 55 records, Mohr 22, Molnar 15, Nake 15, Franke 25, Noll 7, Nees 7,
   Henry 3, Bangert 21. Vera Molnar plotter pieces and Cohen's AARON plotter
   line drawings are the best fit (contiguous pen lines).
3. **Rule-based** (LeWitt, Martin, Darboven) need little scanning. LeWitt wall
   drawings are instructions; the title field of the AIC wall-drawing records
   already holds the rule text. Agnes Martin is the tremor-on-a-straight-line
   corpus.

## Marden: what the line offers, tools, and the hand

Geometry: a single unbroken, slow-drifting line that wanders, loops back, ends in
a deliberate stop; letter-like glyph units (Chinese-calligraphy structure, read
top to bottom, right to left) joined into a composition; strong curvature
variation with few cusps; width and wetness change along the stroke. Tools:
sources describe him dipping **sticks and twigs** in ink (instead of brushes) for
the Cold Mountain drawings; the AIC catalogue record for *Aphrodite (Negril) with
Green* says "stick and black and colored inks". Long-handled brushes and sticks
of 1-2 m for the big Muses/Cold Mountain paintings are widely reported †. For
modelling: stick-drawn line has near-constant width, blobs at starts and
turns, dry/scratchy edge, and a hand-held distance from paper that makes the line
smoother than a brush line. Sugarlift etchings (Zen Studies) transfer the same
stick/brush gesture to the plate, so the printed line is the drawn line (MoMA's
note on sugarlift supports this).

| Source | What | Count | Resolution | Notes |
|---|---|---|---|---|
| AIC API | Sepia Drawing II, Red Rocks 3, Aphrodite (Negril), Hydra, Zen Studies 1-6, Muses study | 12 | 3000-9442 px (source) | IIIF behind a Cloudflare challenge for curl; non-PD delivery cap unverified. Browser fetch needed |
| MoMA CSV | ink drawings 1972-2007 (St. Barts 10, Hydra, Rain, Muses 5, Phuket, 4 Howell) + etchings | ~25 | 1024 px only | direct image URLs in the CSV |
| Matthew Marks 1991 | St. Barts 2-12, Hydra Summer 1990 I-V, Venus, Virgins, Summer Scroll #8 | 18 drawings | not verified | page has installation views |
| Tate | Zen Studies 1-6, Han Shan Exit, 25 etchings 1986, 1977 and 1973 sets | ~60 prints | small (page) | dataset thumbnail paths 404 |
| Walker, Whitney, SFMOMA, Met | Zen Studies set, *Bridge Study* (ink, wash), Cold Mountain 6 | few | verify | Whitney 8025 is the nearest museum drawing to the paintings |

Usable line-dominant Marden drawings online: about 30 on the stick/brush ink side
(1986-2000s), 6 + 6 + 6 + 2 early/late etching states. The 35 Cold Mountain
drawings of 1988-91 are mostly private collection or catalogue only; auctions
(Christie's, Phillips *Study for Cold Mountain 3*) show a few. Marden had also
the Dia/Walker/Menil show 1991-92 (Dia page in the CSV).

## Computer art lineage

| Artist | Offers | Source | Count | Notes |
|---|---|---|---|---|
| Harold Cohen / AARON | closed, self-intersecting, wavering outlines of figures and foliage; occasional pen-running-dry; hand colour added later | V&A (gift of Cohen), Tate T04167, CHM | V&A 55, Tate 1 + 1960s prints | best on-direction set; "20:28" 1985 is a plotter contour |
| Vera Molnar | slightly broken, perturbed rectangles and "Parcours"; plotter | V&A 15, MoMA *Molndrian* | ~17 | line deliberately imperfect |
| Frieder Nake | *Hommage a Paul Klee 13/9/65 Nr.2*, Walk-Through-Raster, random polygons | V&A | ~15 | straight-line segments, plotter |
| Georg Nees | *Schotter*, wobbly grids | V&A | 7 | segments, small perturbation |
| A. Michael Noll | *Gaussian-Quadratic*, *Ninety Parallel Sinusoids* | V&A | 7 | analog-style lines |
| Desmond Paul Henry | drawing-machine curves (Serpent, On the Beach) | V&A | 3 | smooth looping, most "contiguous" |
| Manfred Mohr | P-series cubes: straight segments, no hand | V&A | 22 | B tier |
| Herbert Franke, Csuri, Bangert, Schwartz | oscillograms; Random War | V&A | various | B tier |
| compart DADA (Bremen), ZKM, Kunsthalle Bremen | largest early catalogue | compart | thousands † | https refused, http works; no bulk API found |

V&A rights: still in copyright, non-commercial licence; fine for private line statistics.

## Continuous-line drawers

| Artist | Offers | Best source | Count |
|---|---|---|---|
| Calder | pen/ink drawings and wire-portrait lines (*Mary Reynolds* 1955, 7863x9841; 1931-32 ink) | AIC 35, MoMA 12 drawings | ~20 |
| Picasso | single-line animals: *Taureau* 1938 ink, *The Cock* charcoal; Minotaur 1933 | MoMA 50 drawings, AIC 199 | pick ~6 |
| Cocteau | contour portraits, near continuous | AIC 14, MoMA 4 | ~10 |
| Ellsworth Kelly | plant contour: *Branch of Leaves* 1969-70, *Wild Grape*, *Pine Branches* | MoMA 95 drawings, AIC 61 | ~8 |
| Twombly | scrawl, loops; AIC *Untitled* 1960 (10436x7387), Sketches etchings (7000 px) | AIC 100, MoMA 45 | ~8 |
| Steinberg | long pen lines, graph-paper drawings | AIC 69, MoMA 44 | ~10 |
| Klee, Kandinsky | line works, PD in EU | Wikimedia Commons: Klee ~160, Kandinsky ~16 | high-res; AIC Klee 97 |
| Henri Michaux (extra) | ink gesture, asemic writing | MoMA 41 | 5 |

## Rule-based / geometric

- **Sol LeWitt**: instructions are the data. AIC records: Wall Drawing #63, #118,
  #274, #574 (fifteen arcs from the midpoint...), #1257 and #1210 (Scribbles),
  #890; the 1973 Straight/Not-straight/Broken Lines etchings (AIC
  187737-187745) are hand-drawn from rules. MASS MoCA retrospective carries 1,200+
  wall-drawing instruction texts †.
- **Agnes Martin**: AIC *Untitled* 1961 (8271x8212), 1964 (8356x8484), 1990
  (#8), MoMA 6 ink drawings and the *On a Clear Day* screenprints (30, 1973).
  Hand-ruled lines with tremor: a good straight-line-with-tremor corpus.
- **Hanne Darboven**: AIC *Seven Panels and Index* (22573x11434), MoMA 13 drawings;
  wave-writing ledgers. **Bridget Riley**: V&A 21 records, AIC 6: line works;
  low priority.

## Proposed first harvest (48 images, about 80 MB)

Priority order. Ids are the `id` column of the CSV.

1. **Marden stick/brush ink, AIC (6, ~19 MB)**: aic-196093, aic-136976, aic-73496,
   aic-159693, plus aic-229369 (composition only; skip if size matters) and
   aic-187586.
2. **Marden Zen Studies, AIC (5 more, ~12 MB)**: aic-116247, aic-187583, aic-187585,
   aic-187587, aic-187588.
3. **Marden MoMA ink drawings (13, ~1.5 MB)**: moma-35286, moma-35775, moma-37195,
   moma-37245, moma-90707, moma-96606, moma-96607, moma-102386, moma-102387,
   moma-102388, moma-129743, moma-69038, moma-69053.
4. **Cohen (8, ~12 MB)**: va-O499539, va-O499538, va-O499576, va-O499616, va-O499573,
   va-O218310, va-O239975, va-O499577.
5. **Henry, Nake, Noll, Molnar (11, ~16 MB)**: va-O499536, va-O499535, va-O499534,
   va-O211685, va-O239558, va-O1193787, va-O1193785, va-O1193786, va-O1488634,
   va-O216188, moma-417832.
6. **Continuous line (5, ~17 MB)**: aic-5388, aic-5385, aic-159982, aic-196131, moma-85561.
   (Martin 159982 gives tremor-on-straight-line; Twombly 196131 gives scrawl.)

Swap in Matthew Marks images (Hydra I-V, St. Barts) as soon as their file sizes
are verified from the exhibition page.

## Blockers and caveats

1. **AIC IIIF** returns a Cloudflare challenge (403) to curl; use a browser
   fetch or the AIC public data dump. Non-public-domain IIIF size cap unverified.
2. **MoMA images 1024 px**, usable for curvature and composition, thin for tremor.
3. **Tate** dataset image paths 404; the artwork pages hold small images only.
4. **Met**: five Marden records, none with open images. Met v1 search retired
   2026-10-01 (use v1.1).
5. **compart-bremen**: https refused; http works; no API found.
6. **The Cold Mountain stick drawings themselves** are mostly in private hands or
   only in the 1992 catalogue (no digital copy found; NYPL on-site only).
7. Kandinsky and Klee counts come from Commons category totals, not checked
   file by file; US vs EU public-domain status differs.

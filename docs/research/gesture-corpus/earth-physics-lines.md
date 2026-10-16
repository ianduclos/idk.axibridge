# Earth and physics lines as hands (research, 2026-10-16)

Ian asked for non-human line sources: Amazon rivers seen from orbit (his
pick), plus "machine/physics" lines (group C): bubble-chamber tracks,
seismograms and chart traces, lightning and Lichtenberg figures, cracks, leaf
venation, and anything else that draws a contiguous line without a person.
This note covers what each source offers as line geometry, a candidate list
(`earth-physics-lines-candidates.csv`, 119 rows), the extraction route and a
first harvest. Research used web search plus metadata and API queries only:
Zenodo, Earth Search STAC, Overpass counts, Commons API, HTTP HEAD and
range reads of zip directories and JPEG headers. **Nothing was downloaded.**
Each download still needs Ian's go.

Markers: **†** = general knowledge, not source-checked in this session.
"verify" = metadata did not settle it. "checked" = read from the live source
on 2026-10-16. Licence is recorded as information only. It is not a
selection filter (private research; scans stay gitignored; only line
statistics are used).

## Short answer

1. **Amazon: vector first, imagery for what vectors miss.** GRWL already
   gives 30 m centrelines **with a width at every vertex** for all six
   rivers. One Amazon tile is 11–20 MB and can be pulled out of the 3.1 GB
   zip by range reads. OpenStreetMap has **3,962 mapped oxbow lakes**
   (`water=oxbow`) in the western and central basin. Dente (2024) publishes
   **year-coded centrelines 1984–2020** for the whole basin in 29 MB. No
   vector product has the **scroll bars** (the nested ridge arcs a
   migrating bend leaves behind), so those need Sentinel-2 crops or JRC
   surface-water transitions.
2. **Rivers are already a κ(s) science.** Langbein & Leopold's
   sine-generated curve is a *curvature* model: κ(s) is a cosine along the
   arc. Wavelength is about 10–14 channel widths and bend radius about 2–3
   widths†. That gives a dimensionless line width that drops straight into
   our panel: a river is a line whose width is a fixed fraction of its
   curvature radius.
3. **Standout physics and machine sources**: (a) **insect galleries and
   leaf mines**, the only natural lines here whose **width grows along s**;
   (b) **bubble-chamber tracks**, which give spirals of rising curvature,
   V-vertices, kinks and hub stars, with about 20 PD DOE/LBL scans on
   Commons (14 rowed); (c) **lightning and Lichtenberg figures**, branching trees with
   a physics generator (DBM) to calibrate against; (d) **vector machine
   lines that need no extraction**: seismic particle motion (FDSN),
   vectorcardiogram loops (PTB), cyclone tracks (IBTrACS) and drifter
   loops.
4. **First harvest** (§5): about **500 MB Amazon** (vector 282 + imagery
   217) and **191 MB physics** (35 image files + 3 vector sets), about
   690 MB in all. A lean variant is about 450 MB.

## 1. Amazon rivers

### 1.1 What the line offers

| # | Feature | Geometry | Our measurement it maps to |
|---|---|---|---|
| G1 | Free meander (Ucayali, Juruá, Purus, Mamoré) | Smooth, near-periodic κ(s). The sine-generated curve has direction θ(s) = ω sin(2πs/M), so κ(s) = (2πω/M) cos(2πs/M) (Langbein & Leopold 1966). Real bends add skew and flattening through third harmonics (the Kinoshita curve†) | κ(s) panel and the clothoid fit: a sine-generated bend is close to a chain of clothoids |
| G2 | Scale law | Wavelength λ ≈ 10–14 w; bend radius Rc ≈ 2–3 w; migration fastest near Rc/w ≈ 2–3 (Leopold & Wolman 1960; Hickin & Nanson†). Sylvester et al. 2019 (Geology): migration rate follows curvature with a downstream lag | κ·w is the river's dimensionless curvature, the counterpart of our κ·R and σ-in-line-widths conventions |
| G3 | Cutoff / oxbow | A bend whose neck closes to ~1 w pinches off. The result is a crescent closed curve, abandoned next to the channel | topology: closed **forms**, **near** ends, **kisses** just before a neck cutoff |
| G4 | Scroll bars | Nested ridge-and-swale arcs inside each bend: the bend's earlier positions | **P** (parallel runs) and nesting depth; the "nested parallel curves" trait |
| G5 | Anabranching / braided (Negro, Solimões, Pastaza) | Islands as long closed loops; channels split and rejoin at shallow angles | closed forms, **L** joins, cells |
| G6 | Tributary tree | Junction angle ≈ 72° in humid climates (Seybold, Rothman & Kirchner 2017†), narrower in arid climates; Horton/Hack scaling | **T** ends and branch angle (S9 in the topology results: Ingres 0.61 rad, Hokusai 0.89; 72° = 1.26 rad) |
| G7 | Time stack | The same line redrawn yearly for 40 years (Landsat, Dente centrelines) | a family of drawings of one line: within-"hand" variation, measured for once |

Whitewater rivers (Ucayali, Juruá, Purus, Madeira) carry heavy sediment.
They meander and cut off more than blackwater rivers (Negro); Constantine
et al. 2014 is the study the NASA pieces cite. Sediment load, in other
words, is the physical knob for "how loopy the hand is".

### 1.2 Sources (CSV `topic` = amazon-vector / amazon-imagery)

| # | Source | Rows | What | Licence (info) | Access notes |
|---|---|---|---|---|---|
| A1 | **GRWL** V01.01 (Allen & Pavelsky 2018) | 7 | Centrelines every 30 m with `width_m`, channel count and lake flag; rivers ≥ 30 m wide | CC BY 4.0 | Zenodo 1297434. One 3.1 GB zip of 829 tiles. I listed the central directory by range read: Amazon tiles are 11–21 MB compressed. Extract single tiles with remotezip (checked) |
| A2 | **SWORD** v17c (2026-09-02) | 1 | 10 km reaches with network topology; 200 m nodes | CC BY 4.0 | Zenodo 22259077. Per-basin shapefiles: `sa_sword_reaches_hb62` is 94 MB and is the largest SA basin, so presumably the Amazon (verify) |
| A3 | **HydroRIVERS** v1.0 | 1 | DEM-derived network with Strahler order and next-down topology | HydroSHEDS licence (verify wording) | South America 95.3 MB (checked). 500 m DEM: meanders smoothed, branching intact |
| A4 | **OSM** via Overpass | 2 | `water=oxbow` polygons and river-area polygons | ODbL | 3,962 oxbows in 12°S–0, 78–58°W; 875 water features along the Ucayali (counts checked) |
| A5 | Dente 2024 (Zenodo 11066336) | 2 | Year-coded centrelines 1984–2020 (raster), migration rates for 23,000 reaches | CC BY 4.0 | 29.1 MB + 5.5 MB |
| A6 | Li, Edmonds, Konsoer, Constantine et al. 2026 (Zenodo 18340214) | 1 | Every Amazon cutoff 1984–2021 on reaches > 90 m: location, width, year, type, bend geometry | CC BY 4.0 | 0.44 MB xlsx |
| A7 | Greenberg & Ganti 2024 (Dryad, Zenodo 10791093) | 1 | Masks + yearly centrelines for single rivers incl. **Madre de Dios** and **Rio Curuçá** | CC0 | 21 MB zip |
| A8 | Frasson et al. 2019 (Zenodo 2582500) | 1 | GRWL centrelines with meander wavelength and sinuosity attributes | CC BY 4.0 | 708 MB zip; SA sections 5–36 MB each |
| A9 | JRC Global Surface Water v1.4 | 4 | 1984–2021 water occurrence and transitions (new/lost water) | Copernicus, free (verify) | 10°×10° GeoTIFFs, 22–45 MB (checked) |
| A10 | NASA Earth Observatory / ISS | 7 | Curated natural-colour scenes | NASA, no copyright | Sizes from JPEG headers (checked). **Juruá 145819 is 8383×3913** |
| A11 | NASA SVS 15021 | 1 | Ucayali Landsat 1985–2023 time series (video) | NASA | Released 2026-05-06 |
| A12 | USGS Earth as Art | 1 | "Oxbows in Bolivia" (Beni) | PD | usgs.gov blocks scripted fetch; size unverified |
| A13 | **Sentinel-2 L2A** (Earth Search, AWS COGs) | 9 | 10 m bands, no login | Copernicus free | Cloud ≤ 0.03 % scenes found per reach (§1.4). Full tile per band 55–280 MB; read windows only |
| A14 | Landsat C2 L2 | 3 | 30 m, back to 1985 TM on the same path/row | PD | AWS bucket is requester-pays; Microsoft Planetary Computer is free |
| A15 | Code: meanderpy, RivGraph, RivMAP | 3 | Howard–Knutson migration model; mask→network; Ucayali 31-year masks | open (verify) | meanderpy is a ready **physics generator** of meander centrelines + oxbows |
| A16 | Planet NICFI basemaps | 1 | 4.77 m monthly mosaics | non-commercial, sign-up | Collection ends Feb 2026; only route to < 30 m tributaries |

Not rowed: Copernicus Data Space (same S2 data, login), USGS EarthExplorer
(login), GEE (account; GRWL/SWORD are in the community catalog), MERIT
Hydro/Basins (registration, CC BY-NC), the remaining GRWL tiles (SA18
Marañón/Iquitos 21.3 MB, SA19 Solimões 19.4, SC19 upper Purus 18.3, SA21
Manaus–Parintins 14.4, NA20 upper Negro 10.1) and Leopold & Wolman PP 282-B
(PD, 4.5 MB).

### 1.3 Vector vs imagery

**Vector wins for the first round.** GRWL already did the extraction we
would do: water mask → centreline → orthogonal width. It did it at 30 m
for every Amazon river ≥ 30 m wide. It gives the two things the panel needs,
centreline and width, with no threshold choices on our side. OSM adds
oxbows as closed curves, and Dente adds 37 years of the same lines.
HydroRIVERS adds the tributary tree. The total is under 300 MB.

**Imagery is still needed for three things.** (1) **Scroll bars**:
ridge-and-swale arcs show only as vegetation stripes in 10 m imagery, and
as occurrence/transition contours in JRC. They are the most drawing-like
part of a meander belt (nested curved lines) and exist in no vector set.
(2) **Our own extraction at 10 m**, to check GRWL against
`extract_hybrid` on a known reach. (3) **Narrow rivers** (< 30 m), which
GRWL drops.

### 1.4 Extraction recipe (imagery → lines)

1. **Water mask.** Use MNDWI = (G − SWIR1)/(G + SWIR1) with B03 and B11
   (Xu 2006†), Otsu threshold. Whitewater rivers are bright in the visible
   bands, so plain NDWI (G − NIR) under-detects them. Blackwater (Negro) is
   dark everywhere and NDWI works, but burn scars and cloud shadow can
   pass for water.
2. **Clean.** Drop blobs below ~10 px. Fill holes below a bar-size
   threshold. Keep the largest connected channel. Every other elongated
   component is a candidate **oxbow**.
3. **Centreline and width.** Run `extract_hybrid` on the mask: water is
   "ink". Width = 2 × distance transform along the skeleton, the same
   definition as GRWL's. Braided reaches need the junction logic (or
   RivGraph).
4. **κ(s).** Use `curvature.py` with σ expressed in **channel widths**
   (σ ≈ 1–2 w). This is the river version of our σ ≥ 7 line widths rule.
   Report κ·w. Expect κ·w ≈ 0.3–0.5 at bend apexes (Rc ≈ 2–3 w†).
5. **Scroll bars.** Ridge-filter the NIR/red band (vegetation stripes) or
   contour the JRC occurrence raster, then skeletonise the ridges. These
   are open arcs nested inside each bend.
6. **Plotting.** A river is a *fat* line: its width is a third to a half
   of its bend radius. Drawn as a pen-width centreline at sheet scale,
   that ratio is lost. The faithful rendering is the **two banks as a
   pair of contiguous offset curves** (the P relation by construction).
   This is the `fat_tube` / nib-sweep option from the calligraphy note
   (T5), not hatching.

### 1.5 Recommended reaches (scene ids checked on Earth Search, 2026-10-16)

| # | Reach | Why | Sentinel-2 L2A | Landsat path/row | GRWL tile |
|---|---|---|---|---|---|
| R1 | Ucayali at Pucallpa (8.4 S, 74.6 W) | the canonical free meander; RivMAP/SVS reach | S2B_18LWR_20200828_1_L2A | 006/066 | SB18 |
| R2 | Ucayali near Requena (5.0 S, 73.9 W) | large bends, wetland oxbows | S2A_18MXV_20200803_1_L2A | 006/064 | SB18 |
| R3 | Juruá east of Eirunepé (6.7 S, 69.5 W) | most sinuous river in the basin; EO 145819 | S2A_19MDN_20210802_1_L2A | 004/064 | SB19 |
| R4 | Purus at Lábrea (7.2 S, 64.9 W) | tortuous, dense lakes | S2A_20MKT_20250827_0_L2A | 233/065 | SB20 |
| R5 | Rio Negro, Anavilhanas (2.6 S, 60.9 W) | 400+ elongated islands: nested closed curves | S2A_20MQC_20200729_0_L2A | 231/062 | SA20 |
| R6 | Pastaza megafan (2.6 S, 76.6 W) | braided end-member | S2B_18MUC_20240731_0_L2A | 008/062 | (SA18) |
| R7 | Mamoré, Bolivia (13.6 S, 65.2 W) | densest cutoffs; EO 84833 pair | S2C_20LKK_20250706_0_L2A (16.9 % nodata) | 232/069 | (outside the six) |
| R8 | Madeira at Humaitá (7.5 S, 63.0 W) | low-sinuosity contrast | S2C_20MMS_20250812_0_L2A | 232/065 | SB20 |
| R9 | Solimões near Coari (3.9 S, 63.3 W) | anabranching, scroll-bar fields | S2A_20MMA_20200801_1_L2A | 233/063 | SA20 |

Crop size: a ~30 × 30 km window = 3000 × 3000 px at 10 m. That holds about
10 meander wavelengths on the Juruá (w ≈ 250 m†, λ ≈ 3 km) and is
comparable to a museum scan. Read green + NIR + SWIR16 through COG windows
(GDAL `/vsicurl/`). That is about 25 MB per reach instead of ~700 MB of
full-tile bands.

## 2. Machine and physics lines (group C)

| # | Topic | What the line offers | Best sources (CSV rows) | Vector? | Extraction |
|---|---|---|---|---|---|
| C1 | **Bubble chamber** | Helices in a magnetic field. Charged tracks are circles whose radius **shrinks as the particle slows**, so κ(s) rises monotonically into a spiral (electrons spiral tightly). **V** = two tracks from an empty point (neutral decay). **Kinks** = small-angle decays (π→μ). **Stars** = many tracks from one vertex (a hub). δ-rays = tiny curls branching off a track (T ends). Multiple scattering = tremor. Hazard: the beam is a fan of **parallel straight tracks**, which reads as hatching and must be filtered | 14 PD DOE/LBL/BNL/FNAL scans rowed from ~20 on Commons (2400–4000 px, 0.3–4 MB, rows bc-*; near-duplicate Flickr rescans left out); Anderson's 1932 positron (PD, κ jumps at the lead plate). CERN CDS is the richest archive but mixed © and now behind a bot challenge; UK BCRP is digitising 2 m HBC film (not public) | no (reconstruction software exists but not as public line data) | Medium. Tracks are **dotted bubbles**: blur or close before skeletonising. Fiducial crosses and chamber edges must be masked. Overlaps are projections, not true crossings |
| C2 | **Seismograms, drum records** | y(t) wiggles with quiet → burst → coda envelopes. A drum record is 24+ parallel traces, which reads as **hatching**: take single traces | Commons Czech Academy set (19 × 6000×4000, CC BY-SA); ETH Sieberg slide; **USGS WWSSN film chips: 3.7 M station-days, CC0, ≥ 400 ppi, via Globus** | raw data yes (FDSN) | Easy per trace, but these are **function graphs**: κ statistics differ in kind from free 2-D lines (no backtracking, x monotone) |
| C3 | **Seismic particle motion** | Plot N vs E (or radial vs vertical) ground motion: a single 2-D line of tangled ellipses and spirals that grows and decays with the wave train. A true free 2-D line, not a function graph | Commons hodogram (4579×4228, CC BY 3.0) as proof; **FDSN dataselect** (EarthScope; checked live) for any event, station and length | **yes, exact numbers** | None. ~1 MB per event-station |
| C4 | **Vectorcardiogram** | Frank leads vx vs vy: three nested loops per beat (P, QRS, T), repeated beat over beat with drift: a looping repeated line with tremor | PTB Diagnostic ECG DB (549 records, Frank leads, ODC-By verify); PTB-XL (12-lead only: function graphs); ECG-Image-Database (35,595 photographed printouts with ground-truth signals, an extractor benchmark) | **yes** | None |
| C5 | **Trajectories** | Cyclone tracks: smooth recurving lines, occasional loops and stalls. Ocean drifters: **cycloidal inertial loops** riding on eddy drift, the most scribble-like natural line found | IBTrACS lines (48.1 MB, PD, checked); NOAA GDP drifters via ERDDAP (PD) | **yes** | None |
| C6 | **Lightning** | Tortuous main channel (segment direction changes of ~16° mean, Hill 1968†) with branches of decaying length, nearly all pointing one way (downward), hence a directed tree | NOAA NSSL photos mirrored on Commons (PD, up to 3888×2592; subject of nssl02xx to verify). The NOAA digital library itself blocks scripts (CloudFront 403) | no | Easy. Bright line on dark sky; threshold, skeleton. Glow widens the line: use the ridge, not the blob |
| C7 | **Lichtenberg figures / treeing** | Fractal branching (2-D DLA-like dimension ~1.7†). Surface figures are planar; figures inside acrylic blocks are 3-D trees seen in projection, so their crossings are depth artefacts | Commons: acrylic block 3929×5102, fractal surface figure 3272×3272, wood-burned figures (CC BY-SA). Electrical treeing: only 3 small Commons files; research images are © | no | Medium (fine twigs; dense cores). **Generator available**: Dielectric Breakdown Model (Niemeyer–Pietronero–Wiesmann 1984); η tunes from dense DLA to sparse lightning |
| C8 | **Cracks** | Nets of straight-ish segments. **Sequential cracking gives T junctions at ~90°**: later cracks end on earlier ones. Repeated wet/dry cycling drifts towards **Y junctions at ~120°** (Goehring 2010). Craquelure differs by painting school (Bucklow†): a hand-like fingerprint of a tradition | Commons Category:Craquelure (97 files; Balke detail 6720×3896 PD); Crackle glaze (200+); mud cracks (PD 5472×3648); DeepCrack (537 masks); Goehring lab series (CC BY 3.0) | masks only | Easy on masks; on paintings the image content competes. **Measures our T-end relation directly**. Risk: cells, not long lines |
| C9 | **Leaf venation** | Whole leaf: midrib → secondaries at a family-specific angle, looping to join the next (brochidodromous) → reticulate areoles. A tree that closes into cells | Wilf et al. (Figshare+, 30,252 cleared/x-ray leaves, CC BY 4.0, ~65 GB in 3 zips); Blonder Bornean set (726 leaves, **hand-traced masks**, ODC-By, 1 cm² at 50 MP); Commons leaf skeletons | traced masks (Blonder) | Medium. Cleared leaves have many vein orders; keep the top 2–3 orders for contiguous lines |
| C10 | **Insect galleries and leaf mines** | **Width grows along s** as the larva grows: a monotone dw/ds no other source here has. Serpentine leaf mines are self-avoiding meanders bounded by veins, with a central frass line. Bark-beetle galleries are combs: a mother gallery with perpendicular larval galleries widening outwards (Scolytus "centipede", Ips Y/H) | Commons: Phyllocnistis leaf mines (2 photos, CC BY-SA), bark-beetle didactic board 6036×4020, elm galleries, USFS PD photos, buprestid gallery. Bugwood/ForestryImages has thousands (mostly CC BY-NC) | no | Medium. Galleries are dark grooves on wood: shading, not ink. Width from the groove walls |
| C11 | **Trace fossils** | *Helminthoida/Nereites*: tight parallel hairpin meanders that never cross (guided meandering). *Paleodictyon*: hexagonal net | Commons Helminthoida (4752×3168), Paleodictyon (21 files), Nereites | no | Hard (relief on rock, low contrast). **Generator available**: Raup & Seilacher 1969, three behavioural rules |
| C12 | **Slime trails / grazing** | Overlapping wandering trails, many crossings (a non-human scribble); radula zig-zag | Commons "Forty years of slug and snail slime trails" (CC0); Radulichnus on a car bonnet | no | Medium (sheen-dependent contrast) |
| C13 | **Other networks** | Physarum tube networks (Tero 2010 flux model generates them); tidal creeks, which taper upstream and meander, combining tree and meander in one figure | Commons Physarum network; Bahía Blanca tidal channels (ESA, CC BY 4.0) | no | Medium |

Considered and dropped, or low value: frost ferns (feathery: hatching
risk); tree rings and ice cores (concentric, not one line); mycelium
(Boddy/Fricker network data exists as graphs, licence and host unverified);
Martian channels (not checked); polygraph/barograph charts (function graphs
like C2).

**Ranked by fit to "contiguous lines, never hatching, non-human hand":**
rivers (G1–G4) > insect galleries / leaf mines (C10) > particle motion and
VCG (C3–C4) > bubble chamber (C1) > lightning/Lichtenberg (C7, C6) >
drifters/cyclones (C5) > leaf venation (C9) > trace fossils (C11) > cracks
(C8: nets, not lines) > drum seismograms (C2: function graphs, hatching
risk).

## 3. Pipeline notes

- **P1. Fat lines.** Rivers, leaf mines and galleries are ribbons whose
  width is a large fraction of their curvature radius. Extract centreline
  plus width (the "filled blade" mode). Render the banks as two contiguous
  offset curves; this ties into the open thickness decision in
  `IDEAS-gesture-bank.md`.
- **P2. Width along s is a new feature.** Add `dw/ds` (trend of log width
  versus arc length) to the panel. Pens and brushes give ~0, galleries and
  mines give > 0, and rivers give ~0 within a reach and > 0 downstream
  across tributary junctions.
- **P3. Function graphs are a different species.** Seismograms and ECG
  strips are y(t). Either compare them only to each other, or turn them
  into 2-D lines (particle motion, VCG) before they enter the shared
  panel.
- **P4. Hatching filters.** Masks or heuristics are needed for bubble
  chamber beam fans, drum-record line stacks and frost. Scroll-bar fields
  are nested *curved* parallels: keep them, but Ian should look at them
  first.
- **P5. Projections fake crossings.** Bubble-chamber and acrylic
  Lichtenberg crossings are depth overlaps. Count them separately from the
  X relation, or drop them.
- **P6. Physics generators as partners.** meanderpy (rivers), DBM
  (discharge), Raup–Seilacher rules (trace fossils) and the Tero model
  (Physarum) each give a parameterised synthetic hand. Fit their
  parameters so their panel matches the harvested lines; the fitted
  generator then becomes a hand for juxtaposition. This is the same role
  `kind="oehlen_tree"` plays in `topology.py`.

## 4. Blockers

- CERN CDS (Anubis bot challenge), NOAA digital library (CloudFront 403)
  and usgs.gov media pages refused scripted reads. They need a manual
  browse.
- The old IRIS SeismoArchives index pages return 404 since the move to
  NSF SAGE/EarthScope; full-resolution event scans need a request.
- WWSSN film chips need Globus. Wilf leaves come as 19–23 GB zips behind
  10-second signed links, so per-image range extraction is awkward.
- Planet NICFI access after Feb 2026 is unverified. GRWL drops rivers
  under 30 m, so small igarapé tributary trees come only from HydroRIVERS
  (smoothed) or 10 m Sentinel-2.
- `hb62` = Amazon in SWORD is inferred from file size; verify before
  relying on it.

## 5. Recommended first harvest (for Ian's approval)

**Amazon, about 500 MB.** Vector 282 MB and imagery 217 MB. Ordered by
expected value:

| # | id(s) | what | MB |
|---|---|---|---|
| H1 | grwl-vec-SB18, -SC18, -SB19, -SA20, -SB20, -SC20 | centrelines + widths: Ucayali, Juruá, Purus, Madeira, lower Negro/Solimões (range-extracted from the zip) | 97.8 |
| H2 | grwl-mask-amazon (same 6 tiles) | the masks behind H1, for an extractor cross-check | 6.7 |
| H3 | osm-oxbows-amazon | 3,962 closed oxbow curves (Overpass GeoJSON; size estimated) | ~30 |
| H4 | dente-amazon-centerlines | 1984–2020 year-coded centrelines, the whole basin | 29.1 |
| H5 | greenberg-ganti-single-rivers | Madre de Dios + Rio Curuçá masks and yearly centrelines | 21.0 |
| H6 | li-amazon-cutoffs | every cutoff 1984–2021 with bend geometry | 0.4 |
| H7 | hydrorivers-sa | tributary trees (junction angles, Horton/Hack) | 95.3 |
| H8 | usgs-pp422h-langbein-leopold, meanderpy | theory + physics generator | 1.2 |
| H9 | eo-145819, eo-84833-2014, eo-84833-1985, eo-92370 | curated scenes: Juruá 8383 px, Mamoré 1985/2014 pair, sunglint | 18.8 |
| H10 | jrc-gsw-transitions-80W_0N, -70W_0N | migrated channel and new oxbows as classes; scroll-bar contours | 48.1 |
| H11 | s2-18LWR-20200828, s2-18MXV-20200803, s2-19MDN-20210802, s2-20MKT-20250827, s2-20MQC-20200729, s2-18MUC-20240731 | 3000×3000 px windows of green/NIR/SWIR16 for R1–R6 | ~150 |

**Physics and machine lines, about 191 MB** (35 image files + 3 vector
sets):

| # | id(s) | what | MB |
|---|---|---|---|
| H12 | insect-01..08 (minus 07), trace-helminthoida-carnero, trace-paleodictyon-I01, trace-nereites-cymru, slime-trails-forty-years, leaf-eaten-white-oak | **non-human hands**: width-growing galleries and mines, guided meanders, wandering trails, a vein net | 75.1 |
| H13 | bc-01..07, bc-10, bc-11, bc-14, bc-15, bc-16, bc-17, bc-19, cc-positron-1932 | 15 PD bubble/cloud-chamber events (spirals, V, stars, kinks) | 18.6 |
| H14 | lightning-01, -02, -06, -07, lichtenberg-01, -02, -03, -05 | discharge trees, planar and projected | 28.7 |
| H15 | ibtracs-lines; fdsn-particle-motion (e.g. Tōhoku 2011 at IU.ANMO + 4 other stations/events); ptb-vcg-frank (10 records) | **vector machine lines, zero extraction** | ~69 |

**Grand total ≈ 690 MB.** Lean variant (≈ 450 MB): skip H7 (HydroRIVERS
can wait for a later topology round), cut H11 to R1, R3 and R5 (~75 MB),
and take only the FDSN part of H15. Not in this round: WWSSN film chips (Globus,
unbounded), Wilf leaves (65 GB), Blonder venation (size unknown), CERN
CDS (manual browse), Bugwood (manual, NC licences).

## URLs used

- GRWL: https://zenodo.org/records/1297434 (Allen & Pavelsky 2018, Science, doi:10.1126/science.aat0636)
- SWORD v17c: https://zenodo.org/records/22259077 ; MERIT-SWORD https://zenodo.org/records/14675925
- HydroRIVERS: https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_sa_shp.zip ; HydroLAKES https://data.hydrosheds.org/file/HydroLAKES/HydroLAKES_polys_v10_shp.zip
- Overpass API: https://overpass-api.de/api/interpreter ; Geofabrik https://download.geofabrik.de/south-america/
- Dente 2024: https://zenodo.org/records/11066336 ; Li et al. cutoffs: https://zenodo.org/records/18340214 ; Greenberg & Ganti: https://zenodo.org/records/10791093 ; Frasson et al.: https://zenodo.org/records/2582500
- JRC GSW: https://storage.googleapis.com/global-surface-water/downloads2021/
- Earth Search STAC: https://earth-search.aws.element84.com/v1/search (collections sentinel-2-l2a, landsat-c2-l2)
- NASA EO: https://science.nasa.gov/earth/earth-observatory/the-many-meanders-of-the-jurua-145819 , …/meandering-in-the-amazon-84833 , …/amazon-meanders-in-sunglint-92370 , …/changes-in-the-mamore-river-bolivia-3717/ , …/sunglint-on-the-amazon-river-brazil-9072/ , …/the-bolivian-lowlands-151450 , …/rio-negro-amazonia-brazil-7169/
- NASA SVS: https://svs.gsfc.nasa.gov/15021 (API https://svs.gsfc.nasa.gov/api/15021) ; "Sharp bends make rivers meander": https://science.nasa.gov/missions/landsat/sharp-bends-make-rivers-meander-as-landsat-attests/
- USGS Earth as Art: https://www.usgs.gov/media/images/oxbows-bolivia ; https://store.usgs.gov/assets/MOD/StoreFiles/EAA/EAA_4/Oxbows_in_Bolivia.pdf
- Theory: https://pubs.usgs.gov/pp/0422h/report.pdf ; https://pubs.usgs.gov/pp/0282b/report.pdf ; RivMAP https://www.mathworks.com/matlabcentral/fileexchange/58264 ; https://csdms.colorado.edu/wiki/Model:RivMAP ; meanderpy https://github.com/zsylvester/meanderpy ; RivGraph https://github.com/VeinsOfTheEarth/RivGraph
- NICFI: https://developers.google.com/earth-engine/datasets/catalog/projects_planet-nicfi_assets_basemaps_americas
- Commons API: https://commons.wikimedia.org/w/api.php (categories Bubble chambers, Bubble chamber particle tracks, Brookhaven 80-inch bubble chamber, Fermilab 15-foot bubble chamber, Lichtenberg figures, Electrical treeing, Seismograms, Craquelure, Crackle glaze, Leaf skeletons, Helminthoida, Paleodictyon, Nereites, Slime trails, Tidal channels; file searches for NSSL lightning, bark beetle galleries, mud cracks, leaf mines)
- CERN CDS: https://cds.cern.ch/collection/PhotoLab%20Archives%20Images ; https://cds.cern.ch/collection/Bubble%20chamber%20films ; UK BCRP https://www.ppd.stfc.ac.uk/Pages/BCRP.aspx ; https://www.hep.ph.bham.ac.uk/bubble/reco.html
- Seismograms: https://www.usgs.gov/data/world-wide-standardized-seismographic-network-film-chip-scans (doi:10.5066/P13PHZMA) ; https://ds.iris.edu/ds/newsletter/vol7/no2/192/seismoarchives-seismogram-archives-of-significant-earthquakes-of-the-world/ ; FDSN https://service.iris.edu/fdsnws/station/1/ → https://service.earthscope.org/fdsnws/dataselect/1/
- ECG: https://physionet.org/content/ptbdb/1.0.0/ ; https://physionet.org/content/ptb-xl/ ; https://moody-challenge.physionet.org/2024/ ; https://arxiv.org/abs/2409.16612
- Trajectories: https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/ ; https://www.aoml.noaa.gov/phod/gdp/
- Lightning: https://noaa.gov/digital-library (blocked to scripts)
- Cracks: https://arxiv.org/pdf/2602.09730 ; https://arxiv.org/pdf/2602.12742 ; https://pubs.rsc.org/en/content/articlehtml/2016/sm/c5sm02389k ; https://ar5iv.arxiv.org/html/1211.6762 ; https://irep.ntu.ac.uk/id/eprint/28373/ ; https://data.mendeley.com/datasets/wddt4gbttd ; https://www.inf.bi.rub.de/iib/forschung/datensaetze/index.html.en
- Leaves: https://plus.figshare.com/articles/dataset/_/14980698 (API https://api.figshare.com/v2/articles/14980698) ; https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6899953/ ; https://ora.ox.ac.uk/objects/uuid:de65fc07-4b8f-4277-a6c4-82836afbdeb3 ; https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3986656/
- Insects: https://www.forestryimages.org/ ; https://caps.ceris.purdue.edu/ips-typographus-caps-datasheet-pdf ; https://bladmineerders.nl/
- Fungal networks: https://arxiv.org/pdf/1612.08058
- DBM: https://doi.org/10.1103/PhysRevLett.52.1033 ; Raup & Seilacher: https://doi.org/10.1126/science.166.3908.994

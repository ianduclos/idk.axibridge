# Contemporary dance as a source for the topology layer (research, 2026-10-16)

Ian's idea (binding): *"contemporary dance pose extraction for the topology
layer — get the gestures, then abstract and combine to turn non-human."*

This note covers four things:

- the data sources, in `dance-gesture-candidates.csv` (67 rows);
- the pose-extraction tooling;
- the core question: how dance motion becomes skeleton structures that
  `topology.py` measures, `generate_structure` composes and `restyle.py`
  redraws in a hand;
- a first harvest.

Research used web search, dataset pages, and HTTP HEAD and range requests
that read sizes and zip indexes only. **No video, dataset or model was
downloaded.** Every download still needs Ian's go.

Markers: **†** = general knowledge, not source-checked in this session.
"verify" = the source did not settle it. Rights are recorded as information
only. They are not a selection filter (private research, the same policy as
`calligraphy-arabic.md`).

## Short answer

1. **The best contemporary data is open and small enough.** Two sources stand
   out.
   - Daniel Bisig's two **E2-Create** sets on Zenodo (CC BY 4.0): six
     contemporary dancers improvising on four tasks, one of them
     *Unusual Poses*, and Muriel Romero's 62 takes of **named movement
     qualities** (Levitation, Particles, Staccato, Out of Balance, …, many as
     single-limb isolations).
   - **CMU subjects 5 and 49** (modern dance) plus **subject 55** (a human
     miming hummingbird, praying mantis, dragon and "hippo ballerina").

   The E2 zips are 52.5 and 19.3 GB, but they are ordinary zips. I read both
   indexes by HTTP range: individual BVH members can be fetched alone at about
   a quarter of their raw size.
2. **The postmodern canon is mostly video or concept, not data.**
   - **Motion Bank's Deborah Hay score** is live: *No Time to Fly*, 3 dancers ×
     7 runs, fixed front camera, about 52 MB per MP4, still served. It is the
     best target for 2D pose estimation.
   - **Synchronous Objects** (Forsythe) is CC BY-NC-ND and now videos only. Its
     raw annotation database is not public. It is the blueprint for the
     relational mapping, not a data source.
   - **Cunningham's *Loops*** hand mocap (CC BY-NC-SA) has dead download links.
     Only takes 1 and 3 survive on the Wayback Machine.
3. **Tooling.** Use **rtmlib** (RTMPose/RTMW over onnxruntime on CPU,
   Apache-2.0, pure-Python wheel, and onnxruntime ships cp313 macOS-arm64
   wheels) for 2D. Take 3D from mocap, not from video.
4. **Mappings to prototype first:**
   - **M1** end-effector trails as strokes. This works with today's
     `relation_graph`/`learn_model` unchanged.
   - **M2** the kinematic tree grown along time: the Oehlen-tree bridge.
   - **M5a** retargeting the dancer's joint rotations onto an impossible,
     recursively branching skeleton: the "turn non-human" step.

   "Non-human" is made measurable with a two-sided test: anatomy must fall to
   chance while dance stays detectable (§4).

## 1. Data sources

The full table is in the CSV: 67 rows, tiers **A 16 / B 23 / C 28**.

- **A** = contemporary or postmodern, usable geometry or a clean fixed-camera
  video, reachable now.
- **B** = useful contrast, a concept reference, or access friction.
- **C** = wrong genre, unreachable, or viewing only.

Contemporary-specific sources, ranked:

| # | source | what | format / size | rights (info) | tier |
|---|---|---|---|---|---|
| D1 | **E2-Create Motion Bank** (Zenodo 7031672) | 6 pro contemporary dancers × 4 tasks: Unusual Poses, Movement Qualities, Movement Vocabulary, Music Improvisation. Docs include task descriptions, skeleton structure and 3 dancer interviews | 27 BVH (837 MB raw, ~8 MB of zip per 33 MB BVH), 27 FBX, 72 per-camera skeleton CSVs, 96 front MP4s (51 GB) | CC BY 4.0 | A |
| D2 | **E2-Create Instituto Stocos** (Zenodo 7034917) | Muriel Romero: 62 takes over ~21 named movement qualities, many repeated as LeftArm / RightLeg / Torso / TwoArms isolations | C3D (56/62 markers), BVH + `_proc.bvh` (11–36 MB each), FBX, front MP4 | CC BY 4.0 | A |
| D3 | **CMU mocap**, subjects 5 + 49 | modern dance: arabesques, fold-ins, curls, shifted-axis pirouettes (29 trials) | ASF/AMC, 120 fps, 0.7–1.1 MB per trial (HEAD-checked) | free incl. commercial, no resale | A |
| D4 | **CMU subject 55** | a human pantomiming animals (mantis, hummingbird, dragon, penguin, …) | ASF/AMC, up to ~8 MB per trial | as D3 | A |
| D5 | **EMOKINE** (Zenodo 7821844) | 1 dancer, 9 short choreographies × 6 emotions | MVNX (XSens, 240 fps, 14–24 MB each), CSV, video; zip 1.67 GB | CC BY 4.0 | A |
| D6 | **UCY DanceDB** | contemporary improvisations with 13 emotion labels, plus folk etc. | C3D, FBX, MP4 (SMPL via AMASS); per-file sizes not visible (JS table) | conflicting: "CC BY-SA 3.0" vs a personal non-commercial licence | A |
| D7 | **Motion Bank: Deborah Hay, *No Time to Fly*** | 21 runs of one solo (Durning, Mapp, Warby), fixed front camera, empty stage; also "all seven overlaid" renders and the score text | MP4, ~52 MB each (front, small); 225 MB (following camera) | © Motion Bank / Hay, no licence stated | A |
| D8 | **Cunningham, *Loops*** (OpenEndedGroup) | hand and finger mocap, 4 takes, 2000 | HTR + FBX + video per .tar.gz. **Links 404 today**; Wayback has take-1 (564 MB) and take-3 (1.23 GB) | CC BY-NC-SA 3.0 US | A (access: B) |
| D9 | **Synchronous Objects** (OSU / Forsythe) | *One Flat Thing, reproduced*: cue and alignment annotations, ~200 "sync-ups", 3D alignment forms, motion volumes | videos of the dead Flash tools; essays PDF | CC BY-NC-ND 4.0 | A (concept) |
| D10 | **Trisha Brown**: *Locus* drawings (MoMA, Walker), *It's a Draw* (Walker 2008.54) | the 27-point cube score; drawings made by dancing on paper | museum images | © estate | A (ground truth for M1) |
| D11 | Burrows/Fargion *Seven Duets* (Motion Bank) | seated gesture duets; score books; a Processing repo with marker/Kinect data (NC-SA, contents verify) | streamed video; GitHub | © / NC-SA | B |
| D12 | Bisig AI-Toolbox duet (Romero / Strang / Win) | contemporary **duet** mocap | Qualisys (verify) | verify | B |

Contrast and genre sets (not contemporary; use as the "other" class):

- **AIST++.** Street genres only: 1408 sequences, `motions.zip` 306 MB,
  `keypoints3d` 834 MB. The AIST Dance DB terms allow academic research only,
  with no redistribution. The annotation licence is unstated.
- **BRACE** (breaking). 2D keypoints only; the videos stay with Red Bull.
- **Motorica.** Street, jazz, charleston and tap; 121 BVH clips; licence
  unverified.
- **Others:** FineDance, PopDanceSet, Dance with Melody (ballroom), CoMPAS3D
  (improvised salsa duets, useful for M4), Chang-E, LaFAN1, AMASS.
- **Emotion databases:** PhysioNet's actor set (restricted), Emilya (on
  request) and McNorm (stimuli). All three are low value: actors, not dancers.

Historical line-traces of motion (all PD† unless noted; cheap ground truth
for what M1 and M2 should look like):

- **Marey's** geometric chronophotographs: joints reduced to exposed lines.
- **Gilbreth** chronocyclegraphs: light trails of hand motion.
- **Muybridge's** "Dancing (fancy)" plates.
- The 1895 **Serpentine Dance** film: fabric as swept surface.
- **Schlemmer's** *Figur und Raumlineatur* (1924, PD in the EU and US†).
- Copyrighted: **Laban's** trace-forms (book ©), **Eshkol-Wachman** notation
  (limbs as axes on spheres, the most kinematic-tree-like notation),
  **De Keersmaeker's** floor patterns (©) and the body drawings of
  **Hansen** and **Orrico** (©).

Openly licensed contemporary *video* is scarce. On Commons, "contemporary
dance" videos are mostly mislabelled. **Category:Videos of butoh** (9 files,
CC) is the only usable cluster. RePlay (Siobhan Davies), Numeridanse and
Jacob's Pillow are streaming-only.

## 2. Pose extraction tooling (later; nothing installed)

| # | tool | 2D/3D | Apple-Silicon / CPU | install weight | licence (info) | verdict |
|---|---|---|---|---|---|---|
| P1 | **rtmlib** (RTMPose, RTMO, RTMW whole-body 133 kpts incl. hands/feet) | 2D | onnxruntime CPU; `mps` listed in README; onnxruntime 1.31 has cp313 macOS-14 arm64 wheels | numpy + opencv + onnxruntime; ONNX weights fetched on first use (a download) | Apache-2.0 (code); mmpose weights Apache-2.0† | **recommended** |
| P2 | **MediaPipe Pose Landmarker** (BlazePose GHUM) | 2D + metric "world" 3D, 33 landmarks | CPU real-time; `mediapipe` 1.1.1 ships a py3 macOS-11 arm64 wheel | one wheel + a .task model | Apache-2.0 | fallback / quick look; weak on inversions and floor work† |
| P3 | ViTPose (HF `transformers` VitPose) | 2D, top-down (needs a detector) | torch on MPS/CPU | torch + transformers, ~0.5 GB per model | Apache-2.0 (HF cards) | most accurate 2D†, heavier; only if P1 fails |
| P4 | MotionBERT (2D → 3D lift) | 3D from P1's 2D | torch CPU | moderate | verify | only if 3D from video is ever needed |
| P5 | GVHMR | world-grounded SMPL | CUDA-first; community fork claims MPS (unverified) | heavy; SMPL registration | non-commercial research | later, maybe |
| P6 | 4D-Humans / HMR2.0, WHAM | SMPL 3D | detectron2 / DPVO, CUDA-oriented; Mac CPU is painful | heavy; SMPL registration | MIT code† + SMPL NC; WHAM verify | skip |
| P7 | OpenPose | 2D | Caffe build; CPU very slow | heavy | academic non-commercial | skip |
| P8 | Sapiens (Meta), AlphaPose | 2D | heavy torch | heavy | CC BY-NC 4.0 / NC | skip |

**Route.**

1. **3D comes from mocap**: BVH, AMC, C3D, HTR, MVNX. That avoids SMPL, CUDA
   and estimator noise altogether.
   - BVH and AMC/ASF are short pure-numpy parsers.
   - C3D: `c3d` (pure Python, MIT) or `ezc3d` (cp313 arm64 wheel).
   - MVNX is XML (stdlib).
   - FBX can go through Blender, which is already reachable over MCP.
2. **Video goes through rtmlib** into the gesture venv. That needs a pip
   install plus an ONNX weight download, both Ian's go.
   - Start with **RTMW** whole-body, because hand and foot keypoints are the
     effectors M1 needs.
   - Use the Hay front-camera runs.
3. **Estimator jitter is not tremor.** Smooth trails at an explicit σ through
   `curvature.py` (README contract) and never read 2D-estimator noise as a
   hand.

## 3. From gestures to topology (the core)

**Notation.** A motion is joints J × frames T × 3, with a skeleton tree
(parent of each joint). A **view** P maps 3D to the 2D sheet. Choices:

- a fixed camera;
- the PCA plane of the motion;
- a top view (floor plan);
- an **unfolded** view: one axis carries time.

All outputs are `Drawing`s, normalised by `ref_length` R, so `relation_graph`
and `topology_features` apply unchanged.

**The scale split already in `topology.py`.** `PATH_SIGMA_R` = 0.015 R:
curvature above that scale is "the structure's", below it "the hand's".

- Mocap trails have essentially no sub-σ texture: no tremor, 120 Hz samples
  on smooth joint paths.
- So **dance belongs in the topology/structure layer, not in the hand.** That
  matches Ian's idea exactly.
- The hand still comes from `restyle.py` (Hokusai's hand on a tree was the
  best image of round 3).
- The one exception worth testing is *Loops*. Finger trails at a small view
  scale might be a "dance hand".

### M1. End-effector trails as strokes (implemented first; no API change)

**Construction.**

- Take the trajectories of wrists, ankles and head (RTMW or Loops add
  fingertips), projected by P.
- Each trail is cut into strokes at **phrase boundaries**: minima of
  whole-body kinetic energy† held for more than ~0.2 s, or the dataset's own
  takes and tasks.
- Lines stay contiguous within a phrase, which is Ian's rule.

**What the relations become:**

| relation (topology.py) | arises in dance trails as | stat it feeds |
|---|---|---|
| **X** crossing | a hand path crossing the other hand, a foot path or its own earlier loop | `x_per_ink`, crossing angle |
| **self** end / closed **form** | circling arms, pirouettes (a closed loop in the top view) | `closed_frac`, nesting |
| **P** parallel run | left and right effectors in unison (offset ≈ shoulder or hip width), canon, repeated phrases | `par_per_stroke`, `par_offset`, `par_length` |
| **near** end | a reach that stops short (a hand approaching the body or the other hand); its **aim** is literal | `near_gap`, near-aim (the Matisse statistic S4) |
| **T** end | a phrase that ends where another trail passes (contact, a touch on the body path) | `t_u`, `t_angle` |
| **L** join | consecutive phrases of one effector; the deflection is the change of direction at the phrase boundary | `l_defl` |
| **cusp** (inside a stroke) | velocity reversals: hard corners, unlike smooth handwriting joins | panel corner and turning features; `wind_sd` |

**Plugging in:**

1. `drawing = trails_to_drawing(motion, view, effectors, phrases)` builds a new
   `Drawing`.
2. `relation_graph` / `topology_features` measure it.
3. `learn_model([...], name="stocos-levitation")` gives a `TopologyModel`.
4. `generate_structure(model, rng, kind="learned")` composes new structures
   with dance relation statistics and dance path-winding (`wind_sd`,
   `wind_corr` from `path_wind`).
5. `restyle` redraws them in a hand.

The trail drawing itself can also go straight into restyle, because
`relation_graph` supplies the host/relation meta for end-pinning.

**Experiments this enables at once:**

1. Does the topology separate movement qualities? Use D2's labelled qualities
   and the same 3-way classifier as topology-2026-10-16 §2.
2. Contemporary vs street (D1/D2 vs AIST++).
3. Where do dance trails sit next to Matisse, Hokusai and Ingres?

**Risks:**

- **Long phrases scribble.** Repeated motion becomes dense overdraw, which is
  hatching by another route. Guards:
  - a minimum stroke length (40 w, as in `long_drawing`);
  - collapse retraced runs: P with an offset under 2 w becomes a merge;
  - cap self-crossings per R;
  - choose phrases by novelty.
- **Time-scaling alone changes nothing geometric.** κ(s) is
  arc-length-parametrised. Tempo matters only through segmentation (pauses)
  or when time is mapped to space (M2, the unfolded view).

### M2. The kinematic tree grown along time (the Oehlen-tree bridge)

The skeleton *is* a tree: pelvis → spine → neck → head; shoulders → arms →
hands → fingers; hips → legs → feet. Map edges to branches and time to growth.

**Construction (M2a, "growth tree"):**

- **The trunk** is the root (pelvis) trail in an unfolded or top view, or
  simply a rising axis with t → height. That is Oehlen's upward tropism, with
  time as growth.
- **Branches.** At each phrase keyframe, sprout the limb chains *in that
  pose* as branches. Their bend angles are the joint angles, their lengths the
  bone lengths, scaled by phrase energy.
- **Twigs.** From each branch tip, continue the end-effector trail for the
  next phrase (M1 inside M2).

| tree quantity (`_gen_tree` params / meta) | measured from dance |
|---|---|
| `order` (stroke meta) | depth in the kinematic tree: 0 trunk, 1 thigh/upper arm, 2 shin/forearm, 3 foot/hand, 4 fingers |
| `fork_angle` | distribution of the parent–child bone angles over the phrase (a list, not a scalar) |
| `ratio` | child/parent bone-length ratios (~0.6–0.9†) × energy share |
| `fork_every` | phrase rate (keyframes per unit of trunk length) |
| `wind`, `wind_corr` | `path_wind` of the effector trails |
| `p_meet_T`, `p_cross` | how often limbs touch or cross other limbs and the torso in the view |
| T-junction u, angle | where (in time = along the trunk) a limb sprouts, and at what angle |

**Interface.** There are two options, and the choice is the coordinator's:

- **(i) Fit.** Fit `_gen_tree`'s scalar params from these distributions (use
  medians). No change to `topology.py`.
- **(ii) New kind.** Add `kind="kinematic_tree"`, which samples the
  distributions per fork and keeps the skeleton's branching pattern. This
  changes `topology.py`.

**The measurement side is free either way.** A grown dance tree is a
`Drawing`. Its `features_from` numbers (one component, T share, hubs, cells
per ink, contact degree) compare directly with G4's oehlen_tree row in
topology-2026-10-16 §4.

**M2b, Marey stacking** (the stick figure redrawn at N keyframes along the
root path) is the figurative baseline. Keep it as the "human" end of the
anatomy test.

### M3. Swept envelopes / motion volumes (optional)

- For a bone or limb over a window, the projected swept area is the union of
  the segment positions (shapely, already in the venv). Its boundary is one
  closed contiguous line: **forms** and **nesting**.
- Overlapping windows give nested near-parallel contours, the **P** relation
  at a learned offset.
- Envelopes of a whole arm read as fans and wings, already half non-human.
  This is Synchronous Objects' *Motion Volumes* and Loie Fuller's serpentine
  fabric.
- **Risk:** blobs and figure silhouettes. Keep it as a layer, not a generator.

### M4. Relational structures (Forsythe's cues and alignments)

In *One Flat Thing, reproduced*, dancers are linked by **cues** (one triggers
another) and **alignments** (brief shared shape, direction or timing; about
200 "sync-ups"). As structure:

- **Line.** Each dancer is one line: a root trail in the floor plan, or one
  effector's trail.
- **Alignment.** An alignment event between A and B at time t is either a
  **T** (A's line ends on B's at u = t/T) or a short **connector** (a joined
  L–L pair).
- **Cue.** A cue is a **near** end aimed at the cued line (the aim is the cue
  direction).
- **Unison.** Unison is **P**: two lines at an offset for the overlap
  duration.
- **Crossings.** Floor-path crossings are **X**. De Keersmaeker's and Childs's
  floor plans are made of these.

**Data.** Duets: Bisig AI-Toolbox (contemporary), CoMPAS3D (salsa), CMU
60/61. Also the 21 Hay runs registered on one stage, which give
"alignments" between runs of the same score.

**Within one body.** The same logic applies with limbs as dancers: both hands
at the same height or direction gives a sync-up. That gives M4 for free on
solo data.

### M5. Abstract and combine: turning non-human

Operators act on the motion before drawing, or on the drawing:

| # | operator | what it does to topology | anatomy it removes |
|---|---|---|---|
| M5a | **Impossible-skeleton retarget**: drive a recursively branching skeleton (binary/ternary, depth 3–5, bone ratio r) with the dancer's joint-rotation streams. Joint k's rotation drives every branch at level k, with phase offsets per branch | the motion's angles and timing survive; branching degree and depth are new | 2 arms / 2 legs / head, bilateral pairing, bone proportions |
| M5b | **Graft**: copy a limb chain's local rotations to a new attach point (an arm sprouting from the elbow or the knee; extra legs) | adds hubs of degree > 3; more T ends | the limb count |
| M5c | **Layer**: register several runs or dancers on the root and draw all trails (Hay × 21, Stocos takes of one quality) | more P, X and cells; coverage up | the single-body silhouette |
| M5d | **Symmetry break / mirror**: mirror one side only, or apply a canon (time offset per limb) | P runs become offset, so near-ends and X appear | bilateral symmetry, the strongest "body" cue† |
| M5e | **Proportion scramble**: keep rotations, randomise bone lengths per level | κ statistics kept, extents changed | proportions |
| M5f | **Statistics only**: `learn_model` on dance drawings, then `generate_structure(kind="learned")` | relations kept, all geometry new | everything anatomical |

M5a is the strongest single idea. The dancer's joint-angle signal animates a
tree, which is exactly "get the gestures, then abstract and combine". It also
connects to *Modern Dance Retargeting using Ribbons as Lines of Action*
(Eurographics 2024): lines of action as a bridge between morphologies.

## 4. "Non-human", measurably

A two-sided criterion: **anatomy at chance, dance above chance.**

1. **N1, pose detector.** Render each output (1024 px) and run the P1 detector
   (RTMO/RTMPose).
   - Score: the share of renders with a confident person, and mean keypoint
     confidence.
   - **Pass:** not above the null drawings (`nulls.py` random walks, plain
     oehlen_tree output), with AUC(output vs null) ≤ 0.6.
   - Calibration: M2b Marey stacks and raw stick figures must fail (detected).
2. **N2, anatomy classifier on structure.** Train logreg/forest on
   `topology_features` plus three anatomy probes:
   - bilateral symmetry score;
   - hub-degree histogram (the human signature: a few degree-3 hubs with paired
     long branches);
   - clustering of branch-length ratios at anatomical values.

   Positives: M2b stacks and raw trails with an anatomical view. Negatives:
   oehlen_tree and learned structures. **Pass:** P(figure) on abstracted
   outputs ≈ the negative base rate.
3. **N3, dance still detectable.** AUC(abstracted dance structures vs
   `generate_structure` from an artist TopologyModel with matched ink) should
   be ≥ 0.7 on path-scale κ, the `path_wind` and relation features.
   - Without this, the dance contributed nothing and M5f has collapsed into
     the generic generator.
   - Stronger version: the movement-quality label (D2) is still recoverable
     after abstraction, above 1/k.
4. **N4, blind judge** (the round's existing judge). "Does this read as a body
   or figure?" should be at chance, and "is this the same source quality as
   this reference?" above chance.

**Calibration ladder** (each should pass N1 and N2 more easily than the one
before):

1. raw stick figures;
2. M2b;
3. M1 trails;
4. **CMU 55** (a human miming animals);
5. M5d;
6. M5a/b;
7. M5f.

## 5. Recommended first harvest (for Ian's approval)

About **290 MB transferred, ~545 MB on disk** (BVH is text and could be kept
gzipped, ~140 MB). All rows are CC BY or the CMU terms, except H6.

| # | id | what | why | MB (transfer / disk) |
|---|---|---|---|---|
| H1 | cmu-05 | 19 modern-dance trials, ASF/AMC | parser and M1 smoke test; clean and small | 17 / 17 |
| H2 | cmu-49 | 10 modern-dance trials | curls and fold-ins → forms | 15 / 15 |
| H3 | cmu-55 | ~8 animal-pantomime trials (mantis, hummingbird, dragon, penguin, prairie dog, roadrunner, monkey, hippo ballerina) | the calibration rung between human and non-human | ~40 / 40 |
| H4 | e2mb-unusual | 6 × `Unusual_Poses/*/mocap/mocap_skeleton.bvh`, range-fetched from the zip, plus the `Docs/*.odt` | contemporary, 6 dancers, anatomy-stretching task | ~45 / 177 |
| H5 | e2-stocos | 8 FullBody `_proc.bvh`: Accumulation, Continuity, Fluidity, Levitation, OutOfBalance, Particles, Staccato, Thrusting (+ Docs) | labelled qualities → the first "does topology track quality?" test | ~42 / 166 |
| H6 | mb-hay-front | 2 front-camera runs (e.g. D02T03 Ros Warby, D05T03 Jeanine Durning, `*_Center_Small.mp4`) | the 2D-pose route on postmodern material; layering (M5c) later | 104 / 104 |
| H7 | refs | Trisha Brown *Locus* (MoMA) and *It's a Draw* (Walker) images; 3–5 Marey geometric chronophotographs | ground truth for "what dancing draws" | ~25 / 25 |

**Second round**, once M1 works:

- the rest of Stocos;
- EMOKINE MVNX for one choreography × 6 emotions (~115 MB raw);
- *Loops* take-1 from the Wayback Machine (564 MB) for finger trails;
- the remaining Hay runs;
- AIST++ `motions.zip` (306 MB) as the street contrast;
- a DanceDB contemporary/emotion pick, after Ian accepts its terms.

**Tooling install**, also a go:

- `rtmlib`, `onnxruntime` and `opencv-python` into `.local/gesture/.venv`;
- the RTMW and RTMO ONNX weights (downloaded on first use).

Not needed for H1–H5.

## 6. Prototype order

1. **M1 on H1, H4 and H5.**
   - Build a trail Drawing, then run `topology_features`, `learn_model` and
     `generate_structure(kind="learned")`.
   - Restyle in Hokusai's hand.
   - Report dance-vs-artist topology and quality separability.
2. **M2a growth tree**, first by fitting oehlen_tree params (no API change),
   compared with G4.
3. **M5a impossible-skeleton retarget**, drawn as M1 trails of the new tips.
   - Score N1–N3 along the calibration ladder.
   - Use CMU 55 as the midpoint check.

M4 waits for duet data. M3 is an optional layer.

## 7. Blockers and open points

1. **Downloads.** Every download needs Ian's go: H1–H7, the ONNX weights and
   the pip installs.
2. **Remote range fetch.** Fetching single zip members needs a ~40-line stdlib
   script (local header + zlib inflate). It is not written yet.
3. ***Loops* is dead upstream.** openendedgroup.com returns 404. Only
   Wayback takes 1 and 3 exist, each a whole .tar.gz with video.
4. **DanceDB.**
   - The performance table loads by JS from an endpoint that returned nothing
     to curl, so file sizes are unknown.
   - Downloading implies accepting its (self-contradictory) licence. That is
     Ian's click.
5. **Synchronous Objects and TWO raw data are not public.** Ask ACCAD
   (OSU) if M4 needs real Forsythe cue data.
6. **2D estimators degrade on floor work and inversions**†, which contemporary
   dance has plenty of. That is why the route is mocap-first. Hay's solo is
   mostly upright†.
7. **M2's option (ii) changes `topology.py`.** Adding a `kind` and
   distribution-valued tree params is the coordinator's call. Option (i) does
   not change it.
8. **Unverified details:**
   - BVH frame rates and skeleton layouts of E2 (they are in `Docs/*.odt`);
   - the licences of FineDance, Motorica, BRACE and MotionBERT;
   - Muybridge plate numbers.

## URLs used

- E2-Create Motion Bank: https://zenodo.org/records/7031672 ; Instituto Stocos: https://zenodo.org/records/7034917 ; EMOKINE: https://zenodo.org/records/7821844 , paper https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11525441/
- Bisig AI-Toolbox: https://gitlab.zhdk.ch/dbisig/aitoolbox
- CMU mocap search: http://mocap.cs.cmu.edu/search.php?subjectnumber=%&motion=%dance% ; subject 55: http://mocap.cs.cmu.edu/search.php?subjectnumber=55 ; CMU terms via https://data.4tu.nl/datasets/0448aab2-3332-449f-a8e2-d208cb58c7df
- KIT: https://motion-database.humanoids.kit.edu/details/motions/1035/
- DanceDB: https://dancedb.cs.ucy.ac.cy , FAQ https://dancedb.cs.ucy.ac.cy/main/faq ; Aristidou emotion work https://andreasaristidou.com/DanceWemotion ; AMASS https://amass.is.tue.mpg.de/license.html
- AIST++: https://google.github.io/aistplusplus_dataset/download.html , https://github.com/google/aistplusplus_api ; AIST Dance DB terms https://aistdancedb.ongaaccel.jp/terms_of_use/
- BRACE: https://arxiv.org/pdf/2207.10120 , supp https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136680321-supp.pdf
- FineDance: https://github.com/THUSIGSICLAB/FineDance ; PopDanceSet: https://arxiv.org/html/2405.03178v2 ; Motorica styles: https://arxiv.org/pdf/2511.20469 ; Dance with Melody: https://scrapbox.io/DancePedia/Dance_with_Melody:_An_LSTM-autoencoder_Approach_to_Music-oriented_Dance_Synthesis ; CoMPAS3D: https://arxiv.org/pdf/2507.19684 ; Chang-E: https://cislab.hkust-gz.edu.cn/projects/chang-e/
- Emotion DBs: https://physionet.org/content/kinematic-actors-emotions/ , https://hal.telecom-paris.fr/hal-02287074v1 , https://researchers.mq.edu.au/en/publications/the-mcnorm-library-creating-and-validating-a-new-library-of-emoti/
- Motion Bank scores: http://scores.motionbank.org/ (API: http://scores.motionbank.org/api/deborah_hay/sets.json , /api/two/sets.json , /api/jbmf/sets.json ; video host d35vpnmjdsiejq.cloudfront.net/dh/piecemaker/<file>.mp4) ; Coventry project page https://www.coventry.ac.uk/research/research-directories/current-projects/2015/motion-bank ; Processing repo https://github.com/motionbank/burrows-fargion-processing ; TWO blog https://motionbank.asc.ohio-state.edu/category/motion-capture/
- Synchronous Objects: https://synchronousobjects.osu.edu/ , essays https://synchronousobjects.asc.ohio-state.edu/SODanceDataObjectsEssays.pdf
- Improvisation Technologies: https://improvisation-technologies.zkm.de/intro/ , https://zkm.de/en/node/62551
- Living Archive: https://experiments.withgoogle.com/living-archive-wayne-mcgregor , https://waynemcgregor.com/research/living-archive
- Cunningham: https://www.mercecunningham.org/the-work/dance-capsules/ ; LifeForms https://www.sfu.ca/sfunews/stories/2019/11/sfu-software-key-to-choreographer-merce-cunningham-work.html ; Loops https://www.openendedgroup.com/artworks/loops_open.html , Wayback http://web.archive.org/web/20160527234524/http://openendedgroup.com/wp-content/uploads/loops/Loops-take-1.tar.gz ; OpenEnded Group https://en.wikipedia.org/wiki/The_OpenEnded_Group
- Trisha Brown: https://www.moma.org/collection/works/184698 , https://walkerart.org/collections/artworks/drawing-for-locus , https://walkerart.org/collections/artworks/its-a-draw-for-robert-rauschenberg , https://trishabrowncompany.org/trisha-brown/visual-art , https://Monoskop.org/images/8/83/Rosenberg_Susan_2012_Trisha_Browns_Notebooks.pdf
- Labanotation: https://www.dancenotation.org/ntd-catalog/ , https://www.dancenotation.org/about-the-library/
- Schlemmer: https://www.moma.org/s/ge/collection_ge/object/object_objid-33327.html , https://www.artchive.com/?p=191440
- Hansen / Orrico: https://www.creativeboom.com/inspiration/emptied-gestures-is-an-experiment-in-kinetic-drawing , https://www.arts.gov/stories/video/tony-orrico-endurance-drawings
- Marey: https://collection.sciencemuseumgroup.org.uk/search/object_type/chronophotograph , https://numerabilis.u-paris.fr/medica/bibliotheque-numerique/presentations/marey/03-en.php
- Commons: https://commons.wikimedia.org/wiki/Category:Videos_of_butoh , https://commons.wikimedia.org/wiki/Category:Videos_of_dance
- RePlay: https://impact.ref.ac.uk/casestudies/CaseStudy.aspx?Id=24888
- Retargeting: https://diglib.eg.org/handle/10.2312/egs20241019 , https://sites.cc.gatech.edu/graphics/projects/Sumit/homepage/papers/sca09/jain_moanal_sca09_draft.pdf
- Tooling: rtmlib https://github.com/Tau-J/rtmlib , https://pypi.org/project/rtmlib ; MediaPipe https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python ; ViTPose HF https://huggingface.co/docs/transformers/v5.14.0/model_doc/vitpose ; GVHMR https://github.com/zju3dv/GVHMR , https://huggingface.co/ryanrudes/gvhmr ; WHAM https://github.com/yohanshin/WHAM ; 4D-Humans https://huggingface.co/spaces/nzhenev/HMR2.0/blob/main/README_github.md ; Sapiens https://huggingface.co/facebook/sapiens-pose-0.6b-torchscript/blob/main/README.md ; OpenPose licence via https://community.vuo.org/t/have-you-seen-openpose/6070

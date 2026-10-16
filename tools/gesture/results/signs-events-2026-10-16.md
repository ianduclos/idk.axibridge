# Signs as line events — 2026-10-16

Follow-up to `signs-2026-10-16.md` (round 6). That round's judge result was
clear about what carried the effect (attached signs) and what didn't (beside-
line dots), and the honest reading was that "most signs are separate stamps;
the reference's forms are the line itself changing". This round replaces
stamping: the placement grammar now chooses **where** on the line network an
event happens, and a regime operator (`gesture/regime.py`) turns **that part
of the line** into the sign.

Code: `gesture/signs.py` §"LINE EVENTS" (`EventGrammar`,
`learn_event_grammar`, `plan_events`, `apply_events`, `place_events`,
`render_events`); `experiments/signs_study.py` stages `events_grammar
events_vocab events_sheets events_pairs`; `tests/test_signs.py` (+6 tests,
whole file under 1 s). Per-run outputs: `.local/gesture/out/signs_events/`.
Figures: `signs-events-vocabulary.jpg`, `signs-events-v6.jpg` (events |
round-6 stamps), `signs-events-tree.jpg` (events | the same events at random
places).

Scale used in the sheets: v6/tree drawings at 0.2 mm/px (180 × 240 mm),
pen 0.5 mm. Sign sizes are in units of the drawn line, w = 0.6 mm, as round 6
did.

## 1. Model

`plan_events(lines, rng, grammar, w=…) -> [LineEvent]` reads the network's
sites (`_Net`):

- free ends;
- junctions, both T (a line ending on another) and X (crossings);
- corners (turning ≥ 70° within ±2 w);
- small self-loops and faces of the line arrangement.

Each event picks one of these sites, then an operator. `apply_events(...)`
returns RegimeStrokes: every input line, edited, plus child strokes grown
from it. `render_events` renders each "mark" as one unioned outline. A mark
is a line, its children, and every line it shares a junction mass with.

| # | site | op | what the line does (operator) |
|---|---|---|---|
| 1 | end | drop | pools along a short ramp, then `terminal_drop("drop")` |
| 2 | end | lozenge | thickens to nib over the fitted ramp, then a nuqta press (`thicken` + `terminal_drop`) |
| 3 | end | hook / ring / block | `close_fill(amount ≈ 0.5 / 0 / 1)`: a nib loop whose counter shrinks / a line loop / a counter that closes into a dot |
| 4 | end | vessel | the end flares into a goblet (`swell("vessel")`, W only on the tail) |
| 5 | end | eye | `eye`: a loop, then an inward spiral that swells to a pupil |
| 6 | end | detached | the line stops; after a calligraphic gap, a dot continues it (the only stroke that leaves its line) |
| 7 | interior | bead | asymmetric swelling, with rise and fall drawn separately |
| 8 | interior | vessel_mid | slow rise (nib ramp), fast fall: an oval mass on the line |
| 9 | interior | nib | a stretch becomes a broad-nib ribbon (W ∝ size, r ≈ 1.15–1.4) and back |
| 10 | interior | knot | the line makes a small loop that fills in (geometry insert) |
| 11 | interior | comb | the line sheds 1–3 short tapering ticks |
| 12 | interior | drip | the line swells slightly and sheds a hanging drip ending in a drop |
| 13 | interior / junction | **body** | Oehlen's rule: a thick core on the line with 2–4 thinning exits moving away, each exit's length answering the previous one's |
| 14 | loop | pupil | a short stalk curls from the loop's rim into a pupil |
| 15 | loop | fill_loop | a self-loop closes and fills (op 15 has no reference evidence; it is never drawn by the fitted grammar, only in the vocabulary sheet) |
| 16 | junction | junction_mass | both lines thicken into one rounded mass where they meet; the lines are its exits |
| 17 | corner | comma | the head pools at the corner, and the tail thins along the outgoing leg |

**Transitions.**
- Nib-type ramps come from the fitted thin→thick ramp. The reference image
  measured 1.11 / 1.49 / 2.88 thick widths (25→75 %).
- Calibration: `regime.ink_width` showed that a smoothstep r-ramp of length
  R puts its 25→75 % width rise in 0.22 R. The r-ramp is therefore
  q / 0.22 × size.
- Compact masses (beads, knots, junction masses) use a quarter of that
  length, and junction masses 0.6 of a quarter. The reference's blobs are
  rounder than its nib transitions. **That factor is a design choice, not
  a fit.**
- Rise and fall are drawn independently, so no swelling is symmetric.
- All draws from fitted log-normals are clipped to [0.7·q25, 1.4·q75]. An
  unclipped tail draw once produced a 1 mm "nib".

## 2. What was learned (`events_grammar`)

**Sources.**
- The 26 forms read by eye in round 6 (`MANUAL_REF`). Each is mapped to the
  event that would make it (`signs.REFERENCE_EVENTS`). One form, the
  negative eye inside a mass, is not representable.
- The 16 reference masses with ≥ 3 exits (84 % of 19, `regime` fit).
- 299 calligraphic dots from 11 generative-allowed sheets, through the
  policy gate.

| # | quantity | value |
|---|---|---|
| 1 | site mix | junction 0.39 · end 0.32 · interior 0.17 · loop 0.07 · corner 0.05 |
| 2 | end ops | drop 0.31 · detached 0.23 · hook 0.15 · lozenge / vessel / block / ring 0.08 each |
| 3 | interior ops | knot 0.25 · bead 0.25 · vessel_mid / comb / nib 0.13 each · body 0.12 (design) |
| 4 | density | **0.009 events per w** of line (41 events / 4 557 w) |
| 5 | groups | sizes 2, 3, 3, 5 (13 of 25 forms); a group starts with p = 0.25 |
| 6 | spacing inside a group | 6.7 / 10.0 / **12.8** / 13.1 / 16.7 w (p10–p90, nearest neighbour) |
| 7 | size ratio, neighbour / previous | log ratio −1.34 … +1.57, median ≈ 0: answers are as often bigger as smaller |
| 8 | sizes / w | bead 2.4–4.9 (automated interior swellings; the read boxes include the line and overstate it); junction mass heavy-tailed: 62 automated junction thickenings ≥ 2 w plus the fit masses 6.2–13.5 w; drop 3.9–6.1; hook 7.5–11 |
| 9 | detached dot | size 1.5 × calligraphic dot / line (1.4–4.3 w); gap / dot size 0.23 / 0.49 / **0.93** / 1.81 / 3.58 (p10–p90) |
| 10 | detached share | 3 / 41 = **7 %** of events; overall ≈ 2–4 per sheet |

**Responsive groups** (Oehlen: "each branch answers the one before"):
- A follower sits one spacing draw along the same line from the previous
  event. Past the line's end it hops to the nearest other line.
- Its site is read off the line at that spot. A follower landing at a
  junction becomes a junction event; one landing at a corner becomes a
  comma.
- Its op is conditioned on the previous event: the same op ×0.25, and a
  heavy op answering a light one (or the reverse) ×1.6.
- Its side flips with p = 0.6.
- Its size is the previous size × a sampled neighbour ratio.

The 0.25, 1.6 and 0.6 are design values; there is too little group data to
fit them.

Realised on the sheets:

| # | sheet | events | in groups | detached dots | pen-down length | paths |
|---|---|---|---|---|---|---|
| 1 | matisse | 35 | 17 | 2 | 2.3 → 4.6 m | 49 → 203 |
| 2 | hokusai | 41 | 21 | 4 | 2.8 → 4.5 m | 81 → 231 |
| 3 | ingres | 25 | 5 | 3 | 1.6 → 2.7 m | 35 → 124 |
| 4 | tree | 32 | 16 | 3 | 2.1 → 4.2 m | 40 → 200 |

The events roughly double pen time.

## 3. The sheets, looked at honestly

1. **`signs-events-vocabulary.jpg`**
   - The new ops read as the line doing something:
     - a drop, a block or a hook at a line's end;
     - a vessel/goblet growing out of a wave (the strongest);
     - a knot that fills in;
     - a junction mass whose exits are the lines themselves;
     - **body**, a thick core with thin legs, reads at once as a bug or
       insect: Oehlen's rule works at sign scale.
   - Weak ops:
     - **nib** is barely visible: a small hollow lens. This is the known
       hollow-pipe problem at a 0.5 mm pen.
     - **comb** is often a single tick.
     - **comma** at a corner reads more as a pooled corner than a comma.
     - **pupil** on a stalk reads like a clock hand more than an eye.
2. **`signs-events-v6.jpg`**, events | round-6 stamps.
   - Setup: same lines, same count. The stamps are scaled up to match the
     events' extra ink (otherwise they were far lighter and the comparison
     would be about weight).
   - With events, **it now reads as the line itself changing**. Masses sit
     at junctions and line ends, threads swell, and drops close lines. The
     stamps read as objects laid over the drawing: rings, eyes, crescents
     and black ovals floating in the gaps.
   - The events are heavier and more uniform than the reference:
     - many 2–5 mm blobs of similar weight;
     - where a group lands at one crossing, several masses fuse into one
       large black clot (hokusai, centre);
     - the reference's quieter range (specks, hairline hooks, combs) is
       under-represented next to the masses.
   - **Risk:** one stamp panel (hokusai) holds an accidental *face*, made
     of two dots and a "w" mouth. This is a stamps artefact, but the E3
     face check stays necessary for anything shown.
3. **`signs-events-tree.jpg`**, events | the same events at random places.
   - Both panels are made of line events, so both look organic. The
     difference is subtle:
     - the grammar's masses sit at forks, and its clusters run along one
       branch;
     - the random panel strings beads mid-branch and leaves forks bare.
   - The tree with body ops (seed 4) is the most "communicating" sheet:
     insect-like knots at the forks.
   - Artefact: a long nib event on a trunk renders as a hollow double line
     (seed 1).
4. **Overall.**
   - The glued-capsule look of round 6 is gone: no periodic beads, sizes
     vary, swellings are asymmetric.
   - What is still missing:
     - variety in *weight*: too many mid-size blobs;
     - the wet, irregular mass edges, which are another thread's work in
       `regime.py`;
     - a lighter end of the vocabulary that registers at plot scale.

## 4. Blind judge pairs (to be judged by the lead; not judged here)

`.local/gesture/out/blind_events/pairs/`:
- 36 pairs (`pair_00.jpg` … `pair_35.jpg`), A | B, same lines in both panels;
- `QUESTION.txt`: "In which panel do the small shapes (dots, drops,
  swellings, knots, hooks, ticks) seem to BELONG to the lines — to say
  something? A or B, confidence 1–5."

Key **outside the repo**: `/tmp/gesture_events_key.json`. Per pair it holds
the condition, the source, the seed, which panel holds the events, and the
mark counts.

| # | condition | pairs | the other panel |
|---|---|---|---|
| a | events vs round-6 stamps | 12 | `place_signs` with the same count, weight-matched (stamp w scaled so sign ink ≈ the events') |
| b | events vs random events | 12 | the same ops and sizes, uniform positions along the lines (end ops at random free ends), no groups; junction masses become beads |
| c | calibration: events vs scattered stamps | 12 | weight-matched stamps at random free places (`place_random`); should be easy |

Structures rotate v6 Matisse / Hokusai / Ingres / oehlen_tree, 3 of each
per condition, with seeds 3000+.

Expectation, not a result: (b) is the hard test. Both panels are made of
line events, and only site choice (junctions, ends, corners) and clustering
differ.

## 5. Policy

- `learn_event_grammar` runs every calligraphic dot source through
  `calligraphy.require_generative` before learning (test: a Qur'anic source
  raises `PolicyError`).
- Calligraphy contributes only the detached-dot gap and size ratios. No
  letterform is used. Every event is a parametric operator on the host
  line.

## 6. Open problems

1. **Weight distribution.**
   - Junction masses are 39 % of events, as in the reference, but the
     reference's other 60 % includes specks and hairline marks that read at
     its scale and vanish at ours.
   - Options: a per-sheet mass budget, or a size prior that leans light
     away from structural junctions.
2. **Clots.** A group that revisits one crossing fuses masses. The
   clearance check uses anchors only, not the ramps' reach.
3. **The nib** event, and the hollow pipe it makes on long stretches: the
   open thickness question again.
4. **Faces** (both a pupil and the pupil-on-stalk can make one): no
   automated face check; E3 stays required.
5. The responsive constants (op damping, contrast boost, side flip) are
   design values. More reference reading, or a second reference, would let
   them be fitted.
6. **body** is a design share (12 %), with no measured rate. Oehlen
   supplies the rule, not a frequency.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
$P -m experiments.signs_study events_grammar events_vocab events_sheets   # ~15 s (needs reference/dots stages' json)
$P -m experiments.signs_study events_pairs                                # ~55 s, 3 workers
$P -m pytest -q tests/test_signs.py                                       # 28 tests, ~1 s
```

Full gesture suite: **346 passed in 41 s**.

## Blind judge on the event pairs (run by the lead after this report)

Sonnet judge, images only, key outside the repo; 36 pairs.

| # | condition | judge picks the events panel | p | mean confidence |
|---|---|---|---|---|
| 1 | events vs round-6 stamps (ink-matched) | **12/12** | < .001 | 4.8 |
| 2 | learned events vs the same events at random sites | 4/12 | .39 | 1.2 |
| 3 | calibration: events vs scattered stamps | 12/12 | < .001 | 5.0 |

Growing signs out of the line beats stamping them, decisively. Once marks
are attached, though, the learned choice of *where* (which site) does not
beat random sites for this judge at this scale: attachment carries the
"belonging", not the placement statistics.

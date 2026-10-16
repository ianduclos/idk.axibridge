# Script as a syntax for foreign gestures — 2026-10-16 (round 8)

Code: `gesture/script_syntax.py` (measurement, slot model, assembly,
controls, renderer, overwriting → mass), `experiments/script_syntax.py`
(stages `measure table pairs genres mashq mashq_cloud`),
`tests/test_script_syntax.py` (8 tests, 1.5 s; one run took 31 s under
this round's load). Per-run output: `.local/gesture/out/script_syntax/`.

## What I tried

Arabic-script writing treated as a system for joining marks, with nothing
about letters. From the ink mask of each sheet: pen width w (the nuqta
unit), a baseline angle, connected components split into **bodies**,
**dots** and small **marks** by size in w. Text lines are taken from the row
profile. Per body the model keeps its width, rise and drop around its own
baseline, its offset from the line, the ascender peaks of its column-top
profile (relative x and height) and the gap to the next body leftward
(negative means overlap). Per dot or mark it keeps the owning body,
relative x, vertical offset and group size. A line is a sequence of these
slots. To generate, blocks of 3 consecutive measured slots are resampled
until the line is long enough.

Assembly: each body is one contiguous path, written right to left. Script
connectors run along the baseline. Each measured ascender is filled with a
**foreign fragment**: a Matisse or Hokusai stroke window, normalised so its
chord lies on the baseline with the bulge up, and chosen by bulge/chord
ratio. A long event-free stretch gets a low foreign arch, so no kashida
is longer than 9 w. A measured drop becomes a terminal tail tilted 35–70°
down-left. Dots are small irregular filled blobs at the measured places,
in groups of 1–3. Marks are tiny Hokusai ticks.

**Policy.** I measured everything, including the Bulaq print and the album
and manuscript pages. The generative models are fitted only on sheets that
pass `calligraphy.require_generative`:

1. shikasta: wc-12, wc-13, wc-15;
2. nasta'liq: met-716305, met-716307, wal-W668-66b, wal-W668-74b, met-716304;
3. diwani: wc-05;
4. maghribi: none (see the correction below), so there is no maghribi
   model.

`SyntaxModel.fit(generative=True)` calls the gate plus a local exclusion
list (`EXCLUDE_GENERATIVE`), and a measure-only model refuses to sample
(tested). No stroke, contour or letter shape from a calligraphy sheet
reaches the output: only box sizes, peak positions, gaps and offsets in
w units. The fragment pools are Matisse and Hokusai only.

**Correction (lead, 2026-10-16).** wc-30 (the 1787 treaty) opens with a
devotional invocation, so it is measure-only even though the manifest
gate passes it as a document. It now appears only in the measurement
table. The first run had fitted the maghribi model on it. That model is
gone, and the pairs and the genres sheet were regenerated without it.
`test_wc30_excluded_from_generative_pool` and
`test_experiment_models_exclude_wc30` guard the exclusion.

## Numbers (genre syntax, w units; Y = generative sheets, m = measure-only)

| # | genre | lines | bodies | body width | gap med | overlap | asc /10 w | dots/body | dots above | offset sd |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Bulaq print (m) | 181 | 3991 | 6.0 | **+2.5** | **12 %** | 0.27 | 1.27 | 73 % | **2.6** |
| 2 | naskh MSS (m) | 31 | 694 | 6.3 | +0.8 | 33 % | 0.31 | 1.19 | 67 % | 3.2 |
| 3 | maghribi (m; wc-30, wc-32, wc-33) | 37 | 775 | 6.5 | +0.8 | 34 % | 0.37 | 1.30 | 65 % | 2.8 |
| 4 | diwani wc-05 (Y) | 11 | 698 | 5.0 | −0.5 | 61 % | 0.16 | 1.11 | 57 % | 7.5 |
| 5 | nasta'liq (Y) | 41 | 671 | 6.5 | −0.7 | 55 % | 0.15 | 1.86 | 53 % | 16.5 |
| 6 | shikasta (Y) | 8 | 695 | 8.5 | **−6.0** | **93 %** | 0.06 | 3.04 | 52 % | 42 (!) |

What the table supports:

1. **Print is the most regular syntax.** It has positive gaps, the least
   overlap and the flattest baseline (offset sd 2.6 w).
2. **Overlap rises from print through naskh and maghribi to diwani,
   nasta'liq and shikasta.** That is the order in which bodies stop sitting
   side by side and start nesting and stacking.
3. **Dots sit above the line more often in print** (73 %) than in the
   hanging scripts (52–57 %).
4. **Ascenders get sparser** in the hanging scripts (0.06–0.16 per 10 w,
   against about 0.3).

Caveats:

1. The **shikasta and diwani line finding is weak**. Words step and lines
   interleave, so wc-12 and wc-13 resolve as a single line, and shikasta's
   offset sd of 42 w is mis-assignment, not stepping. Bodies more than
   0.45 line spacings off their line are dropped before fitting.
2. Baseline angles for the slanted and siyah-mashq sheets were **set by
   eye** (`ANGLES`), the same way the crops were picked. Three automatic
   estimators failed on them: projection peakiness, body-centroid alignment
   and `dominant_direction`. They mistake sweep slant, justified columns
   and mashq diagonals for the line.
3. wc-10, wc-17 and wc-24 lose every body under Otsu.
4. Karalama has only 2 usable "lines" (rotated tangles) and is left out of
   generation.

## Images

1. `script-syntax-genres.jpg` shows one pool of fragments under the three
   generative syntaxes, plus both controls on the diwani panel's pieces.
   The **diwani panel reads most as lines of writing**: a baseline, a pulse
   of arches, dots hovering. The two controls read as debris. In the first
   run a maghribi panel, now withdrawn, read the same way.
   Nasta'liq is sparser and larger. Shikasta crams its line into the right
   half, which is a symptom of the overlap measurement.
2. `script-syntax-pairs-1.jpg` holds pairs 1–4 of 12 blind pairs. All 12
   are in `.local/gesture/out/script_syntax/pairs/`.
3. `script-syntax-mashq.jpg` is the limb (below).

**Blind-pair key** (regenerated after the correction; syntax side,
genre, fragments, control). Ink length is identical for scatter pairs and
0.3–3 % lower for chain controls, because of clipping at the band edges.

| # | pair | syntax side | genre | fragments | control |
|---|---|---|---|---|---|
| 1 | 01 | A | shikasta | matisse | scatter |
| 2 | 02 | B | nasta'liq | matisse | chain |
| 3 | 03 | A | diwani | matisse | scatter |
| 4 | 04 | A | shikasta | hokusai | chain |
| 5 | 05 | A | nasta'liq | hokusai | scatter |
| 6 | 06 | A | diwani | hokusai | chain |
| 7 | 07 | B | shikasta | matisse | scatter |
| 8 | 08 | A | nasta'liq | matisse | chain |
| 9 | 09 | B | diwani | matisse | scatter |
| 10 | 10 | A | shikasta | hokusai | chain |
| 11 | 11 | A | nasta'liq | hokusai | scatter |
| 12 | 12 | B | diwani | hokusai | chain |

Honest caveat on the pairs: the syntax side is obvious at a glance,
because the controls have no baseline. A judge will find it at about
100 %, and that measures "lineness", not "saying something". The judge
prompt should ask which one *seems to be saying something*. The next
control should keep the baseline and the bodies and shuffle only the
syntax: body order, gap sequence, and dot placement drawn uniformly along
the line. That control separates "a line" from "this script's rhythm".

## The limb: siyah mashq, rewriting until line becomes mass

The first attempt, `mashq_cloud_dud.jpg` in `.local`, was a dud: 36 lines
scattered at the practice-sheet angles turned into a tangle and then a
generic potato blob.

The second form follows what practice sheets actually do. Each of 3
syntax lines (nasta'liq exercise model; it never used wc-30, and the
rerun was byte-identical) is **rewritten** k times nearly on
top of itself, with an offset of 1.5 w along and 0.7 w across, a ±2° turn
and a smooth wobble. The lines sit in bands at the measured mashq angles
(−30° and +20°). The measured practice sheets reach 23–35 % ink coverage,
and their densest tiles reach 38–55 %.

| # | copies | ink (lines) | ink (mass rule) | masses |
|---|---|---|---|---|
| 1 | 1 | 1.0 % | 1.0 % | 0 |
| 2 | 3 | 2.8 % | 3.5 % | 9 |
| 3 | 8 | 6.7 % | 11.2 % | 11 |
| 4 | 20 | 12.2 % | 19.0 % | 12 |

**It held, at 3× and 8×.**

1. Rewriting alone turns a monoline into a **ribbon with fringes**. Line
   becomes nib by accumulation, with no width model. Repeated dots become
   swarms and constellations, which is a sign behaviour I did not design.
2. With the coincidence rule (blur 0.9 w, threshold 0.30), the mass forms
   **in the line's own shape**, where the copies agree. The hair fringe
   stays line at the edges, where they disagree. That is a transition
   built from agreement rather than from a field.
3. At 20× it collapses into one blob again, so the interesting band is
   3–8 copies.

## Surprises

1. Dots carry most of the "writing" impression. Joined arches on a
   baseline without dots read as stitching or cursive "m"s. With dots at
   measured offsets they read as script. The nuqta-as-placement-grammar
   limb is the obvious next thing.
2. A symmetric bowl with a dot over it read as a letter at once, so drops
   became tilted terminal tails. That was the one abstraction I had to
   make. In my reading no panel shows a letter or a word. Single ∩ arches
   with a dot can still suggest one, so the reader check (E3) stays
   required before anything is shown.

## Next limb

1. Make the baseline-kept, syntax-shuffled control.
2. Make the mashq agreement-mass a composition operator: rewrite count as
   a field, so a sheet goes from line to ribbon to mass where the field
   says so.
3. Use nuqta logic (measured dy, rx and grouping relative to a body) as
   the placement grammar for `signs` along any line, Matisse included.

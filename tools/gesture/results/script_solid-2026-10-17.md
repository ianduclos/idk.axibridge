# Round 11, exploration 3: solid abstract script (2026-10-17)

Ian on the round-10 shikasta rows: "boring and blocky, not solid enough to
register as abstract script." The fix was not more ink per stroke. It was
joining: the P1 rows are lone glyphs with paper between every one. Joined
into words, with a broad nib whose width follows stroke direction and whose
thick parts are filled line-built, the same hand reads as a page of writing.

Run: `cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.script_solid [measure baseline scripts compare threshold page closeup combos radical evidence legibility]`
(full run about 4 min, most of it tesseract). Output and every recipe:
`.local/gesture/out/script_solid/`, numbers in `numbers.json` there.
Tests: `tests/test_script_solid.py`, 11 passed in 12 s.

## What was built (`kit/script_solid.py`, `kit/script_solid_measure.py`)

| kind | id | what |
|---|---|---|
| voice | `script_solid` | Rows of abstract script cut from one hand. The hand draws one long line; it is cut into glyph windows by **turning budget** (each window turns 1–4 π, so smooth and cornered hands both give glyph-sized pieces in their own manner). A small inventory (9–18 glyphs) is reused with Zipf frequencies and a seeded bigram table, so shapes recur the way letters do. Words are runs of glyphs joined by smooth ligatures into ONE path; lognormal word lengths and spaces; baseline `ruled` / `hanging` (words slope and cascade) / `wander`, sometimes ignored; line ends compress and climb, or end in a swash taken from the hand's smoothest window; nib or bead dots. `join: row` makes each row ONE continuous line with hairline kashidas. |
| renderer | `script_solid_nib` | Broad-nib sweep, width = W·\|sin(θ − φ)\|, so thick/thin follows stroke direction. Thick parts filled with contour-parallel insets (counters kept white), chained into one path wherever the jump stays inside the ink. Centreline drawn as the hairline. No hatching anywhere. |
| renderer | `script_solid_bar` | The negative: words (or whole rows) close into round black slugs and the writing is carved out white. |
| arranger | `script_solid_page` | Part 0 is a drawing; script parts sit in a margin column (`margin`), flow around the drawing (`wrap`), or run as a rotated marginal block (`diagonal`). |
| arranger | `script_solid_stack` | Parts stacked in bands (heading / body / closing of a letter). |
| — | `script_solid_measure` | Texture of writing, measured the same way on scans and on my rows. Units are the nib (W = p80 stroke width), never forms. |

## The measure (scans: measure-only, numbers only)

Measured 27 sheets: 138 hand-written lines (shikasta, nasta'liq, diwani,
maghribi, naskh, karalama) and 183 Bulaq print lines. Qur'anic and devotional
sheets are in the numbers only.

| | band cover | runs / 10 W | x-height | contrast p90/p10 | column fill |
|---|---|---|---|---|---|
| hand-written pages (median) | 0.29 | 2.1 | 3.2 W | 3.2 | 0.93 |
| Bulaq print | 0.32 | 2.1 | 2.2 W | 2.0 | 0.79 |
| **P1 shikasta rows (round 9/10)** | **0.16** | **1.4** | 4.2 W | 3.2 | **0.77** |
| A hanging (shikasta hand) | 0.33 | 2.7 | 3.0 W | 6.0 | 0.88 |
| B Matisse | 0.29 | 2.1 | 2.7 W | 6.9 | 0.90 |
| C dance (mantis) | 0.26 | 2.3 | 4.1 W | 6.0 | 0.84 |
| D machine (Cohen meanders) | 0.36 | 2.6 | 3.6 W | 4.9 | 0.91 |
| E physics (bubble chamber) | 0.41 | 2.8 | 2.4 W | 4.4 | 0.94 |

The P1 rows have half the ink in the band of a real page, two thirds of its
stroke frequency, and paper in a quarter of the columns. That is "not solid"
in numbers. Contrast was never the problem (3.2, same as the pages).

## What decides whether a row reads as writing (threshold sheets)

Three things, in this order:

1. **Joining.** Column fill must reach about 0.85–0.95. Lone glyphs
   ("confetti", the P1 condition) give 0.59 and read as a row of signs or
   single letters; this is also where shapes read most as letters. Every
   joined variant reads as writing.
2. **Weight.** Band cover 0.25–0.42, x-height 3–5.5 nib widths. Below
   about 0.2 cover (x-height ≥ 7.5 W) it reads as pen handwriting, not
   calligraphy. Above about 0.5 cover (x-height ≤ 2.7 W) the counters close
   and it becomes black paste: Ian's "blocky" returns at nib_w 0.85·x.
3. **Vertical events.** A row with no ascenders, no descenders and even
   spacing (the "true seismograph", column fill 1.00) reads as a flattened
   scribble or rope, not script. Ascenders and spaces break the band; take
   either away and it slides toward the seismograph.

What mattered less than I expected: an alphabet. A row with no recurring
inventory (every glyph a fresh window) still reads as writing at one row.
Recurrence probably matters at page scale; I did not test that.

The texture distance to the corpus is a blunt proxy. It ranks the extremes
right (nib_w 0.06: 1.95; confetti: 1.11; grouped: 0.5–0.75) but cannot see
recurrence or ascenders. Column fill and band cover are the numbers to
watch.

## Images worth Ian's eyes

1. `results/script_solid-compare.jpg`: P1 rows as cell 1, then the five
   scripts. My read: A and D are the most solid; A reads strongly as
   Persian-like writing. C reads as a notation more than a script. B is the
   most graceful.
2. `results/script_solid-page-manuscript.jpg` and
   `script_solid-closeup-manuscript.jpg`: script A, each row one continuous
   line, with a diagonal marginal gloss. This is the strongest "page of
   writing". The hairline kashidas between words wave like a thread, which
   I like. The gloss came out small and clipped.
3. `results/script_solid-threshold-grouping.jpg` and `-threshold-weight.jpg`:
   where it starts and stops reading as writing.
4. `results/script_solid-radical.jpg`: (a) rows as one line hold. The carved
   versions (c–f) are bold, but they read as neon or graffiti outlines more
   than as writing. (e) row-bars are the most striking and the least
   script-like. Partly a failure; see below.
5. `results/script_solid-combo-answer.jpg`: a mantis drawing; the dance
   script fills the page around it. It is a good composition. The script
   side reads as notation (Λ, zig-zags) more than as text.
   `.local/.../combo-margin.jpg` (a Matisse drawing with its own script in
   the margin) is quieter and more elegant.
6. `results/script_solid-page-matisse.jpg`: a full page of the Matisse
   script. It reads as a page of writing, with the least letter-likeness of
   the round-bodied scripts.

## Legibility self-check (honest)

- **Arabic:** script A, from the shikasta hand with a 70° nib and dots, is
  Arabic-*like*. I see recurring shapes that resemble single letterforms: a
  three-tooth form close to sīn, a lām-alif-like pair, bowls with a dot. I
  see no words, and no letter sequences I can read. My Arabic reading is not
  expert, so a human reader check (the round-8 E3 step) is needed before A
  goes anywhere.
- **Latin:** this is the real failure. Any script written with small arches
  (≈ π turning per glyph) at a modest x-height slides toward Latin cursive.
  - Molnar's hand in the first version of E gave a readable "Don…" fragment
    (tesseract read "daring" at conf 61). It was replaced.
  - The bubble hand in E, used for a letter, gave "bit" and "Und" by eye,
    and letter pairs ("de", "ne", "ue") in the rerun. OCR found nothing. The
    letter page now uses the machine script. E survives only as a row
    script, and it still reads as mirrored Latin handwriting.
  - The Matisse margin column showed "you" by eye when written ltr, so it
    is now written rtl. It still shows 2-letter pairs such as "on" and "no".
  - Evidence crops: `results/script_solid-legibility-evidence.jpg`.
- **OCR probe** (tesseract, English model; Arabic has no model here):
  - Positive controls read: Apple Chancery 16 dictionary words, Bradley
    Hand 17, Brush Script 4.
  - Every script row, page and combination, both as written and mirrored:
    zero dictionary words of four or more letters, with one exception.
    "DINER" (conf 62) was read in the machine-wrap combination. To my eye it
    is zig-zags, not letters. "ory" in the mirrored margin combination is a
    3-letter fluke.
  - OCR is weaker than an eye on cursive: it missed "bit" and "Und".
- What reduces letter-likeness, in order: joining (lone glyphs read as
  letters), corner-rich hands (meanders), larger turning budgets per glyph,
  rtl mirroring, and no dot over a simple bowl (the round-8 lesson again).

## Failures and limits

- Carving (`script_solid_bar`) is "blocky" in a new way: outlined slugs.
  Faint seams show between inset rings in the preview at some scales
  (pitch lowered to 0.75 pen to reduce them).
- Corpus line finding is weak for shikasta (6 lines) and karalama (1): the
  stepped lines confuse the row profile. My word segmentation does not split
  manuscript lines (words come out at 57–147 W), so word length is a
  generated-row statistic, not a match.
- Hanging rows collide at leading under about 3 x-heights.
- `polygon_walk` made X and V glyphs (Latin letters). The machine script
  uses `meander69` with self-crossing windows dropped (`simple_only`).
- Every script in a sheet shares one text RNG stream, so word lengths and
  spaces match across scripts. That is good for comparison and bad for
  variety; vary the seed per script in a real piece.

## Proposed core changes (not made)

1. A shared line-built fill helper in the kit. `script_solid.line_built`
   keeps holes (counters), which `dev_beads.solid` drops.
2. `kit.preview` per-ink colour (as in round 10) would let the script and
   its drawing take two pens.
3. A legibility gate for any text-like output: OCR plus an inventory filter
   that rejects glyph windows OCR reads as a letter.

## Downloads that would help (none made)

- Tesseract Arabic model `ara.traineddata` (tesseract/tessdata_best on
  GitHub, about 12 MB), so the Arabic legibility check is not eye-only.
- A Latin/Greek manuscript or chancery-hand page set (for example e-codices
  or British Library digitised manuscripts, about 50 pages, a few hundred MB),
  to measure the texture of Latin scripts. All references now are Arabic
  plus Bulaq print.

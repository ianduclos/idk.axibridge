# Round 10, developments: beads, rare machines, chorus, rosary (2026-10-17)

This thread takes Ian's round-9 notes (`round9-review-2026-10-17.md`) and develops them rather than fixing them. The core is the loose line. Weight is round. Machines come in as events. Grammars are kept whole and set side by side.

Run it with `.local/gesture/.venv/bin/python -m tools.gesture.experiments.developments [beads rare chorus corpus rosary check]`. A full run takes about 55 s. Every tile was made with `kit.run` + `kit.preview` and has its recipe beside it in `.local/gesture/out/developments/`. Tiles with more than one ink also get a `-colour.jpg`. The numbers are in `numbers.json` in the same folder.

## Modules (`tools/gesture/gesture/kit/dev_*.py`)

| kind | id | what |
|---|---|---|
| renderer | `dev_beads` | Gives weight to stresses as round shapes, whatever the stress length. It reads `emphasis` from prosody, or `r − 1` when that is absent, so `timing` and `own_tempo` drive it too. Shapes: `string`, `gather` (at event / peak / end / low), `pool` (a teardrop with a round body), `cluster` (touching beads, unioned) and `knot` (the line itself winds loops at the stress). Fills are line-built: concentric insets joined into one spiral, plus the outer ring (filled). Base line: `wire`, `nib` (r capped at `nib_cap`) or `none`. With `none` the voice is a **ghost** and only its beads are inked. |
| modulator | `dev_rare_machine` | `events` machine interruptions per line. 0 means none; a fraction gives the chance of one more. Each one goes at a spot that means something: `salient` (the loudest heard event), `switch` (the most decisive hand change), `quiet` (the middle of the calmest stretch), `straight` or `random`. Events are kept at least `min_gap` apart and away from the line's ends. The rewrite itself is `voices_machine.hand_over`; only WHERE and HOW OFTEN changed. |
| arranger | `dev_chorus` | Call and response for N voices. `answer_to` is `previous` (a chain), `all` (a voice speaks only where every earlier voice is silent), `leader` or `none`. Each part keeps its own renderer. `inks` holds one Flexoki ink per voice and is stored in the recipe; `render_colour(sheet)` draws them. Answering reuses `prosody_arrangers.answer_mark`. |

## Results

### 1. Beads, not sausages (`developments-beads.jpg`, `developments-beads-closeup.jpg`)

Every tile uses the same drift line (matisse > shikasta > lichtenberg, chain, seed 7000) and the same segment stresses as round-9 panel d. Mass shape is measured raster-wise for any renderer: open the ink with a 1.6 mm-radius disc, label the blobs, and take elongation = √(λmax/λmin) of each blob's pixels. A disc scores 1.

| tile | masses | elongation median / max | longest |
|---|---|---|---|
| a round-9 segment, nib e (the sausage) | 3 | **2.12 / 2.79** | 30.5 mm |
| b round-9 pulse, nib e (kept) | 3 | 1.16 / 1.38 | 13.3 mm |
| c string | 5 | 1.05 / 1.12 | 10.1 mm |
| d gather at peak | 10 | 1.09 / 1.18 | 10.4 mm |
| f pool | 10 | 1.08 / 1.12 | 10.8 mm |
| g cluster | 5 | 1.18 / 1.33 | 11.9 mm |
| i syncopated rhythm (the sausagiest) → gather | 14 | 1.11 / 1.31 | 10.9 mm |

The prosody timing is unchanged; only the shape differs. The ten stresses now carry ten round masses where there used to be three capsules. Quiet stresses were nib bars before; now they are beads at 0.7× size. Read in images: `gather` with `line: nib` makes a "matchstick", a nib swell that ends in a bead, and it sits closest to the kept pulse panel. `cluster` reads as a knot of grapes. `knot` (h) is the most linear answer: the line ties 2–7 loops, with no fill at all.

### 2. Rare machine events (`developments-rare.jpg`, `developments-rare-closeup.jpg`)

These use the round-10 carrier: the same line, pulse prosody, `gather` beads. The machine runs before prosody, so prosody hears the stair's edges as hand changes and sometimes answers with a bead (close-ups d and j). That came about by accident, and it ties the event into the line's own prosody.

| tile | events | machine share of the line |
|---|---|---|
| a | 0 | 0 |
| b, c, d (salient / switch / quiet) | 1 | 2.3 % |
| e | 2 | 3.1 % |
| g | 4 | 7.8 % |
| h, round-9 `handover` density | 25 | **44.9 %** |
| i, one long (40 mm) coarse stair | 1 | 5.0 % |

On this line `salient` and `switch` pick the same spot, because the loudest event is a hand change. At the line's loudest corner the stair curls into a small knot of square turns (close-up b/i). At `quiet` it becomes a fine serration on a smooth curve (close-up d). The span from none to round-9 density is the whole bottom row.

### 3. Chorus (`developments-chorus.jpg`)

Seed 7100. The leader is the drift with pulse stresses in nib e (black). Followers: bubble > hokusai restated with a contour bound (red); meander69 chain in clusters (blue); a shikasta ghost in beads only (cyan). We measured clash, the share of a voice's loud points within 10 mm of another voice's loud points. With no listening (a) the leader clashes 0.33 and the follower 0.13. With `answer_to: all` (d, e) every voice scores 0.00. With `leader` (f) the followers collide with each other at 0.28 / 0.36, which looks busier. Time listening (h) silences the late voices: blue keeps 3 stresses and cyan 2, against 6 and 9 in space. Inverting the roles (g: clusters lead, the drift answers with knots) gave the most "mixed" sheet.

### 4. Corpus favourites (`developments-corpus.jpg`)

- (a) The one-surface sheet v2: mantis dance itself, its own_tempo pauses turned into beads by `dev_beads` (the round-9 foot capsules are gone), × roadrunner (blue) × meander69 chain (red).
- (b) One line through the favourites: roadrunner > shikasta > meander69, chain, danced by Staccato, nib e. This is kit demo 2's method. Its Staccato pools are still elongated (median 1.57, max 2.93).
- (c) The same route with clusters and one stair at the hand change.
- (d) Shikasta nib c × roadrunner dry wire, kit demo 4's method.
- (e) Mantis × shikasta nib c (cyan) × meander69 (red).
- (f) Meander69 with one coarse stair in its calmest stretch. Next to the machine, meander69's own right angles read as kin.

### 5. The risk: rosary, ghost voices (`developments-rosary.jpg`)

Hands whose lines are never drawn, heard only as their stress beads. They sit around one visible roadrunner line (a, b, d), or with no line at all (c, the "constellation"). Each ghost speaks only where the others are silent, so clash is 0 everywhere.

**It held, with one variant clearly best: e/f "bead chains".** In that variant the ghosts tell long stretches of their course as strings of beads (127 beads), and the invisible shikasta and meander69 courses read clearly as dotted hands around the drawn line. This is the "combination" pattern again, line × punctuation of other hands, and it stays contiguous-line-first: the only drawn line is one hand's. The constellation (c) is the weakest. With no line the beads read as scatter and you cannot infer a course from them. Ian should judge (f) in particular, since a one-pen plot is the real case.

### 6. The check: shikasta rows of P1 (`developments-check-shikasta-rows.jpg`)

This is not a study. It re-runs P1 from its saved recipe, keeps only the six shikasta nib rows, and shows them at 10 px/mm in half-rows, labelled as a check. Nothing was done to make them more or less legible. My read: the strokes are Arabic-script-*like* (dots, bowls, a few looped joins), but I see no letter sequences. Ian decides; the question stays open until he answers.

## Surprises

- Prosody hears a machine event as a hand change, so an interruption earns a bead from the hand that resumes.
- On a long stress, `gather` at the lowest point ("ink runs downhill") is often indistinguishable from `gather` at the peak, because segment emphasis is flat and the stretch runs mostly one way. A physics rule for weight would need curved stretches to show.
- A ghost voice in `pulse` mode reads as scatter, but in `segment` + `string` it reads as a course. Ghosts need runs of beads, not single beads.

## Failures and limits

- `mass_shapes` misses beads smaller than 3.2 mm (the opening disc), so quiet beads and the Staccato clusters (b10) count as 0 masses.
- The kit-demo-2 carrier (6 R, Staccato) was too dense for rare stairs to read, which is why that stage moved to a lighter carrier.
- `dev_beads` `knot` ignores `line` = nib (a knot is always wire).
- The pool tail scales with bead size (1.4 d), not stress length. This is deliberate.

## Proposed kit-core changes (not made)

1. `render_image` / `preview` should honour a per-part ink colour. That could be `Ink.meta["colour"]`, or a recipe-level `inks` list beside `renderer`, so colour lives in the recipe without an arranger. `dev_chorus.render_colour` is the stopgap.
2. The renderers base should offer a shared "line-built solid" helper. `dev_beads.solid`, regime fills and `coil` each make concentric fills their own way.
3. `prosody` could optionally write `emphasis` for any regime-writing modulator (timing, own_tempo), so stress-reading renderers need no `r − 1` fallback.
4. `contact` should size cells per row, not take one max height for every row (it wastes space for header strips).

## Next

Put rosary e/f and one-surface v2 (a) on the bench as saved pieces. Try `knot` and `cluster` as the beads of Staccato pools, at a size that scales with dwell. Rare stairs at `quiet` on meander69 against roadrunner as a two-voice sheet.

## Tests

`tests/test_developments.py`: 11 passed in 2.6 s. Whole research suite: 553 passed in 88 s, with no failures.

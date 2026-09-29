# Meander round (29 September 2026)

Ian's brief, after v5: "perhaps we're holding onto the territory thing too closely. also, i was expecting to see the illusion of line width and narrowness through the lines, to create the illusion of volume etc. also kinda more unified stuff idk." The prompt image was the Rio Mamoré (meanders, oxbows, scroll bars). The plan with his full verbatim direction is `docs/plans/territory-meander-round.md`.

Artifact: https://claude.ai/artifact/Bawx12VN4uRgWR2wU2Lso3 (private). New version, render mode **Meander** is the default; v5 and the older renders are still in the Render menu. Everything is judged on screen only; nothing is plotted.

## Process

1. Re-rendered v5 seeds 3, 13, 21 (`v5-seeds.png`).
2. Three Opus brainstorms (process, width, unity) and two Sonnet research reports (techniques, artistic procedures): `docs/research/meander/`.
3. Fable synthesis brief: `docs/research/meander/synthesis-brief.md`.
4. Build (`tools/territory-prototype/t_meander.js`). Fable diagnosed the first width failure mid-build: `docs/research/meander/build-notes/fable-advice-1.md`.
5. Two blind Sonnet reviews: `docs/reviews/meander-sonnet.md`. Round 1 sheets in `round1/`, round 2 in `round2/`; configs and recipes in each `withheld/`.

## Mechanism

- **Migrate and remember.** Up to 12 open centrelines (a trunk plus smaller minors) migrate by curvature (Howard–Knutson upstream recurrence). A neck editor decides cut (an oxbow), refuse (the two limbs stall shoulder to shoulder: a sling) or stall. Minors can be captured by the trunk; the losing reach is abandoned and fades. One reversal at most. Each channel is shown at its own moment in time. Centrelines come from the seed's territory contours, or from nothing (a noise walk).
- **Width from lines.** A channel is either one line or a band of 3–8 strands. The band swells after the apex of a bend and pinches where the bend changes hand. It has a firm core on the inside of the bend and a ragged outside edge whose strands peel off and merge in. Strands cross, drop out and fuse, so the band is never ruled. Only the trunk and the two most active minors carry bands; the rest are single lines between things.
- **History as traces.** Earlier positions are drawn only near an event (cutoff, capture, refusal, reversal, a bend changing hands), only inside the bend, only beside a band, and newest first, clipped wherever a later sweep passed. A tree-ring guard drops evenly spaced nests.
- **Searching register.** One to three quiet single lines in busy ground are restated 2–5 times, each pass drifting on its own.
- **Activity field.** Broad blobs plus one ridge set where bands swell, where history is kept and where strands may cross.

Not built this round (brief §9): braids/knots, bend-level heterochrony, crop-from-a-larger-field, nib field, v5 events.

## Where it landed (round 2, reviewer's reading)

- The swell reads. Bands that drop out and fuse read as one mark that swells and narrows (M04, M02, M11, M05). Rails still show on gentle arcs and straights (M09, M10, M13).
- The searching register shows as one small knot per cell. With it off (M08, M14, M15) the cells are visibly poorer. Doubling it barely differs from 1.
- **Source.** From-nothing beat territory in 4 of 6 seed pairs, and the reviewer identified the from-nothing cells by eye (5 of 6). In round 1 it could not match any cell to its v5 parent (0 of 6), so the inheritance from seeds 3/13/21 is not visible. Territory does give each seed one coherent family.
- **Still firing:** one handwriting (reduced), identical spiral curls (M12, M15, M17, M18), no protagonist in the thin cells (M01, M06, M07, M14).
- **Reviewer's shortlist:** M04, M02, M18, M03, M11, M05, with M12 as the "unified" contrast. In the page these are the Meander render with these settings, reversed order, Auto camps:

| Cell | Seed | Settings |
|---|---|---|
| M04 | 21 | territory source, Searching 2 |
| M02 | 58 | from nothing |
| M18 | 3 | from nothing |
| M03 | 21 | from nothing |
| M11 | 7 | from nothing |
| M05 | 34 | from nothing |
| M12 | 13 | defaults (territory) |

Decision for Ian: keep the territory as the source, switch the default to "from nothing", or blend the two (the reviewer's suggestion)?

## Checks

- `node tools/territory-prototype/smoke_meander.js`: deterministic on every seed. About 250 ms per full sheet; 24 sheets in 4.4 s in node.
- Playwright on the built page: no console errors. The Meander group shows only in Meander mode, and E2 Renderers runs.
- Page fix: the v5 "Searching lines" group was duplicated in the page with duplicate ids (the second copy was dead); removed.

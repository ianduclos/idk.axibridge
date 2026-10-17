# oehlen_conduct — conduction, double and blank, tree program (round 12, Oehlen thread)

Directions D3 (Conduction), D4 (Tree program), D5 (Double and blank) from
`results/oehlen-research-2026-10-17.md`. I looked at all 29 sheets first, mostly
#12–16 (small collage to *Conduction* canvas) and #20–24 (the charcoals).

What I took from the images, as procedures:
- The *Conduction* canvases (#15, #16) are not blow-ups of #12–14. A few threads
  of the dense small sheet come back, each in another instrument: a bold stroke,
  a wandering hairline. Where things change carries over. The drawing does not.
- In the charcoals (#20–24) the "doubling" is two passes that lie on each other
  and then split apart for a stretch. It never reads as an offset copy. Lines
  enter from the edge and stop in the air. The empty half of the sheet is
  decided, not left over.

## What was built (kit files, all new)

- `kit/voices_oehlen_conduct.py`
  - voice `oehlen_conduct`: a dancer's hand conducts a learned hand.
    - **Conductor.** A few seconds of one dancer's hand (`dance_trail`, here
      *staccato*, right hand, 5–12 s), drawn at 34 mm in a corner.
    - **Cues.** The hand's own kinematics fire them: stop → tacet (the line
      ends and the next one re-enters, often from the sheet's edge); sharp turn
      → a place to land; burst → the next hand takes over.
    - **Performer.** A learned hand (`trail_miner`) grows chunk by chunk. Each
      chunk is the best of 16 proposals steered toward the chord to the next
      cue. The grown stretch is then bent to land 75 % of the way onto the cue
      (`land`). The performer gets only cue positions and durations, never the
      source's shape. Slow source stretches get more line and the 2.2 mm pen.
    - **Blank.** Reserved before anything is drawn. Proposals that enter it are
      penalised, and a cue inside it is swallowed (`blank_hard` also cuts at
      the rim).
    - **Second pass.** The longest lines are redrawn from memory (detail under
      3 mm forgotten). The second pass lies on the first line and splits off it
      in a few smooth bumps of random side and height (≤ 8 mm), then rejoins.
  - voice `oehlen_conduct_ensemble`: the same cue track goes to several hands.
    Who plays each stretch follows speed, stops and bursts. A doubled stretch is
    two players that meet at the cues.
  - voice `oehlen_conduct_tree`: the 1988 rules as a program. The trunk is
    vertical and centred, and its cue points come from the source. Branches
    fire at the source's stops and bursts. Every line narrows with distance
    from the figure's midpoint.
- `kit/renderers_oehlen_conduct.py`: renderer `oehlen_conduct_ink` inks each
  run of constant pen width (channel `cw`) as its own pen pass. Nothing is
  filled or hatched.
- `experiments/oehlen_conduct.py`: sweeps, a debug overlay (the scaled source
  and cues under the sheet), and `review`, which rebuilds the five images.
- `tests/test_kit_oehlen_conduct.py`: 9 tests. They cover cues being hit, the
  blank kept, the hard cut, the second pass meeting and parting, cue thinning,
  and determinism across `PYTHONHASHSEED`.

Frame: **300 × 200 mm**, landscape. That is the AxiDraw's whole reach (300 × 218)
at the 3:2 of the 2016 charcoals. The plotter's "body scale" is its bed. The
conductor is 34 mm and the performance about ×6, close to the 30 cm → 2.7 m
step of the *Conduction* works. Seeds 3301–3336, tree 5507–5511; the piece is
3323.

## What happened (about 30 sweeps, every one looked at)

1. **Steering alone fails.** With K = 10 and pull 4, the performer wanders off
   the cue skeleton. The result is unrelated to the source. Adding the landing
   bend (`land`) made the cue points real: median distance to a cue < 15 mm
   (tested). The stretches in between still belong to the hand.
2. **The hand decides everything.** Small-curl hands (matisse, ingres, aaron)
   go fidgety at R = 0.6 × the diagonal. `trail_miner` gives the long arcs with
   sudden turns that read like charcoal. Loopy hands put on the bold slots
   (lichtenberg, trail_slime, hokusai, fly_fru, levitation, mantis) turn into
   **letter shapes** ("b", "p", "S", "3"). I kept them out, per the legibility
   rule.
3. **Barbs.** The first runs had repeated V reversals (Ian's "staggered barbed
   lines"). Two fixes removed most of them: a corner cost (0.4 per corner
   > 50°) and dropping cues that land closer than 20 mm together. A higher
   corner cost turned every line into soft closed blobs. Those read as
   outlines of things, so I backed off.
4. **Centred cluster → open sheet.** At ×6 the performance kept the source's
   compact cluster. It was a pleasant vignette, not a charcoal. Entries and
   exits from the sheet's edge (`edge_p` 1.0) opened the whole sheet. With a
   soft blank reserved lower left, the drawing went to one side and the empty
   half became part of it. This was the turn where it came alive.
5. **Doubling.** The first version was a smoothed copy with a sine offset. It
   read as a wavering pencil line beside the stroke: neither hatching nor
   charcoal. Split-bumps (on the line, parting in 1–3 places, ≤ 8 mm) read as
   two passes. They cross and open into lenses (see close-up). A tangle of
   cues in the source used to make tight N-zigzags; cue thinning fixed it.
6. **Pens.** Three pens (1.6 / 0.8 / 0.45) were too even. Two pens (2.2 /
   0.5) give the charcoal contrast: the bold line is where the dancer's hand
   was slowest.
7. **Ensemble.** Bold `trail_miner` with a hairline `fly_fru` works like the
   bold-plus-wire of *Conduction 11*. But the fly's small loops read as beads
   or letters, and without edge entries it stays a cluster. It is kept as a
   technique, not as a review image.
8. **Tree (D4): dud.** See below.

## The images (in order)

1. `oehlen_conduct-piece.jpg` — **the finished piece**, seed 3323. A few long
   lines. The blank is lower left, below one long hairline arc that enters
   from the left edge. Two bold passes (the slow stretches) open into lenses
   and rejoin. The conductor sits small in its corner.
2. `oehlen_conduct-process.jpg` — six panels: the reference (#12 → #15,
   credited thumbnails); the conductor enlarged, with its cues; the score (cue
   points ×6, chords, the reserved blank); one pass; second passes in red over
   the first in grey; the piece.
3. `oehlen_conduct-performances.jpg` — one score, four performances (seeds
   3323 / 3322 / 3333 / 3334). The shared skeleton is the conduction: the bold
   pair in the middle, the arc to the right, the long entry. Seed 3334 has a
   moment where two bold passes run parallel for about 25 mm. The risk is
   reduced, not gone.
4. `oehlen_conduct-closeup.jpg` — 120 × 135 mm of the piece at 14 px/mm.
   Second passes split and rejoin. Pen changes show as round pen ends where a
   bold run meets a hairline.
5. `oehlen_conduct-dud-tree.jpg` — **dud**, the tree program on 145 × 218 mm.
   Branches fire at the source's stops and bursts and the lines narrow from
   the midpoint, but the first word is "twig", or "crack". The branches are
   short straight sticks off one spine, i.e. barbed. What it taught me: the
   rule-set works (the narrowing reads), but *branching* as the event is
   itself the cliché. The narrowing rule is worth carrying to another voice;
   the branching is not.

Every image has its recipe beside it (`*.recipe.json`). To rebuild all five:
`.local/gesture/.venv/bin/python tools/gesture/experiments/oehlen_conduct.py review`.

## My honest read

- **Would Ian keep it?** I think he would keep the piece, or at least the
  method. It hits several things he has asked for:
  - bold single gestures;
  - kinematics driving something else (a dancer's hand conducts and never
    draws its own shape);
  - a drawing beside its source (the conductor in the corner, and the process
    and performances sheets as "measurement");
  - contiguous lines with no hatching and no dots.
- **Weak points:**
  - The family resemblance to Oehlen's charcoals is strong, because the
    procedure is strong (few lines, one side, blank half). A viewer may read
    style, not procedure.
  - In the piece alone, the conductor/performance relation is invisible. You
    need image 2 or 3 to see it.
  - The bold-to-hairline pen changes are abrupt. That is honest to the
    plotter, but it is not charcoal pressure.
  - Seed variation is narrow by design (same score). Another conductor
    (another dance, other seconds) is the real variable.
- **Strongest next step:** a series. One conductor per sheet, or the same
  score played by several hands on several sheets.

## Could not do / notes

- No downloads, no plotting, no app.
- The `return` cue (the hand revisiting its own place → retrace there) was
  sketched, then removed: it never fired usefully at these window lengths.
- `tools/gesture/tests/test_kit.py` passes (41).

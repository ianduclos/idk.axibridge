# oehlen_found — D1 found ground, negotiated line + D2 cover cuts (round 12, 2026-10-17)

Ian's seed: "Albert Oehlen works on paper, go deep." Directions D1 and D2 of
`oehlen-research-2026-10-17.md`. Images only, nothing plotted, nothing downloaded.

**Outcome.** The piece is one bold late gesture on a portrait 205 × 297 mm sheet.
It is drawn over found printed matter: the project's own measurement plate, plus
a far view of a real Amazon stem. The gesture rides the river's tight zigzag and
the torn edge of a cut strip, then leaves both. The cut strip interrupts the
river and the plate rows. A "plastic sheet" re-inks the plate's drawing from blue
to green. That last move transfers the clearest. The cut is the weakest.

## Procedure (what transferred from the works on paper)

Looked at all 29 sheets; the moves taken are procedures, never forms.

- **Found layer** (2009–2013 collage-drawings; Krebber leaf 11):
  - printed matter pasted first, in a thin coloured pen (Flexoki blue, 0.3 mm):
    - the plate: a `measure_next` taxonomy plate of a `hokusai` line;
    - the river: `oehlen_found_river`, GRWL SB19 seg 1, 2400 channel widths
      long. That is the far view Ian allowed: a tight meander band, principal
      axis laid horizontal.
  - text (labels, index numbers) is never ridden. A cover cuts a whole word or
    none of it, so no stray glyph fragments are left.
- **Negotiation as events, not a field.** The line alternates log-normal *ignore*
  and *listen* windows. While listening, a found contour that is near and
  aligned takes the line:
  - it *rides* that contour, 0.9 mm beside it, so the blue stays visible;
  - it *leaves* at a tangent (Bézier bridge) and swims back to its own path.
    A ride ends before the line is carried more than 18 mm from its own path;
  - *grow*: a line can start from the end of a found contour. Two modes:
    moved rigidly onto it, or a bridge from it.
- **Covers** (pasted paper / white smear / the 2022 plastic sheet):
  - `cut`: everything beneath stops at the cover. Pieces under 4 mm are dropped;
  - `tint`: everything beneath is re-inked in another pen. This is the
    plastic sheet, and on a plotter it is just a pen change by region.
  - The late line is never cut. It may ride the covers' *undrawn* edges, so a
    torn edge shows only where the line traces it.
- **Frame**: 205 × 297 portrait, the size of Oehlen's 2013 sheet (29.7 × 20.5 cm).
  At 1:1, line density can be compared directly. The lower fifth is a reserved
  blank that only the gesture enters, as in the 2013 sheet's pasted white paper.

## What I tried (≈ 14 recipes, 9 sweeps, all in `.local/gesture/out/oehlen_found/`)

1. **v1–v2: plate and river, two made hands, covers searched by "most ink
   inside".** The covers were invisible: they swallowed whole passages and
   nothing stopped at their edges. The found layer read as wallpaper.
2. **v3–v5: composed covers.**
   - A sheet-wide bottom cover did not read either: too few lines reached its
     edge.
   - A narrow vertical cut strip did read, *if* it crossed the river band.
   - A strip placed over the plate's own column gutter reads as nothing (v5, v6).
3. **v4: the tint cover** was the first legible cover. Blue and black both turn
   green inside a region, and it needs no outline.
4. **Made hands swept** (ingres, dancer_madeline, mime_mantis, trail_grazer,
   meander69, aaron, river_bend, dance_levitation):
   - `trail_miner` and `meander69` give straight barbed chords (Ian's dislike);
   - `river_bend` is the calmest. Two black voices of one weight read as
     clutter.
5. **v9–v10: the turn.** No made layer, only *one bold late gesture*
   (`dance_thrusting`, 0.9 mm). Seeds swept: 3907, 4441, 5153, 8317. 4441 has
   the best gesture: it rises to the top right through the plate rows and
   falls in loops into the blank.
6. **Grow on the late line (v10g, v10h).**
   - The rigid move squashes the gesture into the middle.
   - The bridge mode makes a stiff 62 mm bar, or (flipped) loses the river ride.
   - Kept it off for the piece.
   - Ride beside (0.9 mm) vs on (0): beside wins. With 0 the blue vanishes
     under the black and the borrowing is invisible.
7. **v11: a second thin made voice** added clutter in every hand tried. Dropped.

Piece numbers:
- The late line is 1374 mm long with 6 rides, 11 % of its length riding:
  - river or plate: 12, 61, 47, 34 and 33 mm;
  - the cut strip's torn edge: 56 mm.
- The late line crosses the cut cover for 40 mm and the tint cover for 270 mm.
- 116 found marks stay blue, 124 are green.
- Same recipe ⇒ same inks across processes (checked with PYTHONHASHSEED 1 / 77).

## Images (in order; recipe JSON beside each)

1. `oehlen_found-1-piece.jpg`: **the piece** (seed 4441, recipe `v10`).
2. `oehlen_found-2-process.jpg`: the procedure in four recipes:
   - pasted;
   - covered (torn strip cut + plastic tint);
   - the gesture as the hand drew it;
   - negotiated.
   Panels 3 → 4 show exactly where the line was taken.
3. `oehlen_found-3-closeup.jpg`: 156 × 110 mm of the piece:
   - the river ridden beside, then left;
   - the torn edge ridden;
   - the plastic sheet's corner, where blue becomes green.
4. `oehlen_found-4-dud.jpg`: **dud** v2. Covers placed by search, plus two
   made voices of one character. Left plain; right with the covers and rides
   drawn in. It taught me two things:
   - covers must be composed across a band, not searched into busy passages;
   - one bold line beats two equal ones.
5. `oehlen_found-5-reference.jpg`: the works that taught the moves, credited
   thumbnails:
   - Untitled 2013 (pasted pieces cut, a line crossing the blank);
   - Untitled 2022 (the plastic sheet);
   - the piece beside them, so Ian can see the procedure transfer.

## Honest read

- **Would Ian keep it?** Probably as a procedure, maybe as a drawing.
  - *For it:* it is the drawing-beside-its-measurement he loves, with a bold
    single gesture over it. The plate reads as found printed matter, not
    wallpaper, because the gesture visibly takes from it in the river ride.
    The tint is a new, plotter-native move.
  - *Against it:* the cut strip is subtle at full-sheet size. It reads in the
    close-up and the process strip, less in the piece. The gesture also has
    two small hooks where rides end abruptly, at the river exit and the
    bottom-left knot. "Grow out of" is only in the code and tests, not in the
    piece.
- **The research's risk.** Wallpaper and stubs were real in v1–v6. The fixes:
  - one gesture instead of a layer of made lines;
  - composed covers across the river band;
  - printed text cut whole, never into fragments.

## Files

- `tools/gesture/gesture/kit/arrangers_oehlen_found.py`:
  - arranger `oehlen_found`;
  - voice `oehlen_found_river` (reads the local GRWL corpus; nothing frozen);
  - renderer `oehlen_found_ink`;
  - `render_colour` / `save` colour previews.
- `tools/gesture/experiments/oehlen_found.py`:
  - recipes `v1`…`v10`;
  - `sweep`, `debug`;
  - `final` rebuilds the five review images:
    `.local/gesture/.venv/bin/python tools/gesture/experiments/oehlen_found.py final`.
- `tools/gesture/tests/test_kit_oehlen_found.py`: 9 tests, about 3 s.

**Not done.** The river voice needs `.local/gesture/corpus/earth/grwl-vec-SB19`.
A study in the app would need that stretch frozen into the library first.

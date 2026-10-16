# Composition learned from whole sheets (round 8, 2026-10-16)

Library `gesture/sheetcomp.py`, experiment `experiments/sheet_composition.py`
(`measure`, `space`, `match`, `tune`, `limb`), tests `tests/test_sheetcomp.py`
(10, < 1 s). Outputs in `.local/gesture/out/sheet_composition/`.

## What was measured

All 189 sheets go through one pipeline: an ink mask at 1024 px on the long
side. The mask joins the extractor's line binarisation with a global
solid-ink threshold, because the line binariser hollows out large blots and
would have erased every mass. Each mask gets a 20-number profile, all
dimensionless (lengths are fractions of sqrt(area)):

- coverage;
- gliding-box lacunarity at 1/32, 1/16, 1/8 and 1/4 of the side;
- share of empty cells on a 16-cell grid;
- largest empty disk;
- share of the sheet more than 0.05 side from any ink;
- centre of mass and spread;
- ink in the outer 10 % band relative to that band's area;
- islands after closing gaps of 1 % and 3 %, and the largest island's share;
- orientation coherence;
- line width and mass share (relative to the sheet's own line);
- skeleton ends and junctions per unit length.

The corpora: Matisse 31, Hokusai 27, Ingres 34, Marden 12, Cohen 8,
Henry/Molnar/Nake/Noll 2–3 each, mashq 4, shikasta 5, other calligraphy 22,
and Bulaq print pages 20. Our sheets: the 5 r7 previews, 6 v2 candidates
and Ian's 2024 reference. Kelly (one faint pencil sheet) binarises empty
and is dropped. The r6 jpgs measured empty and were not used.

## Where our sheets sit (`sheet_composition-space.jpg`)

PC1 (44 %) is lacunarity, i.e. clustered vs all-over. Calligraphy, print and
**Ian's reference** sit at the all-over end. The figure drawings (Ingres,
Matisse) sit at the clustered end. PC2 is spread, margin and islands.
**Every one of our sheets sits at the bottom of PC2**, and that is the
finding.

**Density is not what is off.** The r7 sheet's lacunarity and empty share
are at the corpus median at every scale. The two things that are off are
connectivity and margin:

| stat | r7 | Hokusai | Matisse | Marden | mashq | Ian ref |
|---|---|---|---|---|---|---|
| islands (log count, 1 % gaps) | **0.69** (2) | 2.94 (19) | 3.22 (25) | 2.81 (17) | 4.52 (92) | 2.48 (12) |
| free ends per side-length of line | **6.3** | 20 | 29 | 22 | 44 | 15 |
| ink in outer band ÷ area share | **0.14** | 0.31 | 0.36 | 0.60 | 0.73 | 0.67 |
| lacunarity at 1/4 side | 0.15 | 0.23 | 0.27 | 0.16 | 0.17 | 0.08 |
| empty 16-grid cells | 0.31 | 0.36 | 0.43 | 0.33 | 0.10 | 0.06 |

The r7 sheet is **one welded net**: everything joins, almost no line ends
freely, and nothing reaches the margin. The corpora have 12 to 90 separate
units each. Ian's reference is the odd one: dense and all-over like a page
of text, with many separate units, and it runs into the margins. So "control
the density" reads, from the numbers, as "break the one net into units and
let them touch the edge". Spreading the same net more or less thickly
would not get there.

## The controller (`sheet_composition-matched.jpg`; grid version `-match.jpg`)

1. **Grid plus post-selection** (`match`): 21 candidates per target. The
   knobs are structure (r7 tree; tree grown inside the target's layout via
   an envelope; grammar lines), how much of the target's own layout map
   (16 × 12 cells) to clear, and a field modulated so lines thin to wire
   before the void. Selection beats the r7 recipe for every target:
   - Marden: 0.75 → 0.60
   - mashq: 1.11 → 0.73
   - Hokusai: 0.78 → 0.43
   - Matisse: 0.81 → 0.31

   (RMS robust z over 15 layout statistics.) But the median controlled
   candidate is *worse* than the baseline, so the selection does the work.
2. **Feedback tuning** (`tune`): 30 cheap steps per base, each step one
   post-op pass plus a profile in about 1 s. The knobs are clearing, zoom
   (push ink into the margin) and junction gaps (lift the pen where lines
   meet). Gains are small, 0.00–0.10. Gaps help mashq and Hokusai (islands
   go up), and zoom brings the margin closer.

**Failure, stated plainly:** the four "composed like X" winners are
**the same sheet**: grammar lines, seed 3, cleared slightly differently.
The 15 global numbers do not tell Marden's columns from a Hokusai figure.
A generic all-over sheet of separate lines satisfies all four targets. The
layout transplant at 16 cells hardly shows, because the grammar sheet is
already even and the clearing takes little away. The useful outcome is
diagnostic: **the structure decides the composition class** (tree net
≈ 0.75–1.1, separate grammar lines ≈ 0.3–0.7), and post-processing
fine-tunes within it. A real "composed like Marden" needs a structure
that makes **units** (columns, rows, figures), not a better objective.

## Limb: emptiness as an active regime (`sheet_composition-limb.jpg`)

Each void is cut from another sheet's ink: a Hokusai page's figures, a mashq
page's rows and a Marden net become holes in a dense three-trunk tree grown
around them. There are two edge behaviours:

- **halo**: lines thin to wire as they approach the void and stop.
- **pool**: the regime field rises to mass in a band just outside the void
  edge, so lines swell into blots as they arrive and are cut there.

**Pool held.** The void is drawn by the rim of what meets it: a ring of
pooled terminals, beads and fat strokes, and the empty shape reads as a
deliberate form. Marden-as-holes pool s5 is the strongest. Halo voids read
as erased, more like a stencil. Measured: void share 0.23–0.38, islands
at 3 % gaps up from 1 to 3–8, so cutting by a void is the one op that clearly breaks
the net.

Weak points:

- The voids are smoothed 24-cell blobs. The source silhouettes are not
  recognisable, which is fine for near-associations but generic.
- A central void plus a dense rim tends towards a passe-partout frame.

## Surprises

- Siyah mashq sheets have mass share 0.43, as high as our regime sheets:
  the overwritten practice sheet is the corpus's "mass regime".
- Ian's reference is nearest to print pages and mashq, not to any drawing.

## Next limb

A **units** structure: k separate small structures placed on the target
layout's peaks, at varied scales, some touching the edge. Islands and margin
are the two stats nothing else moves. Then pool voids between the units, so
that the gaps between units become shapes.

## Proposed changes to existing modules (not made)

1. `topology.generate_structure(kind="oehlen_tree", envelope=...)`: pass an
   envelope through to `_Sheet` (I wrap `_Sheet.__init__` for the call in
   `sheetcomp.guided_tree`).
2. `regime_field.compose(post=callable)`: a hook before clipping, so
   clear/gap/zoom can keep group and kind tags without rebuilding the
   Composition.
3. `extract._binarize`: optionally union a global solid-ink threshold
   (`sheetcomp.solid_ink`). Line-tuned binarisation hollows large blots,
   which matters for any mass statistics.

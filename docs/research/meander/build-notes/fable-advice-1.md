# Fable advice 1: why the bundle reads as an outline, and the minimum fix

Read: `t_meander.js` in full, `dev-sheet-1.png`, `dev-close-1.png`, `dev.json`, Ian's sketch, `v5-seeds.png`, plus `t_hand.js` (hands) and the `Sheet` class. I also probed the live geometry (`res.T._geo`, seeds 7/3/34, defaults) from a scratchpad script; numbers below are from that run, not from reading formulas.

## 1. Diagnosis: the code builds a pair, not a band

Measured on the trunk of seeds 7 / 3 / 34:

| quantity | value |
|---|---|
| length with **exactly 2** strands active | 45 % / 51 % / 65 % |
| gap of that pair, p50 | 1.54 / 1.54 / 1.55 mm |
| when ≥ 3 strands are active, widest gap sits at the convex edge | 100 % / 100 % / 100 % |
| sibling gaps < 0.45 mm (merged) · 1.5–3 mm | 49 % · 25 % / 35 % · 36 % / 20 % · 48 % |
| k=0 (convex) strand: longest unbroken run | 425 / 448 / 263 mm = the whole channel |
| S p10 / p50 / p90 | 1.4 / 2.2 / 6.5 · 1.7 / 2.3 / 7.2 · 1.7 / 2.0 / 6.9 |

Four formulas interact to produce this, in causal order:

1. **`K = 1 + floor(S / 1.2)` (line 299) with S median ≈ 2.2** puts the trunk in K = 2 for 46–60 % of its length. Two parallel lines are an outline at *any* gap from 0.6 to ~3 mm; there is no gap value that makes a pair read as width. The brief's dead zone (0.6–1.3) was stated per gap; it is really a property of pairs.
2. **`frac` (line 303)** places every fan strand at 0.10–1.0 of `S/2` on the concave side while k=0 sits at `−S/2` (line 310). So the convex→first-fan gap is ≈ 0.55·S and the fan strands are packed into ≈ 0.45·S. At S = 3 (K = 3): offsets −1.5, +0.24, +0.52 → gaps 1.74 and 0.28. The band is half empty, always on the convex side (the 100 % row).
3. **The quantizer (line 325)** then merges the 0.28 (→ 0.4, a fat line) and, wherever a pair lands in 0.45–1.5, pushes it to 1.55. That is where the 1.54 mm p50 comes from: the quantizer manufactures the railway it was meant to prevent. The ink between the two lines is gone, so nothing reads as volume.
4. **`act[k] = K > k` plus stagger 3–12 mm (lines 311, 345)** keeps k=0 continuous for the whole channel and lets k≥1 run as long as `S > 1.2·k` holds, i.e. tens of centimetres. A continuous smooth line at the outer edge of a bend *is* the calligraphic edge; the fan inside it becomes decoration on that edge (the "tongue").

Two smaller contributors: the per-strand drift `0.2·S·own_k(s/25)` (line 309) is ±0.6 mm at S = 3, independent per strand, so anything spaced under ~1 mm would cross randomly; and the A term `(0.45 + 0.55·A)` (line 296) spans only 0.53–0.92 at `activity 0.7`, so S barely follows the field (that is half of flag N).

## 2. Minimum change set for width (prioritised; A1–A3 are the fix, A4–A6 make it hold)

**A1. Forbid K = 2.**
`K = S < 1.6 ? 1 : clamp(1 + round(S / 0.9), 3, 8)`. Target spacing 0.9 mm (0.5 mm white between 0.4 mm lines): dense enough to read as tone, open enough to count. A channel is either one line or a band of ≥ 3. Cap `Smax` at 9 (trunk) / 5.5 (minor) so eight strands never spread beyond ~1.3 mm mean spacing.

**A2. Fill the band; heavy edge concave, ragged edge convex.** Replace `frac` and line 310 with positions across the *whole* band, denser toward the concave edge, using the local K:

```
u_k(i) = 1 − 2·((k + 0.5) / K[i])^1.5        // k=0 ≈ concave edge, k=K−1 ≈ convex edge
off[k][i] = drift + mine + b[i]·S[i]/2·u_k(i)
```

k = 0 becomes the concave-side core (hand `firm`, always active); higher k walk toward the convex edge and are dropped first as S falls. Wherever `!act[k][i]`, set `off[k][i] = off[k−1][i]` (the inward neighbour), then `boxFilter(off[k], 20)` per strand. Two things fall out for free: K changing by one re-spaces the band by ≤ S/(K(K−1)) ≈ 0.3 mm, invisible after the 10 mm low-pass; and every strand end peels off from / rejoins its neighbour over ~10 mm instead of stopping. Ends merging inward is what makes the convex edge read as the mark thinning, not as a second outline.

**A3. Remove the quantizer's spread branch.** Line 325: delete the `1.55 − g` push entirely; keep only `if (g < 0.45) shift += 0.3 − g` (a true merge, lines overlap at pen width) or delete the block and let S → 0.3 do the merging. Spacing is now set by construction, and the push is the direct cause of the 1.54 mm pairs.

**A4. Make S actually swell and taper.** Line 296:
`(0.3 + 1.2·smooth(vlo, vhi, vl))` → `1.5·pow(smooth(vlo, vhi, vl), 1.5)`, and `(0.45 + 0.55·A)` → `(0.15 + 0.85·A·A)`. Expected trunk: ~40 % of length at K = 1, ~25 % at K ≥ 5, p90/p10 ≥ 6. Long single lines alternating with dense masses is both the width illusion and the density contrast.

**A5. Break every strand k ≥ 1 into pieces.** Piece length `(30 + 40·rng())·(1 − 0.07·k)` mm, gaps `3 + 6·rng()` mm, redraw once if a break lands within 8 mm (in s) of a break on strand k−1. The k = 0 core stays continuous. With A2 each piece end merges inward automatically. This kills the continuous outer edge (the 425 mm run).

**A6. Tame per-strand wobble.** Line 309: `0.2·S·own_k(s/25)` → `(0.03 + 0.04·k)·S·shared2(s/25)` with one extra shared noise `shared2`; keep `0.25·loose.A·own_k(s/10)` (≈ ±0.1 mm) as the only independent term. The band breathes as one, outer strands slightly more.

Wobble in `handLine` is already small (strand hand A ≈ 0.13, firm 0.18) and needs no change.

## 3. Crescents / flourish (2)

A2 inverts the tongue by construction: the heavy side is inside the bend and the outer edge dissolves, so a bend stops reading as a drawn arc with decoration inside. What A does not touch is eight channels each drawn as one bend with the same treatment. **One change:** only the two minors with highest mean `A` along their centreline get `S0 = 4`; the rest get `S0 = 1.4` (so K = 1 nearly everywhere: long single lines between things, the sketch's open lines). If crescents still repeat after that, `channels` default 8 → 5; do not touch the geometry first.

## 4. Density contrast (4)

A4 alone should clear N (a 10 mm cell under eight strands holds ~80 mm of ink versus ~10 mm under one line). If it does not: history keep-probability (line 472) `prm.history·(0.3 + 0.7·A)` → `prm.history·1.4·A·A`, so traces gather where bundles already are. **Regardless, gate traces off single-line reaches**: in `keep` (line 477) also require `g.S[bi] ≥ 1.6`. A trace 1–3 mm inside a K = 1 reach is a pair, i.e. another railway, and it is part of the nested-arc reading in (3).

## 5. Metrics to change with it

- **R** (line 337): count length where *exactly two* strands are active within 4 mm and their gap is 0.6–3.0 mm; flag above 10 %. The current 0.6–1.3 window passed 1.54 mm pairs.
- **P**: exclude channels under 60 mm (seed 3's 22 mm minor is what fires it now).
- **New E-edge**: longest continuous run of the convex-most active strand > 60 mm → flag. This is the one that would have caught this sheet.

## 6. What the brief got wrong

Three of the four causes are in my §1 and §3: the dead zone stated per gap rather than per pair; "one firm strand holds the convex side"; and `u_k = lerp(r_k, |r_k|, b)`, which compresses the fan into the concave half and leaves the convex line alone. The lead implemented what was written. A2 is the correction: firm core on the concave side, ragged edge on the convex side, band filled edge to edge.

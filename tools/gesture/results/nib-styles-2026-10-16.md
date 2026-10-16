# Nib styles as options — 2026-10-16

Ian: "b c and e as options, with option to combine." Nothing changes by
default; the outline ribbon (a) stays the default until Ian picks.

## How to ask for one

`regime_field.compose(..., nib_style=SPEC)` (or `penrender.nib_style(SPEC)`
as a `regime.render(nib_renderer=…)` hook):

| spec | ink |
|---|---|
| `None` / `"a"` | outline (default) |
| `"b"`, `"b+"` | inset fill, narrow / full |
| `"c"` | passes along the stroke |
| `"e"` | nib-point traces |
| `["c", "e"]`, `["b+", "c"]`, `["b+", "c", "e"]` | combination: at most one inset fill + any pass families; outline drawn once |
| `"c+e"`, `"b++c"` | same as a string (`+` separates parts, so `"b+c"` = narrow b + c) |
| `{"c": .5, "e": .5}` | per-mark mix, deterministic from (seed, mark) |

CLI: `python -m experiments.regime_compose polish --papers A4 --nibs a,b+,c,e,c+e --pen 0.4`.

## What changed besides the option

1. The nib style changes only the ink. Echoes and drips used to grow from the
   rendered rings, so a style moved them; they now grow from the plain render
   (test: `test_nib_style_changes_ink_not_composition`).
2. **compose was not reproducible across processes.** A line's dominant hand
   was `max(set(hs), key=hs.count)`; ties went by set order, which is seeded
   per process (PYTHONHASHSEED). The same seed gave different sheets per run
   (10 vs 11 signs, different bbox). Ties now go to the first run. Every
   earlier polished sheet was one draw of several; the A4 candidates in
   `.local/gesture/out/plot_candidates_r7/` are re-rendered.

## Results (simulated ink, 0.4 mm fineliner)

Strip (`nib-strip-combos-0.4mm.jpg`, close-up `…-closeup.jpg`): every style and
combination reads as solid ink in simulation. The simulator cannot show
pass texture, drag or wetness — that is what paper would show. Strip times:
b+ 33 s, c 37 s, e 38 s, mix 40 s, b++c 50 s, b++e 51 s, c+e 57 s, b++c+e 70 s.

A4 Strahler sheet (`nib-variants-sheets.jpg`, `nib-variants-detail.jpg`),
app motion model:

| style | lifts | min |
|---|---|---|
| a | 224 | 5.2 |
| b+ | 372 | 7.0 |
| c | 704 | 9.2 |
| e | 517 | 8.7 |
| c+e | 613 | 10.8 |

c's lift count is the cost to watch: short lanes on short ribbons.

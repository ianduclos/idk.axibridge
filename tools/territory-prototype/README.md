# Territory prototype sources (web artifact)

These are the plain-JS sources behind the private web artifacts:
- *Territory*: https://claude.ai/artifact/Bawx12VN4uRgWR2wU2Lso3
- *Cores and Skins* (v1): https://claude.ai/artifact/LPvKv1yKahSiEKVZv2Gf8M

It is not part of the `axibridge/` package, and nothing here runs in the app.

## Build

The engine is the concatenation of the parts in this order: head, flood, body, hand, forms, graph, v5, meander. The page is the template with the engine inlined. `./build.sh` does both; the outputs (`territory-engine.js`, `territory.html`) are gitignored. The folder has its own `package.json` (`"type":"commonjs"`) because the repo root is ESM.

```bash
tools/territory-prototype/build.sh
```

Then publish `territory.html` to the same artifact URL, passing the URL as `url` from a new session.

Contact sheets:
- `node sheet.js <config.json> out.html` renders the sheet. The configs have the shape `{title, cols, w, prm, cells:[{id, random|example, order, prm}]}`.
- `../../.venv/bin/python shoot.py out.html out.png 2000` screenshots it.
- `cfg.flags: true` adds the meander kill-table flags and ink length to captions (lead's eyes only; never on review sheets).
- `node close.js <config.json> out.html ID:x,y,w,h | ID:auto …` renders close views at the plotted pen width; `auto` picks the 100 × 70 mm window with the most ink.
- `node smoke_meander.js [seeds…]` checks determinism and timing and prints each recipe's metrics.

## Parts

| File | Contents |
|---|---|
| `t_head.js` | Grid, RNG and noise, `Sheet` occupancy (lineage-aware `related`), `distField`, `walkLine` helpers, `isolines` |
| `t_body.js` | `Territory`: camps, log-sum-exp fields, borders and edges, history snapshots, v3 volume pass, `runTerritory` |
| `t_hand.js` | The hand: Catmull-Rom, gated sway, overshoot, lift, two hands |
| `t_forms.js` | v4 bodies: Poisson inflation, tubes, wrap/wound/growth |
| `t_graph.js` | Contour graph |
| `t_v5.js` | v5 searching lines |
| `t_meander.js` | Meander (render `meander`): migration + neck editor, strand bands for width, event-dated history, searching register. Design: `docs/research/meander/synthesis-brief.md` and `build-notes/` |

History and verdicts are in `shots/territory-v2-0929` … `shots/territory-v5-0929` and `docs/reviews/territory-v2-0929-sonnet.md`.

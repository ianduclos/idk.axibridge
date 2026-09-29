# Territory prototype sources (web artifact)

These are the plain-JS sources behind the private web artifacts:
- *Territory*: https://claude.ai/artifact/Bawx12VN4uRgWR2wU2Lso3
- *Cores and Skins* (v1): https://claude.ai/artifact/LPvKv1yKahSiEKVZv2Gf8M

It is not part of the `axibridge/` package, and nothing here runs in the app.

## Build

The engine is the concatenation of the parts in this order: head, flood, body, hand, forms, graph, v5. The page is the template with the engine inlined.

```bash
cd tools/territory-prototype
cat t_head.js t_flood.js t_body.js t_hand.js t_forms.js t_graph.js t_v5.js > territory-engine.js
python3 -c "p=open('territory-page.html').read(); e=open('territory-engine.js').read(); open('territory.html','w').write(p.replace('/*ENGINE*/',e))"
```

Then publish `territory.html` to the same artifact URL, passing the URL as `url` from a new session.

Contact sheets:
- `node sheet.js <config.json> out.html` renders the sheet. The configs have the shape `{title, cols, w, prm, cells:[{id, random|example, order, prm}]}`.
- `../../.venv/bin/python shoot.py out.html out.png 2000` screenshots it.

## Parts

| File | Contents |
|---|---|
| `t_head.js` | Grid, RNG and noise, `Sheet` occupancy (lineage-aware `related`), `distField`, `walkLine` helpers, `isolines` |
| `t_body.js` | `Territory`: camps, log-sum-exp fields, borders and edges, history snapshots, v3 volume pass, `runTerritory` |
| `t_hand.js` | The hand: Catmull-Rom, gated sway, overshoot, lift, two hands |
| `t_forms.js` | v4 bodies: Poisson inflation, tubes, wrap/wound/growth |
| `t_graph.js` | Contour graph |
| `t_v5.js` | v5 searching lines |

History and verdicts are in `shots/territory-v2-0929` … `shots/territory-v5-0929` and `docs/reviews/territory-v2-0929-sonnet.md`.

# Territory v3: volume from repeated lines (29 September 2026)

Ian's brief: "make many traces to create some sort of illusion of volume while remaining mostly line based … push further into the abstraction", in the spirit of linedraw v3's form shading.

Artifact: https://claude.ai/artifact/Bawx12VN4uRgWR2wU2Lso3 (version 2, "Volume pass"; private).

## Mechanism

The final field is read as a lit landscape. Height is the winning camp's influence, so every territory is a hill and every border a valley. A light (azimuth −135°, elevation 35°) and a relief factor give a darkness map. Volume comes only from lines:

- **Restated edges.** Each border or edge is retraced up to *traces* times on its shadow side, stepping inward. The count follows darkness, so traces taper where light returns. Gaps are uneven and ends staggered. The walker stops at ink instead of swerving.
- **Form hatch.** Strokes start on steep, dark slopes and follow a base angle that bends along the isophotes, so they wrap the hill. Clearance around existing ink keeps white gaps, as in linedraw v3's Light form.
- **Per-territory appetite.** Each territory draws a shading appetite of 0, 0.55, 1 or 1.6, so some stay bare. Low-frequency noise clumps hatch density and stretches stroke length.
- **Arrival order** (drawn / reversed / largest first / smallest first) is now a control. Ian found that reversal produced interesting results, and the reviewer confirmed order changes the base masses entirely (V against U).

## Sheets

These are Sonnet round 2, blind. The review is appended to `docs/reviews/territory-v2-0929-sonnet.md` as "Round 2 — volume".

R: lines only. S: restate. T: hatch. U: both, reversed. V: both, as drawn. The recipes are in `recipes.json`.

`sheet-W.png` comes after the round-2 fixes: appetite per territory, clumped hatch, and traces defaulting to 3. It has not been reviewed.

## Status

Screens only, with no plot. The reviewer notes that hatch density will read heavier at pen width, so paper should decide the density. Ian has not judged v3 yet.

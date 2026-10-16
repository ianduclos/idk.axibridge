# Hand Drift bench — plan (2026-10-17)

Ian, after round 8: the hybrid/drift thread is "the closest to the idea I had in
mind when I first started this bench … I would make this a bench as it is",
with regimes switchable in and out. Decisions (questions UI, 2026-10-17):
**an AxiBridge bench**; first-version switches = **drift method including the
"failure"**, **regimes on/off + source**, **several lines per draw**. Signs are
out of v1.

Source of truth for the behaviour: `tools/gesture/gesture/hybrid.py`
(`drift_line`, `HybridGrammar`), `tools/gesture/results/hybrid_hands-2026-10-16.md`,
images `results/hybrid_hands-drift*.jpg`; regimes from `gesture/regime.py`,
nib ink from `gesture/penrender.py` (`nib_style`), timing from
`gesture/gesture_timing.py`. Review record: `results/round8-review-2026-10-17.md`.

## Shape

1. **Frozen engine inside the app** — `axibridge/sources/_hand_drift/`: a
   vendored, frozen copy of exactly the research code the generator needs
   (grammar + clothoid + curvature + core + hybrid drift + regime + penrender
   nib styles + the timing→regime mapping), trimmed to what is used, with a
   header naming the research commit it was frozen from. Research code keeps
   evolving in `tools/gesture/`; the app's output never changes underneath a
   kept layer (animation stability contract: equal params ⇒ equal geometry).
   Dependencies: numpy, scipy, shapely only (all in the app venv).
2. **Frozen hands** — `axibridge/sources/_hand_drift/hands/`: matisse,
   hokusai, ingres (grammar v7), shikasta, nastaliq, marden, lichtenberg,
   bubble (round-8 hybrid grammars). Pruned/compressed to a committed budget
   of about 2 MB total, with provenance per hand (training sheets). Arabic
   hands come only from generative-allowed sheets (`meta.json`: shikasta
   wc-12/13/15; nasta'liq exercise sheets) — never Qur'anic/devotional sources.
   Check that pruning doesn't change the drift's character (same seeds,
   before/after sheet).
3. **Frozen timing profiles** — a few dance tempo profiles (speed/stillness
   along normalised time) as small arrays, so the timing regime works without
   the 464 MB mocap corpus (and on the Pi).
4. **Source module** `sources/hand_drift.py` (`HandDriftSource`), label "Hand
   Drift", `library_bench = True`, `bench = {"adapter": "hand-drift",
   "version": 1, "modes": ["new", "resume"]}`, mm output fitted into a
   placement frame. Every numeric param bounded. Params (first version):
   - route: ordered hands (2–4 from the frozen set), plateau;
   - **blend**: `mixture` | `interp`;
   - **joins**: `smooth` (κ-continuous chunks) | `chain` — the chain-context
     continuation that throws straight runs and corners into the line (the
     "failure" Ian rated one of the best);
   - length (R), lines (1–8) with route per line: `same` | `rotate` | `shuffle`
     | `each` (each line keeps ONE hand whole, no drift — several distinct
     grammars side by side on one sheet; see below);
   - **regimes**: `off` (wire) | `timing` (profile enum) | `field` (a preset
     that works on bare lines); amount, nib width, mass width, nib angle;
   - ink: nib style `a` | `b+` | `c` | `e` | `c+e`; pen width mm;
   - seed.
5. **Bench adapter** `static/js/hand_drift_bench.js` registered as
   `hand-drift` v1 in `process.js`, modelled on the magnetic-field bench:
   schema form with the switches visible as toggles/segmented controls, live
   preview through the existing preview path (cancellation already handled),
   shared preset controls, Keep → a normal layer, Resume from a kept layer.
   No new API endpoints unless unavoidable (if one is added, the MCP freshness
   rules apply — see CLAUDE.md).
6. **Tests** — determinism (same params ⇒ same paths, including across
   `PYTHONHASHSEED` in a subprocess: round 7 found a hash-order bug in compose),
   bounds, every switch produces geometry, frozen hands load and carry
   provenance, Arabic provenance gate, timing/field/off regimes differ, and a
   UI acceptance test (bench opens, a switch changes the preview, Keep makes a
   layer) asserting what the user sees.
7. **Docs** — `docs/MODULES.md` (adapter list), CLAUDE.md "Where things live"
   row, ROADMAP entry, `tools/gesture/README.md` note that the app holds a
   frozen copy.

## Why `each` (Ian, 2026-10-17)

On his reference fragments, read together: "how different the grammars are,
but how they are interesting and coherent yet strange in themselves". The
point is the set — distinct grammars, each internally consistent and
unfamiliar, side by side without blending. Drift keeps grammars whole along
stretches of one line; `each` keeps them whole across lines. Never average
grammars into one.

## Not in v1

Signs, learned shapes, data-born fields (earth), dance structures, plotting
anything (Ian: research is judged from images).

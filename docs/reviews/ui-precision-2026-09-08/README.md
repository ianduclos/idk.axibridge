# UI precision evidence — 8 September 2026

This directory is a bounded before/after record for the approved whole-app
visual polish. It does not judge generator output. Every pair uses the same
fixed recipe, viewport and interaction state against a real isolated server.

Run a capture with the repository virtual environment:

```sh
.venv/bin/python docs/reviews/ui-precision-2026-09-08/capture.py \
  --label before --static /path/to/baseline/static
.venv/bin/python docs/reviews/ui-precision-2026-09-08/capture.py \
  --label after --static axibridge/static
```

The harness creates a temporary configuration directory, disables automatic
machine connection, selects a random local port, patches `frontend_dir()` to
the requested static tree, and closes the server in `finally`. It never uses
the running app, saved projects or hardware. See each capture's
`manifest.json` for fixtures, page errors, overflow, visible actions and frame
measurements.

Client randomness is reset before every document load with a fixed generator
for both `Math.random` and `crypto.getRandomValues`. Every scenario records its
full project sources (with generated layer IDs canonicalized by project order),
process recipe, geometry counts and SHA-256 geometry
hashes. After both captures, run `verify_pairs.py`; it fails unless all 28
before/after stable recipe and drawing-geometry records are exactly equal.
Live simulator progress, remaining time and carriage position are recorded
beside that stable evidence and intentionally excluded from equality.

The final hardware-free suite passed 1,290 tests, including 112 browser tests
and five new precision regressions; typecheck passed. One existing Starlette
deprecation warning remains. This harness verifies source directly. The built
frontend is covered by the application suite.

The final source-only run recorded 28 paired scenarios, no page exceptions and
no horizontal document overflow. The zoom-equivalent Second Reading and
Homeostat dialogs kept the modal, complete drawing frame and all rendered
actions reachable and hit-testable after scrolling. The direct CSS-zoom
approximation exposed a before-only modal overflow that is absent after the
polish, but still reports seven advanced Second Reading controls as unreachable;
the closer viewport/DPR equivalent passes. Console output is
retained verbatim: the final after run contains one request aborted by a
deliberate harness reload and the intentionally injected 503 preview response.
Simulator screenshots preserve live progress, position and remaining-time
readouts, which are deliberately time-dependent and need not show identical
percentages. Their fixed project recipe and `.layer` drawing geometry must
still match exactly.

Open [report.html](report.html) locally after both runs. Its pair controls use
only local HTML, CSS, JavaScript and images.

# Ribbon performance and drawing activity — 9 September 2026

The persistent canvas status strip now shows an indeterminate activity bar and
“Updating drawing…” during layer commits, resolved drawing refreshes and live
generator/effect previews. An elapsed-time readout appears after one second.
The prior drawing remains visible and controls remain usable. A 150 ms delay
avoids flicker on cheap edits; overlapping and nested operations each hold a
token, so an early completion cannot hide a later update. Finally blocks clear
activity on errors. Reduced-motion users get a static bar. This is activity,
not a fabricated percentage or backend phase report.

`loading-status.png` shows the built frontend during a deliberately held real
effect resolve. The browser regression verifies visibility and elapsed time,
two overlapping requests, one success, then one failure and error feedback.
The visual was inspected at the normal 1500×950 viewport; native acceptance
remains with Ian.

## Exact-preserving optimization

`silhouette` previously normalized the same spine again for every boundary
point, then scanned it in full. It now normalizes once and indexes its ordered
stations. Outward-rounded search bounds retain complete duplicate runs; the
original tolerance predicate, tie-breaking hint and interpolation arithmetic
remain. A focused regression compares against the literal original lookup with
exact equality, including repeated stations and floating-point boundary probes.
No point decimation, sampling changes, masks, profiles or strand counts changed.

`benchmark.py` loads the silhouette helper directly from prior commit `77785ce`
and alternates three complete `shape_layer` runs with the current helper, using
the same actual corner fixture and layer seed. It asserts exact `(points,
filled)` equality on all six results. Recorded medians in `benchmark.json`:
**4.147 s before → 2.953 s after (28.8% lower wall time)**. Timings are local and
workload-specific; browser painting, HTTP serialization and other effects are
outside this measurement. The integrated test suite ran concurrently, so these
are observed timings, not a guaranteed latency or isolated benchmark.

The early 21% estimate used a conservative reconstruction of the old lookup;
the recorded benchmark supersedes it by loading the actual committed function.
The preserved fractured fixture also matches exactly; the six original study
fixtures retain their 5.17e-14 mm maximum Hausdorff difference.

## Verification and delivery

Full suite: **1,371 passed, one intentional lifecycle skip**, one existing
Starlette deprecation warning. Typecheck and built-browser acceptance passed.
Backend reloaded with the drawing preserved in the distinct
`ribbon-performance-recovery-20260909-004404` project, then restored. Layer
manifest fields match before/after; live resolved points and fill flags match
the accepted `stable.json` drawing exactly (20 strands). Refresh the app window
to load the new frontend bundle. No push or hardware action.

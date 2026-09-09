# Expensive preview updates

Ian reported that editing during a complex Ribbon calculation kept the previous
elapsed count and asked to delete a layer while it was processing.

The status strip remains an indeterminate activity bar. Its elapsed time restarts
on edit intent and covers pending edits through the resulting drawing refresh.
Pending layer patches are coalesced, and obsolete responses cannot repaint the
canvas. Deletion drops the layer's pending slider commit and interrupts active
read-only rendering before taking the project lock.

The server uses cooperative cancellation in Ribbon, shared effect/tween stages,
geometry clipping, generator progress and estimation. Read-only resolved, effect,
plan, sheet and raster previews translate cancellation to HTTP 409 with
`detail.code == "render_cancelled"`. Plotting/export and source regeneration
transactions are not made cancellable. Existing geometry calculations and
parameter formats are unchanged. One native geometry/optimization call must
return before its following checkpoint can abort it.

A true percentage is deferred in ROADMAP.md: line counts do not predict mask,
union, clipping or planning cost. No fabricated progress fraction is shown.

## Verification

Full hardware-free suite: **1,423 passed, one intentional lifecycle skip**.
Typecheck/build passed. The final browser guards passed both focused acceptance
tests against the rebuilt frontend (11.61 s). One existing Starlette warning.

- Threaded API tests interrupt all five preview routes with a patch, single
  deletion and bulk deletion; check cache cleanup, fresh results and undo.
- An additional test interrupts the estimation phase after geometry finishes.
- Controller tests cover cancellation across threads, waiting mutations,
  exception cleanup and no-op behavior outside preview scopes.
- Browser tests exercise elapsed reset, obsolete response suppression and
  deletion of a pending debounced effect edit.
- Accepted Ribbon stable/ordered fixtures retain identical geometry.

Native interaction and paper output remain for Ian to check.

## Live reload

The backend was restarted and the three-layer Homeostat animation restored;
the saved/restored project manifests match, including effect/source parameters
and transforms. Recovery copy:
`/Users/ianduclos/AxidrawProjects/render-cancellation-recovery-20260909-022452`.
A subsequent full live render exceeded the 30-second client verification timeout;
its final appearance is unverified. Refresh the app window for the new JS.

# Whole-app visual precision pass — 8 September 2026

Approved directly by Ian after choosing whole application, precision instrument,
and finish-then-review. Baseline: `81ccade`. Retain Flexoki, offline Roboto Mono,
compact working density and the accepted Compose/bench layout. Only Venation,
Homeostat and Second Reading are exposed as working benches.

## Implementation

1. Shared 13px body/control, 12px labels/sections, 11px support and 14px dialog
   titles. Navigation retains uppercase; working sections use sentence case.
   Tabular numerical readouts and fixed status reservations reduce movement.
2. Shared spacing roles (4/8/12/16/24px), 30/24px regular/compact controls,
   3px corners, consistent existing SVG icon sizing and stroke. Numeric fields
   use a readable common width; placement and calibration use paired label/value
   grids. Boolean labels wrap within their available width.
3. Quiet section markers and reduced nested borders/shadows, restrained neutral
   controls, committing actions in blue, and neutral disabled primary/danger
   controls. Supporting Play/Continue actions no longer compete with Keep.
4. Visible 2px focus, short colour-only transitions and reduced-motion support.
   The status/transport strip wraps whole controls instead of splitting words.
5. Shared application/Compose rules consolidated into static/style.css;
   css/benches.css retains bench-specific layout. Obsolete overridden bench
   sizing removed. Popup height follows its actual available viewport so zoomed
   layouts can scroll to actions. The physical calibration ruler retains its
   true length within a local horizontal scroll container. Shared animation renders
   fit their full frame within a scrollable dialog, keeping exports reachable.

## Invariants

No public API, source recipe, persistence or generator changes. Existing control
IDs, event handlers, numeric bounds, selection/latch/undo and write semantics
remain. The same resolve and capture coordinates remain authoritative. No new
dependency, push, user app restart or hardware use.

## Evidence and acceptance

Application and regression checkpoint: `a3ac4cb`.

The full hardware-free suite passed 1,290 tests, including five new precision
regressions, with 112 browser checks included. Final results after the shared
render-dialog fit correction are recorded in the evidence README. Build/typecheck and source-only evidence checks accompany matched
before/after captures under ../reviews/ui-precision-2026-09-08/.

Desktop and compact coverage uses 1440x1000, 1100x750, 900x650 and 700x650.
Enlargement is checked as an explicitly labelled 2x CSS zoom approximation plus
720x450 CSS viewport at DPR2 (200%-zoom-equivalent layout). This is not a claim
that native browser/menu zoom or macOS/Pi input feel was manually accepted.
Native appearance, sustained interaction and physical output remain Ian's checks.

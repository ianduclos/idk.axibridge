# Approved Compose and expandable benches — 8 September 2026

Implemented after Ian approved the study and chose popup by default, expandable.
Ready for owner checks; screenshots and browser tests do not establish native feel.

## Delivered

1. Shared popup lifecycle: expansion preserves the working recipe, focus stays in
   the dialog, Escape cancels pen capture before closing, compact Controls shelf,
   origin and Return to bench, inline preview error/retry and active-job Stop proxy.
2. Selected-source scope and New material hierarchy in Compose, Benches picker
   group, narrower sidebar and persistent compact/expanded Layers list in Compose.
3. Versioned optional catalogue descriptors, independent of time axes. Process,
   Homeostat and Second Reading adapters retain existing create/keep callbacks.
4. Second Reading keeps its local history and alternatives; exact recipe pinning
   enables a comparison in a shared coordinate frame. Capture exits comparison.
5. Homeostat has grouped controls and numeric telemetry from actual observed
   previews. The trace explicitly identifies its samples; unvisited steps are
   not presented as measured history.

## Verification

The full hardware-free suite passed **1,285 tests**, including **107 browser
acceptance/regression tests**, in 116.33 seconds. One existing dependency
deprecation warning remains. New regression
coverage includes expansion without recipe change, keyboard focus and capture
Escape, local preview failure/retry, delayed obsolete previews, explicit non-axis
bench creation, comparison scale and compact controls. Existing tests retain
Watch read-only, latch, Keep/Resume, placement, undo and frame-fit assertions.

Build and typecheck pass. Isolated source-only browser smoke reports no page
errors (`source-smoke.json`); temporary servers/configs and simulator only.
Captures include desktop, expanded, 1100/900/700 widths, compact Controls open,
Homeostat and selected-layer Compose. These use real generators, not study SVGs.

## Limits

No user app restart, hardware action or push. Unkept alternatives remain memory-only
and are labelled as such. Project replacement clears their return target and draft
namespace. Durable recovery, unified loss prompts, server command reconciliation
and the proposal's full future service API are deferred. Existing mutation callbacks
and the common resolve path remain authoritative. Physical output and native macOS/
Pi appearance, input feel and sustained alternating use remain owner acceptance.

## Captures

- [Second Reading desktop](second-desktop.png), [expanded](second-expanded.png),
  [pinned comparison](second-comparison.png).
- [1100px](second-1100.png), [900px](second-900.png), [700px](second-700.png),
  [700px controls](second-700-controls.png).
- [Homeostat](homeostat-desktop.png), [empty Compose](compose-empty.png),
  [selected source](compose-selected.png).

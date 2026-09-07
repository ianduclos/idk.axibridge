# Cosmetic pass — 7 September 2026

Ian approved cosmetics first: preserve the mono voice and experimental design,
use Compose and Second Reading as references, and carry shared controls across
the application. This implements that bounded pass, not the review's proposed
workspace or architecture changes.

## What changed

1. **Surface and colour:** vendored Flexoki raw scale, warm dark semantic roles,
   paper ground, blue selection and primary actions. Secondary labels use the
   400 neutral tier so they remain readable on raised/selected surfaces. Red
   text uses 300 rather than the darker accent tier. Measured contrast: body on
   bench 10.77:1; secondary on selected surface 4.65:1; danger on raised surface
   4.91:1; primary label on fill 5.72:1. These are selected token pairs, not a
   claim of complete accessibility conformance.
2. **Typography:** retain offline Roboto Mono; clearer 12px section and field
   labels, less letter spacing, brighter subsection labels. Supporting text
   retains a quieter role.
3. **Controls:** shared 30px regular and 24px compact targets; stronger keyboard
   focus, quieter eight-pixel slider tracks with a 26px interaction area.
   Pending Second Reading controls now have amber thumbs and tinted tracks.
4. **Icons:** consistent SVG copy, trash, reorder, upload and dice actions;
   accessible names accompany replaced icon-only buttons. Existing confirmation
   and action handlers are preserved.
5. **Second Reading:** fit the complete working frame into both stage dimensions,
   with a small inset. The stage yields space to controls down to 230px; beyond
   that, the modal scrolls. Expanded help no longer crops the sheet. The SVG's
   visible aspect follows its viewBox; geometry and pointer mapping stay in the
   existing coordinate system.

## Visual evidence

- [Compose, desktop](compose-1440.png) and [compact window](compose-1100.png).
- [Second Reading, desktop](second-reading-1440.png), [1100px](second-reading-1100.png),
  [900px](second-reading-900.png) and [700px](second-reading-700.png).
- Shared controls: [Plot](plot-1100.png), [Pens](pens-1100.png),
  [Settings](settings-1100.png).
- [Pending attention control](second-reading-pending.png), from the source-only check.
- [Stage measurements and browser errors](measurements.json).

The original review's screenshots remain unchanged in `../assets/`. Generated
examples are not an aesthetic before/after experiment; composition and seeds
can differ. These captures document interface proportions and control styling.

## Verification and limits

The new regression reproduced clipping before the fix. It checks all four paper
edges and frame aspect at 1440×1000, 1100×750, 900×650 and 700×650, including
expanded help. The hardware-free full suite passed 1,267 tests (one existing
Starlette/httpx deprecation warning). Build and typecheck passed. All 96 UI tests
passed again after the final label/hover polish.
A separate throwaway source-only copy loaded the imported palette, opened the
bench, fitted the paper and staged a control without page errors.

Ready for Ian to check. Browser inspection was Chromium; the native macOS
window, Pi browser, physical input feel and paper output still need his use.
Small windows necessarily show a smaller sheet or require scrolling. No hardware
or saved user project was touched; no application restart or push was performed.

Workspace promotion, preservation, modal focus/error handling and architecture
proposals remain in the original review. This pass makes no generator-policy
or aesthetic-selection changes.

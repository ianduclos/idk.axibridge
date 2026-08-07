# Plan: the layer list becomes a persistent panel

Ian, 2026-08-07, after Slice 4 of `ui-redesign.md` landed:

> my idea is inspired in photoshop, and having myself be able to select
> different layers without the need to scroll the whole menu. the layer
> settings (adding effects and whatnot) belongs to the top part. also
> wondering if i could click and drag to reposition layer order. reposition
> gave problems before when layers are heavy. but we can compute after
> dropping, and perhaps adding a progress bar in the bottom could be nice.
> +empty layer can stay on top

The complaint is precise and worth keeping in front of you: **selecting a
layer currently costs a scroll.** The list sits in the middle of the Compose
tab under Generate and Import, so picking a different layer means scrolling
past two panels you were not using, and you lose your place in whatever you
were doing. Photoshop's answer — the layer list is a fixed piece of furniture,
not a section of a scrolling page — is the right one.

## Read first (in this order, all in-repo)

- `docs/plans/ui-redesign.md` — Slice 4 finished 2026-08-07; this is the
  follow-on it names as "split inspector", now scoped down to just the list.
- `axibridge/static/js/compose.js` — `initComposeTab`'s template (the panel
  layout), `renderLayerList`, `makeDraggable`/`dropLayer`.
- `ARCHITECTURE.md` "Resolve order" — why reordering costs what it costs.

## Settled (decided with Ian, do not re-litigate)

| Decision | Value | Why |
|---|---|---|
| What moves | the **list only** | Ian: layer settings "belongs to the top part" |
| What stays in Compose | layer detail (effects, placement, pen/occlusion), Generate, Import, Timeline | they are editing surfaces, not orientation |
| `＋ empty layer` | **stays in Compose**, with the top part | Ian, explicitly |
| Position | bottom of the sidebar, Photoshop-style | Ian's hands expect it there |
| Collapsible | yes, state persisted | `applyPanelCollapse` + localStorage already exist |
| Resizable | yes | a 15-layer project and a 2-layer project want different heights |
| Visible on the Compose tab too | **yes** — one list, always present | two lists is the drift bug this repo spent 2026-08-07 removing |
| Selecting from another tab | selects, and does **not** jump you to Compose | a tab jump is jarring; selection already means something everywhere |

## Facts already established (don't re-derive)

- **The seam already exists.** `#layer-list` is its own `<div>` inside its own
  `.panel`, and `#layer-detail-panel` is a *separate* panel
  (`compose.js:261` and `:274`). "Just the selection box, not the parameters"
  is exactly where the markup already divides. This is a hoist, not a rewrite
  — the same move-it-bodily pattern used for the View menu and the plot
  transport, with no second implementation to drift.
- **Selection is already global.** `S.selection` is read at 23 sites across
  `canvas.js`, `draw.js`, `pen.js`, `brush.js`, `compose.js` and `main.js`.
  Clicking a layer while the Plot tab is open ALREADY highlights it on the
  canvas and retargets the drawing tools. No new semantics are needed, which
  is the thing that usually sinks this idea.
- **Drag-to-reorder already shipped**, 2026-08-07, Slice 4f (`51402b7`), and
  it already does what Ian asks for: `dropLayer` posts the new order once and
  then resolves once. **The heavy case he remembers was the per-row ↑ ↓**,
  where each click was its own reorder round-trip — moving a layer across
  fifteen was fourteen reorders and fourteen resolves. Those buttons are gone.
  So "compute after dropping" is done; what is missing is *saying so while it
  happens*.
- **There is no progress to report for a resolve.** `progress_scope` is
  wrapped around the GENERATE endpoints only (`api.py:305, 335, 347, 370`);
  `compose.resolve_project` reports nothing. A real percentage would mean
  instrumenting the single resolve path, which is a separate decision with a
  real cost. An indeterminate "working" bar is honest and cheap; a fake
  percentage is neither.
- Occlusion is memoised (`compose.OcclusionCache`) as of Slice 1, so a reorder
  on a scene with an expensive occluder is much cheaper than it was when Ian
  formed the impression that reordering is slow. **Measure before optimising**
  — the number may already be fine.

## Slices

Each is independently shippable; commit and check in after each.

### Slice 1 — hoist the list

Move `#layer-list` out of the Compose tab into a persistent element in the
sidebar, below the tab bodies. Keep the panel heading ("Layers") and the
"top of the list draws last" hint with it. `＋ empty layer` stays behind in
Compose.

The hazard is the one from 4c: `initComposeTab` rebuilds `#tab-compose` by
`innerHTML` on every project load. If the list is appended into a persistent
container, whoever owns that container must render before the appender —
`main.js:initTabs` already had to be reordered once for exactly this
(`initSettingsTab` before `initPlotTab`), and the comment there says why.
Prefer putting the container in `index.html` (static, never rebuilt) so the
question does not arise a third time.

**Done when:** the list is visible on all four tabs, there is exactly one of
it in the DOM, and selecting from the Plot tab highlights on the canvas.

### Slice 2 — collapse and resize

- Collapse: reuse the `.panel` collapse device (`applyPanelCollapse` +
  its localStorage key) rather than inventing a second one.
- Resize: a drag handle on the box's top edge. `#sidebar-resize` is the
  existing precedent for a drag handle in this UI — copy its shape, including
  the fact that it stores its result and restores on load.
- Sensible bounds: it must not be able to eat the whole sidebar or vanish.

**Done when:** the height survives a reload, the collapsed state survives a
reload, and neither can put the tab body at zero height.

### Slice 3 — say when it is working

A busy indicator at the foot of the box while a resolve is in flight, so a
heavy reorder reads as "working" rather than "frozen".

**Measure first.** Time a reorder on a genuinely heavy project (a 400-path
import, an occluder over a dense hatch fill) *now*, with the occlusion cache
in place. If the drop-to-redraw gap is imperceptible, this slice is
unnecessary and should be dropped rather than built — and the measurement is
the deliverable.

If it is needed: indeterminate, not a percentage, until and unless resolve
reports progress. Say "working", never a number the app is inventing.

## Open decisions — Ian's, not yours

1. **Does the box show its own scrollbar, or grow to fit?** With 30 layers a
   fixed box scrolls internally, which is a second scroll region in a 540px
   column. Growing to fit means the tab body shrinks instead. Photoshop
   scrolls. Ask once there is something to look at.
2. **Should the plot target follow the selection?** With the list always
   visible, "plot this layer" could mean "the selected one" rather than a
   separate picker. Tempting and probably wrong — plotting the wrong layer
   because you clicked one to look at it is exactly the kind of error that
   costs paper. Do not do this without asking.

## Verification protocol (mandatory, same as the redesign)

- `.venv/bin/python -m pytest -q` green before every commit.
- Anything visual: drive the real app in a real browser and *look at the
  screenshot*. Fresh page per shot.
- The acceptance suite is the contract — `tests/test_acceptance_ui.py`
  already asserts layer-row behaviour (rename, drag-reorder, pen swatch).
  Those tests must keep passing with the list in its new home; if one needs
  changing, the change is the thing to look at hardest.
- Measure, don't assert. Slice 3 in particular is a measurement before it is
  a feature.

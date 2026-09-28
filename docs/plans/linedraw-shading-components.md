# Linedraw components and bench — implementation contract

User approved 2026-09-28: separate shading, tonal transitions, better direction,
easier bench. Existing default geometry stays unchanged. No private image data
in Git; no hardware or added inference model. Focused verification only.

## Shared interfaces (primary owns)

LinedrawV3Params adds ink_components (unique contours/form/cores, all default),
shading_mode original|tonal (original), form_flow original|coherent (original),
form_density .25..3 (1), core_strength 0..1 (.5), hair_flow 0..1 (0).
User addendum: smoothing_mm 0..2 (default0), gentle endpoint-preserving path
smoothing bounded in paper mm. Drawing pane uses paper white and dark ink.

Tonal/direction controls act on supplied evidence and never change cache keys.

Renderer: render_document(evidence, params, checkpoint=...) remains entrypoint.
Document layers identify components with names contours/form/cores, IDs 1/2/3.
Only enabled components emit. Default geometry must remain equivalent to prior
recipes; ordering may group roles. Public reference render_light/render_regional
keep list-of-source-polylines API, with helper(s) for component separation.
Maintain shadow geometry/fields until treatment is chosen. Old style defaults
must remain available. New flow/density/hair options are opt-in.

Jobs retain preview.lines (flattened) and add preview.components list of
{id: contours|form|cores, label: human label, lines: mm polylines, count: int}.
Components returned correspond to enabled output, with empty entries permitted.
A successful result carries job ID as before. Backend retains enough completed
job data for Keep separate layers; no inference rerun or client-supplied paths.

POST /api/linedraw/jobs/{identity}/detach body:
{revision: string, source_layer_id: string|null}. Returns {layers: CanvasLayer[]}.
Copies enabled, nonempty completed components to frozen ordinary layers, one
undo checkpoint, aligned using one shared placement. Existing source layer is
left untouched; an existing layer's transform is copied (effects not copied;
UI must explain this). Reject expired/stale/failed/cancelled jobs and jobs from
a different project. No image bytes in layer names or snapshots. No generator
provenance on frozen copies. Client refreshes project/resolved and selection.

UI: Image / Guides / Drawing sections; advanced coordinates collapsed; sticky
redraw/status/keep affordances. Component switches affect actual output, not
just preview. Optional lighter shading preview is explicitly screen-only; actual
lighter plotting via density and assigned pens on detached layers. Normal Keep
and Apply retain editable recipe. Keep separate layers creates independent
frozen copies and stays visibly distinct. Automatic redraw remains user toggle,
switches off on adding guides and blocked during unfinished polygons.

Ownership: renderer agent owns engine/reference renderers/new shading helpers
and focused renderer tests; detach agent owns jobs/API/session/process adapter
and focused detach tests; UI agent owns linedraw JS/CSS and focused UI tests.
Primary owns contracts, runtime cache review, this document, docs and acceptance.
No agent delegates. Changes stay in codex/linedraw-v3 worktree.

## Integration findings

Implemented with original controls as defaults and treatments opt-in. Two
private cached-photo cases retained exactly the old default coordinate multisets
(483 and 425 strokes); model evidence was held fixed across comparisons. Tonal
shading helped one example while the original treatment read better in the
other. Dense normal-tangent variants sometimes created distracting small
clusters; they are experimental controls, not replacement defaults. Lead and
independent Sol reviewer agreed about clutter, differed on the interest of the
seated directional variant. Source images and outputs remain local.

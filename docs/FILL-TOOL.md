# Fill tool

Choose **Fill**, then click inside an area enclosed by visible lines. With
Gap at zero, a quick click waits for the face to be found and creates it once.
The highlight shows the selected face with its holes. Creation adds a selected,
editable **Found face** pen layer, with its outline and no fill effect.

Lines can come from several layers, transformed groups and effect output.
The tool reads the same resolved geometry as the canvas, at the current
timeline time. The new shape is a snapshot: changing those lines later does
not change the captured boundary. Sheet/tray preview disables drawing tools.

## Controls

- **Gap (mm)** connects nearby dangling line ends. Zero uses exact linework.
  With a positive Gap, review the highlighted repaired face before clicking.
  If a click arrives before the preview, the tool asks you to review it and
  click again. Existing closed holes are kept.
- **Detail** starts at the finest setting. Moving left uses fewer anchors;
  moving right follows the original boundary more closely. It re-fits only
  the latest found shape while this editing run is active. Each slider gesture
  has one undo step. An invalid fit leaves the previous shape intact.
- **Fill** explicitly applies Hatch, Offset, Offset v2 or Cymatic as an ordinary
  effect. **None** leaves the outline. Further tuning uses the normal effect
  controls.
- **Outline** controls the selected fill effect's existing outline option.
  It is available after choosing a fill effect.

Switch to **Pen** to edit the captured anchors. Selection changes, unrelated
edits, timeline changes, undo or leaving Fill end the temporary Detail-refit
run. The saved pen layer and ordinary effects remain editable.

## Limits and refusal messages

The tool refuses an unbounded area, a click on a line, a stale preview or a fit
that changes topology or loses the clicked point. Increase Detail for fitting
refusals. Nothing is silently skipped or moved to satisfy a limit.

Geometry work is bounded: 20,000 input segments, 50,000 noded segments,
250,000 bounding-box candidate pairs before each union, and two million
gap-search comparisons. Bounding-box overlap is conservative, so some dense
drawings are refused even if their lines do not actually cross.

A captured boundary is limited to 20,000 raw vertices, 20,000 expanded fitting
samples and 2,000 total pen anchors. Long edges are sampled before fitting to
avoid hidden curve bulges. Reducing complexity or setting Gap to zero can help
with workload refusals; the status message identifies the limit.

## Agent/API use

Preview, capture and raw-boundary refit endpoints are documented in
[MCP](MCP.md). They are available through `call_api` and
never move the machine. The Mac runs the app; the Pi receives resolved plot
jobs and needs no deployment for this tool.

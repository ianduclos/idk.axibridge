# Mosca recording bench

Select **Mosca** in Generate, then **Bench**. Expand an experiment, choose a
recording, and play or scrub its accumulated drawing. **Keep as layer** adds an
independent generator layer and leaves the bench open. **Resume** on a kept layer
copies its recording and cutoff into the bench; subsequent Keeps create new layers.

1. Progress runs from a blank 0% to the final recorded sample at 100%. Previous
   and Next step to adjacent samples. Seconds appear only when the history
   supplies `dt`; legacy files use percentage without invented timing.
2. A fractional cutoff interpolates the final incoming segment. `pen_down[i]`
   describes the segment from sample `i-1` to `i`; index zero is ignored.
   Missing masks mean continuous legacy ink. Pen lifts never become connectors.
3. Curve tolerance defaults to 0.05 mm. Each cut ink passage is simplified
   separately; zero preserves every sample. The wire/display representation is
   reduced above 60,000 points and labelled accordingly; kept geometry retains
   the requested tolerance and exact endpoint. Stationary/empty frames cannot
   be kept from the bench. Preview strokes use a fine 0.07 frame-unit width,
   five times thinner than the general drawing preview. All plot passes apply
   at least 0.01 mm simplification after placement, even when this source
   tolerance is zero; the retained recording and layer remain unchanged.
4. Placement uses the complete recording bounds, a 5 mm margin and a y flip into
   AxiBridge's coordinate frame. The frame never follows the cutoff. Existing
   placement centers at original size and shrinks only when needed to fit the bed.

## Source and persistence

`AXIBRIDGE_MOSCA_DIR` selects the mosca-draw project root or its `out` directory.
The Mac default is `/Users/ianduclos/_SecondBrain/01_Projects/mosca-draw`.
Refresh discovers `out/<experiment>/<name>.npz`; no source files are written,
no simulation runs, and no automatic synchronization updates kept layers.
Thumbnails load when experiment groups open. An incomplete/invalid history
reports an error when opened; it does not stop the rest of the browser.

Preparation is read-only project-wise. Compact deterministic NPZ bytes contain
path samples, optional pen state/timing/configuration and experiment/name
provenance, excluding neural telemetry. SHA-256 names identify immutable content.
Prepared bytes and decoded arrays have bounded process caches; very old unkept
drafts can require reopening their recording after eviction or backend restart.

Keeping persists that recording through the normal project asset store before
adding the generated layer in one undo checkpoint. Multiple keeps share its bytes
but have independent parameters and layer geometry. Save/load and ZIP export/import
carry the recording and normal SVG geometry snapshot. Resume therefore does not
need the original checkout. Asset-reference schema metadata protects recordings
from unused-asset cleanup and excludes them from settings presets. Assets follow
the existing store's lifetime, separately from layer undo history.

The registered `mosca` source has `recording`, `progress` (0–1), and `tolerance`
(0–5 mm) parameters and the `mosca` version 1 bench adapter (`new`, `resume`).
Read-only HTTP access lives under `/api/mosca`: `GET /recordings`, `POST /prepare`
with `{id}`, `GET /info?recording=…`, `GET /thumbnail?id=…`, and `POST /preview`
with `{params}`. Keep uses `/api/layers/generate`, not a separate geometry path.
Superseded preview work cancels cooperatively; the browser rejects late replies.

Source attribution: mosca-draw fruit fly trajectories, based on Janelia FlyEM /
Google connectome data (CC-BY). Neural parameters and the original histories are
unchanged. Native interaction and paper output remain human acceptance checks.

# Linedraw v3 integration

Status: proposed for review; implementation has not started.

## Intent and agreed scope

Bring the local linedraw research into AxiBridge as an image-driven drawing
tool. Ian selected **both** the latest contours/light-form approach and the
earlier Shadow shapes / Face + form approach. He selected **automatic face
regions with manual corrections**. Recognizable expression and small contour
relationships must survive shading; expressive dark masses remain available.

The integration adds `linedraw_v3` beside the existing generators. It does not
replace `linedraw` or `lineart_*`. Processing is local. Reference photographs,
their geometry, annotations and intermediate maps remain outside Git.

## User workflow

1. Choose Linedraw v3, upload/select an ordinary image asset, and open its
   drawing bench through the existing bench host.
2. Choose **Contours**, **Light form**, **Shadow shapes**, or **Face + form**.
   Light form is the proposed initial style. The preview always shows actual
   pen paths, including shadow fill strokes.
3. Analyze the image. Show stage progress and allow cancellation. Detected face
   ellipses appear over the photograph; add, move, resize, disable or delete them.
   A small numeric editor provides a keyboard alternative to dragging.
4. Adjust stroke allowance, face allowance, shadow strength, hatch/fill spacing
   and contour clearance. Redraw explicitly; do not run neural inference on
   every pointer move. Retain the previous successful preview while working.
5. Keep creates an ordinary generator layer through the existing session
   mutation path. Reopen the bench to change the recipe. Cancel discards a draft;
   applying edits is one undo step. Saved projects retain the input, accepted
   regions, settings and generated paths.

Automatic detection is a starting point, not a claim of likeness or anatomical
understanding. No detections must be a visible, correctable state. Accepting zero
faces is valid; Face + form then reports that it has no face-specific detail.

## Drawing behavior

Whole-image learned lines, four overlapping uniformly placed crops, and
photographic contours provide the category-free structural evidence. Trace at
inference resolution, then transform candidates to a common image frame before
clipping, deduplication and spatial allocation. Preserve aspect ratio and exact
crop transforms. Bound working resolution, candidate counts and output points.

Face regions request higher-resolution learned crop evidence with the research
35% context expansion. Default facial allowance is 48 continuous strokes per
face, separate from the broad contour allowance (initially 192). Facial
landmarks may locate a region; they are never emitted as drawing strokes.
These defaults are starting settings from research, not established optima.

Contours emits the selected structural evidence alone. Light form adds sparse,
normal-guided hatching while preserving selected contours and clearing space
around them. Shadow shapes builds larger dark regions. Face + form combines
face detail, structural contours and normal-guided body shading.

Shadow shapes and Face + form use the preserved face-seeded material-relative
proxy when valid face samples exist. An explicit **local darkness** alternative
supports images without valid samples. Report which proxy was used; never
silently describe local darkness as the original material-relative recipe.

Person segmentation supplies foreground probability only. It does not assign
people or body parts. Keep every qualifying foreground component; do not use
the old largest-component shortcut. This first integration does not recreate
manually supplied per-person ownership or semantic hand/hair/clothing budgets.
Face budgets remain independent; broader detail uses spatial allocation.

Filled regions alone are not executable shading: `Path.filled` is occlusion
metadata. Convert shadow interiors to actual bounded fill strokes, preserving
holes and geometric clearance. Show those same strokes in preview and export.
Offer fill spacing in millimetres. Dense shadows will cost plot time; estimates
use the normal resolved geometry. Do not substitute painted SVG fills for paths.

## Production boundaries

Use a `SourceModule` in `axibridge/sources/linedraw_v3.py`, a production geometry
package under `axibridge/`, a local inference adapter, and a dedicated bench
adapter registered through `static/js/bench_registry.js`. Reuse the bench host
for focus, dismissal and project-change lifecycle. The existing asset store,
layer model, project serialization and single resolve path remain authoritative.

Move reusable research kernels into an importable production package with
compatibility imports for research tests. Production must not import `tools/`
or execute any private study runner. Extract and review generic tracing and
selection algorithms without carrying over photograph-specific constants,
coordinates, paths or manifests.

Keep image/rotation/width/frame semantics consistent with `_pixelgen.py`.
Do not expose generic channel or tone controls unless the pipeline honors them.
Store face ellipses in normalized, EXIF-corrected, unrotated image coordinates
with stable IDs and automatic/manual provenance. Rotation and paper placement
are later transforms. Bind region edits to image content and sequence frame;
changing either resets analysis instead of reusing unrelated guides. Redetection
is explicit and must not overwrite accepted corrections automatically.

The bench holds drafts, previews and analysis state. Session methods alone
commit project changes, checkpointing under the session lock. Generation returns
a standard `PathDocument`; previews, effects, estimates and plotting continue
through the existing resolve contract. No additional hardware or plotting route.

## Local models and cancellation

Reuse Informative Drawings, LRASPP person probabilities and DSINE normals from
the research recipe. Use a local face detector/landmarker for initial ellipses;
evaluate detection on full images rather than assuming the earlier crop-only
MediaPipe experiment establishes full-image performance.

Model code/checkpoints live in a configured external model directory. Never
discover them by searching private study directories during application startup.
An explicit setup command checks dependencies and files without reading photos.
Optional dependencies must not break registry imports or ordinary app startup.
Show per-capability readiness and actionable errors; never silently substitute
an unrelated drawing algorithm. No downloads on generation or project open.

Use a serialized worker process for inference so cancellation can terminate an
active model operation without wedging the app. A worker owns model imports and
device selection; the main server owns assets and project state. Use unique
temporary inputs, structured arguments, bounded results and guaranteed cleanup.
Missing models, failed inference and cancellation preserve the prior preview
and leave the project unchanged. Reuse existing render cancellation checks in
tracing, selection and fill loops as well as between inference stages.

The current generator-preview endpoint is not inside a cancellable render scope.
Add a Linedraw analysis/preview job API with explicit start, status and cancel
operations; do not imply that the existing preview route already cancels work.
Jobs are tied to a draft/image revision and return read-only results. Keep may
reuse completed analysis, but only the normal layer mutation path commits it.
Closing a draft or changing projects cancels its jobs and ignores late replies.

Prefer MPS on the supported Mac, CPU as an explicit fallback. Record the chosen
device in diagnostics. The existing environment separates MediaPipe from the
main research interpreter; dependency compatibility must be verified before
installation. Do not change the application's pinned Python to solve conflicts.

Inspect upstream code and checkpoint terms and preserve required notices before
copying implementation. The local DSINE license restricts permitted use; do not
vendor or redistribute it as MIT application code. Keep that optional runtime
separate and document its upstream terms. No third-party weights enter Git.

## Reproducibility and caches

Accepted detections become explicit recipe data before Keep. Frozen saved paths
must open and plot without installed models; regeneration reports missing models
without discarding those paths. Record a recipe version and model fingerprints
without private filesystem paths in saved provenance.

Cache inference by image bytes, frame, preprocessing, model identity and inference
settings. Cache geometry separately by accepted guides, style, budgets and
paper-dependent spacing. Style or allowance changes should reuse evidence.
Bound cache memory and disk usage; keep any persistent image-derived cache in
the user's local application storage. Integrate model identity with the outer
generation memo too, so replacing weights cannot serve stale geometry.

## Verification and acceptance

Repository tests use synthetic images and mocked model outputs. Cover crop and
rotation transforms, EXIF orientation, independent face budgets, small images,
empty foreground, failed detections, duplicate regions, bounded finite paths,
holes, contour clearance, actual shadow fill strokes and deterministic selection.

Exercise asset replacement, changed model identity, cancellation during inference
and tracing, concurrent analysis, stale replies, failed Keep, undo/redo,
save/reopen and regeneration without dependencies. Browser acceptance covers
upload, all styles, region correction, keyboard controls, Keep and reopen.

Run real local inference on a synthetic or publication-approved fixture. Verify
the integrated UI against an isolated server before desktop delivery, then check
the live application's model readiness and endpoints. Inspect current machine
state before restarting anything; never interrupt an active plot. Do not claim
native acceptance or paper quality from automated checks.

For aesthetic acceptance, preserve contour-only and whole-image controls and
compare whole drawings plus close views, including failed detections and weak
cases. Use the project's bounded Sol second-eye review after implementation.
Private comparisons remain local. Ian's visual check and a later paper test
remain necessary; transfer beyond the research examples is unproven.

## Delivery boundary

Implementation is complete only when both approaches can be used through the
app, automatic regions can be corrected, saved layers are portable, cancellation
is safe, and ordinary generators remain compatible. An unavailable-model stub or
a wrapper around private scripts is not a completed integration.

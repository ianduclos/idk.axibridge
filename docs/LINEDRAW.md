# Linedraw v3

Choose **Linedraw v3** in the generator selector, then **Bench**. Select or upload
an image and press **Analyze / redetect faces**. The image stays on this computer.
The left view shows the source and editable face ellipses; the right view shows
actual pen paths. With **Automatic redraw** enabled, edits redraw after a short pause. Switch it off
to batch edits, then press **Redraw**. Adding a face/person/detail region or starting
a polygon switches it off until you explicitly re-enable it. It stays disabled
while a polygon is unfinished.
The shared status indicator stays active during work, and the bench shows the stage.
Keep creates an ordinary layer.
Reopen a kept layer's bench to edit its recipe: Apply updates that layer in one
undo step, while Keep creates another layer.

## Styles and controls

1. **Contours** combines whole-image learned evidence, uniform crops and
   photographic contours. Face regions request separately budgeted crop detail.
2. **Light form** adds sparse normal-guided shading, with clearance around the
   same selected contours. This is the default.
3. **Shadow shapes** converts broad shadow regions into real pen fill strokes.
   Fill spacing changes density and plot time; there is no painted-fill shortcut.
4. **Face + form** combines independent face detail, fuller form hatching and
   filled deep-shadow cores.

5. **Light form support** preserves the final research recipe: weighted spatial
   contour selection, photographic edges stable across two scales, and at most
   60 sparse hatch strokes with clearance around every contour. It uses no
   anatomical guides. Its fixed image-space distances are separate from the
   adjustable Light form style; input images are still capped at 1536 pixels.
6. **Regional face + form** preserves the earlier middle-scale material/form
   base with independent face crops and manually selected regional detail.
   It requires an enabled face region for the material proxy. Start with 48
   facial strokes and 192 additional detail strokes per person; hands/feet,
   clothing and hair are initially visible, body detail is off.

For Regional face + form, use **Edit regions** to switch between faces, people
and detail areas. A person polygon assigns ownership; overlapping people are
resolved front-to-back in list order, with later entries in front. Link each
person to a face when there are several. Add detail polygons and label them
hands/feet, clothing, hair or body. Drag vertices or edit their coordinates;
exclusion polygons can remove unwanted areas such as knees from a dress crop.
The single-person default owns the full image, still clipped by foreground.

Category switches affect added detail only: base hatching and face evidence stay
fixed. An allowance is a ceiling, not a promised count. No regions means base
form only. Regions and category settings are saved in the layer recipe; changing
image/frame resets them. Model inference runs again after crop changes, so these
edits take longer than a cached budget or category change. The previous drawing
stays visible while its replacement runs. Redetecting faces clears person-face
links so that stale identities cannot silently attach to a new detection.

The Light support renderer was compared against the frozen research output with
identical evidence: all 252 paths matched within 0.007 source pixels. Regional
rendering preserved the reference hatching and face crop selection, but its base
contour tracing remains slightly different from the oldest cached study. Treat
it as the corresponding recipe, not guaranteed byte-identical legacy geometry.
These checks are local; no reference images or derived geometry are test fixtures.

Face regions can be dragged and resized with their corner dot, or edited with
numeric controls. Automatic detection is only a proposal. Add missed faces,
disable unwanted ones, or accept none. Redetection explicitly replaces regions.
Changing the input image or sequence frame resets them. A region is a request
for higher-resolution learned detail, not a template of facial landmarks.

**Local darkness** is the default shadow proxy and works without face samples.
**Material** uses the research face-seeded color heuristic and requires useful
face samples; it reports an error if none qualify. Neither recovers physical
illumination. Foreground recognition identifies people versus background; it
neither separates people nor understands named body parts. This version uses
spatial allocation for body detail rather than the manually labeled regional
budgets of the research studies.

The 192 contour / 48 per-face defaults are starting settings. More strokes do
not necessarily improve a drawing. Source correspondence and automatic face
localization are not guarantees of expression or likeness. Physical plot quality
still needs a pen-and-paper check. Dense shadow styles can retain small holes
and ragged tonal boundaries; use shadow strength and spacing to judge that
tradeoff on your image.

## Local runtime

The application's Python does not import neural packages during startup. A
serialized child process runs inference; cancellation terminates its process
group, including the optional separate MediaPipe child. Analysis is limited to
10 minutes. Model code and weights are external, optional runtime dependencies.
Saved paths still open and plot on a machine without them; regeneration requires
the configured runtime. Failed regeneration preserves the previous layer.

`tools/setup_linedraw.py --help` lists explicit configuration inputs. It creates
`linedraw.json` in the application config directory and refuses to overwrite an
existing file. `--check` checks configured paths without inference or downloads.
`AXIBRIDGE_LINEDRAW_CONFIG` may point to another configuration file.

Required configuration keys are `python` (the pinned application interpreter),
`line_code` (Informative Drawings source directory), `line_weights` (the anime
style Generator checkpoint), and `person_weights` (torchvision LRASPP MobileNet
V3 Large checkpoint). Form styles additionally use `normal_code` (DSINE source),
`normal_weights`, and `normal_dependencies` (a list of extra dependency roots,
including geffnet if installed separately). Automatic faces use `face_python`
and `face_weights` (MediaPipe Face Landmarker task). The face interpreter may be
separate to avoid dependency conflicts. `device` can be `mps`, `cpu`, or `cuda`;
absent a setting the worker chooses MPS when available, otherwise CPU.

The line/person/normal worker needs PyTorch, torchvision, Pillow, NumPy, SciPy,
and the upstream model dependencies. The face interpreter needs MediaPipe,
Pillow and NumPy. The setup command never downloads model weights or packages;
install compatible versions deliberately and keep the application's pinned
interpreter. No model code or weights are redistributed in this repository.
Consult the respective upstream licenses before installation or redistribution:
Informative Drawings, torchvision, DSINE and MediaPipe. In particular the DSINE
source used by the research carries restricted noncommercial/internal/academic
research terms, not the application's MIT license. Preserve its upstream license
alongside that optional local installation.

Inference results are cached in memory under a 256 MiB budget multiplied by
`AXIBRIDGE_CACHE_BUDGET`. Image bytes, accepted face regions and model fingerprints
identify evidence. Style/budget edits reuse it; face changes request new crop
analysis. Temporary model inputs/results are removed after every run. No
persistent image-derived cache is created. Closing the application loses warm
analysis, but accepted recipes and geometry travel in project folders.

## Limits and verification

Input images are EXIF-corrected, alpha-composited on white and bounded to 1536
pixels on their long side. Face inference uses a 512-pixel long side with crop
context; whole-image learned inference uses 768. Learned maps are traced at
their native inference size before vector coordinates return to the source
frame, so resizing cannot erase thin evidence. The completed bench reports
the inference device. At most 32 face regions and
1024 broad contours are accepted. Output is limited to 20,000 paths / 500,000
points; excessive detail requests an explicit reduction.

The latest reference-style extension passed 55 focused rendering, runtime,
job, persistence and browser tests, plus typecheck/build. The full repository
suite was not repeated for this extension, following the requested bounded
verification.

Tests use mathematical fixtures and mocked model evidence. Real-model smoke
checks use nonprivate inputs. Private research photographs and all derivatives,
including vector geometry, remain outside Git and are not reusable test fixtures.

# Linedraw v3: research checkpoint, 2026-09-28

The reusable code lives in `tools/linedraw_research/`. This checkpoint preserves
algorithms and reasoning so a fresh agent can continue without the long
conversation. No production module, application UI or hardware path changed.
Reference photographs and every image-specific derivative stay local and must
not be committed or uploaded, including SVG geometry and embedded HTML.

## Direction to preserve

Ian wants recognizable people, clear expression and fine details without losing
the expressive strength of **Shadow shapes** and **Face + form**. He particularly
liked **plain face-crop evidence at48 strokes per person**, then encouraged
similar treatment of the body. Those strokes come from a learned drawing model
inside a supplied crop, not from a facial landmark template.

The useful finding is selective higher-resolution evidence. Processing a small
region separately can recover passages that disappear when the whole image is
resized. Keep whole-image evidence as a control: it sometimes preserves long
contours better. The studies compared facial allowances18/32/48 per person and
additional regional detail48/96/192 per person. Facial detail stays48 in the
regional/coordination studies;96 additional strokes was a useful comparison
starting point, not a universal aesthetic optimum.

Keep source framing, output stroke width, body geometry and fixed facial paths
constant when testing a local change. Crop context was expanded35%; learned
crop inference used a512-pixel long side with aspect ratio preserved. Whole-image
regional evidence used1536. Work in source pixels and record crop transforms.
These are historical experimental settings, not performance promises.

## What was automatic, and what was supplied

- LRASPP MobileNet produced person-versus-background probabilities. It did not
  separate people or label hands, legs, hair and clothing.
- We supplied individual ownership polygons, face ellipses and semantic region
  labels after inspecting the photographs. These choices determine where the
  algorithm looks and how its detail allowance is spent.
- Informative Drawings generated line maps; tracing, clipping and selection
  produced vectors. Its learned evidence can still distort or invent features.
- DSINE supplied surface orientation used by the form hatching heuristic.
- MediaPipe facial landmarks were an optional association/refitting experiment.
  Landmark predictions were not emitted as drawing strokes. The preferred plain
  face-crop branch does not depend on landmark guidance.
- Hair/ground experiments used additional manual search regions; a separately
  labeled guided hair reference included actual hand-authored lock paths.

This is annotation-assisted research. Shared numerical settings are insufficient
to establish transfer if annotations are adjusted after seeing a mistake.
Do not describe the current system as an automatic body-part detector or claim
it generalizes from the small, previously seen reference population.

## Findings worth keeping

1. **Recover evidence before adding constraints.** Local crop evidence showed
   more useful gains than small landmark adjustments. Feature-balanced allocation
   can help, but additional strokes must explain a feature or relationship.
2. **Protect detail without assuming cleanliness is better.** Clearing old
   hatches near detail can clarify local passages, but increases fragments and
   can erase useful overlaps. The independent reviewer could not consistently
   distinguish clearance from control at whole-drawing scale.
3. **Dark masses need structural judgment.** Thresholded dark cores often look
   deposited on the body or swallow important junctions. A shared setting became
   much heavier on another photograph. Keep the failed combined treatment as
   local evidence, not as a new default.
4. **Hair needs directional grouping and appropriate visual weight.** Removing
   transverse hatches can expose useful flow but leave dark hair undescribed.
   Manually supplied long locks suggest a direction; they are not an automatic
   achievement. Conservative automatic joins found no supported joins in the
   latest pass. Lead/reviewer disagreement about the value of the old hatch
   fringe remains unresolved.
5. **Source correspondence does not make a mark useful.** Sparse background
   fragments can float, and a contact-shadow search boundary can turn into an
   artificial ledge. Preserve empty/no-result cases. Broader background work
   is not yet justified by these tests.
6. **Visibility and anatomical relationships are a useful stress test.** Ian
   noted that a small anatomical passage disappearing under shadow can expose
   weak abstract drawing judgment. Do not infer model censorship or model bias
   from the final drawing alone: compare photo, raw line map, shadow proxy,
   selected paths and composition to locate where it vanished. Test contours,
   overlap and negative spaces without relying on a body-part label to rescue
   them. A recognizable face alone is inadequate evidence.

The blind reviewer noticed removal of an important detail passage but could not
reliably identify a displaced version. Retain that calibration limitation;
reviewer agreement is not an exact alignment or likeness metric. All judgments
were screen-based. No physical plot validation was performed.

## Next agent

1. Read this note and the code README, then the ignored local handoff if present.
   Local study runners and comparisons remain authoritative for the original
   outputs; this extraction is a reusable subset, not a replacement bundle.
2. Clarify the intended role of semantic recognition before integration. Compare
   category-free multiscale attention with explicit automated part localization;
   do not silently commit the design to more detectors. Neither is implemented
   by this checkpoint.
3. Freeze a recipe and evaluate genuinely unseen images without per-image guide
   repairs. Separate supplied annotations, automatic detections, raw model
   evidence, selection losses and compositing losses. Include no-detector and
   whole-image controls.
4. Use synthetic or explicitly publication-approved fixtures for repository
   tests. Keep any private evaluation data and output outside Git. Do not push
   the local artifact archive or copy private manifests into code.
5. Only after choosing a direction, plan production integration through the
   existing source/asset and single-resolve contracts. Optional models, cache
   invalidation, licensing, cancellation, deployment and plot planning remain
   future integration work. Preserve the existing `linedraw`/`lineart_*` behavior.

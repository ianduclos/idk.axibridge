# Linedraw v3 research kernels

This is a code-only checkpoint of the local drawing studies, not a registered
source/effect or a finished v3. The existing `linedraw` and `lineart_*` modules
remain unchanged. Nothing here loads a model, reads a reference photograph,
contacts a service, or sends geometry to hardware.

## Preserved code

| File | Responsibility | Inputs supplied by caller |
| --- | --- | --- |
| `flow_hatch.py` | Deterministic normal-guided hatching in a mask | Shadow mask and surface-normal array |
| `geometry.py` | Arc sampling, simplification and cubic fitting | Candidate polylines |
| `shadows.py` | Material-relative darkness, shadow shapes, hatch clearance and real geometric shadow cuts | RGB array, foreground/face masks, or Shapely geometry |
| `allocation.py` | Exclusive ownership, region clipping, duplicate/join handling and independent detail budgets | Explicit person/part guides, foreground probabilities and traced line candidates |
| `guidance.py` | Optional feature-balanced facial selection and bounded landmark adjustment | Existing line candidates, face ellipse and supplied landmark contours |

These are preserved experimental rules, not tuned production defaults. In
particular, the material proxy is a color heuristic rather than recovered
illumination; hatching bends a diagonal field using surface normals rather than
physically projecting strokes onto a reconstructed body. Faces and body parts
are supplied annotations/detections, not recognized by this package.

The learned-line inference adapters, checkpoint files, crop/line-map caches,
per-image manifests, comparison runners and rendered evidence remain local.
The kernels alone cannot reproduce the complete research drawings. The ignored
`.local/linedraw/HANDOFF.md` points to the original study tree on this machine.
Do not turn those local experiment files into public test fixtures.

## Using the selectors

All coordinates are original-image pixels unless a function explicitly says
working pixels. Nothing converts them to the application's paper coordinates.
`prepare_case(case, probability)` accepts an in-memory H×W probability array
and returns owner/region masks and guide metadata without writing anything.
The `case` dictionary describes `width`, `height`, and `people` in back-to-front
order. Each person has an `id`, `owner_polygon`, optional face ellipse, and
`regions` with `id`, `category`, `polygon` and optional `exclude_polygons`.

`select_details(evidence, case, prepared, method, budget)` takes either
`whole_candidates` or a `regions` mapping. Each candidate contains an `id`,
source-coordinate `points`, and `confidence`. The budget applies independently
to each person, excludes the separately retained facial strokes, and may be
under-filled. Category weights are explicit heuristics: hands/feet3,
clothing2, body2, hair1. Clipping creates new continuous stroke fragments;
count visible strokes rather than SVG elements.

`select_guided` and `select_balanced` consume supplied facial contours but
never emit landmark templates as drawing strokes. A failed detector returns
unguided candidates with an unavailable status. Adjustment is capped at1.5%
of supplied face width. The plain crop-based facial result does not require
this optional guidance stage.

`cut_shadow` takes a **full cut width**, returns altered geometry and removed
geometry, and limits subtraction to an explicit edit region. Fill holes are
real geometry. A caller must separately keep black feature strokes on white
paper and report added strokes, cuts, removed area and resulting components.
`clear_hatching` can improve readability while increasing stroke fragments;
it is not a complexity reduction guarantee.

## Verification

Run from the repository root:

```sh
.venv/bin/python -m pytest -q tests/test_linedraw_research_*.py
```

Fixtures are generated mathematical arrays, rectangles and polylines, never
tracings or model outputs from private photographs. Tests cover independent
person budgets, input purity/no file I/O, face clearance, feature allocation,
clipping/deduplication/joins, supported fallback, geometric holes, hatching
component boundaries and deterministic behavior. They do not certify aesthetics.

## Privacy boundary

Never commit source photographs, crops, masks, normals/depth, landmarks,
image-specific coordinates, traced candidates, generated SVG/PNG, embedded
HTML previews, archive bundles, caches, or identifying source paths/hashes.
Derived line geometry can reproduce a reference even without its raster.

This directory's ignore rules permit only code and Markdown, and the private
handoff directory is ignored at repository root. Ignore rules do not make
photo-specific coordinates in Python/Markdown safe: inspect every staged file
and stage explicit paths. Keep future outputs outside the repository.

See [findings and continuation](../../docs/research/linedraw-v3.md).

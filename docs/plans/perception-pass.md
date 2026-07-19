# Plan: perception-pass generator — line weight = certainty (Sonnet 5)

You are Claude (Sonnet 5) running as a coding agent on Ian's Mac, in a git
worktree of axibridge. Written 2026-07-19 (Sonnet 5, no Fable in the loop).
No hard prerequisite beyond current main — this generator only depends on
`sources/_lineart.py` and `sources/_pixelgen.py`, both on main since July.

## The goal, and the design calls this brief freezes

`docs/IDEAS-oehlen-pass.md`'s "line weight = certainty" principle (ROADMAP's
Oehlen-pass item 5) is stated at concept level: "run several cheap perception
passes over the same asset... and let agreement set the mark: fat beam where
all agree, hairline wander where one thinks so, dither-density where
ambiguous." It names three example passes (threshold edges, Depth Pro
discontinuities, a segmentation boundary) without segmentation existing in
this codebase yet, and without specifying HOW "agreement" becomes a mark.
Frozen here:

1. **Agreement = vote count, not blended magnitude.** Each detector is a
   BOOLEAN edge mask (`_lineart.xdog`/`sobel_edges` already return bool
   masks, not continuous magnitude — see Read First #3). Certainty at a
   point = (number of detectors that fire near that point) / (number of
   active detectors). This is simpler than extracting and normalizing
   continuous magnitude fields from three unrelated signal types, reuses
   tested functions AS-IS, and maps naturally onto the idea doc's own
   3-tier language (0 detectors = ambiguous/dither, all detectors = fat
   beam).
2. **v1 detector set: two REQUIRED (same image, two blur scales), one
   OPTIONAL (a depth asset).** Segmentation doesn't exist yet — not
   building it here. Depth Pro is NOT installed in the Pi venv (only the
   Mac's), so making it required would break the Pi clone and the
   hardware-free test suite; it must be a genuinely optional third vote,
   and this module must never call Depth Pro itself — it only reads a
   grayscale depth ASSET that some other, already-existing flow produced
   (the asset-producer rule, see Boundaries). Two same-image, different-
   scale edge detectors are still a real, meaningful "several cheap
   perception passes": a hard edge agrees at both blur radii, a texture
   edge only survives at the fine scale.
3. **Geometry comes from tracing the FINE detector only; agreement supplies
   WEIGHT, not shape.** Don't trace a "combined" mask — trace detector A
   (the literal structure), then sample the agreement grid along that
   trace. This keeps the line's actual path exactly as legible as
   `lineart_edges.py`'s existing edge tracing (a known-good baseline) and
   makes agreement purely a rendering modulation on top of it.
4. **Rendering = width-modulated outline (reuse `drawing.py`'s velocity-tube
   technique, certainty in place of speed) + scattered dither ticks below a
   threshold.** Not a wholly new rendering mechanism — see Phase 4.

## Read first (in order, all in-repo)

1. `CLAUDE.md` — module purity, bounded params; also the note in
   ARCHITECTURE.md/CLAUDE.md that AI-assisted inputs must stay ASSET
   PRODUCERS, never a resolve-path stage — this generator reads assets, it
   never runs a model.
2. `docs/IDEAS-oehlen-pass.md` lines ~10–47 — the Oehlen analysis and the
   "line weight = certainty" paragraph, so you understand the aesthetic
   target, not just the mechanics below.
3. `axibridge/sources/_lineart.py` — read `xdog`, `sobel_edges` (BOTH
   return bool `(h,w)` masks — confirm this yourself, it's the load-bearing
   fact behind design call #1 above), and `trace` (vectorizes a bool mask
   into px-space polylines; already handles smoothing/min-length/joining —
   you are NOT rewriting tracing, just calling it).
4. `axibridge/sources/lineart_edges.py` — the thin-wrapper plumbing pattern:
   `ImageBaseParams` subclass, `image_processing_kwargs`/
   `apply_image_processing_value`, `luma_grid`, `working_dims`, and how
   traced px-space polylines get scaled into placed mm geometry. Copy this
   file's STRUCTURE (imports, working-canvas setup, px→mm scaling at the
   end) closely — don't reinvent working-canvas math.
5. `axibridge/sources/drawing.py`'s `_velocity_outline`/`_tangents`/
   `_velocity_widths` (~lines 186–269) — port this technique, NOT this
   exact code (different module, different per-point driver value). One
   critical difference from the original: `_velocity_widths` normalizes
   speed to EACH STROKE's own min/max range. Do **not** do that here —
   certainty is already globally meaningful in [0, 1] (it's a vote
   fraction, comparable across strokes and across the whole image); a
   stroke where every point agrees 3/3 should render uniformly fat, not
   renormalized to look mid-width just because it has low local variance.
   Also note `_velocity_outline` returns `filled=False` even though the
   outline is closed (first==last) — deliberate, so the fat/thin line
   reads as a thick STROKE, not an occluding solid area. Match that choice
   here for the same reason.
6. `axibridge/assets.py`'s `AssetStore.grayscale(name, blur_px, rotate=0)`
   — how you'll pull the optional depth asset. `axibridge/depth_pro.py`'s
   module docstring — confirms Depth Pro's OUTPUT is already a normalized
   8-bit grayscale depth PNG, i.e. asset-store-compatible with zero special
   handling once it's uploaded as an asset.

## Protocol

- `.venv/bin/python -m pytest -q` green before EVERY commit — including on
  a machine/venv WITHOUT Depth Pro installed (the Pi's). If any test
  imports `depth_pro` or calls it, that's a bug: this module never touches
  that package, only `assets.asset_store.grayscale()` on a plain image.
- Branch `feat/perception-pass` from main. One commit per phase (detectors,
  agreement grid, trace+render, params/polish). NEVER main. Do not push.
- **Eye-check is the core loop.** Throwaway script: run on a real photo
  (something with both a hard silhouette edge and some soft/textured
  regions — a portrait or a building against sky is a good test case),
  render to PNG, LOOK. You're checking for the CONTRAST between fat-and-
  confident vs hairline/dithered, not just "does it draw something."

## Phase 1 — image setup (copy `lineart_edges.py`'s plumbing)

`AgreementParams(ImageBaseParams)` — same image/rotate/width/show_map base,
same collapsed "Image processing" group (brightness/contrast/gamma/levels
via `image_processing.py`, applied to grayscale samples only, per
`docs/MODULES.md`). `luma = luma_grid(params, blur_px=0)` at
`working_dims(params)`.

## Phase 2 — detectors and the agreement grid

- **Detector A (fine, required)**: `edge_fn(luma, sigma_fine, edge_threshold)`
  where `edge_fn` is `L.xdog` or `L.sobel_edges` per an `edge_mode` param
  (mirror `lineart_edges.py`'s own `edge_mode: Literal["xdog","sobel"]`).
  This is also the tracing input in Phase 3.
- **Detector B (coarse, required)**: same `edge_fn`, larger `sigma_coarse`.
  Dilate by `agree_radius_px` (`scipy.ndimage.binary_dilation`, a few px)
  before combining — B and A are computed at different blur radii, so their
  "edge" pixels won't land on the exact same coordinates even when they
  agree about the same real structure; without dilation, agreement would
  almost always read as disagreement. Same dilation applies to C below.
- **Detector C (depth discontinuity, optional)**: only if `params.depth_image`
  is non-empty. `depth_luma = asset_store.grayscale(params.depth_image, 0,
  rotate=params.rotate)`; if its shape doesn't match `luma`'s working
  dimensions (very likely — the depth asset has its own native resolution),
  resample it to match (nearest or a simple scipy zoom is fine, this is a
  coarse signal). `C = L.sobel_edges(depth_luma_resampled, depth_threshold)`,
  then dilate.
- **Agreement grid**: `active = 2 + (1 if C is not None else 0)`;
  `agree_count = A.astype(int) + B_dilated.astype(int) + (C_dilated.astype(int)
  if C is not None else 0)`; `certainty = agree_count / active` — a float
  array in `{0, 1/active, 2/active, ..., 1}`.

## Phase 3 — trace + sample

`strokes_px = L.trace(A, join_angle_deg, min_length_px, smooth)` — trace
detector A ONLY (design call #3). For each traced stroke: resample at a
fixed px step (mirror `drawing.py`'s `_resample`-style arc-length
resampling, or reuse `trace`'s own point density if it's already even
enough — check by eye, don't assume). At each resampled point, sample
`certainty` (nearest-neighbor into the grid is fine — it's already a coarse
vote-count field, no need for bilinear precision here).

## Phase 4 — render: width-modulated outline + dither ticks

- **Outline**: port `_tangents` + a `_velocity_outline`-shaped function,
  swapping the speed-derived per-point width for `width_min +
  (width_max - width_min) * certainty` directly (certainty=0 →
  `width_min`, certainty=1 → `width_max`; NO per-stroke normalization —
  see Read First #5). Same left/right offset + round-cap construction,
  same closed-but-`filled=False` choice.
- **Dither ticks**: wherever a run of consecutive points has `certainty <
  dither_threshold`, scatter short perpendicular tick marks along that run
  instead of (or thickening) the hairline — count over the run ≈
  `dither_density * run_length_mm * (1 - mean_certainty_over_run)`, each
  tick a short open 2-point `Path` (`filled=False`) centered near a
  seeded-jittered position along the run, length `tick_length`, direction
  the local normal (same normal you already computed for the outline).
  Lower certainty → visibly denser scatter, matching "dither-density where
  ambiguous." Seed ticks from `(params.seed, stroke_index, run_index)` so
  output is deterministic.
- Scale px → mm using the SAME working-canvas → `width` mm conversion
  `lineart_edges.py` uses (Read First #4) — don't recompute this
  independently, copy the call.

## Params

```python
class AgreementParams(ImageBaseParams):
    edge_mode: Literal["xdog", "sobel"] = Field(default="xdog", title="Edge mode")
    sigma_fine: float = Field(default=1.2, ge=0.5, le=6.0, title="Fine scale (px)")
    sigma_coarse: float = Field(default=6.0, ge=2.0, le=20.0, title="Coarse scale (px)")
    edge_threshold: float = Field(default=0.5, ge=0.0, le=1.0, title="Edge strictness")
    depth_image: str = Field(default="", title="Depth asset (optional)",
                             json_schema_extra={"format": "asset"})
    depth_threshold: float = Field(default=0.4, ge=0.0, le=1.0, title="Depth edge strictness",
                                   json_schema_extra={"group": "Depth (optional)"})
    agree_radius_px: float = Field(default=3.0, ge=0.0, le=10.0, title="Agreement tolerance (px)",
                                   json_schema_extra={"group": "Fine tuning"})
    width_min: float = Field(default=0.4, ge=0.2, le=6.0, title="Hairline width (mm)")
    width_max: float = Field(default=4.0, ge=1.0, le=15.0, title="Fat beam width (mm)")
    dither_threshold: float = Field(default=0.34, ge=0.0, le=1.0, title="Dither threshold")
    dither_density: float = Field(default=1.5, ge=0.0, le=5.0, title="Dither density (ticks/mm)")
    tick_length: float = Field(default=1.2, ge=0.3, le=5.0, title="Tick length (mm)",
                               json_schema_extra={"group": "Fine tuning"})
    join_angle_deg: float = Field(default=50.0, ge=0.0, le=90.0, title="Join angle (deg)",
                                  json_schema_extra={"group": "Tracing"})
    min_length: float = Field(default=6.0, ge=0.0, le=60.0, title="Min length (px)",
                              json_schema_extra={"group": "Tracing"})
    resolution: float = Field(default=1.0, ge=1.0, le=2.0, title="Resolution ×",
                              json_schema_extra={"group": "Tracing"})
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")
```

(`ImageBaseParams` already supplies `image`, `rotate`, `width`, `show_map`,
and the collapsed Image-processing group — don't redeclare those.)

## Tests (`tests/test_agreement.py`)

- **No `depth_pro` import anywhere in this module or its tests** — grep
  your own new file for the word before you commit. Tests must pass with
  Depth Pro absent from the environment entirely.
- Determinism: same params + same image asset → identical output twice.
- No `depth_image` set (`""`): `active == 2`, certainty values only in
  `{0, 0.5, 1}`; generator runs without touching any depth code path.
- `depth_image` set to a real uploaded asset: `active == 3`, certainty
  values in `{0, 1/3, 2/3, 1}`.
- **Agreement contrast, synthetic image**: build a small synthetic luma
  array with (a) one hard, high-contrast straight edge and (b) one region
  of fine, low-contrast texture noise that a coarse blur erases. Confirm
  the traced stroke crossing the hard edge has width samples clustered near
  `width_max`, and any stroke/tick output in the texture region shows
  LOWER average certainty (more dither ticks, thinner outline) than the
  hard-edge stroke. This is the test that actually proves "line weight =
  certainty," not just that the module runs.
- Dilation matters: with `agree_radius_px=0` on two detectors whose edges
  are offset by a couple of px (construct this synthetically), agreement
  reads mostly as disagreement; with a nonzero radius, the same input
  agrees. Confirms the dilation step is doing real work, not a no-op.
- Depth asset shape mismatch (upload/construct a depth asset at a different
  resolution than the base image) doesn't crash — the resample path is
  exercised.
- Bounded params (spot-check a couple of violations 422 via Pydantic).
- Missing/empty base `image` behaves like other image-driven sources
  (raise a helpful `ValueError`, per `docs/MODULES.md`'s "generators may
  raise" rule — don't silently return empty for the REQUIRED image, only
  the optional depth one).

## Aesthetic target

On a real photo with both a strong silhouette edge and some soft/textured
area: the silhouette should read as a confident, fat, mostly-continuous
beam; the textured area should taper to hairline wander or break into
scattered dither ticks. If width barely varies across the whole image,
`agree_radius_px` is probably too generous (everything agrees with
everything) or `sigma_fine`/`sigma_coarse` are too close together (both
detectors are really the same detector). If NOTHING ever reaches
`width_max`, your dilation or thresholds are too strict — tune before
shipping, the whole feature lives in that contrast.

## Boundaries

- Do not touch: `model.py`, `compose.py`, `session.py`, `estimate.py`,
  backends, `depth_pro.py`, `_lineart.py`, `lineart_edges.py`,
  `drawing.py`, any existing module's params or ids.
- **Never call Depth Pro from this module.** It reads a pre-existing
  grayscale asset only (the asset-producer rule — AI-assisted inputs stay
  asset producers, never a resolve-path stage, per ARCHITECTURE.md "Far /
  undecided — AI-assisted inputs" and CLAUDE.md's open-questions note).
  Producing the depth asset in the first place is the EXISTING Depth Pro
  upload/generate flow — out of scope here.
- Every numeric param bounded; deterministic under `(params, seed)`; no
  live model calls inside `generate()`.
- When done: `docs/plans/perception-pass-RESULTS.md` with the acceptance
  screenshot's path (ideally showing the fat/hairline/dither contrast
  clearly — pick a source photo where it shows), the default values you
  settled on, and confirmation the test suite is green with `depth_pro`
  absent (run `pip uninstall` in a throwaway venv, or just grep-confirm no
  import path reaches it — your call, note which you did).

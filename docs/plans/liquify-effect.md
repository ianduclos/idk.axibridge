# Liquify — a soft-brush warp effect (loose plan, 2026-07-27)

Status: **not built, not committed to.** Ian raised it as a hypothetical
alongside the brush tool ("depth as parameter, perhaps even interp between two
separate liquifications if not too complicated"). This is the thinking from
that pass, written down so it doesn't have to be re-derived — deliberately a
loose plan like `hatch-connect-strokes-v2.md`, not a frozen brief like
`pen-brush-tools.md`. Mechanics are left to whoever picks it up; what's fixed
here is the architecture reasoning and the traps.

## What it is

Drag a soft circular brush over the canvas and the geometry under it deforms —
push (smear along the drag), twirl, pinch/swell. Photoshop's Liquify, on
polylines, in paper-space mm.

## The one genuinely new piece of plumbing

Every pointer-captured module so far — `drawing`, `pen`, `brush` — is a
**Source**. Liquify would be the first captured-input **Effect**. The params
side is identical (a hidden gesture list, `json_schema_extra={"hidden": True}`),
but the client differs: instead of POSTing `regenerate` on a layer's source,
the canvas mode PATCHes a step's params inside the layer's effect stack. That
is the only unfamiliar work in the whole idea; everything else has a precedent
already in the tree.

## Shape

```python
class WarpGesture(BaseModel):
    mode: Literal["push", "twirl", "pinch", "swell"] = "push"
    points: list[tuple[float, float]]   # the drag path, machine-frame mm
    radius: float                        # mm, soft brush radius
    strength: float                      # 0..1
```

Soft falloff: `w = (1 - (d/r)**2)**2`. Zero *with zero derivative* at the rim,
so the brush edge leaves no visible seam — that property is the whole reason
to prefer it over a linear ramp.

Three things come straight from existing patterns, and copying them is not
optional:

- **Densify before warping.** A long straight segment crossing a warp zone
  stays straight — this is the #1 practical gotcha. Already solved:
  `coherent_jitter._resample` is imported and reused by `depth_displace` with
  a `step` param described as "paths are resampled at this interval before
  displacement". Use it verbatim. (Adaptive subdivision only where the field
  varies is a later optimisation, not v1.)
- **Sequential fold, not a simultaneous sum.** Each gesture warps the
  already-warped result, which is what lets you push material a long way.
  Still pure and deterministic — just fold in stored order. Same rule the
  brush tool's paint/erase fold turns on; the symmetry is not a coincidence.
- **`anchor: layer | paper`.** `depth_displace` already carries exactly this
  param and for exactly this reason. Without it, moving a layer after
  liquifying slides its geometry through a warp field that stays put. That is
  a bench surprise waiting to happen.

Closure and `filled` are preserved **by construction** — a pure point map
sends `first == last` to the same place — so the effect contract is satisfied
without doing anything, and `test_effect_contract.py` will pick it up free.

## "Depth as parameter"

Read as a global **`amount` 0..1 scaling the whole displacement field**. This
is the load-bearing choice; everything else falls out of it:

- `amount = 0` must be **exactly** identity, not approximately. Assert it.
- Animating `amount` 0→1 over the master timeline gives "the liquify grows in"
  with **no new machinery** — effect params already lerp through
  `blend_effect_stacks`.
- It bounds the displacement, which matters for the self-intersection limit
  below.

*Alternative reading not chosen:* a depth-**map** asset modulating strength
per point, à la `depth_displace`'s `format:"asset"` param. Also easy, also
supported, but a different feature. Ian was not asked to disambiguate; if this
gets built, ask first.

## Interpolating two liquifications

The expected difficulty is **inverted here**, which is the most useful thing
in this document. A liquify is a *displacement field* — a function, not a
structure — so blending two is unconditional:

```
D_t(p) = (1-t)*D_A(p) + t*D_B(p)
```

That holds even when A and B have completely different gesture counts, radii
and modes. It is *strictly easier* than the captured-geometry morph already
shipped for pen/drawing shapes, which needs matching structure and steps at
0.5 otherwise.

**But the current machinery will not do it.** Checked 2026-07-27:
`blend_effect_stacks` (`tween.py:370`) only calls `lerp_params`. The
`_blend_geometry` deep-lerp was wired into `blend_generator_params` only, so
today a hidden gesture list on an *effect* would step at 0.5.

Two routes:

1. **Extend the core.** Apply `_geometry_param_fields` + `_blend_geometry` to
   effect params too, mirroring `blend_generator_params` exactly. Small diff,
   roughly the same shape as the 2026-07-21 change. Gives morphing when
   gesture structure matches, stepping when it doesn't — the same
   all-or-nothing rule as everywhere else in the codebase.
2. **Put A/B inside the effect** (`gestures_a`, `gestures_b`, `blend_t`).
   Self-contained, needs no tween change at all, and delivers the
   *unconditional* field blend route 1 can't.

**Route 2 is the trap, and route 1 is the answer.** Route 2 re-forks
interpolation inside a module, which is precisely what the 2026-07-19
unification exists to prevent — CLAUDE.md: *extend the core, never re-fork
it*. Take route 1 and accept that mismatched gesture counts step at 0.5 until
someone extends the core to blend fields properly. Do not let route 2's extra
capability win this argument; that is how the two interpolation instruments
drifted apart the first time.

## Two things worth knowing before building

- **Liquify inside a region layer warps only what is under the silhouette.**
  That combination works for free today and is probably the most interesting
  thing on this page.
- **Performance needs one shortcut**: bbox-reject per gesture (skip points
  outside the gesture's bounds + radius). Brushes are local, so this is cheap
  and removes nearly all the cost. Without it you are at
  points x gestures x gesture-points.

## The limit it cannot promise away

A strong warp can fold a filled polygon over itself, and `compose.build_mask`
polygonises filled paths. Bounding push distance to roughly one radius makes
folding unlikely but not impossible. This is a documented limit, not a
guarantee — say so in the module docstring rather than pretending otherwise.

## Shared with the brush

Both are pointer-captured, soft-radius, mm-space tools. `static/js/brush.js`
already has the circle cursor, the geometric `[` / `]` resize, the
capture-phase interception and the client-side live preview. Liquify's canvas
mode should reuse that code rather than growing a second copy — factor the
cursor out when the second user appears, not before.

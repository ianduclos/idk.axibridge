"""Vibrational modes of a plane region — the numerics behind ``eigen_fill``.

Sprinkle sand on a vibrating surface and it collects along the lines that are
not moving. Those are the **nodal lines** of that mode, and the pattern is not
imposed on the shape: it is *produced by* the shape. Change the boundary and
everything reorganises.

WHICH PHYSICS THIS IS, because the distinction is routinely glossed over and
the two look different on paper:

* a **clamped membrane** — a drumhead — is the second-order Dirichlet
  Laplacian eigenproblem, ``-Δu = λu`` with ``u = 0`` on the boundary. That is
  what this module solves.
* a **free plate** — the real Chladni case, a bowed metal sheet — is
  fourth-order (biharmonic) with free edges. Different figures, a genuinely
  harder problem, and the free boundary conditions on a rasterised irregular
  domain are exactly where it would go quietly wrong. Deliberately not
  attempted here; the label says "membrane" rather than claiming Chladni.

Three properties are what make this worth having over a hatch:

* **the mode index changes density AND character together**, unlike spacing,
  which only changes density;
* **degenerate modes.** A symmetric domain has repeated eigenvalues, and any
  combination of the eigenfunctions sharing a frequency is also a valid mode —
  which is physically why a square gives stars, crosses *and* flowers rather
  than one fixed figure. So the interesting control is not only which mode but
  how the degenerate ones are mixed (`mix_group`);
* **high modes on an irregular boundary** drift into the quantum-chaos regime
  (Berry's conjecture): tangled, organic, unrepeating — and entirely
  determined by the boundary. It looks like noise and is pure structure.

The solve is the expensive step and the mode index is a slider, so the whole
eigenbasis is cached (`_CACHE`): solve once, then scrubbing the mode and the
mix costs a scatter and a contour trace. ``k`` is bucketed so neighbouring
mode indices share one solve.

scipy is imported lazily — it is a real dependency of this repo (see
``sources/_lineart.py``) but the effect reports itself unavailable rather than
crashing the registry on a machine that somehow lacks it.
"""

from __future__ import annotations

import hashlib
import math
import threading
from collections import OrderedDict
from typing import Callable, NamedTuple

import numpy as np
from scipy import ndimage
from shapely.geometry import LineString, Polygon

from ..gencache import cache_budget_multiplier

#: Interior lattice nodes allowed before the pitch is coarsened. An effect
#: runs on every resolve of a stored project, so an over-fine pitch on a
#: bed-sized shape must degrade the pattern, never hang the tool.
MAX_NODES = 40_000

#: Hard ceiling on solved modes, and the per-node budget under it. Resolving
#: mode m needs on the order of m cells across the domain, so asking for mode
#: 200 on a 26x26 lattice is not a request the discretisation can honour —
#: capping by ``N // 12`` refuses it in the honest place rather than returning
#: lattice noise dressed as a high mode.
MAX_MODES = 256
NODES_PER_MODE = 12

#: k is rounded up to a multiple of this before solving, so dragging the mode
#: slider through 1..16 is ONE solve rather than sixteen.
K_BUCKET = 16

#: Cached eigenbasis floats (vectors are float32) before LRU eviction. Scaled
#: by the same AXIBRIDGE_CACHE_BUDGET multiplier as every other cache, so the
#: Pi's 0.25 applies here too.
CACHE_BUDGET_FLOATS = 12_000_000
CACHE_MAX_ENTRIES = 16

#: How far past the boundary the mode field is extended before contouring.
#: Zeroing the outside instead would put a contour crossing on every cell
#: where a negative nodal domain meets the edge, i.e. a traced line running
#: along the outline itself — ink the drawing never asked for. Holding the
#: nearest interior value for a couple of cells and zeroing beyond that moves
#: that crossing safely OUTSIDE the shape, where clipping discards it, and
#: leaves the interior nodal lines running right up to the boundary, which is
#: where they genuinely end.
EXTEND_CELLS = 2

#: Gaussian smoothing (in lattice cells) applied to the field before it is
#: contoured. Fixes one artefact only: the held extension outside the domain
#: is piecewise constant, so every non-zero level staircases along the
#: outline without it. Deliberately not a user param — it is a discretisation
#: fix, not a look.
EDGE_SMOOTH = 0.6

#: A gap this much smaller than the local median gap counts as "the same
#: frequency". Discretisation splits what should be exactly repeated
#: eigenvalues, so an exact test finds nothing; an ABSOLUTE tolerance fails
#: the other way at high modes, where Weyl's law shrinks the spacing between
#: genuinely distinct modes to O(lambda / k). A local median adapts to both
#: ends of the spectrum.
DEGENERACY_GAP = 0.25
GAP_WINDOW = 9


def available() -> tuple[bool, str]:
    try:
        import scipy.sparse.linalg  # noqa: F401
    except Exception as e:  # pragma: no cover - scipy is installed on both benches
        return False, f"needs scipy ({e})"
    return True, ""


class Basis(NamedTuple):
    """A solved eigenbasis on a lattice, plus what it takes to place it."""

    mask: np.ndarray            # (ny, nx) bool — interior nodes
    index: np.ndarray           # (ny, nx) int32 — row in `vecs`, -1 outside
    extend: np.ndarray          # (ny, nx) int32 — nearest interior row within
                                #   EXTEND_CELLS of the domain, -1 beyond
    pitch: float                # effective lattice pitch in mm (may be coarsened)
    origin: tuple[float, float] # mm position of node (0, 0)
    values: np.ndarray          # (k,) eigenvalues, ascending
    vectors: np.ndarray         # (N, k) float32, columns matching `values`
    groups: list[tuple[int, int]]  # [start, stop) index ranges of degenerate modes
    settled: set[int]           # groups already canonicalised (done lazily)


# -- rasterising the domain ----------------------------------------------------


def _slices(poly: Polygon, lo: float, hi: float, at: np.ndarray,
            count: int, pitch: float, vertical: bool) -> np.ndarray:
    """Strict inside-the-interval mask for `count` scanlines across `poly`.

    Row `r` of the result is the lattice along the scan direction; a node is
    marked only if it falls STRICTLY between the ends of an intersection
    interval, which is the Dirichlet condition (u = 0 on the boundary) stated
    as a mask.
    """
    out = np.zeros((count, len(at)), dtype=bool)
    eps = pitch * 1e-6
    for r in range(count):
        c = lo + r * pitch
        line = LineString([(lo - 1.0, c), (hi + 1.0, c)] if not vertical
                          else [(c, lo - 1.0), (c, hi + 1.0)])
        hit = poly.intersection(line)
        if hit.is_empty:
            continue
        for part in getattr(hit, "geoms", [hit]):
            if not isinstance(part, LineString) or part.is_empty:
                continue
            x0, y0, x1, y1 = part.bounds
            a, b = (y0, y1) if vertical else (x0, x1)
            out[r] |= (at > a + eps) & (at < b - eps)
    return out


def rasterise(poly: Polygon, pitch: float) -> tuple[np.ndarray, float, tuple[float, float]]:
    """Interior-node mask for `poly` on a `pitch`-mm lattice.

    Scanline fill through shapely (the same row-intersection trick
    ``hatch_fill._hatch`` uses) rather than a prepared point-in-polygon test
    per node, which would be tens of thousands of shapely calls per resolve.

    Scanned along BOTH axes and AND-ed, which is not belt-and-braces: a
    horizontal boundary edge lying exactly ON a scanline intersects it along
    its whole length, so a rows-only pass reads that entire edge as interior
    and a rectangle comes out one row too tall (its spectrum then splits
    degenerate pairs that should be identical, which is how this was caught).
    A strictly interior point is strictly inside its interval on both axes, so
    the AND drops the boundary without dropping anything real.

    Holes need no special case: a shapely interior is simply not in the
    intersection, and that is also the correct physics — a clamped membrane is
    pinned along EVERY boundary it has, inner rings included.
    """
    minx, miny, maxx, maxy = poly.bounds
    width, height = maxx - minx, maxy - miny
    mask = np.zeros((1, 1), dtype=bool)
    for _ in range(8):
        nx = int(math.floor(width / pitch + 1e-9)) + 1
        ny = int(math.floor(height / pitch + 1e-9)) + 1
        if nx < 3 or ny < 3:
            return np.zeros((max(ny, 1), max(nx, 1)), dtype=bool), pitch, (minx, miny)
        xs = minx + np.arange(nx) * pitch
        ys = miny + np.arange(ny) * pitch
        rows = _slices(poly, minx, maxx, xs, ny, pitch, vertical=False)
        cols = _slices(poly, miny, maxy, ys, nx, pitch, vertical=True)
        mask = rows & cols.T
        count = int(mask.sum())
        if count <= MAX_NODES:
            return mask, pitch, (minx, miny)
        # Coarsen and try again: node count scales as 1/pitch^2, and the 1.05
        # keeps a borderline case from needing a second pass.
        pitch *= 1.05 * math.sqrt(count / MAX_NODES)
    return mask, pitch, (minx, miny)


def node_coords(basis_mask: np.ndarray, pitch: float,
                origin: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    """(x, y) in mm for each interior node, in row-major mask order."""
    js, iss = np.nonzero(basis_mask)
    return origin[0] + iss * pitch, origin[1] + js * pitch


# -- the operator --------------------------------------------------------------


def _laplacian(mask: np.ndarray, index: np.ndarray, pitch: float):
    """Sparse 5-point Dirichlet Laplacian over the interior nodes.

    A neighbour outside the mask contributes nothing, which IS the boundary
    condition: its value is zero, so its term vanishes from the stencil. The
    matrix is symmetric positive definite, which is what lets the solve use a
    shift-invert factorisation at sigma = 0.
    """
    from scipy import sparse

    n = int(mask.sum())
    rows = [np.arange(n)]
    cols = [np.arange(n)]
    data = [np.full(n, 4.0)]
    for shift, axis in ((1, 0), (-1, 0), (1, 1), (-1, 1)):
        neigh = np.roll(index, shift, axis=axis)
        # a wrapped edge is not a neighbour
        if axis == 0:
            (neigh[0] if shift == 1 else neigh[-1]).fill(-1)
        else:
            (neigh[:, 0] if shift == 1 else neigh[:, -1]).fill(-1)
        here, there = index[mask], neigh[mask]
        ok = there >= 0
        rows.append(here[ok])
        cols.append(there[ok])
        data.append(np.full(int(ok.sum()), -1.0))
    a = sparse.coo_matrix(
        (np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, n),
    ).tocsr()
    return a * (1.0 / (pitch * pitch))


# -- the solve -----------------------------------------------------------------


def _probe(n: int, which: int) -> np.ndarray:
    """A fixed pseudo-random vector. Deterministic in (n, which) so a rerun,
    a reload and another machine all agree — the effect contract test checks
    exactly this."""
    return np.random.default_rng(20260821 + which).standard_normal(n)


def _solve(a, rho: np.ndarray | None, k: int) -> tuple[np.ndarray, np.ndarray] | None:
    """The k lowest membrane modes. Returns (values, vectors) or None."""
    from scipy import sparse
    from scipy.sparse.linalg import ArpackNoConvergence, eigsh

    n = a.shape[0]
    m = sparse.diags(rho) if rho is not None else None
    try:
        # Shift-invert at sigma=0 rather than which="SM": ARPACK converges to
        # the LARGEST eigenvalues of A^-1, which are the smallest of A, and
        # plain "SM" would never reach mode 200 in interactive time.
        # v0 is fixed because ARPACK's default start vector is RANDOM, which
        # would make this effect nondeterministic.
        vals, vecs = eigsh(a, k=k, M=m, sigma=0.0, which="LM", v0=_probe(n, 0))
    except ArpackNoConvergence as e:
        vals, vecs = e.eigenvalues, e.eigenvectors
        if vals is None or len(vals) < 2:
            return None
    except Exception:
        return None
    order = np.argsort(vals)
    vals, vecs = np.asarray(vals)[order], np.asarray(vecs)[:, order]
    # An eigenvector's SIGN is arbitrary — pin it so the same shape always
    # draws the same picture. Scale to unit peak so `mix` blends comparable
    # amplitudes (the zero set is scale-invariant, the blend is not).
    for c in range(vecs.shape[1]):
        v = vecs[:, c]
        peak = int(np.argmax(np.abs(v)))
        if v[peak] < 0:
            v *= -1.0
        big = abs(v[peak])
        if big > 0:
            v /= big
    return vals, vecs.astype(np.float32)


def _groups(values: np.ndarray) -> list[tuple[int, int]]:
    """Index ranges of near-degenerate modes — see DEGENERACY_GAP."""
    k = len(values)
    if k < 2:
        return [(0, k)]
    gaps = np.diff(values)
    half = GAP_WINDOW // 2
    out: list[tuple[int, int]] = []
    start = 0
    for i, gap in enumerate(gaps):
        local = gaps[max(0, i - half): i + half + 1]
        median = float(np.median(local)) if len(local) else 0.0
        if gap > DEGENERACY_GAP * median:
            out.append((start, i + 1))
            start = i + 1
    out.append((start, k))
    return out


def _crossings(b: "Basis", u: np.ndarray) -> int:
    """Lattice edges the zero set crosses — a stand-in for nodal line length
    that costs one vectorised pass instead of a contour trace."""
    field = np.zeros(b.mask.shape)
    field[b.mask] = u
    s = np.sign(field) * b.mask
    return int(((s[:, :-1] * s[:, 1:]) < 0).sum() + ((s[:-1] * s[1:]) < 0).sum())


def _settle(b: "Basis", group: int) -> None:
    """Fix the basis of one degenerate group, in place, once.

    Any rotation of a degenerate group is an equally valid eigenbasis, so
    ARPACK's choice is arbitrary — and arbitrary means two things go wrong:
    the mix = 0 picture is an accidental superposition rather than the clean
    figure the shape is known for, and the basis jumps whenever the boundary
    is nudged, so ``mix`` stops meaning the same thing between edits.

    The criterion is **least ink**: rotate the group to minimise the total
    nodal length. On a square's degenerate pair that lands on the two single
    straight lines rather than the curved diagonal combinations, so mix = 0 is
    the figure the shape is known for and the knob sweeps out to the others.
    (Quartimax, the textbook "simplest structure" rotation, was tried first
    and prefers the diagonals — it maximises concentration, which is not the
    same question as which picture a pen would rather draw.)

    Done lazily per group because the sweep costs a pass over the lattice per
    trial angle, and a 208-mode solve has a hundred groups the user will never
    look at.
    """
    lo, hi = b.groups[group]
    g = hi - lo
    if g < 2 or group in b.settled:
        b.settled.add(group)
        return
    v = b.vectors[:, lo:hi].astype(np.float64)

    def rotate(a: int, c: int, theta: float) -> tuple[np.ndarray, np.ndarray]:
        cs, sn = math.cos(theta), math.sin(theta)
        return cs * v[:, a] + sn * v[:, c], -sn * v[:, a] + cs * v[:, c]

    for _ in range(3):
        moved = False
        for a in range(g - 1):
            for c in range(a + 1, g):
                # coarse sweep then one refinement — the objective is a smooth
                # function of the angle with a quarter-turn period
                best, best_theta = None, 0.0
                for step, span, centre in ((math.pi / 36, math.pi / 2, 0.0),
                                           (math.pi / 360, math.pi / 18, None)):
                    origin = best_theta if centre is None else centre
                    theta = origin - span / 2
                    while theta <= origin + span / 2 + 1e-12:
                        x, y = rotate(a, c, theta)
                        score = _crossings(b, x) + _crossings(b, y)
                        if best is None or score < best:
                            best, best_theta = score, theta
                        theta += step
                if abs(best_theta) > 1e-6:
                    v[:, a], v[:, c] = rotate(a, c, best_theta)
                    moved = True
        if not moved:
            break

    # Order (simplest first) and sign still have to be pinned or they wobble
    # on float dust; the probe only breaks ties between equally simple figures.
    probe = _probe(v.shape[0], 1)
    rank = sorted(range(g), key=lambda c: (_crossings(b, v[:, c]),
                                           -abs(float(v[:, c] @ probe))))
    v = v[:, rank]
    for col in range(g):
        peak = int(np.argmax(np.abs(v[:, col])))
        if v[peak, col] < 0:
            v[:, col] *= -1.0
        big = abs(v[peak, col])
        if big > 0:
            v[:, col] /= big
    b.vectors[:, lo:hi] = v.astype(np.float32)
    b.settled.add(group)


# -- the cache -----------------------------------------------------------------

_lock = threading.Lock()
_CACHE: "OrderedDict[str, Basis]" = OrderedDict()


def _evict() -> None:
    budget = CACHE_BUDGET_FLOATS * cache_budget_multiplier()
    while _CACHE and (len(_CACHE) > CACHE_MAX_ENTRIES
                      or sum(b.vectors.size for b in _CACHE.values()) > budget):
        _CACHE.popitem(last=False)


def clear_cache() -> None:
    with _lock:
        _CACHE.clear()


def basis(poly: Polygon, pitch: float, wanted: int,
          density: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None
          ) -> Basis | None:
    """Solve (or recall) enough modes of `poly` to reach mode `wanted`.

    `density` maps node coordinates to a mass per node — the generalised
    problem ``-Δu = λ ρ u``, i.e. a membrane whose weight varies from place to
    place. Heavier means slower means shorter wavelength, so nodal lines bunch
    where the density is high and low modes localise there. None is the plain
    uniform membrane and skips the generalised solve entirely.

    The cache is keyed on the sampled arrays themselves rather than on the
    parameters that produced them, so no key-design mistake can serve a stale
    pattern for a changed image.
    """
    mask, pitch, origin = rasterise(poly, pitch)
    n = int(mask.sum())
    if n < 9:
        return None
    index = np.full(mask.shape, -1, dtype=np.int32)
    index[mask] = np.arange(n, dtype=np.int32)
    dist, near = ndimage.distance_transform_edt(~mask, return_indices=True)
    extend = np.where(dist <= EXTEND_CELLS, index[near[0], near[1]], -1).astype(np.int32)

    rho = None
    if density is not None:
        xs, ys = node_coords(mask, pitch, origin)
        rho = np.asarray(density(xs, ys), dtype=np.float64)
        rho = np.clip(rho, 1e-3, 1e3)

    ceiling = min(MAX_MODES, max(4, n // NODES_PER_MODE), n - 2)
    k = min(ceiling, K_BUCKET * math.ceil(max(wanted, 2) / K_BUCKET))

    h = hashlib.blake2b(digest_size=16)
    h.update(np.ascontiguousarray(mask).tobytes())
    h.update(np.array([mask.shape[0], mask.shape[1], k], dtype=np.int64).tobytes())
    h.update(np.array([pitch], dtype=np.float64).tobytes())
    if rho is not None:
        h.update(np.ascontiguousarray(rho.astype(np.float32)).tobytes())
    key = h.hexdigest()

    with _lock:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return hit

    solved = _solve(_laplacian(mask, index, pitch), rho, k)
    if solved is None:
        return None
    values, vectors = solved
    groups = _groups(values)
    out = Basis(mask, index, extend, pitch, origin, values, vectors, groups, set())

    with _lock:
        _CACHE[key] = out
        _CACHE.move_to_end(key)
        _evict()
    return out


# -- picking a mode ------------------------------------------------------------


def mix_group(b: Basis, mode: int) -> tuple[int, int]:
    """(mode index, partner index), both 0-based and clamped into the solved
    range. The partner is the next member of the same degenerate group when
    there is one — that combination is a genuine mode of the same frequency,
    which is why a square plate has a family of figures rather than one. With
    no degenerate partner the next mode up is used instead: not a stationary
    mode, but a legible chord, and it keeps the knob alive on every shape."""
    k = len(b.values)
    m = max(0, min(mode - 1, k - 1))
    for g, (lo, hi) in enumerate(b.groups):
        if lo <= m < hi:
            with _lock:
                _settle(b, g)
            return (m, m + 1) if m + 1 < hi else (m, min(m + 1, k - 1))
    return m, min(m + 1, k - 1)


def _blend(b: Basis, mode: int, mix: float, spread: int = 0) -> np.ndarray:
    """The scalar field over the interior nodes, peak-normalised.

    ``spread`` rings the shape at several frequencies at once instead of
    holding it at one: modes m..m+spread summed with decaying weights, which
    is what a struck plate does. It breaks the schematic symmetry a single
    mode has, at no extra solve — the modes are already in the basis.
    """
    m, partner = mix_group(b, mode)
    theta = float(np.clip(mix, -1.0, 1.0)) * (math.pi / 4.0)
    u = math.cos(theta) * b.vectors[:, m].astype(np.float64)
    if partner != m:
        u = u + math.sin(theta) * b.vectors[:, partner]
    for j in range(1, max(spread, 0) + 1):
        c = m + j
        if c >= b.vectors.shape[1]:
            break
        u = u + b.vectors[:, c].astype(np.float64) / (1.0 + j)
    peak = float(np.max(np.abs(u)))
    return u / peak if peak > 0 else u


def mode_field(b: Basis, mode: int, mix: float, spread: int = 0) -> np.ndarray:
    """The field on the lattice, zero outside the domain."""
    field = np.zeros(b.mask.shape, dtype=np.float64)
    field[b.mask] = _blend(b, mode, mix, spread)
    return field


def contour_levels(count: int, bias: float, magnitude: bool) -> list[float]:
    """Which level sets to trace, over a field normalised to peak 1.

    The zero set alone is a **thin** set — Courant caps the n-th mode at n
    nodal domains, so it can only ever be a dozen or so strokes with a lot of
    white between them. The other level sets of the same mode are just as much
    a product of the boundary, and they nest into long continuous closed
    curves, so tracing a family is what turns this from a partition into a
    fill. ``count = 1`` is the bare nodal set, unchanged.

    ``bias`` crowds the levels toward zero, i.e. toward the nodal lines: at 0
    they are evenly spread and every lobe shades alike; at 1 they pile onto the
    nodal figure, which stays legible as a dark ridge while the lobes open out.
    """
    count = max(1, count)
    if not magnitude and count % 2 == 0:
        # the nodal set is the point of the whole effect, so it is always one
        # of the traced levels — which means an odd count, symmetric about 0
        count += 1
    power = 1.0 + 3.0 * float(np.clip(bias, 0.0, 1.0))
    if magnitude:
        # |u|: every level is a closed band around the nodal set, so low
        # levels hug it. Start above 0 (the nodal set itself is measure-zero
        # for |u| and would trace as a doubled line).
        return [float(((i + 1) / (count + 1)) ** power) for i in range(count)]
    if count == 1:
        return [0.0]
    spread = np.linspace(-1.0, 1.0, count + 2)[1:-1]
    return [float(math.copysign(abs(s) ** power, s)) for s in spread]


def contour_field(b: Basis, mode: int, mix: float, spread: int = 0,
                  magnitude: bool = False
                  ) -> tuple[list[list[float]], tuple[float, float]]:
    """The field as ``marching.trace_contours`` wants it, plus the mm position
    of its (0, 0) cell.

    Three things happen here that ``mode_field`` does not do:

    * the values are **held past the boundary** for ``EXTEND_CELLS``, so a
      contour crossing lands outside the shape where the clip discards it
      rather than running along the outline (see above);
    * the lattice gets a **two-cell ring of padding whose outermost row is
      forced to zero after the smoothing**, because a contour that does not
      close is dropped by the tracer, and the padding is what closes the ones
      touching the lattice edge. Zeroing before the blur is not enough: the
      blur pulls interior values out into the ring, a negative lobe then
      reaches the lattice edge, its contour never closes, and the level is
      silently dropped — which is exactly what happened, and why
      ``test_the_nodal_set_is_always_drawn`` asserts it comes back non-empty;
    * the whole thing is **smoothed by ``EDGE_SMOOTH``** before tracing. The
      held extension is piecewise constant over the boundary nodes' cells, so
      without it every non-zero level visibly staircases along the outline —
      the lattice showing through. Well under a cell, so interior structure is
      untouched; the alternative (clipping a further pitch inward) only traded
      the staircase for ragged line ends.

    ``magnitude`` contours the stillness |u| instead of the displacement:
    closed bands hugging the nodal set, which is what the sand on a real plate
    piles into. Taken after the blur, so the fold at zero stays sharp.
    """
    u = _blend(b, mode, mix, spread)
    ny, nx = b.mask.shape
    pad = 2
    padded = np.zeros((ny + 2 * pad, nx + 2 * pad))
    padded[pad:-pad, pad:-pad] = np.where(b.extend >= 0, u[np.maximum(b.extend, 0)], 0.0)
    padded = ndimage.gaussian_filter(padded, EDGE_SMOOTH)
    if magnitude:
        padded = np.abs(padded)
    padded[0, :] = padded[-1, :] = padded[:, 0] = padded[:, -1] = 0.0
    return padded.tolist(), (b.origin[0] - pad * b.pitch, b.origin[1] - pad * b.pitch)

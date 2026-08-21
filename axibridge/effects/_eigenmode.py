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
    pitch: float                # effective lattice pitch in mm (may be coarsened)
    origin: tuple[float, float] # mm position of node (0, 0)
    values: np.ndarray          # (k,) eigenvalues, ascending
    vectors: np.ndarray         # (N, k) float32, columns matching `values`
    groups: list[tuple[int, int]]  # [start, stop) index ranges of degenerate modes


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


def _canonicalise(vectors: np.ndarray, groups: list[tuple[int, int]]) -> None:
    """Fix the basis WITHIN each degenerate group, in place.

    Any rotation of a degenerate group is an equally valid eigenbasis, so
    ARPACK's choice is arbitrary and jumps when the shape is nudged — which
    would make ``mix`` mean something different every time. Rotating the group
    so its first vector maximises overlap with a fixed probe makes the knob
    stable across edits.
    """
    for lo, hi in groups:
        if hi - lo < 2:
            continue
        v = vectors[:, lo:hi]
        p = _probe(v.shape[0], 1).astype(np.float32)
        c = v.T @ p
        norm = float(np.linalg.norm(c))
        if norm <= 1e-12:
            continue
        first = v @ (c / norm)
        rest = v - np.outer(first, first @ v) / max(float(first @ first), 1e-12)
        q, _ = np.linalg.qr(rest)
        block = [first]
        for col in range(hi - lo - 1):
            u = q[:, col]
            if float(u @ _probe(v.shape[0], 2 + col).astype(np.float32)) < 0:
                u = -u
            block.append(u)
        stacked = np.stack(block, axis=1)
        for col in range(stacked.shape[1]):
            big = float(np.max(np.abs(stacked[:, col])))
            if big > 0:
                stacked[:, col] /= big
        vectors[:, lo:hi] = stacked


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
    _canonicalise(vectors, groups)
    out = Basis(mask, index, pitch, origin, values, vectors, groups)

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
    for lo, hi in b.groups:
        if lo <= m < hi and m + 1 < hi:
            return m, m + 1
    return m, min(m + 1, k - 1)


def mode_field(b: Basis, mode: int, mix: float) -> np.ndarray:
    """The scalar field on the lattice, zero outside the domain.

    ``mix`` runs -1..+1 and rotates by up to a quarter turn into the partner
    mode, so +1 and -1 give ``u1 + u2`` and ``u1 - u2`` — the two different
    figures a symmetric domain shows at one frequency, and the reason the knob
    is signed rather than 0..1.
    """
    m, partner = mix_group(b, mode)
    theta = float(np.clip(mix, -1.0, 1.0)) * (math.pi / 4.0)
    u = math.cos(theta) * b.vectors[:, m]
    if partner != m:
        u = u + math.sin(theta) * b.vectors[:, partner]
    field = np.zeros(b.mask.shape, dtype=np.float64)
    field[b.mask] = u
    return field

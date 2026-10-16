"""Clothoid-alphabet fits of a few synthetic strokes, one figure per stroke.

Top: the input points (grey) and the fit re-integrated with
clothoid.reconstruct, rigidly aligned onto the smoothed stroke and coloured
by segment kind; corners as red rings. Bottom: κ(s) measured
(curvature.kappa_s, grey) against the fitted piecewise-linear κ (coloured by
kind), corners as red verticals, and the ground truth where known (dashed).

Writes PNGs and a segment_stats JSON to .local/gesture/out/clothoid/.

    cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.clothoid_demo
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from gesture.clothoid import Fit, fit_stroke, reconstruct, segment_stats  # noqa: E402
from gesture.curvature import arclength, integrate_kappa, kappa_s, resample  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / ".local" / "gesture" / "out" / "clothoid"

# Flexoki (axibridge/static/css/flexoki.css), light roles
PAPER, INK = "#FFFCF0", "#100F0F"
GREY, GREY_LIGHT = "#878580", "#B7B5AC"
KIND_COLOUR = {"line": "#205EA6", "arc": "#66800B", "clothoid": "#BC5215"}  # blue/green/orange-600
CORNER = "#AF3029"                                                          # red-600


def _strokes(rng: np.random.Generator):
    """(name, points, sigma, closed, truth (breaks, kappas) or None)."""
    out = []
    b = np.array([0, 80, 150, 260, 330, 420, 500.0])
    k = np.array([0, 0, 0.025, 0.025, -0.015, -0.015, 0])
    p = integrate_kappa(b, k, 1.0)
    out.append(("g2_sequence_noise0.5", p + rng.normal(0, 0.5, p.shape), 5.0, False, (b, k)))

    b = np.array([0, 70, 160, 230, 330, 420, 480, 600, 700.0])
    k = np.array([0, -0.012, -0.012, 0.0, 0.0, 0.02, 0.02, -0.008, 0.004])
    p = integrate_kappa(b, k, 1.0)
    out.append(("eight_segments_noise0.3", p + rng.normal(0, 0.3, p.shape), 4.0, False, (b, k)))

    a = integrate_kappa(np.array([0, 160.0]), np.array([0.012, 0.012]), 1.0)
    h = np.arctan2(*(a[-1] - a[-2])[::-1]) - np.deg2rad(110)
    m = integrate_kappa(np.array([0, 140.0]), np.array([0.0, 0.0]), 1.0, start=a[-1], heading=h)
    h2 = h + np.deg2rad(70)
    c = integrate_kappa(np.array([0, 180.0]), np.array([0.0, -0.025]), 1.0, start=m[-1], heading=h2)
    p = np.vstack([a, m[1:], c[1:]])
    out.append(("corners_noise0.3", p + rng.normal(0, 0.3, p.shape), 3.0, False, None))

    cc = 2 * np.pi / 300.0
    b = np.array([0, 100, 150, 250, 300, 400, 450, 550, 600.0])
    k = np.array([0, 0, cc, cc, 0, 0, cc, cc, 0])
    p = integrate_kappa(b, k, 1.0)[:-1]
    out.append(("closed_stadium_noise0.5", p + rng.normal(0, 0.5, p.shape), 5.0, True, (b, k)))

    s = np.linspace(0, 700, 1401)
    kap = 0.012 * np.sin(s / 55.0) + 0.008 * np.sin(s / 23.0 + 1.0)       # not in the alphabet
    p = integrate_kappa(s, kap, 1.0)
    out.append(("smooth_random_kappa_noise0.3", p + rng.normal(0, 0.3, p.shape), 4.0, False,
                (s, kap)))
    return out


def _aligned(fit: Fit, sm: np.ndarray, closed: bool) -> tuple[np.ndarray, np.ndarray]:
    """Reconstructed fit (and its s values) rigidly aligned onto sm, matching
    points by fractional arc length (for display only)."""
    rec = reconstruct(fit)
    srec = arclength(rec)
    ssm = arclength(np.vstack([sm, sm[:1]]) if closed else sm)
    ref = np.vstack([sm, sm[:1]]) if closed else sm
    f = srec / max(srec[-1], 1e-9)
    if closed:   # the fit starts at segments[0].s0, not at sm[0]
        f = (f + (fit.segments[0].s0 % fit.length) / fit.length) % 1.0
    t = f * ssm[-1]
    corr = np.column_stack([np.interp(t, ssm, ref[:, 0]), np.interp(t, ssm, ref[:, 1])])
    mc, mr = rec.mean(axis=0), corr.mean(axis=0)
    U, _, Vt = np.linalg.svd((rec - mc).T @ (corr - mr))
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, d]) @ U.T
    return (rec - mc) @ R.T + mr, srec + fit.segments[0].s0


def _plot(name: str, pts: np.ndarray, sigma: float, closed: bool, truth, fit: Fit) -> Path:
    s_m, k_m, sm = kappa_s(pts, sigma, closed=closed)
    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(9, 10), gridspec_kw={"height_ratios": [3, 2]},
                                   facecolor=PAPER)
    for ax in (ax0, ax1):
        ax.set_facecolor(PAPER)
        for sp in ax.spines.values():
            sp.set_color(GREY)
        ax.tick_params(colors=INK, labelsize=8)

    ax0.plot(pts[:, 0], pts[:, 1], ".", ms=1.5, color=GREY_LIGHT, zorder=1)
    rec, srec = _aligned(fit, sm, closed)
    for g in fit.segments:
        sel = (srec >= g.s0 - 1e-6) & (srec <= g.s1 + 1e-6)
        ax0.plot(rec[sel, 0], rec[sel, 1], "-", lw=2.2, color=KIND_COLOUR[g.kind], zorder=2,
                 solid_capstyle="butt")
    for c in fit.corners:
        i = int(np.argmin(np.abs((srec - c + fit.length / 2) % fit.length - fit.length / 2)
                          if closed else np.abs(srec - c)))
        ax0.plot(rec[i, 0], rec[i, 1], "o", ms=9, mfc="none", mec=CORNER, mew=1.5, zorder=3)
    ax0.set_aspect("equal")
    ax0.invert_yaxis()
    kinds = fit.kinds()
    ax0.set_title(f"{name}   σ={sigma:g}   {len(kinds)} segments "
                  f"({kinds.count('line')} line, {kinds.count('arc')} arc, "
                  f"{kinds.count('clothoid')} clothoid), {len(fit.corners)} corners   "
                  f"pos err {fit.rms_position_error:.2f} px",
                  fontsize=9, color=INK, loc="left")
    handles = [plt.Line2D([], [], color=c, lw=2.2, label=k) for k, c in KIND_COLOUR.items()]
    handles.append(plt.Line2D([], [], color=CORNER, marker="o", ls="", mfc="none", label="corner"))
    ax0.legend(handles=handles, loc="best", fontsize=8, frameon=False, labelcolor=INK)

    # κ(s): measured on the raw parameter, rescaled to the fit's arc length
    s_scaled = s_m * fit.length / max(s_m[-1] + (s_m[1] if closed else 0.0), 1e-9)
    ax1.plot(s_scaled, k_m, "-", lw=0.8, color=GREY, label="measured κ (kappa_s)")
    if truth is not None:
        tb, tk = truth
        ax1.plot(tb, tk, "--", lw=1.0, color=INK, label="truth")
    for g in fit.segments:
        x0 = g.s0 - (g.s0 // fit.length) * fit.length if closed else g.s0
        for shift in ((0.0, -fit.length) if closed else (0.0,)):   # closed: wrapped copy
            ax1.plot([x0 + shift, x0 + g.length + shift], [g.k0, g.k1], "-", lw=2.4,
                     color=KIND_COLOUR[g.kind])
    for c in fit.corners:
        ax1.axvline(c % fit.length if closed else c, color=CORNER, lw=1.0)
    lo, hi = np.percentile(k_m, [1, 99])
    span = max(hi - lo, 1e-3)
    ax1.set_ylim(lo - 0.3 * span, hi + 0.3 * span)
    ax1.set_xlim(0, fit.length)
    ax1.set_xlabel("s (px along the smoothed stroke)", fontsize=8, color=INK)
    ax1.set_ylabel("κ (1/px)", fontsize=8, color=INK)
    ax1.legend(loc="upper right", fontsize=8, frameon=False, labelcolor=INK)
    ax1.axhline(0, color=GREY_LIGHT, lw=0.6)
    fig.tight_layout()
    path = OUT / f"{name}.png"
    fig.savefig(path, dpi=110, facecolor=PAPER)
    plt.close(fig)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2026)
    fits = []
    for name, pts, sigma, closed, truth in _strokes(rng):
        fit = fit_stroke(pts, sigma=sigma, closed=closed)
        fits.append(fit)
        path = _plot(name, pts, sigma, closed, truth, fit)
        print(f"{name:32s} {len(fit.segments):2d} seg  {''.join(k[0] for k in fit.kinds()):12s}"
              f" corners={len(fit.corners)}  rms κ={fit.rms_kappa_error:.1e}"
              f"  pos={fit.rms_position_error:.2f}px  turn_tol={np.rad2deg(fit.turn_tol):.1f}°"
              f"  → {path.name}")
    allp = np.vstack([np.asarray(p) for _n, p, *_ in _strokes(np.random.default_rng(2026))])
    span = allp.max(axis=0) - allp.min(axis=0)
    stats = segment_stats(fits, float(np.hypot(*span)))
    (OUT / "segment_stats.json").write_text(json.dumps(stats, indent=1))
    print(f"wrote {OUT / 'segment_stats.json'}")


if __name__ == "__main__":
    main()

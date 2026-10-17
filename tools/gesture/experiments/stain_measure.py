"""Mass from real stains — measurement (round 12, thread 3, 2026-10-17).

    .local/gesture/.venv/bin/python tools/gesture/experiments/stain_measure.py [--limit N]

The Fabric Stain Dataset (CC0, 466 photos, 398 with stains) carries only
bounding boxes, no masks. Each box is segmented here by its own darkness
against a plane fitted to the box's border, after blurring away the weave at
the weave's own period (measured from the photo's spectrum).

What is measured, per stain (the things that make a stain a stain and not a
blob a hand would make):

  weave      the two strongest weave directions (spectral peaks) and period
  aniso      front radius along the weave axes / along the diagonals between
             them (wicking runs ahead along threads)
  modes      |c_k| / c_0 of the outer front's radius function r(θ), k = 1..8
             (k = 2 elongation, k = 4 the weave cross)
  rough      std of the front's radius after removing modes ≤ 6, ÷ mean R
  rough_slope log-log slope of the front's radius spectrum (k = 6 … 40)
  rim        darkness in the outer band (s = 0.75 … 1.0 of R(θ)) ÷ darkness in
             the core (s < 0.5): > 1 is a tide line
  rim_arc    share of angles where the rim is darker than the core × 1.15 —
             a full ring (≈ 1) vs a crescent (≈ 0.3)
  rim_w      tide-line thickness: width of the darkness peak near the edge, ÷ R
  spacing    where the iso-darkness fronts sit, as radius fractions: equal
             spacing would be a topographic cone; crowding at the edge a tide
  sat_n/d/a  satellite blots: count, distance (÷ R), area (÷ main area)
  open       share of the front's angular extent that is missing (a stain
             that fails to close — the darkness ring is broken)

Outputs .local/gesture/out/stain/measure.json and overlays/. The measurement
digests the stains into numbers; nothing here is a traced form that a drawing
reuses.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / ".local/gesture/corpus/fabric/fabric-stain-dataset/extracted/ds"
OUT = ROOT / ".local/gesture/out/stain"

N_ANG = 180
S_BINS = np.linspace(0.0, 1.3, 27)


def _key(name: str) -> int:
    return int(re.findall(r"\d+", name)[0])


def stain_boxes():
    """(image name, box) for every stain box, in a fixed order."""
    out = []
    for ann in sorted((CORPUS / "ann").glob("stain_*.json"), key=lambda p: _key(p.name)):
        a = json.loads(ann.read_text())
        for j, o in enumerate(a["objects"]):
            (x0, y0), (x1, y1) = o["points"]["exterior"]
            out.append((ann.name[:-5], j, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))))
    return out


def weave(gray: np.ndarray) -> dict:
    """Weave period and the two strongest thread directions from the spectrum."""
    g = gray - ndi.gaussian_filter(gray, 12)
    h, w = g.shape
    n = min(h, w, 512) // 2 * 2
    y0, x0 = (h - n) // 2, (w - n) // 2
    g = g[y0:y0 + n, x0:x0 + n] * np.outer(np.hanning(n), np.hanning(n))
    F = np.abs(np.fft.fftshift(np.fft.fft2(g))) ** 2
    f1 = np.fft.fftshift(np.fft.fftfreq(n)) * n
    fy, fx = np.meshgrid(f1, f1, indexing="ij")
    fr = np.hypot(fx, fy)
    ok = (fr > n / 40.0) & (fr < n / 3.0)
    F = np.where(ok, F, 0.0)
    F = ndi.maximum_filter(F, 3) == F
    P = np.where(F & ok, np.abs(np.fft.fftshift(np.fft.fft2(g))) ** 2, 0.0)
    idx = np.argsort(P.ravel())[::-1][:12]
    peaks = []
    for i in idx:
        yy, xx = np.unravel_index(i, P.shape)
        a = np.arctan2(fy[yy, xx], fx[yy, xx]) % np.pi
        if all(abs(((a - b + np.pi / 2) % np.pi) - np.pi / 2) > np.radians(20) for b, _ in peaks):
            peaks.append((a, n / fr[yy, xx]))
        if len(peaks) == 2:
            break
    if not peaks:
        return {"angles": [0.0, np.pi / 2], "period": 6.0}
    if len(peaks) == 1:
        peaks.append(((peaks[0][0] + np.pi / 2) % np.pi, peaks[0][1]))
    # threads run perpendicular to the wave vector
    return {"angles": [float((a + np.pi / 2) % np.pi) for a, _ in peaks],
            "period": float(np.median([p for _, p in peaks]))}


def darkness(crop: np.ndarray, sigma: float) -> np.ndarray:
    """Darkness relative to a plane fitted to the crop's border."""
    g = ndi.gaussian_filter(crop, sigma)
    h, w = g.shape
    b = max(2, int(0.06 * min(h, w)))
    m = np.zeros_like(g, bool)
    m[:b], m[-b:], m[:, :b], m[:, -b:] = True, True, True, True
    yy, xx = np.mgrid[0:h, 0:w]
    A = np.column_stack([xx[m], yy[m], np.ones(m.sum())])
    v = g[m]
    # robust: refit on the brighter 70 % of the border (stains touching the border)
    for _ in range(2):
        c, *_ = np.linalg.lstsq(A, v, rcond=None)
        r = v - A @ c
        k = r > np.percentile(r, 30)
        A, v = A[k], v[k]
    bg = c[0] * xx + c[1] * yy + c[2]
    return np.clip((bg - g) / np.maximum(bg, 1e-3), 0, None)


def radial(mask: np.ndarray, d: np.ndarray, c: np.ndarray):
    """Outer front radius R(θ) of `mask` from centre c, and the darkness profile
    along each ray in units of R(θ)."""
    h, w = mask.shape
    th = np.linspace(0, 2 * np.pi, N_ANG, endpoint=False)
    rmax = np.hypot(h, w)
    rs = np.arange(0, rmax, 0.5)
    R = np.full(N_ANG, np.nan)
    for i, t in enumerate(th):
        x = c[0] + rs * np.cos(t)
        y = c[1] + rs * np.sin(t)
        ok = (x >= 0) & (x < w - 1) & (y >= 0) & (y < h - 1)
        if not ok.any():
            continue
        inside = mask[y[ok].astype(int), x[ok].astype(int)]
        if inside.any():
            R[i] = rs[ok][np.flatnonzero(inside)[-1]]
    prof = np.full((N_ANG, len(S_BINS)), np.nan)
    for i, t in enumerate(th):
        if not np.isfinite(R[i]) or R[i] < 2:
            continue
        rr = S_BINS * R[i]
        x, y = c[0] + rr * np.cos(t), c[1] + rr * np.sin(t)
        prof[i] = ndi.map_coordinates(d, [y, x], order=1, mode="nearest")
    return th, R, prof


def measure_one(name: str, j: int, box) -> dict | None:
    im = Image.open(CORPUS / "img" / name).convert("L")
    W, H = im.size
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    if bw < 12 or bh < 12:
        return None
    pad = 0.3 * max(bw, bh)
    X0, Y0 = int(max(0, x0 - pad)), int(max(0, y0 - pad))
    X1, Y1 = int(min(W, x1 + pad)), int(min(H, y1 + pad))
    full = np.asarray(im, dtype=np.float32) / 255.0
    wv = weave(full[max(0, Y0 - 200):Y1 + 200, max(0, X0 - 200):X1 + 200])
    crop = full[Y0:Y1, X0:X1]
    scale = min(1.0, 260.0 / max(crop.shape))
    if scale < 1.0:
        crop = np.asarray(Image.fromarray((crop * 255).astype(np.uint8)).resize(
            (max(8, int(crop.shape[1] * scale)), max(8, int(crop.shape[0] * scale))), Image.LANCZOS),
            dtype=np.float32) / 255.0
    period = wv["period"] * scale
    d = darkness(crop, max(1.0, 0.6 * period))
    d99 = float(np.percentile(d, 99.5))
    if d99 < 0.06:
        return None
    t = max(0.03, 0.3 * d99)
    lab, n = ndi.label(ndi.binary_opening(d > t, iterations=1))
    if n == 0:
        return None
    areas = ndi.sum(np.ones_like(d), lab, np.arange(1, n + 1))
    main = int(np.argmax(areas)) + 1
    mask = ndi.binary_fill_holes(lab == main)
    A = float(mask.sum())
    if A < 150:
        return None
    yy, xx = np.nonzero(mask)
    c = np.array([xx.mean(), yy.mean()])
    th, R, prof = radial(mask, d, c)
    if np.isnan(R).mean() > 0.2:
        return None
    R = np.where(np.isfinite(R), R, np.nanmedian(R))
    Rm = float(R.mean())
    # front modes and roughness
    Fk = np.fft.rfft(R) / len(R)
    modes = (np.abs(Fk[1:9]) / abs(Fk[0])).tolist()
    Fs = Fk.copy()
    Fs[:7] = 0
    hi = np.fft.irfft(Fs * len(R), n=len(R))
    rough = float(hi.std() / Rm)
    ks = np.arange(6, 41)
    pw = np.abs(Fk[ks]) ** 2
    slope = float(np.polyfit(np.log(ks), np.log(pw + 1e-12), 1)[0])
    # anisotropy relative to the weave
    def r_at(a):
        i = np.round((a % (2 * np.pi)) / (2 * np.pi) * N_ANG).astype(int) % N_ANG
        return float(np.mean([R[(i + k) % N_ANG] for k in (-2, -1, 0, 1, 2)]))
    ax = [r_at(a + q) for a in wv["angles"] for q in (0, np.pi)]
    a0, a1 = wv["angles"]
    mid = [(a0 + a1) / 2, (a0 + a1) / 2 + np.pi / 2]
    dg = [r_at(a + q) for a in mid for q in (0, np.pi)]
    aniso = float(np.mean(ax) / max(np.mean(dg), 1e-6))
    # tide line
    core = np.nanmean(prof[:, S_BINS < 0.5], axis=1)
    band = (S_BINS >= 0.75) & (S_BINS <= 1.0)
    rimv = np.nanmax(prof[:, band], axis=1)
    rim = float(np.nanmedian(rimv) / max(np.nanmedian(core), 1e-4))
    rim_arc = float(np.nanmean(rimv > 1.15 * np.nanmedian(core)))
    mp = np.nanmean(prof, axis=0)
    pk = int(np.argmax(np.where(S_BINS > 0.5, mp, -1)))
    half = 0.5 * (mp[pk] + np.nanmean(mp[S_BINS < 0.5]))
    lo = pk
    while lo > 0 and mp[lo] > half:
        lo -= 1
    hi_ = pk
    while hi_ < len(mp) - 1 and mp[hi_] > half:
        hi_ += 1
    rim_w = float((S_BINS[hi_] - S_BINS[lo]))
    # iso-darkness fronts: mean radius fraction of each level
    spacing = []
    for f in (0.2, 0.35, 0.5, 0.65, 0.8):
        lv = f * d99
        cross = []
        for row in prof:
            k = np.flatnonzero(row[:21] >= lv)
            cross.append(S_BINS[k[-1]] if len(k) else 0.0)
        spacing.append(float(np.mean(cross)))
    # broken ring: share of angles whose rim darkness never reaches the threshold
    openness = float(np.mean(rimv < t))
    # arms: the faint wet zone (0.12 · d99) connected to the body, reach per angle
    # ÷ body front; an arm is a narrow angular peak of that ratio (a thread that
    # carried ink ahead of the front)
    lab2, _ = ndi.label(d > max(0.02, 0.12 * d99))
    ids = np.unique(lab2[mask & (lab2 > 0)])
    low = np.isin(lab2, ids[ids > 0]) if len(ids) else mask
    _, Rl, _ = radial(ndi.binary_fill_holes(low | mask), d, c)
    Rl = np.where(np.isfinite(Rl), Rl, R)
    ratio = Rl / np.maximum(R, 1.0)
    arms = []
    sm = ndi.uniform_filter1d(ratio, 31, mode="wrap")
    for i in range(N_ANG):
        if ratio[i] >= 1.4 and ratio[i] == ratio[[(i + k) % N_ANG for k in range(-6, 7)]].max() \
                and ratio[i] > 1.25 * sm[i]:
            arms.append((float(th[i]), float(ratio[i])))
    halo = float(np.median(ratio))
    # satellites
    sats = []
    for k in range(1, n + 1):
        if k == main or areas[k - 1] < 12:
            continue
        yk, xk = np.nonzero(lab == k)
        dk = np.hypot(xk.mean() - c[0], yk.mean() - c[1]) / Rm
        if dk < 3.0:
            sats.append((float(dk), float(areas[k - 1] / A)))
    return {"image": name, "obj": j, "box": list(map(int, box)), "scale": scale,
            "weave": wv, "R_px": Rm / scale, "area_px": A / scale ** 2, "d99": d99,
            "elong": float(np.sqrt(np.linalg.eigvalsh(np.cov(np.vstack([xx, yy])))[::-1][0] /
                                   max(np.linalg.eigvalsh(np.cov(np.vstack([xx, yy])))[0], 1e-6))),
            "modes": modes, "rough": rough, "rough_slope": slope, "aniso": aniso,
            "rim": rim, "rim_arc": rim_arc, "rim_w": rim_w, "spacing": spacing,
            "open": openness, "sat_n": len(sats), "arms": arms, "halo": halo,
            "R_over_period": float(Rm / max(period, 1e-6)),
            "sat_d": [s[0] for s in sats], "sat_a": [s[1] for s in sats],
            "profile": np.nan_to_num(mp).round(4).tolist(),
            "front": (R / Rm).round(4).tolist(),
            "_crop": crop, "_d": d, "_mask": mask, "_c": c, "_t": t}


def overlay(r: dict, size: int = 200) -> Image.Image:
    """The crop with the outer front and three iso-darkness fronts drawn on it."""
    from skimage import measure  # noqa: PLC0415
    crop = r["_crop"]
    rgb = np.stack([crop] * 3, -1)
    img = Image.fromarray((rgb * 255).astype(np.uint8)).convert("RGB")
    from PIL import ImageDraw  # noqa: PLC0415
    dr = ImageDraw.Draw(img)
    cols = [(206, 93, 151), (67, 133, 190), (135, 154, 57), (175, 48, 41)]
    for f, col in zip((0.3, 0.5, 0.7), cols):
        for cc in measure.find_contours(r["_d"], f * r["d99"]):
            if len(cc) > 8:
                dr.line([(p[1], p[0]) for p in cc], fill=col, width=1)
    for cc in measure.find_contours(r["_mask"].astype(float), 0.5):
        dr.line([(p[1], p[0]) for p in cc], fill=cols[3], width=2)
    img.thumbnail((size, size))
    return img


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--digest", action="store_true", help="only digest measure.json into the library entry")
    a = ap.parse_args(argv)
    if a.digest:
        digest(json.loads((OUT / "measure.json").read_text()), save=True)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    boxes = stain_boxes()
    if a.limit:
        boxes = boxes[:a.limit]
    rows, ovs = [], []
    for name, j, box in boxes:
        try:
            r = measure_one(name, j, box)
        except Exception as e:  # noqa: BLE001
            print("fail", name, j, e, file=sys.stderr)
            continue
        if r is None:
            continue
        if len(ovs) < 120:
            ovs.append(overlay(r))
        rows.append({k: v for k, v in r.items() if not k.startswith("_")})
    (OUT / "measure.json").write_text(json.dumps(rows))
    cols, cell = 12, 205
    S = Image.new("RGB", (cols * cell, ((len(ovs) + cols - 1) // cols) * cell), "white")
    for i, o in enumerate(ovs):
        S.paste(o, ((i % cols) * cell, (i // cols) * cell))
    S.save(OUT / "overlays.jpg", quality=85)
    print(f"{len(rows)} stains measured of {len(boxes)} boxes")
    summarize(rows)


def summarize(rows):
    def q(key, f=lambda r, k: r[k]):
        v = np.array([f(r, key) for r in rows], float)
        return f"{key:10s} median {np.median(v):7.3f}  IQR {np.percentile(v, 25):7.3f}…{np.percentile(v, 75):7.3f}"
    for k in ("aniso", "rough", "rough_slope", "rim", "rim_arc", "rim_w", "open", "sat_n", "elong"):
        print(q(k))
    m = np.array([r["modes"] for r in rows])
    print("modes k1..8 median", np.round(np.median(m, 0), 3))
    sp = np.array([r["spacing"] for r in rows])
    print("iso-front radius fractions (levels .2 .35 .5 .65 .8) median", np.round(np.median(sp, 0), 3))
    print("rim>1.15 share", np.mean([r["rim"] > 1.15 for r in rows]).round(3))


def digest(rows, save=False) -> dict:
    """The corpus reduced to statistics a renderer samples from (never a stored
    front or a traced form): library `stain/stain_fabric`."""
    A = lambda k: np.array([r[k] for r in rows], float)  # noqa: E731
    q = lambda v, ps=(10, 25, 50, 75, 90): [round(float(x), 4) for x in np.percentile(v, ps)]  # noqa: E731
    rim = A("rim")
    rimmed = rim > 1.15
    prof = np.array([r["profile"] for r in rows])
    prof = prof / np.maximum(prof.max(1, keepdims=True), 1e-9)
    modes = np.array([r["modes"] for r in rows])
    sd = np.concatenate([r["sat_d"] for r in rows])
    sa = np.concatenate([r["sat_a"] for r in rows])
    corr = []
    for r in rows:
        R = np.array(r["front"])
        F = np.fft.rfft(R)
        F[:5] = 0
        h = np.fft.irfft(F, n=len(R))
        ac = np.fft.irfft(np.abs(np.fft.rfft(h)) ** 2, n=len(R))
        ac /= max(ac[0], 1e-12)
        z = np.flatnonzero(ac < 0.5)
        corr.append(z[0] * 360.0 / len(R) if len(z) else 180.0)
    d = {
        "n_stains": len(rows),
        "s_bins": S_BINS.round(4).tolist(),
        "profile_mesa": np.median(prof[~rimmed], 0).round(4).tolist(),
        "profile_rim": np.median(prof[rimmed], 0).round(4).tolist(),
        "rim_share": round(float(rimmed.mean()), 4),
        "rim_arc_q": q(A("rim_arc")[rimmed]),
        "rim_w_q": q(A("rim_w")[rimmed]),
        "rough_q": q(A("rough")),
        "rough_slope_q": q(A("rough_slope")),
        "front_corr_deg_q": q(corr),
        "modes_median": np.median(modes, 0).round(4).tolist(),
        "modes_q75": np.percentile(modes, 75, 0).round(4).tolist(),
        "elong_q": q(A("elong")),
        "iso_front_radius_q50": np.median(np.array([r["spacing"] for r in rows]), 0).round(4).tolist(),
        "iso_levels": [0.2, 0.35, 0.5, 0.65, 0.8],
        "sat_n_hist": np.bincount(A("sat_n").astype(int), minlength=12)[:12].tolist(),
        "sat_d_q": q(sd),
        "sat_a_q": q(sa),
        "sat_d_area_corr": round(float(np.corrcoef(np.log(sd), np.log(sa))[0, 1]), 3),
        "halo_q": q(A("halo")),
        "aniso_q": q(A("aniso")),
        "R_over_period_q": q(A("R_over_period")),
    }
    if save:
        sys.path.insert(0, str(ROOT / "tools/gesture"))
        from gesture.kit import library as L  # noqa: PLC0415
        L.save({"id": "stain_fabric", "kind": "stain", "label": "Fabric stains: fronts, tide lines, satellites",
                "version": 1, "policy": "generative",
                "provenance": {"corpus_path": ".local/gesture/corpus/fabric/fabric-stain-dataset",
                               "source": "Kaggle priemshpathirana/fabric-stain-dataset (CC0)",
                               "research_file": "tools/gesture/experiments/stain_measure.py"},
                "notes": "Statistics only, no stored fronts: the darkness profile (mesa vs tide line), "
                         "front roughness and its spectrum, low shape modes, partial-ring share, satellite "
                         "count/distance/size, halo reach. Weave anisotropy measured weak corpus-wide "
                         "(aniso median 1.03); thread arms visible only in a coarse-weave subset.",
                "digest": d}, None, overwrite=True)
    return d


if __name__ == "__main__":
    main()

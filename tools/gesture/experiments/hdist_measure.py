"""hdist (round 16, thread B): how distinct are the zoomed hands?

Every zoomed line is read through the 74-feature panel with the standard
preprocessing (panel σ ≥ 7 line widths, `medium.SIGMA_MIN_W`; the medium
projector fitted on the real drawings, `hybrid.projector`), at the size the
eye sees it (fitted into its specimen cell, the real pen width), cut into
WINDOWS equal-length strokes so the panel's per-stroke groups have something
to read.

Two readings per variant (a variant = one way of zooming every hand):

`sep`     distinctness among the zoomed hands: for each hand, the distance
          from its centroid (SEEDS lines) to the nearest OTHER hand's
          centroid, in units of the variant's pooled within-hand spread
          (median RMS radius): a d′. `self_rec` = share of lines whose nearest
          centroid (own centroid leave-one-out) is their own hand.
`lib`     against the whole library: each zoomed line's distance to every
          library hand's own generated pages (hands_trails/panel_gen.json, 6
          sheets per hand, read only). `own_rank` = rank of the line's own
          hand among the 44 (1 = it reads as itself). The caricature check:
          a variant that separates the zooms by pushing them away from their
          own hands has a worse own_rank.

Run from the repo root (cached per variant under .local/gesture/out/hdist/feat/):
    .local/gesture/.venv/bin/python tools/gesture/experiments/hdist_measure.py v1 lod0 ...
"""
from __future__ import annotations

import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, "tools/gesture")

OUT = Path(".local/gesture/out/hdist")
FEAT = OUT / "feat3"
LIB_GEN = Path(".local/gesture/out/hands_trails/panel_gen.json")      # read only
REAL = Path(".local/gesture/out/hybrid_hands/panel_real.json")        # read only
SEEDS = (1491, 1492, 1493, 1494, 1495, 1496)
WINDOWS = 6
CELL = (480, 120)          # the specimen cell, as lcorp-1
PEN = 0.45
PX = 10.0                  # px per mm for the panel drawing
# the line's shape only: curvature, extrema, inflections, turning, clothoid segments. Stroke counts,
# lengths, gaps and widths (len_, rel_, w_, end_) read the FORMAT (one cut line vs a page of strokes),
# not the hand, so they are left out of every distance.
SHAPE_GROUPS = ("k", "ext", "infl", "turn", "cl")
# σ = the standard floor, 7 pen widths (3.15 mm at 0.45 mm): the finest scale the pen can show a shape at.
# The default 0.01·ref (≈ 5 mm on a 480 mm cell) reads past the corners and curls that make a hand.
SIGMA_FRAC = 0.0


def hands() -> list[str]:
    from gesture.kit import library as L
    return [e["id"] for e in L.entries("hand") if e["policy"] == "generative"]


# ---------------------------------------------------------------------------
# variants: a variant is a function (hand, seed) -> recipe
# ---------------------------------------------------------------------------

def v1_recipe(hand: str, seed: int, **over) -> dict:
    v = {"id": "lcorp_zoom", "source": "hand", "hand": hand, "schedule": "push", "zoom": 24, "reveal": 0.4}
    v.update(over)
    return {"frame": list(CELL), "seed": seed, "margin": 6, "voice": v,
            "renderer": {"id": "lcorp_ink", "pen": PEN}}


def v2_recipe(hand: str, seed: int, **over) -> dict:
    v = {"id": "hdist_zoom", "hand": hand}
    v.update(over)
    return {"frame": list(CELL), "seed": seed, "margin": 6, "voice": v,
            "renderer": {"id": "lcorp_ink", "pen": PEN}}


VARIANTS = {
    # round 15 as shipped
    "v1": lambda h, s: v1_recipe(h, s),
    # one knob at a time (lcorp's own voice)
    "lod0": lambda h, s: v1_recipe(h, s, lod=0.0),
    "lod03": lambda h, s: v1_recipe(h, s, lod=0.3),
    "reveal1": lambda h, s: v1_recipe(h, s, reveal=1.0),
    "valley0": lambda h, s: v1_recipe(h, s, valley=0.0),
    "valley40": lambda h, s: v1_recipe(h, s, valley=40.0),
    "far6": lambda h, s: v1_recipe(h, s, far_turn_mm=6.0),
    "far12": lambda h, s: v1_recipe(h, s, far_turn_mm=12.0),
    "zoom1": lambda h, s: v1_recipe(h, s, zoom=1.0),
    "zoom6": lambda h, s: v1_recipe(h, s, zoom=6.0),
    "short": lambda h, s: v1_recipe(h, s, drawn_mm=500.0),
    # the hand's own voice, unzoomed (what the hand looks like whole: the ceiling)
    "native": lambda h, s: {"frame": list(CELL), "seed": s, "margin": 6,
                            "voice": {"id": "hand", "hand": h, "length": 6.0},
                            "renderer": {"id": "lcorp_ink", "pen": PEN}},
    # the new voice
    "v2": lambda h, s: v2_recipe(h, s),
}


LONG = 2      # "L/<variant>": the same process drawn LONG× as long in a LONG× wider cell, same paper scale,
              # cut into LONG× the windows: more of the line per sample, so the panel reads the process, not
              # one specimen's luck (the single cell's line is too short for the panel: native hands tell
              # apart at only ~22 % from one line)


def recipe_for(variant: str, hand: str, seed: int) -> dict:
    """A named variant, or 'base:key=val,key=val' (overrides on a named one's voice); 'L/...' = long."""
    if variant.startswith("L/"):
        rec = recipe_for(variant[2:], hand, seed)
        rec["frame"] = [rec["frame"][0] * LONG, rec["frame"][1]]
        v = rec["voice"]
        if v["id"] == "hand":
            v["length"] = v.get("length", 6.0) * LONG
        else:
            v["drawn_mm"] = float(v.get("drawn_mm", 1500.0)) * LONG
        return rec
    if ":" not in variant:
        return VARIANTS[variant](hand, seed)
    base, ov = variant.split(":", 1)
    rec = VARIANTS[base](hand, seed)
    for kv in ov.split(","):
        k, v = kv.split("=")
        rec["voice"][k] = v if v.isalpha() else float(v)
    return rec


# ---------------------------------------------------------------------------
# the panel reading of one line
# ---------------------------------------------------------------------------

def line_drawing(points_mm, pen: float = PEN, windows: int = WINDOWS):
    from gesture.core import Drawing, Stroke
    p = np.asarray(points_mm, float) * PX
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    cuts = np.searchsorted(s, np.linspace(0, s[-1], windows + 1))
    cuts[-1] = len(p) - 1
    st = [Stroke(p[a:b + 1], np.full(b + 1 - a, pen * PX)) for a, b in zip(cuts[:-1], cuts[1:]) if b - a >= 3]
    hi = p.max(axis=0)
    return Drawing(st, "hdist", (int(hi[0]) + 10, int(hi[1]) + 10), {})


def line_features(points_mm, pen: float = PEN, windows: int = WINDOWS) -> dict:
    from gesture import medium, panel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(line_drawing(points_mm, pen, windows), sigma_frac=SIGMA_FRAC,
                                        sigma_min_w=medium.SIGMA_MIN_W)
    return f


EYE = ("corner_share", "straight_share", "loops_per_m", "log_qt_mm", "fine_share", "infl_per_m")


def eye_features(points_mm) -> dict:
    """Six readings of a drawn line at sheet scale, the cues the eye uses to tell hands apart
    (declared before v2 was measured with them):
    corner_share    share of the turning done in sharp turns (> 60° within 1.5 mm of arc)
    straight_share  share of the length in near-straight runs (< 10° of turning over 10 mm)
    loops_per_m     small closed loops per metre (the line returns within 0.5 mm of itself after 3 to 25 mm of
                    arc)
    log_qt_mm       log of the median quarter-turn length (how large the line turns)
    fine_share      share of the turning under 3 mm (lost when θ is smoothed at 1.5 mm)
    infl_per_m      inflections per metre (sign changes of the turning, θ smoothed at 1 mm)"""
    from scipy.ndimage import gaussian_filter1d, uniform_filter1d
    from gesture.kit.voices_lcorp import resample
    h = 0.25
    r = resample(np.asarray(points_mm, float), h)
    d = np.diff(r, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    th = gaussian_filter1d(th, 0.3 / h, mode="nearest")            # below the pen: not a turn
    dth = np.diff(th)
    L = h * len(dth)
    tot = float(np.sum(np.abs(dth))) + 1e-9
    w15 = max(int(1.5 / h), 1)
    loc = np.abs(uniform_filter1d(dth, w15, mode="nearest") * w15)
    corner = float(np.sum(np.abs(dth)[loc > np.radians(60)]) / tot)
    w10 = max(int(10 / h), 1)
    run = np.abs(uniform_filter1d(np.abs(dth), w10, mode="nearest") * w10) < np.radians(10)
    straight = float(np.mean(run))
    close = np.zeros(len(r), bool)
    for k in range(int(3 / h), int(25 / h) + 1):
        dd = np.linalg.norm(r[k:] - r[:-k], axis=1) < 0.5
        close[k:] |= dd
    loops = int(np.sum(np.diff(np.r_[0, close.astype(int)]) == 1)) / (L / 1000.0)
    qt = L / max(tot / (np.pi / 2), 1e-9)
    t15 = gaussian_filter1d(th, 1.5 / h, mode="nearest")
    fine = 1.0 - float(np.sum(np.abs(np.diff(t15)))) / tot
    t1 = np.diff(gaussian_filter1d(th, 1.0 / h, mode="nearest"))
    sg = np.sign(t1[np.abs(t1) > 1e-4])
    infl = float(np.sum(sg[1:] != sg[:-1])) / (L / 1000.0)
    return {"corner_share": corner, "straight_share": straight, "loops_per_m": loops,
            "log_qt_mm": float(np.log(qt)), "fine_share": fine, "infl_per_m": infl}


def sheet_points(sh) -> np.ndarray:
    return np.vstack([np.asarray(m.points) for m in sh.marks if len(m.points) >= 2])


def _job(args):
    variant, hand, seed = args
    from gesture import kit
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            sh = kit.run(recipe_for(variant, hand, seed))
        except Exception as e:  # noqa: BLE001
            return f"{hand}|{seed}", None, repr(e)
    m = sh.marks[0]
    meta = {k: m.meta.get(k) for k in ("measure", "hdist") if k in m.meta}
    win = WINDOWS * (LONG if variant.startswith("L/") else 1)
    pts = sheet_points(sh)
    return f"{hand}|{seed}", {"f": line_features(pts, windows=win), "e": eye_features(pts), "meta": meta}, ""


def features_for(variant: str, hs=None, seeds=SEEDS, jobs: int = 10) -> dict:
    FEAT.mkdir(parents=True, exist_ok=True)
    path = FEAT / f"{_slug(variant)}.json"
    have = json.loads(path.read_text()) if path.exists() else {}
    hs = hs or hands()
    todo = [(variant, h, s) for h in hs for s in seeds if f"{h}|{s}" not in have]
    if todo:
        with ProcessPoolExecutor(jobs) as ex:
            fails = []
            for k, v, err in ex.map(_job, todo, chunksize=2):
                if v is None:
                    fails.append((k, err))
                    continue
                have[k] = v
            if fails:
                print("FAIL", variant, len(fails), fails[0], flush=True)
        path.write_text(json.dumps(have))
    return {k: v for k, v in have.items() if k.split("|")[0] in hs and int(k.split("|")[1]) in seeds}


# ---------------------------------------------------------------------------
# the readings
# ---------------------------------------------------------------------------

_PROJ = {}


def projector():
    if "tf" not in _PROJ:
        from gesture import hybrid as hy
        real = json.loads(REAL.read_text())
        tf, names, _, _ = hy.projector(real)
        lib = json.loads(LIB_GEN.read_text())
        _PROJ.update(tf=tf, names=names, lib=lib)
    return _PROJ["tf"], _PROJ["names"], _PROJ["lib"]


def Z(feats: dict) -> tuple[list[str], np.ndarray]:
    tf, names, _ = projector()
    keys = sorted(k for k in feats if feats[k])
    X = np.array([[feats[k].get(n, np.nan) for n in names] for k in keys], float)
    cols = [i for i, n in enumerate(names) if n.split("_", 1)[0] in SHAPE_GROUPS]
    return keys, tf(X)[:, cols]


def library_centroids(hs) -> dict:
    _, _, lib = projector()
    k, z = Z({k: v for k, v in lib.items() if k.split("|")[0] in hs})
    g = np.array([x.split("|")[0] for x in k])
    return {h: z[g == h].mean(0) for h in hs if (g == h).any()}


def _readings(keys, z) -> dict:
    """Distinctness of the hands in one space: per hand, the distance from its centroid to the nearest
    (sep_nn) and the 5 nearest (sep_k5) other hands' centroids, in units of the pooled within-hand spread
    (a d′); self_rec = share of lines whose nearest centroid (own leave-one-out) is their own hand."""
    grp = np.array([k.split("|")[0] for k in keys])
    hs = sorted(set(grp))
    cen = {h: z[grp == h].mean(0) for h in hs}
    rad = {h: float(np.sqrt(np.mean(np.sum((z[grp == h] - cen[h]) ** 2, 1)))) for h in hs}
    pooled = float(np.median(list(rad.values())))
    hits = 0
    for i in range(len(keys)):
        h = grp[i]
        n = (grp == h).sum()
        own = (cen[h] * n - z[i]) / max(n - 1, 1)
        dd = {o: np.linalg.norm(z[i] - (own if o == h else cen[o])) for o in hs}
        hits += min(dd, key=dd.get) == h
    H = {}
    for h in hs:
        d = {o: float(np.linalg.norm(cen[h] - cen[o]) / pooled) for o in hs if o != h}
        near = sorted(d, key=d.get)
        H[h] = {"nearest": near[0], "sep_nn": round(d[near[0]], 3),
                "sep_k5": round(float(np.mean([d[o] for o in near[:5]])), 3), "spread": round(rad[h] / pooled, 3)}
    summ = {"sep_nn_median": round(float(np.median([v["sep_nn"] for v in H.values()])), 3),
            "sep_k5_median": round(float(np.median([v["sep_k5"] for v in H.values()])), 3),
            "self_rec": round(hits / len(keys), 3), "n": len(keys)}
    return {"summary": summ, "hands": H, "centroids": cen}


def eye_matrix(feats: dict, ref: dict):
    """The six eye readings, standardised on the reference variant (the hands' own unzoomed lines)."""
    keys = sorted(k for k in feats if feats[k].get("e"))
    E = np.array([[feats[k]["e"][n] for n in EYE] for k in keys], float)
    R = np.array([[v["e"][n] for n in EYE] for v in ref.values() if v.get("e")], float)
    return keys, (E - R.mean(0)) / np.where(R.std(0) > 0, R.std(0), 1.0)


def report(feats: dict, ref: dict | None = None) -> dict:
    """feats: 'hand|seed' -> {"f": panel, "e": eye} for one variant; ref: the same for the native lines
    (the hands' own voice in the same cell), for the eye standardisation and the fidelity rank."""
    keys, z = Z({k: v["f"] for k, v in feats.items()})
    panel_r = _readings(keys, z)
    out = {"panel": {k: v for k, v in panel_r.items() if k != "centroids"}}
    # the library's own pages (6 sheets per hand): own rank among the 44. Format-confounded: even the
    # hands' own unzoomed lines rank ~20th against their pages (a line in a cell is not a page of strokes)
    libc = library_centroids(sorted(panel_r["hands"]))
    ranks = {}
    for h, c in panel_r["centroids"].items():
        dl = {o: float(np.linalg.norm(c - x)) for o, x in libc.items()}
        ranks[h] = sorted(dl, key=dl.get).index(h) + 1 if h in dl else None
    out["panel"]["summary"]["page_rank_median"] = float(np.median(list(ranks.values())))
    if ref is not None:
        ke, ze = eye_matrix(feats, ref)
        eye_r = _readings(ke, ze)
        kr, zr = eye_matrix(ref, ref)
        native = _readings(kr, zr)["centroids"]
        fid = {h: sorted(native, key=lambda o: np.linalg.norm(c - native[o])).index(h) + 1
               for h, c in eye_r["centroids"].items() if h in native}
        eye_r["summary"]["own_native_rank_median"] = float(np.median(list(fid.values())))
        eye_r["summary"]["own_native_top5"] = round(float(np.mean([v <= 5 for v in fid.values()])), 3)
        for h in eye_r["hands"]:
            eye_r["hands"][h]["own_native_rank"] = fid.get(h)
        out["eye"] = {k: v for k, v in eye_r.items() if k != "centroids"}
    return out


def _slug(v: str) -> str:
    return v.replace(":", "_").replace(",", "_").replace("/", "_")


def main(argv):
    rows = {}
    for v in argv or ["v1"]:
        ref_v = "L/native" if v.startswith("L/") else "native"
        ref = features_for(ref_v)
        rep = report(features_for(v), ref)
        (OUT / f"report_{_slug(v)}.json").write_text(json.dumps(rep, indent=1))
        rows[v] = {"panel": rep["panel"]["summary"], "eye": rep.get("eye", {}).get("summary")}
        print(v, "\n  panel", rep["panel"]["summary"], "\n  eye  ", rows[v]["eye"], flush=True)
    return rows


if __name__ == "__main__":
    main(sys.argv[1:])


# ---------------------------------------------------------------------------
# zoom bands: each hand at a constant magnification; where is it most unlike the library?
# ---------------------------------------------------------------------------

BANDS = {"x0.25": 20.0, "x0.5": 40.0, "x1": 80.0, "x2": 160.0, "x4": 320.0}   # R on paper, mm (v2's R_mm = 80)


def band_variant(b: str, long: bool = True) -> str:
    return ("L/" if long else "") + f"v2:zoom=1,R_mm={BANDS[b]:g}"


def bands_report(bands=tuple(BANDS), name: str = "bands") -> dict:
    """Every hand at every band (constant zoom, the hand's R drawn at BANDS mm), in the eye space and the
    panel space. A hand-band's distinctness = distance from its centroid to the nearest centroid of ANY
    OTHER hand at ANY band (the whole library at every scale: a band where a hand only looks like another
    hand at another size does not count), in units of the pooled within-hand-band spread. Its best band
    is the argmax; `fidelity` = the share of its lines whose nearest hand-band centroid is its own hand
    (any band): self-consistency against caricature."""
    ref = features_for("L/native")
    allk, alle, allz = [], [], []
    for b in bands:
        f = features_for(band_variant(b))
        ke, ze = eye_matrix(f, ref)
        kp, zp = Z({k: v["f"] for k, v in f.items()})
        assert ke == kp
        allk += [f"{k.split('|')[0]}@{b}|{k.split('|')[1]}" for k in ke]
        alle.append(ze)
        allz.append(np.clip(zp, -6.0, 6.0))      # a few panel features explode on the densest bands
    out = {}
    for space, M in (("eye", np.vstack(alle)), ("panel", np.vstack(allz))):
        grp = np.array([k.split("|")[0] for k in allk])
        hb = sorted(set(grp))
        cen = {g: M[grp == g].mean(0) for g in hb}
        rad = np.median([np.sqrt(np.mean(np.sum((M[grp == g] - cen[g]) ** 2, 1))) for g in hb])
        dist, near = {}, {}
        for g in hb:
            h = g.split("@")[0]
            d = {o: np.linalg.norm(cen[g] - cen[o]) / rad for o in hb if o.split("@")[0] != h}
            near[g] = min(d, key=d.get)
            dist[g] = float(d[near[g]])
        fid = {}
        for g in hb:
            h = g.split("@")[0]
            idx = np.flatnonzero(grp == g)
            hits = 0
            for i in idx:
                own = (cen[g] * len(idx) - M[i]) / max(len(idx) - 1, 1)          # leave-one-out
                dd = {o: np.linalg.norm(M[i] - (own if o == g else cen[o])) for o in hb}
                hits += min(dd, key=dd.get).split("@")[0] == h
            fid[g] = hits / len(idx)
        per_hand = {}
        for h in sorted({g.split("@")[0] for g in hb}):
            row = {b: round(dist[f"{h}@{b}"], 3) for b in bands}
            best = max(row, key=row.get)
            per_hand[h] = {"by_band": row, "best": best, "best_dist": row[best], "nearest": near[f"{h}@{best}"],
                           "fidelity_best": round(fid[f"{h}@{best}"], 3)}
        out[space] = per_hand
    (OUT / f"{name}.json").write_text(json.dumps(out, indent=1))
    return out

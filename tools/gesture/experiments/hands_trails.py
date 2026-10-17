"""New hands from trails and bodies (research round 11, exploration 1b, 2026-10-17).

    .local/gesture/.venv/bin/python tools/gesture/experiments/hands_trails.py <stage> [--only a,b]

stages:
  extract  — insect galleries, leaf miners, slime trails, trace fossils, a
             cloud-chamber track through extract_hybrid. Each trail has a
             "plain" extraction and, where the plain one fails, a RESCUE that
             changes what is extracted rather than a threshold:
               coarse  — the trail's centre-line at a coarser scale (downscale
                         + blur to the gallery's width before extraction)
               relief  — relief photographs (trace fossils): the groove is an
                         edge pair, not ink; the band of gradient energy at the
                         groove's own scale is turned into ink and its centre
                         extracted
  learn    — grammars: trail hands (`trail_*`), one hand per DANCER of the
             E2-Create Motion Bank "Unusual Poses" task (`dancer_*`, six
             dancers, one task), a Diwani hand (`diwani_*`) only from sheets
             the policy gate passes; saved as library `hand` entries
  measure  — distinctness (panel space, standard preprocessing) against every
             library hand + self-consistency; the dancer question: can windows
             of one dancer be told from the other five?
  sheets   — specimens, the hands atlas, combinations (kit.run + kit.preview)
  all

Outputs: .local/gesture/out/hands_trails/. Write-up:
tools/gesture/results/hands_trails-2026-10-17.md.

Corpora give behaviours, never forms: the hands learn token statistics
(segment lengths, curvature, corners, joins), never a drawing's layout.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import grammar as gm  # noqa: E402
from gesture.core import Drawing  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/hands_trails"
RES = HERE / "results"
CORPUS = ROOT / ".local/gesture/corpus"
JOBS = 2
COMMIT = "0dc1785"
DATE = "2026-10-17"

# ---------------------------------------------------------------------------
# trails: name -> (earth dir, crop x0 y0 x1 y1, mode, prep, extract kw)
# mode: "gray" luminance (dark trail) | "inv" (bright trail on dark ground) | "min" darkest channel
# prep: None | ("flat", σ_frac) illumination flattening | ("coarse", px) centre-line at a coarser
#       scale (blur to the gallery width, then extract) | ("relief", px) gradient-energy band
# ---------------------------------------------------------------------------
OTSU = {"method": "otsu", "paper_window_frac": 0.08, "spur_factor": 2.5, "crop_to_plate": False,
        "drop_frames": False}
TRAILS = {
    # leaf miners (Phyllocnistis populiella): a dark frass line down a pale serpentine mine
    "miner_a": ("insect-01", (0.13, 0.28, 0.62, 0.81), "gray", None, {}),
    "miner_b": ("insect-02", (0.29, 0.31, 0.79, 0.86), "gray", None, {}),
    # bark-beetle galleries
    "beetle_didactic": ("insect-03", (0.03, 0.37, 0.37, 0.80), "gray", None, {}),
    "beetle_elm_a": ("insect-04", (0.00, 0.16, 1.00, 0.96), "gray", ("flat", 0.02), {}),
    "beetle_elm_b": ("insect-05", (0.00, 0.05, 1.00, 0.80), "gray", ("flat", 0.02), {}),
    "borer": ("insect-08", (0.13, 0.15, 0.87, 0.87), "inv", ("flat", 0.03), {}),
    # skeletonised oak leaf (the "leaf-eaten" sheet is a vein net, not a miner)
    "oak_net": ("leaf-eaten-white-oak", (0.05, 0.00, 1.00, 0.80), "inv", None, {}),
    # slug/snail slime on concrete
    "slime": ("slime-trails-forty-years", (0.31, 0.12, 0.82, 0.72), "inv", ("flat", 0.03), {}),
    # trace fossils (relief photographs)
    "helminthoida": ("trace-helminthoida-carnero", (0.25, 0.33, 0.88, 0.72), "gray", None, {}),
    "nereites": ("trace-nereites-cymru", (0.08, 0.15, 0.92, 0.95), "gray", None, {}),
    "paleodictyon": ("trace-paleodictyon-I01", (0.00, 0.25, 0.75, 0.97), "gray", None, {}),
    # Anderson's 1932 positron track
    "positron": ("cc-positron-1932", (0.04, 0.04, 0.96, 0.96), "gray", None, {}),
    # bubble-chamber prints (the `bubble` hand learned bc-06 only). First pass ran all eleven others
    # whole: the photographs extract as bubble OUTLINES and specks (bc-03/05/07/11), bc-15 is an aerial
    # photo of the lab, bc-16/17/19 give ~nothing. Kept: the physicists' TRACINGS of events (clean
    # interpretive line drawings of the tracks), cropped away from the photo halves.
    **{b: (b, (0.03, 0.03, 0.97, 0.97), "gray", None, {}) for b in
       ("bc-01", "bc-02", "bc-03", "bc-05", "bc-07", "bc-10", "bc-11", "bc-15", "bc-16", "bc-17", "bc-19")},
    "bc-01t": ("bc-01", (0.46, 0.02, 0.98, 0.98), "gray", None, {}),
    "bc-02t": ("bc-02", (0.02, 0.09, 0.98, 0.98), "gray", None, {}),
    "bc-10t": ("bc-10", (0.02, 0.02, 0.41, 0.98), "gray", None, {}),
}
# rescues: same source, a different reading of what the trail IS
# (first pass, kept as evidence: the plain hysteresis extractor found 0 strokes on every
#  textured photograph — bark, leaf net, rock — and the fine relief band (σ 4–8 px at 2400)
#  traced rock grain, not grooves; see results "What failed")
RESCUE = {
    # name: (base trail, prep, extract kw, max_side of the loaded crop)
    "miner_a@coarse": ("miner_a", ("coarse", 3.0), {}, 2400),
    "miner_b@coarse": ("miner_b", ("coarse", 3.0), {}, 2400),
    "slime@coarse": ("slime", ("coarse", 3.0), {}, 2400),
    "positron@coarse": ("positron", ("coarse", 4.0), {}, 2400),
    "borer@coarse": ("borer", ("coarse", 4.0), OTSU, 2400),
    "beetle_elm_a@coarse": ("beetle_elm_a", ("coarse", 4.0), OTSU, 2400),
    "oak_net@coarse": ("oak_net", ("coarse", 4.0), OTSU, 2400),
    "helminthoida@relief": ("helminthoida", ("relief", 10.0), OTSU, 1200),
    "nereites@relief": ("nereites", ("relief", 10.0), OTSU, 1200),
    "paleodictyon@relief": ("paleodictyon", ("relief", 10.0), OTSU, 1200),
}


def _load_gray(path: Path, crop, mode: str, max_side: int = 2400) -> np.ndarray:
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as im:
        im = im.convert("RGB")
        W, H = im.size
        x0, y0, x1, y1 = crop
        im = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
        if max(im.size) > max_side:
            f = max_side / max(im.size)
            im = im.resize((int(im.size[0] * f), int(im.size[1] * f)), Image.Resampling.LANCZOS)
        a = np.asarray(im, dtype=np.float64) / 255.0
    g = a.min(axis=2) if mode == "min" else a @ np.array([0.299, 0.587, 0.114])
    return 1.0 - g if mode == "inv" else g


def _norm(x: np.ndarray, lo_q: float = 1.0, hi_q: float = 99.5) -> np.ndarray:
    lo, hi = np.percentile(x, [lo_q, hi_q])
    return np.clip((x - lo) / max(hi - lo, 1e-9), 0.0, 1.0)


def prep(g: np.ndarray, how) -> np.ndarray:
    """Pre-extraction readings of a photograph (ink dark, paper bright in and out)."""
    from scipy.ndimage import gaussian_filter
    if how is None:
        return g
    kind, v = how
    if kind == "flat":                       # divide out uneven light (bark, concrete)
        bg = gaussian_filter(g, v * max(g.shape))
        return _norm(g / np.maximum(bg, 1e-3))
    if kind == "coarse":                     # the gallery's centre-line, not its texture
        s = float(v)
        h, w = g.shape
        small = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize(
            (max(8, int(w / s)), max(8, int(h / s))), Image.Resampling.LANCZOS), float) / 255.0
        return _norm(gaussian_filter(small, 1.2))
    if kind == "relief":                     # a groove in rock = an edge pair; its energy band = ink
        s = float(v)
        sm = gaussian_filter(g, s * 0.5)
        gy, gx = np.gradient(sm)
        band = gaussian_filter(np.hypot(gx, gy), s * 0.6)
        flat = band / np.maximum(gaussian_filter(band, 12 * s), 1e-9)   # local contrast
        return 1.0 - _norm(flat, 5.0, 99.0)
    raise ValueError(how)


def _extract_job(args):
    name, path, crop, mode, how, kw, max_side = args
    from gesture import extract_hybrid
    from gesture.extract import debug_overlay
    t = time.perf_counter()
    g = _load_gray(path, crop, mode, max_side)
    if "@" in name:                          # rescues read the base trail's own prep first
        g = prep(g, TRAILS[name.split("@")[0]][3])
    g = prep(g, how)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            d = extract_hybrid.extract(g, source=name, **kw)
        except Exception as e:  # noqa: BLE001
            return {"name": name, "error": repr(e)}
    od = OUT / "extract"
    od.mkdir(parents=True, exist_ok=True)
    d.save(od / f"{name}.json")
    Image.fromarray(debug_overlay(g, d, max_side=1400)).save(od / f"{name}.jpg", quality=80)
    L = [s.length() for s in d.strokes]
    w = float(d.meta.get("line_width_px", 0) or 0)
    Lw = np.array(L) / max(w, 1e-9) if L else np.zeros(0)
    return {"name": name, "strokes": len(d.strokes), "w_px": round(w, 2), "size": list(d.size),
            "med_len_w": round(float(np.median(Lw)), 1) if L else 0,
            "n_long12": int((Lw >= 12).sum()), "ink_long12_w": round(float(Lw[Lw >= 12].sum()), 0),
            "secs": round(time.perf_counter() - t, 1)}


def extract_jobs(only=None):
    jobs = []
    for n, (d, crop, mode, how, kw) in TRAILS.items():
        fs = sorted((CORPUS / "earth" / d).glob("*.jp*g"))
        jobs.append((n, fs[0], crop, mode, how, kw, 2400))
    for n, (base, how, kw, ms) in RESCUE.items():
        d, crop, mode, _, kw0 = TRAILS[base]
        fs = sorted((CORPUS / "earth" / d).glob("*.jp*g"))
        jobs.append((n, fs[0], crop, mode, how, {**kw0, **kw}, ms))
    if only:
        jobs = [j for j in jobs if j[0] in only]
    return jobs


def stage_extract(a):
    only = set(a.only.split(",")) if a.only else None
    rows = []
    with ProcessPoolExecutor(JOBS) as ex:
        for r in ex.map(_extract_job, extract_jobs(only)):
            print(r, flush=True)
            rows.append(r)
    p = OUT / "extract" / "summary.json"
    old = json.loads(p.read_text()) if p.exists() else []
    keep = {r["name"]: r for r in old}
    keep.update({r["name"]: r for r in rows})
    p.write_text(json.dumps([keep[k] for k in sorted(keep)], indent=1))


# ---------------------------------------------------------------------------
# stage: learn
# ---------------------------------------------------------------------------

TRACKS = ("positron@coarse", "bc-01t", "bc-02t", "bc-10t")

# trail hands: id -> (extract names, tile, label, description, earth manifest ids)
TRAIL_HANDS = {
    "trail_miner": (("miner_a@coarse", "miner_b@coarse"), 1, "Trail: leaf miner",
                    "aspen serpentine leaf-miner galleries (Phyllocnistis populiella), the frass centre-line "
                    "at a coarser scale (blur to the mine width, then extract)", ("insect-01", "insect-02")),
    "trail_miner_fine": (("miner_a", "miner_b"), 1, "Trail: leaf miner (fine)",
                         "the same galleries extracted at full resolution (breaks at the hairpins)",
                         ("insect-01", "insect-02")),
    "trail_beetle": (("beetle_didactic",), 1, "Trail: bark-beetle gallery",
                     "a didactic wall relief after a bark-beetle gallery (mother gallery + larval galleries); "
                     "made by people after the insect, so second-hand", ("insect-03",)),
    "trail_slime": (("slime",), 1, "Trail: slug and snail slime",
                    "forty years of slug and snail slime trails on a concrete wall", ("slime-trails-forty-years",)),
    "trail_slime_coarse": (("slime@coarse",), 1, "Trail: slime (coarse)",
                           "the slime trails' centre-lines at a coarser scale", ("slime-trails-forty-years",)),
    "trail_borer": (("borer@coarse",), 1, "Trail: wood-borer galleries",
                    "metallic wood-boring beetle galleries under bark, coarse scale (galleries mixed with grain)",
                    ("insect-08",)),
    "trail_elm": (("beetle_elm_a@coarse",), 1, "Trail: elm bark beetle",
                  "elm bark-beetle galleries on a log, coarse scale (mostly wood grain)", ("insect-04",)),
    "trail_oaknet": (("oak_net@coarse",), 1, "Trail: skeletonised oak leaf",
                     "the vein net left by insects eating a white-oak leaf (negative of the feeding), coarse",
                     ("leaf-eaten-white-oak",)),
    "trail_grazer": (("helminthoida@relief", "nereites@relief", "paleodictyon@relief"), 1,
                     "Trail: grazing trace fossils",
                     "Helminthoida, Nereites, Paleodictyon relief photographs read as gradient-energy bands",
                     ("trace-helminthoida-carnero", "trace-nereites-cymru", "trace-paleodictyon-I01")),
    "trail_positron": (("positron@coarse",), 1, "Trail: positron track",
                       "Anderson's 1932 cloud-chamber positron track (and the lead plate)", ("cc-positron-1932",)),
    "trail_tracks": (TRACKS, 1, "Trail: particle tracks",
                     "Anderson's 1932 positron track + the physicists' tracings of three bubble-chamber events "
                     "(bc-01, bc-02, bc-10; not bc-06, which is the `bubble` hand): spirals, kinks, long arcs",
                     ("cc-positron-1932", "bc-01", "bc-02", "bc-10")),
}

# fly kinematics: simulated walks of the male Drosophila CNS connectome steering a pen
# (Ian's mosca-draw project, read-only; the walks stay where they are, nothing copied)
MOSCA = Path.home() / "_SecondBrain/01_Projects/mosca-draw/out"
FLY = {
    "fly_open": ("Fly: open-field walk", "k4_circulation", "open_control", (7, 11, 23, 42, 99)),
    "fly_fru": ("Fly: courtship neurons driven", "k4_circulation", "open_fru", (7, 11, 23, 42, 99)),
}
FLY_STROKE_S, FLY_PER_DRAWING, FLY_DECIMATE = 3.0, 4, 50       # 3 s strokes, 4 per drawing, 0.1 ms → 5 ms


def fly_drawings(test: str, stem: str, seeds) -> list[Drawing]:
    """One drawing per 12 s of walk: four 3 s strokes, end to end (no pen lifts in these walks)."""
    from gesture import dance as D
    out = []
    for sd in seeds:
        with np.load(MOSCA / test / f"{stem}_s{sd}.npz") as h:
            p = np.asarray(h["path"], float)[::FLY_DECIMATE]
        n = int(round(FLY_STROKE_S / (FLY_DECIMATE * 1e-4)))
        strokes = [p[i:i + n + 1] for i in range(0, len(p) - n // 2, n)]
        for g in range(0, len(strokes) - FLY_PER_DRAWING + 1, FLY_PER_DRAWING):
            polys = [D._dedupe(q, 0.004)[0] for q in strokes[g:g + FLY_PER_DRAWING]]
            d = D._drawing(polys, [{"walk": f"{test}/{stem}_s{sd}"}] * len(polys), (840, 1200),
                           f"{test}/{stem}_s{sd}@{g * FLY_STROKE_S:.0f}s")
            if len(d.strokes) >= 3:
                out.append(d)
    return out


# dancers: one task (E2-Create Motion Bank, "Unusual Poses"), six people
E2MB = ("E2-Create Motion Bank Dataset (Zenodo 7031672): manifest says CC BY 4.0, the dataset Readme says "
        "CC BY-NC-SA (dance-harvest.csv)")
DANCERS = {
    "dancer_amber": ("e2mb-unusual/Amber_Pansters.bvh", "Dancer: Amber Pansters"),
    "dancer_anna": ("e2mb-unusual/Anna_Raiola.bvh", "Dancer: Anna Raiola"),
    "dancer_cristel": ("e2mb-unusual/Cristel_De_Frankrijker_Take2.bvh", "Dancer: Cristel De Frankrijker"),
    "dancer_madeline": ("e2mb-unusual/Madeline_Harms_Take2.bvh", "Dancer: Madeline Harms"),
    "dancer_marija": ("e2mb-unusual/Marija_Slavec.bvh", "Dancer: Marija Slavec"),
    "dancer_zachary": ("e2mb-unusual/Zachary_Chant_Take2.bvh", "Dancer: Zachary Chant"),
}
# control for the dancer question: one company's movement-QUALITY set (E2 Stocos)
STOCOS = {q: f"e2-stocos/{q}_FullBody_Take1_proc.bvh" for q in
          ("Accumulation", "Continuity", "Fluidity", "Levitation", "OutOfBalance", "Particles", "Staccato",
           "Thrusting")}
WIN = 15.0
HAND_WINDOWS = 12          # windows a dancer hand learns from (evenly spaced through the take)
TEST_WINDOWS = 8           # windows per class in the who-vs-how test (balanced)

# Diwani: only sheets the gate passes (manifest content type + EXCLUDE_GENERATIVE), checked here
# and by the library on every load. wc-39 (album page) is refused; wc-05 (Ahmed III letter to the
# Swedish crown, 1711) is a document that opens with the tughra and the sultan's titles, no
# devotional invocation (checked by eye on the sheet's top, 2026-10-17; lead to confirm).
DIWANI = {"diwani_chancery": ("diwani", 2, "Diwani (chancery letter)",
                              "Ottoman chancery diwani, Ahmed III letter (1711), text block only, tiled 2x2")}


def _windows(rel: str, n: int, skip: float = 5.0) -> list[tuple[float, float]]:
    from gesture import dance as D
    m = D.load(CORPUS / "dance" / rel, 0, None, fps_out=30.0)
    dur = m.T / m.fps
    k = int((dur - skip) // WIN)
    idx = np.unique(np.round(np.linspace(0, k - 1, min(n, k))).astype(int))
    return [(skip + i * WIN, skip + (i + 1) * WIN) for i in idx]


def dance_windows(rel: str, n: int, effectors=None) -> list[Drawing]:
    from gesture import dance as D
    m = D.load(CORPUS / "dance" / rel, 0, None, fps_out=60.0)
    out = []
    for t0, t1 in _windows(rel, n):
        d = D.trails(m.window(t0, t1), effectors or D.EFFECTORS, view="front")
        if len(d.strokes) >= 3:
            out.append(Drawing(d.strokes, source=f"{Path(rel).stem}@{int(t0)}s", size=d.size, meta=d.meta))
    return out


def trail_drawings(names, tile: int) -> list[Drawing]:
    from gesture import hybrid as hy
    out = []
    for n in names:
        d = Drawing.load(OUT / "extract" / f"{n}.json")
        d = Drawing(d.strokes, source=n, size=d.size, meta=d.meta)
        out += hy.tile_drawing(d, tile, tile) if tile > 1 else [d]
    return out


def diwani_drawings() -> tuple[list[Drawing], list[str], list[str]]:
    from gesture import calligraphy as C
    from gesture import hybrid as hy
    from gesture.script_syntax import EXCLUDE_GENERATIVE
    cal = ROOT / ".local/gesture/out/calligraphy/extract/diwani"
    dd = {p.stem: Drawing.load(p) for p in sorted(cal.glob("*.json")) if not p.name.endswith(".outline.json")}
    allowed = {k: v for k, v in C.filter_generative(dd).items() if k not in EXCLUDE_GENERATIVE}
    C.require_generative(list(allowed))                      # hard gate
    ds = []
    for k, d in sorted(allowed.items()):
        ds += hy.tile_drawing(C.pen_strokes(d), 2, 2)
    return ds, sorted(allowed), sorted(set(dd) - set(allowed))


def _learn_job(args):
    key, kind = args
    t = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if kind == "dancer":
            ds = dance_windows(DANCERS[key][0], HAND_WINDOWS)
            info = {"windows_s": WIN, "n_windows": len(ds), "task": "Unusual Poses"}
        elif kind == "fly":
            _, test, stem, seeds = FLY[key]
            ds = fly_drawings(test, stem, seeds)
            info = {"walks": [f"{test}/{stem}_s{sd}" for sd in seeds], "stroke_s": FLY_STROKE_S,
                    "strokes_per_drawing": FLY_PER_DRAWING, "decimate_rows": FLY_DECIMATE}
        elif kind == "diwani":
            ds, tr, ex = diwani_drawings()
            info = {"tile": 2, "allowed": tr, "excluded_measure_only": ex}
        else:
            names, tile = TRAIL_HANDS[key][:2]
            ds, info = trail_drawings(names, tile), {"tile": tile, "extracts": list(names)}
        g = gm.learn(ds, name=key, min_len_w=12)
    (OUT / "grammars").mkdir(parents=True, exist_ok=True)
    g.save(OUT / "grammars" / f"{key}.json")
    (OUT / "train").mkdir(parents=True, exist_ok=True)
    for i, d in enumerate(ds):
        d.save(OUT / "train" / f"{key}__{i}.json")
    info.update({"kind": kind, "sources": [d.source for d in ds], "strokes": len(g.strokes),
                 "records": len(g.trans["nx"]), "min_len_w": 12, "drawings": len(ds),
                 "secs": round(time.perf_counter() - t, 1)})
    return key, info


def all_new() -> dict[str, str]:
    out = {k: "trail" for k in TRAIL_HANDS}
    out.update({k: "dancer" for k in DANCERS})
    out.update({k: "fly" for k in FLY})
    out.update({k: "diwani" for k in DIWANI})
    return out


def stage_learn(a):
    jobs = sorted(all_new().items())
    if a.only:
        jobs = [j for j in jobs if j[0] in a.only.split(",")]
    p = OUT / "learn.json"
    rows = json.loads(p.read_text()) if p.exists() else {}
    with ProcessPoolExecutor(JOBS) as ex:
        for key, info in ex.map(_learn_job, jobs):
            rows[key] = info
            print(key, {k: v for k, v in info.items() if k != "sources"}, flush=True)
    p.write_text(json.dumps(rows, indent=1))


# ---------------------------------------------------------------------------
# stage: save — the kept hands go into the library (decided after `measure`)
# ---------------------------------------------------------------------------

KEEP = ("trail_miner", "trail_beetle", "trail_slime", "trail_borer", "trail_oaknet", "trail_grazer", "trail_tracks",
        "dancer_amber", "dancer_anna", "dancer_cristel", "dancer_madeline", "dancer_marija", "dancer_zachary",
        "fly_open", "fly_fru")
# Diwani: learned and measured (the gate passes wc-05 only), then DROPPED this round on Ian's call —
# kept as evidence in .local only, not in the library.
# measured but kept out (duds, evidence): trail_elm (wood grain), trail_positron (14 records), and the
# variants trail_miner_fine / trail_slime_coarse


def _earth_rights() -> dict[str, str]:
    import csv
    p = ROOT / "docs/research/gesture-corpus/earth-physics-harvest.csv"
    with p.open() as f:
        return {r["id"]: r["rights_note"] for r in csv.DictReader(f)}


def save_hand(key: str, overwrite: bool = True) -> int:
    from gesture.kit import library as L
    info = json.loads((OUT / "learn.json").read_text())[key]
    d = json.loads((OUT / "grammars" / f"{key}.json").read_text())
    arrays, sheet = L.encode_hand(d)
    kind = info["kind"]
    if kind == "trail":
        names, tile, label, desc, ids = TRAIL_HANDS[key]
        rr = _earth_rights()
        corpus, rights = "earth", "; ".join(f"{i}: {rr.get(i, '?')}" for i in ids)
        extra = {"earth_items": list(ids), "extracts": list(names)}
    elif kind == "fly":
        label, test, stem, seeds = FLY[key]
        corpus = None
        rights = "Ian's own project (mosca-draw); connectome: male CNS v1.0, Janelia/Google (see mosca-draw docs)"
        desc = (f"simulated walks of the male Drosophila CNS connectome driving a differential-drive body "
                f"(mosca-draw out/{test}/{stem}_s{{{','.join(map(str, seeds))}}}.npz, read in place): "
                f"{FLY_STROKE_S:.0f} s strokes, {FLY_PER_DRAWING} per drawing")
        extra = {"source_paths": [f"~/_SecondBrain/01_Projects/mosca-draw/out/{test}/{stem}_s{sd}.npz" for sd in seeds],
                 "simulated": True}
    elif kind == "dancer":
        rel, label = DANCERS[key]
        corpus, rights = "dance", E2MB
        desc = (f"end-effector trails (hands, feet, head; front view) of {rel}, {info['n_windows']} windows of "
                f"{WIN:.0f} s spread through the take; task 'Unusual Poses' (all six dancers had the same task)")
        extra = {"performer": label.split(": ", 1)[1], "task": "Unusual Poses"}
    else:
        _, tile, label, desc = DIWANI[key]
        corpus, rights = "calligraphy", "calligraphy-harvest.csv: generative-allowed content types only"
        extra = {"allow_list": "every training sheet passes calligraphy.require_generative and is not in "
                               "script_syntax.EXCLUDE_GENERATIVE",
                 "excluded_measure_only": info.get("excluded_measure_only", []),
                 "verification": "wc-05 checked by eye: opens with the tughra and the sultan's titles, no "
                                 "devotional invocation; text-block crop (calligraphy.SHEETS)"}
    prov = {"research_file": str((OUT / "grammars" / f"{key}.json").relative_to(ROOT)), "research_commit": COMMIT,
            "description": desc, "rights": rights, **({"corpus": corpus} if corpus else {}), "training_sheets": info["sources"],
            "n_records": len(d["trans"]["nx"]), "n_strokes": len(d["strokes"]), "sigma_w": d["meta"].get("sigma_w"),
            "selection": d["meta"].get("selection", {}), "training": {k: v for k, v in info.items()},
            "experiment": "tools/gesture/experiments/hands_trails.py learn", **extra}
    note = ("Round-11 hands_trails hand (results/hands_trails-2026-10-17.md). Token statistics only: corpora "
            "give behaviours, never forms.")
    if kind == "diwani":
        note += " Line statistics only: outputs are line studies after the hand, never legible Arabic."
    entry = {"id": key, "kind": "hand", "label": label, "version": 1, "provenance": prov, "policy": "generative",
             "notes": note}
    L.save(entry, {"tables.npz": L.npz_bytes(arrays), "sheet.json.gz": L.json_gz_bytes(sheet)}, overwrite=overwrite)
    g = L.load("hand", key)                         # through the policy gate
    assert L.deep_equal(g.to_json(), d), key
    return L.entry("hand", key)["size_bytes"]


def stage_save(a):
    keep = [k for k in KEEP if not a.only or k in a.only.split(",")]
    for k in keep:
        print(k, save_hand(k), "bytes", flush=True)


# ---------------------------------------------------------------------------
# stage: measure — distinctness vs every library hand, self-consistency, dancers
# ---------------------------------------------------------------------------

SIZE = (1000, 1200)
N_SHEETS = 6
VC = ROOT / ".local/gesture/out/voices_corpus"
HYB_REAL = ROOT / ".local/gesture/out/hybrid_hands/panel_real.json"


def _features(d: Drawing) -> dict:
    from gesture import medium, panel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if len(d.strokes) < 2:
            return {}
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W)
    return f


def _gen_job(args):
    hand, i = args
    t = time.perf_counter()
    if (OUT / "grammars" / f"{hand}.json").exists():
        g = gm.Grammar.load(OUT / "grammars" / f"{hand}.json")
    else:
        from gesture.kit import library as L
        g = L.load("hand", hand)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            d = gm.generate_drawing(g, np.random.default_rng(9000 + i), SIZE)   # = voices_corpus seeds
        except Exception as e:  # noqa: BLE001
            return f"{hand}|gen{i}", None, repr(e)
    (OUT / "gen").mkdir(parents=True, exist_ok=True)
    d.save(OUT / "gen" / f"{hand}__{i}.json")
    return f"{hand}|gen{i}", _features(d), round(time.perf_counter() - t, 1)


def _train_job(path):
    return path.stem.split("__")[0] + "|" + path.stem, _features(Drawing.load(path))


def _win_job(args):
    label, rel, n = args
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ds = dance_windows(rel, n)
    return label, [(d.source, _features(d)) for d in ds]


def stage_measure(a):
    from gesture import hybrid as hy
    sys.path.insert(0, str(HERE / "experiments"))
    import voices_corpus as vc
    from gesture.kit import library as L
    new = [k for k in all_new() if (OUT / "grammars" / f"{k}.json").exists()]
    lib = sorted(e["id"] for e in L.entries("hand") if e["id"] not in new)
    pf = OUT / "panel_gen.json"
    gen = json.loads(pf.read_text()) if pf.exists() else {}
    cached = json.loads((VC / "panel_gen.json").read_text())       # library hands, same seeds & code
    for k, v in cached.items():
        if k.split("|")[0] in lib and k not in gen:
            gen[k] = v
    jobs = [(h, i) for h in lib + new for i in range(N_SHEETS) if f"{h}|gen{i}" not in gen]
    tf_ = OUT / "panel_train.json"
    train = json.loads(tf_.read_text()) if tf_.exists() else {}
    tjobs = [p for p in sorted((OUT / "train").glob("*.json"))
             if (p.stem.split("__")[0] + "|" + p.stem) not in train]
    print(len(jobs), "sheets to generate,", len(tjobs), "training drawings to measure", flush=True)
    with ProcessPoolExecutor(JOBS) as ex:
        for k, f in ex.map(_train_job, tjobs):
            train[k] = f
        tf_.write_text(json.dumps(train))
        for n, (k, f, info) in enumerate(ex.map(_gen_job, jobs)):
            if f is None:
                print("FAIL", k, info, flush=True)
                continue
            gen[k] = f
            if n % 6 == 0:
                print(n, k, info, "s", flush=True)
                pf.write_text(json.dumps(gen))
    pf.write_text(json.dumps(gen))
    real = json.loads(HYB_REAL.read_text())
    rep = vc.measure_report(lib + new, gen, train, real, hy)
    for h in list(rep["hands"]):
        r = rep["hands"][h]
        cand = {o: v for o, v in r["dist"].items() if o in lib and o != h}
        o = min(cand, key=cand.get)
        r["nearest_library"], r["dist_nearest_library"] = o, cand[o]
        r["new"] = h in new
        r["score"] = round(cand[o] / max(r["tightness"], 1e-9), 3)
    (OUT / "measure.json").write_text(json.dumps(rep, indent=1))
    rows = ["| # | hand | nearest library hand (dist) | 2nd nearest | tightness | self-recog | score = dist / tightness |",
            "|---|---|---|---|---|---|---|"]
    H = rep["hands"]
    order = sorted(H, key=lambda h: (not H[h]["new"], -H[h]["score"]))
    for i, h in enumerate(order, 1):
        r = H[h]
        d2 = sorted(((v, o) for o, v in r["dist"].items() if o in lib and o != h))[1]
        rows.append(f"| {i} | {h}{'' if r['new'] else ' (library)'} | {r['nearest_library']} "
                    f"({r['dist_nearest_library']:.2f}) | {d2[1]} ({d2[0]:.2f}) | {r['tightness']:.2f} | "
                    f"{r['self_recognition']:.2f} | {r['score']:.2f} |")
    md = "\n".join(rows) + "\n"
    (OUT / "measure.md").write_text(md)
    print(md)


def stage_dancers(a):
    """Can the six dancers be told apart (same task), and how does that compare with
    telling one company's movement QUALITIES apart? Real trail windows, panel space,
    standard preprocessing; balanced classes; leave-one-out nearest centroid and
    5-fold logistic regression; pairwise AUC."""
    from gesture import hybrid as hy
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    pf = OUT / "panel_windows.json"
    win = json.loads(pf.read_text()) if pf.exists() else {}
    jobs = [(f"who|{k}", rel, TEST_WINDOWS) for k, (rel, _) in DANCERS.items()] + \
           [(f"how|{q}", rel, TEST_WINDOWS) for q, rel in STOCOS.items()]
    jobs = [j for j in jobs if j[0] not in win]
    with ProcessPoolExecutor(JOBS) as ex:
        for label, rows in ex.map(_win_job, jobs):
            win[label] = rows
            print(label, len(rows), flush=True)
    pf.write_text(json.dumps(win))
    tf, names, _, _ = hy.projector(json.loads(HYB_REAL.read_text()))
    out = {}
    for test in ("who", "how"):
        keys = sorted(k for k in win if k.startswith(test + "|"))
        X, y = [], []
        for ci, k in enumerate(keys):
            for _, f in win[k][:TEST_WINDOWS]:
                if f:
                    X.append([f.get(n, np.nan) for n in names])
                    y.append(ci)
        Z, y = tf(np.array(X, float)), np.array(y)
        hits = 0
        for i in range(len(y)):
            m = np.arange(len(y)) != i
            cen = np.array([Z[m & (y == c)].mean(0) for c in range(len(keys))])
            hits += int(np.argmin(np.linalg.norm(cen - Z[i], axis=1)) == y[i])
        lr = cross_val_score(LogisticRegression(C=0.3, max_iter=4000), Z, y,
                             cv=StratifiedKFold(5, shuffle=True, random_state=0)).mean()
        rng = np.random.default_rng(0)
        null = np.mean([cross_val_score(LogisticRegression(C=0.3, max_iter=4000), Z, rng.permutation(y),
                                        cv=StratifiedKFold(5, shuffle=True, random_state=0)).mean()
                        for _ in range(10)])
        pair = {}
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                m = (y == i) | (y == j)
                pair[f"{keys[i].split('|')[1]}~{keys[j].split('|')[1]}"] = round(hy.cv_auc(Z[m], (y[m] == i).astype(int)), 3)
        out[test] = {"classes": [k.split("|")[1] for k in keys], "n": int(len(y)), "chance": round(1 / len(keys), 3),
                     "loo_nearest_centroid": round(hits / len(y), 3), "logreg_cv5": round(float(lr), 3),
                     "logreg_shuffled_labels": round(float(null), 3),
                     "pair_auc_median": round(float(np.median(list(pair.values()))), 3),
                     "pair_auc_min": min(pair.items(), key=lambda kv: kv[1]), "pair_auc": pair}
        print(test, {k: v for k, v in out[test].items() if k != "pair_auc"}, flush=True)
    (OUT / "dancers.json").write_text(json.dumps(out, indent=1))


# ---------------------------------------------------------------------------
# stage: sheets — every image from kit.run + kit.preview (recipe JSON beside it)
# ---------------------------------------------------------------------------

TRAIL_IDS = ("trail_miner", "trail_beetle", "trail_slime", "trail_borer", "trail_oaknet", "trail_grazer", "trail_tracks")
FLY_IDS = tuple(FLY)
DANCER_IDS = tuple(DANCERS)
SHEETS = OUT / "sheets"


def _save_jpg(img, path: Path, max_kb: int = 380, max_side: int = 2600):
    img = img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    for q in (86, 80, 72, 64, 56, 48, 40):
        img.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024:
            break
    print("wrote", path.relative_to(ROOT), f"{path.stat().st_size // 1024} KB", flush=True)


def _tile(name: str, recipe: dict, px: float = 4.0):
    from gesture import kit
    sheet = kit.run(recipe)
    kit.preview(sheet, SHEETS / f"{name}.jpg", px_per_mm=px, label=recipe.get("label", "auto"))
    return kit.render_image(sheet, px_per_mm=px, label=recipe.get("label", "auto"))


def _contact(name: str, tiles: list[tuple[str, dict]], cols: int, title: str, px: float = 4.0,
             to_results: bool = False):
    """Render each recipe (image + recipe beside it in SHEETS), tile them; the contact
    sheet's cell recipes go to <name>.recipe.json beside it."""
    from gesture import kit
    SHEETS.mkdir(parents=True, exist_ok=True)
    imgs, recs = [], {}
    for nm, r in tiles:
        t = time.perf_counter()
        try:
            imgs.append(_tile(f"{name}__{nm}", r, px))
            recs[nm] = json.loads((SHEETS / f"{name}__{nm}.recipe.json").read_text())
        except Exception as e:  # noqa: BLE001
            print("FAIL", nm, repr(e), flush=True)
            continue
        print(f"  {nm:<40} {time.perf_counter() - t:5.1f} s", flush=True)
    sheet = kit.contact(imgs, cols, title=title)
    p = SHEETS / f"{name}.jpg"
    _save_jpg(sheet, p, max_kb=900)
    (SHEETS / f"{name}.recipe.json").write_text(json.dumps({"title": title, "cells": recs}, indent=1))
    if to_results:
        q = RES / f"hands_trails-{name}.jpg"
        _save_jpg(sheet, q, max_kb=390)
        (RES / f"hands_trails-{name}.recipe.json").write_text(json.dumps({"title": title, "cells": recs}))


def specimen_recipe(h: str, seed: int = 7000) -> dict:
    parts = [{"voice": {"id": "hand", "hand": h, "length": 4.0}} for _ in range(6)]
    parts += [{"voice": {"id": "trail_sheet", "hand": h}} for _ in range(2)]
    return {"label": f"{h}: six single lines (hand voice, 4 R, seeds {seed}-{seed + 5}) + two whole sheets "
                     f"(trail_sheet: the hand's learned joins/branches); one common scale; bar = 10 mm",
            "frame": [267, 180], "seed": seed, "arranger": {"id": "trail_specimen", "cols": 4, "bar": 10.0},
            "parts": parts, "renderer": {"id": "wire", "pen": 0.35}}


def _one(h: str, seed: int, note: str = "", length: float = 4.0) -> dict:
    return {"label": f"{h}{note}", "frame": [120, 90], "seed": seed,
            "voice": {"id": "hand", "hand": h, "length": length}, "renderer": {"id": "wire", "pen": 0.35}}


def stage_sheets(a):
    from gesture import kit
    only = set(a.only.split(",")) if a.only else None
    want = lambda k: only is None or k in only  # noqa: E731
    SHEETS.mkdir(parents=True, exist_ok=True)
    rep = json.loads((OUT / "measure.json").read_text())["hands"]
    # 1. specimens: one sheet per new hand
    if want("specimens"):
        for h in TRAIL_IDS + FLY_IDS + DANCER_IDS:
            r = specimen_recipe(h)
            sheet = kit.run(r)
            kit.preview(sheet, SHEETS / f"specimen-{h}.jpg", px_per_mm=5, label=r["label"])
            print("specimen", h, flush=True)
        for grp, ids, cols in (("specimens-trails", TRAIL_IDS + FLY_IDS, 3), ("specimens-dancers", DANCER_IDS, 2)):
            ims = [Image.open(SHEETS / f"specimen-{h}.jpg") for h in ids]
            sh = kit.contact(ims, cols, title=f"hands_trails specimens: {', '.join(ids)}")
            _save_jpg(sh, SHEETS / f"{grp}.jpg", max_kb=1500)
            _save_jpg(sh, RES / f"hands_trails-{grp}.jpg", max_kb=390)
            (RES / f"hands_trails-{grp}.recipe.json").write_text(json.dumps(
                {h: json.loads((SHEETS / f"specimen-{h}.recipe.json").read_text()) for h in ids}))
    # 2. atlas: each new hand beside its two nearest library hands (panel space), same seed
    if want("atlas"):
        for grp, ids in (("atlas-trails", TRAIL_IDS + FLY_IDS), ("atlas-dancers", DANCER_IDS)):
            tiles = []
            for i, h in enumerate(ids):
                r = rep[h]
                near = sorted(((v, o) for o, v in r["dist"].items() if o not in all_new()))[:2]
                tiles.append((h, _one(h, 7100 + i, "  [NEW]")))
                for v, o in near:
                    tiles.append((f"{h}-near-{o}", _one(o, 7100 + i, f"  (nearest to {h}: {v:.2f})")))
            _contact(grp, tiles, 3, f"hands atlas: each new hand (left) beside its two nearest library hands in "
                     f"panel space (distance in cloud radii; ~1 = touching), one line each, same seed",
                     px=4.0, to_results=True)
    # 3. combinations
    if want("miner"):
        tiles = []
        for i, (frass, fill, w1, ch) in enumerate([("line", "chamber", 3.2, 2.2), ("wander", "chamber", 4.0, 2.0),
                                                   ("line", "late", 3.6, 2.4), ("none", "chamber", 5.0, 1.8)]):
            tiles.append((f"gallery-{i}", {
                "label": f"trail_miner as a mine: widens with age to {w1} mm, frass {frass}, fill {fill}, "
                         f"chamber {ch}x (seed {7200 + i})",
                "frame": [180, 130], "seed": 7200 + i, "voice": {"id": "hand", "hand": "trail_miner", "length": 3.5},
                "renderer": {"id": "trail_gallery", "pen": 0.3, "w0": 0.3, "w1": w1, "grow": 1.8,
                             "chamber": ch, "fill": fill, "frass": frass}}))
        tiles.append(("gallery-drift", {
            "label": "drift trail_miner > trail_grazer > trail_miner as one mine (seed 7210)",
            "frame": [180, 130], "seed": 7210,
            "voice": {"id": "drift", "hands": ["trail_miner", "trail_grazer", "trail_miner"], "length": 5.0},
            "renderer": {"id": "trail_gallery", "pen": 0.3, "w0": 0.3, "w1": 3.6, "grow": 2.0, "chamber": 2.2,
                         "frass": "wander"}}))
        tiles.append(("gallery-many", {
            "label": "three miners on one leaf: trail_miner, trail_miner, trail_slime, each a mine (seed 7211)",
            "frame": [180, 130], "seed": 7211,
            "parts": [{"voice": {"id": "hand", "hand": h, "length": 2.2}} for h in
                      ("trail_miner", "trail_miner", "trail_slime")],
            "renderer": {"id": "trail_gallery", "pen": 0.3, "w0": 0.25, "w1": 2.6, "grow": 1.8, "chamber": 2.2,
                         "frass": "line"}}))
        _contact("miner", tiles, 2, "leaf-miner hand inked as a mine: the gallery widens as the larva grows and "
                 "ends in a round chamber (renderer trail_gallery)", px=4.0, to_results=True)
    if want("brood"):
        tiles = []
        for i, (m, l, n) in enumerate([("trail_beetle", "trail_oaknet", 16), ("trail_beetle", "trail_slime", 16),
                                       ("trail_miner", "trail_borer", 12), ("trail_grazer", "dancer_cristel", 14),
                                       ("trail_tracks", "fly_fru", 12), ("dancer_zachary", "trail_grazer", 18)]):
            tiles.append((f"brood-{m}-{l}", {
                "label": f"brood gallery: mother {m}, {n} larvae {l} (seed {7300 + i})",
                "frame": [180, 130], "seed": 7300 + i,
                "voice": {"id": "trail_brood", "mother": m, "larvae": l, "count": n, "mother_length": 0.8},
                "renderer": {"id": "trail_gallery", "pen": 0.3, "w0": 0.3, "w1": 1.6, "chamber": 2.0}}))
        _contact("brood", tiles, 2, "brood galleries as a voice (trail_brood): branching kept as structure, one "
                 "hand for the mother line, another for the larvae; each larva widens into its pupal chamber",
                 px=4.0, to_results=True)
    if want("answer"):
        tiles = []
        pairs = [("dancer_cristel", "trail_miner"), ("dancer_anna", "trail_grazer"), ("fly_fru", "trail_miner"),
                 ("dancer_zachary", "trail_oaknet"), ("fly_open", "trail_tracks"), ("dancer_marija", "trail_beetle")]
        for i, (d, t) in enumerate(pairs):
            tiles.append((f"answer-{d}-{t}", {
                "label": f"one surface: {d} (wire 0.25, 5 R) answered by {t} as a mine (seed {7400 + i})",
                "frame": [180, 130], "seed": 7400 + i,
                "parts": [{"voice": {"id": "hand", "hand": d, "length": 5.0},
                           "renderer": {"id": "wire", "pen": 0.25}},
                          {"voice": {"id": "hand", "hand": t, "length": 2.5},
                           "renderer": {"id": "trail_gallery", "pen": 0.3, "w0": 0.3, "w1": 3.4, "grow": 1.8,
                                        "chamber": 2.2, "frass": "line"}}],
                "renderer": {"id": "wire", "pen": 0.3}}))
        _contact("answer", tiles, 2, "a trail hand answering a dancer hand on one surface: the dancer's line as wire, "
                 "the trail as a mine that swells into its chamber", px=4.0, to_results=True)
    if want("dancers"):
        tiles = [(h, _one(h, 7500, f"  ({DANCERS[h][1].split(': ')[1]}, Unusual Poses)", 5.0)) for h in DANCER_IDS]
        tiles += [(f"{h}-b", _one(h, 7501, "", 5.0)) for h in DANCER_IDS]
        _contact("six-dancers", tiles, 6, "six dancers, one task: one line per dancer hand, seed 7500 (top) and "
                 "7501 (bottom)", px=4.0, to_results=False)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    stages = {k[6:]: v for k, v in globals().items() if k.startswith("stage_")}
    for s in (list(stages) if a.stage == "all" else a.stage.split(",")):
        t = time.time()
        stages[s](a)
        print(f"[{s}] {time.time() - t:.0f} s", flush=True)


if __name__ == "__main__":
    main()

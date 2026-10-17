"""New hands from rivers (research round 11, exploration 1a, 2026-10-17).

    .local/gesture/.venv/bin/python tools/gesture/experiments/hands_rivers.py <stage> [--only a,b]

Rivers were used only as structure and as a channel-width regime field
(round 8, earth_lines). Here they are learned as HANDS: line grammars from
curvature along arc length, saved in the library, measured against every
existing hand.

stages:
  extract  river drawings on disk → .local/gesture/out/hands_rivers/train/*.json
           - meander stretches (GRWL vectors, single-channel main stems
             150–700 m wide) at three zooms, in channel widths along the
             channel: 60 w (bend), 150 w (meander), 400 w (belt); each
             stretch is one drawing of 5 pieces (pen lifts of 1.5 w)
           - oxbow outlines (OSM water=oxbow, closed ways), drawings = the
             oxbows of one 0.12° cell, as the land lays them
           - cut-off bends (Li et al. 2026 xlsx: neck / chute centrelines)
           - Anavilhanas (Sentinel-2 20MQC, NIR): the narrow channels
             between islands (threads) and the island outlines (lenses)
  learn    grammars (grammar.learn, min_len_w = 12 like round 9) saved as
           library `hand` entries river_*; the loop set (oxbow + neck
           curvature profiles) and the braid statistics (island lenses) as
           library `river_loops` / `river_braid` entries for the voices in
           kit/voices_rivers.py
  measure  distinctness (74-feature panel, standard preprocessing σ ≥ 7 w +
           medium projection, round-9 protocol: 6 generated sheets per hand
           at seeds 9000+i) and self-consistency (split halves: 12 sheets per
           new hand, half A vs half B vs every other hand); the voices'
           outputs measured the same way
  sheets   images through kit.run + kit.preview (recipe JSON beside each)
  all

Nominal line width: a river's channel width is not ink width. Every river
drawing gets the dance convention, width = 0.0025 × R (R = the drawing's
bounding-box diagonal), so σ = 2 w fits and the panel's σ ≥ 7 w sit at the
same fraction of R as for the dance hands. The zoom (stretch length in
channel widths) is then the only scale knob: round 8 found κ·R median 33 → 3.8
as a window shrinks; with nominal widths, 60 / 150 / 400 w stretches give
κ·R medians ≈ 4 / 9 / 21 (the human band is 2–7.5).

Outputs: .local/gesture/out/hands_rivers/. Write-up:
tools/gesture/results/hands_rivers-2026-10-17.md.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import warnings
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import earth_lines as el  # noqa: E402
from gesture import grammar as gm  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/hands_rivers"
RES = HERE / "results"
EARTH = ROOT / ".local/gesture/corpus/earth"
JOBS = 2
W_OVER_R = 0.0025          # nominal line width / R (the dance convention)
CANVAS = 1000.0            # drawings are scaled so their long side is this many px
RIGHTS_GRWL = "GRWL V01.01, Allen & Pavelsky 2018, CC BY 4.0 (earth-physics-harvest.csv)"
RIGHTS_OSM = "OpenStreetMap contributors, ODbL (earth-physics-harvest.csv)"
RIGHTS_LI = "Li, Edmonds, Konsoer, Constantine et al. 2026, Zenodo 18340214, CC BY 4.0 (earth-physics-harvest.csv)"
RIGHTS_S2 = "Copernicus Sentinel-2 L2A (Earth Search COG), free use (earth-physics-harvest.csv)"


def _rng(*tags) -> np.random.Generator:
    import zlib
    return np.random.default_rng([zlib.crc32(str(t).encode()) for t in tags])


def _arclen(p: np.ndarray) -> np.ndarray:
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


def _resample(p: np.ndarray, step: float) -> np.ndarray:
    s = _arclen(p)
    if s[-1] <= step:
        return p.copy()
    t = np.linspace(0.0, s[-1], int(math.ceil(s[-1] / step)) + 1)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def to_drawing(lines: list[np.ndarray], source: str, meta: dict, closed_ok: bool = True) -> Drawing:
    """Lines (any metric units) → a Drawing on a CANVAS px canvas, every
    stroke at the nominal width W_OVER_R × R."""
    allp = np.vstack(lines)
    lo, span = allp.min(axis=0), np.ptp(allp, axis=0)
    k = CANVAS / max(float(span.max()), 1e-9)
    pts = [(l - lo) * k + 10.0 for l in lines]
    R = float(np.hypot(*(span * k)))
    w = W_OVER_R * R
    size = (int(span[0] * k + 20), int(span[1] * k + 20))
    rs = [_resample(p, 0.5 * w) for p in pts]
    strokes = [Stroke(q, width=np.full(len(q), w)) for q in rs]
    return Drawing(strokes, source=source, size=size, meta={**meta, "units_per_px": 1.0 / k, "w_over_R": W_OVER_R})


# ---------------------------------------------------------------------------
# meander stems (GRWL vectors)
# ---------------------------------------------------------------------------

STEM_TILES = ("SB18", "SB19", "SB20", "SC18", "SC20")
ZOOMS = {"river_bend": 60, "river_meander": 150, "river_belt": 400}   # stretch length, channel widths
N_PIECES = 5
MAX_DRAWINGS = 14


def stems(tile: str, wlo: float = 150.0, whi: float = 700.0) -> list[dict]:
    """Single-channel main stems of one GRWL tile: GRWL segments whose
    MEDIAN width is in [wlo, whi] m and median nchannels ≤ 1, lakes dropped,
    split at vertex gaps > 100 m; resampled at w/4 and smoothed at 1.5 w
    (the 30 m pixel stair is not the river). Metres, local frame."""
    polys, tab = el.load_grwl(tile)
    w, nc, lk = tab["width_m"], tab["nchannels"], tab["lakeFlag"]
    idx = np.flatnonzero(~(lk > 0))
    seg = tab["segmentID"][idx]
    order = np.lexsort((tab["segmentInd"][idx], seg))
    idx, seg = idx[order], seg[order]
    cuts = np.flatnonzero(np.diff(seg)) + 1
    lon0, lat0 = float(np.median(tab["lon"])), float(np.median(tab["lat"]))
    out = []
    for g in np.split(np.arange(len(idx)), cuts):
        ii = idx[g]
        wm = float(np.nanmedian(w[ii]))
        if not (wlo <= wm <= whi) or float(np.nanmedian(nc[ii])) > 1:
            continue
        P = el.lonlat_to_m(tab["lon"][ii], tab["lat"][ii], lon0, lat0)
        gaps = np.flatnonzero(np.linalg.norm(np.diff(P, axis=0), axis=1) > 100.0) + 1
        for a, b in zip(np.r_[0, gaps], np.r_[gaps, len(P)]):
            p = P[a:b]
            if len(p) < 20:
                continue
            q = _resample(p, wm / 4)
            if len(q) < 4 * 60:
                continue
            q = gaussian_filter1d(q, 1.5 * 4, axis=0, mode="nearest")
            out.append({"tile": tile, "segment": int(seg[g[0]]), "w": wm, "points": q})
    return out


def meander_drawings(name: str, zoom_w: int) -> list[Drawing]:
    """Stretches of zoom_w channel widths along the channel, one drawing
    each (5 pieces, 1.5 w pen lifts). Round-robin over tiles, longest stems
    first, non-overlapping stretches, MAX_DRAWINGS per zoom."""
    per_tile = []
    n = 4 * zoom_w
    for t in STEM_TILES:
        by_stem = []
        for st in sorted(stems(t), key=lambda s: (-len(s["points"]), s["segment"])):
            by_stem.append([(st, a) for a in range(0, len(st["points"]) - n + 1, n)])
        # interleave stems: first stretch of every stem, then the second, ...
        depth = max((len(b) for b in by_stem), default=0)
        per_tile.append([b[j] for j in range(depth) for b in by_stem if j < len(b)])
    picks = []
    k = 0
    while len(picks) < MAX_DRAWINGS and any(k < len(c) for c in per_tile):
        for c in per_tile:
            if k < len(c) and len(picks) < MAX_DRAWINGS:
                picks.append(c[k])
        k += 1
    out = []
    seen = set()
    for st, a in picks:
        key = (st["tile"], st["segment"], a)
        if key in seen:
            continue
        seen.add(key)
        p = st["points"][a:a + n]
        gap = 6        # 1.5 w at w/4 sampling
        pieces = [pc[gap:-gap] if len(pc) > 3 * gap else pc for pc in np.array_split(p, N_PIECES)]
        out.append(to_drawing(pieces, f"grwl:{st['tile']}:seg{st['segment']}@{a}+{n}",
                              {"kind": "river", "zoom_w": zoom_w, "channel_w_m": st["w"], "tile": st["tile"]}))
    return out


# ---------------------------------------------------------------------------
# oxbows (OSM) and cut-off bends (Li et al.)
# ---------------------------------------------------------------------------

def oxbow_outlines() -> list[dict]:
    """Closed OSM ways tagged water=oxbow: outline in local metres (each
    oxbow its own frame origin = centroid), centroid lon/lat, perimeter."""
    d = json.loads((EARTH / "osm-oxbows-amazon/oxbows_overpass.json").read_text())
    out = []
    for e in sorted(d["elements"], key=lambda e: e["id"]):
        if e["type"] != "way" or not e.get("geometry"):
            continue
        g = e["geometry"]
        if len(g) < 12 or g[0] != g[-1]:
            continue
        lon = np.array([p["lon"] for p in g])
        lat = np.array([p["lat"] for p in g])
        c = (float(lon.mean()), float(lat.mean()))
        P = el.lonlat_to_m(lon, lat, *c)
        per = float(_arclen(P)[-1])
        if per < 1500.0:
            continue
        out.append({"id": e["id"], "lonlat": c, "points": P, "perimeter_m": per})
    return out


def _start_at_horn(P: np.ndarray) -> np.ndarray:
    """A closed outline re-started at its sharpest turn (a crescent's horn),
    smoothed at 1/50 of the perimeter (OSM outlines are digitised polygons:
    their vertices are corners the lake does not have); first point
    repeated at the end."""
    q = smooth_outline(P)
    qs = q
    d1 = np.gradient(qs, axis=0)
    th = np.unwrap(np.arctan2(d1[:, 1], d1[:, 0]))
    k = np.abs(np.gradient(th))
    i = int(np.argmax(gaussian_filter1d(k, 3, mode="wrap")))
    qs = np.roll(qs, -i, axis=0)
    return np.vstack([qs, qs[:1]])


def smooth_outline(P: np.ndarray, n: int = 256, sigma: float = 5.0) -> np.ndarray:
    """A closed outline at n equal arc steps, smoothed with wrap-around."""
    q = _resample(P[:-1] if np.allclose(P[0], P[-1]) else P, _arclen(P)[-1] / n)
    return gaussian_filter1d(q, sigma, axis=0, mode="wrap")


def oxbow_drawings(max_drawings: int = 14, cell: float = 0.12, min_n: int = 4) -> list[Drawing]:
    """The oxbows of one 0.12° cell = one drawing, as the land lays them
    (cells with ≥ min_n oxbows, most populated first)."""
    ox = oxbow_outlines()
    cells: dict = {}
    for o in ox:
        k = (int(math.floor(o["lonlat"][0] / cell)), int(math.floor(o["lonlat"][1] / cell)))
        cells.setdefault(k, []).append(o)
    keys = sorted((k for k in cells if len(cells[k]) >= min_n), key=lambda k: (-len(cells[k]), k))[:max_drawings]
    out = []
    for k in keys:
        os_ = cells[k]
        c = (k[0] * cell + cell / 2, k[1] * cell + cell / 2)
        lines = []
        for o in os_:
            off = el.lonlat_to_m([o["lonlat"][0]], [o["lonlat"][1]], *c)[0]
            lines.append(_start_at_horn(o["points"]) + off)
        out.append(to_drawing(lines, f"osm-oxbows:cell{k[0]},{k[1]}",
                              {"kind": "oxbow", "n": len(lines), "osm_ids": [o["id"] for o in os_]}))
    return out


def read_xlsx(path) -> list[dict]:
    """First sheet of an .xlsx as rows of {header: value} (strings or
    floats), parsed by hand (no openpyxl in the research venv)."""
    import xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    z = zipfile.ZipFile(path)
    ss = [("".join(t.itertext())) for t in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns)]
    sh = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for r in sh.find("m:sheetData", ns).findall("m:row", ns):
        vals = {}
        for c in r.findall("m:c", ns):
            ref = c.get("r")
            col = "".join(ch for ch in ref if ch.isalpha())
            v = c.find("m:v", ns)
            if v is None:
                continue
            vals[col] = ss[int(v.text)] if c.get("t") == "s" else float(v.text)
        rows.append(vals)
    head = rows[0]
    return [{head[c]: v for c, v in r.items() if c in head} for r in rows[1:]]


def cutoff_bends() -> list[dict]:
    """Li et al. cut-off bends: centreline (UTM m), type (Neck / Chute),
    La/w, Lc/w, width."""
    out = []
    for i, r in enumerate(read_xlsx(EARTH / "li-amazon-cutoffs/cutoff_data_Amazon_upload.xlsx")):
        try:
            x = np.array(json.loads(r["centerline_x"]), float)
            y = np.array(json.loads(r["centerline_y"]), float)
        except (KeyError, TypeError, ValueError):
            continue
        if len(x) < 6:
            continue
        P = np.column_stack([x - x.mean(), -(y - y.mean())])     # y down
        out.append({"i": i, "type": str(r.get("cutoff_type_supervised", "")), "points": P,
                    "La_w": float(r.get("La/w", np.nan)) if not isinstance(r.get("La/w"), str) else np.nan,
                    "Lc_w": float(r.get("Lc/w", np.nan)) if not isinstance(r.get("Lc/w"), str) else np.nan,
                    "width_m": float(r.get("mean_width_La", np.nan))
                    if not isinstance(r.get("mean_width_La"), str) else np.nan})
    return out


# ---------------------------------------------------------------------------
# Anavilhanas (Sentinel-2 NIR): threads and island lenses
# ---------------------------------------------------------------------------

S2_BRAID = "s2-20MQC-20200729"
S2_PX_M = 10.0


def anavilhanas_masks():
    """(water, narrow, wide) boolean masks at 10 m from B08 (NIR): water is
    dark. narrow = water channels < ~400 m wide (an opening with a 20 px
    disk removes them from `wide`)."""
    import tifffile
    from skimage import morphology
    a = tifffile.imread(EARTH / S2_BRAID / f"{S2_BRAID}_B08_30km.tif").astype(np.float64)
    water = a < 700.0
    water = morphology.remove_small_objects(water, max_size=199)
    water = ~morphology.remove_small_objects(~water, max_size=199)
    wide = morphology.opening(water, morphology.disk(20))
    narrow = water & ~wide
    narrow = morphology.remove_small_objects(narrow, max_size=299)
    return water, narrow, wide


def anavilhanas_threads(max_side: int = 1500) -> Drawing:
    """The narrow channels as lines: the mask drawn dark on white through
    the default extractor (`extract_hybrid`)."""
    from PIL import Image
    from gesture import extract_hybrid
    _, narrow, _ = anavilhanas_masks()
    g = np.where(narrow, 0.05, 0.95)
    im = Image.fromarray((g * 255).astype(np.uint8))
    im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    g = np.asarray(im, np.float64) / 255.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = extract_hybrid.extract(g, source=f"{S2_BRAID}:narrow")
    return d


def anavilhanas_islands(min_area_px: int = 400) -> list[dict]:
    """Island lenses: land components that do not touch the tile edge,
    outline (m, y down), area, length/width from the second moments,
    orientation."""
    from skimage import measure
    water, _, _ = anavilhanas_masks()
    land = ~water
    lab = measure.label(land, connectivity=1)
    out = []
    H, W = land.shape
    for rp in measure.regionprops(lab):
        y0, x0, y1, x1 = rp.bbox
        if y0 == 0 or x0 == 0 or y1 == H or x1 == W or rp.area < min_area_px:
            continue
        sub = np.pad(rp.image, 2)
        cs = measure.find_contours(sub.astype(float), 0.5)
        if not cs:
            continue
        c = max(cs, key=len)
        P = np.column_stack([c[:, 1] + x0 - 2, c[:, 0] + y0 - 2]) * S2_PX_M
        out.append({"label": int(rp.label), "points": P, "area_m2": float(rp.area * S2_PX_M ** 2),
                    "length_m": float(rp.axis_major_length * S2_PX_M),
                    "width_m": float(max(rp.axis_minor_length, 1.0) * S2_PX_M),
                    "orientation": float(rp.orientation), "solidity": float(rp.solidity)})
    return out


# ---------------------------------------------------------------------------
# stage: extract
# ---------------------------------------------------------------------------

def _save_drawings(name: str, ds: list[Drawing]) -> dict:
    od = OUT / "train"
    od.mkdir(parents=True, exist_ok=True)
    for f in od.glob(f"{name}__*.json"):
        f.unlink()
    for i, d in enumerate(ds):
        d.save(od / f"{name}__{i}.json")
    return {"drawings": len(ds), "strokes": int(sum(len(d.strokes) for d in ds)),
            "sources": [d.source for d in ds]}


def _extract_job(name: str):
    t = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if name in ZOOMS:
            ds = meander_drawings(name, ZOOMS[name])
        elif name == "river_oxbow":
            ds = oxbow_drawings()
        elif name == "river_threads":
            d = anavilhanas_threads()
            # tile the 30 km scene 2×2, like the round-8 hands (more drawings, R per quarter)
            from gesture import hybrid as hy
            ds = [Drawing(x.strokes, x.source, x.size, {**x.meta, "kind": "threads"})
                  for x in hy.tile_drawing(d, 2, 2)]
            ds = [renominal(x) for x in ds if len(x.strokes) >= 3]
        else:
            raise ValueError(name)
    info = _save_drawings(name, ds)
    info["secs"] = round(time.perf_counter() - t, 1)
    return name, info


def renominal(d: Drawing) -> Drawing:
    """Re-width an extracted drawing at the nominal W_OVER_R × R (channel
    width is not ink width)."""
    R = d.ref_length()
    w = W_OVER_R * R
    return Drawing([Stroke(s.points, np.full(len(s.points), w), s.closed, s.meta) for s in d.strokes if len(s) >= 3],
                   d.source, d.size, {**d.meta, "w_over_R": W_OVER_R, "extracted_width_px":
                                      float(np.median([np.median(s.width) for s in d.strokes if s.width is not None]
                                                      or [0]))})


HAND_SETS = ("river_bend", "river_meander", "river_belt", "river_oxbow", "river_threads")


def stage_extract(a):
    keys = [k for k in HAND_SETS if not a.only or k in a.only.split(",")]
    rows = {}
    with ProcessPoolExecutor(JOBS) as ex:
        for name, info in ex.map(_extract_job, keys):
            rows[name] = info
            print(name, {k: v for k, v in info.items() if k != "sources"}, flush=True)
    p = OUT / "extract.json"
    old = json.loads(p.read_text()) if p.exists() else {}
    old.update(rows)
    p.write_text(json.dumps(old, indent=1))


# ---------------------------------------------------------------------------
# stage: learn — grammars (library `hand`), loop set, braid statistics
# ---------------------------------------------------------------------------

COMMIT = "0dc1785"     # HEAD when the round started; the files here are uncommitted research
LABELS = {
    "river_bend": ("River: bend (60 w)", "Amazon main stems (GRWL), stretches of 60 channel widths along the "
                   "channel, 5 pieces each: about one bend per sheet (κ·R in the human band)"),
    "river_meander": ("River: meander (150 w)", "Amazon main stems (GRWL), stretches of 150 channel widths, "
                      "5 pieces each: a train of bends"),
    "river_belt": ("River: meander belt (400 w)", "Amazon main stems (GRWL), stretches of 400 channel widths, "
                   "5 pieces each: the dense river (κ·R ≈ 20, outside the human band)"),
    "river_oxbow": ("River: oxbow outlines", "OSM water=oxbow closed outlines in the western/central Amazon, "
                    "the oxbows of one 0.12° cell per drawing, each outline started at its sharpest horn"),
    "river_threads": ("River: Anavilhanas threads", "the narrow (< ~400 m) channels between the Anavilhanas "
                      "islands, Rio Negro (Sentinel-2 20MQC 2020-07-29, NIR < 700), extract_hybrid, 2×2 tiles"),
}
CORPUS_IDS = {
    "river_bend": ["grwl-vec-" + t for t in STEM_TILES], "river_meander": ["grwl-vec-" + t for t in STEM_TILES],
    "river_belt": ["grwl-vec-" + t for t in STEM_TILES], "river_oxbow": ["osm-oxbows-amazon"],
    "river_threads": [S2_BRAID],
}
RIGHTS = {"river_bend": RIGHTS_GRWL, "river_meander": RIGHTS_GRWL, "river_belt": RIGHTS_GRWL,
          "river_oxbow": RIGHTS_OSM, "river_threads": RIGHTS_S2}


def train_drawings(name: str) -> list[Drawing]:
    fs = sorted((OUT / "train").glob(f"{name}__*.json"), key=lambda f: int(f.stem.split("__")[1]))
    return [Drawing.load(f) for f in fs]


def _learn_job(name: str):
    t = time.perf_counter()
    ds = train_drawings(name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = gm.learn(ds, name=name, min_len_w=12)
    (OUT / "grammars").mkdir(parents=True, exist_ok=True)
    g.save(OUT / "grammars" / f"{name}.json")
    return name, {"sources": [d.source for d in ds], "strokes": len(g.strokes), "records": len(g.trans["nx"]),
                  "min_len_w": 12, "drawings": len(ds), "secs": round(time.perf_counter() - t, 1)}


def extraction_method(name: str) -> str:
    if name in ZOOMS:
        return (f"GRWL vertices of segments with median width 150–700 m and median nchannels ≤ 1 "
                f"(lakes dropped), resampled at w/4, smoothed at 1.5 w; non-overlapping stretches of "
                f"{ZOOMS[name]} w round-robin over tiles {', '.join(STEM_TILES)}, longest stems first; "
                f"each stretch cut into {N_PIECES} pieces with 1.5 w pen lifts")
    if name == "river_oxbow":
        return "closed OSM ways tagged water=oxbow, ≥ 12 vertices, perimeter ≥ 1.5 km; 0.12° cells with ≥ 4"
    return "Sentinel-2 B08 < 700 → water; opening with a 20 px disk = wide water; narrow = water − wide; " \
           "extract_hybrid on the narrow mask at 1500 px; 2×2 tiles"


def save_hand(name: str, info: dict, overwrite: bool = True) -> int:
    from gesture.kit import library as L
    d = json.loads((OUT / "grammars" / f"{name}.json").read_text())
    arrays, sheet = L.encode_hand(d)
    label, desc = LABELS[name]
    zoom = {"zoom_w": ZOOMS[name], "zoom_unit": "channel widths along the channel per drawing"} \
        if name in ZOOMS else {}
    prov = {"research_file": str((OUT / "grammars" / f"{name}.json").relative_to(ROOT)), "research_commit": COMMIT,
            "description": desc, "rights": RIGHTS[name], "corpus": "earth", "corpus_ids": CORPUS_IDS[name],
            "training_sheets": info["sources"], **zoom, "extraction": extraction_method(name),
            "line_width": f"nominal: {W_OVER_R} × R (channel width is not ink width; the dance convention)",
            "n_records": len(d["trans"]["nx"]), "n_strokes": len(d["strokes"]),
            "sigma_w": d["meta"].get("sigma_w"), "selection": d["meta"].get("selection", {}), "training": info,
            "experiment": "tools/gesture/experiments/hands_rivers.py learn"}
    entry = {"id": name, "kind": "hand", "label": label, "version": 1, "provenance": prov, "policy": "generative",
             "notes": "Round-11 hands_rivers hand (results/hands_rivers-2026-10-17.md). Curvature along arc "
                      "length only: rivers give behaviours, never forms."}
    L.save(entry, {"tables.npz": L.npz_bytes(arrays), "sheet.json.gz": L.json_gz_bytes(sheet)}, overwrite=overwrite)
    g = L.load("hand", name)
    assert L.deep_equal(g.to_json(), d), name
    return L.entry("hand", name)["size_bytes"]


MAX_LOOPS = 600


def loops_arrays() -> tuple[dict, dict]:
    """Turning-function profiles: oxbow outlines (closed; φ = θ − 2πu) and
    cut-off bends (open; θ(u)), plus per-loop aspect / gap and source ids."""
    from gesture.kit.voices_rivers import loop_profile
    ox = oxbow_outlines()
    rng = _rng("loops", "oxbow")
    sel = sorted(rng.choice(len(ox), min(MAX_LOOPS, len(ox)), replace=False).tolist())
    phi, asp, ids = [], [], []
    for i in sel:
        p, a = loop_profile(smooth_outline(ox[i]["points"]), True)
        if a > 12 or np.ptp(p) > 4 * np.pi:          # slivers and self-crossing digitisations
            continue
        phi.append(p)
        asp.append(a)
        ids.append(ox[i]["id"])
    cb = cutoff_bends()
    nphi, ngap, ntype, nla = [], [], [], []
    for c in cb:
        q = _resample(c["points"], _arclen(c["points"])[-1] / 256)
        q = gaussian_filter1d(q, 6.0, axis=0, mode="nearest")
        th, gap = loop_profile(q, False)
        if th[-1] < np.pi * 0.8:                     # not much of a loop
            continue
        nphi.append(th)
        ngap.append(gap)
        ntype.append(0 if c["type"].lower().startswith("neck") else 1)
        nla.append(c["La_w"])
    arrays = {"oxbow_phi": np.array(phi, np.float32), "oxbow_aspect": np.array(asp, np.float32),
              "oxbow_osm_id": np.array(ids, np.int64), "neck_phi": np.array(nphi, np.float32),
              "neck_gap": np.array(ngap, np.float32), "neck_type": np.array(ntype, np.int8),
              "neck_La_w": np.array(nla, np.float32)}
    info = {"n_oxbow_osm": len(ox), "n_oxbow_kept": len(phi), "n_cutoffs": len(cb), "n_neck_kept": len(nphi),
            "n_neck_type_neck": int(sum(1 for t in ntype if t == 0)),
            "oxbow_aspect_q": [round(float(v), 2) for v in np.quantile(asp, [0.1, 0.5, 0.9])],
            "neck_gap_q": [round(float(v), 3) for v in np.quantile(ngap, [0.1, 0.5, 0.9])] if ngap else []}
    return arrays, info


def braid_arrays() -> tuple[dict, dict]:
    """Island lenses of Anavilhanas: aspect (major/minor axis) and the
    half-width profile along the major axis (32 bins, max = 1)."""
    isl = anavilhanas_islands()
    asp, prof, area = [], [], []
    for it in isl:
        a = it["length_m"] / it["width_m"]
        if a < 1.5 or it["solidity"] < 0.6:
            continue
        P_ = it["points"] - it["points"].mean(0)
        ev, V = np.linalg.eigh(np.cov(P_.T))
        ax = P_ @ V[:, 1]
        cr = P_ @ V[:, 0]
        bins = np.linspace(ax.min(), ax.max(), 33)
        w = np.zeros(32)
        for k in range(32):
            m = (ax >= bins[k]) & (ax <= bins[k + 1])
            w[k] = np.ptp(cr[m]) if m.sum() >= 2 else 0.0
        w = gaussian_filter1d(w, 2.0)
        if w.max() <= 0:
            continue
        w = w / w.max()
        w[0] = w[-1] = 0.0
        asp.append(a)
        prof.append(w)
        area.append(it["area_m2"])
    arrays = {"aspect": np.array(asp, np.float32), "profile": np.array(prof, np.float32),
              "area_m2": np.array(area, np.float32)}
    info = {"n_islands": len(isl), "n_kept": len(asp),
            "aspect_q": [round(float(v), 2) for v in np.quantile(asp, [0.1, 0.5, 0.9])],
            "area_km2_q": [round(float(v) / 1e6, 3) for v in np.quantile(area, [0.1, 0.5, 0.9])]}
    return arrays, info


def save_aux(overwrite: bool = True) -> dict:
    from gesture.kit import library as L
    arrays, info = loops_arrays()
    L.save({"id": "river_cutoffs", "kind": "river_loops", "label": "River cut-off loops", "version": 1,
            "policy": "generative",
            "provenance": {"corpus": "earth", "corpus_ids": ["osm-oxbows-amazon", "li-amazon-cutoffs"],
                           "rights": f"{RIGHTS_OSM}; {RIGHTS_LI}", "research_commit": COMMIT,
                           "training_sheets": ["osm-oxbows-amazon", "li-amazon-cutoffs"],
                           "extraction": "turning function θ(u) at 128 equal arc steps; oxbows: closed OSM outlines "
                                         "(φ = θ − 2πu, traced counter-clockwise, aspect ≤ 12), random sample of "
                                         f"{MAX_LOOPS} (seeded); cut-off bends: Li et al. centrelines smoothed, "
                                         "θ(end) ≥ 0.8π", "counts": info,
                           "experiment": "tools/gesture/experiments/hands_rivers.py learn"},
            "notes": "Read by the river_loops voice (kit/voices_rivers.py). Shapes are resampled curvature "
                     "profiles: behaviours, never a map."},
           {"loops.npz": L.npz_bytes(arrays)}, overwrite=overwrite)
    b_arrays, b_info = braid_arrays()
    L.save({"id": "river_anavilhanas", "kind": "river_braid", "label": "Braid: Anavilhanas islands", "version": 1,
            "policy": "generative",
            "provenance": {"corpus": "earth", "corpus_ids": [S2_BRAID], "rights": RIGHTS_S2,
                           "research_commit": COMMIT, "training_sheets": [S2_BRAID],
                           "extraction": "B08 < 700 → water; land components not touching the tile edge, ≥ 400 px "
                                         "(4 ha); aspect = major/minor axis (≥ 1.5, solidity ≥ 0.6); half-width "
                                         "profile along the major axis in 32 bins", "counts": b_info,
                           "experiment": "tools/gesture/experiments/hands_rivers.py learn"},
            "notes": "Read by the river_braid voice (kit/voices_rivers.py)."},
           {"braid.npz": L.npz_bytes(b_arrays)}, overwrite=overwrite)
    return {"river_cutoffs": info, "river_anavilhanas": b_info}


def stage_learn(a):
    keys = [k for k in HAND_SETS if not a.only or k in a.only.split(",")]
    rows = {}
    if keys:
        with ProcessPoolExecutor(JOBS) as ex:
            for name, info in ex.map(_learn_job, keys):
                info["size_bytes"] = save_hand(name, info)
                rows[name] = info
                print(name, {k: v for k, v in info.items() if k != "sources"}, flush=True)
    p = OUT / "learn.json"
    old = json.loads(p.read_text()) if p.exists() else {}
    old.update(rows)
    if not a.only or "aux" in a.only.split(","):
        old["aux"] = save_aux()
        print("aux", old["aux"], flush=True)
    p.write_text(json.dumps(old, indent=1))


# ---------------------------------------------------------------------------
# stage: measure — distinctness and self-consistency
# ---------------------------------------------------------------------------

SIZE = (1000, 1200)
N_STD = 6                  # round-9 protocol: 6 generated sheets per hand, seeds 9000 + i
N_NEW = 12                 # new hands: 12, so halves A (0–5) and B (6–11) can be compared
VC_GEN = ROOT / ".local/gesture/out/voices_corpus/panel_gen.json"      # read only
HYB_REAL = ROOT / ".local/gesture/out/hybrid_hands/panel_real.json"    # read only
NEW_HANDS = HAND_SETS
VOICE_SPECS = {   # voice-level comparison: 3 lines per sheet (grid), same for every hand
    "V:river_loops-knot": {"id": "river_loops", "mode": "knot", "host": "river_meander"},
    "V:river_loops-alone": {"id": "river_loops", "mode": "alone", "family": "both", "n": 14},
    "V:river_loops-beside": {"id": "river_loops", "mode": "beside", "host": "river_meander"},
    "V:river_braid": {"id": "river_braid"},
}


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
    from gesture.kit import library as L
    g = L.load("hand", hand)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            d = gm.generate_drawing(g, np.random.default_rng(9000 + i), SIZE)
        except Exception as e:  # noqa: BLE001
            return f"{hand}|gen{i}", None, repr(e)
    (OUT / "gen").mkdir(parents=True, exist_ok=True)
    d.save(OUT / "gen" / f"{hand}__{i}.json")
    return f"{hand}|gen{i}", _features(d), ""


def _train_job(path):
    d = Drawing.load(path)
    return path.stem.split("__")[0] + "|" + path.stem, _features(d)


def marks_drawing(sheet, px_per_mm: float = 10.0) -> Drawing:
    """A kit Sheet's marks as a px Drawing at the nominal width."""
    pts = [np.asarray(m.points) * px_per_mm for m in sheet.marks if len(m.points) >= 3]
    allp = np.vstack(pts)
    R = float(np.hypot(*np.ptp(allp, axis=0)))
    w = W_OVER_R * R
    return Drawing([Stroke(p, np.full(len(p), w)) for p in pts], "kit", (int(allp[:, 0].max()) + 10,
                                                                          int(allp[:, 1].max()) + 10), {})


def voice_sheet_recipe(key: str, i: int) -> dict:
    if key.startswith("V:"):
        v = VOICE_SPECS[key]
    else:
        v = {"id": "hand", "hand": key.split(":", 1)[1], "length": 4.0}
    return {"label": f"{key} #{i}", "frame": [300, 120], "seed": 9100 + 10 * i,
            "arranger": {"id": "grid", "cols": 3}, "parts": [{"voice": dict(v)} for _ in range(3)],
            "renderer": {"id": "wire", "pen": 0.35}}


def _voice_job(args):
    key, i = args
    from gesture import kit
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            sh = kit.run(voice_sheet_recipe(key, i))
        except Exception as e:  # noqa: BLE001
            return f"{key}|v{i}", None, repr(e)
    return f"{key}|v{i}", _features(marks_drawing(sh)), ""


def split_half(hands, gen, tf, names) -> dict:
    """Self-consistency: centroid of sheets 0–5 vs 6–11 of the same hand,
    in units of the mean RMS radius, against the distance from each half to
    the nearest OTHER hand's centroid (all 6/12 sheets)."""
    def Z(keys):
        X = np.array([[gen[k].get(n, np.nan) for n in names] for k in keys], float)
        return tf(X)
    grp = {}
    for k in gen:
        if gen[k]:
            grp.setdefault(k.split("|")[0], []).append(k)
    cen, rad = {}, {}
    for h, ks in grp.items():
        z = Z(sorted(ks))
        cen[h], rad[h] = z.mean(0), float(np.sqrt(np.mean(np.sum((z - z.mean(0)) ** 2, 1))))
    out = {}
    for h in hands:
        ks = sorted(grp.get(h, []), key=lambda k: int(k.rsplit("gen", 1)[1]))
        A = [k for k in ks if int(k.rsplit("gen", 1)[1]) < N_STD]
        B = [k for k in ks if int(k.rsplit("gen", 1)[1]) >= N_STD]
        if len(A) < 3 or len(B) < 3:
            continue
        za, zb = Z(A), Z(B)
        ra = float(np.sqrt(np.mean(np.sum((za - za.mean(0)) ** 2, 1))))
        rb = float(np.sqrt(np.mean(np.sum((zb - zb.mean(0)) ** 2, 1))))
        r = 0.5 * (ra + rb)
        d_ab = float(np.linalg.norm(za.mean(0) - zb.mean(0)) / r)
        others = {o: min(np.linalg.norm(za.mean(0) - cen[o]), np.linalg.norm(zb.mean(0) - cen[o]))
                  / (0.5 * (r + rad[o])) for o in cen if o != h}
        o = min(others, key=others.get)
        out[h] = {"d_halves": round(d_ab, 3), "nearest_other": o, "d_nearest_other": round(float(others[o]), 3),
                  "consistent": bool(d_ab < others[o])}
    return out


def closure_report() -> dict:
    """Does a hand close its loops? Share of strokes whose end returns
    within 5 % of the stroke's length of its start: training drawings vs
    the grammar's generated sheets (the oxbow outlines are all closed)."""
    def share(ds):
        c = [np.linalg.norm(st.points[-1] - st.points[0]) / max(st.length(), 1e-9) for d in ds for st in d.strokes]
        return round(float(np.mean(np.array(c) < 0.05)), 3) if c else None, len(c)
    out = {}
    for h in NEW_HANDS:
        tr = share([Drawing.load(f) for f in sorted((OUT / "train").glob(f"{h}__*.json"))])
        ge = share([Drawing.load(f) for f in sorted((OUT / "gen").glob(f"{h}__*.json"))])
        out[h] = {"train_closed": tr[0], "train_n": tr[1], "gen_closed": ge[0], "gen_n": ge[1]}
    return out


def stage_measure(a):
    import experiments.voices_corpus as vc
    from gesture import hybrid as hy
    from gesture.kit import library as L
    lib_hands = [e["id"] for e in L.entries("hand") if e["policy"] == "generative"]
    old_hands = [h for h in lib_hands if h not in NEW_HANDS]
    pf = OUT / "panel_gen.json"
    gen = json.loads(pf.read_text()) if pf.exists() else {}
    vgen = json.loads(VC_GEN.read_text())
    for k, f in vgen.items():                      # round-9 sheets of the library hands, same protocol
        if k.split("|")[0] in old_hands:
            gen.setdefault(k, f)
    jobs = [(h, i) for h in old_hands for i in range(N_STD) if f"{h}|gen{i}" not in gen]
    jobs += [(h, i) for h in NEW_HANDS for i in range(N_NEW) if f"{h}|gen{i}" not in gen]
    tf_ = OUT / "panel_train.json"
    train = json.loads(tf_.read_text()) if tf_.exists() else {}
    tjobs = [p for p in sorted((OUT / "train").glob("*.json")) if f"{p.stem.split('__')[0]}|{p.stem}" not in train]
    vf = OUT / "panel_voice.json"
    vfeat = json.loads(vf.read_text()) if vf.exists() else {}
    vkeys = [f"H:{h}" for h in lib_hands] + list(VOICE_SPECS)
    vjobs = [(k, i) for k in vkeys for i in range(N_STD) if f"{k}|v{i}" not in vfeat]
    print(len(jobs), "sheets,", len(tjobs), "training drawings,", len(vjobs), "voice sheets", flush=True)
    with ProcessPoolExecutor(JOBS) as ex:
        for k, f in ex.map(_train_job, tjobs):
            train[k] = f
        tf_.write_text(json.dumps(train))
        for k, f, err in ex.map(_gen_job, jobs):
            if f is None:
                print("FAIL", k, err, flush=True)
                continue
            gen[k] = f
        pf.write_text(json.dumps(gen))
        for k, f, err in ex.map(_voice_job, vjobs):
            if f is None:
                print("FAIL", k, err, flush=True)
                continue
            vfeat[k] = f
        vf.write_text(json.dumps(vfeat))
    real = json.loads(HYB_REAL.read_text())
    hands = old_hands + list(NEW_HANDS)
    std = {k: v for k, v in gen.items() if int(k.rsplit("gen", 1)[1]) < N_STD}   # equal n per hand
    rep = vc.measure_report(hands, std, train, real, hy)
    tf, names, _, _ = hy.projector(real)
    rep["split_half"] = split_half(list(NEW_HANDS), {k: v for k, v in gen.items()
                                                     if k.split("|")[0] in hands}, tf, names)
    # (the standard projector already leaves out w_ and end_ features: hybrid._matrix — geometry only,
    # so the nominal river width is not what places these hands)
    rep["closure"] = closure_report()
    rep["vs_named"] = {h: {o: rep["hands"][h]["dist"].get(o) for o in ("matisse", "meander69", "hokusai",
                                                                      "dance_levitation", "lichtenberg")}
                       for h in NEW_HANDS if h in rep["hands"]}
    # the zooms against each other (is a zoom a different hand?)
    rep["zoom_pairs"] = {f"{x}~{y}": rep["hands"][x]["dist"].get(y) for x, y in
                         (("river_bend", "river_meander"), ("river_meander", "river_belt"),
                          ("river_bend", "river_belt")) if x in rep["hands"]}
    # voice level: every library hand through the `hand` voice vs the river voices (3 lines per sheet)
    strip = lambda k: k[2:] if k.startswith("H:") else k  # noqa: E731  (seed-hand names for vc's table)
    vrep = vc.measure_report([strip(k) for k in vkeys], {strip(k): v for k, v in vfeat.items()}, {}, real, hy)
    rep["voice_level"] = {k: {kk: vrep["hands"][strip(k)][kk] for kk in ("nearest", "dist_nearest",
                                                                           "auc_vs_nearest", "tightness",
                                                                           "self_recognition")}
                          for k in vkeys if strip(k) in vrep["hands"]}
    rep["voice_level_dist"] = {k: vrep["hands"][k]["dist"] for k in list(VOICE_SPECS) + list(NEW_HANDS)
                               if k in vrep["hands"]}
    (OUT / "measure.json").write_text(json.dumps(rep, indent=1))
    md = measure_md(rep)
    (OUT / "measure.md").write_text(md)
    print(md)


def measure_md(rep: dict) -> str:
    H = rep["hands"]
    rows = ["| # | hand | nearest existing hand (dist) | farthest existing | AUC vs nearest | self-recog (LOO) | "
            "halves A↔B dist | nearest other to a half (dist) | consistent | tightness |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for i, h in enumerate(NEW_HANDS, 1):
        if h not in H:
            continue
        r = H[h]
        ex = {o: v for o, v in r["dist"].items() if o not in NEW_HANDS}
        o = min(ex, key=ex.get)
        far = max(ex, key=ex.get)
        sh = rep["split_half"].get(h, {})
        rows.append(f"| {i} | {h} | {o} ({ex[o]:.2f}) | {far} ({ex[far]:.2f}) | {r['auc_vs_nearest']:.2f} | "
                    f"{r['self_recognition']:.2f} | {sh.get('d_halves', float('nan')):.2f} | "
                    f"{sh.get('nearest_other', '–')} ({sh.get('d_nearest_other', float('nan')):.2f}) | "
                    f"{'yes' if sh.get('consistent') else 'no'} | {r['tightness']:.2f} |")
    rows.append("")
    rows.append("zoom pairs: " + ", ".join(f"{k} {v:.2f}" for k, v in rep["zoom_pairs"].items() if v is not None))
    rows.append("")
    rows.append("closed strokes (end within 5 % of length of the start), training → generated: " + ", ".join(
        f"{h} {v['train_closed']} → {v['gen_closed']}" for h, v in rep["closure"].items()))
    rows.append("")
    rows.append("distances to named hands: " + "; ".join(
        f"{h}: " + ", ".join(f"{o} {v:.2f}" for o, v in d.items() if v is not None) for h, d in rep["vs_named"].items()))
    rows.append("")
    rows.append("| # | through the kit (3 lines per sheet) | nearest (dist) | nearest existing hand (dist) | "
                "AUC vs nearest | self-recog | tightness |")
    rows.append("|---|---|---|---|---|---|---|")
    V = rep["voice_level"]
    D = rep["voice_level_dist"]
    for i, k in enumerate([k for k in V if k.startswith("V:") or k[2:] in NEW_HANDS], 1):
        r = V[k]
        kk = k[2:] if k.startswith("H:") else k
        ex = {o: v for o, v in D.get(kk, {}).items() if o not in NEW_HANDS and not o.startswith("V:")}
        o = min(ex, key=ex.get) if ex else "–"
        rows.append(f"| {i} | {k} | {r['nearest']} ({r['dist_nearest']:.2f}) | {o} ({ex.get(o, float('nan')):.2f}) | "
                    f"{r['auc_vs_nearest']:.2f} | {r['self_recognition']:.2f} | {r['tightness']:.2f} |")
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# stage: sheets — every tile from kit.run + kit.preview (recipe beside it);
# contact sheets get the cell recipes in a .recipe.json beside them
# ---------------------------------------------------------------------------

TILE = [130, 100]
PX = 4.0
PEN = 0.35


def _wire(r: dict, pen: float = PEN) -> dict:
    r.setdefault("renderer", {"id": "wire", "pen": pen})
    return r


def hand_tile(h: str, seed: int, length: float = 5.0, joins: str = "smooth", note: str = "") -> dict:
    return _wire({"label": f"{h}{note}  (hand, {length:g} R, seed {seed}{', chain' if joins == 'chain' else ''})",
                  "frame": TILE, "seed": seed, "voice": {"id": "hand", "hand": h, "length": length, "joins": joins}})


def voice_tile(label: str, v: dict, seed: int, renderer: dict | None = None, frame=None) -> dict:
    r = {"label": f"{label}  (seed {seed})", "frame": frame or TILE, "seed": seed, "voice": dict(v)}
    if renderer:
        r["renderer"] = renderer
    return _wire(r)


def _scale_bar(img, mm: float = 20.0, px: float = PX):
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    W, H = img.size
    x1, y = W - 14, H - 40
    x0 = x1 - mm * px
    d.line([(x0, y), (x1, y)], fill=(0x10, 0x0F, 0x0F), width=3)
    d.line([(x0, y - 6), (x0, y + 6)], fill=(0x10, 0x0F, 0x0F), width=2)
    d.line([(x1, y - 6), (x1, y + 6)], fill=(0x10, 0x0F, 0x0F), width=2)
    d.text((x0, y - 20), f"{mm:g} mm", fill=(0x6F, 0x6E, 0x69))
    return img


def source_tile(name: str, i: int, size_px=(520, 400)):
    """A training drawing (the river itself, at nominal width) drawn as a tile."""
    from PIL import Image, ImageDraw
    from gesture import kit
    d = Drawing.load(OUT / "train" / f"{name}__{i}.json")
    img = Image.new("RGB", size_px, kit.core.PAPER)
    dr = ImageDraw.Draw(img)
    allp = np.vstack([st.points for st in d.strokes])
    lo = allp.min(0)
    k = min((size_px[0] - 30) / max(np.ptp(allp[:, 0]), 1), (size_px[1] - 50) / max(np.ptp(allp[:, 1]), 1))
    for st in d.strokes:
        q = (st.points - lo) * k + 15
        dr.line([tuple(x) for x in q], fill=kit.core.INK, width=2)
    dr.text((10, size_px[1] - 22), f"source: {d.source[:60]}", fill=(0xAF, 0x30, 0x29))
    return img


def sheet_set(name: str, cells: list, cols: int, title: str, keep_res: bool = False):
    """cells: (cell name, recipe | PIL image). Tiles → OUT/sheets (each with
    its recipe); contact → OUT/<name>.jpg + <name>.recipe.json (cell
    recipes); keep_res also copies it to results (≤ 400 KB)."""
    from gesture import kit
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    imgs, recipes = [], {}
    for nm, r in cells:
        if not isinstance(r, dict):
            imgs.append(r)
            continue
        t = time.perf_counter()
        try:
            sh = kit.run(r)
        except Exception as e:  # noqa: BLE001
            print("FAIL", nm, repr(e), flush=True)
            continue
        kit.preview(sh, OUT / "sheets" / f"{name}__{nm}.jpg", px_per_mm=PX, label=r["label"])
        imgs.append(_scale_bar(kit.render_image(sh, px_per_mm=PX, label=r["label"])))
        recipes[nm] = sh.recipe
        print(f"  {nm:<36} {time.perf_counter() - t:5.1f} s", flush=True)
    c = kit.contact(imgs, cols, title=title)
    _save(c, OUT / f"{name}.jpg", 950)
    (OUT / f"{name}.recipe.json").write_text(json.dumps(recipes, indent=1, default=str))
    if keep_res:
        _save(c, RES / f"hands_rivers-{name}.jpg", 390)
        (RES / f"hands_rivers-{name}.recipe.json").write_text(json.dumps(recipes, indent=1, default=str))


def _save(img, path: Path, max_kb: int):
    from PIL import Image
    img = img.convert("RGB")
    lim = 2600 if max_kb > 400 else 2200
    if max(img.size) > lim:
        img.thumbnail((lim, lim), Image.Resampling.LANCZOS)
    for q in (88, 82, 75, 68, 60, 52, 45):
        img.save(path, quality=q)
        if path.stat().st_size <= max_kb * 1024:
            break
    print("wrote", path.relative_to(ROOT), f"{path.stat().st_size // 1024} KB", flush=True)


SPECIMEN_SEEDS = (7000, 7001, 7002, 7003, 7004)


def specimen_cells(h: str) -> list:
    cells = [("source", source_tile(h, 0))] if (OUT / "train" / f"{h}__0.json").exists() else []
    cells += [(f"s{sd}", hand_tile(h, sd)) for sd in SPECIMEN_SEEDS[:4]]
    cells += [("chain", hand_tile(h, SPECIMEN_SEEDS[4], joins="chain"))]
    return cells


def stage_sheets(a):
    only = set(a.only.split(",")) if a.only else None
    want = lambda k: only is None or k in only  # noqa: E731
    rep = json.loads((OUT / "measure.json").read_text())
    keep = {"spec-river_bend", "spec-river_belt", "spec-loops", "spec-braid", "neighbours", "combos"}
    for h in NEW_HANDS:
        if want(f"spec-{h}"):
            sheet_set(f"spec-{h}", specimen_cells(h), 3,
                      f"{h}: {LABELS[h][0]} — the source (a training drawing), then the hand alone, one line, "
                      f"4 seeds smooth + 1 chain joins, wire 0.35", keep_res=f"spec-{h}" in keep)
    if want("spec-loops"):
        V = {"id": "river_loops"}
        cells = [("source-ox", source_tile("river_oxbow", 0)),
                 ("alone-ox", voice_tile("loops alone, oxbow", {**V, "mode": "alone", "family": "oxbow", "n": 12}, 7000)),
                 ("alone-neck", voice_tile("loops alone, neck", {**V, "mode": "alone", "family": "neck", "n": 12}, 7001)),
                 ("knot", voice_tile("knot on river_meander", {**V, "mode": "knot"}, 7000)),
                 ("knot-big", voice_tile("knot, size 1.4, 4 loops", {**V, "mode": "knot", "n": 4, "size": 1.4}, 7002)),
                 ("beside", voice_tile("beside river_meander", {**V, "mode": "beside", "n": 7}, 7001))]
        sheet_set("spec-loops", cells, 3, "river_loops voice: cut-off loops learned from 582 OSM oxbow outlines and "
                  "885 cut-off bends (Li et al.); closed by construction", keep_res=True)
    if want("spec-braid"):
        V = {"id": "river_braid"}
        cells = [("b4", voice_tile("braid, 4 threads on river_bend (islands as measured)", V, 7000)),
                 ("b4-smooth", voice_tile("same, islands eased (smooth 3)", {**V, "smooth": 3.0}, 7000)),
                 ("b3-meander", voice_tile("3 threads on river_meander", {**V, "threads": 3, "host": "river_meander",
                                                                          "width": 0.035, "smooth": 3.0}, 7001)),
                 ("b6-wide", voice_tile("6 threads, wide", {**V, "threads": 6, "width": 0.06, "smooth": 3.0}, 7002)),
                 ("b2-open", voice_tile("2 threads, islands everywhere", {**V, "threads": 2, "open": 1.0,
                                                                         "node": 0.5, "smooth": 3.0}, 7003)),
                 ("b5-rare", voice_tile("5 threads, rare islands", {**V, "threads": 5, "open": 0.3, "smooth": 3.0},
                                        7004)),
                 ("b4-long", voice_tile("4 threads, long bold backbone (6 R, width 0.08)",
                                        {**V, "length": 6.0, "width": 0.08, "smooth": 3.0}, 7006)),
                 ("b3-beads", voice_tile("3 threads, beads at the splits",
                                         {**V, "threads": 3, "smooth": 3.0, "width": 0.06}, 7007,
                                         renderer={"id": "dev_beads", "shape": "gather", "at": "peak", "line": "wire",
                                                   "size": 4.0, "thr": 0.3, "pen": PEN})),
                 ("b4-matisse", voice_tile("4 threads on matisse (dud?)", {**V, "host": "matisse", "length": 4.0},
                                           7005))]
        sheet_set("spec-braid", cells, 3, "river_braid voice: threads split around island lenses learned from 14 "
                  "Anavilhanas islands (aspect, half-width profile) and rejoin; every thread one line", keep_res=True)
    if want("neighbours"):
        cells = []
        V = rep["voice_level_dist"]
        for h in NEW_HANDS:
            ex = {o: v for o, v in rep["hands"][h]["dist"].items() if o not in NEW_HANDS}
            order = sorted(ex, key=ex.get)
            kit_near = min(((o, v) for o, v in V.get(h, {}).items() if o not in NEW_HANDS and not o.startswith("V:")),
                           key=lambda t: t[1], default=(order[1], 0))[0]
            row = [(f"{h}-a", hand_tile(h, 7010)),
                   (f"{h}-near", hand_tile(order[0], 7010, note=f" [nearest to {h}, sheets]")),
                   (f"{h}-kitnear", hand_tile(kit_near if kit_near != order[0] else order[1], 7010,
                                              note=f" [nearest to {h}, {'kit' if kit_near != order[0] else '2nd'}]")),
                   (f"{h}-far", hand_tile(order[-1], 7010, note=f" [farthest from {h}]"))]
            cells += row
        sheet_set("neighbours", cells, 4, "each new river hand (left) beside its nearest existing hand (sheet "
                  "panel), its nearest through the kit, and its farthest — same seed, one line each", keep_res=True)
    if want("combos"):
        cells = [
            ("drift-mat-river-lich", voice_tile("drift matisse > river_meander > lichtenberg",
                                                {"id": "drift", "hands": ["matisse", "river_meander", "lichtenberg"],
                                                 "length": 7.0}, 7000, frame=[200, 130])),
            ("drift-scalejump", voice_tile("drift river_bend > river_belt > river_bend (scale jumps in one line)",
                                           {"id": "drift", "hands": ["river_bend", "river_belt", "river_bend"],
                                            "length": 7.0, "plateau": 0.25}, 7001, frame=[200, 130])),
            ("braid-beads", voice_tile("braid on river_bend, beads at the splits",
                                       {"id": "river_braid", "threads": 4}, 7002,
                                       renderer={"id": "dev_beads", "shape": "gather", "at": "peak", "line": "wire",
                                                 "size": 4.0, "thr": 0.3, "pen": PEN}, frame=[200, 130])),
            ("loops-stress-hokusai", voice_tile("oxbow loops as the stresses of hokusai (knot, loop_r 1.6, nib e)",
                                                {"id": "river_loops", "mode": "knot", "host": "hokusai", "n": 7,
                                                 "size": 1.0, "loop_r": 1.6}, 7003,
                                                renderer={"id": "nib", "style": "e", "pen": PEN}, frame=[200, 130])),
        ]
        two = {"label": "two voices on one surface: river_belt hand + oxbow loops alone", "frame": [200, 130],
               "seed": 7004, "arranger": {"id": "single"},
               "parts": [{"voice": {"id": "hand", "hand": "river_belt", "length": 6.0}},
                         {"voice": {"id": "river_loops", "mode": "alone", "family": "oxbow", "n": 9, "size": 0.22}}],
               "renderer": {"id": "wire", "pen": PEN}}
        three = {"label": "shikasta with abandoned oxbows beside its bends, nib e", "frame": [200, 130],
                 "seed": 7005, "voice": {"id": "river_loops", "mode": "beside", "host": "shikasta", "n": 6,
                                         "loop_r": 1.0, "size": 0.6},
                 "renderer": {"id": "nib", "style": "e", "pen": PEN}}
        cells += [("two-voices", two), ("shikasta-oxbows", three)]
        sheet_set("combos", cells, 2, "combinations through kit.run: river hands meeting other voices on one surface "
                  "(duds kept)", keep_res=True)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["extract", "learn", "measure", "sheets", "all"])
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    stages = ["extract", "learn", "measure", "sheets"] if a.stage == "all" else [a.stage]
    for s in stages:
        t = time.perf_counter()
        globals()[f"stage_{s}"](a)
        print(f"== {s} {time.perf_counter() - t:.1f} s", flush=True)


if __name__ == "__main__":
    main()

"""Regime fields and composition: sheets, plot candidates.

results/regime-field-2026-10-16.md. Library: gesture/regime_field.py.

    ../../.local/gesture/.venv/bin/python -m experiments.regime_compose hand
    ../../.local/gesture/.venv/bin/python -m experiments.regime_compose sheets [--only fields,...]
    ../../.local/gesture/.venv/bin/python -m experiments.regime_compose one --field sense --structure tree
    ../../.local/gesture/.venv/bin/python -m experiments.regime_compose plot

  hand     learn the shikasta grammar (grammar v6) on the policy-gated sheets
           only (calligraphy.require_generative) → out/regime_field/
  sheets   population sheets: fields × structures × hands (duds kept)
  one      a single composition at full size (scratch look)
  plot     A4 portrait SVG candidates + pen stats → out/plot_candidates_regimes/
  order    path ordering before/after on the round-6 + v2 candidates
           (results/pathorder-2026-10-16.md; vpype + the app estimator are
           imported READ-ONLY from the app venv for the comparison)
  polish   the Strahler sheet regenerated at 0.35 mm fill spacing, ordered,
           A4 + A3 → out/plot_candidates_r7/, previews → results/pathorder-*.jpg
Run from tools/gesture. ≤ 3 worker processes.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import regime_field as rf  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / ".local/gesture/out/regime_field"
PLOT = ROOT / ".local/gesture/out/plot_candidates_regimes"
RESULTS = Path(__file__).resolve().parents[1] / "results"
JOBS = 3
SIZE = (840, 1200)
PAPER_HEX = "#FFFCF0"      # flexoki paper (axibridge/static/css/flexoki.css)
INK_HEX = "#100F0F"        # flexoki black


# ---------------------------------------------------------------------------
# hands
# ---------------------------------------------------------------------------

def cmd_hand(a):
    from experiments import calligraphy_study as cs
    from gesture import calligraphy as C
    from gesture import grammar_v6_frozen as gm
    dd = cs.load_group("shikasta")
    allowed = C.filter_generative(dd)
    C.require_generative(list(allowed))          # hard policy gate
    drawings = [C.pen_strokes(d) for d in allowed.values()]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = gm.learn(drawings, name="shikasta", min_len_w=12)
    OUT.mkdir(parents=True, exist_ok=True)
    g.save(OUT / "grammar_shikasta.json")
    (OUT / "grammar_shikasta.meta.json").write_text(json.dumps(
        {"train": sorted(allowed), "excluded": sorted(set(dd) - set(allowed)), "min_len_w": 12,
         "policy": "calligraphy.require_generative (exercise/poetry/document only)"}, indent=1))
    print("shikasta grammar from", sorted(allowed))


def hands_by_regime(fobj, aspect, seed):
    """Lines in a Matisse hand, nib zones in the shikasta hand, masses in Hokusai."""
    return rf.hand_by_field(fobj, {"matisse": 0.0, "shikasta": 1.0, "hokusai": 2.0}, width=0.45)


def hands_zones(fobj, aspect, seed):
    return rf.hand_zones(["matisse", "hokusai", "ingres"], seed, scale=0.25, temp=0.3, aspect=aspect)


def hands_zones_script(fobj, aspect, seed):
    return rf.hand_zones(["matisse", "shikasta", "hokusai"], seed + 3, scale=0.2, temp=0.35, aspect=aspect)


HANDS = {"hokusai": "hokusai", "matisse": "matisse", "by_regime": hands_by_regime, "zones": hands_zones,
         "zones_script": hands_zones_script}


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render(c: rf.Composition, scale: float = 1.0, ss: int = 2, underlay=None):
    """RGB uint8 image of a composition (pen width to scale), optional
    field underlay (a Field: tinted by regime)."""
    from PIL import Image, ImageDraw
    W, H = c.size
    w, h = int(W * scale), int(H * scale)
    img = Image.new("RGB", (w * ss, h * ss), PAPER_HEX)
    if underlay is not None:
        g = underlay.raster((h // 4, w // 4)) / 2.0
        paper = np.array([0xFF, 0xFC, 0xF0], float)
        nib = np.array([0x43, 0x85, 0xBE], float)       # flexoki blue-400
        mass = np.array([0xD1, 0x4D, 0x41], float)      # flexoki red-400
        a1 = np.clip(g * 2, 0, 1)[..., None]
        a2 = np.clip(g * 2 - 1, 0, 1)[..., None]
        col = paper * (1 - 0.22 * a1) + nib * 0.22 * a1
        col = col * (1 - 0.3 * a2) + mass * 0.3 * a2
        img = Image.fromarray(col.astype(np.uint8)).resize((w * ss, h * ss), Image.Resampling.BILINEAR)
    d = ImageDraw.Draw(img)
    lw = max(int(round(c.meta["pen_px"] * scale * ss)), 1)
    for q in c.polylines:
        d.line([tuple(v) for v in q * scale * ss], fill=INK_HEX, width=lw, joint="curve")
    return np.asarray(img.resize((w, h), Image.Resampling.LANCZOS))


def label(arr, text, size=13):
    from PIL import Image, ImageDraw
    im = Image.fromarray(arr)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, im.width, size + 6], fill="#F2F0E5")
    d.text((4, 3), text, fill=INK_HEX)
    return np.asarray(im)


def _cell(spec):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t = time.perf_counter()
        hands = HANDS.get(spec.get("hands", "hokusai"), spec.get("hands"))
        c = rf.compose(spec["seed"], SIZE, structure=spec["structure"], field=spec["field"], hands=hands,
                       signs=spec.get("signs", 6), tremor=spec.get("tremor", 0.0), echo=spec.get("echo", 0),
                       drip=spec.get("drip", 0), structure_params=spec.get("params"),
                       nib_w=spec.get("nib_w"), shape_w=spec.get("shape_w"), label=spec["label"],
                       engine_name=spec.get("engine", "auto"), field_kw=spec.get("field_kw"),
                       script=spec.get("script", 0))
        sec = time.perf_counter() - t
    hat = rf.hatching_families(c.polylines, max_len=0.06 * SIZE[1], solid_gap=1.25 * c.meta["pen_px"])
    from experiments import composite as cp
    _, stt = cp.to_svg(c.drawing(), None, paper="A4", portrait=True)
    rec = {"label": spec["label"], **{k: v for k, v in c.meta.items() if k != "line_hands"},
           "hands_used": sorted(set(c.meta["line_hands"])), "sec": round(sec, 2), "hatching": hat,
           "pen_down_m": round(stt["pen_down_mm"] / 1000, 2), "paths": stt["paths"], "est_min": stt["est_min"]}
    img = render(c, spec.get("scale", 0.5), underlay=None)
    txt = spec["label"]
    img = label(img, txt)
    if spec.get("big"):
        from PIL import Image
        Image.fromarray(render(c, 1.0)).save(spec["big"], quality=90)
    return img, rec


def grid(cells, ncol: int, path: Path, quality: int = 80, max_kb: int = 600):
    from PIL import Image
    h, w = cells[0].shape[:2]
    nrow = (len(cells) + ncol - 1) // ncol
    sheet = np.full((h * nrow, w * ncol, 3), 200, np.uint8)
    for k, im in enumerate(cells):
        i, j = divmod(k, ncol)
        sheet[i * h:i * h + im.shape[0], j * w:j * w + im.shape[1]] = im
        sheet[i * h:(i + 1) * h, j * w] = 160
        sheet[i * h, j * w:(j + 1) * w] = 160
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(sheet)
    q = quality
    while True:
        img.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024 or q <= 40:
            break
        q -= 8
    print("wrote", path, f"{path.stat().st_size / 1024:.0f} KB (q{q})", flush=True)


def field_panel(path: Path, seed: int = 3):
    """Every preset field over its tree, as a tinted raster with the
    structure's centrelines (blue = nib, red = shape)."""
    from PIL import Image, ImageDraw
    cells = []
    st, _ = rf.make_structure("tree", np.random.default_rng(seed), SIZE)
    aspect = SIZE[1] / SIZE[0]
    for name in rf.PRESETS:
        f = rf.PRESETS[name](st, seed, aspect)
        g = f.raster((300, 210)) / 2.0
        paper = np.array([0xFF, 0xFC, 0xF0], float)
        nib = np.array([0x43, 0x85, 0xBE], float)
        mass = np.array([0xD1, 0x4D, 0x41], float)
        a1 = np.clip(g * 2, 0, 1)[..., None]
        a2 = np.clip(g * 2 - 1, 0, 1)[..., None]
        col = paper * (1 - 0.6 * a1) + nib * 0.6 * a1
        col = col * (1 - 0.8 * a2) + mass * 0.8 * a2
        im = Image.fromarray(col.astype(np.uint8))
        d = ImageDraw.Draw(im)
        for s in st.strokes:
            d.line([tuple(v) for v in s.points * 210 / SIZE[0]], fill=INK_HEX, width=1)
        cells.append(label(np.asarray(im), f"{name} ({rf.FAMILY[name]})", 11))
    grid(cells, 8, path, quality=88)


# ---------------------------------------------------------------------------
# sheets
# ---------------------------------------------------------------------------

def sheet_specs() -> dict[str, tuple[list[dict], int]]:
    S = {}
    # A: every field family on the one-trunk tree, one hand (the field alone)
    S["fields"] = ([{"label": f"{f} / tree / hokusai", "seed": 3, "structure": "tree", "field": f,
                     "hands": "hokusai", "signs": 0} for f in rf.PRESETS], 4)
    # B: structures × fields, hands keyed to regime (matisse line / shikasta nib / hokusai mass)
    rows = []
    for st in ("tree", "forest", "grammar", "single"):
        for f in ("sense", "noise", "strahler", "margins"):
            rows.append({"label": f"{st} / {f} / by-regime", "seed": 11, "structure": st, "field": f,
                         "hands": "by_regime", "signs": 6, "script": 5 if f in ("sense", "margins") else 0})
    S["structures"] = (rows, 4)
    # C: hand fields × structures on the 'sense' field
    rows = []
    for hs in ("hokusai", "by_regime", "zones", "zones_script"):
        for st in ("tree", "forest", "grammar"):
            rows.append({"label": f"{hs} / {st} / sense", "seed": 21, "structure": st, "field": "sense",
                         "hands": hs, "signs": 6, "tremor": 0.8, "script": 5})
    S["hands"] = (rows, 3)
    # D: coherence: bleed, shared lines, echoes/drips, axis organising
    rows = []
    for bl, bh, nm in ((0.01, 0.05, "abrupt"), (0.03, 0.6, "mixed"), (0.4, 1.2, "gradual")):
        rows.append({"label": f"noise bleed {nm}", "seed": 31, "structure": "tree", "field": "noise",
                     "field_kw": {"bleed_lo": bl, "bleed_hi": bh}, "hands": "by_regime", "signs": 4})
    rows.append({"label": "single line, trunk field (wire→nib→mass)", "seed": 32, "structure": "single",
                 "field": "trunk", "hands": "hokusai", "signs": 4})
    rows.append({"label": "sense, no signs/echo/drip", "seed": 33, "structure": "tree", "field": "sense",
                 "hands": "by_regime", "signs": 0})
    rows.append({"label": "sense + signs + echo + drips", "seed": 33, "structure": "tree", "field": "sense",
                 "hands": "by_regime", "signs": 8, "echo": 3, "drip": 6})
    rows.append({"label": "sense + all + script zones", "seed": 33, "structure": "tree", "field": "sense",
                 "hands": "by_regime", "signs": 8, "echo": 3, "drip": 6, "script": 6})
    rows.append({"label": "sense, no axis (field w/o trunk)", "seed": 33, "structure": "tree",
                 "field": "sense_noaxis", "hands": "by_regime", "signs": 8, "echo": 3, "drip": 6})
    rows.append({"label": "sense on forest, everything", "seed": 34, "structure": "forest", "field": "sense",
                 "hands": "zones_script", "signs": 8, "echo": 3, "drip": 6, "tremor": 0.8, "script": 6})
    S["coherence"] = (rows, 4)
    return S


def cmd_sheets(a):
    OUT.mkdir(parents=True, exist_ok=True)
    specs = sheet_specs()
    only = a.only.split(",") if a.only else list(specs) + ["panel"]
    if "panel" in only:
        field_panel(RESULTS / "regime-field-fields-raster.jpg")
    recs = []
    for name, (rows, ncol) in specs.items():
        if name not in only:
            continue
        t = time.time()
        with ProcessPoolExecutor(JOBS) as ex:
            res = list(ex.map(_cell, rows, chunksize=1))
        grid([r[0] for r in res], ncol, RESULTS / f"regime-field-{name}.jpg")
        for _, r in res:
            r["sheet"] = name
            recs.append(r)
        print(name, f"{time.time() - t:.0f}s", flush=True)
    with open(OUT / "sheets.jsonl", "a") as f:
        for r in recs:
            f.write(json.dumps(r, default=str) + "\n")
    for r in recs:
        print(r["sheet"], "|", r["label"], "| hands", r["hands_used"], "| shares",
              {k: round(v, 2) for k, v in r["regime_share"].items()}, "| hatch", r["hatching"]["families"],
              "| m", r["pen_down_m"], "| paths", r["paths"], "| min", r["est_min"], "|", r["sec"], "s", flush=True)


def cmd_one(a):
    from PIL import Image
    spec = {"label": a.label or f"{a.structure}/{a.field}/{a.hands}", "seed": a.seed, "structure": a.structure,
            "field": a.field, "hands": a.hands, "signs": a.signs, "tremor": a.tremor, "echo": a.echo,
            "drip": a.drip, "scale": 1.0, "script": a.script}
    img, rec = _cell(spec)
    p = Path(a.out) if a.out else OUT / "one.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).save(p)
    print(json.dumps(rec, default=str)[:1500])
    print("wrote", p)


# ---------------------------------------------------------------------------
# plot candidates
# ---------------------------------------------------------------------------

CANDIDATES = {
    "regimes-strahler-tree": {"seed": 3, "structure": "tree", "field": "strahler", "hands": "by_regime",
                              "signs": 8, "echo": 2, "drip": 5, "tremor": 0.8, "script": 5},
    "regimes-single-noise": {"seed": 11, "structure": "single", "field": "noise", "hands": "by_regime",
                             "signs": 6, "echo": 2, "drip": 4, "tremor": 0.8},
}


def cmd_plot(a):
    from PIL import Image
    from experiments import composite as cp
    PLOT.mkdir(parents=True, exist_ok=True)
    names = a.names.split(",") if a.names else list(CANDIDATES)
    stats = {}
    for name in names:
        spec = {**CANDIDATES[name], **json.loads(a.override or "{}")}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            c = rf.compose(spec["seed"], SIZE, structure=spec["structure"], field=spec["field"],
                           hands=HANDS.get(spec["hands"], spec["hands"]), signs=spec.get("signs", 6),
                           tremor=spec.get("tremor", 0.0), echo=spec.get("echo", 0), drip=spec.get("drip", 0),
                           script=spec.get("script", 0), label=name)
        paths = c.drawing()
        svg, st = cp.to_svg(paths, PLOT / f"{name}.svg", paper="A4", portrait=True, pen_mm=0.4,
                            title=f"{name} (regime field; nothing plotted)")
        st["hatching"] = rf.hatching_families(c.polylines, max_len=0.06 * SIZE[1], solid_gap=1.25 * c.meta["pen_px"])
        st["regime_share"] = c.meta["regime_share"]
        st["engine"] = [c.meta["engine"], c.meta["signs_engine"]]
        st["spec"] = spec
        stats[name] = st
        Image.fromarray(render(c, 1.0)).save(PLOT / f"{name}.jpg", quality=88)
        print(name, json.dumps({k: st[k] for k in ("paths", "pen_down_mm", "pen_up_mm", "est_min")}), flush=True)
    (PLOT / "stats.json").write_text(json.dumps(stats, indent=1, default=str))
    ims = [np.asarray(Image.open(PLOT / f"{n}.jpg")) for n in names]
    grid([label(im, n) for im, n in zip(ims, names)], len(ims), RESULTS / "regime-field-candidates.jpg", quality=85)


# ---------------------------------------------------------------------------
# path ordering and the polished paper candidate (results/pathorder-2026-10-16.md)
# ---------------------------------------------------------------------------

R7 = ROOT / ".local/gesture/out/plot_candidates_r7"
APP_SITE = ROOT / ".venv/lib/python3.13/site-packages"     # read-only: vpype + pydantic for the app's modules
PAPER_MM = {"A4": (210.0, 297.0), "A3": (297.0, 420.0)}     # portrait
RED400, BASE300 = "#D14D41", "#B7B5AC"                     # flexoki: pen-up moves, faint pen-down


def _app_path():
    """Make the app's own modules importable READ-ONLY: the repo root (for
    axibridge.estimate / model) and the app venv's site-packages APPENDED, so
    this venv's numpy/shapely win and nothing is installed or modified."""
    for p in (str(APP_SITE), str(ROOT)):
        if p not in sys.path:
            sys.path.append(p)


def app_estimate(paths_mm, params=None) -> dict | None:
    """axibridge.estimate.plan_job itself (None if not importable)."""
    try:
        _app_path()
        from axibridge.estimate import MotionParams, plan_job
        from axibridge.model import Layer, Path as APath, PathDocument
    except Exception as e:  # noqa: BLE001
        print("app estimator not importable:", e)
        return None
    from gesture import pathorder as po
    doc = PathDocument(layers=[Layer(id="1", name="1", paths=[APath(points=[tuple(map(float, v)) for v in q])
                                                              for q in paths_mm])])
    job = plan_job(doc, MotionParams(**{**po.NATIVE, **(params or {})}))
    return {"lifts": job.pen_lifts, "pen_down_mm": round(job.pen_down_distance, 1),
            "pen_up_mm": round(job.travel_distance, 1), "total_s": round(job.total_duration, 1),
            "total_min": round(job.total_duration / 60, 1)}


def vpype_order(paths_mm, pipeline="linemerge --tolerance 0.05mm linesort"):
    """The app's plot-pass optimiser (session._optimize: linemerge 0.05 mm +
    linesort, its defaults), run through vpype imported read-only."""
    _app_path()
    import vpype as vp
    import vpype_cli
    doc = vp.Document()
    doc.add(vp.LineCollection([q[:, 0] + 1j * q[:, 1] for q in paths_mm]), 1)
    out = vpype_cli.execute(pipeline, document=doc)
    res = []
    for lc in out.layers.values():
        res += [np.column_stack([ln.real, ln.imag]) for ln in lc]
    return res


def sheet_to_mm(polys, size, paper=(210.0, 297.0), margin_mm: float = 10.0, simplify_mm: float = 0.02,
                fit_ink: bool = False):
    """px → mm with the SHEET (not the drawing's bbox) fitted into the paper
    minus margins and centred: the same k as regime_field.pen_px_for, so a
    fill drawn at pen_px spacing lands at exactly pen_mm on paper.
    fit_ink: fit the union of the sheet and the ink's bbox instead (marks
    composed with clip=False stay whole; fill spacing shrinks a little)."""
    from shapely.geometry import LineString
    W, H = size
    lo, hi = np.zeros(2), np.array([W, H], float)
    if fit_ink and polys:
        P = np.vstack(polys)
        lo, hi = np.minimum(lo, P.min(0)), np.maximum(hi, P.max(0))
    span = hi - lo
    k = min((paper[0] - 2 * margin_mm) / span[0], (paper[1] - 2 * margin_mm) / span[1])
    off = np.array(paper) / 2 - (lo + hi) / 2 * k
    out = []
    for p in polys:
        q = np.asarray(p, float) * k + off
        if simplify_mm > 0 and len(q) > 2:
            closed = np.linalg.norm(q[0] - q[-1]) < 1e-9
            q = np.asarray(LineString(q).simplify(simplify_mm, preserve_topology=False).coords)
            if closed and np.linalg.norm(q[0] - q[-1]) > 1e-9:
                q = np.vstack([q, q[:1]])
        out.append(q)
    return out, k


def write_svg(paths_mm, path: Path, *, paper, pen_mm: float, title: str, layers=None, meta=None) -> None:
    """One top-level <g> per pen layer (the app's and vpype's layer
    convention), one <path> per pen-down path, in plot order."""
    W, H = paper
    lay = layers if layers is not None else [1] * len(paths_mm)
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
         f'width="{W:g}mm" height="{H:g}mm" viewBox="0 0 {W:g} {H:g}">', f"<title>{title}</title>",
         f"<!-- {json.dumps(meta or {}, default=str)} -->"]
    k = 0
    for ly in dict.fromkeys(lay):
        L.append(f'<g id="layer{ly}" inkscape:groupmode="layer" inkscape:label="{ly}" fill="none" stroke="black" '
                 f'stroke-width="{pen_mm:g}" stroke-linecap="round" stroke-linejoin="round">')
        for q, l2 in zip(paths_mm, lay):
            if l2 != ly:
                continue
            L.append(f'<path id="p{k:04d}" d="M' + " L".join(f"{x:.3f},{y:.3f}" for x, y in q) + '"/>')
            k += 1
        L.append("</g>")
    L += ["</svg>", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L))


def physical(paths_mm, paper, pen_mm: float = 0.35, ppm: int = 10, ss: int = 2):
    """Each polyline as a disc-swept stroke of a pen_mm pen: a thick segment
    (width = pen) per edge plus a pen disc at every vertex (= the Minkowski
    sum of the polyline with the pen disc), at ss× supersampling, box-filtered
    down to ppm px/mm. Flexoki ink on flexoki paper. No ink spread."""
    from PIL import Image, ImageDraw
    W, H = paper
    f = ppm * ss
    im = Image.new("L", (int(round(W * f)), int(round(H * f))), 0)
    d = ImageDraw.Draw(im)
    w = pen_mm * f
    r = w / 2
    for q in paths_mm:
        pts = [tuple(v) for v in np.asarray(q) * f]
        if len(pts) > 1:
            d.line(pts, fill=255, width=max(int(round(w)), 1))
        for x, y in pts:
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    a = np.asarray(im.resize((int(round(W * ppm)), int(round(H * ppm))), Image.Resampling.BOX), float)[..., None] / 255
    paper_c = np.array([0xFF, 0xFC, 0xF0], float)
    ink = np.array([0x10, 0x0F, 0x0F], float)
    return (paper_c * (1 - a) + ink * a).astype(np.uint8)


def travel_map(paths_mm, paper, ppm: float = 3.0, home=(0.0, 0.0), text: str = ""):
    """Pen-down paths faint grey, pen-up moves (home → … → home) in red."""
    from PIL import Image, ImageDraw
    W, H = paper
    im = Image.new("RGB", (int(W * ppm), int(H * ppm)), PAPER_HEX)
    d = ImageDraw.Draw(im)
    pos = np.asarray(home, float)
    for q in paths_mm:
        d.line([tuple(v) for v in np.asarray(q) * ppm], fill=BASE300, width=1)
    for q in paths_mm:
        if np.linalg.norm(q[0] - pos) > 1e-6:
            d.line([tuple(pos * ppm), tuple(q[0] * ppm)], fill=RED400, width=1)
        pos = q[-1]
    if len(paths_mm):
        d.line([tuple(pos * ppm), tuple(np.asarray(home) * ppm)], fill=RED400, width=1)
    arr = np.asarray(im)
    return label(arr, text, 12) if text else arr


def svg_constraints(paths_mm, pen_mm: float = 0.4):
    """Marks recovered from geometry for an SVG with no tags: rf.nest_tags
    (a path inside a closed ring = that ring's fill)."""
    tags, _ = rf.nest_tags(paths_mm, 0, pen_mm, "line")
    return [g for g, _ in tags], [k for _, k in tags]


def order_variants(paths, groups, kinds, pen, home=(0.0, 0.0)):
    """The orderings compared in the report, all in the paths' own units."""
    from gesture import pathorder as po
    G = [g if k == "fill" else None for g, k in zip(groups, kinds)]
    ph = [1 if k == "fill" else 0 for k in kinds]
    out = {"input": [np.asarray(p, float) for p in paths]}
    out["free"] = po.order_paths(paths, home=home).paths
    out["marks"] = po.order_paths(paths, G, ph, home=home, nest_tol=2 * pen).paths
    pl = po.order_paths(paths, G, ph, home=home, nest_tol=2 * pen, join_tol=pen, chain_join_tol=2 * pen)
    out["marks+join"] = pl.paths
    return out, pl


def _row(name, variant, paths_mm, est_app=False):
    from gesture import pathorder as po
    e = po.estimate(paths_mm)
    r = {"candidate": name, "variant": variant, **e}
    if est_app:
        ea = app_estimate(paths_mm)
        r["app_total_min"] = ea["total_min"] if ea else None
        r["app_total_s"] = ea["total_s"] if ea else None
    return r


def cmd_order(a):
    """Before/after on the round-6 regime candidates and the v2 single lines."""
    from PIL import Image
    from experiments import composite as cp
    rows, maps = [], []
    srcs = sorted((ROOT / ".local/gesture/out/plot_candidates_regimes").glob("*.svg")) + \
        sorted((ROOT / ".local/gesture/out/plot_candidates_v2").glob("*.svg"))
    for svg in srcs:
        (W, H), paths = cp.read_svg_paths(svg.read_text())
        name = svg.stem
        groups, kinds = svg_constraints(paths, 0.4)
        var, pl = order_variants(paths, groups, kinds, 0.4)
        var["app (vpype merge+linesort)"] = vpype_order(paths)
        for vn, ps in var.items():
            rows.append(_row(name, vn, ps, est_app=vn in ("input", "marks+join")))
            print(json.dumps(rows[-1]), flush=True)
        if len(paths) > 1:
            maps += [travel_map(var["input"], (W, H), text=f"{name}: as exported, pen-up {rows[-5]['pen_up_mm'] / 1000:.1f} m"),
                     travel_map(var["app (vpype merge+linesort)"], (W, H),
                                text=f"app linesort, pen-up {rows[-1]['pen_up_mm'] / 1000:.1f} m"),
                     travel_map(var["marks+join"], (W, H),
                                text=f"pathorder marks+join, pen-up {rows[-2]['pen_up_mm'] / 1000:.1f} m")]
    (R7 / "order_rows.json").parent.mkdir(parents=True, exist_ok=True)
    (R7 / "order_rows.json").write_text(json.dumps(rows, indent=1))
    if maps:
        grid(maps, 3, RESULTS / "pathorder-travel-r6.jpg", quality=85)


POLISH = dict(CANDIDATES["regimes-strahler-tree"])


def polish_one(paper_name: str, pen_mm: float = 0.35):
    """Regenerate the Strahler sheet with fill spacing = pen_mm on this paper,
    order it with the mark constraints and joins, write SVG + stats."""
    from gesture import pathorder as po
    paper = PAPER_MM[paper_name]
    pen_px = rf.pen_px_for(SIZE, paper_mm=paper, pen_mm=pen_mm)
    spec = POLISH
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        c = rf.compose(spec["seed"], SIZE, structure=spec["structure"], field=spec["field"],
                       hands=HANDS[spec["hands"]], signs=spec["signs"], tremor=spec["tremor"], echo=spec["echo"],
                       drip=spec["drip"], script=spec["script"], pen_px=pen_px, label=f"strahler-{paper_name}",
                       clip=False)
    hat = rf.hatching_families(c.polylines, max_len=0.06 * SIZE[1], solid_gap=1.25 * pen_px)
    var, pl = order_variants(c.polylines, c.groups, c.kinds, pen_px)
    mm = {k: sheet_to_mm(v, SIZE, paper, fit_ink=True)[0] for k, v in var.items()}
    k_mm = sheet_to_mm(var["input"], SIZE, paper, fit_ink=True)[1]
    mm["app (vpype merge+linesort)"] = vpype_order(mm["input"])
    fills = [q for q, k in zip(c.polylines, c.kinds) if k == "fill"]
    open_fill = sum(1 for q in fills if not po.is_closed(q))
    kinds_of = [c.kinds[i] for i in range(len(c.kinds))]
    open_after = sum(1 for q, src in zip(pl.paths, pl.source)
                     if all(kinds_of[i] == "fill" for i, _ in src) and not po.is_closed(q) and len(src) == 1)
    hat_after = rf.hatching_families(pl.paths, max_len=0.06 * SIZE[1], solid_gap=1.25 * pen_px)
    name = f"regimes-strahler-tree-{paper_name}"
    rows = [_row(name, vn, ps, est_app=vn in ("input", "marks+join")) for vn, ps in mm.items()]
    P = np.vstack(c.polylines)
    st = {"paper_mm": paper, "pen_mm": pen_mm, "fill_spacing_mm": round(pen_px * k_mm, 4), "pen_px": pen_px,
          "ink_bbox_px": [P.min(0).round(1).tolist(), P.max(0).round(1).tolist()],
          "engine": [c.meta["engine"], c.meta["signs_engine"]], "regime_share": c.meta["regime_share"],
          "kinds": {k: c.kinds.count(k) for k in sorted(set(c.kinds))}, "hatching_before_join": hat,
          "hatching_after_join": hat_after, "open_fill_arcs": open_fill, "open_fill_arcs_unjoined": open_after,
          "spec": spec, "rows": rows, "order_meta": pl.meta}
    final = mm["marks+join"]
    st["svg_rows"] = [r for r in rows if r["variant"] == "marks+join"]
    R7.mkdir(parents=True, exist_ok=True)
    write_svg(final, R7 / f"{name}.svg", paper=paper, pen_mm=pen_mm,
              title=f"{name} (regime field, pathorder; nothing plotted)",
              meta=st["svg_rows"][0])
    (R7 / f"{name}.json").write_text(json.dumps(st, indent=1, default=str))
    return name, paper, final, mm, st


def cmd_polish(a):
    from PIL import Image
    papers = a.papers.split(",")
    with ProcessPoolExecutor(min(JOBS, len(papers))) as ex:
        res = list(ex.map(polish_one, papers))
    maps, prev = [], []
    for name, paper, final, mm, st in res:
        for r in st["rows"]:
            print(json.dumps(r), flush=True)
        print(name, "hatching", st["hatching_before_join"], st["hatching_after_join"], "open arcs",
              st["open_fill_arcs"], "→", st["open_fill_arcs_unjoined"], flush=True)
        img = physical(final, paper, pen_mm=st["pen_mm"], ppm=10)
        Image.fromarray(img).save(R7 / f"{name}-preview-10ppm.jpg", quality=90)
        prev.append((name, img))
        r_in = next(r for r in st["rows"] if r["variant"] == "input")
        r_out = next(r for r in st["rows"] if r["variant"] == "marks+join")
        maps += [travel_map(mm["input"], paper, ppm=3.0 * 210 / paper[0],
                            text=f"{name}: render order, pen-up {r_in['pen_up_mm'] / 1000:.1f} m, {r_in['lifts']} lifts"),
                 travel_map(final, paper, ppm=3.0 * 210 / paper[0],
                            text=f"ordered + joined, pen-up {r_out['pen_up_mm'] / 1000:.1f} m, {r_out['lifts']} lifts")]
    grid(maps, 2, RESULTS / "pathorder-travel-polished.jpg", quality=85)
    # previews: whole sheet (downsized) + two 1:1 crops at 10 px/mm
    cells = []
    for name, img in prev:
        from PIL import Image as I
        h = 1000
        w = int(img.shape[1] * h / img.shape[0])
        cells.append(label(np.asarray(I.fromarray(img).resize((w, h), I.Resampling.LANCZOS)), name + " (whole sheet)"))
    grid(cells, len(cells), RESULTS / "pathorder-preview-sheets.jpg", quality=88)
    crops = []
    for name, img in prev:
        crops += _crops(img, name)
    grid(crops, 3, RESULTS / "pathorder-preview-detail.jpg", quality=88)


def _crops(img, name, side=500):
    """Three 50 mm × 50 mm windows at 10 px/mm: densest ink, a mid-density
    one and the sparsest inked one (wire)."""
    g = 255 - img[..., 0].astype(float)
    H, W = g.shape
    cands = []
    for y in range(0, H - side, side // 2):
        for x in range(0, W - side, side // 2):
            cands.append((float(g[y:y + side, x:x + side].mean()), y, x))
    cands = [c for c in cands if c[0] > 2.0]
    cands.sort()
    pick = [cands[-1], cands[len(cands) // 2], cands[len(cands) // 8]]
    out = []
    for (m, y, x), tag in zip(pick, ("densest", "middle", "sparse")):
        out.append(label(img[y:y + side, x:x + side].copy(), f"{name.split('-')[-1]} {tag} 50 mm @10 px/mm"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hand").set_defaults(fn=cmd_hand)
    s = sub.add_parser("sheets")
    s.add_argument("--only", default="")
    s.set_defaults(fn=cmd_sheets)
    o = sub.add_parser("one")
    o.add_argument("--seed", type=int, default=1)
    o.add_argument("--structure", default="tree")
    o.add_argument("--field", default="sense")
    o.add_argument("--hands", default="by_regime")
    o.add_argument("--signs", type=int, default=6)
    o.add_argument("--tremor", type=float, default=0.0)
    o.add_argument("--echo", type=int, default=0)
    o.add_argument("--drip", type=int, default=0)
    o.add_argument("--script", type=int, default=0)
    o.add_argument("--label", default="")
    o.add_argument("--out", default="")
    o.set_defaults(fn=cmd_one)
    p = sub.add_parser("plot")
    p.add_argument("--names", default="")
    p.add_argument("--override", default="")
    p.set_defaults(fn=cmd_plot)
    sub.add_parser("order").set_defaults(fn=cmd_order)
    q = sub.add_parser("polish")
    q.add_argument("--papers", default="A4,A3")
    q.set_defaults(fn=cmd_polish)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()

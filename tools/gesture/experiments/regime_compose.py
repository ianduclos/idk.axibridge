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
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()

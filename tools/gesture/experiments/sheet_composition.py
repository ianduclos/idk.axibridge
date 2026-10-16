"""Composition learned from whole sheets (round 8).

results/sheet_composition-2026-10-16.md. Library: gesture/sheetcomp.py.

    ../../.local/gesture/.venv/bin/python -m experiments.sheet_composition measure
    ../../.local/gesture/.venv/bin/python -m experiments.sheet_composition space
    ../../.local/gesture/.venv/bin/python -m experiments.sheet_composition match
    ../../.local/gesture/.venv/bin/python -m experiments.sheet_composition limb

  measure  ink masks + profiles for every corpus sheet and our regime sheets
           → out/sheet_composition/profiles.json, masks/*.npy (cached)
  space    the composition space: PCA scatter, per-stat strip plot, mask
           contact sheet, "what is off about our sheets" table
  match    density/emptiness controller: candidates per target, post-select
  limb     emptiness as an active regime (negative layouts)
Run from tools/gesture. ≤ 2 worker processes.
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

from gesture import sheetcomp as sc  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / ".local/gesture/corpus"
OUT = ROOT / ".local/gesture/out/sheet_composition"
RESULTS = Path(__file__).resolve().parents[1] / "results"
JOBS = 2
SIZE = (840, 1200)
PAPER = (0xFF, 0xFC, 0xF0)
INK = (0x10, 0x0F, 0x0F)
FLEX = {"blue": "#4385BE", "red": "#D14D41", "green": "#879A39", "orange": "#DA702C", "purple": "#8B7EC8",
        "cyan": "#3AA99F", "yellow": "#D0A215", "magenta": "#CE5D97", "base": "#878580", "black": "#100F0F"}

ARTIST_GROUP = {"brice_marden": "marden", "harold_cohen": "cohen", "desmond_paul_henry": "henry",
                "molnar_vera": "molnar", "vera_molnar": "molnar", "frieder_nake": "nake", "nake_frieder": "nake",
                "a_michael_noll": "noll", "ellsworth_kelly": "kelly"}
MASHQ = {"met-716305", "met-716307", "wc-12", "wc-13"}
SHIKASTA_DOC = {"wc-15", "wc-10", "wc-17", "met-450714", "met-716315"}


# ---------------------------------------------------------------------------
# inventory
# ---------------------------------------------------------------------------

def inventory() -> list[dict]:
    items = []
    for grp in ("matisse", "hokusai", "ingres"):
        for p in sorted((CORPUS / grp).glob("*.jpg")):
            items.append({"id": f"{grp}/{p.stem}", "group": grp, "path": str(p), "inset": 0.04})
    for d in sorted((CORPUS / "artists").iterdir()):
        if d.is_dir() and d.name != "ellsworth_kelly":     # one faint pencil sheet: binarises empty
            for p in sorted(d.glob("*.jpg")):
                items.append({"id": f"{ARTIST_GROUP[d.name]}/{p.stem}", "group": ARTIST_GROUP[d.name],
                              "path": str(p), "inset": 0.04})
    from gesture import calligraphy as C
    for sid, cfg in C.SHEETS.items():
        if "#" in sid or sid in ("wc-37",):        # model-book pdf pages; devotional kufic skipped
            continue
        grp = "mashq" if sid in MASHQ else "shikasta" if sid in SHIKASTA_DOC else "calligraphy"
        items.append({"id": f"{grp}/{sid}", "group": grp, "sheet": sid, "genre": cfg.get("genre", ""),
                      "inset": 0.0})
    for book in ("AL01", "AL04", "AL08", "AL09"):
        pages = sorted((CORPUS / "print/scans" / book).glob("*.jp2"))
        for p in pages[2::4][:5]:
            items.append({"id": f"print/{p.stem}", "group": "print", "path": str(p), "inset": 0.06})
    ours = [*sorted((ROOT / ".local/gesture/out/plot_candidates_r7").glob("*A4*preview*.jpg")),
            *sorted((ROOT / ".local/gesture/out/plot_candidates_v2").glob("*.jpg"))]
    for p in ours:
        grp = "ours_r7" if "r7" in str(p.parent) else "ours_r6" if "regimes" in str(p.parent) else "ours_v2"
        items.append({"id": f"{grp}/{p.stem}", "group": grp, "path": str(p), "inset": 0.0})
    items.append({"id": "ref/ian-regimes-sd-2024", "group": "ref", "path": str(ROOT / ".local/gesture/ref/ian-regimes-sd-2024.png"),
                  "inset": 0.03})
    return items


def _measure(it: dict) -> dict:
    t = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if "sheet" in it:
            from gesture import calligraphy as C
            g, _, _ = C.load_sheet(it["sheet"], max_side=2000)
            g, _ = C.remove_rules(g)
        else:
            g = sc.load_gray(it["path"], max_side=2000)
        m = sc.mask_from_gray(g, inset=it.get("inset", 0.0))
    p = sc.profile(m)
    mp = OUT / "masks" / (it["id"].replace("/", "__") + ".npy")
    mp.parent.mkdir(parents=True, exist_ok=True)
    np.save(mp, np.packbits(m, axis=None))
    return {**it, "profile": p, "shape": list(m.shape), "mask": str(mp), "secs": round(time.perf_counter() - t, 1)}


def load_mask(rec: dict) -> np.ndarray:
    b = np.load(rec["mask"])
    n = rec["shape"][0] * rec["shape"][1]
    return np.unpackbits(b)[:n].reshape(rec["shape"]).astype(bool)


def cmd_measure(a):
    OUT.mkdir(parents=True, exist_ok=True)
    pj = OUT / "profiles.json"
    done = {r["id"]: r for r in json.loads(pj.read_text())} if pj.exists() and not a.force else {}
    todo = [it for it in inventory() if it["id"] not in done]
    print(len(done), "cached,", len(todo), "to measure")
    with ProcessPoolExecutor(JOBS) as ex:
        for r in ex.map(_measure, todo):
            done[r["id"]] = r
            print(f"{r['id']:<50} {r['secs']:5.1f}s cover={r['profile']['cover']:.3f} empty16={r['profile']['empty16']:.2f}",
                  flush=True)
            pj.write_text(json.dumps(list(done.values()), indent=0))


def records() -> list[dict]:
    return json.loads((OUT / "profiles.json").read_text())


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------

GROUP_COLOUR = {"matisse": FLEX["blue"], "hokusai": FLEX["red"], "ingres": FLEX["cyan"], "marden": FLEX["orange"],
                "cohen": FLEX["purple"], "henry": FLEX["purple"], "molnar": FLEX["magenta"], "nake": FLEX["magenta"],
                "noll": FLEX["magenta"], "kelly": FLEX["purple"], "mashq": FLEX["green"], "shikasta": FLEX["green"],
                "calligraphy": FLEX["yellow"], "print": FLEX["base"], "ours_r7": FLEX["black"],
                "ours_r6": FLEX["black"], "ours_v2": FLEX["black"], "ref": FLEX["black"]}
CORPUS_GROUPS = ("matisse", "hokusai", "ingres", "marden", "cohen", "henry", "molnar", "nake", "noll", "kelly",
                 "mashq", "shikasta", "calligraphy", "print")


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor": "#FFFCF0", "axes.facecolor": "#FFFCF0", "savefig.facecolor": "#FFFCF0",
                         "font.size": 8, "axes.edgecolor": "#878580"})
    return plt


def cmd_space(a):
    plt = _mpl()
    recs = records()
    corp = [r for r in recs if r["group"] in CORPUS_GROUPS]
    scale = sc.Scale.fit([r["profile"] for r in corp], sc.COMPOSITION_KEYS)
    X = np.array([scale.z(r["profile"]) for r in corp])
    X = np.nan_to_num(X)
    mu = X.mean(0)
    U, S, Vt = np.linalg.svd(X - mu, full_matrices=False)
    ev = S ** 2 / np.sum(S ** 2)
    proj = lambda r: (np.nan_to_num(scale.z(r["profile"])) - mu) @ Vt[:2].T  # noqa: E731
    fig, ax = plt.subplots(1, 2, figsize=(13, 6.2), gridspec_kw={"width_ratios": [1.25, 1]})
    for r in recs:
        x, y = proj(r)
        g = r["group"]
        ours = g.startswith("ours") or g == "ref"
        ax[0].scatter(x, y, s=60 if ours else 22, c=GROUP_COLOUR[g], marker="*" if ours else "o",
                      edgecolors="none", alpha=1.0 if ours else 0.75, zorder=3 if ours else 2)
        if ours:
            lab = r["id"].split("/")[1].replace("regimes-strahler-tree-", "r7 ").replace("-preview-10ppm", "")
            ax[0].annotate(lab if g != "ref" else "Ian ref 2024", (x, y), fontsize=6.5, xytext=(3, 2),
                           textcoords="offset points")
    for g in CORPUS_GROUPS:
        pts = np.array([proj(r) for r in corp if r["group"] == g])
        if len(pts):
            c = pts.mean(0)
            ax[0].annotate(f"{g} ({len(pts)})", c, fontsize=8, color=GROUP_COLOUR[g], weight="bold", ha="center")
    loads = Vt[:2]
    top = lambda v: ", ".join(f"{'+' if v[i] > 0 else '−'}{scale.keys[i]}" for i in np.argsort(-np.abs(v))[:4])  # noqa: E731
    ax[0].set_xlabel(f"PC1 ({ev[0]:.0%}): {top(loads[0])}")
    ax[0].set_ylabel(f"PC2 ({ev[1]:.0%}): {top(loads[1])}")
    ax[0].set_title("Composition space (15 layout stats, robust z over the corpora). ★ = ours / Ian's reference")
    # strip plot: our r7 sheet vs corpora per key
    keys = sc.COMPOSITION_KEYS
    r7 = [r for r in recs if r["group"] == "ours_r7"]
    ref = [r for r in recs if r["group"] == "ref"]
    for j, k in enumerate(keys):
        for g in CORPUS_GROUPS:
            v = [r["profile"][k] for r in corp if r["group"] == g]
            z = (np.array(v) - scale.centre[j]) / scale.spread[j]
            ax[1].scatter(np.clip(z, -6, 6), np.full(len(z), j) + np.random.default_rng(j).uniform(-.25, .25, len(z)),
                          s=6, c=GROUP_COLOUR[g], alpha=0.5, edgecolors="none")
        for rr, mk, col in ((r7, "*", FLEX["black"]), (ref, "D", FLEX["red"])):
            for r in rr:
                z = (r["profile"][k] - scale.centre[j]) / scale.spread[j]
                ax[1].scatter(np.clip(z, -6, 6), j, s=70 if mk == "*" else 30, c=col, marker=mk, zorder=4)
    ax[1].set_yticks(range(len(keys)))
    ax[1].set_yticklabels(keys)
    ax[1].axvline(0, color="#CECDC3", lw=0.8)
    ax[1].set_xlabel("robust z vs all corpora (clipped ±6)")
    ax[1].set_title("Each stat: corpora (dots, group colours), r7 sheets ★, Ian ref ◆")
    ax[1].invert_yaxis()
    fig.tight_layout()
    fig.savefig(OUT / "space.png", dpi=110)
    _jpg(OUT / "space.png", RESULTS / "sheet_composition-space.jpg")
    # tables
    groups = {g: [r for r in recs if r["group"] == g] for g in list(CORPUS_GROUPS) + ["ours_r7", "ours_r6", "ours_v2", "ref"]}
    med = {g: sc.target_of([r["profile"] for r in v]) for g, v in groups.items() if v}
    (OUT / "group_medians.json").write_text(json.dumps(med, indent=1))
    lines = ["| stat | " + " | ".join(g for g in med) + " |", "|---|" + "---|" * len(med)]
    for k in sc.PROFILE_KEYS:
        lines.append(f"| {k} | " + " | ".join(f"{med[g][k]:.3g}" for g in med) + " |")
    lines.append("| n | " + " | ".join(str(len(groups[g])) for g in med) + " |")
    (OUT / "group_medians.md").write_text("\n".join(lines))
    print("\n".join(lines))
    # nearest corpus group for each of ours (composition keys)
    for r in [r for r in recs if r["group"].startswith("ours") or r["group"] == "ref"]:
        ds = sorted((sc.distance(r["profile"], med[g], scale), g) for g in CORPUS_GROUPS if g in med)
        print(f"{r['id']:<60} nearest: " + ", ".join(f"{g} {d:.2f}" for d, g in ds[:3]))
    contact(recs)


def _jpg(src: Path, dst: Path, max_kb: int = 900, width: int | None = None):
    from PIL import Image
    im = Image.open(src).convert("RGB")
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS)
    for q in (88, 80, 70, 60, 50):
        im.save(dst, quality=q)
        if dst.stat().st_size < max_kb * 1024:
            break


def mask_image(m: np.ndarray, side: int) -> "Image.Image":
    from PIL import Image
    a = np.where(m[..., None], np.array(INK, np.uint8), np.array(PAPER, np.uint8)).astype(np.uint8)
    im = Image.fromarray(a)
    s = side / max(im.size)
    return im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.Resampling.BOX)


SCRIPT_GROUPS = ("mashq", "shikasta", "calligraphy", "print")


def source_image(rec: dict, side: int):
    """What a figure shows of a corpus sheet: its ink mask, except for
    script sheets (calligraphy, print), which are shown only as their
    coarse layout map (16 cells on the long side) so no legible Arabic is
    reproduced in results."""
    from PIL import Image
    m = load_mask(rec)
    if rec["group"] not in SCRIPT_GROUPS:
        return mask_image(m, side)
    d = sc.density_map(m, 16)
    d = d / max(d.max(), 1e-9)
    a = (np.array(PAPER, float)[None, None] * (1 - d[..., None]) + np.array(INK, float)[None, None] * d[..., None])
    im = Image.fromarray(a.astype(np.uint8))
    s = side / max(im.size)
    return im.resize((round(im.width * s), round(im.height * s)), Image.Resampling.NEAREST)


def contact(recs, per_row: int = 12, side: int = 150):
    from PIL import Image, ImageDraw
    rows = []
    for g in list(CORPUS_GROUPS) + ["ours_r7", "ours_r6", "ours_v2", "ref"]:
        rows.append([r for r in recs if r["group"] == g])
    cells = [r for row in rows for r in row]
    n = len(cells)
    nr = (n + per_row - 1) // per_row
    sheet = Image.new("RGB", (per_row * (side + 6), nr * (side + 18)), PAPER)
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(cells):
        im = mask_image(load_mask(r), side)
        x, y = (i % per_row) * (side + 6), (i // per_row) * (side + 18)
        sheet.paste(im, (x + (side - im.width) // 2, y + 14))
        d.text((x + 2, y + 1), r["id"].split("/")[0] + " " + r["id"].split("/")[1][:14], fill=INK)
    sheet.save(OUT / "masks_contact.jpg", quality=80)


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------

TARGETS = {
    # name: (group the target profile comes from, sheet whose layout is transplanted)
    "Marden": ("marden", "marden/moma-69038"),
    "a mashq page": ("mashq", "mashq/wc-12"),
    "a Hokusai manga page": ("hokusai", None),
    "Matisse": ("matisse", None),
}


def _cand(args):
    spec, = args
    t = time.perf_counter()
    c, p, void, m = sc.make_candidate(spec, SIZE)
    return spec, p, c.polylines, c.meta["pen_px"], round(time.perf_counter() - t, 1)


def _best_layout_sheet(recs, group, target):
    """The group's sheet closest to the group median (its layout is used)."""
    corp = [r for r in recs if r["group"] in CORPUS_GROUPS]
    scale = sc.Scale.fit([r["profile"] for r in corp], sc.COMPOSITION_KEYS)
    rr = [r for r in recs if r["group"] == group]
    return min(rr, key=lambda r: sc.distance(r["profile"], target, scale))


def _portrait_map(m: np.ndarray, n_long: int = 16) -> np.ndarray:
    """Layout map of a sheet mask, rotated to portrait when it is landscape
    (our sheets are A4 portrait)."""
    d = sc.density_map(m, n_long)
    if d.shape[1] > d.shape[0]:
        d = np.rot90(d)
    return d


def specs_for(target_name: str, layout: np.ndarray, target: dict, seeds=(1, 2, 3, 4)) -> list[dict]:
    """The candidate grid for one target: structure × emptiness strength ×
    signs, all with the target's own layout; plus the uncontrolled r7 recipe
    as the baseline."""
    from gesture import calligraphy as C
    if "mashq" in target_name:
        C.require_generative(["wc-12"])          # the layout of a policy-gated exercise sheet only
    D = layout / max(layout.max(), 1e-9)
    out = []
    eq = target["empty16"]
    for seed in seeds:
        out.append({"label": f"{target_name}: r7 recipe (uncontrolled)", "seed": seed, "structure": "tree",
                    "field": "strahler", "hands": "by_regime", "signs": 8, "echo": 2, "drip": 5, "tremor": 0.8,
                    "E": None, "target": target_name, "kind": "baseline"})
        for st, sp in (("guided", {"fill": 0.9}), ("guided", {"fill": 0.6, "trunks": 2}), ("grammar", None)):
            for q in (eq, min(eq + 0.15, 0.9)):
                E = sc.layout_field(layout, empty_q=q)
                out.append({"label": f"{target_name}: {st} {sp or ''} empty={q:.2f}", "seed": seed, "structure": st,
                            "structure_params": sp, "field": "strahler", "hands": "by_regime",
                            "signs": 8 if target["cover"] > 0.05 else 4, "echo": 2, "drip": 3, "tremor": 0.8,
                            "E": E.tolist(), "D": D.tolist(), "tau": 0.5, "halo": 1.0, "mass_boost": 0.6,
                            "target": target_name, "kind": "controlled"})
    return out


def cmd_match(a):
    recs = records()
    corp = [r for r in recs if r["group"] in CORPUS_GROUPS]
    scale = sc.Scale.fit([r["profile"] for r in corp], sc.COMPOSITION_KEYS)
    med = {g: sc.target_of([r["profile"] for r in recs if r["group"] == g]) for g in CORPUS_GROUPS
           if any(r["group"] == g for r in recs)}
    (OUT / "cands").mkdir(parents=True, exist_ok=True)
    names = a.only.split(",") if a.only else list(TARGETS)
    allres = {}
    for name in names:
        grp, sheet = TARGETS[name]
        target = med[grp]
        lay_rec = next(r for r in recs if r["id"] == sheet) if sheet else _best_layout_sheet(recs, grp, target)
        layout = _portrait_map(load_mask(lay_rec))
        specs = specs_for(name, layout, target, seeds=tuple(range(1, 1 + a.seeds)))
        print(name, "layout from", lay_rec["id"], len(specs), "candidates")
        res = []
        with ProcessPoolExecutor(JOBS) as ex:
            for spec, p, polys, pen, secs in ex.map(_cand, [(s,) for s in specs]):
                d = sc.distance(p, target, scale)
                res.append({"spec": {k: v for k, v in spec.items() if k not in ("E", "D")}, "profile": p, "dist": d,
                            "secs": secs})
                _save_polys(OUT / "cands" / _cname(spec), polys)
                print(f"  {spec['label']:<60} seed {spec['seed']} d={d:.2f} {secs}s")
        allres[name] = {"layout_sheet": lay_rec["id"], "target_group": grp, "target": target, "cands": res,
                        "layout": layout.tolist()}
        (OUT / f"match_{_slug(name)}.json").write_text(json.dumps(allres[name], indent=0))
    match_figure(names)


def _save_polys(path, polys):
    arr = np.empty(len(polys), dtype=object)
    for i, q in enumerate(polys):
        arr[i] = np.asarray(q, float)
    np.save(path, arr, allow_pickle=True)


def _slug(s):
    return "".join(ch if ch.isalnum() else "_" for ch in s).strip("_").lower()


def _cname(spec):
    return f"{_slug(spec['label'])}_s{spec['seed']}.npy"


def _render_polys(polys, pen, side=520):
    m = sc.render_mask(polys, SIZE, pen, long_side=1200)
    return mask_image(m, side)


def match_figure(names):
    """Per target: the layout source sheet's mask, best uncontrolled, best
    controlled; stats table vs target."""
    from PIL import Image, ImageDraw
    recs = records()
    corp = [r for r in recs if r["group"] in CORPUS_GROUPS]
    scale = sc.Scale.fit([r["profile"] for r in corp], sc.COMPOSITION_KEYS)
    side = 430
    rows = []
    summary = []
    for name in names:
        js = json.loads((OUT / f"match_{_slug(name)}.json").read_text())
        target = js["target"]
        base = min((c for c in js["cands"] if c["spec"]["kind"] == "baseline"), key=lambda c: c["dist"])
        ctl = min((c for c in js["cands"] if c["spec"]["kind"] == "controlled"), key=lambda c: c["dist"])
        ctl_d = sorted(c["dist"] for c in js["cands"] if c["spec"]["kind"] == "controlled")
        base_d = sorted(c["dist"] for c in js["cands"] if c["spec"]["kind"] == "baseline")
        lay = next(r for r in recs if r["id"] == js["layout_sheet"])
        ims = [source_image(lay, side)]
        for c in (base, ctl):
            polys = list(np.load(OUT / "cands" / _cname(c["spec"]), allow_pickle=True))
            from gesture import regime_field as rf
            ims.append(_render_polys(polys, rf.pen_px_for(SIZE), side))
        W = 3 * (side + 10) + 330
        H = side + 40
        row = Image.new("RGB", (W, H), PAPER)
        d = ImageDraw.Draw(row)
        x = 0
        caps = [f"layout source: {js['layout_sheet']}" + (" (layout map)" if lay["group"] in SCRIPT_GROUPS else ""), f"uncontrolled r7 recipe  d={base['dist']:.2f}",
                f"composed like {name}  d={ctl['dist']:.2f}"]
        for im, cap in zip(ims, caps):
            row.paste(im, (x + (side - im.width) // 2, 30))
            d.text((x + 4, 12), cap, fill=INK)
            x += side + 10
        d.text((x, 12), f"target = median of {js['target_group']} (n={sum(r['group'] == js['target_group'] for r in recs)})", fill=INK)
        yy = 32
        d.text((x, yy), f"{'stat':<12}{'target':>8}{'r7':>8}{'ctl':>8}", fill=INK)
        for k in ("cover", "lac_06", "lac_25", "empty16", "void_max", "void_share", "spread", "margin_ratio",
                  "islands_3", "big_island", "com_dy"):
            yy += 14
            j = scale.keys.index(k)
            zb = abs(base["profile"][k] - target[k]) / scale.spread[j]
            zc = abs(ctl["profile"][k] - target[k]) / scale.spread[j]
            d.text((x, yy), f"{k:<12}{target[k]:>8.3f}{base['profile'][k]:>8.3f}{ctl['profile'][k]:>8.3f}", fill=INK)
            d.text((x + 270, yy), "better" if zc < zb - 0.25 else "worse" if zc > zb + 0.25 else "~",
                   fill=FLEX["green"] if zc < zb - 0.25 else FLEX["red"] if zc > zb + 0.25 else FLEX["base"])
        yy += 20
        d.text((x, yy), f"distance (RMS robust z, 15 stats):", fill=INK)
        d.text((x, yy + 14), f"  uncontrolled: best {base_d[0]:.2f}, median {np.median(base_d):.2f}", fill=INK)
        d.text((x, yy + 28), f"  controlled:   best {ctl_d[0]:.2f}, median {np.median(ctl_d):.2f}", fill=INK)
        d.text((x, yy + 42), f"  chosen: {ctl['spec']['label'].split(': ')[1]} s{ctl['spec']['seed']}"[:52], fill=INK)
        rows.append(row)
        summary.append({"target": name, "base_best": base_d[0], "base_median": float(np.median(base_d)),
                        "ctl_best": ctl_d[0], "ctl_median": float(np.median(ctl_d)), "chosen": ctl["spec"]["label"],
                        "seed": ctl["spec"]["seed"]})
    sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)), PAPER)
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    sheet.save(OUT / "match.png")
    _jpg(OUT / "match.png", RESULTS / "sheet_composition-match.jpg")
    (OUT / "match_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


# ---------------------------------------------------------------------------
# feedback tuning (cheap post-knobs on a few base compositions)
# ---------------------------------------------------------------------------

def _tune_job(args):
    spec, target, scale_d, layout, seed = args
    import warnings as _w
    _w.simplefilter("ignore")
    scale = sc.Scale(tuple(scale_d["keys"]), np.array(scale_d["centre"]), np.array(scale_d["spread"]))
    t = time.perf_counter()
    c, p0, _, _ = sc.make_candidate(spec, SIZE)
    lay = np.asarray(layout) if layout is not None else None
    cb, pb, kb, hist = sc.tune(c, target, scale, layout=lay, iters=30, seed=seed)
    return spec, p0, pb, kb, [h[0] for h in hist], cb.polylines, round(time.perf_counter() - t, 1)


def cmd_tune(a):
    recs = records()
    corp = [r for r in recs if r["group"] in CORPUS_GROUPS]
    scale = sc.Scale.fit([r["profile"] for r in corp], sc.COMPOSITION_KEYS)
    sd = {"keys": list(scale.keys), "centre": scale.centre.tolist(), "spread": scale.spread.tolist()}
    names = a.only.split(",") if a.only else list(TARGETS)
    jobs = []
    for name in names:
        js = json.loads((OUT / f"match_{_slug(name)}.json").read_text())
        layout = js["layout"]
        bases = [c["spec"] for c in sorted(js["cands"], key=lambda c: c["dist"]) if c["spec"]["kind"] == "baseline"][:1]
        bases += [c["spec"] for c in sorted(js["cands"], key=lambda c: c["dist"]) if c["spec"]["kind"] == "controlled"][:1]
        for b in bases:
            spec = dict(b)
            if spec.get("kind") == "controlled":     # rebuild its E/D from the layout (not stored in json)
                q = float(spec["label"].split("empty=")[1])
                spec["E"] = sc.layout_field(np.asarray(layout), empty_q=q).tolist()
                spec["D"] = (np.asarray(layout) / max(np.max(layout), 1e-9)).tolist()
            jobs.append((spec, js["target"], sd, layout, 11))
    res = {}
    with ProcessPoolExecutor(JOBS) as ex:
        for spec, p0, pb, kb, hist, polys, secs in ex.map(_tune_job, jobs):
            name = spec["target"]
            tgt = json.loads((OUT / f"match_{_slug(name)}.json").read_text())["target"]
            res.setdefault(name, {"target": tgt})
            d0 = sc.distance(p0, tgt, scale)
            res[name].setdefault("runs", []).append({"spec": {k: v for k, v in spec.items() if k not in ("E", "D")},
                                                      "d_before": d0, "d_after": hist and min(hist), "knobs": kb,
                                                      "profile_before": p0, "profile_after": pb, "hist": hist})
            _save_polys(OUT / "cands" / ("tuned_" + _cname(spec)), polys)
            print(f"{spec['label']:<60} s{spec['seed']} d {d0:.2f} → {min(hist):.2f} knobs {kb} {secs}s", flush=True)
    for name, v in res.items():
        (OUT / f"tune_{_slug(name)}.json").write_text(json.dumps(v, indent=0))
    tune_figure(names)


def tune_figure(names):
    from PIL import Image, ImageDraw
    from gesture import regime_field as rf
    recs = records()
    corp = [r for r in recs if r["group"] in CORPUS_GROUPS]
    scale = sc.Scale.fit([r["profile"] for r in corp], sc.COMPOSITION_KEYS)
    side = 430
    rows, summary = [], []
    for name in names:
        js = json.loads((OUT / f"match_{_slug(name)}.json").read_text())
        tj = json.loads((OUT / f"tune_{_slug(name)}.json").read_text())
        target = js["target"]
        runs = sorted(tj["runs"], key=lambda r: r["d_after"])
        base = next(r for r in tj["runs"] if r["spec"]["kind"] == "baseline")
        best = runs[0]
        lay = next(r for r in recs if r["id"] == js["layout_sheet"])
        ims = [source_image(lay, side)]
        polys0 = list(np.load(OUT / "cands" / _cname(base["spec"]), allow_pickle=True))
        ims.append(_render_polys(polys0, rf.pen_px_for(SIZE), side))
        polys1 = list(np.load(OUT / "cands" / ("tuned_" + _cname(best["spec"])), allow_pickle=True))
        ims.append(_render_polys(polys1, rf.pen_px_for(SIZE), side))
        W = 3 * (side + 10) + 340
        row = Image.new("RGB", (W, side + 40), PAPER)
        d = ImageDraw.Draw(row)
        kb = best["knobs"]
        caps = [f"layout source: {js['layout_sheet']}" + (" (layout map)" if lay["group"] in SCRIPT_GROUPS else ""), f"r7 recipe, uncontrolled  d={base['d_before']:.2f}",
                f"composed like {name}  d={best['d_after']:.2f}"]
        x = 0
        for im, cap in zip(ims, caps):
            row.paste(im, (x + (side - im.width) // 2, 30))
            d.text((x + 4, 12), cap, fill=INK)
            x += side + 10
        d.text((x, 4), f"target = median of {js['target_group']} (n={sum(r['group'] == js['target_group'] for r in recs)})", fill=INK)
        d.text((x, 18), f"base: {best['spec']['label'].split(': ')[1]} s{best['spec']['seed']}"[:56], fill=INK)
        d.text((x, 32), f"knobs: clear {kb['empty_q']:.2f}  gaps {kb['gaps']}  zoom {kb['zoom']:.2f}", fill=INK)
        yy = 52
        d.text((x, yy), f"{'stat':<13}{'target':>8}{'r7':>8}{'tuned':>8}", fill=INK)
        for k in sc.COMPOSITION_KEYS:
            yy += 13
            j = scale.keys.index(k)
            pb, pa = base["profile_before"][k], best["profile_after"][k]
            zb, za = abs(pb - target[k]) / scale.spread[j], abs(pa - target[k]) / scale.spread[j]
            col = FLEX["green"] if za < zb - 0.25 else FLEX["red"] if za > zb + 0.25 else FLEX["base"]
            d.text((x, yy), f"{k:<13}{target[k]:>8.3f}{pb:>8.3f}{pa:>8.3f}", fill=INK)
            d.text((x + 285, yy), "closer" if col == FLEX["green"] else "farther" if col == FLEX["red"] else "~", fill=col)
        d.text((x, yy + 18), "d = RMS robust z over these 15 stats", fill=FLEX["base"])
        rows.append(row)
        summary.append({"target": name, "r7_d": base["d_before"], "tuned_d": best["d_after"], "base": best["spec"]["label"],
                        "knobs": kb, "runs": [(r["spec"]["label"], r["d_before"], r["d_after"]) for r in tj["runs"]]})
    sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)), PAPER)
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    sheet.save(OUT / "tuned.png")
    _jpg(OUT / "tuned.png", RESULTS / "sheet_composition-matched.jpg")
    (OUT / "tune_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("measure")
    m.add_argument("--force", action="store_true")
    sp.add_parser("space")
    mt = sp.add_parser("match")
    mt.add_argument("--only", default="")
    mt.add_argument("--seeds", type=int, default=3)
    sp.add_parser("matchfig")
    sp.add_parser("tunefig")
    sp.add_parser("limb")
    tu = sp.add_parser("tune")
    tu.add_argument("--only", default="")
    a = ap.parse_args(argv)
    if a.cmd == "tunefig":
        tune_figure(list(TARGETS))
        return
    if a.cmd == "matchfig":
        match_figure(list(TARGETS))
        return
    {"measure": cmd_measure, "space": cmd_space, "match": cmd_match, "limb": cmd_limb, "tune": cmd_tune}[a.cmd](a)


LIMB_VOIDS = {
    # name: (sheet whose ink becomes the VOID, grid cells on the long side, share of the sheet cleared)
    "Hokusai figures as holes": ("hokusai/57253", 24, 0.30),
    "mashq rows as holes": ("mashq/wc-12", 24, 0.35),
    "Marden net as holes": ("marden/moma-69038", 20, 0.35),
}


def negative_E(m: np.ndarray, n_long: int, share: float) -> np.ndarray:
    """A sheet's DENSE regions as the void: E = 1 where the source sheet is
    inked most (top `share` of its layout map)."""
    d = _portrait_map(m, n_long)
    return sc.layout_field(d.max() - d, empty_q=share, smooth=0.8)


def cmd_limb(a):
    """Emptiness as an active regime: voids cut from other sheets' ink, in a
    dense structure, with two edge behaviours (halo: lines thin to wire and
    stop; pool: lines swell into masses at the rim and stop)."""
    from PIL import Image, ImageDraw
    from gesture import calligraphy as C
    from gesture import regime_field as rf
    C.require_generative(["wc-12"])
    recs = {r["id"]: r for r in records()}
    specs = []
    for name, (sid, n, share) in LIMB_VOIDS.items():
        E = negative_E(load_mask(recs[sid]), n, share)
        for edge in ("halo", "pool"):
            for seed in (5, 6):
                specs.append({"label": f"limb {name} {edge}", "seed": seed, "structure": "guided",
                              "structure_params": {"fill": 0.97, "trunks": 3, "clearance_r": 0.006},
                              "field": "strahler", "hands": "by_regime", "signs": 6, "echo": 0, "drip": 0,
                              "tremor": 0.8, "E": E.tolist(), "tau": 0.5, "halo": 1.0, "edge": edge,
                              "kind": "limb", "void": name})
    res = []
    with ProcessPoolExecutor(JOBS) as ex:
        for spec, p, polys, pen, secs in ex.map(_cand, [(s,) for s in specs]):
            (OUT / "cands").mkdir(parents=True, exist_ok=True)
            _save_polys(OUT / "cands" / _cname(spec), polys)
            res.append({"spec": {k: v for k, v in spec.items() if k not in ("E", "D")}, "profile": p, "secs": secs})
            print(f"  {spec['label']:<50} s{spec['seed']} void={p['void_share']:.2f} isl3={p['islands_3']:.2f} {secs}s")
    (OUT / "limb.json").write_text(json.dumps(res, indent=0))
    # figure: per void (rows): source ink | E | halo | pool  (seed 5; seed 6 in the population file)
    side = 400
    rows = []
    for name, (sid, n, share) in LIMB_VOIDS.items():
        src = source_image(recs[sid], side)
        E = negative_E(load_mask(recs[sid]), n, share)
        e_im = Image.fromarray((255 - 200 * np.clip(E, 0, 1)).astype(np.uint8)).convert("RGB").resize(
            (round(side * SIZE[0] / SIZE[1]), side), Image.Resampling.BILINEAR)
        ims, caps = [src, e_im], [f"void source: {sid}", "emptiness E (dark = void)"]
        for edge in ("halo", "pool"):
            for seed in (5, 6):
                spec = next(s for s in specs if s["void"] == name and s["edge"] == edge and s["seed"] == seed)
                polys = list(np.load(OUT / "cands" / _cname(spec), allow_pickle=True))
                ims.append(_render_polys(polys, rf.pen_px_for(SIZE), side))
                pr = next(r["profile"] for r in res if r["spec"]["label"] == spec["label"] and r["spec"]["seed"] == seed)
                caps.append(f"{edge} s{seed}  void {pr['void_share']:.2f} lac25 {pr['lac_25']:.2f}")
        Wr = sum(im.width + 10 for im in ims)
        row = Image.new("RGB", (Wr, side + 34), PAPER)
        d = ImageDraw.Draw(row)
        x = 0
        for im, cap in zip(ims, caps):
            row.paste(im, (x, 30))
            d.text((x + 3, 4), cap, fill=INK)
            x += im.width + 10
        d.text((3, 17), name, fill=FLEX["red"])
        rows.append(row)
    W = max(r.width for r in rows)
    sheet = Image.new("RGB", (W, sum(r.height for r in rows)), PAPER)
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    sheet.save(OUT / "limb.png")
    _jpg(OUT / "limb.png", RESULTS / "sheet_composition-limb.jpg")


if __name__ == "__main__":
    main()

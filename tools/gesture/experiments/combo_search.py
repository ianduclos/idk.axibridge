"""combo_search — searching the kit's combination space (round 10, the risky one).

    .local/gesture/.venv/bin/python tools/gesture/experiments/combo_search.py all

Why: round 9's best image (kit demo 4: a heavy hokusai > nasta'liq drift under a
noise field inked with nib lanes, crossed by a dry bubble-chamber wire) was not
a module, it was a COMBINATION (results/round9-review-2026-10-17.md). The kit
can express thousands of recipes; this script samples recipe families around
that pattern, scores every candidate with taste PROXIES calibrated against what
Ian kept / rejected in rounds 8-9, and lets the selector breed a second
generation.

1. sampler     `sample_recipe(rng)`: two or three distinct voices on one
               surface — HEAVY (inked: field / timing / prosody / own-tempo
               weight, nib or line-built renderer), WIRE (a dry hand, machine
               or dance), optionally a THIRD (its own measurement via
               `annotate`, or a dance wire). Every candidate is validated by
               `kit.validate` and saved by `kit.preview` with its recipe.
2. selector    `features(sheet)` + `score(f)`: voice separability (can a
               nearest-centroid classifier tell which voice a 12 mm patch came
               from?), weight contrast, crossing, wholeness, capsules (closed
               mass rings that are long and thin: "sausages"), hatching
               (windows of >= 4 parallel separate strokes), confetti (island
               count), ink cover. Weights are set a priori in WEIGHTS and
               checked against the labelled round-9 recipes in CALIBRATION.
               They are proxies, not taste.
3. sheets      population / top / bottom / generation-2 contact sheets, every
               thumbnail labelled with its id; `<id>.recipe.json` beside
               `<id>.jpg` in .local/gesture/out/combo_search/ rebuilds it.
4. breeding    `mutate` / `crossover` on recipes (swap voices, swap
               modulators, change routes, reseed) from gen-1's top picks.

Never plots; images only.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
from multiprocessing import get_context
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture import sheetcomp as sc  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/combo_search"
PAST = ROOT / ".local/gesture/out"
RESULTS = HERE / "results"
DATE = "2026-10-17"
FRAME = (267.0, 180.0)

# ---------------------------------------------------------------------------
# 1. the sampler
# ---------------------------------------------------------------------------

# Pools are priors, not rules: a hand may appear in both, but never in the
# heavy AND the wire voice of one recipe (distinct grammars, never averaged).
HEAVY_HANDS = ("hokusai", "nastaliq", "shikasta", "matisse", "ingres", "marden", "meander69",
               "dance_fluidity", "dance_levitation", "dance_staccato", "mime_mantis", "mime_dragon",
               "mime_roadrunner")
WIRE_HANDS = ("bubble", "polygon_walk", "aaron", "lichtenberg", "molnar_letters", "meander69",
              "mime_roadrunner", "mime_monkey_hands", "mime_prairiedog", "mime_penguin",
              "dance_particles", "dance_thrusting", "marden")
TRAILS = ("dragon", "hummingbird", "levitation", "mantis", "outofbalance", "particles", "penguin",
          "staccato", "thrusting")
TEMPI = ("cmu_49_10", "cmu_55_mantis", "fluidity", "levitation", "particles", "staccato")
MACHINES = ("compass", "ruler", "stair", "koch", "codebook")
CHARTS = ("kappa", "route", "phase", "atlas", "ledger")


def _r(rng, lo, hi, nd=2):
    return round(float(rng.uniform(lo, hi)), nd)


def _pick(rng, seq, p=None):
    return seq[int(rng.choice(len(seq), p=p))]


def _hands_of(part) -> set:
    v = part["voice"]
    out = set(v.get("hands") or [])
    for k in ("hand",):
        if v.get(k):
            out.add(v[k])
    return out


def sample_heavy_voice(rng, avoid=()):
    pool = [h for h in HEAVY_HANDS if h not in avoid]
    kind = _pick(rng, ("drift", "hand", "dance"), p=(0.55, 0.25, 0.20))
    if kind == "drift":
        n = int(rng.choice([2, 3], p=[0.6, 0.4]))
        hands = [str(h) for h in rng.choice(pool, size=n, replace=False)]
        return {"id": "drift", "hands": hands, "blend": _pick(rng, ("interp", "mixture"), p=(0.6, 0.4)),
                "length": _r(rng, 2.5, 5.5, 1), "joins": _pick(rng, ("smooth", "chain"))}
    if kind == "hand":
        return {"id": "hand", "hand": _pick(rng, pool), "length": _r(rng, 2.5, 5.5, 1),
                "joins": _pick(rng, ("smooth", "chain"))}
    return {"id": "dance", "trail": _pick(rng, TRAILS), "effectors": _pick(rng, ("hands", "all", "lhand", "hands+head")),
            "t0": _r(rng, 0.0, 20.0, 1), "seconds": _r(rng, 5.0, 14.0, 1), "cut": "phrase"}


def sample_weight(rng, voice):
    """The heavy voice's weight source: a modulator chain."""
    opts = ["field", "timing", "prosody"] + (["own_tempo"] if voice["id"] == "dance" else [])
    p = {"field": 0.35, "timing": 0.3, "prosody": 0.25, "own_tempo": 0.3}
    w = np.array([p[o] for o in opts])
    kind = opts[int(rng.choice(len(opts), p=w / w.sum()))]
    if kind == "field":
        return [{"id": "constant", "r": None, "W": _r(rng, 2.0, 4.0, 1), "M": _r(rng, 5.0, 9.0, 1)},
                {"id": "field", "preset": _pick(rng, ("noise", "noise", "noise", "radial", "bands")),
                 "scale": _r(rng, 0.08, 0.3), "amount": _r(rng, 0.5, 1.0)}]
    if kind == "timing":
        return [{"id": "timing", "tempo": _pick(rng, TEMPI), "amount": _r(rng, 0.6, 1.2),
                 "mass_width": _r(rng, 4.0, 9.0, 1)}]
    if kind == "prosody":
        return [{"id": "prosody", "rhythm": "event", "unit": "pulse", "contrast": _r(rng, 0.3, 1.0),
                 "density": _r(rng, 0.5, 2.0), "W": _r(rng, 2.0, 3.5, 1), "M": _r(rng, 4.0, 8.0, 1)}]
    return [{"id": "own_tempo", "amount": _r(rng, 0.7, 1.3), "beads": _pick(rng, ("pauses", "dwell")),
             "mass_width": _r(rng, 2.0, 5.0, 1)}]


def sample_heavy_renderer(rng):
    u = rng.random()
    if u < 0.07:
        return {"id": "restate", "copies": int(rng.integers(3, 9)), "pen": 0.35}
    if u < 0.12:
        return {"id": "coil", "rings": int(rng.integers(3, 8)), "pen": 0.35}
    return {"id": "nib", "style": _pick(rng, ("c", "e", "c+e", "b+", "a"), p=(0.3, 0.3, 0.2, 0.1, 0.1)),
            "pen": 0.4}


def sample_heavy(rng, avoid=()):
    v = sample_heavy_voice(rng, avoid)
    mods = sample_weight(rng, v)
    if mods[0]["id"] == "prosody" and v["id"] == "drift":
        v = {**v, "id": "drift_tokens"}           # prosody listens to grammar tokens too
    if v["id"] in ("drift", "drift_tokens", "hand") and rng.random() < 0.15:
        mods = [{"id": "handover", "a": _pick(rng, ("ruler", "stair", "compass")), "b": "none",
                 "share": _r(rng, 0.1, 0.3), "stretch": _r(rng, 10.0, 30.0, 1)}] + mods
    return {"label": "heavy", "voice": v, "modulators": mods, "renderer": sample_heavy_renderer(rng)}


def sample_wire(rng, avoid=()):
    kind = _pick(rng, ("hand", "machine", "dance"), p=(0.5, 0.25, 0.25))
    pool = [h for h in WIRE_HANDS if h not in avoid]
    if kind == "hand":
        v = {"id": "hand", "hand": _pick(rng, pool), "length": _r(rng, 2.5, 5.0, 1),
             "joins": _pick(rng, ("chain", "smooth"))}
    elif kind == "machine":
        v = {"id": "machine", "grammar": _pick(rng, MACHINES),
             "hand": _pick(rng, [h for h in HEAVY_HANDS + WIRE_HANDS if h not in avoid]),
             "length": _r(rng, 2.0, 4.5, 1)}
    else:
        v = {"id": "dance", "trail": _pick(rng, TRAILS), "effectors": _pick(rng, ("hands", "all", "rhand", "head")),
             "t0": _r(rng, 0.0, 20.0, 1), "seconds": _r(rng, 5.0, 15.0, 1), "cut": "phrase"}
    return {"label": "wire", "voice": v, "modulators": [{"id": "wire"}],
            "renderer": {"id": "wire", "pen": _r(rng, 0.2, 0.35)}}


def sample_measure(rng):
    """The heavy line's own measurement, drawn beside it (appended to its chain)."""
    return {"id": "annotate", "chart": _pick(rng, CHARTS),
            "layout": _pick(rng, ("shadow", "right", "below"), p=(0.4, 0.3, 0.3)),
            "drawn_by": _pick(rng, (None, "matisse", "hokusai"), p=(0.6, 0.2, 0.2)),
            "split": _r(rng, 0.3, 0.45), "gap": _r(rng, 0.8, 2.5), "gain": _r(rng, 2.0, 6.0)}


def repair(recipe: dict) -> dict:
    """Keep grammars distinct: the wire must not speak a hand the heavy voice uses."""
    r = copy.deepcopy(recipe)
    if len(r["parts"]) < 2:
        return r
    heavy = _hands_of(r["parts"][0])
    for part in r["parts"][1:]:
        v = part["voice"]
        if v.get("hand") in heavy:
            v["hand"] = next(h for h in WIRE_HANDS if h not in heavy)
    return r


def summarize(recipe: dict) -> str:
    """One line per recipe, readable on a thumbnail strip."""
    bits = []
    for part in recipe["parts"]:
        v = part["voice"]
        if v["id"] in ("drift", "drift_tokens"):
            s = ">".join(v["hands"]) + ("~" if v.get("blend") == "interp" else "")
        elif v["id"] == "hand":
            s = v["hand"]
        elif v["id"] == "machine":
            s = f"{v['grammar']}({v['hand']})"
        elif v["id"] == "dance":
            s = f"dance:{v['trail']}/{v.get('effectors', 'all')}"
        else:
            s = v["id"]
        if v.get("joins") == "chain":
            s += "[ch]"
        mods = []
        for m in part.get("modulators", []):
            if m["id"] in ("wire", "constant"):
                continue
            if m["id"] == "timing":
                mods.append(f"t:{m.get('tempo')}")
            elif m["id"] == "field":
                mods.append(f"f:{m.get('preset', 'noise')}")
            elif m["id"] == "annotate":
                mods.append(f"+{m.get('chart')}/{m.get('layout')}")
            else:
                mods.append(m["id"])
        rd = part.get("renderer", {"id": "wire"})
        rs = rd["id"] + (f":{rd['style']}" if rd["id"] == "nib" else "")
        bits.append(s + ("{" + ",".join(mods) + "}" if mods else "") + " " + rs)
    arr = recipe.get("arranger", {"id": "single"})["id"]
    return (f"[{arr}] " if arr != "single" else "") + "  x  ".join(bits)


def sample_recipe(rng, seed: int | None = None) -> dict:
    heavy = sample_heavy(rng)
    wire = sample_wire(rng, avoid=_hands_of(heavy))
    parts = [heavy, wire]
    u = rng.random()
    if u < 0.35:
        heavy["modulators"] = heavy["modulators"] + [sample_measure(rng)]
    elif u < 0.6:
        third = sample_wire(rng, avoid=_hands_of(heavy) | _hands_of(wire))
        if third["voice"]["id"] != "dance":
            third["voice"] = {"id": "dance", "trail": _pick(rng, TRAILS), "effectors": "hands",
                              "t0": _r(rng, 0.0, 20.0, 1), "seconds": _r(rng, 5.0, 12.0, 1), "cut": "phrase"}
        third["label"] = "dance"
        parts.append(third)
    arranger = {"id": "single"}
    if rng.random() < 0.15:
        n = len(parts)
        arranger = {"id": "poly_scatter", "counts": [1] + [int(rng.integers(2, 7)) for _ in range(n - 1)],
                    "sizes": [_r(rng, 0.7, 0.95)] + [_r(rng, 0.18, 0.4) for _ in range(n - 1)],
                    "bleed": _r(rng, 0.1, 0.4)}
    rec = {"frame": list(FRAME), "seed": int(seed if seed is not None else rng.integers(20000, 30000)),
           "arranger": arranger, "parts": parts, "renderer": {"id": "wire", "pen": 0.4}}
    rec = repair(rec)
    rec["label"] = summarize(rec)
    kit.validate(rec)
    return rec


# ---------------------------------------------------------------------------
# 4. breeding (defined beside the sampler: it reuses the sampler's parts)
# ---------------------------------------------------------------------------

def _heavy_idx(rec):
    return 0


def mutate(recipe: dict, rng, n_ops: int | None = None) -> tuple[dict, list[str]]:
    """1-2 edits: swap a hand, swap the weight source, swap the renderer,
    change the route, swap the wire voice, add/drop/swap the third, reseed."""
    r = copy.deepcopy(recipe)
    r.pop("label", None)
    ops = ["hand", "weight", "renderer", "route", "wire", "third", "seed"]
    done = []
    for _ in range(n_ops or int(rng.integers(1, 3))):
        op = _pick(rng, ops)
        heavy = r["parts"][0]
        hv = heavy["voice"]
        measure = [m for m in heavy["modulators"] if m["id"] == "annotate"]
        if op == "hand":
            if "hands" in hv:
                i = int(rng.integers(len(hv["hands"])))
                pool = [h for h in HEAVY_HANDS if h not in hv["hands"]]
                hv["hands"][i] = _pick(rng, pool)
            elif "hand" in hv:
                hv["hand"] = _pick(rng, [h for h in HEAVY_HANDS if h != hv["hand"]])
            else:
                hv["trail"] = _pick(rng, [t for t in TRAILS if t != hv.get("trail")])
        elif op == "weight":
            base = {**hv, "id": "drift" if hv["id"] == "drift_tokens" else hv["id"]}
            mods = sample_weight(rng, base)
            heavy["voice"] = {**base, "id": "drift_tokens"} if (mods[0]["id"] == "prosody" and base["id"] == "drift") else base
            keep = [m for m in heavy["modulators"] if m["id"] == "handover"]
            heavy["modulators"] = keep + mods + measure
        elif op == "renderer":
            heavy["renderer"] = sample_heavy_renderer(rng)
        elif op == "route":
            if "hands" in hv:
                c = int(rng.integers(3))
                if c == 0:
                    hv["hands"] = hv["hands"][::-1]
                elif c == 1 and len(hv["hands"]) < 4:
                    hv["hands"].append(_pick(rng, [h for h in HEAVY_HANDS if h not in hv["hands"]]))
                else:
                    hv["blend"] = "mixture" if hv.get("blend") == "interp" else "interp"
            if "joins" in hv:
                hv["joins"] = "chain" if hv.get("joins") == "smooth" else "smooth"
        elif op == "wire":
            r["parts"][1] = sample_wire(rng, avoid=_hands_of(heavy))
        elif op == "third":
            if measure:
                heavy["modulators"] = [m for m in heavy["modulators"] if m["id"] != "annotate"]
                if rng.random() < 0.5:
                    heavy["modulators"].append(sample_measure(rng))
            elif len(r["parts"]) > 2:
                r["parts"] = r["parts"][:2]
            else:
                heavy["modulators"].append(sample_measure(rng))
        elif op == "seed":
            r["seed"] = int(rng.integers(20000, 30000))
        done.append(op)
    _fit_arranger(r)
    r = repair(r)
    r["label"] = summarize(r)
    kit.validate(r)
    return r, done


def crossover(a: dict, b: dict, rng) -> dict:
    """The heavy voice of A, the wire of B, a third from either (or none);
    seed and arranger from A."""
    r = copy.deepcopy(a)
    r.pop("label", None)
    r["parts"] = [copy.deepcopy(a["parts"][0]), copy.deepcopy(b["parts"][1])]
    thirds = [p for p in (a["parts"][2:] + b["parts"][2:])]
    if thirds and rng.random() < 0.5:
        r["parts"].append(copy.deepcopy(thirds[int(rng.integers(len(thirds)))]))
    _fit_arranger(r)
    r = repair(r)
    r["label"] = summarize(r)
    kit.validate(r)
    return r


def _fit_arranger(r):
    arr = r.get("arranger", {"id": "single"})
    if arr["id"] == "poly_scatter":
        n = len(r["parts"])
        arr["counts"] = (list(arr.get("counts", [1])) + [3] * n)[:n]
        arr["sizes"] = (list(arr.get("sizes", [0.8])) + [0.3] * n)[:n]


# ---------------------------------------------------------------------------
# 2. the selector: features (proxies) and score
# ---------------------------------------------------------------------------

LONG = sc.LONG_SIDE                     # 1024 px on the long side, ~3.8 px/mm on the 267 mm frame


def part_masks(sheet) -> tuple[np.ndarray, list[np.ndarray]]:
    """Whole-sheet ink mask and one mask per part (inks drawn at pen width)."""
    W, H = sheet.frame
    n = len(sheet.meta["parts"])
    masks = []
    for i in range(n):
        inks = [k for k in sheet.inks if k.meta.get("part") == i and len(k.points) >= 2]
        m = None
        for pen in sorted({round(k.pen, 3) for k in inks}):
            mm = sc.render_mask([k.points for k in inks if round(k.pen, 3) == pen], (W, H), pen, LONG)
            m = mm if m is None else (m | mm)
        if m is None:
            k = LONG / max(W, H)
            m = np.zeros((round(H * k), round(W * k)), bool)
        masks.append(m)
    whole = np.logical_or.reduce(masks) if masks else None
    return whole, masks


def capsules(sheet, whole: np.ndarray | None = None) -> dict:
    """Closed ink rings (mass outlines). A long, thin, nearly convex ring
    (aspect >= 2.2, >= 6 mm long, solidity >= 0.75) whose inside is mostly
    inked is a SOLID CAPSULE, the "sausage" Ian rejected in round 9. A
    winding ribbon (demo 4's nib-c masses: solidity 0.1-0.5) is not, nor is
    an open outline. Round rings are beads.
    Areas are shares of the sheet."""
    from PIL import Image, ImageDraw
    W, H = sheet.frame
    k = (whole.shape[1] / W) if whole is not None else None
    cap = solid = bead = tot = 0.0
    n_cap = n_solid = n_bead = 0
    for ink in sheet.inks:
        if not ink.closed or len(ink.points) < 8:
            continue
        p = np.asarray(ink.points)
        x, y = p[:, 0], p[:, 1]
        area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        if area < 0.5:
            continue
        ev = np.sort(np.linalg.eigvalsh(np.cov(p.T)))
        aspect = math.sqrt(ev[1] / max(ev[0], 1e-9))
        major = 4.0 * math.sqrt(ev[1])
        tot += area
        hull = _hull_area(p)
        solidity = area / max(hull, 1e-9)
        if aspect >= 2.2 and major >= 6.0 and solidity >= 0.75:
            cap += area
            n_cap += 1
            if whole is not None:
                lo = np.floor(p.min(0) * k).astype(int) - 1
                hi = np.ceil(p.max(0) * k).astype(int) + 2
                lo = np.maximum(lo, 0)
                hi = np.minimum(hi, [whole.shape[1], whole.shape[0]])
                if (hi - lo).min() < 2:
                    continue
                im = Image.new("1", (int(hi[0] - lo[0]), int(hi[1] - lo[1])), 0)
                ImageDraw.Draw(im).polygon([tuple(v) for v in (p * k - lo)], fill=1)
                inside = np.asarray(im, bool)
                sub = whole[lo[1]:hi[1], lo[0]:hi[0]][: inside.shape[0], : inside.shape[1]]
                inside = inside[: sub.shape[0], : sub.shape[1]]
                if inside.sum() and sub[inside].mean() > 0.5:
                    solid += area
                    n_solid += 1
        elif aspect < 1.8:
            bead += area
            n_bead += 1
    A = W * H
    return {"capsule_area": solid / A, "ring_capsule_area": cap / A, "bead_area": bead / A,
            "mass_area": tot / A, "n_capsules": n_solid, "n_open_capsules": n_cap - n_solid, "n_beads": n_bead}


def _hull_area(p: np.ndarray) -> float:
    from scipy.spatial import ConvexHull
    try:
        return float(ConvexHull(p).volume)
    except Exception:                       # degenerate (collinear) ring
        return 0.0


def hatching(mask: np.ndarray, win: int = 48) -> float:
    """Share of inked 12 mm windows that read as hatching: >= 4 separate,
    elongated strokes, all within ~12 degrees of one direction. The mask is
    dilated 2 px (~0.5 mm) first, so nib lanes and tight restatements merge
    into one stroke; real hatching (gaps > 1 mm) stays separate."""
    m = ndi.binary_dilation(mask, iterations=2)
    h, w = m.shape
    inked = hatch = 0
    for y in range(0, h - win + 1, win):
        for x in range(0, w - win + 1, win):
            sub = m[y:y + win, x:x + win]
            if sub.mean() < 0.02:
                continue
            inked += 1
            lab, n = ndi.label(sub, structure=np.ones((3, 3)))
            if n < 4:
                continue
            angs = []
            for j in range(1, n + 1):
                ys, xs = np.nonzero(lab == j)
                if len(xs) < 30:
                    continue
                c = np.cov(np.vstack([xs, ys]))
                ev, vec = np.linalg.eigh(c)
                if ev[1] < 9.0 * max(ev[0], 1e-9):          # aspect < 3
                    continue
                v = vec[:, 1]
                angs.append(math.atan2(v[1], v[0]))
            if len(angs) >= 4:
                a2 = np.exp(2j * np.array(angs))
                if abs(a2.mean()) > 0.9:
                    hatch += 1
    return hatch / max(inked, 1)


def _patch_table(mask: np.ndarray, win: int = 48, stride: int = 32) -> np.ndarray:
    """Per-patch texture features of one voice's own mask (rows = patches with ink)."""
    from skimage.morphology import skeletonize
    if not mask.any():
        return np.zeros((0, 6))
    sk = skeletonize(mask)
    nb = ndi.convolve(sk.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - 1
    ends = sk & (nb == 1)
    junc = sk & (nb >= 3)
    edt = ndi.distance_transform_edt(mask)
    f = mask.astype(float)
    gy, gx = ndi.sobel(f, 0), ndi.sobel(f, 1)
    Jxx, Jyy, Jxy = (ndi.gaussian_filter(a, 1.5) for a in (gx * gx, gy * gy, gx * gy))
    theta2 = np.exp(1j * np.arctan2(2 * Jxy, Jxx - Jyy))
    rows = []
    h, w = mask.shape
    for y in range(0, h - win + 1, stride):
        for x in range(0, w - win + 1, stride):
            sl = (slice(y, y + win), slice(x, x + win))
            ink = mask[sl].sum()
            if ink < 0.01 * win * win:
                continue
            s = sk[sl]
            ns = max(int(s.sum()), 1)
            th = edt[sl][s]
            coh = abs(theta2[sl][s].mean()) if s.any() else 0.0
            rows.append([ink / (win * win),               # density
                         float(np.mean(th)) if len(th) else 0.0,   # stroke half-width (weight)
                         ink / ns,                        # ink per skeleton px (lanes, masses)
                         ends[sl].sum() / ns * 100,       # free ends
                         junc[sl].sum() / ns * 100,       # crossings / branching
                         coh])                            # straightness / parallelism
    return np.asarray(rows, float)


def separability(tables: list[np.ndarray], max_n: int = 300, seed: int = 0) -> tuple[float, float]:
    """Can a nearest-centroid classifier tell which voice a patch came from?
    Two folds (alternate patches), balanced accuracy, per pair of voices.
    Returns (min over pairs, mean over pairs); 0.5 = indistinguishable."""
    rng = np.random.default_rng(seed)
    tabs = []
    for t in tables:
        if len(t) > max_n:
            t = t[np.sort(rng.choice(len(t), max_n, replace=False))]
        tabs.append(t)
    accs = []
    for i in range(len(tabs)):
        for j in range(i + 1, len(tabs)):
            a, b = tabs[i], tabs[j]
            if len(a) < 4 or len(b) < 4:
                accs.append(0.5 if (len(a) or len(b)) else 0.5)
                continue
            X = np.vstack([a, b])
            X = np.log1p(np.abs(X)) * np.sign(X)
            mu, sd = X.mean(0), X.std(0) + 1e-9
            X = (X - mu) / sd
            y = np.r_[np.zeros(len(a)), np.ones(len(b))]
            idx = np.arange(len(X))
            fold_acc = []
            for f in (0, 1):
                tr, te = idx[idx % 2 == f], idx[idx % 2 != f]
                c0 = X[tr][y[tr] == 0].mean(0)
                c1 = X[tr][y[tr] == 1].mean(0)
                pred = (np.linalg.norm(X[te] - c1, axis=1) < np.linalg.norm(X[te] - c0, axis=1)).astype(float)
                yt = y[te]
                if (yt == 0).any() and (yt == 1).any():
                    fold_acc.append(0.5 * ((pred[yt == 0] == 0).mean() + (pred[yt == 1] == 1).mean()))
            accs.append(float(np.mean(fold_acc)) if fold_acc else 0.5)
    if not accs:
        return float("nan"), float("nan")
    return float(min(accs)), float(np.mean(accs))


def islands(mask: np.ndarray, frac: float = 0.01) -> tuple[int, float]:
    """(island count after closing gaps of `frac` side, largest island's ink share)."""
    if not mask.any():
        return 0, 0.0
    side = math.sqrt(mask.size)
    r = max(1, round(frac * side / 2))
    lab, n = ndi.label(ndi.binary_dilation(mask, iterations=r), structure=np.ones((3, 3)))
    sizes = np.bincount(lab[mask])[1:]
    return int(n), float(sizes.max() / max(mask.sum(), 1)) if len(sizes) else 0.0


def island_lengths(mask: np.ndarray, frac: float = 0.01) -> np.ndarray:
    """Skeleton length of every island (gaps of `frac` side closed), in units of side."""
    from skimage.morphology import skeletonize
    if not mask.any():
        return np.zeros(0)
    side = math.sqrt(mask.size)
    r = max(1, round(frac * side / 2))
    lab, n = ndi.label(ndi.binary_dilation(mask, iterations=r), structure=np.ones((3, 3)))
    sk = skeletonize(mask)
    return np.bincount(lab[sk], minlength=n + 1)[1:] / side


def features(sheet) -> dict:
    whole, masks = part_masks(sheet)
    f: dict = {"n_parts": len(masks)}
    f["cover"] = float(whole.mean())
    n_isl, _ = islands(whole, 0.01)
    f["islands"] = n_isl
    f.update(capsules(sheet, whole))
    f["hatch"] = hatching(whole)
    L_all = island_lengths(whole)
    f["specks"] = float(L_all[L_all < 0.012].sum() / max(L_all.sum(), 1e-9))   # ink in islands < ~3 mm
    # per voice
    weights, whole_share, skel_len = [], [], []
    from skimage.morphology import skeletonize
    for m in masks:
        sk = skeletonize(m) if m.any() else m
        skel_len.append(float(sk.sum()))
        weights.append(float(m.sum()) / max(float(sk.sum()), 1.0))
        L = island_lengths(m)
        # a voice stays whole when its line lives in long islands (>= 0.1 side, ~ 27 mm)
        whole_share.append(float(L[L >= 0.1].sum() / max(L.sum(), 1e-9)) if len(L) else 0.0)
    f["weights"] = [round(w, 3) for w in weights]
    f["wholeness"] = float(np.mean(whole_share)) if whole_share else 0.0
    if len(masks) >= 2:
        tables = [_patch_table(m) for m in masks]
        f["sep_min"], f["sep_mean"] = separability(tables)
        ws = [w for w, L in zip(weights, skel_len) if L > 0]
        f["contrast"] = float(math.log(max(ws) / min(ws))) if len(ws) >= 2 else 0.0
        # crossing: share of inked cells (16 across the long side) where >= 2 voices are present
        h, w = whole.shape
        c = LONG // 16
        pres = np.stack([m[: h // c * c, : w // c * c].reshape(h // c, c, w // c, c).mean((1, 3)) > 0.004
                         for m in masks])
        any_ = pres.any(0)
        f["crossing"] = float((pres.sum(0) >= 2).sum() / max(any_.sum(), 1))
        L = sorted(skel_len)
        f["presence"] = float(L[0] / max(L[-1], 1.0))       # quietest voice's line vs loudest
    else:
        f.update(sep_min=float("nan"), sep_mean=float("nan"), contrast=0.0, crossing=0.0, presence=0.0)
    return f


# A priori weights (set before looking at the calibration numbers; see the
# write-up for what changed after). Positive terms reward what Ian kept in
# round 9 (two distinct voices on one surface, each whole, crossing); negative
# terms punish what he rejected (sausages, hatching/systematic runs, confetti,
# over- or under-inked sheets).
WEIGHTS = {"sep": 1.0, "contrast": 0.4, "crossing": 0.4, "wholeness": 0.4, "presence": 0.3,
           "capsule": -1.2, "hatch": -1.2, "confetti": -0.4, "cover": -0.6}
COVER_BAND = (0.025, 0.14)


def terms(f: dict) -> dict:
    t = {}
    sep = f.get("sep_min")
    t["sep"] = 0.0 if sep is None or not np.isfinite(sep) else float(np.clip((sep - 0.5) * 2, 0, 1))
    t["contrast"] = float(np.clip(f["contrast"] / 1.5, 0, 1))
    t["crossing"] = float(np.clip(f["crossing"] / 0.3, 0, 1))
    t["wholeness"] = float(f["wholeness"])
    t["presence"] = float(np.clip(f["presence"] / 0.3, 0, 1))
    t["capsule"] = float(np.clip(f["capsule_area"] / 0.01, 0, 1))
    t["hatch"] = float(np.clip(f["hatch"] / 0.15, 0, 1))
    t["confetti"] = float(np.clip(f["specks"] / 0.1, 0, 1))
    lo, hi = COVER_BAND
    c = max(f["cover"], 1e-6)
    t["cover"] = float(np.clip(max(math.log(lo / c), math.log(c / hi), 0) / math.log(3), 0, 1))
    return t


def score(f: dict, weights: dict = WEIGHTS) -> float:
    t = terms(f)
    return float(sum(weights[k] * t[k] for k in weights))


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

def evaluate(job) -> dict:
    """Worker: run a recipe, save image + recipe + thumbnail, measure it."""
    cid, recipe, out_dir, save = job
    t0 = time.perf_counter()
    try:
        sheet = kit.run(recipe)
        if save:
            out_dir = Path(out_dir)
            kit.preview(sheet, out_dir / f"{cid}.jpg", px_per_mm=4.0, label=f"{cid}  {summarize(sheet.recipe)}")
            th = kit.render_image(sheet, px_per_mm=1.6, label=None)
            (out_dir / "thumbs").mkdir(parents=True, exist_ok=True)
            th.save(out_dir / "thumbs" / f"{cid}.png")
        f = features(sheet)
        return {"id": cid, "ok": True, "features": f, "score": score(f), "terms": terms(f),
                "seconds": round(time.perf_counter() - t0, 1), "recipe": sheet.recipe,
                "summary": summarize(sheet.recipe)}
    except Exception as e:                                     # a failed candidate is data too
        return {"id": cid, "ok": False, "error": f"{type(e).__name__}: {e}", "recipe": recipe,
                "seconds": round(time.perf_counter() - t0, 1)}


def run_jobs(jobs, workers: int = 2) -> list[dict]:
    out = []
    with get_context("spawn").Pool(workers) as pool:
        for res in pool.imap(evaluate, jobs):
            tag = f"{res['score']:+.2f}" if res.get("ok") else "FAIL " + res["error"][:80]
            print(f"  {res['id']:<10} {res['seconds']:5.1f}s  {tag}  {res.get('summary', '')[:90]}", flush=True)
            out.append(res)
    return out


# Round-9 recipes with Ian's verdicts (round9-review-2026-10-17.md):
# +1 kept / loved, 0 neutral ("≈ what the bench already saves", "mixed"),
# -1 passed over ("meh", "too sausagy").
CALIBRATION = {
    "kit/2-chain-staccato-nib-e": 1, "kit/4-polyphony": 1,
    "kit/1-bench-default": 0, "kit/3-grid-each": 0,
    "voices_machine/annotated": 1, "voices_machine/limb-atlas-ledger": 1, "voices_machine/charts": 1,
    "voices_machine/shadow": 1, "voices_machine/handover": 0,
    "polyphonic_sheets/page-P2-columns-rtl": 1, "polyphonic_sheets/converse-contrast-9300": 1,
    "polyphonic_sheets/converse-contrast-9302": 1, "polyphonic_sheets/converse-echo-9301": 1,
    "polyphonic_sheets/scatter-A-dominant": 0, "polyphonic_sheets/scatter-C-sizes": 0,
    "polyphonic_sheets/mixed-M1-page-siblings": -1, "polyphonic_sheets/mixed-M2-scatter-siblings": -1,
    "prosody_accumulation/f1-field-noise": 1, "prosody_accumulation/f2-timing-staccato": 1,
    "prosody_accumulation/f3-event-pulse": 1, "prosody_accumulation/d7-single-space-two-inks": 1,
    "prosody_accumulation/d8-rows-time-two-inks": 1,
    "prosody_accumulation/f4-event-segment": -1, "prosody_accumulation/f5-regular": -1,
    "prosody_accumulation/f6-syncopated": -1, "prosody_accumulation/f7-phrase": -1,
    "prosody_accumulation/f8-anticipate": -1, "prosody_accumulation/f9-staccato-then-prosody": -1,
    "prosody_accumulation/s3-restate6": -1, "prosody_accumulation/s4-restate6-contour": -1,
    "prosody_accumulation/s5-coil-spiral": -1, "prosody_accumulation/s6-restate3-hull": -1,
}


def auc(pos: list[float], neg: list[float]) -> float:
    """P(score of a kept recipe > score of a rejected one), ties count half."""
    if not pos or not neg:
        return float("nan")
    w = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return w / (len(pos) * len(neg))


def calibrate(workers: int = 2) -> list[dict]:
    jobs = []
    for name in CALIBRATION:
        p = PAST / f"{name}.recipe.json"
        if p.exists():
            jobs.append((name.replace("/", "__"), json.loads(p.read_text()), str(OUT / "calib"), False))
    res = run_jobs(jobs, workers)
    for r in res:
        r["label_ian"] = CALIBRATION[r["id"].replace("__", "/")]
    (OUT / "calibration.json").write_text(json.dumps(res, indent=1, default=float))
    return res


def calib_report(res: list[dict]) -> str:
    ok = [r for r in res if r["ok"]]
    lines = ["| recipe | Ian | score | " + " | ".join(WEIGHTS) + " |",
             "|---|---|---|" + "---|" * len(WEIGHTS)]
    for r in sorted(ok, key=lambda r: -r["score"]):
        lines.append(f"| {r['id'].replace('__', '/')} | {r['label_ian']:+d} | {r['score']:+.2f} | "
                     + " | ".join(f"{r['terms'][k]:.2f}" for k in WEIGHTS) + " |")
    pos = [r["score"] for r in ok if r["label_ian"] > 0]
    neg = [r["score"] for r in ok if r["label_ian"] < 0]
    lines.append("")
    lines.append(f"AUC kept vs rejected (whole score): {auc(pos, neg):.2f}  (n = {len(pos)} kept, {len(neg)} rejected)")
    for k in WEIGHTS:
        sgn = 1 if WEIGHTS[k] > 0 else -1
        a = auc([sgn * r["terms"][k] for r in ok if r["label_ian"] > 0],
                [sgn * r["terms"][k] for r in ok if r["label_ian"] < 0])
        lines.append(f"- term {k}: AUC {a:.2f}")
    multi = [r for r in ok if r["features"]["n_parts"] >= 2]
    pm = [r["score"] for r in multi if r["label_ian"] > 0]
    nm = [r["score"] for r in multi if r["label_ian"] < 0]
    lines.append(f"AUC among multi-voice recipes only: {auc(pm, nm):.2f}  (n = {len(pm)} kept, {len(nm)} rejected)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. sheets
# ---------------------------------------------------------------------------

def labelled_thumb(res: dict, note: str = ""):
    from PIL import Image, ImageDraw
    from gesture.kit.core import INK, PAPER, _font
    im = Image.open(OUT / "thumbs" / f"{res['id']}.png").convert("RGB")
    fs = max(11, im.width // 34)
    strip = Image.new("RGB", (im.width, int(fs * 3.3)), PAPER)
    d = ImageDraw.Draw(strip)
    head = f"{res['id']}  score {res['score']:+.2f}" + (f"  {note}" if note else "")
    d.text((4, 2), head, fill=INK, font=_font(fs))
    s = res["summary"]
    maxc = int(im.width / (fs * 0.52))
    d.text((4, 2 + int(fs * 1.5)), s[:maxc], fill=(0x6F, 0x6E, 0x69), font=_font(max(9, int(fs * 0.8))))
    full = Image.new("RGB", (im.width, im.height + strip.height), PAPER)
    full.paste(im, (0, 0))
    full.paste(strip, (0, im.height))
    return full


def save_sheet(images, cols: int, title: str, path: Path) -> Path:
    img = kit.contact(images, cols, title=title)
    for q in (86, 78, 70, 62, 54):
        img.save(path, quality=q, optimize=True)
        if path.stat().st_size < 1_000_000:
            break
    if path.stat().st_size >= 1_000_000:
        img = img.resize((img.width * 3 // 4, img.height * 3 // 4))
        img.save(path, quality=70, optimize=True)
    print(f"sheet -> {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")
    return path


def generation1(n: int, seed: int = 10_000, workers: int = 2) -> list[dict]:
    rng = np.random.default_rng(seed)
    jobs = []
    # the anchor: kit demo 4 as it was, so the ranking shows where the known-good lands
    ref = json.loads((PAST / "kit/4-polyphony.recipe.json").read_text())
    jobs.append(("g1-ref4", ref, str(OUT), True))
    for i in range(n):
        jobs.append((f"g1-{i:02d}", sample_recipe(rng), str(OUT), True))
    return run_jobs(jobs, workers)


def generation2(parents: list[dict], n: int, seed: int = 20_000, workers: int = 2) -> list[dict]:
    rng = np.random.default_rng(seed)
    jobs, lineage = [], {}
    for i in range(n):
        cid = f"g2-{i:02d}"
        if i % 2 == 0 and len(parents) >= 2:
            a, b = rng.choice(len(parents), 2, replace=False)
            rec = crossover(parents[a]["recipe"], parents[b]["recipe"], rng)
            lineage[cid] = f"{parents[a]['id']} x {parents[b]['id']}"
        else:
            a = int(rng.integers(len(parents)))
            rec, ops = mutate(parents[a]["recipe"], rng)
            lineage[cid] = f"{parents[a]['id']} ~ {'+'.join(ops)}"
        jobs.append((cid, rec, str(OUT), True))
    res = run_jobs(jobs, workers)
    for r in res:
        r["lineage"] = lineage[r["id"]]
    return res


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["calibrate", "search", "all"])
    ap.add_argument("--n1", type=int, default=40)
    ap.add_argument("--n2", type=int, default=24)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    if a.what in ("calibrate", "all"):
        print("calibration (round-9 recipes with Ian's verdicts)")
        res = calibrate(a.workers)
        rep = calib_report(res)
        (OUT / "calibration.md").write_text(rep + "\n")
        print(rep)
    if a.what in ("search", "all"):
        print(f"generation 1: {a.n1} samples + the demo-4 anchor")
        g1 = generation1(a.n1, workers=a.workers)
        ok1 = sorted([r for r in g1 if r["ok"]], key=lambda r: -r["score"])
        parents = [r for r in ok1 if r["id"] != "g1-ref4"][: a.top]
        print(f"generation 2: {a.n2} children of {[p['id'] for p in parents]}")
        g2 = generation2(parents, a.n2, workers=a.workers)
        ok2 = sorted([r for r in g2 if r["ok"]], key=lambda r: -r["score"])
        (OUT / "population.json").write_text(json.dumps({"g1": g1, "g2": g2}, indent=1, default=float))
        rank1 = {r["id"]: i + 1 for i, r in enumerate(ok1)}
        pop = sorted(ok1, key=lambda r: r["id"])
        save_sheet([labelled_thumb(r, f"rank {rank1[r['id']]}") for r in pop], 6,
                   f"combo_search gen 1: {len(pop)} recipes sampled around kit demo 4 (+ g1-ref4 = demo 4 itself); "
                   f"id order; recipe beside each <id>.jpg in .local/gesture/out/combo_search",
                   RESULTS / f"combo_search-gen1-population-{DATE}.jpg")
        save_sheet([labelled_thumb(r, f"rank {rank1[r['id']]}") for r in ok1[:12]], 4,
                   "combo_search gen 1: the selector's TOP 12 (proxies, not taste)",
                   RESULTS / f"combo_search-gen1-top-{DATE}.jpg")
        save_sheet([labelled_thumb(r, f"rank {rank1[r['id']]}") for r in ok1[-12:]], 4,
                   "combo_search gen 1: the selector's BOTTOM 12",
                   RESULTS / f"combo_search-gen1-bottom-{DATE}.jpg")
        rank2 = {r["id"]: i + 1 for i, r in enumerate(ok2)}
        save_sheet([labelled_thumb(r, r.get("lineage", "")) for r in sorted(ok2, key=lambda r: r["id"])], 6,
                   f"combo_search gen 2: {len(ok2)} children (even ids = crossover A x B, odd = mutation ~ ops) "
                   f"of gen-1 top {a.top}", RESULTS / f"combo_search-gen2-population-{DATE}.jpg")
        save_sheet([labelled_thumb(r, "gen 1") for r in ok1[:6]] + [labelled_thumb(r, "gen 2") for r in ok2[:6]], 6,
                   "combo_search: gen 1 top 6 (row 1) vs gen 2 top 6 (row 2)",
                   RESULTS / f"combo_search-gen1-vs-gen2-{DATE}.jpg")
        s1 = np.array([r["score"] for r in ok1 if r["id"] != "g1-ref4"])
        s2 = np.array([r["score"] for r in ok2])
        print(f"gen1 score median {np.median(s1):+.2f} top-8 mean {np.mean(np.sort(s1)[-8:]):+.2f}; "
              f"gen2 median {np.median(s2):+.2f} top-8 mean {np.mean(np.sort(s2)[-8:]):+.2f}; "
              f"ref4 rank {rank1.get('g1-ref4')} / {len(ok1)}; failures {len(g1) - len(ok1)} + {len(g2) - len(ok2)}")
    print(f"total {time.perf_counter() - t0:.0f} s")


if __name__ == "__main__":
    main()

"""Gesture timing → line texture (round 8). results/gesture_timing-2026-10-16.md.

    .local/gesture/.venv/bin/python -m experiments.gesture_timing measure   # dance dynamics + 2/3 law
    .local/gesture/.venv/bin/python -m experiments.gesture_timing static    # width vs κ in drawn lines
    .local/gesture/.venv/bin/python -m experiments.gesture_timing strips    # timing → r(s) diagnostic
    .local/gesture/.venv/bin/python -m experiments.gesture_timing sheet     # danced vs preset fields
    .local/gesture/.venv/bin/python -m experiments.gesture_timing limb      # shikasta danced by 49; the dance draws itself

(run from tools/gesture). Outputs: .local/gesture/out/gesture_timing/,
sheets copied (< 1 MB) to results/.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import gesture_timing as gt  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DANCE = ROOT / ".local/gesture/corpus/dance"
OUT = ROOT / ".local/gesture/out/gesture_timing"
RESULTS = Path(__file__).resolve().parents[1] / "results"
PAPER = "#FFFCF0"
INK = "#100F0F"
BLUE, RED, GREEN, ORANGE = "#4385BE", "#D14D41", "#879A39", "#DA702C"
JOBS = 2
SIZE = (840, 1200)

# named takes used for generation (label → path, effector, window start s, window s)
TAKES = {
    "Staccato (Romero)": ("e2-stocos/Staccato_FullBody_Take1_proc.bvh", "rhand", 30.0, 40.0),
    "Fluidity (Romero)": ("e2-stocos/Fluidity_FullBody_Take1_proc.bvh", "rhand", 30.0, 40.0),
    "Levitation (Romero)": ("e2-stocos/Levitation_FullBody_Take1_proc.bvh", "rhand", 30.0, 40.0),
    "Particles (Romero)": ("e2-stocos/Particles_FullBody_Take1_proc.bvh", "rhand", 30.0, 40.0),
    "CMU 49_10 fold-in, curl": ("cmu-49/49_10.amc", "rhand", 0.0, 11.8),
    "CMU 55_13 praying mantis": ("cmu-55/55_13.amc", "rhand", 10.0, 40.0),
}


def _load(rel: str, **kw):
    return gt.load_motion(DANCE / rel, **kw)


# ---------------------------------------------------------------------------
# measure: dance dynamics
# ---------------------------------------------------------------------------

def _trials():
    out = []
    for d in ("cmu-05", "cmu-49", "cmu-55"):
        out += [f"{d}/{p.name}" for p in sorted((DANCE / d).glob("*.amc"))]
    for d in ("e2-stocos", "e2mb-unusual"):
        out += [f"{d}/{p.name}" for p in sorted((DANCE / d).glob("*.bvh"))]
    return out


def _measure_one(rel: str) -> dict:
    t = time.perf_counter()
    kw = {"max_frames": 15000} if rel.endswith(".bvh") else {}
    m = _load(rel, **kw)
    fam = "bvh" if rel.endswith(".bvh") else "amc"
    rec = {"trial": rel, "fps": m.fps, "dur_s": round(m.duration(), 1), "effectors": {}}
    for eff in ("rhand", "lhand", "head", "rfoot"):
        x = m.joint(gt.EFFECTORS[fam][eff][0])
        k = gt.kinematics(x, m.fps, 0.03)
        mask, runs, thr = gt.pauses(k["speed"], m.fps)
        moving = ~mask
        p2, _ = gt.drawing_plane(x, m.up)
        k2 = gt.kinematics(p2, m.fps, 0.03)
        pl3 = gt.power_law(k["speed"], k["kappa"], moving)
        sg3 = gt.segment_power_law(k["speed"], k["kappa"], m.fps)
        sg2 = gt.segment_power_law(k2["speed"], k2["kappa"], m.fps)
        # null: the same speeds against a curvature series from another time
        # (circularly shifted by half the take) — what the fit gives by chance
        sh = np.roll(k["kappa"], len(k["kappa"]) // 2)
        nul = gt.segment_power_law(k["speed"], sh, m.fps)
        dur = [(b - a) / m.fps for a, b in runs]
        rec["effectors"][eff] = {
            "speed_med": float(np.median(k["speed"])), "speed_p95": float(np.percentile(k["speed"], 95)),
            "pause_frac": float(mask.mean()), "pauses_per_min": len(runs) / max(m.duration(), 1e-9) * 60,
            "pause_med_s": float(np.median(dur)) if dur else 0.0,
            "jerk_p95_norm": float(np.percentile(k["jerk"], 95) / max(np.percentile(k["speed"], 95), 1e-9)),
            "cv_speed": float(np.std(k["speed"]) / max(np.mean(k["speed"]), 1e-9)),
            "pl3_global": pl3, "pl3_seg": sg3, "pl2_seg": sg2, "pl3_null": nul}
    rec["sec"] = round(time.perf_counter() - t, 1)
    return rec


def cmd_measure(a):
    OUT.mkdir(parents=True, exist_ok=True)
    trials = _trials()
    recs = []
    with ProcessPoolExecutor(JOBS) as ex:
        for r in ex.map(_measure_one, trials):
            e = r["effectors"]["rhand"]
            print(f"{r['trial']:<52} {r['dur_s']:>6}s  v50 {e['speed_med']:6.1f}  pause {e['pause_frac']:.2f} "
                  f"β3seg {e['pl3_seg']['slope']:+.2f} (R² {e['pl3_seg']['r2']:.2f})  β2seg {e['pl2_seg']['slope']:+.2f} "
                  f"null {e['pl3_null']['slope']:+.2f}  [{r['sec']}s]", flush=True)
            recs.append(r)
    (OUT / "measure.json").write_text(json.dumps(recs, indent=1))
    _measure_table(recs)


def _measure_table(recs):
    groups = {"CMU 05 (modern)": "cmu-05", "CMU 49 (modern)": "cmu-49", "CMU 55 (animal mime)": "cmu-55",
              "E2 Stocos (qualities)": "e2-stocos", "E2 MB (unusual poses)": "e2mb-unusual"}
    lines = ["| # | set | effector | trials | speed med / p95 cm/s | still frac | pauses/min | β 3-D global (R²) | "
             "β 3-D per unit (R²) | β plane per unit | β null (shuffled κ) |", "|---|" + "---|" * 10]
    i = 0
    for gname, pre in groups.items():
        rs = [r for r in recs if r["trial"].startswith(pre)]
        for eff in ("rhand", "head", "rfoot"):
            E = [r["effectors"][eff] for r in rs]
            med = lambda f: float(np.nanmedian([f(e) for e in E]))  # noqa: E731
            i += 1
            lines.append(
                f"| {i} | {gname} | {eff} | {len(rs)} | {med(lambda e: e['speed_med']):.0f} / "
                f"{med(lambda e: e['speed_p95']):.0f} | {med(lambda e: e['pause_frac']):.2f} | "
                f"{med(lambda e: e['pauses_per_min']):.0f} | {med(lambda e: e['pl3_global']['slope']):+.2f} "
                f"({med(lambda e: e['pl3_global']['r2']):.2f}) | {med(lambda e: e['pl3_seg']['slope']):+.2f} "
                f"({med(lambda e: e['pl3_seg']['r2']):.2f}) | {med(lambda e: e['pl2_seg']['slope']):+.2f} | "
                f"{med(lambda e: e['pl3_null']['slope']):+.2f} |")
    (OUT / "measure_table.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


# ---------------------------------------------------------------------------
# static: width vs curvature in drawn lines
# ---------------------------------------------------------------------------

def _static_one(spec):
    name, folder, nib = spec
    from gesture.core import Drawing
    ds = []
    for p in sorted(Path(folder).glob("*.json")):
        if p.name.endswith(".outline.json") or p.name.endswith(".meta.json"):
            continue
        try:
            ds.append(Drawing.load(p))
        except Exception:  # noqa: BLE001
            continue
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = gt.width_curvature(ds, nib=nib)
    smp = r.pop("samples", None)
    if smp is not None:
        rng = np.random.default_rng(0)
        k = min(4000, len(smp[0]))
        ix = rng.choice(len(smp[0]), k, replace=False)
        np.save(OUT / f"static_{name.replace(' ', '_')}.npy", np.stack([smp[0][ix], smp[1][ix]]))
    return {"set": name, "sheets": len(ds), "nib_removed": nib, **r}


def cmd_static(a):
    OUT.mkdir(parents=True, exist_ok=True)
    X = ROOT / ".local/gesture/out"
    specs = [(n, X / "extract_hybrid" / n, False) for n in ("matisse", "hokusai", "ingres")]
    C = X / "calligraphy/extract"
    for n in ("shikasta", "nastaliq", "naskh", "diwani", "maghribi", "ghubar", "karalama"):
        specs.append((n, C / n, False))
        specs.append((n + " −nib", C / n, True))
    for n in ("print_AL01", "print_AL04", "print_AL08", "print_AL09"):
        specs.append((n + " −nib", C / n, True))
    recs = []
    with ProcessPoolExecutor(JOBS) as ex:
        for r in ex.map(_static_one, specs):
            print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
            recs.append(r)
    (OUT / "static.json").write_text(json.dumps(recs, indent=1))
    lines = ["| # | set | sheets | samples | ρ(width resid, κ fine) | ρ(…, κ movement-scale) | slope log w / log κ | "
             "w bend÷straight | w near end÷interior | nib R² |", "|---|" + "---|" * 9]
    for i, r in enumerate(recs, 1):
        if not r.get("n"):
            lines.append(f"| {i} | {r['set']} | {r['sheets']} | 0 | | | | | | |")
            continue
        nr = "" if r.get("nib_r2") is None else f"{r['nib_r2']:.2f}"
        lines.append(f"| {i} | {r['set']} | {r['sheets']} | {r['n']} | {r['rho_fine']:+.2f} | {r['rho_coarse']:+.2f} | "
                     f"{r['slope_logw_logk']:+.3f} | {r['w_ratio_bend_vs_straight']:.2f} | "
                     f"{r['w_ratio_end_vs_interior']:.2f} | {nr} |")
    (OUT / "static_table.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


# ---------------------------------------------------------------------------
# generation helpers
# ---------------------------------------------------------------------------

_TCACHE: dict = {}


def take_timing(label: str):
    if label not in _TCACHE:
        rel, eff, t0, dur = TAKES[label]
        kw = {"max_frames": int((t0 + dur + 2) * 50)} if rel.endswith(".bvh") else {}
        m = _load(rel, **kw)
        tm = gt.timing_from_motion(m, eff, label=label)
        _TCACHE[label] = tm.window(t0, min(dur, tm.t[-1] - t0))
    return _TCACHE[label]


def _base(structure: str, hand: str, seed: int):
    from gesture import regime_field as rf
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return rf.compose(seed, SIZE, structure=structure, field=rf.constant(0.0), hands=hand, signs=0)


def danced(base, tm, *, seed: int = 0, **kw):
    """Render base centrelines danced by timing tm → (polylines, info)."""
    from gesture import signs
    H = SIZE[1]
    W, sw, pen = 0.013 * H, 0.030 * H, base.meta["pen_px"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        st, info = gt.danced_strokes(base.centrelines, tm, W=W, shape_w=sw, pen=pen,
                                     rng=np.random.default_rng(seed), **kw)
        polys = signs.render_events(st, pen)
    r = info["profiles"]["r"]
    info["share"] = (float(np.mean(r < 0.5)), float(np.mean((r >= 0.5) & (r < 1.5))), float(np.mean(r >= 1.5)))
    return polys, info


def _img(polys, meta, scale=0.5):
    from experiments import regime_compose as RC
    from gesture import regime_field as rf
    return RC.render(rf.Composition(polys, SIZE, dict(meta), [], []), scale)


def _label(img, lines, size=13):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    h = 6 + 14 * len(lines)
    d.rectangle([0, 0, im.width, h], fill="#F2F0E5")
    for i, t in enumerate(lines):
        d.text((4, 3 + 14 * i), t, fill=INK if i == 0 else "#6F6E69")
    return np.asarray(im)


def _cell(spec):
    kind = spec["kind"]
    base = _base(spec["structure"], spec["hand"], spec["seed"])
    if kind == "preset":
        from gesture import regime_field as rf
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            c = rf.compose(spec["seed"], SIZE, structure=spec["structure"], field=spec["field"], hands=spec["hand"],
                           signs=6)
        sh = c.meta["regime_share"]
        img = _img(c.polylines, c.meta)
        txt = [f"PRESET field '{spec['field']}' (spatial)", f"{spec['structure']}/{spec['hand']}  line {sh['line']:.0%} "
               f"nib {sh['nib']:.0%} mass {sh['shape']:.0%}  6 signs (grammar sites)"]
        return _label(img, txt), {"label": spec["field"], "share": sh}
    tm = take_timing(spec["take"])
    polys, info = danced(base, tm, seed=spec["seed"], **spec.get("kw", {}))
    sh = info["share"]
    img = _img(polys, base.meta)
    txt = [f"DANCED: {spec['take']}" + (f"  [{spec['note']}]" if spec.get("note") else ""),
           f"{tm.n_pauses()} stills in {tm.t[-1]:.0f}s  line {sh[0]:.0%} nib {sh[1]:.0%} mass {sh[2]:.0%}  "
           f"{len(info['events'])} burst signs"]
    return _label(img, txt), {"label": spec["take"], "share": sh, "events": info["events"]}


def _grid(cells, ncol, path, max_kb=950, title=None):
    from PIL import Image, ImageDraw
    h, w = cells[0].shape[:2]
    nrow = (len(cells) + ncol - 1) // ncol
    top = 26 if title else 0
    sheet = np.full((top + h * nrow, w * ncol, 3), 200, np.uint8)
    for k, im in enumerate(cells):
        i, j = divmod(k, ncol)
        sheet[top + i * h:top + i * h + im.shape[0], j * w:j * w + im.shape[1]] = im
        sheet[top + i * h:top + (i + 1) * h, j * w] = 160
        sheet[top + i * h, j * w:(j + 1) * w] = 160
    img = Image.fromarray(sheet)
    if title:
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, img.width, top], fill="#E6E4D9")
        d.text((6, 7), title, fill=INK)
    path.parent.mkdir(parents=True, exist_ok=True)
    q = 85
    while True:
        img.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024 or q <= 40:
            break
        q -= 7
    print("wrote", path, f"{path.stat().st_size / 1024:.0f} KB", flush=True)


def cmd_sheet(a):
    OUT.mkdir(parents=True, exist_ok=True)
    specs = []
    for structure, hand, seed in (("grammar", "matisse", 7), ("single", "hokusai", 5)):
        for f in ("sense", "noise"):
            specs.append({"kind": "preset", "structure": structure, "hand": hand, "seed": seed, "field": f})
        for tk in TAKES:
            specs.append({"kind": "danced", "structure": structure, "hand": hand, "seed": seed, "take": tk})
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_cell, specs))
    (OUT / "sheet.json").write_text(json.dumps([r[1] for r in res], indent=1))
    _grid([r[0] for r in res], 4, OUT / "sheet.jpg",
          title="Same lines, two ways to place regimes: PRESET spatial fields (cols 1-2, row-pairs) vs a dancer's TIMING "
                "(stillness -> ink pools -> mass; flow -> nib held by the wrist; speed -> dry line; jolts -> signs)")


# ---------------------------------------------------------------------------
# strips: one specimen line danced by each take, with its speed record
# ---------------------------------------------------------------------------

def _phi_spread_deg(phi):
    R = abs(np.mean(np.exp(2j * phi)))
    return float(np.rad2deg(np.sqrt(max(-2 * np.log(max(R, 1e-12)), 0)) / 2))


def cmd_strips(a):
    from PIL import Image, ImageDraw
    from gesture import regime as rg, signs
    OUT.mkdir(parents=True, exist_ok=True)
    Wd, Hs, Hp = 1600, 170, 70
    x = np.linspace(50, Wd - 50, 1500)
    spec_line = np.column_stack([x, 85 + 22 * np.sin(x / 95) + 9 * np.sin(x / 31 + 1)])
    W, sw, pen = 13.0, 32.0, 1.8
    rows = []
    stats = {}
    for label in TAKES:
        tm = take_timing(label)
        im = Image.new("RGB", (Wd, Hp + Hs + 22), PAPER)
        d = ImageDraw.Draw(im)
        T = tm.t[-1]
        X = lambda t: 50 + (Wd - 100) * t / T  # noqa: E731
        vmax = np.percentile(tm.speed, 99)
        for i in np.where(tm.pause)[0]:
            d.line([(X(tm.t[i]), 20), (X(tm.t[i]), Hp + 18)], fill="#F6E2CC")
        pts = [(X(t), Hp + 18 - (Hp - 6) * min(v / vmax, 1)) for t, v in zip(tm.t, tm.speed)]
        d.line(pts, fill=BLUE, width=2)
        for b in gt.bursts(tm):
            d.line([(X(tm.t[b]), 20), (X(tm.t[b]), Hp + 18)], fill=RED, width=2)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            st, info = gt.danced_strokes([spec_line], tm, W=W, shape_w=sw, pen=pen, rng=np.random.default_rng(3))
            polys = signs.render_events(st, pen)
        for q in polys:
            d.line([tuple(v) for v in q + [0, Hp + 22]], fill=INK, width=2, joint="curve")
        # tempo ticks: where each 2 s of dance time lands on the line (crowded = slow)
        sg, tt = info["s_grid"], info["profiles"]["t"]
        sl = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(spec_line, axis=0), axis=1))])
        for tk in np.arange(0, T, 2.0):
            sk = float(np.interp(tk, tt, sg))
            xk = float(np.interp(sk, sl, spec_line[:, 0]))
            d.line([(xk, Hp + Hs + 8), (xk, Hp + Hs + 18)], fill=ORANGE, width=2)
        r = info["profiles"]["r"]
        sh = (np.mean(r < 0.5), np.mean((r >= 0.5) & (r < 1.5)), np.mean(r >= 1.5))
        stats[label] = {"pauses": tm.n_pauses(), "dur": float(T), "share": [float(v) for v in sh],
                        "phi_spread_deg": _phi_spread_deg(tm.phi), "events": len(info["events"])}
        d.rectangle([0, 0, Wd, 16], fill="#F2F0E5")
        d.text((6, 3), f"{label}  |  {T:.0f} s window, right hand  |  blue = speed (orange = stillness, red = jolts -> "
                       f"signs)  |  below: one wavy line drawn at this tempo (orange ticks = every 2 s): line {sh[0]:.0%}  nib {sh[1]:.0%}  "
                       f"mass {sh[2]:.0%}  |  wrist-nib spread {stats[label]['phi_spread_deg']:.0f} deg", fill=INK)
        rows.append(np.asarray(im))
    sheet = np.concatenate(rows, axis=0)
    (OUT / "strips.json").write_text(json.dumps(stats, indent=1))
    p = OUT / "strips.jpg"
    Image.fromarray(sheet).save(p, quality=82, optimize=True)
    print("wrote", p, p.stat().st_size // 1024, "KB")
    print(json.dumps(stats, indent=1))


# ---------------------------------------------------------------------------
# limb: a shikasta line danced by subject 49; the dance draws itself
# ---------------------------------------------------------------------------

def _trail_line(label, sigma_s=0.06):
    rel, eff, t0, dur = TAKES[label]
    kw = {"max_frames": int((t0 + dur + 2) * 50)} if rel.endswith(".bvh") else {}
    m = _load(rel, **kw)
    x = m.joint(gt.EFFECTORS["bvh" if rel.endswith(".bvh") else "amc"][eff][0])
    i0, i1 = int(t0 * m.fps), int(min(t0 + dur, m.duration()) * m.fps)
    from scipy.ndimage import gaussian_filter1d
    p2, _ = gt.drawing_plane(x, m.up)
    p2 = gaussian_filter1d(p2, sigma_s * m.fps, axis=0, mode="nearest")[i0:i1]
    W_, H_ = SIZE
    lo, hi = p2.min(0), p2.max(0)
    k = min((W_ * 0.86) / max(hi[0] - lo[0], 1e-9), (H_ * 0.80) / max(hi[1] - lo[1], 1e-9))
    q = (p2 - (lo + hi) / 2) * k + np.array([W_ / 2, H_ / 2 + 20])
    # drop repeated samples (stillness) for the geometry; timing keeps them
    keep = np.concatenate([[True], np.linalg.norm(np.diff(q, axis=0), axis=1) > 1e-3])
    return q[keep]


def _limb_cell(spec):
    from gesture import regime_field as rf
    kind = spec["kind"]
    H = SIZE[1]
    if kind == "calligraphic":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            c = rf.compose(spec["seed"], SIZE, structure="single", field=rf.constant(1.0), hands="shikasta",
                           signs=0, phi_deg=35.0)
        return _label(_img(c.polylines, c.meta), ["one chained line in the shikasta hand (grammar v6, policy-gated sheets)",
                                                  "nib everywhere, phi fixed 35 deg: the calligraphic law, no time"]), {}
    if kind == "trail":
        base = rf.Composition([], SIZE, {"pen_px": rf.pen_px_for(SIZE)}, [_trail_line(spec["take"])], [])
        title = f"THE DANCE DRAWS ITSELF: {spec['take']}"
        sub = "right-hand trail (wall projection) + its own timing + wrist nib"
    else:
        base = _base("single", "shikasta", spec["seed"])
        title = f"shikasta line DANCED by {spec['take']}"
        sub = {"fixed": "timing only: nib fixed 35 deg", "wrist": "timing + nib angle held by the dancer's wrist",
               "travel": "timing + nib follows the travel"}[spec["nib"]]
    tm = take_timing(spec["take"])
    polys, info = danced(base, tm, seed=spec["seed"], nib_from=spec["nib"], phi_fixed=math.radians(35.0),
                         jitter_gain=spec.get("jit", 1.0), q_line=spec.get("q_line", 1.0))
    sh = info["share"]
    img = _img(polys, base.meta)
    if spec.get("q_line") is not None:
        sub += f" (nib from {spec['q_line']:g} x median ink)"
    return _label(img, [title, f"{sub}  |  line {sh[0]:.0%} nib {sh[1]:.0%} mass {sh[2]:.0%}, "
                               f"{len(info['events'])} jolt signs"]), {"title": title, "share": sh}


def cmd_limb(a):
    specs = [{"kind": "calligraphic", "seed": 12},
             {"kind": "danced", "seed": 12, "take": "CMU 49_10 fold-in, curl", "nib": "fixed", "q_line": 0.6},
             {"kind": "danced", "seed": 12, "take": "CMU 49_10 fold-in, curl", "nib": "wrist", "q_line": 0.6},
             {"kind": "danced", "seed": 12, "take": "Staccato (Romero)", "nib": "wrist", "q_line": 0.6},
             {"kind": "trail", "take": "CMU 49_10 fold-in, curl", "nib": "wrist", "seed": 1},
             {"kind": "trail", "take": "Levitation (Romero)", "nib": "wrist", "seed": 1},
             {"kind": "trail", "take": "CMU 55_13 praying mantis", "nib": "wrist", "seed": 1},
             {"kind": "trail", "take": "Staccato (Romero)", "nib": "wrist", "seed": 1}]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_limb_cell, specs))
    _grid([r[0] for r in res], 4, OUT / "limb.jpg",
          title="Limb: one shikasta line danced by subject 49 (row 1; cols 2-3 differ only in who holds the nib) and the dance drawing itself (row 2). "
                "Stillness pools into masses, the wrist holds the nib, jolts grow signs.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    {"measure": cmd_measure, "static": cmd_static, "sheet": cmd_sheet, "strips": cmd_strips, "limb": cmd_limb}[a.cmd](a)

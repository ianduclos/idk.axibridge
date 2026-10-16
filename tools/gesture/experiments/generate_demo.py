"""Stage-3 prototype: learn clothoid-alphabet grammars per artist, generate,
juxtapose, check memorisation, compare panel features.

Writes to .local/gesture/out/grammar/:
  grammar_<artist>.json        the learned hands
  contact_sheet.png            per artist: 4 generated drawings | 2 real ones
  contact_<artist>.png         the same row at full resolution
  juxtaposition.png            code_switch / translate / restyle
  summary.json, summary.md     transition matrices, kind mix, memorisation,
                               panel mismatches

    cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.generate_demo
"""
from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from gesture import panel, synth  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402
from gesture.grammar import (FROM, TO, code_switch, fit_drawing, fit_tokens, generate_drawing,  # noqa: E402
                             generate_tokens, learn, nearest_training_distance, restyle,
                             tokens_to_points, translate)

ROOT = Path(__file__).resolve().parents[3]
EXTRACT = ROOT / ".local" / "gesture" / "out" / "extract"
OUT = ROOT / ".local" / "gesture" / "out" / "grammar"
ARTISTS = ("matisse", "hokusai", "ingres")
SIGMA_FRAC = 0.005        # ≈ 2–3 line widths on these scans; 0.01 leaves ~90 % one-segment fits
CANVAS = 1200
LINE_W = 3.0

# Flexoki (axibridge/static/css/flexoki.css)
PAPER, INK, GREY = "#FFFCF0", "#100F0F", "#878580"
HAND_COLOUR = {"matisse": "#AF3029", "hokusai": "#205EA6", "ingres": "#66800B"}  # red/blue/green-600


def load(artist: str) -> list[Drawing]:
    return [Drawing.load(p) for p in sorted((EXTRACT / artist).glob("*.json"))]


def usable_drawing(d: Drawing) -> Drawing:
    """The strokes the grammar learns from (length/fit filters), as a Drawing."""
    _R, fitted = fit_drawing(d, sigma_frac=SIGMA_FRAC)
    return Drawing([Stroke(st.points, st.width, st.closed) for st, _f, _t in fitted],
                   source=d.source, size=d.size)


def fit_to_canvas(d: Drawing, size=CANVAS, margin=30) -> Drawing:
    allp = np.vstack([s.points for s in d.strokes])
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    k = (size - 2 * margin) / max(hi - lo)
    off = margin + 0.5 * ((size - 2 * margin) - k * (hi - lo))
    return Drawing([Stroke((s.points - lo) * k + off) for s in d.strokes],
                   source=d.source, size=(size, size))


def render(d: Drawing) -> np.ndarray:
    return synth.render(d, line_width=LINE_W, use_stroke_width=False, paper_noise=0.0,
                        blur_sigma=0.5, supersample=2)


def clean_score(d: Drawing) -> float:
    """Prefer drawings whose ink is mostly long strokes (clean line work)."""
    R = d.ref_length()
    L = np.array([s.length() for s in d.strokes]) / R
    if len(L) == 0:
        return -1
    return float(L[L > 0.1].sum() / max(L.sum(), 1e-9)) - 0.002 * len(L)


# ---------------------------------------------------------------------------

def contact_sheet(grammars, drawings, rng, budget="ink", tag=""):
    rows = []
    gen_drawings = {}
    for a in ARTISTS:
        g = grammars[a]
        gens = [generate_drawing(g, rng, (CANVAS, CANVAS), max_strokes=400, clearance=4.0,
                                 budget=budget)
                for _ in range(4)]
        gen_drawings[a] = gens
        reals = sorted(drawings[a], key=clean_score, reverse=True)[:2]
        reals = [fit_to_canvas(usable_drawing(d)) for d in reals]
        imgs = [render(d) for d in gens] + [render(d) for d in reals]
        labels = ([f"generated {i + 1} ({len(d.strokes)} strokes)" for i, d in enumerate(gens)]
                  + [f"real {Path(d.source).stem} ({len(d.strokes)})" for d in reals])
        rows.append((a, imgs, labels))
        fig, axs = plt.subplots(1, 6, figsize=(36, 6.4), dpi=100)
        for ax, im, lab in zip(axs, imgs, labels):
            ax.imshow(im, cmap="gray", vmin=0, vmax=255)
            ax.set_title(lab, fontsize=14)
            ax.axis("off")
        fig.suptitle(f"{a} — 4 generated ({budget} budget) | 2 real (usable strokes, same renderer)",
                     fontsize=18)
        fig.savefig(OUT / f"contact_{a}{tag}.png", facecolor="white", bbox_inches="tight")
        plt.close(fig)
    fig, axs = plt.subplots(3, 6, figsize=(24, 12.6), dpi=110)
    for r, (a, imgs, labels) in enumerate(rows):
        for c, (im, lab) in enumerate(zip(imgs, labels)):
            ax = axs[r, c]
            ax.imshow(im, cmap="gray", vmin=0, vmax=255)
            ax.set_title(lab, fontsize=9)
            ax.set_xticks([])
            ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_color("#CECDC3")
            if c == 0:
                ax.set_ylabel(a, fontsize=14)
    fig.suptitle("clothoid-alphabet grammar: generated (left 4, "
                 f"{budget} budget) vs real extracted (right 2)", fontsize=14)
    fig.tight_layout()
    fig.savefig(OUT / f"contact_sheet{tag}.png", facecolor="white")
    plt.close(fig)
    return gen_drawings


def _plot(ax, pts, colour, lw=1.6):
    ax.plot(pts[:, 0], pts[:, 1], color=colour, lw=lw, solid_capstyle="round")


def _panel(ax, title):
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_title(title, fontsize=8)


def juxtaposition_sheet(grammars, drawings, rng):
    R = 1000.0
    pairs = [("matisse", "hokusai"), ("hokusai", "matisse"), ("matisse", "ingres")]
    fig, axs = plt.subplots(6, 6, figsize=(18, 18), dpi=110)
    for r, (a, b) in enumerate(pairs):
        for c in range(6):
            ax = axs[r, c]
            st = code_switch(grammars[a], grammars[b], rng, 0.5, ref_length=R,
                             heading=rng.uniform(0, 2 * np.pi), length=0.4)
            si = st.meta["switch_s"]
            p = st.points
            s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
            k = int(np.searchsorted(s, si))
            _plot(ax, p[:k + 1], HAND_COLOUR[a])
            _plot(ax, p[k:], HAND_COLOUR[b])
            _panel(ax, f"code_switch {a}→{b}" if c == 0 else "")
    # translate: Matisse strokes with the most segments
    gm = grammars["matisse"]
    cands = []
    for d in drawings["matisse"]:
        Rd, fitted = fit_drawing(d, sigma_frac=SIGMA_FRAC)
        for st, f, toks in fitted:
            nseg = sum(1 for t in toks if t[0] != "corner")
            if nseg >= 4 and st.length() / Rd > 0.15:
                cands.append((nseg, st.length() / Rd, f, Rd))
    cands.sort(key=lambda x: (-x[0], -x[1]))
    pick = [cands[i] for i in rng.choice(min(len(cands), 30), 4, replace=False)] if cands else []  # rows 3–4
    for i, (_n, _l, f, Rd) in enumerate(pick):
        r, c0 = 3 + i // 2, 3 * (i % 2)
        orig, _, _ = tokens_to_points(fit_tokens(f, Rd), Rd)   # the fit, re-integrated
        _plot(axs[r, c0], orig, HAND_COLOUR["matisse"])
        _panel(axs[r, c0], "Matisse stroke (fit)" if i < 2 else "")
        for j, b in enumerate(("hokusai", "ingres")):
            tr = translate(f, gm, grammars[b], ref_length=Rd)
            _plot(axs[r, c0 + 1 + j], tr.points, HAND_COLOUR[b])
            _panel(axs[r, c0 + 1 + j], f"translate → {b}" if i < 2 else "")
    # restyle: the longest Matisse stroke of the cleanest drawing, and a circle
    d0 = sorted(drawings["matisse"], key=clean_score, reverse=True)[0]
    longest = max(d0.strokes, key=lambda s: s.length())
    t = np.linspace(0, 1.8 * np.pi, 900)
    circle = np.column_stack([400 * np.cos(t), 400 * np.sin(t)])
    for j, (path, Rp, name) in enumerate(((longest.points, d0.ref_length(), "Matisse stroke"),
                                          (circle, 2000.0, "circle"))):
        for k, h in enumerate(("matisse", "hokusai", "ingres")):
            ax = axs[5, 3 * j + k]
            _plot(ax, path, "#CECDC3", lw=3)
            rs = restyle(path, grammars[h], rng, ref_length=Rp, step=1.0)
            _plot(ax, rs.points, HAND_COLOUR[h], lw=1.2)
            _panel(ax, f"restyle {name} in {h}")
    fig.suptitle("juxtaposition — colour = hand (Matisse red, Hokusai blue, Ingres green)",
                 fontsize=14)
    fig.tight_layout()
    fig.savefig(OUT / "juxtaposition.png", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------------

def grammar_summary(g) -> dict:
    P = np.array(g.transition())
    C = np.array(g.counts)
    toks = [t for s in g.strokes for t in s]
    segs = [t for t in toks if t[0] != "corner"]
    nseg = [sum(1 for t in s if t[0] != "corner") for s in g.strokes]
    per_kind = {}
    for k in ("line", "arc", "clothoid"):
        v = [t for t in segs if t[0] == k]
        if v:
            per_kind[k] = {
                "n": len(v),
                "median_length": float(np.median([t[1] for t in v])),
                "median_abs_kappaR": float(np.median([0.5 * (abs(t[2]) + abs(t[3])) for t in v])),
            }
    corners = [abs(t[1]) for t in toks if t[0] == "corner"]
    return {
        "n_strokes": len(g.strokes),
        "segment_counts": g.segment_counts(),
        "segments_per_stroke": {"mean": float(np.mean(nseg)),
                                "share_single": float(np.mean(np.array(nseg) == 1)),
                                "max": int(max(nseg))},
        "per_kind": per_kind,
        "corner_abs_angle_deg_median": float(np.degrees(np.median(corners))) if corners else None,
        "stroke_length_quantiles": [float(q) for q in np.quantile(g.stroke_lengths, [0.1, 0.5, 0.9, 0.99])],
        "strokes_per_drawing_median": float(np.median(g.strokes_per_drawing)),
        "transition_rows": list(FROM), "transition_cols": list(TO),
        "transition_matrix": np.round(P, 4).tolist(),
        "transition_counts": C.tolist(),
        "short_sigma_strokes": g.meta.get("short_sigma"),
    }


def memorisation(artist, drawings, rng, n_gen=600):
    held = drawings[::5]
    train = [d for i, d in enumerate(drawings) if i % 5]
    g = learn(train, sigma_frac=SIGMA_FRAC, name=artist)
    real = []
    for d in held:
        _R, fitted = fit_drawing(d, sigma_frac=SIGMA_FRAC)
        real += [t for _s, _f, t in fitted]
    L = np.array(g.stroke_lengths)
    gen_free = [generate_tokens(g, rng)[0] for _ in range(n_gen)]
    gen_cond = [generate_tokens(g, rng, length=float(rng.choice(L, p=L / L.sum())))[0]
                for _ in range(n_gen)]
    # length-conditioned generation draws strokes ∝ length: compare it with
    # held-out real strokes drawn the same way
    Lr = np.array([sum(x[1] for x in t if x[0] != "corner") for t in real])
    real_w = [real[i] for i in rng.choice(len(real), n_gen, p=Lr / Lr.sum())]
    res = {}
    for mode, gen, rr in (("free", gen_free, real), ("length_conditioned", gen_cond, real_w)):
        gen = [t for t in gen if t]
        res[mode] = _mem_stats(gen, nearest_training_distance(gen, g), rr,
                               nearest_training_distance(rr, g))
    return res


def _mem_stats(gen, dg, real, dr):

    def length(t):
        return sum(x[1] for x in t if x[0] != "corner")

    def nseg(t):
        return sum(1 for x in t if x[0] != "corner")

    out = {}
    for name, sel in (("all", lambda t: True),
                      ("multi_segment", lambda t: nseg(t) >= 2),
                      ("long_ge_0.05R", lambda t: length(t) >= 0.05)):
        mg = np.array([sel(t) for t in gen])
        mr = np.array([sel(t) for t in real])
        a, b = dg[mg], dr[mr]
        if len(a) == 0 or len(b) == 0:
            continue
        out[name] = {
            "n_generated": int(len(a)), "n_heldout_real": int(len(b)),
            "gen_quantiles_10_50_90": [float(q) for q in np.quantile(a, [0.1, 0.5, 0.9])],
            "real_quantiles_10_50_90": [float(q) for q in np.quantile(b, [0.1, 0.5, 0.9])],
            "gen_share_below_real_p10": float(np.mean(a < np.quantile(b, 0.1))),
            "real_share_below_real_p10": 0.1,
        }
    return out


def panel_compare(artist, real_drawings, gen_drawings):
    def feats(ds):
        rows = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for d in ds:
                rows.append(panel.features(d, width_available=False))
        return rows
    fr, fg = feats(real_drawings), feats(gen_drawings)
    names = sorted(set(fr[0]) & set(fg[0]))
    res = []
    for n in names:
        r = np.array([f.get(n, np.nan) for f in fr], dtype=float)
        gv = np.array([f.get(n, np.nan) for f in fg], dtype=float)
        r, gv = r[np.isfinite(r)], gv[np.isfinite(gv)]
        if len(r) < 3 or len(gv) < 3:
            continue
        sd = np.std(r, ddof=1)
        if sd <= 1e-12:
            continue
        res.append((n, float((gv.mean() - r.mean()) / sd), float(r.mean()), float(gv.mean())))
    res.sort(key=lambda x: -abs(x[1]))
    groups = {}
    for n, smd, *_ in res:
        groups.setdefault(panel.group_of(n), []).append(abs(smd))
    return {
        "n_features": len(res),
        "share_abs_smd_lt_0.5": float(np.mean([abs(x[1]) < 0.5 for x in res])),
        "group_median_abs_smd": {k: float(np.median(v)) for k, v in sorted(groups.items())},
        "top_off": [{"feature": n, "smd": round(s, 2), "real": rm, "gen": gm}
                    for n, s, rm, gm in res[:10]],
        "best_match": [{"feature": n, "smd": round(s, 2)} for n, s, _r, _g in res[::-1][:10]],
    }


def write_markdown(summary):
    L = ["# Grammar demo — clothoid-alphabet hands (stage 3 prototype)", "",
         f"σ = {SIGMA_FRAC}·ref; strokes ≥ 8 line widths, fit rms_position_error ≤ 1σ; "
         "reversal-augmented chain; k-NN transition resampling.", ""]
    for a in ARTISTS:
        s = summary["grammars"][a]
        L += [f"## {a}", "",
              f"- usable strokes {s['n_strokes']}, segments {s['segment_counts']}",
              f"- segments/stroke mean {s['segments_per_stroke']['mean']:.2f}, "
              f"single-segment share {s['segments_per_stroke']['share_single']:.2f}",
              f"- stroke length /R quantiles (10/50/90/99 %): "
              + ", ".join(f"{q:.3f}" for q in s["stroke_length_quantiles"]),
              f"- per kind: " + "; ".join(f"{k} n={v['n']} med l={v['median_length']:.4f} "
                                          f"med |κR|={v['median_abs_kappaR']:.1f}"
                                          for k, v in s["per_kind"].items()),
              f"- median |corner| {s['corner_abs_angle_deg_median']}°", "",
              "| from \\ to | " + " | ".join(TO) + " |",
              "|---|" + "---|" * len(TO)]
        for i, f in enumerate(FROM):
            L.append(f"| {f} | " + " | ".join(f"{v:.2f}" for v in s["transition_matrix"][i]) + " |")
        L += ["", "Memorisation (turning-signature NN distance to training; held-out real vs generated):", ""]
        for mode, m in summary["memorisation"][a].items():
          for k, v in m.items():
            L.append(f"- {mode} / {k}: gen median {v['gen_quantiles_10_50_90'][1]:.3f} "
                     f"(p10 {v['gen_quantiles_10_50_90'][0]:.3f}) vs real median "
                     f"{v['real_quantiles_10_50_90'][1]:.3f} (p10 {v['real_quantiles_10_50_90'][0]:.3f}); "
                     f"gen share below real p10 = {v['gen_share_below_real_p10']:.2f} (real: 0.10)")
        p = summary["panel"][a]
        L += ["", f"Panel (geometry only): {p['n_features']} features, share |SMD|<0.5 = "
                  f"{p['share_abs_smd_lt_0.5']:.2f}", "",
              "Group median |SMD|: " + ", ".join(f"{k} {v:.2f}" for k, v in p["group_median_abs_smd"].items()),
              "", "Top mismatches: " + ", ".join(f"{x['feature']} ({x['smd']:+.1f})" for x in p["top_off"][:8]),
              "", "Best matches: " + ", ".join(f"{x['feature']} ({x['smd']:+.2f})" for x in p["best_match"][:8]),
              ""]
    (OUT / "summary.md").write_text("\n".join(L))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rng = np.random.default_rng(20261016)
    drawings = {a: load(a) for a in ARTISTS}
    grammars = {}
    for a in ARTISTS:
        g = learn(drawings[a], sigma_frac=SIGMA_FRAC, name=a)
        g.save(OUT / f"grammar_{a}.json")
        grammars[a] = g
        print(f"[{time.time() - t0:5.1f}s] learned {a}: {g.meta['n_strokes']} strokes")
    gen = contact_sheet(grammars, drawings, rng)
    contact_sheet(grammars, drawings, rng, budget="count", tag="_counts")
    print(f"[{time.time() - t0:5.1f}s] contact sheet")
    juxtaposition_sheet(grammars, drawings, rng)
    print(f"[{time.time() - t0:5.1f}s] juxtaposition sheet")
    summary = {"sigma_frac": SIGMA_FRAC, "grammars": {}, "memorisation": {}, "panel": {}}
    for a in ARTISTS:
        summary["grammars"][a] = grammar_summary(grammars[a])
        summary["memorisation"][a] = memorisation(a, drawings[a], rng)
        print(f"[{time.time() - t0:5.1f}s] memorisation {a}")
        extra = [generate_drawing(grammars[a], rng, (CANVAS, CANVAS), max_strokes=400,
                                  clearance=4.0) for _ in range(8)]
        summary["panel"][a] = panel_compare(a, drawings[a], gen[a] + extra)
        print(f"[{time.time() - t0:5.1f}s] panel {a}")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    write_markdown(summary)
    print(f"[{time.time() - t0:5.1f}s] done → {OUT}")


if __name__ == "__main__":
    main()

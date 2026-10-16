"""Medium-invariance study: can the panel separate artists once it stops
separating media?

Control: Matisse etchings vs Matisse lithographs (same hand, different
medium) should NOT separate. Target: Matisse vs Hokusai vs Ingres should.

Two remedies, crossed:
  * scale  — measure at σ = max(0.01·ref, k·w) for k in --floors: crayon grain
             and etching bite live at a few line widths; a coarser σ stops
             seeing them.
  * drop   — remove features whose univariate etching-vs-litho AUC is far
             from 0.5 (|AUC − 0.5| > t). Selection uses medium labels only,
             never artist labels, so the artist test is not biased by it. The
             medium control IS biased by selecting on itself, so it is also
             reported held-out: select on a random half of the Matisse
             sheets, score on the other half, repeated.

  cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.medium_invariance
Writes .local/gesture/out/medium_invariance/report.{md,json}.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from experiments import discriminate as D  # noqa: E402
from gesture import panel  # noqa: E402

REPO = HERE.parents[2]
OUT = REPO / ".local/gesture/out/medium_invariance"
SPLIT = REPO / ".local/gesture/out/medium_split"       # etching/ litho/ other/ (symlinks)
HYB = REPO / ".local/gesture/out/extract_hybrid"


def load():
    items = []   # (artist, medium, key, drawing)
    for med in ("etching", "litho", "other"):
        for k, d in D.load_dir(SPLIT / med):
            items.append(("matisse", med, f"matisse/{k}", d))
    for art, med in (("hokusai", "brush"), ("ingres", "graphite")):
        for k, d in D.load_dir(HYB / art):
            items.append((art, med, f"{art}/{k}", d))
    return items


def matrix(items, floor, jobs):
    args = [(key, d, 0.01, True, floor) for _, _, key, d in items]
    with ProcessPoolExecutor(jobs) as ex:
        res = list(ex.map(D._feat_job, args, chunksize=4))
    feats = [r[1] for r in res]
    keys = sorted(k for k in set().union(*feats)
                  if all(k in f for f in feats) and panel.group_of(k) not in panel.WIDTH_GROUPS)
    X = np.array([[f[k] for k in keys] for f in feats], dtype=np.float64)
    ok = ~np.all(np.isnan(X), axis=0)
    return X[:, ok], [k for k, o in zip(keys, ok) if o]


def medium_auc(X, y):
    """Per-feature |AUC − 0.5| for binary y (NaN-aware)."""
    from sklearn.metrics import roc_auc_score
    out = np.zeros(X.shape[1])
    for j in range(X.shape[1]):
        m = ~np.isnan(X[:, j])
        if m.sum() >= 6 and len(set(y[m])) == 2:
            out[j] = abs(roc_auc_score(y[m], X[m, j]) - 0.5)
    return out


def heldout_medium(X, y, t, reps, seed):
    """Select on half the sheets, fit logreg on that half, AUC on the other."""
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedShuffleSplit
    mk = D._models(seed)["logreg"]
    aucs = []
    for tr, te in StratifiedShuffleSplit(reps, test_size=0.5, random_state=seed).split(X, y):
        keep = medium_auc(X[tr], y[tr]) <= t if t is not None else np.ones(X.shape[1], bool)
        if keep.sum() == 0:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            p = mk().fit(X[tr][:, keep], y[tr]).predict_proba(X[te][:, keep])[:, 1]
        aucs.append(roc_auc_score(y[te], p))
    return float(np.mean(aucs)), float(np.std(aucs))


def _prep(X):
    """Median-impute and standardise (statistics over all drawings)."""
    X = X.copy()
    med = np.nanmedian(X, axis=0)
    idx = np.where(np.isnan(X))
    X[idx] = np.take(med, idx[1])
    sd = X.std(axis=0)
    return (X - X.mean(axis=0)) / np.where(sd > 0, sd, 1.0)


def inlp(Z, fit_rows, y, n, seed):
    """Iterative nullspace projection: n times, fit a linear etching-vs-litho
    classifier on `fit_rows` and project its direction out of ALL rows.
    Uses medium labels only."""
    from sklearn.linear_model import LogisticRegression
    Z = Z.copy()
    for _ in range(n):
        w = LogisticRegression(C=0.5, max_iter=5000, random_state=seed).fit(Z[fit_rows], y).coef_[0]
        nw = np.linalg.norm(w)
        if nw < 1e-12:
            break
        w = w / nw
        Z = Z - np.outer(Z @ w, w)
    return Z


def heldout_inlp(Z, y, n, reps, seed):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedShuffleSplit
    aucs = []
    for tr, te in StratifiedShuffleSplit(reps, test_size=0.5, random_state=seed).split(Z, y):
        P = inlp(Z, tr, y[tr], n, seed)
        p = LogisticRegression(C=0.5, max_iter=5000).fit(P[tr], y[tr]).predict_proba(P[te])[:, 1]
        aucs.append(roc_auc_score(y[te], p))
    return float(np.mean(aucs)), float(np.std(aucs))


def project_rows(items, floors, iters, a):
    """Strategy 3: INLP at each σ floor."""
    art = np.array([i[0] for i in items])
    med = np.array([i[1] for i in items])
    G = np.array([i[2] for i in items])
    em = np.isin(med, ["etching", "litho"])
    ym = (med[em] == "litho").astype(int)
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    models = {"logreg": lambda: LogisticRegression(max_iter=5000, class_weight="balanced"),
              "forest": lambda: RandomForestClassifier(n_estimators=200, random_state=a.seed,
                                                       class_weight="balanced")}
    rows = []
    for floor in floors:
        X, names = matrix(items, floor, a.jobs)
        Z = _prep(X)
        Zm = Z[em]
        for n in iters:
            # Directions are fitted on the Matisse etching/litho rows only (medium
            # labels, never artist labels) and projected out of every row.
            P = inlp(Z, np.flatnonzero(em), ym, n, a.seed)
            r = {"floor_w": floor, "inlp": n, "n_feat": len(names)}
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r["artists"] = {mn: D.cv_score(mk, P, art, 5, a.repeats, a.seed, a.jobs, G)
                                for mn, mk in models.items()}
                r["pairs"] = {f"{p} vs {q}": {mn: D.pair_auc(mk, P, art, p, q, a.repeats, a.seed, G)["auc"]
                                              for mn, mk in models.items()}
                              for p, q in (("matisse", "hokusai"), ("matisse", "ingres"), ("hokusai", "ingres"))}
            r["medium_heldout"] = heldout_inlp(Zm, ym, n, a.reps, a.seed)
            rows.append(r)
            print(f"floor {floor:>4} INLP {n} | artists {r['artists']['logreg']['bacc']:.3f}/"
                  f"{r['artists']['forest']['bacc']:.3f} | medium held-out {r['medium_heldout'][0]:.3f}",
                  flush=True)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--floors", type=float, nargs="+", default=[0, 7, 12, 20])
    ap.add_argument("--drops", type=float, nargs="+", default=[0.25, 0.20, 0.15, 0.10])
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--inlp", type=int, nargs="*", default=None,
                    help="run strategy 3 (nullspace projection) with these iteration counts instead")
    a = ap.parse_args(argv)
    items = load()
    if a.inlp is not None:
        rows = project_rows(items, a.floors, a.inlp, a)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "report_inlp.json").write_text(json.dumps(rows, indent=1))
        f2 = lambda d: f"{d['logreg']:.2f}/{d['forest']:.2f}"  # noqa: E731
        L = ["# Medium invariance — nullspace projection (INLP)", "",
             "Etching-vs-litho directions fitted on Matisse sheets (medium labels only) and projected "
             "out of every drawing's standardised geometry features. Held-out: projection and probe "
             "fitted on half the Matisse sheets, scored on the other half.", "",
             "| # | σ floor (w) | INLP iters | artists bacc logreg / forest (chance .333) | M–H AUC | M–I AUC "
             "| H–I AUC | medium AUC held-out (want ≈ .5) |", "|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(rows, 1):
            pr = r["pairs"]
            L.append(f"| {i} | {r['floor_w']:g} | {r['inlp']} | {r['artists']['logreg']['bacc']:.3f} / "
                     f"{r['artists']['forest']['bacc']:.3f} | {f2(pr['matisse vs hokusai'])} | "
                     f"{f2(pr['matisse vs ingres'])} | {f2(pr['hokusai vs ingres'])} | "
                     f"{r['medium_heldout'][0]:.2f} ± {r['medium_heldout'][1]:.2f} |")
        (OUT / "report_inlp.md").write_text("\n".join(L) + "\n")
        print("\n".join(L))
        return
    art = np.array([i[0] for i in items])
    med = np.array([i[1] for i in items])
    G = np.array([i[2] for i in items])
    em = np.isin(med, ["etching", "litho"])
    ym = (med[em] == "litho").astype(int)
    models = D._models(a.seed)
    rows = []
    for floor in a.floors:
        X, names = matrix(items, floor, a.jobs)
        mauc = medium_auc(X[em], ym)
        for t in [None] + a.drops:
            keep = np.ones(len(names), bool) if t is None else mauc <= t
            Xk = X[:, keep]
            r = {"floor_w": floor, "drop_t": t, "n_feat": int(keep.sum()),
                 "dropped": [n for n, k in zip(names, keep) if not k]}
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r["artists"] = {mn: D.cv_score(mk, Xk, art, 5, a.repeats, a.seed, a.jobs, G)
                                for mn, mk in models.items()}
                r["pairs"] = {f"{p} vs {q}": {mn: D.pair_auc(mk, Xk, art, p, q, a.repeats, a.seed, G)["auc"]
                                              for mn, mk in models.items()}
                              for p, q in (("matisse", "hokusai"), ("matisse", "ingres"), ("hokusai", "ingres"))}
                r["medium_insample"] = {mn: D.pair_auc(mk, Xk[em], med[em], "etching", "litho",
                                                       a.repeats, a.seed, G[em])["auc"]
                                        for mn, mk in models.items()}
            r["medium_heldout"] = heldout_medium(X[em], ym, t, a.reps, a.seed)
            rows.append(r)
            print(f"floor {floor:>4} drop {t} feats {r['n_feat']:2d} | artists "
                  f"{r['artists']['logreg']['bacc']:.3f}/{r['artists']['forest']['bacc']:.3f} | "
                  f"medium held-out {r['medium_heldout'][0]:.3f}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(rows, indent=1))
    L = ["# Medium invariance — artists vs Matisse etching/litho control", "",
         f"Matisse {int((art == 'matisse').sum())} (etching {int((med == 'etching').sum())}, "
         f"litho {int((med == 'litho').sum())}, other {int((med == 'other').sum())}), "
         f"Hokusai {int((art == 'hokusai').sum())}, Ingres {int((art == 'ingres').sum())}. "
         "Geometry only (no w_, end_). Grouped CV. σ = max(0.01·ref, floor·w).", "",
         "| # | σ floor (w) | drop if \\|AUC−.5\\| > | n feat | artists bacc logreg / forest (chance .333) "
         "| M–H AUC | M–I AUC | H–I AUC | medium AUC held-out (want ≈ .5) | medium AUC in-sample |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        pr = r["pairs"]
        f2 = lambda d: f"{d['logreg']:.2f}/{d['forest']:.2f}"  # noqa: E731
        L.append(f"| {i} | {r['floor_w']:g} | {'—' if r['drop_t'] is None else r['drop_t']} | {r['n_feat']} | "
                 f"{r['artists']['logreg']['bacc']:.3f} / {r['artists']['forest']['bacc']:.3f} | "
                 f"{f2(pr['matisse vs hokusai'])} | {f2(pr['matisse vs ingres'])} | {f2(pr['hokusai vs ingres'])} | "
                 f"{r['medium_heldout'][0]:.2f} ± {r['medium_heldout'][1]:.2f} | {f2(r['medium_insample'])} |")
    (OUT / "report.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()

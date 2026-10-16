"""Stage-2 discrimination experiment: does the panel tell hands apart, and
does it tell a hand apart from its own null drawings (the Pollock test)?

  cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.discriminate \\
      --name matisse-vs-nulls \\
      --group matisse=../../.local/gesture/out/extract/matisse \\
      --group hokusai=../../.local/gesture/out/extract/hokusai \\
      --null-source matisse

Each --group NAME=DIR loads every Drawing JSON in DIR (non-Drawing JSON is
skipped with a warning). --null-source NAME adds, for every drawing of that
group, one drawing per null in gesture.nulls.NULLS (seeded) as classes
`null_<kind>`. Classes with < 3 drawings are warned about and left out.

Analyses (stratified k-fold, k = min(5, smallest class), repeated):
  1. multi-class per-drawing classification — standardise + logistic
     regression, and a random forest: balanced accuracy ± std, confusion
  2. pairwise binary separations (AUC), source vs each null highlighted
  3. group ablation (drop one group / that group alone) and "geometry only"
     (every group except w_ and end_), incl. geometry-only source-vs-null AUC
  4. permutation importance (random forest, on held-out folds), top 15
  5. PCA + LDA scatter (scatter.png)
Writes report.json, report.md, features.csv, scatter.png to
.local/gesture/out/discriminate/<name>/ and prints the markdown.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import warnings
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # `gesture` importable from anywhere

from gesture import nulls, panel  # noqa: E402
from gesture.core import Drawing  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / ".local/gesture/out/discriminate"
MIN_CLASS = 3

# Flexoki accents (600 on paper), from twistermapper/web/flexoki.css
FLEXOKI = {"paper": "#FFFCF0", "tx": "#100F0F", "ui": "#CECDC3", "muted": "#6F6E69"}
ACCENTS = ["#205EA6", "#AF3029", "#66800B", "#BC5215", "#5E409D", "#24837B", "#A02F6F", "#AD8301"]


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

def load_dir(path: Path) -> list[tuple[str, Drawing]]:
    out = []
    for p in sorted(path.glob("*.json")):
        try:
            d = Drawing.load(p)
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"skip {p.name}: not a Drawing ({type(e).__name__})")
            continue
        if not d.strokes:
            warnings.warn(f"skip {p.name}: no strokes")
            continue
        out.append((p.stem, d))
    return out


def _feat_job(args):
    key, d, sigma_frac, width, sigma_min_w = args
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        t = time.perf_counter()
        f, info = panel.features_with_info(d, sigma_frac=sigma_frac, width_available=width,
                                           sigma_min_w=sigma_min_w)
        info["seconds"] = time.perf_counter() - t
    return key, f, info


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

def _models(seed: int):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return {
        "logreg": lambda: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                        LogisticRegression(max_iter=5000, class_weight="balanced")),
        "forest": lambda: make_pipeline(SimpleImputer(strategy="median"),
                                        RandomForestClassifier(n_estimators=200, random_state=seed,
                                                               class_weight="balanced")),
    }


def cv_score(make, X, y, k, repeats, seed, jobs, groups=None) -> dict:
    """Grouped CV: a source drawing and the nulls built from it share a group,
    so they never straddle train and test."""
    from sklearn.model_selection import StratifiedGroupKFold, cross_validate
    g = groups if groups is not None else np.arange(len(y))
    s = []
    for r in range(repeats):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = cross_validate(make(), X, y, groups=g, scoring="balanced_accuracy", n_jobs=jobs,
                                 cv=StratifiedGroupKFold(k, shuffle=True, random_state=seed + r))
        s.extend(res["test_score"])
    s = np.asarray(s)
    return {"bacc": float(s.mean()), "std": float(s.std())}


def confusion(make, X, y, labels, k, seed, groups=None) -> list[list[int]]:
    from sklearn.metrics import confusion_matrix
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
    g = groups if groups is not None else np.arange(len(y))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = cross_val_predict(make(), X, y, groups=g,
                              cv=StratifiedGroupKFold(k, shuffle=True, random_state=seed))
    return confusion_matrix(y, p, labels=labels).tolist()


def pair_auc(make, X, y, a, b, repeats, seed, groups=None) -> dict:
    from sklearn.metrics import balanced_accuracy_score, roc_auc_score
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
    m = (y == a) | (y == b)
    Xp, yp = X[m], (y[m] == b).astype(int)
    gp = (groups if groups is not None else np.arange(len(y)))[m]
    k = int(min(5, np.bincount(yp).min()))
    aucs, baccs = [], []
    for r in range(repeats):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pr = cross_val_predict(make(), Xp, yp, method="predict_proba", groups=gp,
                                   cv=StratifiedGroupKFold(k, shuffle=True, random_state=seed + r))[:, 1]
        aucs.append(roc_auc_score(yp, pr))
        baccs.append(balanced_accuracy_score(yp, pr > 0.5))
    return {"auc": float(np.mean(aucs)), "auc_std": float(np.std(aucs)), "bacc": float(np.mean(baccs))}


def effect_sizes(X, y, names, a, b, top=5) -> list[dict]:
    """Largest |Cohen's d| features between classes a and b (NaN-aware)."""
    A, B = X[y == a], X[y == b]
    out = []
    for i, n in enumerate(names):
        u, v = A[:, i][~np.isnan(A[:, i])], B[:, i][~np.isnan(B[:, i])]
        if len(u) < 2 or len(v) < 2:
            continue
        sd = np.sqrt(0.5 * (u.var(ddof=1) + v.var(ddof=1)))
        diff = v.mean() - u.mean()
        d = diff / sd if sd > 0 else (0.0 if diff == 0 else np.sign(diff) * 99.0)
        d = float(np.clip(d, -99.0, 99.0))      # ±99 = no overlap with zero spread
        out.append({"feature": n, "d": float(d), "a": float(np.median(u)), "b": float(np.median(v))})
    out.sort(key=lambda r: -abs(r["d"]))
    return out[:top]


def perm_importance(make, X, y, names, k, seed, top=15, groups=None) -> list[dict]:
    from sklearn.inspection import permutation_importance
    from sklearn.model_selection import StratifiedGroupKFold
    imps = []
    g = groups if groups is not None else np.arange(len(y))
    for tr, te in StratifiedGroupKFold(k, shuffle=True, random_state=seed).split(X, y, g):
        mdl = make().fit(X[tr], y[tr])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = permutation_importance(mdl, X[te], y[te], scoring="balanced_accuracy",
                                       n_repeats=10, random_state=seed)
        imps.append(r.importances_mean)
    imps = np.array(imps)
    mean, std = imps.mean(axis=0), imps.std(axis=0)
    order = np.argsort(-mean)[:top]
    return [{"feature": names[i], "importance": float(mean[i]), "std": float(std[i])} for i in order]


# ---------------------------------------------------------------------------
# plot
# ---------------------------------------------------------------------------

def scatter(X, y, labels, path: Path, seed: int) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.decomposition import PCA
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler

    Z = StandardScaler().fit_transform(SimpleImputer(strategy="median").fit_transform(X))
    pca = PCA(n_components=2, random_state=seed).fit(Z)
    P = pca.transform(Z)
    nc = min(2, len(labels) - 1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        L = LinearDiscriminantAnalysis(n_components=nc, solver="eigen", shrinkage="auto").fit_transform(Z, y)
    if L.shape[1] == 1:
        L = np.column_stack([L[:, 0], np.random.default_rng(seed).uniform(-0.3, 0.3, len(L))])
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), facecolor=FLEXOKI["paper"])
    titles = [f"PCA (var {pca.explained_variance_ratio_[0]:.0%} + {pca.explained_variance_ratio_[1]:.0%})",
              "shrinkage LDA (in-sample: structure, not accuracy)"]
    for ax, Y, t in zip(axes, (P, L), titles):
        ax.set_facecolor(FLEXOKI["paper"])
        for i, lab in enumerate(labels):
            m = y == lab
            ax.scatter(Y[m, 0], Y[m, 1], s=22, alpha=0.85, color=ACCENTS[i % len(ACCENTS)],
                       label=f"{lab} ({m.sum()})", edgecolors="none")
        ax.set_title(t, color=FLEXOKI["tx"], fontsize=11)
        ax.tick_params(colors=FLEXOKI["muted"], labelsize=8)
        for sp in ax.spines.values():
            sp.set_color(FLEXOKI["ui"])
    axes[0].legend(fontsize=8, frameon=False, labelcolor=FLEXOKI["tx"])
    fig.tight_layout()
    fig.savefig(path, dpi=120, facecolor=FLEXOKI["paper"])
    plt.close(fig)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _auc(g, m):
    return f"{g[m]['auc']:.3f}" if m in g else "—"


def _fmt(r):
    return f"{r['bacc']:.3f} ± {r['std']:.3f}"


def markdown(rep: dict) -> str:
    L = [f"# Discrimination — {rep['name']}", ""]
    c = rep["config"]
    L.append(f"σ = {c['sigma_frac']}·ref · k = {c['k']}-fold × {c['repeats']} repeats · "
             f"seed {c['seed']} · {rep['n_features']} features in groups {', '.join(rep['groups'])} · "
             f"clothoid group: {rep['clothoid_status']} · panel {rep['panel_seconds_mean']:.2f} s/drawing")
    L.append("")
    L.append("Classes: " + ", ".join(f"{k} ({v})" for k, v in rep["classes"].items()))
    if rep["skipped_classes"]:
        L.append(f"Skipped (< {MIN_CLASS} drawings): " + ", ".join(f"{k} ({v})" for k, v in rep["skipped_classes"].items()))
    if rep["dropped_columns"]:
        L.append(f"Dropped columns (missing in some drawings or all-NaN): {len(rep['dropped_columns'])} — "
                 + ", ".join(rep["dropped_columns"][:12]) + (" …" if len(rep["dropped_columns"]) > 12 else ""))
    chance = 1.0 / len(rep["classes"])
    L += ["", f"## 1. Multi-class balanced accuracy (chance {chance:.3f})", "",
          "| # | model | all features | geometry only (no w_, end_) |", "|---|---|---|---|"]
    for i, m in enumerate(rep["multiclass"], 1):
        L.append(f"| {i} | {m} | {_fmt(rep['multiclass'][m])} | {_fmt(rep['geometry_only']['multiclass'][m])} |")
    labs = rep["labels"]
    for m, cm in rep["confusion"].items():
        L += ["", f"Confusion ({m}, rows = true, cols = predicted):", "",
              "| true \\ pred | " + " | ".join(labs) + " |", "|---" * (len(labs) + 1) + "|"]
        for lab, row in zip(labs, cm):
            L.append(f"| {lab} | " + " | ".join(str(v) for v in row) + " |")
    L += ["", "## 2. Pairwise separations (AUC, mean over repeats)", ""]
    src = rep["config"].get("null_source")
    L += ["| # | pair | logreg AUC | forest AUC | geometry-only logreg | geometry-only forest |",
          "|---|---|---|---|---|---|"]
    rows = sorted(rep["pairwise"].items(), key=lambda kv: (0 if src and kv[0].startswith(src + " vs null_") else 1, kv[0]))
    for i, (pair, r) in enumerate(rows, 1):
        g = rep["geometry_only"]["pairwise"].get(pair, {})
        mark = " **(Pollock)**" if src and pair.startswith(src + " vs null_") else ""
        L.append(f"| {i} | {pair}{mark} | {r['logreg']['auc']:.3f} | {r['forest']['auc']:.3f} | "
                 f"{_auc(g, 'logreg')} | {_auc(g, 'forest')} |")
    fair = rep.get("pollock_fair", {}).get("pairwise", {})
    if fair:
        L += ["", "Fair Pollock test (excludes " + ", ".join(rep["pollock_fair"]["excluded"])
              + " — nulls are open and independently placed by construction):", "",
              "| # | pair | logreg AUC | forest AUC |", "|---|---|---|---|"]
        for i, (pair, r) in enumerate(sorted(fair.items()), 1):
            L.append(f"| {i} | {pair} | {r['logreg']['auc']:.3f} | {r['forest']['auc']:.3f} |")
    pm = rep.get("pollock_matched", {})
    if pm:
        L += ["", "**Pipeline-matched Pollock test** (each null vs the identity control, fair feature set) — "
              "the gate number:", "", "| # | pair | logreg AUC | forest AUC |", "|---|---|---|---|"]
        for i, (pair, r) in enumerate(sorted(pm.items()), 1):
            L.append(f"| {i} | {pair} | {r['logreg']['auc']:.3f} | {r['forest']['auc']:.3f} |")
    ao = rep.get("artists_only")
    if ao:
        L += ["", f"**Artists only, geometry only** ({', '.join(ao['classes'])}; chance {ao['chance']:.3f}): "
              + "; ".join(f"{m} {_fmt(r)}" for m, r in ao["geometry_only"].items())]
    if rep.get("effects"):
        L += ["", "Top separating features per pair with the source (Cohen's d, b − a; medians a → b):", ""]
        for pair, rows in rep["effects"].items():
            L.append(f"- **{pair}**: " + "; ".join(
                f"`{r['feature']}` d={r['d']:+.1f} ({r['a']:.3g} → {r['b']:.3g})" for r in rows))
    L += ["", "## 3. Group ablation (multi-class balanced accuracy)", "",
          "| # | group | n feat | drop: logreg Δ | drop: forest Δ | alone: logreg | alone: forest |",
          "|---|---|---|---|---|---|---|"]
    for i, (g, r) in enumerate(rep["ablation"].items(), 1):
        L.append(f"| {i} | {g}_ | {r['n']} | {r['drop']['logreg']['bacc'] - rep['multiclass']['logreg']['bacc']:+.3f} | "
                 f"{r['drop']['forest']['bacc'] - rep['multiclass']['forest']['bacc']:+.3f} | "
                 f"{r['alone']['logreg']['bacc']:.3f} | {r['alone']['forest']['bacc']:.3f} |")
    L += ["", "## 4. Permutation importance (forest, held-out folds; correlated features share credit)", "",
          "| # | feature | Δ balanced acc | std |", "|---|---|---|---|"]
    for i, r in enumerate(rep["importance"], 1):
        L.append(f"| {i} | `{r['feature']}` | {r['importance']:.3f} | {r['std']:.3f} |")
    L += ["", f"## 5. Scatter", "", f"`{rep['scatter']}`", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--group", action="append", default=[], metavar="NAME=DIR", required=True)
    ap.add_argument("--null-source", default=None, metavar="NAME")
    ap.add_argument("--nulls", nargs="*", default=None, help=f"subset of {list(nulls.NULLS)}")
    ap.add_argument("--name", default=None, help="run name (output folder)")
    ap.add_argument("--sigma-frac", type=float, default=0.01)
    ap.add_argument("--sigma-min-w", type=float, default=0.0,
                    help="floor σ at this many median line widths (σ/w confound control)")
    ap.add_argument("--no-width", action="store_true", help="compute the panel without w_/end_")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    t0 = time.perf_counter()

    # ---- load
    items: list[tuple[str, str, Drawing]] = []   # (class, key, drawing)
    groups = {}
    for g in a.group:
        name, _, d = g.partition("=")
        if not d:
            ap.error(f"--group needs NAME=DIR, got {g!r}")
        loaded = load_dir(Path(d))
        groups[name] = loaded
        items += [(name, f"{name}/{k}", dr) for k, dr in loaded]
    if a.null_source:
        if a.null_source not in groups:
            ap.error(f"--null-source {a.null_source!r} is not a --group")
        kinds = a.nulls if a.nulls is not None else list(nulls.NULLS)
        for ki, kind in enumerate(kinds):
            fn = nulls.NULLS[kind]
            for di, (k, dr) in enumerate(groups[a.null_source]):
                nd = fn(dr, np.random.default_rng([a.seed, ki, di]))
                items.append((f"null_{kind}", f"null_{kind}/{k}", nd))

    # ---- features
    jobs = [(key, dr, a.sigma_frac, not a.no_width, a.sigma_min_w) for _, key, dr in items]
    t1 = time.perf_counter()
    if a.jobs > 1 and len(jobs) > 4:
        with ProcessPoolExecutor(a.jobs) as ex:
            res = list(ex.map(_feat_job, jobs, chunksize=4))
    else:
        res = [_feat_job(j) for j in jobs]
    t_feat = time.perf_counter() - t1
    feats = [r[1] for r in res]
    infos = [r[2] for r in res]
    y_all = np.array([c for c, _, _ in items])

    # ---- matrix
    allkeys = sorted(set().union(*feats))
    keep = [k for k in allkeys if all(k in f for f in feats)]
    X_all = np.array([[f[k] for k in keep] for f in feats], dtype=np.float64)
    nonempty = ~np.all(np.isnan(X_all), axis=0)
    dropped = [k for k in allkeys if k not in keep] + [k for k, ok in zip(keep, nonempty) if not ok]
    keep = [k for k, ok in zip(keep, nonempty) if ok]
    X_all = X_all[:, nonempty]
    if dropped:
        warnings.warn(f"dropped {len(dropped)} columns: {dropped}")

    counts = Counter(y_all.tolist())
    skipped = {c: n for c, n in counts.items() if n < MIN_CLASS}
    for c, n in skipped.items():
        warnings.warn(f"class {c!r} has {n} < {MIN_CLASS} drawings: left out of CV")
    m = np.array([c not in skipped for c in y_all])
    X, y = X_all[m], y_all[m]
    # CV groups: a source drawing and its nulls share one group.
    stem = lambda key: key.split("/", 1)[1]
    G = np.array([f"src:{stem(key)}" if (c == a.null_source or c.startswith("null_")) else key
                  for (c, key, _) in items])[m]
    labels = [c for c in dict.fromkeys(y_all.tolist()) if c not in skipped]
    if len(labels) < 2:
        sys.exit("need at least two classes with >= 3 drawings")
    k = int(min(5, min(counts[c] for c in labels)))
    models = _models(a.seed)
    gnames = [panel.group_of(n) for n in keep]
    present = [g for g in panel.GROUPS if g in gnames]

    def cols(excl=(), only=None):
        return [i for i, g in enumerate(gnames) if (g == only if only else g not in excl)]

    def multiclass(ix):
        return {mn: cv_score(mk, X[:, ix], y, k, a.repeats, a.seed, a.jobs, G) for mn, mk in models.items()}

    def pairwise(ix, which=None):
        out = {}
        for la, lb in combinations(labels, 2):
            key = f"{la} vs {lb}"
            if which and not which(la, lb):
                continue
            out[key] = {mn: pair_auc(mk, X[:, ix], y, la, lb, a.repeats, a.seed, G) for mn, mk in models.items()}
        return out

    t2 = time.perf_counter()
    every = list(range(len(keep)))
    geo = cols(excl=panel.WIDTH_GROUPS)
    src = a.null_source
    rep = {
        "name": a.name or "-".join(groups),
        "config": {"groups": {g: str(d) for g, d in (x.partition("=")[::2] for x in a.group)},
                   "null_source": src, "nulls": a.nulls, "sigma_frac": a.sigma_frac, "sigma_min_w": a.sigma_min_w,
                   "width": not a.no_width, "seed": a.seed, "repeats": a.repeats, "k": k},
        "classes": {c: counts[c] for c in labels},
        "skipped_classes": skipped,
        "labels": labels,
        "n_features": len(keep),
        "features": keep,
        "groups": present,
        "dropped_columns": dropped,
        "clothoid_status": ", ".join(f"{s} ×{n}" for s, n in Counter(i.get("clothoid", "?") for i in infos).items()),
        "panel_seconds_mean": float(np.mean([i["seconds"] for i in infos])),
        "panel_seconds_max": float(np.max([i["seconds"] for i in infos])),
        "multiclass": multiclass(every),
        "confusion": {mn: confusion(mk, X, y, labels, k, a.seed, G) for mn, mk in models.items()},
        "pairwise": pairwise(every),
    }
    rep["geometry_only"] = {
        "excluded_groups": list(panel.WIDTH_GROUPS),
        "multiclass": multiclass(geo) if geo else {},
        "pairwise": pairwise(geo, (lambda la, lb: la == src or lb == src) if src else None) if geo else {},
    }
    # Nulls are always open and placed independently of each other, so closure
    # and inter-stroke relations separate them from real drawings for free.
    # The fair Pollock test therefore drops those along with width.
    fair = [i for i in geo if gnames[i] != "rel" and keep[i] != "len_closure"]
    rep["pollock_fair"] = {
        "excluded": list(panel.WIDTH_GROUPS) + ["rel_", "len_closure"],
        "pairwise": pairwise(fair, lambda la, lb: src in (la, lb) and "null_" in la + lb) if src and fair else {},
    }
    # Pipeline-matched Pollock test: each null vs the identity control (same
    # measure-and-re-integrate pipeline, nothing shuffled).
    if "null_identity" in labels:
        rep["pollock_matched"] = pairwise(
            fair, lambda la, lb: "null_identity" in (la, lb) and la.startswith("null_") and lb.startswith("null_"))
    # Artists-only, geometry-only: the honest artist number (the multi-class
    # figure is padded by easy null classes).
    arts = [c for c in labels if not c.startswith("null_")]
    if len(arts) >= 2:
        am = np.isin(y, arts)
        ka = int(min(5, min(counts[c] for c in arts)))
        rep["artists_only"] = {
            "classes": arts, "chance": 1.0 / len(arts),
            "geometry_only": {mn: cv_score(mk, X[am][:, geo], y[am], ka, a.repeats, a.seed, a.jobs, G[am])
                              for mn, mk in models.items()},
        }
    rep["effects"] = {f"{la} vs {lb}": effect_sizes(X, y, keep, la, lb)
                      for la, lb in combinations(labels, 2) if src in (la, lb)} if src else {}
    rep["ablation"] = {}
    for g in present:
        drop = cols(excl=(g,))
        alone = cols(only=g)
        rep["ablation"][g] = {
            "n": len(alone),
            "drop": multiclass(drop) if drop else {mn: {"bacc": float("nan"), "std": 0.0} for mn in models},
            "alone": multiclass(alone),
        }
    rep["importance"] = perm_importance(models["forest"], X, y, keep, k, a.seed, groups=G)

    out = a.out / rep["name"]
    out.mkdir(parents=True, exist_ok=True)
    scatter(X, y, labels, out / "scatter.png", a.seed)
    rep["scatter"] = str(out / "scatter.png")
    rep["seconds"] = {"features": t_feat, "analysis": time.perf_counter() - t2,
                      "total": time.perf_counter() - t0}
    with open(out / "features.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["class", "key"] + keep)
        for (c, key, _), row in zip(items, X_all):
            w.writerow([c, key] + [f"{v:.6g}" for v in row])
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=float))
    md = markdown(rep)
    md += (f"\nTimes: features {t_feat:.1f} s ({len(items)} drawings, {a.jobs} jobs), "
           f"analysis {rep['seconds']['analysis']:.1f} s.\n")
    (out / "report.md").write_text(md)
    print(md)
    return rep


if __name__ == "__main__":
    main()

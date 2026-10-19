# FROZEN from research commit a66c6a5: tools/gesture/gesture/medium.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Standard preprocessing for ARTIST comparisons: remove medium.

The panel, measured raw, separates Matisse's own etchings from his own
lithographs about as well as it separates artists — it hears the medium
(crayon grain, sparser sheets) as loudly as the hand. Two steps make an
artist comparison mean "hand":

1. **Scale** — panel σ = max(0.01·ref, SIGMA_MIN_W · median line width), so
   every drawing is measured at the same scale relative to its own line and
   grain at a few line widths is smoothed away (`panel.features(...,
   sigma_min_w=SIGMA_MIN_W)`).
2. **Projection** — `MediumProjector` learns, from WITHIN-HAND medium
   contrasts listed in docs/research/gesture-corpus/medium-pairs.csv (same
   artist, two media), the linear directions that tell the media apart
   (iterative nullspace projection, INLP), and projects them out of every
   drawing's standardised feature vector. It uses medium labels only, never
   artist labels, so fitting it on all drawings does not leak the artist
   target into cross-validation.

Evidence and limits: tools/gesture/results/medium-invariance-2026-10-16.md
(held-out etching-vs-litho AUC 0.77 → 0.44 with a linear probe, 0.61 with a
forest probe; artists 0.83/0.79). Only media that appear within one hand can
be removed — brush (Hokusai) and graphite (Ingres) are not covered until a
within-hand pair exists for them.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SIGMA_MIN_W = 7.0     # panel σ floor, in median line widths
INLP_ITERS = 4        # nullspace-projection rounds per medium pair
INLP_C = 0.5          # logistic-regression regularisation for each round

_REPO = Path(__file__).resolve().parents[3]
MEDIA_CSV = _REPO / "docs/research/gesture-corpus/media.csv"
PAIRS_CSV = _REPO / "docs/research/gesture-corpus/medium-pairs.csv"


def load_media(path: Path = MEDIA_CSV) -> dict[tuple[str, str], str]:
    """(artist, scan stem) → medium."""
    return {(r["artist"], r["stem"]): r["medium"] for r in csv.DictReader(open(path))}


def load_pairs(path: Path = PAIRS_CSV, enabled_only: bool = True) -> list[tuple[str, str, str]]:
    """[(artist, medium_a, medium_b)] for the contrasts to project out."""
    out = []
    for r in csv.DictReader(open(path)):
        if enabled_only and r["enabled"].strip().lower() not in {"yes", "true", "1", "y"}:
            continue
        out.append((r["artist"], r["medium_a"], r["medium_b"]))
    return out


def _probe_direction(Z: np.ndarray, y: np.ndarray, seed: int) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    w = LogisticRegression(C=INLP_C, max_iter=5000, random_state=seed).fit(Z, y).coef_[0]
    n = np.linalg.norm(w)
    return w / n if n > 1e-12 else w


@dataclass
class MediumProjector:
    """Impute (median) → standardise → project out within-hand medium
    directions. Fit once on a feature matrix, transform any rows.

    `fit` takes per-row artist and medium labels; rows whose (artist, medium)
    is not part of an enabled pair still contribute to the imputation and
    standardisation statistics but not to the directions.
    """
    pairs: list[tuple[str, str, str]]
    iters: int = INLP_ITERS
    seed: int = 0
    median_: np.ndarray | None = field(default=None, init=False)
    mean_: np.ndarray | None = field(default=None, init=False)
    scale_: np.ndarray | None = field(default=None, init=False)
    basis_: np.ndarray | None = field(default=None, init=False)   # (k, d) orthonormal
    fitted_pairs_: list = field(default_factory=list, init=False)

    def _standardise(self, X: np.ndarray) -> np.ndarray:
        X = np.array(X, dtype=np.float64, copy=True)
        idx = np.where(np.isnan(X))
        X[idx] = np.take(self.median_, idx[1])
        return (X - self.mean_) / self.scale_

    def fit(self, X: np.ndarray, artist, medium, rows=None) -> "MediumProjector":
        """rows: optional index subset to learn directions from (for held-out
        checks); statistics always come from all of X."""
        X = np.asarray(X, dtype=np.float64)
        artist, medium = np.asarray(artist), np.asarray(medium)
        self.median_ = np.nan_to_num(np.nanmedian(X, axis=0))
        Xi = X.copy()
        idx = np.where(np.isnan(Xi))
        Xi[idx] = np.take(self.median_, idx[1])
        self.mean_ = Xi.mean(axis=0)
        sd = Xi.std(axis=0)
        self.scale_ = np.where(sd > 0, sd, 1.0)
        Z = (Xi - self.mean_) / self.scale_
        allowed = np.zeros(len(X), bool)
        allowed[np.arange(len(X)) if rows is None else np.asarray(rows)] = True
        dirs: list[np.ndarray] = []
        self.fitted_pairs_ = []
        for art, ma, mb in self.pairs:
            m = allowed & (artist == art) & np.isin(medium, [ma, mb])
            y = (medium[m] == mb).astype(int)
            if m.sum() < 4 or len(set(y)) < 2:
                continue
            Zm = Z[m]
            for _ in range(self.iters):
                for d in dirs:                       # keep earlier directions removed
                    Zm = Zm - np.outer(Zm @ d, d)
                w = _probe_direction(Zm, y, self.seed)
                for d in dirs:                       # orthogonalise
                    w = w - (w @ d) * d
                n = np.linalg.norm(w)
                if n < 1e-9:
                    break
                dirs.append(w / n)
            self.fitted_pairs_.append((art, ma, mb, int((y == 0).sum()), int((y == 1).sum())))
        self.basis_ = np.array(dirs) if dirs else np.zeros((0, X.shape[1]))
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        Z = self._standardise(X)
        B = self.basis_
        return Z - (Z @ B.T) @ B if len(B) else Z

    def fit_transform(self, X, artist, medium) -> np.ndarray:
        return self.fit(X, artist, medium).transform(X)


def heldout_medium_auc(X, artist, medium, pairs, *, iters=INLP_ITERS, reps=100, seed=0,
                       probe="linear") -> dict:
    """For each enabled pair: fit the projector on half that pair's sheets,
    train a fresh probe on the same half, AUC on the other half. ≈ 0.5 means
    the medium is no longer recoverable. probe: "linear" | "forest"."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedShuffleSplit
    artist, medium = np.asarray(artist), np.asarray(medium)
    out = {}
    for art, ma, mb in pairs:
        idx = np.flatnonzero((artist == art) & np.isin(medium, [ma, mb]))
        y = (medium[idx] == mb).astype(int)
        if len(set(y)) < 2 or min(np.bincount(y)) < 4:
            continue
        res = {}
        for it in sorted({0, iters}):
            aucs = []
            for tr, te in StratifiedShuffleSplit(reps, test_size=0.5, random_state=seed).split(idx, y):
                pj = MediumProjector([(art, ma, mb)], iters=it, seed=seed).fit(X, artist, medium, rows=idx[tr])
                Z = pj.transform(X[idx])
                clf = (LogisticRegression(C=INLP_C, max_iter=5000) if probe == "linear"
                       else RandomForestClassifier(300, random_state=seed))
                p = clf.fit(Z[tr], y[tr]).predict_proba(Z[te])[:, 1]
                aucs.append(roc_auc_score(y[te], p))
            res["raw" if it == 0 else "projected"] = (float(np.mean(aucs)), float(np.std(aucs)))
        out[f"{art}: {ma} vs {mb}"] = res
    return out

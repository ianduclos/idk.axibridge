import numpy as np

from gesture import medium


def _toy(seed=0, n=40, d=12):
    """Artist signal on feature 0, medium signal on features 1-2 (within
    artist A only measured as two media; B has one medium)."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(2 * n, d))
    artist = np.array(["A"] * n + ["B"] * n)
    med = np.array(["etch", "litho"] * (n // 2) + ["brush"] * n)
    X[artist == "B", 0] += 3.0
    X[med == "litho", 1] += 2.5
    X[med == "litho", 2] -= 2.0
    return X, artist, med


def test_projection_removes_medium_keeps_artist():
    X, artist, med = _toy()
    pj = medium.MediumProjector([("A", "etch", "litho")], iters=2).fit(X, artist, med)
    Z = pj.transform(X)
    a = (artist == "A")
    gap_med = abs(Z[a & (med == "litho")].mean(0) - Z[a & (med == "etch")].mean(0))
    assert gap_med[1] < 0.3 and gap_med[2] < 0.3
    Z0 = medium.MediumProjector([("A", "etch", "litho")], iters=0).fit(X, artist, med).transform(X)
    gap0 = Z0[artist == "B", 0].mean() - Z0[artist == "A", 0].mean()
    gap_art = Z[artist == "B", 0].mean() - Z[artist == "A", 0].mean()
    assert gap_art > 0.6 * gap0   # most of the artist signal survives


def test_basis_orthonormal_and_pure():
    X, artist, med = _toy(1)
    X0 = X.copy()
    pj = medium.MediumProjector([("A", "etch", "litho")], iters=4).fit(X, artist, med)
    B = pj.basis_
    assert np.allclose(B @ B.T, np.eye(len(B)), atol=1e-8)
    assert np.array_equal(X, X0)


def test_nan_imputed_and_deterministic():
    X, artist, med = _toy(2)
    X[3, 4] = np.nan
    a = medium.MediumProjector([("A", "etch", "litho")]).fit(X, artist, med).transform(X)
    b = medium.MediumProjector([("A", "etch", "litho")]).fit(X, artist, med).transform(X)
    assert np.all(np.isfinite(a)) and np.array_equal(a, b)


def test_heldout_auc_drops_to_chance():
    X, artist, med = _toy(3, n=60)
    r = medium.heldout_medium_auc(X, artist, med, [("A", "etch", "litho")], iters=2, reps=20)
    v = r["A: etch vs litho"]
    assert v["raw"][0] > 0.9 and v["projected"][0] < 0.7


def test_manifests_load():
    media = medium.load_media()
    pairs = medium.load_pairs()
    assert ("matisse", "etching", "lithograph") in pairs
    assert media[("matisse", "KKS21174")] == "etching"

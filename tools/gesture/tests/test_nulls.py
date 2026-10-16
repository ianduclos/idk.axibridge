import numpy as np
import pytest
from scipy.stats import ks_2samp

from gesture import nulls, synth
from gesture.core import Drawing, Stroke
from gesture.curvature import kappa_s, resample, turning_angles

NAMES = list(nulls.NULLS)


@pytest.fixture(scope="module")
def drawings():
    rng = np.random.default_rng(0)
    mat = synth.scene_matisse_like(rng, (1000, 800))
    rnd = synth.scene_random(np.random.default_rng(1), (600, 600), 8, length_frac=(0.3, 0.8))
    loop = synth.scene_closed_loop((500, 500))
    return {"matisse": mat, "random": rnd, "loop": loop}


def _kappas(d: Drawing, sigma: float) -> list[np.ndarray]:
    return [kappa_s(s.points, sigma, step=sigma / 4, closed=s.closed)[1] for s in d.strokes]


@pytest.mark.parametrize("name", NAMES)
def test_null_preserves_count_lengths_canvas(name, drawings):
    for key, d in drawings.items():
        nd = nulls.NULLS[name](d, np.random.default_rng(0))
        assert nd.size == d.size and len(nd.strokes) == len(d.strokes)
        for a, b in zip(d.strokes, nd.strokes):
            assert abs(b.length() / a.length() - 1) < 0.02, (key, b.length(), a.length())
            assert (b.width is None) == (a.width is None)
            if b.width is not None:
                assert b.width.shape == (len(b),)
        assert nd.meta["null"] == name and nd.meta["source"] == d.source
        assert all(s.meta["null"] == name for s in nd.strokes)
        assert nd.meta["overflow"] == sum(s.meta["overflow"] for s in nd.strokes)
        if not (name == "random_walk" and key == "loop"):
            assert nd.meta["overflow"] == 0, (key, name)
        W, H = d.size
        for s in nd.strokes:
            if s.meta["overflow"]:
                continue  # centred, accepted overflow (see test_overflow_rates)
            assert s.points.min() >= -1e-9
            assert s.points[:, 0].max() <= W - 1 + 1e-9 and s.points[:, 1].max() <= H - 1 + 1e-9


@pytest.mark.parametrize("name", NAMES)
def test_null_deterministic_seeded_pure(name, drawings):
    d = drawings["matisse"]
    before = [(s.points.copy(), None if s.width is None else s.width.copy(), dict(s.meta))
              for s in d.strokes]
    a = nulls.NULLS[name](d, np.random.default_rng(5))
    b = nulls.NULLS[name](d, np.random.default_rng(5))
    c = nulls.NULLS[name](d, np.random.default_rng(6))
    assert all(np.array_equal(x.points, y.points) for x, y in zip(a.strokes, b.strokes))
    assert not all(np.allclose(x.points, y.points) for x, y in zip(a.strokes, c.strokes))
    for s, (p, w, m) in zip(d.strokes, before):
        assert np.array_equal(s.points, p) and s.meta == m
        assert (w is None and s.width is None) or np.array_equal(s.width, w)


def test_random_walk_matches_turning_rms(drawings):
    rms = lambda a: np.sqrt(np.mean(a ** 2))  # noqa: E731
    for d in drawings.values():
        nd = nulls.random_walk(d, np.random.default_rng(0))
        h = nd.meta["step"]
        for s, n in zip(d.strokes, nd.strokes):
            src = turning_angles(resample(s.points, h, s.closed), s.closed)
            out = turning_angles(n.points)
            assert abs(np.mean(out)) < 3 * rms(src) / np.sqrt(len(out)) + 1e-9  # zero-mean
            assert abs(rms(out) / rms(src) - 1) < 4 / np.sqrt(len(out)) + 0.05


def test_smooth_noise_matches_rms_kappa(drawings):
    d = drawings["matisse"]
    sig = nulls.kappa_sigma(d)
    nd = nulls.smooth_noise(d, np.random.default_rng(0))
    rms = lambda ks: np.sqrt(np.mean(np.concatenate(ks) ** 2))  # noqa: E731
    assert abs(rms(_kappas(nd, sig)) / rms(_kappas(d, sig)) - 1) < 0.15


def _acf(ks: list[np.ndarray], lag_frac: float) -> float:
    """Pooled-mean autocorrelation of κ at lag = lag_frac of each stroke."""
    allk = np.concatenate(ks)
    mu, var = allk.mean(), allk.var()
    num = cnt = 0.0
    for k in ks:
        lag = max(int(lag_frac * len(k)), 1)
        if len(k) > lag:
            num += np.sum((k[:-lag] - mu) * (k[lag:] - mu))
            cnt += len(k) - lag
    return num / cnt / var


def test_shuffled_segments_keeps_kappa_distribution_breaks_order():
    """Pooled |κ| distribution survives (KS on samples 2σ apart, roughly
    independent), autocorrelation at the piece length collapses.

    Known, intrinsic compression: each piece boundary is a κ jump that the
    re-measurement smooths over ±2σ, pulling the extremes in by ~10% at the
    default seg_frac — so a few seeds fall below p = 0.01 (about 1 in 5 at
    seg_frac=0.1). The test asserts the bulk behaviour, not every seed.
    """
    ps, acf_src, acf_null = [], [], []
    for seed in range(8):
        d = synth.scene_matisse_like(np.random.default_rng(seed), (1000, 800))
        sig = nulls.kappa_sigma(d)
        nd = nulls.shuffled_segments(d, np.random.default_rng(100 + seed), seg_frac=0.1)
        a, b = _kappas(d, sig), _kappas(nd, sig)
        A, B = np.abs(np.concatenate(a)), np.abs(np.concatenate(b))
        ps.append(ks_2samp(A[::8], B[::8]).pvalue)
        acf_src.append(_acf(a, 0.1))
        acf_null.append(_acf(b, 0.1))
        assert abs(np.median(B) / np.median(A) - 1) < 0.25
    assert np.mean(np.array(ps) > 0.01) >= 0.6, np.round(ps, 4)
    assert np.median(ps) > 0.01
    assert np.mean(acf_src) > 0.8
    assert np.mean(acf_null) < 0.4 and all(n < s for n, s in zip(acf_null, acf_src))


def _demeaned_acf(ks: list[np.ndarray], lag: int) -> float:
    """Per-stroke demeaned autocorrelation at `lag` samples, pooled."""
    num = den = 0.0
    for k in ks:
        if len(k) > 4 * lag:
            z = k - k.mean()
            num += np.sum(z[:-lag] * z[lag:])
            den += np.sum(z * z) * (len(k) - lag) / len(k)
    return num / den


def test_kappa_permuted_destroys_correlation(drawings):
    d = drawings["matisse"]
    sig = nulls.kappa_sigma(d)
    # κ samples are σ/4 apart; past the measurement kernel (lag 16 = 4σ)
    # the source is still strongly correlated, the null is not
    src = _demeaned_acf(_kappas(d, sig), 16)
    null = np.mean([_demeaned_acf(_kappas(nulls.kappa_permuted(d, np.random.default_rng(s)), sig), 16)
                    for s in range(4)])
    assert src > 0.7
    assert -0.3 < null < 0.2
    # per-stroke mean κ (net turning) is a histogram property, so it survives
    nd = nulls.kappa_permuted(d, np.random.default_rng(0))
    for a, b in zip(_kappas(d, sig), _kappas(nd, sig)):
        assert abs(b.mean() - a.mean()) < 0.15 * np.abs(a).mean()


def test_overflow_rotate_then_centre():
    # straight lines on a 600×600 canvas (diagonal ≈ 847 px): 700 px fits only
    # rotated, 2000 px cannot fit at all, 100 px just needs translating
    line = lambda L: Stroke(np.column_stack([np.linspace(0, L, 400), np.full(400, 10.0)]))  # noqa: E731
    d = Drawing([line(700.0), line(2000.0), line(100.0)], source="t", size=(600, 600))
    nd = nulls.shuffled_segments(d, np.random.default_rng(0))
    over = [s.meta["overflow"] for s in nd.strokes]
    assert nd.meta["overflow"] == sum(over) >= 1
    for s, o in zip(nd.strokes, d.strokes):
        assert abs(s.length() / o.length() - 1) < 0.02
    # the 2000 px stroke cannot fit at any angle: centred, flagged
    big = [s for s, o in zip(nd.strokes, d.strokes) if o.length() > 1500][0]
    assert big.meta["overflow"]
    lo, hi = big.points.min(axis=0), big.points.max(axis=0)
    assert np.allclose((lo + hi) / 2, [299.5, 299.5], atol=1.0)
    # a straight 700 px stroke must have been rotated to fit, not flagged
    fit = [s for s, o in zip(nd.strokes, d.strokes) if 600 < o.length() < 800][0]
    assert not fit.meta["overflow"]


def test_overflow_rates():
    """How often a null stroke cannot be fitted on the canvas (centred and
    flagged instead). Turning-matched random walks of smooth strokes are
    almost straight (i.i.d. turns diffuse slowly), so a long smooth stroke
    whose null is longer than the canvas diagonal overflows; e.g. the closed
    loop scene's random walk does. Realistic multi-stroke scenes stay clean."""
    counts = {n: 0 for n in NAMES}
    total = 0
    for seed in range(6):
        d = synth.scene_matisse_like(np.random.default_rng(seed), (900, 700))
        total += len(d.strokes)
        for n in NAMES:
            counts[n] += nulls.NULLS[n](d, np.random.default_rng(seed)).meta["overflow"]
    assert all(c / total <= 0.1 for c in counts.values()), (counts, total)
    loop = synth.scene_closed_loop((500, 500))
    assert nulls.random_walk(loop, np.random.default_rng(0)).meta["overflow"] == 1

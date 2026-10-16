"""The composite pipeline: structure → hand → (single line) → (tremor).

results/composite-2026-10-16.md. Library functions (imported by
tests/test_composite.py) plus subcommands (run from tools/gesture):

  composite(structure, hand, rng, ...)  one drawing:
      1. structure: `topology.generate_structure` — kind "oehlen_tree"
         (complexity params) or "learned" (the hand's own TopologyModel) —
         or any given Drawing (e.g. a real drawing's long strokes);
      2. restyle into the hand (`restyle.restyle_drawing`, FROZEN v4 grammar,
         gauss/trace, junctions welded) or `model="lognormal"` (the kinematic
         hand, `source="trace_ln"`);
      3. chain (optional): `chain_paths` joins the lines into as few
         continuous pen paths as possible (Euler path on the junction graph,
         odd ends paired by a min-weight matching = minimal retrace);
         chain="before" chains the skeleton and restyles the single line;
      4. tremor (optional): `gesture.tremor.apply_tremor` if that module and
         a fitted model exist.

  pairwise   panel pairwise hand test: same structure in hand A and hand B;
             a classifier trained on REAL drawings of A vs B says which is A.
  judge      blinded image pairs for a visual judge (key outside the repo).
  sheets     the composite sheets (trees × hands, chained, learned, translation).
  bench      cost per drawing of each pipeline stage.

    ../../.local/gesture/.venv/bin/python -m experiments.composite pairwise
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import grammar_v4_frozen as gm  # noqa: E402
from gesture import restyle as rs  # noqa: E402
from gesture import topology  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUTROOT = ROOT / ".local/gesture/out"
GRAMMARS = OUTROOT / "grammar_v4_frozen"
TOPO = OUTROOT / "topology"
LOGN = OUTROOT / "lognormal"
EXTRACT = OUTROOT / "extract_hybrid"
OUT = OUTROOT / "composite"
RESULTS = Path(__file__).resolve().parents[1] / "results"
ARTISTS = ("matisse", "hokusai", "ingres")
JOBS = 3                                    # shared machine: keep pools small

_CACHE: dict = {}


def grammar(art: str):
    k = ("g", art)
    if k not in _CACHE:
        _CACHE[k] = gm.Grammar.load(GRAMMARS / f"grammar_{art}.json")
    return _CACHE[k]


def topo_model(art: str):
    k = ("t", art)
    if k not in _CACHE:
        p = TOPO / f"model_{art}.json"
        _CACHE[k] = topology.TopologyModel.load(p) if p.exists() else None
    return _CACHE[k]


def ln_hand(art: str):
    k = ("l", art)
    if k not in _CACHE:
        from gesture import lognormal as ln
        _CACHE[k] = ln.Hand.load(LOGN / f"hand_{art}.json")
    return _CACHE[k]


# ---------------------------------------------------------------------------
# chaining: as few continuous pen paths as possible
# ---------------------------------------------------------------------------

def _arclen(p):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def _crossing_splits(S: list[np.ndarray], closed: list[bool]) -> dict[int, list]:
    """Insert X-crossing points: {stroke: [(segment index, point), ...]}."""
    from shapely import STRtree
    from shapely.geometry import LineString
    geoms = [LineString(np.vstack([p, p[:1]]) if c else p) for p, c in zip(S, closed)]
    tree = STRtree(geoms)
    out: dict[int, list] = {}
    for i, gi in enumerate(geoms):
        for j in tree.query(gi):
            j = int(j)
            if j <= i:
                continue
            x = gi.intersection(geoms[j])
            pts = [x] if x.geom_type == "Point" else [g for g in getattr(x, "geoms", []) if g.geom_type == "Point"]
            for pt in pts:
                c = np.array(pt.coords[0])
                for k in (i, j):
                    q = S[k] if not closed[k] else np.vstack([S[k], S[k][:1]])
                    a, b = q[:-1], q[1:]
                    ab = b - a
                    t = np.clip(np.sum((c - a) * ab, 1) / np.maximum(np.sum(ab * ab, 1), 1e-12), 0, 1)
                    seg = int(np.argmin(np.sum((a + t[:, None] * ab - c) ** 2, 1)))
                    out.setdefault(k, []).append((seg, c))
    return out


def chain_paths(drawing: Drawing, *, tol_r: float = rs.WELD_R, at_crossings: bool = False,
                max_retrace: float | None = None) -> Drawing:
    """Join a drawing's lines into as few continuous pen paths as possible.

    Graph: nodes are stroke ends, junction points (an end touching another
    line within tol_r·R splits that line there) and, with at_crossings, X
    crossings; edges are the line pieces between them. Per connected
    component, odd-degree nodes are paired by a min-weight matching on
    shortest-path length, with two virtual ends that may take any odd node
    for free (the exact open Chinese-postman pairing: the path's two ends
    are chosen optimally); the matched shortest paths are duplicated (that
    is the retrace, minimal) and an Euler path is walked. Every input
    line is drawn exactly once plus the retraces; the pen lifts only between
    components. max_retrace (fraction of the ink): add pen paths (2 more
    virtual ends each) until the retrace is below it — the
    trade between one line and doubled twigs. Pure; geometry in, geometry
    out (no smoothing).
    Returns a Drawing with one stroke per component, meta n_in / n_paths /
    ink / retrace (R units)."""
    import networkx as nx
    from scipy.spatial import cKDTree
    S = [s.points.astype(float) for s in drawing.strokes if len(s.points) >= 2]
    C = [bool(s.closed) for s in drawing.strokes if len(s.points) >= 2]
    R = drawing.ref_length()
    tol = tol_r * R
    if not S:
        return Drawing([], source=drawing.source, size=drawing.size, meta={**drawing.meta, "chain": {}})
    # 0. optional crossing points, inserted as vertices
    if at_crossings:
        ins = _crossing_splits(S, C)
        for k, lst in ins.items():
            p = S[k]
            for seg, c in sorted(lst, key=lambda t: -t[0]):
                p = np.insert(p, seg + 1, c, axis=0)
            S[k] = p
    # 1. split indices per stroke where another stroke's end touches it
    P = np.vstack(S)
    own = np.concatenate([np.full(len(p), i) for i, p in enumerate(S)])
    loc = np.concatenate([np.arange(len(p)) for p in S])
    tree = cKDTree(P)
    cuts: list[set] = [set() for _ in S]
    for i, p in enumerate(S):
        if C[i]:
            continue
        for e in (0, len(p) - 1):
            cand = [j for j in tree.query_ball_point(p[e], tol) if own[j] != i]
            if cand:
                j = min(cand, key=lambda c: float(np.sum((P[c] - p[e]) ** 2)))
                cuts[own[j]].add(int(loc[j]))
    if at_crossings:
        for k in range(len(S)):
            # inserted crossing vertices are exact: find them as near-duplicates of other strokes' points
            d, _ = tree.query(S[k], k=2)
            for idx in np.where(d[:, 1] < 1e-9)[0]:
                cuts[k].add(int(idx))
    # 2. pieces
    pieces: list[np.ndarray] = []
    for i, p in enumerate(S):
        n = len(p)
        if C[i]:
            cs = sorted(cuts[i])
            if not cs:
                pieces.append(np.vstack([p, p[:1]]))
                continue
            q = np.vstack([p[cs[0]:], p[:cs[0]], p[cs[0]:cs[0] + 1]])
            rel = sorted({(c - cs[0]) % n for c in cs} | {n})
            for a, b in zip(rel[:-1], rel[1:]):
                pieces.append(q[a:b + 1])
        else:
            cs = sorted({c for c in cuts[i] if 0 < c < n - 1} | {0, n - 1})
            for a, b in zip(cs[:-1], cs[1:]):
                if b > a:
                    pieces.append(p[a:b + 1])
    # 3. nodes: piece ends clustered within tol (union-find)
    ends = np.vstack([[pc[0], pc[-1]] for pc in pieces])
    parent = list(range(len(ends)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, b in cKDTree(ends).query_pairs(tol):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    node = [find(a) for a in range(len(ends))]
    G = nx.MultiGraph()
    for k, pc in enumerate(pieces):
        G.add_edge(node[2 * k], node[2 * k + 1], key=k, piece=k, length=float(_arclen(pc)[-1]))
    ink = sum(d["length"] for _u, _v, d in G.edges(data=True))
    paths, retrace = [], 0.0
    nxt = len(pieces)
    for comp in nx.connected_components(G):
        H = G.subgraph(comp).copy()
        odd = [v for v in H.nodes if H.degree(v) % 2]
        if len(odd) > 2:
            dist, route = {}, {}
            for a in odd:
                dd, pp = nx.single_source_dijkstra(H, a, weight="length")
                for b in odd:
                    if b != a and b in dd:
                        dist[(a, b)], route[(a, b)] = dd[b], pp[b]
            comp_ink = sum(d["length"] for _u, _v, d in H.edges(data=True))

            def match(k):
                """Optimal pairing with k open trails: 2k virtual ends, each free
                to take any odd node at no cost (exact open Chinese postman)."""
                K = nx.Graph()
                for (a, b), w in dist.items():
                    if a < b:
                        K.add_edge(a, b, weight=w)
                for v in range(2 * k):
                    for a in odd:
                        K.add_edge(("virtual", v), a, weight=0.0)
                return [(a, b) for a, b in nx.min_weight_matching(K, weight="weight")
                        if not isinstance(a, tuple) and not isinstance(b, tuple)]
            k = 1
            keep = match(k)
            if max_retrace is not None:
                while keep and sum(dist[(x, y)] for x, y in keep) > max_retrace * comp_ink:
                    k += 1                           # one more pen path instead of the longest retraces
                    keep = match(k)
            for a, b in keep:
                r = route[(a, b)]
                for x, y in zip(r[:-1], r[1:]):
                    kk, dmin = min(((k_, d_) for k_, d_ in H.get_edge_data(x, y).items()),
                                   key=lambda t: t[1]["length"])
                    H.add_edge(x, y, key=nxt, piece=dmin["piece"], length=dmin["length"], retrace=True)
                    retrace += dmin["length"]
                    nxt += 1
        odd = [v for v in H.nodes if H.degree(v) % 2]
        if len(odd) > 2:                             # several trails: a virtual node makes it Eulerian
            for v in odd:
                H.add_edge(-1, v, key=nxt, piece=-1, length=0.0)
                nxt += 1
            walk = list(nx.eulerian_circuit(H, source=-1, keys=True))
        else:
            start = odd[0] if odd else next(iter(H.nodes))
            walk = list(nx.eulerian_path(H, source=start, keys=True)) if H.number_of_edges() else []
        seq = []
        for u, v, k in walk:
            k0 = H.edges[u, v, k]["piece"]
            if k0 < 0:                               # through the virtual node: lift the pen
                if seq:
                    paths.append(np.vstack(seq))
                seq = []
                continue
            pc = pieces[k0]
            fwd = node[2 * k0] == u
            pc = pc if fwd else pc[::-1]
            if seq and np.linalg.norm(seq[-1][-1] - pc[0]) < 1e-9:
                pc = pc[1:]
            seq.append(pc)
        if seq:
            paths.append(np.vstack(seq))
    strokes = [Stroke(p, meta={"chain": True}) for p in paths if len(p) >= 2]
    return Drawing(strokes, source=f"{drawing.source}|chain", size=drawing.size,
                   meta={**drawing.meta, "chain": {"n_in": len(S), "n_paths": len(strokes),
                                                   "ink_R": ink / R, "retrace_R": retrace / R,
                                                   "at_crossings": at_crossings, "max_retrace": max_retrace}})


# ---------------------------------------------------------------------------
# the composite
# ---------------------------------------------------------------------------

def structure_of(kind, hand: str | None, rng, size, params: dict | None = None) -> Drawing:
    if isinstance(kind, Drawing):
        return kind
    if kind == "oehlen_tree":
        return topology.generate_structure(None, rng, size, kind="oehlen_tree", **(params or {}))
    if kind == "learned":
        return topology.generate_structure(topo_model(hand) if hand else None, rng, size, kind="learned",
                                           **(params or {}))
    raise ValueError(f"unknown structure kind {kind!r}")


def _tremor(d: Drawing, art: str, rng, amount: float):
    """Optional stage: another agent's gesture.tremor (if it imports and a
    fitted model is on disk at out/tremor/models/{art}.json). Line width w =
    the hand's own median w/R × the drawing's R, so tremor is at the hand's
    scale. Returns (drawing, note)."""
    try:
        from gesture import tremor as tr
    except Exception as e:  # noqa: BLE001
        return d, f"tremor unavailable: {e}"
    p = OUTROOT / "tremor" / "models" / f"{art}.json"
    if not p.exists():
        return d, "tremor: no fitted model on disk"
    try:
        model = tr.TremorModel.load(p)
        wr = float(np.median([x["w_over_R"] for x in grammar(art).drawings if x["w_over_R"] > 0]))
        return tr.apply_tremor(d, model, rng, amount, w=wr * d.ref_length()), f"tremor {p.name} x{amount:g}"
    except Exception as e:  # noqa: BLE001 — someone else's work in progress
        return d, f"tremor failed: {e}"


def composite(structure, hand, rng: np.random.Generator, *, size=1200, amount: float = 0.6,
              chain: bool | str = False, tremor: float | None = None, model: str = "grammar",
              method: str = "gauss", scale: str = "drawing", weld: bool = True,
              structure_params: dict | None = None, at_crossings: bool = False,
              structure_hand: str | None = None, max_retrace: float | None = None) -> Drawing:
    """structure ("oehlen_tree" | "learned" | a Drawing) → restyled into
    `hand` (artist name, or a Grammar / lognormal.Hand object; model
    "grammar" = frozen v4 + trace, "lognormal" =
    kinematic trace) → optional chain (True/"after": chain the restyled
    lines; "before": chain the skeleton, restyle the single line) →
    optional tremor amount. "learned" uses structure_hand's TopologyModel
    (default: the hand's own). Deterministic in rng; inputs never mutated.
    meta["composite"] records stages and seconds per stage."""
    t0 = time.perf_counter()
    s_seed, r_seed, t_seed = (int(x) for x in rng.integers(0, 2 ** 31, 3))
    named = isinstance(hand, str)
    st = structure_of(structure, structure_hand or (hand if named else None), np.random.default_rng(s_seed), size,
                      structure_params)
    t1 = time.perf_counter()
    g = hand if not named else grammar(hand) if model == "grammar" else ln_hand(hand)
    hname = hand if named else getattr(hand, "name", "")
    src = "trace" if model == "grammar" else "trace_ln"
    R = st.ref_length()
    cm = {}
    if chain == "before":
        sk = chain_paths(st, at_crossings=at_crossings, max_retrace=max_retrace)
        cm = sk.meta.get("chain", {})
        o = rs.restyle_drawing(sk, g, amount=amount, seed=r_seed, method=method, source=src,
                               ref_length=R, scale=scale, weld=False)
        t2 = t3 = time.perf_counter()
    else:
        o = rs.restyle_drawing(st, g, amount=amount, seed=r_seed, method=method, source=src,
                               ref_length=R, scale=scale, weld=weld)
        t2 = time.perf_counter()
        if chain:
            o = chain_paths(o, at_crossings=at_crossings, max_retrace=max_retrace)
            cm = o.meta.get("chain", {})
        t3 = time.perf_counter()
    note = ""
    if tremor:
        o, note = _tremor(o, hname, np.random.default_rng(t_seed), float(tremor))
    t4 = time.perf_counter()
    kind = structure if isinstance(structure, str) else "given"
    return Drawing(o.strokes, source=f"composite:{kind}:{hname}:{model}:{amount:g}", size=st.size,
                   meta={"composite": {"structure": kind, "hand": hname, "model": model, "amount": amount,
                                       "chain": chain, "tremor": tremor, "tremor_note": note,
                                       "n_structure": len(st.strokes), "n_out": len(o.strokes),
                                       "chain_meta": cm, "welds": o.meta.get("restyle", {}).get("welds"),
                                       "sec": {"structure": t1 - t0, "restyle": t2 - t1,
                                               "chain": t3 - t2, "tremor": t4 - t3}},
                         "structure_meta": {k: v for k, v in st.meta.items() if k in ("kind", "params", "coverage")}})


def real_structure(art: str, stem: str, size: int = 1200) -> Drawing:
    """A real drawing's long strokes (the grammar's training domain), fitted
    into a size-px canvas with a 4 % margin."""
    d = gm.long_drawing(Drawing.load(EXTRACT / art / f"{stem}.json"))
    P = np.vstack([s.points for s in d.strokes])
    lo, hi = P.min(0), P.max(0)
    m = 0.04 * size
    k = (size - 2 * m) / max(float((hi - lo).max()), 1e-9)
    off = m + 0.5 * ((size - 2 * m) - (hi - lo) * k)
    return Drawing([Stroke((s.points - lo) * k + off, closed=s.closed) for s in d.strokes],
                   source=f"real:{art}:{stem}", size=(size, size))


# ---------------------------------------------------------------------------
# measurement helpers (shared with restyle_study's conventions)
# ---------------------------------------------------------------------------

TEXTURE_GROUPS = ("k", "ext", "infl", "turn", "cl")


def feats(d: Drawing) -> dict:
    from gesture import medium, panel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W)
    return f


def with_width(d: Drawing, wr: float) -> Drawing:
    R = d.ref_length()
    return Drawing([Stroke(s.points, width=np.full(len(s), wr * R), closed=s.closed) for s in d.strokes
                    if len(s) >= 2], source=d.source, size=d.size)


def w_common() -> float:
    ws = []
    for art in ARTISTS:
        ws += [d["w_over_R"] for d in grammar(art).drawings if d["w_over_R"] > 0]
    return float(np.median(ws))


def _real_job(args):
    art, path = args
    d = gm.long_drawing(Drawing.load(path))
    if len(d.strokes) < 2:
        return None
    return art, Path(path).stem, feats(d)


def real_feats() -> list:
    p = OUT / "real_feats.json"
    if p.exists():
        return [tuple(r) for r in json.loads(p.read_text())]
    OUT.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(JOBS) as ex:
        real = [r for r in ex.map(_real_job, [(a, str(q)) for a in ARTISTS
                                              for q in sorted((EXTRACT / a).glob("*.json"))]) if r]
    p.write_text(json.dumps(real))
    return real


class PairClassifier:
    """Logistic regression on texture panel features of REAL long-stroke
    drawings of two hands, standard preprocessing (σ ≥ 7 w floor in `feats`
    + medium projection)."""

    def __init__(self, real, a: str, b: str, seed: int = 0):
        from sklearn.linear_model import LogisticRegression

        from gesture import medium, panel
        real = [r for r in real if r[0] in (a, b)]
        allk = set.intersection(*[set(f) for _a, _s, f in real])
        self.names = sorted(n for n in allk if panel.group_of(n) in TEXTURE_GROUPS)
        X = self.matrix([f for _a, _s, f in real])
        ok = ~np.all(np.isnan(X), axis=0)
        self.names = [n for n, o in zip(self.names, ok) if o]
        X = X[:, ok]
        art = np.array([r[0] for r in real])
        lut = medium.load_media()
        med = np.array([lut.get((r[0], r[1]), "unknown") for r in real])
        self.pj = medium.MediumProjector(medium.load_pairs(), seed=seed).fit(X, art, med)
        self.Z, self.y = self.pj.transform(X), (art == a).astype(int)
        self.a, self.b = a, b
        self.clf = LogisticRegression(C=0.3, max_iter=5000).fit(self.Z, self.y)

    def matrix(self, fs):
        return np.array([[f.get(n, np.nan) for n in self.names] for f in fs], dtype=float)

    def score(self, fs) -> np.ndarray:
        """P(hand a) per feature dict."""
        return self.clf.predict_proba(self.pj.transform(self.matrix(fs)))[:, 1]

    def cv_pairwise(self, seed: int = 0, n_pairs: int = 400) -> tuple[float, float]:
        """(CV accuracy, CV pairwise accuracy: random held-out real a vs real b)."""
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import StratifiedKFold, cross_val_predict
        p = cross_val_predict(LogisticRegression(C=0.3, max_iter=5000), self.Z, self.y,
                              cv=StratifiedKFold(5, shuffle=True, random_state=seed), method="predict_proba")[:, 1]
        acc = float(np.mean((p > 0.5) == self.y))
        rng = np.random.default_rng(seed)
        ia, ib = np.where(self.y == 1)[0], np.where(self.y == 0)[0]
        pa, pb = p[rng.choice(ia, n_pairs)], p[rng.choice(ib, n_pairs)]
        return acc, float(np.mean(pa > pb) + 0.5 * np.mean(pa == pb))


# ---------------------------------------------------------------------------
# pairwise hand test (panel)
# ---------------------------------------------------------------------------

def pair_structures(n_tree: int, n_learned: int, size: int = 1200) -> dict[str, Drawing]:
    S = {}
    for i in range(n_tree):
        rng = np.random.default_rng([31, i])
        prm = {"depth": int(3 + i % 3), "fill": float(0.7 + 0.1 * (i % 3)), "trunks": int(1 + (i // 3) % 3)}
        S[f"tree{i:02d}"] = topology.generate_structure(None, rng, size, kind="oehlen_tree", **prm)
    for i in range(n_learned):
        art = ARTISTS[i % 3]
        S[f"learned_{art}{i:02d}"] = topology.generate_structure(topo_model(art), np.random.default_rng([32, i]),
                                                                 size, kind="learned")
    return S


def _pair_job(args):
    name, d, hand, amount, seed, wr, model, chain = args
    t0 = time.time()
    g = grammar(hand) if model == "grammar" else ln_hand(hand)
    o = rs.restyle_drawing(d, g, amount=amount, seed=seed, source="trace" if model == "grammar" else "trace_ln")
    if chain:
        o = chain_paths(o)
    return {"src": name, "hand": hand, "amount": amount, "model": model, "chain": bool(chain),
            "time": time.time() - t0, "feats": feats(with_width(o, wr))}


def _gen_job(args):
    hand, seed, wr = args
    d = gm.generate_drawing(grammar(hand), np.random.default_rng(seed), (1200, 1200))
    return hand, feats(with_width(d, wr))


def cmd_pairwise(a):
    OUT.mkdir(parents=True, exist_ok=True)
    real = real_feats()
    wr = w_common()
    S = pair_structures(a.n_tree, a.n_learned)
    amounts = [float(x) for x in a.amounts.split(",")]
    models = a.models.split(",")
    jobs = [(n, d, h, amt, a.seed, wr, m, False) for n, d in S.items() for h in ARTISTS for amt in amounts
            for m in models]
    cache = OUT / "pairwise_rows.jsonl"
    done = {}
    if cache.exists():
        for line in cache.read_text().splitlines():
            try:
                r = json.loads(line)
                done[r["key"]] = r
            except Exception:  # noqa: BLE001
                pass
    key = lambda j: f"{j[0]}|{j[2]}|{j[3]:g}|{j[6]}|{j[4]}"   # noqa: E731
    todo = [j for j in jobs if key(j) not in done]
    print(f"pairwise: {len(S)} structures, {len(done)} cached, {len(todo)} to run", flush=True)
    t0 = time.time()
    from concurrent.futures import as_completed
    with ProcessPoolExecutor(JOBS) as ex, open(cache, "a") as fh:
        futs = {ex.submit(_pair_job, j): key(j) for j in todo}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            r["key"] = futs[f]
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            done[r["key"]] = r
            if i % 20 == 0:
                print(f"  {i}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    rows = [done[key(j)] for j in jobs]
    with ProcessPoolExecutor(JOBS) as ex:
        gens = list(ex.map(_gen_job, [(h, 500 + i, wr) for h in ARTISTS for i in range(a.n_gen)]))
    rep = {"n_structures": len(S), "amounts": amounts, "models": models, "w_common": wr, "pairs": []}
    from scipy.stats import binomtest
    for A, B in (("matisse", "hokusai"), ("matisse", "ingres"), ("hokusai", "ingres")):
        pc = PairClassifier(real, A, B)
        cv, cvp = pc.cv_pairwise()
        gA = [f for h, f in gens if h == A]
        gB = [f for h, f in gens if h == B]
        sA, sB = pc.score(gA), pc.score(gB)
        gen_pair = float(np.mean(sA[:, None] > sB[None, :]))
        ent = {"A": A, "B": B, "n_real": int(len(pc.y)), "n_feat": len(pc.names), "cv_acc": cv,
               "cv_pairwise_real": cvp, "gen_pairwise": gen_pair, "cells": []}
        for m in models:
            for amt in amounts:
                for fam in ("all", "tree", "learned"):
                    ok, n, margins = 0, 0, []
                    for name in S:
                        if fam != "all" and not name.startswith(fam):
                            continue
                        ra = next(r for r in rows if r["src"] == name and r["hand"] == A and r["amount"] == amt
                                  and r["model"] == m)
                        rb = next(r for r in rows if r["src"] == name and r["hand"] == B and r["amount"] == amt
                                  and r["model"] == m)
                        pa, pb = pc.score([ra["feats"], rb["feats"]])
                        ok += int(pa > pb)
                        n += 1
                        margins.append(float(pa - pb))
                    if n:
                        ent["cells"].append({"model": m, "amount": amt, "family": fam, "n": n, "acc": ok / n,
                                             "p_binom": float(binomtest(ok, n, 0.5, alternative="greater").pvalue),
                                             "margin_med": float(np.median(margins))})
        rep["pairs"].append(ent)
    rep["time_med"] = {f"{m}@{amt:g}": float(np.median([r["time"] for r in rows if r["model"] == m
                                                         and r["amount"] == amt])) for m in models for amt in amounts}
    (OUT / "pairwise.json").write_text(json.dumps(rep, indent=1))
    md = pairwise_md(rep)
    (OUT / "pairwise.md").write_text(md)
    print(md)


def pairwise_md(rep) -> str:
    L = ["| # | pair (A vs B) | model | amount | family | n | pairwise acc | p (> 0.5) | median P_A margin |",
         "|---|---|---|---|---|---|---|---|---|"]
    k = 0
    for e in rep["pairs"]:
        for c in e["cells"]:
            k += 1
            L.append(f"| P{k} | {e['A']} vs {e['B']} | {c['model']} | {c['amount']:g} | {c['family']} | {c['n']} | "
                     f"{c['acc']:.2f} | {c['p_binom']:.3f} | {c['margin_med']:+.3f} |")
    L += ["", "| # | pair | real drawings | features | real CV acc | real held-out pairwise acc | grammar-v4 own drawings pairwise |",
          "|---|---|---|---|---|---|---|"]
    for i, e in enumerate(rep["pairs"], 1):
        L.append(f"| C{i} | {e['A']} vs {e['B']} | {e['n_real']} | {e['n_feat']} | {e['cv_acc']:.2f} | "
                 f"{e['cv_pairwise_real']:.2f} | {e['gen_pairwise']:.2f} |")
    L.append("")
    L.append("Restyle seconds per drawing (median): " + ", ".join(f"{k} {v:.2f}" for k, v in rep["time_med"].items()))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# rendering + sheets
# ---------------------------------------------------------------------------

def render_cell(d: Drawing, size: int, lw: float = 1.4, frame: Drawing | None = None) -> np.ndarray:
    """Render into a size² image; `frame` (default d) fixes the bbox → the
    same structure lands on the same pixels in every hand."""
    from gesture import synth
    ref = frame if frame is not None else d
    pts = np.vstack([s.points for s in ref.strokes if len(s)])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    m = 0.05 * size
    sc = (size - 2 * m) / max(float(np.max(hi - lo)), 1e-9)
    off = m + 0.5 * ((size - 2 * m) - (hi - lo) * sc)
    ss = [Stroke((s.points - lo) * sc + off, closed=s.closed) for s in d.strokes if len(s) >= 2]
    return synth.render(Drawing(ss, size=(size, size)), line_width=lw, paper_noise=0.0,
                        blur_sigma=0.4, use_stroke_width=False)


def _label(img, text):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((6, 4), text, fill=60)
    return np.asarray(im)


def _cell_job(args):
    spec, size = args
    kind = spec["kind"]
    if kind == "structure":
        d = spec["drawing"]
        lab = spec["label"] + f" [{len(d.strokes)} lines]"
        return _label(render_cell(d, size), lab), {"label": lab}
    d = composite(spec["structure"], spec["hand"], np.random.default_rng(spec["seed"]), size=1200,
                  amount=spec["amount"], chain=spec.get("chain", False), model=spec.get("model", "grammar"),
                  structure_params=spec.get("params"), structure_hand=spec.get("structure_hand"),
                  at_crossings=spec.get("at_crossings", False), tremor=spec.get("tremor"),
                  max_retrace=spec.get("max_retrace"))
    c = d.meta["composite"]
    lab = spec["label"] + f" [{c['n_out']} path{'s' if c['n_out'] != 1 else ''}]"
    if c["chain_meta"]:
        lab += f" retrace {c['chain_meta']['retrace_R'] / max(c['chain_meta']['ink_R'], 1e-9):.0%}"
    if spec.get("big"):
        from PIL import Image
        Image.fromarray(render_cell(d, 1200, lw=2.0)).save(spec["big"], quality=90)
    return _label(render_cell(d, size), lab), {"label": lab, "sec": c["sec"], "n_out": c["n_out"],
                                               "chain": c["chain_meta"]}


def grid_sheet(rows, path: Path, size: int) -> list:
    from PIL import Image
    flat = [s for r in rows for s in r]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_cell_job, [(s, size) for s in flat], chunksize=1))
    ncol = max(len(r) for r in rows)
    sheet = np.full((size * len(rows), size * ncol), 255, np.uint8)
    k = 0
    for i, r in enumerate(rows):
        for j in range(len(r)):
            sheet[i * size:(i + 1) * size, j * size:(j + 1) * size] = res[k][0]
            sheet[i * size:(i + 1) * size, j * size] = 190
            k += 1
        sheet[i * size, :] = 190
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet).save(path, quality=90)
    print("wrote", path, flush=True)
    return [m for _i, m in res]


TREE_LEVELS = (("simple", {"depth": 3, "trunks": 1, "fill": 0.6}),
               ("medium", {"depth": 4, "trunks": 2, "fill": 0.8}),
               ("complex", {"depth": 5, "trunks": 3, "fill": 0.92}))


def cmd_sheets(a):
    OUT.mkdir(parents=True, exist_ok=True)
    sd = OUT / "sheets"
    sd.mkdir(parents=True, exist_ok=True)
    size, amt = a.size, a.amount
    log = {}
    which = set(a.which.split(","))
    # (i)/(ii) Oehlen-tree complexity × hands, chain off / on
    # chained: chain="before" — one continuous line through the skeleton, redrawn
    # by the hand (chain="after" retraces exactly and looks identical to "trees")
    for tag, chain in (("trees", False), ("trees-chained", "before")):
        if tag not in which:
            continue
        rows = []
        for lvl, prm in TREE_LEVELS:
            seed = 100 + len(rows)
            st = topology.generate_structure(None, np.random.default_rng(
                np.random.default_rng(seed).integers(0, 2 ** 31, 3)[0]), 1200, kind="oehlen_tree", **prm)
            r = [{"kind": "structure", "drawing": st, "label": f"tree {lvl} (skeleton)"}]
            r += [{"kind": "comp", "structure": "oehlen_tree", "params": prm, "hand": h, "seed": seed,
                   "amount": amt, "chain": chain, "label": f"{h} {amt:g}{' chained' if chain else ''}",
                   "big": str(sd / f"big-{tag}-{lvl}-{h}.jpg")} for h in ARTISTS]
            if chain:
                r.append({"kind": "comp", "structure": "oehlen_tree", "params": prm, "hand": "matisse",
                          "seed": seed, "amount": amt, "chain": chain, "max_retrace": 0.15,
                          "label": f"matisse {amt:g} chained, retrace<=15%"})
            rows.append(r)
        log[tag] = grid_sheet(rows, sd / f"composite-{tag}.jpg", size)
    # (iii) learned-topology composites per hand (own topology), 2 seeds; plus chained
    if "learned" in which:
        rows = []
        for h in ARTISTS:
            r = []
            for sdx in (1, 2):
                r.append({"kind": "comp", "structure": "learned", "hand": h, "seed": 200 + sdx, "amount": amt,
                          "label": f"{h} topology+hand s{sdx}"})
            r.append({"kind": "comp", "structure": "learned", "hand": h, "seed": 201, "amount": amt,
                      "chain": True, "at_crossings": True, "label": f"{h} s1 chained@X"})
            r.append({"kind": "comp", "structure": "learned", "hand": h, "seed": 201, "amount": amt,
                      "model": "lognormal", "label": f"{h} s1 lognormal hand"})
            rows.append(r)
        log["learned"] = grid_sheet(rows, sd / "composite-learned.jpg", size)
    # (iv) translation: a real drawing's long strokes → the other hands
    if "translation" in which:
        rows = []
        for src in a.translate.split(","):
            art, stem = src.split(":")
            st = real_structure(art, stem)
            r = [{"kind": "structure", "drawing": st, "label": f"real {art} {stem} (long strokes)"}]
            r += [{"kind": "comp", "structure": st, "hand": h, "seed": 300, "amount": amt,
                   "label": f"-> {h} {amt:g}", "big": str(sd / f"big-translation-{stem}-{h}.jpg")} for h in ARTISTS]
            r += [{"kind": "comp", "structure": st, "hand": h, "seed": 300, "amount": amt, "chain": "before",
                   "label": f"-> {h} chained skeleton"} for h in ARTISTS if h != art][:1]
            rows.append(r)
        log["translation"] = grid_sheet(rows, sd / "composite-translation.jpg", size)
    # model comparison: tree into each hand, grammar vs lognormal, single line
    if "models" in which:
        prm = TREE_LEVELS[1][1]
        rows = []
        for h in ARTISTS:
            rows.append([{"kind": "comp", "structure": "oehlen_tree", "params": prm, "hand": h, "seed": 101,
                          "amount": amt, "model": m, "chain": c,
                          "label": f"{h} {m}{' chained' if c else ''}"}
                         for m in ("grammar", "lognormal") for c in (False, True)])
        log["models"] = grid_sheet(rows, sd / "composite-models.jpg", size)
    old = json.loads((sd / "sheets_log.json").read_text()) if (sd / "sheets_log.json").exists() else {}
    old.update(log)
    (sd / "sheets_log.json").write_text(json.dumps(old, indent=1, default=float))


# ---------------------------------------------------------------------------
# judge pairs
# ---------------------------------------------------------------------------

SIDE, LW, CROP, SMOOTH = 1200, 3.0, 480, 5.0


def _fit(d: Drawing, frame: Drawing | None = None) -> Drawing:
    """blind_pairs.fit_canvas logic (copied: that file is read-only), with a
    shared frame so two hands of one structure land on the same pixels."""
    from gesture.curvature import resample, smooth
    ref = frame if frame is not None else d
    P = np.vstack([s.points for s in ref.strokes])
    lo, hi = P.min(0), P.max(0)
    k = (SIDE - 80) / max((hi - lo).max(), 1e-9)
    st = []
    for s in d.strokes:
        q = (s.points - lo) * k + 40
        if len(q) >= 3:
            r = resample(q, 1.0, closed=s.closed)
            if len(r) >= 5:
                q = smooth(r, SMOOTH, 1.0, closed=s.closed)
        L = float(np.sum(np.linalg.norm(np.diff(q, axis=0), axis=1))) if len(q) > 1 else 0.0
        chord = float(np.linalg.norm(q[-1] - q[0])) if len(q) > 1 else 0.0
        if L > 0.25 * SIDE and chord > 0.995 * L:
            continue                                   # plate marks
        st.append(Stroke(q, closed=s.closed))
    W, H = (np.ceil((hi - lo) * k) + 80).astype(int)
    return Drawing(st, size=(int(W), int(H)))


def _render(d: Drawing) -> np.ndarray:
    from gesture import synth
    return synth.render(d, line_width=LW, use_stroke_width=False, paper_noise=0.0, blur_sigma=0.6, seed=1)


def _crop_xy(imgs, rng, min_ink=0.012, tries=300):
    H = min(i.shape[0] for i in imgs)
    W = min(i.shape[1] for i in imgs)
    best = None
    for _ in range(tries):
        y = int(rng.integers(0, max(H - CROP, 1)))
        x = int(rng.integers(0, max(W - CROP, 1)))
        cs = [i[y:y + CROP, x:x + CROP] for i in imgs]
        if any(c.shape != (CROP, CROP) for c in cs):
            continue
        ink = min(float((c < 128).mean()) for c in cs)
        if ink >= min_ink:
            return cs
        if best is None or ink > best[0]:
            best = (ink, cs)
    return best[1] if best else None


def _pair_panel(a, b, refM, refH):
    from PIL import Image, ImageDraw
    rs_ = 300
    im = Image.new("L", (2 * CROP + 60, CROP + 60 + rs_ + 40), 255)
    dr = ImageDraw.Draw(im)
    im.paste(Image.fromarray(a), (20, 30))
    im.paste(Image.fromarray(b), (CROP + 40, 30))
    dr.text((20 + CROP // 2, 10), "A", fill=0)
    dr.text((CROP + 40 + CROP // 2, 10), "B", fill=0)
    dr.line([(CROP + 30, 30), (CROP + 30, CROP + 30)], fill=180)
    y0 = CROP + 70
    dr.line([(10, y0 - 15), (2 * CROP + 50, y0 - 15)], fill=200)
    for k, (ref, txt) in enumerate(((refM, "reference: real Matisse"), (refH, "reference: real Hokusai"))):
        x0 = 20 + k * (CROP + 20)
        im.paste(Image.fromarray(ref).resize((rs_, rs_), Image.LANCZOS), (x0, y0 + 20))
        dr.text((x0, y0), txt, fill=0)
    return im


def cmd_judge(a):
    from collections import Counter
    rng = np.random.default_rng(a.seed)
    out = OUTROOT / "blind_hand" / "pairs"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()
    reals = {}
    for art in ("matisse", "hokusai"):
        imgs = []
        for p in sorted((EXTRACT / art).glob("*.json")):
            ld = gm.long_drawing(Drawing.load(p))
            if len(ld.strokes) >= 3:
                imgs.append(_render(_fit(ld)))
        reals[art] = imgs
    print("real renders", {k: len(v) for k, v in reals.items()}, flush=True)

    def real_crop(art, avoid=()):
        imgs = reals[art]
        j = int(rng.choice([i for i in range(len(imgs)) if i not in avoid] or range(len(imgs))))
        return _crop_xy([imgs[j]], rng)[0], j

    # composites: structure → Matisse and Hokusai (and Matisse twice for calib_neg)
    specs = []
    for i in range(a.n_test + a.n_neg):
        kind = "oehlen_tree" if i % 2 == 0 else "learned"
        sh = ("matisse", "hokusai", "ingres")[i % 3]
        st = structure_of(kind, sh, np.random.default_rng([41, i]), 1200,
                          TREE_LEVELS[i % 3][1] if kind == "oehlen_tree" else None)
        specs.append((i, kind, sh, st))
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_judge_job, [(i, st, a.amount, i >= a.n_test) for i, _k, _s, st in specs]))
    jobs = []
    for (i, kind, sh, st), (imgA, imgB) in zip(specs, res):
        cs = _crop_xy([imgA, imgB], rng)
        if cs is None:
            continue
        cond = "test" if i < a.n_test else "calib_neg"
        refM, jm = real_crop("matisse")
        refH, _ = real_crop("hokusai")
        jobs.append((cond, f"{kind}:{sh}", cs[0], cs[1], refM, refH))
    for i in range(a.n_pos):
        m, jm = real_crop("matisse")
        h, jh = real_crop("hokusai")
        refM, _ = real_crop("matisse", avoid=(jm,))
        refH, _ = real_crop("hokusai", avoid=(jh,))
        jobs.append(("calib_pos", "real", m, h, refM, refH))
    order = rng.permutation(len(jobs))
    key = {}
    for n, j in enumerate(order, 1):
        cond, what, m, other, refM, refH = jobs[j]
        m_left = bool(rng.integers(2))
        img = _pair_panel(m, other, refM, refH) if m_left else _pair_panel(other, m, refM, refH)
        name = f"pair_{n:03d}.png"
        img.save(out / name)
        ans = ("A" if m_left else "B") if cond != "calib_neg" else "none (both Matisse)"
        key[name] = {"condition": cond, "structure": what, "matisse": ans,
                     "other": "hokusai" if cond != "calib_neg" else "matisse (other seed)"}
    Path(a.key).write_text(json.dumps(key, indent=1))
    print(len(key), "pairs ->", out, "| key ->", a.key, "|", dict(Counter(v["condition"] for v in key.values())))


def _judge_job(args):
    i, st, amount, neg = args
    R = st.ref_length()
    gM = grammar("matisse")
    oM = rs.restyle_drawing(st, gM, amount=amount, seed=1000 + i, source="trace", ref_length=R)
    oB = rs.restyle_drawing(st, gM if neg else grammar("hokusai"), amount=amount,
                            seed=(2000 + i) if neg else (1000 + i), source="trace", ref_length=R)
    return _render(_fit(oM, st)), _render(_fit(oB, st))


# ---------------------------------------------------------------------------
# bench
# ---------------------------------------------------------------------------

def cmd_bench(a):
    rows = []
    for kind, prm in (("oehlen_tree", TREE_LEVELS[0][1]), ("oehlen_tree", TREE_LEVELS[1][1]),
                      ("oehlen_tree", TREE_LEVELS[2][1]), ("learned", None)):
        for model in ("grammar", "lognormal"):
            for chain in (False, True):
                for h in ARTISTS:
                    d = composite(kind, h, np.random.default_rng(7), amount=a.amount, chain=chain, model=model,
                                  structure_params=prm)
                    c = d.meta["composite"]
                    rows.append({"kind": kind, "params": prm, "model": model, "chained": chain, "hand": h,
                                 "n_structure": c["n_structure"], "n_out": c["n_out"], **c["sec"],
                                 "retrace": (c["chain_meta"] or {}).get("retrace_R", 0.0) /
                                 max((c["chain_meta"] or {}).get("ink_R", 1.0), 1e-9)})
                    print(rows[-1], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bench.json").write_text(json.dumps(rows, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("pairwise")
    q.add_argument("--n-tree", type=int, default=15)
    q.add_argument("--n-learned", type=int, default=15)
    q.add_argument("--amounts", default="0.5,0.8")
    q.add_argument("--models", default="grammar")
    q.add_argument("--n-gen", type=int, default=8)
    q.add_argument("--seed", type=int, default=1)
    s = sp.add_parser("sheets")
    s.add_argument("--size", type=int, default=400)
    s.add_argument("--amount", type=float, default=0.7)
    s.add_argument("--which", default="trees,trees-chained,learned,translation,models")
    s.add_argument("--translate", default="matisse:KKS1971-302,matisse:KKS13418_2,hokusai:57263")
    j = sp.add_parser("judge")
    j.add_argument("--n-test", type=int, default=30)
    j.add_argument("--n-neg", type=int, default=10)
    j.add_argument("--n-pos", type=int, default=10)
    j.add_argument("--amount", type=float, default=0.8)
    j.add_argument("--seed", type=int, default=5)
    j.add_argument("--key", default="/tmp/gesture_hand_key.json")
    b = sp.add_parser("bench")
    b.add_argument("--amount", type=float, default=0.7)
    a = p.parse_args(argv)
    {"pairwise": cmd_pairwise, "sheets": cmd_sheets, "judge": cmd_judge, "bench": cmd_bench}[a.cmd](a)


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    main()

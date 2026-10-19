# FROZEN from research commit 9ab70ac: tools/gesture/gesture/kit/voices_passage.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Study B: a continuous line passing through many real learned hands.

Every source runs its own order-2 chain. Corner magnitude/presence, bend,
handedness and length are taken whole from four named source segments, as in
handover; numbers from different hands are never averaged. Unequal sections
hold a source, pass its features gradually, jump, hold a split specimen, or
keep three/four sources speaking together. Joint timing, grammar distance and
discrete echoes of older paper make the schedule aware of its own line.

The optional opening is the exact accrue 3966 wire geometry, translated only.
The continuation selects K chunks toward a boustrophedon route. Composed
segments are integrated separately: grammar.tokens_to_points normally carries
the previous token's curvature across a smooth joint, which would undo a
selected bend. No clipping/refitting, ribbon or extra marks are involved.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from ._research import grammar as gm
from . import voices_accrue as va
from . import voices_gmorph as vm
from . import voices_handover as vh
from .core import P, Mark, channel_kind, voice

FEATURES = vh.FEATURES
HANDS = ["meander69", "fly_open", "river_belt", "hokusai", "dance_staccato", "mime_roadrunner"]
SECTION_CODES = {"opening": -1, "hold": 0, "glide": 1, "jolt": 2, "split": 3, "many": 4, "recall": 5}
for _name in (*("src_" + f for f in FEATURES), "voice", "section", "n_sources"):
    channel_kind(_name, "nearest")


def compose(sources: list[dict], assignment: dict) -> dict:
    """N-hand version of handover.compose: bend angle survives length choice."""
    pick = {f: sources[assignment[f]] for f in FEATURES}
    bend, length, sg = pick["bend"], pick["length"]["l"], pick["turn"]["sgn"]
    ratio = bend["l"] / max(length, 1e-9)
    flip = sg * (-1.0 if bend["k0"] + bend["k1"] < 0 else 1.0)
    corner = pick["corner"]["corner"]
    return {"corner": None if corner is None else abs(corner) * sg,
            "kind": bend["kind"], "l": length, "k0": bend["k0"] * ratio * flip,
            "k1": bend["k1"] * ratio * flip, "sgn": sg}


# The artist's kept accrue free hand (river_belt, seed 3966): entry [2] of
# results/accrue-3-variants.recipe.json, voice params minus id/hand, copied
# verbatim so the opening never reads results/ at run time.
FREE_RECIPE = "tools/gesture/results/accrue-3-variants.recipe.json"
FREE_VOICE = {
    'length': 9.0,
    'scale': 0.45,
    'K': 8,
    'step': 0.3,
    'chunk': 0.06,
    'clear': 2.0,
    'h0': 0.3,
    'h_len': 0.25,
    'h_use': 1.5,
    'lam': 0.08,
    'c_max': 32.0,
    'habit': 'loops',
    'c0': 3.0,
    'grow': 0.45,
    'learn': 1.0,
    'relapse': 0.5,
    'knot_len': 14.0,
    'relapse_turn': 3.1416,
    'c_rate': 1.0,
    'keep': 0.0,
    'transfer': 4.0,
    'spin_half': 35.0,
    'release': 40.0,
    'release_damp': 0.35,
    'press_r': 3.0,
    'press_on': 0.45,
    'press_hold': 30.0,
    'tire': 0.35,
    'exhaust': 2,
    'recall': 6.0,
    'recall_gap': 150.0,
    'mix': 0.8,
    'stereo': 0.6,
    'route': 'ltr',
    'pull': 6.0,
    'look': 15.0,
    'edge_k': 40.0,
}


def free_opening(g, box, free_seed: int = 3966):
    """Exact half-A4 accrue recipe, evaluated at origin then translated only.

    A smaller box is refused rather than silently rescaling Ian's chosen line.
    All parameters come from the recorded row (FREE_VOICE), including its fixed
    sample step.
    """
    x0, y0, w, h = box
    if w < 285 - 1e-8 or h <= 93:
        raise ValueError("passage: opening=free needs a box at least 285 mm wide and over 93 mm high")
    kw = dict(FREE_VOICE)
    R = kw.pop("scale") * 0.95 * float(np.hypot(285, 93))
    pts, _channels, events = va.walk(g, np.random.default_rng([int(free_seed), 0xACC0E]),
                                    R=R, box=(0, 0, 285, 93), **kw)
    return pts + [x0, y0], {"kind": "free", "seed": int(free_seed), "hand": "river_belt",
                            "points": len(pts), "length_mm": events["length_mm"], "R_mm": R,
                            "offset": [float(x0), float(y0)], "recipe": FREE_RECIPE}


def character_distances(grammars, tables):
    """Length/turn quantiles, corner share and same-way persistence; whitened."""
    vectors = []
    for g, tab in zip(grammars, tables):
        signs = []
        persistence = []
        for toks in g.strokes:
            signs.clear()
            for s in vh.segments(toks):
                tr = (s["k0"] + s["k1"]) * s["l"] * 0.5
                if abs(tr) > 0.02 or s["corner"] is not None:
                    signs.append(s["sgn"])
            persistence.extend(float(a == b) for a, b in zip(signs[:-1], signs[1:]))
        qs = lambda vals: np.quantile(vals, [0.2, 0.5, 0.8]) if len(vals) else np.zeros(3)
        vectors.append([*np.log(np.maximum(qs(tab["segl"]), 1e-6)),
                        *np.log1p(qs(tab["turn"])), tab["corner_share"],
                        float(np.mean(persistence)) if persistence else 0.5])
    v = np.asarray(vectors)
    v = (v - v.mean(axis=0)) / np.maximum(v.std(axis=0), 0.1)
    d = np.linalg.norm(v[:, None] - v[None, :], axis=2)
    return d / max(float(d.max()), 1e-9), vectors


class Streams:
    """Lazy independent stream reservoirs; tables and morphed runs are cached.

    Selection draws contiguous slices of real chains, not nearest-token lookup.
    A cache is local to one drawing; no shared state survives recipes/processes.
    """
    def __init__(self, grammars, tables, seed):
        self.grammars, self.tables, self.seed = grammars, tables, seed
        self.banks = {}
        self.morph_batches = 0

    def take(self, plan, n):
        dials = plan["dials"]
        key = (plan["id"], tuple(dials.values()) if dials else ())
        if key not in self.banks:
            self.banks[key] = [(np.random.default_rng([int(self.seed), 0xBA4C, plan["id"], j]), [])
                               for j in range(len(self.grammars))]
        result = []
        for j, (rng, buf) in enumerate(self.banks[key]):
            while len(buf) < n:
                if not dials:
                    buf.extend(vh.stream(self.grammars[j], rng, max(32, n)))
                else:
                    # Draw enough for many proposals once, rather than morphing K times.
                    tab = self.tables[j]
                    mean = float(np.median(tab["segl"])) if len(tab["segl"]) else 0.05
                    toks, _ = vm.morph_tokens(self.grammars[j], rng,
                                             length=max(0.5, mean * max(40, n)),
                                             sched={k: [0.0, v] for k, v in dials.items()},
                                             focus=0.18, knn=24, tab=tab)
                    got = vh.segments(toks)
                    buf.extend(got or vh.stream(self.grammars[j], rng, max(32, n)))
                    self.morph_batches += 1
            result.append(buf[:n])
            del buf[:n]
        return [[result[j][i] for j in range(len(result))] for i in range(n)]


def _majority(assignment, n):
    return int(np.argmax(np.bincount(list(assignment.values()), minlength=n)))


def _new_plan(rng, *, index, assignment, recent, distances, hands, erratic, many,
              specimen, section_length, asym, aware, malleable, echo=None):
    n = len(hands)
    current = _majority(assignment, n)
    kinds = ("hold", "glide", "jolt", "split", "many")
    weights = np.array([0.22, 0.8 * (1 - erratic), 0.8 * erratic, 1.2 * specimen, 1.6 * many])
    kind = "recall" if echo is not None else str(rng.choice(kinds, p=weights / weights.sum()))
    # Near/far affects probability, never any numeric feature of a hand.
    proximity = distances[current]
    w = np.exp(aware * (4 * proximity if kind == "jolt" else -3 * proximity))
    for age, hand in enumerate(reversed(recent[-6:])):
        w[hand] *= (0.35 + 0.08 * age) ** aware
    w[current] = 0
    target = int(rng.choice(n, p=w / w.sum()))
    sigma = 0.06 + 1.15 * asym
    count = int(np.clip(rng.lognormal(np.log(section_length) - sigma * sigma / 2, sigma), 2, 5 * section_length))
    count = max(2, int(count * (1 - 0.3 * erratic)))
    pool = [target]
    base = dict(assignment)
    if kind == "glide":
        count = max(count, 10)
    elif kind == "jolt":
        count = int(rng.integers(1, 3))
        base = dict.fromkeys(FEATURES, target)
    elif kind == "hold":
        base = dict.fromkeys(FEATURES, target)
    elif kind == "split":
        a, b = current, target
        # The kept specimen family is part of the vocabulary, alongside other pairs.
        if "meander69" in hands and "fly_open" in hands and rng.random() < 0.65:
            a, b = hands.index("meander69"), hands.index("fly_open")
        pattern = ((a, b, a, a), (a, b, b, a), (b, b, a, b))
        base = dict(zip(FEATURES, pattern[int(rng.integers(len(pattern)))]))
        pool = [a, b]
        count = max(count, 6)
    elif kind == "many":
        k = min(n, int(rng.integers(3, 5)))
        pool = [target] + [int(i) for i in rng.choice([j for j in range(n) if j != target], k - 1, replace=False)]
        values = [int(v) for v in rng.permutation(pool)]
        base = dict(zip(FEATURES, (values * 2)[:4]))
        count = max(count, 8)
    elif kind == "recall":
        base = dict(echo)
        pool = sorted(set(base.values()))
        count = max(count, 5)
    order = [FEATURES[int(i)] for i in rng.permutation(4)]
    dials = None
    if rng.random() < malleable:
        dials = {"turn": float(rng.uniform(0.12, 0.9)), "span": float(rng.uniform(0.15, 0.85)),
                 "sign": float(rng.choice([-1, 0, 1]))}
    return {"id": index, "type": kind, "count": count, "target": target, "pool": pool,
            "base": base, "from": dict(assignment), "order": order, "dials": dials,
            "align": bool(rng.random() < aware)}


def _assign(plan, state, position, rng):
    kind = plan["type"]
    out = dict(state)
    if kind == "glide":
        u = min(position / max(plan["count"] - 1, 1), 1.0)
        for rank, f in enumerate(plan["order"]):
            p = vh.share_b(u, rank * 0.19, rank * 0.19 + 0.43, 1.5)
            old = plan["from"][f]
            b = vh.step_switch(int(out[f] == plan["target"]), p, 2.0, rng)
            out[f] = plan["target"] if b else old
    elif kind == "many":
        for f in FEATURES:
            if rng.random() < 0.22:
                trial = {**out, f: int(rng.choice(plan["pool"]))}
                if len(set(trial.values())) >= 3:
                    out = trial
    else:
        out = dict(plan["base"])
    return out


def _integrate(segs, pos, heading, R, step):
    parts, ranges = [np.asarray(pos)[None, :]], []
    size = 1
    for s in segs:
        toks = vh.to_tokens([s], False)
        p, _, _ = gm.tokens_to_points(toks, R, start=pos, heading=heading, step=step)
        parts.append(p[1:])
        ranges.append((size, size + len(p) - 1))
        size += len(p) - 1
        heading = gm.end_heading(toks, heading)
        pos = p[-1]
    return np.vstack(parts), ranges, heading


def grow(grammars, *, seed, box, hands, start_points, opening_info, **p):
    """Route-selected chunks with whole-source features and strict bounds."""
    rng = np.random.default_rng([int(seed), 0xFA55A6E])
    schedule_rng = np.random.default_rng([int(seed), 0x5EC710])
    n = len(hands)
    tables = [vm.hand_tables(g) for g in grammars]
    distances, vectors = character_distances(grammars, tables)
    banks = Streams(grammars, tables, seed)
    x0, y0, w, h = box
    lo, hi = np.array([x0 + 0.2, y0 + 0.2]), np.array([x0 + w - 0.2, y0 + h - 0.2])
    has_opening = start_points is not None
    lower = (x0, y0 + 93, w, h - 93) if has_opening else box
    route = np.asarray(vh.rows_path(p["rows"], inset=0.065)).reshape(-1, 2)
    if has_opening:
        route[:, 0] = 1 - route[:, 0]
    route = route * lower[2:] + lower[:2]
    if has_opening:
        route = np.vstack([start_points[-1], route])
    route_fractions = ((route - box[:2]) / box[2:]).ravel().tolist()
    Q, C = vh._dense(route_fractions, box)
    route_length = float(C[-1])
    opening_hand = hands.index("river_belt") if "river_belt" in hands else -1
    initial = opening_hand if opening_hand >= 0 else 0
    state = dict.fromkeys(FEATURES, initial)
    if has_opening:
        points = [start_points]
        heading = float(np.arctan2(*(start_points[-1] - start_points[-2])[::-1]))
        arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(start_points, axis=0), axis=1))]
    else:
        points = [Q[:1]]
        heading = float(np.arctan2(*(Q[1] - Q[0])[::-1]))
        arc = np.zeros(1)
    arcs = [arc]
    arc_done = float(arc[-1])
    initial_mm = arc_done
    channels = {"src_" + f: [np.full(len(arc), opening_hand if has_opening else initial)] for f in FEATURES}
    channels.update({"voice": [np.full(len(arc), opening_hand if has_opening else initial)],
                     "section": [np.full(len(arc), -1 if has_opening else 0)],
                     "n_sources": [np.ones(len(arc))]})
    plan_args = {k: p[k] for k in ("erratic", "many", "specimen", "section_length", "asym", "aware", "malleable")}
    def make_plan(index, echo=None):
        return _new_plan(schedule_rng, index=index, assignment=state, recent=recent, distances=distances,
                         hands=hands, echo=echo, **plan_args)
    recent = [initial]
    plan = make_plan(0)
    state = dict(plan["base"])
    sections, log, recalls = [], [], []
    def enter(reason):
        sections.append({"type": plan["type"], "start_mm": arc_done,
                         "hands": sorted(set(state.values())), "assignment": dict(state),
                         "planned_segments": plan["count"], "dials": plan["dials"],
                         "boundary": reason, "order": plan["order"], "target": plan["target"]})
    enter("opening_end" if has_opening else "start")
    if not has_opening:
        for f in FEATURES:
            channels["src_" + f][0][:] = state[f]
        channels["voice"][0][:] = _majority(state, n)
        channels["section"][0][:] = SECTION_CODES[plan["type"]]
        channels["n_sources"][0][:] = len(set(state.values()))
    index = 0
    next_plan = None
    echo = None
    last_recall = -1e9
    wait, same_turn, last_sign = 0, 0.0, 0.0
    v, chunks, rejected = 0.0, 0, 0
    stopped = "route_end"
    while v < route_length - 0.4 * p["ahead"] and arc_done - initial_mm < p["max_mm"] and chunks < 1600:
        chunks += 1
        drawn = np.vstack(points)
        S = np.concatenate(arcs)
        lag = max(int(3 * p["clear"] / p["step"]), 5)
        tree = cKDTree(drawn[:-lag]) if len(drawn) > 2 * lag else None
        i0 = int(np.searchsorted(C, max(v - 2 * p["ahead"], 0)))
        i1 = min(int(np.searchsorted(C, v + 4 * p["ahead"])) + 1, len(Q))
        near = cKDTree(Q[i0:i1])
        target = Q[min(int(np.searchsorted(C, v + p["ahead"])), len(Q) - 1)]
        due = index >= plan["count"]
        if due and next_plan is None:
            next_plan = make_plan(len(sections), echo)
        # Boundary search uses one segment, at most four waits for a real joint.
        count = 1 if due else min(p["chunk"], plan["count"] - index)
        best = None
        for attempt in range(3):
            for _ in range(p["K"]):
                chosen_plan = plan
                start_state, start_index = dict(state), index
                reason = None
                first_assignment = None
                if due:
                    prospective = banks.take(next_plan, 1)
                    ns = _assign(next_plan, next_plan["base"], 0, rng)
                    ns_seg = compose(prospective[0], ns)
                    if not next_plan["align"] or ns_seg["corner"] is not None or same_turn >= np.pi or wait >= 4:
                        chosen_plan = next_plan
                        start_state, start_index = dict(next_plan["base"]), 0
                        sources = prospective
                        first_assignment = ns
                        reason = ("corner" if ns_seg["corner"] is not None else "turn" if same_turn >= np.pi
                                  else "cap" if wait >= 4 else "unaligned")
                    else:
                        sources = banks.take(plan, 1)
                else:
                    sources = banks.take(plan, count)
                assignments, segs = [], []
                st = start_state
                for i, src in enumerate(sources):
                    st = first_assignment if i == 0 and first_assignment is not None else _assign(chosen_plan, st, start_index + i, rng)
                    assignments.append(dict(st))
                    segs.append(compose(src, st))
                pts, ranges, head = _integrate(segs, drawn[-1], heading, p["R_mm"], p["step"])
                if np.any(pts < lo) or np.any(pts > hi):
                    rejected += 1
                    continue
                crowd = float(np.mean(tree.query(pts[1:])[0] < p["clear"])) if tree is not None else 0
                d, _ = near.query(pts[1:])
                stray = float(np.mean(np.maximum(d - p["band"], 0))) / p["R_mm"]
                score = 2 * crowd + 20 * stray + p["pull"] * np.linalg.norm(pts[-1] - target) / p["R_mm"]
                score += 0.025 * rng.random()
                if best is None or score < best[0]:
                    best = (score, pts, ranges, head, assignments, segs, sources, st, chosen_plan, reason)
            if best is not None:
                break
            count = 1  # Retry intact shorter chunks, never shrink or clip a chosen token.
        if best is None:
            stopped = "no_in_box_proposal"
            break
        _, pts, ranges, heading, assignments, segs, sources, state, chosen_plan, reason = best
        if chosen_plan is not plan:
            sections[-1]["end_mm"] = arc_done
            plan, index, wait = chosen_plan, 0, 0
            next_plan = None
            same_turn = 0.0
            echo = None
            recent.append(plan["target"])
            # The accepted first assignment, not a proposed one, is recorded.
            state = dict(assignments[0])
            enter(reason)
            if plan["type"] == "recall":
                recalls[-1]["echo_section"] = len(sections) - 1
        elif due:
            wait += len(segs)
        sp = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        local = {name: np.empty(len(pts) - 1) for name in channels}
        for i, ((a, b), assignment, seg) in enumerate(zip(ranges, assignments, segs)):
            for f in FEATURES:
                local["src_" + f][a - 1:b - 1] = assignment[f]
            local["voice"][a - 1:b - 1] = _majority(assignment, n)
            local["section"][a - 1:b - 1] = SECTION_CODES[plan["type"]]
            local["n_sources"][a - 1:b - 1] = len(set(assignment.values()))
            log.append({"s0": arc_done + float(sp[a - 1]), "s1": arc_done + float(sp[b - 1]),
                        "section": len(sections) - 1, "assignment": assignment,
                        "sources": sources[i], "segment": seg,
                        "point_start": len(drawn) + a - 1, "point_end": len(drawn) + b - 2})
            tr = 0.5 * (seg["k0"] + seg["k1"]) * seg["l"]
            if seg["corner"] is not None:
                same_turn = 0.0
            sign = float(np.sign(tr))
            same_turn = same_turn + abs(tr) if sign == last_sign else abs(tr)
            last_sign = sign
        state = dict(assignments[-1])
        for name in channels:
            channels[name].append(local[name])
        points.append(pts[1:])
        arcs.append(arc_done + sp[1:])
        arc_done += float(sp[-1])
        index += len(segs)
        used = sorted(set(sections[-1]["hands"]) | {x for a in assignments for x in a.values()})
        sections[-1]["hands"] = used
        # Only old paper is eligible; each echo is discrete and queued for the next section.
        chunk_start = arc_done - float(sp[-1])
        if echo is None and p["aware"] > 0 and p["recall"] > 0 and chunk_start - last_recall >= p["recall_gap"]:
            old = np.flatnonzero(S < chunk_start - p["recall_gap"])
            if len(old):
                memory = cKDTree(drawn[old])
                d, js = memory.query(pts[1:])
                hits = np.flatnonzero(d < p["aware"] * p["recall"])
                if len(hits):
                    k = int(hits[0])
                    j = int(old[int(js[k])])
                    memory_channels = {f: np.concatenate(channels["src_" + f]) for f in FEATURES}
                    remembered = {f: int(memory_channels[f][j]) for f in FEATURES}
                    if min(remembered.values()) >= 0:
                        echo = remembered
                        last_recall = chunk_start + float(sp[k + 1])
                        next_plan = None  # An echo replaces an unentered plan, never disappears in it.
                        recalls.append({"s": last_recall, "from_s": float(S[j]), "distance_mm": float(d[k]),
                                        "pos": pts[k + 1].tolist(), "assignment": dict(echo), "echo_section": None})
        _, j = near.query(pts[-1])
        v = max(v, float(C[i0 + int(j)]))
    if stopped == "route_end" and v < route_length - 0.4 * p["ahead"]:
        stopped = "length_cap" if arc_done - initial_mm >= p["max_mm"] else "chunk_cap"
    sections[-1]["end_mm"] = arc_done
    info = {"hands": list(hands), "sections": sections, "segment_log": log, "recalls": recalls,
            "opening": opening_info, "length_mm": arc_done, "continuation_mm": arc_done - initial_mm,
            "route_progress": v / route_length, "stop": stopped, "rejected_proposals": rejected,
            "morph_batches": banks.morph_batches, "character_vectors": vectors,
            "distances": distances.tolist(), "route": route.tolist(), "section_codes": SECTION_CODES,
            "pending_echo": echo}
    return np.vstack(points), {name: np.concatenate(vs) for name, vs in channels.items()}, info


@voice("passage", params=[
    P("hands", "refs", HANDS, "3–8 real hands; every feature names one source", kind="hand", min_len=3, max_len=8),
    P("opening", "choice", "free", "exact half-A4 free hand before the many-source continuation", choices=("free", "none")),
    P("free_seed", "int", 3966, "accrue opening seed; 3966 is Ian's kept free hand", min=0, max=2147483647),
    P("erratic", "float", 0.35, "gradual glides toward abrupt jolts and shorter sections", min=0, max=1),
    P("many", "float", 0.35, "share of sections with 3–4 hands speaking at once", min=0, max=1),
    P("specimen", "float", 0.35, "share of held two-hand splits, including waves and the key family", min=0, max=1),
    P("section_length", "float", 24.0, "mean section length in segments before log-normal asymmetry", min=2, max=160),
    P("asym", "float", 0.7, "spread of asymmetric log-normal section lengths", min=0, max=1),
    P("aware", "float", 0.8, "joint alignment, paper recall radius and near/far hand preference", min=0, max=1),
    P("recall", "float", 6.0, "older paper within this radius can echo its whole feature assignment, mm", min=0, max=40),
    P("recall_gap", "float", 150.0, "minimum age and spacing of discrete recall events, mm of line", min=10, max=2000),
    P("malleable", "float", 0.2, "chance per section of quantile-selected turn/span and coil/own/zigzag dials", min=0, max=1),
    P("R_mm", "float", 100.0, "reference length of all source grammars, mm", min=20, max=300),
    P("rows", "int", 2, "boustrophedon rows; after the opening, first right to left", min=1, max=8),
    P("K", "int", 8, "independent proposals per chunk (shorter intact chunks retried if all leave the box)", min=1, max=30),
    P("chunk", "int", 5, "segments per route decision; boundaries may shorten a chunk", min=1, max=20),
    P("step", "float", 0.3, "sampling step, mm (opening always retains its recorded 0.3)", min=0.1, max=1),
    P("band", "float", 18.0, "distance from the route before a stray penalty, mm", min=2, max=70),
    P("ahead", "float", 23.0, "route target ahead, mm", min=3, max=80),
    P("pull", "float", 4.0, "route target preference among whole proposals", min=0, max=20),
    P("clear", "float", 1.2, "crowding radius against the line's own past, mm", min=0.1, max=12),
    P("max_mm", "float", 6500.0, "continuation arc-length cap, excluding the exact opening, mm", min=50, max=20000),
], doc="one wire line passing through many learned hands, one whole feature at a time, in unequal aware sections")
def passage(ctx, *, hands, opening, free_seed, **params):
    if len(set(hands)) != len(hands):
        raise ValueError("passage: hands must be distinct")
    if opening == "free" and "river_belt" not in hands:
        raise ValueError("passage: opening=free requires river_belt in hands so its channels name a real source")
    grammars = [ctx.use("hand", h) for h in hands]
    pts, opening_info = None, {"kind": "none", "points": 0, "length_mm": 0.0}
    if opening == "free":
        g = grammars[hands.index("river_belt")]
        pts, opening_info = free_opening(g, ctx.box, free_seed)
    pts, channels, info = grow(grammars, seed=ctx.seed, box=ctx.box, hands=hands,
                                start_points=pts, opening_info=opening_info, **params)
    return [Mark(pts, channels, {"voices": list(hands), "passage": info})]

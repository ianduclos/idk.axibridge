"""S2b (synthesis bench, 2026-10-19): `ccolour` and `arch` as score WRITERS.

The composers decided a whole sheet and drew it; here they decide the same sheet and write it down as a
v2 score (layers + relations) that the shared executor plays. Decisions are the composers' own, IMPORTED
(`arrangers_ccolour.decide` / `pen_plan`, `arrangers_arch.plan_arch`), drawn from the composer's own
`ctx.rng` streams at the writer's seed, so a writer and its composer at one seed share the composition
(frame, found matter, hands, boxes, pens, which acts enter); the drawing then differs because each line is
now played by relations (`relations_ccolour.py`) rather than by one private loop.

Layers (ids carry `wctx.prefix`), in plot order:
    Fks / Fk   found matter k: the found part (unseen, swappable) and its paste (role found)
    Mi         made line i: a `hand` part (swap its hand in the layer stack); grown by `answer` (it hears the
               last `answers` lines) and `catch` (the found layers + the same lines)
    C          the R5 cover (relation-only: `cover` places it on the densest passage, `cover_cut` cuts what
               lies under it); written where found_play put it (after line `cover_after`)
    K          the container (literal lines: the composer's own geometry)
    Q          the counterweight (a part in its box)
    T(s)       ccolour's traverse: a part (unseen) laid along a→b by `paste` (whole);
               arch's danced traverse: a drift part (unseen) steered by `steer` with the dancer's tempo, nib
    P(o/c)s, P arch's passer: its own hand and the core's hand (unseen parts), `steer`ed through the container
    FLs, FL    arch's flicker: a revisit_glyph host (unseen) and the figures `flicker` surfaces on made lines
    X / X0, X1 ccolour's heavy intruder (literal lines) / arch's swell (a part: hand + prosody + swell) and its
               duet (`answer` by stress, the chorus)

Pens: each layer's pen is the composer's pen plan (`own`, `line_pens`); pen events are the contact
relations carry / ride / reverse / spill / touch, one instance each over "*", with ccolour's per-sheet
budget split between them (`budget` key), its per-line cap, min run, lies. `colouring: legend` is the dud
control (fixed pens, the codes as the round-13 map). `awareness` (default on) adds the five awareness
relations over "*" → "*" (round 16), skipping the cover, the container's frame for bending, the flicker
figures, and arch's swell beads for gaps (a separate crossing lets lines pass under the swell).

Fidelity to the composers (judged side by side, never bit parity): the composition is identical; each
line's walk draws from its own relation stream, so rides and catches land elsewhere; pen events are taken
first-come in drawing order (each candidate at chance `p`) instead of a weighted draw over the finished
sheet, and a relation hears only earlier layers (ccolour coloured after everything was drawn); the cover
cuts found matter before later lines walk over it; a counterweight's per-mark pens are one wire pen.
"""
from __future__ import annotations

import json
import math

import numpy as np

from . import arrangers_arch as ar
from . import arrangers_ccolour as cc
from ._writers import WCtx, palette_around, writer
from .core import Ctx, P, fit

ROLES = ("found", "made", "cover", "container", "counter", "traverse", "passer", "flicker", "intruder")
AWARE = ("crossing", "sympathy", "hesitate", "accompany", "make_room")


def _crng(seed: int, module: str, *tags) -> np.random.Generator:
    """The composer's own `ctx.rng` (stage "arranger", module id) at this seed: the writer decides what the
    composer decided at the same seed."""
    return Ctx((1.0, 1.0), (0.0, 0.0, 1.0, 1.0), int(seed), int(seed), -1, "arranger", module, None).rng(*tags)


def _r(v, n=3):
    return round(float(v), n)


def _local_frame(wctx: WCtx):
    """The composer's frame: the region grown by the margin (clipped to the sheet), so the composer's own
    inner box is the region."""
    x, y, w, h = wctx.region
    m = wctx.margin
    W, H = wctx.frame
    x0, y0 = max(x - m, 0.0), max(y - m, 0.0)
    x1, y1 = min(x + w + m, W), min(y + h + m, H)
    return x0, y0, x1 - x0, y1 - y0


class _Score:
    """The fragment being written: layers and relations, locked layers kept verbatim."""

    def __init__(self, wctx: WCtx):
        self.w = wctx
        self.keep = {L["id"]: L for L in wctx.keep}
        self.layers: list[dict] = []
        self.rels: list[dict] = []

    def layer(self, name: str, **spec) -> str:
        lid = self.w.id(name)
        if spec.get("region") is not None:            # rounding never pushes a region past the paper
            W, H = self.w.frame
            x, y, w, h = (float(v) for v in spec["region"])
            x, y = min(max(x, 0.0), W - 2.0), min(max(y, 0.0), H - 2.0)
            spec["region"] = [round(x, 3), round(y, 3), math.floor(min(w, W - x) * 1000) / 1000,
                              math.floor(min(h, H - y) * 1000) / 1000]
        self.layers.append(self.keep.get(lid) or {"id": lid, **spec})
        return lid

    def rel(self, name: str, kind: str, src, dst, params=None, **extra) -> str:
        rid = self.w.id(name)
        if isinstance(src, (list, tuple)):
            src = list(src)[:8]
            src = src[0] if len(src) == 1 else src
        self.rels.append({"id": rid, "kind": kind, "src": src, "dst": dst, "params": dict(params or {}), **extra})
        return rid

    def finish(self) -> tuple[list, list]:
        have = {L["id"] for L in self.layers}
        for lid, L in self.keep.items():          # a locked layer this plan no longer writes stays, at the end
            if lid in have:
                continue
            self.layers.append(L)
            if not any(k in L for k in ("part", "lines", "composer")) and self.layers[0]["id"] != lid:
                self.rel(f"R_keep_{lid[len(self.w.prefix):]}", "paste", self.layers[0]["id"], lid,
                         {"mode": "keep"})
        return self.layers, self.rels


def _swap_pens(obj, swap: dict):
    """A copy of the plan with every pen name in `swap` replaced (own, line pens, lend, the passer's and
    the swell's inks …): pen names are the only plan strings that are Flexoki ink names."""
    if not swap:
        return obj
    if isinstance(obj, dict):
        return {k: _swap_pens(v, swap) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_swap_pens(v, swap) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_swap_pens(v, swap) for v in obj)
    return swap.get(obj, obj) if isinstance(obj, str) else obj


def _abs_box(o, fr, F):
    """Fractions of the composer's frame (cx, cy, w, h) → an absolute [x, y, w, h] region."""
    cx, cy, bw, bh = fr[:4]
    return [_r(o[0] + (cx - bw / 2) * F[2]), _r(o[1] + (cy - bh / 2) * F[3]), _r(bw * F[2]), _r(bh * F[3])]


def _lend_text(pp, ids_found, ids_made) -> str:
    out = []
    for k, v in (pp.get("lend") or {}).items():
        kind, key = k.split(":", 1)
        if kind == "found" and key in ids_found:
            out.append(f"{ids_found[key]}={v}")
        elif kind == "line" and int(key) < len(ids_made):
            out.append(f"{ids_made[int(key)]}={v}")
    return ",".join(out)


def _write(wctx: WCtx, plan: dict, *, arch: bool, colouring: str, awareness: bool) -> dict:
    """Both writers: the composer's plan (in its local frame) → a score fragment."""
    F = _local_frame(wctx)
    o = np.array(F[:2], float)
    reg = [_r(v) for v in wctx.region]
    base = int(wctx.seed)
    sc = _Score(wctx)
    legend = colouring == "legend"
    if wctx.keep and not legend:      # Ian 2026-10-19: recompose builds its palette around the locked pens
        pal, swap = palette_around(plan["pens"]["palette"], [L.get("pen") for L in wctx.keep
                                                             if L.get("role") != "unseen"])
        plan = _swap_pens(plan, swap)
        plan["pens"]["palette"] = pal
    pp = plan["pens"]
    own = dict(pp["own"])
    line_pens = list(pp["line_pens"])
    pl = plan["play"]
    if legend:
        own = {"found": "blue-400", "container": "black", "counter": "black", "traverse": "black",
               "intruder": "black"}
        line_pens = ["black"]
    order: list[str] = []
    # found matter: the part (unseen) and its paste --------------------------------------------------------
    found_ids: dict = {}
    for k, f in enumerate(plan["found"]):
        cx, cy, bw, bh, ang = f["box"]
        box = _abs_box(o, [cx, cy, bw, bh], F)
        s_id = sc.layer(f"F{k}s", role="unseen", pen=own.get("found", "black"), region=box,
                        part={"voice": json.loads(json.dumps(f["voice"]))}, seed=base + 100 + k,
                        label=f"found matter {k} ({f['kind']}): the part, before it is pasted")
        lid = sc.layer(f"F{k}", role="found", pen=own.get("found", "black"),
                       renderer={"id": "wire", "pen": float(pl["found_pen"])}, label=f"found matter: {f['kind']}")
        sc.rel(f"R_paste_F{k}", "paste", s_id, lid,
               {"from_box": box, "to": [_r(o[0] + cx * F[2]), _r(o[1] + cy * F[3]), _r(bw * F[2]), _r(bh * F[3]),
                                         _r(ang)],
                "mode": "clip", "bounds": reg, "kind": {"river": "river", "chart": "chart"}.get(f["kind"], "printed")})
        found_ids[f["kind"]] = lid
        order.append(lid)
    fids = list(found_ids.values())
    # made lines, the cover between them --------------------------------------------------------------------
    made_ids: list[str] = []
    n_made = len(plan["made"])
    cover_after = int(pl["cover_after"])
    bold = float(pl["bold_pen"])
    hair = float(pl["hair_pen"])

    def put_cover():
        cid = sc.layer("C", role="cover", pen=own.get("found", "black"),
                       renderer={"id": "wire", "pen": float(min(pl["found_pen"], 0.25))},
                       label="R5: a torn cover on the densest passage")
        sc.rel("R_cover", "cover", "*", cid, {"wh": list(pl["cover_wh"]), "frame_box": [_r(v) for v in F]},
               roles=["found", "made"])
        sc.rel("R_cover_cut", "cover_cut", "*", cid, roles=["found", "made"])
        order.append(cid)

    for i, m in enumerate(plan["made"]):
        if cover_after == i:
            put_cover()
        box = _abs_box(o, m["box"], F)
        lid = sc.layer(f"M{i}", role="made", pen=line_pens[i % len(line_pens)], region=box,
                       part={"voice": {"id": "hand", "hand": m["hand"], "length": float(m["length"]), "joins": "smooth"},
                             "renderer": {"id": "wire", "pen": hair}},
                       seed=base + 200 + i, label=f"made line {i}: {m['hand']}")
        heard = made_ids[max(0, i - int(pl["answers"])):] if int(pl["answers"]) > 0 else []
        if heard:
            sc.rel(f"R_answer_M{i}", "answer", heard, lid,
                   {"by": "call", "answer_p": float(pl["answer_p"]), "box": box, "bounds": reg})
        src = (fids + heard)[:8] if fids or heard else []
        if src:
            sc.rel(f"R_catch_M{i}", "catch", src, lid,
                   {"catches": int(pl["catches"]), "ride": float(pl["ride"]), "bold_pen": bold, "hair_pen": hair,
                    "inset": 9.0, "frame_box": [_r(v) for v in F], "bounds": reg, "legend": legend})
        made_ids.append(lid)
        order.append(lid)
    if 0 <= cover_after and cover_after >= n_made:
        put_cover()
    # container, counterweight ----------------------------------------------------------------------------
    kid = None
    if plan.get("container"):
        k = plan["container"]
        cx, cy, w, h = k["rect"]
        rect = [_r(cx + o[0]), _r(cy + o[1]), _r(w), _r(h), _r(k["angle"])]
        poly = cc.rect_polygon(cx + o[0], cy + o[1], w, h, k["angle"])
        kid = sc.layer("K", role="container", pen=own.get("container", "black"),
                       lines=[[[_r(x, 4), _r(y, 4)] for x, y in poly]], renderer={"id": "wire", "pen": 0.3},
                       label="a frame inside the frame (T4)")
        order.append(kid)
    if plan.get("counter"):
        c = plan["counter"]
        x, y, w, h = c["box"]
        spec = {"mutual": {"id": "mutual", "T": 110},
                "accrue": {"id": "accrue_walk", "hand": "river_belt", "length": 5.0},
                "loops": {"id": "river_loops"},
                "knot": {"id": "hand", "hand": c["hand"], "length": 9.0, "joins": "chain"}}[c["kind"]]
        qid = sc.layer("Q", role="counter", pen=own.get("counter", "black"),
                       region=[_r(x + o[0]), _r(y + o[1]), _r(w), _r(h)],
                       part={"voice": spec, "renderer": {"id": "wire", "pen": 0.3}}, seed=base + 310,
                       label=f"a smaller density away from the core (T7): {c['kind']}")
        order.append(qid)
    # the late acts -----------------------------------------------------------------------------------------
    late = []
    if plan.get("traverse"):
        late.append("traverse")
    if arch and plan.get("passer"):
        late.append("passer")
    if not arch and plan.get("intruder"):
        late.append("intruder")
    if len(late) == 2 and _crng(base, "arch" if arch else "ccolour", "order").random() < (0.5 if arch else 0.4):
        late.reverse()
    late_ids: dict = {}
    for act in late:
        if act == "traverse" and arch:
            late_ids[act] = _danced(sc, plan, own, o, F, base)
        elif act == "traverse":
            late_ids[act] = _traverse(sc, wctx, plan, own, o, F, reg, base)
        elif act == "passer":
            late_ids[act] = _passer(sc, wctx, plan, own, o, F, base, kid, pp)
        else:
            late_ids[act] = _heavy(sc, plan, own, o, F, reg)
        order.append(late_ids[act])
    fl_id = None
    if arch and plan.get("flicker"):
        fl_id = _flicker(sc, plan, o, F, base, made_ids, late_ids.get("traverse"))
        if fl_id:
            order.append(fl_id)
    swell_ids: list[str] = []
    if arch and plan.get("intruder"):
        swell_ids = _swell(sc, plan, own, o, base)
        order += swell_ids
    # pens: who lends what, within ccolour's budget ---------------------------------------------------------
    on = [] if legend or pp["n"] <= 1 else list(pp["events"])
    budgets = {}
    lend = _lend_text(pp, found_ids, made_ids)
    lp = {"per_line": int(pp["per_line"]), "min_run": float(pp["min_run"]), "p_lie": float(pp["p_lie"]),
          "lie_mm": float(pp["lie_mm"]), "p_end": float(pp["p_end"]), "lend": lend}
    rels = []
    if "carry" in on or "answer" in on:
        what = ["river", "chart", "hand", "motif"] if "carry" in on else []
        rels.append(("carry", {"what": ",".join(what + (["call"] if "answer" in on else []))},
                     {"roles": ["found", "made"]}, 2.0))
    if "ride" in on:
        rels.append(("ride", {}, {"roles": ["found", "made"]}, 1.0))
    if "reverse" in on:
        rels.append(("reverse", {}, {"roles": ["found", "made"]}, 1.0))
    if "spill" in on and kid:
        refuse = plan["container"].get("refuse")
        ex = [made_ids[refuse]] if isinstance(refuse, int) and 0 <= refuse < len(made_ids) else []
        cx, cy, w, h = plan["container"]["rect"]
        rels.append(("spill", {"rect": [_r(cx + o[0]), _r(cy + o[1]), _r(w), _r(h), _r(plan["container"]["angle"])]},
                     {"roles": ["made", "traverse", "counter"], **({"except": ex} if ex else {}), "_src": kid}, 2.0))
    if "contact" in on:
        rels.append(("touch", {"touched": "traverse,counter"}, {"not_roles": ["cover"]}, 1.0))
    wsum = sum(r[3] for r in rels) or 1.0
    for kind, prm, extra, wgt in rels:
        b = max(1, int(round(pp["budget"] * wgt / wsum)))
        budgets[kind] = b
        src = extra.pop("_src", "*")
        sc.rel(f"R_{kind}", kind, src, "*", {**lp, **prm}, budget=b, **extra)
    # awareness everywhere (round 16), never inside the beads ---------------------------------------------
    if awareness:
        bend_skip = ["cover", "container", "flicker", "unseen"] + (["intruder"] if arch else [])
        cross = {"not_roles": ["cover", "flicker"], **({"except": swell_ids} if swell_ids else {})}
        sc.rel("R_aw_crossing", "crossing", "*", "*", {"pen_from": "marks"}, **cross)
        for sid in swell_ids:          # a line meeting the swell passes under it (or both run through)
            sc.rel(f"R_aw_under_{sid[len(wctx.prefix):]}", "crossing", "*", sid,
                   {"pen_from": "marks", "weights": {"gap_over": 0.6, "cross": 0.4}}, not_roles=["cover", "flicker"])
        sc.rel("R_aw_sympathy", "sympathy", "*", "*", {}, not_roles=bend_skip)
        sc.rel("R_aw_hesitate", "hesitate", "*", "*", {}, not_roles=bend_skip)
        sc.rel("R_aw_accompany", "accompany", "*", "*", {}, not_roles=bend_skip)
        sc.rel("R_aw_make_room", "make_room", "*", "*", {}, not_roles=sorted(set(bend_skip) | {"found", "intruder"}))
    layers, rels_out = sc.finish()
    decisions = {"composer": "arch" if arch else "ccolour", "local_frame": [_r(v) for v in F],
                 "plan": json.loads(json.dumps(plan, default=float)), "order": order,
                 "pens": {k: pp[k] for k in ("n", "palette", "mode", "own", "line_pens", "lend", "events")},
                 "colouring": colouring, "events_on": on, "budgets": budgets, "awareness": bool(awareness)}
    return {"layers": layers, "relations": rels_out, "decisions": decisions}


# ---------------------------------------------------------------------------
# the acts that need more than one layer
# ---------------------------------------------------------------------------

def _traverse(sc, wctx, plan, own, o, F, reg, base):
    """ccolour's traverse: its voice in a box of the band's shape (unseen), laid along a → b by `paste`."""
    t = plan["traverse"]
    a, b = np.array(t["a"], float), np.array(t["b"], float)
    L = float(np.linalg.norm(b - a))
    band = float(t["band"])
    k = min(1.0, (F[2] - 2.0) / max(L, 1e-9), (F[3] - 2.0) / max(band, 1e-9))
    box = [_r(o[0] + 1.0), _r(o[1] + 1.0), _r(L * k), _r(band * k)]
    spec = {"belt": {"id": "belt", "hand": t["hand"], "length": 7.0, "gain": 1.0, "gain_end": 3.2},
            "gmorph": {"id": "gmorph", "hand": t["hand"], "length": 8.0,
                       "sign": [0.0, 0.0, 0.35, -1.0, 0.5, 0.6, 0.8, 1.0, 1.0, -0.5],
                       "gain": [0.0, 1.0, 0.4, 2.2, 0.7, 0.8, 1.0, 2.6]},
            "passage": {"id": "passage", "opening": "none", "rows": 1, "max_mm": max(L * 2.2, 200.0)},
            "handover": {"id": "morph_handover", "hands": [t["hand"], "fly_open"], "rows": 1}}.get(t["kind"])
    if spec is None:                                    # free3966: accrue's fixed free walk, literal
        from . import library as _lib  # noqa: PLC0415
        from . import voices_passage as vp  # noqa: PLC0415
        lib = wctx.library if wctx.library is not None else _lib.default()
        pts, _ = vp.free_opening(lib.load("hand", "river_belt", purpose="generate"), (0.0, 0.0, 285.0, 93.5))
        s, off = fit([pts], tuple(box))
        q = pts * s + off
        s_id = sc.layer("Ts", role="unseen", pen=own.get("traverse", "black"),
                        lines=[[[_r(x, 4), _r(y, 4)] for x, y in q]], label="the traverse's line (accrue 3966)")
    else:
        s_id = sc.layer("Ts", role="unseen", pen=own.get("traverse", "black"), region=box, part={"voice": spec},
                        seed=base + 300, label=f"the traverse's voice ({t['kind']})")
    lid = sc.layer("T", role="traverse", pen=own.get("traverse", "black"),
                   renderer={"id": "wire", "pen": float(t["pen"])}, label=f"the traverse (T2): {t['kind']}")
    ang = math.degrees(math.atan2(*(b - a)[::-1]))
    c = (a + b) / 2 + o
    sc.rel("R_paste_T", "paste", s_id, lid, {"from_box": box, "to": [_r(c[0]), _r(c[1]), _r(L), _r(band), _r(ang)],
                                             "mode": "whole", "bounds": reg, "kind": "line"})
    return lid


def _heavy(sc, plan, own, o, F, reg):
    """ccolour's heavy intruder (T3): the composer's own bars, Ls, stairs and knots, literal."""
    local_box = (reg[0] - o[0], reg[1] - o[1], reg[2], reg[3])
    lines = [q + o for q in cc.intruder_lines(plan, local_box)]
    return sc.layer("X", role="intruder", pen=own.get("intruder", "black"),
                    lines=[[[_r(x, 4), _r(y, 4)] for x, y in q] for q in lines if len(q) >= 2],
                    renderer={"id": "wire", "pen": float(plan["intruder"]["pen"])},
                    label="the heavy intruder (T3): foreign in regime, weight and pen")


def _danced(sc, plan, own, o, F, base):
    """arch's traverse: the drift line (unseen part) steered edge to edge, weighted by the dancer's tempo."""
    t = plan["traverse"]
    s_id = sc.layer("Ts", role="unseen", pen=own.get("traverse", "black"), region=[_r(v) for v in F],
                    part={"voice": {"id": "drift", "hands": list(t["hands"]), "joins": "chain", "length": 12.0}},
                    seed=base + 300, label="the danced chain's source (drift)")
    lid = sc.layer("T", role="traverse", pen=own.get("traverse", "black"),
                   renderer={"id": "nib", "style": "e", "pen": float(t["pen"])},
                   label="the danced chain, steered edge to edge (T2)")
    sc.rel("R_steer_T", "steer", s_id, lid,
           {"a": [_r(t["a"][0] + o[0]), _r(t["a"][1] + o[1])], "via": [_r(t["via"][0] + o[0]), _r(t["via"][1] + o[1])],
            "b": [_r(t["b"][0] + o[0]), _r(t["b"][1] + o[1])], "zoom": float(t["zoom"]), "pull": float(t["pull"]),
            "ratio": float(t["ratio"]), "frame_box": [_r(v) for v in F], "timing": t["tempo"],
            "amount": float(t["amount"]), "mass_w": float(t["mass_w"]), "nib_w": float(t["nib_w"]), "seed": base + 301})
    return lid


def _passer(sc, wctx, plan, own, o, F, base, kid, pp):
    """arch's passer: its own hand and the core's (unseen parts), steered through the container, which
    changes its grammar and its pen."""
    t = plan["passer"]
    Fb = [_r(v) for v in F]
    if t["from"] == "free3966":
        from . import library as _lib  # noqa: PLC0415
        from . import voices_passage as vp  # noqa: PLC0415
        lib = wctx.library if wctx.library is not None else _lib.default()
        pts, _ = vp.free_opening(lib.load("hand", "river_belt", purpose="generate"), (0.0, 0.0, 285.0, 93.5))
        q = pts * (F[2] / 285.0) + o
        own_id = sc.layer("Pos", role="unseen", pen=t["ink"], lines=[[[_r(x, 4), _r(y, 4)] for x, y in q]],
                          label="the passer's own line (accrue 3966)")
    else:
        spec = ({"id": "belt", "hand": "river_belt", "length": 9.0, "gain": 1.0, "gain_end": 3.2} if t["from"] == "belt"
                else {"id": "hand", "hand": "meander69", "length": 9.0, "joins": "smooth"})
        own_id = sc.layer("Pos", role="unseen", pen=t["ink"], region=Fb, part={"voice": spec}, seed=base + 330,
                          label=f"the passer's own hand ({t['from']})")
    core_id = sc.layer("Pcs", role="unseen", pen=t["ink"], region=Fb,
                       part={"voice": {"id": "hand", "hand": t["core_hand"], "length": 9.0, "joins": "smooth"}},
                       seed=base + 331, label=f"the core's hand ({t['core_hand']})")
    lid = sc.layer("P", role="passer", pen=t["ink"], renderer={"id": "wire", "pen": float(t["pen"])},
                   label=f"a line that changes type where it is: {t['from']} outside, {t['core_hand']} inside")
    k = plan["container"]
    cx, cy, w, h = k["rect"]
    src = [own_id, core_id] + ([kid] if kid else [])
    sc.rel("R_steer_P", "steer", src, lid,
           {"a": [_r(t["a"][0] + o[0]), _r(t["a"][1] + o[1])], "via": [_r(t["via"][0] + o[0]), _r(t["via"][1] + o[1])],
            "b": [_r(t["b"][0] + o[0]), _r(t["b"][1] + o[1])], "zoom": float(t["zoom"]), "pull": float(t["pull"]),
            "ratio": float(t["ratio"]), "frame_box": Fb,
            "zone": [_r(cx + o[0]), _r(cy + o[1]), _r(w), _r(h), _r(k["angle"])], "depth": float(t["depth"]),
            "zone_pen": bool(kid), "min_run": float(pp["min_run"])})
    return lid


def _flicker(sc, plan, o, F, base, made_ids, trav_id):
    f = plan["flicker"]
    hosts = list(made_ids)
    if f["on"] == "made+traverse" and trav_id:
        hosts = hosts[:6] + [trav_id]
    hosts = hosts[:7]
    if not hosts:
        return None
    side = min(F[2], F[3])
    s_id = sc.layer("FLs", role="unseen", pen="black", region=[_r(o[0]), _r(o[1]), _r(side), _r(side)],
                    part={"voice": {"id": "revisit_glyph", "trail": f["trail"], "host": f["host"], "seconds": 60.0,
                                    "still": 0.2, "min_hold_s": 0.25, "max_glyphs": 20, "spread": 1.0}},
                    seed=base + 340, label=f"limb figures from {f['trail']} ({f['host']})")
    lid = sc.layer("FL", role="flicker", pen="black", renderer={"id": "nib", "style": "c+e", "pen": 0.3},
                   label="limb signs surface on the lines and fall back (T7)")
    sc.rel("R_flicker", "flicker", [s_id] + hosts, lid,
           {"n": int(f["n"]), "size": [float(v) for v in f["size"]], "nib_mm": float(f["nib_mm"]),
            "hosts": "made,traverse" if f["on"] == "made+traverse" else "made"})
    return lid


def _swell(sc, plan, own, o, base):
    t = plan["intruder"]
    x, y, w, h = t["box"]
    box = [_r(x + o[0]), _r(y + o[1]), _r(w), _r(h)]
    pros = {"id": "prosody", "density": 0.4, "gap": round(t["size"] * 3.0, 1), "span": round(t["size"] * 0.4, 1),
            "primary": 0.5, "W": 2.5, "M": 7.0}
    rnd = {"id": "swell", "profile": t["profile"], "size": float(t["size"]), "tail": float(t["tail"]),
           "pen": float(t["pen"]), "k_head": 0.8, "tail_w": 2.0}
    ids = [sc.layer("X0", role="intruder", pen=own.get("intruder", "black"), region=box,
                    part={"voice": {"id": "hand", "hand": t["hand"], "length": float(t["length"]), "joins": "smooth"},
                          "modulators": [pros], "renderer": rnd},
                    seed=base + 320, label=f"the bold swell at the core's edge (T3): {t['hand']}, {t['profile']}")]
    if t.get("duet"):
        hand2 = "shikasta" if t["hand"] != "shikasta" else "meander69"
        ids.append(sc.layer("X1", role="intruder", pen=t.get("duet_ink") or "red", region=box,
                            part={"voice": {"id": "hand", "hand": hand2, "length": float(t["length"]),
                                            "joins": "smooth"}, "modulators": [pros], "renderer": rnd},
                            seed=base + 321, label="the chorus: a second swell voice in a second pen"))
        sc.rel("R_answer_X1", "answer", ids[0], ids[1], {"by": "stress", "radius": round(t["size"] * 1.6, 2)})
    return ids


# ---------------------------------------------------------------------------
# the writers
# ---------------------------------------------------------------------------

@writer("ccolour", params=[
    P("density", "float", -1.0, "the density dial 0 … 1 (-1 = the composer decides, extremes allowed)",
      min=-1.0, max=1.0),
    P("pens", "int", 0, "how many pens 1–5 (0 = the composer decides)", min=0, max=5),
    P("mode", "choice", "auto", "who owns which pen: registers | lines | mono | inverted | pair | auto",
      choices=("auto",) + cc.MODES),
    P("colouring", "choice", "composed", "composed: the pen plan (events, budget, lies) | legend: fixed pens, the "
      "codes as the round-13 map (the dud control)", choices=("composed", "legend")),
    P("acts", "str", "core,traverse,counter,container,intruder", "which acts may enter (comma list)"),
    P("awareness", "bool", True, "the five awareness relations over every pair of layers (round 16)"),
], doc="round 14's ccolour as a score: registers own pens and lend them briefly through carry / ride / reverse, "
       "a container stains and spills, a heavy intruder in its own pen; every line played by relations")
def ccolour_writer(wctx: WCtx, *, density, pens, mode, colouring, acts, awareness):
    F = _local_frame(wctx)
    allowed = {a.strip() for a in acts.split(",") if a.strip()}
    plan = cc.decide(_crng(wctx.seed, "ccolour", "decide"), F[2], F[3], density=density, pens=pens, mode=mode,
                     hands=list(cc.HAND_POOL))
    for k in ("traverse", "counter", "container", "intruder"):
        if k not in allowed:
            plan[k] = None
    if any(k not in allowed for k in ("traverse", "counter", "container", "intruder")):
        plan["pens"] = cc.pen_plan(_crng(wctx.seed, "ccolour", "pens"), plan, pens=pens, mode=mode)
    return _write(wctx, plan, arch=False, colouring=colouring, awareness=awareness)


@writer("arch", params=[
    P("families", "str", "danced,swell,flicker,passer", "which revived families enter (comma list of "
      "danced | swell | flicker | passer)"),
    P("density", "float", -1.0, "the density dial 0 … 1 (-1 = the middle: 0.2 / 0.3 / 0.4)", min=-1.0, max=1.0),
    P("pens", "int", 0, "how many pens 1–5 (0 = the composer decides)", min=0, max=5),
    P("mode", "choice", "auto", "who owns which pen (ccolour's modes)", choices=("auto",) + cc.MODES),
    P("duet", "float", 0.25, "chance the swell intruder is a duet (the chorus: two pens, answering)",
      min=0.0, max=1.0),
    P("acts", "str", "container,counter", "which of ccolour's other acts may enter (comma list)"),
    P("awareness", "bool", True, "the five awareness relations over every pair of layers (round 16)"),
], doc="round 15's arch as a score: ccolour's composer with past keeps in new roles (danced traverse, swell "
       "intruder and its chorus, limb flicker, a passer that changes type in the container)")
def arch_writer(wctx: WCtx, *, families, density, pens, mode, duet, acts, awareness):
    F = _local_frame(wctx)
    fam = [f.strip() for f in families.split(",") if f.strip()]
    bad = sorted(set(fam) - set(ar.FAMILIES))
    if bad:
        raise ValueError(f"arch: unknown famil(ies) {bad}; choose from {ar.FAMILIES}")
    allowed = {a.strip() for a in acts.split(",") if a.strip()}
    plan = ar.plan_arch(_crng(wctx.seed, "arch", "decide"), F[2], F[3], density=density, families=fam, pens=pens,
                        mode=mode, duet=duet, hands=list(cc.HAND_POOL))
    for k in ("container", "counter"):
        if k not in allowed and not (k == "container" and plan["passer"]):
            plan[k] = None
    return _write(wctx, plan, arch=True, colouring="composed", awareness=awareness)

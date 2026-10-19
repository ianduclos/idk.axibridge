"""The score, version 2, and its executor (round 16 contract, lead-owned).

The synthesis bench's substructure (`docs/synthesis-bench/design-2026-10-19.md`
§3): a score is a list of layers and the relations between them. The score is
the program: `run(score)` plays it into an ordinary `Sheet`, and the played
score (every relation that fired, logged by the executor, never by the
technique) is `sheet.meta["notes"]["score"]`, where devices already look.

    {"version": 2, "frame": [250, 175], "seed": 16001, "margin": 5.0,
     "base": null | {"lines": [[[x, y], …], …]},          # → the unseen layer "base", first
     "layers": [
       {"id": "L0", "role": "speaker", "pen": "black",
        "part": {"voice": {"id": "hand", "hand": "matisse"}, "modulators": [], "renderer": {"id": "wire"}}},
       {"id": "L1", "role": "listener", "pen": "red", "region": [x, y, w, h],
        "part": {"voice": {"id": "hand", "hand": "trail_miner"}}},
       {"id": "L2", "role": "sealed", "pen": "blue", "region": [150, 20, 90, 70],
        "composer": {"arranger": {"id": "listen"}, "parts": [ … ]}},      # a whole v1 recipe, confined
       {"id": "L3", "role": "unseen", "lines": [[[x, y], …]]}            # literal lines: heard, never inked
     ],
     "relations": [
       {"id": "R0", "kind": "yield", "src": "*", "dst": "*", "p": 1.0, "params": {"gap": 1.2}}
     ],
     "devices": [{"id": "meas_arcs", "place": "beside"}],
     "decisions": {…}}

Layers
- Drawn in list order (= plot order). Exactly one of `part` (a kit part:
  voice + modulators + renderer, fitted into `region`), `lines` (literal
  polylines in sheet mm), `composer` (a v1 recipe without frame/seed, run in
  a frame of the region's size and placed there: a *sealed* layer).
- Layer k's part seed is `seed + k` (`core.part_seed`), so a score whose
  layers are a recipe's parts draws the same lines.
- `pen` is a Flexoki ink name; it becomes `Ink.meta["colour"]`. A `lines`
  layer may give its own `renderer` (e.g. `{"id": "wire", "pen": 0.8}`).
- role "unseen" is never inked and never included in a `*` wildcard; name it
  to make a relation hear it.

Relations (`_relations.py`)
- grow: applied when its dst is drawn, after the dst's own part; src is an
  earlier layer or "*" (every earlier visible layer, merged).
- contact: applied when the later of its two layers is placed. `*` expands to
  every pair: src="*", dst="*" → (each earlier layer, the new one).
- `p` (default 1): the chance each application fires (its own draw).

Every mark of layer k carries meta {"layer", "score_layer": id, "part": k,
"of_role": role, "colour": pen}; every ink the same, so `devices_meas_read`
maps layers to marks without help.

Cache: the executor's state after each layer is cached by a hash of
everything that led to it, so editing a late layer or a relation that acts
late re-runs only from there (the bench's live preview). `run(..., cache=False)`
bypasses it; `clear_cache()` empties it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Mapping

import numpy as np

from . import core
from ._relations import RCtx, RelOut, get_relation
from .core import Ink, Mark, RecipeError, Sheet

SCORE_VERSION = 2
_TOP = ("version", "label", "notes", "frame", "seed", "margin", "base", "layers", "relations", "devices",
        "decisions", "renderer", "parts")      # "parts" is derived on output, ignored on input
_LAYER = ("id", "role", "pen", "label", "region", "part", "lines", "composer", "lock", "renderer")
_REL = ("id", "kind", "src", "dst", "p", "params", "note")
UNSEEN = "unseen"
DEFAULT_MARGIN = 5.0
DEFAULT_RENDERER = {"id": "wire"}


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def _ident(v, where) -> str:
    if not isinstance(v, str) or not v or v == "*" or not v.replace("_", "").replace("-", "").isalnum():
        raise RecipeError(f"{where}: id must be a non-empty word (letters, digits, _ -), got {v!r}")
    return v


def validate(score: Mapping, *, library=None) -> dict:
    """Normalize a v2 score: ids checked, every part / relation param
    validated, defaults filled. Returns a new JSON-native dict."""
    core.discover()
    if library is None:
        from . import library as _lib  # noqa: PLC0415
        library = _lib.default()
    if not isinstance(score, Mapping):
        raise RecipeError("a score is a dict")
    extra = sorted(k for k in score if k not in _TOP)
    if extra:
        raise RecipeError(f"score: unknown key(s) {extra}; known: {list(_TOP)}")
    if score.get("version", SCORE_VERSION) != SCORE_VERSION:
        raise RecipeError(f"score: version must be {SCORE_VERSION}")
    frame = score.get("frame", list(core.DEFAULT_FRAME))
    if (not isinstance(frame, (list, tuple)) or len(frame) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 10 <= v <= 2000 for v in frame)):
        raise RecipeError(f"score: frame must be [W, H] mm in [10, 2000], got {frame!r}")
    W, H = float(frame[0]), float(frame[1])
    seed = score.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= core.SEED_MAX:
        raise RecipeError(f"score: seed must be an int in [0, {core.SEED_MAX}]")
    margin = float(score.get("margin", DEFAULT_MARGIN) if score.get("margin") is not None else DEFAULT_MARGIN)
    if not 0 <= margin <= 0.25 * min(W, H):
        raise RecipeError("score: margin out of range")
    renderer = core._module_spec("renderer", score.get("renderer") or DEFAULT_RENDERER, "score", library)

    layers_in = list(score.get("layers") or [])
    base = score.get("base")
    if base is not None:
        if not isinstance(base, Mapping) or "lines" not in base:
            raise RecipeError("score: base is null or {\"lines\": [...]} (picture extraction comes later)")
        layers_in = [{"id": "base", "role": UNSEEN, "lines": base["lines"], "label": base.get("label", "base")}] + layers_in
    if not layers_in:
        raise RecipeError("score: needs at least one layer")
    layers, ids = [], []
    for k, L in enumerate(layers_in):
        where = f"layer {k}"
        if not isinstance(L, Mapping):
            raise RecipeError(f"{where}: must be a dict")
        bad = sorted(x for x in L if x not in _LAYER)
        if bad:
            raise RecipeError(f"{where}: unknown key(s) {bad}; known: {list(_LAYER)}")
        lid = _ident(L.get("id", f"L{k}"), where)
        if lid in ids:
            raise RecipeError(f"{where}: duplicate id {lid!r}")
        ids.append(lid)
        kinds = [x for x in ("part", "lines", "composer") if L.get(x) is not None]
        if len(kinds) != 1:
            raise RecipeError(f"{where} ({lid}): give exactly one of part / lines / composer")
        out = {"id": lid, "role": str(L.get("role") or "line"), "pen": str(L.get("pen") or "black"),
               "label": str(L.get("label") or "")}
        reg = L.get("region")
        if reg is not None:
            if (not isinstance(reg, (list, tuple)) or len(reg) != 4
                    or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in reg)
                    or reg[2] <= 1 or reg[3] <= 1 or reg[0] < 0 or reg[1] < 0
                    or reg[0] + reg[2] > W + 1e-6 or reg[1] + reg[3] > H + 1e-6):
                raise RecipeError(f"{where} ({lid}): region must be [x, y, w, h] inside the frame")
            out["region"] = [float(v) for v in reg]
        if L.get("lock"):
            out["lock"] = True
        if L.get("renderer") is not None and kinds[0] != "lines":
            raise RecipeError(f"{where} ({lid}): a layer-level renderer is for lines layers (a part has its own)")
        if kinds[0] == "part":
            p = L["part"]
            if not isinstance(p, Mapping) or "voice" not in p:
                raise RecipeError(f"{where} ({lid}): part needs a voice")
            q = {"voice": core._module_spec("voice", p["voice"], where, library),
                 "modulators": [core._module_spec("modulator", m, f"{where} modulator {j}", library)
                                for j, m in enumerate(p.get("modulators") or [])]}
            if p.get("renderer") is not None:
                q["renderer"] = core._module_spec("renderer", p["renderer"], where, library)
            out["part"] = q
        elif kinds[0] == "lines":
            lines = []
            for line in L["lines"]:
                a = np.asarray(line, float)
                if a.ndim != 2 or a.shape[1] != 2 or len(a) < 2 or not np.all(np.isfinite(a)):
                    raise RecipeError(f"{where} ({lid}): lines are lists of ≥2 [x, y] points")
                lines.append([[round(float(x), 4), round(float(y), 4)] for x, y in a])
            out["lines"] = lines
            if L.get("renderer") is not None:
                out["renderer"] = core._module_spec("renderer", L["renderer"], where, library)
        else:
            c = dict(L["composer"])
            for k2 in ("frame", "seed"):
                if k2 in c:
                    raise RecipeError(f"{where} ({lid}): a composer layer's frame and seed come from the score")
            if "arranger" not in c:
                raise RecipeError(f"{where} ({lid}): composer needs an arranger")
            core.validate({**c, "frame": [10.0, 10.0], "seed": 0}, library=library)     # ids + params
            out["composer"] = copy.deepcopy(c)
        layers.append(out)

    pos = {lid: k for k, lid in enumerate(ids)}
    relations, rids = [], []
    for j, R in enumerate(score.get("relations") or []):
        where = f"relation {j}"
        if not isinstance(R, Mapping):
            raise RecipeError(f"{where}: must be a dict")
        bad = sorted(x for x in R if x not in _REL)
        if bad:
            raise RecipeError(f"{where}: unknown key(s) {bad}; known: {list(_REL)}")
        rid = _ident(R.get("id", f"R{j}"), where)
        if rid in rids:
            raise RecipeError(f"{where}: duplicate id {rid!r}")
        rids.append(rid)
        rel = get_relation(str(R.get("kind", "")))
        src, dst = str(R.get("src", "*")), str(R.get("dst", "*"))
        for side, v in (("src", src), ("dst", dst)):
            if v != "*" and v not in pos:
                raise RecipeError(f"{where} ({rid}): {side} {v!r} is not a layer; have {ids}")
        if src != "*" and src == dst:
            raise RecipeError(f"{where} ({rid}): src and dst are the same layer")
        if rel.phase == "grow":
            if dst == "*":
                raise RecipeError(f"{where} ({rid}): a grow relation needs one dst layer")
            if src != "*" and pos[src] >= pos[dst]:
                raise RecipeError(f"{where} ({rid}): a grow relation hears an EARLIER layer ({src} is not before {dst})")
        p = R.get("p", 1.0)
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0 <= p <= 1:
            raise RecipeError(f"{where} ({rid}): p must be in [0, 1]")
        relations.append({"id": rid, "kind": rel.id, "src": src, "dst": dst, "p": float(p),
                          "params": rel.validate(R.get("params"), where=f"{where} ({rid})"),
                          "note": str(R.get("note") or "")})

    devices = list(score.get("devices") or [])
    out = {"version": SCORE_VERSION, "frame": [W, H], "seed": int(seed), "margin": margin,
           "renderer": renderer, "layers": layers, "relations": relations,
           "devices": copy.deepcopy(devices), "decisions": copy.deepcopy(dict(score.get("decisions") or {}))}
    for k in ("label", "notes"):
        if score.get(k):
            out[k] = str(score[k])
    return out


# ---------------------------------------------------------------------------
# the executor
# ---------------------------------------------------------------------------

_CACHE: "OrderedDict[str, tuple]" = OrderedDict()
_CACHE_MAX = 48


def clear_cache() -> None:
    _CACHE.clear()


def _h(*objs) -> str:
    return hashlib.sha1(json.dumps(objs, sort_keys=True, default=str).encode()).hexdigest()


def _visible(layers, k) -> list[str]:
    return [L["id"] for L in layers[:k] if L["role"] != UNSEEN]


def _pairs(R, k, layers, pos) -> list[tuple[str, str]]:
    """The (src, dst) pairs a contact relation acts on at step k."""
    cur = layers[k]["id"]
    vis_cur = layers[k]["role"] != UNSEEN
    S, D = R["src"], R["dst"]
    if S == "*" and D == "*":
        return [(i, cur) for i in _visible(layers, k)] if vis_cur else []
    if S == "*":
        if D == cur:
            return [(i, D) for i in _visible(layers, k)]
        return [(cur, D)] if vis_cur and pos[D] < k else []
    if D == "*":
        if S == cur:
            return [(S, j) for j in _visible(layers, k)]
        return [(S, cur)] if vis_cur and pos[S] < k else []
    return [(S, D)] if max(pos[S], pos[D]) == k else []


def _tag(marks, L, k) -> list[Mark]:
    return [m.evolve(meta={"layer": L["id"], "score_layer": L["id"], "part": k, "of_role": L["role"],
                           "colour": L["pen"]}) for m in marks]


def _region(rec, L) -> tuple:
    if L.get("region"):
        return tuple(L["region"])
    W, H = rec["frame"]
    m = rec["margin"]
    return (m, m, W - 2 * m, H - 2 * m)


def _grow_layer(rec, L, k, state, lib, sealed) -> list[Mark]:
    W, H = rec["frame"]
    box = _region(rec, L)
    if "part" in L:
        p = core.Part(k, L["part"], L["part"].get("renderer", rec["renderer"]), (W, H), rec["seed"], state, box)
        return p.run(box)
    if "lines" in L:
        return [Mark(np.asarray(line, float), {}, {"lines": True}) for line in L["lines"]]
    x0, y0, w, h = box
    sub = {**copy.deepcopy(L["composer"]), "frame": [w, h], "seed": core.part_seed(rec["seed"], k)}
    sh = core.run(sub, library=lib)
    for e in sh.meta.get("library", []):
        state.used.setdefault((e["kind"], e["id"]), e)
    marks = [m.transformed(1.0, (x0, y0)).evolve(meta={"inner_layer": m.meta.get("layer"),
                                                         "inner_part": m.meta.get("part", 0)})
             for m in sh.marks]
    inks = [Ink(i.points + np.array([x0, y0]), i.closed, i.filled, i.pen, dict(i.meta)) for i in sh.inks]
    sealed[L["id"]] = {"recipe": sh.recipe, "inks": inks, "notes": sh.meta.get("notes"), "marks0": None}
    return marks


def _check_out(out, where, phase, need) -> RelOut:
    if isinstance(out, tuple) and not isinstance(out, RelOut):
        out = RelOut(*out)
    if not isinstance(out, RelOut):
        raise core.ChannelError(f"{where} must return RelOut(dst, src, events)")
    if phase == "grow" and out.src is not None:
        raise core.KitError(f"{where}: a grow relation may not rewrite its src (the past)")
    for side in (out.dst, out.src):
        if side is None:
            continue
        core._check_marks(side, where)
        for mk in side:
            lost = sorted(need - set(mk.channels))
            if lost:
                raise core.ChannelError(f"{where} dropped channel(s) {lost}; carry them (Mark.evolve / remap)")
    return out


def _r(v):
    if v is None:
        return None
    return [round(float(x), 2) for x in v]


def _apply(rec, R, src_id, dst_id, k, ground, state, log, unseen):
    rel = get_relation(R["kind"])
    rctx = RCtx(tuple(rec["frame"]), rec["seed"], R["id"], R["kind"], src_id, dst_id, k, state, ground)
    if R["p"] < 1.0 and rctx.rng("p").random() >= R["p"]:
        log.append({"relation": R["id"], "kind": R["kind"], "src": src_id, "dst": dst_id, "step": k,
                    "outcome": "silent"})
        return
    if src_id == "*":
        order = list(ground)
        src = [m for lid in order[:order.index(dst_id)] if lid not in unseen for m in ground[lid]]
    else:
        src = list(ground[src_id])
    dst = list(ground[dst_id])
    both = src + dst
    need = set.intersection(*(set(m.channels) for m in both)) if both else set()
    out = rel.fn(rctx, src, dst, **copy.deepcopy(R["params"]))
    out = _check_out(out, f"relation {R['id']!r} ({R['kind']})", rel.phase, need)
    if out.dst is not None:
        ground[dst_id] = _keep_meta(out.dst, ground[dst_id])
    if out.src is not None and src_id != "*":
        ground[src_id] = _keep_meta(out.src, ground[src_id])
    for e in out.events or ():
        e = dict(e)
        ev = {"relation": R["id"], "kind": R["kind"], "src": src_id, "dst": dst_id, "step": k,
              "outcome": str(e.pop("outcome", "fired"))}
        for key in ("at", "s", "s_src"):
            if key in e:
                ev[key] = _r(e.pop(key))
        ev.update(json.loads(json.dumps(e, default=float)))
        log.append(ev)


def _keep_meta(new, old) -> list[Mark]:
    """Marks a relation returned keep their layer's tags (a relation may build
    fresh Marks)."""
    if not old:
        return list(new)
    keys = ("layer", "score_layer", "part", "of_role", "colour")
    tags = {k: old[0].meta.get(k) for k in keys}
    return [m if all(m.meta.get(k) == v for k, v in tags.items()) else m.evolve(meta=tags) for m in new]


def run(score: Mapping, *, library=None, cache: bool = True) -> Sheet:
    """Play a v2 score → Sheet (deterministic in the score alone)."""
    from . import library as _lib  # noqa: PLC0415
    from ._devices import apply_devices  # noqa: PLC0415
    t0 = time.perf_counter()
    lib = library if library is not None else _lib.default()
    rec = validate(score, library=lib)
    layers = rec["layers"]
    pos = {L["id"]: k for k, L in enumerate(layers)}
    unseen = {L["id"] for L in layers if L["role"] == UNSEEN}
    state = core._Run(lib)
    ground: dict[str, list[Mark]] = {}
    log: list[dict] = []
    sealed: dict[str, dict] = {}
    key = _h("synth", core.KIT_VERSION, rec["frame"], rec["seed"], rec["margin"], rec["renderer"])
    hits = 0
    for k, L in enumerate(layers):
        acting = [R for R in rec["relations"]
                  if (R["dst"] == L["id"] and get_relation(R["kind"]).phase == "grow")
                  or (get_relation(R["kind"]).phase == "contact" and _pairs(R, k, layers, pos))]
        key = _h(key, L, acting)
        if cache and key in _CACHE:
            g, lg, used, sl = _CACHE[key]
            _CACHE.move_to_end(key)
            ground, log, sealed = dict(g), list(lg), dict(sl)
            state.used = dict(used)
            hits += 1
            continue
        ground[L["id"]] = _tag(_grow_layer(rec, L, k, state, lib, sealed), L, k)
        if L["id"] in sealed:
            sealed[L["id"]]["marks0"] = tuple(ground[L["id"]])
        for R in acting:
            if get_relation(R["kind"]).phase == "grow":
                _apply(rec, R, R["src"], L["id"], k, ground, state, log, unseen)
        for R in acting:
            if get_relation(R["kind"]).phase == "contact":
                for s_id, d_id in _pairs(R, k, layers, pos):
                    _apply(rec, R, s_id, d_id, k, ground, state, log, unseen)
        if cache:
            _CACHE[key] = (dict(ground), list(log), dict(state.used), dict(sealed))
            while len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
    t1 = time.perf_counter()

    W, H = rec["frame"]
    marks, inks = [], []
    for k, L in enumerate(layers):
        mine = ground[L["id"]]
        marks += mine
        if L["role"] == UNSEEN:
            continue
        tags = {"layer": L["id"], "score_layer": L["id"], "part": k, "of_role": L["role"]}
        if L["id"] in sealed and sealed[L["id"]]["marks0"] is not None and \
                len(mine) == len(sealed[L["id"]]["marks0"]) and all(a is b for a, b in zip(mine, sealed[L["id"]]["marks0"])):
            inks += [Ink(i.points, i.closed, i.filled, i.pen,
                         {**i.meta, **tags, "colour": i.meta.get("colour") or L["pen"]}) for i in sealed[L["id"]]["inks"]]
            continue
        if L["id"] in sealed:
            sub = sealed[L["id"]]["recipe"]
            groups: dict[int, list] = {}
            for m in mine:
                groups.setdefault(int(m.meta.get("inner_part", 0) or 0), []).append(m)
            jobs = [(sub["parts"][i].get("renderer", sub["renderer"]), ms) for i, ms in sorted(groups.items())]
        else:
            jobs = [(L["part"].get("renderer", rec["renderer"]) if "part" in L else L.get("renderer", rec["renderer"]), mine)]
        for spec, ms in jobs:
            rnd = core.get("renderer", spec["id"])
            rctx = core.Ctx((W, H), _region(rec, L), core.part_seed(rec["seed"], k), rec["seed"], k,
                            "renderer", rnd.id, state)
            for i in rnd.fn(rctx, ms, **{a: b for a, b in copy.deepcopy(spec).items() if a != "id"}):
                if not isinstance(i, Ink):
                    raise core.ChannelError(f"renderer {rnd.id!r} returned a {type(i).__name__}")
                inks.append(Ink(i.points, i.closed, i.filled, i.pen,
                                {**i.meta, **tags, "colour": (i.meta or {}).get("colour") or L["pen"]}))
    t2 = time.perf_counter()

    played = played_score(rec, log, sealed)
    used = [state.used[k] for k in sorted(state.used)]
    meta = {"recipe": {**rec, "parts": _derived_parts(rec)}, "library": used, "inset": rec["margin"],
            "kit": core.KIT_VERSION, "synth": SCORE_VERSION,
            "parts": [{"index": k, "seed": core.part_seed(rec["seed"], k), "layer": L["id"], "role": L["role"],
                       "voice": _technique(L)} for k, L in enumerate(layers)],
            "seconds": {"marks": round(t1 - t0, 3), "inks": round(t2 - t1, 3)}, "cache_hits": hits,
            "notes": {"score": played}}
    sheet = Sheet((W, H), marks, inks, meta)
    if rec["devices"]:
        sheet = apply_devices(sheet, rec["devices"])
    return sheet


def _technique(L) -> str:
    if "part" in L:
        return L["part"]["voice"]["id"]
    if "lines" in L:
        return "lines"
    return L["composer"]["arranger"]["id"] if isinstance(L["composer"]["arranger"], Mapping) \
        else str(L["composer"]["arranger"])


def _derived_parts(rec) -> list[dict]:
    """A v1-shaped parts list (index = layer index) so devices that read
    recipe parts find the voices."""
    return [copy.deepcopy(L["part"]) if "part" in L else {"voice": {"id": _technique(L)}, "modulators": []}
            for L in rec["layers"]]


def played_score(rec: dict, log: list[dict], sealed: dict | None = None) -> dict:
    """The played score: the v1 shape devices read (layers; relations with
    kind/src/dst/at/s/note, one per relation and layer pair) plus the full
    event log and the written score."""
    layers = []
    for k, L in enumerate(rec["layers"]):
        e = {"id": L["id"], "role": L["role"], "technique": _technique(L), "part": k, "pen": L["pen"],
             "params": {}, "label": L["label"]}
        if sealed and L["id"] in sealed and sealed[L["id"]].get("notes"):
            e["inner"] = sealed[L["id"]]["notes"].get("score")
        layers.append(e)
    agg: "OrderedDict[tuple, dict]" = OrderedDict()
    for ev in log:
        if ev["outcome"] == "silent":
            continue
        a = agg.setdefault((ev["relation"], ev["src"], ev["dst"]),
                           {"kind": ev["kind"], "src": ev["src"], "dst": ev["dst"], "relation": ev["relation"],
                            "outcomes": {}, "_at": [], "s": ev.get("s")})
        a["outcomes"][ev["outcome"]] = a["outcomes"].get(ev["outcome"], 0) + 1
        if ev.get("at"):
            a["_at"].append(ev["at"])
    rels = []
    for a in agg.values():
        at = a.pop("_at")
        a["at"] = _r(np.mean(at, axis=0)) if at else None
        n = sum(a["outcomes"].values())
        a["note"] = f"{n} event(s): " + ", ".join(f"{k} {v}" for k, v in sorted(a["outcomes"].items()))
        rels.append(a)
    return {"version": SCORE_VERSION, "layers": layers, "relations": rels, "log": log,
            "decisions": {**rec["decisions"], "order": [L["id"] for L in rec["layers"]]},
            "written": {k: v for k, v in rec.items() if k != "parts"}}


def played(sheet: Sheet) -> dict | None:
    return (sheet.meta.get("notes") or {}).get("score")


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------

def render(sheet: Sheet, *, px_per_mm: float = 6.0, grain: bool = False):
    """PIL image in pen colours (Ink.meta["colour"], Flexoki names)."""
    from .arrangers_ccolour import render_pens  # noqa: PLC0415
    return render_pens(sheet, px_per_mm=px_per_mm, grain=grain)


def preview(sheet: Sheet, path, *, px_per_mm: float = 6.0, label: str | None = None, quality: int = 88) -> Path:
    """Write the colour image, the written score beside it
    (<stem>.recipe.json, which `run` accepts) and the played score
    (<stem>.played.json)."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = render(sheet, px_per_mm=px_per_mm)
    if label:
        fs = max(12, int(im.width / 80))
        strip = Image.new("RGB", (im.width, int(fs * 2.0)), core.PAPER)
        ImageDraw.Draw(strip).text((int(fs * 0.6), int(fs * 0.45)), label, fill=core.INK, font=core._font(fs))
        full = Image.new("RGB", (im.width, im.height + strip.height), core.PAPER)
        full.paste(im, (0, 0))
        full.paste(strip, (0, im.height))
        im = full
    if path.suffix.lower() in (".jpg", ".jpeg"):
        im.save(path, quality=quality, optimize=True)
    else:
        im.save(path)
    written = played(sheet)["written"]
    path.with_suffix(".recipe.json").write_text(json.dumps(written, indent=1, default=float))
    pl = {k: v for k, v in played(sheet).items() if k != "written"}
    path.with_suffix(".played.json").write_text(json.dumps(pl, indent=1, default=float))
    return path

# FROZEN from research commit d5ccd75: tools/gesture/gesture/kit/_synth.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
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

S0′ (2026-10-19), all opt-in — a score that uses none of it plays exactly as before:
- a layer with none of part / lines / composer starts empty and is drawn by
  its grow relations (it may give a layer-level `renderer`);
- relation keys `except` [ids], `roles` / `not_roles` [role names] narrow a
  "*" side; `budget` (int) caps the relation's non-neutral firings across all
  its pairs (`rctx.remaining()`; once spent, applications log "spent");
- a grow relation's `src` may be a list of earlier layer ids (marks merged in
  that order; events log `src` = the first, `srcs` = all);
- marks also carry `pen_mm` (their renderer's pen width) and a stable `mid`
  with `mid_s0`; events naming a mark gain `mid` / `s_uncut` (and
  `mid_src` / `s_src_uncut`);
- a mark with meta `own_pen` {"colour", "renderer"} is inked with that pen,
  after its layer's own marks;
- `replay(score_or_sheet, drop=…, keep_only=…, drop_kinds=…, keep_only_kinds=…)`
  plays counterfactuals.

S0″ (2026-10-19), opt-in the same way:
- side-specific wildcard filters `src_except` / `src_roles` / `src_not_roles` and
  `dst_except` / `dst_roles` / `dst_not_roles` narrow only that "*" side (the plain
  keys narrow both), so "ground × mine, never ground × ground" is
  `{"src": "*", "dst": "*", "dst_except": [ground ids]}`;
- `budget_groups` {name: int} at the score's top and `budget_group: name` on a
  relation: its firings count against the shared group as well as its own
  `budget`; `rctx.remaining()` is the tighter of the two;
- a relation's own `seed` (int) replaces the sheet seed in its random stream
  (`rctx.rng`), so the bench's relation die re-rolls its outcomes alone.
- Reminder (by design since round 16): `src: "*"` with a named dst, on a contact
  relation, fires when the dst is placed (every earlier layer) AND again when each
  LATER layer is placed (that layer as src). Narrow it with `src_…` filters.

Pins (S4, `pin`): a locked layer's `pin` is {"marks": [mark…], "final"?: [mark…]},
a mark being {"points": [[x, y]…], "channels": {name: [v…]}, "meta": {…}} at full
float precision. `marks` is the layer as grown (laid down at its step), `final`
its lines once the score had played (the layer ends as these), given only when
they differ. A final mark may instead be shared with the grown one it came from,
so a pin stores each line once (2026-10-21): {"of": i, "points": items,
"channels": {name: items}, "meta": {…}}, where items list the values in order
and an item {"copy": [start, n]} stands for `marks[i]`'s same array from
`start`, n values long (bitwise equal: what a cut kept, the channels a bend
left alone). `pin` writes a shared mark only where it is smaller; a literal
final mark (every pin before 2026-10-21) still reads as before.

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
        "decisions", "renderer", "parts", "budget_groups")      # "parts" is derived on output, ignored on input
_LAYER = ("id", "role", "pen", "label", "region", "part", "lines", "composer", "lock", "renderer", "seed", "pin")
_SIDE_FILTERS = tuple(f"{side}_{k}" for side in ("src", "dst") for k in ("except", "roles", "not_roles"))
_REL = ("id", "kind", "src", "dst", "p", "params", "note", "except", "roles", "not_roles", "budget",
        *_SIDE_FILTERS, "budget_group", "seed")
NEUTRAL = ("silent", "spent", "cross", "unplaced")   # outcomes that change nothing: not counted against a budget
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
        if len(kinds) > 1:
            raise RecipeError(f"{where} ({lid}): give at most one of part / lines / composer")
        kinds = kinds or ["relations"]          # none: the layer starts empty, grown only by its relations
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
        if L.get("seed") is not None:
            sd = L["seed"]
            if isinstance(sd, bool) or not isinstance(sd, int) or not 0 <= sd <= core.SEED_MAX:
                raise RecipeError(f"{where} ({lid}): seed must be an int in [0, {core.SEED_MAX}]")
            out["seed"] = int(sd)
        if L.get("pin") is not None:
            if L.get("composer") is not None:
                raise RecipeError(f"{where} ({lid}): a composer layer is held still by its seed, not a pin")
            out["pin"] = _valid_pin(L["pin"], f"{where} ({lid})")
            out["lock"] = True
        if L.get("renderer") is not None and kinds[0] not in ("lines", "relations"):
            raise RecipeError(f"{where} ({lid}): a layer-level renderer is for lines layers and relation-grown ones "
                              "(a part has its own)")
        if kinds[0] == "relations" and L.get("renderer") is not None:
            out["renderer"] = core._module_spec("renderer", L["renderer"], where, library)
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
        elif kinds[0] == "composer":
            c = dict(L["composer"])
            for k2 in ("frame", "seed"):
                if k2 in c:
                    raise RecipeError(f"{where} ({lid}): a composer layer's frame and seed come from the score")
            if "arranger" not in c:
                raise RecipeError(f"{where} ({lid}): composer needs an arranger")
            # ids + params, in the frame the composer will really get (its region, or the margin box)
            probe = out.get("region") or [margin, margin, W - 2 * margin, H - 2 * margin]
            core.validate({**c, "frame": [max(float(probe[2]), 10.0), max(float(probe[3]), 10.0)], "seed": 0},
                          library=library)
            out["composer"] = copy.deepcopy(c)
        layers.append(out)

    pos = {lid: k for k, lid in enumerate(ids)}
    groups = score.get("budget_groups") or {}
    if not isinstance(groups, Mapping) or not all(
            isinstance(g, str) and g.replace("_", "").replace("-", "").isalnum()
            and isinstance(b, int) and not isinstance(b, bool) and 0 <= b <= 100_000 for g, b in groups.items()):
        raise RecipeError("score: budget_groups is {name: int in [0, 100000]} (firings shared by its relations)")
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
        raw_src = R.get("src", "*")
        srcs = None
        if isinstance(raw_src, (list, tuple)):                       # a grow relation hearing several layers
            if rel.phase != "grow" or not 2 <= len(raw_src) <= 8:
                raise RecipeError(f"{where} ({rid}): a list src (2–8 layers) is for grow relations")
            srcs = [str(v) for v in raw_src]
            if len(set(srcs)) != len(srcs):
                raise RecipeError(f"{where} ({rid}): src lists a layer twice")
        src, dst = ("+".join(srcs) if srcs else str(raw_src)), str(R.get("dst", "*"))
        for side, v in [*(("src", s) for s in (srcs or [src])), ("dst", dst)]:
            if v != "*" and v not in pos:
                raise RecipeError(f"{where} ({rid}): {side} {v!r} is not a layer; have {ids}")
        if any(s != "*" and s == dst for s in (srcs or [src])):
            raise RecipeError(f"{where} ({rid}): src and dst are the same layer")
        if rel.phase == "grow":
            if dst == "*":
                raise RecipeError(f"{where} ({rid}): a grow relation needs one dst layer")
            for s in (srcs or [src]):
                if s != "*" and pos[s] >= pos[dst]:
                    raise RecipeError(f"{where} ({rid}): a grow relation hears an EARLIER layer ({s} is not before {dst})")
        p = R.get("p", 1.0)
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0 <= p <= 1:
            raise RecipeError(f"{where} ({rid}): p must be in [0, 1]")
        rout = {"id": rid, "kind": rel.id, "src": srcs or src, "dst": dst, "p": float(p),
                "params": rel.validate(R.get("params"), where=f"{where} ({rid})"),
                "note": str(R.get("note") or "")}
        # wildcard filters: which layers a "*" side may stand for (opt-in; absent = every visible layer)
        if any(R.get(k) is not None for k in ("except", "roles", "not_roles")) and "*" not in (src, dst):
            raise RecipeError(f"{where} ({rid}): except / roles / not_roles filter a \"*\" side; this relation has none")
        for side, v in (("src", src), ("dst", dst)):          # S0″: a filter for one side only
            if v != "*" and any(R.get(f"{side}_{k}") is not None for k in ("except", "roles", "not_roles")):
                raise RecipeError(f"{where} ({rid}): {side}_except / {side}_roles / {side}_not_roles filter a "
                                  f"\"*\" {side}; this relation's {side} is {v!r}")
        for k2 in ("except", *(f"{side}_except" for side in ("src", "dst"))):
            if R.get(k2) is not None:
                ex = R[k2]
                if isinstance(ex, str) or not isinstance(ex, (list, tuple)) or not all(v in pos for v in ex):
                    raise RecipeError(f"{where} ({rid}): {k2} is a list of layer ids; have {ids}")
                rout[k2] = [str(v) for v in ex]
        for k2 in ("roles", "not_roles", *(f"{side}_{k}" for side in ("src", "dst") for k in ("roles", "not_roles"))):
            if R.get(k2) is not None:
                v = R[k2]
                if isinstance(v, str) or not isinstance(v, (list, tuple)) or not all(isinstance(x, str) for x in v):
                    raise RecipeError(f"{where} ({rid}): {k2} is a list of role names")
                rout[k2] = [str(x) for x in v]
        if R.get("seed") is not None:            # S0″: the relation's own die (its outcomes re-rolled alone)
            sd = R["seed"]
            if isinstance(sd, bool) or not isinstance(sd, int) or not 0 <= sd <= core.SEED_MAX:
                raise RecipeError(f"{where} ({rid}): seed must be an int in [0, {core.SEED_MAX}]")
            rout["seed"] = int(sd)
        if R.get("budget_group") is not None:
            g = R["budget_group"]
            if g not in groups:
                raise RecipeError(f"{where} ({rid}): budget_group {g!r} is not in the score's budget_groups "
                                  f"{sorted(groups)}")
            rout["budget_group"] = str(g)
        if R.get("budget") is not None:
            b = R["budget"]
            if isinstance(b, bool) or not isinstance(b, int) or not 0 <= b <= 100_000:
                raise RecipeError(f"{where} ({rid}): budget is an int in [0, 100000] (firings across all pairs)")
            rout["budget"] = int(b)
        relations.append(rout)
    for L in layers:
        if not any(k in L for k in ("part", "lines", "composer", "pin")) and not any(
                R["dst"] == L["id"] and get_relation(R["kind"]).phase == "grow" for R in relations):
            raise RecipeError(f"layer {L['id']!r}: has no part / lines / composer, so a grow relation must draw it")

    devices = list(score.get("devices") or [])
    out = {"version": SCORE_VERSION, "frame": [W, H], "seed": int(seed), "margin": margin,
           "renderer": renderer, "layers": layers, "relations": relations,
           "devices": copy.deepcopy(devices), "decisions": copy.deepcopy(dict(score.get("decisions") or {}))}
    if groups:
        out["budget_groups"] = {str(g): int(b) for g, b in groups.items()}
    for k in ("label", "notes"):
        if score.get(k):
            out[k] = str(score[k])
    return out


def _valid_pin(pin, where) -> dict:
    """A pinned layer's geometry: {"marks": [mark…], "final"?: [mark…]}, a mark being {"points",
    "channels"?, "meta"?} (not for composer layers). `marks`: the layer once grown; `final`: its lines
    when the whole score had played, when those differ, each literal or shared with a grown mark
    ({"of": i, …}, see the module docstring; kept shared)."""
    if not isinstance(pin, Mapping) or not isinstance(pin.get("marks"), (list, tuple)):
        raise RecipeError(f"{where}: pin is {{\"marks\": [...]}}")
    bad = sorted(set(pin) - {"marks", "final"})
    if bad:
        raise RecipeError(f"{where}: pin has unknown key(s) {bad}")
    out = {"marks": _valid_marks(pin["marks"], where)}
    if pin.get("final") is not None:
        if not isinstance(pin["final"], (list, tuple)):
            raise RecipeError(f"{where}: pin final is a list of marks")
        final = []
        for j, m in enumerate(pin["final"]):
            w = f"{where} (final)"
            if not isinstance(m, Mapping) or "of" not in m:
                final += _valid_marks([m], w, j)
                continue
            i = m["of"]
            if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(out["marks"]):
                raise RecipeError(f"{w}: pin mark {j} 'of' is the index of a grown mark")
            bad = sorted(set(m) - {"of", "points", "channels", "meta"})
            if bad:
                raise RecipeError(f"{w}: pin mark {j} has unknown key(s) {bad}")
            g = out["marks"][i]
            sh = {"of": i, "points": _valid_items(m.get("points"), g["points"], f"{w}: pin mark {j} points"),
                  "channels": {str(c): _valid_items(v, g["channels"].get(str(c)), f"{w}: pin mark {j} channel {c!r}")
                               for c, v in dict(m.get("channels") or {}).items()},
                  "meta": json.loads(json.dumps(dict(m.get("meta") or {}), default=float))}
            _valid_marks([_unshared(sh, out["marks"])], w, j)          # what it stands for is a valid mark
            final.append(sh)
        out["final"] = final
    return out


def _valid_items(items, src, where) -> list:
    """A shared array: values, and {"copy": [start, n]} runs inside `src` (that grown array)."""
    if not isinstance(items, (list, tuple)):
        raise RecipeError(f"{where}: a list of values and {{\"copy\": [start, n]}} runs")
    out = []
    for it in items:
        if isinstance(it, Mapping):
            c = it.get("copy")
            if (set(it) != {"copy"} or not isinstance(c, (list, tuple)) or len(c) != 2
                    or not all(isinstance(v, int) and not isinstance(v, bool) for v in c)
                    or c[0] < 0 or c[1] < 1 or src is None or c[0] + c[1] > len(src)):
                raise RecipeError(f"{where}: a run is {{\"copy\": [start, n]}} inside the grown mark's array")
            out.append({"copy": [int(c[0]), int(c[1])]})
            continue
        try:
            out.append([float(v) for v in it] if isinstance(it, (list, tuple)) else float(it))
        except (TypeError, ValueError):
            raise RecipeError(f"{where}: {it!r} is not a value") from None
    return out


def _unshared(m: Mapping, grown: list) -> dict:
    """A final mark as a literal one (a shared mark's runs copied out of `grown[m["of"]]`)."""
    if "of" not in m:
        return m
    g = grown[m["of"]]

    def expand(items, src):
        out = []
        for it in items:
            if isinstance(it, Mapping):
                a, n = it["copy"]
                out += src[a:a + n]
            else:
                out.append(it)
        return out
    return {"points": expand(m["points"], g["points"]),
            "channels": {c: expand(v, g["channels"].get(c) or []) for c, v in m["channels"].items()},
            "meta": m["meta"]}


def _share(final: list, grown: list) -> list:
    """`pin`'s final marks, each shared with the grown mark it came from (same `mid`) where that is
    smaller: every run of values bitwise equal to a run of that mark's array becomes a copy."""
    def bits(v):
        return np.asarray(v, float).tobytes()

    def items(vals, src):
        at: dict[bytes, list[int]] = {}
        sb = [bits(v) for v in src]
        for j, b in enumerate(sb):
            at.setdefault(b, []).append(j)
        vb = [bits(v) for v in vals]
        out, i = [], 0
        while i < len(vals):
            best, start = 0, -1
            for j in at.get(vb[i], ())[:64]:
                n = 0
                while i + n < len(vals) and j + n < len(sb) and sb[j + n] == vb[i + n]:
                    n += 1
                if n > best:
                    best, start = n, j
            run = {"copy": [start, best]}
            if best and _size(run) < _size(vals[i:i + best]):
                out.append(run)
                i += best
            else:
                out.append(vals[i])
                i += 1
        return out

    out = []
    for m in final:
        best = (_size(m), m)
        for i, g in enumerate(grown):
            if g["meta"].get("mid") is None or g["meta"].get("mid") != m["meta"].get("mid"):
                continue
            sh = {"of": i, "points": items(m["points"], g["points"]),
                  "channels": {c: items(v, g["channels"].get(c) or []) for c, v in m["channels"].items()},
                  "meta": m["meta"]}
            if _size(sh) < best[0]:
                best = (_size(sh), sh)
        out.append(best[1])
    return out


def _size(obj) -> int:
    return len(json.dumps(obj, separators=(",", ":")))


def _valid_marks(raw, where, first: int = 0) -> list:
    marks = []
    for j, m in enumerate(raw, first):
        if not isinstance(m, Mapping):
            raise RecipeError(f"{where}: pin mark {j} must be a dict")
        a = np.asarray(m.get("points"), float)
        if a.ndim != 2 or a.shape[1] != 2 or len(a) < 2 or not np.all(np.isfinite(a)):
            raise RecipeError(f"{where}: pin mark {j} points are ≥2 [x, y]")
        ch = {}
        for name, v in dict(m.get("channels") or {}).items():
            b = np.asarray(v, float)
            if b.shape != (len(a),) or not np.all(np.isfinite(b)):
                raise RecipeError(f"{where}: pin mark {j} channel {name!r} must have one finite value per point")
            ch[str(name)] = [float(x) for x in b]
        # full precision (S4): a rounded pin moves arclengths by ~0.01 mm on a long line, enough to flip
        # a later relation's choice, so locking a layer would change the sheet
        marks.append({"points": [[float(x), float(y)] for x, y in a], "channels": ch,
                      "meta": json.loads(json.dumps(dict(m.get("meta") or {}), default=float))})
    return marks


def _layer_seed(rec, L, k) -> int:
    """Layer k's own seed: `seed` when the layer gives one (a re-rolled layer), else sheet seed + k."""
    return int(L["seed"]) if L.get("seed") is not None else core.part_seed(rec["seed"], k)


# ---------------------------------------------------------------------------
# the executor
# ---------------------------------------------------------------------------

_CACHE: "OrderedDict[str, tuple]" = OrderedDict()
_CACHE_MAX = 48


def clear_cache() -> None:
    _CACHE.clear()


def _h(*objs) -> str:
    return hashlib.sha1(json.dumps(objs, sort_keys=True, default=str).encode()).hexdigest()


def _wild_ok(R, L, side=None) -> bool:
    """May a "*" side of R stand for layer L (the opt-in except / roles / not_roles filters, and, S0″,
    `src_…` / `dst_…` ones that narrow one side only)?"""
    for pre in ("", *((f"{side}_",) if side else ())):
        if (L["id"] in R.get(pre + "except", ()) or (pre + "roles" in R and L["role"] not in R[pre + "roles"])
                or L["role"] in R.get(pre + "not_roles", ())):
            return False
    return True


def _visible(layers, k, R=None, side=None) -> list[str]:
    return [L["id"] for L in layers[:k] if L["role"] != UNSEEN and (R is None or _wild_ok(R, L, side))]


def _pairs(R, k, layers, pos) -> list[tuple[str, str]]:
    """The (src, dst) pairs a contact relation acts on at step k."""
    cur = layers[k]["id"]
    vis_cur = layers[k]["role"] != UNSEEN
    S, D = R["src"], R["dst"]
    if S == "*" and D == "*":
        return [(i, cur) for i in _visible(layers, k, R, "src")] if vis_cur and _wild_ok(R, layers[k], "dst") else []
    if S == "*":
        if D == cur:
            return [(i, D) for i in _visible(layers, k, R, "src")]
        return [(cur, D)] if vis_cur and pos[D] < k and _wild_ok(R, layers[k], "src") else []
    if D == "*":
        if S == cur:
            return [(S, j) for j in _visible(layers, k, R, "dst")]
        return [(S, cur)] if vis_cur and pos[S] < k and _wild_ok(R, layers[k], "dst") else []
    return [(S, D)] if max(pos[S], pos[D]) == k else []


def _renderer_of(rec, L) -> dict:
    if "part" in L:
        return L["part"].get("renderer", rec["renderer"])
    return L.get("renderer", rec["renderer"])


def _pen_mm(spec) -> float | None:
    v = (spec or {}).get("pen")
    return round(float(v), 4) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _layer_tags(rec, L, k) -> dict:
    """The tags every mark of layer k carries (`pen_mm`: its renderer's pen width, for relations that
    size gaps or bends by the line's real weight)."""
    t = {"layer": L["id"], "score_layer": L["id"], "part": k, "of_role": L["role"], "colour": L["pen"]}
    if "composer" not in L:
        pm = _pen_mm(_renderer_of(rec, L))
        if pm is not None:
            t["pen_mm"] = pm
    return t


def _tag(marks, L, k, rec=None, sealed=None) -> list[Mark]:
    """Layer tags, plus a stable mark id (`mid`, with `mid_s0` = where the mark starts on the line it
    was grown as; `_relations.cut` keeps both, so an event can name a stretch whatever cuts came later)."""
    t = _layer_tags(rec, L, k) if rec is not None else {"layer": L["id"], "score_layer": L["id"], "part": k,
                                                         "of_role": L["role"], "colour": L["pen"]}
    sub = (sealed or {}).get(L["id"], {}).get("recipe")
    out = []
    for i, m in enumerate(marks):
        meta = {**t, "mid": f"{L['id']}:{i}", "mid_s0": 0.0}
        if sub is not None:
            j = int(m.meta.get("inner_part", 0) or 0)
            parts = sub.get("parts") or []
            pm = _pen_mm(parts[j].get("renderer", sub.get("renderer")) if j < len(parts) else sub.get("renderer"))
            if pm is not None:
                meta["pen_mm"] = pm
        out.append(m.evolve(meta=meta))
    return out


def _pinned(rec, L, k, which: str = "marks") -> list[Mark]:
    """A pinned layer's marks (`which`: "marks" as grown, "final" when the score had played), rebuilt from the
    pin (channels and meta kept), with its layer tags."""
    t = _layer_tags(rec, L, k)
    out = []
    for i, m in enumerate(L["pin"][which]):
        m = _unshared(m, L["pin"]["marks"])
        meta = {**m.get("meta", {}), **{a: b for a, b in t.items()
                                         if not (a == "colour" and (m.get("meta") or {}).get("own_pen"))
                                         and not (a == "pen_mm" and "pen_mm" in (m.get("meta") or {}))}}
        meta.setdefault("mid", f"{L['id']}:{i}")
        meta.setdefault("mid_s0", 0.0)
        out.append(Mark(np.asarray(m["points"], float), {a: np.asarray(b, float) for a, b in m["channels"].items()},
                        meta))
    return out


def _mark_json(m: Mark) -> dict:
    return {"points": [[float(x), float(y)] for x, y in m.points],
            "channels": {a: [float(x) for x in b] for a, b in m.channels.items()},
            "meta": json.loads(json.dumps(core._jsonable(dict(m.meta)), default=float))}


def pin(score: Mapping, ids, *, library=None) -> dict:
    """Lock layers in place: each layer in `ids` gets `lock`, its own `seed` frozen, and (unless it is a
    sealed composer, which hears nobody) a `pin` holding its marks as they stand once it has GROWN (its
    part drawn, its grow relations played: where it was placed and what it heard) and, when its contact
    relations changed it, its FINAL lines (when the whole score had played). A pinned layer no longer
    regrows: at its step it is laid down as grown and every relation plays as before, so what it does to
    the other layers stays (a crossing that cuts them); when the score has played, it is reset to its
    final lines. So locking alone changes nothing on the sheet, and no edit anywhere moves a locked line
    (S4, 2026-10-19; before, the pin held the end of its step and skipped its contact relations, which
    dropped the cuts it made in earlier layers). The final lines are shared with the grown ones where
    they kept them (each line stored once, 2026-10-21; see the module docstring). Unpin by removing
    `pin`."""
    rec = validate(score, library=library)
    rec.pop("parts", None)
    ids = list(ids)
    have = {L["id"] for L in rec["layers"]}
    bad = sorted(set(ids) - have)
    if bad:
        raise RecipeError(f"pin: no layer(s) {bad}")
    sh = run(rec, library=library, capture=set(ids))
    cap = sh.meta["captured"]
    for L in rec["layers"]:
        if L["id"] not in set(ids):
            continue
        k = [x["id"] for x in rec["layers"]].index(L["id"])
        L["lock"], L["seed"] = True, _layer_seed(rec, L, k)
        if "composer" not in L:
            # a sealed composer hears nobody: its frozen seed already holds its drawing still (and keeps its
            # own inks); every other layer keeps its geometry as it stands once grown
            L["pin"] = {"marks": [_mark_json(m) for m in cap[L["id"]]]}
            final = [_mark_json(m) for m in sh.meta["captured_final"][L["id"]]]
            if final != L["pin"]["marks"]:
                L["pin"]["final"] = _share(final, L["pin"]["marks"])      # each line stored once
    return validate(rec, library=library)


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
        if L.get("seed") is not None:
            p.seed = int(L["seed"])
        return p.run(box)
    if "lines" in L:
        return [Mark(np.asarray(line, float), {}, {"lines": True}) for line in L["lines"]]
    if "composer" not in L:
        return []                       # grown only by its relations
    x0, y0, w, h = box
    sub = {**copy.deepcopy(L["composer"]), "frame": [w, h], "seed": _layer_seed(rec, L, k)}
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


def _mark_ref(marks, i, s, s0_key="mid_s0"):
    """(mid, s on the uncut line) for index i into `marks` (as the relation saw them), or Nones."""
    if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(marks):
        return None, None
    md = marks[i].meta
    if "mid" not in md:
        return None, None
    s_u = None if s is None else [round(float(v) + float(md.get(s0_key, 0.0)), 2) for v in s]
    return md["mid"], s_u


def _apply(rec, R, src_id, dst_id, k, ground, state, log, unseen, ltags, spent):
    """One application of relation R to (src, dst). `ltags`: layer id → its mark tags; `spent`:
    relation id → firings so far (for `budget`)."""
    rel = get_relation(R["kind"])
    budget = R.get("budget")
    left = None if budget is None else max(int(budget) - spent.get(R["id"], 0), 0)
    grp = R.get("budget_group")
    if grp is not None:                 # S0″: a budget several relations share; the tighter of the two holds
        g_left = max(int(rec["budget_groups"][grp]) - spent.get(f"group:{grp}", 0), 0)
        left = g_left if left is None else min(left, g_left)
    rctx = RCtx(tuple(rec["frame"]), int(R.get("seed", rec["seed"])), R["id"], R["kind"], src_id, dst_id, k, state,
                ground, left)
    srcs = src_id.split("+") if isinstance(R["src"], list) else None
    base = {"relation": R["id"], "kind": R["kind"], "src": srcs[0] if srcs else src_id, "dst": dst_id, "step": k}
    if srcs:
        base["srcs"] = list(srcs)
    if R["p"] < 1.0 and rctx.rng("p").random() >= R["p"]:
        log.append({**base, "outcome": "silent"})
        return
    if left == 0:
        log.append({**base, "outcome": "spent"})
        return
    if srcs:
        src = [m for lid in srcs for m in ground[lid]]
    elif src_id == "*":
        order = list(ground)
        src = [m for lid in order[:order.index(dst_id)] if lid not in unseen and _wild_ok(R, ltags[lid]["_L"], "src")
               for m in ground[lid]]
    else:
        src = list(ground[src_id])
    dst = list(ground[dst_id])
    both = src + dst
    need = set.intersection(*(set(m.channels) for m in both)) if both else set()
    out = rel.fn(rctx, src, dst, **copy.deepcopy(R["params"]))
    out = _check_out(out, f"relation {R['id']!r} ({R['kind']})", rel.phase, need)
    if out.dst is not None:
        ground[dst_id] = _keep_meta(out.dst, ltags[dst_id])
    if out.src is not None and src_id != "*" and not srcs:
        ground[src_id] = _keep_meta(out.src, ltags[src_id])
    for e in out.events or ():
        e = dict(e)
        ev = {**base, "outcome": str(e.pop("outcome", "fired"))}
        for key in ("at", "s", "s_src"):
            if key in e:
                ev[key] = _r(e.pop(key))
        ev.update(json.loads(json.dumps(e, default=float)))
        # stable refs (S0′): the mark ids and the stretches on the uncut lines, beside the old fields
        mid, s_u = _mark_ref(dst, ev.get("mark"), ev.get("s"))
        if mid is not None:
            ev["mid"] = mid
            if s_u is not None:
                ev["s_uncut"] = s_u
        mid, s_u = _mark_ref(src, ev.get("mark_src", ev.get("src_mark")), ev.get("s_src"))
        if mid is not None:
            ev["mid_src"] = mid
            if s_u is not None:
                ev["s_src_uncut"] = s_u
        log.append(ev)
        if ev["outcome"] not in NEUTRAL:
            spent[R["id"]] = spent.get(R["id"], 0) + 1
            if grp is not None:
                spent[f"group:{grp}"] = spent.get(f"group:{grp}", 0) + 1


def _keep_meta(new, tags) -> list[Mark]:
    """Marks a relation returned keep their layer's tags (a relation may build fresh Marks). A mark
    with `own_pen` keeps its own colour; a mark that already has a `pen_mm` keeps it."""
    t = {a: b for a, b in tags.items() if a != "_L"}
    out = []
    for m in new:
        want = {a: b for a, b in t.items()
                if not (a == "colour" and m.meta.get("own_pen")) and not (a == "pen_mm" and "pen_mm" in m.meta)}
        out.append(m if all(m.meta.get(a) == b for a, b in want.items()) else m.evolve(meta=want))
    return out


def _lib_key(lib) -> list:
    """What makes two libraries draw differently (S4: the app pins snapshots and entry hashes), so the
    per-layer cache never hands one library's lines to another."""
    pins = getattr(lib, "pins", None) or {}
    return [str(getattr(lib, "root", "")), getattr(lib, "snapshot_id", None),
            sorted(f"{k[0]}/{k[1]}@{v}" for k, v in pins.items()) if isinstance(pins, Mapping) else None]


def run(score: Mapping, *, library=None, cache: bool = True, capture=()) -> Sheet:
    """Play a v2 score → Sheet (deterministic in the score alone). `capture`: layer ids whose marks,
    as they stand once grown (before their step's contact relations), go to `sheet.meta["captured"]`
    (what `pin` stores)."""
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
    spent: dict[str, int] = {}
    captured: dict[str, list] = {}

    ltags = {L["id"]: {**_layer_tags(rec, L, k), "_L": L} for k, L in enumerate(layers)}
    key = _h("synth", core.KIT_VERSION, rec["frame"], rec["seed"], rec["margin"], rec["renderer"], _lib_key(lib),
             rec.get("budget_groups"))
    hits = 0
    for k, L in enumerate(layers):
        acting = [R for R in rec["relations"]
                  if (R["dst"] == L["id"] and get_relation(R["kind"]).phase == "grow")
                  or (get_relation(R["kind"]).phase == "contact" and _pairs(R, k, layers, pos))]
        key = _h(key, L, acting)
        if cache and key in _CACHE:
            g, lg, used, sl, sp, grown = _CACHE[key]
            _CACHE.move_to_end(key)
            ground, log, sealed, spent = dict(g), list(lg), dict(sl), dict(sp)
            state.used = dict(used)
            hits += 1
            if capture and L["id"] in capture:
                captured[L["id"]] = list(grown)
            continue
        if "pin" in L:                  # locked: its grown geometry as pinned (part + grow relations, S4)
            ground[L["id"]] = _pinned(rec, L, k)
        else:
            ground[L["id"]] = _tag(_grow_layer(rec, L, k, state, lib, sealed), L, k, rec, sealed)
            if L["id"] in sealed:
                sealed[L["id"]]["marks0"] = tuple(ground[L["id"]])
            for R in acting:
                if get_relation(R["kind"]).phase == "grow":
                    s_id = "+".join(R["src"]) if isinstance(R["src"], list) else R["src"]
                    _apply(rec, R, s_id, L["id"], k, ground, state, log, unseen, ltags, spent)
        grown = tuple(ground[L["id"]])          # the layer once grown: what a pin holds (cached with the step)
        if capture and L["id"] in capture:
            captured[L["id"]] = list(grown)
        # contact relations play at every step, a pinned layer's too: what it does to the layers before it
        # (a crossing that cuts them) stays, so locking a layer changes nothing by itself
        for R in acting:
            if get_relation(R["kind"]).phase == "contact":
                for s_id, d_id in _pairs(R, k, layers, pos):
                    _apply(rec, R, s_id, d_id, k, ground, state, log, unseen, ltags, spent)
        if cache:
            _CACHE[key] = (dict(ground), list(log), dict(state.used), dict(sealed), dict(spent), grown)
            while len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
    for k, L in enumerate(layers):           # held: a pinned layer ends as its final lines, whatever moved
        if "pin" in L and "final" in L["pin"]:
            ground[L["id"]] = _pinned(rec, L, k, "final")
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
        jobs = [(spec, ms, None) for spec, ms in jobs]
        if any(m.meta.get("own_pen") for m in mine):
            jobs = _own_pen_jobs(jobs, lib)
        for spec, ms, own_colour in jobs:
            rnd = core.get("renderer", spec["id"])
            rctx = core.Ctx((W, H), _region(rec, L), _layer_seed(rec, L, k), rec["seed"], k,
                            "renderer", rnd.id, state)
            for i in rnd.fn(rctx, ms, **{a: b for a, b in copy.deepcopy(spec).items() if a != "id"}):
                if not isinstance(i, Ink):
                    raise core.ChannelError(f"renderer {rnd.id!r} returned a {type(i).__name__}")
                inks.append(Ink(i.points, i.closed, i.filled, i.pen,
                                {**i.meta, **tags,
                                 "colour": own_colour or (i.meta or {}).get("colour") or L["pen"]}))
    t2 = time.perf_counter()

    played = played_score(rec, log, sealed)
    used = [state.used[k] for k in sorted(state.used)]
    meta = {"recipe": {**rec, "parts": _derived_parts(rec)}, "library": used, "inset": rec["margin"],
            "kit": core.KIT_VERSION, "synth": SCORE_VERSION,
            "parts": [{"index": k, "seed": _layer_seed(rec, L, k), "layer": L["id"], "role": L["role"],
                       "voice": _technique(L)} for k, L in enumerate(layers)],
            "seconds": {"marks": round(t1 - t0, 3), "inks": round(t2 - t1, 3)}, "cache_hits": hits,
            "notes": {"score": played}}
    if capture:
        meta["captured"] = captured
        meta["captured_final"] = {lid: list(ground[lid]) for lid in captured}
    sheet = Sheet((W, H), marks, inks, meta)
    if rec["devices"]:
        sheet = apply_devices(sheet, rec["devices"])
    return sheet


def _own_pen_jobs(jobs, lib) -> list[tuple]:
    """Split render jobs by `own_pen` (S0′): marks a relation added with their own pen
    ({"colour": Flexoki name, "renderer": spec}) render with that renderer and colour, after the
    layer's own marks. Groups keep first-appearance order; empty groups are dropped."""
    out = []
    for spec, ms, colour in jobs:
        groups: "OrderedDict[str, tuple]" = OrderedDict()
        groups[""] = (spec, [], colour)
        for m in ms:
            op = m.meta.get("own_pen")
            if not op:
                groups[""][1].append(m)
                continue
            if not isinstance(op, Mapping):
                raise RecipeError(f"own_pen must be {{colour, renderer}}, got {op!r}")
            rs = core._module_spec("renderer", op.get("renderer") or spec, "own_pen", lib)
            key = _h(op.get("colour"), rs)
            if key not in groups:
                groups[key] = (rs, [], op.get("colour") or colour)
            groups[key][1].append(m)
        out += [g for g in groups.values() if g[1]]
    return out


def _technique(L) -> str:
    if "part" in L:
        return L["part"]["voice"]["id"]
    if "lines" in L:
        return "lines"
    if "composer" not in L:
        return "relations"
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
        if ev["outcome"] in ("silent", "spent"):
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


def written(score_or_sheet) -> dict | None:
    """The written score: a copy of a score dict, or the one a played sheet carries (None for a v1 sheet)."""
    if isinstance(score_or_sheet, Sheet):
        pl = played(score_or_sheet)
        return copy.deepcopy(pl.get("written")) if pl and pl.get("written") else None
    return copy.deepcopy(dict(score_or_sheet))


def replay(score_or_sheet, *, drop=(), keep_only=None, drop_kinds=(), keep_only_kinds=None,
           devices: bool = False, library=None, cache: bool = True) -> Sheet | None:
    """Counterfactuals (S0′): the score played again with some relations taken out — `drop` /
    `keep_only` by relation id, `drop_kinds` / `keep_only_kinds` by kind. Devices are left off unless
    `devices`. Takes a score or a played sheet; None when a sheet has no written v2 score."""
    w = written(score_or_sheet)
    if w is None:
        return None
    rels = [r for r in w.get("relations", []) if r["id"] not in set(drop) and r["kind"] not in set(drop_kinds)]
    if keep_only is not None:
        rels = [r for r in rels if r["id"] in set(keep_only)]
    if keep_only_kinds is not None:
        rels = [r for r in rels if r["kind"] in set(keep_only_kinds)]
    w["relations"] = rels
    if not devices:
        w["devices"] = []
    w.pop("parts", None)
    return run(w, library=library, cache=cache)


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

"""Score writers (S2 contract, lead-owned, 2026-10-19): composers that write scores instead of drawing.

Design: `docs/synthesis-bench/design-2026-10-19.md` §6. A writer receives a
region and the ground (the layers already on the sheet) and returns a score
fragment: layers and relations inside its region, plus the decisions it took.
The executor (`_synth.run`) draws it. Two writers can share a sheet, and a
writer can write onto a ground Ian started. "Compose" asks a writer for a
score; "Recompose" asks it again around the layers Ian locked.

    from ._writers import writer, WCtx
    from .core import P

    @writer("listen", params=[P("balance", "choice", "one", "…", choices=("none", "one", "speakers", "all"))],
            doc="layers that listen …")
    def listen(wctx: WCtx, *, balance):
        L0 = wctx.id("L0")                      # ids carry the writer's prefix
        sheet = wctx.play(fragment_so_far)      # read geometry while writing (ground + fragment, cached)
        ...
        return {"layers": [...], "relations": [...], "decisions": {...}}

    score = compose("listen", frame=[250, 175], seed=15102, params={"balance": "one"})
    again = recompose(score, locked=["L1"], seed=15199)

Rules a writer keeps
- Every id it writes starts with `wctx.prefix` ("" for the first writer on an
  empty sheet, "w1_", "w2_" … after). Relations may name ground layers (to
  hear them) but may not change a ground layer's spec.
- `wctx.keep`: layers Ian locked, as specs (usually pinned, see
  `_synth.pin`). The writer includes each one verbatim, under its id, and
  writes the rest around it; it may listen to them like any earlier layer.
- Decisions: what it chose (counts, palette, which kinds fired) — they go to
  `decisions["writers"][i]["decisions"]` beside its id, params, seed, region
  and prefix, which is what `recompose` reads back.
- Determinism: draw only from `wctx.rng(*tags)` (seeded by the score seed,
  the writer id and its prefix).
- Pens around locks (Ian, 2026-10-19): when `wctx.keep` is not empty the writer
  builds its palette around the pens of the kept layers (`palette_around`), so a
  kept line belongs to the recomposed drawing instead of reading as a foreign
  pen. Draw the palette as usual first (the random stream stays the same), then
  substitute.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import numpy as np

from .core import KitError, P, Param, RecipeError, tag  # noqa: F401  (P re-exported for writers)

_WRITERS: dict[str, "Writer"] = {}


@dataclass(frozen=True)
class Writer:
    id: str
    fn: Callable
    params: tuple
    doc: str

    def validate(self, spec: Mapping | None, *, where: str = "") -> dict:
        spec = dict(spec or {})
        names = {p.name for p in self.params}
        bad = sorted(k for k in spec if k not in names)
        if bad:
            raise RecipeError(f"{where}: writer {self.id!r} has no param(s) {bad}; known: {sorted(names)}")
        return {p.name: p.validate(spec.get(p.name, p.default), where=f"{where} ({self.id})") for p in self.params}

    def spec(self) -> dict:
        return {"id": self.id, "doc": self.doc, "params": [p.to_json() for p in self.params]}


def writer(id: str, *, params=(), doc: str = ""):
    for p in params:
        if not isinstance(p, Param):
            raise KitError(f"writer {id!r}: params must be P(...)")

    def wrap(fn):
        if id in _WRITERS and _WRITERS[id].fn is not fn:
            raise KitError(f"writer id {id!r} is already registered")
        _WRITERS[id] = Writer(id, fn, tuple(params), doc)
        return fn
    return wrap


def get_writer(id: str) -> Writer:
    from .core import discover  # noqa: PLC0415
    discover()
    if id not in _WRITERS:
        raise RecipeError(f"unknown writer {id!r}; known: {sorted(_WRITERS)}")
    return _WRITERS[id]


def writer_list() -> list[dict]:
    from .core import discover  # noqa: PLC0415
    discover()
    return [_WRITERS[k].spec() for k in sorted(_WRITERS)]


@dataclass(frozen=True)
class WCtx:
    frame: tuple[float, float]
    region: tuple[float, float, float, float]
    seed: int
    writer: str
    prefix: str
    margin: float
    ground: dict | None = field(default=None, repr=False)       # the score already on the sheet (validated)
    keep: tuple = field(default=(), repr=False)                  # locked layer specs to include verbatim
    library: Any = field(default=None, repr=False, compare=False)
    sheet_seed: int | None = None        # the score's seed (the ground's, when there is one)

    def rng(self, *tags) -> np.random.Generator:
        return np.random.default_rng([tag(self.seed), tag("writer"), tag(self.writer), tag(self.prefix),
                                      *map(tag, tags)])

    def id(self, name: str) -> str:
        return f"{self.prefix}{name}"

    def ground_ids(self) -> list[str]:
        return [L["id"] for L in (self.ground or {}).get("layers", [])]

    def score(self, fragment: Mapping) -> dict:
        """ground + fragment as one score (not yet validated)."""
        return _merge(self.frame, self.seed if self.sheet_seed is None else self.sheet_seed, self.margin,
                      self.ground, fragment)

    def play(self, fragment: Mapping):
        """Play ground + fragment so far (cached prefixes make repeated plays cheap)."""
        from . import _synth  # noqa: PLC0415
        return _synth.run(self.score(fragment), library=self.library)


def hue(c: str) -> str:
    return str(c).split("-")[0]


def palette_around(palette, kept, *, hue_of=hue) -> tuple[list, dict]:
    """Ian, 2026-10-19 ("build around locked pens"): the palette a writer drew, with the pens of its
    kept layers substituted in. Each kept pen not already in the palette takes the slot of a pen of
    its own hue if there is one, else the first slot no earlier kept pen holds (a palette full of
    kept pens grows). Returns (new palette, {old pen: new pen}) so the writer can rewrite every pen
    it planned from the old palette. Deterministic, no random draws."""
    pal = list(palette)
    held: set[int] = set()
    for c in dict.fromkeys(str(x) for x in kept if x):
        if c in pal:
            held.add(pal.index(c))
            continue
        same = [j for j, q in enumerate(pal) if hue_of(q) == hue_of(c) and j not in held]
        free = [j for j in range(len(pal)) if j not in held]
        j = same[0] if same else (free[0] if free else None)
        if j is None:
            pal.append(c)
            held.add(len(pal) - 1)
            continue
        pal[j] = c
        held.add(j)
    mapping = {a: b for a, b in zip(palette, pal) if a != b}
    return pal, mapping


def _merge(frame, seed, margin, ground, fragment) -> dict:
    g = copy.deepcopy(ground) if ground else {}
    g.pop("parts", None)
    out = {"version": 2, "frame": [float(frame[0]), float(frame[1])], "seed": int(seed), "margin": float(margin),
           "layers": list(g.get("layers", [])) + copy.deepcopy(list(fragment.get("layers", []))),
           "relations": list(g.get("relations", [])) + copy.deepcopy(list(fragment.get("relations", []))),
           "devices": list(g.get("devices", [])),
           "decisions": dict(g.get("decisions", {}))}
    for k in ("renderer", "label", "notes"):
        if g.get(k) is not None:
            out[k] = g[k]
    return out


def _region(frame, margin, region):
    if region is None:
        return (float(margin), float(margin), float(frame[0]) - 2 * margin, float(frame[1]) - 2 * margin)
    if len(region) != 4:
        raise RecipeError("region is [x, y, w, h]")
    return tuple(float(v) for v in region)


def compose(writer_id: str, *, frame, seed: int, params: Mapping | None = None, region=None,
            ground: Mapping | None = None, keep=(), margin: float = 5.0, prefix: str | None = None,
            library=None) -> dict:
    """Ask a writer for a score → the whole v2 score (ground + its fragment), validated."""
    from . import _synth  # noqa: PLC0415
    from . import library as _lib  # noqa: PLC0415
    lib = library if library is not None else _lib.default()
    w = get_writer(writer_id)
    p = w.validate(params, where="compose")
    g = _synth.validate(ground, library=lib) if ground else None
    sheet_seed = int(seed)
    if g is not None:            # the ground's seed stays the sheet's (its parts must not re-roll); the
        g.pop("parts", None)     # writer's own seed drives its decisions, and its layers' `seed` keys
        frame, margin, sheet_seed = g["frame"], g["margin"], int(g["seed"])
    used = [e.get("prefix", "") for e in (g or {}).get("decisions", {}).get("writers", [])]
    if prefix is None:
        prefix = "" if g is None else f"w{len(used) + 1}_"
    if g is not None and prefix in used:
        raise RecipeError(f"compose: prefix {prefix!r} is already used on this sheet")
    reg = _region(frame, margin, region)
    keep = tuple(copy.deepcopy(list(keep)))
    wctx = WCtx((float(frame[0]), float(frame[1])), reg, int(seed), w.id, prefix, float(margin), g, keep, lib,
                sheet_seed)
    frag = w.fn(wctx, **p)
    if not isinstance(frag, Mapping) or "layers" not in frag:
        raise KitError(f"writer {w.id!r} must return {{layers, relations, decisions}}")
    gids = set(wctx.ground_ids())
    kept = {L["id"]: L for L in keep}
    for L in frag["layers"]:
        lid = L.get("id", "")
        if lid in gids:
            raise KitError(f"writer {w.id!r}: layer {lid!r} is already on the ground")
        if lid in kept:
            if L != kept[lid]:
                raise KitError(f"writer {w.id!r}: locked layer {lid!r} must be included verbatim")
        elif not lid.startswith(prefix):
            raise KitError(f"writer {w.id!r}: layer id {lid!r} lacks the prefix {prefix!r}")
    missing = sorted(set(kept) - {L.get("id") for L in frag["layers"]})
    if missing:
        raise KitError(f"writer {w.id!r} dropped locked layer(s) {missing}")
    for R in frag.get("relations", []):
        if not str(R.get("id", "")).startswith(prefix):
            raise KitError(f"writer {w.id!r}: relation id {R.get('id')!r} lacks the prefix {prefix!r}")
    score = _merge(frame, sheet_seed, margin, g, frag)
    entry = {"writer": w.id, "params": p, "seed": int(seed), "prefix": prefix, "region": list(reg),
             "layers": [L["id"] for L in frag["layers"]], "relations": [R["id"] for R in frag.get("relations", [])],
             "decisions": copy.deepcopy(dict(frag.get("decisions") or {}))}
    score["decisions"]["writers"] = list(score["decisions"].get("writers", [])) + [entry]
    for k in ("label", "notes"):
        if frag.get(k):
            score[k] = str(frag[k])
    return _synth.validate(score, library=lib)


def recompose(score: Mapping, *, locked=(), seed: int, writer_index: int = -1, params: Mapping | None = None,
              library=None) -> dict:
    """Ask the writer that wrote part of `score` again, with a new seed, around the layers in `locked`
    (which keep their specs; pin them first with `_synth.pin` so their geometry holds still). Layers
    and relations of other writers / Ian's own stay as they are."""
    from . import _synth  # noqa: PLC0415
    s = _synth.validate(score, library=library)
    s.pop("parts", None)
    writers = s["decisions"].get("writers") or []
    if not writers:
        raise RecipeError("recompose: this score has no writer to ask")
    e = writers[writer_index]
    mine_L, mine_R = set(e["layers"]), set(e["relations"])
    bad = sorted(set(locked) - mine_L)
    if bad:
        raise RecipeError(f"recompose: {bad} are not layers this writer wrote")
    keep = [L for L in s["layers"] if L["id"] in set(locked)]
    ground = {**s, "layers": [L for L in s["layers"] if L["id"] not in mine_L],
              "relations": [R for R in s["relations"] if R["id"] not in mine_R],
              "decisions": {**s["decisions"], "writers": [x for x in writers if x is not e]}}
    ground_ids = {L["id"] for L in ground["layers"]}
    ground["relations"] = [R for R in ground["relations"]
                           if all(v == "*" or v in ground_ids
                                  for v in ([*R["src"]] if isinstance(R["src"], list) else [R["src"]]) + [R["dst"]])]
    has_ground = bool(ground["layers"])
    out = compose(e["writer"], frame=s["frame"], seed=seed, params={**e["params"], **(params or {})},
                  region=e["region"], ground=ground if has_ground else None, keep=keep, margin=s["margin"],
                  prefix=e["prefix"], library=library)
    if not has_ground:                 # an empty ground loses the score-level keys: carry them over
        out["renderer"], out["devices"] = s["renderer"], s["devices"]
        out = _synth.validate(out, library=library)
    return out

# FROZEN from research commit c712045: tools/gesture/gesture/kit/sampler.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""The combination sampler (round 10 `combo_search`, moved into the kit for the
app's Sampler study, 2026-10-17).

Ian on the round-10 combination search: the population had "some golden ones
here", and "curiously I dig the unbred ones more. it's like these are
collapsing into a style." So the app keeps the SAMPLING only — one seed, one
whole unbred combination — never the selector or the breeding.

This is a copy of `experiments/combo_search.py`'s sampler (`sample_recipe`,
`repair`, `summarize` and the pieces they call), unchanged except that the
pools (heavy hands, wire hands, dance trails, tempi) are an argument:

- `PRIORS` — combo_search's own pools: `sample_recipe(rng)` with them returns
  exactly what combo_search's does for the same generator (a test checks);
- `library_pools(library)` — the priors kept where the library still holds
  them, plus every other generative entry of the library (sorted, appended to
  both hand pools: a hand with no prior role may speak as either voice), so
  hands learned later enter the sample space with no edit here.

`sample(seed, library=...)` is what a study calls: a fresh generator seeded
from the seed alone, the library's pools, the recipe's own seed = the seed.
Not a registered technique (it makes recipes, not marks).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

from .core import validate

FRAME = (267.0, 180.0)

# Pools are priors, not rules: a hand may appear in both, but never in the
# heavy AND the wire voice of one recipe (distinct grammars, never averaged).
HEAVY_HANDS = ("hokusai", "nastaliq", "shikasta", "matisse", "ingres", "marden", "meander69",
               "dance_fluidity", "dance_levitation", "dance_staccato", "mime_mantis", "mime_dragon",
               "mime_roadrunner")
WIRE_HANDS = ("bubble", "polygon_walk", "aaron", "lichtenberg", "molnar_letters", "meander69",
              "mime_roadrunner", "mime_monkey_hands", "mime_prairiedog", "mime_penguin",
              "dance_particles", "dance_thrusting", "marden")
TRAILS = ("dragon", "hummingbird", "levitation", "mantis", "outofbalance", "particles", "penguin",
          "staccato", "thrusting")
TEMPI = ("cmu_49_10", "cmu_55_mantis", "fluidity", "levitation", "particles", "staccato")
MACHINES = ("compass", "ruler", "stair", "koch", "codebook")
CHARTS = ("kappa", "route", "phase", "atlas", "ledger")


@dataclass(frozen=True)
class Pools:
    heavy: tuple[str, ...]
    wire: tuple[str, ...]
    trails: tuple[str, ...]
    tempi: tuple[str, ...]


PRIORS = Pools(HEAVY_HANDS, WIRE_HANDS, TRAILS, TEMPI)


def _generative(library, kind: str) -> list[str]:
    from .library import PolicyError  # noqa: PLC0415
    out = []
    for eid in library.ids(kind):
        e = library.entry(kind, eid)
        if e.get("policy") != "generative":
            continue
        try:
            library.check(e, "generate")
        except PolicyError:
            continue
        out.append(eid)
    return sorted(out)


def library_pools(library) -> Pools:
    """The priors where the library still holds them, plus every other
    generative entry (sorted) — new hands enter both hand pools."""
    hands = _generative(library, "hand")
    have = set(hands)
    known = set(HEAVY_HANDS) | set(WIRE_HANDS)
    extra = tuple(h for h in hands if h not in known)
    trails = _generative(library, "dance_trail")
    tempi = _generative(library, "tempo")
    return Pools(heavy=tuple(h for h in HEAVY_HANDS if h in have) + extra,
                 wire=tuple(h for h in WIRE_HANDS if h in have) + extra,
                 trails=tuple(t for t in TRAILS if t in set(trails)) + tuple(t for t in trails if t not in TRAILS),
                 tempi=tuple(t for t in TEMPI if t in set(tempi)) + tuple(t for t in tempi if t not in TEMPI))


def _r(rng, lo, hi, nd=2):
    return round(float(rng.uniform(lo, hi)), nd)


def _pick(rng, seq, p=None):
    return seq[int(rng.choice(len(seq), p=p))]


def _hands_of(part) -> set:
    v = part["voice"]
    out = set(v.get("hands") or [])
    for k in ("hand",):
        if v.get(k):
            out.add(v[k])
    return out


def sample_heavy_voice(rng, avoid=(), pools: Pools = PRIORS):
    pool = [h for h in pools.heavy if h not in avoid]
    kind = _pick(rng, ("drift", "hand", "dance"), p=(0.55, 0.25, 0.20))
    if kind == "drift":
        n = int(rng.choice([2, 3], p=[0.6, 0.4]))
        hands = [str(h) for h in rng.choice(pool, size=n, replace=False)]
        return {"id": "drift", "hands": hands, "blend": _pick(rng, ("interp", "mixture"), p=(0.6, 0.4)),
                "length": _r(rng, 2.5, 5.5, 1), "joins": _pick(rng, ("smooth", "chain"))}
    if kind == "hand":
        return {"id": "hand", "hand": _pick(rng, pool), "length": _r(rng, 2.5, 5.5, 1),
                "joins": _pick(rng, ("smooth", "chain"))}
    return {"id": "dance", "trail": _pick(rng, pools.trails),
            "effectors": _pick(rng, ("hands", "all", "lhand", "hands+head")),
            "t0": _r(rng, 0.0, 20.0, 1), "seconds": _r(rng, 5.0, 14.0, 1), "cut": "phrase"}


def sample_weight(rng, voice, pools: Pools = PRIORS):
    """The heavy voice's weight source: a modulator chain."""
    opts = ["field", "timing", "prosody"] + (["own_tempo"] if voice["id"] == "dance" else [])
    p = {"field": 0.35, "timing": 0.3, "prosody": 0.25, "own_tempo": 0.3}
    w = np.array([p[o] for o in opts])
    kind = opts[int(rng.choice(len(opts), p=w / w.sum()))]
    if kind == "field":
        return [{"id": "constant", "r": None, "W": _r(rng, 2.0, 4.0, 1), "M": _r(rng, 5.0, 9.0, 1)},
                {"id": "field", "preset": _pick(rng, ("noise", "noise", "noise", "radial", "bands")),
                 "scale": _r(rng, 0.08, 0.3), "amount": _r(rng, 0.5, 1.0)}]
    if kind == "timing":
        return [{"id": "timing", "tempo": _pick(rng, pools.tempi), "amount": _r(rng, 0.6, 1.2),
                 "mass_width": _r(rng, 4.0, 9.0, 1)}]
    if kind == "prosody":
        return [{"id": "prosody", "rhythm": "event", "unit": "pulse", "contrast": _r(rng, 0.3, 1.0),
                 "density": _r(rng, 0.5, 2.0), "W": _r(rng, 2.0, 3.5, 1), "M": _r(rng, 4.0, 8.0, 1)}]
    return [{"id": "own_tempo", "amount": _r(rng, 0.7, 1.3), "beads": _pick(rng, ("pauses", "dwell")),
             "mass_width": _r(rng, 2.0, 5.0, 1)}]


def sample_heavy_renderer(rng):
    u = rng.random()
    if u < 0.07:
        return {"id": "restate", "copies": int(rng.integers(3, 9)), "pen": 0.35}
    if u < 0.12:
        return {"id": "coil", "rings": int(rng.integers(3, 8)), "pen": 0.35}
    return {"id": "nib", "style": _pick(rng, ("c", "e", "c+e", "b+", "a"), p=(0.3, 0.3, 0.2, 0.1, 0.1)),
            "pen": 0.4}


def sample_heavy(rng, avoid=(), pools: Pools = PRIORS):
    v = sample_heavy_voice(rng, avoid, pools)
    mods = sample_weight(rng, v, pools)
    if mods[0]["id"] == "prosody" and v["id"] == "drift":
        v = {**v, "id": "drift_tokens"}           # prosody listens to grammar tokens too
    if v["id"] in ("drift", "drift_tokens", "hand") and rng.random() < 0.15:
        mods = [{"id": "handover", "a": _pick(rng, ("ruler", "stair", "compass")), "b": "none",
                 "share": _r(rng, 0.1, 0.3), "stretch": _r(rng, 10.0, 30.0, 1)}] + mods
    return {"label": "heavy", "voice": v, "modulators": mods, "renderer": sample_heavy_renderer(rng)}


def sample_wire(rng, avoid=(), pools: Pools = PRIORS):
    kind = _pick(rng, ("hand", "machine", "dance"), p=(0.5, 0.25, 0.25))
    pool = [h for h in pools.wire if h not in avoid]
    if kind == "hand":
        v = {"id": "hand", "hand": _pick(rng, pool), "length": _r(rng, 2.5, 5.0, 1),
             "joins": _pick(rng, ("chain", "smooth"))}
    elif kind == "machine":
        v = {"id": "machine", "grammar": _pick(rng, MACHINES),
             "hand": _pick(rng, [h for h in pools.heavy + pools.wire if h not in avoid]),
             "length": _r(rng, 2.0, 4.5, 1)}
    else:
        v = {"id": "dance", "trail": _pick(rng, pools.trails),
             "effectors": _pick(rng, ("hands", "all", "rhand", "head")),
             "t0": _r(rng, 0.0, 20.0, 1), "seconds": _r(rng, 5.0, 15.0, 1), "cut": "phrase"}
    return {"label": "wire", "voice": v, "modulators": [{"id": "wire"}],
            "renderer": {"id": "wire", "pen": _r(rng, 0.2, 0.35)}}


def sample_measure(rng):
    """The heavy line's own measurement, drawn beside it (appended to its chain)."""
    return {"id": "annotate", "chart": _pick(rng, CHARTS),
            "layout": _pick(rng, ("shadow", "right", "below"), p=(0.4, 0.3, 0.3)),
            "drawn_by": _pick(rng, (None, "matisse", "hokusai"), p=(0.6, 0.2, 0.2)),
            "split": _r(rng, 0.3, 0.45), "gap": _r(rng, 0.8, 2.5), "gain": _r(rng, 2.0, 6.0)}


def repair(recipe: dict, pools: Pools = PRIORS) -> dict:
    """Keep grammars distinct: the wire must not speak a hand the heavy voice uses."""
    r = copy.deepcopy(recipe)
    if len(r["parts"]) < 2:
        return r
    heavy = _hands_of(r["parts"][0])
    for part in r["parts"][1:]:
        v = part["voice"]
        if v.get("hand") in heavy:
            v["hand"] = next(h for h in pools.wire if h not in heavy)
    return r


def summarize(recipe: dict) -> str:
    """One line per recipe, readable on a thumbnail strip."""
    bits = []
    for part in recipe["parts"]:
        v = part["voice"]
        if v["id"] in ("drift", "drift_tokens"):
            s = ">".join(v["hands"]) + ("~" if v.get("blend") == "interp" else "")
        elif v["id"] == "hand":
            s = v["hand"]
        elif v["id"] == "machine":
            s = f"{v['grammar']}({v['hand']})"
        elif v["id"] == "dance":
            s = f"dance:{v['trail']}/{v.get('effectors', 'all')}"
        else:
            s = v["id"]
        if v.get("joins") == "chain":
            s += "[ch]"
        mods = []
        for m in part.get("modulators", []):
            if m["id"] in ("wire", "constant"):
                continue
            if m["id"] == "timing":
                mods.append(f"t:{m.get('tempo')}")
            elif m["id"] == "field":
                mods.append(f"f:{m.get('preset', 'noise')}")
            elif m["id"] == "annotate":
                mods.append(f"+{m.get('chart')}/{m.get('layout')}")
            else:
                mods.append(m["id"])
        rd = part.get("renderer", {"id": "wire"})
        rs = rd["id"] + (f":{rd['style']}" if rd["id"] == "nib" else "")
        bits.append(s + ("{" + ",".join(mods) + "}" if mods else "") + " " + rs)
    arr = recipe.get("arranger", {"id": "single"})["id"]
    return (f"[{arr}] " if arr != "single" else "") + "  x  ".join(bits)


def sample_recipe(rng, seed: int | None = None, *, pools: Pools = PRIORS, frame=FRAME, library=None) -> dict:
    """combo_search's `sample_recipe`, pools and frame as arguments; the
    result is validated (against `library`, default: the committed one)."""
    heavy = sample_heavy(rng, pools=pools)
    wire = sample_wire(rng, avoid=_hands_of(heavy), pools=pools)
    parts = [heavy, wire]
    u = rng.random()
    if u < 0.35:
        heavy["modulators"] = heavy["modulators"] + [sample_measure(rng)]
    elif u < 0.6:
        third = sample_wire(rng, avoid=_hands_of(heavy) | _hands_of(wire), pools=pools)
        if third["voice"]["id"] != "dance":
            third["voice"] = {"id": "dance", "trail": _pick(rng, pools.trails), "effectors": "hands",
                              "t0": _r(rng, 0.0, 20.0, 1), "seconds": _r(rng, 5.0, 12.0, 1), "cut": "phrase"}
        third["label"] = "dance"
        parts.append(third)
    arranger = {"id": "single"}
    if rng.random() < 0.15:
        n = len(parts)
        arranger = {"id": "poly_scatter", "counts": [1] + [int(rng.integers(2, 7)) for _ in range(n - 1)],
                    "sizes": [_r(rng, 0.7, 0.95)] + [_r(rng, 0.18, 0.4) for _ in range(n - 1)],
                    "bleed": _r(rng, 0.1, 0.4)}
    rec = {"frame": list(frame), "seed": int(seed if seed is not None else rng.integers(20000, 30000)),
           "arranger": arranger, "parts": parts, "renderer": {"id": "wire", "pen": 0.4}}
    rec = repair(rec, pools)
    rec["label"] = summarize(rec)
    validate(rec, library=library)
    return rec


# Machines whose lines are straight runs (compass headings, ruler runs with
# corner ticks, stair rook moves, koch polygons). Ian on Sampler seed 19 (round
# 11): "i dont like those staggered barbed straight lines".
STRAIGHT_MACHINES = ("compass", "ruler", "stair", "koch", "lsys")


def tidy(recipe: dict, pools: Pools = PRIORS, library=None) -> dict:
    """The `clean` option (round 12): the same combination with what Ian
    called pollution taken out, by rule, with no new draw from the generator,
    so the drawing he liked stays the drawing. Ian on seed 30: "nice drawing,
    unsure of the pollution to the right"; on seed 19: "i dont like those
    staggered barbed straight lines".

    - a wire voice that is a straight-run machine speaks its own hand instead
      (same hand, same length, smooth joins);
    - a handover to a straight-run machine is dropped from the heavy chain;
    - a measurement laid BESIDE the drawing (`annotate` right / below) is
      dropped, so nothing is drawn off the main drawing (one laid over it as a
      shadow stays);
    - a scatter of small copies becomes one surface (`single`).
    A recipe with none of these comes back unchanged."""
    r = copy.deepcopy(recipe)
    for part in r["parts"]:
        v = part["voice"]
        if v.get("id") == "machine" and v.get("grammar") in STRAIGHT_MACHINES:
            part["voice"] = {"id": "hand", "hand": v["hand"], "length": v.get("length", 3.0), "joins": "smooth"}
        part["modulators"] = [m for m in part.get("modulators", [])
                              if not (m["id"] == "handover" and (m.get("a") in STRAIGHT_MACHINES
                                                                 or m.get("b") in STRAIGHT_MACHINES))
                              and not (m["id"] == "annotate" and m.get("layout") in ("right", "below"))]
    if r.get("arranger", {}).get("id") == "poly_scatter":
        r["arranger"] = {"id": "single"}
    r = repair(r, pools)
    r["label"] = summarize(r)
    validate(r, library=library)
    return r


def sample(seed: int, *, library=None, frame=FRAME, pools: Pools | None = None, clean: bool = False) -> dict:
    """One whole, unbred combination for `seed`: the generator is seeded from
    the seed alone, the pools come from `library` (default: the committed
    library), and the recipe's own seed is `seed`. Deterministic. `clean`
    tidies the combination (`tidy`); False is the sample exactly as before."""
    if library is None:
        from . import library as _lib  # noqa: PLC0415
        library = _lib.default()
    pools = pools if pools is not None else library_pools(library)
    rng = np.random.default_rng(int(seed))
    rec = sample_recipe(rng, seed=int(seed), pools=pools, frame=frame, library=library)
    return tidy(rec, pools, library) if clean else rec

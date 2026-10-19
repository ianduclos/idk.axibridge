"""Round 16 thread A `aware`: the listen bridge — a listen sheet as a v2 score.

listen (round 15) builds a sheet as a short history of layers, then makes every
crossing aware inside its own `overlaps()` (weave / yield). This bridge keeps
the history and moves the awareness out into the score: the composer runs with
`overlaps()` as a no-op, each listen layer becomes one `lines` layer per ink
(a v2 layer has one pen), in drawing order, and awareness is written as score
relations that the executor (`kit/_synth.py`) plays.

It is also the seed of the next step (listen as a score writer): `score()` is
a listen sheet written as a score, with no private executor.

    from experiments.aware_bridge import score, AWARE
    sheet = synth.run(score(15102, AWARE))

The void (listen's `mask` layer, a torn edge drawn in part) is not aware of
crossings in listen; the score has no "every pair except" wildcard, so a sheet
with a void gets its relations as named pairs that skip it (same order as
`*`→`*`: relation-major, then pairs by drawing order).
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gesture.kit import arrangers_listen as al  # noqa: E402
from gesture.kit import core  # noqa: E402
from gesture.kit.arrangers_oehlen_found import arclen  # noqa: E402

MIN_PIECE = 1.5          # listen's own cleanup in overlaps(): drawn pieces shorter than this are dropped

# the awareness this round tests on listen: varied crossings + sympathy
AWARE = [{"kind": "sympathy"}, {"kind": "crossing"}]


class BridgeComposer(al.Composer):
    """listen's composer with its awareness removed: crossings are the score's business now."""

    def overlaps(self):
        return None


def compose(seed: int, recipe: dict | None = None):
    """Run listen's composer for a seed exactly as `listen()` does (same ctx, same parts), but
    without its overlaps. Returns (composer, validated recipe)."""
    from gesture.kit import library as _lib  # noqa: PLC0415
    lib = _lib.default()
    rec = core.validate(recipe or al.recipe(seed), library=lib)
    state = core._Run(lib)
    W, H = rec["frame"]
    parts = [core.Part(i, p, p.get("renderer", rec["renderer"]), (W, H), rec["seed"], state, (0.0, 0.0, W, H))
             for i, p in enumerate(rec["parts"])]
    inset = min(rec["margin"], 0.25 * min(W, H))
    box = (inset, inset, W - 2 * inset, H - 2 * inset)
    for p in parts:
        p.box = box
    arr = dict(rec["arranger"])
    ctx = core.Ctx((W, H), box, rec["seed"], rec["seed"], -1, "arranger", "listen", state)
    hands = [p.spec["voice"].get("hand") for p in parts if p.spec["voice"].get("hand")]
    kinds = {k.strip() for k in arr["relations"].split(",") if k.strip()}
    C = BridgeComposer(ctx, hands, density=arr["density"], mask_p=arr["mask_p"], river_p=arr["river_p"],
                       kinds=kinds, pens=arr["pens"])
    C.compose()
    return C, rec


def _flat(L):
    """A listen layer's drawn lines with their inks (cut pieces flattened, tiny ones dropped)."""
    out = []
    for l, ink in zip(L.lines, L.inks):
        for q in (l if isinstance(l, list) else [l]):
            q = np.asarray(q, float)
            if len(q) >= 2 and arclen(q)[-1] >= MIN_PIECE:
                out.append((q, ink))
    return out


def layers_of(C) -> list[dict]:
    """listen layers → v2 `lines` layers, one per ink, in drawing order. Ids keep listen's (L3), with a
    suffix when a layer carries more than one ink (L3, L3_b: its own line, then the borrowed stretch)."""
    W, H = C.W, C.H
    lo, hi = np.array([1.0, 1.0]), np.array([W - 1.0, H - 1.0])
    out = []
    for L in C.layers:
        groups: dict[str, list] = {}
        for q, ink in _flat(L):
            groups.setdefault(ink, []).append(np.clip(q, lo, hi))
        for n, (ink, lines) in enumerate(groups.items()):
            lid = L.lid if n == 0 else f"{L.lid}_{'bcdefgh'[n - 1]}"
            out.append({"id": lid, "role": L.role, "pen": ink,
                        "label": (L.label or L.technique) + ("" if n == 0 else f" ({ink})"),
                        "lines": [[[round(float(x), 3), round(float(y), 3)] for x, y in q] for q in lines],
                        "renderer": {"id": "wire", "pen": round(float(L.pen), 3)}})
    return out


def relations_for(layers: list[dict], specs: list[dict]) -> list[dict]:
    """Relation specs ({"kind", "params"?, "p"?, "id"?}) → score relations: `*`→`*`, or named pairs
    that skip the void when the sheet has one."""
    void = {L["id"] for L in layers if L["role"] == "mask"}
    out = []
    for j, s in enumerate(specs):
        base = {k: copy.deepcopy(v) for k, v in s.items() if k in ("kind", "params", "p", "note")}
        rid = s.get("id") or f"R{j}_{s['kind']}"
        if not void:
            out.append({"id": rid, "src": "*", "dst": "*", **base})
            continue
        ids = [L["id"] for L in layers if L["id"] not in void and L["role"] != "unseen"]
        for b in range(len(ids)):
            for a in range(b):
                out.append({"id": f"{rid}-{ids[a]}-{ids[b]}", "src": ids[a], "dst": ids[b], **base})
    return out


def score(seed: int, specs: list[dict] | None = None, *, recipe: dict | None = None) -> dict:
    """A listen sheet for `seed` as a v2 score, its awareness given by `specs` (default AWARE;
    [] = no awareness at all: lines simply cross)."""
    C, rec = compose(seed, recipe)
    layers = layers_of(C)
    specs = AWARE if specs is None else specs
    W, H = rec["frame"]
    ls = C.score.to_json()
    return {"version": 2, "label": f"listen {seed} via the aware bridge", "frame": [W, H], "seed": int(seed),
            "margin": rec["margin"], "layers": layers, "relations": relations_for(layers, specs),
            "decisions": {**ls["decisions"], "source": {"arranger": rec["arranger"], "seed": int(seed)},
                          "listen_relations": [{k: r[k] for k in ("kind", "src", "dst", "at")}
                                               for r in ls["relations"]]}}


if __name__ == "__main__":
    from gesture.kit import _synth as synth  # noqa: PLC0415
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 15102
    out = HERE.parents[1] / ".local/gesture/out/aware" / f"bridge-{seed}.jpg"
    sh = synth.run(score(seed))
    synth.preview(sh, out)
    print(out, sh.meta["seconds"], synth.played(sh)["relations"][:3])

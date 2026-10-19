"""Integration after round 16 (lead): listen with distinct-hand voices, all awareness on.

Ian, round 16 notes: the relay "yess thats whats up. we need to integrate this
type of line with the aware compositions and the complex ones"; the hdist
lines "i really wanna see this stuff integrated in the other drawings".

listen's composer grows every speaker, listener and refuser line through
`hand_line` (kit voice `hand`). Here that one method draws the same hand
through `hdist_zoom` instead (round 16 B: each hand at its own scales, the pen
as camera, the zoom stopping at the hand's finest detail). Everything else in
listen is unchanged; its own weave/yield is removed (the bridge) and the five
round-16 awareness relations are written into the v2 score.

    .local/gesture/.venv/bin/python tools/gesture/experiments/integ16.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from PIL import Image  # noqa: E402

from experiments import aware_bridge as ab  # noqa: E402
from gesture import kit  # noqa: E402
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit import arrangers_listen as al  # noqa: E402
from gesture.kit import core  # noqa: E402
from gesture.kit.arrangers_ccolour import _part, render_pens  # noqa: E402

OUT = HERE.parents[1] / ".local/gesture/out/integ16"
ALL_AWARE = [{"kind": "sympathy"}, {"kind": "crossing"}, {"kind": "hesitate"},
             {"kind": "accompany"}, {"kind": "make_room"}]
MM_PER_LENGTH = 200.0     # listen's hand length (R units) → hdist drawn length before fitting


class HdistComposer(ab.BridgeComposer):
    """listen, with every grown line drawn by hdist_zoom (distinct hands) and no private overlaps."""

    def hand_line(self, hand, length, wh):
        if not self.use_hdist(length):
            return super().hand_line(hand, length, wh)
        k = self.k
        self.k += 1
        box = (0.0, 0.0, float(wh[0]), float(wh[1]))
        spec = {"id": "hdist_zoom", "source": "hand", "hand": hand,
                "drawn_mm": round(float(length) * MM_PER_LENGTH, 1),
                "recur": int(self.rng.integers(1, 4))}
        marks = _part(self.ctx, 400 + k, spec, box).voice(box)
        pts = max((m.points for m in marks), key=lambda q: al.arclen(q)[-1])
        return al.resample(pts, al.STEP), 400 + k


class SpeakersComposer(HdistComposer):
    """Balance (Ian: "a bit too chaotic when everything is this way, so its a matter of balance"):
    only the speakers (listen grows them at length ≥ 3 R) are distinct hands; listeners, refusers
    and the later small layers keep listen's own calmer lines."""

    def use_hdist(self, length):
        return float(length) >= 3.0


HdistComposer.use_hdist = lambda self, length: True

SHARES = ("none", "one", "speakers", "all")


def dial(share: str):
    """The balance dial as a composer class: how many grown lines are distinct hands.
    none: listen's own lines · one: only the first speaker · speakers: every speaker (length ≥ 3 R)
    · all: every grown line. Distinct-hand lines draw their own randomness from ctx.rng, so the
    composition's own draws stay the same as listen's whatever the setting."""
    if share not in SHARES:
        raise ValueError(f"share must be one of {SHARES}")

    class DialComposer(ab.BridgeComposer):
        n_grown = 0

        def hand_line(self, hand, length, wh):
            i = self.n_grown
            self.n_grown += 1
            on = (share == "all" or (share == "speakers" and float(length) >= 3.0)
                  or (share == "one" and i == 0))
            if not on:
                return super().hand_line(hand, length, wh)
            k = self.k
            self.k += 1
            box = (0.0, 0.0, float(wh[0]), float(wh[1]))
            spec = {"id": "hdist_zoom", "source": "hand", "hand": hand,
                    "drawn_mm": round(float(length) * MM_PER_LENGTH, 1),
                    "recur": int(self.ctx.rng("hdist_recur", k).integers(1, 4))}
            marks = _part(self.ctx, 400 + k, spec, box).voice(box)
            pts = max((m.points for m in marks), key=lambda q: al.arclen(q)[-1])
            return al.resample(pts, al.STEP), 400 + k

    DialComposer.__name__ = f"DialComposer_{share}"
    return DialComposer


def compose(seed: int, cls=HdistComposer):
    """`aware_bridge.compose`, with the composer class swapped."""
    from gesture.kit import library as _lib  # noqa: PLC0415
    lib = _lib.default()
    rec = core.validate(al.recipe(seed), library=lib)
    state = core._Run(lib)
    W, H = rec["frame"]
    inset = min(rec["margin"], 0.25 * min(W, H))
    box = (inset, inset, W - 2 * inset, H - 2 * inset)
    parts = [core.Part(i, p, p.get("renderer", rec["renderer"]), (W, H), rec["seed"], state, box)
             for i, p in enumerate(rec["parts"])]
    arr = dict(rec["arranger"])
    ctx = core.Ctx((W, H), box, rec["seed"], rec["seed"], -1, "arranger", "listen", state)
    hands = [p.spec["voice"].get("hand") for p in parts if p.spec["voice"].get("hand")]
    kinds = {k.strip() for k in arr["relations"].split(",") if k.strip()}
    C = cls(ctx, hands, density=arr["density"], mask_p=arr["mask_p"], river_p=arr["river_p"],
            kinds=kinds, pens=arr["pens"])
    C.compose()
    return C, rec


def score(seed: int, specs=None, cls=HdistComposer) -> dict:
    C, rec = compose(seed, cls)
    layers = ab.layers_of(C)
    W, H = rec["frame"]
    return {"version": 2, "label": f"listen {seed}, distinct hands, all awareness", "frame": [W, H],
            "seed": int(seed), "margin": rec["margin"], "layers": layers,
            "relations": ab.relations_for(layers, ALL_AWARE if specs is None else specs),
            "decisions": {**C.score.to_json()["decisions"], "voices": "hdist_zoom", "mm_per_length": MM_PER_LENGTH}}


def balance(seeds=range(15101, 15109)):
    """Speakers distinct, listeners calm; all awareness on."""
    OUT.mkdir(parents=True, exist_ok=True)
    pop = []
    for seed in seeds:
        sh = synth.run(score(seed, cls=SpeakersComposer))
        p = synth.preview(sh, OUT / f"balance-{seed}.jpg", px_per_mm=5,
                          label=f"{seed} · distinct-hand speakers, listen's listeners · all awareness")
        pop.append(Image.open(p))
    kit.contact(pop, 2, title="balance: only the speakers are distinct hands; listeners keep listen's lines · "
                              "all awareness · 15101–15108, unpicked").save(OUT / "balance.jpg", quality=85)


def dial_compare(seeds=range(15101, 15109), shares=("one", "speakers")):
    """The same seeds at two dial settings, side by side; all awareness on."""
    OUT.mkdir(parents=True, exist_ok=True)
    cells = []
    for seed in seeds:
        for share in shares:
            sh = synth.run(score(seed, cls=dial(share)))
            p = synth.preview(sh, OUT / f"dial-{share}-{seed}.jpg", px_per_mm=4, label=f"{seed} · {share}")
            cells.append(Image.open(p))
    kit.contact(cells, len(shares), title=f"balance dial: {' | '.join(shares)} · same seeds side by side · "
                                          "all awareness · 15101–15108, unpicked").save(OUT / "dial.jpg", quality=85)


def main(seeds=range(15101, 15109)):
    OUT.mkdir(parents=True, exist_ok=True)
    pop, rows = [], []
    for seed in seeds:
        sc = score(seed)
        sh = synth.run(sc)
        c = Counter(e["outcome"] for e in synth.played(sh)["log"])
        print(seed, sh.meta["seconds"], len(sc["layers"]), "layers", dict(c), flush=True)
        p = synth.preview(sh, OUT / f"integ-{seed}.jpg", px_per_mm=5, label=f"{seed} · distinct hands · all awareness")
        pop.append(Image.open(p))
        if seed in (15102, 15106, 15107):
            a = render_pens(kit.run(al.recipe(seed)), px_per_mm=4)
            b = synth.render(synth.run(score(seed, specs=[])), px_per_mm=4)
            c2 = synth.render(sh, px_per_mm=4)
            rows += [a, b, c2]
    kit.contact(pop, 2, title="listen 15101–15108 with distinct-hand voices (hdist) and all five awareness relations "
                              "· consecutive, unpicked").save(OUT / "population.jpg", quality=85)
    kit.contact(rows, 3, title="left: round-15 listen · middle: distinct-hand voices, no awareness · "
                               "right: distinct-hand voices + all awareness").save(OUT / "compare.jpg", quality=85)


if __name__ == "__main__":
    {"balance": balance, "dial": dial_compare}.get(sys.argv[1] if sys.argv[1:] else "", main)()

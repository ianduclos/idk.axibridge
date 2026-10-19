# FROZEN from research commit ecd64f8: tools/gesture/gesture/kit/_score.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""The composition score (round 15 contract, lead-owned): the substructure a
future composition bench will let Ian edit.

An arranger that composes builds a `Score` while it works and records it with
`ctx.note("score", score.to_json())`; `kit.run` then returns it as
`sheet.meta["notes"]["score"]`. Measuring devices (`_devices.py`) read it.

    {"version": 1,
     "layers": [{"id": "L0", "role": "found|line|mask|intruder|traverse|device|…",
                 "technique": "<kit id>", "part": 0, "pen": "<pen name or mm>",
                 "params": {…}, "label": "…"}],
     "relations": [{"kind": "imitate|exaggerate|translate|echo|refuse|mask|ride|…",
                    "src": "L0", "dst": "L2", "at": [x, y] | null,
                    "s": [s0, s1] | null, "note": "…"}],
     "decisions": {"frame": …, "density": …, …}}

- Layer ids are stable strings within one sheet; relations refer to them.
- `kind` is an open vocabulary: use the round-15 relation names where they
  fit and add your own, documented in your write-up.
- `at` is sheet mm; `s` is an arc-length range (mm) on the dst layer's line.
- Everything must be JSON-able and deterministic (no floats from hash order).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Score:
    layers: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    decisions: dict = field(default_factory=dict)

    def layer(self, role: str, technique: str, *, part: int | None = None, pen=None,
              params: dict | None = None, label: str = "") -> str:
        lid = f"L{len(self.layers)}"
        self.layers.append({"id": lid, "role": str(role), "technique": str(technique), "part": part,
                            "pen": pen, "params": dict(params or {}), "label": str(label)})
        return lid

    def relate(self, kind: str, src: str, dst: str, *, at=None, s=None, note: str = "") -> None:
        self.relations.append({"kind": str(kind), "src": src, "dst": dst,
                               "at": None if at is None else [round(float(at[0]), 2), round(float(at[1]), 2)],
                               "s": None if s is None else [round(float(s[0]), 2), round(float(s[1]), 2)],
                               "note": str(note)})

    def decide(self, **kv) -> None:
        self.decisions.update(kv)

    def to_json(self) -> dict:
        return {"version": 1, "layers": self.layers, "relations": self.relations, "decisions": self.decisions}


def score_of(sheet) -> dict | None:
    """The score a sheet's arranger recorded, or None."""
    return (sheet.meta.get("notes") or {}).get("score")

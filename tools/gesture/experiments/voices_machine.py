"""Round 9 — machine voices and diagram voices (kit modules voices_machine*.py).

    .local/gesture/.venv/bin/python -m experiments.voices_machine [sheet ...]

Sheets (each one kit recipe → kit.preview, recipe JSON beside the image):
  alone      one matisse line re-spoken by every machine grammar (same line)
  handover   drift lines handing stretches to two machines (four pairings)
  annotated  a drift + handover with its κ(s) chart beside it
  shadow     the same drawing shadowed by a line whose distance is κ
  charts     six charts of ONE line (diagrams as pieces)
  limb       the κ(s) of a shikasta line: machine-drawn, Matisse-drawn, Lichtenberg-drawn
  numbers    print measurements used in the write-up
Outputs: .local/gesture/out/voices_machine/; results/voices_machine-*.jpg copies.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "gesture"))
from gesture import kit  # noqa: E402

OUT = ROOT / ".local" / "gesture" / "out" / "voices_machine"
RES = ROOT / "tools" / "gesture" / "results"
DRIFT = {"id": "drift", "hands": ["matisse", "shikasta", "lichtenberg"], "length": 6.0}


def save(name: str, recipe: dict, label: str, *, publish: bool = True, px: float = 6.0):
    sheet = kit.run(recipe)
    p = kit.preview(sheet, OUT / f"{name}.jpg", label=label, px_per_mm=px)
    if publish:
        for suf in (".jpg", ".recipe.json"):
            shutil.copy(p.with_suffix(suf), RES / f"voices_machine-{name}{suf}")
    kb = p.stat().st_size // 1024
    print(f"{name}: {len(sheet.marks)} marks, {len(sheet.inks)} inks, {kb} KB, {sheet.meta['seconds']}")
    return sheet


def alone():
    cells = [("hand", {"id": "hand", "hand": "matisse", "length": 4.0}),
             ("compass k5", {"id": "machine", "grammar": "compass", "k": 5, "source_part": 0}),
             ("compass k3", {"id": "machine", "grammar": "compass", "k": 3, "source_part": 0}),
             ("ruler", {"id": "machine", "grammar": "ruler", "source_part": 0}),
             ("stair", {"id": "machine", "grammar": "stair", "source_part": 0}),
             ("koch", {"id": "machine", "grammar": "koch", "source_part": 0}),
             ("lsys", {"id": "machine", "grammar": "lsys", "source_part": 0}),
             ("codebook k6", {"id": "machine", "grammar": "codebook", "k": 6, "source_part": 0})]
    rec = {"label": "machine voices alone", "seed": 9100, "frame": [267, 150],
           "arranger": {"id": "grid", "cols": 4, "scale": "cell", "gap": 7},
           "parts": [{"label": n, "voice": v} for n, v in cells]}
    save("alone", rec, "one matisse line, re-spoken: " + " | ".join(n for n, _ in cells))


def handover():
    pairs = [("ruler", "compass", "seams", {}), ("stair", "koch", "even", {}),
             ("lsys", "codebook", "random", {}), ("compass", "ruler", "straight", {"k": 3})]
    parts = []
    for a, b, at, extra in pairs:
        parts.append({"label": f"{a}+{b} @{at}", "voice": dict(DRIFT),
                      "modulators": [{"id": "handover", "a": a, "b": b, "at": at, "share": 0.4,
                                      "stretch": 16.0, "unit": 2.2, **extra}]})
    rec = {"label": "drift hands stretches to machines", "seed": 7000, "frame": [267, 180],
           "arranger": {"id": "grid", "cols": 2, "scale": "cell", "gap": 8}, "parts": parts}
    save("handover", rec, "matisse→shikasta→lichtenberg drift, handing the pen:  "
         + " | ".join(p["label"] for p in parts))


def annotated():
    rec = {"label": "a drawing with its diagram", "seed": 7003, "frame": [267, 180],
           "voice": dict(DRIFT),
           "modulators": [{"id": "handover", "a": "ruler", "b": "stair", "at": "seams", "share": 0.3,
                           "stretch": 22.0, "unit": 3.0},
                          {"id": "annotate", "chart": "kappa", "layout": "right", "split": 0.5, "rows": 6,
                           "label_h": 2.0}]}
    save("annotated", rec, "drift + handover(ruler, stair) | its k(s): seams ticked and named, machine "
         "stretches bracketed")


def shadow():
    rec = {"label": "a drawing shadowed by its curvature", "seed": 7003, "frame": [267, 180],
           "voice": dict(DRIFT),
           "modulators": [{"id": "handover", "a": "ruler", "b": "stair", "at": "seams", "share": 0.3,
                           "stretch": 22.0, "unit": 3.0},
                          {"id": "annotate", "chart": "kappa", "layout": "shadow", "gap": 1.2, "gain": 4.0}]}
    save("shadow", rec, "the same drawing, shadowed by a second line at distance 1.2 + 4·|k|^ mm")


def charts():
    kinds = ["kappa", "route", "tempo", "phase", "atlas", "ledger"]
    parts = [{"label": k, "voice": {"id": "diagram", "chart": k, "of_part": 0, "machine_a": "ruler",
                                    "machine_b": "compass", "share": 0.35, "rows": 4, "label_h": 1.7,
                                    "hands": DRIFT["hands"], "length": 6.0}} for k in kinds]
    rec = {"label": "six diagrams of one line", "seed": 7000, "frame": [267, 180],
           "arranger": {"id": "grid", "cols": 3, "scale": "cell", "gap": 10}, "parts": parts}
    save("charts", rec, "one drift line handed to ruler+compass, measured six ways: " + " | ".join(kinds), px=8)


def limb():
    base = {"id": "diagram", "chart": "kappa", "hands": ["shikasta"], "length": 4.0, "rows": 2, "of_part": 0,
            "label_h": 2.0, "aspect": 3.4}
    rows = [("machine", None), ("matisse", "matisse"), ("lichtenberg", "lichtenberg")]
    parts = [{"label": f"drawn by {n}", "voice": {**base, "drawn_by": h}} for n, h in rows]
    rec = {"label": "a diagram that becomes a drawing", "seed": 7000, "frame": [267, 240],
           "arranger": {"id": "grid", "cols": 1, "scale": "cell", "gap": 6}, "parts": parts}
    save("limb", rec, "k(s) of ONE shikasta line, drawn by: the machine | matisse | lichtenberg "
         "(restyle keep 0.006, amount 1.5)")
    parts = [{"label": f"{c} drawn by matisse",
              "voice": {**base, "chart": c, "drawn_by": "matisse", "hands": DRIFT["hands"], "length": 6.0,
                        "aspect": 1.05}}
             for c in ("atlas", "ledger")]
    rec = {"label": "charts drawn by a hand", "seed": 7000, "frame": [267, 120],
           "arranger": {"id": "grid", "cols": 2, "scale": "cell", "gap": 10}, "parts": parts}
    save("limb-atlas-ledger", rec, "the drift's shape atlas | its ledger — both drawn by matisse", px=8)


def numbers():
    """Rule-adherence: share of segment headings on the compass set; corners/R per grammar."""
    from gesture.kit import voices_machine as vm
    from gesture.kit.voices_machine_diagram import measure
    res = {}
    for g in vm.GRAMMARS:
        sh = kit.run({"seed": 9100, "voice": {"id": "machine", "grammar": g, "k": 5}})
        m = sh.marks[0]
        d = np.diff(m.points, axis=0)
        seg = np.linalg.norm(d, axis=1)
        h = np.mod(np.degrees(np.arctan2(d[:, 1], d[:, 0])), 360)[seg > 1e-6]
        M = measure([m])
        th = M["theta"]
        dth = np.abs(np.diff(th))
        corners = int(np.sum(dth > np.radians(25)))
        res[g] = {"vertices": int(len(m)), "distinct_headings_1deg": int(len(np.unique(np.round(h)))),
                  "corners_per_R": round(corners / (M["L"] / M["R"]), 1),
                  "median_abs_kR": round(float(np.median(np.abs(M["kappa"]))) * M["R"], 2)}
    sh = kit.run({"seed": 9100, "voice": {"id": "hand", "hand": "matisse", "length": 4.0}})
    M = measure(sh.marks)
    res["hand(matisse)"] = {"vertices": len(sh.marks[0]),
                            "median_abs_kR": round(float(np.median(np.abs(M["kappa"]))) * M["R"], 2),
                            "corners_per_R": round(int(np.sum(np.abs(np.diff(M["theta"])) > np.radians(25)))
                                                   / (M["L"] / M["R"]), 1)}
    sh = kit.run({"seed": 7000, "voice": dict(DRIFT), "modulators": [
        {"id": "handover", "a": "ruler", "b": "compass", "at": "seams", "share": 0.4, "stretch": 16.0,
         "unit": 2.2}]})
    m = sh.marks[0]
    s = m.arclength()
    mach = m.channels["machine"]
    res["handover"] = {"stretches": len(m.meta["handover"]),
                       "machine_share_of_length": round(float(np.sum(np.diff(s)[mach[1:] > 0]) / s[-1]), 3),
                       "voices": m.meta["voices"]}
    print(json.dumps(res, indent=1))


SHEETS = {"alone": alone, "handover": handover, "annotated": annotated, "shadow": shadow, "charts": charts,
          "limb": limb, "numbers": numbers}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or list(SHEETS):
        SHEETS[name]()

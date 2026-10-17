"""Round 10 — a drawing and its measurement (kit/measure_pairs.py).

    .local/gesture/.venv/bin/python -m experiments.measure_pairs [sheet ...]

Sheets (each one kit recipe → kit.preview, recipe JSON beside the image):
  pairs     four pairings: drift + κ wrapped round it | drift + its atlas (numbered origins) |
            the dance itself + its phase plot | a corpus hand + its ledger (drawn by matisse)
  pair_*    the same four as full pages
  shadow    shadow merged: law × side × shape, one drift (+ round 9's unmerged for reference)
  shadow_best   a full page of the best merged shadow
  atlas     the atlas as a piece: four hands/orderings/layouts
  atlas_*   the atlas pieces as full pages
  answer    the risk: the drawing answered by a second hand where its κ is silent / busy
  numbers   measurements for the write-up
Outputs: .local/gesture/out/measure_pairs/; results/measure_pairs-*.jpg copies (< 1 MB).
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "gesture"))
from gesture import kit  # noqa: E402

OUT = ROOT / ".local" / "gesture" / "out" / "measure_pairs"
RES = ROOT / "tools" / "gesture" / "results"
DRIFT = {"id": "drift", "hands": ["matisse", "shikasta", "lichtenberg"], "length": 6.0}
INK = {"id": "measure_wire", "pen": 0.4, "chart_pen": 0.25}


def save(name: str, recipe: dict, label: str, *, publish: bool = True, px: float = 6.0):
    sheet = kit.run(recipe)
    p = kit.preview(sheet, OUT / f"{name}.jpg", label=label, px_per_mm=px)
    kb = p.stat().st_size // 1024
    if publish:
        q = 88
        while kb > 980 and q > 50:                                        # keep results < 1 MB
            q -= 8
            p = kit.preview(sheet, OUT / f"{name}.jpg", label=label, px_per_mm=px, quality=q)
            kb = p.stat().st_size // 1024
        for suf in (".jpg", ".recipe.json"):
            shutil.copy(p.with_suffix(suf), RES / f"measure_pairs-{name}{suf}")
    print(f"{name}: {len(sheet.marks)} marks, {len(sheet.inks)} inks, {kb} KB, {sheet.meta['seconds']}")
    return sheet


def contact_recipes(name: str, recs: list[dict]) -> None:
    """The normalized recipes of a contact sheet's cells, in order, beside it."""
    data = json.dumps([kit.validate(r) for r in recs], indent=1, ensure_ascii=False)
    for d in (OUT, RES):
        (d / f"measure_pairs-{name}.recipe.json" if d == RES else d / f"{name}.recipe.json").write_text(data)


# ---------------------------------------------------------------------------
# 1. pairings
# ---------------------------------------------------------------------------

PAIRS = {
    "wrap": ("drift + its κ(s), wrapped round it on a rounded frame; 9 strongest turns numbered on both",
             {"seed": 7003, "voice": dict(DRIFT),
              "modulators": [{"id": "measure_pair", "chart": "kappa", "layout": "wrap", "split": 0.5,
                              "index": 9, "index_by": "peaks", "label_h": 2.4, "index_h": 2.2}]}),
    "atlas": ("drift + its shape atlas in order of time; each specimen's number sits where it came from",
              {"seed": 7003, "voice": dict(DRIFT),
               "modulators": [{"id": "measure_pair", "chart": "atlas", "layout": "diptych", "split": 0.4,
                               "cells": 24, "order": "time", "index_h": 2.0}]}),
    "dance": ("the mantis dance itself (hands+feet, 20 s) + its shape atlas in order of time, origins numbered",
              {"seed": 7100, "voice": {"id": "dance", "trail": "mantis", "seconds": 20.0},
               "modulators": [{"id": "measure_pair", "chart": "atlas", "layout": "diptych", "split": 0.42,
                               "cells": 20, "order": "time", "label_h": 2.2, "index_h": 2.0}]}),
    "dance_phase": ("the dance drawing itself (levitation) + its phase plot (κ, dκ/ds); 8 even indices",
                    {"seed": 7100, "voice": {"id": "dance", "trail": "levitation", "seconds": 12.0},
                     "modulators": [{"id": "measure_pair", "chart": "phase", "layout": "diptych", "split": 0.42,
                                     "index": 8, "index_by": "even", "label_h": 2.2, "index_h": 2.0}]}),
    "ledger": ("mime_roadrunner's hand + its ledger, the ledger drawn by matisse; deciles 01–10 on the line",
               {"seed": 7200, "voice": {"id": "hand", "hand": "mime_roadrunner", "length": 5.0},
                "modulators": [{"id": "measure_pair", "chart": "ledger", "layout": "diptych", "split": 0.45,
                                "label_h": 2.2, "index_h": 2.2, "drawn_by": "matisse"}]}),
    "margin": ("meander69, chain joins + κ rows in the margin below; seams indexed",
               {"seed": 7300, "voice": {"id": "drift", "hands": ["meander69", "shikasta"], "length": 5.0,
                                        "joins": "chain"},
                "modulators": [{"id": "measure_pair", "chart": "kappa", "layout": "margin", "split": 0.34,
                                "rows": 3, "index": 7, "index_by": "seams", "label_h": 2.0, "index_h": 2.0}]}),
    "under": ("drift with its route lanes UNDER it in the same box (finer pen), peaks indexed",
              {"seed": 7004, "voice": dict(DRIFT),
               "modulators": [{"id": "measure_pair", "chart": "route", "layout": "under", "index": 8,
                               "index_by": "peaks", "label_h": 3.0, "index_h": 2.2}]}),
}


def _rec(base: dict, label: str, frame=(267, 180)) -> dict:
    return {"label": label, "frame": list(frame), "margin": 8.0, "renderer": dict(INK), **base}


def pairs():
    for k, (lab, base) in PAIRS.items():
        save(f"pair_{k}", _rec(base, lab), lab)
    ims = [kit.render_image(kit.run(_rec(base, lab)), px_per_mm=3.2, label=lab) for k, (lab, base) in PAIRS.items()]
    c = kit.contact(ims, 2, title="a drawing and its measurement — seven pairings")
    c.save(OUT / "pairs.jpg", quality=84, optimize=True)
    shutil.copy(OUT / "pairs.jpg", RES / "measure_pairs-pairs.jpg")
    contact_recipes("pairs", [_rec(base, lab) for lab, base in PAIRS.values()])
    print("pairs contact:", (OUT / "pairs.jpg").stat().st_size // 1024, "KB")


# ---------------------------------------------------------------------------
# 2. shadow, merged
# ---------------------------------------------------------------------------

SHADOWS = [
    ("round 9: unmerged, κ left", {"law": "kappa", "side": "left", "gap": 1.2, "gain": 4.0, "merge": "none"}),
    ("merged strip, κ left", {"law": "kappa", "side": "left", "gap": 1.2, "gain": 4.0, "shape": "strip"}),
    ("merged beads, κ left", {"law": "kappa", "side": "left", "gap": 1.2, "gain": 4.0}),
    ("beads, κ inner side of turns", {"law": "kappa", "side": "turns", "gap": 0.6, "gain": 6.0}),
    ("beads, speed right (wide on straights)", {"law": "speed", "side": "right", "gap": 0.4, "gain": 3.5}),
    ("beads, κ turns, close 1.5", {"law": "kappa", "side": "turns", "gap": 0.6, "gain": 6.0, "close": 1.5}),
    ("beads, voice left (each hand its own width)", {"law": "voice", "side": "left", "gap": 0.8, "gain": 4.0}),
    ("beads, κ outer side, far", {"law": "kappa", "side": "outer", "gap": 2.0, "gain": 8.0}),
]


def shadow_variants_same_line():
    """Every cell shows the SAME drift (grid parts get seed + i, so use single parts at one seed each)."""
    ims, recs = [], []
    for lab, p in SHADOWS:
        rec = {"label": lab, "seed": 7003, "frame": [134, 180], "margin": 6.0, "renderer": dict(INK),
               "voice": dict(DRIFT), "modulators": [{"id": "measure_shadow", **p}]}
        recs.append(rec)
        s = kit.run(rec)
        kit.preview(s, OUT / f"shadow_{len(ims)}.jpg", label=lab, px_per_mm=6)
        ims.append(kit.render_image(s, px_per_mm=3.4, label=lab))
    c = kit.contact(ims, 4, title="shadow, merged — one drift (seed 7003), eight laws / sides / shapes")
    c.save(OUT / "shadow.jpg", quality=84, optimize=True)
    shutil.copy(OUT / "shadow.jpg", RES / "measure_pairs-shadow.jpg")
    contact_recipes("shadow", recs)
    print("shadow contact:", (OUT / "shadow.jpg").stat().st_size // 1024, "KB")


def shadow_best():
    save("shadow_beads", _rec({"seed": 7003, "voice": dict(DRIFT),
                               "modulators": [{"id": "measure_shadow", "law": "kappa", "side": "left",
                                               "gap": 1.2, "gain": 4.0}]},
                              "shadow merged"),
         "the round-9 shadow with overlaps merged: drawing ∪ κ-shadow traced as one contour (beads, left, 1.2 + 4·|κ|^ mm)")
    save("shadow_turns", _rec({"seed": 7003, "voice": dict(DRIFT),
                               "modulators": [{"id": "measure_shadow", "law": "kappa", "side": "turns",
                                               "gap": 0.6, "gain": 6.0, "close": 1.0}]},
                              "shadow turns"),
         "shadow on the inner side of every turn, merged: pinches to the line at inflections, turns swell into beads")
    save("shadow_dance", _rec({"seed": 7100, "voice": {"id": "dance", "trail": "mantis", "seconds": 14.0},
                               "modulators": [{"id": "measure_shadow", "law": "speed", "side": "turns",
                                               "gap": 0.3, "gain": 5.0, "close": 0.8}]},
                              "shadow dance"),
         "the mantis dance itself, shadowed by its OWN speed (inner side of turns), merged")


# ---------------------------------------------------------------------------
# 3. atlas as a piece
# ---------------------------------------------------------------------------

ATLASES = {
    "turning_matisse": ("the drift's atlas by total turning, drawn by matisse",
                        {"seed": 7000, "voice": dict(DRIFT),
                         "modulators": [{"id": "measure_atlas", "order": "turning", "layout": "grid", "cells": 30,
                                         "drawn_by": "matisse", "label_h": 2.2}]}),
    "frieze_time": ("the drift's atlas in order of time, as a frieze (read like a line of writing), machine-drawn",
                    {"seed": 7000, "voice": dict(DRIFT),
                     "modulators": [{"id": "measure_atlas", "order": "time", "layout": "frieze", "rows": 5,
                                     "cells": 60, "grain": 0.005, "degrees": False, "label_h": 1.8}]}),
    "hand_lichtenberg": ("the atlas grouped by speaking hand, drawn by lichtenberg",
                         {"seed": 7000, "voice": dict(DRIFT),
                          "modulators": [{"id": "measure_atlas", "order": "hand", "layout": "grid", "cells": 36,
                                          "drawn_by": "lichtenberg", "label_h": 2.0}]}),
    "exploded": ("the drift taken apart at its inflections, each specimen where it was, pushed out ×0.6",
                 {"seed": 7000, "voice": dict(DRIFT),
                  "modulators": [{"id": "measure_atlas", "order": "time", "layout": "exploded", "cells": 120,
                                  "grain": 0.005, "explode": 0.6, "numbers": True, "label_h": 2.0}]}),
}


def atlas():
    ims = []
    for k, (lab, base) in ATLASES.items():
        s = save(f"atlas_{k}", _rec(base, lab), lab)
        ims.append(kit.render_image(s, px_per_mm=3.2, label=lab))
    c = kit.contact(ims, 2, title="the atlas as a piece — one drift (seed 7000), four orderings / hands")
    c.save(OUT / "atlas.jpg", quality=84, optimize=True)
    shutil.copy(OUT / "atlas.jpg", RES / "measure_pairs-atlas.jpg")
    contact_recipes("atlas", [_rec(base, lab) for lab, base in ATLASES.values()])


# ---------------------------------------------------------------------------
# 4. the risk: the measurement answers
# ---------------------------------------------------------------------------

ANSWERS = [
    ("silence: lichtenberg answers where the drift is calm", {"hand": "lichtenberg", "where": "silence"}),
    ("echo: lichtenberg answers where the drift turns", {"hand": "lichtenberg", "where": "echo"}),
    ("silence, far: matisse on a loose spine, 8 mm off", {"hand": "matisse", "where": "silence", "spine": 0.08,
                                                          "offset": 8.0}),
    ("lift: lichtenberg only interjects in the drift's silences, 5 mm off", {"hand": "lichtenberg",
                                                                             "where": "silence", "quiet": "lift",
                                                                             "offset": 5.0, "spine": 0.05}),
]


def answer():
    ims, recs = [], []
    for i, (lab, p) in enumerate(ANSWERS):
        voice = {"id": "dance", "trail": "levitation", "seconds": 12.0} if "dance" in lab else dict(DRIFT)
        rec = _rec({"seed": 7003 if "dance" not in lab else 7100, "voice": voice,
                    "modulators": [{"id": "measure_answer", **p}],
                    "renderer": {"id": "measure_wire", "pen": 0.4, "chart_pen": 0.25}}, lab)
        recs.append(rec)
        s = save(f"answer_{i}", rec, lab, publish=(i in (0, 2, 3)))
        ims.append(kit.render_image(s, px_per_mm=3.2, label=lab))
    c = kit.contact(ims, 2, title="risk — the measurement drawn back into the drawing as a second voice")
    c.save(OUT / "answer.jpg", quality=84, optimize=True)
    shutil.copy(OUT / "answer.jpg", RES / "measure_pairs-answer.jpg")
    contact_recipes("answer", recs)


# ---------------------------------------------------------------------------
# numbers
# ---------------------------------------------------------------------------

def numbers():
    import numpy as np
    import shapely
    from gesture.kit import measure_pairs as mp
    from gesture.kit import voices_machine_diagram as vd
    rec = {"seed": 7003, "frame": [267, 180], "margin": 8.0, "voice": dict(DRIFT)}
    base = kit.run(rec)
    M = vd.measure(base.marks)
    out = {"drift_L_mm": round(M["L"], 1), "specimens": len(mp.specimens(M))}
    for lab, p in SHADOWS:
        if p.get("merge") == "none":
            continue
        t0 = time.perf_counter()
        pairs_ = mp.shadow_lines(M, law=p["law"], side=p["side"], gap=p["gap"], gain=p["gain"])
        rings, opened, G = mp.merged_rings(pairs_, close=p.get("close", 0.0), shape=p.get("shape", "beads"))
        dt = time.perf_counter() - t0
        raw = sum(float(np.sum(np.linalg.norm(np.diff(q, axis=0), axis=1))) for _, q, _ in pairs_) + M["L"]
        ink = sum(shapely.LineString(r).length for r in rings) + sum(shapely.LineString(o).length for o in opened)
        out[lab] = {"rings": len(rings), "open": len(opened), "ink_mm": round(ink), "unmerged_ink_mm": round(raw),
                    "ink_ratio": round(ink / raw, 3), "seconds": round(dt, 2)}
    print(json.dumps(out, indent=1))
    return out


SHEETS = {"pairs": pairs, "shadow": shadow_variants_same_line, "shadow_best": shadow_best, "atlas": atlas,
          "answer": answer, "numbers": numbers}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name in (sys.argv[1:] or list(SHEETS)):
        SHEETS[name]()

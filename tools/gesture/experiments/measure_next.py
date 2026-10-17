"""Round 11 — measurement, next versions (kit/measure_next.py).

    .local/gesture/.venv/bin/python tools/gesture/experiments/measure_next.py [sheet ...]

Every image is one kit recipe → kit.preview (recipe JSON beside it); contact
sheets carry their cells' recipes in a .recipe.json beside them.
Round 10's numbered atlas pairing (measure_pairs-pair_atlas) is frozen; these
are versions BESIDE it, named as versions of their parent.

Sheets:
  specimen   specimen side: cuts (pause / hand / crossing / loops / approach), normalised + κ traces,
             packed frieze, capped explosion, taxonomy + histogram
  drawing    drawing side: mantis dance by its own pauses, new library hands, a duet, merged-shadow
             beads, a drawing that changes hand at its specimen boundaries
  pairing    drawn_by with straight rules vs machine; the plate as the bigger element; drawing | atlas |
             re-chained
  rechain    the risk: the drawing redrawn from its atlas, orders × cuts, joins measured
  labels     index collisions, round 10 placement vs avoid
Outputs: .local/gesture/out/measure_next/; results/measure_next-*.jpg copies (< 400 KB).
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
from gesture.kit import measure_next as mn  # noqa: E402

OUT = ROOT / ".local" / "gesture" / "out" / "measure_next"
RES = ROOT / "tools" / "gesture" / "results"
DRIFT = {"id": "drift", "hands": ["matisse", "shikasta", "lichtenberg"], "length": 6.0}
INK = {"id": "measure_wire", "pen": 0.4, "chart_pen": 0.25}
PARENT = "numbered atlas"                     # round 10's measure_pairs-pair_atlas (frozen study)
NUMBERS: dict = {}


def rec(label: str, voice: dict, mods: list[dict], seed: int = 7003, frame=(267, 180)) -> dict:
    return {"label": label, "frame": list(frame), "seed": seed, "margin": 8.0, "renderer": dict(INK),
            "voice": voice, "modulators": mods}


def save(name: str, recipe: dict, *, publish: bool = False, px: float = 6.0):
    t0 = time.perf_counter()
    sheet = kit.run(recipe)
    p = kit.preview(sheet, OUT / f"{name}.jpg", label=recipe["label"], px_per_mm=px)
    if publish:
        q = 86
        while p.stat().st_size > 390_000 and q > 40:
            q -= 8
            p = kit.preview(sheet, OUT / f"{name}.jpg", label=recipe["label"], px_per_mm=px, quality=q)
        for suf in (".jpg", ".recipe.json"):
            shutil.copy(p.with_suffix(suf), RES / f"measure_next-{name}{suf}")
    print(f"{name}: {len(sheet.marks)} marks, {p.stat().st_size // 1024} KB, {time.perf_counter() - t0:.1f} s",
          flush=True)
    return sheet


def contact(name: str, recs: list[dict], cols: int, title: str, *, publish: bool = True, px: float = 3.0):
    ims = []
    for r in recs:
        ims.append(kit.render_image(kit.run(r), px_per_mm=px, label=r["label"]))
    c = kit.contact(ims, cols, title=title)
    q = 84
    c.save(OUT / f"{name}.jpg", quality=q, optimize=True)
    while (OUT / f"{name}.jpg").stat().st_size > 390_000 and q > 40:
        q -= 8
        c.save(OUT / f"{name}.jpg", quality=q, optimize=True)
    data = json.dumps([kit.validate(r) for r in recs], indent=1, ensure_ascii=False)
    (OUT / f"{name}.recipe.json").write_text(data)
    if publish:
        shutil.copy(OUT / f"{name}.jpg", RES / f"measure_next-{name}.jpg")
        (RES / f"measure_next-{name}.recipe.json").write_text(data)
    print(f"{name} contact: {(OUT / f'{name}.jpg').stat().st_size // 1024} KB", flush=True)


def nx(**p) -> dict:
    return {"id": "measure_next", **p}


# ---------------------------------------------------------------------------
# 1. specimen side
# ---------------------------------------------------------------------------

CUT_LABEL = {"pause": "specimens by pause (speed minima = turn apexes)", "hand": "specimens by hand change",
             "crossing": "specimens cut where the line crosses itself", "loops": "the loops as specimens",
             "approach": "specimens cut where the line comes closest to itself",
             "inflection": "specimens by inflection, the whole line kept"}


def specimen():
    recs = []
    for cut in ("pause", "hand", "crossing", "loops", "approach", "inflection"):
        lab = f"{PARENT} v2: {CUT_LABEL[cut]}"
        r = rec(lab, dict(DRIFT), [nx(cut=cut, cells=40)])
        save(f"cut_{cut}", r)
        recs.append(r)
    save("loops_size", rec(f"{PARENT} v2: the loops as specimens, each at a common size",
                           dict(DRIFT), [nx(cut="loops", norm="size", cells=40, split=0.3)]))
    contact("cuts", recs, 2, f"{PARENT} v2 — six new specimen cuts, one drift (seed 7003)")
    save("norm_trace", rec(f"{PARENT} v2: specimens at a common size on their principal axis, each with its own κ",
                           dict(DRIFT), [nx(cut="inflection", norm="axis+size", trace=True, cells=40,
                                            degrees=False)]), publish=True)
    save("trace_chord", rec(f"{PARENT} v2: each specimen with its own κ trace (chord level, true size)",
                            dict(DRIFT), [nx(trace=True)]))
    save("frieze", rec(f"{PARENT} v2: a true frieze — specimens packed by their own width, read like writing",
                       dict(DRIFT), [nx(cut="inflection", plate="frieze", cells=40, split=0.45)]), publish=True)
    save("exploded", rec(f"{PARENT} v2: exploded, every specimen capped at 2.5 × the median length",
                         dict(DRIFT), [nx(cut="inflection", plate="exploded", cells=60, split=0.5, explode=1.0,
                                          cap=2.5)]), publish=True)
    save("taxonomy", rec(f"{PARENT} v2: a taxonomy plate — five families by shape, with a length histogram",
                         dict(DRIFT), [nx(cut="inflection", plate="taxonomy", cells=40, families=5,
                                          hist="length")]), publish=True)
    save("taxonomy_tally", rec(f"{PARENT} v2: taxonomy, the histogram built of the specimen numbers (tally)",
                               dict(DRIFT), [nx(cut="inflection", plate="taxonomy", cells=40, families=5,
                                                hist="turning", hist_style="tally", split=0.45)]))
    save("taxonomy_trace", rec(f"{PARENT} v2: taxonomy, each specimen with its κ",
                               dict(DRIFT), [nx(cut="inflection", plate="taxonomy", cells=40, families=6,
                                                trace=True, split=0.45)]))


# ---------------------------------------------------------------------------
# 2. drawing side
# ---------------------------------------------------------------------------

def drawing():
    mantis = {"id": "dance", "trail": "mantis", "seconds": 20.0}
    save("dance_pause", rec("dance + atlas v2: the mantis dance cut at the dancer's own pauses (speed minima)",
                            mantis, [nx(cut="pause", cells=30, split=0.42, grain=0.01)], seed=7100), publish=True)
    save("dance_taxonomy", rec("dance + atlas v2: the mantis dance as a taxonomy of its gestures",
                               mantis, [nx(cut="pause", plate="taxonomy", cells=36, families=5, split=0.45,
                                           grain=0.008)], seed=7100))
    hands = [h["id"] for h in kit.library.entries("hand") if h.get("policy") == "generative"]
    NUMBERS["hands_in_library"] = hands
    recs = []
    for hd in ("aaron", "hokusai", "molnar_letters", "mime_dragon", "river_oxbow", "river_meander"):
        if hd not in hands:
            continue
        r = rec(f"{PARENT} v2: a library hand ({hd}) + its atlas", {"id": "hand", "hand": hd, "length": 5.0},
                [nx(cut="inflection", cells=30)], seed=7400)
        save(f"hand_{hd}", r)
        recs.append(r)
    contact("hands", recs, 2, f"{PARENT} v2 — other hands from the library, each beside its own atlas",
            publish=False)
    if "river_oxbow" in hands:
        save("river_taxonomy", rec(f"{PARENT} v2: a new hand (river_oxbow, round 11) as a taxonomy of its turns",
                                   {"id": "hand", "hand": "river_oxbow", "length": 5.0},
                                   [nx(cut="inflection", plate="taxonomy", cells=36, families=5, trace=True,
                                       split=0.45)], seed=7400), publish=True)
    save("duet", rec(f"{PARENT} v2: a drawing of two voices (matisse + lichtenberg), specimens grouped by hand",
                     {"id": "measure_next_duet", "hand_a": "matisse", "hand_b": "lichtenberg", "length": 3.5,
                      "apart": 0.3},
                     [nx(cut="inflection", plate="taxonomy", group="hand", cells=36)], seed=7500), publish=True)
    save("shadow", rec(f"{PARENT} v2: the drawing in merged-shadow beads, its atlas from the centreline",
                       dict(DRIFT), [nx(cut="inflection", shadow="turns", shadow_gain=5.0, cells=32)]),
         publish=True)
    save("rehand", rec(f"{PARENT} v2: the hand changes at every specimen boundary (matisse / lichtenberg / "
                       "shikasta), cut by hand",
                       dict(DRIFT), [{"id": "measure_next_rehand", "hands": ["matisse", "lichtenberg", "shikasta"],
                                      "cut": "inflection", "grain": 0.02},
                                     nx(cut="hand", order="time", cells=40)]), publish=True)


# ---------------------------------------------------------------------------
# 3. pairings
# ---------------------------------------------------------------------------

def pairing():
    save("drawn_straight", rec(f"{PARENT} v2: the plate drawn by matisse, rules and numbers kept machine-straight",
                               dict(DRIFT), [nx(cut="inflection", trace=True, cells=30, drawn_by="matisse",
                                                straight="rules+labels")]))
    save("drawn_traces", rec(f"{PARENT} v2: only the κ traces drawn by matisse; specimens, rules, numbers machine",
                             dict(DRIFT), [nx(cut="inflection", trace=True, cells=30, drawn_by="matisse",
                                              straight="rules+labels+specimens", norm="axis+size",
                                              degrees=False)]), publish=True)
    save("drawn_all", rec(f"{PARENT} v2: the plate drawn by matisse, nothing kept straight",
                          dict(DRIFT), [nx(cut="inflection", trace=True, cells=30, drawn_by="matisse",
                                           straight="none")]))
    save("plate_big", rec(f"{PARENT} v2: the plate is the bigger element, the drawing its accessory",
                          dict(DRIFT), [nx(cut="inflection", plate="taxonomy", cells=40, families=5, split=0.72,
                                           trace=True, index_h=1.6)]), publish=True)
    save("triptych", rec(f"{PARENT} v2: drawing | its atlas | the atlas re-chained into a second drawing "
                         "(signs alternating)",
                         dict(DRIFT), [nx(cut="inflection", page="triptych", split=0.34, cells=40,
                                          rechain="sign", label_h=1.8, index_h=1.7)]))


# ---------------------------------------------------------------------------
# 4. the risk: the drawing redrawn from its atlas
# ---------------------------------------------------------------------------

def rechain():
    base = kit.run(rec("", dict(DRIFT), []))
    M = mn.measure_plus(base.marks)
    table = {}
    for cut in ("inflection", "pause", "crossing", "hand", "approach"):
        sp = mn.cut_specimens(M, cut, 0.012)
        for order in ("time", "sign", "turning", "match", "shuffle"):
            for rot in (True, False):
                if not rot and order != "sign":
                    continue
                import numpy as np  # noqa: PLC0415
                seq = mn.rechain_order(sp, order, M, np.random.default_rng(7003))
                ch = mn.rechain(M, sp, seq, rotate=rot)
                table[f"{cut}/{order}/{'g1' if rot else 'collage'}"] = mn.join_report(M, sp, ch)
    NUMBERS["rechain_joins"] = table
    recs = []
    for order, rot, mirror, lab in (("time", True, False, "time order (the original, a check)"),
                                    ("sign", False, False, "signs alternating, translated only — the collage"),
                                    ("sign", True, False, "signs alternating, tangent continued"),
                                    ("turning", True, False, "calm to coiled"),
                                    ("match", True, False, "each next specimen matches the curvature"),
                                    ("shuffle", True, False, "shuffled")):
        recs.append(rec(f"re-chained from its atlas: {lab}", dict(DRIFT),
                        [{"id": "measure_next_rechain", "cut": "inflection", "order": order, "rotate": rot,
                          "mirror": mirror}], frame=(134, 120)))
    contact("rechain", recs, 3, "risk — the drawing redrawn from its atlas (inflection specimens, seed 7003)")
    recs = []
    for cut, order in (("pause", "sign"), ("crossing", "sign"), ("loops", "time"), ("pause", "match")):
        recs.append(rec(f"re-chained: {cut} specimens, {order}", dict(DRIFT),
                        [{"id": "measure_next_rechain", "cut": cut, "order": order}], frame=(134, 120)))
    contact("rechain_cuts", recs, 2, "risk — other cuts re-chained (pause / crossing joins sit on turns)",
            publish=False)
    save("triptych_turning", rec(f"{PARENT} v2: drawing | atlas | re-chained calm to coiled",
                                 dict(DRIFT), [nx(cut="inflection", page="triptych", split=0.34, cells=40,
                                                  rechain="turning", label_h=1.8, index_h=1.7)]))
    save("triptych_dance", rec("dance + atlas v2: the mantis dance | its atlas | its gestures re-chained into one "
                               "line",
                               {"id": "dance", "trail": "mantis", "seconds": 20.0},
                               [nx(cut="pause", page="triptych", split=0.34, cells=30, rechain="match",
                                   grain=0.01, label_h=1.8, index_h=1.7)], seed=7100), publish=True)


# ---------------------------------------------------------------------------
# 5. labels
# ---------------------------------------------------------------------------

def labels():
    from gesture.kit import core as kc  # noqa: PLC0415
    from gesture.kit import measure_pairs as mp  # noqa: PLC0415
    from gesture.kit import voices_machine_diagram as vd  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    out = {}
    cases = {"pair_atlas (frozen)": (dict(DRIFT), 7003, "turning", 24),
             "mantis dance": ({"id": "dance", "trail": "mantis", "seconds": 20.0}, 7100, "turning", 20),
             "drift, 40 inflection specimens": (dict(DRIFT), 7003, "inflection", 40),
             "aaron, 30": ({"id": "hand", "hand": "aaron", "length": 5.0}, 7400, "inflection", 30)}
    for name, (voice, seed, cut, cells) in cases.items():
        s = kit.run(rec("", voice, [], seed=seed))
        x0, y0, w, h = 8.0, 8.0, 251.0, 164.0
        pad = 0.04 * w
        dbox = (x0, y0, w * 0.6 - pad / 2, h)
        d = kc.refit(s.marks, dbox)
        M = mn.measure_plus(d)
        sp = mp.order_specimens(mn.cut_specimens(M, cut, 0.012), "time", cells)
        ss = [t["s_mid"] for t in sp]
        labs = [f"{i + 1:02d}" for i in range(len(sp))]
        old = mn.label_stats(M["p"], mn.round10_rects(M, ss, labs, label_h=2.0, tick=1.6))
        _, rects = mn.place_labels(M, ss, labs, label_h=2.0, avoid=True, bounds=dbox)
        new = mn.label_stats(M["p"], rects)
        out[name] = {"round10": old, "avoid": new}
    NUMBERS["labels"] = out
    print(json.dumps(out, indent=1))


SHEETS = {"specimen": specimen, "drawing": drawing, "pairing": pairing, "rechain": rechain, "labels": labels}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name in (sys.argv[1:] or list(SHEETS)):
        SHEETS[name]()
    if NUMBERS:
        f = OUT / "numbers.json"
        old = json.loads(f.read_text()) if f.exists() else {}
        old.update(NUMBERS)
        f.write_text(json.dumps(old, indent=1, default=float))

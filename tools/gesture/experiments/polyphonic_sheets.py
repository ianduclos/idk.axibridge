"""Polyphonic sheets (round 9): units, pages, annotation, conversation.

    .local/gesture/.venv/bin/python tools/gesture/experiments/polyphonic_sheets.py [annot|scatter|page|converse|all]

Every image comes from kit.run + kit.preview (recipe JSON beside it) in
.local/gesture/out/polyphonic_sheets/; contact sheets go to
tools/gesture/results/polyphonic_sheets-*.jpg. Each sheet is measured with
sheetcomp (islands, free ends, edge contact, distance to the corpora and to
Ian's 2024 reference) and logged to measure.json.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture import sheetcomp as sc  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/polyphonic_sheets"
RES = HERE / "results"
SC_OUT = ROOT / ".local/gesture/out/sheet_composition"
CORPUS_GROUPS = ("matisse", "hokusai", "ingres", "marden", "cohen", "henry", "molnar", "nake", "noll", "mashq",
                 "shikasta", "calligraphy", "print")

W8 = {"id": "wire", "pen": 0.35}
SEED_HANDS = "bubble hokusai ingres lichtenberg marden matisse nastaliq shikasta"   # fixed: the library grows


def measure(sheet) -> dict:
    im = kit.render_image(sheet, px_per_mm=4, label=None)
    g = np.asarray(im.convert("L"), dtype=np.float64) / 255.0
    return sc.profile(sc.mask_from_gray(g, binarize=False))


_SCALE = None


def corpus_scale():
    global _SCALE
    if _SCALE is None:
        recs = json.loads((SC_OUT / "profiles.json").read_text())
        _SCALE = (sc.Scale.fit([r["profile"] for r in recs if r["group"] in CORPUS_GROUPS]),
                  json.loads((SC_OUT / "group_medians.json").read_text()))
    return _SCALE


def summarize(name, p) -> dict:
    scale, med = corpus_scale()
    d = {g: sc.distance(p, med[g], scale) for g in ("ref", "print", "mashq", "marden", "matisse", "ours_r7")}
    row = {"name": name, "islands_1": round(math.exp(p["islands_1"])), "islands_3": round(math.exp(p["islands_3"])),
           "ends_len": round(p["ends_len"], 1), "margin_ratio": round(p["margin_ratio"], 2),
           "cover": round(p["cover"], 3), "empty16": round(p["empty16"], 2), "lac_25": round(p["lac_25"], 3),
           **{f"d_{k}": round(v, 2) for k, v in d.items()}}
    return row


LOG: list[dict] = []


def shoot(name, recipe, label=None):
    t = time.perf_counter()
    s = kit.run(recipe)
    path = OUT / f"{name}.jpg"
    kit.preview(s, path, label=label or recipe.get("label") or "auto")
    row = summarize(name, measure(s))
    row["secs"] = round(time.perf_counter() - t, 1)
    LOG.append(row)
    print(json.dumps(row), flush=True)
    return path


def contact(paths, cols, title, dst, width=1100):
    from PIL import Image
    ims = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        ims.append(im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS))
    sheet = kit.contact(ims, cols, title=title)
    q = 86
    while True:
        sheet.save(dst, quality=q, optimize=True)
        if dst.stat().st_size < 980_000 or q < 40:
            break
        q -= 8
    print("->", dst, dst.stat().st_size // 1024, "KB")


# ---------------------------------------------------------------------------
# recipes
# ---------------------------------------------------------------------------

def scatter_base(annotate="none", n=6, seed=9100, **arr):
    return {"seed": seed,
            "arranger": {"id": "poly_scatter", "counts": [1, 5, 9, 1], "sizes": [0.62, 0.24, 0.12],
                         "mode": "restate", "pull": "edges", "bleed": 0.3,
                         "annotate": annotate, "n_annot": n, **arr},
            "parts": [
                {"label": "dominant", "voice": {"id": "hand", "hand": "matisse", "length": 2.5},
                 "modulators": [{"id": "timing", "tempo": "staccato", "amount": 0.9}],
                 "renderer": {"id": "nib", "style": "e"}},
                {"label": "marden units", "voice": {"id": "hand", "hand": "marden", "length": 1.2}},
                {"label": "chain drift units", "voice": {"id": "drift", "hands": ["shikasta", "bubble"],
                                                         "joins": "chain", "length": 1.0}},
                {"label": "annotator", "voice": {"id": "hand", "hand": "lichtenberg", "length": 0.7}}],
            "renderer": W8}


def cmd_annot():
    paths = []
    for mode in ("underline", "bracket", "encircle", "tether", "point", "echo"):
        r = scatter_base(mode, n=5)
        r["label"] = f"poly_scatter, annotate = {mode} (annotator: lichtenberg hand, 0.7 R, wire)"
        paths.append(shoot(f"annot-{mode}", r))
    contact(paths, 2, "Annotation modes: one scatter (matisse dominant / marden units / shikasta>bubble chain "
            "units), five annotations each", RES / "polyphonic_sheets-annotation-modes.jpg")


def cmd_scatter():
    paths = []
    r = scatter_base("mixed", n=7, seed=9101)
    r["label"] = "A  dominant + marginal units (pull edges), restated, mixed annotation"
    paths.append(shoot("scatter-A-dominant", r))
    r = {"seed": 9102, "label": "B  many small units of four voices, cut from one utterance each, bleed 0.35, "
         "quarter turns, tethers",
         "arranger": {"id": "poly_scatter", "counts": [10, 14, 8, 1, 1], "sizes": [0.2, 0.1, 0.16],
                      "mode": "cut", "bleed": 0.35, "rotate": "quarter", "gap": 2.0, "annotate": "tether",
                      "n_annot": 6, "annotator": 4},
         "parts": [
             {"voice": {"id": "hand", "hand": "hokusai", "length": 5}},
             {"voice": {"id": "hand", "hand": "nastaliq", "length": 4},
              "modulators": [{"id": "constant", "r": 1.0, "W": 1.6, "phi": 40}],
              "renderer": {"id": "nib", "style": "c"}},
             {"voice": {"id": "drift", "hands": ["marden", "lichtenberg"], "joins": "chain", "length": 5}},
             {"voice": {"id": "hand", "hand": "bubble", "length": 1}},
             {"voice": {"id": "hand", "hand": "ingres", "length": 0.8}}],
         "renderer": W8}
    paths.append(shoot("scatter-B-cut-many", r))
    r = {"seed": 9103, "label": "C  three voices, each restated as units at its own size; heavy voice small, "
         "dry voice large; encircling + pointing (mixed)",
         "arranger": {"id": "poly_scatter", "counts": [3, 12, 22, 1], "sizes": [0.42, 0.16, 0.07],
                      "mode": "restate", "bleed": 0.25, "gap": 4.0, "overlap": 0.05,
                      "annotate": "mixed", "n_annot": 8},
         "parts": [
             {"voice": {"id": "hand", "hand": "bubble", "length": 1.6}},
             {"voice": {"id": "drift", "hands": ["ingres", "marden"], "joins": "chain", "length": 0.9},
              "modulators": [{"id": "timing", "tempo": "particles", "mass_width": 4.0}],
              "renderer": {"id": "nib", "style": "e"}},
             {"voice": {"id": "hand", "hand": "shikasta", "length": 0.35},
              "modulators": [{"id": "constant", "r": 1.0, "W": 1.2, "phi": 30}],
              "renderer": {"id": "nib", "style": "a"}},
             {"voice": {"id": "hand", "hand": "hokusai", "length": 0.6}}],
         "renderer": W8}
    paths.append(shoot("scatter-C-sizes", r))
    contact(paths, 1, "poly_scatter: units, bleed, annotation", RES / "polyphonic_sheets-scatter.jpg", width=1300)


def cmd_page():
    paths = []
    r = {"seed": 9200, "label": "P1  interlinear page: shikasta rows alternate with marden rows; bubble glosses "
         "in the outer margin, tethered by a lichtenberg wire",
         "arranger": {"id": "poly_page", "roles": "body gloss body", "rows": 12, "words": 36,
                      "annotate": "tether", "n_annot": 5},
         "parts": [
             {"voice": {"id": "hand", "hand": "shikasta", "length": 6},
              "modulators": [{"id": "constant", "r": 1.0, "W": 1.4, "phi": 35}],
              "renderer": {"id": "nib", "style": "c"}},
             {"voice": {"id": "hand", "hand": "bubble", "length": 4}},
             {"voice": {"id": "hand", "hand": "marden", "length": 6}},
             {"voice": {"id": "hand", "hand": "lichtenberg", "length": 0.6}}],
         "renderer": W8}
    paths.append(shoot("page-P1-interlinear", r))
    r = {"seed": 9201, "label": "P2  two columns rtl, hokusai > nastaliq chain drift as body, matisse glosses "
         "left, brackets + underlines by a staccato-danced nib (mixed)",
         "arranger": {"id": "poly_page", "roles": "body gloss", "columns": 2, "rows": 14, "words": 44,
                      "direction": "rtl", "justify": True, "margin": "left", "gloss_share": 0.35,
                      "annotate": "mixed", "n_annot": 7, "annot_amp": 2.4},
         "parts": [
             {"voice": {"id": "drift", "hands": ["hokusai", "nastaliq"], "joins": "chain", "length": 8}},
             {"voice": {"id": "hand", "hand": "matisse", "length": 3}},
             {"voice": {"id": "hand", "hand": "marden", "length": 0.8},
              "modulators": [{"id": "timing", "tempo": "staccato", "mass_width": 3.0}],
              "renderer": {"id": "nib", "style": "e"}}],
         "renderer": W8}
    paths.append(shoot("page-P2-columns-rtl", r))
    r = {"seed": 9202, "label": "P3  sparse page: 6 rows, few long words, rows run off the edge (bleed 0.5); "
         "ingres glosses; echo annotation in a bubble hand",
         "arranger": {"id": "poly_page", "roles": "body gloss", "rows": 6, "words": 9, "x_height": 0.45,
                      "word_gap": 0.8, "bleed": 0.5, "gloss_share": 0.8, "gloss_size": 0.7,
                      "annotate": "echo", "n_annot": 6, "annot_amp": 1.2},
         "parts": [
             {"voice": {"id": "drift", "hands": ["lichtenberg", "shikasta"], "joins": "chain", "length": 5}},
             {"voice": {"id": "hand", "hand": "ingres", "length": 3}},
             {"voice": {"id": "hand", "hand": "bubble", "length": 0.7}}],
         "renderer": W8}
    paths.append(shoot("page-P3-sparse-bleed", r))
    contact(paths, 1, "poly_page: pages of writing, glosses, annotation", RES / "polyphonic_sheets-page.jpg",
            width=1300)


def cmd_converse():
    paths = []
    for reply, seed in (("contrast", 9300), ("echo", 9301), ("contrast", 9302)):
        r = {"seed": seed, "label": f"conversation, reply = {reply}: each unit's hand, length, weight and start "
             "are derived from the previous unit",
             "arranger": {"id": "poly_converse", "turns": 14, "reply": reply, "size": 0.22, "pool": SEED_HANDS,
                          "annotate": "tether" if seed == 9302 else "none", "n_annot": 5},
             "parts": [
                 {"voice": {"id": "hand", "hand": "matisse", "length": 1.4},
                  "modulators": [{"id": "timing", "tempo": "staccato", "mass_width": 5.0}],
                  "renderer": {"id": "nib", "style": "e"}},
                 {"voice": {"id": "hand", "hand": "marden", "length": 1.4}}]
             + ([{"voice": {"id": "hand", "hand": "lichtenberg", "length": 0.6}}] if seed == 9302 else []),
             "renderer": W8}
        paths.append(shoot(f"converse-{reply}-{seed}", r))
    contact(paths, 1, "poly_converse: conversation as a composition rule", RES / "polyphonic_sheets-converse.jpg",
            width=1300)


def cmd_mixed():
    """Sibling voices (round 9, same day) through these arrangers, by id with default params."""
    paths = []
    r = {"seed": 9400, "label": "M1  page: shikasta nib rows interlinear with a machine re-speaking; diagram "
         "glosses; a dance trail as the annotator (mixed)",
         "arranger": {"id": "poly_page", "roles": "body body gloss", "rows": 11, "words": 36,
                      "annotate": "mixed", "n_annot": 6},
         "parts": [
             {"voice": {"id": "hand", "hand": "shikasta", "length": 6},
              "modulators": [{"id": "constant", "r": 1.0, "W": 1.4, "phi": 35}],
              "renderer": {"id": "nib", "style": "c"}},
             {"voice": {"id": "machine"}},
             {"voice": {"id": "diagram"}},
             {"voice": {"id": "dance"}}],
         "renderer": W8}
    paths.append(shoot("mixed-M1-page-siblings", r))
    r = {"seed": 9401, "label": "M2  scatter: a dance drawing dominant, machine units, diagram units at the rim, "
         "a lichtenberg wire annotating (mixed)",
         "arranger": {"id": "poly_scatter", "counts": [1, 6, 5, 1], "sizes": [0.7, 0.2, 0.14], "mode": "restate",
                      "pull": "edges", "bleed": 0.3, "annotate": "mixed", "n_annot": 7},
         "parts": [
             {"voice": {"id": "dance"}},
             {"voice": {"id": "machine"}},
             {"voice": {"id": "diagram"}},
             {"voice": {"id": "hand", "hand": "lichtenberg", "length": 0.7}}],
         "renderer": W8}
    paths.append(shoot("mixed-M2-scatter-siblings", r))
    contact(paths, 1, "Sibling voices through poly_page / poly_scatter", RES / "polyphonic_sheets-siblings.jpg",
            width=1300)


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    what = argv[1] if len(argv) > 1 else "all"
    cmds = {"annot": cmd_annot, "scatter": cmd_scatter, "page": cmd_page, "converse": cmd_converse, "mixed": cmd_mixed}
    for k, fn in cmds.items():
        if what in (k, "all"):
            fn()
    mj = OUT / "measure.json"
    old = {r["name"]: r for r in json.loads(mj.read_text())} if mj.exists() else {}
    old.update({r["name"]: r for r in LOG})
    mj.write_text(json.dumps(list(old.values()), indent=1))


if __name__ == "__main__":
    main(sys.argv)

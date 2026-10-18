"""Study B recipes, a neutral-labelled population, candidates and one diagnostic.

Run from the repo root using .local/gesture/.venv/bin/python, images only:
  tools/gesture/experiments/study_b.py sweep
  tools/gesture/experiments/study_b.py select B02 B05 B07 B10 B14 B17 --diagnostic B07

Selection is a human/agent reading of the saved contact and close views. No
beauty score or automatic ranking chooses the candidates. Timings cover kit.run,
not JPEG encoding. Every preview has a normalized, rerunnable recipe beside it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))
from gesture import kit  # noqa: E402
from gesture.kit.core import PAPER, INK, _font  # noqa: E402
from gesture.kit.voices_passage import HANDS, SECTION_CODES  # noqa: E402

OUT = ROOT / ".local/gesture/out/study_b"
# Flexoki 600 accents, read from axibridge/static/css/flexoki.css.
COLORS = ["#AF3029", "#205EA6", "#66800B", "#A02F6F", "#BC5215", "#24837B", "#5E409D", "#AD8301"]
TYPE_COLORS = {"opening": "#878580", "hold": "#403E3C", "glide": "#205EA6", "jolt": "#AF3029",
               "split": "#BC5215", "many": "#5E409D", "recall": "#24837B"}


def recipe(seed=18101, **params):
    return {"frame": [297, 210], "seed": seed, "margin": 6,
            "voice": {"id": "passage", "hands": HANDS, **params},
            "renderer": {"id": "wire", "pen": 0.35}}


def population():
    """Factor/seed exploration: gradual ↔ erratic, few ↔ many, plus no opening."""
    rows = []
    families = [
        {"erratic": 0.08, "many": 0.08, "specimen": 0.45, "section_length": 36, "malleable": 0},
        {"erratic": 0.3, "many": 0.35, "specimen": 0.5, "section_length": 25, "malleable": 0.2},
        {"erratic": 0.8, "many": 0.2, "specimen": 0.5, "section_length": 20, "malleable": 0.35},
        {"erratic": 0.45, "many": 0.9, "specimen": 0.25, "section_length": 24, "malleable": 0.5},
        {"erratic": 0.85, "many": 0.85, "specimen": 0.25, "section_length": 13, "malleable": 0.7},
        {"opening": "none", "erratic": 0.4, "many": 0.7, "specimen": 0.65,
         "section_length": 24, "malleable": 0.35, "rows": 3, "band": 23},
        {"erratic": 0.4, "many": 0.65, "specimen": 0.45, "section_length": 26,
         "malleable": 0.4, "recall": 16, "recall_gap": 90, "clear": 0.35,
         "band": 28, "ahead": 16, "pull": 2.2},
        {"opening": "none", "erratic": 0.65, "many": 0.8, "specimen": 0.6,
         "section_length": 30, "malleable": 0.55, "recall": 15, "recall_gap": 100,
         "clear": 0.4, "band": 28, "ahead": 17, "pull": 2.0},
    ]
    for i, family in enumerate(families):
        for j in range(3):
            key = f"B{3 * i + j + 1:02}"
            rows.append((key, recipe(seed=18101 + 31 * i + j, R_mm=(90, 100, 110)[j],
                                     asym=0.8, aware=0.85, **family)))
    return rows


def render_one(key, rec, directory):
    t = time.perf_counter()
    sh = kit.run(rec)
    elapsed = time.perf_counter() - t
    kit.preview(sh, directory / f"{key}.jpg", px_per_mm=6, label=key)
    info = sh.marks[0].meta["passage"]
    summary = {"id": key, "seconds": round(elapsed, 3), "stop": info["stop"],
               "route_progress": round(info["route_progress"], 3), "length_mm": round(info["length_mm"], 1),
               "sections": len(info["sections"]), "recalls": len(info["recalls"]),
               "morph_batches": info["morph_batches"],
               "sources": sorted({h for s in info["segment_log"] for h in s["assignment"].values()})}
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{key}.meta.json").write_text(json.dumps(info, indent=1) + "\n")
    print(json.dumps(summary), flush=True)
    return sh, summary


def contact(keys, directory, dest, *, cols=3):
    images = []
    for key in keys:
        with Image.open(directory / f"{key}.jpg") as im:
            images.append(im.resize((713, 520), Image.Resampling.LANCZOS))
    kit.contact(images, cols, title="Study B · " + " / ".join(keys)).save(dest, quality=92)


def diagnostic(sheet, path, key):
    """Majority hand colour; ties choose the lowest hand index, matching the mark.

    The lower strip is ARC LENGTH, not spatial position. It includes the exact
    opening so section durations and unequal pacing remain visible. A neutral
    opening is coloured river green because that is its real source.
    """
    m = sheet.marks[0]
    info = m.meta["passage"]
    k, ss = 6, 2
    W, H = sheet.frame
    width, height = round(W * k), round(H * k)
    im = Image.new("RGB", (width * ss, height * ss), PAPER)
    dr = ImageDraw.Draw(im)
    ids = m["voice"].astype(int)
    cut = np.r_[0, np.flatnonzero(np.diff(ids)) + 1, len(ids)]
    for a, b in zip(cut[:-1], cut[1:]):
        q = m.points[max(a - 1, 0):b] * k * ss
        if len(q) >= 2:
            dr.line([tuple(v) for v in q], fill=COLORS[ids[a]] if ids[a] >= 0 else INK,
                    width=round(0.35 * k * ss), joint="curve")
    im = im.resize((width, height), Image.Resampling.LANCZOS)
    full = Image.new("RGB", (width, height + 205), PAPER)
    full.paste(im, (0, 0))
    dr = ImageDraw.Draw(full)
    dr.text((24, height + 8), f"{key} · majority hand (ties: lower index)", fill=INK, font=_font(21))
    for i, hand in enumerate(info["hands"]):
        x, y = 24 + (i % 3) * 570, height + 43 + (i // 3) * 28
        dr.line((x, y + 10, x + 35, y + 10), fill=COLORS[i], width=4)
        dr.text((x + 44, y), f"{i}: {hand}", fill=INK, font=_font(19))
    left, right, y = 24, width - 24, height + 118
    total = info["length_mm"]
    op = info["opening"]["length_mm"]
    if op:
        dr.rectangle((left, y, left + (right - left) * op / total, y + 23), fill=TYPE_COLORS["opening"])
    for s in info["sections"]:
        a = left + (right - left) * s["start_mm"] / total
        b = left + (right - left) * s["end_mm"] / total
        dr.rectangle((a, y, b, y + 23), fill=TYPE_COLORS[s["type"]])
    dr.text((left, y + 28), f"arc length 0 to {total:.0f} mm", fill=INK, font=_font(17))
    x = 370
    for name, col in TYPE_COLORS.items():
        dr.rectangle((x, y + 33, x + 14, y + 46), fill=col)
        dr.text((x + 20, y + 27), name, fill=INK, font=_font(17))
        x += 150
    full.save(path, quality=94)
    sheet.save_recipe(path.with_suffix(".recipe.json"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("sweep", "select"))
    parser.add_argument("keys", nargs="*")
    parser.add_argument("--diagnostic")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.action == "sweep":
        chosen = set(args.keys)
        rows = [(key, rec) for key, rec in population() if not chosen or key in chosen]
        summaries = [render_one(key, rec, OUT / "sweep")[1] for key, rec in rows]
        timing_path = OUT / "sweep" / "timings.json"
        previous = json.loads(timing_path.read_text()) if timing_path.exists() else []
        combined = {r["id"]: r for r in [*previous, *summaries]}
        timing_path.write_text(json.dumps([combined[k] for k in sorted(combined)], indent=2) + "\n")
        available = [key for key, _ in population() if (OUT / "sweep" / f"{key}.jpg").exists()]
        contact(available, OUT / "sweep", OUT / "sweep-contact.jpg")
        for i in range(0, len(available), 6):
            contact(available[i:i + 6], OUT / "sweep", OUT / f"population-{i // 6 + 1}.jpg")
    else:
        summaries = []
        for key in args.keys:
            rec = json.loads((OUT / "sweep" / f"{key}.recipe.json").read_text())
            sh, summary = render_one(key, rec, OUT / "candidates")
            summaries.append(summary)
            if key == args.diagnostic:
                diagnostic(sh, OUT / "candidates" / "diagnostic.jpg", key)
        (OUT / "candidates" / "timings.json").write_text(json.dumps(summaries, indent=2) + "\n")
        contact(args.keys, OUT / "candidates", OUT / "candidates-contact.jpg")


if __name__ == "__main__":
    main()

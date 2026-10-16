"""Derive docs/research/gesture-corpus/media.csv (one row per scan: artist,
stem, medium, technique) from the corpus manifests. Re-run after adding
scans; hand-edit `medium-pairs.csv` to choose which within-hand medium
contrasts the panel projects out (see gesture/medium.py).

  .local/gesture/.venv/bin/python tools/gesture/experiments/make_media_manifest.py
"""
from __future__ import annotations

import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M = REPO / "docs/research/gesture-corpus"


def matisse_medium(obj: str, tech: str) -> str:
    t = f"{obj} {tech}".lower()
    if "lithograph" in t:
        return "lithograph"
    if "etching" in t or "engraving" in t or "drypoint" in t:
        return "etching"
    if "linocut" in t:
        return "linocut"
    if "pen" in t:
        return "pen_ink"
    return "drawing_unspecified"


def met_medium(artist: str, med: str) -> str:
    t = med.lower()
    if artist == "hokusai":
        return "ink_brush_colour" if "color" in t else "ink_brush"
    if "counterproof" in t:
        return "counterproof"
    if "chalk" in t:
        return "chalk_graphite"
    return "graphite"


def main() -> None:
    rows = []
    for r in csv.DictReader(open(M / "matisse-smk.csv")):
        rows.append({"artist": "matisse", "stem": Path(r["file"]).stem,
                     "medium": matisse_medium(r["object_type"], r["technique"]),
                     "technique": r["technique"] or r["object_type"]})
    for r in csv.DictReader(open(M / "comparison-met.csv")):
        rows.append({"artist": r["artist"], "stem": Path(r["file"]).stem,
                     "medium": met_medium(r["artist"], r["medium"]), "technique": r["medium"]})
    with open(M / "media.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["artist", "stem", "medium", "technique"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows → {M / 'media.csv'}")


if __name__ == "__main__":
    main()

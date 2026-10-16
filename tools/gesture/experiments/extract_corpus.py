"""Run stroke extraction over the scan corpus.

    cd tools/gesture
    ../../.local/gesture/.venv/bin/python -m experiments.extract_corpus --artist matisse --limit 5

Writes, per scan, ``.local/gesture/out/extract/<artist>/<stem>.json`` (the
Drawing, original-pixel geometry) and ``<stem>.png`` (debug overlay,
downscaled) and prints a summary table. Files that fail to open (e.g. a
download still in progress) are skipped and reported.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))          # tools/gesture → `import gesture`
REPO = HERE.parents[3]

import importlib  # noqa: E402

from gesture.extract import debug_overlay, load_image  # noqa: E402

CORPUS = REPO / ".local/gesture/corpus"
OUT = REPO / ".local/gesture/out/extract"
MANIFESTS = REPO / "docs/research/gesture-corpus"


def manifest_rows() -> dict[str, dict]:
    """filename → manifest row (all manifests; unreadable ones skipped)."""
    rows: dict[str, dict] = {}
    for m in sorted(MANIFESTS.glob("*.csv")):
        try:
            with m.open(newline="") as f:
                for r in csv.DictReader(f):
                    name = Path(r.get("file") or "").name
                    if name:
                        rows[name] = r
        except Exception as e:  # a manifest being written concurrently
            print(f"[skip manifest] {m.name}: {e}", file=sys.stderr)
    return rows


def select(artist: str, tier: str | None, files: list[str] | None,
           limit: int | None) -> list[tuple[Path, dict]]:
    rows = manifest_rows()
    folder = CORPUS / artist
    cands = sorted(p for p in folder.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"})
    out = []
    for p in cands:
        r = rows.get(p.name, {})
        if files and p.stem not in files and p.name not in files:
            continue
        if tier and r and (r.get("tier") or "").strip() != tier:
            continue
        out.append((p, r))
    if artist == "matisse" and not files:
        # manifest order is the curator's order; keep it for tier selection
        order = {name: i for i, name in enumerate(rows)}
        out.sort(key=lambda t: order.get(t[0].name, 1 << 30))
    return out[:limit] if limit else out


def run_one(path: Path, row: dict, artist: str, max_side: int, kw: dict,
            method: str = "extract") -> dict:
    extract = importlib.import_module(f"gesture.{method}").extract
    invert = (row.get("inverted") or "").strip().lower() in {"yes", "true", "1", "y"}
    t0 = time.perf_counter()
    with Image.open(path) as im:
        size = im.size
    gray, scale = load_image(path, invert=invert, max_side=max_side)
    d = extract(gray, scale=scale, source=str(path.relative_to(REPO)), original_size=size, **kw)
    dt = time.perf_counter() - t0
    od = (OUT if method == "extract" else OUT.parent / method) / artist
    od.mkdir(parents=True, exist_ok=True)
    d.meta["run"] = {"invert": invert, "max_side": max_side, "seconds": round(dt, 2),
                     "tier": row.get("tier")}
    d.save(od / f"{path.stem}.json")
    ov = debug_overlay(gray, d, max_side=1600)
    Image.fromarray(ov).save(od / f"{path.stem}.png")
    lens = [s.length() for s in d.strokes]
    c = d.meta["counts"]
    return {
        "file": path.name, "size": f"{size[0]}x{size[1]}", "scale": round(scale, 3),
        "w_px": d.meta["line_width_px"], "strokes": len(d.strokes),
        "closed": c["strokes_closed"],
        "med_len": round(float(np.median(lens)), 1) if lens else 0.0,
        "med_len_w": round(float(np.median(lens)) / max(d.meta["line_width_px"], 1e-9), 1) if lens else 0.0,
        "junctions": c["junctions"], "spurs": c["spurs_pruned"], "xm": c["x_merged"],
        "plate": c.get("plate_lines", 0), "secs": round(dt, 2),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--artist", default="matisse", choices=["matisse", "hokusai", "ingres"])
    ap.add_argument("--tier", default=None, help="manifest tier filter (A/B)")
    ap.add_argument("--files", nargs="*", help="stems or filenames to run")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-side", type=int, default=3000)
    ap.add_argument("--method", default="extract",
                    help="extractor module; output goes to out/<method>/ (out/extract/ for the default)")
    ap.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE",
                    help="ExtractParams overrides, e.g. --set spur_factor=2.5")
    a = ap.parse_args(argv)
    kw: dict = {}
    for kv in a.set:
        k, v = kv.split("=", 1)
        try:
            kw[k] = int(v) if v.isdigit() else float(v)
        except ValueError:
            kw[k] = {"true": True, "false": False}.get(v.lower(), v)
    todo = select(a.artist, a.tier, a.files, a.limit)
    if not todo:
        print(f"no scans selected in {CORPUS / a.artist}")
        return 1
    res, skipped = [], []
    for p, r in todo:
        try:
            res.append(run_one(p, r, a.artist, a.max_side, kw, a.method))
            print(f"  done {p.name} ({res[-1]['secs']} s)", file=sys.stderr)
        except (OSError, SyntaxError, ValueError) as e:   # unreadable / partial file
            skipped.append((p.name, str(e)[:80]))
    cols = ["file", "size", "scale", "w_px", "strokes", "closed", "med_len", "med_len_w",
            "junctions", "spurs", "xm", "plate", "secs"]
    wid = {c: max(len(c), *(len(str(r[c])) for r in res)) for c in cols} if res else {}
    print("  ".join(c.rjust(wid[c]) for c in cols))
    for r in res:
        print("  ".join(str(r[c]).rjust(wid[c]) for c in cols))
    for name, err in skipped:
        print(f"[skipped] {name}: {err}")
    print(f"outputs: {OUT / a.artist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Extraction bake-off: score extractor modules on synthetic ground truth and
on the Matisse corpus with the same harness (gesture/extract_eval.py).

  cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.bench_extract \
      --methods extract_naive extract --gt --real --limit 19

Each method is a module gesture/<name>.py exposing extract(gray, **kw) -> Drawing,
gray float [0,1], ink dark. Results: .local/gesture/out/bench/<method>/ (JSON,
overlays) and a summary table printed + written to .local/gesture/out/bench/summary.md.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from gesture import synth
from gesture.extract_eval import reference_ink, score_gt, score_real

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / ".local/gesture/out/bench"
CORPUS = ROOT / ".local/gesture/corpus"
MANIFEST = ROOT / "docs/research/gesture-corpus/matisse-smk.csv"


def gt_cases():
    """(name, truth Drawing, gray, line_width). Fixed seeds: identical every run."""
    cases = []
    size = (1200, 1200)
    scenes = [("x", synth.scene_x_crossing(size)), ("t", synth.scene_t_junction(size)),
              ("loop", synth.scene_closed_loop(size))]
    for sd in range(3):
        scenes.append((f"random{sd}", synth.scene_random(np.random.default_rng(sd), size, 8)))
        scenes.append((f"matisse{sd}", synth.scene_matisse_like(np.random.default_rng(100 + sd), size)))
    for lw, noise, tag in ((3.0, 0.03, "thin"), (6.0, 0.08, "thick-noisy")):
        for name, d in scenes:
            img = synth.render(d, line_width=lw, paper_noise=noise, use_stroke_width=False, seed=7)
            cases.append((f"{name}-{tag}", d, img.astype(np.float64) / 255.0, lw))
    return cases


def real_cases(limit: int, tiers=("A",)):
    rows = [r for r in csv.DictReader(open(MANIFEST)) if r["tier"] in tiers][:limit]
    for r in rows:
        im = Image.open(CORPUS / "matisse" / r["file"]).convert("L")
        scale = 1.0
        if max(im.size) > 2500:
            scale = 2500 / max(im.size)
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        g = np.asarray(im, dtype=np.float64) / 255.0
        if r.get("inverted") == "yes":
            g = 1.0 - g
        yield r["file"], g, scale


def overlay(gray, drawing, path, max_side=1400):
    H, W = gray.shape
    k = min(1.0, max_side / max(H, W))
    base = Image.fromarray((180 + 75 * gray).clip(0, 255).astype(np.uint8)).convert("RGB")
    base = base.resize((max(1, round(W * k)), max(1, round(H * k))))
    dr = ImageDraw.Draw(base)
    rng = np.random.default_rng(0)
    for s in drawing.strokes:
        c = tuple(int(v) for v in rng.integers(30, 220, 3))
        p = s.points * k
        if s.closed:
            p = np.vstack([p, p[:1]])
        if len(p) > 1:
            dr.line([tuple(q) for q in p], fill=c, width=2)
            dr.ellipse([p[0][0] - 2, p[0][1] - 2, p[0][0] + 2, p[0][1] + 2], outline=c)
    base.save(path)


def run(method, do_gt, do_real, limit, refs):
    mod = importlib.import_module(f"gesture.{method}")
    od = OUT / method
    od.mkdir(parents=True, exist_ok=True)
    res = {"method": method, "gt": [], "real": []}
    if do_gt:
        for name, truth, g, lw in gt_cases():
            t0 = time.time()
            try:
                d = mod.extract(g)
                sc = score_gt(truth, d, lw)
            except Exception as e:  # a crash is a result too
                sc = {"error": repr(e)[:200]}
            sc.update(case=name, seconds=round(time.time() - t0, 2))
            res["gt"].append(sc)
    if do_real:
        for name, g, scale in real_cases(limit):
            if name not in refs:
                refs[name] = reference_ink(g)
            t0 = time.time()
            try:
                d = mod.extract(g)
                sc = score_real(g, d, refs[name])
                overlay(g, d, od / f"{Path(name).stem}.png")
                d.save(od / f"{Path(name).stem}.json")
            except Exception as e:
                sc = {"error": repr(e)[:200]}
            sc.update(case=name, seconds=round(time.time() - t0, 2))
            res["real"].append(sc)
    (od / "scores.json").write_text(json.dumps(res, indent=1))
    return res


def _mean(rows, key):
    v = [r[key] for r in rows if key in r and r[key] == r[key]]
    return float(np.mean(v)) if v else float("nan")


def summarize(results):
    lines = ["| method | GT cover | GT prec | GT contin | GT frags | GT κ err | real cover | real prec | real mean_len | real short | real rough | s/scan | errors |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        g, q = r["gt"], r["real"]
        errs = sum("error" in x for x in g + q)
        lines.append("| {} | {:.3f} | {:.3f} | {:.3f} | {:.2f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.1f} | {:.1f} | {} |".format(
            r["method"], _mean(g, "coverage"), _mean(g, "precision"), _mean(g, "continuity"),
            _mean(g, "fragments"), _mean(g, "kappa_err"), _mean(q, "ink_coverage"),
            _mean(q, "ink_precision"), _mean(q, "mean_len"), _mean(q, "short_frac"),
            _mean(q, "roughness"), _mean(q, "seconds"), errs))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", nargs="+", default=["extract_naive"])
    ap.add_argument("--gt", action="store_true")
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--limit", type=int, default=19)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    refs, results = {}, []
    for m in a.methods:
        results.append(run(m, a.gt, a.real, a.limit, refs))
        print(f"done {m}", flush=True)
    table = summarize(results)
    print(table)
    (OUT / f"summary-{'-'.join(a.methods)}.md").write_text(table + "\n")


if __name__ == "__main__":
    main()

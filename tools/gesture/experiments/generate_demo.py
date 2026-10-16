"""Grammar v2 demo: population sheets and a juxtaposition sheet (LOOK at them).

Per artist: 8 generated drawings in contiguous mode (tree relations), 4 in
single-line mode, 2 real drawings reduced to the long-stroke subset the
grammar learned from — all through `synth.render` on a 1000×1200 canvas.
Juxtaposition: one long line code-switching Matisse → Hokusai → Matisse
(and the reverse), and a Matisse-structure tree redrawn in Hokusai's hand
(`restyle` per stroke, `translate_tokens` per stroke).

Uses the per-drawing fits cached by `experiments.grammar_eval prepare`
(computed here if missing). Writes .local/gesture/out/grammar_v2/demo/
{sheet_<artist>.png, juxtaposition.png, summary.json} and JPEG copies
(≤ 600 KB) next to them for results/.

    cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.generate_demo
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import grammar as gm  # noqa: E402
from gesture import synth  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

from experiments.grammar_eval import ARTISTS, OUT, load, prepared  # noqa: E402

DEMO = OUT / "demo"
CANVAS = (1000, 1200)
LINE_W = 2.6
TILE = (400, 480)
# Flexoki (axibridge/static/css/flexoki.css): paper, black, red-600, blue-600, green-600, base-300
PAPER, INK = (0xFF, 0xFC, 0xF0), (0x10, 0x0F, 0x0F)
HAND = {"matisse": (0xAF, 0x30, 0x29), "hokusai": (0x20, 0x5E, 0xA6), "ingres": (0x66, 0x80, 0x0B)}
GREY = (0xB7, 0xB5, 0xAC)


def fit_to_canvas(d: Drawing, size=CANVAS, margin=30) -> Drawing:
    allp = np.vstack([s.points for s in d.strokes])
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    k = min((size[0] - 2 * margin) / max(hi[0] - lo[0], 1e-9), (size[1] - 2 * margin) / max(hi[1] - lo[1], 1e-9))
    off = margin + 0.5 * (np.array(size) - 2 * margin - k * (hi - lo))
    return Drawing([Stroke((s.points - lo) * k + off) for s in d.strokes], source=d.source, size=size)


def tint(gray: np.ndarray) -> Image.Image:
    a = (gray.astype(np.float32) / 255.0)[..., None]
    return Image.fromarray((np.array(PAPER) * a + np.array(INK) * (1 - a)).astype(np.uint8))


def render(d: Drawing) -> Image.Image:
    g = synth.render(d, line_width=LINE_W, use_stroke_width=False, paper_noise=0.0, blur_sigma=0.5,
                     supersample=2)
    return tint(g)


def label(img: Image.Image, text: str) -> Image.Image:
    img = img.copy()
    ImageDraw.Draw(img).text((8, 6), text, fill=(0x6F, 0x6E, 0x69))
    return img


def grid(tiles, cols, title=""):
    rows = (len(tiles) + cols - 1) // cols
    W, H = TILE
    top = 28
    sheet = Image.new("RGB", (cols * W + (cols + 1) * 8, rows * H + (rows + 1) * 8 + top), (0xF2, 0xF0, 0xE5))
    ImageDraw.Draw(sheet).text((10, 8), title, fill=INK)
    for i, t in enumerate(tiles):
        if t is None:
            continue
        r, c = divmod(i, cols)
        sheet.paste(t.resize(TILE, Image.Resampling.LANCZOS), (8 + c * (W + 8), top + 8 + r * (H + 8)))
    return sheet


def save_jpeg(img: Image.Image, path: Path, max_kb=600):
    q, im = 88, img
    while True:
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024 or q < 40:
            break
        q -= 8
        if q < 64:
            im = im.resize((int(im.width * 0.85), int(im.height * 0.85)), Image.Resampling.LANCZOS)


def clean_score(d: Drawing) -> float:
    """Prefer real drawings whose long-stroke subset carries most of the ink."""
    keep, info = gm.select_long(d)
    return info["ink_long"] / max(info["ink_all"], 1e-9)


def population_sheet(art, g, drawings, rng):
    tiles = []
    gens = []
    for i in range(8):
        d = gm.generate_drawing(g, rng, CANVAS)
        gens.append(d)
        tiles.append(label(render(d), f"contiguous {i + 1}: {len(d.strokes)} strokes, ink {d.meta['ink']:.1f} R"))
    reals = sorted(drawings, key=lambda sd: clean_score(sd[1]), reverse=True)[:2]
    rt = []
    for stem, d in reals:
        ld = fit_to_canvas(gm.long_drawing(d))
        rt.append(label(render(ld), f"REAL {stem}, long strokes only ({len(ld.strokes)})"))
    singles = []
    for i in range(4):
        d = gm.generate_drawing(g, rng, CANVAS, mode="single")
        singles.append(label(render(d), f"single line {i + 1}: ink {d.strokes[0].length() / d.meta['ref_length_gen']:.1f} R"
                             if d.strokes else "single: empty"))
    # row 1 = 4 contiguous + real 1, row 2 = 4 contiguous + real 2, row 3 = 4 single lines
    layout = tiles[:4] + [rt[0]] + tiles[4:8] + [rt[1]] + singles + [None]
    return grid(layout, 5, f"{art} - grammar v2 (sigma = {g.meta['sigma_w']:g} w, long strokes only): "
                           "rows 1-2 contiguous/tree mode + a real long-stroke subset (right); row 3 single line"), gens


def _draw_lines(size, polys, scale=1.0):
    img = Image.new("RGB", size, PAPER)
    dr = ImageDraw.Draw(img)
    for pts, col in polys:
        if len(pts) >= 2:
            dr.line([tuple(p) for p in (pts * scale).tolist()], fill=col, width=3, joint="curve")
    return img


def _spans_polys(st: Stroke, colours):
    s = gm._arclen(st.points)
    out = []
    for s0, s1, hand in st.meta.get("spans", []):
        m = (s >= s0 - 1e-6) & (s <= s1 + 1e-6)
        out.append((st.points[m], colours.get(hand, INK)))
    return out


def juxtaposition_sheet(G, rng):
    tiles = []
    gm_, gh = G["matisse"], G["hokusai"]
    for hands, lab in (((gm_, gh), "one line: Matisse (red) / Hokusai (blue) alternating"),
                       ((gh, gm_), "one line: Hokusai (blue) / Matisse (red) alternating"),
                       ((gm_, gh), "one line: Matisse / Hokusai, again")):
        d = gm.generate_drawing(gm_, rng, CANVAS, mode="single", hands=hands, switch_every=2.0)
        polys = _spans_polys(d.strokes[0], HAND) if d.strokes else []
        tiles.append(label(_draw_lines(CANVAS, polys), lab))
    # structure from Matisse, hand from Hokusai
    tree = gm.generate_drawing(gm_, rng, CANVAS)
    R = tree.meta["ref_length_gen"]
    tiles.append(label(_draw_lines(CANVAS, [(s.points, HAND["matisse"]) for s in tree.strokes]),
                       "Matisse tree (structure + hand)"))
    rs = []
    for s in tree.strokes:
        try:
            rs.append((gm.restyle(s.points, gh, rng, ref_length=R, step=1.0).points, HAND["hokusai"]))
        except Exception:  # noqa: BLE001 — a degenerate stroke stays as drawn
            rs.append((s.points, GREY))
    tiles.append(label(_draw_lines(CANVAS, [(s.points, GREY) for s in tree.strokes] + rs),
                       "same tree, restyled in Hokusai's hand (grey = Matisse base)"))
    tr = []
    for s in tree.strokes:
        toks = gm.translate_tokens(s.meta["tokens"], gm_, gh)
        p, _, _ = gm.tokens_to_points(toks, R, start=s.meta["start"], heading=s.meta["heading"], step=1.0)
        tr.append((p, HAND["hokusai"]))
    tiles.append(label(_draw_lines(CANVAS, tr), "same tree, every token translated to Hokusai's nearest"))
    return grid(tiles, 3, "juxtaposition - code-switching along one line; Matisse structure in Hokusai's hand")


def grammar_summary(g) -> dict:
    nseg = [gm.n_segments(s) for s in g.strokes]
    return {"n_strokes": len(g.strokes), "segment_counts": g.segment_counts(),
            "segments_per_stroke_median": float(np.median(nseg)),
            "share_single": float(np.mean(np.array(nseg) == 1)),
            "transition_rows": list(gm.FROM), "transition_cols": list(gm.TO),
            "transition_matrix": np.round(g.transition(), 3).tolist(),
            "relations": {k: v for k, v in g.relations.items() if k not in ("u", "angle")},
            "branch_angle_deg_median": float(np.degrees(np.median(g.relations["angle"]))) if g.relations["angle"] else None,
            "ink_per_drawing_median": float(np.median([d["ink"] for d in g.drawings]))}


def main():
    DEMO.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    P = prepared()
    G = {a: gm.learn(prepared=[pd for _, pd in P[a]], name=a) for a in ARTISTS}
    print(f"[{time.time() - t0:5.1f}s] learned")
    rng = np.random.default_rng(20261016)
    summary = {}
    for a in ARTISTS:
        sheet, _ = population_sheet(a, G[a], load(a), rng)
        sheet.save(DEMO / f"sheet_{a}.png")
        save_jpeg(sheet.convert("RGB"), DEMO / f"sheet_{a}.jpg")
        summary[a] = grammar_summary(G[a])
        print(f"[{time.time() - t0:5.1f}s] sheet {a}")
    jx = juxtaposition_sheet(G, rng)
    jx.save(DEMO / "juxtaposition.png")
    save_jpeg(jx, DEMO / "juxtaposition.jpg")
    (DEMO / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"[{time.time() - t0:5.1f}s] done → {DEMO}")


if __name__ == "__main__":
    main()

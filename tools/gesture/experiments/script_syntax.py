"""Script syntax as an assembly grammar for foreign gestures (round 8).

Stages (python -m tools.gesture.experiments.script_syntax <stage>):
  measure   ink masks of calligraphy + print sheets → syntax records
            (.local/gesture/out/script_syntax/records.json) + overlays
  table     genre summary (generative and measure-only sides)
  pairs     syntax lines vs controls built from the SAME Matisse/Hokusai
            fragments, A/B order shuffled, key written to key.json
  genres    one fragment pool, five generative syntax models
  mashq     limb: siyah-mashq overwriting → lines become mass

Policy: generation uses only SyntaxModels fitted with generative=True, i.e.
sheets passing calligraphy.require_generative. Print (Bulaq) and album /
manuscript pages are measured for the contrast table only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gesture import calligraphy as cal  # noqa: E402
from gesture import script_syntax as ss  # noqa: E402
from gesture.core import Drawing  # noqa: E402

REPO = HERE.parents[2]
OUT = REPO / ".local/gesture/out/script_syntax"
RES = REPO / "tools/gesture/results"
EXH = REPO / ".local/gesture/out/extract_hybrid"

# sheets measured (generative flag comes from the manifest, never from here)
CALL_SHEETS = {
    "shikasta": ["wc-12", "wc-13", "wc-15", "wc-10", "wc-17", "met-450714"],
    "nastaliq": ["met-716305", "met-716307", "wal-W668-66b", "wal-W668-74b", "met-716304", "met-450713", "wc-24"],
    "diwani": ["wc-05", "wc-39"],
    "maghribi": ["wc-30", "wc-32", "wc-33"],
    "karalama": ["wal-W672-5b", "wal-W672-6a"],
    "naskh": ["cma-1945.383.b", "cma-1977.91.a"],
}
# baseline page angles (deg, seen CCW), set by eye from angles.jpg like the
# crops: the automatic estimators (projection peakiness, body-centroid
# alignment, calligraphy.dominant_direction) confuse the slant of the sweeps,
# justified columns and siyah-mashq diagonals with the line. Sheets not
# listed are near-horizontal and use the projection estimator within ±12°.
ANGLES = {"wc-12": 20.0, "wc-13": 20.0, "wc-15": 0.0, "met-716305": 0.0, "met-716307": -30.0,
          "wal-W668-66b": -32.0, "wal-W668-74b": -40.0, "met-716304": 0.0, "met-450713": 32.0}
SKIP = {"wc-10", "wc-17", "wc-24"}        # faint masks: no bodies survive Otsu

PRINT_PAGES = ["AL08_p0018", "AL08_p0028", "AL08_p0031", "AL08_p0038", "AL09_p0086", "AL09_p0143",
               "AL09_p0181", "AL09_p0199"]

FLEX = {"blue": (67, 133, 190), "red": (209, 77, 65), "green": (135, 154, 57), "orange": (218, 112, 44)}


def _font(sz=18):
    for f in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def sheet_mask(sid: str, max_side: int = 2200):
    from skimage.filters import threshold_otsu

    if sid.startswith("AL"):
        p = next((REPO / ".local/gesture/corpus/print").rglob(f"{sid}*"), None)
        if p is None:
            raise FileNotFoundError(sid)
        im = Image.open(p).convert("L")
        s = min(1.0, max_side / max(im.size))
        im = im.resize((round(im.size[0] * s), round(im.size[1] * s)), Image.Resampling.BOX)
        g = np.asarray(im, float) / 255.0
        H, W = g.shape
        g = g[int(0.08 * H):int(0.92 * H), int(0.08 * W):int(0.92 * W)]   # margins, folios
    else:
        g, s, _ = cal.load_sheet(sid, max_side=max_side)
        g, _ = cal.remove_rules(g)
    t = threshold_otsu(g)
    from scipy import ndimage as ndi
    m = g < t
    m = ndi.binary_opening(m, iterations=1)
    return m, g


def stage_measure():
    OUT.mkdir(parents=True, exist_ok=True)
    man = {**cal.load_manifest("print"), **cal.load_manifest("calligraphy")}
    recs = []
    jobs = [(g, s) for g, ids in CALL_SHEETS.items() for s in ids] + [("bulaq", p) for p in PRINT_PAGES]
    ov = []
    for genre, sid in jobs:
        if sid in SKIP:
            continue
        try:
            m, g = sheet_mask(sid)
        except Exception as e:  # noqa: BLE001
            print("skip", sid, e)
            continue
        w = ss.pen_width(m)
        a = ANGLES.get(sid)
        if a is None:
            a = ss.baseline_angle(m, w, span=12.0)
        r = ss.measure_mask(m, source=sid, genre=genre, w=w, angle=a)
        mid = cal._manifest_id(sid) if not sid.startswith("AL") else sid
        row = man.get(mid)
        r["generative"] = bool(row and cal.generative_allowed(row)) and sid not in ss.EXCLUDE_GENERATIVE
        r["content_type"] = row.get("content_type") if row else "?"
        recs.append(r)
        nb = sum(len(ln["bodies"]) for ln in r["lines"])
        print(f"{genre:9s} {sid:16s} gen={r['generative']!s:5s} w={r['w_px']:.1f} angle={r['angle']:+.0f} "
              f"lines={len(r['lines'])} bodies={nb} dots={r['n_dots']} marks={r['n_marks']}", flush=True)
        ov.append(_overlay(m, r, sid, genre))
    (OUT / "records.json").write_text(json.dumps(recs))
    _grid(ov, OUT / "measure_overlays.jpg", cols=4, cell=(520, 400))


def _overlay(m, r, sid, genre):
    """Mask (grey) with line baselines (blue) and body boxes, dots red —
    drawn in the rotated frame mapped back to the page."""
    H, W = m.shape
    im = Image.new("RGB", (W, H), ss.PAPER)
    a = np.asarray(im).copy()
    a[m] = (150, 150, 150)
    im = Image.fromarray(a)
    dr = ImageDraw.Draw(im)
    w = r["w_px"]
    ang = np.deg2rad(r["angle"])
    c, s = np.cos(ang), np.sin(ang)

    def back(xr, yr):  # inverse of ss._rot
        return (xr * c + yr * s, -xr * s + yr * c)

    for ln in r["lines"]:
        y = ln["y"] * w
        x0, x1 = ln["bodies"][-1]["xl"] * w, ln["bodies"][0]["xr"] * w
        dr.line([back(x0, y), back(x1, y)], fill=FLEX["blue"], width=max(2, int(w / 3)))
        for b in ln["bodies"]:
            yb = y + b["offset"] * w
            pts = [back(b["xl"] * w, yb - b["rise"] * w), back(b["xr"] * w, yb - b["rise"] * w),
                   back(b["xr"] * w, yb + b["drop"] * w), back(b["xl"] * w, yb + b["drop"] * w)]
            dr.polygon(pts, outline=FLEX["green"])
            for rx, h in b["asc"]:
                xa = (b["xr"] - rx * (b["xr"] - b["xl"])) * w
                dr.line([back(xa, yb), back(xa, yb - h * w)], fill=FLEX["orange"], width=max(2, int(w / 4)))
            for d in b["dots"]:
                xd = (b["xr"] - d["rx"] * (b["xr"] - b["xl"])) * w
                p = back(xd, yb + d["dy"] * w)
                rr = w * (1.2 if d["kind"] == "dot" else 0.8)
                dr.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr],
                           outline=FLEX["red"] if d["kind"] == "dot" else FLEX["blue"], width=2)
    im.thumbnail((520, 380))
    cell = Image.new("RGB", (520, 400), ss.PAPER)
    cell.paste(im, (0, 20))
    ImageDraw.Draw(cell).text((4, 2), f"{genre} {sid} {'GEN' if r['generative'] else 'measure-only'}",
                              fill=(0, 0, 0), font=_font(14))
    return cell


def _grid(cells, path, cols=4, cell=(520, 400), title=None):
    rows = (len(cells) + cols - 1) // cols
    top = 40 if title else 0
    sheet = Image.new("RGB", (cols * cell[0], rows * cell[1] + top), ss.PAPER)
    if title:
        ImageDraw.Draw(sheet).text((8, 8), title, fill=(0, 0, 0), font=_font(20))
    for i, c in enumerate(cells):
        sheet.paste(c, ((i % cols) * cell[0], top + (i // cols) * cell[1]))
    sheet.save(path, quality=85)
    return sheet


def stage_table():
    recs = json.loads((OUT / "records.json").read_text())
    rows = []
    groups = {}
    for r in recs:
        groups.setdefault((r["genre"], r["generative"]), []).append(r)
    keys = ["sheets", "lines", "bodies", "width_med", "rise_med", "drop_med", "gap_med", "overlap_frac",
            "asc_per_10w", "dots_per_body", "marks_per_body", "dot_above_frac", "offset_sd", "slope_med",
            "bodies_per_line", "width_ac1", "coverage"]
    for (g, gen), rs in sorted(groups.items()):
        s = ss.summarize(rs)
        if not s:
            continue
        rows.append({"genre": g, "generative": gen, **{k: s[k] for k in keys}})
    (OUT / "table.json").write_text(json.dumps(rows, indent=1))
    hdr = "| genre | gen | " + " | ".join(keys) + " |"
    print(hdr)
    for r in rows:
        print(f"| {r['genre']} | {'Y' if r['generative'] else 'm'} | " +
              " | ".join(f"{r[k]:.2f}" if isinstance(r[k], float) else str(r[k]) for k in keys) + " |")


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------

def models():
    recs = json.loads((OUT / "records.json").read_text())
    out = {}
    for g in ("shikasta", "nastaliq", "diwani", "maghribi"):   # karalama: rotated tangles; maghribi: no generative sheet left
        rs = [r for r in recs if r["genre"] == g and r["generative"] and ss.generative_ok(r["source"])
              and len(r["lines"])]
        if rs:
            out[g] = ss.SyntaxModel.fit(rs, generative=True, genre=g)
    return out


def banks(seed=0):
    rng = np.random.default_rng(seed)
    dm = [Drawing.load(p) for p in sorted((EXH / "matisse").glob("*.json"))[:40]]
    dh = [Drawing.load(p) for p in sorted((EXH / "hokusai").glob("*.json"))[:40]]
    bm = ss.fragment_bank(dm, rng, n=1200)
    bh = ss.fragment_bank(dh, rng, n=1200)
    th = ss.fragment_bank(dh, rng, n=400, len_frac=(0.01, 0.03))
    return {"matisse": bm, "hokusai": bh, "mixed": bm + bh, "ticks": th}


def compose_panel(model, bank, ticks, rng, size, *, w=9.0, n_lines=4, margin=40):
    W, H = size
    sp = H / (n_lines + 0.6)
    pieces_all, bands = [], []
    for i in range(n_lines):
        base = margin * 0.5 + sp * (i + 0.85)
        slots = model.sample_line(rng, (W - 2 * margin) / w)
        pcs = ss.assemble_line(slots, bank, rng, x_right=W - margin, base=base, w=w,
                               slope=float(np.clip(model.slope, -0.3, 0.3)), tick_bank=ticks)
        # keep inside the panel
        pcs = [p for p in pcs if p.pts[:, 0].min() > margin * 0.3]
        for p in pcs:
            p.body += 100 * i
        pieces_all += pcs
        allp = np.vstack([p.pts for p in pcs]) if pcs else np.array([[margin, base]])
        bands.append((float(allp[:, 0].min()), float(allp[:, 1].min()), float(allp[:, 0].max()),
                      float(allp[:, 1].max())))
    return pieces_all, bands


def _controls(pieces, bands, rng, kind):
    out = []
    for i, band in enumerate(bands):
        pcs = [p for p in pieces if 100 * i <= p.body < 100 * (i + 1)]
        f = ss.scatter_control if kind == "scatter" else ss.chain_control
        out += f(pcs, band, rng)
    return out


def stage_pairs(n_pairs=12, seed=8):
    rng = np.random.default_rng(seed)
    M = models()
    B = banks(seed)
    pdir = OUT / "pairs"
    pdir.mkdir(parents=True, exist_ok=True)
    key, cells, stats = [], [], []
    size = (900, 520)
    gl = list(M)
    for k in range(n_pairs):
        genre = gl[k % len(gl)]
        src = ("matisse", "hokusai")[(k // len(gl)) % 2]
        ctrl = ("scatter", "chain")[k % 2]
        syn, bands = compose_panel(M[genre], B[src], B["ticks"], rng, size)
        con = _controls(syn, bands, rng, ctrl)
        Ls, Lc = ss.ink_length(syn), ss.ink_length(con)
        a_is_syntax = bool(rng.random() < 0.5)
        A, Bp = (syn, con) if a_is_syntax else (con, syn)
        ia = ss.render(A, size)
        ib = ss.render(Bp, size)
        pair = Image.new("RGB", (size[0] * 2 + 30, size[1] + 40), ss.PAPER)
        pair.paste(ia, (0, 40))
        pair.paste(ib, (size[0] + 30, 40))
        dr = ImageDraw.Draw(pair)
        dr.text((10, 8), f"pair {k + 1:02d}   A", fill=(0, 0, 0), font=_font(20))
        dr.text((size[0] + 40, 8), "B", fill=(0, 0, 0), font=_font(20))
        dr.line([(size[0] + 15, 40), (size[0] + 15, size[1] + 40)], fill=(180, 180, 180), width=1)
        pair.save(pdir / f"pair_{k + 1:02d}.jpg", quality=88)
        cells.append(pair)
        key.append({"pair": k + 1, "syntax_side": "A" if a_is_syntax else "B", "genre": genre,
                    "fragments": src, "control": ctrl, "ink_syntax": Ls, "ink_control": Lc,
                    "model_sources": M[genre].sources})
        stats.append((Ls, Lc))
        print(key[-1]["pair"], genre, src, ctrl, key[-1]["syntax_side"], f"ink {Ls:.0f} / {Lc:.0f}")
    (OUT / "pairs_key.json").write_text(json.dumps(key, indent=1))
    # contact sheets of the pairs, 4 per image, for the results folder
    for j in range(0, len(cells), 4):
        grp = cells[j:j + 4]
        sheet = Image.new("RGB", (grp[0].width, sum(c.height for c in grp)), ss.PAPER)
        y = 0
        for c in grp:
            sheet.paste(c, (0, y))
            y += c.height
        sheet.thumbnail((1500, 3000))
        sheet.save(OUT / f"pairs_sheet_{j // 4 + 1}.jpg", quality=80)


def stage_genres(seed=11):
    """Same fragment pool, one panel per generative syntax model — plus the
    two controls on the same pieces as the top band."""
    rng = np.random.default_rng(seed)
    M = models()
    B = banks(seed)
    size = (1300, 300)
    rows = []
    for g, m in M.items():
        pcs, bands = compose_panel(m, B["mixed"], B["ticks"], rng, size, n_lines=2, w=8.0)
        im = ss.render(pcs, size)
        lab = Image.new("RGB", (size[0], size[1] + 26), ss.PAPER)
        lab.paste(im, (0, 26))
        ImageDraw.Draw(lab).text((8, 4), f"syntax after the {g} hand  (fitted on {', '.join(m.sources)}; "
                                         f"{len(m.lines)} lines) — bodies: Matisse+Hokusai fragments",
                                 fill=(0, 0, 0), font=_font(16))
        rows.append(lab)
    # controls on the last panel's pieces
    for kind in ("chain", "scatter"):
        con = _controls(pcs, bands, rng, kind)
        im = ss.render(con, size)
        lab = Image.new("RGB", (size[0], size[1] + 26), ss.PAPER)
        lab.paste(im, (0, 26))
        ImageDraw.Draw(lab).text((8, 4), f"control ({kind}): the same pieces as the {g} panel above, "
                                         f"syntax removed", fill=FLEX["red"], font=_font(16))
        rows.append(lab)
    sheet = Image.new("RGB", (size[0], sum(r.height for r in rows)), ss.PAPER)
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    sheet.save(OUT / "genres.jpg", quality=85)


def stage_mashq(seed=5):
    """Limb. Measure overwriting on the practice sheets, then overwrite
    syntax lines at the sheets' rotations until the page goes dark; dense
    zones turn into mass (shape regime) by accumulation."""
    recs = json.loads((OUT / "records.json").read_text())
    meas = {}
    for sid in ("met-716305", "met-716307", "wc-12", "wc-13", "wal-W672-5b", "wal-W672-6a", "wc-30", "wc-05"):
        m, _ = sheet_mask(sid)
        r = next(x for x in recs if x["source"] == sid)
        meas[sid] = {"genre": r["genre"], "angle": r["angle"], **ss.mashq_measure(m, r["w_px"])}
        print(sid, meas[sid])
    (OUT / "mashq_measure.json").write_text(json.dumps(meas, indent=1))
    rng = np.random.default_rng(seed)
    M = models()
    B = banks(seed)
    model = M["nastaliq"]
    size = (1100, 1100)
    W, H = size
    w = 8.0
    # practice-sheet rotations: the measured siyah-mashq line angles (± jitter)
    angs = [meas[s]["angle"] for s in ("met-716305", "met-716307", "wc-12", "wc-13")]
    stages = [1, 4, 12, 36]
    cells = []
    allp = []
    k = 0
    for n in stages:
        while k < n:
            a = np.deg2rad(rng.choice(angs) + rng.normal(0, 6))
            Lw = rng.uniform(40, 90)
            slots = model.sample_line(rng, Lw)
            pcs = ss.assemble_line(slots, B["mixed"], rng, x_right=0.0, base=0.0, w=w, tick_bank=B["ticks"])
            c = rng.normal([W / 2, H / 2], [W * 0.16, H * 0.16])
            ca, sa = np.cos(a), np.sin(a)
            R = np.array([[ca, sa], [-sa, ca]])           # seen-CCW rotation in y-down coords
            pts0 = np.vstack([p.pts for p in pcs])
            ctr = pts0.mean(axis=0)
            for p in pcs:
                p.pts = (p.pts - ctr) @ R.T + c
                p.body += 1000 * k
            allp += pcs
            k += 1
        im = ss.render(allp, size, pen=2.0)
        masses = ss.density_masses(allp, size, pen=2.0, sigma=2.2 * w, thresh=0.22, min_area=(6 * w) ** 2)
        im2 = ss.render(allp, size, pen=2.0, masses=masses)
        cov = float((np.asarray(im.convert("L")) < 128).mean())
        cov2 = float((np.asarray(im2.convert("L")) < 128).mean())
        for img, lab in ((im, f"{n} overwritten lines  (ink {cov:.0%})"),
                         (im2, f"{n} lines, dense zones → mass  ({len(masses)} masses, ink {cov2:.0%})")):
            c = Image.new("RGB", (W, H + 30), ss.PAPER)
            c.paste(img, (0, 30))
            ImageDraw.Draw(c).text((8, 6), lab, fill=(0, 0, 0), font=_font(18))
            c.thumbnail((640, 670))
            cells.append(c)
        print(n, "lines; coverage", cov, "with masses", cov2, "masses", len(masses))
    # arrange: two rows (plain / with masses) × 4 stages
    order = [cells[i] for i in range(0, len(cells), 2)] + [cells[i] for i in range(1, len(cells), 2)]
    _grid(order, OUT / "mashq_cloud_dud.jpg", cols=4, cell=(order[0].width, order[0].height),
          title="siyah mashq limb: syntax lines (after nasta'liq exercise sheets) overwritten at the practice "
                "sheets' measured angles; bottom row: blurred density > 0.22 filled as mass")





def _wobble(p, rng, amp, corr=25):
    """Smooth per-copy hand wobble: low-pass noise along the polyline."""
    from scipy.ndimage import gaussian_filter1d
    n = rng.standard_normal((len(p), 2))
    n = gaussian_filter1d(n, corr, axis=0, mode="nearest")
    n /= max(np.abs(n).max(), 1e-9)
    return p + amp * n


def stage_mashq2(seed=21):
    """Limb, second form. A practice sheet does not scatter lines in a
    cloud: it REWRITES the same line, nearly on top of itself, in bands at
    one or two angles. So: three syntax lines (nasta'liq model), each
    rewritten k times with a small offset, a ±2° turn and a smooth wobble,
    in bands at the measured siyah-mashq angles (−30°, +20°). Where the
    copies coincide, density passes the threshold and the line becomes
    mass in its own shape; loose tails and dots stay line."""
    rng = np.random.default_rng(seed)
    M = models()
    B = banks(seed)
    model = M["nastaliq"]
    size = (1100, 1100)
    W, H = size
    w = 9.0
    bands = [(-30.0, (560, 380)), (-30.0, (520, 640)), (20.0, (560, 560))]
    bases = []
    for ang, c in bands:
        slots = model.sample_line(rng, rng.uniform(70, 95))
        pcs = ss.assemble_line(slots, B["mixed"], rng, x_right=0.0, base=0.0, w=w, tick_bank=B["ticks"])
        ctr = np.vstack([p.pts for p in pcs]).mean(axis=0)
        bases.append((ang, np.array(c, float), pcs, ctr))
    cells, rows = [], []
    for kcopies in (1, 3, 8, 20):
        allp = []
        r2 = np.random.default_rng([seed, kcopies])
        for bi, (ang, c, pcs, ctr) in enumerate(bases):
            for k in range(kcopies):
                a = np.deg2rad(ang + r2.normal(0, 2.0))
                R = np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
                d = r2.normal(0, [1.5 * w, 0.7 * w]) @ R.T
                for p in pcs:
                    q = (p.pts - ctr) @ R.T + c + d
                    if not p.filled:
                        q = _wobble(q, r2, 0.35 * w)
                    allp.append(ss.Piece(p.kind, q, p.body + 1000 * (bi * 100 + k), p.filled))
        plain = ss.render(allp, size, pen=2.0)
        masses = ss.density_masses(allp, size, pen=2.0, sigma=0.9 * w, thresh=0.30, min_area=(2.5 * w) ** 2)
        mixed = ss.render(allp, size, pen=2.0, masses=masses)
        cov = float((np.asarray(plain.convert("L")) < 128).mean())
        cov2 = float((np.asarray(mixed.convert("L")) < 128).mean())
        rows.append({"copies": kcopies, "ink_lines": cov, "ink_with_mass": cov2, "masses": len(masses)})
        print(rows[-1])
        for img, lab in ((plain, f"each line rewritten {kcopies}x  (ink {cov:.0%})"),
                         (mixed, f"{kcopies}x, coincident zones -> mass ({len(masses)} masses, ink {cov2:.0%})")):
            cc = Image.new("RGB", (W, H + 34), ss.PAPER)
            cc.paste(img, (0, 34))
            ImageDraw.Draw(cc).text((8, 6), lab, fill=(0, 0, 0), font=_font(22))
            cc.thumbnail((640, 670))
            cells.append(cc)
    (OUT / "mashq2.json").write_text(json.dumps(rows, indent=1))
    order = [cells[i] for i in range(0, len(cells), 2)] + [cells[i] for i in range(1, len(cells), 2)]
    _grid(order, OUT / "mashq.jpg", cols=4, cell=(order[0].width, order[0].height),
          title="siyah mashq limb: 3 syntax lines (nasta'liq exercise model) rewritten 1/3/8/20x at -30/+20 deg; "
                "bottom: where copies coincide (blur 0.9w, >0.30) the line becomes mass")
    # a large single image of the 8x state for Ian
    return rows


if __name__ == "__main__":
    st = sys.argv[1] if len(sys.argv) > 1 else "measure"
    {"measure": stage_measure, "table": stage_table, "pairs": stage_pairs, "genres": stage_genres,
     "mashq_cloud": stage_mashq, "mashq": stage_mashq2}[st]()

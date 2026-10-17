"""Round 12, thread `drive` — inking a driven line.

`drive_ink` reads what the drive_* modulators wrote:
  dw      full ink width, mm → a disc of that width swept along the line,
          line-built (outline ring + one inset spiral per component, never
          hatching; swell_ink.sweep / line_fill), the centreline drawn through;
  pen_i   which pen (meta["drive_pens"], Flexoki names) → the mark is split
          where the pen changes; every piece keeps its colour in
          Ink.meta["colour"] (the plotter runs one pass per pen);
  knot    peaks → a knot at each pause: `wound` (the line itself winds out
          and back in — contiguous with the line), `bead` (a round spiral
          disc), or `none`.
Marks with meta["drive_role"] == "trace" (the measurement drawn by
`drive_beside`) are thin wires at `chart_pen`, split by pen the same way.

`render_colour(sheet)` previews in the inks' colours (the kit preview is
monochrome); `save(sheet, path)` writes it plus the recipe beside it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .core import INK, PAPER, Ink, P, renderer
from .dev_chorus import FLEXOKI
from .swell_ink import line_fill, spiral_disc, sweep, wound_path

KNOTS = ("wound", "bead", "none")
BODIES = ("sweep", "nib_e", "nib_c+e", "nib_b+", "nib_a")


def _runs_of(lev: np.ndarray):
    d = np.nonzero(np.diff(lev))[0] + 1
    a = np.r_[0, d]
    b = np.r_[d, len(lev)]
    return list(zip(a.tolist(), b.tolist()))


def _ink(p, pen, colour, role, closed=False, filled=False, voice=None):
    return Ink(np.asarray(p, np.float64), closed=closed, filled=filled, pen=pen,
               meta={"colour": colour, "role": role, "voice": voice})


def _peaks(k: np.ndarray, floor: float = 0.05) -> list[int]:
    if len(k) < 3:
        return []
    i = np.nonzero((k[1:-1] >= k[:-2]) & (k[1:-1] > k[2:]) & (k[1:-1] > floor))[0] + 1
    return i.tolist()


@renderer("drive_ink", params=[
    P("pen", "float", 0.4, "pen width mm", min=0.05, max=3.0),
    P("pitch", "float", 0.85, "fill: inset spacing in pens (< 1 reads solid)", min=0.4, max=4.0),
    P("sweep_from", "float", 1.6, "dw (in pens) above which the line is swept wide; below it stays a wire",
      min=1.0, max=20.0),
    P("knots", "choice", "wound", "wound: the line winds out and back (contiguous) | bead: a round disc | none",
      choices=KNOTS),
    P("knot_size", "float", 6.0, "knot diameter at a full-size pause, mm", min=0.5, max=30.0),
    P("chart_pen", "float", 0.25, "pen for the measurement traces, mm", min=0.05, max=3.0),
    P("body", "choice", "sweep", "sweep: a disc of width dw swept along the line (+ the centreline) | nib_<style>: "
      "the research broad nib from r / phi / W / M (drive_phi turns it), per pen", choices=BODIES),
], doc="a driven line: width swept from dw, split into pens by pen_i, knots wound at the driver's pauses",
    reach=lambda p: 0.5 * p["knot_size"] + p["pen"])
def drive_ink(ctx, marks, *, pen, pitch, sweep_from, knots, knot_size, chart_pen, body):
    import shapely  # noqa: PLC0415
    out = []
    for m in marks:
        if len(m) < 2:
            continue
        names = list(m.meta.get("drive_pens") or ["black"])
        lev = np.clip(np.round(np.asarray(m.channel("pen_i", 0.0))).astype(int), 0, len(names) - 1)
        trace = m.meta.get("drive_role") == "trace"
        scale = float(m.meta.get("drive_scale", 1.0))
        vid = m.meta.get("voice_id")
        pts = np.asarray(m.points)
        if trace:
            for a, b in _runs_of(lev):
                q = pts[a:min(b + 1, len(pts))]
                if len(q) >= 2:
                    out.append(_ink(q, chart_pen, names[lev[a]], "trace", voice=vid))
            continue
        dw = m.channel("dw")
        knot = m.channel("knot")
        tg = np.gradient(pts, axis=0)
        tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
        # where a knot winds, the plain line is replaced by the wound path (one contiguous line)
        kp = _peaks(np.asarray(knot)) if (knot is not None and knots != "none") else []
        winds = {}
        for c in kp:
            D = knot_size * float(knot[c]) * scale
            if D >= 2 * pen:
                winds[c] = D
        for a, b in _runs_of(lev):
            b1 = min(b + 1, len(pts))
            col = names[lev[a]]
            cs = sorted(c for c in winds if a <= c < b1)
            if body != "sweep":
                from .core import Mark, get  # noqa: PLC0415
                sub = Mark(pts[a:b1], {k: np.asarray(v)[a:b1] for k, v in m.channels.items()}, m.meta)
                if "W" in sub.channels and scale != 1.0:
                    sub = sub.evolve(channels={"W": np.asarray(sub["W"]) * scale, "M": np.asarray(sub["M"]) * scale})
                for k in get("renderer", "nib").fn(ctx, [sub], style=body[4:], pen=pen):
                    out.append(_ink(k.points, pen, col, "nib", k.closed, k.filled, vid))
                for c in cs:
                    if knots == "wound":
                        out.append(_ink(wound_path(pts[c], tg[c], 0.5 * winds[c], pen, pitch, 0.0), pen, col, "knot",
                                        voice=vid))
                    elif knots == "bead":
                        for p, closed, filled in spiral_disc(pts[c], 0.5 * winds[c], pen, pitch,
                                                             lambda t: np.ones_like(t)):
                            out.append(_ink(p, pen, col, "knot", closed, filled, vid))
                continue
            if knots == "wound" and cs:
                seg, last = [], a
                for c in cs:
                    seg.append(pts[last:c + 1])
                    seg.append(wound_path(pts[c], tg[c], 0.5 * winds[c], pen, pitch, 0.0))
                    last = c
                seg.append(pts[last:b1])
                line = np.vstack(seg)
            else:
                line = pts[a:b1]
            if len(line) >= 2:
                out.append(_ink(line, pen, col, "line", voice=vid))
            if knots == "bead":
                one = lambda t: np.ones_like(t)  # noqa: E731
                for c in cs:
                    for p, closed, filled in spiral_disc(pts[c], 0.5 * winds[c], pen, pitch, one):
                        out.append(_ink(p, pen, col, "knot", closed, filled, vid))
            if dw is not None:
                w = np.asarray(dw[a:b1])
                on = w > sweep_from * pen
                if on.any():
                    d = np.diff(np.r_[0, on.astype(np.int8), 0])
                    i0s, i1s = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
                    geoms = []
                    for i0, i1 in zip(i0s, i1s):
                        lo, hi = max(i0 - 1, 0), min(i1 + 1, len(w))     # let the swell start from the pen
                        C = pts[a + lo:a + hi]
                        r = np.maximum(0.5 * w[lo:hi], 0.5 * pen)
                        if len(C) >= 1:
                            geoms.append(sweep(C, r))
                    if geoms:
                        g = shapely.union_all(geoms)
                        for p, closed, filled in line_fill(g, pen, pitch):
                            out.append(_ink(p, pen, col, "swell", closed, filled, vid))
    return out


# ---------------------------------------------------------------------------
# colour preview
# ---------------------------------------------------------------------------

def _hex(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def ink_colour(ink) -> tuple:
    name = ink.meta.get("colour") or "black"
    return _hex(FLEXOKI.get(name, FLEXOKI["black"])) if name in FLEXOKI else INK


def render_colour(sheet, *, px_per_mm: float = 6.0, label: str | None = None, ss: int = 2, mono: bool = False):
    """PIL image: inks at their pen width, each in its Ink.meta["colour"]
    (Flexoki), one layer per colour in order of first appearance."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    from .core import _font  # noqa: PLC0415
    W, H = sheet.frame
    k = px_per_mm * ss
    order = []
    for ink in sheet.inks:
        c = INK if mono else ink_colour(ink)
        if c not in order:
            order.append(c)
    rgb = np.ones((int(round(H * px_per_mm)), int(round(W * px_per_mm)), 3)) * np.array(PAPER, float)
    for c in order:
        im = Image.new("L", (int(round(W * k)), int(round(H * k))), 0)
        dr = ImageDraw.Draw(im)
        for ink in sheet.inks:
            if (INK if mono else ink_colour(ink)) != c:
                continue
            q = ink.points * k
            d = max(ink.pen * k, 1.0)
            if len(q) >= 2:
                dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
            r = d / 2
            for v in (q if d > 4 else q[[0, -1]]):
                dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
        im = im.resize((rgb.shape[1], rgb.shape[0]), Image.Resampling.BOX)
        a = np.asarray(im, float)[..., None] / 255.0
        rgb = rgb * (1 - a) + np.array(c, float) * a
    out = Image.fromarray(rgb.astype(np.uint8), "RGB")
    if label is None:
        return out
    fs = max(12, int(out.width / 90))
    strip = Image.new("RGB", (out.width, int(fs * 2.0)), PAPER)
    ImageDraw.Draw(strip).text((int(fs * 0.6), int(fs * 0.45)), label, fill=INK, font=_font(fs))
    full = Image.new("RGB", (out.width, out.height + strip.height), PAPER)
    full.paste(out, (0, 0))
    full.paste(strip, (0, out.height))
    return full


def save(sheet, path, *, px_per_mm: float = 6.0, label: str | None = None, quality: int = 88, mono=False) -> Path:
    """Colour preview + the normalized recipe beside it (<stem>.recipe.json)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = render_colour(sheet, px_per_mm=px_per_mm, label=label, mono=mono)
    im.save(path, quality=quality, optimize=True) if path.suffix.lower() in (".jpg", ".jpeg") else im.save(path)
    sheet.save_recipe(path.with_suffix(".recipe.json"))
    return path

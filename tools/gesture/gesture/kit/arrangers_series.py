"""Series arranger + the cut into sheets (round 12, thread `series`).

The unit here is a SET of sheets, read in order. A series recipe is an
ordinary kit recipe whose frame is the whole row (sheets side by side, no
gutter: a line that leaves sheet k at its right edge enters sheet k+1 at its
left edge at the same height). `run_series(recipe)` runs it once and cuts the
inks into the sheets; sheet k's own recipe is {"series": recipe, "sheet": k},
and `run_sheet(that)` rebuilds exactly that sheet.

- `series_row`  part 0 grows the travelling line (any voice; `series_travel`
                is made for it) and its modulators run on the whole line.
                Then the line is cut at progress values `at` into stretches;
                stretch j is handed to part j+1, whose own modulators and
                renderer weight it (its voice is ignored when it is
                `series_stretch`; any other voice is grown as a GUEST in the
                sheets the stretch occupies). Each stretch gets `age` (0…1
                within the stretch — what trail_gallery widens by) and keeps
                `series_u` (0…1 along the whole line).

The cut is geometric: ink polylines are clipped to each sheet's rectangle,
so a mass that straddles an edge is split by the paper, as it would be.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .core import INK, P, PAPER, Ink, Mark, Sheet, _font, arranger
from .core import run as kit_run


def _u(m: Mark) -> np.ndarray:
    u = m.channel("series_u")
    if u is None:
        s = m.arclength()
        u = s / max(s[-1], 1e-9)
    return np.asarray(u)


def split_at(marks: list[Mark], at: list[float]) -> list[list[Mark]]:
    """Stretches of the line(s) between progress values `at` (sorted)."""
    edges = [0.0, *sorted(float(a) for a in at), 1.0 + 1e-9]
    out: list[list[Mark]] = [[] for _ in range(len(edges) - 1)]
    for m in marks:
        u = _u(m)
        s = m.arclength()
        for j in range(len(edges) - 1):
            a, b = edges[j], edges[j + 1]
            k = np.flatnonzero((u >= a) & (u < b))
            if len(k) < 2:
                continue
            lo, hi = k[0], min(k[-1] + 1, len(u) - 1)      # include the boundary point (joints overlap)
            idx = np.arange(lo, hi + 1)
            pts = m.points[idx]
            ch = {c: v[idx] for c, v in m.channels.items()}
            ss = s[idx] - s[idx[0]]
            ch["age"] = ss / max(ss[-1], 1e-9)
            out[j].append(Mark(pts, ch, {**m.meta, "stretch": j}))
    return out


def _tucked(m: Mark, tuck: float) -> Mark | None:
    s = m.arclength()
    if s[-1] <= tuck + 1e-6:
        return None
    return m.remap(np.r_[tuck, s[s > tuck]])


@arranger("series_row", params=[
    P("sheets", "int", 7, "sheets in the row (the frame is the whole row; sheet width = frame W / sheets)",
      min=1, max=12),
    P("at", "floats", [], "progress values (0…1) where the line is handed to the next part"),
    P("inks", "str", "black", "Flexoki ink per part (pen colours for previews), comma list, cycled"),
    P("tuck", "float", 0.0, "mm cut from the start of every stretch after the first (a line that emerges from "
      "a mass starts at its rim, not drawn over it)", min=0.0, max=100.0),
], doc="a row of sheets: part 0's line travels the row; stretches of it go to the next parts")
def series_row(ctx, parts, *, sheets, at, inks, tuck):
    W, H = ctx.frame
    sw = W / sheets
    line = parts[0].run((0.0, 0.0, W, H))
    if len(parts) == 1:
        return line
    stretches = split_at(line, list(at)[: len(parts) - 1])
    out = []
    for j, ms in enumerate(stretches):
        if j > 0 and tuck > 0:
            ms = [_tucked(m, tuck) for m in ms]
            ms = [m for m in ms if m is not None]
        p = parts[min(j + 1, len(parts) - 1)]
        ms = [m.evolve(meta={"part": p.index}) for m in ms]
        if p.spec["voice"]["id"] != "series_stretch" and ms:
            xs = np.concatenate([m.points[:, 0] for m in ms])
            k0, k1 = int(np.clip(np.floor(xs.min() / sw), 0, sheets - 1)), int(np.clip(np.ceil(xs.max() / sw), 1, sheets))
            ins = 0.06 * min(sw, H)
            ms = ms + p.voice((k0 * sw + ins, ins, (k1 - k0) * sw - 2 * ins, H - 2 * ins))
        out += p.modulate(ms, (0.0, 0.0, W, H))
    return out


# ---------------------------------------------------------------------------
# the cut
# ---------------------------------------------------------------------------

def _clip_poly(pts: np.ndarray, x0: float, x1: float, H: float) -> list[np.ndarray]:
    from shapely.geometry import LineString, box  # noqa: PLC0415
    if len(pts) < 2:
        return []
    if pts[:, 0].min() >= x0 and pts[:, 0].max() <= x1:
        return [pts]
    if pts[:, 0].max() < x0 or pts[:, 0].min() > x1:
        return []
    g = LineString(pts).intersection(box(x0, -1e3, x1, H + 1e3))
    if g.is_empty:
        return []
    geoms = getattr(g, "geoms", [g])
    return [np.asarray(q.coords) for q in geoms if q.geom_type == "LineString" and len(q.coords) >= 2]


def _clip_mark(m: Mark, x0: float, x1: float) -> list[Mark]:
    inside = (m.points[:, 0] >= x0) & (m.points[:, 0] <= x1)
    out, k = [], np.flatnonzero(inside)
    if not len(k):
        return out
    runs = np.split(k, np.flatnonzero(np.diff(k) > 1) + 1)
    for r in runs:
        if len(r) >= 2:
            out.append(Mark(m.points[r] - [x0, 0.0], {c: v[r] for c, v in m.channels.items()}, m.meta))
    return out


def cut(strip: Sheet, sheets: int) -> list[Sheet]:
    """The row cut into its sheets (inks clipped to each sheet's rectangle)."""
    W, H = strip.frame
    sw = W / sheets
    out = []
    for k in range(sheets):
        x0, x1 = k * sw, (k + 1) * sw
        inks = []
        for ink in strip.inks:
            for q in _clip_poly(np.asarray(ink.points), x0, x1, H):
                whole = len(q) == len(ink.points)
                inks.append(Ink(q - [x0, 0.0], ink.closed and whole, ink.filled and whole, ink.pen,
                                {**ink.meta, "sheet": k}))
        marks = [mm for m in strip.marks for mm in _clip_mark(m, x0, x1)]
        meta = {**{k_: v for k_, v in strip.meta.items() if k_ != "recipe"},
                "recipe": {"series": strip.recipe, "sheet": k}, "sheet": k, "sheets": sheets}
        out.append(Sheet((sw, H), marks, inks, meta))
    return out


def _sheets_of(recipe: dict) -> int:
    arr = recipe.get("arranger", {})
    return int(arr.get("sheets", 1)) if isinstance(arr, dict) and arr.get("id") == "series_row" else 1


def run_series(recipe: dict) -> tuple[Sheet, list[Sheet]]:
    """(the whole row as one Sheet, its sheets)."""
    strip = kit_run(recipe)
    return strip, cut(strip, _sheets_of(strip.recipe))


def run_sheet(sheet_recipe: dict) -> Sheet:
    """Rebuild one sheet from {"series": recipe, "sheet": k}."""
    _, sheets = run_series(sheet_recipe["series"])
    return sheets[int(sheet_recipe["sheet"])]


def save_sheet_recipe(sheet: Sheet, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sheet.meta["recipe"], indent=1) + "\n")
    return path


# ---------------------------------------------------------------------------
# colour (one pen per part)
# ---------------------------------------------------------------------------

# Flexoki black + 600 accents (axibridge/static/css/flexoki.css)
FLEXOKI = {"black": "#100F0F", "red": "#AF3029", "orange": "#BC5215", "yellow": "#AD8301",
           "green": "#66800B", "cyan": "#24837B", "blue": "#205EA6", "purple": "#5E409D",
           "magenta": "#A02F6F"}


def _rgb(name: str) -> tuple:
    h = FLEXOKI[name.strip()].lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def part_inks(recipe: dict) -> dict[int, tuple]:
    """Part index → RGB from the arranger's `inks` (black when absent)."""
    arr = recipe.get("arranger", {})
    names = [n for n in str(arr.get("inks", "black")).split(",") if n.strip()] or ["black"]
    bad = [n for n in names if n.strip() not in FLEXOKI]
    if bad:
        raise ValueError(f"unknown Flexoki ink(s) {bad}; choose from {sorted(FLEXOKI)}")
    return {i: _rgb(names[i % len(names)]) for i in range(len(recipe.get("parts", [])))}


def render(sheet: Sheet, *, px_per_mm: float = 6.0, ss: int = 2, colours: dict | None = None):
    """PIL image of a sheet (or a row), each part in its pen colour, later
    parts over earlier ones; paper as kit.render_image."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    rec = sheet.recipe.get("series", sheet.recipe)
    cols = colours if colours is not None else part_inks(rec)
    W, H = sheet.frame
    k = px_per_mm * ss
    rgb = np.ones((int(round(H * px_per_mm)), int(round(W * px_per_mm)), 3)) * np.array(PAPER, float)
    for pi in sorted({int(i.meta.get("part", 0)) for i in sheet.inks}):
        im = Image.new("L", (int(round(W * k)), int(round(H * k))), 0)
        dr = ImageDraw.Draw(im)
        for ink in sheet.inks:
            if int(ink.meta.get("part", 0)) != pi:
                continue
            q = np.asarray(ink.points) * k
            d = max(ink.pen * k, 1.0)
            if len(q) >= 2:
                dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
            r = d / 2
            for v in (q if d > 4 else q[[0, -1]]):
                dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
        im = im.resize((rgb.shape[1], rgb.shape[0]), Image.Resampling.BOX)
        a = np.asarray(im, float)[..., None] / 255.0
        rgb = rgb * (1 - a) + np.array(cols.get(pi, INK), float) * a
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


# ---------------------------------------------------------------------------
# showing a set
# ---------------------------------------------------------------------------

WALL = (0xE6, 0xE4, 0xD9)       # Flexoki base-100 (the wall the sheets hang on)
EDGE = (0xCE, 0xCD, 0xC3)       # Flexoki base-200 (a sheet's edge / shadow)


def assemble(images, *, cols: int | None = None, gap: int = 24, pad: int = 40, title: str | None = None,
             numbers: bool = True):
    """Sheet images hung on a wall: one row (cols=None) or a grid, gaps
    between, a hairline edge and a faint drop shadow per sheet, small
    numbers under each sheet."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    n = len(images)
    cols = n if cols is None else cols
    rows = -(-n // cols)
    cw = max(i.width for i in images)
    ch = max(i.height for i in images)
    fs = max(12, int(min(cw, ch) / 22))
    nh = int(fs * 1.8) if numbers else 0
    th = int(fs * 2.4) if title else 0
    Wt = 2 * pad + cols * cw + (cols - 1) * gap
    Ht = 2 * pad + th + rows * (ch + nh) + (rows - 1) * gap
    wall = Image.new("RGB", (Wt, Ht), WALL)
    dr = ImageDraw.Draw(wall)
    if title:
        dr.text((pad, pad // 2), title, fill=(0x57, 0x56, 0x53), font=_font(fs))
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        x = pad + c * (cw + gap)
        y = pad + th + r * (ch + nh + gap)
        dr.rectangle([x + 3, y + 3, x + im.width + 3, y + im.height + 3], fill=EDGE)
        wall.paste(im, (x, y))
        if numbers:
            dr.text((x + im.width // 2 - fs // 3, y + im.height + int(fs * 0.4)), str(i + 1),
                    fill=(0x87, 0x85, 0x80), font=_font(int(fs * 0.8)))
    return wall

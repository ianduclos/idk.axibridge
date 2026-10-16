"""Calligraphy and Arabic-print corpora: manifests, policy filter, sheet
loading and extraction glue (research; see
docs/research/gesture-corpus/calligraphy-arabic.md and typography.md).

**Policy (binding, "Adopted policy" in calligraphy-arabic.md).** Qur'anic
and other devotional text is MEASUREMENT-ONLY: statistics are fine, but it
is never a source of strokes/tokens/segments for generation, restyle or
juxtaposition. Enforced mechanically here from the manifests' content_type:
`generative_allowed(row)` is True only when every base type in content_type
is one of GENERATIVE_TYPES (exercise, poetry, document) AND nothing in
content_type or note says "verify"/"unverified" (unverified = restricted).
`require_generative(ids)` raises PolicyError otherwise; every generator
entry point in experiments/calligraphy_study.py goes through it. Fonts are
shaped with neutral strings only (`NEUTRAL_STRINGS`, checked by
`neutral_string_ok`): letter-repetition joining drills and spaced isolated
letters, never words, never sacred sequences.

Sheets: museum scans carry illuminated borders, gold/coloured inks, cloud
bands and ruled frames (jadval). Each sheet in SHEETS has a hand-picked crop
(fractions of the image, chosen by looking at gridded thumbnails) and an
ink mode: "black" = max(R, G, B) + chroma (black ink stays dark; gold, red,
blue and paper go bright), "lum" = luminance (for blue/red-ink sheets), "white" =
1 − min(R, G, B) (light ink on a dark ground). `remove_rules` then erases
long thin straight lines (frame rulings) before extraction.

Output geometry follows the README contract: points in ORIGINAL pixels of
the CROP (meta records the crop box in the full image).
"""
from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from .core import Drawing, Stroke

Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[3]
CORPUS = REPO / ".local/gesture/corpus"
MANIFESTS = {
    "calligraphy": REPO / "docs/research/gesture-corpus/calligraphy-harvest.csv",
    "print": REPO / "docs/research/gesture-corpus/print-harvest.csv",
}
GENERATIVE_TYPES = frozenset({"exercise", "poetry", "document"})


class PolicyError(RuntimeError):
    """Restricted (measure-only) material reached a generative path."""


# ---------------------------------------------------------------------------
# manifests + policy
# ---------------------------------------------------------------------------

def load_manifest(which: str = "calligraphy") -> dict[str, dict]:
    """id → row of the harvest manifest (`calligraphy` | `print`)."""
    with open(MANIFESTS[which], newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def base_types(content_type: str) -> set[str]:
    """'exercise + poetry' → {exercise, poetry}; parentheticals dropped
    ('document (petition)' → {document})."""
    ct = re.sub(r"\([^)]*\)", " ", content_type or "").lower()
    parts = re.split(r"[+/,;]| and ", ct)
    return {p.strip() for p in parts if p.strip()}


def generative_allowed(row: dict) -> bool:
    """True only for secular exercise/poetry/document rows with nothing
    flagged for verification. Anything else (qur'an, devotional, album page,
    book, font, diagram, tughra, '(verify)', unverified notes) is
    measure-only."""
    ct = (row.get("content_type") or "").lower()
    note = (row.get("note") or "").lower()
    if "verif" in ct or "verif" in note:
        return False
    if any(w in ct for w in ("qur", "koran", "devotional", "sacred", "hadith", "prayer")):
        return False
    bt = base_types(ct)
    return bool(bt) and bt <= GENERATIVE_TYPES


def require_generative(ids, manifest: dict[str, dict] | None = None) -> list[str]:
    """Gate for every generative use: returns ids unchanged or raises
    PolicyError naming the restricted ones (unknown ids are restricted)."""
    man = manifest if manifest is not None else {**load_manifest("print"), **load_manifest("calligraphy")}
    ids = list(ids)
    bad = [i for i in ids if _manifest_id(i) not in man or not generative_allowed(man[_manifest_id(i)])]
    if bad:
        raise PolicyError(f"measure-only material in a generative path: {bad}")
    return ids


def _manifest_id(sheet_id: str) -> str:
    """Sheet ids may carry a sub-crop suffix ('met-716304#b')."""
    return SHEETS.get(sheet_id, {}).get("mid", sheet_id.split("#")[0])


def filter_generative(drawings: dict, manifest: dict[str, dict] | None = None) -> dict:
    """Keep only the drawings whose sheet id is generative-allowed."""
    man = manifest if manifest is not None else {**load_manifest("print"), **load_manifest("calligraphy")}
    return {k: v for k, v in drawings.items()
            if _manifest_id(k) in man and generative_allowed(man[_manifest_id(k)])}


# ---------------------------------------------------------------------------
# sheets: crop + ink mode + genre (crops picked from gridded thumbnails)
# ---------------------------------------------------------------------------

# genre keys: naskh, nastaliq, shikasta, karalama, diwani, tughra, maghribi,
# kufic, ghubar, baghdadi (model-book plates, genre per plate unverified)
SHEETS: dict[str, dict] = {
    "cma-1945.383.b": {"genre": "naskh", "crop": (0.12, 0.03, 0.95, 0.85), "ink": "black"},
    "cma-1977.91.a": {"genre": "naskh", "crop": (0.15, 0.03, 0.95, 0.92), "ink": "black"},
    "cma-1983.1115.a": {"genre": "nastaliq", "crop": (0.72, 0.20, 0.88, 0.82), "ink": "black"},
    "met-449533": {"genre": "tughra", "crop": (0.05, 0.08, 0.97, 0.75), "ink": "lum"},
    "met-450713": {"genre": "nastaliq", "crop": (0.30, 0.30, 0.70, 0.73), "ink": "black"},
    "met-450714": {"genre": "shikasta", "crop": (0.07, 0.18, 0.91, 0.68), "ink": "black"},
    "met-451802": {"genre": "kufic", "crop": (0.12, 0.08, 0.88, 0.92), "ink": "black"},
    "met-665823": {"genre": "ghubar", "crop": (0.04, 0.12, 0.97, 0.93), "ink": "lum"},
    "met-716304": {"genre": "nastaliq", "crop": (0.11, 0.09, 0.70, 0.40), "ink": "black"},
    "met-716305": {"genre": "nastaliq", "crop": (0.19, 0.25, 0.68, 0.80), "ink": "black"},
    "met-716307": {"genre": "nastaliq", "crop": (0.18, 0.15, 0.84, 0.86), "ink": "black"},
    "met-716315": {"genre": "shikasta", "crop": (0.30, 0.25, 0.72, 0.85), "ink": "lum"},
    "wal-W668-66b": {"genre": "nastaliq", "crop": (0.25, 0.24, 0.80, 0.86), "ink": "black"},
    "wal-W668-74b": {"genre": "nastaliq", "crop": (0.07, 0.04, 0.87, 0.94), "ink": "black"},
    "wal-W672-5b": {"genre": "karalama", "crop": (0.22, 0.18, 0.78, 0.80), "ink": "black"},
    "wal-W672-6a": {"genre": "karalama", "crop": (0.30, 0.22, 0.70, 0.78), "ink": "black"},
    "wc-05": {"genre": "diwani", "crop": (0.02, 0.28, 0.98, 0.96), "ink": "black"},
    "wc-06": {"genre": "tughra", "crop": (0.10, 0.18, 0.95, 0.60), "ink": "lum"},
    "wc-10": {"genre": "shikasta", "crop": (0.22, 0.10, 0.83, 0.86), "ink": "black"},
    "wc-12": {"genre": "shikasta", "crop": (0.11, 0.17, 0.88, 0.80), "ink": "black"},
    "wc-13": {"genre": "shikasta", "crop": (0.06, 0.13, 0.95, 0.86), "ink": "black"},
    "wc-15": {"genre": "shikasta", "crop": (0.08, 0.10, 0.92, 0.92), "ink": "black"},
    "wc-17": {"genre": "shikasta", "crop": (0.08, 0.07, 0.90, 0.93), "ink": "black"},
    "wc-19": {"genre": "nastaliq", "crop": (0.22, 0.52, 0.70, 0.85), "ink": "black"},
    "wc-22": {"genre": "nastaliq", "crop": (0.12, 0.15, 0.42, 0.82), "ink": "black"},
    "wc-24": {"genre": "nastaliq", "crop": (0.18, 0.20, 0.85, 0.85), "ink": "black"},
    "wc-30": {"genre": "maghribi", "crop": (0.15, 0.36, 0.95, 0.80), "ink": "black"},
    "wc-32": {"genre": "maghribi", "crop": (0.42, 0.15, 0.92, 0.78), "ink": "lum"},
    "wc-33": {"genre": "maghribi", "crop": (0.05, 0.12, 0.98, 0.97), "ink": "black"},
    "wc-35": {"genre": "kufic", "crop": (0.12, 0.10, 0.88, 0.92), "ink": "lum"},
    "wc-37": {"genre": "kufic", "crop": (0.10, 0.05, 0.42, 0.50), "ink": "lum"},
    "wc-39": {"genre": "diwani", "crop": (0.08, 0.12, 0.92, 0.72), "ink": "white"},
}
# Baghdadi model-book plates (low-res PDF, ~1140 px pages); per-plate genre
# unverified, and the manifest note flags unverified religious phrases, so
# the whole book is measure-only.
BAGHDADI_PAGES = {15: "letters (pl. 5)", 21: "letters + nuqta (pl. 8)",
                  83: "joins + numerals (pl. 20)", 101: "running text (pl. 48)"}
for _p, _lab in BAGHDADI_PAGES.items():
    SHEETS[f"nyu-baghdadi#p{_p}"] = {"genre": "baghdadi", "crop": (0.10, 0.12, 0.90, 0.86),
                                     "ink": "black", "mid": "nyu-baghdadi", "page": _p, "label": _lab}


def sheet_path(sheet_id: str) -> Path:
    mid = _manifest_id(sheet_id)
    row = {**load_manifest("print"), **load_manifest("calligraphy")}[mid]
    return CORPUS / row["file"]


def to_gray(rgb: np.ndarray, ink: str = "black") -> np.ndarray:
    """RGB uint8/float → float gray in [0, 1], ink dark (see module doc)."""
    a = np.asarray(rgb, dtype=np.float64)
    if a.max() > 1.0:
        a = a / 255.0
    if a.ndim == 2:
        return 1.0 - a if ink == "white" else a
    a = a[..., :3]
    if ink == "black":
        mx, mn = a.max(axis=2), a.min(axis=2)
        return np.minimum(mx + (mx - mn), 1.0)      # chroma pushes gold/colour to paper
    if ink == "lum":
        return a @ np.array([0.299, 0.587, 0.114])
    if ink == "white":
        return 1.0 - a.min(axis=2)
    raise ValueError(ink)


def render_pdf_page(pdf: Path, page: int, out_dir: Path, dpi: int = 96) -> Path:
    """Extract one PDF page as an image: the embedded raster (pdfimages,
    native resolution) when poppler is present, else pdftoppm at `dpi`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"p{page:04d}"
    hits = sorted(out_dir.glob(f"p{page:04d}-*.jpg")) + sorted(out_dir.glob(f"p{page:04d}*.png"))
    if hits:
        return hits[0]
    try:
        subprocess.run(["pdfimages", "-j", "-f", str(page), "-l", str(page), str(pdf), str(stem)],
                       check=True, capture_output=True)
        hits = sorted(out_dir.glob(f"p{page:04d}-*.jpg"))
        if hits:
            return hits[0]
    except (OSError, subprocess.CalledProcessError):
        pass
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png",
                    str(pdf), str(stem)], check=True, capture_output=True)
    return sorted(out_dir.glob(f"p{page:04d}*.png"))[0]


def load_sheet(sheet_id: str, *, max_side: int | None = 3000, crop=None, ink: str | None = None,
               cache: Path | None = None) -> tuple[np.ndarray, float, dict]:
    """→ (gray working raster of the crop, scale = working/original px,
    info {crop_px, size (crop original w, h), ink, path})."""
    cfg = SHEETS.get(sheet_id, {})
    path = sheet_path(sheet_id)
    if path.suffix.lower() == ".pdf":
        path = render_pdf_page(path, cfg["page"], cache or (REPO / ".local/gesture/out/calligraphy/pdfpages"))
    with Image.open(path) as im:
        im = im.convert("RGB")
        Wf, Hf = im.size
        c = crop or cfg.get("crop", (0, 0, 1, 1))
        box = (int(c[0] * Wf), int(c[1] * Hf), int(c[2] * Wf), int(c[3] * Hf))
        im = im.crop(box)
        size = im.size
        s = 1.0
        if max_side and max(size) > max_side:
            s = max_side / max(size)
            im = im.resize((max(1, round(size[0] * s)), max(1, round(size[1] * s))), Image.Resampling.BOX)
            s = 0.5 * (im.size[0] / size[0] + im.size[1] / size[1])
        rgb = np.asarray(im)
    g = to_gray(rgb, ink or cfg.get("ink", "black"))
    return g, s, {"crop_px": box, "size": size, "ink": ink or cfg.get("ink", "black"), "path": str(path),
                  "full_size": (Wf, Hf)}


def remove_rules(gray: np.ndarray, *, min_frac: float = 0.25, max_thick_frac: float = 0.006,
                 dark_frac: float = 0.5, isolation: float = 0.15) -> tuple[np.ndarray, int]:
    """Erase long thin straight horizontal/vertical lines (frame rulings,
    jadval): binarise at an Otsu threshold, open with a 1-px line of length
    min_frac·side, keep opened components thinner than max_thick_frac·diag,
    dilate by 2 px and paint them with the local paper level. Returns
    (new gray, number of lines erased). Calligraphic strokes survive: they
    are curved or tapered, so they never hold a long thin straight run."""
    from skimage.filters import threshold_otsu

    g = np.asarray(gray, dtype=np.float64)
    H, W = g.shape
    try:
        t = threshold_otsu(g)
    except ValueError:
        return g.copy(), 0
    ink = g < (t * dark_frac + (1 - dark_frac) * float(np.median(g))) if dark_frac < 1 else g < t
    diag = float(np.hypot(H, W))
    thick = max(2.0, max_thick_frac * diag)
    found = np.zeros_like(ink)
    n = 0
    for horiz in (True, False):
        L = int(min_frac * (W if horiz else H))
        if L < 10:
            continue
        se = np.ones((1, L), bool) if horiz else np.ones((L, 1), bool)
        op = ndi.binary_opening(ink, structure=se)
        lab, k = ndi.label(op)
        if k == 0:
            continue
        for sl_i, sl in enumerate(ndi.find_objects(lab), start=1):
            hh = sl[0].stop - sl[0].start
            ww = sl[1].stop - sl[1].start
            th = hh if horiz else ww
            if th > thick:
                continue
            # isolation: a ruling stands alone; a straight slice of a thick
            # stroke has ink right beside it
            pad = int(3 * thick) + 2
            r0, r1 = max(sl[0].start - (pad if horiz else 0), 0), min(sl[0].stop + (pad if horiz else 0), H)
            c0, c1 = max(sl[1].start - (0 if horiz else pad), 0), min(sl[1].stop + (0 if horiz else pad), W)
            comp = np.zeros((r1 - r0, c1 - c0), bool)
            comp[sl[0].start - r0:sl[0].stop - r0, sl[1].start - c0:sl[1].stop - c0] = lab[sl] == sl_i
            comp = ndi.binary_dilation(comp, iterations=2)
            around = ink[r0:r1, c0:c1] & ~comp
            if around.mean() > isolation:
                continue
            found[sl] |= lab[sl] == sl_i
            n += 1
    if not n:
        return g.copy(), 0
    found = ndi.binary_dilation(found, iterations=2)
    paper = ndi.median_filter(np.where(found, np.nan_to_num(np.median(g)), g), size=15)
    out = g.copy()
    out[found] = np.maximum(paper[found], float(np.percentile(g, 75)))
    return out, n


# extractor settings for broad-nib ribbons: global Otsu on the ink-mode gray
# (the hysteresis noise model assumes sparse lines; calligraphy covers 10-35 %
# of a panel and its noise estimate swallows the ink). If hysteresis is used,
# the local paper level must be
# estimated over a window wider than the thickest stroke (the default 1.5 %
# of the diagonal sits INSIDE a reed-pen downstroke and reads it as paper),
# terminal wedges need a longer spur cut, and there are no plate marks.
EXTRACT_DEFAULTS = {"method": "otsu", "paper_window_frac": 0.08, "spur_factor": 2.5, "crop_to_plate": False,
                    "drop_frames": False}


def extract_sheet(sheet_id: str, *, max_side: int | None = 3000, rules: bool = True,
                  extract_kw: dict | None = None, **load_kw) -> tuple[Drawing, np.ndarray]:
    """Crop → ink gray → rule removal → extract_hybrid. Returns (Drawing in
    crop ORIGINAL px, the working gray used)."""
    from . import extract_hybrid

    g, s, info = load_sheet(sheet_id, max_side=max_side, **load_kw)
    n_rules = 0
    if rules:
        g, n_rules = remove_rules(g)
    kw = dict(EXTRACT_DEFAULTS)
    kw.update(extract_kw or {})
    d = extract_hybrid.extract(g, scale=s, source=sheet_id, original_size=info["size"], **kw)
    meta = dict(d.meta)
    meta.update({"sheet": sheet_id, "genre": SHEETS.get(sheet_id, {}).get("genre", ""),
                 "crop_px": info["crop_px"], "ink_mode": info["ink"], "rules_erased": n_rules,
                 "scale": s})
    return Drawing(d.strokes, source=sheet_id, size=d.size, meta=meta), g


# ---------------------------------------------------------------------------
# the outline view: closed contours of the ink
# ---------------------------------------------------------------------------

def ink_mask(gray: np.ndarray, **params) -> tuple[np.ndarray, float]:
    """The extractor's own ink mask (same binarisation as the centreline
    view) and its initial width estimate, working px."""
    from . import extract as ex

    p = ex.ExtractParams().resolved(**params)
    mask, info = ex._binarize(np.asarray(gray, dtype=np.float64), p, None, 0.0)
    return mask, float(info["w_initial"])


def outlines(gray: np.ndarray, *, scale: float = 1.0, min_area_w2: float = 3.0, smooth_px: float = 0.7,
             source: str = "", original_size=None, mask: np.ndarray | None = None,
             params: dict | None = None, w_px: float | None = None) -> Drawing:
    """Closed contours of the ink mask as closed Strokes (ORIGINAL px).
    meta["hole"] marks inner contours (counters); meta["area_w2"] = enclosed
    area in squared line widths. Contours are traced at the 0.5 level of the
    lightly blurred mask (sub-pixel). Default mask: the calligraphy
    extractor's (EXTRACT_DEFAULTS); `params` overrides (e.g. {} for the
    default hysteresis on print), or pass a ready `mask` (+ its `w_px`)."""
    from skimage import measure

    if mask is None:
        mask, w0 = ink_mask(gray, **(EXTRACT_DEFAULTS if params is None else params))
    else:
        w0 = 3.0 if w_px is None else float(w_px)
    m = ndi.gaussian_filter(mask.astype(np.float64), smooth_px) if smooth_px > 0 else mask.astype(float)
    m = np.pad(m, 1)
    strokes = []
    for c in measure.find_contours(m, 0.5):
        rc = c - 1.0
        if len(rc) < 8:
            continue
        xy = rc[:, ::-1]
        if np.allclose(xy[0], xy[-1]):
            xy = xy[:-1]
        x, y = xy[:, 0], xy[:, 1]
        area = 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
        if abs(area) < min_area_w2 * w0 * w0:
            continue
        pts = (xy + 0.5) / scale - 0.5
        # find_contours on a mask with ink = 1 traces outer boundaries with a
        # positive (x, y) shoelace area and counters with a negative one
        strokes.append(Stroke(pts, closed=True,
                              meta={"hole": bool(area < 0), "area_w2": abs(area) / (w0 * w0)}))
    size = original_size or (int(round(gray.shape[1] / scale)), int(round(gray.shape[0] / scale)))
    return Drawing(strokes, source=source, size=tuple(size),
                   meta={"view": "outline", "line_width_px": w0 / scale})


# ---------------------------------------------------------------------------
# fonts: neutral strings only
# ---------------------------------------------------------------------------

# joining drills (one letter repeated: medial forms) + spaced isolated
# letters in abjad order. No words, no lam–heh sequences, no ligature
# code points.
NEUTRAL_STRINGS = [
    "ببببب سسسسس ممممم ععععع",
    "ففففف ككككك ححححح ططططط",
    "صصصصص ققققق ننننن ييييي",
    "ههههه ججججج ششششش ضضضضض",
    "ا ب ج د ه و ز ح ط ي ك",
    "ل م ن س ع ف ص ق ر ش ت",
    "ث خ ذ ض ظ غ",
    "تتتتت ثثثثث غغغغغ ظظظظظ",
]
_BLACKLIST = ("الله", "لله", "ﷲ", "ﷺ", "ﷻ", "﷽")


def neutral_string_ok(s: str) -> bool:
    """Reject sacred sequences and ligature code points; require every word
    to be a single repeated letter or a single letter (no words possible)."""
    if any(b in s for b in _BLACKLIST):
        return False
    if re.search("ل[ً-ْ]*ه", s):
        return False
    for w in s.split():
        if len(set(w)) != 1:
            return False
    return True


def _flatten_pen(glyphset):
    from fontTools.pens.basePen import BasePen

    class FlatPen(BasePen):
        def __init__(self):
            super().__init__(glyphset)
            self.contours: list[list] = []
            self.cur: list = []

        def _moveTo(self, p):
            self.cur = [p]

        def _lineTo(self, p):
            self.cur.append(p)

        def _curveToOne(self, p1, p2, p3):
            p0 = np.array(self.cur[-1], float)
            t = np.linspace(0, 1, 9)[1:, None]
            a, b, c = np.array(p1, float), np.array(p2, float), np.array(p3, float)
            pts = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t ** 2 * b + t ** 3 * c
            self.cur += [tuple(v) for v in pts]

        def _qCurveToOne(self, p1, p2):
            p0 = np.array(self.cur[-1], float)
            t = np.linspace(0, 1, 7)[1:, None]
            a, b = np.array(p1, float), np.array(p2, float)
            pts = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * a + t ** 2 * b
            self.cur += [tuple(v) for v in pts]

        def _closePath(self):
            if len(self.cur) >= 3:
                self.contours.append(self.cur)
            self.cur = []

        _endPath = _closePath

    return FlatPen()


def shape_text(font_path: Path, text: str, *, variations: dict | None = None) -> list[np.ndarray]:
    """HarfBuzz-shaped text → flattened glyph contours in font units
    (y up, pen origin at 0). Raises ValueError for non-neutral text."""
    import uharfbuzz as hb
    from fontTools.ttLib import TTFont

    if not neutral_string_ok(text):
        raise ValueError(f"not a neutral string: {text!r}")
    blob = hb.Blob.from_file_path(str(font_path))
    face = hb.Face(blob)
    font = hb.Font(face)
    if variations:
        font.set_variations(variations)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {})
    tt = TTFont(str(font_path))
    gs = tt.getGlyphSet(location=variations) if variations else tt.getGlyphSet()
    order = tt.getGlyphOrder()
    x = 0.0
    out = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        name = order[info.codepoint]
        pen = _flatten_pen(gs)
        gs[name].draw(pen)
        for c in pen.contours:
            a = np.asarray(c, float)
            a[:, 0] += x + pos.x_offset
            a[:, 1] += pos.y_offset
            out.append(a)
        x += pos.x_advance
    return out


def render_font_lines(font_path: Path, lines: list[str], *, px_per_em: float = 80.0,
                      line_gap: float = 1.6, margin: float = 0.5, variations: dict | None = None,
                      ss: int = 3) -> tuple[np.ndarray, list]:
    """Neutral lines set right-aligned (RTL) one under another → anti-aliased
    gray raster (paper 1, ink 0) + the shapely geometry per line in px.
    Contours are combined as union(outer) − counters, by nesting depth."""
    from fontTools.ttLib import TTFont
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from .broadnib import render_mask

    upem = TTFont(str(font_path))["head"].unitsPerEm
    s = px_per_em / upem
    geoms = []
    widths = []
    for ln in lines:
        cs = shape_text(font_path, ln, variations=variations)
        polys = []
        for c in cs:
            if len(c) < 3:
                continue
            p = Polygon(c * s)
            if not p.is_valid:
                p = p.buffer(0)
            if not p.is_empty and p.area > 0:
                polys.append(p)
        # nesting depth decides outer vs counter (orientation-free, so
        # TrueType and CFF fonts both work; overlapping outers union)
        outer, holes = [], []
        for i, p in enumerate(polys):
            pt = p.representative_point()
            depth = sum(1 for j, q in enumerate(polys) if j != i and q.contains(pt) and q.area > p.area)
            (holes if depth % 2 else outer).append(p)
        g = unary_union(outer)
        if holes:
            g = g.difference(unary_union(holes))
        geoms.append(g)
        widths.append(g.bounds)
    Wmax = max(b[2] - b[0] for b in widths)
    m = margin * px_per_em
    H = int(m * 2 + line_gap * px_per_em * len(lines))
    Wd = int(Wmax + 2 * m)
    from shapely import affinity
    placed = []
    for i, (g, b) in enumerate(zip(geoms, widths)):
        y0 = m + (i + 0.8) * line_gap * px_per_em
        gg = affinity.scale(g, 1, -1, origin=(0, 0))           # y down
        gg = affinity.translate(gg, Wd - m - b[2], y0)          # right-aligned
        placed.append(gg)
    return render_mask(placed, (Wd, H), ss=ss), placed


def dominant_direction(drawing: Drawing, *, kappa: float = 8.0, sigma_w: float = 2.0) -> float:
    """Length-weighted mode of stroke tangent page angle (deg, [0, 180)) —
    a baseline proxy: in every genre here the long sweeps run along the
    writing line, so a sheet written diagonally (album qit'a) or rotated
    (siyah mashq panels) reports its own baseline. Doubled-angle von Mises
    kernel density, mode on a 1° grid."""
    from .broadnib import page_angle

    th, wt = [], []
    for st in drawing.strokes:
        if len(st) < 4:
            continue
        w = float(np.median(st.width)) if st.width is not None else 2.0
        t = page_angle(st.points, sigma=sigma_w * w)
        d = np.linalg.norm(np.diff(st.points, axis=0), axis=1)
        th.append(t[1:]); wt.append(d)
    if not th:
        return float("nan")
    th, wt = np.concatenate(th), np.concatenate(wt)
    grid = np.deg2rad(np.arange(0, 180, 1.0))
    dens = np.exp(kappa * np.cos(2 * (th[None, :] - grid[:, None]))) @ wt
    return float(np.rad2deg(grid[int(np.argmax(dens))]))


def pen_strokes(drawing: Drawing, *, min_rel_width: float = 0.4, border_frac: float = 0.03) -> Drawing:
    """The strokes of the HAND: drops hairline strokes thinner than
    min_rel_width × the ink-weighted 75th-percentile stroke width
    (illumination outlines, cloud-band borders, ruling remnants) and strokes
    reaching within border_frac of the crop edge (frames)."""
    sts = [s for s in drawing.strokes if s.width is not None and len(s) >= 2]
    if not sts:
        return Drawing([], source=drawing.source, size=drawing.size, meta=dict(drawing.meta))
    v = np.array([float(np.median(s.width)) for s in sts])
    L = np.array([s.length() for s in sts])
    o = np.argsort(v)
    c = np.cumsum(L[o]) / max(L.sum(), 1e-9)
    floor = min_rel_width * float(v[o][min(np.searchsorted(c, 0.75), len(v) - 1)])
    Wd, Hd = drawing.size
    m = border_frac * max(Wd, Hd)
    keep = []
    for s, w in zip(sts, v):
        p = s.points
        if w < floor:
            continue
        if Wd and (p[:, 0].min() < m or p[:, 1].min() < m or p[:, 0].max() > Wd - m or p[:, 1].max() > Hd - m):
            continue
        keep.append(s)
    meta = dict(drawing.meta)
    meta["pen_strokes"] = {"kept": len(keep), "of": len(drawing.strokes), "width_floor": floor}
    return Drawing(keep, source=drawing.source, size=drawing.size, meta=meta)

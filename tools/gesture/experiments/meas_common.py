"""Thread D (`meas`, round 15): shared helpers for the device experiments:
the test drawings (round-14 keepers rebuilt from their recipes, and the
catalogue drawing), a colour render that reads Ink.meta["colour"] (Flexoki
names or hex), and the image budget (<= 2400 px, < 400 KB)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "gesture"))

import numpy as np  # noqa: E402

from gesture import kit  # noqa: E402
from gesture.kit.arrangers_ccolour import FLEXOKI  # noqa: E402
from gesture.kit.core import PAPER  # noqa: E402

RESULTS = ROOT / "tools" / "gesture" / "results"
OUT = ROOT / ".local" / "gesture" / "out" / "meas"


def round14(name: str):
    """A round-14 keeper rebuilt from the recipe beside its image."""
    rec = json.loads((RESULTS / f"{name}.recipe.json").read_text())
    if "panels" in rec:
        rec = rec["panels"][0]
    return kit.run(rec)


def catalogue_recipe(seed: int = 15310) -> dict:
    """The catalogue drawing: a free-course river_zoom push across the middle
    (Ian's favourite resource, constant width), a drift through three corpora
    (trail, dance, artist) above it, a dance drawn with its own clock to the
    right, a fly walk low left. Middle density; the score records what the
    geometry did between them (meas_boxes)."""
    return {
        "label": f"meas catalogue drawing {seed}", "frame": [267.0, 180.0], "seed": seed, "margin": 10.0,
        "arranger": {"id": "meas_boxes", "roles": "found,line,line,line",
                     "boxes": [0.0, 0.30, 1.0, 0.42,
                               0.04, 0.0, 0.52, 0.60,
                               0.58, 0.02, 0.40, 0.62,
                               0.10, 0.62, 0.34, 0.38]},
        "parts": [
            {"voice": {"id": "river_zoom", "schedule": "push", "recur": 3, "zoom": 24.0, "course": "free",
                       "pace": 0.5}, "renderer": {"id": "meas_ink", "pen": 0.3, "ink": "blue"}},
            {"voice": {"id": "drift", "hands": ["trail_miner", "dance_staccato", "meander69"], "length": 5.0,
                       "joins": "smooth"}, "renderer": {"id": "meas_ink", "pen": 0.35, "ink": "black"}},
            {"voice": {"id": "dance", "trail": "levitation", "effectors": "hands+head", "seconds": 14.0},
             "renderer": {"id": "meas_ink", "pen": 0.3, "ink": "orange"}},
            {"voice": {"id": "hand", "hand": "fly_open", "length": 1.6},
             "renderer": {"id": "meas_ink", "pen": 0.3, "ink": "black"}},
        ],
    }


def _hex(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def colour_of(c) -> np.ndarray:
    c = str(c or "black")
    if c.startswith("#"):
        return _hex(c)
    return _hex(FLEXOKI.get(c, FLEXOKI["black"]))


def render(sheet, *, px_per_mm: float = 6.0, ss: int = 2):
    """Inks at their pen width in their own colour, multiplied like inks."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    W, H = sheet.frame
    k = px_per_mm * ss
    size = (int(round(W * k)), int(round(H * k)))
    out_size = (size[0] // ss, size[1] // ss)
    rgb = np.ones((out_size[1], out_size[0], 3)) * np.array(PAPER, float)
    names = []
    for ink in sheet.inks:
        c = str((ink.meta or {}).get("colour") or "black")
        if c not in names:
            names.append(c)
    for c in names:
        im = Image.new("L", size, 0)
        dr = ImageDraw.Draw(im)
        for ink in sheet.inks:
            if str((ink.meta or {}).get("colour") or "black") != c or len(ink.points) < 2:
                continue
            q = ink.points * k
            d = max(ink.pen * k, 1.0)
            dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
            r = d / 2
            for v in q[[0, -1]]:
                dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
        im = im.resize(out_size, Image.Resampling.BOX)
        a = np.asarray(im, float)[..., None] / 255.0 * 0.94
        pen = colour_of(c) / 255.0
        rgb = rgb * (1 - a * (1 - pen))
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def caption(im, text: str, *, fs: int | None = None):
    from PIL import Image, ImageDraw  # noqa: PLC0415
    from gesture.kit.core import INK, _font  # noqa: PLC0415
    fs = fs or max(14, int(im.width / 85))
    strip = Image.new("RGB", (im.width, int(fs * 2.0)), PAPER)
    ImageDraw.Draw(strip).text((int(fs * 0.6), int(fs * 0.45)), text, fill=INK, font=_font(fs))
    full = Image.new("RGB", (im.width, im.height + strip.height), PAPER)
    full.paste(im, (0, 0))
    full.paste(strip, (0, im.height))
    return full


def save_budget(im, path, *, long_side: int = 2400, budget: int = 395_000):
    """JPEG <= long_side px and < budget bytes (quality stepped down)."""
    from PIL import Image  # noqa: PLC0415
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    s = min(1.0, long_side / max(im.size))
    if s < 1.0:
        im = im.resize((int(im.width * s), int(im.height * s)), Image.Resampling.LANCZOS)
    for q in (90, 86, 82, 78, 74, 70, 65, 60, 55):
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < budget:
            break
    return path


def save_spec(path, spec: dict):
    Path(path).with_suffix(".recipe.json").write_text(json.dumps(spec, indent=1, default=str) + "\n")


def quartet_recipe(seed: int = 15500) -> dict:
    """Four hands from four corpora on one surface, each in its own ink, in
    overlapping boxes: a drawing whose lines differ by how they turn (the
    meas_turning pairing)."""
    hands = [("river_oxbow", "blue", 2.4), ("trail_miner", "orange", 2.6), ("fly_open", "black", 1.4),
             ("mime_mantis", "red", 2.0)]
    boxes = [0.0, 0.05, 0.62, 0.9, 0.30, 0.0, 0.70, 0.75, 0.12, 0.35, 0.5, 0.65, 0.55, 0.30, 0.45, 0.7]
    return {"label": f"meas quartet {seed}", "frame": [267.0, 180.0], "seed": seed, "margin": 10.0,
            "arranger": {"id": "meas_boxes", "boxes": boxes},
            "parts": [{"voice": {"id": "hand", "hand": h, "length": L},
                       "renderer": {"id": "meas_ink", "pen": 0.35, "ink": ink}} for h, ink, L in hands]}

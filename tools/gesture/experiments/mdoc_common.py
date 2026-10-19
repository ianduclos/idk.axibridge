"""Round 16 thread D (`mdoc`): shared helpers for the process-document
experiments: the test scores (v2) and the round-15 keepers (v1, from their
study recipes), and the image budget (<= 2400 px, < 400 KB)."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "gesture"))

from gesture import kit  # noqa: E402
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit._devices import apply_devices  # noqa: E402

RESULTS = ROOT / "tools" / "gesture" / "results"
OUT = ROOT / ".local" / "gesture" / "out" / "mdoc"
STUDIES = ROOT / "axibridge" / "sources" / "_gesture_studies" / "studies"


def study_recipe(name: str, seed: int | None = None) -> dict:
    rec = dict(json.loads((STUDIES / name / "study.json").read_text())["recipe"])
    rec.pop("kit", None)
    if seed is not None:
        rec["seed"] = int(seed)
    return rec


def listen_composer() -> dict:
    """listen 15102's arranger + parts, as a composer layer (frame/seed come from the score)."""
    rec = study_recipe("listen")
    return {k: copy.deepcopy(v) for k, v in rec.items() if k not in ("frame", "seed", "margin")}


def save(sheet, path: Path, *, label: str | None = None, extra: dict | None = None, px_per_mm: float = 6.0,
         max_px: int = 2400, max_kb: int = 395) -> Path:
    """Colour image (ccolour render_pens), JPEG within budget, the score or
    recipe beside it (<stem>.recipe.json; v2 sheets also <stem>.played.json)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    W, H = sheet.frame
    k = min(px_per_mm, max_px / max(W, H))
    from gesture.kit.arrangers_ccolour import render_pens  # noqa: PLC0415
    im = render_pens(sheet, px_per_mm=k, grain=False)
    q = 90
    while True:
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < max_kb * 1024 or q <= 50:
            break
        q -= 6
    pl = synth.played(sheet)
    if pl and pl.get("version") == 2:
        spec = {"score": pl["written"], "devices": sheet.meta.get("devices", [])}
        path.with_suffix(".played.json").write_text(
            json.dumps({k: v for k, v in pl.items() if k != "written"}, indent=1, default=float))
    else:
        spec = {"recipe": sheet.meta["recipe"], "devices": sheet.meta.get("devices", [])}
    if extra:
        spec.update(extra)
    if label:
        spec["label"] = label
    path.with_suffix(".recipe.json").write_text(json.dumps(spec, indent=1, default=float))
    return path

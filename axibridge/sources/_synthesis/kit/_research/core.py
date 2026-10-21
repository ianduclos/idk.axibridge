# FROZEN from research commit 6f96418: tools/gesture/gesture/core.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Shared data types for the gesture-bank research code (see ../README.md)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Stroke:
    points: np.ndarray                 # (N, 2) float64, ordered, pixels
    width: np.ndarray | None = None    # (N,) float64, full width, pixels
    closed: bool = False               # closed strokes do not repeat point 0
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        pts = np.asarray(self.points, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != 2:
            raise ValueError(f"points must be (N, 2), got {pts.shape}")
        object.__setattr__(self, "points", pts)
        if self.width is not None:
            w = np.asarray(self.width, dtype=np.float64)
            if w.shape != (len(pts),):
                raise ValueError("width must be (N,) matching points")
            object.__setattr__(self, "width", w)

    def __len__(self) -> int:
        return len(self.points)

    def length(self) -> float:
        p = self.points
        if self.closed and len(p) > 1:
            p = np.vstack([p, p[:1]])
        return float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)))

    def to_json(self) -> dict:
        return {
            "points": self.points.round(3).tolist(),
            "width": None if self.width is None else self.width.round(3).tolist(),
            "closed": self.closed,
            "meta": self.meta,
        }

    @staticmethod
    def from_json(d: dict) -> "Stroke":
        return Stroke(
            points=np.array(d["points"], dtype=np.float64).reshape(-1, 2),
            width=None if d.get("width") is None else np.array(d["width"], dtype=np.float64),
            closed=bool(d.get("closed", False)),
            meta=dict(d.get("meta", {})),
        )


@dataclass(frozen=True)
class Drawing:
    strokes: list[Stroke]
    source: str = ""
    size: tuple[int, int] = (0, 0)     # (width_px, height_px) of the canvas/scan
    meta: dict = field(default_factory=dict)

    def ref_length(self) -> float:
        """Bounding-box diagonal of all stroke points: the unit that makes
        scale-dependent statistics comparable across drawings."""
        pts = [s.points for s in self.strokes if len(s)]
        if not pts:
            return 1.0
        allp = np.vstack(pts)
        span = allp.max(axis=0) - allp.min(axis=0)
        return float(max(np.hypot(*span), 1e-9))

    def to_json(self) -> dict:
        return {
            "source": self.source,
            "size": list(self.size),
            "meta": self.meta,
            "strokes": [s.to_json() for s in self.strokes],
        }

    @staticmethod
    def from_json(d: dict) -> "Drawing":
        return Drawing(
            strokes=[Stroke.from_json(s) for s in d["strokes"]],
            source=d.get("source", ""),
            size=tuple(d.get("size", (0, 0))),
            meta=dict(d.get("meta", {})),
        )

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_json()))

    @staticmethod
    def load(path: str | Path) -> "Drawing":
        return Drawing.from_json(json.loads(Path(path).read_text()))

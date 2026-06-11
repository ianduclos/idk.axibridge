"""Machine-level persistent stores: the global pen library and settings.

Both live outside any project, in ``~/.axibridge/`` — the pen library is the
user's physical pen drawer (shared across projects), and settings are
properties of the machine/holder (calibration, estimator constants), not of
an artwork. Projects *snapshot* the pens they use so a moved project folder
still knows what drew it; the library remains the editable source of truth.

Writes are atomic (tmp + rename) so a crash mid-save can't truncate the
library, and guarded by a lock because API handlers run in a thread pool.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path as FsPath
from typing import Any

from pydantic import BaseModel, Field

CONFIG_DIR = FsPath(os.environ.get("AXIBRIDGE_CONFIG_DIR", "~/.axibridge")).expanduser()


class Pen(BaseModel):
    """A physical pen preset.

    ``barrel_diameter_mm`` is the registration input: the V-cradle holder
    self-centres every barrel on the vee's bisector, so the nib offset is the
    holder calibration vector × this diameter (see Settings.holder_calibration).
    ``line_diameter_mm`` / ``opacity`` drive the ink-simulation preview only.
    ``pen_pos_down`` / ``pen_pos_up``, when set, override the global motion
    params while a layer using this pen plots (a marker contacts at a
    different height than a fine liner).
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "unnamed pen"
    color: str = "#26241f"
    barrel_diameter_mm: float = Field(default=10.0, ge=1, le=30)
    line_diameter_mm: float = Field(default=0.4, ge=0.03, le=10)
    opacity: float = Field(default=1.0, ge=0.05, le=1.0)
    pen_pos_down: float | None = Field(default=None, ge=0, le=100)
    pen_pos_up: float | None = Field(default=None, ge=0, le=100)


class HolderCalibration(BaseModel):
    """Nib offset per mm of barrel diameter, in machine frame (mm/mm).

    Measured once for the holder with the two-pen wizard:
    ``vector = (mark2 - mark1) / (diameter2 - diameter1)``. A zero vector
    disables compensation entirely — deliberately available when raw seating
    misregistration is wanted as an artifact.
    """

    dx_per_mm: float = 0.0
    dy_per_mm: float = 0.0

    @property
    def is_zero(self) -> bool:
        return self.dx_per_mm == 0.0 and self.dy_per_mm == 0.0

    def offset_for(self, barrel_diameter_mm: float) -> tuple[float, float]:
        """The nib's displacement for a pen; compensation translates the
        toolpath by the *negative* of this."""
        return (self.dx_per_mm * barrel_diameter_mm, self.dy_per_mm * barrel_diameter_mm)


class PaperPreset(BaseModel):
    name: str
    width: float
    height: float


class Settings(BaseModel):
    """Machine-level configuration — everything that describes *this machine
    and holder*, not an artwork."""

    holder_calibration: HolderCalibration = Field(default_factory=HolderCalibration)
    #: last-used motion params per backend id — machine-level defaults that
    #: survive restarts; a project's own stored params still win over these.
    backend_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    #: soft-limit envelope (machine.SoftLimits dump) — survives restarts
    soft_limits: dict[str, Any] = Field(default_factory=dict)
    # Estimator calibration (formerly constants buried in estimate.py).
    max_speed_mm_s: float = Field(default=279.4, gt=0, title="Max XY speed (mm/s)")
    max_accel_mm_s2: float = Field(default=4000.0, gt=0, title="Max acceleration (mm/s²)")
    pen_swing_s: float = Field(default=0.15, ge=0, title="Servo full-swing time (s)")
    projects_root: str = "~/AxidrawProjects"
    host: str = "0.0.0.0"
    port: int = 2942
    paper_presets: list[PaperPreset] = Field(default_factory=lambda: [
        PaperPreset(name="A4", width=210, height=297),
        PaperPreset(name="A5", width=148, height=210),
        PaperPreset(name="A6", width=105, height=148),
    ])

    def projects_dir(self) -> FsPath:
        return FsPath(self.projects_root).expanduser()


class _JsonStore:
    """Atomic, locked JSON persistence for one pydantic model."""

    def __init__(self, path: FsPath, model: type[BaseModel]) -> None:
        self.path = path
        self.model = model
        self._lock = threading.Lock()

    def load(self) -> BaseModel:
        with self._lock:
            if self.path.exists():
                return self.model.model_validate_json(self.path.read_text())
            return self.model()

    def save(self, obj: BaseModel) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(obj.model_dump_json(indent=2))
            tmp.replace(self.path)


class _PenFile(BaseModel):
    pens: list[Pen] = Field(default_factory=list)


class PenLibrary:
    def __init__(self, path: FsPath | None = None) -> None:
        self._store = _JsonStore(path or CONFIG_DIR / "pens.json", _PenFile)
        self._pens: dict[str, Pen] = {p.id: p for p in self._store.load().pens}

    def all(self) -> list[Pen]:
        return list(self._pens.values())

    def get(self, pen_id: str) -> Pen | None:
        return self._pens.get(pen_id)

    def upsert(self, pen: Pen) -> Pen:
        self._pens[pen.id] = pen
        self._persist()
        return pen

    def delete(self, pen_id: str) -> None:
        self._pens.pop(pen_id, None)
        self._persist()

    def _persist(self) -> None:
        self._store.save(_PenFile(pens=self.all()))


class SettingsStore:
    def __init__(self, path: FsPath | None = None) -> None:
        self._store = _JsonStore(path or CONFIG_DIR / "settings.json", Settings)
        self.settings: Settings = self._store.load()

    def update(self, values: dict) -> Settings:
        self.settings = Settings(**{**self.settings.model_dump(), **values})
        self._store.save(self.settings)
        return self.settings


pen_library = PenLibrary()
settings_store = SettingsStore()

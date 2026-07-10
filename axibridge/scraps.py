"""Global scrap library: workbench results saved outside any project.

The generation workbench (a popup: pick a generator + effect stack, reroll,
preview) can keep what it finds. A *scrap* is the frozen SVG of one such
result plus the recipe that produced it (module, params, effect stack) — the
SVG is the artifact of record (importing a scrap inserts exactly what you
saw, even if module code changes later); the recipe is metadata, kept so a
scrap can be reopened in the workbench and riffed on.

Scraps are machine-level like the pen library (``~/.axibridge/scraps/``):
"save for later" means across projects. Importing copies geometry *into* the
current project through the normal SVG-layer path; the library itself is
never referenced by a project file.

Same durability rules as stores.py: atomic writes (tmp + rename), a lock
because API handlers run in a thread pool.
"""

from __future__ import annotations

import datetime as _dt
import json
import threading
import uuid
from pathlib import Path as FsPath
from typing import Any

from pydantic import BaseModel, Field

from .stores import CONFIG_DIR


class Scrap(BaseModel):
    id: str
    name: str = "scrap"
    module: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    effects: list[dict[str, Any]] = Field(default_factory=list)
    created: str = ""  # ISO timestamp
    points: int = 0


class _ScrapIndex(BaseModel):
    scraps: list[Scrap] = Field(default_factory=list)


class ScrapLibrary:
    def __init__(self, root: FsPath | None = None) -> None:
        self._root = root or CONFIG_DIR / "scraps"
        self._lock = threading.Lock()

    def _index_path(self) -> FsPath:
        return self._root / "index.json"

    def _load(self) -> _ScrapIndex:
        try:
            return _ScrapIndex(**json.loads(self._index_path().read_text()))
        except FileNotFoundError:
            return _ScrapIndex()

    def _persist(self, index: _ScrapIndex) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        tmp = self._index_path().with_suffix(".tmp")
        tmp.write_text(index.model_dump_json(indent=2))
        tmp.replace(self._index_path())

    def all(self) -> list[Scrap]:
        with self._lock:
            return self._load().scraps

    def get(self, scrap_id: str) -> Scrap | None:
        with self._lock:
            return next((s for s in self._load().scraps if s.id == scrap_id), None)

    def svg(self, scrap_id: str) -> str | None:
        path = self._root / f"{scrap_id}.svg"
        try:
            return path.read_text()
        except FileNotFoundError:
            return None

    def save(self, *, name: str, module: str, params: dict[str, Any],
             effects: list[dict[str, Any]], svg: str, points: int) -> Scrap:
        scrap = Scrap(
            id=uuid.uuid4().hex[:12],
            name=name.strip() or module or "scrap",
            module=module, params=params, effects=effects, points=points,
            created=_dt.datetime.now().isoformat(timespec="seconds"),
        )
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            tmp = self._root / f"{scrap.id}.svg.tmp"
            tmp.write_text(svg)
            tmp.replace(self._root / f"{scrap.id}.svg")
            index = self._load()
            index.scraps.insert(0, scrap)  # newest first, like a darkroom strip
            self._persist(index)
        return scrap

    def delete(self, scrap_id: str) -> None:
        with self._lock:
            index = self._load()
            index.scraps = [s for s in index.scraps if s.id != scrap_id]
            self._persist(index)
            (self._root / f"{scrap_id}.svg").unlink(missing_ok=True)


scrap_library = ScrapLibrary()

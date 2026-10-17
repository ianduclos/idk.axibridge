"""Saved Gesture Studies: forks made in the bench, kept beside the pens and the
gallery (machine-level, `~/.axibridge/gesture_studies/`, one JSON file per
study), so they persist across projects. Built-in studies ship in the app
(`sources/_gesture_studies/studies/`) and are never written here; promoting a
saved study into the repo is a later script, not a UI action.

A saved study is validated in full before it is written (format, recipe
through its engine, every control against the params it points at) and again
when read; a file that no longer validates is reported, never served. Kept
layers embed their own study snapshot, so deleting a saved study never
changes a layer.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import tempfile
import threading
from pathlib import Path as FsPath
from uuid import uuid4

from .sources._gesture_studies import studies as ST
from .stores import CONFIG_DIR

MAX_STUDIES = 500
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class GestureStudyStore:
    def __init__(self, root: FsPath):
        self.root = root
        self._lock = threading.RLock()

    def _file(self, study_id: str) -> FsPath:
        if not _ID.fullmatch(study_id or ""):
            raise KeyError("Study not found")
        return self.root / f"{study_id}.json"

    def _read(self, study_id: str) -> ST.Study:
        try:
            raw = json.loads(self._file(study_id).read_text())
        except FileNotFoundError:
            raise KeyError("Study not found") from None
        study = ST.Study(**raw)
        if study.id != study_id:
            raise ValueError("Study identifier does not match its file")
        return study

    def _write(self, study: ST.Study) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".study-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(json.dumps(study.model_dump(mode="json"), indent=1, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self._file(study.id))
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def list(self) -> dict:
        with self._lock:
            items, warnings = [], []
            for path in sorted(self.root.glob("*.json")) if self.root.exists() else []:
                try:
                    items.append(ST.check_study(self._read(path.stem)))
                except (ValueError, OSError, KeyError) as exc:
                    warnings.append(f"Could not read saved study {path.stem}: {str(exc)[:200]}")
            items.sort(key=lambda s: (s.created, s.label.casefold(), s.id))
            return {"items": items, "warnings": warnings}

    def get(self, study_id: str) -> ST.Study:
        with self._lock:
            return self._read(study_id)

    def save(self, *, label: str, engine: str, recipe: dict, controls: list, notes: str = "",
             source: str = "", parent: dict | None = None) -> ST.Study:
        """Store a NEW study (a fork): a fresh id, version 1, `parent` the
        study + version it grew from. Validated in full before writing."""
        with self._lock:
            if self.root.exists() and len(list(self.root.glob("*.json"))) >= MAX_STUDIES:
                raise ValueError(f"At most {MAX_STUDIES} saved studies; delete some first")
            taken = set(ST.builtin_ids())
            while True:
                sid = f"{ST.slug(label)}_{uuid4().hex[:6]}"
                if sid not in taken and not self._file(sid).exists():
                    break
            study = ST.Study(id=sid, label=label.strip() or "Untitled study", version=1, parent=parent,
                             created=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                             source=source or (f"forked from {parent['id']} v{parent['version']}" if parent else ""),
                             engine=engine, notes=notes, recipe=recipe, controls=controls)
            study = ST.check_study(study)
            self._write(study)
            return study

    def delete(self, study_id: str) -> None:
        with self._lock:
            if study_id in ST.builtin_ids():
                raise ValueError("Built-in studies ship with the app and cannot be deleted")
            path = self._file(study_id)
            if not path.exists():       # an unreadable file can still be deleted
                raise KeyError("Study not found")
            path.unlink()


gesture_study_store = GestureStudyStore(CONFIG_DIR / "gesture_studies")

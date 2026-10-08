"""Kept-project dirty tracking and detached recovery capture for Session.

Session owns the lock and content. This mixin owns only recovery bookkeeping;
it does not import the Session singleton or change any save/load route.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from .assets import asset_store
from .compose import Project
from .recovery import RecoverySnapshot, RecoveryStore


@dataclass(frozen=True)
class _Fingerprint:
    signature: tuple[Any, ...]
    # Keep identity-keyed immutable objects alive while this fingerprint is
    # retained; otherwise Python could reuse an id after a project switch.
    references: tuple[object, ...] = field(compare=False, repr=False)


def _clone_project(project: Project) -> Project:
    """Copy mutable model metadata while sharing frozen capture geometry lists."""
    shared = {
        id(paths): paths
        for group in project.staging
        if group.snapshot is not None
        for paths in group.snapshot.source_geometry.values()
    }
    return copy.deepcopy(project, shared)


def _fingerprint(session: Any) -> _Fingerprint:
    project = session.project
    layers = []
    for layer in project.layers:
        data = layer.model_dump(mode="json")
        if layer.source.type in ("generator", "baked", "tween"):
            # save_project adds this provenance while serializing a folder.
            data["source"].pop("file", None)
            data["source"].pop("svg_layer", None)
        layers.append(data)

    staging = []
    references: list[object] = []
    for group in project.staging:
        data = group.model_dump(mode="json", exclude={"snapshot", "sheets"})
        sheets = []
        for sheet in group.sheets:
            sheet_data = sheet.model_dump(mode="json")
            sheet_data.pop("file", None)  # serializer-derived on first save
            sheets.append(sheet_data)
        data["sheets"] = sheets
        if group.snapshot is not None:
            snapshot = group.snapshot
            data["snapshot"] = snapshot.model_dump(
                mode="json", exclude={"source_geometry", "svg_files"}
            )
            data["snapshot_identity"] = id(snapshot)
            references.append(snapshot)
            references.extend(snapshot.source_geometry.values())
        staging.append(data)

    source_geometry = []
    for layer in project.layers:
        if layer.source.type == "tween":
            continue  # resolve-time geometry is derived from its endpoints
        paths = session.source_geometry.get(layer.id)
        source_geometry.append((layer.id, id(paths) if paths is not None else None))
        if paths is not None:
            references.append(paths)

    staged_documents = []
    for name, document in sorted(session.staging_documents.items()):
        staged_documents.append((name, id(document)))
        references.append(document)

    signature = (
        json.dumps(project.model_dump(mode="json", exclude={"layers", "staging"}), sort_keys=True),
        json.dumps(layers, sort_keys=True),
        json.dumps(staging, sort_keys=True),
        tuple(source_geometry),
        tuple(sorted(session.svg_files.items())),
        tuple(staged_documents),
        tuple(sorted(asset_store.all().items())),
    )
    return _Fingerprint(signature, tuple(references))


class RecoveryStateMixin:
    """Mixin for a Session with `_lock` and the usual project state fields."""

    def init_recovery_state(self) -> None:
        """Call once from Session.__init__ after its persistent fields exist."""
        self._recovery_write_lock = threading.RLock()
        self._recovery_store: RecoveryStore | None = None
        self.begin_project()

    def _require_recovery_state(self) -> None:
        if not hasattr(self, "_recovery_session_id"):
            raise RuntimeError("Session must call init_recovery_state() after initialization")

    @property
    def recovery_store(self) -> RecoveryStore:
        self._require_recovery_state()
        if self._recovery_store is None:
            self._recovery_store = RecoveryStore()
        return self._recovery_store

    def _observe_recovery_locked(self) -> _Fingerprint:
        current = _fingerprint(self)
        if current != self._recovery_seen:
            self._recovery_revision += 1
            self._recovery_seen = current
        return current

    def recovery_status(self) -> dict:
        self._require_recovery_state()
        with self._lock:
            current = self._observe_recovery_locked()
            recovery = dict(self._recovery_metadata or {})
            if self._recovery_error is not None:
                recovery["error"] = self._recovery_error
            return {
                "dirty": current != self._recovery_baseline,
                "revision": self._recovery_revision,
                "session_id": self._recovery_session_id,
                "recovery": recovery,
            }

    def mark_saved(self) -> None:
        self._require_recovery_state()
        with self._lock:
            self._recovery_baseline = self._observe_recovery_locked()
            self._recovery_error = None

    def begin_project(self) -> None:
        """Reset tracking after New/Load; the present state is the baseline."""
        with self._lock:
            self._recovery_session_id = uuid.uuid4().hex
            self._recovery_revision = 0
            self._recovery_baseline = self._recovery_seen = _fingerprint(self)
            self._recovery_metadata: dict | None = None
            self._recovery_error: str | None = None

    def capture_recovery(self) -> RecoverySnapshot:
        self._require_recovery_state()
        with self._lock:
            self._observe_recovery_locked()
            history = [
                (_clone_project(project), dict(geometry), dict(svg), dict(staging))
                for project, geometry, svg, staging in self.history_for_save()
            ]
            return RecoverySnapshot(
                project=_clone_project(self.project),
                source_geometry=dict(self.source_geometry),
                svg_files=dict(self.svg_files),
                assets=asset_store.all(),
                staging_documents=dict(self.staging_documents),
                history=history,
                revision=self._recovery_revision,
                session_id=self._recovery_session_id,
                project_dir=str(self.project_dir) if self.project_dir is not None else None,
            )

    def checkpoint_recovery(self) -> dict:
        """Persist a capture without holding the Session lock during disk I/O."""
        self._require_recovery_state()
        with self._recovery_write_lock:
            status = self.recovery_status()
            if not status["dirty"]:
                return {"id":status["session_id"],"revision":status["revision"],"checkpointed":False}
            snapshot = self.capture_recovery()
            try:
                metadata = self.recovery_store.write(snapshot)
            except Exception as exc:
                with self._lock:
                    if self._recovery_session_id == snapshot.session_id:
                        self._recovery_error = str(exc)
                raise
            with self._lock:
                self._observe_recovery_locked()
                if (self._recovery_session_id == snapshot.session_id
                        and self._recovery_revision == snapshot.revision):
                    self._recovery_metadata = dict(metadata)
                    self._recovery_error = None
            return metadata

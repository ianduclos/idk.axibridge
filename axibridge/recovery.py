"""Bounded, detached recovery archives for unfinished projects.

Each session owns a current ZIP and one previous valid ZIP under the machine
configuration directory. The archive contains an ordinary project folder and
its own recovery metadata, so metadata and content become visible together.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path as FsPath

from . import project_io
from .compose import Project
from .model import Path, PathDocument
from .stores import CONFIG_DIR


HistoryEntry = tuple[
    Project, dict[str, list[Path]], dict[str, str], dict[str, PathDocument]
]
LoadedProject = tuple[
    Project, dict[str, list[Path]], dict[str, str], dict[str, bytes],
    dict[str, PathDocument], list[HistoryEntry],
]

_SAFE_ID = re.compile(
    r"(?:[A-Fa-f0-9]{8,64}|[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12})\Z"
)


@dataclass
class RecoverySnapshot:
    project: Project
    source_geometry: dict[str, list[Path]]
    svg_files: dict[str, str]
    assets: dict[str, bytes]
    staging_documents: dict[str, PathDocument]
    history: list[HistoryEntry]
    revision: int
    session_id: str
    project_dir: str | None


def _validated_id(recovery_id: str) -> str:
    if not isinstance(recovery_id, str) or not _SAFE_ID.fullmatch(recovery_id):
        raise ValueError("recovery id must be hexadecimal or a canonical UUID")
    return recovery_id


class RecoveryStore:
    """Write, discover, load and discard recovery ZIPs for independent sessions."""

    def __init__(self, root: FsPath | None = None):
        self.root = FsPath(root) if root is not None else CONFIG_DIR / "recovery"

    def _paths(self, recovery_id: str) -> tuple[FsPath, FsPath]:
        safe_id = _validated_id(recovery_id)
        return self.root / f"{safe_id}.zip", self.root / f"{safe_id}.previous.zip"

    @staticmethod
    def _metadata(archive: FsPath, expected_id: str) -> dict:
        """Reject truncated archives and mismatched metadata before using one."""
        with zipfile.ZipFile(archive) as zf:
            if zf.testzip() is not None:
                raise ValueError("corrupt recovery ZIP member")
            if "project.json" not in zf.namelist():
                raise ValueError("recovery ZIP has no project")
            metadata = json.loads(zf.read("recovery.json"))
        if not isinstance(metadata, dict) or metadata.get("id") != expected_id:
            raise ValueError("recovery metadata id does not match archive")
        if not isinstance(metadata.get("revision"), int):
            raise ValueError("recovery metadata has no revision")
        return metadata

    def _candidate(self, recovery_id: str) -> tuple[FsPath, dict]:
        current, previous = self._paths(recovery_id)
        for archive, fallback in ((current, False), (previous, True)):
            try:
                metadata = self._metadata(archive, recovery_id)
            except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
                continue
            return archive, {**metadata, "fallback": fallback} if fallback else metadata
        raise FileNotFoundError(f"no valid recovery for {recovery_id}")

    @staticmethod
    def _fsync_directory(path: FsPath) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def write(self, snapshot: RecoverySnapshot) -> dict:
        current, previous = self._paths(snapshot.session_id)
        metadata = {
            "id": snapshot.session_id,
            "revision": snapshot.revision,
            "name": snapshot.project.name,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "project_dir": snapshot.project_dir,
        }
        # save_project sets source.file and sheet.file. Keep those mutations on
        # fresh model metadata while sharing immutable geometry lists/bytes.
        project = snapshot.project.model_copy(deep=True)
        history = [
            (item[0].model_copy(deep=True), dict(item[1]), dict(item[2]), dict(item[3]))
            for item in snapshot.history
        ]
        with tempfile.TemporaryDirectory(prefix="axibridge-recovery-build-") as work:
            folder = FsPath(work) / "project"
            project_io.save_project(
                project, snapshot.source_geometry, snapshot.svg_files, folder,
                assets=snapshot.assets, staging_documents=snapshot.staging_documents,
                history=history,
            )
            (folder / "recovery.json").write_text(json.dumps(metadata, indent=2))
            archive_data = project_io.export_zip(folder)

        self.root.mkdir(parents=True, exist_ok=True)
        temp_path: FsPath | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{snapshot.session_id}-", suffix=".tmp",
                dir=self.root, delete=False,
            ) as out:
                temp_path = FsPath(out.name)
                out.write(archive_data)
                out.flush()
                os.fsync(out.fileno())

            # A bad current ZIP must never replace the known-good fallback.
            if current.exists():
                try:
                    self._metadata(current, snapshot.session_id)
                except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
                    pass
                else:
                    old_temp: FsPath | None = None
                    try:
                        with tempfile.NamedTemporaryFile(
                            mode="wb", prefix=f".{snapshot.session_id}-old-",
                            suffix=".tmp", dir=self.root, delete=False,
                        ) as old:
                            old_temp = FsPath(old.name)
                            with current.open("rb") as source:
                                shutil.copyfileobj(source, old)
                            old.flush()
                            os.fsync(old.fileno())
                        os.replace(old_temp, previous)
                        self._fsync_directory(self.root)
                    finally:
                        if old_temp is not None:
                            old_temp.unlink(missing_ok=True)
            os.replace(temp_path, current)
            self._fsync_directory(self.root)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return metadata

    def list_entries(self) -> list[dict]:
        if not self.root.exists():
            return []
        ids: set[str] = set()
        for archive in self.root.glob("*.zip"):
            name = archive.name
            recovery_id = name.removesuffix(".previous.zip").removesuffix(".zip")
            if _SAFE_ID.fullmatch(recovery_id):
                ids.add(recovery_id)
        entries = []
        for recovery_id in ids:
            try:
                _, metadata = self._candidate(recovery_id)
            except FileNotFoundError:
                continue
            entries.append(metadata)
        return sorted(entries, key=lambda entry: entry["created_at"], reverse=True)

    def load(self, recovery_id: str) -> tuple[dict, LoadedProject]:
        current, previous = self._paths(recovery_id)
        for archive, fallback in ((current, False), (previous, True)):
            try:
                metadata = self._metadata(archive, recovery_id)
                with tempfile.TemporaryDirectory(prefix="axibridge-recovery-load-") as work:
                    project_dir = project_io.import_zip(
                        archive.read_bytes(), FsPath(work), "recovered"
                    )
                    loaded = project_io.load_project(project_dir)
                return ({**metadata, "fallback": True} if fallback else metadata), loaded
            except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
                continue
        raise FileNotFoundError(f"no valid recovery for {recovery_id}")

    def discard(self, recovery_id: str) -> None:
        current, previous = self._paths(recovery_id)
        for archive in (current, previous):
            archive.unlink(missing_ok=True)
        if self.root.exists():
            self._fsync_directory(self.root)

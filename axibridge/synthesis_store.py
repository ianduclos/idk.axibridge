"""Saved syntheses: whole scores Ian saved from the bench (machine-level,
`~/.axibridge/synthesis/`, one JSON file each), so they persist across
projects and appear in the bench's gallery beside the built-in starting
points. A score is validated (bounds and the frozen executor) before it is
written and again when read; a file that no longer validates is reported,
never served. Kept layers embed their own score, so deleting a saved
synthesis never changes a layer.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import tempfile
import threading
from pathlib import Path as FsPath
from typing import Any
from uuid import uuid4

from .stores import CONFIG_DIR

MAX_SAVED = 500
MAX_THUMB = 120_000                  # a small PNG data URL drawn by the bench from its preview
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    return (s or "synthesis")[:40]


def _checked(score: dict) -> dict:
    from .sources.synthesis import SynthesisParams  # noqa: PLC0415
    return SynthesisParams(score=score).score


class SynthesisStore:
    def __init__(self, root: FsPath):
        self.root = root
        self._lock = threading.RLock()

    def _file(self, sid: str) -> FsPath:
        if not _ID.fullmatch(sid or ""):
            raise KeyError("Synthesis not found")
        return self.root / f"{sid}.json"

    def _read(self, sid: str) -> dict[str, Any]:
        try:
            raw = json.loads(self._file(sid).read_text())
        except FileNotFoundError:
            raise KeyError("Synthesis not found") from None
        if raw.get("id") != sid:
            raise ValueError("Synthesis identifier does not match its file")
        raw["score"] = _checked(raw["score"])
        return raw

    def _write(self, item: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".synthesis-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self._file(item["id"]))
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def list(self) -> dict:
        with self._lock:
            items, warnings = [], []
            for path in sorted(self.root.glob("*.json")) if self.root.exists() else []:
                try:
                    items.append(self._read(path.stem))
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    warnings.append(f"Could not read saved synthesis {path.stem}: {str(exc)[:200]}")
            items.sort(key=lambda s: (s.get("created", ""), s.get("label", "").casefold(), s["id"]))
            return {"items": items, "warnings": warnings}

    def get(self, sid: str) -> dict:
        with self._lock:
            return self._read(sid)

    def save(self, *, label: str, score: dict, thumb: str = "", notes: str = "") -> dict:
        with self._lock:
            if self.root.exists() and len(list(self.root.glob("*.json"))) >= MAX_SAVED:
                raise ValueError(f"At most {MAX_SAVED} saved syntheses; delete some first")
            if thumb and (len(thumb) > MAX_THUMB or not thumb.startswith("data:image/png;base64,")):
                raise ValueError("thumb must be a small PNG data URL")
            while True:
                sid = f"{_slug(label)}_{uuid4().hex[:6]}"
                if not self._file(sid).exists():
                    break
            item = {"id": sid, "label": label.strip()[:120] or "Untitled synthesis", "notes": notes[:2000],
                    "created": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                    "score": _checked(score), "thumb": thumb}
            self._write(item)
            return item

    def delete(self, sid: str) -> None:
        with self._lock:
            path = self._file(sid)
            if not path.exists():
                raise KeyError("Synthesis not found")
            path.unlink()


synthesis_store = SynthesisStore(CONFIG_DIR / "synthesis")

"""Project-independent module presets, preferences, and identifying previews."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path as FsPath
import tempfile
import threading
import subprocess
import sys
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .registry import effects, get_effect, get_source, preset_exclusions, representative_params, sources
from .stores import CONFIG_DIR

Kind = Literal["source", "effect"]


class Preset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    kind: Kind
    module: str
    name: str = Field(min_length=1, max_length=200)
    created_at: datetime
    updated_at: datetime
    params: dict[str, Any]

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give this preset a name")
        return value


class Preference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    module: str
    starred: bool = False
    tags: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values: list[str]) -> list[str]:
        result, seen = [], set()
        for raw in values:
            value = raw.strip()
            if len(value) > 60:
                raise ValueError("Tags must be 60 characters or fewer")
            if value and value.casefold() not in seen:
                result.append(value)
                seen.add(value.casefold())
        return result


class LibraryFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    presets: list[Preset] = Field(default_factory=list)
    preferences: list[Preference] = Field(default_factory=list)


def _module(kind: Kind, module_id: str):
    return get_source(module_id) if kind == "source" else get_effect(module_id)


def _asset_fields(model: type[BaseModel]) -> set[str]:
    """Find asset-bearing top-level fields, including refs nested below them."""
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})

    def contains_asset(node: Any, seen: set[str]) -> bool:
        if isinstance(node, list):
            return any(contains_asset(item, seen) for item in node)
        if not isinstance(node, dict):
            return False
        if node.get("format") == "asset":
            return True
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            key = ref.rsplit("/", 1)[-1]
            if key in seen:
                return False
            return contains_asset(defs.get(key, {}), seen | {key})
        return any(contains_asset(v, seen) for v in node.values())

    return {name for name, node in schema.get("properties", {}).items()
            if contains_asset(node, set())}


def _validate_keys(model: type[BaseModel], params: dict[str, Any]) -> None:
    schema = model.model_json_schema()

    def walk(node: Any, value: Any, path: str, seen: set[str]) -> None:
        if not isinstance(node, dict):
            return
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            key = ref.rsplit("/", 1)[-1]
            if key not in seen:
                walk(schema.get("$defs", {}).get(key, {}), value, path, seen | {key})
            return
        branches = node.get("anyOf") or node.get("oneOf")
        if branches:
            if isinstance(value, dict):
                candidates = []
                object_branches = []
                for branch in branches:
                    resolved = branch
                    ref = branch.get("$ref") if isinstance(branch, dict) else None
                    if isinstance(ref, str) and ref.startswith("#/$defs/"):
                        resolved = schema.get("$defs", {}).get(ref.rsplit("/", 1)[-1], {})
                    props = resolved.get("properties", {}) if isinstance(resolved, dict) else {}
                    if props:
                        object_branches.append(props)
                    if props and set(value).issubset(props):
                        candidates.append(branch)
                if candidates:
                    walk(candidates[0], value, path, seen)
                elif object_branches:
                    allowed = set().union(*(set(props) for props in object_branches))
                    names = ", ".join(f"{path}{name}" for name in sorted(set(value) - allowed))
                    raise ValueError("Unknown saved parameter(s): " + names)
            return
        properties = node.get("properties")
        if isinstance(value, dict) and isinstance(properties, dict):
            unknown = set(value) - set(properties)
            if unknown:
                names = ", ".join(f"{path}{name}" for name in sorted(unknown))
                raise ValueError("Unknown saved parameter(s): " + names)
            for name, child in properties.items():
                if name in value:
                    walk(child, value[name], f"{path}{name}.", seen)
        if isinstance(value, list) and isinstance(node.get("items"), dict):
            for index, item in enumerate(value):
                walk(node["items"], item, f"{path}{index}.", seen)

    walk(schema, params, "", set())


def portable_params(kind: Kind, module_id: str, params: dict[str, Any]) -> dict[str, Any]:
    module = _module(kind, module_id)
    _validate_keys(module.Params, params)
    full = module.Params(**params).model_dump()
    excluded = set(preset_exclusions(kind, module_id)) | _asset_fields(module.Params)
    return {key: value for key, value in full.items() if key not in excluded}


class ModuleLibraryStore:
    def __init__(self, root: FsPath):
        self.root = root
        self.path = root / "library.json"
        self._lock = threading.RLock()
        self._thumbs: OrderedDict[str, str] = OrderedDict()
        self._thumb_lock = threading.Lock()
        self._thumb_capacity = threading.BoundedSemaphore(10)  # 2 active + 8 waiting
        self._thumb_renderers = threading.BoundedSemaphore(2)
        self._thumb_flights: dict[str, dict[str, Any]] = {}

    def _read(self) -> LibraryFile:
        try:
            return LibraryFile.model_validate_json(self.path.read_text())
        except FileNotFoundError:
            return LibraryFile()

    def _write(self, data: LibraryFile) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".library-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(data.model_dump_json())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def list(self) -> dict[str, Any]:
        with self._lock:
            data = self._read()
        warnings = []
        known = {("source", key) for key in sources()} | {("effect", key) for key in effects()}
        for preset in data.presets:
            if (preset.kind, preset.module) not in known:
                warnings.append(f"Preset {preset.id} references missing {preset.kind} module {preset.module}")
        return {"presets": [p.model_dump(mode="json") for p in data.presets],
                "preferences": [p.model_dump(mode="json") for p in data.preferences],
                "warnings": warnings}

    def create(self, kind: Kind, module: str, name: str, params: dict[str, Any]) -> dict[str, Any]:
        clean = portable_params(kind, module, params)
        now = datetime.now(timezone.utc)
        record = Preset(id=uuid4().hex, kind=kind, module=module, name=name,
                        created_at=now, updated_at=now, params=clean)
        with self._lock:
            data = self._read()
            data.presets.append(record)
            self._write(data)
        return record.model_dump(mode="json")

    def update(self, preset_id: str, *, name: str | None = None,
               params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            for index, old in enumerate(data.presets):
                if old.id == preset_id:
                    changes: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
                    if name is not None:
                        changes["name"] = Preset(name=name, **old.model_dump(exclude={"name"})).name
                    if params is not None:
                        changes["params"] = portable_params(old.kind, old.module, params)
                    record = old.model_copy(update=changes)
                    data.presets[index] = record
                    self._write(data)
                    return record.model_dump(mode="json")
        raise KeyError("Preset not found")

    def delete(self, preset_id: str) -> None:
        with self._lock:
            data = self._read()
            before = len(data.presets)
            data.presets = [p for p in data.presets if p.id != preset_id]
            if len(data.presets) == before:
                raise KeyError("Preset not found")
            self._write(data)

    def resolve(self, kind: Kind, module_id: str, preset_id: str | None,
                current: dict[str, Any]) -> dict[str, Any]:
        module = _module(kind, module_id)
        defaults = module.Params().model_dump()
        saved: dict[str, Any] = {}
        if preset_id is not None:
            with self._lock:
                preset = next((p for p in self._read().presets if p.id == preset_id), None)
            if preset is None:
                raise KeyError("Preset not found")
            if (preset.kind, preset.module) != (kind, module_id):
                raise ValueError("Preset belongs to a different module")
            # Re-sanitize on every application. This protects old files and
            # hand-edited/malicious records from restoring captured state or
            # project asset names after the exclusion policy changes.
            saved = portable_params(kind, module_id, preset.params)
        merged = {**defaults, **saved}
        merged = _preserve_asset_leaves(module.Params.model_json_schema(), current, merged)
        return module.Params(**merged).model_dump()

    def preference(self, kind: Kind, module: str, starred: bool,
                   tags: list[str]) -> dict[str, Any]:
        _module(kind, module)
        item = Preference(kind=kind, module=module, starred=starred, tags=tags)
        with self._lock:
            data = self._read()
            data.preferences = [p for p in data.preferences
                                if (p.kind, p.module) != (kind, module)]
            data.preferences.append(item)
            self._write(data)
        return item.model_dump(mode="json")

    def thumbnail(self, kind: Kind, module_id: str) -> str:
        module = _module(kind, module_id)
        params = representative_params(kind, module_id, module)
        module_file = FsPath(inspect.getfile(module.__class__)).read_bytes()
        worker_file = FsPath(__file__).with_name("module_thumbnail_worker.py").read_bytes()
        key = hashlib.sha256(kind.encode() + module_id.encode() + module_file
                             + json.dumps(params, sort_keys=True, default=str).encode()
                             + worker_file).hexdigest()
        with self._thumb_lock:
            if key in self._thumbs:
                self._thumbs.move_to_end(key)
                return self._thumbs[key]
        if not self._thumb_capacity.acquire(blocking=False):
            raise ValueError("Module preview queue is full")
        owner = False
        try:
            with self._thumb_lock:
                if key in self._thumbs:
                    self._thumbs.move_to_end(key)
                    return self._thumbs[key]
                flight = self._thumb_flights.get(key)
                if flight is None:
                    flight = {"event": threading.Event(), "error": None}
                    self._thumb_flights[key] = flight
                    owner = True
            if not owner:
                flight["event"].wait(13)
                with self._thumb_lock:
                    if key in self._thumbs:
                        return self._thumbs[key]
                raise ValueError(flight["error"] or "Module preview unavailable")
            with self._thumb_renderers:
                svg = self._render_thumbnail(kind, module_id, params)
            with self._thumb_lock:
                self._thumbs[key] = svg
                while len(self._thumbs) > 128:
                    self._thumbs.popitem(last=False)
            return svg
        except Exception as exc:
            if owner:
                flight["error"] = str(exc)
            raise
        finally:
            if owner:
                with self._thumb_lock:
                    self._thumb_flights.pop(key, None)
                flight["event"].set()
            self._thumb_capacity.release()

    def _render_thumbnail(self, kind: Kind, module_id: str,
                          params: dict[str, Any]) -> str:
        request = json.dumps({"kind": kind, "module": module_id, "params": params})
        try:
            result = subprocess.run(
                [sys.executable, "-m", "axibridge.module_thumbnail_worker"],
                input=request, text=True, capture_output=True, timeout=12, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Module preview timed out") from exc
        if result.returncode or not result.stdout:
            raise ValueError("Module preview unavailable")
        return result.stdout


_MISSING = object()


def _preserve_asset_leaves(schema: dict[str, Any], current: Any, target: Any) -> Any:
    defs = schema.get("$defs", {})

    def copy(node: Any, old: Any, new: Any, seen: set[str]) -> Any:
        if not isinstance(node, dict):
            return new
        if node.get("format") == "asset":
            return new if old is _MISSING else old
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            key = ref.rsplit("/", 1)[-1]
            if key in seen:
                return new
            return copy(defs.get(key, {}), old, new, seen | {key})
        for branch in node.get("anyOf", []) + node.get("oneOf", []):
            candidate = copy(branch, old, new, seen)
            if candidate is not new:
                return candidate
        props = node.get("properties")
        if isinstance(props, dict) and isinstance(new, dict):
            result = dict(new)
            old_map = old if isinstance(old, dict) else {}
            for name, child in props.items():
                if name in result:
                    result[name] = copy(child, old_map.get(name, _MISSING), result[name], seen)
            return result
        items = node.get("items")
        if isinstance(items, dict) and isinstance(new, list) and isinstance(old, list):
            return [copy(items, old[i] if i < len(old) else _MISSING, value, seen)
                    for i, value in enumerate(new)]
        return new

    return copy(schema, current, target, set())


module_library_store = ModuleLibraryStore(CONFIG_DIR / "module-library")

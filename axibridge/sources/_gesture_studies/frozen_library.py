"""The frozen gesture library, read the way a study (or a kept layer) asks.

Layout (written by `tools/gesture_studies/freeze.py`, append-only):

    library/<kind>/<id>/<hash12>/entry.json + data   one frozen version of an entry
    library/snapshots/<snapshot12>.json              {kind: {id: hash12}} of one freeze
    library/index.json                               current snapshot, history, withdrawn

`FrozenLibrary(snapshot, pins)` is the kit's `Library` with its folder lookup
replaced: an id resolves to the hash its `pins` name, else to the hash in the
snapshot (default: the current one). `ids(kind)` lists the snapshot, so a kept
layer whose recipe says "every generative hand" (an empty conversation pool)
keeps the hand set it was made with. Everything else — the policy gate, the
decoders, `entry()` — is the frozen kit's own code. Entries the research has
since made measure-only (`withdrawn`) are refused through any snapshot.
"""
from __future__ import annotations

import json
import re
import threading
from functools import lru_cache
from pathlib import Path

from .kit import library as _kl

ROOT = Path(__file__).resolve().parent / "library"
HASH = re.compile(r"^[0-9a-f]{12}$")
#: control type -> library kind
KIND_OF = {"hand": "hand", "hands": "hand", "tempo": "tempo", "trail": "dance_trail"}

_LOAD_LOCK = threading.Lock()
_LOADED: dict[tuple[str, str, str], object] = {}      # (kind, id, hash) -> decoded data, process-wide


def set_root(path: Path) -> Path:
    """Point the reader at another frozen library (tests); returns the old root."""
    global ROOT
    old, ROOT = ROOT, Path(path)
    index.cache_clear()
    snapshot.cache_clear()
    with _LOAD_LOCK:
        _LOADED.clear()
    return old


@lru_cache(maxsize=1)
def index() -> dict:
    return json.loads((ROOT / "index.json").read_text())


def current_snapshot() -> str:
    return index()["current"]


@lru_cache(maxsize=64)
def snapshot(sid: str) -> dict[str, dict[str, str]]:
    if not HASH.match(sid or ""):
        raise _kl.LibraryError(f"library snapshot id {sid!r} is malformed")
    p = ROOT / "snapshots" / f"{sid}.json"
    if not p.exists():
        raise _kl.LibraryError(f"library snapshot {sid} is not in this app's frozen library")
    return json.loads(p.read_text())["entries"]


class FrozenLibrary(_kl.Library):
    """The kit Library over one snapshot (+ explicit per-entry pins)."""

    def __init__(self, snapshot_id: str | None = None, pins: dict[tuple[str, str], str] | None = None):
        super().__init__(ROOT)
        self.snapshot_id = snapshot_id or current_snapshot()
        self.entries_map = snapshot(self.snapshot_id)
        self.pins = dict(pins or {})
        for (kind, eid), h in self.pins.items():
            if not HASH.match(h) or not (ROOT / kind / eid / h / "entry.json").exists():
                raise _kl.LibraryError(f"pinned library entry {kind}/{eid}@{h} is not in the frozen library")

    def kinds(self) -> list[str]:
        return sorted(self.entries_map)

    def ids(self, kind: str) -> list[str]:
        return sorted(self.entries_map.get(kind, {}))

    def hash_of(self, kind: str, id: str) -> str | None:
        return self.pins.get((kind, id)) or self.entries_map.get(kind, {}).get(id)

    def folder(self, kind: str, id: str) -> Path:
        h = self.hash_of(kind, id)
        return ROOT / kind / id / h if h else ROOT / kind / id / "_missing"

    def check(self, entry: dict, purpose: str = "generate", items=None) -> None:
        if purpose == "generate" and f"{entry['kind']}/{entry['id']}" in index().get("withdrawn", []):
            raise _kl.PolicyError(f"{entry['kind']}/{entry['id']} was withdrawn from generation by a later "
                                  "freeze (the research made it measure-only)")
        super().check(entry, purpose, items)

    def load(self, kind: str, id: str, purpose: str = "generate", items=None):
        e = self.entry(kind, id)
        self.check(e, purpose, items)
        key = (kind, id, self.hash_of(kind, id))
        with _LOAD_LOCK:
            if key not in _LOADED:
                fn = _kl._LOADERS.get(kind)
                folder = self.folder(kind, id)
                _LOADED[key] = fn(e, folder) if fn else {"entry": e, "folder": folder,
                                                         "files": {k: folder / v for k, v in e["files"].items()}}
            return _LOADED[key]

    def pin(self, kind: str, id: str) -> dict:
        """The record a kept layer stores for one entry it names."""
        e = self.entry(kind, id)
        return {"kind": kind, "id": id, "version": int(e.get("version", 1)), "hash": self.hash_of(kind, id)}

    def save(self, *a, **k):  # pragma: no cover — the app never writes the frozen library
        raise _kl.LibraryError("the frozen library is read-only (refreeze with tools/gesture_studies/freeze.py)")


def options(kind: str, snapshot_id: str | None = None) -> list[dict]:
    """Every entry of `kind` a control may offer: generative, not withdrawn,
    in the snapshot (default: current) — the list grows on refreeze."""
    lib = FrozenLibrary(snapshot_id)
    withdrawn = set(index().get("withdrawn", []))
    out = []
    for eid in lib.ids(kind):
        e = lib.entry(kind, eid)
        if e.get("policy") != "generative" or f"{kind}/{eid}" in withdrawn:
            continue
        try:
            lib.check(e, "generate")
        except _kl.PolicyError:
            continue
        out.append({"id": eid, "label": e.get("label") or eid, "version": int(e.get("version", 1)),
                    "hash": lib.hash_of(kind, eid)})
    return out

"""The frozen hand library, read for the synthesis bench.

Gesture Studies' `frozen_library` (one source), loaded over THIS package's
kit (`_shared.load`): the same append-only, content-addressed library folder
(`_gesture_studies/library/`), the same snapshot / pin / withdrawn rules, but
`FrozenLibrary` subclasses the synthesis kit's own `Library`. The bench's
default snapshot is the one `tools/synthesis/freeze.py` recorded in
`kit/FROZEN.json` (Gesture Studies' `current` may differ: each bench moves on
its own freeze).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ._shared import load

_gs = load("frozen_library")
ROOT = _gs.ROOT
HASH = _gs.HASH
LibraryError = _gs._kl.LibraryError
PolicyError = _gs._kl.PolicyError
_kl = _gs._kl
_LOAD_LOCK = _gs._LOAD_LOCK
_LOADED = _gs._LOADED
index = _gs.index
snapshot = _gs.snapshot


@lru_cache(maxsize=1)
def frozen() -> dict:
    return json.loads((Path(__file__).resolve().parent / "kit" / "FROZEN.json").read_text())


def current_snapshot() -> str:
    """The snapshot the bench resolves against by default (its freeze's)."""
    return frozen()["library_snapshot"]


class FrozenLibrary(_gs.FrozenLibrary):
    def __init__(self, snapshot_id: str | None = None, pins: dict | None = None):
        super().__init__(snapshot_id or current_snapshot(), pins)


def options(kind: str, snapshot_id: str | None = None) -> list[dict]:
    return _gs.options(kind, snapshot_id or current_snapshot())

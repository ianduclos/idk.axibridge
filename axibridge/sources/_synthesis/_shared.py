"""Load one of Gesture Studies' app modules a second time, as a module of THIS package.

`load("devices")` executes `_gesture_studies/devices.py` under the name
`axibridge.sources._synthesis._gs_devices`: its relative imports (`.kit`,
`.frozen_library`, `...render_work`) resolve inside `_synthesis`, so the same
code drives the synthesis bench's own frozen kit. The Gesture Studies module
objects are untouched; each loaded copy has its own globals (caches, locks).
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

GS_DIR = Path(__file__).resolve().parents[1] / "_gesture_studies"
_LOCK = threading.Lock()


def load(name: str):
    full = f"{__package__}._gs_{name}"
    with _LOCK:
        mod = sys.modules.get(full)
        if mod is not None:
            return mod
        spec = importlib.util.spec_from_file_location(full, GS_DIR / f"{name}.py",
                                                      submodule_search_locations=None)
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = __package__
        sys.modules[full] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            sys.modules.pop(full, None)
            raise
        return mod

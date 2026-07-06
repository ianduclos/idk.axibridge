"""In-memory server log ring: the app-shell window has no terminal, so the
last ~500 log records are kept here and served at ``GET /api/logs`` for the
Settings tab's "Server log" panel.

A module-level singleton (like the stores): ``install()`` is idempotent and
attaches one handler to the root logger — uvicorn's loggers propagate there,
so server + axibridge records all land in the ring.
"""

from __future__ import annotations

import itertools
import logging
import threading
from collections import deque

_lock = threading.Lock()
_ring: deque[dict] = deque(maxlen=500)
_seq = itertools.count(1)  # monotonic id — 'after' cursor for cheap polling
_installed = False


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "id": next(_seq),
                "ts": record.created,
                "level": record.levelname,
                "logger": record.name,
                "msg": self.format(record),
            }
        except Exception:  # a broken record must never take the server down
            return
        with _lock:
            _ring.append(entry)


def install() -> None:
    """Attach the ring to the root logger (idempotent). uvicorn's loggers
    propagate to root by default, so one handler catches everything."""
    global _installed
    with _lock:
        if _installed:
            return
        _installed = True
    handler = _RingHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.INFO)
    root = logging.getLogger()
    root.addHandler(handler)
    # the root logger defaults to WARNING, which drops INFO records before any
    # handler sees them — open it to INFO (per-handler levels still apply)
    if root.level in (logging.NOTSET, logging.WARNING):
        root.setLevel(logging.INFO)
    # uvicorn.access does NOT propagate by default in some configs — attach
    # directly so request lines show up too (harmless if it also propagates:
    # the ring handler sits on root, not on uvicorn.access, in that case).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        if not lg.propagate:
            lg.addHandler(handler)


def entries(after: int = 0) -> list[dict]:
    """Records with id > ``after``, oldest first."""
    with _lock:
        return [e for e in _ring if e["id"] > after]

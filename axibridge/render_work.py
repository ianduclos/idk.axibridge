"""Cooperative cancellation for expensive, read-only render work."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Hashable, Iterator


class RenderCancelled(BaseException):
    """Intentional render cancellation, kept outside ordinary error recovery."""


_current: ContextVar[threading.Event | None] = ContextVar(
    "axibridge_render_work", default=None
)


def checkpoint() -> None:
    """Raise when the current render scope has been superseded."""
    event = _current.get()
    if event is not None and event.is_set():
        raise RenderCancelled()


class RenderWork:
    """Tracks active render scopes independently of a Session's main lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: set[threading.Event] = set()
        self._waiting_mutations = 0
        self._lanes: dict[Hashable, threading.Event] = {}

    @contextmanager
    def scope(self, replacement_key: Hashable | None = None) -> Iterator[threading.Event]:
        event = threading.Event()
        with self._lock:
            if self._waiting_mutations:
                event.set()
            if replacement_key is not None:
                previous = self._lanes.get(replacement_key)
                if previous is not None:
                    previous.set()
                self._lanes[replacement_key] = event
            self._events.add(event)
        token = _current.set(event)
        try:
            checkpoint()
            yield event
        finally:
            _current.reset(token)
            with self._lock:
                self._events.discard(event)
                if replacement_key is not None and self._lanes.get(replacement_key) is event:
                    del self._lanes[replacement_key]

    @contextmanager
    def mutation(self) -> Iterator[None]:
        with self._lock:
            self._waiting_mutations += 1
            for event in self._events:
                event.set()
        try:
            yield
        finally:
            with self._lock:
                self._waiting_mutations -= 1

    def cancel(self) -> None:
        """Cancel scopes active now without blocking future scopes."""
        with self._lock:
            for event in self._events:
                event.set()

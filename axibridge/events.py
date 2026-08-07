"""Event bus: thread-side emit -> per-client asyncio queues -> SSE.

Progress and status flow one way (machine -> UI), so the transport is
Server-Sent Events, not WebSockets: EventSource reconnects automatically
(handy over Tailscale), proxies don't need upgrade support, and commands are
ordinary POSTs. Backends run in worker threads, so ``emit`` hops onto the
event loop with ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator


#: pushed into every subscriber queue at shutdown — see EventBus.close.
_CLOSE = object()


class EventBus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue] = set()
        self._closing = False

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once at app startup from inside the running loop. Clears the
        closing flag too: this is a module-level singleton, so a process that
        builds a second app after shutting the first down (the test suite does
        exactly that) must get a live bus back, not a permanently closed one."""
        self._loop = loop
        self._closing = False

    def emit(self, event: dict[str, Any]) -> None:
        """Thread-safe publish. Safe to call before startup (drops events)."""
        if self._loop is None:
            return
        event.setdefault("ts", time.time())
        self._loop.call_soon_threadsafe(self._fanout, event)

    def _fanout(self, event: dict[str, Any]) -> None:
        for q in list(self._queues):
            if q.qsize() > 500:  # slow client: drop oldest rather than grow
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)

    def close(self) -> None:
        """End every open stream. Called from the lifespan's shutdown side.

        An SSE response never finishes on its own, and uvicorn's graceful
        shutdown waits for open connections — so without this the server sat
        out its whole ``timeout_graceful_shutdown`` on every quit (measured:
        0.16 s with no client attached, 2.20 s with one). The browser always
        holds a stream open, so that cost was paid every single time. Waking
        the subscribers lets the responses end and shutdown finish promptly.
        """
        self._closing = True
        for q in list(self._queues):
            q.put_nowait(_CLOSE)

    def close_threadsafe(self) -> None:
        """:meth:`close` from outside the event loop (a signal handler)."""
        if self._loop is None:
            self.close()
            return
        try:
            self._loop.call_soon_threadsafe(self.close)
        except RuntimeError:  # loop already closed — nothing left to wake
            pass

    async def subscribe(self) -> AsyncIterator[str]:
        """Yields SSE-formatted frames, with a 15s heartbeat comment so idle
        connections survive proxies. Ends when :meth:`close` runs."""
        if self._closing:
            return
        q: asyncio.Queue = asyncio.Queue()
        self._queues.add(q)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if event is _CLOSE:
                    return
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            self._queues.discard(q)


bus = EventBus()

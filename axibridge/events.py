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


class EventBus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue] = set()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once at app startup from inside the running loop."""
        self._loop = loop

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

    async def subscribe(self) -> AsyncIterator[str]:
        """Yields SSE-formatted frames, with a 15s heartbeat comment so idle
        connections survive proxies."""
        q: asyncio.Queue = asyncio.Queue()
        self._queues.add(q)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            self._queues.discard(q)


bus = EventBus()

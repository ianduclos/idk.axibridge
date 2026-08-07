"""The SSE stream must end when the bus closes.

/api/events never finishes on its own, and uvicorn's graceful shutdown waits
for open connections — so a stream that ignores shutdown makes every quit sit
out the whole `timeout_graceful_shutdown` (measured before the fix: 0.13 s with
no client attached, 2.20 s with one, on every single close).

`__main__` closes the bus from `Server.handle_exit` rather than from the app's
lifespan, because uvicorn waits for connections BEFORE running lifespan
shutdown. These tests cover the bus contract that fix depends on.

Plain asyncio.run rather than pytest-asyncio: the suite carries no async plugin
and this doesn't justify adding one.
"""

import asyncio

from axibridge.events import EventBus


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=5.0))


async def _drain(bus, out, ready):
    ready.set()
    async for frame in bus.subscribe():
        out.append(frame)


def test_close_ends_an_open_stream():
    async def go():
        bus = EventBus()
        bus.attach_loop(asyncio.get_running_loop())
        out, ready = [], asyncio.Event()
        task = asyncio.create_task(_drain(bus, out, ready))
        await ready.wait()
        await asyncio.sleep(0)      # let subscribe() register its queue

        bus.emit({"type": "ping"})
        await asyncio.sleep(0.05)
        assert any("ping" in f for f in out), "a live stream should still deliver events"

        bus.close()
        # without the fix this never returns and the wait_for times out
        await asyncio.wait_for(task, timeout=2.0)
    _run(go())


def test_subscribe_after_close_returns_immediately():
    """A client connecting during shutdown must not open a fresh stream that
    would hold the server open all over again."""
    async def go():
        bus = EventBus()
        bus.attach_loop(asyncio.get_running_loop())
        bus.close()
        assert [f async for f in bus.subscribe()] == []
    _run(go())


def test_attach_loop_reopens_the_bus():
    """The bus is a module-level singleton: a process that builds a second app
    after shutting the first down (the suite does exactly that) must get a live
    bus back, not a permanently closed one."""
    async def go():
        bus = EventBus()
        bus.attach_loop(asyncio.get_running_loop())
        bus.close()
        bus.attach_loop(asyncio.get_running_loop())   # "startup" again

        out, ready = [], asyncio.Event()
        task = asyncio.create_task(_drain(bus, out, ready))
        await ready.wait()
        await asyncio.sleep(0)
        bus.emit({"type": "alive"})
        await asyncio.sleep(0.05)
        bus.close()
        await asyncio.wait_for(task, timeout=2.0)
        assert any("alive" in f for f in out)
    _run(go())


def test_close_threadsafe_from_another_thread():
    """handle_exit runs in a signal handler, off the loop thread."""
    import threading

    async def go():
        bus = EventBus()
        bus.attach_loop(asyncio.get_running_loop())
        out, ready = [], asyncio.Event()
        task = asyncio.create_task(_drain(bus, out, ready))
        await ready.wait()
        await asyncio.sleep(0)
        threading.Thread(target=bus.close_threadsafe).start()
        await asyncio.wait_for(task, timeout=2.0)
    _run(go())

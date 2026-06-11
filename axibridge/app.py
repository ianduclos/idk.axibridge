"""FastAPI app factory: API router + static frontend + lifecycle wiring."""

from __future__ import annotations

import asyncio
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import router
from .events import bus
from .machine import manager
from .registry import load_builtin_modules

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    bus.attach_loop(asyncio.get_running_loop())
    load_builtin_modules()
    # If an AxiDraw is plugged in, grab it right away (background thread —
    # serial connect blocks ~2 s). Tests and CI set AXIBRIDGE_NO_AUTOCONNECT
    # so the suite never touches real hardware.
    if not os.environ.get("AXIBRIDGE_NO_AUTOCONNECT"):
        threading.Thread(target=manager.auto_connect, name="axibridge-autoconnect",
                         daemon=True).start()
    yield
    manager.shutdown()


class _RevalidatedStatic(StaticFiles):
    """Static files with `Cache-Control: no-cache` — the browser revalidates
    every file on every load (cheap 304s when unchanged). Without this, a
    cached index.html can pair with freshly-fetched JS modules after a server
    update: the version mix throws at module scope and the whole UI goes
    blank. Zero-build means the server owns cache correctness."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app() -> FastAPI:
    app = FastAPI(title="axibridge", lifespan=_lifespan)
    app.include_router(router)
    # html=True serves index.html at "/"; mounted last so /api wins.
    app.mount("/", _RevalidatedStatic(directory=STATIC_DIR, html=True), name="static")
    return app

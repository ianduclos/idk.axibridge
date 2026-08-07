"""FastAPI app factory: API router + static frontend + lifecycle wiring."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import logbuf
from .api import router
from .events import bus
from .machine import manager
from .registry import load_builtin_modules

#: Frontend source — the files you edit. Also what gets served when there is
#: no build (see ``frontend_dir``).
STATIC_DIR = Path(__file__).parent / "static"
#: `npm run build` output (gitignored). Vite's config points here.
DIST_DIR = Path(__file__).parent / "static_dist"


def frontend_dir() -> Path:
    """Which frontend the server hands out. **This is the whole switch:**
    the BUILT output when it exists, the SOURCE when it does not.

    No env var and no third mode, deliberately. The fallback is what lets a
    machine with no Node toolchain (the Pi) serve the UI exactly as it did
    before there was a build step — the source is real, runnable ES modules,
    not an intermediate form.

    The trap it creates is worth knowing: a STALE `static_dist/` shadows your
    edits to `static/`, so "I changed the JS and nothing happened" means
    either re-run `npm run build` or delete the build. The startup log says
    which one is live, so the answer is always one line away.
    """
    return DIST_DIR if (DIST_DIR / "index.html").is_file() else STATIC_DIR


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # ring the logs for the in-app panel — from the LIFESPAN, not create_app:
    # uvicorn applies its dictConfig between the two, which would strip the
    # handler from its propagate=False loggers (uvicorn.error / .access).
    logbuf.install()
    bus.attach_loop(asyncio.get_running_loop())
    load_builtin_modules()
    # If an AxiDraw is plugged in, grab it right away (background thread —
    # serial connect blocks ~2 s). Tests and CI set AXIBRIDGE_NO_AUTOCONNECT
    # so the suite never touches real hardware.
    if not os.environ.get("AXIBRIDGE_NO_AUTOCONNECT"):
        threading.Thread(target=manager.auto_connect, name="axibridge-autoconnect",
                         daemon=True).start()
    yield
    bus.close()  # end the SSE streams so graceful shutdown doesn't wait them out
    manager.shutdown()


class _RevalidatedStatic(StaticFiles):
    """Static files with `Cache-Control: no-cache` — the browser revalidates
    every file on every load (cheap 304s when unchanged). Without this, a
    cached index.html can pair with freshly-fetched JS modules after a server
    update: the version mix throws at module scope and the whole UI goes
    blank. The server owns cache correctness.

    Still required after the Vite port (2026-08-07), for both modes: the
    source mode is unhashed and would cache forever, and the built mode
    hashes its assets but NOT index.html — a cached index pointing at a
    deleted hash is the same blank page by another route."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app() -> FastAPI:
    app = FastAPI(title="axibridge", lifespan=_lifespan)
    app.include_router(router)
    served = frontend_dir()
    logging.getLogger("axibridge").info(
        "serving the %s frontend from %s",
        "BUILT" if served is DIST_DIR else "source", served)
    # html=True serves index.html at "/"; mounted last so /api wins.
    app.mount("/", _RevalidatedStatic(directory=served, html=True), name="static")
    return app

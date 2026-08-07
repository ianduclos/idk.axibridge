"""Entry point: ``axibridge`` or ``python -m axibridge``.

Host/port default from ~/.axibridge/settings.json (factory default: 0.0.0.0
on the uncommon port 2942 — "AXI2" on a phone keypad). Wide-open LAN binding
is a deliberate, documented choice for the Tailscale/Pi workflow; there is no
authentication in v2. CLI flags override settings.
"""

from __future__ import annotations

import argparse


def main() -> None:
    from .stores import settings_store

    s = settings_store.settings
    parser = argparse.ArgumentParser(prog="axibridge", description="AxiDraw experimental interface")
    parser.add_argument("--host", default=s.host, help=f"bind address (default {s.host})")
    parser.add_argument("--port", type=int, default=s.port, help=f"port (default {s.port})")
    args = parser.parse_args()

    import uvicorn

    from .app import create_app
    from .events import bus

    # Quitting used to cost a flat 2 s. /api/events is an SSE stream that never
    # finishes by design, and uvicorn's graceful shutdown waits for open
    # connections — the browser always holds one, so every quit sat out the
    # whole timeout (measured: 0.13 s with no client attached, 2.2 s with one).
    #
    # timeout_graceful_shutdown is the backstop. The actual fix is ending the
    # streams the moment the signal lands: uvicorn waits for connections BEFORE
    # running the app's lifespan shutdown, so closing the bus from the lifespan
    # is too late to help. handle_exit is the hook that runs first.
    class _Server(uvicorn.Server):
        def handle_exit(self, sig, frame):  # type: ignore[override]
            bus.close_threadsafe()
            super().handle_exit(sig, frame)

    config = uvicorn.Config(create_app(), host=args.host, port=args.port,
                            log_level="info", timeout_graceful_shutdown=2)
    _Server(config).run()


if __name__ == "__main__":
    main()

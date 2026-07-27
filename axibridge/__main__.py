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

    # timeout_graceful_shutdown is NOT optional here. uvicorn's default is to
    # wait forever for open connections to finish, and /api/events is an SSE
    # stream that never finishes by design — so a plain SIGTERM hung until the
    # app shell's own 5s grace ran out and SIGKILLed it. That was the whole of
    # "the app takes ages to close". Two seconds is longer than any real
    # request here and short enough that quitting feels instant.
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info",
                timeout_graceful_shutdown=2)


if __name__ == "__main__":
    main()

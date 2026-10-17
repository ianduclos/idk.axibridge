"""Freeze sheet 1 of the oehlen_intuit session as a library entry.

library/typed_drawing/oehlen_intuit_sheet1/: the four typed polylines (literal
numbers typed blind in the session) and the stork window that became the knot
(Oduella fixes 4500..4800, local metres from the window's first fix — no
lon/lat). The voice `oehlen_intuit_sheet` replays the session's operations on
these. Run once from the repo root:

    .local/gesture/.venv/bin/python tools/gesture/experiments/oehlen_intuit_freeze.py
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "tools/gesture/experiments")
sys.path.insert(0, "tools/gesture")
from gesture.kit import library as L  # noqa: E402
from oehlen_intuit_session import TYPED_L1, TYPED_L2, TYPED_L3, TYPED_L4  # noqa: E402
from oehlen_intuit_tools import stork  # noqa: E402

START, N = 4500, 300


def main():
    P = stork("Oduella")[START:START + N]
    P = P - P[0]
    data = {
        "work_frame": [300.0, 200.0],
        "typed": {"swoosh": TYPED_L1, "stub": TYPED_L2, "horizon": TYPED_L3, "feeler": TYPED_L4},
        "knot_m": np.round(P, 3).tolist(),
        "knot_place": {"centre_mm": [158.0, 150.0], "inner80_radius_mm": 22.0},
    }
    entry = {
        "id": "oehlen_intuit_sheet1", "kind": "typed_drawing", "version": 1,
        "label": "oehlen_intuit sheet 1: typed lines + a stork's nest",
        "policy": "generative",
        "provenance": {
            "typed": "typed blind as numbers during the round-12 oehlen_intuit session (2026-10-17)",
            "corpus": "animal/movebank-lifetrack-stork-sicily", "file": "stork-gps.csv",
            "individual": "Oduella + / IAB PA339 (eobs 4563)", "fixes": [START, START + N], "licence": "CC0",
            "research_file": "tools/gesture/experiments/oehlen_intuit_session.py",
        },
        "notes": "Source lines of the session's finished sheet; the voice oehlen_intuit_sheet replays the "
                 "session's operations (smooth, clip, turn, pixel stretch, knot split at its own crossings). "
                 "Log: tools/gesture/results/oehlen_intuit-2026-10-17.md",
    }
    print(L.save(entry, {"lines.json.gz": L.json_gz_bytes(data)}, overwrite=True))


if __name__ == "__main__":
    main()

"""Round-12 keeps (2026-10-18): freeze the found river's far-view stem into the library.

The `oehlen_found_river` voice read GRWL from the local corpus
(`.local/gesture/corpus/earth/grwl-vec-SB19`) at run time, so the Oehlen
found-ground piece could not become an app study (the app never reads
`.local`). Every recipe of the oehlen_found thread draws tile SB19, rank 0
(the longest single-channel main stem). This script saves exactly that stem —
the points `_stems("SB19")` computes, float64, lossless — as library entry
`river_stems/grwl_far_sb19`, plus the tile's stem count (the voice clamps
`rank` to it), and refuses to save unless the voice draws byte-identical
points from the entry and from the corpus.

    .local/gesture/.venv/bin/python tools/gesture/experiments/keeps13_river_stems.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))
from gesture import kit  # noqa: E402
from gesture.kit import arrangers_oehlen_found as A  # noqa: E402
from gesture.kit import library as L  # noqa: E402

TILE = "SB19"
RANKS = (0,)
EID = A.FAR_STEMS


def river_recipe(stems, **voice) -> dict:
    v = {"id": "oehlen_found_river", "tile": TILE, "rank": 0, "start": 0.0, "span_w": 2400, "angle": 0.0,
         "stems": stems, **voice}
    return {"kit": 1, "frame": [205.0, 297.0], "seed": 4441, "arranger": {"id": "single"},
            "parts": [{"voice": v}], "renderer": {"id": "wire", "pen": 0.3}}


def main() -> None:
    st = A._stems(TILE)
    arrays, frozen = {}, []
    for r in RANKS:
        seg, wm, q = st[r]
        name = f"{TILE}_{r}"
        arrays[name] = np.ascontiguousarray(q, dtype=np.float64)
        frozen.append({"tile": TILE, "rank": r, "segment": int(seg), "channel_w_m": float(wm), "array": name,
                       "points": int(len(q))})
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.strip()
    entry = {
        "id": EID, "kind": "river_stems", "label": "Far-view river stem (GRWL SB19, Amazon)",
        "policy": "generative",
        "provenance": {
            "corpus": "earth", "corpus_ids": [f"grwl-vec-{TILE}"], "training_sheets": [f"grwl-vec-{TILE}"],
            "rights": "GRWL V01.01, Allen & Pavelsky 2018 (Science 361:585), CC BY 4.0",
            "local_path": f".local/gesture/corpus/earth/grwl-vec-{TILE}",
            "extraction": "kit/arrangers_oehlen_found._stems: single-channel main stems (median width 150-700 m, "
                          "nchannels <= 1, lakes dropped), local equirectangular metres, resampled at w/4, "
                          "gaussian-smoothed at sigma 6 samples (1.5 w), longest first; rank 0 kept whole",
            "research_commit": commit,
            "experiment": "tools/gesture/experiments/keeps13_river_stems.py",
        },
        "notes": "The found river of the Oehlen found-ground piece (round 12): read by the oehlen_found_river "
                 "voice in place of the local corpus. Far views only (Ian 2026-10-17). Points in metres; the "
                 "voice takes a stretch, turns its principal axis horizontal and fits it to the pasted box.",
        "stems": {"n_stems": {TILE: len(st)}, "frozen": frozen},
    }
    tmp = ROOT / ".local/gesture/out/keeps13/library"
    lib = L.Library(tmp)
    lib.save(entry, {"stems.npz": L.npz_bytes(arrays)}, overwrite=True)
    # the voice must draw the very same points from the entry as from the corpus
    for voice in ({}, {"start": 0.5, "span_w": 1000}, {"angle": -25.0, "span_w": 1600}, {"rank": 3}):
        if voice.get("rank", 0) not in RANKS:
            continue
        a = kit.run(river_recipe(None, **voice))
        b = kit.run(river_recipe(EID, **voice), library=lib)
        for x, y in zip(a.inks, b.inks):
            if not np.array_equal(x.points, y.points):
                raise SystemExit(f"entry and corpus differ for {voice}")
    saved = L.save(entry, {"stems.npz": L.npz_bytes(arrays)}, overwrite=True)
    print(f"saved river_stems/{EID}: {saved['size_bytes'] / 1024:.0f} KB, {sum(f['points'] for f in frozen)} points")


if __name__ == "__main__":
    main()

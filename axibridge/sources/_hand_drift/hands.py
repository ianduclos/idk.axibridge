"""The frozen hands and dance tempo profiles (data in `hands/`).

Each `<hand>.npz` holds the transition table's next-token kind, params,
remaining length, position and source-stroke id at the research's own
rounding (stored as integers, so the round trip is exact), plus the training
strokes' lengths. The previous-token columns and the per-kind token pools are
derived here: a record's previous token is the record before it in the same
source stroke (`sid`), and the original training strokes are the even-`sid`
records. `tools/hand_drift/freeze.py` asserts that this reproduces the
research JSON exactly.

Provenance per hand is in `hands/hands.json`. Arabic hands are learned only
from generative-allowed sheets (calligraphy exercises, siyah mashq, a
petition) — never Qur'anic or devotional material, which is measure-only.
"""
from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

from .grammar import Grammar

DATA = Path(__file__).resolve().parent / "hands"
NX = ("line", "arc", "clothoid", "corner")
_P = 10_000_000
_PU = 100_000
_LOCK = threading.Lock()

HAND_IDS = ("matisse", "hokusai", "ingres", "shikasta", "nastaliq", "marden", "lichtenberg", "bubble")
ARABIC_HANDS = ("shikasta", "nastaliq")
TIMING_IDS = ("staccato", "levitation", "fluidity", "particles", "cmu_49_10", "cmu_55_mantis")


@lru_cache(maxsize=1)
def catalogue() -> dict:
    """hands.json: per-hand label, scale/spread, sheets, provenance; timing meta."""
    return json.loads((DATA / "hands.json").read_text())


def _grammar_from_arrays(name: str, a: dict, scale: dict, spread: dict) -> Grammar:
    nx_codes = np.asarray(a["nx"]).tolist()
    nx = [NX[c] for c in nx_codes]
    par_all = (np.asarray(a["par"]) / _P).tolist()
    par = [row[:1] if k == "corner" else row for k, row in zip(nx, par_all)]
    sid = np.asarray(a["sid"]).tolist()
    n = len(nx)
    p1, p2, f1, f2 = [], [], [], []
    for i in range(n):
        if i >= 1 and sid[i - 1] == sid[i]:
            p1.append(nx[i - 1])
            f1.append(list(par[i - 1]))
            if i >= 2 and sid[i - 2] == sid[i]:
                p2.append(nx[i - 2])
                f2.append(list(par[i - 2]))
            else:
                p2.append("START")
                f2.append([])
        else:
            p1.append("START")
            f1.append([])
            p2.append("START")
            f2.append([])
    trans = {"p2": p2, "p1": p1, "nx": nx, "f2": f2, "f1": f1,
             "rem": (np.asarray(a["rem"]) / _P).tolist(), "u": (np.asarray(a["u"]) / _PU).tolist(),
             "par": par, "sid": sid}
    kind_params: dict[str, list] = {k: [] for k in NX}
    for k, row, s in zip(nx, par, sid):
        if s % 2 == 0:
            kind_params[k].append(list(row))
    lengths = (np.asarray(a["stroke_lengths"]) / _P).tolist()
    return Grammar(name, trans, lengths, dict(scale), dict(spread), kind_params)


def load_hand(name: str) -> Grammar:
    """A frozen hand, pools built (cached for the process; read-only after)."""
    if name not in HAND_IDS:
        raise ValueError(f"unknown hand {name!r}")
    with _LOCK:
        return _load_hand_locked(name)


@lru_cache(maxsize=None)
def _load_hand_locked(name: str) -> Grammar:
    meta = catalogue()["hands"][name]
    with np.load(DATA / f"{name}.npz") as z:
        arrays = {k: z[k] for k in z.files}
    return _grammar_from_arrays(name, arrays, meta["scale"], meta["spread"]).warm()


def load_timing(name: str) -> dict:
    """A frozen tempo profile: t (s), speed (cm/s), phi (rad, [0, π)),
    jitter (cm), fps — the research `Timing` fields the regimes read."""
    if name not in TIMING_IDS:
        raise ValueError(f"unknown timing profile {name!r}")
    with _LOCK:
        return _load_timing_locked(name)


@lru_cache(maxsize=None)
def _load_timing_locked(name: str) -> dict:
    meta = catalogue()["timing"][name]
    with np.load(DATA / "timing.npz") as z:
        speed = z[f"{name}_speed"].astype(np.float64)
        phi = z[f"{name}_phi"].astype(np.float64)
        jitter = z[f"{name}_jitter"].astype(np.float64)
    fps = float(meta["fps"])
    t = np.arange(len(speed)) / fps
    for v in (t, speed, phi, jitter):
        v.setflags(write=False)
    return {"t": t, "speed": speed, "phi": phi, "jitter": jitter, "fps": fps, "label": meta["label"]}

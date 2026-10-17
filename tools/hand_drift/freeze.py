"""Freeze the Hand Drift bench's data into the app (one-off, re-runnable).

    .local/gesture/.venv/bin/python tools/hand_drift/freeze.py

Reads the round-7/8 research grammars and dance takes from `.local/gesture/`
(gitignored, this Mac only) and writes compact, committed copies into
`axibridge/sources/_hand_drift/hands/`:

- `<hand>.npz` — exactly what `drift_line` needs from a grammar: the
  transition table's next-token kind, params, remaining length, position and
  source-stroke id, plus training stroke lengths. Everything else the chain
  reads (previous-token kinds/params, the per-kind token pools) is derived
  from these at load time; this script asserts that the derivation
  reproduces the research JSON exactly. Values are stored as integers at the
  research's own rounding (1e-7, u at 1e-5), so the round trip is bit-exact.
  Sheet-level data (drawings, relations, start positions) are dropped: the
  drift never reads them.
- `hands.json` — per hand: label, scale/spread, training sheets, provenance.
- `timing.npz` — six dance tempo profiles (speed, wrist angle, lateral
  residual) at the research windows, float32.

Arabic hands pass the research policy gate (`calligraphy.require_generative`)
here, and the sheets are recorded so the app's test can check them against
its own allow-list. The app never reads `.local/` or `tools/`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GES = ROOT / "tools/gesture"
sys.path.insert(0, str(GES))

from gesture import calligraphy  # noqa: E402

V7 = ROOT / ".local/gesture/out/grammar_v7"
HYB = ROOT / ".local/gesture/out/hybrid_hands/grammars"
OUT = ROOT / "axibridge/sources/_hand_drift/hands"
NX = ("line", "arc", "clothoid", "corner")
P = 10_000_000          # research rounding: round(v, 7)
PU = 100_000            # u: round(v, 5)

HANDS = {
    "matisse": (V7 / "grammar_matisse.json", "Matisse", "Henri Matisse prints and drawings (SMK open data)",
                "matisse-smk.csv: public domain mark (SMK)"),
    "hokusai": (V7 / "grammar_hokusai.json", "Hokusai", "Hokusai sketches (museum open-access scans)",
                "artists manifests: open access"),
    "ingres": (V7 / "grammar_ingres.json", "Ingres", "Ingres graphite drawings (museum open-access scans)",
               "artists manifests: open access"),
    "shikasta": (HYB / "shikasta.json", "Shikasta (exercise)", "Shekasteh nasta'liq siyah mashq and a petition",
                 "calligraphy manifest: generative-allowed content types only"),
    "nastaliq": (HYB / "nastaliq.json", "Nasta'liq (exercise)", "Nasta'liq calligraphic exercises / pen trials",
                 "calligraphy manifest: generative-allowed content types only"),
    "marden": (HYB / "marden.json", "Marden", "Brice Marden drawings (MoMA open data images)",
               "artists-harvest.csv: (c) artist/estate, museum permits personal use; private research"),
    "lichtenberg": (HYB / "lichtenberg.json", "Lichtenberg", "One Lichtenberg figure, tiled 2x2",
                    "earth-physics manifest"),
    "bubble": (HYB / "bubble.json", "Bubble chamber", "One bubble-chamber print, tiled 2x2",
               "earth-physics manifest"),
}
ARABIC = ("shikasta", "nastaliq")

# label -> (file under corpus/dance, effector, window start s, window s) — experiments/gesture_timing.TAKES
TAKES = {
    "staccato": ("Staccato (Romero)", "E2-Create Stocos, Staccato take 1, right hand"),
    "fluidity": ("Fluidity (Romero)", "E2-Create Stocos, Fluidity take 1, right hand"),
    "levitation": ("Levitation (Romero)", "E2-Create Stocos, Levitation take 1, right hand"),
    "particles": ("Particles (Romero)", "E2-Create Stocos, Particles take 1, right hand"),
    "cmu_49_10": ("CMU 49_10 fold-in, curl", "CMU mocap subject 49 trial 10, right hand"),
    "cmu_55_mantis": ("CMU 55_13 praying mantis", "CMU mocap subject 55 trial 13, right hand"),
}


def _ints(values, scale) -> np.ndarray:
    a = np.asarray(values, dtype=np.float64)
    q = np.round(a * scale).astype(np.int64)
    if not np.array_equal(q / scale, a):
        raise AssertionError("value not on the research rounding grid")
    return q


def freeze_hand(key: str) -> dict:
    path, label, desc, rights = HANDS[key]
    d = json.loads(path.read_text())
    T = d["trans"]
    n = len(T["nx"])
    nx = np.array([NX.index(k) for k in T["nx"]], np.int8)
    par = np.zeros((n, 3), np.float64)
    for i, (k, row) in enumerate(zip(T["nx"], T["par"])):
        if len(row) != (1 if k == "corner" else 3):
            raise AssertionError(f"{key}: record {i} param count")
        par[i, :len(row)] = row
    arrays = {"nx": nx, "par": _ints(par, P), "rem": _ints(T["rem"], P), "u": _ints(T["u"], PU).astype(np.int32),
              "sid": np.asarray(T["sid"], np.int32), "stroke_lengths": _ints(d["stroke_lengths"], P)}
    np.savez_compressed(OUT / f"{key}.npz", **arrays)

    # the app's derivation must reproduce the research JSON exactly
    sys.path.insert(0, str(ROOT))
    from axibridge.sources._hand_drift import hands as H  # noqa: PLC0415
    g = H._grammar_from_arrays(key, dict(np.load(OUT / f"{key}.npz")), d["scale"], d["spread"])
    for col in ("p2", "p1", "nx", "f2", "f1", "rem", "u", "par", "sid"):
        a, b = g.trans[col], T[col]
        if col in ("f2", "f1", "par"):
            ok = len(a) == len(b) and all(list(x) == list(y) for x, y in zip(a, b))
        else:
            ok = list(a) == list(b)
        if not ok:
            raise AssertionError(f"{key}: derived trans[{col}] differs from research")
    if [float(x) for x in g.stroke_lengths] != d["stroke_lengths"]:
        raise AssertionError(f"{key}: stroke lengths")
    for kind in ("line", "arc", "clothoid", "corner"):
        want = [list(t[1:]) for toks in d["strokes"] for t in toks if t[0] == kind]
        got = g._kind_params(kind)
        if [list(map(float, x)) for x in got] != want:
            raise AssertionError(f"{key}: kind pool {kind} differs from the research strokes")

    sheets = list(d["meta"].get("sources", []))
    sheets = [Path(s).stem if "/" in s else s for s in sheets]
    rec = {"label": label, "description": desc, "rights": rights, "scale": d["scale"], "spread": d["spread"],
           "records": n, "strokes": len(d["strokes"]), "sheets": sheets,
           "research_file": str(path.relative_to(ROOT))}
    if key in ARABIC:
        calligraphy.require_generative([s.split("#")[0] for s in sheets])
        rec["policy"] = "generative-allowed sheets only (calligraphy.require_generative passed at freeze time)"
    return rec


def freeze_timing() -> dict:
    from experiments import gesture_timing as E  # noqa: PLC0415
    arrays, meta = {}, {}
    for key, (label, desc) in TAKES.items():
        tm = E.take_timing(label)
        arrays[f"{key}_speed"] = tm.speed.astype(np.float32)
        arrays[f"{key}_phi"] = tm.phi.astype(np.float32)
        arrays[f"{key}_jitter"] = tm.jitter.astype(np.float32)
        rel, eff, t0, dur = E.TAKES[label]
        meta[key] = {"label": label, "description": desc, "fps": float(tm.fps), "frames": int(len(tm.t)),
                     "file": rel, "effector": eff, "window_s": [t0, float(tm.t[-1])], "pauses": tm.n_pauses()}
    np.savez_compressed(OUT / "timing.npz", **arrays)
    return meta


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip()
    hands = {k: freeze_hand(k) for k in HANDS}
    import os  # noqa: PLC0415
    cwd = os.getcwd()
    os.chdir(GES)          # the experiment module resolves its corpus from the tools tree
    try:
        timing = freeze_timing()
    finally:
        os.chdir(cwd)
    (OUT / "hands.json").write_text(json.dumps({"frozen_from": commit, "hands": hands, "timing": timing},
                                               indent=1, ensure_ascii=False) + "\n")
    total = sum(p.stat().st_size for p in OUT.iterdir())
    for p in sorted(OUT.iterdir()):
        print(f"{p.name:<20} {p.stat().st_size / 1024:8.1f} KB")
    print(f"{'total':<20} {total / 1024:8.1f} KB")


if __name__ == "__main__":
    main()

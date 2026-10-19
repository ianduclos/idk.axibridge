"""S0′ guard (synthesis bench build, 2026-10-19): golden hashes of every round-16 written score.

S0′ closes the score-contract gaps in `kit/_synth.py` / `kit/_relations.py`, default-preserving:
a score that uses none of the new keys must play bit-identically. This records, before any
edit, a hash per sheet (inks exactly, plus the played log minus the event keys S0′ adds) for
every v2 score written to disk in round 16 and its integration, a few with devices laid on,
and checks them after.

    .local/gesture/.venv/bin/python tools/gesture/experiments/s0prime_golden.py record
    .local/gesture/.venv/bin/python tools/gesture/experiments/s0prime_golden.py check
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit._devices import apply_devices  # noqa: E402

OUT = HERE.parents[1] / ".local/gesture/out"
GOLDEN = OUT / "s0prime" / "golden.json"
DIRS = ("aware", "hdist", "dig", "mdoc", "lead16", "integ16", "synth")
NEW_EVENT_KEYS = {"mid", "s_uncut", "mid_src", "s_src_uncut"}          # what S0′ adds to events; not part of the old contract
DEVICES = [[{"id": "mdoc_unheard", "place": "beside"}],
           [{"id": "mdoc_staff", "place": "beside", "side": "bottom"}],
           [{"id": "mdoc_census", "place": "margin"}, {"id": "mdoc_ledger", "place": "beside"}],
           [{"id": "mdoc_provenance", "place": "beside"}],
           [{"id": "mdoc_sympathy", "place": "beside"}]]


def scores() -> list[Path]:
    out = []
    for d in DIRS:
        for p in sorted((OUT / d).rglob("*.recipe.json")):
            try:
                if json.loads(p.read_text()).get("version") == 2:
                    out.append(p)
            except json.JSONDecodeError:
                pass
    return out


def digest(sheet) -> str:
    h = hashlib.sha1()
    h.update(json.dumps(list(sheet.frame)).encode())
    for k in sheet.inks:
        h.update(np.ascontiguousarray(k.points, float).tobytes())
        h.update(json.dumps([bool(k.closed), bool(k.filled), float(k.pen),
                             {a: b for a, b in (k.meta or {}).items() if a in ("colour", "layer", "device")}],
                            sort_keys=True, default=str).encode())
    log = [{a: b for a, b in e.items() if a not in NEW_EVENT_KEYS} for e in (synth.played(sheet) or {}).get("log", [])]
    h.update(json.dumps(log, sort_keys=True, default=float).encode())
    return h.hexdigest()


def run_all() -> dict[str, str]:
    res = {}
    paths = scores()
    for i, p in enumerate(paths):
        sc = json.loads(p.read_text())
        name = str(p.relative_to(OUT))
        sh = synth.run(sc, cache=False)
        res[name] = digest(sh)
        if i % 9 == 0:                                        # a spread of sheets with devices on
            for j, devs in enumerate(DEVICES):
                res[f"{name}+dev{j}"] = digest(apply_devices(sh, devs))
        print(i + 1, "/", len(paths), name, flush=True)
    return res


def main(cmd: str):
    res = run_all()
    if cmd == "record":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(res, indent=1, sort_keys=True))
        print("recorded", len(res), "→", GOLDEN)
        return
    gold = json.loads(GOLDEN.read_text())
    bad = sorted(k for k in gold if res.get(k) != gold[k])
    missing = sorted(set(gold) - set(res))
    print(f"{len(gold) - len(bad)}/{len(gold)} identical; changed: {bad}; missing: {missing}")
    sys.exit(1 if bad or missing else 0)


if __name__ == "__main__":
    main(sys.argv[1] if sys.argv[1:] else "check")

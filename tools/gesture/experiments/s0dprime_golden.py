"""S0″ guard (synthesis bench build, 2026-10-19): golden hashes of the S2 score writers.

S0″ adds side-specific wildcard filters, `budget_group` and palettes built around locked pens. A
plain compose (nothing locked) must write and play exactly as at S2. This records, before the edit,
a hash of each written score and its played sheet for listen / ccolour / arch at the S2 review seeds.

    .local/gesture/.venv/bin/python tools/gesture/experiments/s0dprime_golden.py record
    .local/gesture/.venv/bin/python tools/gesture/experiments/s0dprime_golden.py check
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit._writers import compose  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s0prime_golden import digest  # noqa: E402

OUT = HERE.parents[1] / ".local/gesture/out"
GOLDEN = OUT / "s0dprime" / "golden.json"
FRAME = [250, 175]
CASES = ([("listen", s, {"balance": b}) for s in (15101, 15102, 15103, 15104) for b in ("one", "speakers")]
         + [("ccolour", s, {}) for s in (4541, 4542, 4543, 4544, 4545)]
         + [("arch", s, {}) for s in (15041, 15042, 15043, 15045)])


def run_all() -> dict[str, str]:
    res = {}
    for i, (w, seed, params) in enumerate(CASES):
        sc = compose(w, frame=FRAME, seed=seed, params=params)
        name = f"{w}-{seed}-" + ",".join(f"{k}={v}" for k, v in sorted(params.items()))
        res[name + ":score"] = hashlib.sha1(json.dumps(sc, sort_keys=True, default=float).encode()).hexdigest()
        res[name + ":sheet"] = digest(synth.run(sc, cache=False))
        print(i + 1, "/", len(CASES), name, flush=True)
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

"""Round 15 C `arch`: a role-coloured debug view of one sheet (which ink is which act)."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "experiments"))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_arch as ar  # noqa: E402
from gesture.kit import arrangers_ccolour as cc  # noqa: E402

ROLE = {"found": "blue-400", "made": "black", "edge": "blue-400", "container": "purple", "counter": "purple-400",
        "traverse": "red", "passer": "green", "flicker": "orange", "intruder": "magenta", None: "black"}


def debug(sheet):
    inks = [kit.core.Ink(k.points, k.closed, k.filled, k.pen, {**k.meta, "colour": ROLE.get(k.meta.get("role"), "black")})
            for k in sheet.inks]
    return cc.render_pens(kit.Sheet(sheet.frame, sheet.marks, inks, sheet.meta), px_per_mm=4)


if __name__ == "__main__":
    seed = int(sys.argv[1])
    arr = dict(a.split("=", 1) for a in sys.argv[2:])
    s = kit.run(ar.recipe(seed, **arr))
    debug(s).save(HERE.parents[1] / f".local/gesture/out/arch/debug-{seed}.jpg", quality=88)
    print({k.meta.get("role") for k in s.inks})

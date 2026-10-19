"""Round 15, lead: lay measuring devices on this round's own composed sheets
(real scores, not derived). Rebuilds results/lead15-*.jpg."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))
sys.path.insert(0, str(ROOT / "tools/gesture/experiments"))

from gesture import kit  # noqa: E402
from gesture.kit._devices import apply_devices  # noqa: E402
from meas_common import caption, render, save_budget  # noqa: E402

RES = ROOT / "tools/gesture/results"
OUT = ROOT / ".local/gesture/out/lead15"

CASES = {
    "listen15102-arcs": ("listen-2-15102.recipe.json", None,
                         [{"id": "misfit_grid", "place": "under", "pitch": 14.0, "strength": 3.0, "pen": 0.15},
                          {"id": "meas_arcs", "place": "beside", "side": "bottom", "size": 70.0}],
                         "listen 15102 over a misfit grid, with the relations its own score recorded (arcs, below)"),
    "arch15010-air": (str(ROOT / ".local/gesture/out/arch/pop-15010.recipe.json"), None,
                      [{"id": "meas_air", "place": "over"},
                       {"id": "scale_ruler", "place": "margin", "side": "bottom", "size": 18.0}],
                      "arch 15010 with the pen's flight through the air and a ruler of the drawing"),
}


def load(path, idx):
    p = Path(path) if Path(path).is_absolute() else RES / path
    r = json.loads(p.read_text())
    if isinstance(r, dict) and "panels" in r:
        r = r["panels"]
    if isinstance(r, list):
        r = r[idx or 0]
    return r.get("recipe", r)


def main(names):
    for name in names or CASES:
        path, idx, specs, cap = CASES[name]
        rec = load(path, idx)
        sheet = kit.run(rec)
        try:
            out = apply_devices(sheet, specs)
        except Exception as e:  # report and keep going
            print(name, "FAILED:", type(e).__name__, e)
            continue
        im = caption(render(out), cap)
        dst = RES / f"lead15-{name}.jpg"
        save_budget(im, dst)
        (RES / f"lead15-{name}.recipe.json").write_text(json.dumps({"recipe": rec, "devices": specs}, indent=1))
        print(name, "ok", out.frame, len(out.inks) - len(sheet.inks), "device inks")


if __name__ == "__main__":
    main(sys.argv[1:])

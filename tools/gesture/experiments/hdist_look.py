"""hdist: working contact sheets (not review images). Run from the repo root:
    .local/gesture/.venv/bin/python tools/gesture/experiments/hdist_look.py <variant> [hand ...]
Writes .local/gesture/out/hdist/look_<variant>.jpg (one cell per hand, seed 1491)."""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, "tools/gesture")
sys.path.insert(0, "tools/gesture/experiments")
from gesture import kit  # noqa: E402
import hdist_measure as HM  # noqa: E402

OUT = Path(".local/gesture/out/hdist")
LOOK = ["hokusai", "matisse", "lichtenberg", "polygon_walk", "marden", "fly_open", "river_bend", "nastaliq",
        "shikasta", "bubble", "trail_tracks", "dancer_cristel", "mime_mantis", "molnar_letters", "aaron", "ingres"]


def main(argv):
    variant = argv[0]
    hs = argv[1:] or LOOK
    ims = []
    for h in hs:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sh = kit.run(HM.recipe_for(variant, h, 1491))
        m = sh.marks[0].meta
        lab = f"{h}  {m.get('measure', '')}  {m.get('hdist', '')}"[:150]
        ims.append(kit.render_image(sh, px_per_mm=2.6, label=lab))
    kit.contact(ims, 2, title=variant).save(OUT / f"look_{variant.replace(':', '_').replace(',', '_')}.jpg", quality=80)


if __name__ == "__main__":
    main(sys.argv[1:])

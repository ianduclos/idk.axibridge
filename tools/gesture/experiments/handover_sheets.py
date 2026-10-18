"""handover (round 13, II-b): sheets — each variant drawn twice, stage-coloured and in ink.

usage: handover_sheets.py OUT.jpg 'A>B|order|seed|{json voice overrides}' ...
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, "tools/gesture")
sys.path.insert(0, "tools/gesture/experiments")
from gesture import kit
from handover_diag import stage_image

FRAME = [297, 210]


def one(spec):
    pair, order, seed, extra = (spec.split("|") + ["{}"])[:4]
    a, b = pair.split(">")
    v = {"id": "morph_handover", "hands": [a, b], "order": order, "rows": 3, "R_mm": 80}
    v.update(json.loads(extra))
    fr = v.pop("frame", FRAME)
    rec = {"label": f"{a}->{b} {order} s{seed}", "frame": fr, "seed": int(seed), "margin": 12, "voice": v}
    sh = kit.run(rec)
    lab = f"{a} -> {b}  order {order}  seed {seed}  {extra}  ({sh.marks[0].meta['handover']['segments']} segs)"
    return stage_image(sh, px_per_mm=3, label=lab), kit.render_image(sh, px_per_mm=3, label=None), rec


if __name__ == "__main__":
    out = sys.argv[1]
    ink_only = sys.argv[2] == "--ink"
    specs = sys.argv[3:] if ink_only else sys.argv[2:]
    with ProcessPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(one, specs))
    imgs = [r[1] for r in res] if ink_only else [im for r in res for im in r[:2]]
    if ink_only:
        from PIL import ImageDraw
        from gesture.kit.core import _font
        for im, r in zip(imgs, res):
            ImageDraw.Draw(im).text((8, 8), f"seed {r[2]['seed']}", fill=(0x10, 0x0F, 0x0F), font=_font(16))
    kit.contact(imgs, 2).save(out, quality=85)
    json.dump([r[2] for r in res], open(out.replace(".jpg", ".recipes.json"), "w"), indent=1)

"""handover (round 13, II-b): survey — each candidate hand alone as a travelling strip."""
import sys
sys.path.insert(0, "tools/gesture")
from gesture import kit

HANDS = sys.argv[1].split(",") if len(sys.argv) > 1 else [
    "meander69", "polygon_walk", "fly_open", "fly_fru", "river_meander", "matisse", "molnar_letters",
    "shikasta", "trail_borer", "river_oxbow", "lichtenberg", "trail_slime"]
imgs = []
for i, h in enumerate(HANDS):
    rec = {"label": h, "frame": [300, 50], "seed": 1311 + i,
           "voice": {"id": "series_travel", "hands": [h], "length": 3.0, "sheets": 1,
                     "route": [0.0, 0.03, 0.5, 1.0, 0.97, 0.5], "pull": 6.0, "scale": 0.35, "chunk": 0.15}}
    sh = kit.run(rec)
    imgs.append(kit.render_image(sh, px_per_mm=4, label=h))
    print(h, flush=True)
kit.contact(imgs, 1, title="handover survey: hands alone").save(".local/gesture/out/handover/survey.jpg", quality=85)

import sys, json, copy
sys.path.insert(0, "tools/gesture")
from gesture import kit
from gesture.kit import _synth as s
from PIL import Image
OUT = ".local/gesture/out/lead16/"

def score(seed, gain=1.6, devices=()):
    return {"version": 2, "frame": [250, 175], "seed": seed, "margin": 8,
      "layers": [
        {"id": "ground", "role": "found", "pen": "black",
         "part": {"voice": {"id": "river_zoom"}, "renderer": {"id": "wire", "pen": 0.35}}},
        {"id": "fly", "role": "listener", "pen": "blue",
         "part": {"voice": {"id": "hand", "hand": "dancer_cristel", "length": 1.6}, "renderer": {"id": "wire", "pen": 0.5}}},
        {"id": "bend", "role": "listener", "pen": "red",
         "part": {"voice": {"id": "hand", "hand": "fly_open", "length": 1.2}, "renderer": {"id": "wire", "pen": 0.5}}}],
      "relations": [
        {"id": "S", "kind": "sympathy", "src": "*", "dst": "*", "params": {"gain": gain, "reach": 6.0}},
        {"id": "A", "kind": "accompany", "src": "*", "dst": "*"},
        {"id": "X", "kind": "crossing", "src": "*", "dst": "*", "params": {"w_cross": 0.15, "w_sympathy": 0.25}}],
      "devices": list(devices)}


ims = []
for seed in range(16901, 16905):
    for aware in (False, True):
        sc = score(seed)
        if not aware:
            sc["relations"] = []
        sh = s.run(sc)
        from collections import Counter
        print(seed, aware, Counter(e["outcome"] for e in s.played(sh)["log"]))
        p = s.preview(sh, OUT + f"aw-{seed}-{int(aware)}.jpg", px_per_mm=4, label=f"{seed} " + ("sympathy + accompany + crossing" if aware else "no awareness"))
        ims.append(Image.open(p))
kit.contact(ims, 2, title="lead: awareness built to be seen (left: none; right: sympathy + accompany + crossing)").save(OUT + "contact.jpg", quality=85)

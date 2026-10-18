"""rzoom exploration: quick sheets of river_zoom variants (scratch, .local/gesture/out/rzoom/)."""
import sys, json
sys.path.insert(0, "tools/gesture")
from gesture import kit

OUT = ".local/gesture/out/rzoom/"


def sheet(frame, voice, seed=1414, pen=0.3, renderer=None):
    rec = {"frame": list(frame), "seed": seed, "margin": 8, "voice": {"id": "river_zoom", **voice},
           "renderer": renderer or {"id": "wire", "pen": pen}}
    return kit.run(rec)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "a"
    if which == "a":
        ims = []
        for course in ("free", "steer"):
            for sch in ("swell", "push", "pulses", "drift"):
                s = sheet((400, 260), {"schedule": sch, "course": course, "zoom": 24})
                m = s.marks[0]
                print(course, sch, {k: m.meta[k] for k in ("river_km", "drawn_mm", "far_mm_per_km")})
                ims.append(kit.render_image(s, px_per_mm=2.5, label=f"{course} {sch}"))
        kit.contact(ims, 4, title="rzoom a: free vs steer").save(OUT + "a.jpg", quality=85)
    if which == "b":
        ims = []
        for i, sch in enumerate(("push", "pulses", "drift", "dive", "steps", "ramp_in", "swell", "breath")):
            s = sheet((360, 260), {"schedule": sch, "course": "steer", "zoom": 48, "length_mm": 8000, "recur": 4,
                                   "far_mm_per_km": 0.5}, seed=1414 + i)
            m = s.marks[0]
            print(sch, {k: round(m.meta[k], 2) for k in ("river_km", "drawn_mm", "far_mm_per_km")})
            ims.append(kit.render_image(s, px_per_mm=3, label=f"steer {sch}"))
        kit.contact(ims, 4, title="rzoom b: zoom 48 steer").save(OUT + "b.jpg", quality=85)
    if which == "close":
        import numpy as np
        from gesture.kit.arrangers_oehlen_found import render_colour
        for sm in (0.0, 3.0):
            s = sheet((360, 260), {"schedule": "dive", "course": "steer", "zoom": 60, "length_mm": 8000,
                                   "far_mm_per_km": 0.5, "smooth_w": sm}, seed=1417)
            m = s.marks[0]
            z = m["zoom"]; i = int(np.argmax(z)); p = m.points[i]
            crop = (p[0] - 30, p[1] - 20, p[0] + 30, p[1] + 20)
            kit.preview(s, OUT + f"close_full_sm{sm}.jpg", px_per_mm=3)
            from PIL import Image
            im = kit.render_image(s, px_per_mm=40, label=None)
            im = im.crop(tuple(int(v * 40) for v in crop)); im.save(OUT + f"close_sm{sm}.jpg", quality=85)
            print("max zoom", z.max(), "at", p)
    if which == "c":
        ims = []
        for sch in ("push", "pulses", "dive", "steps"):
            for pace in (0.0, 0.4, 0.8):
                s = sheet((360, 260), {"schedule": sch, "zoom": 48, "recur": 4, "pace": pace, "far_mm_per_km": 0.5},
                          seed=1420)
                m = s.marks[0]
                print(sch, pace, {k: round(m.meta[k], 2) for k in ("river_km", "drawn_mm", "far_mm_per_km")})
                ims.append(kit.render_image(s, px_per_mm=2.5, label=f"{sch} pace {pace}  {m.meta['drawn_mm']:.0f} mm"))
        kit.contact(ims, 3, title="rzoom c: pace").save(OUT + "c.jpg", quality=85)
    if which == "d":
        from gesture.kit.arrangers_oehlen_found import render_colour
        ims = []
        for zoom in (16, 32, 64):
            s = sheet((360, 260), {"schedule": "pulses", "course": "free", "zoom": zoom, "recur": 4, "pace": 0.6},
                      seed=1420, renderer={"id": "rzoom_ink", "pens": [0.25, 0.45, 0.7], "inks": "blue,black,black"})
            m = s.marks[0]
            print(zoom, {k: round(m.meta[k], 2) for k in ("river_km", "drawn_mm", "far_mm_per_km")})
            ims.append(render_colour(s, px_per_mm=2.5))
        for pan in (0.0, 0.3, -0.4):
            s = sheet((360, 260), {"mode": "window", "frames": 5, "zoom": 20, "span_w": 1600, "pan": pan, "start": 0.2},
                      seed=1430, renderer={"id": "rzoom_ink", "pens": [0.25, 0.45, 0.7], "inks": "blue,black,black", "min_run": 0})
            ims.append(render_colour(s, px_per_mm=2.5))
        kit.contact(ims, 3, title="rzoom d: zoom 16/32/64 free + rzoom_ink; window pan 0/0.3/-0.4").save(OUT + "d.jpg", quality=85)
    if which == "e":
        from gesture.kit.arrangers_oehlen_found import save
        ink = {"id": "rzoom_ink", "pens": [0.25, 0.35, 0.5, 0.7], "inks": "blue,blue,black,black"}
        cands = {
            "e1_square_pulses": ((320, 320), {"schedule": "pulses", "zoom": 32, "recur": 5, "pace": 0.75}, 1441),
            "e2_scroll_push": ((600, 200), {"schedule": "push", "course": "free", "zoom": 24, "recur": 4, "pace": 0.5}, 1442),
            "e3_square_drift": ((320, 320), {"schedule": "drift", "zoom": 32, "recur": 4, "pace": 0.75}, 1443),
            "e4_tall_dive": ((240, 340), {"schedule": "dive", "zoom": 40, "pace": 0.7, "angle": 90}, 1444),
        }
        for name, (fr, v, sd) in cands.items():
            s = sheet(fr, {"far_mm_per_km": 0.5, **v}, seed=sd, renderer=ink)
            m = s.marks[0]
            print(name, {k: round(m.meta[k], 2) for k in ("river_km", "drawn_mm", "far_mm_per_km")})
            save(s, OUT + name + ".jpg", px_per_mm=5)
    if which == "f":
        from gesture.kit.arrangers_oehlen_found import render_colour
        ink = {"id": "rzoom_ink", "pens": [0.25, 0.35, 0.5, 0.7], "inks": "blue,blue,black,black"}
        pace = float(sys.argv[2]); zoom = float(sys.argv[3])
        ims = []
        for i, sch in enumerate(("push", "pulses", "drift", "dive", "steps", "ramp_in", "swell", "breath")):
            s = sheet((240, 340), {"schedule": sch, "zoom": zoom, "recur": 3, "pace": pace, "angle": 90,
                                   "far_mm_per_km": float(sys.argv[4])}, seed=1450 + i, renderer=ink)
            m = s.marks[0]
            print(sch, {k: round(m.meta[k], 2) for k in ("river_km", "drawn_mm", "far_mm_per_km")})
            ims.append(render_colour(s, px_per_mm=2.5))
        kit.contact(ims, 8, title=f"rzoom f: pace {pace} zoom {zoom}").save(OUT + f"f_{pace}_{zoom}_{sys.argv[4]}.jpg", quality=85)
    if which == "g":
        from gesture.kit.arrangers_oehlen_found import render_colour
        ink = {"id": "rzoom_ink", "pens": [0.25, 0.35, 0.5, 0.7], "inks": "blue,blue,black,black"}
        sch = sys.argv[2]; pace = float(sys.argv[3]); zoom = float(sys.argv[4]); recur = int(sys.argv[5])
        FR = tuple(map(float, sys.argv[6].split("x"))) if len(sys.argv) > 6 else (240, 340)
        ims = []
        for i in range(8):
            s = sheet(FR, {"schedule": sch, "zoom": zoom, "recur": recur, "pace": pace, "angle": 90,
                                   "far_mm_per_km": 0.8}, seed=1460 + i, renderer=ink)
            m = s.marks[0]
            ims.append(render_colour(s, px_per_mm=2.5))
            print(1460 + i, round(m.meta["drawn_mm"]), round(m.meta["far_mm_per_km"], 2))
        kit.contact(ims, 8, title=f"rzoom g: {sch} pace {pace} zoom {zoom} recur {recur}").save(OUT + f"g_{sch}_{pace}_{zoom}_{recur}_{FR[0]:.0f}.jpg", quality=85)
    if which == "h":
        from gesture.kit.arrangers_oehlen_found import save
        ink = {"id": "rzoom_ink", "pens": [0.25, 0.35, 0.5, 0.7], "inks": "blue,blue,black,black"}
        sch = sys.argv[2]; pace = float(sys.argv[3]); zoom = float(sys.argv[4]); recur = int(sys.argv[5]); seed = int(sys.argv[6])
        FR = tuple(map(float, sys.argv[7].split("x"))) if len(sys.argv) > 7 else (240, 340)
        s = sheet(FR, {"schedule": sch, "zoom": zoom, "recur": recur, "pace": pace, "angle": 90,
                               "far_mm_per_km": 0.8}, seed=seed, renderer=ink)
        save(s, OUT + f"h_{sch}_{pace}_{zoom}_{recur}_{seed}_{FR[0]:.0f}.jpg", px_per_mm=6)

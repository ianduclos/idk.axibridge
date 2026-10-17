"""Round 12, thread `drive` — compose drawings steered by recorded kinematics.

    .local/gesture/.venv/bin/python tools/gesture/experiments/drive_compose.py <stage> [...]

Stages write to .local/gesture/out/drive/<stage>/ (every image has its
recipe beside it). Drivers are frozen by experiments/drive_sources.py.

  width     one hand, the stork's altitude laid over 7 / 14 / 28 days, as value vs climb rate
  pens      the mosquito's steering as pen changes: thresholds, smoothing, min run
  knots     pauses: mosquito wing stops vs tropicbird sitting on the water
  hands     the same drivers on different hands (does the driver survive a change of hand?)
  pair      undriven vs driven, same hand, same seed (the honest test)
  nib       the mosquito's heading turns a broad nib
  combo     stork (regime) + mosquito (nib angle, pens) on a few hands
  seeds / stork / try_beside   tuning the piece
  pair      the honest test (undriven → each driver → piece; surrogate and calm-window controls)
  final     the five review images → tools/gesture/results/drive-*.jpg (+ recipes)
  all       everything
"""
from __future__ import annotations

import copy
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "gesture"))
warnings.filterwarnings("ignore")

from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit import renderers_drive as RD  # noqa: E402

OUT = ROOT / ".local" / "gesture" / "out" / "drive"
DAY = 86400.0


def dur(driver: str) -> float:
    return float(L.entry("drive_signal", driver)["duration_s"])


def window(driver: str, start_s: float, span_s: float) -> dict:
    """start/span shares from seconds."""
    T = dur(driver)
    return {"start": round(start_s / T, 8), "span": round(span_s / T, 8)}


# ---- driver presets (mapping params recorded in the recipe) ----

def stork_width(day0=60.0, days=14.0, lo=0.4, hi=6.0, transform="value", floor=0.08, smooth=1.0, gamma=1.0,
                side="abs"):
    m = {"id": "drive_width", "driver": "drive_stork", "channel": "alt", "transform": transform, "tau": 600.0,
         **window("drive_stork", day0 * DAY, days * DAY), "lo": lo, "hi": hi, "floor": floor,
         "smooth": smooth, "gamma": gamma, "side": side}
    if transform == "rate":
        m["norm"] = "signed"
    return m


def stork_climb(day0=60.0, days=14.0, hi=5.0, floor=0.12, gamma=1.0):
    """The stork's thermal climbs (positive climb rate) swell the line; glides and nights stay a wire."""
    return stork_width(day0=day0, days=days, hi=hi, transform="rate", floor=floor, side="pos", gamma=gamma)


def mosq_pen(t0=97.0, span=120.0, pens="black,red,blue", thr=0.25, smooth=4.0, min_run=15.0, transform="highpass",
             tau=3.0, mode="sign", driver="drive_mosquito"):
    return {"id": "drive_pen", "driver": driver, "channel": "steer", "transform": transform, "tau": tau,
            **window(driver, t0, span), "norm": "signed", "smooth": smooth, "thr": thr,
            "min_run": min_run, "pens": pens, "mode": mode, "stretch": True}


def mosq_knots(t0=97.0, span=120.0, thr=0.2, min_s=0.15, full_s=2.0):
    return {"id": "drive_knots", "driver": "drive_mosquito", "channel": "effort",
            **window("drive_mosquito", t0, span), "thr": thr, "min_s": min_s, "full_s": full_s, "smooth": 0.5}


def mosq_tremor(t0=97.0, span=120.0, amount=0.35, band=2.0, gate=2.0, channel="steer"):
    return {"id": "drive_tremor", "driver": "drive_mosquito", "channel": channel,
            **window("drive_mosquito", t0, span), "amount": amount, "band": band, "gate": gate, "smooth": 0.0}


def bird_knots(h0=0.0, hours=9.9, thr=0.1, min_min=8.0, full_min=40.0):
    return {"id": "drive_knots", "driver": "drive_tropicbird", "channel": "speed", "norm": "record",
            **window("drive_tropicbird", h0 * 3600, hours * 3600), "thr": thr, "min_s": min_min * 60,
            "merge_s": 180.0, "full_s": full_min * 60, "smooth": 0.5}


def recipe(mods, *, hand="marden", length=6.0, seed=3301, frame=(280, 200), show="hidden", layout="below",
           share=0.38, ink=None, voice=None, label=""):
    ink = ink or {"id": "drive_ink", "pen": 0.4, "knot_size": 6.0}
    return {"label": label, "seed": seed, "frame": list(frame), "margin": 6.0,
            "arranger": {"id": "drive_beside", "show": show, "layout": layout, "share": share},
            "parts": [{"voice": voice or {"id": "hand", "hand": hand, "length": length},
                       "modulators": mods, "renderer": ink}]}


def shoot(rec, path: Path, px=5.0, label=None):
    sh = kit.run(rec)
    RD.save(sh, path, px_per_mm=px, label=(label if label is not None else rec.get("label")) or None)
    return sh


def grid(name: str, items: list[tuple[str, dict]], cols: int, title: str, px=3.0):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    ims = []
    for i, (lab, rec) in enumerate(items):
        sh = kit.run(rec)
        p = d / f"{name}-{i:02d}.jpg"
        RD.save(sh, p, px_per_mm=px, label=f"{i}  {lab}")
        from PIL import Image  # noqa: PLC0415
        ims.append(Image.open(p).convert("RGB"))
    kit.contact(ims, cols, title=title).save(d / f"{name}-contact.jpg", quality=85)
    print(d / f"{name}-contact.jpg")


# ---- stages ----

def st_width():
    items = []
    for days in (7, 14, 28):
        for tr in ("value", "rate"):
            m = stork_width(days=days, transform=tr, hi=6.0 if tr == "value" else 5.0)
            if tr == "rate":
                m.update(norm="signed", floor=0.15)
            items.append((f"stork alt {tr}, {days} d", recipe([m])))
    grid("width", items, 2, "stork altitude → width, marden, seed 3301 (rows: 7 / 14 / 28 days; value | climb rate)")


def st_pens():
    w = stork_climb()
    items = []
    for t0 in (97.0, 300.0):
        for thr, sm in ((0.2, 4.0), (0.3, 8.0)):
            items.append((f"steer sign t0 {t0:.0f}s thr {thr} smooth {sm}mm",
                          recipe([w, mosq_pen(t0=t0, thr=thr, smooth=sm)])))
        items.append((f"steer envelope bands t0 {t0:.0f}s",
                      recipe([w, mosq_pen(t0=t0, transform="envelope", tau=0.5, mode="bands", smooth=6.0,
                                          pens="black,orange,blue")])))
    grid("pens", items, 3, "mosquito steering → pen changes over stork climb-rate beads (marden, seed 3301)")


def mosq_phi(t0=97.0, span=120.0, gain=0.25, phi0=35.0, smooth=1.0, max_rate=0.0, driver="drive_mosquito"):
    return {"id": "drive_phi", "driver": driver, "channel": "heading", **window(driver, t0, span),
            "gain": gain, "phi0": phi0, "smooth": smooth, "max_rate": max_rate}


def nib_ink(style="e", pen=0.4, knots="wound"):
    return {"id": "drive_ink", "pen": pen, "body": f"nib_{style}", "knots": knots, "knot_size": 6.0}


def st_nib():
    items = []
    base = {"id": "constant", "r": 1.0, "W": 3.5}
    for t0, span in ((97.0, 120.0), (430.0, 60.0)):
        for gain in (0.05, 0.25, 1.0):
            items.append((f"heading t0 {t0:.0f}s span {span:.0f}s gain {gain}, W 3.5",
                          recipe([base, mosq_phi(t0=t0, span=span, gain=gain)], hand="river_meander", length=3.5,
                                 ink=nib_ink())))
    for t0, span in ((97.0, 120.0), (430.0, 60.0)):
        w = stork_climb(hi=6.0)
        w.update(write="W", lo=1.0, floor=0.05)
        items.append((f"heading t0 {t0:.0f}s gain 0.25, W = stork climbs 1..6",
                      recipe([base, w, mosq_phi(t0=t0, span=span, gain=0.25)], hand="river_meander", length=3.5,
                             ink=nib_ink())))
    grid("nib", items, 4, "mosquito heading turns the nib (river_meander L3.5, seed 3301)")


def stork_ground(day0=60.0, days=6.0, smooth=1.5, W=3.5, fly_at=0.5, min_run=8.0, ramp=2.0):
    """Weight is being on the ground: the stork resting/walking → nib ribbon; flying → a hairline (wire)."""
    return {"id": "drive_regime", "driver": "drive_stork", "channel": "speed", "norm": "window",
            **window("drive_stork", day0 * DAY, days * DAY), "invert": True, "smooth": smooth, "stretch": False,
            "nib_at": round(1.0 - fly_at, 4), "mass_at": 1.01, "hyst": 0.04, "min_run": min_run, "W": W, "M": 7.0, "ramp": ramp}


def st_combo():
    items = []
    for hand in ("river_meander", "mime_monkey_hands"):
        for days, mr in ((4.0, 6.0), (6.0, 12.0)):
            mods = [stork_ground(days=days), mosq_phi(t0=420.0, span=100.0, gain=0.5, max_rate=mr),
                    mosq_pen(t0=420.0, span=100.0, thr=0.3, smooth=6.0, min_run=20.0)]
            items.append((f"{hand}: stork {days:.0f} d → ribbon/hairline; heading → nib (cap {mr}°/mm); steer → pens",
                          recipe(mods, hand=hand, length=3.5, ink=nib_ink())))
    grid("combo", items, 2, "stork (regime) + mosquito (nib angle, pens), seed 3301, L3.5")


def piece_mods(days=12.0, day0=60.0, phi_t0=420.0, phi_span=100.0, pen_t0=380.0, pen_span=200.0, cap=12.0,
               knots=False, W=3.5, min_run=4.0, fly_at=0.15, smooth=0.5, fly="drive_mosquito"):
    m = [stork_ground(day0=day0, days=days, W=W, min_run=min_run, fly_at=fly_at, smooth=smooth),
         mosq_phi(t0=phi_t0, span=phi_span, gain=0.5, max_rate=cap, driver=fly),
         mosq_pen(t0=pen_t0, span=pen_span, thr=0.3, smooth=6.0, min_run=20.0, driver=fly)]
    if knots:
        m.append(mosq_knots(t0=phi_t0, span=phi_span))
    return m


def st_seeds():
    items = []
    for hand in ("river_meander", "mime_monkey_hands"):
        for seed in (3301, 5120, 8846):
            items.append((f"{hand} seed {seed}", recipe(piece_mods(), hand=hand, length=3.5, seed=seed,
                                                        ink=nib_ink())))
    grid("seeds", items, 3, "piece candidates: stork 12 d → ribbon/hairline; mosquito heading → nib; steer → pens")


def st_stork():
    items = []
    for days in (8.0, 16.0):
        for fly_at in (0.12, 0.3):
            items.append((f"stork {days:.0f} d, a flight = speed above {fly_at} of the window's p98",
                          recipe(piece_mods(days=days, fly_at=fly_at), hand="river_meander", length=3.5, seed=3301,
                                 ink=nib_ink())))
    grid("stork", items, 2, "how much of the stork shows: its flights as hairlines (river_meander 3301)")


PIECE = {"hand": "river_meander", "length": 3.5, "seed": 3301, "frame": (280, 210)}
PIECE_MODS = {"days": 8.0, "fly_at": 0.12}


def st_try_beside():
    d = OUT / "beside"
    for layout, share in (("below", 0.38), ("right", 0.42), ("right", 0.5)):
        rec = recipe(piece_mods(**PIECE_MODS), ink=nib_ink(), show="beside", layout=layout, share=share, **PIECE)
        p = d / f"beside-{layout}-{share}.jpg"
        shoot(rec, p, px=5.0)
        print(p)


def st_pair():
    still = {"id": "constant", "r": 1.0, "W": 3.5, "phi": 35.0}
    pm = piece_mods(**PIECE_MODS)
    items = [
        ("the hand alone: river_meander, a broad nib held at 35°", recipe([still], ink=nib_ink(), **PIECE)),
        ("+ stork: on the ground → ribbon, in flight → hairline (8 days)", recipe([pm[0]], ink=nib_ink(), **PIECE)),
        ("+ mosquito heading turns the nib (100 s)", recipe(pm[:2], ink=nib_ink(), **PIECE)),
        ("+ mosquito steering picks the pen (200 s) = the piece", recipe(pm, ink=nib_ink(), **PIECE)),
        ("control: the mosquito replaced by its phase-randomised surrogate",
         recipe(piece_mods(fly="drive_surrogate_mosquito", **PIECE_MODS), ink=nib_ink(), **PIECE)),
        ("the real mosquito, a calm 100 s (t0 150 s)",
         recipe(piece_mods(phi_t0=150.0, pen_t0=150.0, **PIECE_MODS), ink=nib_ink(), **PIECE)),
    ]
    grid("pair", items, 3, "the honest test: one hand, one seed (3301), drivers added one at a time; then a control",
         px=2.6)


RESULTS = ROOT / "tools" / "gesture" / "results"


def _contact_with_recipes(items, cols, title, path: Path, px=2.6):
    """A review contact sheet + <stem>.recipe.json holding every tile's recipe."""
    ims, recs = [], []
    for i, (lab, rec) in enumerate(items):
        sh = kit.run(rec)
        ims.append(RD.render_colour(sh, px_per_mm=px, label=f"{i}  {lab}"))
        recs.append({"tile": i, "label": lab, "recipe": sh.recipe})
    kit.contact(ims, cols, title=title).save(path, quality=86, optimize=True)
    path.with_suffix(".recipe.json").write_text(json.dumps(recs, indent=1))
    print(path)


def st_final():
    pm = piece_mods(**PIECE_MODS)
    hidden = recipe(pm, ink=nib_ink(), show="hidden", label="drive: stork on the ground, mosquito turning", **PIECE)
    beside = recipe(pm, ink=nib_ink(), show="beside", layout="right", share=0.42,
                    label="drive: the same drawing beside its drivers", **PIECE)
    for name, rec in (("drive-1-piece", hidden), ("drive-2-piece-measured", beside)):
        p = RESULTS / f"{name}.jpg"
        shoot(rec, p, px=8.0, label="")
        print(p)
    # 3: the honest test
    still = {"id": "constant", "r": 1.0, "W": 3.5, "phi": 35.0}
    items = [
        ("the hand alone: river_meander, nib held at 35°", recipe([still], ink=nib_ink(), **PIECE)),
        ("+ stork: ground → ribbon, flight → hairline", recipe([pm[0]], ink=nib_ink(), **PIECE)),
        ("+ mosquito heading turns the nib", recipe(pm[:2], ink=nib_ink(), **PIECE)),
        ("+ mosquito steering picks the pen = the piece", recipe(pm, ink=nib_ink(), **PIECE)),
        ("control: mosquito phases randomised (same spectrum, no bursts)",
         recipe(piece_mods(fly="drive_surrogate_mosquito", **PIECE_MODS), ink=nib_ink(), **PIECE)),
        ("the real mosquito, a calm 100 s", recipe(piece_mods(phi_t0=150.0, pen_t0=150.0, **PIECE_MODS),
                                                  ink=nib_ink(), **PIECE)),
    ]
    _contact_with_recipes(items, 3, "the honest test: one hand, one seed, drivers added one at a time; then two "
                          "controls", RESULTS / "drive-3-honest-test.jpg")
    # 4: the same drivers on other hands
    items = [(f"{h} seed {sd}", recipe(pm, ink=nib_ink(), hand=h, length=3.5, seed=sd, frame=PIECE["frame"]))
             for h, sd in (("mime_monkey_hands", 8846), ("marden", 3301), ("dance_levitation", 5120),
                           ("hokusai", 3301))]
    _contact_with_recipes(items, 2, "variant: the same three drivers on other hands (does the rhythm survive a "
                          "change of hand?)", RESULTS / "drive-4-other-hands.jpg", px=3.0)
    # 5: duds
    w0 = stork_width(days=7.0, hi=6.0)
    w1 = stork_climb(days=14.0, hi=5.0)
    t1 = [dict(w0, hi=7.0, smooth=1.5),
          {"id": "drive_tremor", "driver": "drive_mosquito", "channel": "effort",
           **window("drive_mosquito", 97.0, 120.0), "amount": 0.35, "band": 2.0, "gate": 0.0, "smooth": 0.0}]
    items = [
        ("stork altitude → width: sausages (capsules)", recipe([w0], seed=3301)),
        ("stork climb rate → width: rosaries, 'still dots'", recipe([w1], seed=3301)),
        ("mosquito spin, nib gain 1.0, no cap: barbs", recipe([{"id": "constant", "r": 1.0, "W": 3.5},
                                                              mosq_phi(t0=430.0, span=60.0, gain=1.0)],
                                                             hand="river_meander", length=3.5, ink=nib_ink())),
        ("mosquito effort as ungated tremor: noise everywhere", recipe(t1, seed=3301)),
    ]
    _contact_with_recipes(items, 2, "duds kept as evidence", RESULTS / "drive-5-duds.jpg", px=3.0)


def full(t0=97.0, span=120.0, days=14.0, day0=60.0, hi=5.0, knots=True):
    m = [stork_climb(day0=day0, days=days, hi=hi), mosq_pen(t0=t0, span=span)]
    if knots:
        m.append(mosq_knots(t0=t0, span=span))
    return m


def st_hands():
    items = []
    for hand in ("marden", "river_meander", "mime_monkey_hands", "dance_levitation", "hokusai", "trail_miner"):
        for length in (3.5, 6.0):
            items.append((f"{hand} L{length}", recipe(full(), hand=hand, length=length)))
    grid("hands", items, 4, "stork climbs → width, mosquito steering → pens, mosquito wing stops → knots; per hand")


def main(argv=None):
    argv = argv or sys.argv[1:]
    stages = {"width": st_width, "pens": st_pens, "hands": st_hands, "nib": st_nib, "combo": st_combo, "seeds": st_seeds, "stork": st_stork, "try_beside": st_try_beside, "pair": st_pair, "final": st_final}
    for s in (list(stages) if argv == ["all"] else argv):
        stages[s]()


if __name__ == "__main__":
    main()

"""hdist (round 16, thread B): build the review images.

Run from the repo root:
    .local/gesture/.venv/bin/python tools/gesture/experiments/hdist_review.py [1 2 3 4 5] [--draft]
Writes tools/gesture/results/hdist-*.jpg, each with <stem>.recipe.json beside it
(--draft: .local/gesture/out/hdist/draft-*.jpg instead).
"""
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, "tools/gesture")
sys.path.insert(0, "tools/gesture/experiments")
from PIL import Image, ImageDraw  # noqa: E402

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_oehlen_found as OF  # noqa: E402
from gesture.kit.core import INK, PAPER, _font  # noqa: E402

warnings.simplefilter("ignore")
RES = Path("tools/gesture/results")
DRAFT = Path(".local/gesture/out/hdist")
MAX_PX = 2400
V1_SPEC = RES / "lcorp-1-zoom-specimen.recipe.json"     # read only: v1's panels, order and measures
OUT = {"dir": RES, "prefix": "hdist"}

V2 = {}          # the voice's defaults are v2; overrides for experiments go here


def labelled(im, text, fs=None):
    fs = fs or max(12, im.width // 60)
    strip = Image.new("RGB", (im.width, int(fs * 1.9)), PAPER)
    ImageDraw.Draw(strip).text((int(fs * 0.5), int(fs * 0.4)), text, fill=INK, font=_font(fs))
    out = Image.new("RGB", (im.width, im.height + strip.height), PAPER)
    out.paste(im, (0, 0))
    out.paste(strip, (0, im.height))
    return out


def save(im, stem, recipe):
    if max(im.size) > MAX_PX:
        k = MAX_PX / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)), Image.Resampling.LANCZOS)
    d, p = OUT["dir"], OUT["prefix"]
    path = d / f"{p}-{stem}.jpg"
    for q in (88, 82, 76, 70, 64, 58):
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < 400_000:
            break
    (d / f"{p}-{stem}.recipe.json").write_text(json.dumps(recipe, indent=1))
    print(path, im.size, path.stat().st_size // 1000, "KB", flush=True)


def v2_recipe(hand, seed=1491, frame=(480, 120), **over):
    return {"frame": list(frame), "seed": seed, "margin": 6,
            "voice": {"id": "hdist_zoom", "hand": hand, **V2, **over},
            "renderer": {"id": "lcorp_ink", "pen": 0.45}}


def v1_panels():
    return json.loads(V1_SPEC.read_text())


def hd_label(name, m):
    hd = m.meta.get("hdist", {})
    if not hd:
        return f"{name}   (unchanged: the river set v1's scales)"
    return (f"{name}   far {hd['far_on_sheet_mm']:.1f} mm/qt   zoom {hd['zoom']:.1f}   "
            f"range {hd['span']:.1f} oct")


# ---------------------------------------------------------------------------
# 1. the specimen, v2, in v1's layout
# ---------------------------------------------------------------------------

def image1():
    spec = v1_panels()
    ims, recs = [], []
    for p in spec["panels"]:
        v = p["voice"]
        if v.get("source") == "river":
            rec = p                                  # the river is the reference: unchanged
            name = "river"
        else:
            name = v["hand"]
            rec = v2_recipe(name)
        sh = kit.run(rec)
        ims.append(labelled(kit.render_image(sh, px_per_mm=2.6, label=None), hd_label(name, sh.marks[0])))
        recs.append(sh.recipe)
    sheet = kit.contact(ims, 4, title="v2: every hand zoomed at its own scales (far scale, zoom and camera from "
                                      "its scale ladder); same hands, order, seed 1491, pen 0.45 mm and cells as "
                                      "lcorp-1 (v1)")
    save(sheet, "1-specimen-v2", {"panels": recs, "v1": str(V1_SPEC)})



# ---------------------------------------------------------------------------
# 2. beside: v1 | v2, the same hands (every 5th of lcorp-1's order), seed 1491
# ---------------------------------------------------------------------------

def image2():
    spec = v1_panels()
    hands = [p["voice"]["hand"] for p in spec["panels"] if p["voice"].get("source") != "river"][::5][:8]
    by = {p["voice"].get("hand"): p for p in spec["panels"]}
    ims, recs = [], []
    for h in hands:
        s1 = kit.run(by[h])
        s2 = kit.run(v2_recipe(h))
        ims.append(labelled(kit.render_image(s1, px_per_mm=2.4, label=None), f"{h}   v1 (lcorp, one river-set scale)"))
        ims.append(labelled(kit.render_image(s2, px_per_mm=2.4, label=None), f"{h}   v2   " +
                            hd_label("", s2.marks[0]).strip()))
        recs += [s1.recipe, s2.recipe]
    sheet = kit.contact(ims, 2, title="v1 (left) beside v2 (right): every 5th hand of lcorp-1's order, seed 1491, "
                                      "pen 0.45 mm, same cell")
    save(sheet, "2-beside", {"panels": recs, "hands": hands})


# ---------------------------------------------------------------------------
# 4. the relay: hands in turn, each whole AND at its own scales
# ---------------------------------------------------------------------------

RELAY = ["river_bend", "shikasta", "trail_borer", "fly_fru"]
INKS = "black,blue,red,green"


def relay_recipe(seed, hands=RELAY, frame=(600, 150), drawn=1800.0):
    return {"frame": list(frame), "seed": seed, "margin": 8,
            "voice": {"id": "hdist_zoom", "source": "relay", "hands": list(hands), "drawn_mm": drawn},
            "renderer": {"id": "lcorp_ink", "by": "voice", "inks": INKS}}


def image4(seeds=(3001, 3002, 3003)):
    ims, recs = [], []
    for seed in seeds:
        sh = kit.run(relay_recipe(seed))
        ims.append(labelled(OF.render_colour(sh, px_per_mm=3.6), f"seed {seed}", fs=22))
        recs.append(sh.recipe)
    sheet = kit.contact(ims, 1, title="relay v2: " + " > ".join(RELAY) + " (" + INKS.replace(",", ", ") +
                                      "), each hand whole and at its own scales")
    save(sheet, "4-relay", {"panels": recs})



# ---------------------------------------------------------------------------
# 3. the plate: the 8 most distinct hands, each at its most distinct band
# ---------------------------------------------------------------------------

BANDS_JSON = DRAFT / "bands_mid.json"    # hdist_measure.bands_report(("x0.5", "x1", "x2"), "bands_mid")
BANDS_ALL = DRAFT / "bands.json"         # hdist_measure.bands_report(): every band, extremes included


def plate_choice(n=8, min_fid=0.5, path=None):
    """The n hands with the largest eye-space distinctness at their best band, among those whose lines
    at that band are self-consistent (fidelity >= min_fid: half or more of its lines sit nearest its own
    hand), skipping a hand whose nearest other is already on the plate (twins score high together)."""
    b = json.loads((path or BANDS_JSON).read_text())
    eye, pan = b["eye"], b["panel"]
    ok = [h for h, v in eye.items() if v["fidelity_best"] >= min_fid]
    ok.sort(key=lambda h: -eye[h]["best_dist"])
    out = []
    for h in ok:
        if eye[h]["nearest"].split("@")[0] in [r[0] for r in out]:
            continue
        out.append((h, eye[h]["best"], eye[h]["best_dist"], pan[h]["by_band"][eye[h]["best"]],
                    eye[h]["fidelity_best"], eye[h]["nearest"]))
        if len(out) == n:
            break
    return out


def image3(path=None, stem="3-plate", title=None):
    import hdist_measure as HM  # noqa: PLC0415
    ims, recs = [], []
    rows = plate_choice(path=path)
    for h, band, de, dp, fid, nn in rows:
        rec = v2_recipe(h, zoom=1.0, R_mm=HM.BANDS[band])
        sh = kit.run(rec)
        ims.append(labelled(kit.render_image(sh, px_per_mm=2.6, label=None),
                            f"{h}   band {band} (R = {HM.BANDS[band]:g} mm)   d' eye {de:.2f}  panel {dp:.2f}   "
                            f"self-consistent {fid:.2f}   nearest {nn.replace('@', ' ')}"))
        recs.append(sh.recipe)
    sheet = kit.contact(ims, 2, title=title or "the 8 most distinct hands, each at the middle band (x0.5, x1, x2) "
                                               "where it is most unlike every other hand at those bands; d' to the "
                                               "nearest other")
    save(sheet, stem, {"panels": recs, "rows": rows, "rule": plate_choice.__doc__})


def image7():
    """The surprise: the same rule over every band walks to the density extremes."""
    image3(BANDS_ALL, "7-extremes", "the same rule over all five bands (x0.25 to x4): the measure walks to the "
                                    "density extremes (5 of 8), and the two dense strips (fly_open, river_meander) "
                                    "read alike by eye")


# ---------------------------------------------------------------------------
# 5. the dud: per-hand scales from the quarter-turn (the first fix) vs from R
# ---------------------------------------------------------------------------

DUD_HANDS = ["polygon_walk", "trail_borer", "river_bend", "fly_fru", "ingres", "mime_monkey"]


def image5():
    ims, recs = [], []
    for h in DUD_HANDS:
        v1 = next(p for p in v1_panels()["panels"] if p["voice"].get("hand") == h)
        for rec, lab in ((v1, "v1: one far quarter-turn (the river's)"),
                         (v2_recipe(h, calib="ladder"), "first fix: own camera + own far scale, but from the "
                                                        "quarter-turn"),
                         (v2_recipe(h), "v2: own reference length (curliness kept)")):
            sh = kit.run(rec)
            ims.append(labelled(kit.render_image(sh, px_per_mm=1.9, label=None), f"{h}   {lab}"))
            recs.append(sh.recipe)
    sheet = kit.contact(ims, 3, title="the dud I learned from: calibrating every hand by its quarter-turn keeps "
                                      "them alike even with its own camera and zoom (middle); by its own size, "
                                      "they part (right)")
    save(sheet, "5-dud-quarter-turn", {"panels": recs})


# ---------------------------------------------------------------------------
# 6. a v2 score: distinct hands as layers that yield to each other
# ---------------------------------------------------------------------------

SCORE_HANDS = [("river_bend", "black"), ("trail_borer", "black"), ("shikasta", "black"), ("polygon_walk", "black"),
               ("fly_fru", "black")]


def score6(seed=16201, frame=(267.0, 180.0)):
    W, H = frame
    n = len(SCORE_HANDS)
    layers = []
    lane = 60.0                                     # lanes overlap: each hand meets its neighbours
    step = (H - 12.0 - lane) / (n - 1)
    for i, (h, pen) in enumerate(SCORE_HANDS):
        layers.append({"id": f"L{i}", "role": "speaker" if i == 0 else "listener", "pen": pen,
                       "region": [12.0, round(6.0 + i * step, 1), W - 24.0, lane],
                       "part": {"voice": {"id": "hdist_zoom", "hand": h},
                                "renderer": {"id": "lcorp_ink", "pen": 0.35}}})
    return {"version": 2, "label": "hdist: five distinct hands, overlapping lanes, the later line yields",
            "frame": [W, H], "seed": seed, "margin": 6.0, "layers": layers,
            "relations": [{"id": "R0", "kind": "yield", "src": "*", "dst": "*", "params": {"gap": 0.8, "pen": 0.35}}]}


def image6(seeds=(16201, 16202, 16203, 16204)):
    from gesture.kit import _synth as synth  # noqa: PLC0415
    ims, scores = [], []
    for sd in seeds:
        sc = score6(sd)
        sh = synth.run(sc)
        ims.append(labelled(OF.render_colour(sh, px_per_mm=4.2), f"seed {sd}", fs=20))
        scores.append(synth.played(sh)["written"] if "written" in (synth.played(sh) or {}) else sc)
    sheet = kit.contact(ims, 2, title="v2 score: " + ", ".join(h for h, _ in SCORE_HANDS) +
                                      " as layers in overlapping lanes; relation yield (the later line gives way)")
    save(sheet, "6-score", {"scores": scores})


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--draft" in sys.argv:
        OUT.update(dir=DRAFT, prefix="draft")
    for w in args or ["1"]:
        globals()[f"image{w}"]()

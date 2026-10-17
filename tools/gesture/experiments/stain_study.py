"""Mass from real stains — studies (round 12, thread 3, 2026-10-17).

    .local/gesture/.venv/bin/python tools/gesture/experiments/stain_study.py <stage>

stages:
  blot    single stains from a point over a sweep of the medium (weave,
          fibre), each with its front measured the way the corpus was
          (roughness, slope) — calibration against the photos
  approach a straight line that slows into a stain and leaves, per tide /
          tail setting (the transition alone)
Outputs .local/gesture/out/stain/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))
from gesture import kit  # noqa: E402
from gesture.kit import renderers_stain as S  # noqa: E402

OUT = ROOT / ".local/gesture/out/stain"
DIG = json.loads((ROOT / "tools/gesture/library/stain/stain_fabric/entry.json").read_text())["digest"]


def draw(polys, size_mm, px=8, pen=0.3, label=None):
    W, H = int(size_mm[0] * px), int(size_mm[1] * px)
    im = Image.new("RGB", (W, H + (22 if label else 0)), (255, 252, 240))
    d = ImageDraw.Draw(im)
    for p in polys:
        q = [(float(x * px), float(y * px)) for x, y in p]
        if len(q) > 1:
            d.line(q, fill=(16, 15, 15), width=max(1, int(round(pen * px))))
    if label:
        d.text((4, H + 4), label, fill=(80, 80, 80))
    return im


def blot(R=7.0, weave=0.8, fiber=0.55, elong=1.15, tide="mesa", seed=1, halo=0.16, tail_len=0.0,
         pitch=0.55, contrast=1.6, period=0.9, arc=0.63, schedule="density", inner=3):
    rng = np.random.default_rng(seed)
    c = np.array([R * 3.2, R * 2.1])
    if tail_len > 0:
        n = 40
        src = np.column_stack([c[0] - np.linspace(tail_len * R, 0, n), np.full(n, c[1])])
        b = R * np.linspace(0, 1, n) ** 0.7
        b[-1] = R
        k = b > 0.15
        src, b = src[k], b[k]
    else:
        src, b = c[None, :], np.array([R])
    ex = np.column_stack([c[0] + np.linspace(0.1, 2 * R, 200), np.full(200, c[1])])
    res = S.stain_event(c, src, b, R=R, dig=DIG, tide=tide, arc=arc, rim_dir=0.0, pitch=pitch,
                        contrast=contrast, halo=halo, weave=weave, fiber=fiber, elong=elong, period=period,
                        angle=0.3, sheet_seed=seed, rng=rng, exit_pts=ex,
                        schedule=schedule, inner=inner)
    path, exi, laps = res
    body = laps[-2] if halo > 0 and len(laps) > 1 else laps[-1]
    rough, slope = S.front_roughness(body)
    return path, laps, (rough, slope), c, ex[exi:]


def stage_blot():
    ims = []
    rows = []
    for weave in (0.0, 0.8, 3.0):
        for fiber in (0.15, 0.3, 0.55):
            path, laps, (rough, slope), c, rest = blot(weave=weave, fiber=fiber, seed=11)
            rows.append({"weave": weave, "fiber": fiber, "rough": rough, "slope": slope})
            ims.append(draw([path, rest], (28, 28), label=f"weave {weave} fiber {fiber}  rough {rough:.3f} slope {slope:.2f}"))
    print(json.dumps(rows, indent=0))
    print("corpus rough q", DIG["rough_q"], "slope q", DIG["rough_slope_q"])
    w, h = ims[0].size
    sheet = Image.new("RGB", (3 * w, 3 * h), "white")
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % 3) * w, (i // 3) * h))
    sheet.save(OUT / "study_blot.jpg", quality=88)


def stage_approach():
    ims = []
    for tide in ("mesa", "rim"):
        for sched in ("density", "pinned", "iso"):
            path, laps, (rough, slope), c, rest = blot(tide=tide, tail_len=1.5, seed=5, weave=0.15, fiber=0.55,
                                                       schedule=sched, R=6.0)
            inc = np.column_stack([np.linspace(0, c[0], 100), np.full(100, c[1])])
            ims.append(draw([inc, path, rest], (36, 26), label=f"{tide} {sched}"))
    w, h = ims[0].size
    sheet = Image.new("RGB", (3 * w, 2 * h), "white")
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % 3) * w, (i // 3) * h))
    sheet.save(OUT / "study_approach.jpg", quality=88)


class FakeCtx:
    """Enough of kit.Ctx to call a renderer directly on hand-made marks."""

    def __init__(self, seed=1):
        self.seed = self.sheet_seed = seed
        self._lib = kit.library

    def use(self, kind, id, purpose="generate"):
        return self._lib.load(kind, id, purpose)

    def rng(self, *tags):
        return np.random.default_rng([self.seed, *[kit.core.tag(t) for t in tags]])


def slowing_line(L=90.0, at=(0.45,), width=3.0, depth=0.97, bend=0.15, y=20.0):
    """A gentle curve whose clock slows (almost stops) at fractions `at`."""
    s = np.linspace(0, L, 900)
    pts = np.column_stack([5 + s, y + 6 * np.sin(bend * s / 6)])
    v = np.ones_like(s)
    for a in at:
        v -= depth * np.exp(-((s - a * L) / width) ** 2)
    v = np.maximum(v, 1e-3)
    t = np.r_[0, np.cumsum(np.diff(s) / (0.5 * (v[1:] + v[:-1])))]
    return kit.Mark(pts, {"dance_t": t})


def stage_transition():
    from gesture.kit.renderers_stain_particle import stain_particle  # noqa: PLC0415
    mod = kit.core.get("renderer", "stain_particle")
    base = mod.validate({})
    base.pop("id", None)
    ims = []
    variants = json.loads(sys.argv[2]) if len(sys.argv) > 2 else [
        dict(), dict(tide="rim"), dict(persist=3.0, curl=0.8), dict(persist=3.0, curl=0.8, tide="rim"),
        dict(slack=6.0, persist=2.0), dict(slack=6.0, persist=2.0, tide="rim", drift=8.0)]
    for v in variants:
        prm = {**base, **v}
        if prm["tide"] == "auto":
            prm["tide"] = "mesa"
        inks = stain_particle(FakeCtx(3), [slowing_line()], **prm)
        lab = " ".join(f"{k}={x}" for k, x in v.items()) or "defaults"
        ims.append(draw([i.points for i in inks], (100, 40), px=8, label=lab))
    w, h = ims[0].size
    sheet = Image.new("RGB", (2 * w, ((len(ims) + 1) // 2) * h), "white")
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % 2) * w, (i // 2) * h))
    sheet.save(OUT / (sys.argv[3] if len(sys.argv) > 3 else "study_transition.jpg"), quality=88)





# ---------------------------------------------------------------------------
# review images
# ---------------------------------------------------------------------------

def _panel(polys, size_mm, px, title, pen=0.3, thin=()):
    W, H = int(size_mm[0] * px), int(size_mm[1] * px)
    im = Image.new("RGB", (W, H + 34), (255, 252, 240))
    d = ImageDraw.Draw(im)
    for p in polys:
        q = [(float(x * px), float(y * px)) for x, y in p]
        if len(q) > 1:
            d.line(q, fill=(16, 15, 15), width=max(1, int(round(pen * px))))
    for p in thin:
        q = [(float(x * px), float(y * px)) for x, y in p]
        if len(q) > 1:
            d.line(q, fill=(110, 110, 105), width=1)
    d.text((6, H + 8), title, fill=(60, 60, 60), font=kit.core._font(15))
    return im


def stage_strip():
    """The process beside the piece: corpus → medium → passes → clock."""
    px = 10
    S_ = np.asarray(DIG["s_bins"])
    out = []
    # A. what the photos say: radial darkness, mesa vs tide line (s = r / R)
    W, H = 60.0, 50.0
    def curve(prof, y0):
        return np.column_stack([6 + S_ / 1.3 * (W - 12), y0 - np.asarray(prof) * 16])
    axis = [np.array([[6, 24], [W - 6, 24]]), np.array([[6, 46], [W - 6, 46]]),
            np.array([[6 + (W - 12) / 1.3, 4], [6 + (W - 12) / 1.3, 47]])]
    out.append(_panel([curve(DIG["profile_mesa"], 24), curve(DIG["profile_rim"], 46)], (W, H), px,
                      "A  755 stains: darkness vs r/R — mesa (90 %), tide line (10 %, dark arc 63 %)", thin=axis))
    # B. the medium: fronts of one blot at six times (first passage through the weave)
    rng = np.random.default_rng(12)
    R = 14.0
    U, x0, y0 = S.arrival(np.zeros((1, 2)), np.array([R]), h=R / 50, pad=1.5, period=0.9, weave=0.1, fiber=0.3,
                          elong=1.0, sheet_seed=12, rng=rng)
    fr = []
    for f in (0.15, 0.35, 0.55, 0.75, 0.9, 1.0):
        F = S._front(U, (x0, y0), R / 50, (f - 1) * R, np.zeros(2))
        if F is not None:
            fr.append(S._smooth_closed(S._resample_closed(F, 360), 1.6 * R / 50) + [30, 25])
    rough, slope = S.front_roughness(fr[-1] - [30, 25])
    out.append(_panel([np.vstack([f, f[:1]]) for f in fr], (60, 50), px,
                      f"B  the medium's fronts (rough {rough:.3f} R, slope {slope:.1f}; corpus IQR 0.036–0.12, −2.5)"))
    # C. one dwell, three lengths: the dark ring closes as the line stays longer
    polys = []
    for i, (Rk, clo) in enumerate([(5.0, 0.2), (7.5, 0.45), (10.0, 0.75)]):
        cx = 10 + [0, 16, 39][i] + Rk * 0.4
        c = np.array([cx, 25.0])
        L = np.column_stack([np.linspace(cx - 2.2 * Rk, cx + 1.8 * Rk, 200), np.full(200, 25.0)])
        k = np.flatnonzero(L[:, 0] <= cx)
        res = S.stain_event(c, L[k[-1]:k[-1] + 1], np.array([Rk]), R=Rk, dig=DIG, tide="rim", arc=0.63,
                            rim_dir=0.0, pitch=0.55, contrast=1.6, halo=0.0, weave=0.1, fiber=0.3, elong=1.0,
                            period=0.9, angle=0.4, sheet_seed=12, rng=np.random.default_rng(30 + i),
                            exit_pts=L[k[-1] + 1:], schedule="passes", pile=0.15, slip=1.5,
                            entry_pts=L[:k[-1] + 1], passes=7, closure=clo)
        path, ent, _ = res
        polys.append(np.vstack([L[:ent + 1], path, L[ent:]]))
    out.append(_panel(polys, (70, 50), px, "C  the line stays longer: the stain grows (√t) and its dark ring closes"))
    # D. the clock: time spent per mm along both hands, above the part's own median pace; the stains
    sh = kit.run({"seed": 6620, "frame": [200, 200], "voice": {"id": "dance", "trail": "levitation",
                  "effectors": "hands", "cut": "none", "seconds": 15, "t0": 15}, "renderer": {"id": "wire"}})
    tr = []
    for m in sh.marks:
        pts = np.asarray(m.points)
        s0 = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
        s = np.arange(0, s0[-1], 0.2)
        t = np.interp(s, s0, S.line_time(pts, m.channel("dance_t")))
        tr.append((s, S.dwell(s, t, 3.0), m.meta.get("joint")))
    base = 1.5 * float(np.median(np.concatenate([d for _, d, _ in tr])))   # wet = 0.5
    top = max(float(d.max()) for _, d, _ in tr) - base
    W4 = 90.0
    polys, thin = [], []
    for row, (s, D, joint) in enumerate(tr):
        Dx = np.clip(D - base, 0, None) / top
        y0 = 22 + row * 24
        xx = 4 + s / s[-1] * (W4 - 8)
        polys.append(np.column_stack([xx, y0 - np.sqrt(Dx) * 18]))
        thin.append(np.array([[4, y0], [W4 - 4, y0]]))
        ev = [e for e in S.pick_events(Dx, s, 6, sep=36.0, floor=0.0) if 12 * np.sqrt(Dx[e]) >= 1.8]
        thin += [np.array([[xx[e], y0 + 1.0], [xx[e], y0 + 3.0]]) for e in ev]
    out.append(_panel(polys, (W4, 50), px,
                      "D  levitation, both hands: √(time per mm above 1.5 × their median) — ticks: the stains",
                      thin=thin))
    Wt = sum(im.width for im in out) + 20 * (len(out) + 1)
    Ht = max(im.height for im in out) + 40
    sheet = Image.new("RGB", (Wt, Ht), (255, 252, 240))
    x = 20
    for im in out:
        sheet.paste(im, (x, 20))
        x += im.width + 20
    if sheet.width > 2400:
        sheet = sheet.resize((2400, int(sheet.height * 2400 / sheet.width)), Image.LANCZOS)
    path = OUT / "final" / "strip.jpg"
    sheet.save(path, quality=90)
    (OUT / "final" / "strip.params.json").write_text(json.dumps({
        "built_by": "tools/gesture/experiments/stain_study.py strip",
        "A": "library stain/stain_fabric digest profile_mesa / profile_rim",
        "B": {"R": 14, "h": 0.28, "weave": 0.1, "fiber": 0.3, "seed": 12, "fronts_at": [0.15, 0.35, 0.55, 0.75, 0.9, 1]},
        "C": {"R": [5, 7.5, 10], "closure": [0.2, 0.45, 0.75], "passes": 7, "pile": 0.15, "slip": 1.5, "seeds": [30, 31, 32]},
        "D": {"recipe_voice": {"trail": "levitation", "effectors": "hands", "seconds": 15, "t0": 15}, "seed": 6620,
              "window_mm": 3.0, "R": 12, "R_min": 1.8, "sep_mm": 36},
    }, indent=1))


def stage_duds():
    """Three ways the mass failed, on the same line (levitation right hand)."""
    voice = {"id": "dance", "trail": "levitation", "effectors": "rhand", "cut": "none", "seconds": 15, "t0": 15}
    recipes = {
        "fronts spiral (schedule=density): the topographic map": {"id": "stain", "schedule": "density", "tide": "mesa",
                                                                    "R": 10, "fiber": 0.45},
        "particle in its own ink: a scribble": {"id": "stain_particle", "R": 10, "slack": 3},
        "loose threads (arms=4): shards": {"id": "stain", "schedule": "pinned", "tide": "rim", "R": 10, "arms": 4.0,
                                           "inner": 2},
    }
    ims, saved = [], {}
    for lab, rend in recipes.items():
        r = {"seed": 6620, "frame": [120, 120], "voice": voice, "renderer": rend}
        sh = kit.run(r)
        ims.append(kit.render_image(sh, px_per_mm=6, label=lab))
        saved[lab] = sh.recipe
    kit.contact(ims, 3, title="stain duds — same line, three masses that failed").save(OUT / "final" / "duds.jpg",
                                                                                          quality=90)
    (OUT / "final" / "duds.recipes.json").write_text(json.dumps(saved, indent=1, default=str))


STAGES = {"blot": stage_blot, "approach": stage_approach, "transition": stage_transition, "strip": stage_strip,
          "duds": stage_duds}


if __name__ == "__main__":
    (OUT / "final").mkdir(parents=True, exist_ok=True)
    STAGES[sys.argv[1]]()

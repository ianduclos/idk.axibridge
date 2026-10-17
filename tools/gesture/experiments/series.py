"""Round 12, thread `series`: the unit is a SET of sheets.

Run from the repo root:
    .local/gesture/.venv/bin/python tools/gesture/experiments/series.py metamorphosis [seed ...]

Each series is one kit recipe whose frame is the whole row (arranger
`series_row`); `arrangers_series.run_series` cuts it into sheets. Outputs in
.local/gesture/out/series/<name>-<seed>/: the row hung on a wall
(row.jpg), every sheet at full size (sheet-<k>.jpg) with its own recipe
beside it (sheet-<k>.recipe.json = {"series": recipe, "sheet": k}) and the
row recipe (row.recipe.json).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "tools/gesture")

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_series as S  # noqa: E402

OUT = Path(".local/gesture/out/series")

# A5 portrait: plottable on the AxiDraw bed (300 × 218), narrow enough that a
# travelling line must cross an edge every ~15 cm; seven of them hang as a
# 1036 × 210 mm frieze, or fold as a leporello.
A5 = (148.0, 210.0)


def metamorphosis(seed: int = 4211, **kw) -> dict:
    """One line through seven sheets: a leaf-miner hand mines (hairline →
    widening gallery, solid at the last), pupates in a chamber, and a fly hand
    walks out of it and leaves the set through the top of the last sheet. The
    route's tempo — lingering, crossing fast — gives every sheet its own
    density; the edges cut the line wherever it happens to be."""
    N = kw.get("sheets", 7)
    sw, H = kw.get("sheet", A5)
    route = kw.get("route", [
        0.00, 0.50, 0.62,  0.03, 0.85, 0.50,                  # sheet 1: only the start
        0.06, 1.05, 0.30,  0.09, 1.50, 0.15,  0.12, 1.85, 0.60,  0.14, 2.10, 0.82,   # sheet 2: one loose sweep
        0.19, 2.80, 0.80,  0.25, 2.80, 0.22,  0.31, 2.20, 0.20,  0.36, 2.35, 0.55,  0.40, 2.75, 0.50,  # 3: a circuit
        0.44, 3.20, 0.25,  0.50, 4.00, 0.78,                  # 4: down to the chamber, ON the 4|5 edge
        0.53, 4.40, 0.60,  0.60, 5.05, 0.30,                  # 5: the fly rises, sparse
        0.66, 5.80, 0.20,  0.72, 5.80, 0.75,  0.78, 5.25, 0.80,  0.84, 5.25, 0.30,  0.90, 5.60, 0.45,  # 6: circling
        0.96, 6.30, 0.35,  1.00, 6.70, -0.40])                # 7: it leaves through the top
    at = kw.get("at", 0.5)
    return {
        "label": f"metamorphosis — seven sheets, one line (seed {seed})",
        "frame": [N * sw, H], "seed": seed, "margin": 0,
        "arranger": {"id": "series_row", "sheets": N, "at": [at], "inks": kw.get("inks", "black,black,blue"),
                     "tuck": kw.get("tuck", 13.0)},
        "parts": [
            {"label": "the line",
             "voice": {"id": "series_travel", "hands": kw.get("hands", ["trail_miner", "fly_fru"]),
                       "hand_at": [at], "fade": 0.01, "length": kw.get("length", 22.0), "sheets": N,
                       "clear": kw.get("clear", 5.0), "pull": kw.get("pull", 4.0), "chunk": kw.get("chunk", 0.4),
                       "K": kw.get("K", 16),
                       "exit": True, "route": route}},
            {"label": "the mine",
             "voice": {"id": "series_stretch"},
             "renderer": {"id": "trail_gallery", "w0": 0.3, "w1": kw.get("w1", 8.0), "grow": 1.4,
                          "chamber": kw.get("chamber", 3.2), "ramp": 1.2, "fill": kw.get("fill", "chamber"),
                          "solid_from": 0.93, "frass": kw.get("frass", "line"), "pen": 0.35}},
            {"label": "the fly",
             "voice": {"id": "series_stretch"},
             "renderer": {"id": "wire", "pen": 0.3}}],
        "renderer": {"id": "wire", "pen": 0.35}}


_PROSODY = {"id": "prosody", "rhythm": "event", "listen": "switch,corner,kappa,inflection,token,tempo",
            "contrast": 0.5, "density": 1.0, "gap": 20.0, "span": 5.0, "primary": 0.34}


def relay_sheets(seed: int = 5300, **kw) -> list[dict]:
    """A relay: on sheet k, line k calls (black, nib masses) and line k+1
    answers it (red, restated where the call is silent). On sheet k+1 that
    answer comes back unchanged in shape as the CALL, black, and a new line
    answers it. Every line is drawn twice, in two roles, on neighbouring
    sheets — the series is a chain of conversations, the hands passing from
    drawn (hokusai) to found (river, trail, fly) along the way.

    Line identity is exact, not approximate: sheet k's recipe seed is
    seed + k, so its part 1 (seed + k + 1) is sheet k+1's part 0."""
    hands = kw.get("hands", ["hokusai", "bubble", "marden", "meander69", "river_meander", "trail_miner", "fly_fru"])
    side = kw.get("side", 180.0)
    length = kw.get("length", 2.6)
    out = []
    for k in range(len(hands) - 1):
        call, answer = hands[k], hands[k + 1]
        out.append({
            "label": f"relay {k + 1}/{len(hands) - 1}: {call} calls, {answer} answers",
            "frame": [side, side], "seed": seed + k,
            "arranger": {"id": "dev_chorus", "answer_to": "all", "listen_by": "space", "radius": 15.0,
                         "answer": 0.8, "inks": "black,red", "voices": 2},
            "parts": [
                {"label": f"call: {call}",
                 "voice": {"id": "drift_tokens", "hands": [call], "length": length, "joins": "chain"},
                 "modulators": [{**_PROSODY, "unit": "pulse"}],
                 "renderer": {"id": "nib", "style": "e", "pen": 0.4}},
                {"label": f"answer: {answer}",
                 "voice": {"id": "drift_tokens", "hands": [answer], "length": length, "joins": "chain"},
                 "modulators": [{**_PROSODY, "unit": "segment", "span": 8.0}],
                 "renderer": {"id": "restate", "pen": 0.4, "copies": 8, "bound": "contour"}}],
            "renderer": {"id": "wire", "pen": 0.4}})
    return out


def build_sheets(name: str, recipes: list[dict], seed: int, *, px_per_mm: float = 6.0, row_px_per_mm: float = 2.0,
                 cols: int | None = None):
    """A series whose sheets are separate kit recipes (no shared row)."""
    t = time.time()
    d = OUT / f"{name}-{seed}"
    d.mkdir(parents=True, exist_ok=True)
    sheets = [kit.run(r) for r in recipes]
    ims = [S.render(s, px_per_mm=row_px_per_mm) for s in sheets]
    S.assemble(ims, cols=cols, gap=int(8 * row_px_per_mm), pad=int(12 * row_px_per_mm)).save(d / "row.jpg", quality=90)
    for k, s in enumerate(sheets):
        S.render(s, px_per_mm=px_per_mm).save(d / f"sheet-{k + 1}.jpg", quality=90)
        s.save_recipe(d / f"sheet-{k + 1}.recipe.json")
    print(f"{name} seed {seed}: {time.time() - t:.1f} s -> {d}")
    return sheets, d


SERIES = {"metamorphosis": metamorphosis}
SHEET_SERIES = {"relay": relay_sheets}


def build(name: str, seed: int, *, px_per_mm: float = 6.0, row_px_per_mm: float = 2.0, tag: str = "", **kw):
    rec = SERIES[name](seed, **kw)
    t = time.time()
    strip, sheets = S.run_series(rec)
    d = OUT / f"{name}{tag}-{seed}"
    d.mkdir(parents=True, exist_ok=True)
    strip.save_recipe(d / "row.recipe.json")
    ims = [S.render(s, px_per_mm=row_px_per_mm) for s in sheets]
    S.assemble(ims, gap=int(8 * row_px_per_mm), pad=int(12 * row_px_per_mm)).save(d / "row.jpg", quality=90)
    for k, s in enumerate(sheets):
        S.render(s, px_per_mm=px_per_mm).save(d / f"sheet-{k + 1}.jpg", quality=90)
        S.save_sheet_recipe(s, d / f"sheet-{k + 1}.recipe.json")
    print(f"{name} seed {seed}: {time.time() - t:.1f} s -> {d}")
    return strip, sheets, d


RESULTS = Path("tools/gesture/results")


def _hang(sheets, k, cols=None, title=None):
    ims = [S.render(s, px_per_mm=k) for s in sheets]
    return S.assemble(ims, cols=cols, gap=int(round(8 * k)), pad=int(round(12 * k)), title=title)


def _save(im, stem: str, recipe) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    assert max(im.size) <= 2400, im.size
    im.save(RESULTS / f"{stem}.jpg", quality=90, optimize=True)
    (RESULTS / f"{stem}.recipe.json").write_text(json.dumps(recipe, indent=1) + "\n")
    print(stem, im.size)


def review():
    """The ≤ 5 review images for round 12 (rebuilt from their recipes)."""
    # 1. the finished piece: the row as it would hang
    strip, sheets = S.run_series(metamorphosis(4242))
    _save(_hang(sheets, 2.15, title="metamorphosis: seven A5 sheets, one line (seed 4242)"),
          "series-metamorphosis", strip.recipe)
    # 2. two sheets at full size: the chamber sits on the edge between 4 and 5
    pair = [sheets[3], sheets[4]]
    _save(S.assemble([S.render(s, px_per_mm=7.4) for s in pair], gap=74, pad=40, numbers=False),
          "series-metamorphosis-sheets4-5", {"sheets": [s.recipe for s in pair]})
    # 3. the same series recipe at another seed
    strip2, sheets2 = S.run_series(metamorphosis(4247))
    _save(_hang(sheets2, 2.15, title="metamorphosis, the same recipe at seed 4247"),
          "series-metamorphosis-4247", strip2.recipe)
    # 4. the contrasting series: a relay (every line drawn twice, as answer then as call)
    relay = [kit.run(r) for r in relay_sheets(5310, length=1.1)]
    _save(_hang(relay, 1.95, title="relay: each red answer returns black as the next sheet's call (seed 5310)"),
          "series-relay", {"sheets": [s.recipe for s in relay]})
    # 5. the dud: the same relay with full-length lines; the recurrence drowns
    dense = [kit.run(r) for r in relay_sheets(5300)]
    _save(_hang(dense, 1.95, title="dud: relay with long lines (seed 5300); the recurring line cannot be found"),
          "series-dud-relay-dense", {"sheets": [s.recipe for s in dense]})


if __name__ == "__main__":
    if sys.argv[1:2] == ["review"]:
        review()
        sys.exit(0)
    name = sys.argv[1] if len(sys.argv) > 1 else "metamorphosis"
    seeds = [int(a) for a in sys.argv[2:]] or [4211]
    extra = {}
    for sd in seeds:
        if name in SHEET_SERIES:
            build_sheets(name, SHEET_SERIES[name](sd, **extra), sd)
        else:
            build(name, sd, **extra)

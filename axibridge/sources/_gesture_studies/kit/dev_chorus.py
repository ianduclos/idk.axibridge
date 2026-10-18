# FROZEN from research commit 9c3844a: tools/gesture/gesture/kit/dev_chorus.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Developments (round 10): call and response, mixed — a chorus.

Ian liked round-9 call-response g/h "when you start mixing it up": the leader
in masses, the follower answering in a different weight (restated line,
coils). `dev_chorus` pushes the mixing:

- any number of voices on one surface (or one band each);
- who listens to whom (`answer_to`): previous (a chain of replies, as
  `call_response`), all (each voice speaks only where EVERY earlier voice is
  silent — the stresses interleave across the whole chorus), leader (all
  answer the first voice only), none (independent: a plain polyphony that
  still carries inks);
- every part keeps its own renderer, so a nib-mass leader can be answered by
  beads (`dev_beads`), restatement, coils, or a ghost voice whose line is
  never drawn (beads answering lines);
- `inks`: one Flexoki ink per voice, recorded in the recipe; the kit preview
  is monochrome, so `render_colour(sheet)` draws the same inks in colour
  (proposed as a core change: honour Ink.meta["colour"] in render_image).

Answering reuses `prosody_arrangers.answer_mark` (the round-9 rules: a
follower stress is allowed only where the voices it listens to stay below
emphasis 0.15 over the whole stretch it would ink). A part whose modulators do
not end with `prosody` is never re-decided (it speaks as written) but is
still heard by the others (its emphasis, or r/2, counts).
"""
from __future__ import annotations

import numpy as np

from .core import INK, PAPER, P, arranger
from .prosody_arrangers import answer_mark

# Flexoki 600 accents + black (axibridge/static/css/flexoki.css, the raw scale)
FLEXOKI = {"black": "#100F0F", "red": "#AF3029", "orange": "#BC5215", "yellow": "#AD8301",
           "green": "#66800B", "cyan": "#24837B", "blue": "#205EA6", "purple": "#5E409D",
           "magenta": "#A02F6F"}


def _heard(m):
    """The mark as another voice hears it: emphasis, or r/2 when it has none."""
    if "emphasis" in m.channels:
        return m
    return m.evolve(channels={"emphasis": np.clip(np.asarray(m["r"]) / 2.0, 0.0, 1.0)})


def parse_inks(spec: str) -> list[str]:
    names = [x.strip() for x in spec.split(",") if x.strip()]
    bad = [x for x in names if x not in FLEXOKI]
    if bad:
        raise ValueError(f"dev_chorus: unknown ink(s) {bad}; choose from {sorted(FLEXOKI)}")
    return names or ["black"]


@arranger("dev_chorus", params=[
    P("answer_to", "choice", "all", "previous (chain of replies) | all (speak only where every earlier voice "
      "is silent) | leader | none (independent)", choices=("previous", "all", "leader", "none")),
    P("listen_by", "choice", "space", "space: hear what passes near on the sheet | time: along the course",
      choices=("space", "time")),
    P("radius", "float", 15.0, "space: how near another voice is heard, mm", min=0.5, max=200.0),
    P("answer", "float", 0.8, "bonus for an event beside a quiet passage / right after a call", min=0.0, max=5.0),
    P("delay", "float", 0.05, "time: how long after a call the reply may come, share of the line",
      min=0.0, max=0.5),
    P("window", "float", 0.012, "time: quiet margin either side, share of the line", min=0.0, max=0.2),
    P("layout", "choice", "single", "single: one surface | rows: one band per voice", choices=("single", "rows")),
    P("inks", "str", "black,red,blue,cyan,orange,purple", "Flexoki ink per voice, in part order (cycled)"),
    P("voices", "int", None, "sing only the first n parts (null = all); every voice answers only earlier "
      "ones, so on one surface the first n are exactly what they are in the full chorus", min=1, max=16, optional=True),
], doc="call and response for N voices, each in its own weight and ink; beads can answer lines")
def dev_chorus(ctx, parts, *, answer_to, listen_by, radius, answer, delay, window, layout, inks, voices=None):
    parse_inks(inks)
    if voices is not None:
        parts = list(parts)[:voices]
    x0, y0, W, H = ctx.box
    n = len(parts)
    placed = []
    for i, p in enumerate(parts):
        box = ctx.box if layout == "single" else (x0, y0 + i * H / n, W, H / n)
        placed.append(p.run(box))
    if answer_to != "none":
        for i in range(1, n):
            src = {"previous": [i - 1], "all": list(range(i)), "leader": [0]}[answer_to]
            lead = [_heard(m) for j in src for m in placed[j]]
            new = []
            for m in placed[i]:
                if "prosody" not in m.meta:
                    new.append(m)
                    continue
                q, info = answer_mark(m, lead, listen_by=listen_by, radius=radius, answer=answer, delay=delay,
                                      window=window)
                new.append(q.evolve(meta={"chorus": {"listens_to": src, **info}}))
            placed[i] = new
    return [m for grp in placed for m in grp]


def _hex(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def part_colours(sheet) -> dict[int, tuple]:
    rec = sheet.recipe
    arr = rec["arranger"]
    names = parse_inks(arr["inks"]) if arr.get("id") == "dev_chorus" else ["black"]
    return {i: _hex(FLEXOKI[names[i % len(names)]]) for i in range(len(rec["parts"]))}


def render_colour(sheet, *, px_per_mm: float = 6.0, label: str | None = None, ss: int = 2):
    """Like kit.render_image, but each part in its recipe ink (dev_chorus
    `inks`). Later parts are laid over earlier ones."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    from .core import _font  # noqa: PLC0415
    W, H = sheet.frame
    k = px_per_mm * ss
    cols = part_colours(sheet)
    rgb = np.ones((int(round(H * px_per_mm)), int(round(W * px_per_mm)), 3)) * np.array(PAPER, float)
    for pi in sorted({int(i.meta.get("part", 0)) for i in sheet.inks}):
        im = Image.new("L", (int(round(W * k)), int(round(H * k))), 0)
        dr = ImageDraw.Draw(im)
        for ink in sheet.inks:
            if int(ink.meta.get("part", 0)) != pi:
                continue
            q = ink.points * k
            d = max(ink.pen * k, 1.0)
            if len(q) >= 2:
                dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
            r = d / 2
            for v in (q if d > 4 else q[[0, -1]]):
                dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
        im = im.resize((rgb.shape[1], rgb.shape[0]), Image.Resampling.BOX)
        a = np.asarray(im, float)[..., None] / 255.0
        rgb = rgb * (1 - a) + np.array(cols.get(pi, INK), float) * a
    out = Image.fromarray(rgb.astype(np.uint8), "RGB")
    if label is None:
        return out
    fs = max(12, int(out.width / 80))
    strip = Image.new("RGB", (out.width, int(fs * 2.0)), PAPER)
    ImageDraw.Draw(strip).text((int(fs * 0.6), int(fs * 0.45)), label, fill=INK, font=_font(fs))
    full = Image.new("RGB", (out.width, out.height + strip.height), PAPER)
    full.paste(out, (0, 0))
    full.paste(strip, (0, out.height))
    return full

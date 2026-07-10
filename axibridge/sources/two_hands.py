"""Two hands negotiating — drawing as conversation.

Two line-agents with different characters take turns marking the sheet.
Each turn: **perceive** (pick a focus on what's already drawn — the other
hand's last stroke, or anywhere on the sheet, per ``attention``) →
**respond** (echo, complete, or contradict the local direction, per
``agreeableness``) → **mark** (a stroke in the agent's own character:
curvature habit, stroke length, lift frequency, jitter). Composition
emerges from the exchange; nothing is placed by a layout. With
agreeableness high the sheet reads as one drawing by two moods; low, as an
argument — marks blocking and crossing each other.
(See docs/IDEAS-generators.md §5.)

**Two physical pens, no new machinery**: the whole conversation is
generated deterministically from (seed, params) *regardless* of ``draw``;
the ``draw`` filter only selects whose strokes are emitted. Add two layers
with the same recipe, set one to ``hand_a`` and the other to ``hand_b``,
assign each layer its own pen — the negotiation lands on paper in two
inks, perfectly registered. Generation order is fixed (A then B, every
round) so this actually holds.
"""

from __future__ import annotations

import math
import random
from typing import Literal

from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source, report_progress

_STEP = 0.8  # mm march interval while a hand draws


class TwoHandsParams(BaseModel):
    rounds: int = Field(default=14, ge=1, le=60, title="Rounds",
                        description="Turn pairs — each round both hands mark once")
    agreeableness: float = Field(default=0.7, ge=0.0, le=1.0, title="Agreeableness",
                                 description="1 = echo and complete the other hand, "
                                             "0 = contradict and cross it")
    attention: float = Field(default=0.4, ge=0.0, le=1.0, title="Attention",
                             description="0 = respond to the last stroke, "
                                         "1 = to anywhere on the sheet")
    size: float = Field(default=150.0, ge=30.0, le=280.0, title="Size (mm)",
                        description="The square sheet the conversation happens on")
    draw: Literal["both", "hand_a", "hand_b"] = Field(
        default="both", title="Draw",
        description="Same seed = same conversation; this only filters whose "
                    "strokes are emitted (two layers + two pens = two hands)")
    a_curvature: float = Field(default=0.25, ge=0.0, le=1.0, title="Curvature",
                               description="Straight sweeps ↔ tight loops",
                               json_schema_extra={"group": "Agent A"})
    a_length: float = Field(default=40.0, ge=5.0, le=80.0, title="Stroke length (mm)",
                            json_schema_extra={"group": "Agent A"})
    a_lifts: float = Field(default=0.2, ge=0.0, le=1.0, title="Lift frequency",
                           description="How often a stroke breaks mid-thought",
                           json_schema_extra={"group": "Agent A"})
    a_jitter: float = Field(default=0.3, ge=0.0, le=1.0, title="Jitter",
                            json_schema_extra={"group": "Agent A"})
    b_curvature: float = Field(default=0.7, ge=0.0, le=1.0, title="Curvature",
                               description="Straight sweeps ↔ tight loops",
                               json_schema_extra={"group": "Agent B"})
    b_length: float = Field(default=20.0, ge=5.0, le=80.0, title="Stroke length (mm)",
                            json_schema_extra={"group": "Agent B"})
    b_lifts: float = Field(default=0.45, ge=0.0, le=1.0, title="Lift frequency",
                           description="How often a stroke breaks mid-thought",
                           json_schema_extra={"group": "Agent B"})
    b_jitter: float = Field(default=0.15, ge=0.0, le=1.0, title="Jitter",
                            json_schema_extra={"group": "Agent B"})
    seed: int = Field(default=0, ge=0, le=99999, title="Seed",
                      json_schema_extra={"group": "Fine tuning"})


class _Hand:
    def __init__(self, curvature: float, length: float, lifts: float, jitter: float):
        self.curvature = curvature
        self.length = length
        self.lifts = lifts
        self.jitter = jitter


@register_source
class TwoHands(SourceModule):
    id = "two_hands"
    label = "Two hands (negotiation)"
    description = ("Two line-agents take turns responding to each other's marks — echoing, "
                   "completing, contradicting. The composition is the conversation.")
    Params = TwoHandsParams

    def generate(self, params: TwoHandsParams) -> PathDocument:
        p = params
        rng = random.Random(p.seed)
        hands = {
            "a": _Hand(p.a_curvature, p.a_length, p.a_lifts, p.a_jitter),
            "b": _Hand(p.b_curvature, p.b_length, p.b_lifts, p.b_jitter),
        }
        # the sheet: every stroke ever drawn, tagged by hand — the strokes
        # are the conversation state both agents perceive
        strokes: list[tuple[str, list[tuple[float, float]]]] = []
        for rnd in range(p.rounds):
            report_progress(rnd / p.rounds, "negotiating")
            for who in ("a", "b"):
                start, heading = self._respond(strokes, p, rng)
                pieces = self._mark(hands[who], start, heading, p.size, rng)
                strokes.extend((who, piece) for piece in pieces)
        wanted = {"both": ("a", "b"), "hand_a": ("a",), "hand_b": ("b",)}[p.draw]
        paths = [Path(points=pts, filled=False) for who, pts in strokes
                 if who in wanted and len(pts) >= 2]
        return PathDocument(
            layers=[Layer(id=1, name="two hands", color="#26241f", paths=paths)],
            width=p.size, height=p.size, source=f"two_hands {p.draw}",
        )

    def _respond(self, strokes, p: TwoHandsParams, rng: random.Random):
        """Perceive the sheet, choose where and how to answer."""
        if not strokes:  # opening statement: somewhere near the middle
            x = p.size * (0.35 + 0.3 * rng.random())
            y = p.size * (0.35 + 0.3 * rng.random())
            return (x, y), rng.random() * math.tau
        # perceive: the last stroke, or (with prob = attention) any stroke
        _, focus_pts = strokes[-1] if rng.random() > p.attention \
            else strokes[rng.randrange(len(strokes))]
        i = rng.randrange(len(focus_pts))
        fx, fy = focus_pts[i]
        j0, j1 = max(i - 2, 0), min(i + 2, len(focus_pts) - 1)
        tx, ty = focus_pts[j1][0] - focus_pts[j0][0], focus_pts[j1][1] - focus_pts[j0][1]
        tangent = math.atan2(ty, tx) if (tx or ty) else rng.random() * math.tau
        agree = rng.random() < p.agreeableness
        side = 1 if rng.random() < 0.5 else -1
        if agree and rng.random() < 0.4:
            # complete: pick up just past the focus stroke's end, same direction
            ex, ey = focus_pts[-1]
            ex2, ey2 = focus_pts[max(len(focus_pts) - 3, 0)]
            end_tan = math.atan2(ey - ey2, ex - ex2) if (ex != ex2 or ey != ey2) else tangent
            gap = 1.5 + 3.0 * rng.random()
            return ((ex + gap * math.cos(end_tan), ey + gap * math.sin(end_tan)),
                    end_tan + (rng.random() - 0.5) * 0.3)
        if agree:
            # echo: start a few mm to the side, run parallel
            off = 3.0 + 5.0 * rng.random()
            nx, ny = -math.sin(tangent) * side, math.cos(tangent) * side
            return ((fx + nx * off, fy + ny * off),
                    tangent + (rng.random() - 0.5) * 0.4)
        # contradict: approach from the side and cross the focus at the mark
        heading = tangent + side * (math.pi / 2 + (rng.random() - 0.5) * 0.6)
        back = 6.0 + 6.0 * rng.random()
        return ((fx - back * math.cos(heading), fy - back * math.sin(heading)), heading)

    def _mark(self, hand: _Hand, start, heading: float, size: float,
              rng: random.Random) -> list[list[tuple[float, float]]]:
        """One turn's stroke in the hand's own character; lifts may split it."""
        x, y = start
        x = min(max(x, 2.0), size - 2.0)
        y = min(max(y, 2.0), size - 2.0)
        curl = 1 if rng.random() < 0.5 else -1
        phase = rng.random() * math.tau
        n = max(int(hand.length / _STEP), 3)
        lift_at = {rng.randrange(n // 4, n) for _ in range(2)
                   if rng.random() < hand.lifts}
        pieces: list[list[tuple[float, float]]] = [[(x, y)]]
        for i in range(n):
            # character: a habitual curl plus a slower S-modulation, then noise
            heading += hand.curvature * 0.16 * (0.5 * curl + 0.8 * math.sin(i * 0.07 + phase))
            heading += (rng.random() - 0.5) * 0.45 * hand.jitter
            nx_ = x + _STEP * math.cos(heading)
            ny_ = y + _STEP * math.sin(heading)
            # the sheet edge: steer back toward the middle, don't clip
            if not (2.0 <= nx_ <= size - 2.0 and 2.0 <= ny_ <= size - 2.0):
                to_c = math.atan2(size / 2 - y, size / 2 - x)
                heading = to_c + (rng.random() - 0.5) * 0.8
                nx_ = x + _STEP * math.cos(heading)
                ny_ = y + _STEP * math.sin(heading)
            x, y = nx_, ny_
            if i in lift_at:  # pen up for a couple of mm — a breath, mid-thought
                x = min(max(x + 2.5 * math.cos(heading), 2.0), size - 2.0)
                y = min(max(y + 2.5 * math.sin(heading), 2.0), size - 2.0)
                pieces.append([(x, y)])
            else:
                pieces[-1].append((x, y))
        return [piece for piece in pieces if len(piece) >= 2]

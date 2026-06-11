"""Worked example of a minimal Effect module: multipass retracing.

The simplest possible effect — shows the full contract in ~20 lines. Each
path is retraced back and forth N times as one continuous polyline, so the
pen never lifts between passes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect


class MultipassParams(BaseModel):
    count: int = Field(default=2, ge=1, le=20, title="Passes",
                       description="Draw each path this many times, alternating direction")


@register_effect
class Multipass(EffectModule):
    id = "multipass"
    label = "Multipass"
    description = "Retrace every path N times — heavier ink, embossing experiments."
    Params = MultipassParams

    def apply(self, paths: list[Path], params: MultipassParams, ctx: EffectContext) -> list[Path]:
        out: list[Path] = []
        for path in paths:
            run = list(path.points)
            for i in range(1, params.count):
                # odd extra passes retrace backwards, even ones forwards;
                # [1:] skips the point we are already standing on
                leg = path.points[::-1] if i % 2 else list(path.points)
                run += leg[1:]
            out.append(Path(points=run, filled=path.filled))
        return out

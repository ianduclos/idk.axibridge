"""Hand — redraw any layer as one of the frozen Gesture Studies hands.

Each path is an intention; the chosen library hand follows it, wandering off
by up to `stray_mm` in its own bends (`bend_mm`). The work is done by
`effects/_hand/engine.py`; this module is the parameters and the plumbing.
Pure and deterministic: seeded from `seed` and `ctx.seed`, one stream per path.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect
from ..sources._gesture_studies import frozen_library as FL
from ._hand.engine import follow, load_hand

log = logging.getLogger(__name__)
_unknown_logged: set[str] = set()
_stale_pin_logged: set[str] = set()


@lru_cache(maxsize=8)
def _hashes(snapshot_id: str) -> dict[str, str]:
    """{hand id: hash} of every hand a control may offer in one snapshot."""
    return {o["id"]: o["hash"] for o in FL.options("hand", snapshot_id)}


def _current_hash(hand_id: str) -> str | None:
    """The current snapshot's hash for `hand_id`, or None (unknown, withdrawn,
    or the library can't be read). Cheap: the index, the snapshot and this
    table are all cached, and it runs on every kept effect edit."""
    try:
        return _hashes(FL.current_snapshot()).get(hand_id)
    except Exception:   # never let a library problem block an edit
        return None


class HandParams(BaseModel):
    hand: str = Field(default="matisse", pattern=r"^[a-z0-9_]{1,64}$", title="Hand",
                      description="Whose hand redraws the line",
                      json_schema_extra={"format": "library-hand"})
    stray_mm: float = Field(default=3.0, ge=0.1, le=30.0, title="Stray (mm)",
                            description="How far the hand may wander from your line")
    bend_mm: float = Field(default=20.0, ge=3.0, le=200.0, title="Bend size (mm)",
                           description="Size of the hand's own bends")
    wander: bool = Field(default=False, title="Let it wander",
                         description="Let it wander — looser, longer departures")
    seed: int = Field(default=0, ge=0, le=99999, title="Seed",
                      json_schema_extra={"group": "Fine tuning"})
    step: float = Field(default=0.3, ge=0.1, le=2.0, title="Step (mm)",
                        description="Output point spacing",
                        json_schema_extra={"group": "Fine tuning"})
    pin: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,64}@[0-9a-f]{12}$",
                            json_schema_extra={"hidden": True})


@register_effect
class HandEffect(EffectModule):
    id = "hand"
    label = "Hand"
    description = "Redraws the layer as one of your Gesture Studies hands following the line."
    Params = HandParams

    def complete_params(self, params: dict[str, Any],
                        previous: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Pin the chosen hand at Keep, and keep that pin while the hand is
        unchanged (a refreeze never changes a kept layer). In order: a pin
        that names the hand stays; else a pin naming the hand on one of the
        layer's previous Hand steps is carried over (an edit that omits the
        pin — an agent's patch, a preset or defaults applied — keeps it, and
        matching by hand survives reorder and add); else the current
        snapshot's hash; an unknown hand is left unpinned."""
        hand = params.get("hand", HandParams.model_fields["hand"].default)
        if not isinstance(hand, str):
            return params
        pin = params.get("pin")
        if isinstance(pin, str) and pin.partition("@")[0] == hand:
            return params
        out = {k: v for k, v in params.items() if k != "pin"}
        for prev in previous or ():
            old = prev.get("pin") if isinstance(prev, dict) else None
            if isinstance(old, str) and old.partition("@")[0] == hand:
                out["pin"] = old
                return out
        h = _current_hash(hand)
        if h is not None:
            out["pin"] = f"{hand}@{h}"
        return out

    def apply(self, paths: list[Path], params: HandParams, ctx: EffectContext) -> list[Path]:
        pin_hash = None
        if params.pin:
            pid, _, h = params.pin.partition("@")
            if pid == params.hand:
                pin_hash = h
        grammar = load_hand(params.hand, pin_hash)
        if grammar is None and pin_hash is not None:
            # the pinned version is gone (the library is append-only, so this
            # is rare): draw with the current one rather than silently not at all
            grammar = load_hand(params.hand, None)
            if grammar is not None and params.pin not in _stale_pin_logged:
                _stale_pin_logged.add(params.pin)
                log.warning("hand effect: pinned %s is not in the library; using the current %r",
                            params.pin, params.hand)
        if grammar is None:
            if params.hand not in _unknown_logged:
                _unknown_logged.add(params.hand)
                log.warning("hand effect: hand %r not available; layer left unchanged", params.hand)
            return [Path(points=list(p.points), filled=p.filled) for p in paths]
        base_seed = (params.seed * 31 + ctx.seed) & 0x7FFFFFFF
        out: list[Path] = []
        for idx, path in enumerate(paths):
            if len(path.points) < 2:
                out.append(Path(points=list(path.points), filled=path.filled))
                continue
            rng = np.random.default_rng([base_seed, idx])
            pts = follow(np.asarray(path.points, dtype=float), path.is_closed, grammar, rng,
                         params.stray_mm, params.bend_mm, params.wander, params.step)
            new = [(float(x), float(y)) for x, y in pts]
            if path.is_closed and new:
                new[-1] = new[0]
            out.append(Path(points=new, filled=path.filled))
        return out

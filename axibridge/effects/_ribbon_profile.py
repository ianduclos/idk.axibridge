"""Deterministic width profiles for the open-path ribbon effect.

The baseline algorithms are a direct port of the ribbon geometry study.  Keep
this module independent of path geometry so profile generation can be tested
and evolved without involving the effect's sampling code.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any


_UINT32_MASK = 0xFFFFFFFF


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mix(a: float, b: float, amount: float) -> float:
    return a + (b - a) * amount


def _smooth(amount: float) -> float:
    return amount * amount * (3.0 - 2.0 * amount)


class _Mulberry32:
    """JavaScript-compatible unsigned Mulberry32 stream."""

    def __init__(self, seed: int) -> None:
        self._state = int(seed) & _UINT32_MASK

    def __call__(self) -> float:
        self._state = (self._state + 0x6D2B79F5) & _UINT32_MASK
        value = self._state
        value = _imul(value ^ (value >> 15), 1 | value)
        value = ((value + _imul(value ^ (value >> 7), 61 | value)) ^ value) & _UINT32_MASK
        value ^= value >> 14
        return (value & _UINT32_MASK) / 4294967296.0


def _imul(a: int, b: int) -> int:
    """The unsigned bits of JavaScript Math.imul()."""

    return ((a & _UINT32_MASK) * (b & _UINT32_MASK)) & _UINT32_MASK


def _number(params: dict[str, Any], key: str, fallback: float) -> float:
    value = params.get(key, fallback)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if math.isfinite(result) else fallback


class _Profile:
    def __init__(
        self,
        knots: list[dict[str, float]],
        smoothing_radius: float = 0.0,
        radius_scales: list[float] | None = None,
    ) -> None:
        self.knots = knots
        self.smoothing_radius = smoothing_radius
        self.smoothingRadius = smoothing_radius  # reference spelling for diagnostics
        self.smoothing_scales = radius_scales
        self._radius_midpoints = [
            (a["s"] + b["s"]) * 0.5
            for a, b in zip(knots, knots[1:])
        ]
        self._total = knots[-1]["s"] if knots else 0.0
        self._areas = [0.0]
        for a, b in zip(knots, knots[1:]):
            self._areas.append(
                self._areas[-1] + (b["s"] - a["s"]) * (a["v"] + b["v"]) / 2.0
            )

    def _interval(self, at: float) -> int:
        lo, hi = 0, len(self.knots) - 1
        while hi - lo > 1:
            mid = (lo + hi) >> 1
            if self.knots[mid]["s"] < at:
                lo = mid
            else:
                hi = mid
        return lo

    def _integral(self, at: float) -> float:
        if at < 0.0:
            at = -at
        if at > self._total:
            at = 2.0 * self._total - at
        index = self._interval(at)
        a, b = self.knots[index], self.knots[index + 1]
        length = b["s"] - a["s"]
        amount = _clamp((at - a["s"]) / (length or 1.0), 0.0, 1.0)
        return self._areas[index] + length * (
            a["v"] * amount
            + (b["v"] - a["v"]) * (amount**3 - 0.5 * amount**4)
        )

    def _radius_at(self, at: float) -> float:
        if self.smoothing_scales is None:
            return self.smoothing_radius
        midpoints = self._radius_midpoints
        if at <= midpoints[0]:
            return self.smoothing_radius * self.smoothing_scales[0]
        if at >= midpoints[-1]:
            return self.smoothing_radius * self.smoothing_scales[-1]
        lo, hi = 0, len(midpoints) - 1
        while hi - lo > 1:
            middle = (lo + hi) >> 1
            if midpoints[middle] < at:
                lo = middle
            else:
                hi = middle
        amount = _smooth((at - midpoints[lo]) / (midpoints[hi] - midpoints[lo]))
        scale = _mix(self.smoothing_scales[lo], self.smoothing_scales[hi], amount)
        return self.smoothing_radius * scale

    def __call__(self, at: float) -> float:
        if self._total <= 0.0 or len(self.knots) < 2:
            return 0.0
        at = _clamp(float(at), 0.0, self._total)
        radius = self._radius_at(at)
        if radius > 0.0:
            value = (self._integral(at + radius) - self._integral(at - radius)) / (2.0 * radius)
            return _clamp(value, 0.0, 1.0)
        index = self._interval(at)
        a, b = self.knots[index], self.knots[index + 1]
        amount = _clamp((at - a["s"]) / (b["s"] - a["s"] or 1.0), 0.0, 1.0)
        return _mix(a["v"], b["v"], _smooth(amount))


def _radius_scales(interval_count: int, seed: int, variation: float) -> list[float] | None:
    if variation <= 0.0:
        return None
    # A separate stream means this option cannot move or resize profile knots.
    random = _Mulberry32((seed & _UINT32_MASK) ^ 0xD1B54A35)
    amount = _clamp(variation, 0.0, 1.0)
    return [1.0 + (random() - 0.5) * 0.3 * amount for _ in range(interval_count)]


def _profile_from_knots(
    knots: list[dict[str, float]], radius: float = 0.0, *, smoothing_seed: int = 0,
    smoothing_variation: float = 0.0,
) -> _Profile:
    return _Profile(
        knots,
        radius,
        _radius_scales(len(knots) - 1, smoothing_seed, smoothing_variation),
    )


def _legacy_profile(total: float, opts: dict[str, Any], random: Callable[[], float],
                    guide: list[dict[str, float]] | None = None) -> _Profile:
    if total <= 0.0:
        return _profile_from_knots([{"s": 0.0, "v": 0.0}, {"s": 0.0, "v": 0.0}])
    knots: list[dict[str, float]] = [{"s": 0.0, "v": 0.0}]
    station = 0.0
    index = 0
    variation = opts["variation"]
    while station < total:
        guided = guide[index] if guide is not None and index < len(guide) else None
        spacing = guided["spacing"] if guided else 1.0 + (random() - 0.5) * 0.5 * variation
        station = min(total, station + opts["wavelength"] * 0.5 * spacing)
        crest = index % 2 == 0
        regular = 0.86 if crest else 0.21
        amplitude = (
            guided["amplitude"] if guided else
            regular + (random() - 0.5) * (0.28 if crest else 0.14) * variation
        )
        if not guided and crest and random() < 0.22 * variation:
            amplitude *= 0.45 + random() * 0.2
        amplitude = _clamp(amplitude, 0.3 if crest else 0.12, 1.0 if crest else 0.3)
        knots.append({"s": station, "v": amplitude, "spacing": spacing, "amplitude": amplitude})
        index += 1
    knots[-1]["s"] = total
    knots[-1]["v"] = 0.0
    return _profile_from_knots(knots)


def _crest_profile(total: float, opts: dict[str, Any], seed: int) -> _Profile:
    spacing = opts["spacing_variation"]
    height = opts["height_variation"]
    phrasing = opts["phrasing"]
    spacing_push = _smooth(_clamp((spacing - 0.5) * 2.0, 0.0, 1.0))
    height_push = _smooth(_clamp((height - 0.5) * 2.0, 0.0, 1.0))

    def height_contrast(value: float) -> float:
        power = 1.0 + 2.5 * height_push
        a, b = value**power, (1.0 - value) ** power
        return _clamp(a / (a + b), 0.015, 1.0)

    wave = max(1.0, opts["wavelength"])
    unsigned_seed = seed & _UINT32_MASK
    rhythm = _Mulberry32(unsigned_seed ^ 0xA341316C)
    heights = _Mulberry32(unsigned_seed ^ 0xC8013EA4)
    structure = _Mulberry32(unsigned_seed ^ 0xAD90777D)
    count = max(1, min(4096, math.floor(total / wave + 0.5)))
    motif = [0.4 + structure() * 1.1 for _ in range(3)]
    events: list[dict[str, float]] = []
    phrase_left = phrase_size = accent = 0
    phrase_gain = pace = 1.0
    for index in range(count):
        if phrase_left == 0:
            phrase_size = 3 + math.floor(structure() * 3.0)
            phrase_left = phrase_size
            accent = math.floor(structure() * min(phrase_size, count - index))
            phrase_gain = 0.82 + structure() * 0.18
            pace = 0.65 + structure() * 0.7
        position = phrase_size - phrase_left
        phrase_left -= 1
        local_span = 0.25 + rhythm() * 1.5
        phrase_span = pace * motif[position % len(motif)]
        span = _clamp(
            _mix(1.0, _mix(local_span, phrase_span, phrasing), spacing) ** (1.0 + 2.5 * spacing_push),
            0.18, 3.5,
        )
        skew = (rhythm() - 0.5) * 0.5 * spacing
        free_height = 0.08 + heights() * 0.92
        hierarchy = phrase_gain * (1.0 if position == accent else 0.12 + heights() * 0.73)
        peak = height_contrast(_mix(0.86, _mix(free_height, hierarchy, phrasing), height))
        trough = height_contrast(_mix(0.21, 0.07 + heights() * 0.2, height))
        events.append({"span": span, "skew": skew, "peak": peak, "trough": trough})
    for index, event in enumerate(events):
        next_peak = events[index + 1]["peak"] if index + 1 < len(events) else event["peak"]
        event["trough"] = min(event["trough"], 0.65 * event["peak"], 0.65 * next_peak)
    scale = max(0.0, total) / sum(event["span"] for event in events)
    knots = [{"s": 0.0, "v": 0.0}]
    station = 0.0
    for index, event in enumerate(events):
        length = event["span"] * scale
        knots.append({"s": station + length * (0.5 + event["skew"]), "v": event["peak"]})
        station += length
        last = index == len(events) - 1
        knots.append({"s": total if last else station, "v": 0.0 if last else event["trough"]})
    radius = min(wave * opts["crest_softening"], total * 0.04)
    return _profile_from_knots(
        knots, radius, smoothing_seed=seed,
        smoothing_variation=opts["smoothing_variation"],
    )


def _related_profile(left: _Profile, opts: dict[str, Any], seed: int) -> _Profile:
    random = _Mulberry32((seed & _UINT32_MASK) ^ 0x85EBCA6B)
    spacing, height = opts["spacing_variation"], opts["height_variation"]
    knots: list[dict[str, float]] = []
    for index, knot in enumerate(left.knots):
        if index == 0 or index == len(left.knots) - 1:
            knots.append({"s": knot["s"], "v": 0.0})
            continue
        room = min(knot["s"] - left.knots[index - 1]["s"], left.knots[index + 1]["s"] - knot["s"])
        knots.append({
            "s": knot["s"] + (random() - 0.5) * 0.55 * spacing * room,
            "v": _clamp(knot["v"] * (1.0 + (random() - 0.5) * 0.55 * height), 0.035, 1.0),
        })
    for index in range(2, len(knots) - 1, 2):
        knots[index]["v"] = min(knots[index]["v"], 0.65 * knots[index - 1]["v"], 0.65 * knots[index + 1]["v"])
    return _profile_from_knots(
        knots, left.smoothing_radius, smoothing_seed=seed ^ 0x85EBCA6B,
        smoothing_variation=opts["smoothing_variation"],
    )


def make_profiles(total: float, params: dict[str, Any], seed: int) -> tuple[Callable[[float], float], Callable[[float], float]]:
    """Return deterministic left/right normalized ribbon width profiles."""

    total = max(0.0, float(total))
    variation = _clamp(_number(params, "variation", 0.5), 0.0, 1.0)
    wavelength = _number(params, "wavelength", 90.0) or 90.0
    opts: dict[str, Any] = {
        "variation": variation,
        "wavelength": max(1e-6, wavelength),
        "spacing_variation": _clamp(_number(params, "spacing_variation", variation), 0.0, 1.0),
        "height_variation": _clamp(_number(params, "height_variation", variation), 0.0, 1.0),
        "phrasing": _clamp(_number(params, "phrasing", 0.7), 0.0, 1.0),
        "crest_softening": _clamp(_number(params, "crest_softening", 0.055), 0.0, 0.49),
        "smoothing_variation": _clamp(_number(params, "smoothing_variation", 0.0), 0.0, 1.0),
    }
    phrased = params.get("rhythm", "legacy") == "phrased"
    unsigned_seed = int(seed) & _UINT32_MASK
    left = _crest_profile(total, opts, unsigned_seed) if phrased else _legacy_profile(total, opts, _Mulberry32(unsigned_seed))

    right_opts = dict(opts)
    if params.get("independent_wavelengths", False):
        right_wave = _number(params, "wavelength_right", opts["wavelength"]) or opts["wavelength"]
        right_opts["wavelength"] = max(1.0, right_wave)
    right_base = left if right_opts["wavelength"] == opts["wavelength"] else (
        _crest_profile(total, right_opts, unsigned_seed) if phrased
        else _legacy_profile(total, right_opts, _Mulberry32(unsigned_seed))
    )
    relation = params.get("relation", "related")
    if relation == "mirrored":
        right = right_base
    elif relation == "independent":
        right_seed = unsigned_seed ^ 0x9E3779B9
        right = _crest_profile(total, right_opts, right_seed) if phrased else _legacy_profile(total, right_opts, _Mulberry32(right_seed))
    elif phrased:
        right = _related_profile(right_base, right_opts, unsigned_seed)
    else:
        random = _Mulberry32(unsigned_seed ^ 0x85EBCA6B)
        guide = []
        for knot in right_base.knots[1:]:
            guide.append({
                "spacing": _clamp(knot["spacing"] + (random() - 0.5) * 0.16 * variation, 0.65, 1.35),
                "amplitude": _clamp(knot["amplitude"] * (1.0 + (random() - 0.5) * 0.28 * variation), 0.12, 1.0),
            })
        right = _legacy_profile(total, right_opts, random, guide)
    return left, right


__all__ = ["make_profiles"]

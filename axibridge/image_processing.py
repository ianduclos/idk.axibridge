"""Shared non-destructive image-processing controls for asset samplers."""

from __future__ import annotations

from typing import Any


IMAGE_PROCESSING_GROUP = {"group": "Image processing"}


def _clamp01(v: float) -> float:
    return min(max(v, 0.0), 1.0)


def image_processing_kwargs(params: Any) -> dict[str, float]:
    """Extract shared image-processing params from any Pydantic params object."""
    return {
        "brightness": float(getattr(params, "brightness", 0.0)),
        "contrast": float(getattr(params, "contrast", 0.0)),
        "gamma": float(getattr(params, "gamma", 1.0)),
        "black_point": float(getattr(params, "black_point", 0.0)),
        "white_point": float(getattr(params, "white_point", 1.0)),
    }


def apply_image_processing_value(
    value: float,
    *,
    brightness: float = 0.0,
    contrast: float = 0.0,
    gamma: float = 1.0,
    black_point: float = 0.0,
    white_point: float = 1.0,
) -> float:
    """Process a single grayscale luma sample.

    Input and output are both in [0, 1], with 0=black and 1=white. Brightness
    and contrast use the plotterfun byte-scale ranges (-100..100), keeping the
    existing image-generator tone knobs compatible while giving other
    image-driven modules the same feel.
    """
    v = _clamp01(value)
    bp = _clamp01(black_point)
    wp = _clamp01(white_point)
    span = max(wp - bp, 1e-6)
    v = _clamp01((v - bp) / span)

    g = max(float(gamma), 1e-6)
    v = _clamp01(v ** g)

    c = min(max(float(contrast), -100.0), 100.0)
    b = float(brightness)
    byte = v * 255.0
    if c:
        cf = (259.0 * (c + 255.0)) / (255.0 * (259.0 - c))
        byte = cf * (byte - 128.0) + 128.0
    byte += b
    return _clamp01(byte / 255.0)


def apply_image_processing_byte(value: float, **kwargs: float) -> float:
    """Process a byte-scale luma sample and return byte-scale luma."""
    return apply_image_processing_value(value / 255.0, **kwargs) * 255.0

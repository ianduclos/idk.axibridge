"""Colour separation: which plane of an image a generator samples.

Every image-driven generator used to see exactly one thing — luminance. This
module is the seam that lets one image yield *plates*: CMYK ink separations,
raw RGB planes, or (later) spot colours and solved N-pen palettes. A plate is
plotted with its own pen, and transparent felt tips overprinting one another
are the point.

**The polarity contract — the load-bearing rule.**

Every decoder returns rows of floats in ``[0, 1]`` where **0 means "draw
hardest"**, exactly the convention ``asset_store.grayscale`` has always had
(0 = black). That single rule is why colour separation touches so little code:
``_tone_lut``, brightness/contrast/gamma/levels, ``ImageSampler``,
``image_threshold``'s marching squares — none of them know or care which plane
they are looking at. Break the polarity and every generator inverts.

So an *ink* plate is returned as ``1 - ink``: lots of cyan reads as dark, which
reads as "draw hard". An RGB plate is returned raw, which reads that plane as
its own greyscale image (the Photoshop reading of "the red channel").

**Two consequences worth knowing, because they are the model being honest:**

- At ``black_generation = 0`` the CMY plates are *exactly* the R/G/B plates
  (``1 - (1 - r) == r``). That is not a coincidence to paper over, it is what
  "remove no black" means, and ``tests/test_separation.py`` pins it.
- At ``black_generation = 0`` the K plate is *empty*. Also correct — you asked
  for no black to be pulled out — but it is a footgun, so the separation UI
  says so out loud rather than quietly making a blank layer.

Design notes, alternatives and how to reverse each judgment call live in
``docs/plans/channel-separation.md``.
"""

from __future__ import annotations

from typing import Any, Literal

from .assets import asset_store

#: Every plate a generator can sample. Adding one means adding a decoder to
#: ``CHANNEL_DECODERS`` and a label here — never touching a generator.
ChannelName = Literal["luma", "c", "m", "y", "k", "r", "g", "b"]

CHANNEL_NAMES: tuple[str, ...] = ("luma", "c", "m", "y", "k", "r", "g", "b")

CHANNEL_LABELS: dict[str, str] = {
    "luma": "Luminance",
    "c": "Cyan",
    "m": "Magenta",
    "y": "Yellow",
    "k": "Black (K)",
    "r": "Red",
    "g": "Green",
    "b": "Blue",
}

#: Plates that are ink separations — the only ones ``black_generation`` moves.
INK_CHANNELS: frozenset[str] = frozenset({"c", "m", "y", "k"})

#: Plates that are a raw RGB plane, readable straight off ``Image.split()``.
PLANE_CHANNELS: dict[str, int] = {"r": 0, "g": 1, "b": 2}


def cmyk_plate(r: float, g: float, b: float, channel: str,
               black_generation: float) -> float:
    """One CMYK plate for one pixel, in ink units (0 = none, 1 = full).

    Grey-component replacement in the *subtract* form::

        k_full = 1 - max(r, g, b)      # the achromatic component
        k      = black_generation * k_full
        c      = (1 - r) - k           # m from g, y from b

    Chosen over the textbook *divide* form ``(1 - r - k) / (1 - k)`` for two
    reasons: it needs no guard as ``k`` approaches 1, and it lays much less ink
    for the same picture — the divide form re-saturates every plate, which is
    right for offset presses laying transparent process inks in register and
    wrong for a plotter dragging felt tips across paper. The endpoints are
    exact either way: at 1.0 the achromatic content is entirely K's, at 0.0 no
    black is pulled out at all. See ``docs/plans/channel-separation.md`` to
    switch forms.
    """
    k = black_generation * (1.0 - max(r, g, b))
    if channel == "k":
        return k
    complement = {"c": 1.0 - r, "m": 1.0 - g, "y": 1.0 - b}[channel]
    return complement - k


def sample_rows(
    params: Any,
    blur_px: float = 0.0,
    size: tuple[int, int] | None = None,
) -> tuple[list[list[float]], int, int] | None:
    """Decode the plane this params object selects — the ONE entry point.

    Resolves a frame sequence to its concrete frame first, then reads the
    selected channel. ``channel``/``black_generation`` are read defensively so
    a params model that predates them still samples luma, which is what keeps
    this callable from ``image_threshold`` as well as the pixelgen family.
    """
    image = asset_store.resolve_frame(params.image, getattr(params, "frame", 0.0))
    return asset_store.channel(
        image,
        getattr(params, "channel", "luma"),
        black_generation=getattr(params, "black_generation", 1.0),
        blur_px=blur_px,
        rotate=params.rotate,
        size=size,
    )

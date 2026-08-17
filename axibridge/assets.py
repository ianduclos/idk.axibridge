"""Project image assets (depth maps): bytes in, sampled grayscale out.

A module-level singleton (like the stores) so both the session (which owns
save/load) and effect modules (which only get paths+params) can reach it
without import cycles. Assets travel with the project folder under
``assets/``; the session swaps the store's contents on project open/new.

``grayscale()`` returns a row-major list of float rows in [0, 1] plus
dimensions — decoded once per asset and cached until the bytes change.
"""

from __future__ import annotations

import io
import re
import threading


def safe_asset_name(filename: str) -> str:
    # '#' is allowed: it is the frame-sequence marker (``clip#0000.jpg``) — the
    # store groups such assets into one named sequence (see SEQUENCE_FRAME_RE).
    cleaned = re.sub(r"[^A-Za-z0-9._#-]+", "_", filename).strip("._") or "asset"
    return cleaned


#: A sequence frame is a plain asset named ``<prefix>#<NNNN>.<ext>`` (4+ digit
#: zero-padded index). Group 1 is the prefix INCLUDING the '#' — that prefix is
#: what modules/UI reference; individual frames never surface on their own.
SEQUENCE_FRAME_RE = re.compile(r"^(.+#)\d{4,}\.[^.]+$")


def _open(data: bytes):
    """Decode + apply the EXIF orientation tag. Browsers honour EXIF when
    showing the raw asset (ghost overlays), PIL does not when sampling —
    without this, phone photos plot rotated relative to what the canvas shows."""
    from PIL import Image, ImageOps

    return ImageOps.exif_transpose(Image.open(io.BytesIO(data)))


def _rotated(img, rotate: int):
    """Clockwise-on-paper rotation. PIL's ROTATE_* constants are CCW."""
    from PIL import Image

    transpose = {90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}
    return img.transpose(transpose[rotate]) if rotate in transpose else img


class AssetStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, bytes] = {}
        #: (name, blur_px rounded, rotate, size) -> decoded grayscale
        self._gray: dict[
            tuple[str, float, int, tuple[int, int] | None],
            tuple[list[list[float]], int, int],
        ] = {}
        #: (name, rotate, size) -> alpha rows, or None for images without alpha
        self._alpha: dict[
            tuple[str, int, tuple[int, int] | None],
            list[list[float]] | None,
        ] = {}
        #: (name, channel, black_generation, blur_px, rotate, size) -> decoded
        #: colour plate. Deliberately a SEPARATE dict from ``_gray`` rather
        #: than an extra key element on it: ``channel("luma")`` delegates to
        #: ``grayscale`` and so never lands here at all, which keeps the hot,
        #: unchanged luma path's key shape untouched.
        self._channel: dict[
            tuple[str, str, float, float, int, tuple[int, int] | None],
            tuple[list[list[float]], int, int],
        ] = {}
        #: sequence prefix ("clip#") -> sorted concrete frame names; derived
        #: from ``self._data`` keys by ``_reindex`` (held under the lock).
        self._seq: dict[str, list[str]] = {}
        #: name -> font family label if the bytes parse as a font, else None.
        #: No separate "kind" is stored anywhere: an asset's kind is just
        #: whichever decoder accepts its bytes (PIL for images, fontTools
        #: here), the same idea as ``grayscale`` returning None for
        #: non-images — so save/load round-trips never need to carry a kind
        #: alongside the bytes. Cached like ``_gray``/``_alpha``.
        self._font_label: dict[str, str | None] = {}
        #: monotonic counter, bumped under the lock by ``put``/``replace_all``.
        #: ``gencache`` folds this into its cache key so any asset change
        #: (upload, project load/new) implicitly orphans stale memo entries —
        #: no explicit invalidation call needed anywhere that touches assets.
        self._version = 0

    def _reindex(self) -> None:
        """Rebuild the sequence prefix index from the current keys. Cheap
        (a scan + per-group sort of the key strings). Caller holds the lock."""
        seq: dict[str, list[str]] = {}
        for name in self._data:
            m = SEQUENCE_FRAME_RE.match(name)
            if m:
                seq.setdefault(m.group(1), []).append(name)
        for frames in seq.values():
            frames.sort()  # zero-padded index -> lexical sort is frame order
        self._seq = seq

    def put(self, name: str, data: bytes) -> str:
        name = safe_asset_name(name)
        with self._lock:
            self._data[name] = data
            self._gray = {k: v for k, v in self._gray.items() if k[0] != name}
            self._alpha = {k: v for k, v in self._alpha.items() if k[0] != name}
            self._channel = {k: v for k, v in self._channel.items() if k[0] != name}
            self._font_label.pop(name, None)
            self._reindex()
            self._version += 1
        return name

    def version(self) -> int:
        """Monotonic counter, bumped by ``put``/``replace_all``. Folded into
        ``gencache``'s cache key so asset changes implicitly invalidate any
        cached generate() result that read the old bytes."""
        with self._lock:
            return self._version

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._data)

    def is_sequence(self, name: str) -> bool:
        """True if ``name`` is a known frame-sequence prefix (``clip#``) that
        maps to concrete frames — i.e. a name with a per-frame ``frame`` axis.
        Thread-safe; never raises."""
        with self._lock:
            return bool(self._seq.get(name))

    def sequence_frames(self, name: str) -> list[str]:
        """Concrete frame names for a known sequence prefix, in frame order —
        empty list if ``name`` isn't a sequence. Lets callers (e.g. the "clear
        unused assets" endpoint) treat a referenced clip as the whole set of
        stored frame keys, since the prefix itself is never a real ``_data``
        key. Thread-safe; never raises."""
        with self._lock:
            return list(self._seq.get(name, ()))

    def resolve_frame(self, name: str, frame: float) -> str:
        """Map a sequence prefix + normalized position to a concrete frame name.
        ``frame`` is clamped to [0,1] and rounded to the nearest frame index
        (0 -> first, 1 -> last). Plain names (and unknown names) pass through
        unchanged — the caller's "no asset named X" error still fires. Thread-
        safe; never raises."""
        with self._lock:
            frames = self._seq.get(name)
            if not frames:
                return name
            f = min(max(frame, 0.0), 1.0)
            return frames[round(f * (len(frames) - 1))]

    def info(self) -> list[dict]:
        """[{name, width, height, frames}] — dimensions let the canvas place
        overlays and effects derive aspect ratios without decoding pixels.
        Frame sequences collapse to ONE entry (name = the ``clip#`` prefix,
        ``frames`` = count, dimensions from the first frame); the individual
        frames never appear on their own. Plain assets carry ``frames`` = 1.
        Non-image assets sharing the store (fonts) fail the decode and are
        skipped here — same idea as ``font_names`` skipping images, the
        other way round."""
        with self._lock:
            seq = {k: list(v) for k, v in self._seq.items()}
            plain = sorted(set(self._data) - {n for fr in seq.values() for n in fr})
        entries = [("plain", n) for n in plain] + [("seq", p) for p in seq]
        out = []
        for kind, name in sorted(entries, key=lambda e: e[1]):
            rep = seq[name][0] if kind == "seq" else name
            try:
                g = self.grayscale(rep)  # takes the lock itself — not held here
            except Exception:
                g = None
            if g is not None:
                out.append({
                    "name": name,
                    "width": g[1],
                    "height": g[2],
                    "frames": len(seq[name]) if kind == "seq" else 1,
                })
        return out

    def get(self, name: str) -> bytes | None:
        with self._lock:
            data = self._data.get(name)
            if data is None:
                # a sequence prefix has no bytes of its own: hand back the first
                # frame so /api/assets/{prefix} serves a representative image
                # (the canvas ghost/preview fetch) instead of 404ing.
                frames = self._seq.get(name)
                if frames:
                    data = self._data.get(frames[0])
            return data

    def replace_all(self, assets: dict[str, bytes]) -> None:
        with self._lock:
            self._data = dict(assets)
            self._gray.clear()
            self._alpha.clear()
            self._channel.clear()
            self._font_label.clear()
            self._reindex()
            self._version += 1

    def font_label(self, name: str) -> str | None:
        """The font's family name if ``name``'s bytes parse as a font
        (TTF/OTF/TTC), else None — an image asset simply fails the parse and
        gets None, the same decoding-as-validation ``grayscale`` already
        does the other way around."""
        with self._lock:
            if name in self._font_label:
                return self._font_label[name]
            data = self._data.get(name)
        label = None
        if data is not None:
            try:
                from fontTools.ttLib import TTFont  # lazy: keep server start fast

                font = TTFont(io.BytesIO(data), lazy=True, fontNumber=0)
                nm = font.get("name")
                label = (nm.getDebugName(1) if nm else None) or name
            except Exception:
                label = None
        with self._lock:
            self._font_label[name] = label
        return label

    def font_names(self) -> list[tuple[str, str]]:
        """[(asset name, font label)] for every stored asset that is
        actually a font — image assets are naturally excluded, they fail
        the parse in ``font_label``."""
        with self._lock:
            names = list(self._data)
        out = []
        for n in names:
            label = self.font_label(n)
            if label is not None:
                out.append((n, label))
        return out

    def alpha(
        self,
        name: str,
        rotate: int = 0,
        size: tuple[int, int] | None = None,
    ) -> list[list[float]] | None:
        """Alpha channel as rows in [0,1], or None if absent/opaque. Same
        dimensions as ``grayscale`` at the same rotation and size; unblurred
        apart from image resampling — it's a hard crop mask."""
        key = (name, rotate % 360, size)
        with self._lock:
            if key in self._alpha:
                return self._alpha[key]
            data = self._data.get(name)
        if data is None:
            return None
        img = _rotated(_open(data), key[1])
        rows = None
        if "A" in img.getbands():
            a = img.getchannel("A")
            if size is not None and a.size != size:
                from PIL import Image

                a = a.resize(size, Image.Resampling.LANCZOS)
            w, h = a.size
            px = a.tobytes()  # mode "L": one byte per pixel, row-major
            if min(px) < 255:  # an all-opaque alpha is no mask at all
                rows = [[px[y * w + x] / 255.0 for x in range(w)] for y in range(h)]
        with self._lock:
            self._alpha[key] = rows
        return rows

    def all(self) -> dict[str, bytes]:
        with self._lock:
            return dict(self._data)

    def grayscale(
        self,
        name: str,
        blur_px: float = 0.0,
        rotate: int = 0,
        size: tuple[int, int] | None = None,
    ) -> tuple[list[list[float]], int, int] | None:
        """Decoded image as rows of floats in [0,1] (0=black), (rows, w, h).
        ``blur_px`` applies a Gaussian blur before sampling — the smoothing
        knob for depth/threshold work, cached per radius. ``rotate`` (0/90/
        180/270, clockwise on paper) pre-rotates: dimensions come back
        swapped for 90/270, so callers' sampling code never changes.
        ``size`` resamples to exactly (w, h) after rotation and before the
        blur — the pixel-space generators work at a fixed resolution so their
        px-calibrated params mean the same thing for any source image."""
        key = (name, round(max(blur_px, 0.0), 2), rotate % 360, size)
        with self._lock:
            cached = self._gray.get(key)
            if cached is not None:
                return cached
            data = self._data.get(name)
        if data is None:
            return None
        from PIL import Image, ImageFilter  # lazy: keep server start fast

        img = _rotated(_open(data), key[2]).convert("L")
        if size is not None and img.size != size:
            img = img.resize(size, Image.LANCZOS)
        if key[1] > 0:
            img = img.filter(ImageFilter.GaussianBlur(key[1]))
        w, h = img.size
        px = img.tobytes()  # mode "L": one byte per pixel, row-major
        rows = [[px[y * w + x] / 255.0 for x in range(w)] for y in range(h)]
        result = (rows, w, h)
        with self._lock:
            self._gray[key] = result
        return result

    def channel(
        self,
        name: str,
        channel: str = "luma",
        *,
        black_generation: float = 1.0,
        blur_px: float = 0.0,
        rotate: int = 0,
        size: tuple[int, int] | None = None,
    ) -> tuple[list[list[float]], int, int] | None:
        """One colour plate of ``name``, in ``grayscale``'s polarity.

        Same shape and same contract as ``grayscale``: rows of floats in [0, 1]
        where 0 draws hardest, plus dimensions. ``channel`` picks the plane —
        ``"luma"`` (the default) is literally ``grayscale``, ``"c"``/``"m"``/
        ``"y"``/``"k"`` are CMYK ink plates returned as ``1 - ink``, and
        ``"r"``/``"g"``/``"b"`` are the raw planes read as their own greyscale
        image. ``black_generation`` (0..1) moves achromatic density between CMY
        and K and is meaningless for the others. See ``channels.py`` for the
        polarity contract and the maths.
        """
        from .channels import (
            HSL_CHANNELS,
            INK_CHANNELS,
            PLANE_CHANNELS,
            cmyk_plate,
            hsl_plate,
        )

        # luma DELEGATES rather than being reimplemented: it is the default
        # every existing project already sits on, and PIL's fixed-point
        # ITU-R 601 kernel is not something to reproduce from decoded floats
        # and hope matches. Same call, same cache, byte-identical by identity.
        if channel == "luma":
            return self.grayscale(name, blur_px, rotate, size)
        if (channel not in INK_CHANNELS and channel not in PLANE_CHANNELS
                and channel not in HSL_CHANNELS):
            raise ValueError(f"unknown channel {channel!r}")

        bg = min(max(float(black_generation), 0.0), 1.0)
        # black_generation cannot move an RGB plane, so it is normalised out of
        # their keys — otherwise dragging the knob would fragment the cache
        # with identical entries.
        key = (
            name,
            channel,
            round(bg, 3) if channel in INK_CHANNELS else 0.0,
            round(max(blur_px, 0.0), 2),
            rotate % 360,
            size,
        )
        with self._lock:
            cached = self._channel.get(key)
            if cached is not None:
                return cached
            data = self._data.get(name)
        if data is None:
            return None
        from PIL import Image, ImageFilter  # lazy: keep server start fast

        img = _rotated(_open(data), key[4]).convert("RGB")
        if size is not None and img.size != size:
            img = img.resize(size, Image.LANCZOS)
        # Blur BEFORE the channel maths, deliberately. RGB->L is linear so
        # grayscale() may blur either side of it, but the CMYK decomposition is
        # not — converting first makes the blur ring around dark edges. Keeping
        # resize-then-blur order identical to grayscale() is also what keeps
        # blur_px meaning the same millimetres it always did.
        if key[3] > 0:
            img = img.filter(ImageFilter.GaussianBlur(key[3]))
        w, h = img.size

        plane = PLANE_CHANNELS.get(channel)
        if channel in INK_CHANNELS and bg == 0.0:
            # black_generation 0 pulls out no black at all, so C/M/Y collapse
            # to 1 - (1 - r) = r — the RGB planes exactly, at C speed.
            plane = {"c": 0, "m": 1, "y": 2, "k": None}[channel]
            if plane is None:  # the K plate with no black generation: empty
                rows = [[1.0] * w for _ in range(h)]
                plane = -1  # handled; skip both branches below
        if plane is not None and plane >= 0:
            px = img.split()[plane].tobytes()
            rows = [[px[y * w + x] / 255.0 for x in range(w)] for y in range(h)]
        elif plane is None:
            # Per-pixel decode. The plate function returns plate polarity
            # directly for HSL and ink units for CMYK, so the one inversion
            # lives here rather than being repeated in every decoder.
            ink_plate = channel in INK_CHANNELS
            px = img.tobytes()  # mode "RGB": three bytes per pixel, row-major
            rows = []
            for y in range(h):
                base = y * w * 3
                row = []
                for x in range(w):
                    i = base + x * 3
                    r, g, b = px[i] / 255.0, px[i + 1] / 255.0, px[i + 2] / 255.0
                    v = (1.0 - cmyk_plate(r, g, b, channel, bg)) if ink_plate \
                        else hsl_plate(r, g, b, channel)
                    # Both stay in range analytically; the clamp is for float
                    # dust, because ImageSampler indexes a 256-entry LUT with
                    # int(v * 255 + 0.5) and an out-of-range value is an
                    # IndexError, not a slightly wrong pixel.
                    row.append(min(max(v, 0.0), 1.0))
                rows.append(row)

        result = (rows, w, h)
        with self._lock:
            self._channel[key] = result
        return result


asset_store = AssetStore()

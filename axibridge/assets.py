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
        #: (name, rotate) -> alpha rows, or None for images without alpha
        self._alpha: dict[tuple[str, int], list[list[float]] | None] = {}
        #: sequence prefix ("clip#") -> sorted concrete frame names; derived
        #: from ``self._data`` keys by ``_reindex`` (held under the lock).
        self._seq: dict[str, list[str]] = {}

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
            self._reindex()
        return name

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._data)

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
        frames never appear on their own. Plain assets carry ``frames`` = 1."""
        with self._lock:
            seq = {k: list(v) for k, v in self._seq.items()}
            plain = sorted(set(self._data) - {n for fr in seq.values() for n in fr})
        entries = [("plain", n) for n in plain] + [("seq", p) for p in seq]
        out = []
        for kind, name in sorted(entries, key=lambda e: e[1]):
            rep = seq[name][0] if kind == "seq" else name
            g = self.grayscale(rep)  # takes the lock itself — not held here
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
            self._reindex()

    def alpha(self, name: str, rotate: int = 0) -> list[list[float]] | None:
        """Alpha channel as rows in [0,1], or None if absent/opaque. Same
        dimensions as ``grayscale`` at the same rotation; unblurred — it's a
        hard crop mask."""
        key = (name, rotate % 360)
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


asset_store = AssetStore()

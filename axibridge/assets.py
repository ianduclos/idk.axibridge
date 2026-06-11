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
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._") or "asset"
    return cleaned


def _rotated(img, rotate: int):
    """Clockwise-on-paper rotation. PIL's ROTATE_* constants are CCW."""
    from PIL import Image

    transpose = {90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}
    return img.transpose(transpose[rotate]) if rotate in transpose else img


class AssetStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, bytes] = {}
        #: (name, blur_px rounded, rotate) -> decoded grayscale
        self._gray: dict[tuple[str, float, int], tuple[list[list[float]], int, int]] = {}
        #: (name, rotate) -> alpha rows, or None for images without alpha
        self._alpha: dict[tuple[str, int], list[list[float]] | None] = {}

    def put(self, name: str, data: bytes) -> str:
        name = safe_asset_name(name)
        with self._lock:
            self._data[name] = data
            self._gray = {k: v for k, v in self._gray.items() if k[0] != name}
            self._alpha = {k: v for k, v in self._alpha.items() if k[0] != name}
        return name

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._data)

    def info(self) -> list[dict]:
        """[{name, width, height}] — dimensions let the canvas place overlays
        and effects derive aspect ratios without decoding pixels."""
        out = []
        for name in self.names():
            g = self.grayscale(name)
            if g is not None:
                out.append({"name": name, "width": g[1], "height": g[2]})
        return out

    def get(self, name: str) -> bytes | None:
        with self._lock:
            return self._data.get(name)

    def replace_all(self, assets: dict[str, bytes]) -> None:
        with self._lock:
            self._data = dict(assets)
            self._gray.clear()
            self._alpha.clear()

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
        from PIL import Image

        img = _rotated(Image.open(io.BytesIO(data)), key[1])
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
        self, name: str, blur_px: float = 0.0, rotate: int = 0
    ) -> tuple[list[list[float]], int, int] | None:
        """Decoded image as rows of floats in [0,1] (0=black), (rows, w, h).
        ``blur_px`` applies a Gaussian blur before sampling — the smoothing
        knob for depth/threshold work, cached per radius. ``rotate`` (0/90/
        180/270, clockwise on paper) pre-rotates: dimensions come back
        swapped for 90/270, so callers' sampling code never changes."""
        key = (name, round(max(blur_px, 0.0), 2), rotate % 360)
        with self._lock:
            cached = self._gray.get(key)
            if cached is not None:
                return cached
            data = self._data.get(name)
        if data is None:
            return None
        from PIL import Image, ImageFilter  # lazy: keep server start fast

        img = _rotated(Image.open(io.BytesIO(data)), key[2]).convert("L")
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

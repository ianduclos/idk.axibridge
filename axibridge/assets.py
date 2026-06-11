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


class AssetStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, bytes] = {}
        #: (name, blur_px rounded) -> decoded grayscale
        self._gray: dict[tuple[str, float], tuple[list[list[float]], int, int]] = {}

    def put(self, name: str, data: bytes) -> str:
        name = safe_asset_name(name)
        with self._lock:
            self._data[name] = data
            self._gray = {k: v for k, v in self._gray.items() if k[0] != name}
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

    def all(self) -> dict[str, bytes]:
        with self._lock:
            return dict(self._data)

    def grayscale(
        self, name: str, blur_px: float = 0.0
    ) -> tuple[list[list[float]], int, int] | None:
        """Decoded image as rows of floats in [0,1] (0=black), (rows, w, h).
        ``blur_px`` applies a Gaussian blur before sampling — the smoothing
        knob for depth/threshold work, cached per radius."""
        key = (name, round(max(blur_px, 0.0), 2))
        with self._lock:
            cached = self._gray.get(key)
            if cached is not None:
                return cached
            data = self._data.get(name)
        if data is None:
            return None
        from PIL import Image, ImageFilter  # lazy: keep server start fast

        img = Image.open(io.BytesIO(data)).convert("L")
        if key[1] > 0:
            img = img.filter(ImageFilter.GaussianBlur(key[1]))
        w, h = img.size
        px = list(img.getdata())
        rows = [[px[y * w + x] / 255.0 for x in range(w)] for y in range(h)]
        result = (rows, w, h)
        with self._lock:
            self._gray[key] = result
        return result


asset_store = AssetStore()

"""Rasterise axibridge geometry to PNG — the agent's eyes on what the canvas
shows. Pillow only: no browser, no cairo. Flexoki palette (hexes from
flexoki.css: paper, black, 100, 300, 600, red-400)."""

from __future__ import annotations

import io
import math

from mcp.server.mcpserver import Image as McpImage
from PIL import Image, ImageDraw, ImageFont

PAPER = "#FFFCF0"
INK = "#100F0F"
BED_LINE = "#E6E4D9"
GUIDE_LINE = "#B7B5AC"
CAPTION = "#6F6E69"
TRAVEL = "#D14D41"
CAPTION_H = 22


def png(data: bytes) -> McpImage:
    return McpImage(data=data, format="png")


def _encode(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def render_layers(layers: list[dict], *, bed: tuple[float, float], guide: dict | None,
                  travel: list[list[list[float]]] | None, view: str, size: int) -> bytes:
    W, H = bed
    portrait = view == "portrait"
    out_w, out_h = (H, W) if portrait else (W, H)
    scale = size / max(out_w, out_h)
    img = Image.new("RGB", (round(out_w * scale), round(out_h * scale)), PAPER)
    d = ImageDraw.Draw(img)

    def px(x: float, y: float) -> tuple[float, float]:
        if portrait:  # canvas.js: translate(H 0) rotate(90) — origin top-right
            x, y = H - y, x
        return (x * scale, y * scale)

    def rect(x: float, y: float, w: float, h: float, color: str) -> None:
        corners = [px(x, y), px(x + w, y), px(x + w, y + h), px(x, y + h), px(x, y)]
        d.line(corners, fill=color, width=1)

    rect(0, 0, W, H, BED_LINE)
    if guide:
        rect(guide["x"], guide["y"], guide["width"], guide["height"], GUIDE_LINE)
    for layer in layers:
        if not layer.get("visible", True):
            continue
        color = layer.get("color") or INK
        width = max(1, round((layer.get("line_diameter_mm") or 0.4) * scale))
        for path in layer.get("paths", []):
            pts = [px(*p) for p in path["points"]]
            if len(pts) >= 2:
                d.line(pts, fill=color, width=width, joint="curve")
            elif pts:
                d.point(pts, fill=color)
    for seg in travel or []:
        if len(seg) >= 2:
            d.line([px(*p) for p in seg], fill=TRAVEL, width=1)
    return _encode(img)


def fit_lines(lines: list[list[list[float]]], size: int) -> Image.Image:
    """A free-floating preview (generator/effect `lines`) fitted to a square
    tile with a small margin. Absolute scale is dropped; captions carry it."""
    img = Image.new("RGB", (size, size), PAPER)
    pts = [p for line in lines for p in line]
    if not pts:
        return img
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0 = min(xs), min(ys)
    span = max(max(xs) - x0, max(ys) - y0) or 1.0
    pad = size * 0.06
    k = (size - 2 * pad) / span
    d = ImageDraw.Draw(img)
    for line in lines:
        q = [(pad + (x - x0) * k, pad + (y - y0) * k) for x, y in line]
        if len(q) >= 2:
            d.line(q, fill=INK, width=1)
        elif q:
            d.point(q, fill=INK)
    return img


def contact_sheet(tiles: list[tuple[Image.Image, str]], cols: int | None = None) -> bytes:
    if not tiles:
        return _encode(Image.new("RGB", (1, 1), PAPER))
    cols = cols or math.ceil(math.sqrt(len(tiles)))
    rows = math.ceil(len(tiles) / cols)
    tw, th = tiles[0][0].size
    sheet = Image.new("RGB", (cols * tw, rows * (th + CAPTION_H)), PAPER)
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=13)
    for i, (tile, caption) in enumerate(tiles):
        x, y = (i % cols) * tw, (i // cols) * (th + CAPTION_H)
        sheet.paste(tile, (x, y))
        d.rectangle([x, y, x + tw - 1, y + th - 1], outline=BED_LINE)
        d.text((x + 6, y + th + 4), caption, fill=CAPTION, font=font)
    return _encode(sheet)

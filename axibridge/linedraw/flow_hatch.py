"""Deterministic curved hatching within a pixel shadow mask.

The direction field is an artistic heuristic: a diagonal baseline bends with
the image-space normal. It is not a physical surface projection.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter, label


def flow_hatch(
    mask: np.ndarray, normals: np.ndarray, spacing: float = 5, checkpoint=lambda: None,
    *, coherent: bool = False, density_field: np.ndarray | None = None,
) -> list[np.ndarray]:
    """Return image-coordinate (x, y) polylines contained in ``mask``.

    ``mask`` has shape (H, W), ``normals`` has shape (H, W, >=2), and
    ``spacing`` is in pixels. Stroke order and seed placement are deterministic.
    """
    mask = np.asarray(mask, dtype=bool)
    normals = np.asarray(normals, dtype=float)
    if (
        mask.ndim != 2
        or normals.shape[:2] != mask.shape
        or normals.ndim != 3
        or normals.shape[2] < 2
    ):
        raise ValueError("mask must be HxW and normals must be HxWxC with C >= 2")
    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("spacing must be positive and finite")
    h, w = mask.shape
    if density_field is not None:
        density_field = np.asarray(density_field, dtype=float)
        if density_field.shape != mask.shape or not np.isfinite(density_field).all():
            raise ValueError("density field must be finite and match mask")
        density_field = np.clip(density_field, 0, 1)
    if not mask.any():
        return []

    # Smoothing suppresses local depth/noise ripples before they steer a pen.
    nx = gaussian_filter(np.nan_to_num(normals[..., 0], nan=0, posinf=0, neginf=0), 10)
    ny = gaussian_filter(np.nan_to_num(normals[..., 1], nan=0, posinf=0, neginf=0), 10)
    if coherent:
        # Projected surface tangents; weak/flat normals retain the study's
        # diagonal direction instead of inventing a direction from noise.
        strength = np.hypot(nx, ny)
        blend = np.clip(strength / .18, 0, 1)
        dx = (1 - blend) * 1.0 - blend * ny
        dy = (1 - blend) * -.65 + blend * nx
    else:
        dx = 1.0 - 1.3 * ny
        dy = -0.65 + 1.3 * nx
    mag = np.hypot(dx, dy)
    dx /= np.maximum(mag, 1e-9)
    dy /= np.maximum(mag, 1e-9)

    components, _ = label(mask)  # Four-neighbour components prevent gap jumps.
    distance = distance_transform_edt(mask)
    occupied = np.zeros_like(mask)
    radius = max(1, int(round(0.7 * spacing)))
    if density_field is not None:
        radius = max(radius, int(round(1.4 * spacing)))
    yy, xx = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    disk_y, disk_x = np.nonzero(xx * xx + yy * yy <= radius * radius)
    disk_y -= radius
    disk_x -= radius

    stride = max(1, int(round(spacing if density_field is None else spacing / 2)))
    seeds: list[tuple[float, int, int]] = []
    for row, y in enumerate(range(stride // 2, h, stride)):
        offset = stride // 2 if row % 2 else 0
        for x in range(stride // 2 + offset, w, stride):
            if mask[y, x]:
                seeds.append((-float(distance[y, x]), y, x))
    seeds.sort()

    def inside(x: float, y: float, component: int) -> bool:
        ix, iy = int(round(x)), int(round(y))
        return 0 <= ix < w and 0 <= iy < h and components[iy, ix] == component

    def vector(x: float, y: float) -> tuple[float, float]:
        x = min(max(x, 0.0), w - 1.0)
        y = min(max(y, 0.0), h - 1.0)
        x0, y0 = int(x), int(y)
        x1, y1 = min(x0 + 1, w - 1), min(y0 + 1, h - 1)
        u, v = x - x0, y - y0
        vx = (1 - v) * ((1 - u) * dx[y0, x0] + u * dx[y0, x1]) + v * (
            (1 - u) * dx[y1, x0] + u * dx[y1, x1]
        )
        vy = (1 - v) * ((1 - u) * dy[y0, x0] + u * dy[y0, x1]) + v * (
            (1 - u) * dy[y1, x0] + u * dy[y1, x1]
        )
        length = max(float(np.hypot(vx, vy)), 1e-9)
        return float(vx / length), float(vy / length)

    paths: list[np.ndarray] = []
    max_half_length = 200
    for _, sy, sx in seeds:
        checkpoint()
        if occupied[sy, sx] or len(paths) >= 600:
            continue
        component = int(components[sy, sx])
        arms: list[list[tuple[float, float]]] = []
        for sign in (-1, 1):
            arm: list[tuple[float, float]] = []
            x, y = float(sx), float(sy)
            prev_vx, prev_vy = vector(x, y)
            prev_vx *= sign
            prev_vy *= sign
            for _step in range(max_half_length):
                vx, vy = vector(x, y)
                if vx * prev_vx + vy * prev_vy < 0:
                    vx, vy = -vx, -vy
                # A midpoint check keeps diagonal pixel steps from bridging gaps.
                nxp, nyp = x + vx, y + vy
                if not inside((x + nxp) / 2, (y + nyp) / 2, component) or not inside(
                    nxp, nyp, component
                ):
                    break
                ix, iy = int(round(nxp)), int(round(nyp))
                if occupied[iy, ix]:
                    break
                arm.append((nxp, nyp))
                x, y = nxp, nyp
                prev_vx, prev_vy = vx, vy
            arms.append(arm)
        points = arms[0][::-1] + [(float(sx), float(sy))] + arms[1]
        if len(points) < 6:
            continue
        path = np.asarray(points, dtype=np.float32)
        paths.append(path)
        # Rasterize the accepted path only after tracing both arms, so it does
        # not stop itself. Dilated occupancy gives subsequent seeds clearance.
        for px, py in path:
            ix, iy = int(round(float(px))), int(round(float(py)))
            local_radius = radius
            if density_field is not None:
                tone = density_field[iy, ix]
                local_radius = max(1, int(round(.7 * spacing / (.6 + 1.4 * tone))))
            active = disk_x * disk_x + disk_y * disk_y <= local_radius * local_radius
            xs, ys = ix + disk_x[active], iy + disk_y[active]
            valid = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
            occupied[ys[valid], xs[valid]] = True
    return paths

"""Project persistence: a project is a folder.

::

    <projects_root>/<name>/
      project.json      # the Project model, pretty-printed — diff-able
      sources/
        upload-*.svg    # uploaded SVGs, verbatim
        gen-*.svg       # generated/baked layers, snapshotted as SVG
      assets/
        *.png           # image assets (depth maps), verbatim

Generated layers keep generator id+params in the manifest (re-editable) AND a
snapshot SVG (exact geometry survives generator-code drift); loading prefers
the snapshot. Snapshots are written by :func:`snapshot_svg`, a deliberately
tiny writer that preserves each path's ``filled`` flag as an actual SVG fill
(the vpype writer would drop it, and fills are the occlusion-mask input).

Zip export/import wraps the same folder for portability.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path as FsPath

from .compose import CanvasLayer, Project
from .model import Path
from .svg_io import doc_from_svg


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip() or "untitled"
    return cleaned


def snapshot_svg(paths: list[Path]) -> str:
    """Minimal SVG snapshot of one layer's source paths (mm units), keeping
    ``filled`` as a real fill so it round-trips through doc_from_svg."""
    xs = [x for p in paths for x, _ in p.points] or [0.0]
    ys = [y for p in paths for _, y in p.points] or [0.0]
    w = max(max(xs), 1.0)
    h = max(max(ys), 1.0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.4f}mm" '
        f'height="{h:.4f}mm" viewBox="0 0 {w:.4f} {h:.4f}">',
        '<g id="snapshot">',
    ]
    for p in paths:
        d = "M " + " L ".join(f"{x:.6f} {y:.6f}" for x, y in p.points)
        closed = len(p.points) > 2 and p.points[0] == p.points[-1]
        if closed:
            d += " Z"
        fill = "#000000" if (p.filled and closed) else "none"
        parts.append(f'<path d="{d}" fill="{fill}" stroke="#000000" stroke-width="0.1"/>')
    parts += ["</g>", "</svg>"]
    return "\n".join(parts)


def _load_layer_geometry(layer: CanvasLayer, project_dir: FsPath) -> list[Path]:
    if not layer.source.file:
        return []
    svg_text = (project_dir / layer.source.file).read_text()
    doc = doc_from_svg(svg_text, layer.source.quantization_mm, source=layer.source.file)
    if layer.source.svg_layer is not None:
        for svg_layer in doc.layers:
            if svg_layer.id == layer.source.svg_layer:
                return list(svg_layer.paths)
        return []
    return [p for lyr in doc.layers for p in lyr.paths]


def save_project(
    project: Project,
    source_geometry: dict[str, list[Path]],
    svg_files: dict[str, str],
    project_dir: FsPath,
    assets: dict[str, bytes] | None = None,
) -> None:
    """Write the folder. Mutates generator/baked layers' ``source.file`` to
    point at their (re)written snapshots."""
    (project_dir / "sources").mkdir(parents=True, exist_ok=True)
    for layer in project.layers:
        if layer.source.type in ("generator", "baked"):
            relname = f"sources/gen-{layer.id}.svg"
            (project_dir / relname).write_text(
                snapshot_svg(source_geometry.get(layer.id, []))
            )
            layer.source.file = relname
            layer.source.svg_layer = None
    for relname, text in svg_files.items():
        target = project_dir / relname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    if assets:
        (project_dir / "assets").mkdir(parents=True, exist_ok=True)
        for name, data in assets.items():
            (project_dir / "assets" / safe_name(name)).write_bytes(data)
    (project_dir / "project.json").write_text(project.model_dump_json(indent=2))


def load_project(
    project_dir: FsPath,
) -> tuple[Project, dict[str, list[Path]], dict[str, str], dict[str, bytes]]:
    """Read a folder back: (project, source_geometry, svg texts, assets)."""
    project = Project.model_validate_json((project_dir / "project.json").read_text())
    geometry: dict[str, list[Path]] = {}
    svg_files: dict[str, str] = {}
    for layer in project.layers:
        geometry[layer.id] = _load_layer_geometry(layer, project_dir)
        if layer.source.file and layer.source.type == "svg":
            svg_files.setdefault(
                layer.source.file, (project_dir / layer.source.file).read_text()
            )
    assets: dict[str, bytes] = {}
    assets_dir = project_dir / "assets"
    if assets_dir.is_dir():
        for f in sorted(assets_dir.iterdir()):
            if f.is_file():
                assets[f.name] = f.read_bytes()
    return project, geometry, svg_files, assets


def export_zip(project_dir: FsPath) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(project_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(project_dir))
    return buf.getvalue()


def import_zip(data: bytes, projects_root: FsPath, name: str) -> FsPath:
    """Extract a project zip to a fresh folder. Rejects path traversal."""
    target = projects_root / safe_name(name)
    if target.exists():
        raise FileExistsError(f"project folder already exists: {target}")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            dest = (target / info.filename).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise ValueError(f"unsafe path in zip: {info.filename}")
        zf.extractall(target)
    if not (target / "project.json").exists():
        raise ValueError("zip does not contain a project.json")
    return target

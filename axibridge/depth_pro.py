"""Optional Apple Depth Pro adapter for generating depth-map image assets."""

from __future__ import annotations

import io
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any


class DepthProUnavailable(RuntimeError):
    """Raised when Apple Depth Pro is not installed or not ready to run."""


_model_lock = threading.Lock()
_model: Any | None = None
_transform: Any | None = None
_device_label: str | None = None


def _import_depth_pro() -> Any:
    try:
        import depth_pro as depth_pro_pkg  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise DepthProUnavailable(
            "Depth Pro is not installed in the AxiBridge environment yet. "
            "Install apple/ml-depth-pro into the .venv and download its checkpoint."
        ) from exc
    return depth_pro_pkg


def _torch_device(torch: Any) -> Any:
    requested = os.environ.get("AXIBRIDGE_DEPTH_PRO_DEVICE", "").strip()
    if requested:
        return torch.device(requested)
    if getattr(getattr(torch, "backends", None), "mps", None) is not None:
        try:
            if torch.backends.mps.is_available():
                return torch.device("mps")
        except Exception:
            pass
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _checkpoint_path() -> Path | None:
    override = os.environ.get("AXIBRIDGE_DEPTH_PRO_CHECKPOINT", "").strip()
    if override:
        return Path(override).expanduser()
    try:
        from depth_pro.depth_pro import DEFAULT_MONODEPTH_CONFIG_DICT  # type: ignore[import-not-found]

        uri = DEFAULT_MONODEPTH_CONFIG_DICT.checkpoint_uri
    except Exception:
        uri = "./checkpoints/depth_pro.pt"
    return Path(uri).expanduser() if uri else None


def _cli_command() -> list[str] | None:
    raw = os.environ.get("AXIBRIDGE_DEPTH_PRO_RUN", "").strip()
    return shlex.split(raw) if raw else None


def _checked_cli_command() -> list[str]:
    cmd = _cli_command()
    if not cmd:
        raise DepthProUnavailable("Depth Pro CLI is not configured")
    exe = Path(cmd[0]).expanduser()
    if exe.is_absolute() or "/" in cmd[0]:
        if not exe.exists():
            raise DepthProUnavailable(f"Depth Pro command not found: {exe}")
        cmd[0] = str(exe)
    elif shutil.which(cmd[0]) is None:
        raise DepthProUnavailable(f"Depth Pro command not found on PATH: {cmd[0]}")
    return cmd


def status() -> dict[str, Any]:
    """Cheap readiness check for the UI. Does not load model weights."""
    if _cli_command() is not None:
        try:
            cmd = _checked_cli_command()
        except DepthProUnavailable as exc:
            return {"available": False, "ready": False, "detail": str(exc)}
        return {
            "available": True,
            "ready": True,
            "detail": "Depth Pro CLI ready; each run starts the external model process.",
            "command": cmd[0],
        }

    try:
        _import_depth_pro()
    except DepthProUnavailable as exc:
        return {"available": False, "ready": False, "detail": str(exc)}

    checkpoint = _checkpoint_path()
    if checkpoint is not None and not checkpoint.exists():
        return {
            "available": False,
            "ready": False,
            "detail": f"Depth Pro is installed, but the checkpoint is missing at {checkpoint}.",
            "checkpoint": str(checkpoint),
        }
    return {
        "available": True,
        "ready": _model is not None,
        "detail": "Depth Pro ready" if _model is not None else "Depth Pro installed; first run loads the model.",
        "checkpoint": str(checkpoint) if checkpoint is not None else None,
        "device": _device_label,
    }


def _load_model() -> tuple[Any, Any]:
    global _model, _transform, _device_label
    with _model_lock:
        if _model is not None and _transform is not None:
            return _model, _transform
        depth_pro_pkg = _import_depth_pro()
        try:
            import torch  # type: ignore[import-not-found]

            device = _torch_device(torch)
            checkpoint = _checkpoint_path()
            kwargs: dict[str, Any] = {"device": device}
            if checkpoint is not None:
                if not checkpoint.exists():
                    raise DepthProUnavailable(
                        f"Depth Pro checkpoint not found at {checkpoint}. "
                        "Run get_pretrained_models.sh from apple/ml-depth-pro, or set "
                        "AXIBRIDGE_DEPTH_PRO_CHECKPOINT."
                    )
                if os.environ.get("AXIBRIDGE_DEPTH_PRO_CHECKPOINT", "").strip():
                    from depth_pro.depth_pro import DEFAULT_MONODEPTH_CONFIG_DICT  # type: ignore[import-not-found]

                    kwargs["config"] = replace(
                        DEFAULT_MONODEPTH_CONFIG_DICT,
                        checkpoint_uri=str(checkpoint),
                    )
            model, transform = depth_pro_pkg.create_model_and_transforms(**kwargs)
            model.eval()
        except DepthProUnavailable:
            raise
        except Exception as exc:
            raise DepthProUnavailable(f"Depth Pro could not start: {exc}") from exc
        _model = model
        _transform = transform
        _device_label = str(device)
        return model, transform


def depth_asset_name(source_name: str, frame: float = 0.0) -> str:
    stem = source_name.rstrip("#")
    if "." in stem:
        stem = Path(stem).stem
    stem = stem.replace("#", "_").strip("._-") or "asset"
    frame_tag = f"_f{round(max(0.0, min(1.0, frame)) * 1000):03d}" if source_name.endswith("#") else ""
    return f"{stem}{frame_tag}_depth.png"


def _depth_to_png(depth: Any, near_white: bool) -> bytes:
    import numpy as np
    from PIL import Image

    arr = np.asarray(depth, dtype=np.float32)
    finite = np.isfinite(arr)
    if not finite.any():
        raise ValueError("Depth Pro produced no finite depth values")
    vals = arr[finite]
    if vals.size > 8:
        lo, hi = np.percentile(vals, [1.0, 99.0])
    else:
        lo, hi = float(vals.min()), float(vals.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        norm = np.zeros_like(arr, dtype=np.float32)
    else:
        norm = (arr - lo) / (hi - lo)
    norm = np.clip(norm, 0.0, 1.0)
    if near_white:
        norm = 1.0 - norm
    norm[~finite] = 0.0
    pixels = np.rint(norm * 255.0).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(pixels, "L").save(buf, "PNG")
    return buf.getvalue()


def _depth_png_from_cli(data: bytes, source_name: str, near_white: bool) -> bytes:
    import numpy as np

    cmd = _checked_cli_command()
    suffix = Path(source_name).suffix or ".png"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        input_path = root / f"input{suffix}"
        output_dir = root / "out"
        input_path.write_bytes(data)
        proc = subprocess.run(
            [*cmd, "-i", str(input_path), "-o", str(output_dir), "--skip-display"],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=float(os.environ.get("AXIBRIDGE_DEPTH_PRO_TIMEOUT", "900")),
        )
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "Depth Pro CLI failed").strip()
            raise DepthProUnavailable(msg[-800:])
        npzs = sorted(output_dir.rglob("input.npz"))
        if not npzs:
            npzs = sorted(output_dir.rglob("*.npz"))
        if not npzs:
            raise DepthProUnavailable("Depth Pro CLI did not write a depth .npz file")
        depth = np.load(npzs[0])["depth"]
        return _depth_to_png(depth, near_white)


def depth_png_from_image(data: bytes, source_name: str, near_white: bool = True) -> bytes:
    """Run Depth Pro on image bytes and return a normalized 8-bit depth PNG."""
    if _cli_command() is not None:
        return _depth_png_from_cli(data, source_name, near_white)
    depth_pro_pkg = _import_depth_pro()
    model, transform = _load_model()
    suffix = Path(source_name).suffix or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        image, _, f_px = depth_pro_pkg.load_rgb(path)
        image = transform(image)
        prediction = model.infer(image, f_px=f_px)
        depth = prediction["depth"].detach().float().cpu().numpy()
        return _depth_to_png(depth, near_white)
    finally:
        os.unlink(path)

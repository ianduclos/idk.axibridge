"""Short-lived local inference process. Imports model packages only on demand."""

import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image


def release_import_root(root):
    """Remove a completed model's top-level modules before another is imported."""
    root = Path(root).resolve()
    sys.path[:] = [p for p in sys.path if Path(p).resolve() != root]
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if filename and Path(filename).resolve().is_relative_to(root):
            del sys.modules[name]


def face_detection(config, image_path):
    import mediapipe as mp

    image = np.asarray(Image.open(image_path).convert("RGB"))
    options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=config["face_weights"]),
        running_mode=mp.tasks.vision.RunningMode.IMAGE,
        num_faces=32,
        min_face_detection_confidence=0.35,
        min_face_presence_confidence=0.35,
    )
    faces = []
    with mp.tasks.vision.FaceLandmarker.create_from_options(options) as detector:
        result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=image))
    for i, landmarks in enumerate(result.face_landmarks):
        # Only the face outline locates the crop. Mesh lines are never traced.
        indices = [
            10,
            338,
            297,
            332,
            284,
            251,
            389,
            356,
            454,
            323,
            361,
            288,
            397,
            365,
            379,
            378,
            400,
            377,
            152,
            148,
            176,
            149,
            150,
            136,
            172,
            58,
            132,
            93,
            234,
            127,
            162,
            21,
            54,
            103,
            67,
            109,
        ]
        xy = np.array([[landmarks[j].x, landmarks[j].y] for j in indices])
        low = np.clip(xy.min(0), 0, 1)
        high = np.clip(xy.max(0), 0, 1)
        cx, cy = (low + high) / 2
        rx, ry = np.maximum((high - low) / 2, 0.005)
        faces.append(
            dict(
                id=f"face-{i + 1}",
                cx=float(cx),
                cy=float(cy),
                rx=float(min(0.5, rx)),
                ry=float(min(0.5, ry)),
                enabled=True,
                origin="automatic",
            )
        )
    return faces


def main(request_path):
    import gc
    import subprocess
    from types import SimpleNamespace

    request_path = Path(request_path)
    directory = request_path.parent
    request = json.loads(request_path.read_text())
    c = request["config"]
    image = Image.open(directory / "input.png").convert("RGB")
    w, h = image.size

    def progress(frac, message):
        tmp = directory / "progress.tmp"
        tmp.write_text(json.dumps(dict(fraction=frac, message=message)))
        tmp.replace(directory / "progress.json")

    if "--faces" in sys.argv:
        (directory / "faces.json").write_text(
            json.dumps(face_detection(c, directory / "input.png"))
        )
        return
    faces = request["faces"]
    if request["detect"]:
        progress(0.02, "Finding face regions")
        if not c.get("face_python") or not c.get("face_weights"):
            raise ValueError(
                "Face detector is not configured; supply manual regions or configure MediaPipe"
            )
        subprocess.run(
            [
                c["face_python"],
                str(Path(__file__).resolve()),
                str(request_path),
                "--faces",
            ],
            check=True,
        )
        faces = json.loads((directory / "faces.json").read_text())
    (directory / "faces.json").write_text(json.dumps(faces))
    import torch
    import torch.nn.functional as F
    from torchvision.models.segmentation import (
        lraspp_mobilenet_v3_large,
        LRASPP_MobileNet_V3_Large_Weights,
    )

    device = torch.device(
        c.get("device") or ("mps" if torch.backends.mps.is_available() else "cpu")
    )
    torch.set_num_threads(4)

    def clear(model):
        del model
        gc.collect()
        if device.type == "mps":
            torch.mps.empty_cache()

    result = {}
    progress(0.08, "Reading foreground")
    model = lraspp_mobilenet_v3_large(weights=None, weights_backbone=None)
    model.load_state_dict(
        torch.load(c["person_weights"], map_location="cpu", weights_only=True)
    )
    model = model.to(device).eval()
    weights = LRASPP_MobileNet_V3_Large_Weights.DEFAULT
    batch = weights.transforms()(image).unsqueeze(0).to(device)
    with torch.inference_mode():
        logits = model(batch)["out"]
        prob = logits.softmax(1)[:, 15:16]
        result["foreground"] = (
            F.interpolate(prob, size=(h, w), mode="bilinear", align_corners=False)[0, 0]
            .cpu()
            .numpy()
        )
    del model, batch, logits, prob
    gc.collect()
    progress(0.2, "Reading whole-image contours")
    sys.path.insert(0, c["line_code"])
    from model import Generator

    model = Generator(3, 1, 3)
    model.load_state_dict(
        torch.load(c["line_weights"], map_location="cpu", weights_only=True)
    )
    model = model.to(device).eval()

    def infer(rgb, longside):
        factor = longside / max(rgb.size)
        size = tuple(max(8, int(round(d * factor / 4) * 4)) for d in rgb.size)
        small = rgb.resize(size, Image.Resampling.BICUBIC)
        batch = (
            torch.from_numpy(np.asarray(small, dtype=np.float32) / 255)
            .permute(2, 0, 1)
            .unsqueeze(0)
            .to(device)
        )
        with torch.inference_mode():
            array = model(batch)[0, 0].clamp(0, 1).cpu().numpy()
        return array

    def resized(arr, size):
        return np.asarray(
            Image.fromarray(arr).resize(size, Image.Resampling.BILINEAR),
            dtype=np.float32,
        )

    result["whole_lines"] = resized(infer(image, 768), (w, h))
    acc = np.zeros((h, w))
    weight = np.zeros((h, w))
    cw, ch = max(1, round(w * 0.64)), max(1, round(h * 0.64))
    for i, (x, y) in enumerate(((x, y) for y in [0, h - ch] for x in [0, w - cw])):
        progress(0.3 + i * 0.07, f"Reading detail crop {i + 1} of 4")
        crop = image.crop((x, y, x + cw, y + ch))
        arr = resized(infer(crop, 512), (cw, ch))
        yy, xx = np.mgrid[:ch, :cw]
        win = np.maximum(
            0.025,
            np.sin(np.pi * (xx + 0.5) / cw) ** 2 * np.sin(np.pi * (yy + 0.5) / ch) ** 2,
        )
        acc[y : y + ch, x : x + cw] += arr * win
        weight[y : y + ch, x : x + cw] += win
    result["tiled_lines"] = (acc / weight).astype(np.float32)
    for i, face in enumerate(faces):
        if not face["enabled"]:
            continue
        progress(0.6, "Reading face detail")
        x0 = max(0, int((face["cx"] - face["rx"] * 1.35) * w))
        x1 = min(w, max(x0 + 1, int(np.ceil((face["cx"] + face["rx"] * 1.35) * w))))
        y0 = max(0, int((face["cy"] - face["ry"] * 1.35) * h))
        y1 = min(h, max(y0 + 1, int(np.ceil((face["cy"] + face["ry"] * 1.35) * h))))
        result[f"face_{i}"] = infer(image.crop((x0, y0, x1, y1)), 512)
        result[f"box_{i}"] = np.array([x0, y0, x1, y1])
    del model
    gc.collect()
    release_import_root(c["line_code"])
    if c.get("normal_code") and c.get("normal_weights"):
        progress(0.7, "Reading surface form")
        sys.path.insert(0, c["normal_code"])
        for path in c.get("normal_dependencies", []):
            sys.path.insert(0, path)
        from models.dsine.v02 import DSINE_v02
        from utils.projection import intrins_from_fov
        from utils.utils import get_padding
        from torchvision import transforms

        args = SimpleNamespace(
            NNET_encoder_B=5,
            NNET_decoder_NF=2048,
            NNET_decoder_BN=False,
            NNET_decoder_down=8,
            NNET_learned_upsampling=True,
            NNET_output_dim=3,
            NNET_feature_dim=64,
            NNET_hidden_dim=64,
            NRN_prop_ps=5,
            NRN_num_iter_train=5,
            NRN_num_iter_test=5,
            NRN_ray_relu=True,
        )
        model = DSINE_v02(args)
        state = torch.load(c["normal_weights"], map_location="cpu", weights_only=True)[
            "model"
        ]
        model.load_state_dict({k.removeprefix("module."): v for k, v in state.items()})
        del state
        model = model.to(device).eval()
        model.pixel_coords = model.pixel_coords.to(device)
        factor = 768 / max(w, h)
        nw, nh = max(8, round(w * factor)), max(8, round(h * factor))
        small = image.resize((nw, nh), Image.Resampling.LANCZOS)
        batch = (
            torch.from_numpy(np.asarray(small, dtype=np.float32) / 255)
            .permute(2, 0, 1)
            .unsqueeze(0)
            .to(device)
        )
        pad = get_padding(nh, nw)
        batch = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])(
            F.pad(batch, pad)
        )
        intrinsic = intrins_from_fov(60.0, nh, nw, device=device).unsqueeze(0)
        intrinsic[:, 0, 2] += pad[0]
        intrinsic[:, 1, 2] += pad[2]
        with torch.inference_mode():
            out = model(batch, intrins=intrinsic)[-1][
                :, :, pad[2] : pad[2] + nh, pad[0] : pad[0] + nw
            ]
            out = F.normalize(
                F.interpolate(out, size=(h, w), mode="bilinear", align_corners=False),
                dim=1,
            )
            result["normals"] = out[0].permute(1, 2, 0).cpu().numpy()
        del model, out, batch
        gc.collect()
    progress(0.9, "Preparing drawing evidence")
    np.savez(directory / "output.npz", **result)


if __name__ == "__main__":
    main(sys.argv[1])

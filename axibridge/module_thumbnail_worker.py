"""Isolated one-shot renderer for module-library identifying thumbnails."""
from __future__ import annotations

import io
import json
import sys

from PIL import Image, ImageDraw

from .assets import asset_store
from .gallery import bounds, thumbnail
from .model import Path
from .registry import EffectContext, get_effect, get_source, load_builtin_modules


def _fixture_image() -> bytes:
    image = Image.new("L", (160, 100), 245)
    draw = ImageDraw.Draw(image)
    draw.ellipse((18, 12, 94, 88), fill=45)
    draw.polygon([(72, 82), (118, 18), (148, 88)], fill=115)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def main() -> int:
    request = json.loads(sys.stdin.read())
    load_builtin_modules()
    kind, module_id = request["kind"], request["module"]
    module = get_source(module_id) if kind == "source" else get_effect(module_id)
    params = dict(request["params"])
    schema = module.Params.model_json_schema()
    # This process owns its AssetStore, so fixture injection cannot mutate the
    # live project's names, bytes, version, or generation cache.
    asset_store.put("module-library-fixture.png", _fixture_image())
    for name, node in schema.get("properties", {}).items():
        if _contains_asset(node, schema.get("$defs", {}), set()):
            params[name] = "module-library-fixture.png"
    if kind == "source":
        doc = module.generate(module.Params(**params))
        paths = [path for layer in doc.layers for path in layer.paths]
    else:
        fixture = [
            Path(points=[(8, 12), (42, 7), (48, 36), (13, 42), (8, 12)], filled=True),
            Path(points=[(4, 48), (28, 26), (55, 47), (78, 18), (96, 43)]),
        ]
        paths = module.apply(fixture, module.Params(**params), EffectContext(
            layer_id="module-library-fixture", seed=1729, page=(0, 0, 100, 55)))
    if not paths:
        return 2
    x0, y0, x1, y1 = bounds(paths)
    sys.stdout.write(thumbnail(paths, stroke_width=max(x1 - x0, y1 - y0, 1) / 200))
    return 0


def _contains_asset(node, defs, seen):
    if isinstance(node, list):
        return any(_contains_asset(item, defs, seen) for item in node)
    if not isinstance(node, dict):
        return False
    if node.get("format") == "asset":
        return True
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        key = ref.rsplit("/", 1)[-1]
        if key in seen:
            return False
        return _contains_asset(defs.get(key, {}), defs, seen | {key})
    return any(_contains_asset(value, defs, seen) for value in node.values())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(1)

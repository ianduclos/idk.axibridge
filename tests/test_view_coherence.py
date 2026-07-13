"""Orientation coherence pass: params stay stored in machine-frame mm
FOREVER — all portrait/landscape display mapping happens once, in the
frontend, driven by json_schema_extra tags (viewRotate/viewAngle/viewSize/
viewOrient/viewAxis). This locks the architecture's two guarantees:

  (a) toggling the project's `view` never touches backend geometry — the
      single resolve path (session.resolved -> compose.resolve_project)
      doesn't read `view` at all, so the same params resolve byte-identical
      regardless of which view is active.
  (b) the tagged Pydantic fields actually carry their tags in the schema
      the frontend renders from.
  (c) the pure JS mapping functions in static/js/viewmap.js hold the
      documented sign convention (verified with a node shellout — the
      module has zero imports so it runs standalone under node)."""

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _round_points(layers):
    """SVG save/load round-trips coordinates through a fixed-precision text
    format (see ARCHITECTURE.md / CLAUDE.md on svgelements mm conversion),
    so points lose precision on the order of ~1e-6 mm on a load — nowhere
    near plotter resolution. Round (well above that noise floor, well below
    anything the plotter can resolve) before comparing so expected precision
    loss doesn't masquerade as a geometry change."""
    return [
        [{**p, "points": [[round(x, 3), round(y, 3)] for x, y in p["points"]]} for p in l["paths"]]
        for l in layers
    ]


def _png_blob(size=(40, 30)) -> bytes:
    from PIL import Image

    img = Image.new("L", size)
    img.putdata([255 - int(255 * (i % size[0]) / size[0]) for i in range(size[0] * size[1])])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        yield c


# ---------------------------------------------------------------------------
# (a) resolve is bit-identical across view toggles
# ---------------------------------------------------------------------------

def test_resolve_identical_across_view_toggle(client):
    r = client.post("/api/assets", files={"file": ("depth.png", _png_blob(), "image/png")})
    assert r.status_code == 200, r.text
    image_name = r.json()["name"]

    lay = client.post("/api/layers/generate", json={
        "module": "image_threshold",
        "params": {"image": image_name, "width": 30, "detail": 2.0, "threshold_max": 0.6},
    }).json()

    effects = [{
        "effect": "depth_displace",
        "enabled": True,
        "params": {
            "image": image_name, "rotate": 270, "width": 40,
            "amplitude": 4.0, "angle_deg": 30.0,
        },
    }]
    r = client.patch(f"/api/layers/{lay['id']}", json={"effects": effects})
    assert r.status_code == 200, r.text

    r = client.put("/api/project", json={"view": "landscape"})
    assert r.status_code == 200, r.text
    landscape = client.get("/api/compose/resolved").json()["layers"]

    r = client.put("/api/project", json={"view": "portrait"})
    assert r.status_code == 200, r.text
    portrait = client.get("/api/compose/resolved").json()["layers"]

    assert [l["paths"] for l in portrait] == [l["paths"] for l in landscape]


def test_view_toggle_survives_save_load_with_rotate_param(client):
    """Extends the save/load roundtrip coverage (tests/test_save_roundtrip.py):
    a project saved with view=portrait and a viewRotate-tagged param at a
    non-default stored value loads back byte-identical — the tags are
    display-only and never touch the stored value or the save format."""
    r = client.post("/api/assets", files={"file": ("depth.png", _png_blob(), "image/png")})
    image_name = r.json()["name"]
    client.post("/api/layers/generate", json={
        "module": "image_threshold",
        "params": {"image": image_name, "width": 30, "detail": 2.0, "rotate": 270},
    })
    client.put("/api/project", json={"view": "portrait"})

    before = client.get("/api/project").json()
    before_resolved = client.get("/api/compose/resolved").json()["layers"]
    r = client.post("/api/project/save", json={"name": "view coherence roundtrip"})
    assert r.status_code == 200, r.text

    client.post("/api/project/new")
    r = client.post("/api/project/load", json={"name": "view coherence roundtrip"})
    assert r.status_code == 200, r.text

    after = client.get("/api/project").json()
    assert after["view"] == "portrait"
    assert after["layers"][0]["source"]["params"]["rotate"] == before["layers"][0]["source"]["params"]["rotate"] == 270
    after_resolved = client.get("/api/compose/resolved").json()["layers"]
    assert _round_points(after_resolved) == _round_points(before_resolved)


# ---------------------------------------------------------------------------
# (b) schema tags land on the right fields
# ---------------------------------------------------------------------------

def test_schema_tags_present():
    from axibridge.effects.depth_displace import DepthDisplaceParams
    from axibridge.effects.hatch_fill import HatchFillParams
    from axibridge.effects.perspective import PerspectiveParams
    from axibridge.sources.dots import DotsParams
    from axibridge.sources.image_threshold import ImageThresholdParams
    from axibridge.sources.lineart_hatch import LineartHatchParams
    from axibridge.sources.linescan import LinescanParams
    from axibridge.sources.longwave import LongwaveParams
    from axibridge.sources.waves import WavesParams

    it_props = ImageThresholdParams.model_json_schema()["properties"]
    assert it_props["rotate"]["viewRotate"] is True
    assert it_props["width"]["viewSize"] is True

    dots_props = DotsParams.model_json_schema()["properties"]  # inherits PixelGenParams
    assert dots_props["rotate"]["viewRotate"] is True
    assert dots_props["width"]["viewSize"] is True
    assert dots_props["line_direction"]["viewAngle"] == 180

    waves_props = WavesParams.model_json_schema()["properties"]
    assert waves_props["angle"]["viewAngle"] == 360

    lh_props = LineartHatchParams.model_json_schema()["properties"]
    assert lh_props["angle_deg"]["viewAngle"] == 180

    lw_props = LongwaveParams.model_json_schema()["properties"]
    assert lw_props["direction"]["viewOrient"] is True

    ls_props = LinescanParams.model_json_schema()["properties"]
    assert ls_props["direction"]["viewOrient"] is True

    dd_props = DepthDisplaceParams.model_json_schema()["properties"]
    assert dd_props["rotate"]["viewRotate"] is True
    assert dd_props["width"]["viewSize"] is True
    assert dd_props["angle_deg"]["viewAngle"] == 360
    assert dd_props["x"]["viewAxis"] is True
    assert dd_props["y"]["viewAxis"] is True

    hf_props = HatchFillParams.model_json_schema()["properties"]
    assert hf_props["angle_deg"]["viewAngle"] == 180

    # perspective: pivot stays viewAxis (unchanged); tilt_x/tilt_y are
    # deliberately NOT tagged (sign semantics unverified) — sanity check
    # both directions so this test would fail loudly if that changed.
    persp_props = PerspectiveParams.model_json_schema()["properties"]
    assert persp_props["pivot_dx"]["viewAxis"] is True
    assert persp_props["pivot_dy"]["viewAxis"] is True
    assert "viewAxis" not in persp_props["tilt_x"]
    assert "viewAngle" not in persp_props["tilt_x"]
    assert "viewAxis" not in persp_props["tilt_y"]
    assert "viewAngle" not in persp_props["tilt_y"]


# ---------------------------------------------------------------------------
# (c) viewmap.js sign convention, verified standalone under node
# ---------------------------------------------------------------------------

VIEWMAP_JS = Path(__file__).resolve().parent.parent / "axibridge" / "static" / "js" / "viewmap.js"

_NODE_SCRIPT = """
import {{ rotToDisplay, rotToStored, sizeFactor }} from "{module_url}";

const results = {{}};

// full rotate table, both directions, portrait
results.displayTable = [0, 90, 180, 270].map((v) => rotToDisplay(v, 360, true));
results.storedTable = [0, 90, 180, 270].map((v) => rotToStored(v, 360, true));

// landscape is the identity map
results.landscapeDisplay = rotToDisplay(270, 360, false);
results.landscapeStored = rotToStored(0, 360, false);

// sanity anchor: stored 270 in portrait must display as 0
results.anchor = rotToDisplay(270, 360, true);

// sizeFactor: a 100x50 (w x h) asset, rotate=0 -> f = h/w = 0.5
results.sizeFactorFlat = sizeFactor(
  {{ image: "a", rotate: 0 }},
  {{ properties: {{ image: {{ format: "asset" }}, rotate: {{ viewRotate: true }} }} }},
  [{{ name: "a", width: 100, height: 50, frames: 1 }}],
);
// rotate=90 swaps w/h before the ratio: f = w/h = 2
results.sizeFactorRotated = sizeFactor(
  {{ image: "a", rotate: 90 }},
  {{ properties: {{ image: {{ format: "asset" }}, rotate: {{ viewRotate: true }} }} }},
  [{{ name: "a", width: 100, height: 50, frames: 1 }}],
);
// unknown asset -> null
results.sizeFactorMissing = sizeFactor(
  {{ image: "nope" }},
  {{ properties: {{ image: {{ format: "asset" }} }} }},
  [{{ name: "a", width: 100, height: 50, frames: 1 }}],
);

console.log(JSON.stringify(results));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_viewmap_js_sign_convention(tmp_path):
    script = _NODE_SCRIPT.format(module_url=VIEWMAP_JS.as_uri())
    script_path = tmp_path / "run_viewmap.mjs"
    script_path.write_text(script)

    proc = subprocess.run([sys.executable and shutil.which("node"), str(script_path)],
                           capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    # user 0/90/180/270 <-> stored 270/0/90/180 (the rotate mapping table)
    assert out["displayTable"] == [90, 180, 270, 0]
    assert out["storedTable"] == [270, 0, 90, 180]
    assert out["landscapeDisplay"] == 270
    assert out["landscapeStored"] == 0
    assert out["anchor"] == 0
    assert out["sizeFactorFlat"] == pytest.approx(0.5)
    assert out["sizeFactorRotated"] == pytest.approx(2.0)
    assert out["sizeFactorMissing"] is None

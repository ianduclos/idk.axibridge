import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.module_library import ModuleLibraryStore


@pytest.fixture
def library(tmp_path):
    return ModuleLibraryStore(tmp_path / "module-library")


@pytest.fixture
def client():
    with TestClient(create_app()) as value:
        yield value


def test_store_is_atomic_and_allows_duplicate_names(library):
    first = library.create("source", "lissajous", "Same", {"freq_x": 4})
    second = library.create("source", "lissajous", "Same", {"freq_x": 5})
    assert first["id"] != second["id"]
    assert {p["name"] for p in library.list()["presets"]} == {"Same"}
    assert json.loads(library.path.read_text())["version"] == 1
    assert not list(library.root.glob("*.tmp"))


def test_preset_filters_capture_and_asset_params(library):
    drawing = library.create("source", "drawing", "Line", {
        "strokes": [[(1, 2, 0), (3, 4, 1)]], "smooth": 2,
    })
    assert "strokes" not in drawing["params"]
    assert drawing["params"]["smooth"] == 2

    image = library.create("source", "linedraw", "Image", {"image": "private.png"})
    assert "image" not in image["params"]


def test_resolve_defaults_excluded_state_and_preserves_asset(library):
    preset = library.create("source", "linedraw", "Fine", {"hatch_scale": 3})
    resolved = library.resolve("source", "linedraw", preset["id"],
                               {"image": "current.png"})
    assert resolved["image"] == "current.png"
    assert resolved["hatch_scale"] == 3

    drawing = library.create("source", "drawing", "Smooth", {"smooth": 3})
    resolved = library.resolve("source", "drawing", drawing["id"], {
        "strokes": [[(1, 2, 0), (3, 4, 1)]],
    })
    assert resolved["strokes"] == []
    assert resolved["smooth"] == 3

    # A browser can apply this while another module's form is current; only
    # compatible asset references are considered from that old form.
    switched = library.resolve("source", "lissajous", None,
                               {"image": "old.png", "other_module_field": 4})
    assert switched["freq_x"] == 3


def test_resolve_rejects_unknown_and_incompatible_saved_values(library):
    with pytest.raises(ValueError, match="Unknown saved"):
        library.create("source", "lissajous", "Bad", {"retired_field": 2})

    preset = library.create("source", "lissajous", "Good", {})
    data = json.loads(library.path.read_text())
    data["presets"][0]["params"]["samples"] = "wrong"
    library.path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        library.resolve("source", "lissajous", preset["id"], {})

    from axibridge.registry import get_source
    magnetic = get_source("magnetic_field").Params().model_dump()
    magnetic["magnets"][0]["retired_nested_field"] = True
    with pytest.raises(ValueError, match="retired_nested_field"):
        library.create("source", "magnetic_field", "Nested", magnetic)


def test_resolve_resanitizes_hand_edited_forbidden_fields(library):
    preset = library.create("source", "drawing", "Clean", {"smooth": 2})
    data = json.loads(library.path.read_text())
    data["presets"][0]["params"]["strokes"] = [[(1, 2, 0), (3, 4, 1)]]
    library.path.write_text(json.dumps(data))
    assert library.resolve("source", "drawing", preset["id"], {})["strokes"] == []


def test_magnetic_preset_keeps_settings_but_resets_arrangement(library):
    from axibridge.registry import get_source

    defaults = get_source("magnetic_field").Params().model_dump()
    params = {**defaults, "seed": 91, "magnets": []}
    preset = library.create("source", "magnetic_field", "Field", params)
    assert preset["params"]["seed"] == 91
    assert "magnets" not in preset["params"]
    assert "mix_active" not in preset["params"]
    resolved = library.resolve("source", "magnetic_field", preset["id"], {})
    assert resolved["seed"] == 91
    assert resolved["magnets"] == defaults["magnets"]
    assert resolved["mix_active"] == defaults["mix_active"]


def test_magnetic_seed_round_trips_through_api(client):
    made = client.post("/api/module-library/presets", json={
        "kind": "source", "module": "magnetic_field", "name": "Seeded",
        "params": {"seed": 2056731596},
    }).json()
    assert made["params"]["seed"] == 2056731596
    resolved = client.post("/api/module-library/resolve", json={
        "kind": "source", "module": "magnetic_field", "preset_id": made["id"],
        "current_params": {"seed": 356727607},
    }).json()["params"]
    assert resolved["seed"] == 2056731596


def test_missing_module_remains_listable_and_removable(library):
    preset = library.create("source", "lissajous", "Old", {})
    data = json.loads(library.path.read_text())
    data["presets"][0]["module"] = "removed_module"
    library.path.write_text(json.dumps(data))
    listed = library.list()
    assert listed["presets"][0]["module"] == "removed_module"
    assert listed["warnings"]
    with pytest.raises(KeyError):
        library.resolve("source", "removed_module", preset["id"], {})
    library.delete(preset["id"])
    assert library.list()["presets"] == []


def test_identifiers_are_read_only_on_patch(client):
    created = client.post("/api/module-library/presets", json={
        "kind": "source", "module": "lissajous", "name": "A", "params": {},
    }).json()
    response = client.patch(f"/api/module-library/presets/{created['id']}", json={
        "module": "shape",
    })
    assert response.status_code == 422


def test_preferences_and_thumbnail_api(client):
    response = client.put("/api/module-library/preferences/effect/coherent_jitter", json={
        "starred": True, "tags": [" Texture ", "texture"],
    })
    assert response.status_code == 200
    assert response.json()["tags"] == ["Texture"]
    thumb = client.get("/api/module-library/modules/effect/coherent_jitter/thumbnail")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"].startswith("image/svg+xml")
    assert thumb.headers["cache-control"] == "private, no-cache"


def test_thumbnail_endpoint_names_registered_module_when_render_fails(client, monkeypatch):
    from axibridge import module_library_api

    def fail(*args):
        raise ValueError("busy")

    monkeypatch.setattr(module_library_api.module_library_store, "thumbnail", fail)
    response = client.get("/api/module-library/modules/source/lissajous/thumbnail")
    assert response.status_code == 200
    assert response.headers["x-preview-unavailable"] == "true"
    assert "Lissajous / harmonograph" in response.text
    assert "polyline" not in response.text
    assert client.get("/api/module-library/modules/source/no-such-tool/thumbnail").status_code == 404


def test_real_thumbnails_use_fixture_without_touching_live_assets(library):
    from axibridge.assets import asset_store
    from axibridge.gallery import thumbnail
    from axibridge.model import Path

    before = (asset_store.names(), asset_store.version())
    generic = thumbnail([Path(points=[(8, 12), (42, 7), (48, 36), (13, 42), (8, 12)],
                              filled=True),
                         Path(points=[(4, 48), (28, 26), (55, 47), (78, 18), (96, 43)])])
    image_svg = library.thumbnail("source", "linedraw")
    effect_svg = library.thumbnail("effect", "hatch_fill")
    assert image_svg != generic
    assert effect_svg != generic
    assert image_svg != effect_svg
    assert 'stroke-width="0.' in image_svg
    assert (asset_store.names(), asset_store.version()) == before


def test_thumbnail_single_flight_and_two_renderer_limit(library, monkeypatch):
    lock = threading.Lock()
    active = peak = calls = 0

    def render(kind, module, params):
        nonlocal active, peak, calls
        with lock:
            active += 1
            calls += 1
            peak = max(peak, active)
        time.sleep(.04)
        with lock:
            active -= 1
        return f"<svg>{module}</svg>"

    monkeypatch.setattr(library, "_render_thumbnail", render)
    modules = ["lissajous", "grid", "flowfield", "polygon"]
    threads = [threading.Thread(target=library.thumbnail, args=("source", module))
               for module in modules]
    # Duplicate requests share one render.
    threads += [threading.Thread(target=library.thumbnail, args=("source", "lissajous"))
                for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak == 2
    assert calls == len(modules)
    assert library.thumbnail("source", "lissajous") == "<svg>lissajous</svg>"
    assert calls == len(modules)


def test_thumbnail_queue_rejects_excess_immediately(library):
    for _ in range(10):
        assert library._thumb_capacity.acquire(blocking=False)
    started = time.monotonic()
    with pytest.raises(ValueError, match="queue is full"):
        library.thumbnail("source", "lissajous")
    assert time.monotonic() - started < .1
    for _ in range(10):
        library._thumb_capacity.release()


def test_preset_detail_api(client):
    created = client.post("/api/module-library/presets", json={
        "kind": "effect", "module": "multipass", "name": "Double", "params": {},
    }).json()
    assert client.get(f"/api/module-library/presets/{created['id']}").json() == created
    assert client.get(f"/api/module-library/presets/{'0' * 32}").status_code == 404

"""Study bench v3 (2026-10-19), server side: each ink's colour and width in the
preview, the slow-result memo, and the study gallery's thumbnails."""
import time

from fastapi.testclient import TestClient

from axibridge import gencache
from axibridge.app import create_app
from axibridge.gesture_studies_thumbs import KEY_RE, key_of, thumbnails
from axibridge.registry import get_source, load_builtin_modules
from axibridge.sources import gesture_studies as GS
from axibridge.sources._gesture_studies import studies as ST

load_builtin_modules()
SRC = get_source("gesture_studies")


def params(sid, values=None, **extra):
    return {"study": ST.builtin(sid).model_dump(mode="json"), "values": values or {}, **extra}


def test_preview_names_each_inks_colour_and_width():
    c = TestClient(create_app())
    out = c.post("/api/generators/preview", json={"module": "gesture_studies", "params": params("limb_signs")}).json()
    runs = out["styles"]
    assert sum(r["paths"] for r in runs) == len(out["lines"])
    assert {r["color"].lower() for r in runs} == {"#100f0f", "#af3029"}      # black and red limbs
    assert all(r["width"] == 0.35 for r in runs)
    # a chorus: each voice in its voice's ink, in the voices' order
    out = c.post("/api/generators/preview", json={"module": "gesture_studies", "params": params("chorus")}).json()
    assert [r["color"] for r in out["styles"]] == [layer["color"] for layer in out["layers"]]
    # other generators are unchanged
    out = c.post("/api/generators/preview", json={"module": "lissajous", "params": {}}).json()
    assert "styles" not in out


def test_styles_follow_the_engine_paths_exactly():
    doc = SRC.generate(SRC.Params(**params("found_ground")))
    paths = [p for layer in doc.layers for p in layer.paths]
    runs = SRC.preview_styles(doc)
    assert sum(r["paths"] for r in runs) == len(paths) and len(runs) >= 3


def test_slow_results_are_kept_apart_from_gencache(monkeypatch):
    GS.clear_slow_cache()
    monkeypatch.setattr(GS, "SLOW_SECONDS", 0.0)            # every result counts as slow here
    p = SRC.Params(**params("bold_swell", {"seed": 4}))
    first = SRC.generate(p)
    gencache.clear()
    assert SRC.generate(p) is first                          # served from the slow memo
    monkeypatch.setattr(GS, "_slow_limits", lambda: (2, 10**9))
    for s in (5, 6, 7):
        SRC.generate(SRC.Params(**params("bold_swell", {"seed": s})))
    assert len(GS._SLOW) == 2                                # bounded (AXIBRIDGE_CACHE_BUDGET scales it)
    GS.clear_slow_cache()


def test_thumbnails_draw_in_the_background_and_are_served():
    c = TestClient(create_app())
    st = ST.check_study(ST.builtin("bold_swell"))
    key = key_of(st)
    assert KEY_RE.fullmatch(key) and key.startswith("bold_swell-v1-")
    status = c.get("/api/gesture-studies/thumbnails").json()["thumbnails"]
    assert set(ST.builtin_ids()) <= set(status)
    r = c.post("/api/gesture-studies/thumbnails", json={"ids": ["bold_swell", "no_such_study"]}).json()["thumbnails"]
    assert set(r) == {"bold_swell"} and r["bold_swell"]["state"] in ("queued", "drawing", "ready")
    for _ in range(240):
        s = c.get("/api/gesture-studies/thumbnails").json()["thumbnails"]["bold_swell"]
        if s["state"] in ("ready", "failed"):
            break
        time.sleep(0.25)
    assert s["state"] == "ready", s
    assert s["seconds"] >= 0 and s["slow"] is False
    svg = c.get(f"/api/gesture-studies/thumbnail/{key}")
    assert svg.status_code == 200 and svg.headers["content-type"] == "image/svg+xml"
    assert svg.text.startswith("<svg") and "<polyline" in svg.text
    assert thumbnails.file(key).parent.is_relative_to(thumbnails.root)
    # the cache is on disk, in the machine-level config dir the tests isolate
    import os
    assert str(thumbnails.root).startswith(os.environ["AXIBRIDGE_CONFIG_DIR"])
    assert c.get("/api/gesture-studies/thumbnail/../../etc").status_code == 404
    assert c.get("/api/gesture-studies/thumbnail/bold_swell-v1-000000000000").status_code == 404
    # a study that draws differently is a different thumbnail
    moved = st.model_copy(update={"recipe": {**st.recipe, "seed": 1}})
    assert key_of(moved) != key

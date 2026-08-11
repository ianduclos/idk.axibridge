"""system_fonts.py: best-effort OS font discovery + the bundled-font
registry that feeds text_fill.py's font picker. Must never raise, even on a
machine with none of the search directories (the Pi) or a broken font file."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axibridge import system_fonts as sf
from axibridge.app import create_app


@pytest.fixture(autouse=True)
def clean_cache():
    """Isolate each test's view of the module cache and bundled registry —
    text_fill.py registers "recursive" at import time, which must survive."""
    before_bundled = list(sf._bundled)
    before_cache = sf._cache
    yield
    sf._bundled[:] = before_bundled
    sf._cache = before_cache


def test_no_search_dirs_found_returns_empty_not_raise(monkeypatch, tmp_path):
    # simulates the Pi: none of the usual font directories exist
    monkeypatch.setattr(sf, "_SEARCH_DIRS", [tmp_path / "nowhere"])
    assert sf.catalogue(refresh=True) == list(sf._bundled)


def test_a_broken_font_file_is_skipped_not_raised(monkeypatch, tmp_path):
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "not-a-font.ttf").write_bytes(b"not actually a font file")
    monkeypatch.setattr(sf, "_SEARCH_DIRS", [d])
    assert sf.catalogue(refresh=True) == list(sf._bundled)  # no crash, no bogus entry


def test_register_bundled_appears_in_catalogue(monkeypatch, tmp_path):
    monkeypatch.setattr(sf, "_SEARCH_DIRS", [tmp_path / "nowhere"])
    sf.catalogue(refresh=True)
    sf.register_bundled("test-font", "Test Font", "/dev/null")
    cat = sf.catalogue()
    assert any(f.id == "test-font" and f.source == "bundled" for f in cat)


def test_find_returns_none_for_unknown_id():
    assert sf.find("sys:/nonexistent/path.ttf#0") is None


def test_recursive_is_registered_at_import_time():
    # text_fill.py's module-level register_bundled call must have run by now
    # (load_builtin_modules imports every sources/*.py module)
    from axibridge.registry import load_builtin_modules
    load_builtin_modules()
    assert sf.find("recursive") is not None


def test_real_scan_never_raises_and_is_deduped_by_resolved_path():
    cat = sf.catalogue(refresh=True)
    paths_and_faces = [(f.path, f.font_number) for f in cat if f.source == "system"]
    assert len(paths_and_faces) == len(set(paths_and_faces))


# -- API surface --------------------------------------------------------------


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def test_api_fonts_endpoint_includes_bundled_recursive(client):
    r = client.get("/api/fonts").json()
    assert any(f["id"] == "recursive" and f["source"] == "bundled" for f in r["fonts"])


def test_api_state_includes_fonts_key(client):
    r = client.get("/api/state").json()
    assert "fonts" in r
    assert any(f["id"] == "recursive" for f in r["fonts"])

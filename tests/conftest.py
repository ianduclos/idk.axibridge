"""Test isolation: point the machine-level stores at a throwaway config dir
BEFORE anything imports axibridge.stores (singletons bind paths at import)."""

import os
import tempfile

_cfg = tempfile.mkdtemp(prefix="axibridge-test-cfg-")
os.environ["AXIBRIDGE_CONFIG_DIR"] = _cfg
os.environ["AXIBRIDGE_NO_AUTOCONNECT"] = "1"  # never grab real hardware in tests

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_session(tmp_path):
    """Reset the session and point projects_root at a per-test tmp dir."""
    from axibridge.compose import Project
    from axibridge.registry import load_builtin_modules
    from axibridge.session import session
    from axibridge.stores import settings_store

    load_builtin_modules()
    session.project = Project()
    session.project_dir = None
    session.source_geometry.clear()
    session.svg_files.clear()
    session._shaped_cache.clear()
    settings_store.update({
        "projects_root": str(tmp_path / "projects"),
        "holder_calibration": {"dx_per_mm": 0.0, "dy_per_mm": 0.0},
        "backend_params": {},
        "soft_limits": {},
    })
    yield

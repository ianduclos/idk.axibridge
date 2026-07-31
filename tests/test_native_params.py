"""Regressions for the native backend's option handling and param persistence.

The EBB interpolates pen-delay values verbatim into command strings: a float
option produces e.g. "SP,1,253.0,1", which firmware 2.7.0 rejects with
"!7 Err: Extra parmater" — and that stray reply line desynchronizes plotink's
one-command-one-response bookkeeping for the rest of the session (reads as
"USB connection lost" on a healthy link). pyaxidraw declares every numeric
option argparse type=int; _apply must enforce the same.
"""

from types import SimpleNamespace

from axibridge.backends.axidraw_native import NativeAxidrawBackend, NativeParams


def _stub_backend():
    b = NativeAxidrawBackend()
    b._ad = SimpleNamespace(options=SimpleNamespace(), update=lambda: None)
    return b


def test_apply_casts_numeric_options_to_int():
    b = _stub_backend()
    b._apply(NativeParams(
        speed_pendown=25.6, pen_delay_down=120.4, pen_delay_up=-200.0,
        pen_pos_down=40.5, pen_rate_raise=75.0,
    ))
    opts = b._ad.options
    for name in (
        "speed_pendown", "speed_penup", "accel", "pen_pos_down", "pen_pos_up",
        "pen_rate_lower", "pen_rate_raise", "pen_delay_down", "pen_delay_up",
        "model",
    ):
        assert type(getattr(opts, name)) is int, name
    assert opts.pen_delay_down == 120
    assert opts.pen_delay_up == -200
    assert type(opts.const_speed) is bool


def test_params_survive_a_fresh_project():
    from axibridge.compose import Project
    from axibridge.session import session

    session.set_params("simulator", {"time_scale": 250})
    session.project = Project()  # what a server restart amounts to
    assert session.params_for("simulator").time_scale == 250


def test_project_params_win_over_machine_defaults():
    from axibridge.session import session
    from axibridge.stores import settings_store

    settings_store.update({"backend_params": {"simulator": {"time_scale": 250}}})
    session.project.backend_params["simulator"] = {"time_scale": 99}
    assert session.params_for("simulator").time_scale == 99


def test_apply_casts_machine_options_to_int():
    b = _stub_backend()
    b._apply(NativeParams(resolution=1.0, penlift=2.0, model=5.0))
    for name in ("resolution", "penlift", "model"):
        assert type(getattr(b._ad.options, name)) is int, name
    assert b._ad.options.resolution == 1
    assert b._ad.options.penlift == 2
    assert b._ad.options.model == 5


def test_model_syncs_stock_envelope_but_never_a_custom_one():
    from axibridge.machine import manager

    saved = manager.limits.model_copy()
    try:
        manager.limits.width, manager.limits.height = 300.0, 218.0  # stock V3
        assert manager.sync_limits_for_model(2) is True
        assert (manager.limits.width, manager.limits.height) == (430.0, 297.0)
        assert manager.sync_limits_for_model(5) is True  # stock → stock follows
        assert (manager.limits.width, manager.limits.height) == (864.0, 594.0)
        manager.limits.width = 999.0  # hand-tuned: no longer a stock envelope
        assert manager.sync_limits_for_model(1) is False
        assert manager.limits.width == 999.0
    finally:
        manager.limits = saved


def test_envelope_tolerance_ignores_float_noise():
    from axibridge.machine import manager
    from axibridge.model import Layer, Path, PathDocument

    saved = manager.limits.model_copy()
    try:
        manager.limits.width, manager.limits.height = 300.0, 218.0
        manager.limits.enabled = True
        hair = PathDocument(layers=[Layer(id=1, name="l", paths=[
            Path(points=[(0.0, 0.0), (300.04, 217.96)])])])
        assert manager.check_envelope(hair) == []  # 0.04mm over is noise
        over = PathDocument(layers=[Layer(id=1, name="l", paths=[
            Path(points=[(0.0, 0.0), (301.0, 100.0)])])])
        assert manager.check_envelope(over)  # 1mm over is a real violation
    finally:
        manager.limits = saved

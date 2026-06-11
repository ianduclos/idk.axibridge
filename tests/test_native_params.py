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

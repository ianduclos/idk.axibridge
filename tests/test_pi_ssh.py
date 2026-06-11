"""Pi ssh backend — command construction only (no network in tests)."""

from axibridge.backends.pi_ssh import PiSshBackend, PiSshParams


def test_flags_are_ints():
    b = PiSshBackend()
    flags = b._flags(PiSshParams(speed_pendown=25.6, pen_pos_down=40.4, const_speed=True))
    s = " ".join(flags)
    assert "--speed_pendown 26" in s and "--pen_pos_down 40" in s
    assert "." not in s.replace("--", "")  # no float ever reaches axicli
    assert "--const_speed" in s and "--model 1" in s


def test_jog_dead_reckons_in_mm(monkeypatch):
    b = PiSshBackend()
    b._connected = True
    sent = []
    monkeypatch.setattr(b, "_axicli_run", lambda p, args, timeout=60: sent.append(args))
    pos = b.jog(25.4, -12.7, PiSshParams())
    assert pos == (25.4, -12.7)
    assert ["-m", "manual", "-M", "walk_x", "--walk_dist", "1.0000"] in sent  # inches
    assert ["-m", "manual", "-M", "walk_y", "--walk_dist", "-0.5000"] in sent


def test_capabilities_are_honest():
    caps = PiSshBackend().capabilities()
    assert caps.jog and caps.pen_control
    assert not caps.pause_resume and not caps.raw_ebb and not caps.live_position
    assert not caps.requires_serial_port

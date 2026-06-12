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


def test_plot_detaches_and_polls(monkeypatch):
    import types

    from axibridge.backends.base import JobControl
    from axibridge.model import Layer, Path, PathDocument

    b = PiSshBackend()
    b._connected = True
    calls = []

    def fake_run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(" ".join(cmd))
        joined = " ".join(cmd)
        if cmd[0] == "scp":
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if "setsid nohup" in joined:
            return types.SimpleNamespace(returncode=0, stdout="4242\n", stderr="")
        if "cat" in joined and ".exit" in joined:
            # first poll: still running; second: done
            n = sum(".exit" in c and "cat" in c for c in calls)
            return types.SimpleNamespace(returncode=0,
                                         stdout="RUNNING\n" if n < 2 else "0\n", stderr="")
        if "tail" in joined:
            return types.SimpleNamespace(returncode=0, stdout="Elapsed time: 1.0\n", stderr="")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("axibridge.backends.pi_ssh.subprocess.run", fake_run)
    monkeypatch.setattr("axibridge.backends.pi_ssh.time.sleep", lambda s: None)
    doc = PathDocument(layers=[Layer(id=1, name="t", paths=[Path(points=[(0, 0), (5, 0)])])])
    events = []
    b.plot(doc, PiSshParams(), JobControl(), events.append)
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "started" and kinds[-1] == "finished"
    assert any("setsid nohup" in c for c in calls)       # detached launch
    assert any("NTFY_URL" in c for c in calls)           # completion notify wired


def test_plot_stop_kills_remote_group(monkeypatch):
    import types

    from axibridge.backends.base import JobControl
    from axibridge.model import Layer, Path, PathDocument

    b = PiSshBackend()
    b._connected = True
    control = JobControl()
    calls = []

    def fake_run(cmd, capture_output=True, text=True, timeout=None):
        joined = " ".join(cmd)
        calls.append(joined)
        if cmd[0] == "scp":
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if "setsid nohup" in joined:
            return types.SimpleNamespace(returncode=0, stdout="777\n", stderr="")
        return types.SimpleNamespace(returncode=0, stdout="RUNNING\n", stderr="")

    monkeypatch.setattr("axibridge.backends.pi_ssh.subprocess.run", fake_run)
    monkeypatch.setattr("axibridge.backends.pi_ssh.time.sleep",
                        lambda s: control.stop())  # stop arrives mid-poll
    doc = PathDocument(layers=[Layer(id=1, name="t", paths=[Path(points=[(0, 0), (5, 0)])])])
    events = []
    b.plot(doc, PiSshParams(), control, events.append)
    assert events[-1]["kind"] == "stopped"
    assert any("kill -TERM -- -777" in c for c in calls)   # process GROUP killed
    assert any("raise_pen" in c for c in calls)            # pen lifted after

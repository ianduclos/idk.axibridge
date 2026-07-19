"""Characterization pins for the TWO per-layer interpolation implementations.

The canvas tween (tween.py) and the tray capture-interpolation
(session._interpolate_layer) implement the same "blend two versions of a
layer" semantics twice, sharing only lerp_affine/lerp_params. Before they
are unified onto one core (the 2026-07-19 review's item 1), these tests
freeze today's observed behavior of BOTH paths, so the unification is a
sequence of deliberate, visible changes instead of silent drift.

Unification ledger (Ian's ruling, 2026-07-19: non-lerpables are exclusively
bools, seeds, and mismatched stacks — where "stack" means the FULL step
list, a step's `enabled` being just a bool that steps at 0.5):

* Full-stack rule LANDED — ``blend_effect_stacks`` is shared by both paths;
  ``test_pin_canvas_tween_steps_on_disabled_extra_step`` documents the flip
  (tween.py used to blend past a disabled extra step, the tray stepped).
* ``test_pin_tray_freezes_a_tweens_own_t`` — a KNOWN FIDELITY GAP still
  pinned as-is: the tray keeps capture A's tween params at every step (the
  non-generator branch never touches ``source``), so a tween-t change
  between captures produces N identical sheets and the last step does NOT
  reproduce capture B. TweenParams.t is a float; under the ruling it should
  lerp — scheduled next.
* One-sided layers step at the midpoint in BOTH directions
  (``test_pin_one_sided_layers_step_at_midpoint``) — guards the 2026-07-19
  crash fix (B-only layers used to raise AttributeError for every step with
  t < 0.5) and the deliberate symmetry change (A-only layers used to
  persist across all steps).

Numbers used throughout: a closed hexagon is 7 points; multipass emits
n + (n-1)·(count-1) points, so count 2/3/6 → 13/19/37.
"""

import pytest

from axibridge.session import session

MP = lambda count, enabled=True: {  # noqa: E731 — terse stack literals keep the scenarios readable
    "effect": "multipass", "enabled": enabled, "params": {"count": count}}
JITTER_OFF = {"effect": "coherent_jitter", "enabled": False, "params": {}}


def _pts(paths):
    return sum(len(p.points) for p in paths)


def _doc_pts(doc):
    return sum(len(p.points) for layer in doc.layers for p in layer.paths)


def _doc_points(doc):
    return [p.points for layer in doc.layers for p in layer.paths]


def _hex(radius=20):
    return session.add_generated_layer("polygon", {"sides": 6, "radius": radius})


# -- the agreement pin: MUST survive the unification untouched ---------------


def test_pin_matching_stacks_blend_identically_on_both_paths():
    """Same stacks, different params: both paths blend. The positive case the
    unification must not disturb: multipass count 2→6 at t=0.25 → count 3 →
    19 points, on the canvas tween AND the tray batch."""
    lay = _hex()
    session.update_layer(lay.id, {"effects": [MP(2)]})
    cap_a = session.capture_to_staging(kind="plot", name="A")
    session.update_layer(lay.id, {"effects": [MP(6)]})
    cap_b = session.capture_to_staging(kind="plot", name="B")
    batch = session.interpolate_captures(cap_a.id, cap_b.id, steps=5)
    assert _doc_pts(session.staged_document(batch.id, batch.sheets[1].id)) == 19
    # endpoint steps reproduce the captures' own geometry exactly
    assert _doc_points(session.staged_document(batch.id, batch.sheets[0].id)) == \
        _doc_points(session.staged_document(cap_a.id))
    assert _doc_points(session.staged_document(batch.id, batch.sheets[4].id)) == \
        _doc_points(session.staged_document(cap_b.id))

    a = _hex()
    b = _hex()
    session.update_layer(a.id, {"effects": [MP(2)]})
    session.update_layer(b.id, {"effects": [MP(6)]})
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 0.25})
    assert _pts(session.resolved()[tw.id]) == 19


# -- the divergence pins: one side flips with the unification ----------------


def test_pin_canvas_tween_steps_on_disabled_extra_step():
    """UNIFIED (was the divergence): tween.py used to compare
    enabled-filtered stacks, so B's disabled extra step didn't break the
    match and params blended (19 pts) while the tray stepped — the same A/B
    pair morphed or jump-cut depending on the instrument. Both paths now
    share blend_effect_stacks' full-stack rule: the extra step is a
    mismatch, the stack steps at 0.5, t=0.25 renders A's stack (13 pts)."""
    a = _hex()
    b = _hex()
    session.update_layer(a.id, {"effects": [MP(2)]})
    session.update_layer(b.id, {"effects": [MP(6), dict(JITTER_OFF)]})
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 0.25})
    assert _pts(session.resolved()[tw.id]) == 13


def test_pin_tray_steps_on_disabled_extra_step():
    """The tray side of the same rule (this side always compared full
    stacks): B's disabled extra step is a mismatch, the whole stack steps at
    0.5, and t=0.25 renders A's stack (13 pts) with a warning."""
    lay = _hex()
    session.update_layer(lay.id, {"effects": [MP(2)]})
    cap_a = session.capture_to_staging(kind="plot", name="A")
    session.update_layer(lay.id, {"effects": [MP(6), dict(JITTER_OFF)]})
    cap_b = session.capture_to_staging(kind="plot", name="B")
    batch = session.interpolate_captures(cap_a.id, cap_b.id, steps=5)
    assert _doc_pts(session.staged_document(batch.id, batch.sheets[1].id)) == 13
    assert any("effect stack changed" in w for w in batch.warnings)


# -- one-sided layers (regression: the B-only case crashed before 2026-07-19)


def test_pin_one_sided_layers_step_at_midpoint():
    keep = _hex()
    cap_a = session.capture_to_staging(kind="plot", name="A")
    extra = session.add_generated_layer("polygon", {"sides": 4, "radius": 10})
    cap_b = session.capture_to_staging(kind="plot", name="B")
    batch = session.interpolate_captures(cap_a.id, cap_b.id, steps=5)
    counts = [
        sum(len(l.paths) for l in session.staged_document(batch.id, s.id).layers)
        for s in batch.sheets
    ]
    assert counts == [1, 1, 2, 2, 2], "B-only layer must step IN at t=0.5"
    assert any("only exists on one side" in w for w in batch.warnings)

    session.delete_layer(extra.id)
    cap_c = session.capture_to_staging(kind="plot", name="C")
    batch2 = session.interpolate_captures(cap_b.id, cap_c.id, steps=5)
    counts2 = [
        sum(len(l.paths) for l in session.staged_document(batch2.id, s.id).layers)
        for s in batch2.sheets
    ]
    assert counts2 == [2, 2, 1, 1, 1], "A-only layer must step OUT at t=0.5"


# -- nesting: a canvas tween inside tray captures ----------------------------


def _hidden_tween_pair(radius_b=90):
    p = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    q = session.add_generated_layer("polygon", {"sides": 6, "radius": radius_b})
    tw = session.create_tween_layer(p.id, q.id)
    session.update_layer(p.id, {"visible": False})
    session.update_layer(q.id, {"visible": False})
    return p, q, tw


def _doc_width(doc):
    b = doc.bounds()
    return b[2] - b[0]


def test_pin_nested_tween_rederives_from_blended_endpoints():
    """Captures differ in an ENDPOINT layer's generator param: the tray blends
    the tween's inputs and the tween re-materialises from them, so the
    nested morph tracks the blend — widths grow monotonically and the
    endpoint steps reproduce the captures. This is the coexistence the
    unification must preserve."""
    p, q, tw = _hidden_tween_pair(radius_b=45)
    session.set_tween_params(tw.id, {"t": 0.5})
    cap_a = session.capture_to_staging(kind="plot", name="A")
    session.regenerate_layer(q.id, {"sides": 6, "radius": 90})
    cap_b = session.capture_to_staging(kind="plot", name="B")
    batch = session.interpolate_captures(cap_a.id, cap_b.id, steps=3)
    widths = [_doc_width(session.staged_document(batch.id, s.id)) for s in batch.sheets]
    assert widths[0] < widths[1] < widths[2]
    assert widths[0] == pytest.approx(_doc_width(session.staged_document(cap_a.id)))
    assert widths[2] == pytest.approx(_doc_width(session.staged_document(cap_b.id)))


def test_pin_tray_freezes_a_tweens_own_t():
    """KNOWN FIDELITY GAP, pinned as-is — scheduled to change. Captures that
    differ ONLY in a tween's own t produce N IDENTICAL sheets at capture A's
    t: the tray's non-generator branch never touches ``source``, and
    re-materialisation overwrites the pointwise-lerped geometry. The final
    step does NOT reproduce capture B. Under the 2026-07-19 ruling
    (TweenParams.t is a float → it lerps) the unification should make the
    steps sweep A→B; rewrite this test then."""
    p, q, tw = _hidden_tween_pair()
    session.set_tween_params(tw.id, {"t": 0.1})
    cap_c = session.capture_to_staging(kind="plot", name="C")
    session.set_tween_params(tw.id, {"t": 0.9})
    cap_d = session.capture_to_staging(kind="plot", name="D")
    batch = session.interpolate_captures(cap_c.id, cap_d.id, steps=3)
    widths = [_doc_width(session.staged_document(batch.id, s.id)) for s in batch.sheets]
    w_c = _doc_width(session.staged_document(cap_c.id))
    w_d = _doc_width(session.staged_document(cap_d.id))
    assert w_c < w_d  # the captures really do differ
    for w in widths:
        assert w == pytest.approx(w_c), "every step frozen at capture A's t"

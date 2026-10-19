"""Every control of every built-in study is alive (study bench v3, 2026-10-19).

Ian: "I tried some studies and some faders didnt seem to change anything."
The fader audit (docs/superpowers/specs/2026-10-19-fader-audit.txt) moved every
control and found the dead ones. Each is now either removed (truly dead) or
declares `when` (it acts only in some settings; the bench dims it and says why).

- a control with no `when` changes the drawing at the study's defaults;
- a control with `when` changes it once its condition holds (and the bench's
  reading of `when` agrees with the server's: `acts`);
- a study whose drawing ignores the seed has no seed control.

Slow studies (Shape atlas ~76 s a render, Ledger ~38 s on a first render) run
only with AXIBRIDGE_SLOW_TESTS=1: their controls are covered by the audit, and
running them here would multiply the suite's time several times over.
"""
import hashlib
import json
import os

import pytest

from axibridge.registry import get_source, load_builtin_modules
from axibridge.sources._gesture_studies import frozen_library as FL
from axibridge.sources._gesture_studies import studies as ST

load_builtin_modules()
SRC = get_source("gesture_studies")
SLOW = {"shape_atlas": "~76 s per render (the atlas's clothoid fits)",
        "ledger_straight": "~38 s for a first render (the ledger's clothoid fits)"}
# controls that act only on some drawings, in a way `when` cannot say (it reads controls, not
# the drawing): the setting they are checked in, and why
CONTEXT = {("sampler", "clean"): ({"seed": 19}, "clean tidies only a combination with something to tidy; "
                                                 "seed 12's has none, seed 19's has straight-run machines")}
NO_SEED = {"dance_atlas", "dance_triptych", "limb_signs", "limb_signs_levitation"}
# the 28 studies this test was written against; studies added later bring their own alive test
STUDIES = [s.id for s in ST.builtin_studies()][:28]


def _draw(study, values):
    doc = SRC.generate(SRC.Params(study=study.model_dump(mode="json"), values=values))
    h = hashlib.sha256()
    for layer in doc.layers:
        for p in layer.paths:
            h.update(json.dumps([p.filled, [[round(x, 4), round(y, 4)] for x, y in p.points]]).encode())
    return h.hexdigest()


def _library_ids(study, c):
    lib = FL.FrozenLibrary()
    return sorted(ST.options_for(study, c, lib))


def _alternatives(study, c, v):
    """Other values for control c, near its current value first."""
    if c.type in ("int", "float"):
        span = c.max - c.min
        out = []
        for k in (-0.25, 0.25, -0.5, 0.5):        # lighter first: usually the faster drawing
            x = v + k * span
            x = int(round(x)) if c.type == "int" else round(x, 6)
            if c.min <= x <= c.max and x != v:
                out.append(x)
        if c.key == "seed":
            out = [v + 1 if v < c.max else v - 1]
        return out[:2]
    if c.type == "bool":
        return [not v]
    if c.type == "choice":
        return [x for x in c.choices if x != v][:4]
    if c.type == "toggles":
        on = [x for x in v.split(c.join) if x]
        off = [x for x in c.choices if x not in on]
        out = []
        if on and len(on) > (c.min_len or 0):
            out.append(c.join.join(on[:-1]))
        if off:
            out.append(c.join.join(on + off[:1]))
        return out
    ids = _library_ids(study, c)
    if c.type == "hands":
        items = v.split() if c.join else list(v)
        others = [h for h in ids if h not in items]
        if c.join:
            return [" ".join(items[:-1] or others[:1]), " ".join(items + others[:1])]
        return [items[:-1] + [others[0]], items[:-1] + [others[1]]]
    return [x for x in ids if x != v][:2]


def _satisfying(study, w, values):
    """Values under which condition w holds (the first branch that can)."""
    by_key = {c.key: c for c in study.controls}
    if w is None:
        return values
    if "all" in w:
        for x in w["all"]:
            values = _satisfying(study, x, values)
        return values
    if "any" in w:
        return _satisfying(study, w["any"][0], values)
    c = by_key[w["key"]]
    if "is" in w:
        return {**values, c.key: w["is"]}
    if "in" in w:
        return {**values, c.key: w["in"][0]}
    current = values.get(c.key, ST.get_at(study.recipe, c.targets[0]))
    if current != w["not"]:
        return values
    return {**values, c.key: next(x for x in _alternatives(study, c, current) if x != w["not"])}


def test_when_is_validated():
    base = ST.builtin("bold_swell").model_dump()
    ok = ST.check_study(ST.Study(**base))
    assert [c.key for c in ok.controls if c.when] == ["renderer.dot_shape"]
    bad = json.loads(json.dumps(base))
    shape = next(c for c in bad["controls"] if c["path"] == "renderer.dot_shape")
    for when, msg in [({"key": "renderer.nope", "is": "none"}, "not another control"),
                      ({"key": "renderer.dot_shape", "is": "disc"}, "not another control"),
                      ({"key": "renderer.dots", "is": "sometimes"}, "is not one of"),
                      ({"key": "renderer.size", "in": [99.0]}, "outside")]:
        shape["when"] = when
        with pytest.raises(ST.StudyError, match=msg):
            ST.check_study(ST.Study(**bad))
    for when in [{"key": "renderer.dots"}, {"key": "renderer.dots", "is": "count", "not": "none"},
                 {"any": []}, {"all": [{"key": "renderer.dots", "is": "count"}], "key": "renderer.dots"},
                 {"key": "renderer.dots", "is": "count", "colour": 1}, "renderer.dots"]:
        shape["when"] = when
        with pytest.raises(ValueError):
            ST.Study(**bad)


def test_when_reads_like_the_bench():
    hd = ST.check_study(ST.builtin("hand_drift"))
    nib = next(c for c in hd.controls if c.key == "nib_angle")
    assert not ST.acts(hd, {}, nib)
    assert ST.acts(hd, {"regimes": "field"}, nib)
    assert not ST.acts(hd, {"regimes": "timing"}, nib)                 # the wrist holds the nib
    assert ST.acts(hd, {"regimes": "timing", "wrist_nib": False}, nib)
    dim = [c.key for c in hd.controls if not ST.acts(hd, {}, c)]
    assert dim == ["timing", "wrist_nib", "amount", "nib_width", "mass_width", "nib_angle", "ink"]
    assert all(ST.acts(hd, {"regimes": "timing", "wrist_nib": False}, c) for c in hd.controls)


def test_choice_and_toggles_over_a_text_param():
    base = ST.builtin("bold_swell").model_dump()
    listen = "parts.0.modulators.0.listen"          # the prosody modulator's free text: a comma list of events
    heard = base["recipe"]["parts"][0]["modulators"][0]["listen"]
    lib = FL.FrozenLibrary()
    st = json.loads(json.dumps(base))
    st["controls"].insert(0, {"path": listen, "label": "Hears", "type": "toggles",
                              "choices": ["switch", "corner", "kappa", "inflection", "token", "tempo"],
                              "min_len": 1})
    study = ST.check_study(ST.Study(**st))
    assert ST.resolve(study, {listen: ["kappa", "switch"]}, lib)["parts"][0]["modulators"][0]["listen"] \
        == "kappa,switch"
    assert ST.resolve(study, {listen: "corner"}, lib)["parts"][0]["modulators"][0]["listen"] == "corner"
    for v in (["nope"], [], ["kappa", "kappa"], 3):
        with pytest.raises(ST.StudyError):
            ST.resolve(study, {listen: v}, lib)
    # a choice over the same text param: the study names the values it takes
    st = json.loads(json.dumps(base))
    st["controls"].insert(0, {"path": listen, "label": "Hears", "type": "choice", "choices": [heard, "kappa"]})
    study = ST.check_study(ST.Study(**st))
    assert ST.resolve(study, {listen: "kappa"}, lib)["parts"][0]["modulators"][0]["listen"] == "kappa"
    with pytest.raises(ST.StudyError, match="not one of"):
        ST.resolve(study, {listen: "corner"}, lib)
    st["controls"][0].pop("choices")
    with pytest.raises(ST.StudyError, match="lists its choices"):
        ST.check_study(ST.Study(**st))
    st["controls"][0].update({"type": "toggles", "choices": ["kappa"], "path": "renderer.thr"})
    with pytest.raises(ST.StudyError, match="text param"):
        ST.check_study(ST.Study(**st))


def test_studies_that_ignore_the_seed_have_no_seed_control():
    for sid in NO_SEED:
        st = ST.builtin(sid)
        assert all(c.key != "seed" for c in st.controls), sid
        assert "no seed control" in st.notes
    st = ST.builtin("dance_atlas")
    moved = st.model_copy(update={"recipe": {**st.recipe, "seed": st.recipe["seed"] + 1}})
    assert _draw(st, {}) == _draw(moved, {})                # the reason it went


def test_every_study_has_a_family():
    families = {"Hands and drift", "Measurement", "Several voices", "Swell", "After Oehlen", "Rivers"}
    for sid in STUDIES:
        assert ST.builtin(sid).family in families, sid


@pytest.mark.parametrize("sid", STUDIES)
def test_every_control_is_alive(sid):
    if sid in SLOW and os.environ.get("AXIBRIDGE_SLOW_TESTS") != "1":
        pytest.skip(f"slow study: {SLOW[sid]}; run with AXIBRIDGE_SLOW_TESTS=1")
    study = ST.check_study(ST.builtin(sid))
    dead = []
    bases = {}
    for c in study.controls:
        values = _satisfying(study, c.when, CONTEXT.get((sid, c.key), ({}, ""))[0])
        assert ST.acts(study, values, c), (sid, c.key)
        key = json.dumps(values, sort_keys=True)
        if key not in bases:
            bases[key] = _draw(study, values)
        current = values.get(c.key, ST.get_at(study.recipe, c.targets[0]))
        tried = []
        for alt in _alternatives(study, c, current):
            tried.append(alt)
            if _draw(study, {**values, c.key: alt}) != bases[key]:
                break
        else:
            dead.append((c.key, values, tried))
    assert not dead, f"{sid}: these controls change nothing: {dead}"

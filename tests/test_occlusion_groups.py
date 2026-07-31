"""Occlusion groups: scoped masking via checkbox group sets.

A layer independently picks which groups it OCCLUDES INTO and which it
RECEIVES FROM. Additive semantics (the contract pinned here):
* An occluder with an EMPTY occlude_groups masks every receiver below — the
  classic global behaviour.
* An occluder with groups masks only receivers listening to any of them.
* A receiver is clipped by the global mask plus every group it listens to.
* Projects saved with the old single ``occlusion_group`` letter migrate to
  both lists on load.
"""

import pytest

from axibridge.compose import Affine
from axibridge.session import session


def total_len(paths):
    return sum(p.length() for p in paths)


@pytest.fixture()
def two_receivers_one_occluder():
    """Two lissajous receivers, one filled-hexagon occluder on top of both."""
    low = session.add_generated_layer("lissajous", {"size": 100, "margin": 5})
    high = session.add_generated_layer("lissajous", {"size": 100, "margin": 5})
    hexa = session.add_generated_layer("polygon", {"sides": 6, "radius": 25, "filled": True})
    session.update_layer(hexa.id, {
        "transform": Affine(e=30, f=30).model_dump(),
        "occluder": True,
    })
    return low, high, hexa


def test_grouped_occluder_masks_only_its_group(two_receivers_one_occluder):
    low, high, hexa = two_receivers_one_occluder
    src_len = total_len(session.source_geometry[low.id])
    session.update_layer(hexa.id, {"occlude_groups": ["A"]})
    session.update_layer(low.id, {"receives_groups": ["A"]})

    res = session.resolved()
    assert total_len(res[low.id]) < src_len, "listening receiver must be clipped"
    assert len(res[high.id]) == 1, "non-listening receiver must be untouched"
    assert total_len(res[high.id]) == pytest.approx(src_len)


def test_multi_group_occluder_masks_each_listed_group(two_receivers_one_occluder):
    low, high, hexa = two_receivers_one_occluder
    src_len = total_len(session.source_geometry[low.id])
    session.update_layer(hexa.id, {"occlude_groups": ["A", "C"]})
    session.update_layer(low.id, {"receives_groups": ["A"]})
    session.update_layer(high.id, {"receives_groups": ["C"]})

    res = session.resolved()
    assert total_len(res[low.id]) < src_len, "A receiver must be clipped"
    assert total_len(res[high.id]) < src_len, "C receiver must be clipped"
    # but a receiver listening only to B is not in the occluder's set
    session.update_layer(high.id, {"receives_groups": ["B"]})
    assert len(session.resolved()[high.id]) == 1


def test_multi_group_receiver_listens_to_all_its_groups():
    """Two occluders targeting different single groups both reach a receiver
    that listens to both."""
    low = session.add_generated_layer("lissajous", {"size": 100, "margin": 5})
    src_len = total_len(session.source_geometry[low.id])
    occ_a = session.add_generated_layer("polygon", {"sides": 6, "radius": 25, "filled": True})
    session.update_layer(occ_a.id, {
        "transform": Affine(e=30, f=30).model_dump(),
        "occluder": True, "occlude_groups": ["A"]})
    occ_b = session.add_generated_layer("polygon", {"sides": 5, "radius": 18, "filled": True})
    session.update_layer(occ_b.id, {
        "transform": Affine(e=60, f=0).model_dump(),
        "occluder": True, "occlude_groups": ["B"]})
    session.update_layer(low.id, {"receives_groups": ["A", "B"]})

    both = total_len(session.resolved()[low.id])
    assert both < src_len
    session.update_layer(occ_b.id, {"occluder": False})
    assert total_len(session.resolved()[low.id]) > both, (
        "the receiver must lose the B mask when the B occluder goes away")


def test_empty_occlude_groups_is_the_global_mask(two_receivers_one_occluder):
    low, high, _ = two_receivers_one_occluder  # hexa occluder with empty set
    src_len = total_len(session.source_geometry[low.id])
    session.update_layer(low.id, {"receives_groups": ["A"]})

    res = session.resolved()
    assert total_len(res[low.id]) < src_len, "global mask reaches group listeners"
    assert total_len(res[high.id]) < src_len, "…and plain receivers alike"


def test_receiver_with_no_groups_hears_only_global(two_receivers_one_occluder):
    low, _, hexa = two_receivers_one_occluder
    src_len = total_len(session.source_geometry[low.id])
    session.update_layer(hexa.id, {"occlude_groups": ["A"]})
    # low listens to nothing (default): the A-targeted mask must not reach it
    res = session.resolved()
    assert len(res[low.id]) == 1
    assert total_len(res[low.id]) == pytest.approx(src_len)


def test_draw_off_grouped_occluder_still_masks(two_receivers_one_occluder):
    low, _, hexa = two_receivers_one_occluder
    session.update_layer(hexa.id, {"occlude_groups": ["A"], "draw": False})
    session.update_layer(low.id, {"receives_groups": ["A"]})
    res = session.resolved()
    assert res[hexa.id] == []
    assert total_len(res[low.id]) < total_len(session.source_geometry[low.id])


def test_hidden_grouped_occluder_is_inert(two_receivers_one_occluder):
    low, _, hexa = two_receivers_one_occluder
    session.update_layer(hexa.id, {"occlude_groups": ["A"], "visible": False})
    session.update_layer(low.id, {"receives_groups": ["A"]})
    res = session.resolved()
    assert len(res[low.id]) == 1


def test_group_fields_roundtrip_save_load(tmp_path):
    from axibridge import project_io

    layer = session.add_generated_layer("polygon", {"sides": 5, "radius": 10})
    session.update_layer(layer.id, {
        "occluder": True, "occlude_groups": ["A", "C"], "receives_groups": ["B"]})
    target = tmp_path / "proj"
    project_io.save_project(session.project, session.source_geometry,
                            session.svg_files, target)
    project, _, _, _, _, _ = project_io.load_project(target)
    loaded = project.layer(layer.id)
    assert loaded.occlude_groups == ["A", "C"]
    assert loaded.receives_groups == ["B"]


def test_legacy_occlusion_group_migrates_to_both_lists(tmp_path):
    """Projects saved with the single-letter occlusion_group load with the
    letter in both lists (it used to mean both directions)."""
    from axibridge import project_io
    from axibridge.compose import CanvasLayer, Project

    layer = session.add_generated_layer("polygon", {"sides": 5, "radius": 10})
    target = tmp_path / "proj"
    project_io.save_project(session.project, session.source_geometry,
                            session.svg_files, target)
    import json
    manifest = target / "project.json"
    data = json.loads(manifest.read_text())
    for ld in data["layers"]:
        if ld["id"] == layer.id:
            ld.pop("occlude_groups", None)
            ld.pop("receives_groups", None)
            ld["occlusion_group"] = "A"
    manifest.write_text(json.dumps(data, indent=2))
    project, _, _, _, _, _ = project_io.load_project(target)
    loaded = project.layer(layer.id)
    assert loaded.occlude_groups == ["A"]
    assert loaded.receives_groups == ["A"]
    assert not hasattr(loaded, "occlusion_group")


def test_update_layer_accepts_group_lists():
    layer = session.add_generated_layer("polygon", {"sides": 4, "radius": 8})
    session.update_layer(layer.id, {"occlude_groups": ["A", "D"], "receives_groups": ["C"]})
    loaded = session.project.layer(layer.id)
    assert loaded.occlude_groups == ["A", "D"]
    assert loaded.receives_groups == ["C"]
    session.update_layer(layer.id, {"occlude_groups": [], "receives_groups": []})
    assert session.project.layer(layer.id).occlude_groups == []
    with pytest.raises(Exception):
        session.update_layer(layer.id, {"occlude_groups": ["E"]})  # outside A–D
    with pytest.raises(Exception):
        session.update_layer(layer.id, {"occlusion_group": "A"})  # removed field

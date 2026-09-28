"""Rendering controls remain independent of expensive image evidence."""
import pytest
from pydantic import ValidationError
from axibridge.linedraw.contracts import LinedrawV3Params
from axibridge.linedraw.runtime import evidence_key


def test_components_and_treatments_roundtrip_without_reanalyzing():
    base = LinedrawV3Params(style="regional_form")
    edited = LinedrawV3Params(style="regional_form", ink_components=["form", "cores"],
        shading_mode="tonal", form_flow="coherent", form_density=1.5,
        core_strength=.8, hair_flow=.5, smoothing_mm=.15)
    assert LinedrawV3Params.model_validate_json(edited.model_dump_json()) == edited
    assert evidence_key(b"synthetic", base, "models") == evidence_key(b"synthetic", edited, "models")


def test_invalid_component_controls_are_rejected():
    for kwargs in ({"ink_components":["form","form"]}, {"ink_components":["unknown"]},
                   {"form_density":0}, {"smoothing_mm":float("nan")}, {"smoothing_mm":3}):
        with pytest.raises(ValidationError):
            LinedrawV3Params(**kwargs)

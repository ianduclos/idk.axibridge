import pytest
from pydantic import ValidationError


def test_new_recipe_is_available():
    from axibridge.linedraw.contracts import LinedrawV3Params, FaceRegion

    assert LinedrawV3Params().style == "light_form"
    assert FaceRegion(id="f", cx=0.25, cy=0.5, rx=0.1, ry=0.2).cx == 0.25


@pytest.mark.parametrize("values", [dict(cx=float("nan")), dict(rx=0), dict(cx=1.2)])
def test_invalid_region(values):
    from axibridge.linedraw.contracts import FaceRegion

    with pytest.raises(ValidationError):
        FaceRegion(**(dict(id="f", cx=0.5, cy=0.5, rx=0.1, ry=0.2) | values))


def test_duplicate_regions_rejected():
    from axibridge.linedraw.contracts import LinedrawV3Params

    face = dict(id="f", cx=0.5, cy=0.5, rx=0.1, ry=0.2)
    with pytest.raises(ValidationError):
        LinedrawV3Params(faces=[face, face])

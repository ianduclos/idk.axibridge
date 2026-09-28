"""Saved drawing recipes and canonical, EXIF-corrected image coordinates."""

from dataclasses import dataclass, field
from typing import Literal, Annotated
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

HIDDEN = {"hidden": True}


class FaceRegion(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=64)
    cx: float = Field(ge=0, le=1)
    cy: float = Field(ge=0, le=1)
    rx: float = Field(gt=0, le=0.5)
    ry: float = Field(gt=0, le=0.5)
    enabled: bool = True
    origin: Literal["automatic", "manual"] = "manual"


Unit = Annotated[float, Field(ge=0, le=1)]
Outline = Annotated[list[tuple[Unit, Unit]], Field(min_length=3, max_length=64)]
DetailCategory = Literal["hands_feet", "clothing", "hair", "body"]


def valid_outline(points):
    from shapely.geometry import Polygon
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= 1e-8:
        raise ValueError("Region must be a simple polygon with positive area")
    return points


class DetailPerson(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=64)
    face_id: str = Field(default="", max_length=64)
    polygon: Outline
    _polygon = field_validator("polygon")(valid_outline)


class DetailRegion(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=64)
    person_id: str = Field(default="person-1", min_length=1, max_length=64)
    category: DetailCategory = "clothing"
    polygon: Outline
    exclude_polygons: list[Outline] = Field(default_factory=list, max_length=8)
    enabled: bool = True
    _polygon = field_validator("polygon")(valid_outline)

    @field_validator("exclude_polygons")
    @classmethod
    def valid_holes(cls, holes):
        for points in holes:
            valid_outline(points)
        return holes


class LinedrawV3Params(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    image: str = Field(default="", title="Image", json_schema_extra={"format": "asset"})
    frame: float = Field(default=0, ge=0, le=1, title="Frame")
    rotate: Literal[0, 90, 180, 270] = Field(
        default=0, title="Rotate image (°)", json_schema_extra={"viewRotate": True}
    )
    width: float = Field(
        default=150,
        ge=10,
        le=400,
        title="Width (mm)",
        json_schema_extra={"viewSize": True},
    )
    show_map: bool = Field(default=False, title="Show image on canvas")
    style: Literal["contours", "light_form", "shadow_shapes", "face_form", "light_support", "regional_form"] = Field(
        default="light_form", title="Drawing style"
    )
    contour_budget: int = Field(default=192, ge=0, le=1024, title="Contour strokes")
    face_budget: int = Field(default=48, ge=0, le=192, title="Strokes per face")
    shadow_proxy: Literal["local", "material"] = Field(
        default="local",
        title="Shadow reading",
        description="Local darkness works without faces; material requires valid face samples.",
    )
    shadow_strength: float = Field(default=0.5, ge=0, le=1, title="Shadow strength")
    hatch_spacing: float = Field(default=1.5, ge=0.1, le=10, title="Form spacing (mm)")
    fill_spacing: float = Field(
        default=0.3, ge=0.05, le=5, title="Shadow fill spacing (mm)"
    )
    clearance: float = Field(default=0.6, ge=0, le=5, title="Contour clearance (mm)")
    faces: list[FaceRegion] = Field(
        default_factory=list, max_length=32, json_schema_extra=HIDDEN
    )
    detail_budget: int = Field(default=192, ge=0, le=1024, title="Detail strokes per person")
    detail_categories: list[DetailCategory] = Field(
        default_factory=lambda: ["hands_feet", "clothing", "hair"], max_length=4,
        json_schema_extra=HIDDEN,
    )
    detail_regions: list[DetailRegion] = Field(default_factory=list, max_length=64, json_schema_extra=HIDDEN)
    people: list[DetailPerson] = Field(default_factory=list, max_length=32, json_schema_extra=HIDDEN)
    image_identity: str = Field(default="", max_length=64, json_schema_extra=HIDDEN)
    model_identity: str = Field(default="", max_length=64, json_schema_extra=HIDDEN)
    recipe_version: Literal[1] = Field(default=1, json_schema_extra=HIDDEN)

    @model_validator(mode="after")
    def unique_faces(self):
        if len({f.id for f in self.faces}) != len(self.faces):
            raise ValueError("Face region IDs must be unique")
        for name in ("people", "detail_regions"):
            entries = getattr(self, name)
            if len({r.id for r in entries}) != len(entries):
                raise ValueError(f"{name} IDs must be unique")
        owners = {p.id for p in self.people} or {"person-1"}
        if any(r.person_id not in owners for r in self.detail_regions):
            raise ValueError("Detail region needs an existing person")
        faces = {f.id for f in self.faces}
        assigned = [p.face_id for p in self.people if p.face_id]
        if any(f not in faces for f in assigned) or len(set(assigned)) != len(assigned):
            raise ValueError("Link each person to a different existing face")
        if len(set(self.detail_categories)) != len(self.detail_categories):
            raise ValueError("Detail categories must be unique")
        return self


@dataclass(frozen=True)
class Candidate:
    points: np.ndarray
    confidence: float
    identity: str


@dataclass(frozen=True)
class Evidence:
    rgb: np.ndarray
    foreground: np.ndarray
    normals: np.ndarray | None
    whole_lines: np.ndarray
    tiled_lines: np.ndarray
    faces: tuple[FaceRegion, ...] = ()
    face_candidates: dict[str, tuple[Candidate, ...]] = field(default_factory=dict)
    identity: str = ""
    alpha: np.ndarray | None = None
    whole_candidates: tuple[Candidate, ...] | None = None
    tiled_candidates: tuple[Candidate, ...] | None = None
    device: str = "unknown"
    reference_whole: list[dict] | None = None
    reference_tiles: list[dict] | None = None
    reference_base: list[dict] | None = None
    reference_faces: dict[str, list[dict]] = field(default_factory=dict)
    reference_regions: dict[str, list[dict]] = field(default_factory=dict)



def region_mask(face, width, height):
    y, x = np.mgrid[:height, :width]
    return ((x / width - face.cx) / face.rx) ** 2 + (
        (y / height - face.cy) / face.ry
    ) ** 2 <= 1

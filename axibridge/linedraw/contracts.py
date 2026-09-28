"""Saved drawing recipes and canonical, EXIF-corrected image coordinates."""
from dataclasses import dataclass, field
from typing import Literal
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

HIDDEN = {"hidden": True}

class FaceRegion(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=64)
    cx: float = Field(ge=0, le=1)
    cy: float = Field(ge=0, le=1)
    rx: float = Field(gt=0, le=.5)
    ry: float = Field(gt=0, le=.5)
    enabled: bool = True
    origin: Literal['automatic', 'manual'] = 'manual'

class LinedrawV3Params(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    image: str = Field(default='', title='Image', json_schema_extra={'format':'asset'})
    frame: float = Field(default=0, ge=0, le=1, title='Frame')
    rotate: Literal[0,90,180,270] = Field(default=0, title='Rotate image (°)', json_schema_extra={'viewRotate':True})
    width: float = Field(default=150, ge=10, le=400, title='Width (mm)', json_schema_extra={'viewSize':True})
    show_map: bool = Field(default=False, title='Show image on canvas')
    style: Literal['contours','light_form','shadow_shapes','face_form'] = Field(default='light_form', title='Drawing style')
    contour_budget: int = Field(default=192, ge=0, le=1024, title='Contour strokes')
    face_budget: int = Field(default=48, ge=0, le=192, title='Strokes per face')
    shadow_proxy: Literal['local','material'] = Field(default='local', title='Shadow reading', description='Local darkness works without faces; material requires valid face samples.')
    shadow_strength: float = Field(default=.5, ge=0, le=1, title='Shadow strength')
    hatch_spacing: float = Field(default=1.5, ge=.1, le=10, title='Form spacing (mm)')
    fill_spacing: float = Field(default=.3, ge=.05, le=5, title='Shadow fill spacing (mm)')
    clearance: float = Field(default=.6, ge=0, le=5, title='Contour clearance (mm)')
    faces: list[FaceRegion] = Field(default_factory=list, max_length=32, json_schema_extra=HIDDEN)
    image_identity: str = Field(default='', max_length=64, json_schema_extra=HIDDEN)
    model_identity: str = Field(default='', max_length=64, json_schema_extra=HIDDEN)
    recipe_version: Literal[1] = Field(default=1, json_schema_extra=HIDDEN)

    @model_validator(mode='after')
    def unique_faces(self):
        if len({f.id for f in self.faces}) != len(self.faces):
            raise ValueError('Face region IDs must be unique')
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
    identity: str = ''
    alpha: np.ndarray | None = None

def region_mask(face, width, height):
    y,x = np.mgrid[:height,:width]
    return ((x/width-face.cx)/face.rx)**2 + ((y/height-face.cy)/face.ry)**2 <= 1

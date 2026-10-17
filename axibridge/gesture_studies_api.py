"""Gesture Studies HTTP boundary: list / save / delete studies, validate a
recipe edit. Geometry never travels here — previews and Keep go through the
normal generator endpoints with the `gesture_studies` source. None of these
routes touches the machine (MCP: reviewed, not motion)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from .gesture_studies_store import gesture_study_store
from .sources._gesture_studies import frozen_library as FL
from .sources._gesture_studies import studies as ST

router = APIRouter(prefix="/gesture-studies")


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    except ValidationError as exc:
        raise HTTPException(400, "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                                           for e in exc.errors()[:6])) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


def _out(study: ST.Study, builtin: bool) -> dict:
    return {**study.model_dump(mode="json"), "builtin": builtin, "defaults": ST.defaults(study)}


@router.get("")
def list_studies() -> dict[str, Any]:
    """Built-in studies (in order), saved studies, and the frozen library
    entries every hand / tempo / dance control offers."""
    def build():
        saved = gesture_study_store.list()
        from .sources.gesture_studies import frozen_from  # noqa: PLC0415
        return {"studies": [_out(ST.check_study(s), True) for s in ST.builtin_studies()]
                + [_out(s, False) for s in saved["items"]],
                "warnings": saved["warnings"],
                "library": {k: FL.options(k) for k in ("hand", "tempo", "dance_trail")},
                "snapshot": FL.current_snapshot(), "frozen_from": frozen_from()}
    return _call(build)


class StudyValues(BaseModel):
    study: dict[str, Any]
    values: dict[str, Any] = Field(default_factory=dict, max_length=32)


def _resolved(body: StudyValues) -> ST.Study:
    """The study with the control values written into its recipe (validated)."""
    lib = FL.FrozenLibrary()
    study = ST.check_study(ST.Study(**body.study), lib)
    return ST.check_study(study.model_copy(update={"recipe": ST.resolve(study, body.values, lib)}), lib)


class SaveStudy(StudyValues):
    label: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)


@router.post("")
def save_study(body: SaveStudy) -> dict[str, Any]:
    """Save a NEW study (a fork) from the bench: the current study with the
    current control values as its recipe, a fresh id, version 1, and the
    study + version it grew from as `parent`."""
    def save():
        base = _resolved(body)
        study = gesture_study_store.save(
            label=body.label, engine=base.engine, recipe=base.recipe,
            controls=[c.model_dump(exclude_none=True) for c in base.controls],
            notes=base.notes if body.notes is None else body.notes,
            parent={"id": base.id, "version": base.version})
        return _out(study, False)
    return _call(save)


@router.post("/validate")
def validate_study(body: StudyValues) -> dict[str, Any]:
    """Validate a study (the bench's Edit recipe drawer) without saving:
    the normalized study with the values written into its recipe, or 400."""
    return _call(lambda: _out(_resolved(body), False))


@router.delete("/{study_id}")
def delete_study(study_id: str) -> dict[str, Any]:
    _call(gesture_study_store.delete, study_id)
    return {"ok": True}

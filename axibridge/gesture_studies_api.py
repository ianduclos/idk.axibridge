"""Gesture Studies HTTP boundary: list / save / delete studies, validate a
recipe edit, the library options of an older snapshot, and Keep for a voices
study (the chorus: a group with one layer per voice). Other geometry never
travels here — previews and single-layer Keep go through the normal generator
endpoints with the `gesture_studies` source. None of these routes touches the
machine (MCP: reviewed, not motion)."""
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


@router.get("/library/{snapshot}")
def library_options(snapshot: str) -> dict[str, Any]:
    """What the hand / tempo / dance controls of a layer pinned to an older
    snapshot offer: that snapshot's entries (not the current library's)."""
    return _call(lambda: {"snapshot": snapshot, "current": FL.current_snapshot(),
                          "library": {k: FL.options(k, snapshot) for k in ("hand", "tempo", "dance_trail")}})


class StudyValues(BaseModel):
    study: dict[str, Any]
    values: dict[str, Any] = Field(default_factory=dict, max_length=32)
    # a resumed layer's pins (it stays on its own snapshot); empty = current
    library: str | None = Field(default=None, pattern=r"^[0-9a-f]{12}$")
    pins: list[dict[str, Any]] = Field(default_factory=list, max_length=64)
    sampled: dict[str, Any] | None = None


def _library(body: StudyValues) -> FL.FrozenLibrary:
    from .sources.gesture_studies import Pin  # noqa: PLC0415
    pins = [Pin(**x) for x in body.pins]
    return FL.FrozenLibrary(body.library, {(x.kind, x.id): x.hash for x in pins})


def _resolved(body: StudyValues) -> ST.Study:
    """The study with the control values written into its recipe (validated)."""
    lib = _library(body)
    study = ST.check_study(ST.Study(**body.study), lib)
    return ST.check_study(study.model_copy(update={"recipe": ST.resolve(study, body.values, lib)}), lib)


def _run_info(body: StudyValues, study: ST.Study) -> dict[str, Any]:
    """What the resolved study draws: the kit recipe (a sampler's sampled
    combination), its one-line summary, and a voices study's voices."""
    run = ST.run_recipe(study, study.recipe, _library(body), body.sampled)
    return {"run_recipe": run, "summary": ST.summary_of(study, run), "voices": ST.voices_of(study, run)}


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
        engine, recipe = base.engine, base.recipe
        controls = [c.model_dump(exclude_none=True) for c in base.controls]
        if engine == "sampler":
            # a sampler keeps the combination it found: a kit study of that
            # recipe, its seed still a control (now the drawing's seed only)
            engine, recipe = "kit", _run_info(body, base)["run_recipe"]
        study = gesture_study_store.save(
            label=body.label, engine=engine, recipe=recipe, controls=controls,
            notes=base.notes if body.notes is None else body.notes,
            parent={"id": base.id, "version": base.version})
        return _out(study, False)
    return _call(save)


@router.post("/validate")
def validate_study(body: StudyValues) -> dict[str, Any]:
    """Validate a study (the bench's Edit recipe drawer) without saving:
    the normalized study with the values written into its recipe, or 400."""
    def check():
        study = _resolved(body)
        return {**_out(study, False), **_run_info(body, study)}
    return _call(check)


class KeepVoices(BaseModel):
    params: dict[str, Any]


@router.post("/keep")
def keep_voices(body: KeepVoices) -> dict[str, Any]:
    """Keep a voices study (the chorus) as ONE undo step: a group named after
    the study, one ordinary `gesture_studies` layer per voice inside it, each
    on its own pen (pinned once, so every voice resolves the same recipe)."""
    from .session import session  # noqa: PLC0415

    def keep():
        group, layers = session.keep_gesture_study_voices(body.params)
        return {"group": group.model_dump(), "layers": [layer.model_dump() for layer in layers]}
    return _call(keep)


@router.delete("/{study_id}")
def delete_study(study_id: str) -> dict[str, Any]:
    _call(gesture_study_store.delete, study_id)
    return {"ok": True}

"""Drawing drafts and explicit retention of completed component geometry."""

from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .linedraw.contracts import LinedrawV3Params
from .linedraw.jobs import manager
from .linedraw import runtime
from .session import session

router = APIRouter(prefix="/api/linedraw", tags=["linedraw"])


class StartJob(BaseModel):
    revision: str = Field(min_length=1, max_length=128)
    params: LinedrawV3Params
    operation: Literal["analyze", "render"]


@router.get("/status")
def status():
    return runtime.status()


@router.post("/jobs")
def start(body: StartJob):
    try:
        return manager.start(body.revision, body.params, body.operation, session.project)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/jobs/{identity}")
def get(identity: str):
    try:
        return manager.get(identity)
    except KeyError:
        raise HTTPException(404, "Drawing job expired")


@router.delete("/jobs/{identity}")
def cancel(identity: str):
    try:
        return manager.cancel(identity)
    except KeyError:
        raise HTTPException(404, "Drawing job expired")


class DetachJob(BaseModel):
    revision: str = Field(min_length=1, max_length=128)
    source_layer_id: str | None


@router.post("/jobs/{identity}/detach")
def detach(identity: str, body: DetachJob):
    try:
        project = session.project
        doc, params = manager.completed_snapshot(identity, body.revision, project)
        layers = session.add_linedraw_components(
            doc, params.model_dump(), body.source_layer_id, project,
        )
        return {"layers": [layer.model_dump() for layer in layers]}
    except KeyError as exc:
        raise HTTPException(404, "Drawing job expired") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

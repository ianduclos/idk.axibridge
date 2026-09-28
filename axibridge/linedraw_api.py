"""Read-only drawing drafts; Keep uses the ordinary layer generation API."""

from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .linedraw.contracts import LinedrawV3Params
from .linedraw.jobs import manager
from .linedraw import runtime

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
        return manager.start(body.revision, body.params, body.operation)
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

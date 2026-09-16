"""Read-only access to external Mosca recordings and draft previews."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import mosca, gencache
from .registry import get_source
from .render_work import RenderWork, RenderCancelled, checkpoint

router = APIRouter(prefix='/mosca')
_preview_work = RenderWork()


def call(fn, *args):
    try:
        return fn(*args)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/recordings')
def recordings():
    return {'recordings': call(mosca.list_recordings)}


class PrepareBody(BaseModel):
    id: str


@router.post('/prepare')
def prepare(body: PrepareBody):
    return call(mosca.prepare_recording, body.id)


@router.get('/info')
def info(recording: str):
    return call(mosca.recording_info, recording)


@router.get('/thumbnail')
def thumbnail(id: str):
    return Response(call(mosca.thumbnail_recording, id), media_type='image/svg+xml',
                    headers={'Cache-Control': 'no-cache'})


class PreviewBody(BaseModel):
    params: dict


@router.post('/preview')
def preview(body: PreviewBody):
    _preview_work.cancel()
    try:
        with _preview_work.scope():
            doc = call(gencache.generate_cached, get_source('mosca'), body.params)
            paths = [p for layer in doc.layers for p in layer.paths]
            # Bound the wire representation before converting/rounding coordinates.
            # The source geometry used by Keep stays untouched, including at zero tolerance.
            total = sum(len(path.points) for path in paths)
            stride = max(1, -(-total // 60_000))
            lines = []
            drawable = any(any(point != path.points[0] for point in path.points[1:])
                           for path in paths if path.points)
            for path in paths:
                checkpoint()
                points = path.points[::stride]
                if path.points and (len(path.points) - 1) % stride:
                    points = points + path.points[-1:]
                lines.append([(round(x, 2), round(y, 2)) for x, y in points])
            return {'lines': lines, 'points': total, 'decimated': stride > 1, 'drawable': drawable,
                    'width': doc.width, 'height': doc.height}
    except RenderCancelled:
        raise HTTPException(409, 'Preview superseded') from None

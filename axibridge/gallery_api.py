"""Gallery HTTP boundary, separate from image assets and project recipes."""
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import gallery, gencache
from .registry import get_source
from .session import session

router = APIRouter(prefix='/gallery')


class LayerCapture(BaseModel):
    kind: Literal['layer']
    layer_id: str
    master_t: float | None = Field(default=None, ge=0, le=1)


class GeneratorCapture(BaseModel):
    kind: Literal['generator']
    module: str
    params: dict[str, Any] = Field(default_factory=dict)


class SaveCapture(gallery.GalleryMetadata):
    capture_id: str


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('')
def list_assets(q: str = '', tag: str = '', generator: str = ''):
    return _call(gallery.gallery_store.list, q, tag, generator)


@router.post('/prepare')
def prepare_capture(body: Annotated[LayerCapture | GeneratorCapture, Field(discriminator='kind')]):
    def prepare():
        if isinstance(body, LayerCapture):
            paths, name, origin = session.gallery_capture(body.layer_id, body.master_t)
        else:
            src = get_source(body.module)
            doc = gencache.generate_cached(src, body.params)
            paths = [p for layer in doc.layers for p in layer.paths]
            name, origin = src.label, {'kind': 'generator', 'module': src.id, 'label': src.label}
        return gallery.gallery_store.prepare(paths, name or 'Collected shape', origin)
    return _call(prepare)


@router.post('')
def save_capture(body: SaveCapture):
    return _call(gallery.gallery_store.save, body.capture_id,
                 **body.model_dump(exclude={'capture_id'}))


@router.get('/{asset_id}')
def asset_detail(asset_id: str):
    return _call(gallery.gallery_store.get, asset_id)


@router.get('/{asset_id}/thumbnail')
def asset_thumbnail(asset_id: str):
    paths = _call(gallery.gallery_store.paths, asset_id)
    return Response(gallery.thumbnail(paths), media_type='image/svg+xml',
                    headers={'Cache-Control': 'private, max-age=86400'})


@router.patch('/{asset_id}')
def update_asset(asset_id: str, body: gallery.GalleryMetadata):
    return _call(gallery.gallery_store.update, asset_id, **body.model_dump())


@router.delete('/{asset_id}')
def delete_asset(asset_id: str):
    _call(gallery.gallery_store.delete, asset_id)
    return {'ok': True}


@router.post('/{asset_id}/insert')
def insert_asset(asset_id: str):
    def insert():
        # Read once: deletion/metadata edits cannot split this snapshot.
        with gallery.gallery_store._lock:
            record = gallery.gallery_store._read(asset_id)
        return session.insert_gallery_asset(record.name, record.paths).model_dump()
    return _call(insert)

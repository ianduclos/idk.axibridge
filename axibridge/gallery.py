"""Local, project-independent line assets. Geometry is authoritative JSON;
SVGs are disposable previews. No recipes or external image dependencies.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path as FsPath
import re
import tempfile
import threading
import time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .model import Path
from .stores import CONFIG_DIR


class GalleryMetadata(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=32)
    note: str = Field(default='', max_length=4000)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Give this asset a name')
        return value

    @field_validator('tags')
    @classmethod
    def clean_tags(cls, values):
        result, seen = [], set()
        for value in values:
            value = value.strip()
            if len(value) > 60:
                raise ValueError('Tags must be 60 characters or fewer')
            if value and value.casefold() not in seen:
                seen.add(value.casefold())
                result.append(value)
        return result


class GalleryOrigin(BaseModel):
    kind: Literal['generator', 'layer']
    module: str | None = None
    label: str


def bounds(paths: list[Path]) -> tuple[float, float, float, float]:
    x0 = y0 = math.inf
    x1 = y1 = -math.inf
    drawable = False
    for path in paths:
        drawable |= len(path.points) >= 2
        for x, y in path.points:
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError('The drawing contains non-finite coordinates')
            x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
    if not drawable:
        raise ValueError('There are no lines to save')
    return x0, y0, x1, y1


class GalleryRecord(GalleryMetadata):
    version: Literal[1] = 1
    id: str = Field(pattern=r'^[0-9a-f]{32}$')
    created_at: datetime
    origin: GalleryOrigin
    paths: list[Path]

    @model_validator(mode='after')
    def valid_geometry(self):
        bounds(self.paths)
        return self

    def metadata(self):
        x0, y0, x1, y1 = bounds(self.paths)
        return {**self.model_dump(mode='json', exclude={'paths'}),
                'width_mm': x1 - x0, 'height_mm': y1 - y0}


def thumbnail(paths: list[Path]) -> str:
    """Line-only view, including closed filled silhouettes as outlines.

    Display sampling never changes stored paths. Stroke width scales with
    bounds so a tiny asset and a page-sized asset are both legible in a tile.
    """
    x0, y0, x1, y1 = bounds(paths)
    span = max(x1 - x0, y1 - y0, 1.)
    pad = span * .06
    stride = max(1, math.ceil(sum(len(p.points) for p in paths) / 60000))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0-pad} {y0-pad} {x1-x0+2*pad} {y1-y0+2*pad}">',
             f'<g fill="none" stroke="#100F0F" stroke-width="{span/650}" stroke-linejoin="round" stroke-linecap="round">']
    for path in paths:
        if len(path.points) < 2:
            continue
        step = min(stride, max(1, (len(path.points)-1)//3)) if path.is_closed else stride
        points = path.points[::step]
        if points[-1] != path.points[-1]:
            points = [*points, path.points[-1]]
        d = ' '.join(f'{x:.8g},{y:.8g}' for x, y in points)
        parts.append(f'<polyline points="{d}"/>')
    return ''.join([*parts, '</g></svg>'])


class GalleryStore:
    def __init__(self, root: FsPath):
        self.root = root
        self._lock = threading.RLock()
        self._index = {}  # file stat -> metadata only; never pins stored geometry
        self._drafts = OrderedDict()

    def _file(self, asset_id):
        if not re.fullmatch(r'[0-9a-f]{32}', asset_id):
            raise KeyError('Asset not found')
        return self.root / f'{asset_id}.json'

    def _read(self, asset_id):
        try:
            record = GalleryRecord.model_validate_json(self._file(asset_id).read_text())
        except FileNotFoundError:
            raise KeyError('Asset not found') from None
        if record.id != asset_id:
            raise ValueError('Asset identifier does not match its file')
        return record

    def _write(self, record):
        self.root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.asset-', suffix='.tmp', dir=self.root)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(record.model_dump_json())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self._file(record.id))
        finally:
            if os.path.exists(name):
                os.unlink(name)
        self._index.pop(record.id, None)

    def list(self, q='', tag='', generator=''):
        with self._lock:
            records, warnings, existing = [], [], set()
            for path in self.root.glob('*.json'):
                existing.add(path.stem)
                try:
                    stat = path.stat()
                    stamp = (stat.st_mtime_ns, stat.st_size)
                    cached = self._index.get(path.stem)
                    if cached is None or cached[0] != stamp:
                        cached = (stamp, self._read(path.stem).metadata())
                        self._index[path.stem] = cached
                    records.append(cached[1])
                except (ValueError, OSError, KeyError):
                    warnings.append(f'Could not read asset {path.stem}')
            self._index = {k: v for k, v in self._index.items() if k in existing}
            tags, generators, counts = {}, {}, {}
            for record in records:
                for t in record['tags']:
                    tags.setdefault(t.casefold(), t)
                    counts[t.casefold()] = counts.get(t.casefold(), 0) + 1
                origin = record['origin']
                if origin['module']:
                    generators[origin['module']] = origin['label']
            selected = [r for r in records
                        if (not tag or tag.casefold() in [t.casefold() for t in r['tags']])
                        and (not generator or r['origin']['module'] == generator)
                        and (not q or q.casefold() in ' '.join([
                            r['name'], r['note'], *r['tags'], r['origin']['label'],
                            r['origin']['module'] or '']).casefold())]
            return {'items': sorted(selected, key=lambda r: (r['created_at'], r['id']), reverse=True),
                    'tags': sorted(tags.values(), key=str.casefold),
                    'tag_counts': [{'tag': tags[k], 'count': count} for k, count in
                                   sorted(counts.items(), key=lambda entry: (-entry[1], entry[0]))],
                    'generators': [{'id': k, 'label': v} for k, v in sorted(generators.items())],
                    'warnings': warnings}

    def get(self, asset_id):
        with self._lock:
            return self._read(asset_id).metadata()

    def paths(self, asset_id):
        with self._lock:
            return self._read(asset_id).paths

    def prepare(self, paths, name, origin):
        record = GalleryRecord(id=uuid4().hex, name=name, origin=origin,
                               created_at=datetime.now(timezone.utc),
                               paths=[p.model_copy(deep=True) for p in paths])
        with self._lock:
            now = time.monotonic()
            self._drafts = OrderedDict((k, v) for k, v in self._drafts.items() if now-v[0] < 3600)
            self._drafts[record.id] = (now, record)
            # Protect the newest capture even when one drawing exceeds budget.
            total = sum(sum(len(p.points) for p in r.paths) for _, r in self._drafts.values())
            while len(self._drafts) > 1 and (len(self._drafts) > 16 or total > 3_000_000):
                _, (_, old) = self._drafts.popitem(last=False)
                total -= sum(len(p.points) for p in old.paths)
        return {**record.metadata(), 'capture_id': record.id, 'thumbnail': thumbnail(record.paths)}

    def save(self, capture_id, **metadata):
        values = GalleryMetadata(**metadata)
        with self._lock:
            # Capture ID is also the stable asset ID: an uncertain retry is
            # idempotent, even after a process restart.
            if self._file(capture_id).exists():
                return self._read(capture_id).metadata()
            draft = self._drafts.get(capture_id)
            if draft is None or time.monotonic()-draft[0] >= 3600:
                raise KeyError('Capture expired; close this dialog and save the drawing again')
            record = draft[1].model_copy(update=values.model_dump())
            self._write(record)
            self._drafts.pop(capture_id, None)
            return record.metadata()

    def update(self, asset_id, **metadata):
        values = GalleryMetadata(**metadata)
        with self._lock:
            record = self._read(asset_id).model_copy(update=values.model_dump())
            self._write(record)
            return record.metadata()

    def delete(self, asset_id):
        with self._lock:
            self._read(asset_id)
            self._file(asset_id).unlink()
            self._index.pop(asset_id, None)


gallery_store = GalleryStore(CONFIG_DIR / 'gallery')

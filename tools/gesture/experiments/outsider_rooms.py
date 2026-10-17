"""Round 12 outsider: draw with a moving, telescopic arm.

One learned hand drives the arm's heading; a slower copy moves its pivot.
Only the arm's end draws. No source outlines, area fills, hatch, or pen lifts.
Run from repo root with .local/gesture/.venv/bin/python.
Frozen research imports live under .local/gesture/out/outsider/frozen.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter1d

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / '.local/gesture/out/outsider'
FROZEN = OUT / 'frozen/tools/gesture'
if not (FROZEN/'gesture/__init__.py').exists():
    raise RuntimeError('Restore the HEAD snapshot described in results/outsider-2026-10-17.md first.')
# A private package name also keeps tests from accidentally using the live kit.
_spec = importlib.util.spec_from_file_location('outsider_frozen_gesture', FROZEN/'gesture/__init__.py',
                                               submodule_search_locations=[str(FROZEN/'gesture')])
_package = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _package
_spec.loader.exec_module(_package)
kit = importlib.import_module('outsider_frozen_gesture.kit')

PAPER = '#FFFCF0'
INK = '#100F0F'
FROZEN_COMMIT = '6b169b2008296a03c9ec67ea342079f7186ce34d'


def arclength_resample(p, count=3600):
    p = np.asarray(p, float)
    s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    keep = np.r_[True, np.diff(s) > 1e-10]
    return np.column_stack([np.interp(np.linspace(0, s[-1], count), s[keep], p[keep, j]) for j in range(2)])


def arm_trace(p, *, arm=0.23, pivot=0.72, lag=0.025, breathe=0.28, phase=0.0, gear=1.0):
    """Translation/scale-invariant motion transfer, with no added random noise.

    Lengths use source bbox diagonal. Heading memory and pivot memory operate
    in fractions of total source arc, so the answer is sampling-independent.
    """
    p = arclength_resample(p)
    scale = np.linalg.norm(np.ptp(p, axis=0))
    p = (p - p.mean(axis=0)) / scale
    n = len(p)
    support = gaussian_filter1d(p, n * lag, axis=0, mode='nearest')
    v = np.gradient(gaussian_filter1d(p, n * 0.0015, axis=0, mode='nearest'), axis=0)
    theta = np.unwrap(np.arctan2(v[:, 1], v[:, 0]))
    theta = gaussian_filter1d(theta, n * 0.0025, mode='nearest')
    turning = np.abs(np.gradient(theta)) * n
    activity = gaussian_filter1d(turning, n * .018, mode='nearest')
    activity /= max(float(np.quantile(activity, .8)), 1e-8)
    radius = arm * (1 + breathe * np.tanh(activity - .7))
    theta = theta[0] + gear * (theta - theta[0]) + phase
    return pivot * support + radius[:, None] * np.column_stack([np.cos(theta), np.sin(theta)])


def fit(p, frame=(190., 190.), margin=18.):
    lo, hi = p.min(axis=0), p.max(axis=0)
    scale = np.min((np.asarray(frame) - 2 * margin) / np.maximum(hi - lo, 1e-12))
    return (p - (lo + hi) / 2) * scale + np.asarray(frame) / 2


def source(params):
    recipe = {'seed': params['seed'], 'frame': [160., 160.], 'margin': 8.,
              'voice': {'id': 'hand', 'hand': params.get('hand', 'fly_open'),
                        'length': params.get('length', 3.7), 'joins': 'chain'},
              'renderer': {'id': 'wire', 'pen': .4}}
    sheet = kit.run(recipe)
    return np.array(sheet.marks[0].points, copy=True)


def geometry(params):
    p = source(params)
    if params.get('raw', False):
        q = arclength_resample(p)
    else:
        q = arm_trace(p, **{k: params[k] for k in ['arm', 'pivot', 'lag', 'breathe', 'phase', 'gear'] if k in params})
    angle = np.deg2rad(params.get('rotation_deg', 0.))
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    return fit(q @ rot.T, params.get('frame', [190., 190.]), params.get('margin', 18.))


def render_many(paths, params, path, long_side=2000):
    frame = np.array(params.get('frame', [190., 190.]))
    scale = long_side / max(frame)
    aa = 2
    size = tuple(np.round(frame * scale * aa).astype(int))
    im = Image.new('RGB', size, PAPER)
    d = ImageDraw.Draw(im)
    for p in paths:
        pts = [tuple(x) for x in p * scale * aa]
        d.line(pts, fill=INK, width=max(1, round(params.get('pen', .42) * scale * aa)), joint='curve')
    im = im.resize(tuple(np.round(frame * scale).astype(int)), Image.Resampling.LANCZOS)
    metadata = dict(params)
    metadata['geometry_sha256'] = geometry_digest(paths)
    metadata['path_count'] = len(paths)
    metadata['frozen_commit'] = FROZEN_COMMIT
    exif = Image.Exif()
    exif[270] = json.dumps(metadata, sort_keys=True)
    im.save(path, quality=95, subsampling=0, exif=exif)
    return im


def geometry_digest(paths):
    return hashlib.sha256(b''.join(np.asarray(p, '<f8').tobytes() for p in paths)).hexdigest()


def render(p, params, path, long_side=2000):
    return render_many([p], params, path, long_side)


def process_geometry(params):
    """Independent scale per cell: driver, slow pivot, drawn end. No connectors."""
    base = params['base']
    p = arclength_resample(source(base))
    p = (p - p.mean(axis=0)) / np.linalg.norm(np.ptp(p, axis=0))
    pivot = base['pivot'] * gaussian_filter1d(p, len(p) * base['lag'], axis=0, mode='nearest')
    panels = [fit(x, base['frame'], base['margin']) for x in [p, pivot]] + [geometry(base)]
    return [x + [i * (base['frame'][0] + params['gap']), 0] for i, x in enumerate(panels)]


def review_manifest():
    text = (ROOT/'tools/gesture/results/outsider-2026-10-17.md').read_text()
    for block in re.findall(r'```json\s*\n(.*?)\n```', text, re.S):
        data = json.loads(block)
        if data.get('format') == 'outsider-review-v1':
            return data
    raise ValueError('no outsider-review-v1 JSON manifest in report')


def rebuild_review():
    for record in review_manifest()['images']:
        params = record['parameters']
        paths = process_geometry(params) if record['kind'] == 'process' else [geometry(params)]
        path = ROOT/'tools/gesture/results'/record['file']
        render_many(paths, params, path, long_side=record['long_side_px'])
        (OUT/f"{path.stem}.parameters.json").write_text(json.dumps(params, indent=2) + '\n')
        np.savez_compressed(OUT/f'{path.stem}.paths.npz', **{f'path_{i}': p for i, p in enumerate(paths)})
        print(path.relative_to(ROOT), geometry_digest(paths))


def save(params, name, directory=OUT):
    directory.mkdir(parents=True, exist_ok=True)
    p = geometry(params)
    path = directory / f'{name}.jpg'
    im = render(p, params, path)
    (OUT / f'{name}.parameters.json').write_text(json.dumps(params, indent=2) + '\n')
    np.savez_compressed(OUT / f'{name}.paths.npz', points=p)
    print(json.dumps({'name': name, 'seed': params['seed'], 'length_mm': float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()),
                      'points': len(p), 'path_count': 1, 'image': str(path.relative_to(ROOT))}))
    return im


def scan():
    images = []
    for i, seed in enumerate([19331, 19337, 19349, 19351, 19373, 19379, 19381, 19387, 19391, 19403, 19417, 19421]):
        params = {'seed': seed, 'length': 3.7, 'arm': .23, 'pivot': .72, 'lag': .025, 'breathe': .28, 'phase': 1.5707963267948966}
        im = save(params, f'scan-{i+1:02d}')
        im.thumbnail((460, 460))
        images.append(im)
    contact = Image.new('RGB', (1920, 3*500), PAPER)
    d = ImageDraw.Draw(contact)
    for i, im in enumerate(images):
        x, y = i % 4 * 480, i // 4 * 500
        contact.paste(im, (x, y))
        d.text((x+15, y+465), f'{i+1:02d}', fill=INK)
    contact.save(OUT/'population.jpg', quality=94)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scan', action='store_true')
    parser.add_argument('--parameters', type=Path)
    parser.add_argument('--name', default='drawing')
    parser.add_argument('--review', action='store_true')
    parser.add_argument('--rebuild-review', action='store_true', help='rebuild the four images from the adjacent report manifest')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.rebuild_review:
        rebuild_review()
    elif args.scan:
        scan()
    elif args.parameters:
        save(json.loads(args.parameters.read_text()), args.name, ROOT/'tools/gesture/results' if args.review else OUT)
    else:
        parser.error('choose --scan or --parameters')


if __name__ == '__main__':
    main()

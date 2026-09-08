"""Compare the previous committed silhouette implementation with the current one.
Run with .venv/bin/python docs/reviews/ribbon-performance-2026-09-09/benchmark.py
"""
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from axibridge.compose import CanvasLayer, shape_layer
from axibridge.effects import ribbon
from axibridge.sources.pen import PenParams, PenSource

BASE = '77785ce'
old = {'__name__': '_ribbon_geometry_baseline'}
exec(compile(subprocess.check_output(['git', 'show', f'{BASE}:axibridge/effects/_ribbon_geometry.py'], cwd=ROOT), '<committed ribbon geometry>', 'exec'), old)
fixture = ROOT / 'docs/reviews/ribbon-edge-joins-2026-09-09/input.json'
layer = CanvasLayer(**json.loads(fixture.read_text()))
source = PenSource().generate(PenParams(**layer.source.params)).layers[0].paths
current = ribbon.silhouette
functions = {'before': old['silhouette'], 'after': current}
timings = {name: [] for name in functions}
reference = None
try:
    for iteration in range(3):
        for name, function in functions.items():
            ribbon.silhouette = function
            start = time.perf_counter()
            result = shape_layer(layer, source)
            timings[name].append(time.perf_counter() - start)
            coordinates = [(p.points, p.filled) for p in result]
            if reference is None:
                reference = coordinates
            assert coordinates == reference
finally:
    ribbon.silhouette = current
medians = {name: statistics.median(times) for name, times in timings.items()}
print(json.dumps({'baseline_commit': BASE, 'seconds': timings, 'median_seconds': medians,
                  'reduction_percent': 100*(1-medians['after']/medians['before']),
                  'exact_geometry': True}, indent=2))

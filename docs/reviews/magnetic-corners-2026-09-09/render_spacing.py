"""Render a matched population from the registered source, with neutral cell IDs."""
from pathlib import Path
import json
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from axibridge.sources.magnetic_field import MagneticFieldParams, MagneticFieldSource

OUT = Path(__file__).resolve().parent
fig, axes = plt.subplots(2, 3, figsize=(14, 7))
records = []
for row, visible in enumerate([True, False]):
    for col, spacing in enumerate([1.0, 0.0, 0.3]):
        cell = f'{chr(65+row)}{col+1}'
        params = MagneticFieldParams(show_magnets=visible, keep_silhouettes=False, pole_spacing=spacing)
        start = time.perf_counter()
        doc = MagneticFieldSource().generate(params)
        elapsed = time.perf_counter()-start
        lines = [p.points for layer in doc.layers for p in layer.paths]
        ax=axes[row,col]
        ax.add_collection(LineCollection(lines,colors='black',linewidths=.35))
        ax.set(xlim=(0,240),ylim=(170,0),aspect='equal',title=cell)
        ax.axis('off')
        records.append(dict(cell=cell,spacing=spacing,visible=visible,paths=len(lines),seconds=elapsed))
        detail, da = plt.subplots(figsize=(12,8.5))
        da.add_collection(LineCollection(lines,colors='black',linewidths=.4))
        da.set(xlim=(0,240),ylim=(170,0),aspect='equal'); da.axis('off')
        detail.savefig(OUT/f'{cell}.png',dpi=140,bbox_inches='tight',pad_inches=.05)
        plt.close(detail)
fig.tight_layout(); fig.savefig(OUT/'spacing-sheet.png',dpi=150)
(OUT/'spacing-metrics.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps(records,indent=2))

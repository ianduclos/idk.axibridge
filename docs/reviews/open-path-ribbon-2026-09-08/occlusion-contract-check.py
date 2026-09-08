"""Check study silhouettes against the app's existing filled-path mask contract."""
from pathlib import Path as FilePath
import json
import os
import subprocess
import sys
import tempfile
HERE=FilePath(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
with tempfile.TemporaryDirectory(prefix='ribbon-contract-') as config:
    os.environ['AXIBRIDGE_CONFIG_DIR']=config
    from axibridge.model import Path
    from axibridge.compose import build_mask, clip_paths
    from shapely.geometry import Polygon, LineString
    from shapely.ops import unary_union
    code="""require('./load-join.cjs');require('./silhouette.js');require('./geometry.js');
    const R=globalThis.RibbonStudy;
    console.log(JSON.stringify(Object.entries(R.fixtures).map(([name,p])=>({name,...R.generate(p,{rhythm:'phrased',outputMode:'outline',mergeOverlaps:true,solidOccluder:true,width:24})}))));"""
    rows=json.loads(subprocess.check_output(['node','-e',code],cwd=HERE,text=True))
    for row in rows:
        paths=[Path(**p) for p in row['occluders']]
        mask=build_mask(paths,.3,0)
        expected=unary_union([Polygon(p[0],p[1:]) for p in row['silhouette']])
        assert mask is not None and mask.is_valid, row['name']
        assert mask.symmetric_difference(expected).area<1e-7,row['name']
        x0,y0,x1,y1=mask.bounds
        scan=[Path(points=[(x0-1,y),(x1+1,y)]) for y in [y0+(y1-y0)*t for t in [.2,.4,.6,.8]]]
        clipped=clip_paths(scan,mask)
        length=lambda ps:sum(LineString(p.points).length for p in ps)
        assert length(clipped)<length(scan),row['name']
    print('occlusion-contract-check: six filled silhouettes match app masks, holes preserved, lower paths clipped')

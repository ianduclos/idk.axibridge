"""Developer-only parity check; the application never requires Node."""
import json
from pathlib import Path as File
import subprocess
import sys
from shapely.geometry import LineString

ROOT = File(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from axibridge.effects.ribbon import Ribbon, RibbonParams
from axibridge.model import Path
from axibridge.registry import EffectContext
HERE = File(__file__).resolve().parent
script = '''
require('./load-join.cjs');require('./geometry.js');
const r=globalThis.RibbonStudy;
const options={width:24,wavelength:120,steps:10,seed:7,seedB:19,
  rhythm:'phrased',spacingVariation:.75,heightVariation:.75,phrasing:.7,
  relation:'related',variation:.75,taper:.12};
console.log(JSON.stringify(Object.entries(r.fixtures).map(([name,source])=>
  ({name,source,strands:r.generate(source,options).strands}))));
'''
fixtures=json.loads(subprocess.check_output(['node','-e',script],cwd=HERE,text=True))
worst=0
for fixture in fixtures:
    source=Path(points=[(x/4,y/4) for x,y in fixture['source']])
    out=Ribbon().apply([source],RibbonParams(),EffectContext())
    assert len(out)==len(fixture['strands'])
    error=max(LineString(p.points).hausdorff_distance(LineString([(x/4,y/4) for x,y in q]))
              for p,q in zip(out,fixture['strands']))
    worst=max(worst,error)
    assert error<1e-6,(fixture['name'],error)
print(f'{len(fixtures)} complete production fixtures match study; maximum Hausdorff error {worst:.3g} mm')

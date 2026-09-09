"""Real JavaScript arrangement math, without a browser or field solver."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which('node'), reason='Node unavailable')
def test_interpolation_corners_continuity_fit_and_identity():
    root = Path(__file__).resolve().parents[1]
    script = """
    import assert from 'node:assert/strict';
    import {interpolated, scattered} from './axibridge/static/js/magnetic_arrangement.js';
    const m = {kind:'bar', x:60, y:60, rotation:170, strength:.5, length:48, thickness:12, flipped:false, locked:true};
    const corners = [[m], [{...m,x:100,rotation:-170,strength:1.5}],
      [{...m,y:100,strength:1.5}], [{...m,x:100,y:100,rotation:-170,strength:2.5}]];
    const p = {width:240,height:170,magnets:[m],presets:corners};
    const original = JSON.stringify(p);
    assert.deepEqual(interpolated(p,0,0),corners[0]);
    assert.deepEqual(interpolated(p,1,0),corners[1]);
    assert.deepEqual(interpolated(p,0,1),corners[2]);
    assert.deepEqual(interpolated(p,1,1),corners[3]);
    const center = interpolated(p,.5,.5)[0];
    assert.equal(center.x,80); assert.equal(center.y,80); assert.equal(center.strength,1.5);
    assert.equal(Math.abs(center.rotation),180); assert.equal(center.locked,true);
    assert.equal(JSON.stringify(p),original);
    for(let x=0;x<=1;x+=.1) for(let y=0;y<=1;y+=.1) {
      const v=interpolated(p,x,y)[0];
      assert.ok(v.x>=60 && v.x<=100.000001 && v.y>=60 && v.y<=100.000001);
      assert.ok(Math.abs(v.rotation)>=169.999);
    }
    // A long body can fit both corner angles but need shrinking between them.
    const narrow={width:40,height:100,magnets:[{...m,x:20,y:50,length:80,rotation:90}],presets:[]};
    narrow.presets=Array.from({length:4},(_,i)=>[{...narrow.magnets[0],rotation:i%2 ? -90 : 90}]);
    narrow.preset_sizes=[{length:80,thickness:12}];
    const fitted=interpolated(narrow,.5,.5)[0];
    const a=fitted.rotation*Math.PI/180;
    const ex=(Math.abs(Math.cos(a))*fitted.length+Math.abs(Math.sin(a))*fitted.thickness)/2;
    assert.ok(fitted.x-ex>=0 && fitted.x+ex<=40);
    // Fitting in one pose must not ratchet down size in later corner blends.
    narrow.presets[1][0] = fitted;
    narrow.presets[3][0] = fitted;
    const turnBack = interpolated(narrow,.5,0)[0];
    assert.ok(turnBack.length > fitted.length);
    const restored = interpolated(narrow,0,0)[0];
    assert.equal(restored.length,80);
    const sizesOnly = {...p,preset_sizes:[{length:48,thickness:12}],presets:corners.map(c=>c.map(m=>({...m})))};
    sizesOnly.presets[1][0].length=20;
    assert.equal(interpolated(sizesOnly,.5,0)[0].length,48);

    """
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

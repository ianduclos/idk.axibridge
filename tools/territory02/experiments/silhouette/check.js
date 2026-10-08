const fs = require('fs'), assert = require('assert');
const E = require('./territory-engine.js');
const results = [];
for (const recipe of ['sparse', 'full']) {
  const cfg = JSON.parse(fs.readFileSync(`../../${recipe}.json`, 'utf8'));
  for (const seed of [5, 13, 18, 24]) {
    const sh = E.randomSheet(seed), prm = {...cfg.prm, camps:Math.max(2,sh.camps)};
    const before = JSON.stringify(sh.cores);
    const a = E.runTerritory(sh.cores, prm, seed, 'reversed');
    const b = E.runTerritory(sh.cores, prm, seed, 'reversed');
    assert.strictEqual(JSON.stringify(a.lines),JSON.stringify(b.lines), `nondeterministic ${recipe}/${seed}`);
    assert.strictEqual(JSON.stringify(sh.cores),before, `input mutation ${recipe}/${seed}`);
    const strokes = a.lines.flatMap(l=>l.strokes);
    let ink = 0, points = 0, maxSegment = 0;
    for (const st of strokes) {
      assert(st.length >= 2);
      ink += E.polyLen(st);
      for (let i=0;i<st.length;i++) {
        const [x,y] = st[i]; points++;
        assert(Number.isFinite(x)&&Number.isFinite(y));
        assert(x>=0&&x<=300&&y>=0&&y<=218, `${recipe}/${seed} outside bed ${x},${y}`);
        if(i) maxSegment=Math.max(maxSegment,Math.hypot(x-st[i-1][0],y-st[i-1][1]));
      }
    }
    assert(ink>0&&ink<100000,`${recipe}/${seed} ink cap`);
    results.push({recipe,seed,strokes:strokes.length,points,inkMm:Math.round(ink),maxSegmentMm:+maxSegment.toFixed(3),finite:true,withinBed:true,deterministic:true,inputPreserved:true});
  }
}
fs.writeFileSync('checks.json',JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify(results,null,2));

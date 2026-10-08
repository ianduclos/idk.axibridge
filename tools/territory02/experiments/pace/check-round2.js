// Geometry contracts only; no aesthetic thresholds.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const context = { module: { exports: {} }, console };
vm.runInNewContext(fs.readFileSync('territory-engine.js', 'utf8') + '\nmodule.exports.paceCurve = paceCurve; module.exports.hingeCurve = hingeCurve; module.exports.crossings = crossings;', context);
const H = context.module.exports;
const E = require('./territory-engine.js');
const curve = Array.from({length: 81}, (_, i) => [35 + 2 * i, 100 + 35 * Math.sin(i / 17)]);
const before = JSON.stringify(curve);
const a = H.paceCurve(curve, E.mulberry32(5)), b = H.paceCurve(curve, E.mulberry32(5));
assert.equal(JSON.stringify(a), JSON.stringify(b));
assert.equal(JSON.stringify(curve), before);
// Resampling may omit an endpoint within 0.45mm; use that stated contract.
assert(Math.hypot(a[0][0] - curve[0][0], a[0][1] - curve[0][1]) < 1e-10);
assert(Math.hypot(a.at(-1)[0] - curve.at(-1)[0], a.at(-1)[1] - curve.at(-1)[1]) <= 0.45);
const hingeInput = Array.from({length:121}, (_,i) => [45+1.5*i,100+25*Math.sin(i/10)]);
const hinged = H.hingeCurve(hingeInput);
assert.equal(hinged.length, hingeInput.length);
assert.equal(JSON.stringify(curve), before);
assert.equal(JSON.stringify(hinged[0]), JSON.stringify(hingeInput[0]));
assert.equal(JSON.stringify(hinged.at(-1)), JSON.stringify(hingeInput.at(-1)));
assert(hinged.some((p,i) => Math.hypot(p[0]-hingeInput[i][0],p[1]-hingeInput[i][1]) > 0.01));
assert(hinged.every((p,i) => Math.hypot(p[0]-hingeInput[i][0],p[1]-hingeInput[i][1]) <= 6.000001));
const report = [];
for (const recipe of ['sparse', 'full']) {
  const cfg = JSON.parse(fs.readFileSync('round2-' + recipe + '.json', 'utf8'));
  for (const c of cfg.cells) {
    const sh = E.randomSheet(c.random), prm = {...cfg.prm, camps: Math.max(2, sh.camps), debug:true};
    const run = () => E.runTerritory(sh.cores, prm, c.random, c.order);
    const res = run(), second = run();
    assert.equal(JSON.stringify(res.lines), JSON.stringify(second.lines));
    let mm = 0, points = 0;
    for (const stroke of res.lines.flatMap(l => l.strokes)) {
      mm += E.polyLen(stroke);
      for (const p of stroke) {
        assert(Number.isFinite(p[0]) && Number.isFinite(p[1]));
        assert(p[0] >= 0 && p[0] <= 300 && p[1] >= 0 && p[1] <= 218);
        points++;
      }
    }
    assert(mm < 100000); assert(points <= 250000);
    const pre = E.runTerritory(sh.cores, {...prm, hinge: 0}, c.random, c.order);
    assert.equal(JSON.stringify(res.meander.events), JSON.stringify(pre.meander.events));
    const now = res.T.meanderDebug.chans, old = pre.T.meanderDebug.chans;
    for (let i=1;i<now.length;i++) assert.equal(JSON.stringify(now[i].present), JSON.stringify(old[i].present));
    const intersections = chans => chans.slice(1).map(c => c.present && chans[0].present ? H.crossings(chans[0].present,c.present) : 0);
    var beforeCross = intersections(old), afterCross = intersections(now);
    report.push({recipe, seed: c.random, mm: Math.round(mm), points, deterministic: true, finite: true, withinBed: true, beforeCross, afterCross});
  }
}
fs.writeFileSync('round2-checks.json', JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report));

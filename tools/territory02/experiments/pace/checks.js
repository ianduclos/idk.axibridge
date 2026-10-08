// Geometry contracts only; no aesthetic thresholds.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const context = { module: { exports: {} }, console };
vm.runInNewContext(fs.readFileSync('territory-engine.js', 'utf8') + '\nmodule.exports.paceCurve = paceCurve;', context);
const E = context.module.exports;
const curve = Array.from({length: 81}, (_, i) => [35 + 2 * i, 100 + 35 * Math.sin(i / 17)]);
const before = JSON.stringify(curve);
const a = E.paceCurve(curve, E.mulberry32(5)), b = E.paceCurve(curve, E.mulberry32(5));
assert.equal(JSON.stringify(a), JSON.stringify(b));
assert.equal(JSON.stringify(curve), before);
// Resampling may omit an endpoint within 0.45mm; use that stated contract.
assert(Math.hypot(a[0][0] - curve[0][0], a[0][1] - curve[0][1]) < 1e-10);
assert(Math.hypot(a.at(-1)[0] - curve.at(-1)[0], a.at(-1)[1] - curve.at(-1)[1]) <= 0.45);
const report = [];
for (const recipe of ['sparse', 'full']) {
  const cfg = JSON.parse(fs.readFileSync('../../' + recipe + '.json', 'utf8'));
  for (const c of cfg.cells) {
    const sh = E.randomSheet(c.random), prm = {...cfg.prm, camps: Math.max(2, sh.camps)};
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
    assert(mm < 100000);
    report.push({recipe, seed: c.random, mm: Math.round(mm), points, deterministic: true, finite: true, withinBed: true});
  }
}
fs.writeFileSync('round1-checks.json', JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report));

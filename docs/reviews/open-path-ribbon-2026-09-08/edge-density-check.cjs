'use strict';

require('./load-join.cjs');
require('./geometry.js');
const assert = require('node:assert/strict');
const R = globalThis.RibbonStudy;

const EPS = 1e-9;
const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const finite = result => result.strands.every(path =>
  path.every(point => point.length === 2 && point.every(Number.isFinite)));

function assertSharedEndpoints(result, source, label) {
  for (const strand of result.strands) {
    assert.deepEqual(strand[0], source[0], `${label}: start must stay exact`);
    assert.deepEqual(strand.at(-1), source.at(-1), `${label}: end must stay exact`);
  }
}

function maxAdjacentGap(result) {
  let maximum = 0;
  for (let strand = 1; strand < result.strands.length; strand++) {
    assert.equal(result.strands[strand].length, result.strands[0].length,
      'straight strands must share sampling stations');
    for (let station = 0; station < result.strands[strand].length; station++) {
      maximum = Math.max(maximum,
        distance(result.strands[strand - 1][station], result.strands[strand][station]));
    }
  }
  return maximum;
}

const straight = [[0, 0], [600, 0]];
const manual = {width: 38, wavelength: 110, variation: .82, seed: 13,
  relation: 'related', steps: 7, taper: 0};
const edges = R.generate(straight, {...manual, interpolation: 'edges'});
assert.equal(edges.strands.length, 2 * manual.steps,
  'edge interpolation produces an even strand population');
assert.deepEqual(edges.strands[0], edges.left,
  'first edge strand is exactly the generated left boundary');
assert.deepEqual(edges.strands.at(-1), edges.right,
  'last edge strand is exactly the generated right boundary');
assert.ok(!edges.strands.some(path => JSON.stringify(path) === JSON.stringify(edges.spine)),
  'edge interpolation has no dedicated original-spine strand');
assertSharedEndpoints(edges, straight, 'edge mode');

// Each station is a direct blend between the signed outer widths. Even when
// related sides differ, every adjacent pair therefore has the same gap.
for (let station = 0; station < edges.strands[0].length; station++) {
  const gaps = edges.strands.slice(1).map((path, index) =>
    distance(edges.strands[index][station], path[station]));
  for (const gap of gaps.slice(1)) {
    assert.ok(Math.abs(gap - gaps[0]) <= EPS,
      `edge gaps must be uniform at station ${station}`);
  }
}

const legacy = R.generate(straight, manual);
const explicitSpine = R.generate(straight, {...manual, interpolation: 'spine'});
assert.deepEqual(legacy, explicitSpine,
  'omitting interpolation retains the exact prior spine-mode result');
assert.equal(legacy.strands.length, 2 * manual.steps + 1);
assertSharedEndpoints(legacy, straight, 'spine mode');

const full = R.generate(R.fixtures.corner, {...manual, interpolation: 'edges'});
const retainedSteps = 4;
const trimmed = R.generate(R.fixtures.corner, {
  ...manual, interpolation: 'edges', retainedSteps
});
assert.deepEqual(trimmed.strands,
  full.strands.slice(manual.steps - retainedSteps, manual.steps + retainedSteps),
  'edge trimming removes exact symmetric outer pairs from the full even set');
assert.deepEqual(trimmed.left, trimmed.strands[0]);
assert.deepEqual(trimmed.right, trimmed.strands.at(-1));
assert.ok(finite(trimmed), 'trimmed corner geometry remains finite');
assertSharedEndpoints(trimmed, R.fixtures.corner, 'trimmed edge corner');

const broadPen = R.generate(straight, {
  ...manual, interpolation: 'edges', autoDensity: true, penWidth: 8
});
const finePen = R.generate(straight, {
  ...manual, interpolation: 'edges', autoDensity: true, penWidth: 2
});
assert.ok(finePen.strands.length >= broadPen.strands.length,
  'a thinner pen never chooses a lower edge density');
assert.ok(maxAdjacentGap(broadPen) <= 8 * .9 + EPS,
  'broad-pen auto density meets the measured straight-path gap target');
assert.ok(maxAdjacentGap(finePen) <= 2 * .9 + EPS,
  'fine-pen auto density meets the measured straight-path gap target');

const capped = R.generate(straight, {
  ...manual, width: 2000, interpolation: 'edges', autoDensity: true, penWidth: .01
});
assert.equal(capped.strands.length, 1024, 'automatic edge density caps at 512 steps');
assert.equal(capped.diagnostics.densityLimited, true,
  'the diagnostic reports when the density cap prevents the requested spacing');

const inputs = [straight, [[0, 70], [300, 70]], [[0, 140], [120, 140]]];
const many = R.generateMany(inputs, {
  ...manual, interpolation: 'edges', autoDensity: true, penWidth: 3,
  widthByLength: true
});
const probedSteps = inputs.map(input => R.generate(input, {
  ...manual, interpolation: 'edges', autoDensity: true, penWidth: 3
}).strands.length / 2);
assert.equal(many.steps, Math.max(...probedSteps),
  'generateMany chooses the largest required density before width trimming');
assert.equal(many.retainedSteps[0], many.steps,
  'the longest input retains the shared global step count');
assert.equal(many.items[0].strands.length, 2 * many.retainedSteps[0]);
for (let i = 0; i < many.items.length; i++) {
  const independentlyFull = R.generate(inputs[i], {
    ...manual, interpolation: 'edges', steps: many.steps, autoDensity: false
  });
  const retained = many.retainedSteps[i];
  assert.deepEqual(many.items[i].strands,
    independentlyFull.strands.slice(many.steps - retained, many.steps + retained),
    `generateMany item ${i} is an exact symmetric slice of its shared-density geometry`);
}

console.log('edge-density-check: edge interpolation, exact trimming, auto density, cap diagnostics, and legacy default passed');

for(const interpolation of ['spine','edges']) {
 const sizes=[0,.25,.5,.75,1].map(seedBlend=>globalThis.RibbonStudy.generateMany([globalThis.RibbonStudy.fixtures.arch],{rhythm:'phrased',seed:7,seedB:19,seedBlend,interpolation,autoDensity:true,penWidth:1}).steps);
 assert.ok(sizes.every(n=>n===sizes[0]),'auto density remains fixed through the seed blend');
}

"use strict";

const assert = require("node:assert/strict");
require("./geometry.js");
const RibbonStudy = globalThis.RibbonStudy;

function finite(result) {
  return result.strands.every(path => path.every(p => p.length === 2 && p.every(Number.isFinite)));
}

const input = RibbonStudy.fixtures.sCurve.map(p => p.slice());
const before = JSON.stringify(input);
const a = RibbonStudy.generate(input);
const b = RibbonStudy.generate(input);
assert.deepEqual(a, b, "same seed must be deterministic");
assert.equal(JSON.stringify(input), before, "input must remain unchanged");
assert.equal(a.strands.length, 21, "steps means paths per side");
assert.ok(finite(a), "all generated coordinates must be finite");
for (const path of a.strands) {
  assert.deepEqual(path[0], input[0], "every path shares the original start");
  assert.deepEqual(path.at(-1), input.at(-1), "every path shares the original end");
}

const mirrored = RibbonStudy.generate(RibbonStudy.fixtures.arch, { relation: "mirrored" });
for (let i = 0; i < mirrored.spine.length; i++) {
  assert.ok(Math.abs(mirrored.left[i][0] + mirrored.right[i][0] - 2 * mirrored.spine[i][0]) < 1e-9);
  assert.ok(Math.abs(mirrored.left[i][1] + mirrored.right[i][1] - 2 * mirrored.spine[i][1]) < 1e-9);
}

const regularRelated = RibbonStudy.generate(RibbonStudy.fixtures.arch, { relation: "related", variation: 0 });
for (let i = 0; i < regularRelated.spine.length; i++) {
  assert.ok(Math.abs(regularRelated.left[i][0] + regularRelated.right[i][0] - 2 * regularRelated.spine[i][0]) < 1e-9);
  assert.ok(Math.abs(regularRelated.left[i][1] + regularRelated.right[i][1] - 2 * regularRelated.spine[i][1]) < 1e-9);
}

const dense = RibbonStudy.generate(RibbonStudy.fixtures.straight, { steps: 3, wavelength: 40 });
assert.equal(dense.strands.length, 7);
assert.ok(dense.spine.length > RibbonStudy.fixtures.straight.length, "sampling density is arc-length based");
assert.ok(dense.spine.every((p, i, all) => i === 0 || Math.hypot(p[0] - all[i - 1][0], p[1] - all[i - 1][1]) <= 2.0000001), "study spacing is at most two units");

const stress = RibbonStudy.generate(RibbonStudy.fixtures.hairpin, { width: 90, steps: 5 });
assert.ok(finite(stress), "stress fixture remains finite");
for (let i = 1; i < stress.spine.length - 1; i++) {
  const s = stress.spine[i];
  for (let level = 1; level <= 5; level++) {
    for (const [index,edge] of [[5-level,stress.left],[5+level,stress.right]]) {
      for (let axis=0;axis<2;axis++) assert.ok(Math.abs(stress.strands[index][i][axis]-(s[axis]+(edge[i][axis]-s[axis])*level/5))<1e-8);
    }
  }
}

const closed = [[0, 0], [20, 0], [20, 20], [0, 0]];
const closedResult = RibbonStudy.generate(closed);
assert.equal(closedResult.diagnostics.reason, "closed-path-bypass");
assert.deepEqual(closedResult.strands, [closed]);

const duplicate = RibbonStudy.generate([[0, 0], [0, 0], [50, 0], [50, 0]]);
assert.ok(finite(duplicate));
assert.deepEqual(duplicate.spine[0], [0, 0]);
assert.deepEqual(duplicate.spine.at(-1), [50, 0]);

for (const degenerate of [[], [[4, 5]], [[4, 5], [4, 5]], null]) {
  const result = RibbonStudy.generate(degenerate);
  assert.equal(result.diagnostics.reason, "degenerate");
  assert.ok(finite(result));
}

console.log("geometry-check: geometry invariants and stress-case interpolation passed");

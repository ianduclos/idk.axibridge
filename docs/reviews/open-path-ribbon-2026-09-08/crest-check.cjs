"use strict";

const assert = require("node:assert/strict");
require("./load-join.cjs");
require("./masking.js");
require("./geometry.js");

const R = globalThis.RibbonStudy;
const relations = ["mirrored", "related", "independent"];
const base = {
  rhythm: "phrased",
  width: 24,
  wavelength: 90,
  spacingVariation: 0.7,
  heightVariation: 0.7,
  phrasing: 0.65,
  steps: 4,
  taper: 0.12,
  relation: "related",
};

const serial = value => JSON.stringify(value);
const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const knotsOf = profile => {
  assert.ok(profile && Array.isArray(profile.knots), "crestProfile exposes knots");
  return profile.knots;
};

function assertProfileContract(profile, total, label) {
  const knots = knotsOf(profile);
  assert.ok(knots.length >= 2, `${label}: endpoints are represented`);
  assert.equal(knots[0].s, 0, `${label}: starts at zero`);
  assert.equal(knots[0].v, 0, `${label}: starts at zero height`);
  assert.equal(knots.at(-1).s, total, `${label}: ends at total length`);
  assert.equal(knots.at(-1).v, 0, `${label}: ends at zero height`);
  for (let i = 0; i < knots.length; i++) {
    assert.ok(Number.isFinite(knots[i].s) && Number.isFinite(knots[i].v), `${label}: finite knot`);
    assert.ok(knots[i].v >= 0 && knots[i].v <= 1, `${label}: normalized knot height`);
    if (i) assert.ok(knots[i].s > knots[i - 1].s, `${label}: strictly ordered knots`);
    if (i > 0 && i < knots.length - 1) assert.ok(knots[i].v > 0, `${label}: positive interior height`);
  }
  if (typeof profile === "function") {
    for (const s of [0, total * 0.17, total * 0.5, total]) {
      const value = profile(s);
      assert.ok(Number.isFinite(value) && value >= 0 && value <= 1, `${label}: callable is normalized`);
    }
  }
}

function assertFiniteResult(result, source, label, expectSharedEndpoints) {
  const paths = [result.spine, result.left, result.right, ...result.strands];
  for (const path of paths) {
    assert.ok(Array.isArray(path) && path.length >= 2, `${label}: nonempty path`);
    assert.ok(path.every(p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite)), `${label}: finite geometry`);
  }
  const spinePoints = new Set(result.spine.map(serial));
  assert.ok(result.left.slice(1, -1).some(p => !spinePoints.has(serial(p))), `${label}: positive left width`);
  assert.ok(result.right.slice(1, -1).some(p => !spinePoints.has(serial(p))), `${label}: positive right width`);
  assert.deepEqual(result.left[0], source[0], `${label}: left start meets spine`);
  assert.deepEqual(result.right[0], source[0], `${label}: right start meets spine`);
  assert.deepEqual(result.left.at(-1), source.at(-1), `${label}: left end meets spine`);
  assert.deepEqual(result.right.at(-1), source.at(-1), `${label}: right end meets spine`);
  if (expectSharedEndpoints) {
    for (const strand of result.strands) {
      assert.deepEqual(strand[0], source[0], `${label}: strand shares start endpoint`);
      assert.deepEqual(strand.at(-1), source.at(-1), `${label}: strand shares end endpoint`);
    }
  }
}

assert.equal(typeof R.crestProfile, "function", "RibbonStudy exports crestProfile");

const total = 620;
const sameA = R.crestProfile(total, { ...base, seed: 17 });
const sameB = R.crestProfile(total, { ...base, seed: 17 });
assertProfileContract(sameA, total, "phrased profile");
assert.equal(serial(knotsOf(sameA)), serial(knotsOf(sameB)), "same seed is deterministic");

const changedSeed = R.crestProfile(total, { ...base, seed: 18 });
assert.notEqual(serial(knotsOf(sameA)), serial(knotsOf(changedSeed)), "seed changes a varied profile");

const fallback = knotsOf(R.crestProfile(total, {
  rhythm: "phrased", seed: 23, wavelength: 90, variation: 0.6, phrasing: 0.65,
}));
const explicit = knotsOf(R.crestProfile(total, {
  rhythm: "phrased", seed: 23, wavelength: 90,
  spacingVariation: 0.6, heightVariation: 0.6, phrasing: 0.65,
}));
assert.deepEqual(fallback, explicit, "variation remains the fallback for both independent controls");

const lowHeight = knotsOf(R.crestProfile(total, { ...base, seed: 31, heightVariation: 0.15 }));
const highHeight = knotsOf(R.crestProfile(total, { ...base, seed: 31, heightVariation: 0.95 }));
assert.deepEqual(lowHeight.map(k => k.s), highHeight.map(k => k.s), "height variation leaves knot positions invariant");
assert.notDeepEqual(lowHeight.map(k => k.v), highHeight.map(k => k.v), "height variation changes knot values");

const lowSpacing = knotsOf(R.crestProfile(total, { ...base, seed: 31, spacingVariation: 0.15 }));
const highSpacing = knotsOf(R.crestProfile(total, { ...base, seed: 31, spacingVariation: 0.95 }));
assert.deepEqual(lowSpacing.map(k => k.v), highSpacing.map(k => k.v), "spacing variation leaves knot values invariant");
assert.notDeepEqual(lowSpacing.map(k => k.s), highSpacing.map(k => k.s), "spacing variation changes knot positions");

const controlSource = R.fixtures.arch;
const lowHeightGeometry = R.generate(controlSource, { ...base, seed: 31, heightVariation: 0.15 });
const highHeightGeometry = R.generate(controlSource, { ...base, seed: 31, heightVariation: 0.95 });
assert.notDeepEqual(lowHeightGeometry.left, highHeightGeometry.left, "height variation changes generated geometry");
const lowSpacingGeometry = R.generate(controlSource, { ...base, seed: 31, spacingVariation: 0.15 });
const highSpacingGeometry = R.generate(controlSource, { ...base, seed: 31, spacingVariation: 0.95 });
assert.notDeepEqual(lowSpacingGeometry.left, highSpacingGeometry.left, "spacing variation changes generated geometry");

const legacyImplicit = R.generate(controlSource, { seed: 31, variation: 0.7, steps: 3 });
const legacyExplicit = R.generate(controlSource, { seed: 31, variation: 0.7, steps: 3, rhythm: "legacy" });
assert.deepEqual(legacyImplicit, legacyExplicit, "omitting rhythm preserves legacy generation");

for (const relation of relations) {
  const options = { ...base, relation, spacingVariation: 0, heightVariation: 0, seed: 1 };
  const first = R.generate(R.fixtures.sCurve, options);
  const second = R.generate(R.fixtures.sCurve, { ...options, seed: 999 });
  assert.deepEqual(first, second, `${relation}: zero spacing and height variation is seed-independent`);
}

const straight = R.fixtures.straight;
const mirrored = R.generate(straight, { ...base, relation: "mirrored", seed: 43 });
const related = R.generate(straight, { ...base, relation: "related", seed: 43 });
assertFiniteResult(mirrored, straight, "mirrored straight", true);
for (let i = 0; i < mirrored.spine.length; i++) {
  assert.ok(Math.abs(distance(mirrored.left[i], mirrored.spine[i]) - distance(mirrored.right[i], mirrored.spine[i])) < 1e-9,
    "mirrored sides have equal width at every station");
}
assert.deepEqual(related.left, mirrored.left, "relation keeps the seeded left side fixed");
assert.notDeepEqual(related.right, mirrored.right, "related side differs from exact mirroring");

const fixtureEntries = Object.entries(R.fixtures);
assert.equal(fixtureEntries.length, 6, "crest study retains all six fixtures");
const sweeps = [
  ["modest", { ...base, seed: 7, width: 24, wavelength: 90 }],
  ["extreme", { ...base, seed: 91, width: 90, wavelength: 45, spacingVariation: 1, heightVariation: 1, phrasing: 1 }],
];
let configurations = 0;
for (const [fixture, source] of fixtureEntries) {
  for (const [scale, options] of sweeps) {
    for (const maskLoops of [false, true]) {
      const label = `${fixture}/${scale}/${maskLoops ? "masked" : "open"}`;
      const result = R.generate(source, { ...options, maskLoops });
      assertFiniteResult(result, source, label, !maskLoops);
      assert.deepEqual(result, R.generate(source, { ...options, maskLoops }), `${label}: deterministic geometry`);
      configurations++;
    }
  }
}

console.log(`crest-check: profile controls, relations, endpoints, and ${configurations} fixture configurations passed`);

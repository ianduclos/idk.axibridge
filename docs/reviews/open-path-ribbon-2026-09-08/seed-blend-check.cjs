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
  wavelengthRight: 155,
  independentWavelengths: true,
  spacingVariation: 0.72,
  heightVariation: 0.68,
  phrasing: 0.65,
  steps: 4,
  taper: 0.12,
  seed: 7,
  seedB: 43,
};

const serial = value => JSON.stringify(value);
const geometryKeys = ["strands", "left", "right", "spine"];

function assertGeometryEqual(actual, expected, message) {
  for (const key of geometryKeys) assert.deepEqual(actual[key], expected[key], `${message}: ${key}`);
}

function assertFinite(result, source, message) {
  for (const key of geometryKeys) {
    const paths = key === "strands" ? result[key] : [result[key]];
    for (const path of paths) for (const point of path) {
      assert.equal(point.length, 2, `${message}: ${key} point shape`);
      assert.ok(point.every(Number.isFinite), `${message}: ${key} has finite coordinates`);
    }
  }
  for (const key of ["left", "right", "spine"]) {
    assert.deepEqual(result[key][0], source[0], `${message}: ${key} shares the start endpoint`);
    assert.deepEqual(result[key].at(-1), source.at(-1), `${message}: ${key} shares the end endpoint`);
  }
}

function assertNormalizedMix(actual, a, b, t, message, tolerance = 2e-12) {
  assert.equal(actual.length, a.length, `${message}: path count`);
  assert.equal(actual.length, b.length, `${message}: matching path count`);
  for (let i = 0; i < actual.length; i++) {
    assert.equal(actual[i].length, a[i].length, `${message}: point count at path ${i}`);
    assert.equal(actual[i].length, b[i].length, `${message}: matching point count at path ${i}`);
    const centre=R.fixtures.straight[0][1];
    const peak=path=>Math.max(...path.map(p=>Math.abs(p[1]-centre)));
    const raw=a[i].map((p,j)=>[p[0],p[1]+(b[i][j][1]-p[1])*t]);
    const target=peak(a[i])+(peak(b[i])-peak(a[i]))*t;
    const gain=peak(raw)>1e-12 ? target/peak(raw) : 1;
    assert.ok(Math.abs(peak(actual[i])-target)<2e-12,'blend retains interpolated peak amplitude');
    for (let j = 0; j < actual[i].length; j++) for (let axis = 0; axis < 2; axis++) {
      const mixed = a[i][j][axis] + (b[i][j][axis] - a[i][j][axis]) * t;
      const expected = axis===1 ? centre+(mixed-centre)*gain : mixed;
      assert.ok(Math.abs(actual[i][j][axis] - expected) <= tolerance,
        `${message}: path ${i}, point ${j}, axis ${axis}`);
    }
  }
}

// Seed blend endpoints retain the exact pre-blend geometries. seedB cannot
// affect endpoint A, and using the same seed at both ends is constant in t.
for (const relation of relations) {
  const options = { ...base, relation };
  const originalA = R.generate(R.fixtures.arch, { ...options, seedB: undefined });
  const endpointA = R.generate(R.fixtures.arch, { ...options, seedBlend: 0 });
  const endpointB = R.generate(R.fixtures.arch, { ...options, seedBlend: 1 });
  const originalB = R.generate(R.fixtures.arch, { ...options, seed: options.seedB, seedB: undefined });
  assertGeometryEqual(endpointA, originalA, `${relation}: blend endpoint A is exact`);
  assertGeometryEqual(endpointB, originalB, `${relation}: blend endpoint B is exact`);

  const otherSeedBAtZero = R.generate(R.fixtures.arch, { ...options, seedB: 999, seedBlend: 0 });
  assertGeometryEqual(otherSeedBAtZero, endpointA, `${relation}: seedB is irrelevant at zero`);

  const sameSeed = { ...options, seedB: options.seed };
  const sameReference = R.generate(R.fixtures.arch, { ...sameSeed, seedBlend: 0 });
  for (const seedBlend of [0.17, 0.5, 0.83, 1]) {
    assertGeometryEqual(R.generate(R.fixtures.arch, { ...sameSeed, seedBlend }), sameReference,
      `${relation}: identical seeds are constant at ${seedBlend}`);
  }
}

// A straight path has no nonlinear corner join. Its complete strand geometry
// therefore exposes the intended pointwise profile interpolation plus one uniform amplitude gain per side.
for (const relation of relations) {
  const options = { ...base, relation, maskLoops: false };
  const a = R.generate(R.fixtures.straight, { ...options, seedBlend: 0 });
  const b = R.generate(R.fixtures.straight, { ...options, seedBlend: 1 });
  for (const t of [0.001, 0.499, 0.5, 0.501, 0.999]) {
    const blended = R.generate(R.fixtures.straight, { ...options, seedBlend: t });
    assertNormalizedMix(blended.strands, a.strands, b.strands, t,
      `${relation}: straight blend is normalized profile interpolation at ${t}`);
  }
}

// The second wavelength is opt-in, affects only the right side, and each
// relation builds that side from the same seeded logic at its own wavelength.
for (const relation of relations) {
  const options = { ...base, relation, seedBlend: 0.5 };
  const shortRight = R.generate(R.fixtures.straight, options);
  const longRight = R.generate(R.fixtures.straight, { ...options, wavelengthRight: 220 });
  assert.deepEqual(shortRight.left, longRight.left, `${relation}: right wavelength leaves left fixed`);
  assert.notEqual(serial(shortRight.right), serial(longRight.right), `${relation}: right wavelength changes right`);

  const legacy = R.generate(R.fixtures.sCurve, { ...options, independentWavelengths: false });
  const ignored = R.generate(R.fixtures.sCurve, {
    ...options, independentWavelengths: false, wavelengthRight: 333,
  });
  const equalWaves = R.generate(R.fixtures.sCurve, {
    ...options, independentWavelengths: true, wavelengthRight: options.wavelength,
  });
  assertGeometryEqual(ignored, legacy, `${relation}: disabled right wavelength is ignored`);
  assertGeometryEqual(equalWaves, legacy, `${relation}: equal wavelengths preserve prior geometry`);
}

const mirrored = R.generate(R.fixtures.straight, { ...base, relation: "mirrored", seedBlend: 0.5 });
assert.notEqual(serial(mirrored.left), serial(mirrored.right),
  "mirrored relation with distinct wavelengths is independently sampled, not a literal reflection");
for (const relation of ["related", "independent"]) {
  const result = R.generate(R.fixtures.straight, { ...base, relation, seedBlend: 0.5 });
  assert.notEqual(serial(result.right), serial(mirrored.right),
    `${relation}: right-side seeded relation is applied after its wavelength profile is generated`);
}

// Keep the integration sweep bounded while covering joins, masking and
// reversed passage order for every study fixture.
let fixtureCount = 0;
for (const [name, source] of Object.entries(R.fixtures)) {
  const result = R.generate(source, {
    ...base,
    relation: relations[fixtureCount % relations.length],
    seedBlend: 0.5,
    maskLoops: true,
    reverseOrder: true,
    steps: 3,
  });
  assertFinite(result, source, name);
  fixtureCount++;
}

assert.equal(fixtureCount, 6, "all six study fixtures covered");
console.log("seed-blend-check: seed interpolation, independent wavelengths, and 6 masked fixtures passed");

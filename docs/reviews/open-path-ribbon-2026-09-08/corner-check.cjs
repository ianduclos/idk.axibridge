require('./load-join.cjs');
"use strict";

const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const vm = require("node:vm");

require("./geometry.js");
const current = globalThis.RibbonStudy;

function loadBaseline() {
  const source = execFileSync("git", [
    "show", "39af8e7:docs/reviews/open-path-ribbon-2026-09-08/geometry.js"
  ], { encoding: "utf8" });
  const context = { module: { exports: {} }, exports: {} };
  vm.createContext(context);
  vm.runInContext(source, context, { filename: "geometry.js@39af8e7" });
  return context.module.exports;
}

const baseline = loadBaseline();
const relations = ["related", "mirrored", "independent"];
const widths = [24, 45, 90];
const wavelengths = [90, 180];
const seeds = [7, 8];

function orient(a, b, c) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function properIntersection(a, b, c, d) {
  const eps = 1e-9;
  const abC = orient(a, b, c), abD = orient(a, b, d);
  const cdA = orient(c, d, a), cdB = orient(c, d, b);
  return ((abC > eps && abD < -eps) || (abC < -eps && abD > eps)) &&
    ((cdA > eps && cdB < -eps) || (cdA < -eps && cdB > eps));
}

// Count only crossings made by non-neighboring segments near a nominated source
// corner. This deliberately ignores remote folds such as the hairpin fixture.
function localCrossings(path, corner, radius) {
  const segments = [];
  for (let i = 0; i + 1 < path.length; i++) {
    const a = path[i], b = path[i + 1];
    const midpoint = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    if (Math.hypot(midpoint[0] - corner[0], midpoint[1] - corner[1]) <= radius) {
      segments.push({ i, a, b });
    }
  }
  let count = 0;
  for (let i = 0; i < segments.length; i++) {
    for (let j = i + 1; j < segments.length; j++) {
      const x = segments[i], y = segments[j];
      if (Math.abs(x.i - y.i) <= 1) continue;
      if (properIntersection(x.a, x.b, y.a, y.b)) count++;
    }
  }
  return count;
}

function localInterStrandCrossings(paths, corner, radius) {
  const localSegments = paths.map(path => {
    const segments = [];
    for (let i = 0; i + 1 < path.length; i++) {
      const a = path[i], b = path[i + 1];
      const midpoint = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      if (Math.hypot(midpoint[0] - corner[0], midpoint[1] - corner[1]) <= radius) {
        segments.push({ a, b });
      }
    }
    return segments;
  });
  let count = 0;
  for (let i = 0; i < localSegments.length; i++) {
    for (let j = i + 1; j < localSegments.length; j++) {
      for (const x of localSegments[i]) for (const y of localSegments[j]) {
        // properIntersection excludes touches at the common ribbon endpoints.
        if (properIntersection(x.a, x.b, y.a, y.b)) count++;
      }
    }
  }
  return count;
}

function assertCleanCorner(source, corner, label) {
  const failures = new Map();
  for (const width of widths) for (const wavelength of wavelengths) {
    for (const seed of seeds) for (const relation of relations) {
      const input = source.map(point => point.slice());
      const before = JSON.stringify(input);
      const result = current.generate(input, {
        width, wavelength, seed, relation, maskLoops: false
      });
      assert.equal(JSON.stringify(input), before, `${label}: source mutated`);
      for (const strand of result.strands) {
        assert.deepEqual(strand[0], input[0], `${label}: start moved`);
        assert.deepEqual(strand.at(-1), input.at(-1), `${label}: end moved`);
        const crossings = localCrossings(strand, corner, width * 2.5);
        if (crossings) {
          const key = JSON.stringify({ width, wavelength, seed, relation });
          const found = failures.get(key) || { strands: 0, crossings: 0 };
          found.strands++;
          found.crossings += crossings;
          failures.set(key, found);
        }
      }
      const interStrand = localInterStrandCrossings(result.strands, corner, width * 2.5);
      if (interStrand) {
        const key = JSON.stringify({ width, wavelength, seed, relation });
        const found = failures.get(key) || { strands: 0, crossings: 0 };
        found.interStrand = interStrand;
        failures.set(key, found);
      }
    }
  }
  const report = [...failures].map(([options, counts]) => ({ ...JSON.parse(options), ...counts }));
  if (process.env.CORNER_REPORT) console.log(label, JSON.stringify(report));
  return report;
}

const corner = current.fixtures.corner;
const loopFailures = [];
for (const [source, cornerPoint, label] of [
  [corner, [430, 142], "curved corner fixture"],
  [[[0, 0], [100, 0], [145, 95]], [100, 0], "two-segment V clockwise"],
  [[[0, 0], [100, 0], [145, -95]], [100, 0], "two-segment V counterclockwise"]
]) {
  const report = assertCleanCorner(source, cornerPoint, label);
  if (report.length) loopFailures.push({ label, report });
}

// The corner repair is intentionally narrow. All accepted non-corner studies
// remain byte-for-byte equivalent to the committed prototype baseline.
for (const fixtureName of ["straight", "arch", "sCurve", "hairpin"]) {
  for (const width of widths) for (const wavelength of wavelengths) {
    for (const seed of seeds) for (const relation of relations) {
      const options = { width, wavelength, seed, relation };
      assert.equal(
        JSON.stringify(current.generate(current.fixtures[fixtureName], options)),
        JSON.stringify(baseline.generate(baseline.fixtures[fixtureName], options)),
        `${fixtureName} changed from 39af8e7 (${JSON.stringify(options)})`
      );
    }
  }
}

assert.deepEqual(loopFailures, [], `local corner crossings: ${JSON.stringify(loopFailures)}`);

console.log("corner-check: corner crossings absent; endpoints, source purity, and baseline fixtures preserved");

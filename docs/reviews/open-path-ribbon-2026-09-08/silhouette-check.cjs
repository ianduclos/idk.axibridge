"use strict";

const assert = require("node:assert/strict");
require("./load-join.cjs");
require("./silhouette.js");
const S = globalThis.RibbonSilhouette;
const n = (p, s) => ({p, s});

function areaRing(ring) {
  let area = 0;
  for (let i = 0; i + 1 < ring.length; i++) area += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
  return area / 2;
}
function area(mp) {
  return mp.reduce((total, polygon) => total + polygon.reduce((sum, ring) => sum + areaRing(ring), 0), 0);
}
function valid(mp) {
  return mp.every(polygon => polygon.every(ring => ring.length >= 4 &&
    ring.every(p => p.length === 2 && p.every(Number.isFinite)) &&
    assert.deepEqual(ring[0], ring.at(-1)) === undefined));
}

const left = [n([0, 2], 0), n([10, 2], 10)];
const right = [n([0, -2], 0), n([10, -2], 10)];
const spine = [n([0, 0], 0), n([10, 0], 10)];
const before = JSON.stringify([left, right, spine]);
const rectangle = S.fromNodes(left, right, spine, {mergeOverlaps: true});
assert.ok(valid(rectangle));
assert.equal(Math.abs(area(rectangle)), 40);
assert.equal(JSON.stringify([left, right, spine]), before, "silhouette construction is pure");

const raw = S.fromNodes(left, right, spine, {mergeOverlaps: false});
assert.deepEqual(raw[0][0], [[0, 2], [10, 2], [10, -2], [0, -2], [0, 2]]);

const shifted = S.fromNodes(
  [n([5, 2], 0), n([15, 2], 10)], [n([5, -2], 0), n([15, -2], 10)],
  [n([5, 0], 0), n([15, 0], 10)], {mergeOverlaps: true});
const merged = S.union([rectangle, shifted]);
assert.equal(merged.length, 1);
assert.equal(Math.abs(area(merged)), 60, "overlap is solid and carries no seam");

// A closed annular sweep retains its central hole.
const loopSpine = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]].map((p, i) => n(p, i));
const loopLeft = [[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]].map((p, i) => n(p, i));
const loopRight = [[-2, -2], [12, -2], [12, 12], [-2, 12], [-2, -2]].map((p, i) => n(p, i));
const annulus = S.fromNodes(loopLeft, loopRight, loopSpine, {mergeOverlaps: true});
assert.ok(valid(annulus));
assert.equal(annulus.length, 1);
assert.equal(annulus[0].length, 2, "loop sweep preserves the hole");

const clipped = S.clipPaths([[[-5, 5], [15, 5]]], annulus);
assert.deepEqual(clipped, [
  [[-5, 5], [-2, 5]],
  [[2, 5], [8, 5]],
  [[12, 5], [15, 5]],
], "line is removed only in annular fill and remains inside the hole");

const alongBoundary = S.clipPaths([[[-5, -2], [15, -2]]], rectangle);
assert.deepEqual(alongBoundary, [
  [[-5, -2], [0, -2]],
  [[10, -2], [15, -2]],
], "a collinear polygon-boundary interval is blocked");

console.log("silhouette-check: closure, purity, overlap union, holes, and line clipping passed");

"use strict";

const assert = require("node:assert/strict");
require("./masking.js");
const { visibleIntervals } = globalThis.RibbonMask;

function close(actual, expected, message) {
  assert.equal(actual.length, expected.length, message);
  for (let i = 0; i < actual.length; i++) {
    assert.ok(Math.abs(actual[i][0] - expected[i][0]) < 1e-9, message);
    assert.ok(Math.abs(actual[i][1] - expected[i][1]) < 1e-9, message);
  }
}

const rect = [[3, -1], [7, -1], [7, 1], [3, 1]];
close(visibleIntervals([0, 0], [10, 0], [rect]), [[0, 0.3], [0.7, 1]], "rectangle crossing");
close(visibleIntervals([4, 0], [6, 0], [rect]), [], "fully inside");
close(visibleIntervals([0, 3], [10, 3], [rect]), [[0, 1]], "fully outside");

const overlap = [[5, -1], [9, -1], [9, 1], [5, 1]];
close(visibleIntervals([0, 0], [10, 0], [rect, overlap]), [[0, 0.3], [0.9, 1]], "blocker union");

const concave = [[2, -2], [8, -2], [8, 2], [6, 2], [6, 0], [4, 0], [4, 2], [2, 2]];
close(visibleIntervals([0, 1], [10, 1], [concave]), [[0, 0.2], [0.4, 0.6], [0.8, 1]], "concave polygon");

close(visibleIntervals([0, 1], [10, 1], [[[3, 1], [7, 1], [7, 3], [3, 3]]]), [[0, 0.3], [0.7, 1]], "collinear boundary blocked");
close(visibleIntervals([0, 0], [10, 0], [[[5, 0], [6, 1], [4, 1]]]), [[0, 1]], "single-point tangent remains drawable");

close(visibleIntervals([1, 1], [1, 1], [rect]), [[0, 1]], "visible zero-length segment");
close(visibleIntervals([4, 0], [4, 0], [rect]), [], "blocked zero-length segment");
assert.deepEqual(visibleIntervals([NaN, 0], [1, 1], [rect]), [], "invalid segment is safely empty");

console.log("masking-check: 10 assertion groups passed");

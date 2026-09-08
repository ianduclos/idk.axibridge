"use strict";

const { execFileSync } = require("node:child_process");

// Keep the sweep bounded even if a future geometry change introduces a loop.
if (!process.argv.includes("--worker")) {
  try {
    const output = execFileSync(process.execPath, [__filename, "--worker"], {
      encoding: "utf8",
      timeout: 240_000,
      maxBuffer: 8 * 1024 * 1024,
    });
    process.stdout.write(output);
  } catch (error) {
    if (error.code === "ETIMEDOUT" || error.signal === "SIGTERM") {
      console.error("stress-check: exceeded fixed 240 s timeout");
    } else {
      if (error.stdout) process.stdout.write(error.stdout);
      if (error.stderr) process.stderr.write(error.stderr);
      console.error(`stress-check: worker failed (${error.message})`);
    }
    process.exitCode = 1;
  }
  return;
}

require("./load-join.cjs");
require("./masking.js");
require("./geometry.js");

const RibbonStudy = globalThis.RibbonStudy;
const reverse = path => path.slice().reverse().map(point => point.slice());
const paths = [
  ...Object.entries(RibbonStudy.fixtures),
  ["short", [[0, 0], [0.25, 0.1]]],
  ["repeated-points", [[0, 0], [0, 0], [35, 0], [35, 0], [35, 22], [70, 22], [70, 22]]],
  ["zigzag", [[0, 0], [45, 35], [90, -30], [135, 40], [180, -35], [225, 20]]],
  ["near-180", [[0, 0], [100, 0], [0.1, 0.35], [115, 1.2]]],
  ["short-reversed", [[0.25, 0.1], [0, 0]]],
  ["zigzag-reversed", reverse([[0, 0], [45, 35], [90, -30], [135, 40], [180, -35], [225, 20]])],
  ["near-180-reversed", reverse([[0, 0], [100, 0], [0.1, 0.35], [115, 1.2]])],
];
const widths = [5, 24, 90];
const wavelengths = [45, 180, 240];
const seeds = [0, 7, 43];
const steps = [1, 10, 32];
const relations = ["related", "mirrored", "independent"];
const optionRows = [
  [5, 45, 0, 1, "related", false, false],
  [24, 180, 7, 10, "mirrored", false, false],
  [90, 240, 43, 32, "independent", false, false],
  [5, 180, 43, 32, "mirrored", true, false],
  [24, 240, 0, 1, "independent", true, true],
  [90, 45, 7, 10, "related", true, false],
  [5, 240, 7, 10, "independent", false, false],
  [24, 45, 43, 32, "related", false, false],
  [90, 180, 0, 1, "mirrored", false, false],
  [5, 45, 43, 10, "mirrored", true, true],
  [24, 180, 0, 32, "independent", false, false],
  [90, 240, 7, 1, "related", false, false],
];
const failures = [];
const timings = [];
let masked = 0;
let deterministic = 0;
let generatedPoints = 0;
let maxFragments = { count: 0 };

function finiteResult(result) {
  const finitePath = path => Array.isArray(path) && path.every(point =>
    Array.isArray(point) && point.length === 2 && point.every(Number.isFinite));
  return Array.isArray(result.strands) && result.strands.every(finitePath) &&
    [result.spine, result.left, result.right].every(finitePath);
}

function settings(pathName, round, pathIndex) {
  const [width, wavelength, seed, stepCount, relation, maskLoops, reverseOrder] =
    optionRows[(round + pathIndex) % optionRows.length];
  return {
    path: pathName,
    width,
    wavelength,
    seed,
    steps: stepCount,
    relation,
    maskLoops,
    reverseOrder,
  };
}

for (let pathIndex = 0; pathIndex < paths.length; pathIndex++) {
  const [pathName, source] = paths[pathIndex];
  for (let round = 0; round < 12; round++) {
    const config = settings(pathName, round, pathIndex);
    const options = { ...config };
    delete options.path;
    const input = source.map(point => point.slice());
    const before = JSON.stringify(input);
    const started = process.hrtime.bigint();
    try {
      const result = RibbonStudy.generate(input, options);
      const elapsedMs = Number(process.hrtime.bigint() - started) / 1e6;
      timings.push({ elapsedMs, config });
      if (JSON.stringify(input) !== before) throw new Error("input mutated");
      if (!finiteResult(result)) throw new Error("non-finite or malformed coordinates");
      if (!config.maskLoops) {
        for (const strand of result.strands) {
          if (JSON.stringify(strand[0]) !== JSON.stringify(source[0])) throw new Error("start endpoint moved");
          if (JSON.stringify(strand.at(-1)) !== JSON.stringify(source.at(-1))) throw new Error("end endpoint moved");
        }
      } else masked++;
      if ((round + pathIndex * 12) % 11 === 0) {
        const again = RibbonStudy.generate(input, options);
        deterministic++;
        if (JSON.stringify(result) !== JSON.stringify(again)) throw new Error("nondeterministic output");
      }
      const points = result.strands.reduce((sum, strand) => sum + strand.length, 0);
      generatedPoints += points;
      if (result.strands.length > maxFragments.count) maxFragments = { count: result.strands.length, config };
    } catch (error) {
      failures.push({ config, error: error.message });
    }
  }
}

timings.sort((a, b) => b.elapsedMs - a.elapsedMs);
const summary = {
  baseline: "6617aed",
  configurations: paths.length * 12,
  paths: paths.map(([name]) => name),
  masked,
  deterministic,
  generatedPoints,
  elapsedMs: +timings.reduce((sum, item) => sum + item.elapsedMs, 0).toFixed(3),
  slowest: timings.slice(0, 5).map(item => ({ ms: +item.elapsedMs.toFixed(3), ...item.config })),
  maxFragments,
  failures,
};
console.log(JSON.stringify(summary, null, 2));
if (failures.length) process.exitCode = 1;

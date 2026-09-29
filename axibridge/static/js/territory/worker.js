// Territory bench worker: runs the (generated) engine off the main thread.
// Jobs: {kind:'sheet', id, seed, dials} and {kind:'thumb', gen, seed, dials}.
// A newer sheet makes older sheets stale; a newer thumbnail generation makes
// older thumbnails stale. Strokes come back packed (flat Float32 + lengths).
import { runTerritory, randomSheet, polyLen } from './engine.js';

const BASE = { loose: 0.5, yieldP: 0.5, wander: 1, reach: 15, spread: 0.7, eps: 0.03, borders: true, outer: true,
  voids: true, interior: false, disregard: 0.15, hyst: 25, render: 'meander' };
const queue = [];
let latestSheet = 0, latestGen = 0, busy = false;

self.onmessage = e => {
  const job = e.data;
  if (job.kind === 'sheet') latestSheet = Math.max(latestSheet, job.id);
  if (job.kind === 'thumb') latestGen = Math.max(latestGen, job.gen);
  if (job.kind === 'cancel-thumbs') { latestGen = Math.max(latestGen, job.gen); return; }
  queue.push(job);
  if (!busy) { busy = true; setTimeout(pump, 0); }
};

function pump() {
  // sheets first: the stage is what the person is looking at
  queue.sort((a, b) => (a.kind === 'sheet' ? 0 : 1) - (b.kind === 'sheet' ? 0 : 1));
  const job = queue.shift();
  if (!job) { busy = false; return; }
  const stale = job.kind === 'sheet' ? job.id !== latestSheet : job.gen !== latestGen;
  if (!stale) {
    try {
      const sh = randomSheet(job.seed), t = performance.now();
      const res = runTerritory(sh.cores, { ...BASE, ...job.dials, camps: Math.max(2, sh.camps), ...(job.kind === 'thumb' ? { quality: 'thumb' } : {}) }, job.seed, 'reversed');
      const strokes = res.lines.flatMap(l => l.strokes).filter(s => s.length > 1);
      let n = 0, ink = 0; for (const s of strokes) { n += s.length; ink += polyLen(s); }
      const xy = new Float32Array(n * 2), lens = new Uint32Array(strokes.length); let k = 0;
      strokes.forEach((s, i) => { lens[i] = s.length; for (const p of s) { xy[k++] = p[0]; xy[k++] = p[1]; } });
      self.postMessage({ ...job, xy, lens, ink, ms: performance.now() - t }, [xy.buffer, lens.buffer]);
    } catch (error) {
      self.postMessage({ ...job, error: String(error?.message || error) });
    }
  }
  setTimeout(pump, 0);
}

// node smoke_meander.js [seeds…] — determinism, timing and recipe metrics for render:'meander'.
const E = require('./territory-engine.js');
const base = { loose: 0.5, yieldP: 0.5, wander: 1, reach: 15, spread: 0.7, eps: 0.03, borders: true, outer: true, voids: false, interior: false, disregard: 0.15, hyst: 25, render: 'meander' };
const r3 = process.argv.includes('--r3'), seeds = process.argv.slice(2).filter(a => a !== '--r3').map(Number); if (!seeds.length) seeds.push(3, 13, 21, 7, 34, 58);
const run = s => { const sh = E.randomSheet(s); return E.runTerritory(sh.cores, { ...base, voids: r3 || base.voids, camps: Math.max(2, sh.camps), ...(r3 ? E.MEANDER_MACROS : {}) }, s, 'reversed'); };
let total = 0;
for (const s of seeds) {
  const t0 = process.hrtime.bigint(), a = run(s), ms = Number(process.hrtime.bigint() - t0) / 1e6; total += ms;
  const b = run(s), same = JSON.stringify(a.lines) === JSON.stringify(b.lines);
  const m = a.meander;
  console.log(`seed ${s}: ${ms.toFixed(0)} ms, deterministic=${same}, ink ${m.inkMm} mm, flags '${m.flags}', dead ${m.deadFrac}, contrast ${m.contrast}, empty ${m.empty}, white ${m.white}, rings ${m.ringsDropped}`);
  if (r3) console.log(`   r3: chaosShare ${m.chaosShare} · accents ${m.accents.length} · bridges ${m.bridges.map(b => b.kind + b.mm + (b.echoes ? 'e' + b.echoes : '')).join(',') || '-'} (ink ${m.bridgeInk}) · trunks ${m.channels.filter(c => c.cls === 'trunk').length}`);
  console.log('   events', m.events.map(e => e.kind + '@' + e.t + '/c' + e.ch).join(' '), '| channels', m.channels.map(c => `${c.cls[0]}${c.id}:${c.len}mm t${c.tDraw}${c.abandoned ? 'A' : ''}${c.drawn ? '' : '(undrawn)'}`).join(' '), '| ratios', m.ratios.map(r => r.ratio).join(','));
}
console.log(`mean ${(total / seeds.length).toFixed(0)} ms per sheet`);

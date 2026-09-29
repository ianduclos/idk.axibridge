// node close.js config.json out.html ID:x,y,w,h [ID:x,y,w,h …] — close views (mm windows) of cells.
// Rendered at 6 px/mm with the pen at its plotted 0.4 mm, so gaps read as on paper.
const fs = require('fs'); const E = require('./territory-engine.js');
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
let figs = '';
for (const spec of process.argv.slice(4)) {
  const [id, box] = spec.split(':'), [x, y, w, h] = box.split(',').map(Number), c = cfg.cells.find(q => q.id === id);
  const prm = { ...cfg.prm, ...(c.prm || {}) };
  let cores; if (c.random) { const sh = E.randomSheet(c.random); cores = sh.cores; if (!c.prm || c.prm.camps === undefined) prm.camps = Math.max(2, sh.camps); } else cores = E.exampleSheet();
  const res = E.runTerritory(cores, prm, c.seed || c.random || 1, c.order || 'drawn');
  const paths = res.lines.flatMap(l => l.strokes).map(st => `<path d="M${st.map(p => p[0].toFixed(2) + ' ' + p[1].toFixed(2)).join(' L')}"/>`).join('');
  figs += `<figure><svg viewBox="${x} ${y} ${w} ${h}" width="${w * 6}" height="${h * 6}"><rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#FFFCF0"/><g fill="none" stroke="#100F0F" stroke-width="0.4" stroke-linecap="round" stroke-linejoin="round">${paths}</g></svg><figcaption>${esc(id)} · close ${w}×${h} mm</figcaption></figure>`;
}
fs.writeFileSync(process.argv[3], `<!doctype html><meta charset="utf-8"><style>body{margin:0;padding:14px;background:#fff;font:13px ui-monospace,Menlo,monospace}figure{margin:0 0 14px;display:inline-block;vertical-align:top;margin-right:14px}svg{display:block;border:1px solid #CECDC3}</style>${figs}`);

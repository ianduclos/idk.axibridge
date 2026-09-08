"""Matched probes: sampling density versus tangent continuity in the loop."""
from pathlib import Path
import subprocess
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1200,'height':900},device_scale_factor=1)
    page.set_content('<body style="margin:0;background:#FFFCF0;color:#100F0F;font:14px monospace"><main id="sheet" style="padding:20px;display:grid;grid-template-columns:repeat(3,1fr);gap:16px"></main></body>')
    baseline=subprocess.check_output(['git','show','6617aed:docs/reviews/open-path-ribbon-2026-09-08/geometry.js'],text=True)
    page.add_script_tag(content=baseline)
    page.evaluate('window.BeforeLoop=RibbonStudy')
    for name in ['vendor/polygon-clipping-0.15.7.js','corner-envelope.js','masking.js','geometry.js']:
        page.add_script_tag(content=(HERE/name).read_text())
    summary=page.evaluate('''() => {
      const cubic=(a,b,c,d,n)=>Array.from({length:n+1},(_,i)=>{const t=i/n,u=1-t;return [0,1].map(k=>u*u*u*a[k]+3*u*u*t*b[k]+3*u*t*t*c[k]+t*t*t*d[k]);});
      const fixture=(scale,continuous)=>[].concat(
        cubic([60,180],[220,155],[440,55],[620,40],100*scale),
        cubic([620,40],continuous?[740,30]:[730,30],continuous?[740,202]:[740,215],[620,190],65*scale).slice(1),
        cubic([620,190],[470,175],[200,70],[60,50],100*scale).slice(1));
      const variants=[['Original',BeforeLoop.fixtures.loop],['Denser sampling only',fixture(4,false)],['Corrected loop sample',RibbonStudy.fixtures.loop]];
      const path=p=>p.map((q,i)=>(i?'L':'M')+q.join(' ')).join(' ');
      const summaries=[];
      for(const width of [24,60])for(const [label,points] of variants){
        const r=RibbonStudy.generate(points,{width,wavelength:180,variation:.75,steps:10,seed:7,relation:'related'});
        const id='B'+(summaries.length+1);
        document.getElementById('sheet').insertAdjacentHTML('beforeend',`<section><div>${id} · ${label} · ${width}</div><svg viewBox="555 0 190 240" style="width:100%;height:340px"><g fill="none" stroke="#100F0F" stroke-width=".6">${r.strands.map(p=>`<path d="${path(p)}"/>`).join('')}</g></svg></section>`);
        summaries.push({id,label,width,sourcePoints:points.length});
      }
      return summaries;
    }''')
    page.locator('#sheet').screenshot(path=str(HERE/'loop-bend-probes.png'))
    browser.close()
print(summary)

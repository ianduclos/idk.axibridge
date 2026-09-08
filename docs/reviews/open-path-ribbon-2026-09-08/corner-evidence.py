"""Capture matching corner joins and loop order, using the committed baseline."""
from pathlib import Path
import subprocess
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
BASE='39af8e7'
REL='docs/reviews/open-path-ribbon-2026-09-08/geometry.js'
baseline=subprocess.check_output(['git','show',BASE+':'+REL],text=True)
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1200,'height':1000},device_scale_factor=1)
    page.set_content('<body style="margin:0;background:#FFFCF0;color:#100F0F;font:14px monospace"><main id="sheet"></main></body>')
    page.add_script_tag(content=baseline)
    page.evaluate('window.BeforeCorner=RibbonStudy')
    page.add_script_tag(content=(HERE/'vendor/polygon-clipping-0.15.7.js').read_text())
    page.add_script_tag(content=(HERE/'corner-envelope.js').read_text())
    page.add_script_tag(content=(HERE/'masking.js').read_text())
    page.add_script_tag(content=(HERE/'geometry.js').read_text())
    page.evaluate('''() => {
      const path=ps=>ps.map((p,i)=>(i?'L':'M')+p.join(' ')).join(' ');
      window.renderCases=(cases,box,height)=>{
        const sheet=document.getElementById('sheet');
        sheet.style='display:grid;grid-template-columns:repeat(2,1fr);gap:16px;padding:20px';
        sheet.innerHTML='';
        cases.forEach(c=>{
          const engine=c.before?BeforeCorner:RibbonStudy;
          const result=engine.generate(engine.fixtures[c.shape||'corner'],{seed:7,width:c.width||32,wavelength:180,variation:.75,steps:c.steps||10,maskLoops:!!c.mask,reverseOrder:!!c.reverse});
          sheet.insertAdjacentHTML('beforeend',`<section id="${c.id}"><div>${c.id} · ${c.label}</div><svg viewBox="${box}" style="width:100%;height:${height}px;background:#FFFCF0"><g fill="none" stroke="#100F0F" stroke-width=".65" stroke-linejoin="round">${result.strands.map(p=>`<path d="${path(p)}"/>`).join('')}</g></svg></section>`);
        });
      };
      renderCases([
        {id:'J1',label:'Before · 3 strands',before:true,steps:1},
        {id:'J2',label:'Joined · 3 strands',steps:1},
        {id:'J3',label:'Before · 21 strands',before:true},
        {id:'J4',label:'Joined · 21 strands'},
        {id:'J5',label:'Before · wide',before:true,width:75},
        {id:'J6',label:'Joined · wide',width:75}
      ],'360 55 145 125',220);
    }''')
    page.locator('#sheet').screenshot(path=str(HERE/'corner-comparison.png'))
    page.evaluate('''() => renderCases([
      {id:'L1',label:'Transparent',shape:'loop',width:42},
      {id:'L2',label:'Later passage on top',shape:'loop',width:42,mask:true},
      {id:'L3',label:'Earlier passage on top',shape:'loop',width:42,mask:true,reverse:true},
      {id:'L4',label:'Later passage on top · sparse',shape:'loop',width:42,mask:true,steps:3}
    ],'35 0 700 235',230)''')
    page.locator('#sheet').screenshot(path=str(HERE/'loop-comparison.png'))
    for id in ['L2','L3']:
        page.locator('#'+id+' svg').evaluate('(e)=>{e.setAttribute("viewBox","240 70 225 90");e.style.height="260px";}')
        page.locator('#'+id).screenshot(path=str(HERE/(id+'-close.png')))
    browser.close()
print('Captured matched corner joins and both loop orders.')

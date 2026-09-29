#!/bin/sh
# Rebuild the engine and the single-file page (see README).
cd "$(dirname "$0")"
cat t_head.js t_flood.js t_body.js t_hand.js t_forms.js t_graph.js t_v5.js t_meander.js > territory-engine.js
python3 -c "p=open('territory-page.html').read(); e=open('territory-engine.js').read(); open('territory.html','w').write(p.replace('/*ENGINE*/',e))"

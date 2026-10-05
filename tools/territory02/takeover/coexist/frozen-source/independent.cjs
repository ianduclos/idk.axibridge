// Coexistence through shared space; the rough drawing stays byte-identical.
function develop({base,smooth}){return {strokes:base.strokes.concat(smooth.map(s=>s.P)),events:smooth.map(s=>({kind:'independent-passage',sourceIndex:s.sourceIndex,at:s.P[Math.floor(s.P.length/2)],roughAltered:false})),info:{unchangedRough:true,passages:smooth.length}};}
module.exports={develop};

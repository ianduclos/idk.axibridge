(function(root){
  'use strict';
  const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
  function projection(p,a,b) {
    const dx=b[0]-a[0],dy=b[1]-a[1];
    const t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy||1)));
    return {t,d:Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)};
  }
  function area(a,b,c){return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);}
  function envelope(nodes,spine,stations,corners,width) {
    if(!corners.length)return nodes;
    if(!root.polygonClipping)throw Error('Corner polygon helper missing');
    const patches=[];
    for(let k=0;k<corners.length;k++) {
      const c=corners[k],reach=width*Math.min(4,Math.abs(Math.tan(c.turn/2)))*2+12;
      const lo=Math.max(c.s-reach,k?(corners[k-1].s+c.s)/2:0);
      const hi=Math.min(c.s+reach,k+1<corners.length?(corners[k+1].s+c.s)/2:stations.at(-1));
      let start=0,end=stations.length-1;
      while(start+1<stations.length && stations[start+1]<lo)start++;
      while(end>0 && stations[end-1]>hi)end--;
      const source=[],offset=[],ss=[];
      for(let i=start;i<=end;i++) {
        if(stations[i]===c.s && i>0 && i<spine.length-1) {
          const a=spine[i-1],b=spine[i],dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy);
          const nx=-dy/len,ny=dx/len;
          const w=(nodes[i].p[0]-b[0])*nx+(nodes[i].p[1]-b[1])*ny;
          const angle=Math.atan2(ny,nx),n=Math.max(4,Math.ceil(Math.abs(c.turn)/.055));
          for(let j=0;j<=n;j++) {
            source.push(b);offset.push([b[0]+w*Math.cos(angle+c.turn*j/n),b[1]+w*Math.sin(angle+c.turn*j/n)]);ss.push(c.s);
          }
        } else {source.push(spine[i]);offset.push(nodes[i].p);ss.push(stations[i]);}
      }
      const triangles=[];
      for(let i=0;i<source.length-1;i++) {
        for(const t of [[source[i],source[i+1],offset[i+1]],[source[i],offset[i+1],offset[i]]])
          if(Math.abs(area(...t))>1e-10)triangles.push([t]);
      }
      if(!triangles.length)continue;
      const union=root.polygonClipping.union(...triangles);
      let chosen=null;
      for(const polygon of union) {
        const ring=polygon[0].slice(0,-1);
        const a=ring.findIndex(p=>distance(p,offset[0])<1e-7);
        const b=ring.findIndex(p=>distance(p,offset.at(-1))<1e-7);
        if(a<0||b<0)continue;
        function route(step) {
          const out=[];let i=a;
          while(i!==b){out.push(ring[i]);i=(i+step+ring.length)%ring.length;}
          return out.concat([ring[b]]);
        }
        const first=route(1),second=route(-1);
        const score=path=>path.reduce((total,p)=>total+Math.min(...source.slice(1).map((q,i)=>projection(p,source[i],q).d)),0);
        chosen=score(first)>score(second)?first:second;break;
      }
      if(!chosen)continue; // complex topology: retain rather than invent a join
      let previous=stations[start];
      const path=chosen.map((p,index)=>{
        if(index===0)return {p:nodes[start].p,s:stations[start]};
        if(index===chosen.length-1)return {p:nodes[end].p,s:stations[end]};
        let closest={d:Infinity,s:previous};
        for(let j=0;j<offset.length-1;j++) {
          const hit=projection(p,offset[j],offset[j+1]);
          if(hit.d<closest.d)closest={d:hit.d,s:ss[j]+hit.t*(ss[j+1]-ss[j])};
        }
        previous=Math.max(previous,closest.s);
        return {p,s:previous};
      });
      patches.push({start,end,path});
    }
    let result=[],cursor=0;
    for(const patch of patches){result.push(...nodes.slice(cursor,patch.start),...patch.path);cursor=patch.end+1;}
    return result.concat(nodes.slice(cursor));
  }
  root.RibbonJoin={envelope};
})(globalThis);

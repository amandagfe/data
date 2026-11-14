/* Data Detectives: tendências, El Niño e previsão de deslizamentos com dados da NASA e da NOAA.
   As séries meteorológicas vêm da API NASA POWER no momento da consulta. Textos em i18n.js (pt, en, es). */
(async function(){
'use strict';
const $ = s => document.querySelector(s);
const store = {get(k,d){try{const v=localStorage.getItem(k);return v?JSON.parse(v):d}catch(e){return d}}, set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ================= idioma ================= */
const LANGS=['pt','en','es'];
let lang = store.get('dd-lang', null) || (LANGS.find(l=>(navigator.language||'').toLowerCase().startsWith(l)) || 'pt');
let L = I18N.str[lang];
const fmt = n => n.toLocaleString(L.locale);
const nf = (v,d) => v.toLocaleString(L.locale,{minimumFractionDigits:d,maximumFractionDigits:d});
const sgn = (v,d) => { const r=+v.toFixed(d); return (r>0?'+':r<0?'−':'')+nf(Math.abs(r),d); };
const dFmt = s => new Date(Date.UTC(+s.slice(0,4),+s.slice(4,6)-1,+s.slice(6,8))).toLocaleDateString(L.locale,{day:'2-digit',month:'2-digit',year:'numeric',timeZone:'UTC'});
const dShort = s => new Date(Date.UTC(+s.slice(0,4),+s.slice(4,6)-1,+s.slice(6,8))).toLocaleDateString(L.locale,{day:'2-digit',month:'2-digit',timeZone:'UTC'});
const isoFmt = s => dFmt(s.replace(/-/g,''));
const PT_HTML = new Map(), PT_PH = new Map();
document.querySelectorAll('[data-i18n]').forEach(el=>PT_HTML.set(el, el.innerHTML));
document.querySelectorAll('[data-i18n-ph]').forEach(el=>PT_PH.set(el, el.placeholder));
function renderTex(root=document){
  if(!window.katex) return;
  root.querySelectorAll('.tex').forEach(el=>{ if(!el.querySelector('.katex')) try{ katex.render(el.textContent, el, {throwOnError:false}); }catch(e){} });
}
function applyStatic(){
  document.documentElement.lang = {pt:'pt-BR',en:'en',es:'es'}[lang];
  PT_HTML.forEach((pt,el)=>{ el.innerHTML = lang==='pt' ? pt : (I18N.html[lang][el.dataset.i18n] ?? pt); });
  PT_PH.forEach((pt,el)=>{ el.placeholder = lang==='pt' ? pt : (I18N.html[lang][el.dataset.i18nPh] ?? pt); });
  document.querySelectorAll('.lang button').forEach(b=>b.setAttribute('aria-pressed', b.dataset.lang===lang));
  renderTex();
}

const [CAT, MOD, ENSO] = await Promise.all(['catalog','models','enso'].map(n=>fetch(`data/${n}.json`).then(r=>r.json())));

/* ================= catálogo ================= */
const TRIG = CAT.trig;
const PT = CAT.pts.map(p => ({lat:p[0], lng:p[1], year:p[2], month:p[3], fat:p[4], trig:TRIG[p[5]], cty:CAT.ctys[p[6]], day:p[7]||0}));
const rainSet = ['downpour','rain','continuous_rain','monsoon','tropical_cyclone'];
const total = PT.length, deaths = PT.reduce((s,p)=>s+p.fat,0), rainN = PT.filter(p=>rainSet.includes(p.trig)).length;
const nCountries = CAT.ctys.filter(Boolean).length;
const trigName = t => L.trig[t] || t.replace(/_/g,' ');

/* ================= ENSO (NOAA ONI) ================= */
const SEAS = ['DJF','JFM','FMA','MAM','AMJ','MJJ','JJA','JAS','ASO','SON','OND','NDJ'];
const C = {nino:'#f55d5d', nina:'#4f9fd1', neutro:'#9fc2bf', ninoInk:'#c63d3d', ninaInk:'#2a7bb0'};
const ONI = new Map(); ENSO.oni.forEach(([y,m,v])=>ONI.set(y*12+m-1, v));
const oniKeys = [...ONI.keys()].sort((a,b)=>a-b);
const PHASE = new Map();   // regra da NOAA: pelo menos 5 estações seguidas além de ±0,5 °C
(function(){
  let run=[], sign=0;
  const flush=()=>{ if(run.length>=5) run.forEach(k=>PHASE.set(k, sign>0?'nino':'nina')); run=[]; };
  oniKeys.forEach(k=>{ const v=ONI.get(k), s=v>=0.5?1:v<=-0.5?-1:0;
    if(s!==0 && s===sign && run.length && run[run.length-1]===k-1) run.push(k); else { flush(); sign=s; if(s!==0) run=[k]; }
    if(!PHASE.has(k)) PHASE.set(k,'neutro'); });
  flush();
})();
const phaseOf = k => PHASE.get(k) || null;
const lastK = oniKeys[oniKeys.length-1], lastOni = ONI.get(lastK);
const lastSeas = `${SEAS[lastK%12]} ${Math.floor(lastK/12)}`;
const curPhase = phaseOf(lastK)==='neutro' ? (lastOni>=0.5?'nino':lastOni<=-0.5?'nina':'neutro') : phaseOf(lastK);
const strengthKey = v => { const a=Math.abs(v); return a>=2?'vs':a>=1.5?'s':a>=1?'m':'w'; };
const PHN = ph => L.phase[ph];
const curTxt = () => curPhase==='neutro' ? L.neutral : L.phaseStr(PHN(curPhase), L.strength[strengthKey(lastOni)]);
const annualPhase = y => { let s=0,n=0; for(let m=0;m<12;m++){const v=ONI.get(y*12+m); if(v!=null){s+=v;n++;}} if(n<6) return null; const a=s/n; return a>=0.5?'nino':a<=-0.5?'nina':'neutro'; };

/* ================= estatística ================= */
function erf(x){const t=1/(1+.3275911*Math.abs(x));const y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-.284496736)*t+.254829592)*t*Math.exp(-x*x);return x>=0?y:-y}
const Phi = z => .5*(1+erf(z/Math.SQRT2));
function gammaln(x){const c=[76.18009172947146,-86.50532032941677,24.01409824083091,-1.231739572450155,0.1208650973866179e-2,-0.5395239384953e-5];let y=x,t=x+5.5;t-=(x+.5)*Math.log(t);let s=1.000000000190015;for(const ci of c)s+=ci/++y;return -t+Math.log(2.5066282746310005*s/x);}
function betacf(a,b,x){let qab=a+b,qap=a+1,qam=a-1,c=1,d=1-qab*x/qap;if(Math.abs(d)<1e-30)d=1e-30;d=1/d;let h=d;
  for(let m=1;m<=200;m++){const m2=2*m;let aa=m*(b-m)*x/((qam+m2)*(a+m2));d=1+aa*d;if(Math.abs(d)<1e-30)d=1e-30;c=1+aa/c;if(Math.abs(c)<1e-30)c=1e-30;d=1/d;h*=d*c;
    aa=-(a+m)*(qab+m)*x/((a+m2)*(qap+m2));d=1+aa*d;if(Math.abs(d)<1e-30)d=1e-30;c=1+aa/c;if(Math.abs(c)<1e-30)c=1e-30;d=1/d;const del=d*c;h*=del;if(Math.abs(del-1)<3e-7)break;}return h;}
function betai(a,b,x){if(x<=0)return 0;if(x>=1)return 1;const bt=Math.exp(gammaln(a+b)-gammaln(a)-gammaln(b)+a*Math.log(x)+b*Math.log(1-x));return x<(a+1)/(a+b+2)?bt*betacf(a,b,x)/a:1-bt*betacf(b,a,1-x)/b;}
const tPval = (t,df) => betai(df/2, .5, df/(df+t*t));   // bicaudal
function tcrit(df){ let lo=0,hi=50; for(let i=0;i<60;i++){const m=(lo+hi)/2; tPval(m,df)>0.05?lo=m:hi=m;} return (lo+hi)/2; }
const mean = a => a.reduce((s,v)=>s+v,0)/a.length;
const sd = a => { const m=mean(a); return Math.sqrt(a.reduce((s,v)=>s+(v-m)**2,0)/(a.length-1)); };
function welch(a,b){ if(a.length<3||b.length<3) return {p:NaN,d:NaN}; const va=sd(a)**2/a.length, vb=sd(b)**2/b.length, t=(mean(a)-mean(b))/Math.sqrt(va+vb), df=(va+vb)**2/(va*va/(a.length-1)+vb*vb/(b.length-1)); return {t,df,p:tPval(t,df),d:mean(a)-mean(b)}; }
function lag1(a){ const m=mean(a); let n=0,d=0; for(let i=0;i<a.length;i++){d+=(a[i]-m)**2; if(i) n+=(a[i]-m)*(a[i-1]-m);} return n/d; }
function pearson(x,y){ const mx=mean(x),my=mean(y); let sxy=0,sxx=0,syy=0; for(let i=0;i<x.length;i++){sxy+=(x[i]-mx)*(y[i]-my);sxx+=(x[i]-mx)**2;syy+=(y[i]-my)**2;} return sxy/Math.sqrt(sxx*syy); }
function trendStats(x, y){
  const n=x.length, mx=mean(x), my=mean(y);
  let sxx=0,sxy=0; for(let i=0;i<n;i++){sxx+=(x[i]-mx)**2;sxy+=(x[i]-mx)*(y[i]-my)}
  const b=sxy/sxx, a=my-b*mx; let sse=0; for(let i=0;i<n;i++) sse+=(y[i]-a-b*x[i])**2;
  const se=Math.sqrt(sse/(n-2)), seb=se/Math.sqrt(sxx), tc=tcrit(n-2);
  let S=0; const sl=[], ties={};
  for(let i=0;i<n-1;i++) for(let j=i+1;j<n;j++){S+=Math.sign(y[j]-y[i]); sl.push((y[j]-y[i])/(x[j]-x[i]));}
  y.forEach(v=>ties[v]=(ties[v]||0)+1);
  sl.sort((p,q)=>p-q); const m=sl.length, sen = m%2? sl[(m-1)/2] : (sl[m/2-1]+sl[m/2])/2;
  let vs=n*(n-1)*(2*n+5); Object.values(ties).forEach(t=>{if(t>1) vs-=t*(t-1)*(2*t+5)}); vs/=18;
  const Z = S>0?(S-1)/Math.sqrt(vs):S<0?(S+1)/Math.sqrt(vs):0, p=2*(1-Phi(Math.abs(Z)));
  return {a,b,ci:[b-tc*seb,b+tc*seb],tc,se,sxx,mx,n,S,Z,p,sen};
}
function niceTicks(lo,hi,k=4){const span=hi-lo||1, step0=span/k, mag=10**Math.floor(Math.log10(step0)), st=[1,2,2.5,5,10].map(m=>m*mag).find(s=>s>=step0); const out=[]; for(let v=Math.ceil(lo/st)*st; v<=hi+1e-9; v+=st) out.push(+v.toFixed(10)); return out;}
const sortNum = a => Float64Array.from(a).sort();
function ub(s,v){let lo=0,hi=s.length;while(lo<hi){const m=(lo+hi)>>1; if(s[m]<=v) lo=m+1; else hi=m;}return lo;}
const pct = (s,v) => ub(s,v)/s.length;
const quant = (s,q) => s[Math.floor(q*(s.length-1))];
const pTxt = p => Number.isNaN(p)?'–':p<0.001?'p < '+nf(0.001,3):'p = '+nf(p,3);

/* ================= modelos ================= */
const G = MOD.grid, CELL = new Map();
G.cells.forEach(r=>{ const pm=r.slice(2).map(v=>v/1000); const p2=1-pm.reduce((a,v)=>a*(1-v),1); CELL.set(r[0]+','+r[1], {lat:r[0]+.5, lng:r[1]+.5, pm, p2}); });
const P2 = sortNum([...CELL.values()].map(c=>c.p2));
const TH = {mod:quant(P2,.60), alto:quant(P2,.85), muito:quant(P2,.95)};
const CLS = {muito:{key:'muito',c:'#f55d5d',t:'#fff'}, alto:{key:'alto',c:'#f58b5d',t:'#1a0d08'}, mod:{key:'mod',c:'#f2c38b',t:'#2a1a08'}, baixo:{key:'baixo',c:'#2f7a77',t:'#eaf6f4'}, nd:{key:'nd',c:'rgba(234,246,244,.12)',t:'#9fc2bf'},
  elev:{key:'elev',c:'#f2c38b',t:'#2a1a08'}, normal:{key:'normal',c:'#2f7a77',t:'#eaf6f4'}};
const clsName = cl => L.cls[cl.key];
const structClass = p => p>=TH.muito?CLS.muito : p>=TH.alto?CLS.alto : p>=TH.mod?CLS.mod : CLS.baixo;
function nearestCell(lat,lng){
  const a=Math.floor(lat), b=Math.floor(lng); let best=CELL.get(a+','+b);
  if(!best) for(let da=-1;da<=1;da++) for(let db=-1;db<=1;db++){const c=CELL.get((a+da)+','+(b+db)); if(c&&(!best||c.p2>best.p2)) best=c;}
  return best;
}
const TM = MOD.trig;
function predictTrig(x){
  let raw = TM.base;
  for(const t of TM.trees){ let i=0; while(!t.leaf[i]){ const v=x[t.f[i]]; i = (Number.isNaN(v) ? t.ml[i] : v<=t.th[i]) ? t.l[i] : t.r[i]; } raw += t.v[i]; }
  return 1/(1+Math.exp(-raw));
}
const trigClass = s => s>=TM.thr.muito?CLS.muito : s>=TM.thr.alto?CLS.alto : s>=TM.thr.elev?CLS.elev : CLS.normal;
const slopeClass = s => s>=30?{k:L.slope.vs,c:CLS.muito.c,t:CLS.muito.t}: s>=15?{k:L.slope.s,c:CLS.alto.c,t:CLS.alto.t}: s>=5?{k:L.slope.m,c:'#f2c38b',t:'#2a1a08'}:{k:L.slope.f,c:'#2f7a77',t:'#eaf6f4'};
function badge(el, cl, label){ el.textContent=label||cl.k||clsName(cl); el.style.background=cl.c; el.style.color=cl.t; }

/* ================= cabeçalho e resumo ================= */
function renderHeroAbstract(){
  $('#hero-stats').innerHTML = [[L.hs[0],fmt(total)],[L.hs[1],fmt(deaths)],[L.hs[2],Math.round(rainN/total*100)+'%'],[L.hs[3],`${sgn(lastOni,2)} °C`]]
    .map(([a,b])=>`<div><dt>${a}</dt><dd>${b}</dd></div>`).join('');
  const o={rain:Math.round(rainN/total*100), total:fmt(total), auc1:nf(TM.metrics.auc,2), auc2:nf(G.metrics.auc,2), cur:curTxt(), oni:sgn(lastOni,2), seas:lastSeas,
    ctys:fmt(nCountries), cases:fmt(TM.metrics.cases), places:fmt(TM.metrics.places), base1:nf(TM.metrics.base_auc,2), base2:nf(G.metrics.base_auc,2)};
  $('#abs-p').innerHTML = L.abs(o);
  $('#abs-nums').innerHTML = L.absn(o).map(([a,b,c])=>`<div><dt>${b}</dt><dd>${a}<small>${c}</small></dd></div>`).join('');
}

/* ================= globo ================= */
const land = topojson.feature(CAT.land, CAT.land.objects.countries).features.filter(f=>f.properties.name!=='Antarctica');
function unwrap(ring){let off=0,prev=null;return ring.map(([lng,lat])=>{let x=lng+off;if(prev!==null){if(x-prev>180){off-=360;x-=360;}else if(x-prev<-180){off+=360;x+=360;}}prev=x;return [x,lat];});}
const TW=2048, THt=1024, DOT=9;
const MASK = (function(){
  const m=document.createElement('canvas'); m.width=TW; m.height=THt; const mc=m.getContext('2d'); mc.fillStyle='#000';
  const P=([lng,lat])=>[(lng+180)/360*TW,(90-lat)/180*THt];
  // Rússia e Fiji cruzam a longitude 180°: desenha cada contorno com longitudes contínuas e repete deslocado em ±360°
  land.forEach(f=>{const g=f.geometry; if(!g) return; const polys=g.type==='Polygon'?[g.coordinates]:g.coordinates;
    mc.beginPath(); polys.forEach(poly=>poly.forEach(ring=>{const u=unwrap(ring); [-360,0,360].forEach(k=>u.forEach((pt,i)=>{const [x,y]=P([pt[0]+k,pt[1]]); i?mc.lineTo(x,y):mc.moveTo(x,y);}));})); mc.fill('evenodd');});
  return mc.getImageData(0,0,TW,THt).data;
})();
const texCanvas=document.createElement('canvas'); texCanvas.width=TW; texCanvas.height=THt;
function paintTexture(colorAt){
  const oc=texCanvas.getContext('2d');
  const gr=oc.createLinearGradient(0,0,0,THt); gr.addColorStop(0,'#0a4d4b'); gr.addColorStop(.5,'#06403f'); gr.addColorStop(1,'#0a4d4b');
  oc.fillStyle=gr; oc.fillRect(0,0,TW,THt);
  for(let y=DOT/2;y<THt;y+=DOT){const latD=90-y/THt*180, sx=DOT/Math.max(.12,Math.cos(latD*Math.PI/180));
    for(let x=sx/2;x<TW;x+=sx){ if(MASK[((y|0)*TW+(x|0))*4+3]>0){ oc.fillStyle=colorAt(latD, x/TW*360-180); oc.beginPath(); oc.arc(x,y,2.4,0,6.2832); oc.fill(); } }}
  return texCanvas.toDataURL('image/png');
}
// mapa de cores "inferno" (matplotlib), perceptualmente uniforme
const INF=['#000004','#160b39','#420a68','#6a176e','#932667','#bc3754','#dd513a','#f37819','#fca50a','#f6d746','#fcffa4'];
function inferno(t){ t=Math.min(1,Math.max(0,t))*10; const i=Math.min(9,Math.floor(t)), f=t-i;
  const a=parseInt(INF[i].slice(1),16), b=parseInt(INF[i+1].slice(1),16);
  const ch=s=>Math.round(((a>>s)&255)*(1-f)+((b>>s)&255)*f); return `rgb(${ch(16)},${ch(8)},${ch(0)})`; }
const BASE_DOT='rgba(206,244,238,0.85)', DIM_DOT='rgba(206,244,238,0.22)';
const TEX_BASE = paintTexture(()=>BASE_DOT);
const baseCv=document.createElement('canvas'); baseCv.width=TW; baseCv.height=THt; baseCv.getContext('2d').drawImage(texCanvas,0,0);
// camadas do NASA GIBS (as mesmas do Worldview), em projeção geográfica igual à textura do globo
const GIBS={
  rain:{id:'IMERG_Precipitation_Rate', overlay:true, legend:'https://gibs.earthdata.nasa.gov/legends/GPM_Precipitation_Rate_H.png'},
  soil:{id:'SMAP_L4_Analyzed_Root_Zone_Soil_Moisture', overlay:true, legend:'https://gibs.earthdata.nasa.gov/legends/SMAP_Analyzed_Soil_Moisture_H.png'},
  haz:{id:'NDH_Landslide_Hazard_Distribution_2000', overlay:true, legend:'https://gibs.earthdata.nasa.gov/legends/NDH_Landslide_Hazard_Distribution_2000_H.png'},
  sat:{id:'VIIRS_NOAA20_CorrectedReflectance_TrueColor', overlay:false, legend:null, daysAgo:1}   // o dia corrente ainda está incompleto
};
const gibsCache=new Map();
function gibsTexture(key){
  if(gibsCache.has(key)) return gibsCache.get(key);
  const g=GIBS[key], url=`https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=${g.id}&CRS=EPSG:4326&BBOX=-90,-180,90,180&WIDTH=${TW}&HEIGHT=${THt}&FORMAT=${g.overlay?'image/png&TRANSPARENT=true':'image/jpeg'}${g.daysAgo?'&TIME='+new Date(Date.now()-g.daysAgo*864e5).toISOString().slice(0,10):''}`;
  const pr=new Promise((res,rej)=>{ const im=new Image(); im.crossOrigin='anonymous';
    im.onload=()=>{ const cv=document.createElement('canvas'); cv.width=TW; cv.height=THt; const c=cv.getContext('2d');
      if(g.overlay){ c.drawImage(baseCv,0,0); c.globalAlpha=.92; } c.drawImage(im,0,0,TW,THt); res(cv.toDataURL('image/jpeg',.9)); };
    im.onerror=()=>rej(new Error('gibs')); im.src=url; });
  pr.catch(()=>gibsCache.delete(key)); gibsCache.set(key,pr); return pr;
}

const gEl = $('#globe');
const globe = Globe({animateIn:!reduced})(gEl)
  .backgroundColor('rgba(0,0,0,0)').globeImageUrl(TEX_BASE)
  .showAtmosphere(true).atmosphereColor('#7fe0d8').atmosphereAltitude(0.2)
  .width(gEl.clientWidth).height(gEl.clientHeight).pointsMerge(true)
  .ringColor(d=>t=>d.sel?`rgba(255,255,255,${1-t})`:`rgba(245,93,93,${1-t})`).ringMaxRadius(d=>d.r||4)
  .ringPropagationSpeed(d=>d.sel?3:1.6).ringRepeatPeriod(d=>d.sel?900:1400)
  .labelText('name').labelSize(0.9).labelDotRadius(0.4).labelColor(()=> '#eaf6f4').labelResolution(2).labelAltitude(0.01);
globe.globeMaterial().shininess = 6;
globe.controls().enableZoom = false; globe.controls().autoRotate = !reduced; globe.controls().autoRotateSpeed = 0.45;
new ResizeObserver(()=>globe.width(gEl.clientWidth).height(gEl.clientHeight)).observe(gEl);
globe.pointOfView({lat:5, lng:-40, altitude:2.15}, 0);
const deadliest = [...PT].sort((a,b)=>b.fat-a.fat).slice(0,14);

let layer='risk', horizon=0, riskTexFor=null;
const riskVal = (c,h) => h===0 ? c.p2 : c.pm[h-1];
function drawLayer(){
  $('#risk-ctl').hidden = layer!=='risk';
  $('#gibs-ctl').hidden = !GIBS[layer];
  if(GIBS[layer]){
    const key=layer, g=GIBS[key]; riskTexFor=null;
    globe.pointsData([]);
    $('#gibs-legend').hidden=!g.legend; if(g.legend) $('#gibs-legend').src=g.legend;
    $('#gibs-note').textContent=L.gibs[key]; $('#pt-count').textContent=L.gibsLoading;
    gibsTexture(key).then(tex=>{ if(layer!==key) return; globe.globeImageUrl(tex); $('#pt-count').textContent='NASA GIBS · '+g.id; })
      .catch(()=>{ if(layer===key) $('#pt-count').textContent=L.gibsErr; });
    return;
  }
  $('#risk-month-lbl').textContent = horizon===0 ? L.twoYears : L.MESL[horizon-1];
  if(layer==='risk'){
    const vals=sortNum([...CELL.values()].map(c=>riskVal(c,horizon)));
    if(riskTexFor!==horizon){
      const tex=paintTexture((lat,lng)=>{ const c=CELL.get(Math.floor(lat)+','+Math.floor(lng)); return c ? inferno(.12+.88*pct(vals,riskVal(c,horizon))) : DIM_DOT; });
      globe.pointsData([]).globeImageUrl(tex); riskTexFor=horizon;
    }
    const tk=[0,.6,.85,.95,1].map(q=>quant(vals,q));
    $('#colorbar').innerHTML=`<div class="ramp" style="background:linear-gradient(90deg,${[...Array(11)].map((_,i)=>inferno(.12+.88*i/10)).join(',')})"></div>
      <div class="ticks">${tk.map(v=>`<span>${nf(v*100,v<.1?1:0)}%</span>`).join('')}</div>
      <div class="ticks cap"><span>p0</span><span>p60</span><span>p85</span><span>p95</span><span>${L.cbMax}</span></div>
      <span class="cap">${L.cbCap(fmt(CELL.size))}</span>`;
    $('#pt-count').innerHTML = horizon===0 ? L.ch2y : L.chMonth(L.MESL[horizon-1]);
  } else {
    riskTexFor=null;
    globe.globeImageUrl(TEX_BASE).pointsData(PT).pointColor(()=> '#ff7a6e').pointRadius(0.11).pointAltitude(p => 0.003 + Math.min(0.07, Math.sqrt(p.fat)*0.006));
    $('#pt-count').innerHTML = L.evCount(fmt(total), fmt(deaths));
  }
}
$('#layer-chips').addEventListener('click', e=>{const b=e.target.closest('.chip'); if(!b) return; layer=b.dataset.l;
  document.querySelectorAll('#layer-chips .chip').forEach(x=>x.setAttribute('aria-pressed', x.dataset.l===layer)); drawLayer();});
let hzT; $('#risk-month').addEventListener('input', e=>{ horizon=+e.target.value; $('#risk-month-lbl').textContent = horizon===0?L.twoYears:L.MESL[horizon-1]; clearTimeout(hzT); hzT=setTimeout(drawLayer,60); });

/* ================= APIs ================= */
const ymd = d => d.toISOString().slice(0,10).replace(/-/g,'');
const wait = ms => new Promise(r=>setTimeout(r,ms));
async function getJSON(url, ms=60000){
  const ctl=new AbortController(), to=setTimeout(()=>ctl.abort(), ms);
  try{ const r=await fetch(url,{signal:ctl.signal}); if(!r.ok) throw new Error('HTTP '+r.status); return await r.json(); } finally { clearTimeout(to); }
}
// a API POWER limita pedidos simultâneos: uma chamada por vez, com novas tentativas
let powerChain=Promise.resolve();
function fetchPower(lat,lng){
  const run=async()=>{ let err; for(const d of [0,4000,10000]){ if(d) await wait(d); try{ return await fetchPowerOnce(lat,lng); }catch(e){ err=e; } } throw err; };
  const p=powerChain.then(run,run); powerChain=p.catch(()=>{}); return p;
}
async function fetchPowerOnce(lat,lng){
  const url=`https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR,GWETTOP,GWETROOT,T2M&community=AG&longitude=${lng.toFixed(4)}&latitude=${lat.toFixed(4)}&start=19810101&end=${ymd(new Date())}&format=JSON`;
  const d=await getJSON(url, 90000), p=d.properties.parameter, fill=(d.header&&d.header.fill_value)||-999;
  const keys=Object.keys(p.PRECTOTCORR).sort();
  const arr=k=>Float64Array.from(keys, d=>{const v=p[k][d]; return (v===fill||v==null)?NaN:v;});
  return {dates:keys, P:arr('PRECTOTCORR'), GT:arr('GWETTOP'), GR:arr('GWETROOT'), T:arr('T2M')};
}
async function fetchSlope(lat,lng){
  const d=0.0025, la=[lat,lat+d,lat-d,lat,lat], lo=[lng,lng,lng,lng+d,lng-d];
  const r=await getJSON(`https://api.open-meteo.com/v1/elevation?latitude=${la.map(v=>v.toFixed(5)).join(',')}&longitude=${lo.map(v=>v.toFixed(5)).join(',')}`, 20000);
  const [z0,zn,zs,ze,zw]=r.elevation, dy=2*d*110540, dx=2*d*111320*Math.cos(lat*Math.PI/180);
  return {elev:z0, slope:Math.atan(Math.hypot((ze-zw)/dx,(zn-zs)/dy))*180/Math.PI};
}
async function geocode(q){
  const r=await getJSON(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(q)}&count=7&language=${L.geo}&format=json`, 15000);
  return (r.results||[]).map(x=>({name:x.name, sub:[x.admin1,x.country].filter(Boolean).join(', '), lat:x.latitude, lng:x.longitude}));
}
async function reverse(lat,lng){
  try{
    const r=await getJSON(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat.toFixed(4)}&lon=${lng.toFixed(4)}&zoom=10&accept-language=${L.geo}`, 12000);
    if(!r||r.error) return null; const a=r.address||{};
    const name=a.city||a.town||a.village||a.municipality||a.county||a.state_district||a.state||r.name;
    return name ? {name, sub:[a.state,a.country].filter(v=>v&&v!==name).join(', ')} : null;
  }catch(e){ return null; }
}
function inRing(x,y,ring){let c=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi)+xi))c=!c;}return c;}
function countryAt(lat,lng){for(const f of land){const g=f.geometry;if(!g)continue;const polys=g.type==='Polygon'?[g.coordinates]:g.coordinates;for(const poly of polys){const rs=poly.map(unwrap);for(const x of [lng,lng-360,lng+360]){if(inRing(x,lat,rs[0])&&!rs.slice(1).some(r=>inRing(x,lat,r)))return f.properties.name;}}}return null;}

/* ================= análise de um lugar ================= */
const VK=['rx5','trig','rain','soil','t2m'], VDEC={rx5:0,trig:0,rain:0,soil:3,t2m:1};
const V = k => ({label:L.vars[k][0], unit:L.vars[k][1], def:L.vars[k][2], dec:VDEC[k]});
function analyze(S){
  const n=S.dates.length, {P,GT,GR,T}=S, yr=S.dates.map(d=>+d.slice(0,4)), mo=S.dates.map(d=>+d.slice(4,6)-1);
  const roll=(w,t)=>{let s=0; for(let k=t-w+1;k<=t;k++){ if(k<0||Number.isNaN(P[k])) return NaN; s+=P[k]; } return s;};
  // linha de base 2001–2017, a mesma usada no treino do modelo de disparo
  const b0=S.dates.indexOf('20010101'), b1=S.dates.indexOf('20171231');
  const B={D:[],R3:[],R7:[],R14:[],GT:[],GR:[]}; let psum=0, pn=0;
  for(let t=b0;t<=b1;t++){
    if(!Number.isNaN(P[t])){B.D.push(P[t]); psum+=P[t]; pn++;}
    if(!Number.isNaN(GT[t])) B.GT.push(GT[t]); if(!Number.isNaN(GR[t])) B.GR.push(GR[t]);
    if(t-2>=b0){const v=roll(3,t); if(!Number.isNaN(v)) B.R3.push(v);}
    if(t-6>=b0){const v=roll(7,t); if(!Number.isNaN(v)) B.R7.push(v);}
    if(t-13>=b0){const v=roll(14,t); if(!Number.isNaN(v)) B.R14.push(v);}
  }
  for(const k in B) B[k]=sortNum(B[k]);
  const map=psum/pn*365.25, q95_7=quant(B.R7,.95);
  function feats(t){
    if(t<30) return null;
    for(let k=t-29;k<=t;k++) if(Number.isNaN(P[k])) return null;
    if(Number.isNaN(GT[t-1])||Number.isNaN(GR[t-1])) return null;
    const r1=Math.max(P[t],P[t-1]), r3=roll(3,t), r7=roll(7,t), r14=roll(14,t), r30=roll(30,t), gt=GT[t-1], gr=GR[t-1];
    return [r1,r3,r7,r14,r30,r30-r7,pct(B.D,r1),pct(B.R3,r3),pct(B.R7,r7),pct(B.R14,r14),gt,gr,pct(B.GT,gt),pct(B.GR,gr),map,r7/Math.max(1,q95_7)];
  }
  let last=n-1; while(last>0 && (Number.isNaN(P[last])||Number.isNaN(GT[last-1])||Number.isNaN(GR[last-1]))) last--;
  const recent=[];
  for(let t=Math.max(30,last-119);t<=last;t++){ const x=feats(t); recent.push({d:S.dates[t], p:P[t], r7:roll(7,t), gt:GT[t], s:x?predictTrig(x):NaN}); }
  const xNow=feats(last), now={date:S.dates[last], score:xNow?predictTrig(xNow):NaN, r7:xNow?xNow[2]:NaN, pr7:xNow?xNow[8]:NaN, gt:xNow?xNow[10]:NaN, pgt:xNow?xNow[12]:NaN, q95_7};
  const fullR7=[], fullGT=[];
  for(let t=0;t<n;t++){ const v=roll(7,t); if(!Number.isNaN(v)) fullR7.push(v); if(!Number.isNaN(GT[t])) fullGT.push(GT[t]); }
  const th7=quant(sortNum(fullR7),.95), thg=quant(sortNum(fullGT),.80);
  const Y={}, M={};
  for(let t=0;t<n;t++){
    const y=yr[t], k=y*12+mo[t];
    const o=Y[y]||(Y[y]={np:0,ps:0,rx5:-1,trig:0,gr:0,ngr:0,ts:0,nt:0});
    const q=M[k]||(M[k]={np:0,ps:0,trig:0,gr:0,ngr:0,ts:0,nt:0});
    const r5=roll(5,t), r7=roll(7,t);
    const isTrig = t>0&&!Number.isNaN(r7)&&!Number.isNaN(GT[t-1])&&r7>th7&&GT[t-1]>thg;
    if(!Number.isNaN(P[t])){o.np++; o.ps+=P[t]; q.np++; q.ps+=P[t];}
    if(!Number.isNaN(r5)&&r5>o.rx5) o.rx5=r5;
    if(isTrig){o.trig++; q.trig++;}
    if(!Number.isNaN(GR[t])){o.gr+=GR[t]; o.ngr++; q.gr+=GR[t]; q.ngr++;}
    if(!Number.isNaN(T[t])){o.ts+=T[t]; o.nt++; q.ts+=T[t]; q.nt++;}
  }
  const years=Object.keys(Y).map(Number).filter(y=>Y[y].np>=360&&Y[y].ngr>=360).sort((a,b)=>a-b);
  const series={ rx5:years.map(y=>Y[y].rx5), trig:years.map(y=>Y[y].trig), rain:years.map(y=>Y[y].ps), soil:years.map(y=>Y[y].gr/Y[y].ngr), t2m:years.map(y=>Y[y].ts/Y[y].nt) };
  const trends={}; for(const k in series) trends[k]=trendStats(years, series[k]);
  const mk=Object.keys(M).map(Number).filter(k=>M[k].np>=27).sort((a,b)=>a-b);
  const clim=Array(12).fill(0), cn=Array(12).fill(0); mk.forEach(k=>{clim[k%12]+=M[k].ps; cn[k%12]++;});
  for(let i=0;i<12;i++) clim[i]/=cn[i]||1;
  const monthly=mk.map(k=>({k, y:Math.floor(k/12), m:k%12, rain:M[k].ps, anom:M[k].ps-clim[k%12], trig:M[k].trig, soil:M[k].ngr?M[k].gr/M[k].ngr:NaN, t2m:M[k].nt?M[k].ts/M[k].nt:NaN, oni:ONI.get(k), phase:phaseOf(k)}));
  const withPh=monthly.filter(r=>r.phase), by=ph=>withPh.filter(r=>r.phase===ph);
  const comp={}; ['nino','neutro','nina'].forEach(ph=>{const a=by(ph).map(r=>r.anom), t=by(ph).map(r=>r.trig); comp[ph]={n:a.length, m:mean(a), se:sd(a)/Math.sqrt(a.length), tm:mean(t), tse:sd(t)/Math.sqrt(t.length), a, t};});
  comp.nino.w=welch(comp.nino.a, comp.neutro.a); comp.nina.w=welch(comp.nina.a, comp.neutro.a);
  comp.nino.wt=welch(comp.nino.t, comp.neutro.t); comp.nina.wt=welch(comp.nina.t, comp.neutro.t);
  const lags=[];
  for(let Lg=0;Lg<=6;Lg++){
    const xs=[], ys=[]; monthly.forEach(r=>{const o=ONI.get(r.k-Lg); if(o!=null){xs.push(o); ys.push(r.anom);}});
    if(xs.length<30){lags.push(null); continue;}
    const r=pearson(xs,ys), r1=lag1(xs), r2=lag1(ys), neff=Math.max(10, xs.length*(1-r1*r2)/(1+r1*r2));
    const df=neff-2, tval=r*Math.sqrt(df/(1-r*r)), tc=tcrit(df);
    lags.push({L:Lg, r, n:xs.length, neff, p:tPval(tval,df), rc:tc/Math.sqrt(df+tc*tc)});
  }
  return {years, series, trends, recent, now, map, th7, thg, monthly, comp, lags, meanMonthly:mean(clim)};
}
const cache=new Map();
function study(pl){
  const key=pl.lat.toFixed(3)+','+pl.lng.toFixed(3);
  if(!cache.has(key)){
    const pr=Promise.all([fetchPower(pl.lat,pl.lng).then(analyze), fetchSlope(pl.lat,pl.lng).catch(()=>null)]).then(([a,sl])=>({...a, slope:sl}));
    pr.catch(()=>cache.delete(key)); cache.set(key, pr);
  }
  return cache.get(key);
}

/* ================= render: lugar ================= */
const hav=(a,b,c,d)=>{const R=6371,r=Math.PI/180,x=Math.sin((c-a)*r/2)**2+Math.cos(a*r)*Math.cos(c*r)*Math.sin((d-b)*r/2)**2;return 2*R*Math.asin(Math.sqrt(x));};
const coordTxt=(lat,lng)=>`${nf(Math.abs(lat),3)}° ${lat>=0?'N':'S'} · ${nf(Math.abs(lng),3)}° ${lng>=0?(lang==='en'?'E':'L'):(lang==='en'?'W':'O')}`;
const TX=(x,y,t,a='start',c='#9fc2bf',fs=11,ff='Figtree, sans-serif')=>`<text x="${x}" y="${y}" fill="${c}" font-size="${fs}" text-anchor="${a}" font-family="${ff}">${t}</text>`;
const MONO='IBM Plex Mono, monospace';

let current=null, vk='rx5', radius=250, reqId=0, status={k:null};
const plName = pl => pl.nameKey ? L[pl.nameKey] : pl.name;
function bars(svgId, vals, color, peakColor, fmtV){
  const W=300,H=92,B=18,T=12, mx=Math.max(...vals)||1, bw=W/12, pk=vals.indexOf(Math.max(...vals));
  let s='';
  vals.forEach((v,i)=>{const h=(H-B-T)*v/mx, x=i*bw+bw*.16, w=bw*.68, isPk=i===pk&&v>0;
    s+=`<rect x="${x}" y="${H-B-Math.max(h,1.5)}" width="${w}" height="${Math.max(h,1.5)}" rx="3" fill="${isPk?peakColor:color}" fill-opacity="${v>0?1:.35}"><title>${L.MESL[i]}: ${fmtV(v)}</title></rect>`+TX(x+w/2,H-4,L.MES[i][0],'middle','#9fc2bf',9.5);});
  if(vals[pk]>0){const x=pk*bw+bw/2; s+=TX(Math.min(Math.max(x,24),W-24),9,fmtV(vals[pk]),'middle','#eaf6f4',10,MONO);}
  $('#'+svgId).innerHTML=s;
}
function renderHistory(pl){
  const near=PT.filter(p=>hav(pl.lat,pl.lng,p.lat,p.lng)<=radius);
  const fat=near.reduce((s,p)=>s+p.fat,0), rain=near.filter(p=>rainSet.includes(p.trig)).length, yrs=new Set(near.map(p=>p.year)).size;
  $('#pl-kpis').innerHTML=[[L.kpi[0],fmt(near.length)],[L.kpi[1],fmt(fat)],[L.kpi[2],near.length?Math.round(rain/near.length*100)+'%':'–'],[L.kpi[3],fmt(yrs)]].map(([a,b])=>`<div><dt>${a}</dt><dd>${b}</dd></div>`).join('');
  const days={}; near.forEach(p=>{ if(p.year&&p.month&&p.day){ const k=`${p.year}${String(p.month).padStart(2,'0')}${String(p.day).padStart(2,'0')}`; days[k]=(days[k]||0)+1; } });
  const top=Object.entries(days).sort((a,b)=>b[1]-a[1])[0];
  $('#pl-episode').innerHTML = top && top[1]>1 ? L.episode(fmt(top[1]), dFmt(top[0])) : '';
  const sm=Array(12).fill(0); near.forEach(p=>{if(p.month>=1) sm[p.month-1]++}); bars('pl-season', sm, '#16aba9', '#6fe0d6', v=>`${fmt(v)} ${L.evs}`);
  const tc={}; near.forEach(p=>tc[p.trig]=(tc[p.trig]||0)+1);
  $('#pl-trig').innerHTML=Object.entries(tc).sort((a,b)=>b[1]-a[1]).slice(0,4).map(([t,n])=>`<span>${trigName(t)} <b>${fmt(n)}</b></span>`).join('')||`<span>${L.noEv}</span>`;
  const cell=nearestCell(pl.lat,pl.lng);
  if(cell){
    const cl=structClass(cell.p2), pk=cell.pm.indexOf(Math.max(...cell.pm));
    $('#st-prob').textContent=(cell.p2<.01?'< 1':Math.round(cell.p2*100))+'%'; badge($('#st-badge'), cl, L.riskOf(clsName(cl)));
    $('#st-txt').innerHTML=L.stTxt(L.MESL[pk]);
    bars('pl-pred', cell.pm.map(v=>v*100), '#f58b5d', '#f55d5d', v=>`${nf(v,1)}%`);
  } else {
    $('#st-prob').textContent='< 1%'; badge($('#st-badge'), CLS.nd, L.outModel);
    $('#st-txt').textContent=L.stNone;
    bars('pl-pred', Array(12).fill(0), '#f58b5d', '#f55d5d', v=>`${nf(v,1)}%`);
  }
}
function drawRecent(A){
  const svg=$('#recent'), W=960, Lm=58, R=14, rc=A.recent, N=rc.length; if(!N){svg.innerHTML='';return;}
  const X=i=>Lm+(i+.5)/N*(W-Lm-R), bw=(W-Lm-R)/N*.7;
  const pA={t:16,b:150}, pB={t:180,b:240}, pC={t:270,b:330};
  const mxA=Math.max(A.now.q95_7, ...rc.map(d=>d.r7||0))*1.08||1, yA=v=>pA.b-(v/mxA)*(pA.b-pA.t);
  const yB=v=>pB.b-v*(pB.b-pB.t);
  const mxC=Math.max(TM.thr.muito*1.15, ...rc.map(d=>d.s||0)), yC=v=>pC.b-(v/mxC)*(pC.b-pC.t);
  let s='';
  niceTicks(0,mxA,3).forEach(t=>{s+=`<line x1="${Lm}" x2="${W-R}" y1="${yA(t)}" y2="${yA(t)}" stroke="rgba(234,246,244,.08)"/>`+TX(Lm-8,yA(t)+4,fmt(t),'end','#9fc2bf',11,MONO);});
  rc.forEach((d,i)=>{ if(d.p>0) s+=`<rect x="${X(i)-bw/2}" y="${yA(d.p)}" width="${bw}" height="${pA.b-yA(d.p)}" fill="#16aba9"><title>${dFmt(d.d)}: ${nf(d.p,1)} mm</title></rect>`; });
  s+=`<polyline points="${rc.map((d,i)=>`${X(i)},${yA(d.r7||0)}`).join(' ')}" fill="none" stroke="#eaf6f4" stroke-width="1.6"/>`;
  s+=`<line x1="${Lm}" x2="${W-R}" y1="${yA(A.now.q95_7)}" y2="${yA(A.now.q95_7)}" stroke="#f55d5d" stroke-dasharray="5 4"/>`;
  s+=TX(Lm,pA.t-4,L.rec_a)+TX(W-R,yA(A.now.q95_7)-6,`q95(R⁷) = ${fmt(Math.round(A.now.q95_7))} mm`,'end','#ff9c94',11,MONO);
  [0,.5,1].forEach(t=>{s+=`<line x1="${Lm}" x2="${W-R}" y1="${yB(t)}" y2="${yB(t)}" stroke="rgba(234,246,244,.08)"/>`+TX(Lm-8,yB(t)+4,nf(t,1),'end','#9fc2bf',11,MONO);});
  s+=`<polyline points="${rc.map((d,i)=>`${X(i)},${yB(Number.isNaN(d.gt)?0:d.gt)}`).join(' ')}" fill="none" stroke="#6fcfc8" stroke-width="1.8"/>`;
  s+=`<line x1="${Lm}" x2="${W-R}" y1="${yB(A.thg)}" y2="${yB(A.thg)}" stroke="#f2c38b" stroke-dasharray="5 4"/>`;
  s+=TX(Lm,pB.t-6,L.rec_b)+TX(W-R,yB(A.thg)-6,'q80','end','#f2c38b',11,MONO);
  [['elev','#f2c38b'],['alto','#f58b5d'],['muito','#f55d5d']].forEach(([k,c])=>{s+=`<line x1="${Lm}" x2="${W-R}" y1="${yC(TM.thr[k])}" y2="${yC(TM.thr[k])}" stroke="${c}" stroke-opacity=".55" stroke-dasharray="3 4"/>`;});
  const pts=rc.map((d,i)=>[X(i),yC(Number.isNaN(d.s)?0:d.s)]);
  s+=`<polygon points="${Lm},${pC.b} ${pts.map(p=>p.join(',')).join(' ')} ${X(N-1)},${pC.b}" fill="#f55d5d" fill-opacity=".14"/><polyline points="${pts.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#f55d5d" stroke-width="2"/>`;
  const lastS=rc[N-1].s; if(!Number.isNaN(lastS)) s+=`<circle cx="${X(N-1)}" cy="${yC(lastS)}" r="5" fill="#f55d5d" stroke="#001a1a" stroke-width="2"/>`;
  s+=TX(Lm,pC.t-8,L.rec_c);
  for(let i=0;i<N;i+=Math.ceil(N/8)) s+=TX(X(i),352,dShort(rc[i].d),'middle','#9fc2bf',11,MONO);
  s+=TX(X(N-1),352,dShort(rc[N-1].d),'middle','#eaf6f4',11,MONO);
  svg.innerHTML=s;
}
function drawTrend(A){
  const v=V(vk), x=A.years, y=A.series[vk], st=A.trends[vk], svg=$('#trend');
  const W=640,H=300,Lm=56,R=16,T=18,B=34, x0=x[0], x1=x[x.length-1];
  const lo0=Math.min(...y), hi0=Math.max(...y), pad=(hi0-lo0)*.15||1, ticks=niceTicks(lo0-pad,hi0+pad);
  const lo=Math.min(ticks[0],lo0-pad), hi=Math.max(ticks[ticks.length-1],hi0+pad);
  const Xs=q=>Lm+(q-x0)/(x1-x0)*(W-Lm-R), Ys=q=>T+(hi-q)/(hi-lo)*(H-T-B);
  const fit=q=>st.a+st.b*q, band=q=>st.tc*st.se*Math.sqrt(1/st.n+(q-st.mx)**2/st.sxx);
  const col=st.p<.05?(st.sen>0?'#f55d5d':'#4f9fd1'):'#eaf6f4', tf=v.dec>1?2:v.dec;
  let s='';
  ticks.forEach(t=>{s+=`<line x1="${Lm}" x2="${W-R}" y1="${Ys(t)}" y2="${Ys(t)}" stroke="rgba(234,246,244,.09)"/>`+TX(Lm-8,Ys(t)+4,nf(t,tf),'end','#9fc2bf',11,MONO);});
  niceTicks(x0,x1,5).filter(t=>t>=x0&&t<=x1).forEach(t=>{s+=TX(Xs(t),H-10,t,'middle','#9fc2bf',11,MONO);});
  s+=TX(Lm,11,v.unit);
  const up=x.map(q=>`${Xs(q)},${Ys(fit(q)+band(q))}`), dn=x.slice().reverse().map(q=>`${Xs(q)},${Ys(fit(q)-band(q))}`);
  s+=`<polygon points="${up.join(' ')} ${dn.join(' ')}" fill="${col}" fill-opacity=".12"/>`;
  s+=`<polyline points="${x.map((q,i)=>`${Xs(q)},${Ys(y[i])}`).join(' ')}" fill="none" stroke="rgba(234,246,244,.3)" stroke-width="1.2"/>`;
  s+=`<line x1="${Xs(x0)}" y1="${Ys(fit(x0))}" x2="${Xs(x1)}" y2="${Ys(fit(x1))}" stroke="${col}" stroke-width="2.4"/>`;
  x.forEach((q,i)=>{const ph=annualPhase(q), f=ph?C[ph]:'#eaf6f4'; s+=`<circle cx="${Xs(q)}" cy="${Ys(y[i])}" r="${ph&&ph!=='neutro'?4:2.8}" fill="${f}"><title>${q}: ${nf(y[i],v.dec)} ${v.unit}${ph?' · '+PHN(ph):''}</title></circle>`;});
  svg.innerHTML=s;
  const sig=st.p<.05, vd=$('#verdict');
  vd.className='verdict '+(sig?(st.sen>0?'sig-up':'sig-down'):'');
  vd.textContent=sig?(st.sen>0?L.verdict.up:L.verdict.down):L.verdict.none;
  const dd=v.dec>1?3:1;
  $('#results').innerHTML=[[L.res[0],sgn(st.sen*10,dd)],[L.res[1],`${nf(st.ci[0]*10,dd)} ${L.to} ${nf(st.ci[1]*10,dd)}`],[L.res[2],nf(st.Z,2)],[L.res[3],st.p<.001?'< '+nf(0.001,3):nf(st.p,3)]]
    .map(([a,b])=>`<div><dt>${a}</dt><dd>${b}</dd></div>`).join('');
  $('#vardef').innerHTML=v.def+L.serie(x0,x1,x.length);
}
function drawEnso(A){
  const cp=A.comp, order=['nino','neutro','nina'];
  { const svg=$('#enso-comp'), W=420,H=170,Lm=46,R=10,T=14,B=26;
    const ext=Math.max(...order.map(k=>Math.abs(cp[k].m)+cp[k].se))*1.25||1, Ys=v=>T+(ext-v)/(2*ext)*(H-T-B), bw=(W-Lm-R)/3;
    let s=''; niceTicks(-ext,ext,4).forEach(t=>{s+=`<line x1="${Lm}" x2="${W-R}" y1="${Ys(t)}" y2="${Ys(t)}" stroke="rgba(234,246,244,${t===0?.35:.08})"/>`+TX(Lm-6,Ys(t)+4,nf(t,0),'end','#9fc2bf',10.5,MONO);});
    order.forEach((k,i)=>{const o=cp[k], cx=Lm+bw*i+bw/2, w=bw*.42, y0=Ys(0), y1=Ys(o.m);
      s+=`<rect x="${cx-w/2}" y="${Math.min(y0,y1)}" width="${w}" height="${Math.max(1,Math.abs(y1-y0))}" rx="4" fill="${C[k]}" fill-opacity="${k==='neutro'?.5:.9}"/>`;
      s+=`<line x1="${cx}" x2="${cx}" y1="${Ys(o.m+o.se)}" y2="${Ys(o.m-o.se)}" stroke="#eaf6f4" stroke-width="1.4"/>`;
      s+=TX(cx,H-8,`${PHN(k)} (n=${o.n})`,'middle','#c4dcda',10.5);
      if(o.w) s+=TX(cx,T+2,pTxt(o.w.p),'middle',o.w.p<.05?'#eaf6f4':'#9fc2bf',10,MONO);});
    s+=TX(Lm,9,L.mmMonth,'start','#9fc2bf',10);
    svg.innerHTML=s; }
  { const svg=$('#enso-trig'), W=420,H=120,Lm=70,R=60,T=6;
    const mx=Math.max(...order.map(k=>cp[k].tm+cp[k].tse))*1.15||1, X=v=>Lm+v/mx*(W-Lm-R), rh=(H-T-12)/3;
    let s='';
    order.forEach((k,i)=>{const o=cp[k], cy=T+rh*i+rh/2;
      s+=TX(0,cy+4,PHN(k),'start','#c4dcda',11)+`<rect x="${Lm}" y="${cy-7}" width="${Math.max(1,X(o.tm)-Lm)}" height="14" rx="7" fill="${C[k]}" fill-opacity="${k==='neutro'?.5:.9}"/>`;
      s+=`<line x1="${X(o.tm-o.tse)}" x2="${X(o.tm+o.tse)}" y1="${cy}" y2="${cy}" stroke="#eaf6f4" stroke-width="1.4"/>`;
      s+=TX(X(o.tm+o.tse)+6,cy+4,`${nf(o.tm,2)}${o.wt&&!Number.isNaN(o.wt.p)?' · '+pTxt(o.wt.p):''}`,'start','#9fc2bf',10,MONO);});
    svg.innerHTML=s; }
  { const svg=$('#enso-lag'), W=420,H=150,Lm=46,R=10,T=12,B=28, lg=A.lags.filter(Boolean);
    const ext=Math.max(.3,...lg.map(o=>Math.abs(o.r)),...lg.map(o=>o.rc))*1.15, Ys=v=>T+(ext-v)/(2*ext)*(H-T-B), bw=(W-Lm-R)/7;
    let s=''; const rc=mean(lg.map(o=>o.rc));
    s+=`<rect x="${Lm}" y="${Ys(rc)}" width="${W-Lm-R}" height="${Ys(-rc)-Ys(rc)}" fill="rgba(234,246,244,.07)"/>`;
    niceTicks(-ext,ext,4).forEach(t=>{s+=`<line x1="${Lm}" x2="${W-R}" y1="${Ys(t)}" y2="${Ys(t)}" stroke="rgba(234,246,244,${t===0?.35:.06})"/>`+TX(Lm-6,Ys(t)+4,nf(t,1),'end','#9fc2bf',10.5,MONO);});
    lg.forEach(o=>{const cx=Lm+bw*o.L+bw/2, w=bw*.5, y0=Ys(0), y1=Ys(o.r), sig=o.p<.05;
      s+=`<rect x="${cx-w/2}" y="${Math.min(y0,y1)}" width="${w}" height="${Math.max(1,Math.abs(y1-y0))}" rx="3" fill="${o.r>0?C.nino:C.nina}" fill-opacity="${sig?.95:.35}"><title>${L.lagTip(o.L,nf(o.r,2),pTxt(o.p),Math.round(o.neff))}</title></rect>`+TX(cx,H-12,o.L,'middle','#9fc2bf',10.5,MONO);});
    s+=TX((Lm+W-R)/2,H-1,L.lagAxis,'middle','#9fc2bf',10)+TX(Lm,9,L.pearson,'start','#9fc2bf',10);
    svg.innerHTML=s; }
  const nino=cp.nino, pctD=nino.w.d/A.meanMonthly*100, sig=nino.w.p<.05;
  const cl = !sig ? {c:'rgba(234,246,244,.12)',t:'#9fc2bf',k:L.ensoBadge.none} : pctD>0 ? {c:C.nino,t:'#fff',k:L.ensoBadge.more} : {c:C.nina,t:'#fff',k:L.ensoBadge.less};
  $('#en-delta').innerHTML=`${sgn(pctD,0)}<small>%</small>`; badge($('#en-badge'), cl);
  $('#en-txt').innerHTML=L.ensoTxt({cur:curTxt(), oni:sgn(lastOni,2), seas:lastSeas, d:sgn(nino.w.d,0), p:pTxt(nino.w.p), tr:nf(cp.nino.tm,2), tn:nf(cp.neutro.tm,2)});
}
function renderVarChips(){
  $('#vars').innerHTML=VK.map(k=>`<button class="chip" type="button" data-k="${k}" aria-pressed="${k===vk}">${L.vars[k][0]}</button>`).join('');
  $('#cmp-vars').innerHTML=VK.map(k=>`<button class="chip" type="button" data-k="${k}" aria-pressed="${k===cvk}">${L.vars[k][0]}</button>`).join('');
}
$('#vars').addEventListener('click',e=>{const b=e.target.closest('.chip'); if(!b) return; vk=b.dataset.k;
  document.querySelectorAll('#vars .chip').forEach(x=>x.setAttribute('aria-pressed',x.dataset.k===vk)); if(current&&current.A) drawTrend(current.A);});
$('#radius-chips').addEventListener('click',e=>{const b=e.target.closest('.chip'); if(!b) return; radius=+b.dataset.r;
  document.querySelectorAll('#radius-chips .chip').forEach(x=>x.setAttribute('aria-pressed',x.dataset.r===b.dataset.r)); if(current) renderHistory(current.pl);});

function setStatus(k, args){
  status={k,args}; const s=$('#pl-status');
  if(k==='loading'){ s.className='status loading'; s.textContent=L.st_loading; }
  else if(k==='done'){ s.className='status'; s.textContent=L.st_done(dFmt(args[0]), lastSeas); }
  else if(k==='err'){ s.className='status error'; s.textContent=L.st_err;
    const b=document.createElement('button'); b.className='pill'; b.type='button'; b.textContent=L.retry; b.onclick=()=>current&&selectPlace(current.pl,{fly:false}); s.append(' ', b); }
  else if(k==='msg'){ s.className='status error'; s.textContent=args[0](); }
}
function renderHeader(pl){
  $('#pl-name').textContent=plName(pl);
  $('#pl-coord').textContent=[pl.sub, coordTxt(pl.lat,pl.lng)].filter(Boolean).join(' · ');
}
async function selectPlace(pl, opts={}){
  const id=++reqId; current={pl};
  renderHeader(pl);
  ['#now-score','#st-prob','#sl-deg','#en-delta'].forEach(s=>$(s).textContent='…');
  ['#now-badge','#sl-badge','#en-badge'].forEach(s=>{$(s).textContent='';$(s).style.background='';});
  ['#now-txt','#sl-txt','#en-txt'].forEach(s=>$(s).textContent='');
  $('#pl-csv').disabled=true;
  renderHistory(pl); updateSaveBtn(); paintGlobeMarks();
  globe.ringsData([{lat:pl.lat,lng:pl.lng,sel:true,r:radius/111}].concat(reduced||layer==='risk'?[]:deadliest));
  if(opts.fly!==false){ globe.controls().autoRotate=false; globe.pointOfView({lat:pl.lat,lng:pl.lng,altitude:1.9}, reduced?0:1000); }
  if(opts.scroll) $('#s1').scrollIntoView({behavior:reduced?'auto':'smooth'});
  const wvT=new Date(Date.now()-864e5).toISOString().slice(0,10), d=2;
  $('#pl-wv').href=`https://worldview.earthdata.nasa.gov/?v=${(pl.lng-d).toFixed(2)},${(pl.lat-d).toFixed(2)},${(pl.lng+d).toFixed(2)},${(pl.lat+d).toFixed(2)}&l=Reference_Labels_15m,Reference_Features_15m,Coastlines_15m,IMERG_Precipitation_Rate,SMAP_L4_Analyzed_Root_Zone_Soil_Moisture(hidden),VIIRS_NOAA20_CorrectedReflectance_TrueColor&t=${wvT}`;
  setStatus('loading');
  try{
    const A=await study(pl); if(id!==reqId) return;
    current.A=A; renderPlace(pl,A); setStatus('done',[A.now.date]); $('#pl-csv').disabled=false;
  }catch(err){
    if(id!==reqId) return;
    setStatus('err'); ['#now-score','#sl-deg','#en-delta'].forEach(s=>$(s).textContent='–');
  }
}
function renderPlace(pl,A){
  const nw=A.now;
  if(!Number.isNaN(nw.score)){
    const cl=trigClass(nw.score);
    $('#now-score').innerHTML=Math.round(nw.score*100)+'<small>/100</small>'; badge($('#now-badge'), cl);
    $('#now-txt').innerHTML=L.nowTxt({r7:fmt(Math.round(nw.r7)), pr7:Math.round(nw.pr7*100), gt:nf(nw.gt,2), pgt:Math.round(nw.pgt*100), date:dFmt(nw.date)});
  } else { $('#now-score').textContent='–'; $('#now-txt').textContent=L.nowNA; }
  if(A.slope){
    const cl=slopeClass(A.slope.slope);
    $('#sl-deg').textContent=nf(A.slope.slope,1)+'°'; badge($('#sl-badge'), cl);
    $('#sl-txt').innerHTML=L.slTxt(fmt(Math.round(A.slope.elev)));
  } else { $('#sl-deg').textContent='–'; $('#sl-txt').textContent=L.slNA; }
  $('#recent-src').textContent=`NASA POWER (MERRA-2) · ${dFmt(A.recent[0].d)}–${dFmt(A.recent[A.recent.length-1].d)}`;
  drawRecent(A); drawTrend(A); drawEnso(A);
}

/* CSV */
$('#pl-csv').addEventListener('click',()=>{
  if(!current||!current.A) return; const A=current.A, pl=current.pl;
  const head=[`# Data Detectives · ${plName(pl)} (${pl.sub||''})`,`# lat ${pl.lat.toFixed(4)}, lon ${pl.lng.toFixed(4)}`,`# ${L.csvSrc}: NASA POWER daily (MERRA-2) PRECTOTCORR, GWETTOP, GWETROOT, T2M; NOAA CPC ONI (${ENSO.updated})`,`# ${L.csvGen} ${new Date().toISOString()}`,
    L.csvTrig(A.th7.toFixed(1), A.thg.toFixed(3))];
  const rows=[L.csvCols].concat(A.monthly.map(r=>[r.y,r.m+1,r.rain.toFixed(2),r.anom.toFixed(2),r.trig,Number.isNaN(r.soil)?'':r.soil.toFixed(4),Number.isNaN(r.t2m)?'':r.t2m.toFixed(2),r.oni??'',r.phase??''].join(',')));
  const blob=new Blob([head.join('\n')+'\n'+rows.join('\n')],{type:'text/csv'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=`data-detectives_${plName(pl).normalize('NFD').replace(/[^\w]+/g,'-').toLowerCase()}.csv`;
  document.body.append(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(a.href),5000);
});

/* ================= busca e clique ================= */
const inp=$('#busca'), list=$('#busca-res'); let found=[], sel=-1, tmo;
function showList(items,msg){
  found=items; sel=-1;
  list.innerHTML = msg ? `<li class="msg">${msg}</li>` : items.map((r,i)=>`<li role="option" id="opt-${i}" data-i="${i}" aria-selected="false"><span class="r1">${r.name}</span><span class="r2">${r.sub} · ${coordTxt(r.lat,r.lng)}</span></li>`).join('');
  list.hidden=false;
}
inp.addEventListener('input',()=>{ clearTimeout(tmo); const q=inp.value.trim(); if(q.length<2){list.hidden=true;return;}
  tmo=setTimeout(async()=>{ try{ const r=await geocode(q); if(inp.value.trim()!==q) return; r.length?showList(r):showList([],L.pNone); }catch(e){ showList([],L.pFail); } },250); });
inp.addEventListener('keydown',e=>{
  if(list.hidden||!found.length) return;
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){ e.preventDefault(); sel=(sel+(e.key==='ArrowDown'?1:-1)+found.length)%found.length;
    list.querySelectorAll('li').forEach((li,i)=>li.setAttribute('aria-selected',i===sel)); }
  if(e.key==='Escape') list.hidden=true;
});
function pick(i){ const r=found[i]; if(!r) return; list.hidden=true; inp.value=r.name; selectPlace(r,{scroll:true}); }
list.addEventListener('click',e=>{const li=e.target.closest('li[data-i]'); if(li) pick(+li.dataset.i);});
$('#busca-wrap').addEventListener('submit',async e=>{ e.preventDefault(); const q=inp.value.trim(); if(!q) return;
  if(found.length&&!list.hidden) return pick(sel>=0?sel:0);
  try{ const r=await geocode(q); r.length?(found=r,pick(0)):showList([],L.pNone); }catch(err){ showList([],L.pFail); } });
document.addEventListener('click',e=>{ if(!e.target.closest('#busca-wrap')) list.hidden=true; });
const SUG=['Petrópolis','Medellín','Kathmandu','Baguio','Wayanad','Los Angeles'];
function renderSuggest(){ $('#suggest').innerHTML=`<span>${L.tryIt}</span>`+SUG.map(s=>`<button class="chip" type="button" data-q="${s}">${s}</button>`).join(''); }
$('#suggest').addEventListener('click',async e=>{const b=e.target.closest('.chip'); if(!b) return; inp.value=b.dataset.q;
  try{ const r=await geocode(b.dataset.q); if(r.length){found=r; pick(0);} }catch(err){ setStatus('msg',[()=>L.pFail]); } });
async function onPick({lat,lng}){
  const c=countryAt(lat,lng);
  const pl={lat,lng,nameKey:c?'point':'ocean',sub:c||''};
  selectPlace(pl,{scroll:false});
  const r=await reverse(lat,lng);
  if(r && current && current.pl===pl){ delete pl.nameKey; pl.name=r.name; pl.sub=r.sub; renderHeader(pl); updateSaveBtn(); }
}
globe.onGlobeClick(onPick);
globe.onPointClick(p=>onPick({lat:p.lat,lng:p.lng}));

/* ================= comparação ================= */
let saved=store.get('dd-places',[]), cvk='rx5';
const sameP=(a,b)=>Math.abs(a.lat-b.lat)<1e-3&&Math.abs(a.lng-b.lng)<1e-3;
function updateSaveBtn(){ const b=$('#pl-save'); if(!current) return; const on=saved.some(s=>sameP(s,current.pl)); b.textContent=on?L.saved:L.save; b.disabled=on; }
$('#pl-save').addEventListener('click',()=>{ if(!current||saved.some(s=>sameP(s,current.pl))) return;
  const {sub,lat,lng}=current.pl; saved.push({name:plName(current.pl),sub,lat,lng}); store.set('dd-places',saved); updateSaveBtn(); renderCompare(); paintGlobeMarks(); });
function paintGlobeMarks(){ globe.labelsData(saved.map(s=>({lat:s.lat,lng:s.lng,name:s.name}))); }
$('#cmp-vars').addEventListener('click',e=>{const b=e.target.closest('.chip'); if(!b) return; cvk=b.dataset.k;
  document.querySelectorAll('#cmp-vars .chip').forEach(x=>x.setAttribute('aria-pressed',x.dataset.k===cvk)); renderCompare();});
async function renderCompare(){
  $('#cmp-empty').hidden=saved.length>0; $('#div-fig').hidden=!saved.length;
  const v=V(cvk), dd=v.dec>1?3:1; $('#cmp-th').textContent=L.cmpTh(v.label);
  const body=$('#cmp-body');
  body.innerHTML=saved.map((s,i)=>`<tr data-i="${i}"><td><button class="nm" type="button" data-go="${i}">${s.name}</button><span class="sub">${s.sub||coordTxt(s.lat,s.lng)}</span></td><td class="c-now mono">…</td><td class="c-st"></td><td class="c-en mono">…</td><td class="c-sl mono">…</td><td class="c-tr mono">…</td><td><button class="rm" type="button" data-rm="${i}">${L.remove}</button></td></tr>`).join('');
  const rows=[];
  await Promise.all(saved.map(async (s,i)=>{
    const tr=body.querySelector(`tr[data-i="${i}"]`); if(!tr) return; const cell=nearestCell(s.lat,s.lng), cs=cell?structClass(cell.p2):CLS.nd;
    tr.querySelector('.c-st').innerHTML=`<span class="pillc" style="background:${cs.c};color:${cs.t}">${cell?Math.round(cell.p2*100)+'% · '+clsName(cs):clsName(cs)}</span>`;
    try{
      const A=await study(s), st=A.trends[cvk], cl=trigClass(A.now.score), w=A.comp.nino.w;
      if(!tr.isConnected) return;
      tr.querySelector('.c-now').innerHTML=Number.isNaN(A.now.score)?'–':`<span class="pillc" style="background:${cl.c};color:${cl.t}">${Math.round(A.now.score*100)} · ${clsName(cl)}</span>`;
      tr.querySelector('.c-en').innerHTML=`${sgn(w.d/A.meanMonthly*100,0)}% <span style="color:${w.p<.05?(w.d>0?C.ninoInk:C.ninaInk):'#4b6866'}">· ${w.p<.05?L.sig:L.ns}</span>`;
      tr.querySelector('.c-sl').textContent=A.slope?nf(A.slope.slope,1)+'°':'–';
      tr.querySelector('.c-tr').innerHTML=`${sgn(st.sen*10,dd)} ${v.unit} <span style="color:${st.p<.05?(st.sen>0?C.ninoInk:C.ninaInk):'#4b6866'}">· ${st.p<.05?L.sig:L.ns}</span>`;
      rows[i]={name:s.name, d:st.sen*10, p:st.p};
    }catch(e){ if(tr.isConnected) tr.querySelector('.c-now').textContent=L.dlErr; }
  }));
  drawDiverging(rows.filter(Boolean));
}
$('#cmp-body').addEventListener('click',e=>{
  const rm=e.target.closest('[data-rm]'), go=e.target.closest('[data-go]');
  if(rm){ saved.splice(+rm.dataset.rm,1); store.set('dd-places',saved); renderCompare(); paintGlobeMarks(); updateSaveBtn(); }
  if(go){ selectPlace(saved[+go.dataset.go],{scroll:true}); }
});
function drawDiverging(rows){
  const svg=$('#div-chart'); if(!rows.length){svg.innerHTML='';return;}
  const W=640, Lm=170, R=80, rh=34, H=rows.length*rh+34, v=V(cvk), dd=v.dec>1?3:1;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const m=Math.max(...rows.map(o=>Math.abs(o.d)))*1.1||1, X=q=>Lm+(q+m)/(2*m)*(W-Lm-R);
  let s=`<line x1="${X(0)}" x2="${X(0)}" y1="4" y2="${H-24}" stroke="rgba(11,40,39,.3)"/>`+TX(X(-m),H-6,L.dec,'start','#4b6866')+TX(X(m),H-6,L.inc,'end','#4b6866');
  rows.forEach((o,i)=>{const cy=8+rh*i+rh/2, col=o.d>0?C.nino:C.nina, sig=o.p<.05;
    s+=TX(0,cy+4,o.name,'start','#0b2827',13.5)+`<line x1="${X(0)}" x2="${X(o.d)}" y1="${cy}" y2="${cy}" stroke="${col}" stroke-width="3" stroke-opacity="${sig?1:.5}"/>`;
    s+=`<circle cx="${X(o.d)}" cy="${cy}" r="6" fill="${sig?col:'#f5f9f8'}" stroke="${col}" stroke-width="2"/>`+TX(o.d>=0?X(o.d)+12:X(o.d)-12,cy+4,sgn(o.d,dd),o.d>=0?'start':'end','#4b6866',11,MONO);});
  svg.innerHTML=s;
}

/* ================= seção ENSO global ================= */
const REGB=[[-90,90,-180,180],[5,37,60,92],[-11,25,92,141],[-56,13,-82,-34],[7,24,-118,-59],[24,72,-170,-52]];
const REGSTAT=REGB.map(([a,b,c,d])=>{
  const cnt=new Map(); for(let k=2007*12;k<=2017*12+11;k++) cnt.set(k,0);
  PT.forEach(p=>{ if(p.year>=2007&&p.year<=2017&&p.month>=1&&p.lat>=a&&p.lat<=b&&p.lng>=c&&p.lng<=d){const k=p.year*12+p.month-1; cnt.set(k,cnt.get(k)+1);} });
  const ym={}; cnt.forEach((v,k)=>{const y=Math.floor(k/12); ym[y]=(ym[y]||0)+v/12;});
  const g={nino:[],neutro:[],nina:[]}; cnt.forEach((v,k)=>{const y=Math.floor(k/12), ph=phaseOf(k); if(ph&&ym[y]>0) g[ph].push(v/ym[y]);});
  const st={}; for(const ph in g){const a2=g[ph]; st[ph]={m:a2.length?mean(a2):NaN, se:a2.length>2?sd(a2)/Math.sqrt(a2.length):0, n:a2.length};}
  st.wn=welch(g.nino,g.neutro); st.wa=welch(g.nina,g.neutro);
  return st;
});
function renderEnsoSection(){
  const upd=isoFmt(ENSO.updated);
  $('#oni-src').textContent=L.oniSrc(upd); $('#oni-upd').textContent=upd;
  $('#enso-intro').innerHTML=L.ensoIntro({oni:sgn(lastOni,2), seas:lastSeas, cur:curTxt()});
  const svg=$('#oni-chart'), W=960,H=260,Lm=46,R=12,T=14,B=28, k0=oniKeys[0], k1=lastK;
  const X=k=>Lm+(k-k0)/(k1-k0)*(W-Lm-R), ext=3, Ys=v=>T+(ext-v)/(2*ext)*(H-T-B), bw=Math.max(1,(W-Lm-R)/(k1-k0+1));
  let s='';
  [-2,-1,-.5,0,.5,1,2].forEach(t=>{s+=`<line x1="${Lm}" x2="${W-R}" y1="${Ys(t)}" y2="${Ys(t)}" stroke="rgba(11,40,39,${t===0?.35:Math.abs(t)===.5?.18:.07})" ${Math.abs(t)===.5?'stroke-dasharray="4 4"':''}/>`+TX(Lm-6,Ys(t)+4,(t>0?'+':'')+nf(t,1),'end','#4b6866',10.5,MONO);});
  oniKeys.forEach(k=>{const v=ONI.get(k), ph=phaseOf(k), c=ph==='nino'?C.nino:ph==='nina'?C.nina:'#9bb3b1';
    s+=`<rect x="${X(k)-bw/2}" y="${Math.min(Ys(0),Ys(v))}" width="${bw}" height="${Math.abs(Ys(v)-Ys(0))}" fill="${c}"><title>${SEAS[k%12]} ${Math.floor(k/12)}: ${sgn(v,2)} °C</title></rect>`;});
  for(let y=1950;y<=Math.floor(k1/12);y+=10) s+=TX(X(y*12),H-8,y,'middle','#4b6866',10.5,MONO);
  s+=`<circle cx="${X(k1)}" cy="${Ys(lastOni)}" r="5" fill="${C.nino}" stroke="#f5f9f8" stroke-width="2"/>`+TX(X(k1)-10,Ys(lastOni)+4,`${lastSeas}: ${sgn(lastOni,2)} °C`,'end','#0b2827',12,MONO);
  [['1982–83',1982*12+11],['1997–98',1997*12+11],['2015–16',2015*12+11],['2010–11',2010*12+11]].forEach(([t,k])=>{const v=ONI.get(k); if(v!=null) s+=TX(X(k),Ys(v)+(v>0?-8:16),t,'middle','#4b6866',10);});
  s+=TX(Lm,9,L.oniAxis,'start','#4b6866',10.5);
  svg.innerHTML=s;

  const s2=$('#enso-regions'), W2=960,H2=330,L2=180,R2=40,T2=34, rh=(H2-T2-30)/REGSTAT.length;
  const vmax=Math.max(...REGSTAT.flatMap(r=>['nino','neutro','nina'].map(ph=>(r[ph].m||0)+r[ph].se)))*1.08, vmin=Math.min(.5,...REGSTAT.flatMap(r=>['nino','neutro','nina'].map(ph=>(r[ph].m||1)-r[ph].se)))*.95;
  const X2=v=>L2+(v-vmin)/(vmax-vmin)*(W2-L2-R2);
  let t='';
  niceTicks(vmin,vmax,6).forEach(v=>{t+=`<line x1="${X2(v)}" x2="${X2(v)}" y1="${T2-6}" y2="${H2-26}" stroke="rgba(11,40,39,${v===1?.4:.08})" ${v===1?'stroke-dasharray="4 4"':''}/>`+TX(X2(v),H2-10,nf(v,1),'middle','#4b6866',10.5,MONO);});
  t+=TX(X2(1),T2-12,L.yearMean,'middle','#4b6866',10.5);
  REGSTAT.forEach((r,i)=>{const cy=T2+rh*i+rh/2, nm=L.regions[i];
    t+=TX(0,cy+4,nm,'start','#0b2827',13.5);
    [['nina',-9],['neutro',0],['nino',9]].forEach(([ph,dy])=>{const o=r[ph]; if(Number.isNaN(o.m)) return; const y=cy+dy;
      t+=`<line x1="${X2(o.m-o.se)}" x2="${X2(o.m+o.se)}" y1="${y}" y2="${y}" stroke="${C[ph]}" stroke-width="2"/><circle cx="${X2(o.m)}" cy="${y}" r="5" fill="${C[ph]}"><title>${L.regTip(nm,PHN(ph),nf(o.m,2),nf(o.se,2),o.n)}</title></circle>`;});
    const pn=r.wn.p, pa=r.wa.p;
    t+=TX(W2-R2+34,cy+4,`${Number.isNaN(pn)?'':'N '+(pn<.05?'*':'ns')} ${Number.isNaN(pa)?'':'L '+(pa<.05?'*':'ns')}`,'end','#4b6866',10.5,MONO);});
  t+=`<circle cx="${L2}" cy="12" r="5" fill="${C.nino}"/>`+TX(L2+10,16,PHN('nino'),'start','#0b2827',11.5)+`<circle cx="${L2+90}" cy="12" r="5" fill="${C.neutro}"/>`+TX(L2+100,16,PHN('neutro'),'start','#0b2827',11.5)+`<circle cx="${L2+170}" cy="12" r="5" fill="${C.nina}"/>`+TX(L2+180,16,PHN('nina'),'start','#0b2827',11.5)+TX(W2-6,16,L.welchNote,'end','#4b6866',10.5);
  s2.innerHTML=t;
}

/* ================= modelos, catálogo e limites ================= */
function renderCatalogModels(){
  const tc={}; PT.forEach(p=>{tc[p.trig]=(tc[p.trig]||0)+1});
  const order=['downpour','rain','continuous_rain','tropical_cyclone','monsoon','snowfall_snowmelt','earthquake','unknown'];
  const other=total-order.reduce((s,k)=>s+(tc[k]||0),0);
  const pal={downpour:'#005453',rain:'#16aba9',continuous_rain:'#6fcfc8',tropical_cyclone:'#2f7a77',monsoon:'#9adcd5',snowfall_snowmelt:'#4f9fd1',earthquake:'#f55d5d',unknown:'#c9d6d5',other:'#e5a39b'};
  const segs=order.map(k=>[k,tc[k]||0]).concat([['other',other]]), nm=k=>k==='other'?L.others:trigName(k);
  $('#trigger-bar').innerHTML=segs.map(([k,n])=>`<span style="width:${n/total*100}%;background:${pal[k]}" title="${nm(k)}: ${fmt(n)}"></span>`).join('');
  $('#trigger-legend').innerHTML=segs.map(([k,n])=>`<span><i style="background:${pal[k]}"></i>${nm(k)} <span class="mono">${nf(n/total*100,1)}%</span></span>`).join('');

  const svg=$('#year-chart'), W=640,H=300,Lm=46,R=10,T=20,B=30, yc={};
  PT.forEach(p=>{if(p.year>=2007&&p.year<=2017) yc[p.year]=(yc[p.year]||0)+1});
  const ys=Object.keys(yc).map(Number).sort(), mx=Math.max(...Object.values(yc)), ticks=niceTicks(0,mx*1.08), top=ticks[ticks.length-1], bw=(W-Lm-R)/ys.length, Yp=v=>T+(top-v)/top*(H-T-B);
  let s='';
  ticks.forEach(t=>{s+=`<line x1="${Lm}" x2="${W-R}" y1="${Yp(t)}" y2="${Yp(t)}" stroke="rgba(11,40,39,.1)"/>`+TX(Lm-8,Yp(t)+4,fmt(t),'end','#4b6866',11,MONO);});
  ys.forEach((y,i)=>{const x=Lm+i*bw+bw*.18, w=bw*.64, ph=annualPhase(y), c=ph==='nino'?C.nino:ph==='nina'?C.nina:'#16aba9'; s+=`<rect x="${x}" y="${Yp(yc[y])}" width="${w}" height="${Yp(0)-Yp(yc[y])}" rx="5" fill="${c}" fill-opacity=".85"><title>${y}: ${fmt(yc[y])} ${L.evs}${ph?' · '+PHN(ph):''}</title></rect>`+TX(x+w/2,H-10,String(y).slice(2),'middle','#4b6866',11,MONO);});
  s+=TX(Lm,12,L.yearChart,'start','#4b6866',11);
  svg.innerHTML=s;
  const me=Math.max(...CAT.cmp.map(c=>c[1])), mf=Math.max(...CAT.cmp.map(c=>c[2]));
  $('#cmp').innerHTML=`<span></span><span style="color:#4b6866">${L.cmpLeg}</span><span></span>`+CAT.cmp.map(([c,e,f])=>`<span>${L.ctry[c]||c}</span><span style="display:grid;gap:3px"><span class="bar" style="width:${Math.max(1,e/me*100)}%;background:#16aba9"></span><span class="bar" style="width:${Math.max(1,f/mf*100)}%;background:#f55d5d"></span></span><span class="mono" style="text-align:right">${fmt(e)} · ${fmt(f)}</span>`).join('');
  const us=CAT.cmp.find(c=>c[0]==='United States'), ind=CAT.cmp.find(c=>c[0]==='India');
  $('#l1-p').textContent=L.l1({ue:fmt(us[1]), uf:fmt(us[2]), ie:fmt(ind[1]), if:fmt(ind[2])});

  function imp(id, list, names){
    const top=list.slice(0,8), mx=Math.max(...top.map(d=>d[1])), W=520, Lm=230, rh=34, svg=$('#'+id); let s='';
    top.forEach(([n,v],i)=>{const y=6+i*rh, w=Math.max(2,(W-Lm-56)*Math.max(v,0)/mx);
      s+=TX(0,y+16,names[n]||n,'start','#0b2827',13)+`<rect x="${Lm}" y="${y+4}" width="${W-Lm-56}" height="16" rx="8" fill="#e6efef"/><rect x="${Lm}" y="${y+4}" width="${w}" height="16" rx="8" fill="${i===0?'#f55d5d':'#16aba9'}"/>`+TX(Lm+w+8,y+16,nf(v,3),'start','#4b6866',11,MONO);});
    svg.setAttribute('viewBox',`0 0 ${W} ${top.length*rh+8}`); svg.innerHTML=s;
  }
  const m1=TM.metrics, m2=G.metrics;
  $('#m1-metrics').innerHTML=L.m1m({auc:nf(m1.auc,2), base:nf(m1.base_auc,2), time:nf(m1.auc_time,2), rec:Math.round(m1.recall_alto*100)+'%', fpr:Math.round((1-m1.spec_alto)*100)})
    .map(([a,b,c])=>`<div><dt>${a}</dt><dd>${b}</dd><span class="vs">${c}</span></div>`).join('');
  $('#m2-metrics').innerHTML=L.m2m({auc:nf(m2.auc,2), base:nf(m2.base_auc,2), top:Math.round(m2.top10*100)+'%', btop:Math.round(m2.base_top10*100)+'%', ap:nf(m2.ap,2), pr:nf(m2.pos_rate,3)})
    .map(([a,b,c])=>`<div><dt>${a}</dt><dd>${b}</dd><span class="vs">${c}</span></div>`).join('');
  imp('m1-imp', TM.imp, L.imp1);
  imp('m2-imp', G.imp, L.imp2);
}

/* ================= troca de idioma ================= */
function renderAll(){
  applyStatic(); renderHeroAbstract(); drawLayer(); renderVarChips(); renderSuggest();
  renderEnsoSection(); renderCatalogModels(); renderCompare(); updateSaveBtn();
  if(current){ renderHeader(current.pl); renderHistory(current.pl); if(current.A) renderPlace(current.pl, current.A); }
  if(status.k) setStatus(status.k, status.args);
}
document.querySelector('.lang').addEventListener('click',e=>{
  const b=e.target.closest('button[data-lang]'); if(!b||b.dataset.lang===lang) return;
  lang=b.dataset.lang; L=I18N.str[lang]; store.set('dd-lang',lang); renderAll();
});

/* equações (não mudam com o idioma) */
if(window.katex) document.querySelectorAll('.eq[data-tex]').forEach(el=>{ try{ katex.render(el.dataset.tex, el, {displayMode:true, throwOnError:false}); }catch(e){ el.textContent=el.dataset.tex; } });

/* ================= início ================= */
renderAll(); paintGlobeMarks();
selectPlace({name:'Petrópolis', sub:'Rio de Janeiro, Brasil', lat:-22.505, lng:-43.1786}, {fly:true, scroll:false});
})().catch(err=>{ console.error(err); const s=document.getElementById('pl-status'); if(s){s.className='status error'; const L=(window.I18N&&I18N.str.pt)||{}; s.textContent=L.init_err||'Falha ao iniciar o app.';} });

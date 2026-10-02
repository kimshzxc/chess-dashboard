const $ = (s)=>document.querySelector(s);
const esc = (s)=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const clk = (s)=> s==null?'-':`${Math.floor(Math.round(s)/60)}:${String(Math.round(s)%60).padStart(2,'0')}`;
const ev = (cp)=> cp==null?'-':Math.abs(cp)>=9000 ? (cp>0?'#승':'#패') : ((cp>0?'+':'')+(cp/100).toFixed(1));
const evW = (cp)=> cp==null?'-':Math.abs(cp)>=9000 ? ('M'+Math.round((10000-Math.abs(cp))/10)) : ((cp>0?'+':'')+(cp/100).toFixed(1));
const mv = (w)=> `${w.move}.${w.mover==='w'?'':'..'}${w.san}`;
const pct=(v)=> v==null?'-':v+'%';
const PH={opening:'오프닝',middlegame:'중반',endgame:'엔드게임'};
const gameId=(url)=> (url||'').split('/').pop();
const RED='#d03b3b', GREEN='#0ca30c', BLUE='#2a78d6', GRAY='#8a8883';

/* ---------- 테마 (체스닷컴 판 색상 프리셋 + 기물 세트) ---------- */
const GRAIN=true;
const BOARDS={
  wood:{name:'나무 (Dark Wood)',l:'#C8AA77',d:'#815A37',hl:'rgba(255,255,51,.5)',tex:true},
  walnut:{name:'호두나무 (Walnut)',l:'#BCA07C',d:'#75543B',hl:'rgba(255,255,51,.5)',tex:true},
  burled:{name:'옹이나무 (Burled Wood)',l:'#E9C49C',d:'#764226',hl:'rgba(255,255,51,.5)',tex:true},
  green:{name:'초록 (Green)',l:'#EBECD0',d:'#739552',hl:'rgba(255,255,51,.5)'},
  brown:{name:'갈색',l:'#EDD6B0',d:'#B88762',hl:'rgba(255,255,51,.5)'},
  blue:{name:'파랑',l:'#EAE9D2',d:'#4B7399',hl:'rgba(255,255,51,.5)'},
  purple:{name:'보라',l:'#EFEFEF',d:'#8877B7',hl:'rgba(255,255,51,.5)'},
  icy:{name:'얼음바다',l:'#E8EEF2',d:'#5A7E9B',hl:'rgba(255,255,51,.5)'},
  gray:{name:'회색',l:'#DEE3E6',d:'#8B8B8B',hl:'rgba(255,255,51,.5)'},
  bubblegum:{name:'버블검',l:'#FEF3F5',d:'#F9A8C9',hl:'rgba(120,120,255,.4)'},
};
const PSETS={maestro:'마에스트로 (Neo와 비슷)',cburnett:'클래식',merida:'메리다',alpha:'알파',california:'캘리포니아'};
let THEME={v:2,board:'wood',pieces:'maestro'};
try{ const t=JSON.parse(localStorage.getItem('chess-theme')||'null'); if(t&&t.v>=2&&BOARDS[t.board]&&PSETS[t.pieces]) THEME=t; }catch(e){}
function applyTheme(){
  const b=BOARDS[THEME.board]; const r=document.documentElement.style;
  r.setProperty('--sq-l',b.l); r.setProperty('--sq-d',b.d); r.setProperty('--sq-hl',b.hl);
  document.documentElement.dataset.tex = b.tex?'1':'0';
  document.querySelectorAll('svg.board use').forEach(u=>{ const id=u.getAttribute('href').split('-').pop(); u.setAttribute('href',`#${THEME.pieces}-${id}`); });
  document.querySelectorAll('.sw[data-board]').forEach(x=>x.classList.toggle('on',x.dataset.board===THEME.board));
  document.querySelectorAll('.sw[data-pieces]').forEach(x=>x.classList.toggle('on',x.dataset.pieces===THEME.pieces));
  try{localStorage.setItem('chess-theme',JSON.stringify(THEME))}catch(e){}
}
function themePanel(){
  let h=`<div class="tpanel" id="tpanel"><div class="lab">판 색상</div><div class="row">`;
  for(const [k,b] of Object.entries(BOARDS)) h+=`<span class="sw" data-board="${k}"><i><b style="background:${b.l}"></b><b style="background:${b.d}"></b><b style="background:${b.d}"></b><b style="background:${b.l}"></b></i>${b.name}</span>`;
  h+=`</div><div class="lab">기물</div><div class="row">`;
  for(const [k,n] of Object.entries(PSETS)) h+=`<span class="sw" data-pieces="${k}"><svg viewBox="0 0 100 100"><use href="#${k}-wN" width="100" height="100"/></svg>${n}</span>`;
  return h+`</div><div class="lab">체스닷컴 Neo 기물은 저작권 때문에 그대로 넣을 수 없어, 가장 비슷한 무료 세트(마에스트로)를 기본으로 씁니다. 나무 판 색은 체스닷컴 Dark Wood 판에서 추출했습니다.</div></div>`;
}
document.addEventListener('click',(e)=>{
  const tb=e.target.closest('#tbtn'); if(tb){ $('#tpanel').classList.toggle('open'); return; }
  const t=e.target.closest('.sw'); if(!t) return;
  if(t.dataset.board) THEME.board=t.dataset.board; if(t.dataset.pieces) THEME.pieces=t.dataset.pieces; THEME.v=2; applyTheme();
});

/* ---------- 체스판 SVG ---------- */
const FILES='abcdefgh';
function parseFen(fen){
  const rows=fen.split(' ')[0].split('/'); const out=[];
  rows.forEach((r,ri)=>{let f=0; for(const ch of r){ if(/\d/.test(ch)) f+=+ch; else { out.push({sq:FILES[f]+(8-ri), p:(ch===ch.toUpperCase()?'w':'b')+ch.toUpperCase()}); f++; } }});
  return out;
}
function sqXY(sq,flip){ let x=FILES.indexOf(sq[0]), y=8-(+sq[1]); if(flip){x=7-x;y=7-y;} return [x*100,y*100]; }
function arrow(from,to,color,flip){
  const [x1,y1]=sqXY(from,flip).map(v=>v+50),[x2,y2]=sqXY(to,flip).map(v=>v+50);
  const dx=x2-x1,dy=y2-y1,len=Math.hypot(dx,dy); if(!len) return '';
  const ux=dx/len,uy=dy/len, head=28, w=11, ex=x2-ux*head, ey=y2-uy*head, px=-uy, py=ux;
  return `<line x1="${x1+ux*22}" y1="${y1+uy*22}" x2="${ex}" y2="${ey}" stroke="${color}" stroke-width="${w}" stroke-linecap="round" opacity=".85"/>
  <polygon points="${x2},${y2} ${ex+px*18},${ey+py*18} ${ex-px*18},${ey-py*18}" fill="${color}" opacity=".85"/>`;
}
function boardSVG(fen, o={}){
  const flip=!!o.flip; let h=`<svg class="board" viewBox="0 0 800 800" xmlns="http://www.w3.org/2000/svg">`;
  for(let r=0;r<8;r++) for(let f=0;f<8;f++){ const light=(r+f)%2===0; h+=`<rect x="${f*100}" y="${r*100}" width="100" height="100" fill="var(${light?'--sq-l':'--sq-d'})"/>`; }
  if(GRAIN) h+=`<use class="grain" href="#grain-img" opacity=".55" style="mix-blend-mode:overlay"/>`;
  for(const sq of (o.last||[])){ const [x,y]=sqXY(sq,flip); h+=`<rect x="${x}" y="${y}" width="100" height="100" fill="var(--sq-hl)"/>`; }
  for(let i=0;i<8;i++){ const fl=flip?FILES[7-i]:FILES[i], rk=flip?i+1:8-i;
    h+=`<text x="${i*100+4}" y="796" font-size="22" fill="${i%2?'var(--sq-l)':'var(--sq-d)'}" font-family="system-ui" font-weight="600">${fl}</text>`;
    h+=`<text x="784" y="${i*100+24}" font-size="22" fill="${i%2?'var(--sq-d)':'var(--sq-l)'}" font-family="system-ui" font-weight="600">${rk}</text>`; }
  for(const {sq,p} of parseFen(fen)){ const [x,y]=sqXY(sq,flip); h+=`<use href="#${THEME.pieces}-${p}" x="${x}" y="${y}" width="100" height="100"/>`; }
  for(const [uci,color] of (o.arrows||[])){ if(uci) h+=arrow(uci.slice(0,2),uci.slice(2,4),color,flip); }
  return h+'</svg>';
}

/* ---------- 뷰어 ---------- */
const VIEWERS={}; let vid=0;
function viewer(spec){ const id='v'+(++vid); VIEWERS[id]={spec,line:0,idx:0}; return `<div class="viewer" id="${id}"></div>`; }
function drawViewer(id){
  const v=VIEWERS[id], el=document.getElementById(id); if(!el||!v) return;
  const line=v.spec.lines[v.line], st=line.states[v.idx];
  let h=boardSVG(st.fen,{flip:v.spec.flip,arrows:st.arrows,last:st.last});
  if(v.spec.lines.length>1) h+=`<div class="vtabs">`+v.spec.lines.map((l,i)=>`<span class="btn ${l.cls||''} ${i===v.line?'on':''}" data-v="${id}" data-line="${i}">${esc(l.label)}</span>`).join('')+`</div>`;
  h+=`<div class="cap">${st.caption||''}</div>`;
  h+=`<div class="vctl"><span class="btn nav" data-v="${id}" data-go="0">⏮</span><span class="btn nav" data-v="${id}" data-go="-1">‹</span><span class="btn nav" data-v="${id}" data-go="1">›</span><span class="btn nav" data-v="${id}" data-go="9">⏭</span></div>`;
  h+=`<div class="moves">`;
  line.states.forEach((s,i)=>{ if(i===0) return; if(s.num) h+=`<span class="num">${s.num}</span>`; h+=`<span class="${i===v.idx?'cur':''} ${s.bad?'bad':''}" data-v="${id}" data-idx="${i}">${esc(s.san)}</span>`; });
  el.innerHTML=h+`</div>`;
}
document.addEventListener('click',(e)=>{
  const t=e.target.closest('[data-v]'); if(!t) return;
  const v=VIEWERS[t.dataset.v]; if(!v) return;
  if(t.dataset.line!==undefined){ v.line=+t.dataset.line; v.idx=0; }
  else if(t.dataset.idx!==undefined){ v.idx=+t.dataset.idx; }
  else if(t.dataset.go!==undefined){ const n=v.spec.lines[v.line].states.length; const g=+t.dataset.go; v.idx = g===0?0 : g===9? n-1 : Math.max(0,Math.min(n-1,v.idx+g)); }
  drawViewer(t.dataset.v);
});
function drawAll(root){ (root||document).querySelectorAll('.viewer').forEach(el=>{ if(!el.innerHTML) drawViewer(el.id); }); }

/* 실수 국면 뷰어: 정답 수순 / 내 수와 반격 */
function blunderViewer(w){
  const flip=w.color==='b'||w.mover==='b';
  const start={fen:w.fen,arrows:[[w.uci,RED],[w.best_uci,GREEN]],caption:`<span style="color:${RED}">■</span> 내가 둔 수 ${esc(w.san)} &nbsp; <span style="color:${GREEN}">■</span> 정답 ${esc(w.best)}`};
  const lines=[]; const best=(w.best_line||[]);
  if(best.length){
    const states=[start]; let mover=w.mover, move=w.move;
    best.forEach((s,i)=>{ states.push({fen:s.fen,san:s.san,num:mover==='w'?`${move}.`:(i===0?`${move}...`:''),last:[s.uci.slice(0,2),s.uci.slice(2,4)],
      caption:i===0?`정답 ${esc(s.san)} 을 두면 평가 ${ev(w.cp_before)} 유지`:`정답 수순 계속 (${i+1}수째)`});
      if(mover==='b') move++; mover=mover==='w'?'b':'w'; });
    lines.push({label:'정답 수순',cls:'green',states});
  }
  { const ref=(w.refutation||[]); const states=[start]; let mover=w.mover, move=w.move;
    states.push({fen:w.after_fen||w.fen,san:w.san,bad:true,num:mover==='w'?`${move}.`:`${move}...`,last:[w.uci.slice(0,2),w.uci.slice(2,4)],caption:`내가 둔 ${esc(w.san)} → 평가 ${ev(w.cp_before)} 에서 ${ev(w.cp_after)} 로`});
    if(mover==='b') move++; mover=mover==='w'?'b':'w';
    ref.forEach((s,i)=>{ states.push({fen:s.fen,san:s.san,num:mover==='w'?`${move}.`:(i===0?`${move}...`:''),last:[s.uci.slice(0,2),s.uci.slice(2,4)],caption:i===0?`상대의 최선 반격 ${esc(s.san)}`:'반격 수순 계속'});
      if(mover==='b') move++; mover=mover==='w'?'b':'w'; });
    lines.push({label:'내 수와 반격',cls:'red',states});
  }
  return viewer({flip,lines});
}

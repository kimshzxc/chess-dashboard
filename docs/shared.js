const $ = (s)=>document.querySelector(s);
const esc = (s)=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const clk = (s)=> s==null?'-':`${Math.floor(Math.round(s)/60)}:${String(Math.round(s)%60).padStart(2,'0')}`;
const ev = (cp)=> cp==null?'-':Math.abs(cp)>=9000 ? (cp>0?'#승':'#패') : ((cp>0?'+':'')+(cp/100).toFixed(1));
const evW = (cp)=> cp==null?'-':Math.abs(cp)>=9000 ? ('M'+Math.round((10000-Math.abs(cp))/10)) : ((cp>0?'+':'')+(cp/100).toFixed(1));
const mv = (w)=> `${w.move}.${w.mover==='w'?'':'..'}${w.san}`;
const pct=(v)=> v==null?'-':v+'%';
const PH={opening:'오프닝',middlegame:'중반',endgame:'엔드게임'};
const gameId=(url)=> (url||'').split('/').pop();
const RED='#e5484d', GREEN='#2fb564', BLUE='#3b82f6', GRAY='#8a8883';

/* ---------- 실수 유형: 이름·설명·두기 전 규칙·체크 질문 (키는 pipeline.py 의 CAT_KEYS 와 같다) ---------- */
const CATG={give:'기물을 내줌',blind:'상대 수를 못 봄',miss:'내 기회를 놓침',plan:'조용한 판단 실수'};
const CATS={
  into_capture:{n:'잡히는 칸에 둠',g:'give',d:'기물을 옮긴 바로 그 칸에서 잡혔습니다.',rule:'도착할 칸을 노리는 상대 기물과 지키는 내 기물의 수를 세고 둔다.',q:'놓으려는 칸을 상대가 잡을 수 있나?'},
  ignored_threat:{n:'걸린 기물을 그대로 둠',g:'give',d:'이미 공격받고 있던 기물을 두고 다른 수를 뒀습니다.',rule:'상대가 둔 직후 "저 수가 무엇을 노리나"부터 본다. 공격받는 기물이 있으면 그것부터 해결한다.',q:'상대의 방금 수가 내 기물을 노리고 있나?'},
  unguard:{n:'수비를 풀어줌',g:'give',d:'지키던 기물을 떼거나 길을 열어서 다른 기물이 잡혔습니다.',rule:'움직이려는 기물이 지금 무엇을 지키고 무엇을 막고 있는지 확인하고 뗀다.',q:'이 기물을 떼면 무엇이 무방비가 되나?'},
  bad_trade:{n:'손해 보는 잡기·교환',g:'give',d:'잡았지만 되잡히거나 교환 결과가 손해였습니다.',rule:'잡기 전에 교환 순서를 끝까지 센다. 내가 내주는 것과 얻는 것을 비교한다.',q:'이 교환을 끝까지 세면 누가 이득인가?'},
  allowed_tactic:{n:'상대의 다음 수를 못 봄',g:'blind',d:'내 수 바로 다음에 상대의 체크·잡는 수·새 위협 한 방이 있었습니다.',rule:'수를 정한 뒤 손을 떼기 전에 상대의 체크, 잡는 수, 위협을 한 번 훑는다.',q:'이 수를 두면 상대의 체크·잡는 수·위협은 무엇인가?'},
  allowed_mate:{n:'외통을 허용',g:'blind',d:'이 수로 상대에게 강제 외통이 생겼습니다.',rule:'상대 기물이 내 킹 근처에 모이면 상대의 모든 체크와 킹이 도망칠 칸부터 센다.',q:'상대가 체크하면 내 킹이 도망칠 칸이 있나?'},
  missed_capture:{n:'잡을 수 있는 걸 안 잡음',g:'miss',d:'잡는 수가 최선이었는데 다른 수를 뒀습니다.',rule:'내 차례마다 잡을 수 있는 기물을 전부 본다. 상대의 방금 수가 무엇을 무방비로 만들었는지 확인한다.',q:'지금 잡을 수 있는 것을 전부 봤나?'},
  missed_tactic:{n:'체크로 시작하는 수를 놓침',g:'miss',d:'체크로 시작하는 강한 수가 있었는데 놓쳤습니다.',rule:'후보 수는 체크, 잡는 수, 위협 순서로 찾는다.',q:'둘 수 있는 체크를 전부 봤나?'},
  missed_mate:{n:'외통을 놓침',g:'miss',d:'강제 외통이 있었는데 다른 수를 뒀습니다.',rule:'상대 킹이 몰려 있으면 모든 체크를 끝까지 계산한다.',q:'체크로 끝낼 수 있나?'},
  opening:{n:'오프닝 전개 실수',g:'plan',d:'10수 안에서, 당장 기물을 잃지는 않지만 전개·중앙·킹 안전에서 손해를 본 수입니다.',rule:'10수 전에는 안 나온 기물, 캐슬링, 중앙이 먼저다. 같은 기물을 두 번 움직이기 전에 한 번 더 본다.',q:'아직 안 나온 기물이 있나?'},
  middlegame:{n:'중반 판단 실수',g:'plan',d:'당장의 전술은 아니지만 엔진이 뚜렷이 나쁘게 본 중반의 수입니다.',rule:'급한 전술이 없으면 가장 나쁜 내 기물을 개선한다. 폰은 되돌릴 수 없으니 밀기 전에 한 번 더 본다.',q:'내 기물 중 가장 일을 안 하는 것은?'},
  endgame:{n:'엔드게임 기술',g:'plan',d:'엔드게임에서 엔진이 뚜렷이 나쁘게 본 수입니다.',rule:'킹을 중앙으로 보내고, 통과폰을 밀고, 룩은 폰 뒤에 둔다.',q:'내 킹이 일하고 있나?'},
};
const catOf=(k)=>CATS[k]||{n:k||'',g:'plan',d:'',rule:'',q:''};
const catTag=(k,cls)=>k?`<span class="ctag ${cls||''}">${esc(catOf(k).n)}</span>`:'';

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
  document.querySelectorAll('.sw[data-mode]').forEach(x=>x.classList.toggle('on',x.dataset.mode===MODE));
  try{localStorage.setItem('chess-theme',JSON.stringify(THEME))}catch(e){}
}
/* 화면 모드: 기본 짙은 톤. 'light' 를 고르면 밝은 톤 */
let MODE='dark'; try{ MODE=localStorage.getItem('chess-mode')||'dark'; }catch(e){}
function applyMode(){
  if(MODE==='light') document.documentElement.dataset.mode='light'; else delete document.documentElement.dataset.mode;
  const m=document.querySelector('meta[name="theme-color"]'); if(m) m.content=MODE==='light'?'#f4f5f7':'#0e1014';
  document.querySelectorAll('.sw[data-mode]').forEach(x=>x.classList.toggle('on',x.dataset.mode===MODE));
  try{localStorage.setItem('chess-mode',MODE)}catch(e){}
}
const ICON={
  home:'<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  games:'<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  mistakes:'<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
  puzzle:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  stats:'<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  sliders:'<path d="M4 6h8M16 6h4M4 12h2M10 12h10M4 18h10M18 18h2"/><circle cx="14" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="18" r="2"/>',
  back:'<path d="M15 5l-7 7 7 7"/>',
};
const icon=(n)=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${ICON[n]}</svg>`;
/* 하단 탭바 (세 페이지 공용). body[data-tab] 이 현재 탭 */
function tabbar(){
  const cur=document.body.dataset.tab||'';
  const items=[['home','홈','index.html#home'],['games','게임','index.html#games'],['mistakes','복기','index.html#mistakes'],['puzzle','퍼즐','puzzle.html'],['stats','통계','index.html#stats']];
  return `<nav class="tabbar" id="tabbar">`+items.map(([k,n,u])=>`<a href="${u}" data-tab="${k}" class="${k===cur?'on':''}">${icon(k)}${n}</a>`).join('')+`</nav>`;
}
document.body.insertAdjacentHTML('beforeend',tabbar());
{ const tb=document.getElementById('tbtn'); if(tb) tb.innerHTML=icon('sliders')+'테마'; }
function themePanel(){
  let h=`<div class="tpanel" id="tpanel"><div class="lab">화면</div><div class="row"><span class="sw mode" data-mode="dark">짙게</span><span class="sw mode" data-mode="light">밝게</span></div><div class="lab">판 색상</div><div class="row">`;
  for(const [k,b] of Object.entries(BOARDS)) h+=`<span class="sw" data-board="${k}"><i><b style="background:${b.l}"></b><b style="background:${b.d}"></b><b style="background:${b.d}"></b><b style="background:${b.l}"></b></i>${b.name}</span>`;
  h+=`</div><div class="lab">기물</div><div class="row">`;
  for(const [k,n] of Object.entries(PSETS)) h+=`<span class="sw" data-pieces="${k}"><svg viewBox="0 0 100 100"><use href="#${k}-wN" width="100" height="100"/></svg>${n}</span>`;
  return h+`</div><div class="note">체스닷컴 Neo 기물은 저작권 때문에 그대로 넣을 수 없어, 가장 비슷한 무료 세트(마에스트로)를 기본으로 씁니다. 나무 판 색은 체스닷컴 Dark Wood 판에서 추출했습니다.</div></div>`;
}
document.addEventListener('click',(e)=>{
  const tb=e.target.closest('#tbtn'); if(tb){ $('#tpanel').classList.toggle('open'); return; }
  const t=e.target.closest('.sw'); if(!t) return;
  if(t.dataset.mode){ MODE=t.dataset.mode; applyMode(); return; }
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

/* ---------- 선 그래프 크로스헤어·툴팁 (세 페이지 공용) ----------
   CHARTS[svg id] = {N, L, pw, W, x(i), ys(i,k), tip(i), pick?(i)}
   tip(i) 는 문자열, 또는 {head, rows:[{c:색, k:계열 이름, v:값}]}. 값은 textContent 로만 넣는다. */
const CHARTS={};
function chartHide(svg){ const g=svg.querySelector('.xc'); if(g) g.style.display='none'; const tip=svg.parentElement.querySelector('.tip'); if(tip) tip.classList.remove('on'); }
function chartShow(svg,i){
  const C=CHARTS[svg.id]; if(!C) return;
  const g=svg.querySelector('.xc'); if(!g) return; g.style.display=''; const X=C.x(i).toFixed(1);
  const l=g.querySelector('.xc-l'); l.setAttribute('x1',X); l.setAttribute('x2',X);
  g.querySelectorAll('.xc-d').forEach((d,k)=>{ const y=C.ys(i,k); if(y==null){ d.style.display='none'; } else { d.style.display=''; d.setAttribute('cx',X); d.setAttribute('cy',y.toFixed(1)); } });
  const tip=svg.parentElement.querySelector('.tip'); const t=C.tip(i); tip.replaceChildren();
  if(typeof t==='string') tip.textContent=t;
  else { const hd=document.createElement('span'); hd.className='hd'; hd.textContent=t.head; tip.append(hd);
    for(const r of t.rows){ const row=document.createElement('span'); row.className='row'; const key=document.createElement('i'); key.style.background=r.c;
      const val=document.createElement('b'); val.textContent=r.v; const nm=document.createElement('small'); nm.textContent=r.k; row.append(key,val,nm); tip.append(row); } }
  tip.classList.add('on');
}
function chartMove(e){
  const svg=e.target.closest&&e.target.closest('svg.xchart'); if(!svg) return; const C=CHARTS[svg.id]; if(!C) return;
  const r=svg.getBoundingClientRect(); const px=(e.clientX-r.left)/r.width*C.W;
  const i=Math.max(0,Math.min(C.N-1,Math.round((px-C.L)/C.pw*(C.N-1))));
  chartShow(svg,i); if(e.type==='pointerdown'&&C.pick) C.pick(i);
}
document.addEventListener('pointermove',chartMove);
document.addEventListener('pointerdown',chartMove);
/* 터치: 누른 값이 손을 떼도 남고, 그래프 밖을 누르면 사라진다. 마우스: 그래프를 벗어나면 사라진다. */
document.addEventListener('pointerdown',(e)=>{ const inside=e.target.closest&&e.target.closest('svg.xchart'); document.querySelectorAll('svg.xchart').forEach(s=>{ if(s!==inside) chartHide(s); }); });
document.addEventListener('pointerout',(e)=>{ if(e.pointerType!=='mouse') return; const svg=e.target.closest&&e.target.closest('svg.xchart'); if(svg&&!(e.relatedTarget&&svg.contains(e.relatedTarget))) chartHide(svg); });

/* ---------- 설치형 웹앱: 서비스 워커 (온라인이면 항상 최신, 오프라인이면 마지막으로 받은 화면) ---------- */
if('serviceWorker' in navigator && window.isSecureContext){ navigator.serviceWorker.register('sw.js').catch(()=>{}); }

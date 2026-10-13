/* 교본: learn.html[?c=<장 id> | ?cat=<실수 유형> | ?rep=<오프닝 id>]. shared.js 다음에 module 로 로드된다.
   lessons.json 은 lessons/build.py 가 원고(lessons/content.py)에서 만든다. 블록 종류: p, h, list, tip, board(그림), line(넘겨 보는 수순), try(한 수 문제).
   learn-done (localStorage)  {장 id: 읽은 날짜} */
document.body.insertAdjacentHTML('afterbegin', await fetch('pieces.svg').then(r=>r.text()));
const get=(u)=>fetch(u,{cache:'no-cache'}).then(r=>r.ok?r.json():null).catch(()=>null);
const [LES,COACH,BOOK]=await Promise.all([get('lessons.json'),get('coach.json'),get('book.json')]);
$('#tpanel-slot').innerHTML=themePanel(); applyMode(); $('#pnav').innerHTML=practiceNav('learn');
const Q=new URLSearchParams(location.search);
const CH=(LES&&LES.chapters)||[], PARTS=(LES&&LES.parts)||[], OPS=(BOOK&&BOOK.openings)||{};
const VERD={weak:['취약','critical'],weak_hint:['취약 조짐','serious'],strong:['강점','good'],strong_hint:['강점 조짐','good'],even:['평균 수준','']};
const load=(k,d)=>{ try{ const v=JSON.parse(localStorage.getItem(k)||'null'); return v??d; }catch(e){ return d; } };
const save=(k,v)=>{ try{ localStorage.setItem(k,JSON.stringify(v)); }catch(e){} };
const DONE=load('learn-done',{});
const today=()=>new Date(Date.now()+9*3600*1000).toISOString().slice(0,10);
const md=(s)=>esc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`(.+?)`/g,'<span class="mono mv">$1</span>');
const url=(id)=>`learn.html?c=${encodeURIComponent(id)}`;
const weakRep=(c)=>c.rep.map(r=>OPS[r]).find(o=>o&&o.verdict.startsWith('weak'));

/* 어느 장을 열지: c 가 우선, cat·rep 는 해당하는 장 중 안 읽은 첫 장 */
function pick(){
  const by=(f)=>CH.filter(f).sort((a,b)=>(!!DONE[a.id])-(!!DONE[b.id]))[0];
  if(Q.get('c')) return CH.find(c=>c.id===Q.get('c'));
  if(Q.get('cat')) return by(c=>c.cats[0]===Q.get('cat'))||by(c=>c.cats.includes(Q.get('cat')));
  if(Q.get('rep')) return by(c=>c.rep.includes(Q.get('rep')))||CH.find(c=>c.id==='principles');
  return null;
}
const C=pick();

/* ---------- 목차 ---------- */
/* 먼저 읽을 장: 집중 과제(coach.json 의 focus)를 다루는 장과 취약 오프닝의 장 중 안 읽은 것 */
function recommend(){
  const out=[], has=(c)=>out.some(x=>x[0]===c);
  for(const k of (COACH&&COACH.focus)||[]){ const c=CH.find(c=>!DONE[c.id]&&!has(c)&&c.cats[0]===k)||CH.find(c=>!DONE[c.id]&&!has(c)&&c.cats.includes(k)&&c.part!=='mine'); if(c) out.push([c,`집중 과제 · ${catOf(k).n}`]); }
  for(const c of CH){ const o=weakRep(c); if(o&&!DONE[c.id]&&!has(c)&&out.length<5) out.push([c,`${VERD[o.verdict][0]} · ${o.color==='w'?'백':'흑'} ${o.n}판 ${o.score}%`]); }
  return out.slice(0,4);
}
function rowHTML(c,i,why){
  const o=weakRep(c);
  return `<a class="lrow ${DONE[c.id]?'done':''}" href="${url(c.id)}"><span class="no">${DONE[c.id]?'✓':i+1}</span><div class="bd"><div class="tt">${esc(c.title)}</div><div class="nm">${esc(why||c.sub)}</div></div>${!why&&o?`<span class="chip ${VERD[o.verdict][1]}">${VERD[o.verdict][0]}</span>`:''}<span class="mn">${c.min}분</span></a>`;
}
function listHTML(){
  if(!CH.length) return '<div class="empty">교본을 불러오지 못했습니다.</div>';
  const nd=CH.filter(c=>DONE[c.id]).length, rec=recommend();
  let h=`<div class="card lsum"><div class="n">체스 교본 <span class="sub">${CH.length}장 중 ${nd}장 읽음</span></div><div class="sub" style="margin-top:4px">기본기부터 내 오프닝까지 읽고, 판 위에서 한 수씩 넘겨 보고, 직접 두어 봅니다.</div><div class="pbar"><i style="width:${(nd/CH.length*100).toFixed(1)}%"></i></div></div>`;
  if(rec.length) h+=`<div class="lpart"><h2>먼저 읽을 장</h2><div class="sub">내 게임의 실수 유형과 오프닝 성적으로 골랐습니다</div></div><div class="card" id="lrec">${rec.map(([c,why])=>rowHTML(c,CH.indexOf(c),why)).join('')}</div>`;
  for(const p of PARTS){ const cs=CH.filter(c=>c.part===p.id); if(!cs.length) continue;
    h+=`<div class="lpart"><h2>${esc(p.name)}</h2><div class="sub">${esc(p.sub)}</div></div><div class="card">${cs.map(c=>rowHTML(c,CH.indexOf(c))).join('')}</div>`; }
  return h;
}

/* ---------- 본문 ---------- */
const TRY=[];   // {b, sel, wrong, done, shown, cls}
function lineSpec(b){
  return {flip:b.flip,lines:b.lines.map(l=>({label:l.label,states:[{fen:l.fen,caption:l.intro?md(l.intro):'<span class="sub">› 를 눌러 한 수씩 넘겨 보세요.</span>'}].concat(l.plies.map((p,i)=>(
    {fen:p.fen,san:p.san,num:p.num,bad:p.san.includes('?'),last:[p.uci.slice(0,2),p.uci.slice(2,4)],caption:`<b class="mono">${p.num||'…'}${esc(p.san)}</b>${md(p.c)}`})))}))};
}
function blockHTML(b){
  if(b.t==='p') return `<p>${md(b.x)}</p>`;
  if(b.t==='h') return `<h2>${md(b.x)}</h2>`;
  if(b.t==='list') return `<ul>${b.items.map(x=>`<li>${md(x)}</li>`).join('')}</ul>`;
  if(b.t==='tip') return `<div class="rule"><span>${esc(b.k)}</span>${md(b.x)}</div>`;
  if(b.t==='board') return `<div class="fig">${boardSVG(b.fen,{flip:b.flip,last:b.marks,arrows:b.arrows.map(a=>[a,GREEN])})}<div class="figc">${md(b.cap)}</div></div>`;
  if(b.t==='line') return `<div class="fig"><div class="figq">${md(b.cap)}</div>${viewer(lineSpec(b))}</div>`;
  if(b.t==='try'){ TRY.push({b,sel:null,wrong:0,done:false,shown:false,cls:''}); return `<div class="fig try" id="try${TRY.length-1}"></div>`; }
  return '';
}
function drawTry(i){
  const t=TRY[i], b=t.b, el=document.getElementById('try'+i); if(!el) return;
  const mv=[b.uci.slice(0,2),b.uci.slice(2,4)];
  let m='', cls='';
  if(t.done){ cls='ok'; m=`<span class="ic">정답</span><b class="mono">${esc(t.san||b.san)}</b> ${md(b.x)}`; }
  else if(t.shown){ m=`<span class="ic">정답</span><b class="mono">${esc(b.san)}</b> 화살표대로 두어 보세요.`; }
  else if(t.wrong){ cls='ng'; m=`<span class="ic">다시</span>${t.wrong>=2?'움직일 기물을 표시했습니다.':'더 좋은 수가 있습니다. 체크와 잡는 수부터 찾아보세요.'}`; }
  el.innerHTML=`<span class="tag">직접 두어 보기 · ${b.fen.split(' ')[1]==='w'?'백':'흑'} 차례</span><div class="figq">${md(b.q)}</div>
    <div class="tryb ${t.cls}">${boardSVG(t.done?t.after||b.after:b.fen,{flip:b.flip,last:t.done?(t.mv||mv):t.sel?[t.sel]:(!t.shown&&t.wrong>=2?[mv[0]]:[]),arrows:t.shown&&!t.done?[[b.uci,GREEN]]:[]})}</div>
    <div class="trym ${cls}">${m||'<span class="sub">기물을 누르고 갈 칸을 누르세요.</span>'}</div>
    <div class="trya">${t.done?`<span class="btn" data-tryre="${i}">다시 풀기</span>`:`<span class="btn" data-tryshow="${i}">정답 보기</span>`}</div>`;
  applyTheme();
}
function recHTML(c){
  const os=c.rep.map(r=>OPS[r]).filter(Boolean); if(!os.length) return '';
  return `<div class="card myrec">${os.map(o=>`<a href="train.html?o=${encodeURIComponent(o.id)}"><span><span class="side">${o.color==='w'?'백':'흑'}</span>${esc(o.name)} · ${o.n}판 ${o.score}% ${o.verdict==='even'?'':`<span class="chip ${VERD[o.verdict][1]}">${VERD[o.verdict][0]}</span>`}</span><span class="go">내 게임 라인 연습 ›</span></a>`).join('')}</div>`;
}
function chapterHTML(c){
  const i=CH.indexOf(c), nx=CH[i+1], pv=CH[i-1], part=PARTS.find(p=>p.id===c.part)||{};
  const pz=c.cats.map(k=>[k,((COACH&&COACH.cats)||{})[k]]).find(([k,v])=>v&&v.puzzles);
  let h=`<a class="backl" href="learn.html">‹ 교본 목차</a><article class="lesson"><div class="eyebrow">${esc(part.name||'')} · ${i+1}장</div><h1>${esc(c.title)}</h1><div class="sub">${esc(c.sub)} · 약 ${c.min}분</div>${recHTML(c)}`;
  h+=c.blocks.map(blockHTML).join('');
  h+=`<div class="lend"><span class="btn on" id="ldone">${DONE[c.id]?'읽음 ✓':'다 읽었습니다'}${nx?' · 다음 장 ›':''}</span><div class="row2">${pv?`<a class="btn" href="${url(pv.id)}">‹ ${esc(pv.title)}</a>`:''}${pz?`<a class="btn" href="puzzle.html?cat=${pz[0]}">${esc(catOf(pz[0]).n)} 퍼즐 ${pz[1].puzzles}개 ›</a>`:''}</div></div></article>`;
  return h;
}
function squareAt(svg,e,flip){
  const r=svg.getBoundingClientRect(); let fx=Math.floor((e.clientX-r.left)/r.width*8), ry=Math.floor((e.clientY-r.top)/r.height*8);
  if(fx<0||fx>7||ry<0||ry>7) return null; if(flip){ fx=7-fx; ry=7-ry; }
  return FILES[fx]+(8-ry);
}
document.addEventListener('pointerdown',(e)=>{
  const svg=e.target.closest('.tryb svg.board'); if(!svg) return;
  const i=+svg.closest('.try').id.slice(3), t=TRY[i], b=t.b; if(t.done) return;
  const sq=squareAt(svg,e,b.flip); if(!sq) return;
  const turn=b.fen.split(' ')[1], mine=(s)=>{ const x=parseFen(b.fen).find(q=>q.sq===s); return x&&x.p[0]===turn; };
  if(t.sel&&sq!==t.sel&&!mine(sq)){
    const u=t.sel+sq, alt=b.ok.find(a=>a.uci.slice(0,4)===u); t.sel=null;
    if(u===b.uci.slice(0,4)||alt){ t.done=true; t.cls=''; if(alt){ t.san=`${alt.san} (${b.san} 도 정답)`; t.after=alt.after; t.mv=[u.slice(0,2),u.slice(2,4)]; } }
    else { t.wrong++; t.cls='ng'; }
    drawTry(i); if(t.cls==='ng') setTimeout(()=>{ t.cls=''; },400); return; }
  if(mine(sq)){ t.sel=t.sel===sq?null:sq; t.cls=''; drawTry(i); }
});
document.addEventListener('click',(e)=>{
  const sh=e.target.closest('[data-tryshow]'); if(sh){ const t=TRY[+sh.dataset.tryshow]; t.shown=true; t.sel=null; drawTry(+sh.dataset.tryshow); return; }
  const re=e.target.closest('[data-tryre]'); if(re){ const i=+re.dataset.tryre; Object.assign(TRY[i],{sel:null,wrong:0,done:false,shown:false,cls:'',san:null,mv:null}); drawTry(i); return; }
  if(e.target.closest('#ldone')&&C){ DONE[C.id]=DONE[C.id]||today(); save('learn-done',DONE); const nx=CH[CH.indexOf(C)+1]; location.href=nx?url(nx.id):'learn.html'; }
});

if(C){ document.title=`${C.title} · 교본`; $('#main').innerHTML=chapterHTML(C); drawAll($('#main')); TRY.forEach((_,i)=>drawTry(i)); applyTheme(); }
else $('#main').innerHTML=listHTML();
